"""End-to-end CLI checks through a real local HTTP boundary, without a model."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from consequa_x import cli
from consequa_x.models import ResponseStatus, ToolResponse, Trace, VerificationStatus
from consequa_x.policies import PolicyRequest, ScriptedRefundPolicy


@contextmanager
def local_policy_server(*, installed=True, chat_status=200, stop=False,
                        show_metadata=None, returned_model="test:latest", chat_metadata=None):
    requests = []
    scripted = ScriptedRefundPolicy()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(("GET", self.path, None))
            self.respond({"models": ([{"name": "test:latest", "model": "test:latest",
                                         "digest": "fixture-digest"}] if installed else [])})

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            payload = json.loads(raw)
            requests.append(("POST", self.path, payload))
            if self.path == "/api/show":
                self.respond({"model_info": {}, "details": {}, "capabilities": ["completion"],
                              **({} if show_metadata is None else show_metadata)})
                return
            if chat_status != 200:
                self.respond({"error": "SECRET_SERVER_DIAGNOSTIC"}, status=chat_status)
                return
            public = json.loads(payload["messages"][1]["content"])
            responses = tuple(ToolResponse(
                attempt_id=response["attempt_id"], status=ResponseStatus(response["status"]), time_ms=response["time_ms"],
                provider_request_id=response["provider_request_id"], result=response["result"], action_id=response["action_id"],
            ) for response in public["responses"])
            request = PolicyRequest(public["stage"], public["task"], public["context"],
                                    responses, public["attempts_remaining"])
            decision = (dict(operation="stop", assessment="unknown", rationale="Fixture decline")
                        if stop else scripted.decide(request, seed=payload["options"]["seed"]).decision.to_dict())
            self.respond({"model": returned_model, "done": True,
                          "message": {"role": "assistant", "content": json.dumps(decision)},
                          **({} if chat_metadata is None else chat_metadata)})

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


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def args(output, url, *extra):
    return ["model-eval", "--provider", "ollama", "--model", "test", "--base-url", url,
            "--cases", "clean,timeout_after_commit", "--samples", "1", "--timeout", "2",
            "--output", str(output), *extra]


def test_cli_local_http_path_exports_model_identity_and_evidence(tmp_path, capsys):
    output = tmp_path / "run"
    with local_policy_server() as (url, requests):
        assert cli.main(args(output, url)) == 0
    report = read_json(output / "results.json")
    assert report["evaluation_kind"] == "local_model"
    assert report["installed_model"] == {
        "name": "test:latest", "model": "test:latest", "digest": "fixture-digest",
    }
    assert report["summary"]["completed_samples"] == 2
    assert report["summary"]["policy_calls"] == 4
    assert report["summary"]["verification"] == {"satisfied": 2, "violated": 0, "unknown": 0}
    assert requests[0][:2] == ("GET", "/api/tags")
    assert requests[1][:2] == ("POST", "/api/show")
    assert requests[1][2] == {"model": "test", "verbose": False}
    assert sum(request[1] == "/api/show" for request in requests) == 1
    assert all(request[1] == "/api/chat" for request in requests[2:])
    for receipt in report["samples"]:
        trace = Trace.from_dict(read_json(output / receipt["trace"]))
        assert trace.verifications[-1].status is VerificationStatus.SATISFIED
        assert trace.single_action.arguments == trace.single_action.contract.expected
        assert read_json(output / receipt["evaluator_truth"])["scenario"] == receipt["scenario"]
    initial = [json.loads(payload["messages"][1]["content"])
               for _, path, payload in requests if path == "/api/chat"]
    assert initial[0] == initial[2]  # Only phase seeds differ across clean/timeout cases.
    assert all("SECRET" not in json.dumps(request) for request in initial)
    capsys.readouterr()


def test_missing_installed_model_stops_before_any_decision_or_artifact(tmp_path, capsys):
    output = tmp_path / "missing"
    with local_policy_server(installed=False) as (url, requests):
        assert cli.main(args(output, url)) == 2
    assert not output.exists()
    assert requests == [("GET", "/api/tags", None)]
    assert "not installed" in capsys.readouterr().err


def test_existing_output_refusal_happens_before_network_preflight(tmp_path, capsys):
    output = tmp_path / "existing"
    output.mkdir()
    previous = output / "results.json"
    previous.write_text("old result", encoding="utf-8")
    with local_policy_server() as (url, requests):
        assert cli.main(args(output, url)) == 2
    assert requests == []
    assert previous.read_text(encoding="utf-8") == "old result"
    capsys.readouterr()


def test_local_model_decline_preserves_fixed_contract_and_counts_violation(tmp_path, capsys):
    output = tmp_path / "decline"
    with local_policy_server(stop=True) as (url, requests):
        assert cli.main(args(output, url)) == 0
    report = read_json(output / "results.json")
    assert report["summary"]["completed_samples"] == 2
    assert report["summary"]["verification"] == {"satisfied": 0, "violated": 2, "unknown": 0}
    assert report["summary"]["policy_calls"] == 2
    assert len([request for request in requests if request[1] == "/api/chat"]) == 2
    for receipt in report["samples"]:
        trace = Trace.from_dict(read_json(output / receipt["trace"]))
        assert not receipt["action_selected"]
        assert trace.responses == ()
        assert trace.single_action.contract.expected == {
            "payment_id": "pay_42", "amount_minor": 500_000, "currency": "INR",
        }
    capsys.readouterr()


def test_provider_failures_keep_receipts_and_a_nonzero_cli_status(tmp_path, capsys):
    output = tmp_path / "failed"
    with local_policy_server(chat_status=500) as (url, requests):
        status = cli.main(args(output, url))
    report = read_json(output / "results.json")
    assert report["summary"]["completed_samples"] == 0
    assert report["summary"]["failed_samples"] == 2
    assert report["summary"]["policy_calls"] == 2
    assert report["summary"]["known_outcome_samples"] == 0
    assert len([request for request in requests if request[1] == "/api/chat"]) == 2
    assert not (output / "traces").exists()
    assert "SECRET_SERVER_DIAGNOSTIC" not in (output / "results.json").read_text(encoding="utf-8")
    assert all("HTTP 500" in sample["error"] for sample in report["samples"])
    assert status != 0
    capsys.readouterr()


def test_call_budget_prevents_a_fourth_http_generation_and_keeps_partial_counts(tmp_path, capsys):
    output = tmp_path / "budget"
    with local_policy_server() as (url, requests):
        assert cli.main(args(output, url, "--max-calls", "3")) == 2
    report = read_json(output / "results.json")
    assert len([item for item in requests if item[1] == "/api/chat"]) == 3
    assert report["summary"]["budget_exhausted"]
    assert report["summary"]["completed_samples"] == 1
    assert report["summary"]["failed_samples"] == 1
    assert report["summary"]["not_started_samples"] == 0
    assert report["summary"]["verification"] == {"satisfied": 1, "violated": 0, "unknown": 0}
    failure = report["samples"][-1]
    assert failure["error_type"] == "CallBudgetExceeded"
    assert "trace" not in failure and "verified_outcome" not in failure
    capsys.readouterr()


def test_declared_remote_model_is_rejected_before_generation_or_outputs(tmp_path, capsys):
    output = tmp_path / "remote"
    with local_policy_server(show_metadata={
        "remote_host": "https://ollama.com", "remote_model": "some-cloud-model",
    }) as (url, requests):
        assert cli.main(args(output, url)) == 2
    assert [request[:2] for request in requests] == [
        ("GET", "/api/tags"), ("POST", "/api/show"),
    ]
    assert not output.exists()
    assert "remote" in capsys.readouterr().err.lower()


def test_unrelated_returned_model_is_a_failure_without_false_completed_evidence(tmp_path, capsys):
    output = tmp_path / "mismatch"
    with local_policy_server(returned_model="different-model:latest") as (url, requests):
        assert cli.main(args(output, url)) == 2
    report = read_json(output / "results.json")
    assert report["summary"]["completed_samples"] == 0
    assert report["summary"]["failed_samples"] == 2
    assert report["summary"]["known_outcome_samples"] == 0
    assert len([request for request in requests if request[1] == "/api/chat"]) == 2
    assert not (output / "traces").exists()
    assert all(sample["error_type"] == "PolicyError" for sample in report["samples"])
    capsys.readouterr()


def test_latest_tag_normalization_allows_the_same_returned_model(tmp_path, capsys):
    output = tmp_path / "normalized"
    with local_policy_server(returned_model="test") as (url, _):
        assert cli.main(args(output, url)) == 0
    report = read_json(output / "results.json")
    assert report["summary"]["completed_samples"] == 2
    capsys.readouterr()


def test_remote_routing_reported_during_chat_invalidates_the_episode(tmp_path, capsys):
    output = tmp_path / "remote-chat"
    with local_policy_server(chat_metadata={"remote_host": "https://ollama.com"}) as (url, requests):
        assert cli.main(args(output, url)) == 2
    report = read_json(output / "results.json")
    assert report["summary"]["completed_samples"] == 0
    assert report["summary"]["failed_samples"] == 2
    assert report["summary"]["known_outcome_samples"] == 0
    assert not (output / "traces").exists()
    assert sum(request[1] == "/api/show" for request in requests) == 1
    assert all("remote" in sample["error"].lower() for sample in report["samples"])
    capsys.readouterr()
