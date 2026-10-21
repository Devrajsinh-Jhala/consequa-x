"""Independent audit development fixtures; no official tasks or model calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_saved_audit", ROOT / "research/native_agent/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def call(name="read", identity="development-call", **arguments):
    return {"id": identity, "name": name, "arguments": arguments, "requestor": "assistant"}


def messages(name="read", content='{"value":0}', error=False):
    return [{"role": "assistant", "content": None, "tool_calls": [call(name)]},
            {"role": "tool", "id": "development-call", "requestor": "assistant", "content": content, "error": error}]


def row(name="read", *, before="0", after="0", outcome=None, index=0, phase="episode", **arguments):
    return {"schema": "native-tool-dispatch-v1", "call_index": index, "phase": phase,
            "request": {"tool_name": name, "requestor": "assistant", "arguments": arguments},
            "before": {"agent_db_hash": before, "user_db_hash": None},
            "after": {"agent_db_hash": after, "user_db_hash": None},
            "outcome": outcome or {"status": "returned", "content": '{"value":0}'}}


class ToyEnvironment:
    def __init__(self):
        self.value, self.synced = 0, 0

    def get_db_hash(self):
        return str(self.value)

    def get_user_db_hash(self):
        return None

    def make_tool_call(self, name, requestor="assistant", **arguments):
        assert requestor == "assistant"
        if name == "raise":
            raise ValueError("development rejection")
        if name == "write":
            self.value = arguments["value"]
        if name == "returned_error":
            return {"error": "ordinary returned JSON"}
        return {"value": self.value}

    def sync_tools(self):
        self.synced += 1

    @staticmethod
    def to_json_str(value):
        return json.dumps(value, separators=(",", ":"))


def test_ordered_native_call_result_matching_and_id_reuse_between_batches():
    extracted = audit.extract_tool_pairs(messages() + messages())
    assert len(extracted["pairs"]) == 2 and not extracted["pending"]
    bad = messages()
    bad[-1]["id"] = "wrong"
    with pytest.raises(ValueError, match="ID mismatch"):
        audit.extract_tool_pairs(bad)


def test_pending_proposal_is_not_an_executed_call_or_replacement():
    incomplete = messages()[:1]
    with pytest.raises(ValueError, match="unfinished"):
        audit.extract_tool_pairs(incomplete)
    retained = audit.extract_tool_pairs(incomplete, allow_pending=True)
    assert len(retained["pending"]) == 1 and retained["pairs"] == []


def test_orphan_results_and_interrupted_batches_fail_closed():
    with pytest.raises(ValueError, match="orphan"):
        audit.extract_tool_pairs(messages()[1:])
    with pytest.raises(ValueError, match="before required"):
        audit.extract_tool_pairs(messages()[:1] + [{"role": "user", "content": "interruption"}])


def test_requestor_and_nonfinite_argument_corruption_are_rejected():
    bad = messages()
    bad[0]["tool_calls"][0]["requestor"] = "user"
    with pytest.raises(ValueError, match="requestor"):
        audit.extract_tool_pairs(bad)
    bad = messages()
    bad[0]["tool_calls"][0]["arguments"]["value"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        audit.extract_tool_pairs(bad)


def test_native_multitool_container_is_flattened_without_faking_results():
    first = messages()
    wrapped = [first[0], {"role": "tool", "tool_messages": [first[1]]}]
    assert audit.extract_tool_pairs(wrapped) == audit.extract_tool_pairs(first)


def test_initial_history_prefix_ignores_only_metadata_and_is_applied_once():
    prefix = [{"role": "assistant", "content": "development hello", "timestamp": "older", "turn_idx": 9}]
    actual = deepcopy(prefix)
    actual[0].update(timestamp="newer", turn_idx=0)
    assert audit.episode_suffix(actual + messages(), prefix) == messages()
    actual[0]["content"] = "changed"
    with pytest.raises(ValueError, match="prefix differs"):
        audit.episode_suffix(actual + messages(), prefix)


def test_full_replay_checks_actual_read_output_that_native_db_replay_skips():
    environment = ToyEnvironment()
    pairs = audit.extract_tool_pairs(messages())["pairs"]
    result = audit.replay_episode_calls(environment, [row()], pairs)
    assert result["counts"]["calls"] == 1 and environment.synced == 1
    corrupted = row(outcome={"status": "returned", "content": '{"value":99}'})
    with pytest.raises(ValueError, match="outcome differs"):
        audit.replay_episode_calls(ToyEnvironment(), [corrupted], pairs)


def test_full_replay_checks_database_change_and_syncs_after_success():
    transcript = messages("write", '{"value":7}')
    transcript[0]["tool_calls"][0]["arguments"] = {"value": 7}
    saved = row("write", value=7, after="7", outcome={"status": "returned", "content": '{"value":7}'})
    result = audit.replay_episode_calls(ToyEnvironment(), [saved], audit.extract_tool_pairs(transcript)["pairs"])
    assert result["counts"]["db_changed_calls"] == 1
    saved["after"]["agent_db_hash"] = "0"
    with pytest.raises(ValueError, match="DB hash differs"):
        audit.replay_episode_calls(ToyEnvironment(), [saved], audit.extract_tool_pairs(transcript)["pairs"])


def test_returned_error_json_and_raised_exception_are_distinct_native_outcomes():
    environment = ToyEnvironment()
    transcript = messages("raise", "Error: development rejection", error=True)
    saved = row("raise", outcome={"status": "raised", "error_type": "ValueError", "error": "development rejection"})
    result = audit.replay_episode_calls(environment, [saved], audit.extract_tool_pairs(transcript)["pairs"])
    assert result["counts"]["raised"] == 1 and environment.synced == 0
    environment = ToyEnvironment()
    transcript = messages("returned_error", '{"error":"ordinary returned JSON"}')
    saved = row("returned_error", outcome={"status": "returned", "content": '{"error":"ordinary returned JSON"}'})
    result = audit.replay_episode_calls(environment, [saved], audit.extract_tool_pairs(transcript)["pairs"])
    assert result["counts"]["returned"] == 1 and environment.synced == 1


def test_journal_requires_global_consecutive_indices_and_initialization_first():
    audit.validate_journal([row(phase="initialization"), row(index=1)])
    with pytest.raises(ValueError, match="index"):
        audit.validate_journal([row(index=1)])
    with pytest.raises(ValueError, match="initialization call after"):
        audit.validate_journal([row(), row(index=1, phase="initialization")])


def test_replay_never_silently_omits_calls_or_changes_response_error_flags():
    pairs = audit.extract_tool_pairs(messages())["pairs"]
    with pytest.raises(ValueError, match="denominator"):
        audit.replay_episode_calls(ToyEnvironment(), [], pairs)
    pairs[0]["result"]["error"] = True
    with pytest.raises(ValueError, match="ToolMessage"):
        audit.replay_episode_calls(ToyEnvironment(), [row()], pairs)


def test_cost_and_token_unavailability_are_retained_not_replaced_with_zero():
    rows = [{"role": "assistant", "content": "deterministic", "cost": 0.0, "usage": None},
            {"role": "assistant", "content": "model response", "cost": None,
             "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
            {"role": "user", "content": "reply", "cost": 0.0, "usage": {"total_tokens": 9}}]
    result = audit.message_costs(rows)
    assert result["assistant"]["native_cost"] is None
    assert result["assistant"]["unavailable_cost_messages"] == 1
    assert result["assistant"]["usage"]["prompt_tokens"] == {
        "sum_observed": 12, "observed_messages": 1, "unavailable_messages": 1}
    assert result["user"]["native_cost"] == 0.0


def test_offline_guard_refuses_network_and_restores_socket_functions():
    original = socket.create_connection
    with pytest.raises(ValueError, match="network attempted"):
        with audit.no_network() as attempts:
            with pytest.raises(RuntimeError, match="forbidden"):
                socket.create_connection(("127.0.0.1", 1))
    assert len(attempts) == 1 and socket.create_connection is original


def test_unexpected_required_judge_fails_before_any_native_import(monkeypatch):
    monkeypatch.setattr(audit, "verify_native_source", lambda root: {"commit": "synthetic", "files": {}})
    task = SimpleNamespace(evaluation_criteria=SimpleNamespace(reward_basis=[SimpleNamespace(value="NL_ASSERTION")]))
    with pytest.raises(ValueError, match="unexpected required"):
        audit.audit_native_episode({}, task, [], {}, {}, "unused")


def test_source_guard_records_pure_windows_checkout_eol_but_rejects_code_edits(tmp_path, monkeypatch):
    names = ["src/tau2/evaluator/evaluator.py", "src/tau2/environment/environment.py",
             "data/tau2/domains/airline/development.json"]
    original = b"# synthetic source identity\n"
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original.replace(b"\n", b"\r\n"))
    def git_output(command):
        if "rev-parse" in command:
            return (audit.UPSTREAM_COMMIT + "\n").encode()
        if "ls-tree" in command:
            return ("\n".join(names) + "\n").encode()
        return original
    monkeypatch.setattr(audit.subprocess, "check_output", git_output)
    result = audit.verify_native_source(tmp_path)
    assert all(item["checkout_mode"] == "git_lf_to_windows_crlf" for item in result["files"].values())
    (tmp_path / names[0]).write_bytes(b"edited implementation\r\n")
    with pytest.raises(ValueError, match="beyond checkout EOL"):
        audit.verify_native_source(tmp_path)
