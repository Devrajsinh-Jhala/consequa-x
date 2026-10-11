"""Study split isolation, reproducible order and pre-provider validation."""

from dataclasses import replace
from hashlib import sha256
import json
from unittest.mock import patch

from jsonschema import Draft202012Validator
import pytest

from consequa_x import cli
from consequa_x.adapters.ollama import OllamaPolicy
from consequa_x.benchmark.evaluation import evaluate_policy
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.runner import ScenarioConfig
from consequa_x.benchmark.study import StudyCase, StudyPlan, study_plan_from_json
from consequa_x.benchmark.templates import DEFAULT_REFUND_TEMPLATE, REFUND_TASK_TEMPLATES
from consequa_x.models import Trace
from consequa_x.policies import ScriptedRefundPolicy
from consequa_x.schema import get_trace_schema


def candidate_plan():
    templates = tuple(REFUND_TASK_TEMPLATES[name] for name in (
        "refund-support-note-v1", "refund-case-note-v1", "refund-operations-ticket-v1",
    ))
    cases = tuple(
        StudyCase(case_id := f"{split}.{condition}", split,
                  ScenarioConfig(name=case_id, fault=fault, amount_minor=125_000), template)
        for split, template in zip(("tuning", "validation", "held_out"), templates, strict=True)
        for condition, fault in (("ordinary", Fault.CLEAN), ("ambiguous", Fault.TIMEOUT_AFTER_COMMIT))
    )
    return StudyPlan("candidate-refund-v1", templates, cases)


def save_plan(path, plan=None):
    # Preserve CRLF to ensure provenance hashes cover exact source bytes.
    data = json.dumps((plan or candidate_plan()).to_dict(), indent=2).replace("\n", "\r\n")
    path.write_bytes(data.encode("utf-8"))
    return path


def test_plan_roundtrip_and_disjoint_family_assignment():
    plan = candidate_plan()
    restored = study_plan_from_json(json.dumps(plan.to_dict()))
    assert restored == plan
    assert {case.split for case in restored.cases} == {"tuning", "validation", "held_out"}
    assert len({template.family_id for template in restored.templates}) == 3
    assert restored.select("tuning", order_seed=7) == plan.select("tuning", order_seed=7)
    assert set(restored.select("tuning")) == set(plan.cases[:2])


def test_family_cannot_cross_splits():
    plan = candidate_plan()
    altered = replace(plan.cases[0], split="held_out")
    with pytest.raises(ValueError, match="cannot cross"):
        replace(plan, cases=(altered, *plan.cases[1:]))


@pytest.mark.parametrize("renamed", [False, True])
def test_pilot_wording_cannot_be_reassigned_to_a_holdout(renamed):
    template = replace(DEFAULT_REFUND_TEMPLATE, template_id="new-id", family_id="new-family") if (
        renamed
    ) else DEFAULT_REFUND_TEMPLATE
    case = StudyCase("held_out.pilot", "held_out", ScenarioConfig(name="held_out.pilot"), template)
    with pytest.raises(ValueError, match="pilot template"):
        StudyPlan("invalid-holdout", (template,), (case,))


def test_same_wording_cannot_be_declared_as_independent_families():
    plan = candidate_plan()
    duplicate = replace(plan.templates[0], template_id="duplicate", family_id="different-family")
    with pytest.raises(ValueError, match="identical visible wording"):
        StudyPlan(plan.study_id, (*plan.templates, duplicate), plan.cases)


@pytest.mark.parametrize("mutate", [
    lambda value: value.update(schema_version="unsupported"),
    lambda value: value.update(extra="unexpected"),
    lambda value: value["cases"][0].update(template_id="undeclared"),
    lambda value: value["cases"][0]["scenario"].update(name="label-injection"),
    lambda value: value["cases"][0]["scenario"].update(fault="unknown"),
    lambda value: value["cases"][0]["scenario"].update(context={"vip_memory": "yes"}),
    lambda value: value["cases"].append(value["cases"][0]),
    lambda value: value["templates"].append(value["templates"][0]),
    lambda value: value["cases"][0].update(case_id="../../escape"),
    lambda value: value["cases"][0]["scenario"].pop("fault"),
])
def test_invalid_manifest_is_rejected_without_provider_or_output(tmp_path, mutate):
    value = candidate_plan().to_dict()
    mutate(value)
    manifest = tmp_path / "invalid.json"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "rejected"
    with patch.object(OllamaPolicy, "list_models") as listing:
        assert cli.main(["model-eval", "--study", str(manifest), "--split", "tuning",
                         "--provider", "ollama", "--model", "fixture", "--output", str(output)]) == 2
    listing.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize("text", ['{"schema_version": 1, "schema_version": 2}', '{"n": NaN}'])
def test_ambiguous_or_nonfinite_manifest_json_is_rejected(text):
    with pytest.raises(ValueError, match="strict finite JSON"):
        study_plan_from_json(text)


@pytest.mark.parametrize("extra", [
    [], ["--split", "tuning", "--cases", "clean"],
    ["--split", "tuning", "--order-seed", "-1"],
])
def test_missing_split_conflicting_cases_or_bad_order_rejected_before_provider(tmp_path, extra):
    manifest = save_plan(tmp_path / "plan.json")
    output = tmp_path / "rejected"
    with patch.object(OllamaPolicy, "list_models") as listing:
        assert cli.main(["model-eval", "--study", str(manifest), "--provider", "ollama",
                         "--model", "fixture", "--output", str(output), *extra]) == 2
    listing.assert_not_called()
    assert not output.exists()


@pytest.mark.parametrize("extra", [["--split", "tuning"], ["--order-seed", "1"]])
def test_split_arguments_require_manifest(tmp_path, extra):
    output = tmp_path / "rejected"
    assert cli.main(["model-eval", "--output", str(output), *extra]) == 2
    assert not output.exists()


def test_split_export_preserves_exact_manifest_and_hides_evaluator_ids(tmp_path):
    manifest = save_plan(tmp_path / "plan.json")
    outputs = (tmp_path / "first", tmp_path / "second")
    for output in outputs:
        assert cli.main(["model-eval", "--study", str(manifest), "--split", "held_out",
                         "--order-seed", "77", "--seed", "11", "--samples", "2",
                         "--output", str(output)]) == 0
        result = json.loads((output / "results.json").read_text(encoding="utf-8"))
        assert result["summary"]["completed_samples"] == 4
        assert result["study"]["manifest_sha256"] == sha256(manifest.read_bytes()).hexdigest()
        assert (output / "study-plan.json").read_bytes() == manifest.read_bytes()
        schedule = result["study"]["planned_schedule"]
        assert [item["seed"] for item in schedule] == [11, 12, 13, 14]
        for receipt, planned in zip(result["samples"], schedule, strict=True):
            assert receipt["case_id"] == planned["case_id"]
            assert receipt["family_id"] == "refund-operations-ticket"
            trace_data = json.loads((output / receipt["trace"]).read_text(encoding="utf-8"))
            trace = Trace.from_dict(trace_data)
            Draft202012Validator(get_trace_schema()).validate(trace_data)
            assert trace.trace_id == f"trace:{receipt['seed']}"
            for event in trace.events:
                if "policy_request" not in event.data:
                    continue
                request_text = json.dumps(event.data["policy_request"])
                for hidden in (receipt["case_id"], receipt["family_id"], receipt["template_id"],
                               "held_out", "timeout_after_commit", "candidate-refund-v1"):
                    assert hidden not in request_text
                assert "Operations ticket:" in request_text
        for item in json.loads((output / "manifest.json").read_text(encoding="utf-8"))["artifacts"]:
            assert sha256((output / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    assert (outputs[0] / "results.json").read_bytes() == (outputs[1] / "results.json").read_bytes()


def test_budget_exhaustion_retains_entire_planned_schedule(tmp_path):
    manifest = save_plan(tmp_path / "plan.json")
    output = tmp_path / "limited"
    assert cli.main(["model-eval", "--study", str(manifest), "--split", "tuning",
                     "--samples", "2", "--max-calls", "1", "--output", str(output)]) == 2
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert len(result["study"]["planned_schedule"]) == 4
    assert result["summary"]["completed_samples"] == 0
    assert result["summary"]["failed_samples"] == 1
    assert result["summary"]["not_started_samples"] == 3
    assert result["summary"]["action_linked_consequence"] == {
        "satisfied": 0, "not_satisfied": 0, "unknown": 0,
    }


@pytest.mark.parametrize("templates", [{}, {"extra": DEFAULT_REFUND_TEMPLATE}, {"only": "bad"}])
def test_programmatic_template_map_is_validated_before_decisions(templates):
    with patch.object(ScriptedRefundPolicy, "decide") as decide:
        with pytest.raises(ValueError, match="templates must map"):
            evaluate_policy(ScriptedRefundPolicy(), (ScenarioConfig(name="only"),), templates=templates)
    decide.assert_not_called()


def test_evaluation_distinguishes_external_satisfaction_and_missing_provenance():
    configs = (ScenarioConfig(name="external", fault=Fault.TIMEOUT_BEFORE_COMMIT, external_actor=True),
               ScenarioConfig(name="missing", fault=Fault.CLEAN, include_provenance=False))
    result = evaluate_policy(ScriptedRefundPolicy(), configs, samples=1)
    assert result.summary()["verification"] == {"satisfied": 2, "violated": 0, "unknown": 0}
    assert result.summary()["action_linked_consequence"] == {
        "satisfied": 0, "not_satisfied": 1, "unknown": 1,
    }
