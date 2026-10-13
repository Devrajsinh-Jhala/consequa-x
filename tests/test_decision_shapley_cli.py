"""Installed contributor exports keep coalition coverage and evidence auditable."""

from hashlib import sha256
import json

from jsonschema import Draft202012Validator
import pytest

from consequa_x import cli
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED
from consequa_x.explanation import explain
from consequa_x.models import Trace
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply, ScriptedRefundPolicy


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(output, *extra):
    return cli.main(["decision-shapley", "--output", str(output), "--pairs", "2",
                     "--endpoint-samples", "2", "--interval-method", "normal",
                     "--endpoint-interval-method", "normal", *extra])


def check_manifest(output):
    paths = []
    for item in read(output / "manifest.json")["artifacts"]:
        relative = item["path"]
        assert not relative.startswith(("/", "\\")) and ":" not in relative
        assert ".." not in relative.split("/")
        assert sha256((output / relative).read_bytes()).hexdigest() == item["sha256"]
        paths.append(relative)
    assert len(paths) == len(set(paths))
    assert set(paths) == {path.relative_to(output).as_posix() for path in output.rglob("*")
                          if path.is_file() and path != output / "manifest.json"}


def test_complete_control_schedule_and_independent_endpoints(tmp_path):
    output = tmp_path / "control"
    assert run(output) == 0
    result = read(output / "results.json")
    assert result["estimator_availability"]["status"] == "available"
    assert result["planning"]["source"] == "validated_capture"
    schedule = result["planned_schedule"]
    assert len(schedule) == len(result["branches"]) == 16
    assert [slot["role"] for slot in schedule[:4]] == ["endpoint_empty"] * 2 + ["endpoint_full"] * 2
    seeds = [slot["continuation_seed"] for slot in schedule]
    assert seeds == list(range(100, 116))
    assert len(set(seeds)) == 16
    assert all(branch["status"] == "completed" for branch in result["branches"])
    assert result["calls"] == {"total": 18, "factual": 2, "continuation": 16,
                               "max_calls": 2000, "budget_exhausted": False}
    assert all(estimate["status"] == "estimated" and estimate["shapley_value"] == 0
               and estimate["interval_degenerate"] for estimate in result["estimates"])
    endpoint = result["endpoint_checks"][0]
    assert endpoint["endpoint_difference"] == endpoint["coefficient_sum"] == endpoint["discrepancy"] == 0
    assert result["factual"]["trace_sha256"] == sha256(
        (output / result["factual"]["trace"]).read_bytes()).hexdigest()
    check_manifest(output)


def test_default_cli_uses_conservative_pair_and_endpoint_bounds(tmp_path):
    output = tmp_path/"conservative-default"
    assert cli.main(["decision-shapley", "--pairs", "2", "--endpoint-samples", "2",
                     "--output", str(output)]) == 0
    result = read(output/"results.json")
    assert result["settings"]["interval_method"] == "hoeffding"
    assert result["settings"]["endpoint_interval_method"] == "clopper_pearson_difference"
    assert result["settings"]["coalition_game"] == "strict"
    assert all(item["shapley_value"] == 0 and item["confidence_interval"][0] < 0
               < item["confidence_interval"][1] for item in result["estimates"])
    assert result["calls"]["total"] == 18


def test_three_targets_share_calls_and_every_completed_trace_is_explainable(tmp_path):
    output = tmp_path / "three"
    assert run(output, "--targets", "action,consequence,action_linked_consequence",
               "--template", "refund-support-note-v1") == 0
    result = read(output / "results.json")
    assert result["calls"]["total"] == 18
    assert len(result["estimates"]) == 6 and len(result["endpoint_checks"]) == 3
    validator = Draft202012Validator(read(output / "trace-schema.json"))
    for receipt in [result["factual"], *result["branches"]]:
        raw = read(output / receipt["trace"])
        validator.validate(raw)
        trace = Trace.from_dict(raw)
        assert "records" not in raw and "scenario" not in raw and "config" not in raw
        assert read(output / receipt["explanation"]) == explain(trace).to_dict()
        assert read(output / receipt["evaluator_truth"])["scenario"] == "clean"
        assert sum(decision["policy_calls"] for decision in receipt["decisions"]) == receipt["policy_calls"]
    assert not (output / "attribution-explanation.json").exists()
    check_manifest(output)


def test_partial_budget_receipt_and_full_unstarted_plan(tmp_path):
    output = tmp_path / "budget"
    assert run(output, "--max-calls", "3") == 2
    result = read(output / "results.json")
    assert result["calls"]["total"] == 3 and result["calls"]["continuation"] == 1
    assert len(result["branches"]) == 16
    failed = [branch for branch in result["branches"] if branch["status"] == "failed"]
    assert len(failed) == 1 and failed[0]["error_type"] == "CallBudgetExceeded"
    assert failed[0]["decisions"][-1]["policy_calls"] == 0
    assert sum(branch["status"] == "not_started" for branch in result["branches"]) == 15
    assert all("trace" not in branch and "outcome" not in branch for branch in result["branches"])
    assert all(item["status"] == "refused" for item in result["estimates"])
    assert len(list((output / "traces").glob("*.json"))) == 1
    check_manifest(output)


def test_factual_failure_has_no_coalition_schedule_or_invented_outcome(tmp_path):
    output = tmp_path / "factual-failure"
    assert run(output, "--max-calls", "1") == 2
    result = read(output / "results.json")
    assert result["factual"]["status"] == "failed"
    assert result["factual"]["policy_calls"] == 1
    assert result["factual"]["decisions"][-1]["policy_calls"] == 0
    assert "trace" not in result["factual"] and "outcome" not in result["factual"]
    assert result["planned_schedule"] is None and result["branches"] == []
    assert result["estimates"] == [] and result["endpoint_checks"] == []
    check_manifest(output)


def test_unreachable_held_positions_remain_invalid_without_outcome(tmp_path, monkeypatch):
    class ShortPolicy(ScriptedRefundPolicy):
        def decide(self, request, *, seed):
            if seed >= 600 and request.stage == "after_response":
                return PolicyReply(PolicyDecision("stop"), self.metadata)
            return super().decide(request, seed=seed)

    monkeypatch.setattr(cli, "_prepare_policy", lambda args: (ShortPolicy(), None))
    output = tmp_path / "invalid"
    assert run(output, "--case", "unsafe_retry") == 2
    result = read(output / "results.json")
    invalid = [branch for branch in result["branches"] if branch["status"] == "invalid"]
    assert invalid
    assert all(branch["unreached_held_indices"] and "trace" not in branch
               and "outcome" not in branch for branch in invalid)
    assert all(item["status"] == "refused" for item in result["estimates"])
    check_manifest(output)


def test_provider_failure_is_not_a_bad_label_and_does_not_redraw(tmp_path, monkeypatch):
    class BrokenPolicy(ScriptedRefundPolicy):
        def decide(self, request, *, seed):
            if seed >= 600:
                raise PolicyError("fixture provider failure")
            return super().decide(request, seed=seed)

    monkeypatch.setattr(cli, "_prepare_policy", lambda args: (BrokenPolicy(), None))
    output = tmp_path / "provider-failure"
    assert run(output) == 2
    result = read(output / "results.json")
    failed = [branch for branch in result["branches"] if branch["status"] == "failed"]
    assert failed and all(branch["policy_calls"] == 1 for branch in failed)
    assert all("trace" not in branch and "outcome" not in branch for branch in failed)
    assert len(result["branches"]) == len(result["planned_schedule"]) == 16
    assert all(item["status"] == "refused" for item in result["estimates"])
    check_manifest(output)


def test_on_reach_exports_actual_early_termination_and_inactive_players(tmp_path, monkeypatch):
    class ShortPolicy(ScriptedRefundPolicy):
        def decide(self, request, *, seed):
            if seed >= 600 and request.stage == "after_response":
                return PolicyReply(PolicyDecision("stop"), self.metadata)
            return super().decide(request, seed=seed)

    monkeypatch.setattr(cli, "_prepare_policy", lambda args: (ShortPolicy(), None))
    output = tmp_path/"on-reach"
    assert run(output, "--case", "unsafe_retry", "--coalition-game", "on_reach",
               "--interval-method", "hoeffding",
               "--endpoint-interval-method", "clopper_pearson_difference") == 0
    result = read(output/"results.json")
    assert result["method"]["name"] == "binary_on_reach_decision_shapley"
    assert result["settings"]["coalition_game"] == "on_reach"
    inactive = [branch for branch in result["branches"] if branch["inactive_held_indices"]]
    assert inactive and all(branch["status"] == "completed" for branch in inactive)
    for branch in inactive:
        trace = Trace.from_dict(read(output/branch["trace"]))
        assert len(trace.responses) == 1
        assert len(branch["decisions"]) == 2
        assert branch["inactive_held_indices"] == [2]
        assert read(output/branch["explanation"]) == explain(trace).to_dict()
    assert all(item["status"] == "estimated" for item in result["estimates"])
    check_manifest(output)


def test_unknown_provenance_refuses_linked_vector_only(tmp_path):
    output = tmp_path / "unknown"
    assert run(output, "--case", "missing_provenance",
               "--targets", "action,consequence,action_linked_consequence") == 0
    result = read(output / "results.json")
    by_target = {target: [item for item in result["estimates"] if item["target"] == target]
                 for target in result["settings"]["targets"]}
    assert all(item["status"] == "estimated" for target in ("action", "consequence")
               for item in by_target[target])
    assert all(item["status"] == "refused" for item in by_target["action_linked_consequence"])
    check_manifest(output)


@pytest.mark.parametrize("option,value", [
    ("--pairs", "1"), ("--samples", "0"), ("--endpoint-samples", "1"),
    ("--max-calls", "0"), ("--max-attempts", "6"), ("--confidence", "nan"),
    ("--confidence", "1"), ("--targets", "action,action"), ("--targets", "missing"),
    ("--seed", "0"), ("--seed", str(MAX_TRIAL_SEED)),
    ("--factual-seed", "100"), ("--permutation-seed", "-1"),
])
def test_preflight_rejects_before_provider_and_output(tmp_path, monkeypatch, option, value):
    def forbidden(args):
        pytest.fail("Provider preparation must follow preflight")

    monkeypatch.setattr(cli, "_prepare_policy", forbidden)
    output = tmp_path / "invalid-settings"
    assert run(output, option, value) == 2
    assert not output.exists()


def test_existing_export_is_preserved(tmp_path):
    output = tmp_path / "preserved"
    output.mkdir()
    marker = output / "receipt.txt"
    marker.write_text("retain", encoding="utf-8")
    assert run(output) == 2
    assert marker.read_text(encoding="utf-8") == "retain"
