"""Physical refund interaction, reachability and frozen enumeration checks."""

from dataclasses import replace
import gzip
import importlib.util
import json
from pathlib import Path
import random
import shutil

import pytest
from jsonschema.validators import validator_for

from consequa_x.benchmark.decision_coalition import replay_decision_coalition
from consequa_x.benchmark.decision_shapley import shapley_decisions
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.interaction_export import export_refund_interactions
from consequa_x.benchmark.interaction_mechanisms import (
    COMPONENTS, INTERACTION_MECHANISMS, RefundInteractionMechanism, RefundInteractionPolicy,
)
from consequa_x.benchmark.policy_runner import run_policy_scenario
from consequa_x.benchmark.targets import episode_outcome
from consequa_x.models import EventType


def _audit(root):
    path = Path(__file__).resolve().parents[1] / "scripts" / "audit_refund_interactions.py"
    spec = importlib.util.spec_from_file_location("independent_refund_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.audit(root)


@pytest.mark.parametrize("name", tuple(INTERACTION_MECHANISMS))
def test_physical_four_component_game_matches_independent_reference(name):
    mechanism = INTERACTION_MECHANISMS[name]
    # Cost refusal is checked in the retained exporter separately.
    mechanism = replace(mechanism, max_calls=100)
    for game in ("strict", "on_reach"):
        values = {target: [[] for _ in range(8)] for target in ("action", "consequence", "action_linked_consequence")}
        for component_index, component in enumerate(COMPONENTS):
            factual_seed = 4_020_000 + component_index * 100
            policy = mechanism.make_policy(factual_policy_seed=factual_seed, component=component)
            budget = BudgetedPolicy(policy, 100)
            factual = run_policy_scenario(mechanism.scenario_config(), budget,
                seed=factual_seed, policy_seed=factual_seed, max_attempts=2)
            assert budget.calls == 3
            captures = [event for event in factual.trace.events if event.type is EventType.AGENT_DECISION]
            assert [event.data["policy_reply"]["decision"]["operation"] for event in captures] == ["refund", "retry", "stop"]
            weight = mechanism.component_weights()[component_index]
            for mask in range(8):
                replay = replay_decision_coalition(factual, budget,
                    held_indices=[i for i in range(3) if mask & (1 << i)],
                    continuation_seed=factual_seed + 1 + mask, coalition_game=game)
                outcome = episode_outcome(replay.episode) if replay.episode is not None else None
                for target in values:
                    value = outcome.target_value(target) if outcome is not None else None
                    values[target][mask].append((weight, None if value is None else int(not value)))
                if game == "on_reach":
                    assert replay.status == "completed"
                    assert replay.inactive_held_indices == replay.unreached_held_indices
        reference = mechanism.analytic_reference(coalition_game=game)
        for target, by_mask in values.items():
            for mask, components in enumerate(by_mask):
                positive = [(weight, value) for weight, value in components if weight > 0]
                actual = None if any(value is None for _, value in positive) else sum(weight * value for weight, value in positive)
                expected = reference["targets"][target]["coalition_bad_rates"][mask]
                assert actual == pytest.approx(expected) if expected is not None else actual is None


def test_closed_form_main_case_and_idempotency_removes_retry_interaction():
    targets = INTERACTION_MECHANISMS["refund-p50-q50"].analytic_reference()["targets"]
    assert targets["consequence"]["shapley_values"] == [-.125, .375, 0.]
    assert targets["consequence"]["selection_retry_interaction"] == .25
    assert targets["consequence"]["endpoint_difference"] == .25
    assert targets["action"]["shapley_values"] == [-.5, 0., 0.]
    strict = INTERACTION_MECHANISMS["refund-p50-q50"].analytic_reference(coalition_game="strict")
    assert not strict["targets"]["consequence"]["shapley_eligible"]
    targets = INTERACTION_MECHANISMS["idempotent-p50-q50"].analytic_reference()["targets"]
    assert targets["consequence"]["shapley_values"] == [-.5, 0., 0.]
    assert targets["consequence"]["selection_retry_interaction"] == 0.


def test_frozen_export_all_evidence_separate_gold_and_independent_audit(tmp_path):
    result = export_refund_interactions(tmp_path, source_revision="test-source")
    assert len(result["cases"]) == 8
    assert result["additional_reference_policy_calls"] == 0
    audited = _audit(tmp_path)
    assert audited["passed"] and audited["planned_branches"] == 512
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed" and manifest["completed"] is True
    assert "files" not in manifest and len(manifest["artifacts"]) == 6
    schema = json.loads((tmp_path / "trace-schema.json").read_text(encoding="utf-8"))
    validator = validator_for(schema)(schema)
    with gzip.open(tmp_path / "evidence.jsonl.gz", "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    assert len(rows) == 8 * 2 * 4 * 9
    for row in rows:
        assert "records" not in row and "config" not in row
        if row["trace"] is not None:
            validator.validate(row["trace"])
    main = result["cases"]["refund-p50-q50"]["games"]["on_reach"]
    assert main["targets"]["consequence"]["shapley_values"] == [-.125, .375, 0.]
    assert main["inactive_held_branch_count"] > 0
    assert result["cases"]["refund-p50-q50"]["games"]["strict"]["targets"]["action"]["shapley_values"] is None
    unknown = result["cases"]["unknown-provenance-p50-q50"]["games"]["on_reach"]["targets"]
    assert unknown["consequence"]["numeric_available"]
    assert not unknown["action_linked_consequence"]["numeric_available"]
    lagged = result["cases"]["lagged-readback-p50-q50"]["games"]["on_reach"]["targets"]
    assert lagged["action"]["numeric_available"] and not lagged["consequence"]["numeric_available"]
    budget = result["cases"]["budget-p50-q50"]["games"]["on_reach"]
    assert budget["branch_status_counts"]["failed"] > 0
    assert budget["branch_status_counts"]["unstarted"] > 0
    assert not budget["targets"]["consequence"]["numeric_available"]


def test_protocol_written_before_calls_and_partial_export_has_no_manifest(tmp_path, monkeypatch):
    def interrupted(*args, **kwargs):
        protocol = json.loads((tmp_path / "protocol.json").read_text(encoding="utf-8"))
        assert protocol["source_revision"] == "pre-call-freeze"
        assert len(protocol["schedule"]) == 8
        raise RuntimeError("deliberate interrupted run")

    monkeypatch.setattr("consequa_x.benchmark.interaction_export.run_policy_scenario", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        export_refund_interactions(tmp_path, source_revision="pre-call-freeze", mechanisms=("refund-p50-q50",))
    assert not (tmp_path / "manifest.json").exists()
    with pytest.raises(ValueError, match="empty"):
        export_refund_interactions(tmp_path, source_revision="pre-call-freeze")


@pytest.mark.parametrize("kwargs", [{"seed": True}, {"seed": 3_999_999}, {"source_revision": ""},
    {"mechanisms": ()}, {"mechanisms": ("unknown",)}, {"mechanisms": ("refund-p50-q50",) * 2}])
def test_invalid_export_plan_rejected_before_output(tmp_path, kwargs):
    with pytest.raises(ValueError):
        export_refund_interactions(tmp_path / "invalid", **{"source_revision": "valid", **kwargs})
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("name", ("refund-p50-q50", "idempotent-p50-q50"))
def test_seeded_sampler_uses_actual_payment_world_and_conservative_bounds(name):
    mechanism = INTERACTION_MECHANISMS[name]
    factual_seed = 4_030_000
    policy = mechanism.make_policy(factual_policy_seed=factual_seed)
    factual = mechanism.capture_factual(seed=factual_seed, policy_seed=factual_seed)
    result = shapley_decisions(factual, BudgetedPolicy(policy, 2000), pairs=32,
        samples_per_eval=1, endpoint_samples=32, seed=4_031_000, permutation_seed=24_210_000,
        targets=("action", "consequence", "action_linked_consequence"), coalition_game="on_reach",
        interval_method="hoeffding", endpoint_interval_method="clopper_pearson_difference")
    reference = mechanism.analytic_reference()
    assert all(estimate.status == "estimated" for estimate in result.results)
    for estimate in result.results:
        truth = reference["targets"][estimate.target]["shapley_values"][estimate.decision_index]
        assert abs(estimate.shapley_value - truth) <= .3
        assert estimate.confidence_interval[1] - estimate.confidence_interval[0] > 0
    assert any(branch.replay.inactive_held_indices for branch in result.branches)
    assert policy.metadata["fresh_rule"]["kind"] == "seeded_bernoulli"


def test_seeded_public_choices_match_declared_rng_and_do_not_read_hidden_fields():
    from consequa_x.models import ResponseStatus, ToolResponse
    from consequa_x.policies import PolicyRequest

    policy = RefundInteractionPolicy(.2, .8, 4_040_000)
    selection = PolicyRequest("select", {"public": "refund"}, {"request": "refund"})
    timeout = PolicyRequest("after_response", selection.task, selection.context,
        (ToolResponse(attempt_id="attempt", status=ResponseStatus.TIMEOUT, time_ms=6, provider_request_id="request", result={"code": "timeout"}, action_id="refund"),), 1)
    selected, retried = 0, 0
    for seed in range(24_300_000, 24_301_000, 6):
        first = policy.decide(selection, seed=seed)
        second = policy.decide(timeout, seed=seed + 1)
        assert (first.decision.operation == "refund") == (random.Random(seed).random() < .2)
        assert (second.decision.operation == "retry") == (random.Random(seed + 1).random() < .8)
        selected += first.decision.operation == "refund"
        retried += second.decision.operation == "retry"
    assert 20 <= selected <= 50 and 115 <= retried <= 155


@pytest.mark.parametrize("kwargs", [{"selection_probability": True}, {"retry_probability": float("nan")},
    {"use_idempotency": 1}, {"read_lag_ms": -1}, {"max_calls": 2}])
def test_invalid_mechanism(kwargs):
    with pytest.raises(ValueError):
        RefundInteractionMechanism("invalid", **kwargs)


@pytest.fixture(scope="module")
def manifest_artifact(tmp_path_factory):
    root = tmp_path_factory.mktemp("refund-manifest-source")
    export_refund_interactions(root, source_revision="manifest-source", mechanisms=("refund-p50-q50",))
    return root


@pytest.mark.parametrize("kind", ("canonical", "canonical-status-only", "legacy", "legacy-with-status", "preserved-envelope"))
def test_auditor_accepts_unambiguous_canonical_and_legacy_manifests(tmp_path, manifest_artifact, kind):
    from hashlib import sha256

    root = tmp_path / "artifact"
    shutil.copytree(manifest_artifact, root)
    path = root / "manifest.json"
    canonical = json.loads(path.read_text(encoding="utf-8"))
    legacy = {"completed": True, "files": {
        item["path"]: {key: item[key] for key in ("bytes", "sha256")}
        for item in canonical["artifacts"]}}
    if kind == "canonical":
        manifest = canonical
    elif kind == "canonical-status-only":
        manifest = {"status": "completed", "artifacts": canonical["artifacts"]}
    elif kind == "legacy":
        manifest = legacy
    elif kind == "legacy-with-status":
        manifest = {**legacy, "status": "completed"}
    else:
        backup = root / "export-manifest.json"
        backup.write_text(json.dumps(legacy), encoding="utf-8")
        canonical["artifacts"].append({"path": backup.name, "bytes": backup.stat().st_size,
            "sha256": sha256(backup.read_bytes()).hexdigest()})
        manifest = canonical
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = _audit(root)
    assert result["passed"] and result["actual_policy_calls"] == 98
    assert result["manifest_files_checked"] == (7 if kind == "preserved-envelope" else 6)


@pytest.mark.parametrize("mutation", (
    "both-formats", "neither-format", "duplicate-path", "duplicate-resolved-path", "unsafe-path",
    "path-nonstr", "extra-entry-field", "missing-entry-field", "artifacts-not-list", "empty-artifacts",
    "files-not-dict", "legacy-extra-entry-field", "boolean-bytes", "negative-bytes", "wrong-bytes",
    "nonstring-hash", "uppercase-hash", "wrong-hash", "missing-artifact", "extra-file", "missing-status",
    "incomplete-status", "false-completed", "integer-completed", "legacy-incomplete-status", "legacy-incomplete",
    "duplicate-json-key",
))
def test_manifest_validation_rejects_ambiguous_unsafe_or_incomplete_inventory(tmp_path, manifest_artifact, mutation):
    root = tmp_path / "artifact"
    shutil.copytree(manifest_artifact, root)
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    items = manifest["artifacts"]
    if mutation in ("files-not-dict", "legacy-extra-entry-field", "legacy-incomplete-status", "legacy-incomplete"):
        manifest = {"completed": True, "files": {
            item["path"]: {key: item[key] for key in ("bytes", "sha256")} for item in items}}
    if mutation == "both-formats":
        manifest["files"] = {}
    elif mutation == "neither-format":
        manifest.pop("artifacts")
    elif mutation == "duplicate-path":
        items.append(dict(items[0]))
    elif mutation == "duplicate-resolved-path":
        items.append({**items[0], "path": items[0]["path"].upper()})
    elif mutation == "unsafe-path":
        items[0]["path"] = "../README.md"
    elif mutation == "path-nonstr":
        items[0]["path"] = 1
    elif mutation == "extra-entry-field":
        items[0]["extra"] = True
    elif mutation == "missing-entry-field":
        items[0].pop("bytes")
    elif mutation == "artifacts-not-list":
        manifest["artifacts"] = {}
    elif mutation == "empty-artifacts":
        manifest["artifacts"] = []
    elif mutation == "files-not-dict":
        manifest["files"] = []
    elif mutation == "legacy-extra-entry-field":
        next(iter(manifest["files"].values()))["extra"] = True
    elif mutation == "boolean-bytes":
        items[0]["bytes"] = True
    elif mutation == "negative-bytes":
        items[0]["bytes"] = -1
    elif mutation == "wrong-bytes":
        items[0]["bytes"] += 1
    elif mutation == "nonstring-hash":
        items[0]["sha256"] = 1
    elif mutation == "uppercase-hash":
        items[0]["sha256"] = items[0]["sha256"].upper()
    elif mutation == "wrong-hash":
        items[0]["sha256"] = "0" * 64
    elif mutation == "missing-artifact":
        items.pop()
    elif mutation == "extra-file":
        (root / "extra.txt").write_text("unlisted", encoding="utf-8")
    elif mutation == "missing-status":
        manifest.pop("status")
    elif mutation == "incomplete-status":
        manifest["status"] = "partial"
    elif mutation == "false-completed":
        manifest["completed"] = False
    elif mutation == "integer-completed":
        manifest["completed"] = 1
    elif mutation == "legacy-incomplete-status":
        manifest["status"] = "partial"
    elif mutation == "legacy-incomplete":
        manifest["completed"] = False
    encoded = json.dumps(manifest)
    if mutation == "duplicate-json-key":
        encoded = encoded.replace('"status": "completed"', '"status": "completed", "status": "completed"')
    path.write_text(encoded, encoding="utf-8")
    with pytest.raises((AssertionError, OSError)):
        _audit(root)
