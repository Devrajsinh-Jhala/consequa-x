"""Saved-artifact audit CLI fixtures; no official tasks, native imports or model."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.native_agent.protocol import make_schedule, select_metadata, verify_artifact_manifest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("independent_native_audit_cli",
    ROOT / "scripts/audit_native_external_benchmark.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def write_journal(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({"event_index": index, **row}) + "\n"
                            for index, row in enumerate(rows)), encoding="utf-8")


def metadata():
    tasks = [{"id": f"toy-{present}-{index}", "evaluation_criteria": {
        "reward_basis": ["DB", "COMMUNICATE"], "communicate_info": ["toy criterion"] if present else []}}
        for present in (True, False) for index in range(6)]
    return select_metadata(tasks)


def test_jsonl_reader_retains_valid_prefix_and_unfinished_line_diagnostic(tmp_path):
    path = tmp_path / "partial.jsonl"
    write_journal(path, [{"kind": "request_start", "call_index": 0}])
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"event_index":1,"kind":')
    result = runner.read_journal(path)
    assert result["available"] and len(result["rows"]) == 1
    assert result["errors"][0]["line"] == 2
    assert runner.read_journal(tmp_path / "absent.jsonl") == {"available": False, "rows": [], "errors": []}


def test_jsonl_reader_refuses_reordered_metadata_and_nonfinite_values(tmp_path):
    path = tmp_path / "corrupt.jsonl"
    path.write_text('{"event_index":2,"value":0}\n', encoding="utf-8")
    assert runner.read_journal(path)["errors"]
    path.write_text('{"event_index":0,"value":NaN}\n', encoding="utf-8")
    assert runner.read_journal(path)["errors"]


def test_partial_model_costs_preserve_pending_failed_and_unknown_usage(tmp_path):
    write_journal(tmp_path / "model-calls.jsonl", [
        {"kind": "request_start", "call_index": 0, "request": {
            "model": "openai/fixture", "messages": [{"role": "user", "content": "fixture"}]}},
        {"kind": "request_return", "call_index": 0,
         "response": {"usage": {"prompt_tokens": 10, "completion_tokens": 3}}},
        {"kind": "request_start", "call_index": 1},
        {"kind": "request_error", "call_index": 1},
        {"kind": "request_start", "call_index": 2}])
    model = runner.journal_diagnostics(tmp_path, {})["model"]
    assert (model["attempted"], model["returned"], model["failed"], model["pending"]) == (3, 1, 1, 1)
    assert model["tokens"]["prompt_tokens"] == {
        "sum_observed": 10, "observed_responses": 1, "unavailable_attempts": 2}
    assert model["http_generation_dispatch_records"] is None


def test_tool_counts_use_native_mutation_flag_and_do_not_label_repeats_harm(tmp_path):
    def call(name, phase="episode"):
        return {"phase": phase, "request": {"tool_name": name, "requestor": "assistant", "arguments": {"id": "toy"}},
                "before": {"agent_db_hash": "a", "user_db_hash": None},
                "after": {"agent_db_hash": "a", "user_db_hash": None},
                "outcome": {"status": "returned", "content": "toy"}}
    write_journal(tmp_path / "tool-dispatch.jsonl", [call("write", "initialization"),
        call("write"), call("read"), call("write"), call("transfer")])
    types = {"write": {"type": "write", "mutates_state": True},
             "read": {"type": "read", "mutates_state": False},
             "transfer": {"type": "write", "mutates_state": False}}
    result = runner.journal_diagnostics(tmp_path, types)["tools"]
    assert result["dispatches"] == 4 and result["mutating_dispatches"] == 2
    assert result["tool_type_write"] == 3 and result["repeated_same_payload_mutating_dispatches"] == 1
    assert not any("harm" in key for key in result)


def test_receipt_declarations_are_not_claimed_as_independent_semantic_labels(tmp_path):
    write_journal(tmp_path / "controller-events.jsonl", [{"event": "receipt", "receipt": {
        "verification": {"status": "unknown", "origin": "unknown"}}}, {"event": "guard_block"}])
    result = runner.journal_diagnostics(tmp_path, {})["controller"]
    assert result["guard_blocks"] == 1 and result["receipt_count"] == 1
    assert result["receipt_declared_status_counts"] == {"unknown": 1}
    assert result["receipt_semantic_status_independently_recomputed"] is False


def test_matrix_requires_all_planned_slots_and_exact_schedule_join():
    selection = metadata()
    protocol = {"selection": selection, "schedule": make_schedule(selection)}
    receipt = {"protocol_sha256": runner.canonical_sha(protocol), "all_planned_slots": [
        {**slot, "status": "unstarted"} for slot in protocol["schedule"]]}
    assert len(runner.validate_matrix(protocol, receipt)) == 48
    missing = deepcopy(receipt)
    missing["all_planned_slots"].pop()
    with pytest.raises(ValueError, match="48"):
        runner.validate_matrix(protocol, missing)
    altered = deepcopy(receipt)
    altered["all_planned_slots"][0]["arm"] = "invalid"
    with pytest.raises(ValueError, match="Disposition/schedule"):
        runner.validate_matrix(protocol, altered)


def test_all_unstarted_matrix_is_48_operational_zeros_not_48_native_reward_zeros():
    rows = [{**slot, "collection_disposition": "unstarted", "operational_success": 0,
             "native_reward": None, "normal_termination": None, "episode_audit_passed": None}
            for slot in make_schedule(metadata())]
    result = runner.summarize(rows)
    assert result["distinct_task_ids"] == 12 and result["planned_slots"] == 48
    assert result["groups"]["G:all"]["planned_slots"] == 12
    assert result["groups"]["G:all"]["native_reward_unavailable"] == 12
    assert result["groups"]["G:all"]["native_reward_observed"] == 0
    assert result["groups"]["G:all"]["native_required_components"]["DB"] == {
        "observed": 0, "unavailable": 12, "succeeded": 0, "failed": 0}
    assert result["groups"]["G:nonempty"]["planned_slots"] == 6
    assert result["groups"]["G:empty"]["planned_slots"] == 6
    assert all(value is None for pair in result["paired_tasks"] for value in pair["native_reward_by_arm"].values())


def test_bad_collection_manifest_fails_before_protocol_or_native_imports(tmp_path, monkeypatch):
    collection = tmp_path / "collection"
    collection.mkdir()
    (collection / "manifest.json").write_text('{"files":{}}', encoding="utf-8")
    (collection / "unbound.txt").write_text("unbound", encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Later stage must not run after manifest failure")
    monkeypatch.setattr(runner, "verify_frozen_protocol", forbidden)
    args = SimpleNamespace(collection=collection, output=tmp_path / "audit", protocol="unused",
        protocol_commit="1" * 40, source_root="unused", native_root="unused", wheel="unused")
    assert runner.execute(args) == 1
    result = json.loads((args.output / "audit-result.json").read_text(encoding="utf-8"))
    assert result["passed"] is False and result["error"]["type"] == "ValueError"
    assert result["new_model_calls"] == 0 and result["rows"] == []
    verify_artifact_manifest(args.output)


def test_completed_accounting_requires_exact_context_and_transport_attempt_denominators(tmp_path):
    for name in ("controller-events", "tool-dispatch", "tool-dispatch-starts"):
        write_journal(tmp_path / (name + ".jsonl"), [])
    write_journal(tmp_path / "model-calls.jsonl", [
        {"kind": "request_start", "call_index": 0, "request": {
            "model": "openai/fixture", "messages": [{"role": "user", "content": "fixture"}]}},
        {"kind": "request_return", "call_index": 0,
         "response": {"usage": {"prompt_tokens": 7, "completion_tokens": 2}}}])
    wire = {"model": "fixture", "messages": [{"role": "user", "content": "fixture"}]}
    digest = runner.hashlib.sha256(json.dumps(wire, sort_keys=True).encode()).hexdigest()
    (tmp_path / "network-guard.json").write_text(json.dumps({"events": [
        {"kind": "http", "generation_request": True, "parsed_body_sha256": digest}]}), encoding="utf-8")
    (tmp_path / "context-checks.json").write_text(json.dumps({"checks": [
        {"passed": True, "request": wire, "request_sha256": digest}]}), encoding="utf-8")
    execution = {"model_requests": {"attempted": 1, "completed": 1, "failed": 0,
        "prompt_tokens": 7, "completion_tokens": 2}, "actual_tool_dispatches": 0,
        "completed_tool_dispatches": 0, "inflight_tool_dispatches": []}
    diagnostics = runner.journal_diagnostics(tmp_path, {})
    runner.verify_completed_accounting(tmp_path, diagnostics, execution)
    network_path = tmp_path / "network-guard.json"
    original = network_path.read_text(encoding="utf-8")
    network = json.loads(original)
    network["events"][0]["parsed_body_sha256"] = "0" * 64
    network_path.write_text(json.dumps(network), encoding="utf-8")
    with pytest.raises(ValueError, match="body/context receipt binding"):
        runner.verify_completed_accounting(tmp_path, diagnostics, execution)
    network_path.write_text(original, encoding="utf-8")
    (tmp_path / "context-checks.json").write_text('{"checks":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="context dispatch"):
        runner.verify_completed_accounting(tmp_path, diagnostics, execution)


def test_completed_accounting_rejects_unavailable_journals_instead_of_zero_cost(tmp_path):
    with pytest.raises(ValueError, match="unavailable/malformed"):
        runner.verify_completed_accounting(tmp_path, runner.journal_diagnostics(tmp_path, {}), {})


def test_native_wire_link_accepts_only_documented_null_tool_content_normalization():
    native = {"model": "openai/fixture", "messages": [{"role": "assistant", "content": None,
        "tool_calls": [{"id": "call0", "type": "function", "function": {
            "name": "get_user_details", "arguments": '{"user_id":"fixture"}'}}]}],
        "tools": [{"type": "function", "function": {"name": "get_user_details", "parameters": {
            "type": "object", "properties": {"user_id": {"type": "string"}}}}}],
        "max_tokens": 512, "temperature": 0, "seed": 1701, "tool_choice": "auto"}
    wire = deepcopy(native)
    wire["model"] = "fixture"
    del wire["messages"][0]["content"]
    runner.verify_model_wire(native, wire)
    for key, replacement in (("model", "other"), ("tools", []), ("seed", 42),
                             ("max_tokens", 256), ("temperature", 1), ("tool_choice", "none")):
        altered = deepcopy(wire)
        altered[key] = replacement
        with pytest.raises(ValueError, match="differ"):
            runner.verify_model_wire(native, altered)
    altered = deepcopy(wire)
    altered["messages"][0]["tool_calls"][0]["function"]["arguments"] = '{"user_id":"changed"}'
    with pytest.raises(ValueError, match="history"):
        runner.verify_model_wire(native, altered)
    altered = deepcopy(wire)
    altered["messages"][0]["content"] = "rewritten"
    with pytest.raises(ValueError, match="history"):
        runner.verify_model_wire(native, altered)
    altered = deepcopy(wire)
    altered["temperature"] = False
    with pytest.raises(ValueError, match="parameter differs"):
        runner.verify_model_wire(native, altered)
    altered = deepcopy(wire)
    altered["stop"] = ["rewritten"]
    with pytest.raises(ValueError, match="unbound"):
        runner.verify_model_wire(native, altered)
