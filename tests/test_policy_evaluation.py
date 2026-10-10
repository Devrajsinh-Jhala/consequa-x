"""Evaluation coverage and failures must remain visible and independently counted."""

from hashlib import sha256
import json

import pytest

from consequa_x import cli
from consequa_x.benchmark.evaluation import evaluate_policy
from consequa_x.benchmark.runner import ScenarioConfig, demo_scenarios
from consequa_x.models import Trace
from consequa_x.policies import PolicyError, ScriptedRefundPolicy


def test_scripted_evaluation_counts_all_outcomes_without_counting_unknown_as_failure():
    result = evaluate_policy(ScriptedRefundPolicy(), samples=2)
    summary = result.summary()
    assert summary["planned_samples"] == summary["completed_samples"] == 24
    assert summary["failed_samples"] == summary["not_started_samples"] == 0
    assert summary["verification"] == {"satisfied": 12, "violated": 10, "unknown": 2}
    assert summary["known_outcome_samples"] == 22
    assert sum(summary["origin"].values()) == 24
    assert sum(summary["assessment_alignment"].values()) == 24
    assert summary["policy_calls"] == 52
    assert not summary["budget_exhausted"]


class BrokenPolicy(ScriptedRefundPolicy):
    def decide(self, request, *, seed):
        raise PolicyError("The policy output is unusable")


def test_policy_errors_are_retained_and_do_not_enter_outcome_denominators():
    result = evaluate_policy(BrokenPolicy(), samples=1)
    summary = result.summary()
    assert summary["failed_samples"] == summary["attempted_samples"] == 12
    assert summary["policy_calls"] == 12
    assert sum(summary["verification"].values()) == 0
    assert sum(summary["origin"].values()) == 0
    assert summary["known_outcome_samples"] == 0
    assert all(sample.error_type == "PolicyError" and sample.episode is None for sample in result.samples)


def test_budget_refuses_an_extra_decision_and_counts_unstarted_samples():
    result = evaluate_policy(ScriptedRefundPolicy(), samples=1, max_calls=3)
    summary = result.summary()
    assert summary["policy_calls"] == 3
    assert summary["completed_samples"] == 1
    assert summary["failed_samples"] == 1
    assert summary["not_started_samples"] == 10
    assert summary["budget_exhausted"]
    assert result.samples[-1].error_type == "CallBudgetExceeded"


def test_exactly_sufficient_call_budget_completes_normally():
    result = evaluate_policy(ScriptedRefundPolicy(), (ScenarioConfig(),), samples=1, max_calls=2)
    assert result.summary()["completed_samples"] == 1
    assert not result.budget_exhausted


@pytest.mark.parametrize("kwargs", [
    {"samples": 0}, {"samples": True}, {"seed": -1}, {"seed": 2**31},
    {"max_calls": 0}, {"max_calls": False}, {"max_attempts": 0}, {"max_attempts": 6},
    {"configs": []}, {"configs": [ScenarioConfig(), ScenarioConfig()]},
])
def test_invalid_schedule_is_rejected_before_model_calls(kwargs):
    with pytest.raises(ValueError):
        evaluate_policy(BrokenPolicy(), **kwargs)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_exports_a_reproducible_scripted_evaluation(tmp_path, capsys):
    outputs = (tmp_path / "first", tmp_path / "second")
    for output in outputs:
        assert cli.main(["model-eval", "--provider", "scripted", "--samples", "1",
                         "--output", str(output)]) == 0
        report = read_json(output / "results.json")
        assert report["evaluation_kind"] == "scripted_smoke"
        assert len(report["samples"]) == len(demo_scenarios())
        assert "No language model was run" in (output / "README.md").read_text(encoding="utf-8")
        for sample in report["samples"]:
            trace = Trace.from_dict(read_json(output / sample["trace"]))
            assert trace.trace_id == f"trace:{sample['seed']}"
            assert read_json(output / sample["evaluator_truth"])["scenario"] == sample["scenario"]
            for event in trace.events:
                if "policy_request" in event.data:
                    request = event.data["policy_request"]
                    assert set(request) == {"stage", "task", "context", "responses", "attempts_remaining"}
                    assert "fault" not in request["task"]
                    assert "ground_truth" not in request["task"]
        manifest = read_json(output / "manifest.json")
        assert len(manifest["artifacts"]) == 36
        for artifact in manifest["artifacts"]:
            assert sha256((output / artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
    assert (outputs[0] / "results.json").read_bytes() == (outputs[1] / "results.json").read_bytes()
    assert (outputs[0] / "README.md").read_bytes() == (outputs[1] / "README.md").read_bytes()
    capsys.readouterr()


@pytest.mark.parametrize("args", [
    ["--provider", "ollama"], ["--model", "fake-model"], ["--cases", "does_not_exist"],
    ["--cases", "clean,clean"], ["--samples", "0"], ["--seed", "-1"],
    ["--max-calls", "0"], ["--max-attempts", "6"],
])
def test_cli_bad_configuration_has_no_outputs(tmp_path, capsys, args):
    output = tmp_path / "rejected"
    assert cli.main(["model-eval", "--output", str(output), *args]) == 2
    assert not output.exists()
    assert "consequa-x:" in capsys.readouterr().err


def test_cli_refuses_to_mix_new_samples_into_existing_outputs(tmp_path, capsys):
    output = tmp_path / "existing"
    output.mkdir()
    artifact = output / "previous.json"
    artifact.write_text("previous evaluation", encoding="utf-8")
    assert cli.main(["model-eval", "--output", str(output)]) == 2
    assert artifact.read_text(encoding="utf-8") == "previous evaluation"
    assert sorted(path.name for path in output.iterdir()) == ["previous.json"]
    assert "new or empty" in capsys.readouterr().err


def test_cli_budget_exhaustion_preserves_an_explicit_partial_report(tmp_path, capsys):
    output = tmp_path / "limited"
    assert cli.main(["model-eval", "--samples", "1", "--max-calls", "3",
                     "--output", str(output)]) == 2
    report = read_json(output / "results.json")
    assert report["summary"]["budget_exhausted"]
    assert report["summary"]["not_started_samples"] == 10
    assert report["samples"][-1]["status"] == "failed"
    assert "verified_outcome" not in report["samples"][-1]
    capsys.readouterr()
