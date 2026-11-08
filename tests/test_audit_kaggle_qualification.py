"""Invented saved-output fixtures only; no GPU, inference or archive execution."""
from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile

import pytest

from scripts import audit_kaggle_qualification as audit


def encoded(value):
    return audit.canonical(value)


def make_raw(*, call=True, text=""):
    condition = {"runtime_version": "0.40.10", "archive_sha256": "1e8ad2d2a394efdd235bee74deec237badd95142ffba77588140ab2a9ecec227",
        "gpu_name": "INVENTED GPU fixture", "compute_capability": "fixture", "driver_version": "fixture",
        "python_version": "fixture", "library_versions": {"consequa-x": "fixture"}}
    schedule = encoded([{"slot": 0, "model_id": "invented-model"}])
    identity = {"schema": "conseqax-kaggle-checkpoint-v1", "planned_slots": 1,
        "schedule": audit.digest(schedule), "lineage": {"condition": condition, "source_commit": "b" * 40}}
    raw = {"schedule.json": schedule, "identity.json": encoded(identity)}
    event = {"sequence": 0, "previous_sha256": None, "identity": audit.digest(raw["identity.json"]),
        "kind": "session", "session_id": "invented-session"}
    event["content_sha256"] = audit.digest(encoded(event))["sha256"]
    raw["events/000000.json"] = encoded(event)
    prefix = "sessions/invented-session/fixture/"
    runtime = {"model": "invented-model", "model_digest": "c" * 64, "context_tokens": 8192,
        "runner_pid": 123, "runner_create_time": 1000.0, "model_blob_sha256": "a" * 64}
    line = "load_tensors: offloaded 2/2 layers to GPU"
    proof = {"schema": "conseqax-gpu-layer-offload-v1", "runner_pid": 123, "runner_create_time": 1000.0,
        "model_blob_sha256": "a" * 64, "requested_gpu_layers": 999, "offloaded_layers": 2, "total_layers": 2,
        "log_line": line, "log_line_sha256": hashlib.sha256(line.encode()).hexdigest()}
    request = {"model": "invented-model", "max_tokens": 128}
    function = {"name": "lookup_echo", "arguments": '{"name":"test-item"}'}
    message = {"content": text}
    parsed_calls = []
    if call:
        message["tool_calls"] = [{"id": "invented-call", "function": function}]
        parsed_calls = [{"id": "invented-call", **function}]
    finish = "tool_calls" if call else "stop"
    response = {"model": "invented-model", "choices": [{"message": message, "finish_reason": finish}],
        "usage": {"completion_tokens": 7}}
    prompt = "INVENTED prompt; not a measured task"
    context = {"passed": True, "request": request,
        "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(),
        "runtime_binding": runtime,
        "resident_response": {"models": [{"name": runtime["model"], "digest": runtime["model_digest"],
            "context_length": 8192, "size": 1000, "size_vram": 1000}]},
        "provider_rendered_prompt": prompt, "runtime_tokenizer": {"tokens": [1, 2]},
        "context": {"rendered_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "prompt_tokens": 2, "required_tokens": 194, "context_tokens": 8192,
            "reserve_tokens": 64, "fits": True}}
    records = {"parsed-turn.json": {"text": text, "tool_calls": parsed_calls, "finish_reason": finish},
        "client/0001-request.bin": request, "client/0001-response.bin": response,
        "client/0001-response-meta.json": {"status": 200, "body_sha256": audit.digest(encoded(response))["sha256"]},
        "client/0001-context.json": context,
        "client/kaggle-gpu-config.json": {"condition": condition, "runtime": runtime,
            "gpu_load_proof": proof, "cpu_fallback_allowed": False},
        "client/0001-terminal.json": {"returned": True, "dispatches": 1},
        "lease/runtime-binding.json": runtime, "lease/gpu-load-proof.json": proof}
    if call:
        records["preflight.json"] = {"passed": True, "model_id": "invented-model", "condition": condition}
    raw.update({prefix + key: encoded(value) for key, value in records.items()})
    return raw, prefix


def zipped(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def pack(tmp_path, raw, *, mutate_nested=None, mutate_outer=None, state=None):
    identity = json.loads(raw["identity.json"])
    state = state or audit.checkpoint_state(raw, identity)
    nested = {**raw, "checkpoint.json": encoded({"files": {key: audit.digest(value) for key, value in raw.items()}})}
    if mutate_nested:
        mutate_nested(nested)
    checkpoint = zipped(nested)
    outer = {"conseqax-benchmark/" + key: value for key, value in raw.items()}
    outer.update({"checkpoint.zip": checkpoint,
        "checkpoint-export.json": encoded({"archive": audit.digest(checkpoint), "state": state}),
        "progress.json": encoded({"state": state})})
    if mutate_outer:
        mutate_outer(outer)
    target = tmp_path / "invented-results.zip"
    target.write_bytes(zipped(outer))
    return target


def change_json(raw, name, update):
    value = json.loads(raw[name])
    update(value)
    raw[name] = encoded(value)


@pytest.mark.parametrize("call", [True, False])
def test_synthetic_qualification_audit_preserves_pass_or_failure_without_inference(tmp_path, call):
    raw, _ = make_raw(call=call)
    report = audit.audit_archive(pack(tmp_path, raw))
    row = report["models"][0]
    assert report["byte_consistency_passed"]
    assert report["checkpoint_state"]["started"] == 0
    assert row["exact_required_tool_call"] is call
    assert row["raw_api_tool_calls"] == int(call)
    assert row["reported_output_tokens"] == 7
    assert row["offloaded_layers"] == row["total_layers"] == 2
    assert report["scope"]["fresh_inference_calls"] == 0
    assert report["scope"]["archive_code_executed"] is False
    assert report["scope"]["underlying_generated_text_before_provider_parser_available"] is False


def test_changed_nested_archive_hash_is_rejected(tmp_path):
    raw, _ = make_raw()
    path = pack(tmp_path, raw, mutate_outer=lambda files: files.__setitem__("checkpoint.zip", files["checkpoint.zip"] + b"changed"))
    with pytest.raises(ValueError, match="nested checkpoint ZIP"):
        audit.audit_archive(path)


def test_corrupted_inner_file_rejected_even_when_outer_archive_hash_is_rebound(tmp_path):
    raw, prefix = make_raw()
    path = pack(tmp_path, raw, mutate_nested=lambda files: files.__setitem__(prefix + "parsed-turn.json", b"changed"))
    with pytest.raises(ValueError, match="Byte binding differs"):
        audit.audit_archive(path)


def test_schedule_changed_and_resealed_still_rejected_by_identity_binding(tmp_path):
    raw, _ = make_raw()
    state = audit.checkpoint_state(raw, json.loads(raw["identity.json"]))
    raw["schedule.json"] = encoded([{"slot": 0, "model_id": "different-model"}])
    with pytest.raises(ValueError, match="schedule"):
        audit.audit_archive(pack(tmp_path, raw, state=state))


def test_raw_and_native_parsed_response_inconsistency_rejected_after_resealing(tmp_path):
    raw, prefix = make_raw()
    change_json(raw, prefix + "parsed-turn.json", lambda turn: turn.update(text="invented tampering"))
    with pytest.raises(ValueError, match="raw API response and parsed turn disagree"):
        audit.audit_archive(pack(tmp_path, raw))


def test_edited_event_checksum_rejected_after_resealing(tmp_path):
    raw, _ = make_raw()
    state = audit.checkpoint_state(raw, json.loads(raw["identity.json"]))
    change_json(raw, "events/000000.json", lambda event: event.update(session_id="changed"))
    with pytest.raises(ValueError, match="Event content checksum"):
        audit.audit_archive(pack(tmp_path, raw, state=state))


def test_edited_gpu_layer_proof_rejected_after_resealing(tmp_path):
    raw, prefix = make_raw()
    for name in [prefix + "lease/gpu-load-proof.json", prefix + "client/kaggle-gpu-config.json"]:
        change_json(raw, name, lambda value: (value.get("gpu_load_proof") or value).update(offloaded_layers=1))
    with pytest.raises(ValueError, match="all layers"):
        audit.audit_archive(pack(tmp_path, raw))


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../b", "C:/drive"])
def test_unsafe_outer_members_rejected_without_extraction(tmp_path, name):
    raw, _ = make_raw()
    path = pack(tmp_path, raw, mutate_outer=lambda files: files.__setitem__(name, b"do not execute"))
    with pytest.raises(ValueError):
        audit.audit_archive(path)
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("raw_name", [b"a\\b", b"a\x00b"])
def test_raw_archive_names_rejected_even_if_zipinfo_normalizes_them(tmp_path, raw_name):
    # ZipInfo normalizes these names on Windows; modify encoded headers to
    # exercise an actual untrusted ZIP containing their original bytes.
    path = tmp_path / "unsafe-encoded-name.zip"
    data = zipped({"a/b": b"invented nonexecutable content"})
    assert data.count(b"a/b") == 2
    path.write_bytes(data.replace(b"a/b", raw_name))
    with pytest.raises(ValueError):
        audit.audit_archive(path)


def test_case_colliding_archive_members_are_rejected(tmp_path):
    path = tmp_path / "collision.zip"
    path.write_bytes(zipped({"one": b"a", "ONE": b"b"}))
    with pytest.raises(ValueError, match="case-colliding"):
        audit.audit_archive(path)


def test_archive_expansion_budget_is_enforced(tmp_path, monkeypatch):
    path = tmp_path / "too-many.zip"
    path.write_bytes(zipped({"one": b"a", "two": b"b"}))
    monkeypatch.setattr(audit, "MAX_ENTRIES", 1)
    with pytest.raises(ValueError, match="audit limits"):
        audit.audit_archive(path)


def test_linked_archive_members_are_rejected(tmp_path):
    item = zipfile.ZipInfo("link")
    item.create_system = 3
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    path = tmp_path / "linked.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(item, b"/outside")
    with pytest.raises(ValueError, match="Linked"):
        audit.audit_archive(path)


def test_curated_report_does_not_include_generated_content(tmp_path):
    secret = "INVENTED_PRIVATE_MODEL_TEXT_NOT_FOR_REPORT"
    raw, _ = make_raw(call=False, text=secret)
    report = audit.audit_archive(pack(tmp_path, raw))
    assert secret not in json.dumps(report)
    assert report["models"][0]["raw_api_content_characters"] == len(secret)


def test_cli_preserves_existing_report(tmp_path):
    raw, _ = make_raw()
    path = pack(tmp_path, raw)
    output = tmp_path / "report.json"
    assert audit.main(["--archive", str(path), "--output", str(output)]) == 0
    retained = output.read_bytes()
    with pytest.raises(FileExistsError):
        audit.main(["--archive", str(path), "--output", str(output)])
    assert output.read_bytes() == retained
