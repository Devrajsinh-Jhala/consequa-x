"""Boundary/retention tests for the isolated local judge; no live model requests."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from urllib.error import URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_matched_trace_judge as judge
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import run_policy_scenario
from consequa_x.benchmark.runner import ScenarioConfig
from consequa_x.policies import PolicyError, ScriptedRefundPolicy


def trace():
    return run_policy_scenario(ScenarioConfig("private-fault-marker", Fault.TIMEOUT_AFTER_COMMIT),
                               ScriptedRefundPolicy(), seed=7).trace


def envelope(state="satisfied", linked="satisfied", origin="confirmed"):
    return {"model": judge.MODEL, "done": True, "message": {
        "role": "assistant", "content": json.dumps({"state": state,
        "action_linked": linked, "origin": origin})}, "eval_count": 19}


def identity(settings=None):
    return {"server_version": {"version": "frozen-test-server"}, "models": {
        judge.MODEL: {"tag": {"name": judge.MODEL, "digest": judge.MODEL_DIGEST},
                      "inspection": {"no_declared_remote_routing": True}}}}


class Response:
    status = 200

    def __init__(self, value):
        self.body = value if isinstance(value, bytes) else json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class Opener:
    def __init__(self, results):
        self.results = list(results)
        self.chats = []

    def open(self, request, timeout):
        if request.full_url.endswith("/api/show"):
            return Response({"model_info": {}, "details": {}, "capabilities": []})
        if request.full_url.endswith("/api/tags"):
            return Response({"models": [{"name": judge.MODEL, "digest": judge.MODEL_DIGEST}]})
        assert request.full_url == judge.SETTINGS["base_url"] + "/api/chat"
        self.chats.append(json.loads(request.data))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return Response(result)


def fixture_freeze(tmp_path, monkeypatch, statuses=("available", "available", "unavailable")):
    factual_trace = trace()
    prediction = judge.matched_predictions(factual_trace)
    gold = {"state": True, "action_linked": True, "origin": "confirmed"}
    prepared = []
    for index, status in enumerate(statuses):
        entry = {"slot": {"slot_id": f"episode_{index:05d}", "repetition": 0,
                           "model": "masked-generator-a" if index < 2 else "generator-b",
                           "prompt_version": "profile-a", "case_id": f"case-{index}"},
                 "judge_seed": judge.SEED_BASE + index, "input_status": status,
                 "factual_status": "completed" if status == "available" else "failed"}
        if status == "available":
            entry.update(input=judge.public_input(factual_trace),
                         evaluation={"gold": gold, "baselines": prediction})
        prepared.append(entry)
    monkeypatch.setattr(judge, "load_pool", lambda *args: (deepcopy(prepared), {}, {
        "planned": 504, "completed": 503, "failed": 1,
        "protocol_sha256": "pool-hash", "analysis_sha256": "analysis-hash"}))
    out = tmp_path / "frozen"
    judge.freeze("unused-study", "unused-analysis", out, inspector=identity)
    return out


def factory(opener):
    def make(*args, **kwargs):
        instance = judge.TraceJudge(*args, **kwargs)
        instance._opener = opener
        return instance
    return make


def test_allowlist_excludes_hidden_text_and_consistently_aliases_ids():
    marker = "NEVER_SEND_HIDDEN_LABEL_OR_RATIONALE"
    data = trace().to_dict()
    data["actions"][0]["arguments"]["hidden_gold"] = marker
    data["actions"][0]["contract"]["expected"]["hidden_fault"] = marker
    data["events"][0]["data"]["value"] = marker
    data["events"][0]["data"]["model"] = marker
    data["responses"][0]["result"]["private_error_detail"] = marker
    data["observations"][0]["records"][0]["evaluator_truth"] = marker
    captured = type(trace()).from_dict(data)
    value = judge.public_input(captured)
    encoded = json.dumps(value)
    assert marker not in encoded
    assert all(field not in value for field in ("assessment", "events", "verifications", "explanation"))
    assert "RefundAgent" not in encoded and "pay_42" not in encoded and "refund:7" not in encoded
    row = value["observation"]["records"][0]
    assert row["actor"] == value["action"]["actor"]
    assert row["action_id"] == value["action"]["action_id"]
    assert row["payment_id"] == value["action"]["contract"]["expected"]["payment_id"]
    assert row["attempt_id"] == value["responses"][0]["attempt_id"]
    assert value["responses"][0]["status"] == "timeout"
    assert set(value) == {"action", "attempts", "responses", "observation"}


def test_refund_effect_identifier_equality_survives_aliasing():
    captured = run_policy_scenario(ScenarioConfig("clean", Fault.CLEAN), ScriptedRefundPolicy(), seed=99).trace
    value = judge.public_input(captured)
    assert value["responses"][0]["result"]["refund_id"] == value["observation"]["records"][0]["effect_id"]
    assert value == judge.public_input(captured)


@pytest.mark.parametrize("bad", [
    '{"state":"satisfied","action_linked":"satisfied","origin":"confirmed","reason":"x"}',
    '{"state":true,"action_linked":"satisfied","origin":"confirmed"}',
    '{"state":"satisfied","state":"violated","action_linked":"satisfied","origin":"confirmed"}',
    '```json\n{}\n```', '{"state":"success","action_linked":"satisfied","origin":"confirmed"}',
])
def test_strict_three_target_schema_refuses_invalid_or_duplicate_output(bad):
    response = envelope()
    response["message"]["content"] = bad
    with pytest.raises(PolicyError):
        judge.parse_prediction(response)


def test_unknown_is_an_abstention_and_not_failure():
    assert judge.parse_prediction(envelope("unknown", "unknown", "unknown")) == {
        "state": None, "action_linked": None, "origin": "unknown"}


def test_token_limit_refuses_even_if_remaining_content_is_valid_json():
    response = envelope()
    response["done_reason"] = "length"
    with pytest.raises(PolicyError, match="token limit"):
        judge.parse_prediction(response)


def test_freeze_writes_all_inputs_before_calls_and_binds_definition(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    protocol = judge.validate_freeze(out)
    assert protocol["selected_planned"] == 3 and protocol["available_inputs"] == 2
    assert protocol["max_chat_calls"] == 2
    assert protocol["pool_context"]["planned"] == 504
    assert not (out / "calls").exists() and not (out / "request-journal.jsonl").exists()
    assert len(list((out / "inputs").glob("*.json"))) == 2
    assert (out / "evaluation-context.json").exists()
    seeds = [entry["judge_seed"] for entry in protocol["schedule"]]
    assert len(set(seeds)) == len(seeds) and seeds == [judge.SEED_BASE + i for i in range(3)]
    with pytest.raises(ValueError, match="new or empty"):
        judge.freeze("unused", "unused", out, inspector=identity)


def test_resume_retains_failure_and_unavailable_without_redraw(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    invalid = envelope()
    invalid["message"]["content"] = "not JSON"
    opener = Opener([invalid, envelope()])
    judge.run(out, limit=1, inspector=identity, judge_factory=factory(opener))
    assert len(opener.chats) == 1
    judge.run(out, inspector=identity, judge_factory=factory(opener))
    assert len(opener.chats) == 2
    judge.run(out, inspector=identity, judge_factory=factory(opener))
    assert len(opener.chats) == 2
    protocol = judge.validate_freeze(out)
    journal, receipts = judge.audit_run(out, protocol)
    assert [r["status"] for r in receipts] == ["failed", "completed", "input_unavailable"]
    assert sum(e["event"] == "chat_started" for e in journal.records) == 2
    analysis_out = tmp_path / "analysis"
    judge.analyze(out, analysis_out)
    result = judge.read_json(analysis_out / "analysis.json")
    assert result["final"] is True and result["collection_state"] == "completed"
    assert result["summary"]["selected_planned"] == 3
    assert result["summary"]["attempted_chat_calls"] == 2
    assert result["pool_context"]["planned"] == 504
    metric = result["summary"]["methods"]["local_trace_judge"]["state"]
    assert metric["completed_outputs"] == metric["correct_claims"] == 1
    assert metric["selected_planned_correct_yield"] == {"numerator": 1, "denominator": 3, "value": 1 / 3}
    assert metric["selected_available_input_correct_yield"]["denominator"] == 2
    baseline = result["summary"]["methods"]["consequa_state_origin"]["state"]
    assert baseline["completed_outputs"] == 2
    assert sum(v["selected_planned"] for v in result["strata"]["model"].values()) == 3


def test_transport_failure_is_one_failed_call_then_stops_invocation(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    opener = Opener([URLError("deliberate failure"), envelope()])
    judge.run(out, inspector=identity, judge_factory=factory(opener))
    _, receipts = judge.audit_run(out, judge.validate_freeze(out))
    assert [r["status"] for r in receipts] == ["failed", "unstarted", "unstarted"]
    assert receipts[0]["attempted_calls"] == 1 and len(opener.chats) == 1
    judge.run(out, inspector=identity, judge_factory=factory(opener))
    assert len(opener.chats) == 2


def test_started_interrupted_slot_is_never_regenerated(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    protocol = judge.validate_freeze(out)
    entry = protocol["schedule"][0]
    start = out / "judgments" / entry["slot"]["slot_id"] / "started.json"
    judge.write_new(start, {"entry": entry, "utc": judge.now(),
        "protocol_sha256": judge.read_json(out / "protocol.sha256.json")["sha256"]})
    journal = judge.Journal(out / "request-journal.jsonl")
    journal.append("judge_started", slot_id=entry["slot"]["slot_id"],
                   started_sha256=judge.digest(start.read_bytes()))
    opener = Opener([envelope()])
    judge.run(out, inspector=identity, judge_factory=factory(opener))
    _, receipts = judge.audit_run(out, protocol)
    assert [r["status"] for r in receipts] == ["interrupted_partial", "completed", "input_unavailable"]
    assert len(opener.chats) == 1


@pytest.mark.parametrize("change", ["input", "code", "context"])
def test_changed_frozen_input_code_or_private_context_refuses_before_calls(tmp_path, monkeypatch, change):
    out = fixture_freeze(tmp_path, monkeypatch)
    if change == "input":
        path = next((out / "inputs").glob("*.json"))
        path.write_text("{}")
    elif change == "context":
        (out / "evaluation-context.json").write_text("{}")
    else:
        monkeypatch.setattr(judge, "code_hashes", lambda: {"changed": "source"})
    opener = Opener([envelope()])
    with pytest.raises(ValueError, match="changed"):
        judge.run(out, inspector=identity, judge_factory=factory(opener))
    assert opener.chats == []


def test_changed_model_digest_or_daemon_refuses_before_calls(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    changed = identity()
    changed["models"][judge.MODEL]["tag"]["digest"] = "changed"
    opener = Opener([envelope()])
    with pytest.raises(PolicyError, match="identity changed"):
        judge.run(out, inspector=lambda settings: changed, judge_factory=factory(opener))
    assert opener.chats == [] and not (out / "runner.lock").exists()


def test_never_run_analysis_refused_and_limited_run_explicitly_incomplete(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="terminal valid run_stopped"):
        judge.analyze(out, tmp_path / "never-run-analysis")
    judge.run(out, limit=1, inspector=identity, judge_factory=factory(Opener([envelope()])))
    dest = tmp_path / "incomplete-analysis"
    judge.analyze(out, dest)
    result = judge.read_json(dest / "analysis.json")
    assert result["final"] is False and result["collection_state"] == "incomplete"
    assert result["stopped_reason"] == "slot_limit"


def test_evidence_support_is_explicitly_limited_to_readback_methods():
    assert "response_only" not in judge.READBACK_METHODS
    assert "agent_self_report" not in judge.READBACK_METHODS
    assert {"local_trace_judge", "independent_public_reference", "consequa_state_origin"} <= judge.READBACK_METHODS


def test_torn_journal_and_changed_raw_bytes_are_hard_refusals(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    judge.run(out, limit=1, inspector=identity, judge_factory=factory(Opener([envelope()])))
    raw = next((out / "calls").glob("*.response.raw"))
    raw.write_bytes(b"changed")
    with pytest.raises(ValueError, match="provider bytes changed"):
        judge.audit_run(out, judge.validate_freeze(out))
    journal_path = out / "request-journal.jsonl"
    with journal_path.open("ab") as stream:
        stream.write(b"{torn")
    with pytest.raises(ValueError, match="Torn journal"):
        judge.Journal(journal_path)


def test_origin_claims_on_unassessable_gold_remain_visible(tmp_path, monkeypatch):
    out = fixture_freeze(tmp_path, monkeypatch)
    protocol = judge.validate_freeze(out)
    context = judge.read_json(out / "evaluation-context.json")
    context["episode_00000"]["gold"]["origin"] = "unknown"
    context["episode_00000"]["baselines"]["independent_public_reference"]["origin"] = "unknown"
    receipts = [{"slot_id": "episode_00000", "status": "completed", "attempted_calls": 1,
                 "prediction": {"state": None, "action_linked": None, "origin": "confirmed"}},
                {"slot_id": "episode_00001", "status": "failed", "attempted_calls": 1},
                {"slot_id": "episode_00002", "status": "unstarted", "attempted_calls": 0}]
    metrics = judge.summarize(protocol["schedule"], receipts, context)["methods"]["local_trace_judge"]
    origin = metrics["origin"]
    assert origin["all_definite_outputs"] == origin["claims_with_unassessable_gold"] == 1
    assert origin["claims"] == origin["all_evidence_supported_claims"] == 0
    assert origin["claim_error"]["value"] is None
    assert metrics["state"]["coverage"]["value"] == 0
    assert metrics["state"]["claim_error"]["value"] is None
