"""Trace comparison, the verify command and key-based report redaction."""

from dataclasses import replace
import json
from pathlib import Path

import pytest

from consequa_x import (
    AssessmentStatus, Comparison, Trace, cli, compare, migrate_trace, render_report,
)
from test_multi_action import two_action_run


FIXTURES = Path(__file__).parent / "fixtures" / "v0.1"


def refund_trace():
    return migrate_trace((FIXTURES / "refund-timeout-after-commit.json").read_text(encoding="utf-8"))


def test_compare_reports_changed_aspects_and_unmatched_actions():
    trace = two_action_run().trace()
    same = compare(trace, trace)
    assert isinstance(same, Comparison) and same.same and same.changes == ()
    assert "No differences" in same.to_text()
    reported = replace(trace.assessments[-2], status=AssessmentStatus.SUCCESS)
    changed = replace(trace, assessments=trace.assessments[:-2] + (reported, trace.assessments[-1]))
    result = compare(trace, changed)
    assert not result.same
    aspects = {(item.action_id, item.aspect): (item.left, item.right) for item in result.changes}
    assert aspects[("refund-1", "assessment")] == ("failure", "success")
    assert aspects[("refund-1", "alignment")] == ("contradicted", "consistent")
    assert ("refund-1", "diagnoses") in aspects
    other = refund_trace()
    disjoint = compare(trace, other)
    assert disjoint.only_left == ("refund-1", "email-1") and disjoint.only_right
    assert json.loads(disjoint.to_json())["same"] is False
    with pytest.raises(TypeError):
        compare(trace, trace.to_dict())


def test_details_reports_redact_named_keys_everywhere():
    trace = refund_trace()
    document = render_report(trace, include_details=True, redact=("payment_id", "Currency"))
    assert '&quot;payment_id&quot;: &quot;[redacted]&quot;' in document
    assert "pay_42" not in document
    assert "Values of these keys are redacted: currency, payment_id." in document
    assert render_report(trace, redact=("payment_id",)) == render_report(trace)
    for bad in ("payment_id", ("",), (1,)):
        with pytest.raises(TypeError):
            render_report(trace, include_details=True, redact=bad)


def test_verify_command_adds_a_receipt_for_built_in_predicates(tmp_path, capsys):
    trace = refund_trace()
    unverified = replace(trace, verifications=(), observations=())
    source = tmp_path / "trace.json"
    source.write_text(unverified.to_json(), encoding="utf-8")
    readback = tmp_path / "readback.json"
    readback.write_text(json.dumps(trace.observations[0].to_dict()), encoding="utf-8")
    output = tmp_path / "verified.json"
    assert cli.main(["verify", str(source), "--readback", str(readback),
                     "--output", str(output)]) == 0
    printed = capsys.readouterr().out
    assert "state satisfied, origin confirmed, alignment contradicted" in printed
    verified = Trace.from_json(output.read_text(encoding="utf-8"))
    assert verified.verifications[0].target_effect_ids == trace.verifications[0].target_effect_ids
    assert cli.main(["verify", str(source), "--readback", str(readback),
                     "--output", str(output)]) == 2  # never overwrites
    assert "new file" in capsys.readouterr().err

    record = migrate_trace((FIXTURES / "record-timeout-after-commit.json").read_text(encoding="utf-8"))
    source = tmp_path / "record.json"
    source.write_text(replace(record, verifications=()).to_json(), encoding="utf-8")
    readback.write_text(json.dumps(record.observations[0].to_dict()), encoding="utf-8")
    assert cli.main(["verify", str(source), "--readback", str(readback),
                     "--output", str(tmp_path / "r1.json")]) == 2
    assert "--scope-field" in capsys.readouterr().err
    assert cli.main(["verify", str(source), "--readback", str(readback), "--scope-field",
                     "order_id", "--output", str(tmp_path / "r2.json")]) == 0
    assert "state satisfied" in capsys.readouterr().out


def test_compare_command_can_fail_on_difference(tmp_path, capsys):
    trace = two_action_run().trace()
    left, right = tmp_path / "a.json", tmp_path / "b.json"
    left.write_text(trace.to_json(), encoding="utf-8")
    right.write_text(replace(trace, verifications=trace.verifications[:1]).to_json(),
                     encoding="utf-8")
    assert cli.main(["compare", str(left), str(left), "--fail-on-difference"]) == 0
    assert cli.main(["compare", str(left), str(right)]) == 0
    assert "email-1: state violated -> unverified" in capsys.readouterr().out
    assert cli.main(["compare", str(left), str(right), "--fail-on-difference",
                     "--format", "json"]) == 1
