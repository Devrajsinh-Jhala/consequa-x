from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from unittest.mock import patch

import pytest

from consequa_x.adapters.ollama import MAX_RESPONSE_BYTES, OllamaPolicy, PROMPT_VERSION
from consequa_x.models import AssessmentStatus, ResponseStatus, ToolResponse
from consequa_x.policies import PolicyError, PolicyRequest


def request(stage="select", attempts_remaining=2):
    return PolicyRequest(stage, {"order_age_days": 43, "payment_id": "pay_42"},
                         {"customer_request": "Please refund.", "vip_memory": "VIP status",
                          "vip_policy": "VIP refunds allowed through 60 days."},
                         () if stage == "select" else (
                             ToolResponse("attempt:1", ResponseStatus.TIMEOUT, 6,
                                          "request:1", {"code": "timeout"}),
                         ), attempts_remaining)


def envelope(**changes):
    value = {
        "model": "tiny", "done": True, "done_reason": "stop",
        "message": {"role": "assistant", "content": json.dumps({
            "operation": "refund", "assessment": "unknown", "rationale": "Visible VIP policy."
        })},
        "prompt_eval_count": 120, "eval_count": 25, "total_duration": 2_000,
    }
    value.update(changes)
    return value


def local_inspection(**changes):
    value = {"model_info": {"general.architecture": "test"},
             "details": {"format": "gguf", "family": "test", "families": ["test"],
                         "parameter_size": "1B", "quantization_level": "Q4"},
             "capabilities": ["completion"]}
    value.update(changes)
    return value


@contextmanager
def server(response=None, *, status=200, headers=None, raw=None, inspection=None,
           inspection_raw=None):
    recorded = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            recorded.append({"method": self.command, "path": self.path, "body": body,
                             "headers": dict(self.headers)})
            self.send_response(status)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if self.path == "/api/show":
                content = inspection_raw if inspection_raw is not None else json.dumps(
                    local_inspection() if inspection is None else inspection
                ).encode("utf-8")
            else:
                default = envelope(model=json.loads(body)["model"]) if body else envelope()
                content = raw if raw is not None else json.dumps(
                    default if response is None else response
                ).encode("utf-8")
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    instance = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}", recorded
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def test_construction_is_offline_and_metadata_exports_a_copy():
    with patch("consequa_x.adapters.ollama.build_opener") as opener:
        policy = OllamaPolicy("local-model:latest")
        opener.return_value.open.assert_not_called()
    exported = policy.metadata
    exported["requested_model"] = "changed"
    assert policy.metadata["requested_model"] == "local-model:latest"


def test_url_guard_is_rechecked_if_adapter_configuration_is_changed():
    with patch("consequa_x.adapters.ollama.build_opener") as opener:
        policy = OllamaPolicy("tiny")
        policy.base_url = "http://example.com"
        with pytest.raises(PolicyError):
            policy.decide(request(), seed=0)
        opener.return_value.open.assert_not_called()


def test_truncated_http_response_has_a_policy_error():
    from http.client import IncompleteRead

    with patch("consequa_x.adapters.ollama.build_opener") as opener:
        opener.return_value.open.side_effect = IncompleteRead(b"partial", 8)
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny").decide(request(), seed=0)


def test_chat_sends_public_structured_request_and_records_declared_metadata():
    with server() as (url, recorded):
        policy = OllamaPolicy("local-model:latest", base_url=url, temperature=0.1,
                              timeout=2, num_predict=128)
        reply = policy.decide(request(), seed=15)
        assert reply.decision.operation == "refund"
        assert reply.decision.assessment is AssessmentStatus.UNKNOWN
        assert len(recorded) == 2
        assert recorded[0]["path"] == "/api/show"
        assert json.loads(recorded[0]["body"]) == {"model": "local-model:latest", "verbose": False}
        assert recorded[1]["path"] == "/api/chat"
        assert recorded[1]["method"] == "POST"
        payload = json.loads(recorded[1]["body"])
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["format"]["additionalProperties"] is False
        assert payload["format"]["properties"]["operation"]["enum"] == ["refund", "stop"]
        assert payload["options"] == {"seed": 15, "temperature": 0.1, "num_predict": 128}
        assert json.loads(payload["messages"][1]["content"]) == request().to_dict()
        assert "fault" not in payload["messages"][1]["content"]
        assert "ground_truth" not in payload["messages"][1]["content"]
        assert reply.metadata["requested_model"] == "local-model:latest"
        assert reply.metadata["returned_model"] == "local-model:latest"
        assert reply.metadata["prompt_version"] == PROMPT_VERSION
        assert reply.metadata["eval_count"] == 25
        assert len(reply.metadata["request_sha256"]) == 64
        assert reply.metadata["request_payload_sha256"] == hashlib.sha256(recorded[1]["body"]).hexdigest()
        assert reply.metadata["system_prompt_sha256"] == hashlib.sha256(
            payload["messages"][0]["content"].encode("utf-8")
        ).hexdigest()
        repeated = policy.decide(request(), seed=15)
        assert repeated.metadata["request_sha256"] == reply.metadata["request_sha256"]
        assert [entry["path"] for entry in recorded] == ["/api/show", "/api/chat", "/api/chat"]


def test_read_only_model_listing_preserves_identities_without_loading_models():
    with server({"models": [{"name": "tiny:latest", "model": "tiny:latest", "digest": "sha256:abc",
                              "size": 1234, "details": {"family": "test"}}]}) as (url, recorded):
        assert OllamaPolicy("tiny:latest", base_url=url).list_models() == (
            {"name": "tiny:latest", "model": "tiny:latest", "digest": "sha256:abc"},
        )
        assert recorded[0]["method"] == "GET"
        assert recorded[0]["path"] == "/api/tags"
        assert recorded[0]["body"] == b""


@pytest.mark.parametrize("url", [
    "https://localhost:11434", "http://example.com", "http://192.168.1.10:11434",
    "http://0.0.0.0:11434", "http://user:pass@localhost", "http://localhost/api",
    "http://localhost?secret=1", "http://localhost?", "http://localhost#",
    "http://localhost:0", "http://localhost:65536", "http://localhost:invalid",
    " http://localhost", "http://localhost\n", "http://localhost.evil.example", "file:///tmp/x",
    "http://[::1%25eth0]:11434",
])
def test_only_plain_loopback_http_origins_are_allowed(url):
    with pytest.raises(PolicyError):
        OllamaPolicy("tiny", base_url=url)


@pytest.mark.parametrize("url", ["http://localhost:11434/", "http://127.0.0.1", "http://[::1]:11434"])
def test_loopback_origins_are_accepted_without_calls(url):
    policy = OllamaPolicy("tiny", base_url=url)
    assert policy.base_url == url.rstrip("/")


@pytest.mark.parametrize("changes", [
    {"model": ""}, {"model": " model "}, {"temperature": True}, {"temperature": -0.1},
    {"temperature": float("nan")}, {"temperature": 2.1}, {"timeout": 0},
    {"timeout": float("inf")}, {"num_predict": True}, {"num_predict": -1},
])
def test_adapter_options_are_validated_before_network_access(changes):
    options = {"model": "tiny"}
    options.update(changes)
    with pytest.raises(PolicyError):
        OllamaPolicy(**options)


@pytest.mark.parametrize("response", [
    [], {"error": "provider error"}, envelope(done=False), envelope(done=1),
    envelope(model=None), envelope(message={"role": "user", "content": "{}"}),
    envelope(message={"role": "assistant", "content": {"operation": "stop"}}),
    envelope(message={"role": "assistant", "content": '```json\n{"operation":"stop"}\n```'}),
    envelope(message={"role": "assistant", "content": '{"operation":"refund","operation":"stop"}'}),
    envelope(message={"role": "assistant", "content": '{"operation":"stop"}', "tool_calls": [{}]}),
    envelope(eval_count=True), envelope(total_duration=-1), envelope(done_reason=1),
])
def test_invalid_envelopes_or_decisions_are_rejected(response):
    with server(response) as (url, _):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)


@pytest.mark.parametrize("raw", [b"not json", b"\xff", b'{"done":true,"done":false}',
                                  b'{"value":NaN}', b"x" * (MAX_RESPONSE_BYTES + 1)],
                         ids=["invalid-json", "invalid-utf8", "duplicate-key", "nan", "over-limit"])
def test_response_decoding_and_size_limits(raw):
    with server(raw=raw) as (url, _):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)


def test_adapter_rejects_operations_for_wrong_stage_and_exhausted_budget():
    with server(envelope(message={"role": "assistant", "content": '{"operation":"retry"}'})) as (url, _):
        policy = OllamaPolicy("tiny", base_url=url)
        with pytest.raises(PolicyError):
            policy.decide(request(), seed=0)
        with pytest.raises(PolicyError):
            policy.decide(request("after_response", 0), seed=0)


def test_environment_proxy_is_ignored_and_redirects_are_never_followed(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    with server() as (destination, destination_requests):
        with server(status=302, headers={"Location": destination + "/api/chat"}) as (url, captured):
            with pytest.raises(PolicyError, match="redirects"):
                OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)
            assert len(captured) == 1
            assert destination_requests == []
        assert OllamaPolicy("tiny", base_url=destination).decide(request(), seed=0)
        assert len(destination_requests) == 2


def test_http_errors_do_not_echo_response_bodies():
    with server(status=500, raw=b"secret provider diagnostic") as (url, _):
        with pytest.raises(PolicyError) as raised:
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)
        assert "HTTP 500" in str(raised.value)
        assert "secret" not in str(raised.value)


def test_unreachable_local_endpoint_has_actionable_sanitized_error():
    with server() as (url, _):
        pass
    with pytest.raises(PolicyError, match="check that it is running"):
        OllamaPolicy("tiny", base_url=url, timeout=1).list_models()


@pytest.mark.parametrize("seed", [-1, True, 2**31])
def test_invalid_seed_is_rejected_without_a_call(seed):
    with server() as (url, recorded):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=seed)
        assert recorded == []


@pytest.mark.parametrize("data", [
    {}, {"models": {}}, {"models": ["tiny"]}, {"models": [{"name": ""}]},
    {"models": [{"name": "tiny", "digest": 1}]},
])
def test_model_listing_rejects_malformed_entries(data):
    with server(data) as (url, _):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).list_models()


@pytest.mark.parametrize("returned", ["different", "tiny:small", " tiny", "tiny "])
def test_returned_model_identity_must_match_request(returned):
    with server(envelope(model=returned)) as (url, captured):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)
        assert [entry["path"] for entry in captured] == ["/api/show", "/api/chat"]


@pytest.mark.parametrize("requested,returned", [
    ("tiny", "tiny"), ("tiny", "tiny:latest"), ("tiny:latest", "tiny"),
    ("tiny:small", "tiny:small"), ("user/tiny", "user/tiny:latest"),
])
def test_exact_model_identity_and_optional_latest_tag_are_accepted(requested, returned):
    with server(envelope(model=returned)) as (url, _):
        assert OllamaPolicy(requested, base_url=url).decide(request(), seed=0).metadata[
            "returned_model"
        ] == returned


@pytest.mark.parametrize("routing", [
    {"remote_host": "https://ollama.com"}, {"remote_model": "tiny-cloud"},
    {"remote_host": " "}, {"remote_host": None}, {"remote_model": False},
])
def test_declared_remote_routing_is_rejected_before_generation(routing):
    with server(inspection=local_inspection(**routing)) as (url, captured):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)
        assert [entry["path"] for entry in captured] == ["/api/show"]


@pytest.mark.parametrize("routing", [{"remote_host": "https://ollama.com"},
                                     {"remote_model": "tiny-cloud"}, {"remote_host": True}])
def test_declared_remote_routing_in_chat_response_is_also_rejected(routing):
    with server(envelope(**routing)) as (url, captured):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)
        assert [entry["path"] for entry in captured] == ["/api/show", "/api/chat"]


def test_inspection_exports_safe_metadata_without_templates_or_local_paths():
    details = local_inspection(remote_host="", remote_model="", modelfile="FROM C:/private/model",
                               template="private template", system="private system")
    details["model_info"]["private_path"] = "C:/private/model"
    details["details"]["parent_model"] = "C:/private/parent"
    with server(inspection=details) as (url, captured):
        policy = OllamaPolicy("tiny", base_url=url)
        exported = policy.validate_local_model()
        assert exported["no_declared_remote_routing"] is True
        assert exported["routing_fields_present"] == ["remote_model", "remote_host"]
        assert len(exported["inspection_sha256"]) == 64
        assert "private" not in json.dumps(exported)
        exported["details"]["families"].append("changed")
        assert policy.validate_local_model()["details"]["families"] == ["test"]
        exported = policy.metadata
        exported["local_inspection"]["capabilities"].append("changed")
        assert policy.metadata["local_inspection"]["capabilities"] == ["completion"]
        assert [entry["path"] for entry in captured] == ["/api/show"]


def test_inspection_cache_refreshes_on_model_origin_changes_and_explicit_force():
    with server() as (url, first), server() as (second_url, second):
        policy = OllamaPolicy("tiny", base_url=url)
        policy.validate_local_model()
        policy.validate_local_model()
        assert len(first) == 1
        policy.model = "another"
        assert "local_inspection" not in policy.metadata
        policy.validate_local_model()
        assert json.loads(first[-1]["body"])["model"] == "another"
        policy.model = "tiny"
        policy.validate_local_model()
        assert len(first) == 3
        policy.base_url = second_url
        policy.validate_local_model()
        assert len(second) == 1
        policy.validate_local_model(force=True)
        assert len(second) == 2


def test_changed_model_inspection_failure_does_not_reuse_previous_cache():
    inspection = local_inspection()
    with server(inspection=inspection) as (url, captured):
        policy = OllamaPolicy("tiny", base_url=url)
        policy.validate_local_model()
        inspection["remote_host"] = "https://ollama.com"
        policy.model = "tiny-cloud"
        with pytest.raises(PolicyError):
            policy.decide(request(), seed=0)
        policy.model = "tiny"
        with pytest.raises(PolicyError):
            policy.decide(request(), seed=0)
        assert [entry["path"] for entry in captured] == ["/api/show"] * 3


@pytest.mark.parametrize("inspection", [
    {}, {"model_info": []}, {"model_info": {}, "details": []},
    {"model_info": {}, "capabilities": "completion"},
    {"model_info": {}, "capabilities": [True]},
    {"model_info": {}, "details": {"format": 1}},
    {"model_info": {}, "details": {"families": [1]}},
])
def test_model_inspection_rejects_malformed_shapes_before_generation(inspection):
    with server(inspection=inspection) as (url, captured):
        with pytest.raises(PolicyError):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)
        assert [entry["path"] for entry in captured] == ["/api/show"]


def test_model_inspection_uses_the_same_bounded_transport():
    with server(inspection_raw=b"x" * (MAX_RESPONSE_BYTES + 1)) as (url, captured):
        with pytest.raises(PolicyError, match="1 MiB"):
            OllamaPolicy("tiny", base_url=url).decide(request(), seed=0)
        assert [entry["path"] for entry in captured] == ["/api/show"]


def test_mutated_invalid_model_and_force_are_rejected_without_inspection():
    with server() as (url, captured):
        policy = OllamaPolicy("tiny", base_url=url)
        policy.model = ""
        with pytest.raises(PolicyError):
            policy.validate_local_model()
        policy.model = "tiny"
        with pytest.raises(PolicyError):
            policy.validate_local_model(force=1)
        assert captured == []
