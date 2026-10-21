"""No generation, paid APIs, official task cases, or model loading in these tests."""
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

from research.native_agent.transport import (
    ContextRefusal, LOCAL_MODEL, LocalOnlyGuard, ServerContextGate, TransportRefusal,
    MODEL_BLOB_SHA256, configure_local_environment, context_gate, local_model_kwargs,
    native_wire_equivalent, ollama_messages_for_render, ollama_tools_for_render, read_gguf_metadata,
)


def test_generation_body_semantic_binding_survives_json_ordering_and_detects_changed_values():
    payload = {"model": LOCAL_MODEL, "messages": [{"role": "user", "content": "fixture"}],
               "max_tokens": 128}
    guard = LocalOnlyGuard(allow_generation=True)
    first = json.dumps(payload).encode()
    second = json.dumps(dict(reversed(list(payload.items()))), separators=(",", ":")).encode()
    for body in (first, second):
        guard.check_http("POST", guard.api_base + "/chat/completions", body)
    assert guard.events[0]["body_sha256"] != guard.events[1]["body_sha256"]
    expected = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    assert {row["parsed_body_sha256"] for row in guard.events} == {expected}
    payload["messages"][0]["content"] = "changed fixture"
    guard.check_http("POST", guard.api_base + "/chat/completions", json.dumps(payload).encode())
    assert guard.events[-1]["parsed_body_sha256"] != expected


def test_provider_schema_normalization_is_offline_and_retains_constraints():
    schema = {"type": "function", "function": {"name": "fixture", "description": "Describe",
              "parameters": {"title": "parameters", "properties": {
                  "z": {"description": "Value", "title": "Decorative", "type": "string", "enum": ["a", "b"]},
                  "a": {"title": "Array", "type": "array", "items": {"title": "Nested", "$ref": "#/$defs/Thing"}}},
                  "required": ["z", "a"], "type": "object", "$defs": {
                      "Thing": {"type": "object", "title": "Retained", "properties": {"z": {}, "a": {}}}}}}}
    original = json.loads(json.dumps(schema))
    result = ollama_tools_for_render([schema])[0]
    assert schema == original
    parameters = result["function"]["parameters"]
    assert list(parameters) == ["type", "$defs", "required", "properties"]
    assert list(parameters["properties"]) == ["z", "a"]
    assert list(parameters["properties"]["z"]) == ["type", "description", "enum"]
    assert parameters["properties"]["z"]["enum"] == ["a", "b"]
    assert parameters["properties"]["a"]["items"] == {"$ref": "#/$defs/Thing", "title": "Nested"}
    assert parameters["$defs"]["Thing"]["title"] == "Retained"
    assert list(parameters["$defs"]["Thing"]["properties"]) == ["a", "z"]


@pytest.mark.parametrize("where,keyword,value", [
    ("property", "minimum", 1), ("property", "$ref", "#/$defs/Thing"),
    ("property", "additionalProperties", False), ("parameters", "additionalProperties", False),
    ("property", "enum", []), ("property", "anyOf", []),
])
def test_refuses_provider_schema_constraint_loss(where, keyword, value):
    parameters = {"type": "object", "properties": {"value": {"type": "string"}}}
    target = parameters if where == "parameters" else parameters["properties"]["value"]
    target[keyword] = value
    with pytest.raises(ContextRefusal):
        ollama_tools_for_render([{"type": "function", "function": {"name": "fixture", "parameters": parameters}}])


def test_provider_argument_rendering_preserves_ordered_outer_values_and_wire():
    arguments = {"z": [{"z": "caf\u00e9", "a": 1.0}], "a": True}
    messages = [{"role": "assistant", "tool_calls": [{"id": "fixed-id", "type": "function",
                 "function": {"name": "fixture", "arguments": json.dumps(arguments)}}]},
                {"role": "tool", "content": "Full result", "tool_call_id": "fixed-id"}]
    original = json.loads(json.dumps(messages))
    result = ollama_messages_for_render(messages)
    assert messages == original
    parsed = result[0]["tool_calls"][0]["function"]["arguments"]
    assert list(parsed) == ["z", "a"]
    assert list(parsed["z"][0]) == ["a", "z"]
    assert parsed == arguments
    assert result[1] == original[1]
    assert result[0]["tool_calls"][0]["id"] == "fixed-id"


@pytest.mark.parametrize("value", [2 ** 53, -(2 ** 53), float("inf"), float("nan")])
def test_refuses_provider_argument_numeric_value_loss(value):
    messages = [{"role": "assistant", "tool_calls": [{"function": {
        "name": "fixture", "arguments": json.dumps({"value": value})}}]}]
    with pytest.raises(ContextRefusal):
        ollama_messages_for_render(messages)


@pytest.mark.parametrize("address", [
    ("example.com", 443), ("localhost", 11434), ("127.0.0.1", 80),
    ("127.0.0.2", 11434), ("::1", 11434), "/tmp/socket",
])
def test_forbids_non_allowlisted_connections(address):
    guard = LocalOnlyGuard()
    with pytest.raises(TransportRefusal):
        guard.address(address)
    assert guard.events[-1]["allowed"] is False


def test_allows_only_exact_listener_address():
    guard = LocalOnlyGuard()
    guard.address(("127.0.0.1", 11434))
    assert guard.events[-1]["allowed"]
    assert not guard.events[-1]["internal_socketpair"]


def test_actual_connect_ex_is_refused_before_other_local_service():
    with socket.socket() as target:
        target.bind(("127.0.0.1", 0))
        target.listen()
        with LocalOnlyGuard() as guard, socket.socket() as client:
            with pytest.raises(TransportRefusal):
                client.connect_ex(target.getsockname())
        assert not guard.events[-1]["allowed"]


def test_asyncio_internal_socketpair_is_allowed_and_cleanup_works():
    async def toy():
        return 19

    with LocalOnlyGuard() as guard:
        assert asyncio.run(toy()) == 19
    assert not any(not event["allowed"] for event in guard.events)


def test_internal_pair_exception_does_not_leak_to_later_connections():
    with LocalOnlyGuard() as guard:
        left, right = socket.socketpair()
        left.close()
        right.close()
        with pytest.raises(TransportRefusal):
            guard.address(("127.0.0.1", 12999))


def test_dns_subprocess_dotenv_and_protected_writes_are_refused(tmp_path):
    secret = tmp_path / ".env"
    secret.write_text("invented_fixture_only")
    source = tmp_path / "protected"
    source.mkdir()
    with LocalOnlyGuard(protected_roots=[source]):
        with pytest.raises(TransportRefusal):
            socket.getaddrinfo("example.com", 443)
        with pytest.raises(TransportRefusal):
            subprocess.run([sys.executable, "-c", "pass"])
        with pytest.raises(TransportRefusal):
            secret.read_text()
        with pytest.raises(TransportRefusal):
            (source / "changed.py").write_text("x")
    assert not (source / "changed.py").exists()


@pytest.mark.parametrize("method,url,body", [
    ("POST", "https://api.openai.com/v1/chat/completions", {}),
    ("POST", "http://127.0.0.1:11434/api/pull", {"model": LOCAL_MODEL}),
    ("POST", "http://127.0.0.1:11434/api/create", {"model": LOCAL_MODEL}),
    ("POST", "http://127.0.0.1:11434/v1/chat/completions", {"model": "gpt-4.1"}),
    ("POST", "http://127.0.0.1:11434/v1/chat/completions", {"model": LOCAL_MODEL, "stream": True}),
    ("POST", "http://127.0.0.1:11434/v1/chat/completions", {"model": LOCAL_MODEL, "n": 2}),
    ("POST", "http://user@127.0.0.1:11434/v1/chat/completions", {"model": LOCAL_MODEL}),
    ("POST", "http://127.0.0.1/v1/chat/completions", {"model": LOCAL_MODEL}),
])
def test_http_endpoint_model_and_shape_refusals(method, url, body):
    with pytest.raises(TransportRefusal):
        LocalOnlyGuard(allow_generation=True).check_http(method, url, json.dumps(body).encode())


def test_generation_permission_is_explicit_and_metadata_does_not_grant_it():
    guard = LocalOnlyGuard()
    guard.check_http("POST", "http://127.0.0.1:11434/api/show", json.dumps({"model": LOCAL_MODEL}).encode())
    with pytest.raises(TransportRefusal):
        guard.check_http("POST", "http://127.0.0.1:11434/v1/chat/completions",
                         json.dumps({"model": LOCAL_MODEL}).encode())


def test_render_only_extension_cannot_dispatch_generation():
    guard = LocalOnlyGuard(allow_render_only=True)
    endpoint = "http://127.0.0.1:11434/v1/chat/completions"
    guard.check_http("POST", endpoint, json.dumps({"model": LOCAL_MODEL, "_debug_render_only": True}).encode())
    assert guard.events[-1]["generation_request"] is False
    for flag in [None, False, 1, "true"]:
        with pytest.raises(TransportRefusal):
            guard.check_http("POST", endpoint, json.dumps({"model": LOCAL_MODEL, "_debug_render_only": flag}).encode())


def test_generation_dispatch_count_excludes_previews_and_refused_contexts():
    guard = LocalOnlyGuard(allow_generation=True, allow_render_only=True)
    endpoint = "http://127.0.0.1:11434/v1/chat/completions"
    guard.check_http("POST", endpoint, json.dumps({"model": LOCAL_MODEL, "_debug_render_only": True}).encode())
    guard.check_http("POST", endpoint, json.dumps({"model": LOCAL_MODEL}).encode())
    assert sum(e.get("generation_request", False) for e in guard.events) == 1

    def refuse_context(payload):
        raise ContextRefusal("fixture overflow")

    guard.before_generation = refuse_context
    with pytest.raises(ContextRefusal):
        guard.check_http("POST", endpoint, json.dumps({"model": LOCAL_MODEL}).encode())
    assert sum(e.get("generation_request", False) for e in guard.events) == 1


def test_context_failure_preserves_terminal_receipt_before_propagation(monkeypatch):
    blob = "C:/fixture/sha256-" + MODEL_BLOB_SHA256
    executable = "C:/fixture/llama-server.exe"
    guard = LocalOnlyGuard(allow_render_only=True)
    guard.register_tokenizer_runner(port=34567, pid=1234, executable=executable,
                                    executable_sha256="a" * 64, model_blob=blob,
                                    model_blob_sha256=MODEL_BLOB_SHA256)
    process = SimpleNamespace(cmdline=lambda: [executable, "--model", blob, "--port", "34567"],
                              exe=lambda: executable)
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=lambda pid: process))
    logged = []
    gate = ServerContextGate(guard, {}, None, on_receipt=logged.append)
    payload = {"model": LOCAL_MODEL, "max_tokens": 513, "messages": []}
    with pytest.raises(ContextRefusal, match="output cap"):
        gate(payload)
    assert len(logged) == len(gate.receipts) == 1
    assert logged[0]["passed"] is False
    assert logged[0]["generation_dispatched_by_gate"] is False
    assert logged[0]["error"]["type"] == "ContextRefusal"
    payload["messages"].append({"role": "user", "content": "later mutation"})
    assert logged[0]["request"]["messages"] == []


def test_context_gate_refuses_same_name_with_changed_model_digest(monkeypatch):
    blob = "C:/fixture/sha256-" + MODEL_BLOB_SHA256
    executable = "C:/fixture/llama-server.exe"
    guard = LocalOnlyGuard(allow_render_only=True)
    guard.register_tokenizer_runner(port=34567, pid=1234, executable=executable,
                                    executable_sha256="a" * 64, model_blob=blob,
                                    model_blob_sha256=MODEL_BLOB_SHA256)
    process = SimpleNamespace(cmdline=lambda: [executable, "--model", blob, "--port", "34567"],
                              exe=lambda: executable)
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=lambda pid: process))
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"models": [
        {"name": LOCAL_MODEL, "context_length": 16384, "digest": "changed-digest"}]})

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            return response

        def post(self, *args, **kwargs):
            raise AssertionError("Changed identity must be refused before preview/tokenization")

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Client=Client))
    tokenizer = SimpleNamespace(encode=lambda *args, **kwargs: SimpleNamespace(ids=[1]))
    gate = ServerContextGate(guard, {"tokenizer.chat_template": "{{ messages[0].content }}"}, tokenizer)
    with pytest.raises(ContextRefusal, match="pinned"):
        gate({"model": LOCAL_MODEL, "max_tokens": 512,
              "messages": [{"role": "user", "content": "complete fixture"}]})
    assert gate.receipts[-1]["passed"] is False


def test_private_runner_exception_does_not_permit_completion_or_other_ports():
    guard = LocalOnlyGuard()
    guard.register_tokenizer_runner(port=34567, pid=1234,
                                    executable="C:/fixture/llama-server.exe", executable_sha256="a" * 64,
                                    model_blob="C:/fixture/sha256-" + MODEL_BLOB_SHA256,
                                    model_blob_sha256=MODEL_BLOB_SHA256)
    guard.address(("127.0.0.1", 34567))
    guard.check_http("POST", "http://127.0.0.1:34567/tokenize", b'{"content":"fixture"}')
    for path in ["/completion", "/chat/completions", "/health", "/tokenize?extra=1"]:
        with pytest.raises(TransportRefusal):
            guard.check_http("POST", "http://127.0.0.1:34567" + path, b"{}")
    with pytest.raises(TransportRefusal):
        guard.address(("127.0.0.1", 34568))


def test_wire_equivalence_preserves_everything_except_documented_null_content():
    native = [{"role": "assistant", "content": None,
               "tool_calls": [{"id": "fixture", "function": {"name": "read", "arguments": "{}"}}]},
              {"role": "tool", "content": "fixture", "tool_call_id": "fixture"}]
    observed = [{k: v for k, v in message.items() if v is not None} for message in native]
    assert native_wire_equivalent(observed, native)
    observed[1] = {**observed[1], "tool_call_id": "different"}
    assert not native_wire_equivalent(observed, native)
    assert not native_wire_equivalent(native[::-1], native)


def native_scope_fixture():
    request = {"model": "openai/" + LOCAL_MODEL, "messages": [
        {"role": "system", "content": "Complete native policy"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "fixed", "type": "function", "function": {"name": "read", "arguments": "{}"}}]},
        {"role": "tool", "content": "Complete actual response", "tool_call_id": "fixed"}],
        "tools": [{"type": "function", "function": {"name": "read", "parameters": {
            "type": "object", "properties": {}, "required": []}}}],
        "tool_choice": "auto", "max_tokens": 512, "temperature": 0, "seed": 1701,
        "num_retries": 0, "api_key": "not-retained", "timeout": 600}
    payload = {key: deepcopy(value) for key, value in request.items()
               if key not in {"num_retries", "api_key", "timeout"}}
    payload["model"] = LOCAL_MODEL
    return request, payload


def test_native_scope_refuses_unscoped_and_second_generation_before_context_preview():
    request, payload = native_scope_fixture()
    guard = LocalOnlyGuard(allow_generation=True, allow_render_only=True)
    guard.require_native_invocation = True
    previews = []
    guard.before_generation = lambda body: previews.append(deepcopy(body))
    endpoint = guard.api_base + "/chat/completions"
    with pytest.raises(TransportRefusal, match="outside a recorded"):
        guard.check_http("POST", endpoint, json.dumps(payload).encode())
    assert not previews
    with guard.native_invocation(request):
        guard.check_http("POST", endpoint, json.dumps({**payload, "_debug_render_only": True}).encode())
        guard.check_http("POST", endpoint, json.dumps(payload).encode())
        with pytest.raises(TransportRefusal, match="second generation"):
            guard.check_http("POST", endpoint, json.dumps(payload).encode())
    assert len(previews) == 1
    assert sum(row.get("generation_request", False) for row in guard.events) == 1
    assert getattr(guard._thread, "native_invocation", None) is None


@pytest.mark.parametrize("changed", ["model", "history", "role", "arguments", "call_id", "schema",
    "max_tokens", "temperature", "seed", "tool_choice", "extra"])
def test_native_scope_refuses_changed_input_before_preview(changed):
    request, payload = native_scope_fixture()
    guard = LocalOnlyGuard(allow_generation=True)
    guard.before_generation = lambda body: pytest.fail("Changed native input reached context preview")
    if changed == "model":
        payload["model"] = "different"
    elif changed == "history":
        payload["messages"][0]["content"] = "Truncated policy"
    elif changed == "role":
        payload["messages"][0]["role"] = "user"
    elif changed == "arguments":
        payload["messages"][1]["tool_calls"][0]["function"]["arguments"] = '{"changed": true}'
    elif changed == "call_id":
        payload["messages"][2]["tool_call_id"] = "changed"
    elif changed == "schema":
        payload["tools"][0]["function"]["parameters"]["required"] = ["changed"]
    elif changed == "extra":
        payload["stop"] = ["truncation"]
    else:
        payload[changed] = "changed"
    with guard.native_invocation(request), pytest.raises(TransportRefusal):
        guard.check_http("POST", guard.api_base + "/chat/completions", json.dumps(payload).encode())
    assert not any(row.get("generation_request") for row in guard.events)


def test_native_scope_snapshots_inputs_null_equivalence_cleanup_and_new_invocation():
    request, payload = native_scope_fixture()
    guard = LocalOnlyGuard(allow_generation=True)
    guard.require_native_invocation = True
    endpoint = guard.api_base + "/chat/completions"
    with guard.native_invocation(request):
        assert "api_key" not in guard._thread.native_invocation["request"]
        request["messages"][0]["content"] = "Provider mutated input"
        payload["messages"][1].pop("content")
        guard.check_http("POST", endpoint, json.dumps(payload).encode())
        with pytest.raises(TransportRefusal, match="Nested"):
            with guard.native_invocation(request):
                pytest.fail("Nested scope entered")
    request, payload = native_scope_fixture()
    with pytest.raises(ValueError, match="Synthetic failed request"), guard.native_invocation(request):
        guard.check_http("POST", endpoint, json.dumps(payload).encode())
        raise ValueError("Synthetic failed request")
    with guard.native_invocation(request):
        guard.check_http("POST", endpoint, json.dumps(payload).encode())
    assert sum(row.get("generation_request", False) for row in guard.events) == 3
    assert guard._thread.native_invocation is None


def test_failed_context_does_not_mark_generation_as_dispatched():
    request, payload = native_scope_fixture()
    guard = LocalOnlyGuard(allow_generation=True)

    def refuse(payload):
        raise ContextRefusal("Synthetic full-context refusal")

    guard.before_generation = refuse
    with guard.native_invocation(request):
        with pytest.raises(ContextRefusal):
            guard.check_http("POST", guard.api_base + "/chat/completions", json.dumps(payload).encode())
        assert guard._thread.native_invocation["dispatched"] is False
    assert not any(row.get("generation_request") for row in guard.events)


@pytest.mark.skipif(not os.environ.get("CONSEQAX_NATIVE_PYTHON"), reason="Requires the pinned native Python environment")
def test_installed_provider_hidden_retries_are_refused_offline(tmp_path):
    """Exercise the real installed SDKs with synthetic responses and no sockets."""
    script = r'''
import sys, json
from copy import deepcopy
sys.path.insert(0, sys.argv[1])
from research.native_agent.transport import LocalOnlyGuard, configure_local_environment, local_model_kwargs, LITELLM_MODEL, TransportRefusal
from research.native_agent.harness import record_completions
configure_local_environment(sys.argv[2])
class OfflineGuard(LocalOnlyGuard):
    def address(self, address, kind="network"):
        if getattr(self._thread, "socketpair", 0):
            return super().address(address, kind)
        self.refuse(kind, "All real connections forbidden during offline retry test")
class Journal:
    def __init__(self): self.rows = []
    def append(self, row): self.rows.append(deepcopy(row))
with OfflineGuard(allow_generation=True, api_base="http://127.0.0.1:11436/v1") as guard:
    import httpx
    mode, sends, previews = [None], [], []
    def fake_send(client, request, *args, **kwargs):
        assert str(request.url) == "http://127.0.0.1:11436/v1/chat/completions"
        sends.append(mode[0])
        if mode[0] == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout", request=request)
        if mode[0] == "connection":
            raise httpx.ConnectError("Synthetic connection failure", request=request)
        messages = {"ordinary_500": "Synthetic server failure",
            "alternating": "Conversation roles must alternate user/assistant",
            "last_role": "Last message must have role `user`",
            "tool_index": "unknown field: parameter index is not a valid field"}
        return httpx.Response(500, json={"error": {"message": messages[mode[0]], "type": "server_error"}}, request=request)
    httpx.Client.send = fake_send
    guard.attach_httpx()
    import litellm
    import openai
    from importlib.metadata import version
    assert version("litellm") == "1.82.6"
    assert version("openai") == "3.35.1"
    litellm.cache = None
    assert litellm.num_retries is None and litellm.model_fallbacks is None
    openai._base_client.SyncAPIClient._sleep_for_retry = lambda *a, **k: (_ for _ in ()).throw(AssertionError("SDK retry sleep reached"))
    guard.require_native_invocation = True
    guard.before_generation = lambda payload: previews.append(deepcopy(payload))
    journal = Journal()
    state = record_completions(litellm, journal, 6, invoke_scope=guard.native_invocation)
    results = []
    for case in ("ordinary_500", "timeout", "connection", "alternating", "last_role", "tool_index"):
        mode[0] = case
        before = len(sends)
        try:
            litellm.completion(model=LITELLM_MODEL, messages=[{"role": "user", "content": "Synthetic fixture"}],
                **local_model_kwargs(api_base="http://127.0.0.1:11436/v1", timeout=0.1))
        except BaseException as error:
            assert (isinstance(error, TransportRefusal)) == (case in {"alternating", "last_role", "tool_index"})
            assert not isinstance(error, AssertionError)
        else:
            raise AssertionError("Synthetic failed request returned a completion")
        assert len(sends) - before == 1
        assert guard._thread.native_invocation is None
        results.append({"case": case, "fake_http_sends": len(sends) - before})
    assert state["attempted"] == state["failed"] == state["provider_invoked"] == 6
    assert state["completed"] == state["provider_returned"] == 0
    assert len(previews) == 6
    assert len([row for row in journal.rows if row["kind"] == "request_error"]) == 6
    assert len([row for row in guard.events if row.get("generation_request")]) == 6
    assert len([row for row in guard.events if row.get("kind") == "native_invocation" and not row["allowed"]]) == 3
    print(json.dumps({"cases": results, "actual_network_connections": 0, "actual_model_calls": 0}))
'''
    result = subprocess.run([os.environ["CONSEQAX_NATIVE_PYTHON"], "-B", "-c", script,
        str(Path(__file__).resolve().parents[1]), str(tmp_path / "absent-data")],
        capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert len(report["cases"]) == 6 and all(row["fake_http_sends"] == 1 for row in report["cases"])
    assert report["actual_network_connections"] == report["actual_model_calls"] == 0


def test_sanitizes_environment_without_recording_values(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret-never-record")
    monkeypatch.setenv("HTTPS_PROXY", "fixture-proxy-never-record")
    record = configure_local_environment(tmp_path)
    assert {"OPENAI_API_KEY", "HTTPS_PROXY"} <= set(record["removed_variable_names"])
    assert "fixture-secret" not in json.dumps(record)
    assert "fixture-proxy" not in json.dumps(record)


def test_output_cap_and_no_retries():
    assert local_model_kwargs()["num_retries"] == 0
    for bad in [0, 513, True, 1.5]:
        with pytest.raises(ValueError):
            local_model_kwargs(max_tokens=bad)


def test_context_gate_counts_tokens_and_refuses_without_truncating():
    class Encoded:
        ids = list(range(16000))

    class Tokenizer:
        def encode(self, value, **kwargs):
            assert value == "fixture prompt"
            assert kwargs == {"add_special_tokens": False}
            return Encoded()

    with pytest.raises(ContextRefusal):
        context_gate("fixture prompt", Tokenizer())
    receipt = context_gate("fixture prompt", Tokenizer(), output_tokens=128)
    assert receipt["required_tokens"] == 16192
    assert receipt["fits"] and not receipt["truncation_requested"]


def test_reads_metadata_only_and_rejects_truncation(tmp_path):
    def string(value):
        value = value.encode()
        return struct.pack("<Q", len(value)) + value

    prefix = (b"GGUF" + struct.pack("<IQQ", 3, 999, 1)
              + string("tokenizer.ggml.pre") + struct.pack("<I", 8) + string("qwen2"))
    fixture = tmp_path / "fixture.gguf"
    fixture.write_bytes(prefix + b"unread tensor bytes")
    result = read_gguf_metadata(fixture)
    assert result["tokenizer.ggml.pre"] == "qwen2"
    assert result["_metadata_end_bytes"] == len(prefix)
    fixture.write_bytes(prefix[:-1])
    with pytest.raises(ValueError, match="Truncated"):
        read_gguf_metadata(fixture)


def test_child_imports_httpx_under_guard_without_socketpair_failure(tmp_path):
    # Keep this import probe in a child so its import environment cannot alter
    # another test. It returns no invented provider response and makes no call.
    module = Path(__file__).resolve().parents[1] / "research/native_agent/transport.py"
    script = tmp_path / "child.py"
    script.write_text(
        "import importlib.util,json\n"
        f"spec=importlib.util.spec_from_file_location('transport',{str(module)!r})\n"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
        f"m.configure_local_environment({str(tmp_path)!r})\n"
        "with m.LocalOnlyGuard() as g:\n"
        "    g.attach_httpx()\n"
        "print(json.dumps({'refusals':[e for e in g.events if not e['allowed']]}))\n"
    )
    result = subprocess.run([sys.executable, "-B", str(script)], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["refusals"] == []
