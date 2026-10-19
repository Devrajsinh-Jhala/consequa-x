"""Bounded replay through a local HTTP fixture; no language model is run."""

from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from jsonschema import Draft202012Validator
import pytest

from consequa_x import cli
from consequa_x.models import EventType, ResponseStatus, ToolResponse, Trace
from consequa_x.policies import PolicyRequest, ScriptedRefundPolicy
from consequa_x.schema import get_trace_schema


@contextmanager
def replay_server(*, fail_chats=False):
    """Return scripted public decisions with auditable raw HTTP request bytes."""
    requests = []
    scripted = ScriptedRefundPolicy()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"method": "GET", "path": self.path, "body": None})
            self.respond({"models": [{"name": "fixture:latest", "model": "fixture:latest",
                                       "digest": "fixture-digest"}]})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(body)
            requests.append({"method": "POST", "path": self.path,
                             "body": body, "payload": payload})
            if self.path == "/api/show":
                self.respond({"model_info": {}, "details": {}, "capabilities": ["completion"]})
                return
            if fail_chats:
                self.respond({"error": "PRIVATE_PROVIDER_DIAGNOSTIC"}, status=500)
                return
            public = json.loads(payload["messages"][1]["content"])
            responses = tuple(ToolResponse(
                attempt_id=response["attempt_id"], status=ResponseStatus(response["status"]), time_ms=response["time_ms"],
                provider_request_id=response["provider_request_id"], result=response["result"], action_id=response["action_id"],
            ) for response in public["responses"])
            request = PolicyRequest(public["stage"], public["task"], public["context"],
                                    responses, public["attempts_remaining"])
            decision = scripted.decide(request, seed=payload["options"]["seed"]).decision
            self.respond({"model": "fixture:latest", "done": True,
                          "message": {"role": "assistant", "content": json.dumps(decision.to_dict())}})

        def respond(self, value, status=200):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(value).encode("utf-8"))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def replay_args(output, url, *extra):
    return ["model-experiment", "--provider", "ollama", "--model", "fixture", "--base-url", url,
            "--samples", "2", "--seed", "7", "--timeout", "2", "--output", str(output), *extra]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def chats(requests):
    return [request for request in requests if request["path"] == "/api/chat"]


def nested_keys(value):
    if isinstance(value, dict):
        yield from value
        for item in value.values():
            yield from nested_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from nested_keys(item)


@pytest.mark.parametrize("extra", [
    ["--candidates", "refund_decision"],
    ["--candidates", "vip_policy,vip_policy"],
    ["--candidates", ""],
    ["--samples", "1"],
    ["--max-calls", "0"],
    ["--max-attempts", "6"],
    ["--seed", "357913941"],
])
def test_invalid_replay_plan_is_rejected_before_network_and_artifacts(tmp_path, capsys, extra):
    output = tmp_path / "invalid"
    with replay_server() as (url, requests):
        assert cli.main(replay_args(output, url, *extra)) == 2
    assert requests == []
    assert not output.exists()
    assert capsys.readouterr().err


def test_unknown_case_parse_error_is_rejected_before_network(tmp_path, capsys):
    output = tmp_path / "unknown-case"
    with replay_server() as (url, requests):
        with pytest.raises(SystemExit) as error:
            cli.main(replay_args(output, url, "--case", "unknown_case"))
    assert error.value.code == 2
    assert requests == [] and not output.exists()
    assert "invalid choice" in capsys.readouterr().err


def test_existing_replay_output_is_preserved_before_network(tmp_path, capsys):
    output = tmp_path / "previous"
    output.mkdir()
    previous = output / "results.json"
    previous.write_text("prior replay", encoding="utf-8")
    with replay_server() as (url, requests):
        assert cli.main(replay_args(output, url)) == 2
    assert requests == []
    assert previous.read_text(encoding="utf-8") == "prior replay"
    capsys.readouterr()


def test_http_replay_reuses_factual_branches_for_candidates_and_both_targets(tmp_path, capsys):
    output = tmp_path / "complete"
    with replay_server() as (url, requests):
        assert cli.main(replay_args(output, url)) == 0
    report = read_json(output / "results.json")
    assert report["evaluation_kind"] == "local_model_replay"
    assert report["seeds"] == [7, 8]
    assert report["installed_model"]["digest"] == "fixture-digest"
    # Per seed: factual 3 + two VIP removals 1 each + retry removal 2 + distractor 3.
    assert len(chats(requests)) == report["summary"]["policy_calls"] == 20
    assert len(report["branches"]) == 10
    assert sum(branch["candidate_id"] is None for branch in report["branches"]) == 2
    assert len(report["estimates"]) == 8
    estimates = {(result["event_id"], result["target"]): result for result in report["estimates"]}
    assert all(result["status"] == "estimated" and result["known_pairs"] == 2
               for result in estimates.values())
    assert estimates["retry_instruction", "action"]["estimate"]["effect"] == 0
    assert estimates["retry_instruction", "consequence"]["estimate"]["effect"] == -1
    overlay = read_json(output / report["attribution_explanation"])
    causal = [edge for edge in overlay["graph"]["edges"] if edge["kind"] == "ESTIMATED_INFLUENCE"]
    assert len(causal) == 8
    assert {(edge["source"], edge["data"]["target"]) for edge in causal} == set(estimates)
    assert len({(edge["source"], edge["target"]) for edge in causal}) == 8
    assert report["attribution_trace"] == report["branches"][0]["trace"]
    assert [request["path"] for request in requests[:2]] == ["/api/tags", "/api/show"]
    assert sum(request["path"] == "/api/show" for request in requests) == 1
    assert all(request["path"] == "/api/chat" for request in requests[2:])
    capsys.readouterr()


def test_completed_replay_exports_fixed_contracts_portable_traces_and_request_hashes(tmp_path, capsys):
    output = tmp_path / "evidence"
    with replay_server() as (url, requests):
        assert cli.main(replay_args(output, url, "--candidates", "vip_policy,retry_instruction")) == 0
    report = read_json(output / "results.json")
    validator = Draft202012Validator(get_trace_schema())
    assert read_json(output / "trace-schema.json") == get_trace_schema()
    contracts = {}
    captured = iter(chats(requests))
    all_paths = set()
    for branch in report["branches"]:
        assert branch["status"] == "completed"
        assert branch["trace"] not in all_paths
        all_paths.add(branch["trace"])
        raw_trace = read_json(output / branch["trace"])
        validator.validate(raw_trace)
        trace = Trace.from_dict(raw_trace)
        assert Trace.from_json(trace.to_json()) == trace
        if branch["seed"] in contracts:
            assert trace.single_action.contract == contracts[branch["seed"]]
        else:
            contracts[branch["seed"]] = trace.single_action.contract
        truth = read_json(output / branch["evaluator_truth"])
        assert truth["seed"] == branch["seed"] and "records" in truth
        decisions = [event for event in trace.events if event.type is EventType.AGENT_DECISION]
        for phase, event in enumerate(decisions):
            sent = next(captured)
            payload = sent["payload"]
            public_text = payload["messages"][1]["content"]
            assert json.loads(public_text) == event.data["policy_request"]
            metadata = event.data["policy_reply"]["metadata"]
            assert metadata["request_payload_sha256"] == sha256(sent["body"]).hexdigest()
            assert metadata["request_sha256"] == sha256(public_text.encode("utf-8")).hexdigest()
            assert metadata["system_prompt_sha256"] == sha256(
                payload["messages"][0]["content"].encode("utf-8")
            ).hexdigest()
            assert metadata["seed"] == event.data["model_seed"] == payload["options"]["seed"]
            assert event.data["model_seed"] == branch["seed"] * 6 + phase
            assert "unsafe_retry" not in public_text and "timeout_after_commit" not in public_text
            public = json.loads(public_text)
            assert not {"ground_truth", "fault", "verifications", "observations", "fault_applied"} & set(nested_keys(public))
            assert public["task"]["amount_minor"] == trace.single_action.contract.expected["amount_minor"]
            if branch["candidate_id"] is not None:
                assert public["context"][branch["candidate_id"]] == ""
    assert list(captured) == []
    for artifact in read_json(output / "manifest.json")["artifacts"]:
        assert sha256((output / artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
    manifest_paths = {artifact["path"] for artifact in read_json(output / "manifest.json")["artifacts"]}
    assert {"results.json", "trace-schema.json", "README.md", report["attribution_explanation"]} <= manifest_paths
    capsys.readouterr()


def test_unknown_consequences_refuse_only_that_target_without_extra_calls(tmp_path, capsys):
    output = tmp_path / "unknown"
    with replay_server() as (url, requests):
        assert cli.main(replay_args(output, url, "--case", "delayed_visibility",
                                    "--candidates", "distractor")) == 0
    report = read_json(output / "results.json")
    assert len(chats(requests)) == report["summary"]["policy_calls"] == 8
    action, consequence = report["estimates"]
    assert action["target"] == "action" and action["status"] == "estimated"
    assert action["known_pairs"] == 2 and action["estimate"]["effect"] == 0
    assert consequence["target"] == "consequence" and consequence["status"] == "refused"
    assert consequence["estimate"] is None
    assert consequence["unknown_pairs"] == 2 and consequence["known_pairs"] == 0
    assert consequence["failed_pairs"] == consequence["unstarted_pairs"] == 0
    overlay = read_json(output / report["attribution_explanation"])
    causal = [edge for edge in overlay["graph"]["edges"] if edge["kind"] == "ESTIMATED_INFLUENCE"]
    assert len(causal) == 1 and causal[0]["data"]["target"] == "action"
    capsys.readouterr()


def test_provider_failures_refuse_both_targets_and_preserve_full_pair_denominator(tmp_path, capsys):
    output = tmp_path / "failed"
    with replay_server(fail_chats=True) as (url, requests):
        assert cli.main(replay_args(output, url, "--candidates", "retry_instruction")) == 2
    report = read_json(output / "results.json")
    assert len(chats(requests)) == report["summary"]["policy_calls"] == 4
    assert len(report["branches"]) == 4
    assert all(branch["status"] == "failed" and branch["policy_calls"] == 1
               and "trace" not in branch for branch in report["branches"])
    assert all(result["status"] == "refused" and result["estimate"] is None
               and result["failed_pairs"] == 2 and result["known_pairs"] == 0
               and result["unknown_pairs"] == 0 and result["unstarted_pairs"] == 0
               for result in report["estimates"])
    assert not (output / "traces").exists()
    assert report["attribution_trace"] is None and report["attribution_explanation"] is None
    assert "PRIVATE_PROVIDER_DIAGNOSTIC" not in (output / "results.json").read_text(encoding="utf-8")
    capsys.readouterr()


def test_global_budget_keeps_partial_receipts_and_refuses_incomplete_planned_pairs(tmp_path, capsys):
    output = tmp_path / "budget"
    with replay_server() as (url, requests):
        assert cli.main(replay_args(output, url, "--candidates", "retry_instruction",
                                    "--max-calls", "4")) == 2
    report = read_json(output / "results.json")
    assert len(chats(requests)) == report["summary"]["policy_calls"] == 4
    assert report["summary"]["budget_exhausted"]
    assert len(report["branches"]) == 2
    completed, failed = report["branches"]
    assert completed["status"] == "completed" and completed["policy_calls"] == 3
    assert failed["status"] == "failed" and failed["policy_calls"] == 1
    assert failed["error_type"] == "CallBudgetExceeded" and "trace" not in failed
    for result in report["estimates"]:
        assert result["status"] == "refused" and result["estimate"] is None
        assert result["failed_pairs"] == 1 and result["unstarted_pairs"] == 1
        assert result["known_pairs"] == result["unknown_pairs"] == 0
        assert sum(result[key] for key in ("known_pairs", "unknown_pairs", "failed_pairs", "unstarted_pairs")) == 2
    assert report["attribution_trace"] is None and report["attribution_explanation"] is None
    capsys.readouterr()
