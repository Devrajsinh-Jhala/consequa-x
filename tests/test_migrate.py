"""Schema 0.1 traces written by the released 1.2.0 package migrate to schema 1.0."""

import json
from pathlib import Path

import pytest

import consequa_x
from consequa_x import (
    MigrationReport, RecordVerifier, SchemaVersionError, TimeBase, Trace, ValidationError,
    explain, migrate_trace,
)
from consequa_x import cli
import consequa_x.research as research


FIXTURES = Path(__file__).parent / "fixtures" / "v0.1"
NAMES = ("refund-timeout-after-commit", "refund-stale-readback", "refund-another-actor",
         "record-timeout-after-commit")


def legacy(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", NAMES)
def test_released_0_1_traces_migrate_structurally(name):
    old = legacy(name)
    trace = migrate_trace(old)
    assert trace.schema_version == "1.0" and trace.time_base is TimeBase.RELATIVE_MS
    (action,) = trace.actions
    assert action.action_id == old["action"]["action_id"]
    assert action.to_dict() == {key: value for key, value in old["action"].items()
                                if key != "trace_id"}
    assert [event.id for event in trace.events] == [event["id"] for event in old["events"]]
    assert all(item.action_id == action.action_id
               for item in trace.responses + trace.assessments + trace.verifications)
    (assessment,) = trace.assessments
    assert assessment.status.value == old["assessment"]["status"]
    assert Trace.from_json(trace.to_json()) == trace
    assert migrate_trace(trace.to_json()) == trace  # schema 1.0 input is returned unchanged


def test_migrated_refund_explanation_reproduces_the_1_x_result():
    old = json.loads((FIXTURES / "refund-timeout-after-commit.explanation.json")
                     .read_text(encoding="utf-8"))
    report = MigrationReport()
    trace = migrate_trace(legacy("refund-timeout-after-commit"), report=report)
    assert report == {"source_schema_version": "0.1", "schema_version": "1.0",
                      "verifications": 1, "reproduced": 1, "not_reproduced": 0,
                      "time_base": "relative_ms"}
    action = explain(trace).single_action
    assert action.assessment_alignment == old["assessment_alignment"] == "contradicted"
    assert list(action.codes) == old["diagnoses"]
    assert trace.assessments[0].assessment_id == "assessment_1"  # the matching event's ID


def test_record_traces_need_their_verifier_to_regain_target_matches():
    report = MigrationReport()
    plain = migrate_trace(legacy("record-timeout-after-commit"), report=report)
    assert report["reproduced"] == 0 and report["not_reproduced"] == 1
    assert plain.verifications[0].target_effect_ids is None
    assert explain(plain).single_action.assessment_alignment == "unassessable"
    verifier = RecordVerifier(scope_fields=("order_id",))
    matched = migrate_trace(legacy("record-timeout-after-commit"),
                            verifiers={"record_present": verifier})
    assert matched.verifications[0].target_effect_ids == ("rf-1",)
    assert explain(matched).single_action.assessment_alignment == "contradicted"


def test_a_receipt_the_verifier_does_not_reproduce_keeps_its_recorded_conclusion():
    old = legacy("refund-timeout-after-commit")
    old["verifications"][0]["origin"] = "unknown"
    old["verifications"][0]["attributable_effect_ids"] = []
    report = MigrationReport()
    trace = migrate_trace(old, report=report)
    assert report["not_reproduced"] == 1
    receipt = trace.verifications[0]
    assert receipt.origin.value == "unknown" and receipt.target_effect_ids is None
    assert receipt.findings == ()


@pytest.mark.parametrize("change,message", [
    (lambda item: item.update(extra=True), "unknown schema 0.1 fields"),
    (lambda item: item["action"].update(extra=True), "unknown schema 0.1 fields"),
    (lambda item: item["events"][0].update(trace_id="other"), "event.trace_id"),
    (lambda item: item["action"].update(trace_id="other"), "action.trace_id"),
    (lambda item: item.pop("assessment"), "missing required"),
    (lambda item: item.update(schema_version="0.9"), "cannot migrate"),
])
def test_malformed_0_1_input_is_refused(change, message):
    old = legacy("refund-timeout-after-commit")
    change(old)
    with pytest.raises((ValidationError, SchemaVersionError), match=message):
        migrate_trace(old)


def test_cli_validate_and_migrate(tmp_path, capsys):
    source = FIXTURES / "refund-timeout-after-commit.json"
    assert cli.main(["validate", str(source)]) == 2
    assert "consequa-x migrate" in capsys.readouterr().out
    output = tmp_path / "out" / "migrated.json"
    assert cli.main(["migrate", str(source), "--output", str(output)]) == 0
    printed = capsys.readouterr().out
    assert "Verifier reproduced 1 of 1" in printed
    assert cli.main(["validate", str(output)]) == 0
    assert "valid:" in capsys.readouterr().out
    before = output.read_bytes()
    assert cli.main(["migrate", str(source), "--output", str(output)]) == 2
    assert output.read_bytes() == before
    assert "new file" in capsys.readouterr().err


def test_research_interfaces_moved_out_of_the_top_level_namespace():
    for name in ("EffectEstimate", "Intervention", "leave_one_out", "recency_attribution",
                 "Policy", "PolicyRequest", "ScriptedRefundPolicy"):
        assert not hasattr(consequa_x, name) and name in research.__all__
        assert hasattr(research, name)
