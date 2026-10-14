"""Contributor exports preserve decisions, refusal coverage, and shared budgets."""

from hashlib import sha256
import json

from jsonschema import Draft202012Validator
import pytest

from consequa_x import cli
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED
from consequa_x.explanation import explain
from consequa_x.models import Trace
from consequa_x.policies import PolicyError, ScriptedRefundPolicy


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_manifest(output):
    manifest = read_json(output / "manifest.json")
    paths = []
    for item in manifest["artifacts"]:
        relative = item["path"]
        assert not relative.startswith(("/", "\\")) and ":" not in relative
        assert ".." not in relative.split("/")
        assert sha256((output / relative).read_bytes()).hexdigest() == item["sha256"]
        paths.append(relative)
    assert len(paths) == len(set(paths))
    actual = {path.relative_to(output).as_posix() for path in output.rglob("*")
              if path.is_file() and path.name != "manifest.json"}
    assert set(paths) == actual


def run(output, *extra):
    return cli.main(["decision-experiment", "--output", str(output),
                     "--samples", "2", "--bootstrap-samples", "20",
                     "--interval-method", "percentile_bootstrap", *extra])


def test_legacy_bootstrap_targets_and_distinct_seed_schedule(tmp_path):
    output = tmp_path / "default"
    assert run(output, "--case", "clean") == 0
    result = read_json(output / "results.json")
    assert result["settings"]["targets"] == ["consequence"]
    assert result["settings"]["initial_continuation_seed"] == 100
    assert result["settings"]["factual_seed"] == 0
    assert result["planned_seeds"] == [[100, 101], [102, 103]]
    assert result["planned_branches"] == 4
    assert result["calls"] == {"total": 8, "factual": 2, "continuation": 6,
                               "max_calls": 400, "budget_exhausted": False}
    assert len(result["planned_schedule"]) == len(result["branches"]) == 4
    assert len(result["estimates"]) == 2
    assert all(item["status"] == "estimated" and item["effect"] == 0
               for item in result["estimates"])
    assert all(item["interval_degenerate"] is True for item in result["estimates"])
    assert result["method"]["bootstrap_baseline"] == "constant observed label; no RNG draws for baseline"
    assert result["method"]["multiplicity_adjustment"] == "none"
    assert result["settings"]["confidence"] == 0.95
    assert result["loci"][0]["status"] == "no_rescue"
    check_manifest(output)


def test_default_cli_uses_exact_binomial_uncertainty(tmp_path):
    output = tmp_path/"exact-default"
    assert cli.main(["decision-experiment", "--case", "clean", "--samples", "2",
                     "--output", str(output)]) == 0
    result = read_json(output/"results.json")
    assert result["method"]["interval_method"] == "clopper_pearson"
    assert result["method"]["bootstrap_samples"] is None
    assert all(item["effect"] == 0 and item["confidence_interval"][0] == 0
               and item["confidence_interval"][1] > 0 for item in result["estimates"])
    assert result["calls"]["total"] == 8


def test_three_targets_reuse_branches_and_independently_explain_each_trace(tmp_path):
    output = tmp_path / "three-targets"
    assert run(output, "--case", "unsafe_retry", "--template", "refund-support-note-v1",
               "--targets", "action,consequence,action_linked_consequence") == 0
    result = read_json(output / "results.json")
    assert result["calls"]["total"] == 15
    assert result["calls"]["factual"] == 3
    assert result["calls"]["continuation"] == 12
    assert len(result["branches"]) == 6
    assert len(result["estimates"]) == 9
    assert len(result["loci"]) == 3
    assert result["settings"]["template"]["template_id"] == "refund-support-note-v1"
    factual = result["factual"]
    assert factual["trace_sha256"] == sha256((output / factual["trace"]).read_bytes()).hexdigest()
    validator = Draft202012Validator(read_json(output / "trace-schema.json"))
    for receipt in [factual, *result["branches"]]:
        raw = read_json(output / receipt["trace"])
        validator.validate(raw)
        trace = Trace.from_dict(raw)
        assert "records" not in raw and "config" not in raw and "scenario" not in raw
        assert read_json(output / receipt["explanation"]) == explain(trace).to_dict()
        assert read_json(output / receipt["evaluator_truth"])["scenario"] == "unsafe_retry"
        assert len(receipt["decisions"]) == 3
    for receipt in result["branches"]:
        held = receipt["decision_index"]
        assert receipt["hold_count"] == held
        assert sum(item["policy_calls"] for item in receipt["decisions"]) == 3 - held
        assert all(item["source"] == "held_factual" and item["policy_calls"] == 0
                   for item in receipt["decisions"][:held])
    assert not (output / "attribution-explanation.json").exists()
    check_manifest(output)


def test_budget_exhaustion_keeps_full_planned_schedule_without_fabricating_traces(tmp_path):
    output = tmp_path / "budget"
    assert run(output, "--case", "clean", "--max-calls", "3") == 2
    result = read_json(output / "results.json")
    assert result["calls"] == {"total": 3, "factual": 2, "continuation": 1,
                               "max_calls": 3, "budget_exhausted": True}
    assert len(result["planned_schedule"]) == len(result["branches"]) == 4
    failed = [item for item in result["branches"] if item["status"] == "failed"]
    unstarted = [item for item in result["branches"] if item["status"] == "not_started"]
    assert len(failed) == 1 and len(unstarted) == 3
    assert failed[0]["error_type"] == "CallBudgetExceeded"
    assert failed[0]["decisions"][-1]["policy_calls"] == 0
    for item in failed + unstarted:
        assert "trace" not in item and "outcome" not in item
    assert len(list((output / "traces").iterdir())) == 1
    assert all(item["status"] == "refused" for item in result["estimates"])
    assert result["loci"][0]["status"] == "refused"
    check_manifest(output)


def test_unknown_target_refusal_is_valid_completion(tmp_path):
    output = tmp_path / "unknown"
    assert run(output, "--case", "delayed_visibility", "--targets", "action,consequence") == 0
    result = read_json(output / "results.json")
    assert all(item["status"] == "completed" for item in result["branches"])
    action = [item for item in result["estimates"] if item["target"] == "action"]
    consequence = [item for item in result["estimates"] if item["target"] == "consequence"]
    assert all(item["status"] == "estimated" for item in action)
    assert all(item["status"] == "refused" and item["factual_bad"] is None
               and item["unknown_samples"] == 2 for item in consequence)
    assert {item["target"]: item["status"] for item in result["loci"]} == {
        "action": "no_rescue", "consequence": "refused",
    }
    check_manifest(output)


@pytest.mark.parametrize("fail_call", [1, 2])
def test_factual_failure_preserves_reached_calls_without_running_estimator(
    tmp_path, monkeypatch, fail_call,
):
    class FailingPolicy(ScriptedRefundPolicy):
        def __init__(self):
            self.calls = 0

        def decide(self, request, *, seed):
            self.calls += 1
            if self.calls == fail_call:
                raise PolicyError("test provider refused the factual decision")
            return super().decide(request, seed=seed)

    policy = FailingPolicy()
    monkeypatch.setattr(cli, "_prepare_policy", lambda args: (policy, None))
    output = tmp_path / "factual-failure"
    assert run(output, "--case", "clean") == 2
    result = read_json(output / "results.json")
    assert policy.calls == fail_call
    assert result["status"] == "unavailable"
    assert result["planned_seeds"] is None and result["planned_schedule"] is None
    assert result["summary"] is None and result["estimates"] == result["loci"] == []
    assert result["branches"] == []
    assert result["calls"]["total"] == result["calls"]["factual"] == fail_call
    assert result["calls"]["continuation"] == 0
    factual = result["factual"]
    assert factual["status"] == "failed" and "trace" not in factual and "outcome" not in factual
    assert len(factual["decisions"]) == fail_call
    assert factual["decisions"][-1]["reply"] is None
    assert factual["decisions"][-1]["error_type"] == "PolicyError"
    assert not (output / "traces").exists()
    check_manifest(output)


def test_shared_budget_applies_while_recording_factual(tmp_path):
    output = tmp_path / "factual-budget"
    assert run(output, "--case", "clean", "--max-calls", "1") == 2
    result = read_json(output / "results.json")
    assert result["status"] == "unavailable"
    assert result["calls"]["total"] == result["calls"]["factual"] == 1
    assert result["calls"]["budget_exhausted"] is True
    assert len(result["factual"]["decisions"]) == 2
    assert result["factual"]["decisions"][-1]["policy_calls"] == 0
    assert result["factual"]["error_type"] == "CallBudgetExceeded"
    check_manifest(output)


def test_completed_factual_with_policy_identity_drift_is_preserved_on_preflight_refusal(
    tmp_path, monkeypatch,
):
    class DriftingPolicy(ScriptedRefundPolicy):
        def __init__(self):
            self.calls = 0

        @property
        def metadata(self):
            return {**super().metadata, "declared_revision": self.calls}

        def decide(self, request, *, seed):
            reply = super().decide(request, seed=seed)
            self.calls += 1
            return reply

    policy = DriftingPolicy()
    monkeypatch.setattr(cli, "_prepare_policy", lambda args: (policy, None))
    output = tmp_path / "preflight-refusal"
    assert run(output, "--case", "clean") == 2
    result = read_json(output / "results.json")
    assert policy.calls == 2
    assert result["factual"]["status"] == "completed"
    assert result["calls"] == {"total": 2, "factual": 2, "continuation": 0,
                               "max_calls": 400, "budget_exhausted": False}
    availability = result["estimator_availability"]
    assert availability["status"] == "refused" and availability["error_type"] == "ValueError"
    assert "metadata changed" in availability["error"]
    assert result["planning"]["source"] == "unvalidated_capture"
    assert result["planning"]["recorded_factual_decisions"] == 2
    assert result["planning"]["conservative_max_positions"] == 3
    assert result["planned_seeds"] is None and result["planned_schedule"] is None
    assert result["branches"] == result["estimates"] == result["loci"] == []
    factual = result["factual"]
    raw = read_json(output / factual["trace"])
    Draft202012Validator(read_json(output / "trace-schema.json")).validate(raw)
    trace = Trace.from_dict(raw)
    assert factual["trace_sha256"] == sha256((output / factual["trace"]).read_bytes()).hexdigest()
    assert read_json(output / factual["explanation"]) == explain(trace).to_dict()
    assert read_json(output / factual["evaluator_truth"])["scenario"] == "clean"
    assert "estimator preflight was refused" in (output / "README.md").read_text(encoding="utf-8")
    check_manifest(output)


def test_continuation_provider_failure_has_receipt_and_whole_estimate_refusal(
    tmp_path, monkeypatch,
):
    class FailingPolicy(ScriptedRefundPolicy):
        def decide(self, request, *, seed):
            if seed == 600:
                raise PolicyError("test provider failed continuation")
            return super().decide(request, seed=seed)

    monkeypatch.setattr(cli, "_prepare_policy", lambda args: (FailingPolicy(), None))
    output = tmp_path / "continuation-failure"
    assert run(output, "--case", "clean") == 2
    result = read_json(output / "results.json")
    failed = [item for item in result["branches"] if item["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["policy_calls"] == 1 and failed[0]["error_type"] == "PolicyError"
    assert "trace" not in failed[0] and "outcome" not in failed[0]
    first = next(item for item in result["estimates"] if item["decision_index"] == 0)
    assert first["status"] == "refused" and first["failed_samples"] == 1
    assert result["loci"][0]["status"] == "refused"
    check_manifest(output)


@pytest.mark.parametrize("option,value", [
    ("--samples", "1"), ("--max-calls", "0"), ("--max-attempts", "6"),
    ("--seed", "-1"), ("--factual-seed", "-1"),
    ("--seed", str(MAX_TRIAL_SEED)), ("--factual-seed", str(MAX_TRIAL_SEED + 1)),
    ("--factual-seed", "101"), ("--confidence", "0"), ("--confidence", "1"),
    ("--confidence", "nan"), ("--confidence", "inf"),
    ("--bootstrap-samples", "1"), ("--bootstrap-seed", "-1"),
    ("--targets", ""), ("--targets", "consequence,consequence"),
    ("--targets", "success"),
])
def test_invalid_schedule_is_rejected_before_provider_or_output(tmp_path, monkeypatch, option, value):
    def forbid(args):
        raise AssertionError("Invalid options must fail before provider preparation")

    monkeypatch.setattr(cli, "_prepare_policy", forbid)
    output = tmp_path / "rejected"
    assert run(output, option, value) == 2
    assert not output.exists()


def test_nonempty_output_is_preserved_before_provider_preparation(tmp_path, monkeypatch):
    output = tmp_path / "preserved"
    output.mkdir()
    sentinel = output / "results.json"
    sentinel.write_bytes(b"existing evidence\n")
    monkeypatch.setattr(cli, "_prepare_policy", lambda args: pytest.fail("Unexpected provider setup"))
    assert run(output) == 2
    assert sentinel.read_bytes() == b"existing evidence\n"
    assert list(output.iterdir()) == [sentinel]


def test_scripted_provider_rejects_model_prompt_options_before_writing(tmp_path):
    for option, value in (("--model", "small-local-model"),
                          ("--prompt-version", "refund-policy-v2")):
        output = tmp_path / option.lstrip("-")
        assert run(output, option, value) == 2
        assert not output.exists()


def test_exports_repeat_exactly_with_identical_scripted_settings(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        assert run(output, "--case", "clean", "--seed", "17", "--factual-seed", "5") == 0
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()

