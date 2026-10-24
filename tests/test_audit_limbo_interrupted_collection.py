"""Temporary invented prefixes only; never substitute test grades for results."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts import audit_limbo_interrupted_collection as subject


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


@pytest.fixture
def collection(tmp_path):
    directory = tmp_path / "original"
    directory.mkdir()
    value = {"schedule": [{"slot": index, "world_rank": index // 4,
        "arm": subject.portable.ARMS[index % 4], "spec": {"synthetic_only": True}}
        for index in range(96)], "limits": {"max_requests": 16}}
    write(directory / "claim.json", {"synthetic": True})
    write(directory / "protocol.json", value)
    first = value["schedule"][0]
    slot = directory / "slot-000"
    receipt = {**{key: first[key] for key in ("slot", "world_rank", "arm")},
        "directory": "slot-000", "status": "child_returned", "exit_code": 0}
    write(slot / "worker-config.json", {"protocol": value, "slot": first})
    write(slot / "parent-terminal.json", receipt)
    write(slot / "worker-terminal.json", {"status": "native_returned"})
    write(slot / "manifest.json", subject.inventory(slot))
    write(directory / "disposition-000.json", receipt)
    partial = directory / "slot-001"
    write(partial / "worker-config.json", {"protocol": value, "slot": value["schedule"][1]})
    return directory, value


def test_all_planned_slots_kept_and_partial_has_no_invented_terminal(collection):
    directory, value = collection
    before = subject.inventory(directory)
    slots = subject.inspect_slots(directory, value)
    assert len(slots) == 96
    assert [row[1] for row in slots[:3]] == ["sealed_native_return",
        "interrupted_terminal_unavailable", "unstarted_interruption"]
    assert sum(row[2] is None for row in slots) == 94
    assert before == subject.inventory(directory)


@pytest.mark.parametrize("change,match", [
    ("bad_manifest", "Sealed file changed"),
    ("extra_artifact", "Unplanned original"),
    ("partial_terminal", "Partial slot contains"),
    ("wrong_config", "worker configuration differs"),
    ("noncontiguous", "Noncontiguous"),
])
def test_prefix_integrity_fails_closed(collection, change, match):
    directory, value = collection
    if change == "bad_manifest":
        with (directory / "slot-000/worker-terminal.json").open("a", encoding="utf-8") as stream:
            stream.write(" ")
    elif change == "extra_artifact":
        write(directory / "unexpected.json", {})
    elif change == "partial_terminal":
        write(directory / "slot-001/native-result.json", {"grade": "must not be accepted"})
    elif change == "wrong_config":
        write(directory / "slot-001/worker-config.json", {})
    else:
        write(directory / "slot-003/worker-config.json", {"protocol": value, "slot": value["schedule"][3]})
    with pytest.raises(ValueError, match=match):
        subject.inspect_slots(directory, value)


def test_unknown_outcomes_and_usage_never_replaced_by_zero(collection):
    directory, value = collection
    partial = directory / "slot-001"
    model = partial / "model"
    model.mkdir()
    request = model / "0001-request.bin"
    request.write_bytes(b"synthetic request, no generation")
    records = [{"event": "request_start", "invocation": 1},
        {"event": "before_dispatch", "invocation": 1, "dispatches": 1,
         "request_sha256": subject.binding(request)["sha256"]}]
    (model / "model-calls.jsonl").write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    fake_auditor = SimpleNamespace(validate_model_journal=lambda records, known, cap: None)
    row = subject.interrupted_row(partial, value["schedule"][1], value, fake_auditor)
    assert row["started"] is True and row["native_grade"] is None
    assert row["grade_available"] is False and row["audit_complete"] is False
    prefix = row["observed_journal_prefix"]
    assert prefix["generation_dispatch_attempts"] == 1
    assert prefix["missing_terminal_for_started_invocations"] == 1
    assert prefix["usage"]["output_tokens"]["unknown_started_invocations"] == 1
    assert prefix["usage"]["output_tokens"]["complete_for_actual_episode"] is False
    assert prefix["actual_work_may_exceed_saved_prefix"] is True
    unstarted = subject.interrupted_row(None, value["schedule"][2], value, fake_auditor)
    assert unstarted["started"] is False and unstarted["native_grade"] is None
    assert "usage" not in unstarted


def test_partial_raw_request_tamper_is_rejected(collection):
    directory, value = collection
    model = directory / "slot-001/model"
    model.mkdir()
    (model / "0001-request.bin").write_bytes(b"changed")
    (model / "model-calls.jsonl").write_text(json.dumps({"event": "request_start", "invocation": 1}) + "\n"
        + json.dumps({"event": "before_dispatch", "invocation": 1, "dispatches": 1,
            "request_sha256": "0" * 64}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="request bytes differ"):
        subject.interrupted_row(directory / "slot-001", value["schedule"][1], value,
            SimpleNamespace(validate_model_journal=lambda *args: None))


def test_partial_metering_is_checked_against_saved_raw_response(tmp_path):
    raw_path = tmp_path / "0001-response.bin"
    raw_path.write_text(json.dumps({"usage": {"prompt_tokens": 7, "completion_tokens": 2,
        "prompt_tokens_details": {"cached_tokens": 3}}}), encoding="utf-8")
    terminal = {"invocation": 1, "dispatches": 1, "returned": True,
        "usage": {"input_tokens": {"available": True, "value": 7},
            "output_tokens": {"available": True, "value": 2},
            "cached_tokens": {"available": True, "value": 3},
            "reasoning_tokens": {"available": False, "value": None}}}
    write(tmp_path / "0001-terminal.json", terminal)
    write(tmp_path / "0001-response-meta.json", {"status": 200,
        "body_sha256": subject.binding(raw_path)["sha256"]})
    assert subject.check_partial_model_terminal(tmp_path, 1) == terminal
    terminal["usage"]["reasoning_tokens"] = {"available": True, "value": 0}
    write(tmp_path / "0001-terminal.json", terminal)
    with pytest.raises(ValueError, match="usage terminal differ"):
        subject.check_partial_model_terminal(tmp_path, 1)


def test_incomplete_or_corrupt_journal_stays_explicitly_partial(tmp_path):
    path = tmp_path / "partial.jsonl"
    path.write_bytes(b'{"event":"request_start"}\n{"trunc')
    records, metadata = subject.valid_prefix(path)
    assert len(records) == 1 and metadata["first_invalid"]["line"] == 2
    assert metadata["complete_accounting"] is False and metadata["trailing_newline"] is False


def test_original_final_seal_is_not_silently_replaced(collection):
    directory, value = collection
    protocol = directory / "protocol.json"
    claim = {"protocol_commit": "a" * 40, "protocol_sha256": subject.binding(protocol)["sha256"],
        "retry_resume_replacement": False}
    write(directory / "claim.json", claim)
    subject.check_claim(directory, value, protocol, "a" * 40)
    write(directory / "collection.json", {"historical": "existing final record"})
    with pytest.raises(ValueError, match="without a final collector seal"):
        subject.check_claim(directory, value, protocol, "a" * 40)
