"""Dedicated sampler integration, reference eligibility and hostile saved-data checks."""

from copy import deepcopy
from dataclasses import replace
import gzip
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from consequa_x.benchmark import interaction_sampling as study
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED


def _audit_module():
    path = Path(__file__).resolve().parents[1] / "scripts/audit_interaction_sampling.py"
    spec = importlib.util.spec_from_file_location("interaction_sampling_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _small(**changes):
    return study.InteractionSamplingPlan(repeats=1, pairs=2, endpoint_samples=2, **changes)


def test_default_complete_fresh_phase_schedule():
    plan = study.InteractionSamplingPlan()
    entries = study.predeclare_interaction_sampling(plan)
    assert len(entries) == 2048
    assert plan.branches_per_trial == 320
    assert sum(entry.planned_branches for entry in entries) == 655360
    assert entries[0].factual_seed == 20_000_000
    assert entries[-1].continuation_seed + 319 <= MAX_TRIAL_SEED
    for left, right in zip(entries, entries[1:]):
        assert left.continuation_seed + left.planned_branches - 1 < right.factual_seed
    assert min(entry.permutation_seed for entry in entries) > max(
        (entry.continuation_seed + entry.planned_branches - 1) * 6 + 5 for entry in entries
    )
    assert all(
        entry.max_calls == (4 if entry.mechanism == "budget-p50-q50" else 1000) for entry in entries
    )


@pytest.mark.parametrize(
    "change",
    [
        {"repeats": True},
        {"repeats": 0},
        {"pairs": 1},
        {"samples_per_eval": 0},
        {"endpoint_samples": 1},
        {"max_calls": 2},
        {"confidence": True},
        {"confidence": float("nan")},
        {"confidence": 1},
        {"confidence": 10**1000},
        {"seed": 19_999_999},
        {"seed": True},
        {"seed": MAX_TRIAL_SEED},
        {"mechanisms": ("missing",)},
        {"mechanisms": ()},
        {"mechanisms": (["bad"],)},
        {"games": ("strict", "strict")},
        {"games": ["strict"]},
    ],
)
def test_invalid_plans_refuse_before_collection(change):
    with pytest.raises(ValueError):
        study.InteractionSamplingPlan(**change)


def test_interval_variants_share_branches_points_pairs_and_costs():
    plan = _small(mechanisms=("refund-p50-q50",), games=("on_reach",))
    trial = study.run_interaction_trial(plan, study.predeclare_interaction_sampling(plan)[0])
    assert trial.experiment.branches is trial.comparison.branches
    assert trial.experiment.calls == trial.comparison.calls
    for normal, bounded in zip(trial.experiment.results, trial.comparison.results):
        assert normal.shapley_value == bounded.shapley_value
        assert normal.pair_values == bounded.pair_values
        assert normal.status == bounded.status
        assert normal.coverage == bounded.coverage
    record = study.compact_interaction_trial(plan, trial)
    assert len(record["branches"]) == 20
    assert record["calls"]["additional_comparison"] == 0
    assert record["calls"]["total"] == 3 + sum(
        branch["policy_calls"] for branch in record["branches"]
    )
    with pytest.raises(ValueError):
        study.run_interaction_trial(plan, replace(trial.entry, permutation_seed=0))


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    root = tmp_path_factory.mktemp("interaction-sampling") / "study"
    plan = _small()
    result = study.export_interaction_sampling(plan, root, source_revision="test-frozen-source")
    return root, plan, result


def test_full_small_export_passes_independent_audit(exported):
    root, plan, result = exported
    audited = _audit_module().audit(root, "test-frozen-source")
    assert audited["status"] == "passed"
    assert audited["trials"] == 16 and audited["branches"] == 320
    assert audited["actual_policy_calls"] == result["actual_policy_calls"]
    assert audited["generation_calls"] == 0
    assert audited["full_traces"] > 0
    assert result["additional_comparison_policy_calls"] == 0
    files = list((root / "trials").glob("*.jsonl.gz"))
    assert len(files) == 16
    records = []
    for entry in study.predeclare_interaction_sampling(plan):
        with gzip.open(
            root / "trials" / f"{entry.mechanism}__{entry.coalition_game}.jsonl.gz", "rt"
        ) as stream:
            records.append(json.loads(stream.readline()))
    assert study.analyze_interaction_sampling(plan, records) == result


def test_eligibility_refusals_and_boundary_width_are_distinct(exported):
    _, _, result = exported

    def rows(name, game, target, variant="hoeffding_exact_endpoints"):
        return [
            row
            for row in result["coefficient_rows"]
            if (row["mechanism"], row["coalition_game"], row["target"], row["variant"])
            == (name, game, target, variant)
        ]

    assert all(
        row["reference_eligible_trials"] == 0 and row["interval_coverage"]["denominator"] == 0
        for row in rows("refund-p50-q50", "strict", "consequence")
    )
    assert all(
        row["available_estimates"] == 0 and row["refused_estimates"] == 1
        for row in rows("lagged-readback-p50-q50", "on_reach", "consequence")
    )
    assert all(
        row["available_estimates"] == 1
        for row in rows("lagged-readback-p50-q50", "on_reach", "action")
    )
    assert all(
        row["available_estimates"] == 0 and row["reference_eligible_trials"] == 1
        for row in rows("budget-p50-q50", "on_reach", "consequence")
    )
    assert all(
        row["mean_interval_width"] > 0 for row in rows("refund-p100-q100", "strict", "consequence")
    )
    assert all(
        row["mean_interval_width"] == 0
        for row in rows("refund-p100-q100", "strict", "consequence", "normal")
    )
    assert all(
        row["available_estimates"] == 0
        for row in rows("unknown-provenance-p50-q50", "on_reach", "action_linked_consequence")
    )


def test_export_freezes_before_first_call_and_partial_error_retains_schedule(tmp_path, monkeypatch):
    root = tmp_path / "partial"
    original = study.run_interaction_trial
    calls = 0

    def interrupt(plan, entry):
        nonlocal calls
        assert (root / "protocol.json").exists()
        calls += 1
        if calls == 2:
            raise RuntimeError("declared smoke interruption")
        return original(plan, entry)

    monkeypatch.setattr(study, "run_interaction_trial", interrupt)
    with pytest.raises(RuntimeError, match="smoke interruption"):
        study.export_interaction_sampling(_small(), root, source_revision="frozen")
    assert (root / "protocol.json").exists()
    assert not (root / "manifest.json").exists()
    with gzip.open(root / "trials/refund-p50-q50__strict.jsonl.gz", "rt") as stream:
        assert len(stream.readlines()) == 1
    with pytest.raises(ValueError, match="empty"):
        study.export_interaction_sampling(_small(), root, source_revision="frozen")


def _rewrite_manifest(root):
    original = json.loads((root / "manifest.json").read_text())
    original["artifacts"] = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / "manifest.json"
    ]
    (root / "manifest.json").write_text(json.dumps(original))


def _mutate_trial(root, mutation):
    path = root / "trials/refund-p50-q50__on_reach.jsonl.gz"
    with gzip.open(path, "rt") as stream:
        rows = [json.loads(line) for line in stream]
    mutation(rows[0])
    with gzip.open(path, "wt") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_trial",
        "extra_trial",
        "duplicate_slot",
        "wrong_seed",
        "wrong_operation",
        "wrong_label",
        "wrong_calls",
        "wrong_pair",
        "wrong_interval",
        "duplicate_estimate",
        "missing_endpoint",
        "wrong_inactive",
        "wrong_row_schema",
        "wrong_trial_error",
        "wrong_available",
        "wrong_complete",
        "wrong_linked_count",
        "wrong_branch_error",
        "wrong_budget_flag",
        "wrong_receipt_error",
        "wrong_factual_measurement",
        "wrong_factual_error",
        "wrong_method",
        "wrong_local_summary",
        "wrong_degenerate",
        "wrong_endpoint_sum",
        "wrong_endpoint_discrepancy",
        "wrong_summary",
        "missing_summary_row",
        "wrong_reference",
        "wrong_probability",
        "wrong_schedule",
        "wrong_collection_method",
        "wrong_comparison_method",
        "wrong_package_version",
        "wrong_execution_order",
        "wrong_execution_resampling",
        "wrong_execution_workers",
        "wrong_full_slot",
        "wrong_full_receipt",
        "wrong_full_summary",
        "wrong_full_request",
        "wrong_reference_game",
        "extra_file",
        "manifest_duplicate",
        "manifest_path",
        "manifest_bytes",
        "manifest_hash",
    ],
)
def test_independent_auditor_rejects_corruption_even_with_refreshed_hashes(
    exported, tmp_path, corruption
):
    source, _, _ = exported
    root = tmp_path / "corrupt"
    shutil.copytree(source, root)
    if corruption in ("missing_trial", "extra_trial"):
        path = root / "trials/refund-p50-q50__on_reach.jsonl.gz"
        with gzip.open(path, "rt") as stream:
            line = stream.readline()
        with gzip.open(path, "wt") as stream:
            stream.write("" if corruption == "missing_trial" else line + line)
    elif corruption in (
        "duplicate_slot",
        "wrong_seed",
        "wrong_operation",
        "wrong_label",
        "wrong_calls",
        "wrong_pair",
        "wrong_interval",
        "duplicate_estimate",
        "missing_endpoint",
        "wrong_inactive",
        "wrong_row_schema",
        "wrong_trial_error",
        "wrong_available",
        "wrong_complete",
        "wrong_linked_count",
        "wrong_branch_error",
        "wrong_budget_flag",
        "wrong_receipt_error",
        "wrong_factual_measurement",
        "wrong_factual_error",
        "wrong_method",
        "wrong_local_summary",
        "wrong_degenerate",
        "wrong_endpoint_sum",
        "wrong_endpoint_discrepancy",
    ):

        def corrupt(row):
            variant = row["variants"]["normal"]
            if corruption == "duplicate_slot":
                row["branches"][1]["slot_index"] = 0
            elif corruption == "wrong_seed":
                row["slots"][0]["continuation_seed"] += 1
            elif corruption == "wrong_operation":
                row["branches"][0]["decisions"][0]["operation"] = "retry"
            elif corruption == "wrong_label":
                row["branches"][0]["measurement"]["target_values"]["action"] = not row["branches"][
                    0
                ]["measurement"]["target_values"]["action"]
            elif corruption == "wrong_calls":
                row["branches"][0]["policy_calls"] += 1
            elif corruption == "wrong_pair":
                variant["estimates"][0]["pair_values"][0] += 0.125
            elif corruption == "wrong_interval":
                variant["estimates"][0]["confidence_interval"][0] += 0.125
            elif corruption == "duplicate_estimate":
                variant["estimates"][1] = deepcopy(variant["estimates"][0])
            elif corruption == "missing_endpoint":
                variant["endpoint_checks"].pop()
            elif corruption == "wrong_inactive":
                row["branches"][0]["inactive_held_indices"] = [2]
            elif corruption == "wrong_row_schema":
                row["schema_version"] = "forged-schema"
            elif corruption == "wrong_trial_error":
                row["error"] = {"error": "unreported failure"}
            elif corruption == "wrong_available":
                row["branches"][0]["measurement"]["available"] = False
            elif corruption == "wrong_complete":
                row["branches"][0]["measurement"]["complete"] = False
            elif corruption == "wrong_linked_count":
                row["branches"][0]["measurement"]["linked_count"] += 1
            elif corruption == "wrong_branch_error":
                row["branches"][0]["error_type"] = "CallBudgetExceeded"
            elif corruption == "wrong_budget_flag":
                row["branches"][0]["budget_exhausted"] = True
            elif corruption == "wrong_receipt_error":
                row["branches"][0]["decisions"][0]["error"] = "unreported failure"
            elif corruption == "wrong_factual_measurement":
                row["factual"]["measurement"]["target_values"]["action"] = False
            elif corruption == "wrong_factual_error":
                row["factual"]["decisions"][0]["error_type"] = "PolicyError"
            elif corruption == "wrong_method":
                variant["summary"]["method"]["interval_method"] = "exact magic"
            elif corruption == "wrong_local_summary":
                variant["summary"]["policy_calls"] += 1
            elif corruption == "wrong_degenerate":
                variant["estimates"][0]["interval_degenerate"] = not variant["estimates"][0][
                    "interval_degenerate"
                ]
            elif corruption == "wrong_endpoint_sum":
                variant["endpoint_checks"][0]["coefficient_sum"] += 1
            elif corruption == "wrong_endpoint_discrepancy":
                variant["endpoint_checks"][0]["discrepancy"] += 1

        _mutate_trial(root, corrupt)
    elif corruption in ("wrong_summary", "missing_summary_row"):
        path = root / "summary.json"
        value = json.loads(path.read_text())
        if corruption == "wrong_summary":
            value["actual_policy_calls"] += 1
        else:
            value["coefficient_rows"].pop()
        path.write_text(json.dumps(value))
    elif corruption in (
        "wrong_reference",
        "wrong_probability",
        "wrong_schedule",
        "wrong_collection_method",
        "wrong_comparison_method",
        "wrong_package_version",
        "wrong_execution_order",
        "wrong_execution_resampling",
        "wrong_execution_workers",
        "wrong_reference_game",
    ):
        path = root / "protocol.json"
        value = json.loads(path.read_text())
        if corruption == "wrong_reference":
            value["references"]["refund-p50-q50"]["on_reach"]["targets"]["consequence"][
                "shapley_values"
            ][0] = 0
        elif corruption == "wrong_probability":
            value["mechanisms"]["refund-p50-q50"]["selection_probability"] = 0.6
        elif corruption == "wrong_schedule":
            value["trial_schedule"][0]["continuation_seed"] += 1
        elif corruption == "wrong_collection_method":
            value["collection_intervals"]["pair"] = "hoeffding"
        elif corruption == "wrong_comparison_method":
            value["comparison_intervals"]["endpoint"] = "normal"
        elif corruption == "wrong_execution_order":
            value["execution"]["result_order"] = "fastest_first"
        elif corruption == "wrong_execution_resampling":
            value["execution"]["resampling_on_failure"] = True
        elif corruption == "wrong_execution_workers":
            value["execution"]["workers"] = True
        elif corruption == "wrong_reference_game":
            value["references"]["refund-p50-q50"]["on_reach"]["coalition_game"] = "strict"
        else:
            value["package_version"] = "unreviewed-build"
        path.write_text(json.dumps(value))
    elif corruption in (
        "wrong_full_slot",
        "wrong_full_receipt",
        "wrong_full_summary",
        "wrong_full_request",
    ):
        path = root / "evidence/refund-p50-q50__on_reach.json.gz"
        with gzip.open(path, "rt") as stream:
            value = json.load(stream)
        branch = value["branches"]["branch_0"]
        if corruption == "wrong_full_slot":
            branch["slot"]["continuation_seed"] += 1
        elif corruption == "wrong_full_receipt":
            branch["decisions"][0]["policy_calls"] += 1
        elif corruption == "wrong_full_request":
            branch["decisions"][0]["request"]["task"] = "different captured task"
        else:
            branch["summary"]["policy_calls"] += 1
        with gzip.open(path, "wt") as stream:
            json.dump(value, stream)
    elif corruption == "extra_file":
        (root / "unexpected.json").write_text("{}")
    _rewrite_manifest(root)
    if corruption.startswith("manifest_"):
        path = root / "manifest.json"
        value = json.loads(path.read_text())
        if corruption == "manifest_duplicate":
            value["artifacts"].append(deepcopy(value["artifacts"][0]))
        elif corruption == "manifest_path":
            value["artifacts"][0]["path"] = "../outside.json"
        elif corruption == "manifest_bytes":
            value["artifacts"][0]["bytes"] += 1
        else:
            value["artifacts"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(value))
    with pytest.raises((AssertionError, ValueError, KeyError, StopIteration)):
        _audit_module().audit(root, "test-frozen-source")
