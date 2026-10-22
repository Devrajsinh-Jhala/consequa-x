"""Invented wire fixtures only; no generation, tasks, service or model loading."""
from dataclasses import asdict
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from research.limbo_agent import transport as t


WIRE_IMPLEMENTATION = t.AuditedLIMBOClient._wire


@pytest.fixture
def native(monkeypatch):
    path = Path("D:/ConsequaX-Research/limbo-pinned-2db09fba/limbo/llm.py")
    if not path.is_file():
        pytest.skip("Pinned standalone public client source is required")
    spec = importlib.util.spec_from_file_location("_limbo_test_client_only", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    assert t.sha256(path.read_bytes().replace(b"\r\n", b"\n")) == t.UPSTREAM_LLM_SHA256
    monkeypatch.setattr(t, "native_llm_module", lambda: module)
    return module


@pytest.fixture
def binding():
    return t.RuntimeBinding("http://127.0.0.1:11436/v1", "fixture-local:ctx8k", "a" * 64,
        "D:/fake/sha256-" + "b" * 64, "b" * 64, 100, "D:/fake/ollama.exe", "c" * 64,
        1700000000.0, 101, "D:/fake/llama-server.exe", "d" * 64, 1700000001.0, 34567, 8192, 1)


def response(text="fixture response", calls=None, usage=True):
    value = {"choices": [{"message": {"role": "assistant", "content": text,
                                       "tool_calls": calls or []}, "finish_reason": "stop"}]}
    if usage:
        value["usage"] = {"prompt_tokens": 100, "completion_tokens": 5,
                          "prompt_tokens_details": {"cached_tokens": 50}}
    return value


@pytest.fixture
def rig(tmp_path, native, binding, monkeypatch):
    monkeypatch.setattr(t.AuditedLIMBOClient, "_verify_identity", lambda self, **kw: None)
    monkeypatch.setattr(t, "read_gguf_metadata", lambda path: {})
    monkeypatch.setattr(t, "render_gguf_template", lambda metadata, messages, tools:
                        json.dumps({"messages": messages, "tools": tools}))
    tokenizer = SimpleNamespace(encode=lambda prompt, **kw: SimpleNamespace(ids=list(range(len(prompt)))))
    monkeypatch.setattr(t, "tokenizer_from_gguf", lambda metadata: tokenizer)
    wires, generations = [], []
    settings = {"preview_match": True, "token_match": True, "resident": True,
                "payloads": [response()], "status": 200, "error": None}
    def wire(self, method, url, data, timeout):
        self.guard.check_http(method, url, data)
        payload = json.loads(data) if data else {}
        wires.append({"method": method, "url": url, "payload": payload, "data": data, "timeout": timeout})
        if url.endswith("/api/ps"):
            value = {"models": [{"name": binding.model, "digest": binding.model_digest,
                                  "context_length": binding.context_tokens}] if settings["resident"] else []}
        elif url.endswith("/tokenize"):
            value = {"tokens": list(range(len(payload["content"]))) if settings["token_match"] else [999]}
        elif payload.get("_debug_render_only"):
            prompt = t.render_gguf_template({}, payload["messages"], payload["tools"])
            value = {"_debug_info": {"rendered_template": prompt if settings["preview_match"] else "wrong"}}
        else:
            generations.append(payload)
            if settings["error"]:
                raise settings["error"]
            value = settings["payloads"].pop(0)
            return settings["status"], {"Content-Type": "application/json"}, json.dumps(value).encode()
        return 200, {}, json.dumps(value).encode()
    monkeypatch.setattr(t.AuditedLIMBOClient, "_wire", wire)
    def make(**kwargs):
        options = {"max_requests": 3, "max_output_tokens": 128, "request_timeout_s": 1200, "seed": 1701, **kwargs}
        return t.AuditedLIMBOClient(binding, tmp_path / "client", **options)
    return SimpleNamespace(make=make, wires=wires, generations=generations, settings=settings, tmp=tmp_path)


SYSTEM = "Use all supplied fields."
TOOLS = [{"name": "fixture", "description": "Invented fixture.", "parameters": {
    "type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}}]
CONVERSATION = [{"role": "user", "content": "A complete invented question."}]


def terminal(rig, number=1):
    return json.loads((rig.tmp / "client" / f"{number:04d}-terminal.json").read_text())


def test_exact_native_renderer_and_full_history_tool_roundtrip(rig):
    calls = [{"id": "unchanged-id", "type": "function", "function": {
        "name": "fixture", "arguments": '{"value":"caf\u00e9"}'}}]
    rig.settings["payloads"] = [response("", calls), response("Read the complete fixture result.")]
    conversation = json.loads(json.dumps(CONVERSATION))
    with rig.make() as client:
        first = client.complete(SYSTEM, conversation, TOOLS)
        conversation.extend([
            {"role": "assistant", "content": first.text, "tool_calls": [
                {"id": first.tool_calls[0].id, "name": first.tool_calls[0].name,
                 "arguments": first.tool_calls[0].arguments}]},
            {"role": "tool", "tool_call_id": "unchanged-id", "name": "fixture",
             "content": '{"value":"complete result with all fields"}'},
        ])
        second = client.complete(SYSTEM, conversation, TOOLS)
    assert second.text == "Read the complete fixture result."
    assert len(rig.generations) == 2
    sent = rig.generations[1]
    assert sent["messages"][0] == {"role": "system", "content": SYSTEM}
    assert sent["messages"][1] == CONVERSATION[0]
    assert sent["messages"][2]["tool_calls"] == calls
    assert sent["messages"][3] == {k: v for k, v in conversation[2].items() if k != "name"}
    assert sent["tools"] == [{"type": "function", "function": TOOLS[0]}]
    assert sent["seed"] == 1701 and sent["max_tokens"] == 128 and sent["temperature"] == 0
    assert terminal(rig)["dispatches"] == 1 and terminal(rig, 2)["returned"]
    assert terminal(rig)["usage"]["input_tokens"] == {"available": True, "value": 100}
    assert terminal(rig)["usage"]["reasoning_tokens"] == {"available": False, "value": None}
    assert json.loads((rig.tmp / "client/client-summary.json").read_text())["generation_dispatch_attempts"] == 2
    assert len(rig.wires) == 8  # each call: residency + render + tokenize + exactly one generation


@pytest.mark.parametrize("error", [TimeoutError("invented timeout"), ConnectionError("invented disconnect")])
def test_failed_wire_is_one_attempt_and_durable_terminal(rig, error):
    rig.settings["error"] = error
    with rig.make() as client, pytest.raises(client.native.LLMError, match="failed"):
        client.complete(SYSTEM, CONVERSATION, TOOLS)
    assert len(rig.generations) == 1
    assert terminal(rig)["dispatches"] == 1
    assert not terminal(rig)["returned"] and terminal(rig)["usage"] is None
    events = [json.loads(line) for line in (rig.tmp / "client/model-calls.jsonl").read_text().splitlines()]
    assert [e["event"] for e in events].count("before_dispatch") == 1
    assert events[-1]["event"] == "request_error"


@pytest.mark.parametrize("status", [301, 400, 408, 429, 500, 503])
def test_http_failure_is_retained_without_retry(rig, status):
    rig.settings["status"] = status
    with rig.make() as client, pytest.raises(client.native.LLMError, match="HTTP"):
        client.complete(SYSTEM, CONVERSATION, TOOLS)
    assert len(rig.generations) == 1
    assert (rig.tmp / "client/0001-response.bin").is_file()
    assert json.loads((rig.tmp / "client/0001-response-meta.json").read_text())["status"] == status


@pytest.mark.parametrize("setting", ["preview_match", "token_match", "resident"])
def test_failed_full_context_check_dispatches_nothing(rig, setting):
    rig.settings[setting] = False
    with rig.make() as client, pytest.raises(client.native.LLMError):
        client.complete(SYSTEM, CONVERSATION, TOOLS)
    assert not rig.generations
    assert terminal(rig)["dispatches"] == 0
    context = json.loads((rig.tmp / "client/0001-context.json").read_text())
    assert context["passed"] is False


def test_prompt_overflow_refuses_without_trimming_or_generation(rig):
    conversation = [{"role": "user", "content": "x" * 9000}]
    with rig.make() as client, pytest.raises(client.native.LLMError, match="ContextRefusal"):
        client.complete(SYSTEM, conversation, TOOLS)
    assert not rig.wires and not rig.generations
    saved = json.loads((rig.tmp / "client/0001-native-input.json").read_text())
    assert saved["conversation"] == conversation


def test_missing_usage_is_unknown_beside_native_zero_aggregate(rig):
    rig.settings["payloads"] = [response(usage=False)]
    with rig.make() as client:
        value = client.complete(SYSTEM, CONVERSATION, TOOLS)
    assert value.usage.input_tokens == 0
    assert all(row == {"available": False, "value": None} for row in terminal(rig)["usage"].values())


@pytest.mark.parametrize("value", [True, -1, "0", None, 1.5])
def test_invalid_usage_value_does_not_become_known_zero(value):
    result = t.usage_availability({"usage": {"prompt_tokens": value}})
    assert result["input_tokens"] == {"available": False, "value": None}


def test_cap_has_no_replacement_generation(rig):
    with rig.make(max_requests=1) as client:
        client.complete(SYSTEM, CONVERSATION, TOOLS)
        with pytest.raises(client.native.LLMError, match="cap exhausted"):
            client.complete(SYSTEM, CONVERSATION, TOOLS)
    assert len(rig.generations) == 1
    refused = terminal(rig, 2)
    assert refused["dispatches"] == 0 and refused["budget_refusal"] is True
    assert refused["permitted_model_invocation"] is False
    assert refused["usage"] is None and refused["returned"] is False
    assert "cap exhausted" in refused["error"]["message"]
    summary = json.loads((rig.tmp / "client/client-summary.json").read_text())
    assert summary["native_invocations_including_budget_refusals"] == 2
    assert summary["permitted_model_invocations"] == 1
    assert summary["budget_refusals"] == 1
    assert summary["generation_dispatch_attempts"] == 1
    assert not (rig.tmp / "client/0002-request.bin").exists()


def test_hard_deadline_is_checked_before_dispatch(rig):
    with rig.make(absolute_deadline_monotonic=1) as client, pytest.raises(client.native.LLMError, match="deadline"):
        client.complete(SYSTEM, CONVERSATION, TOOLS)
    assert not rig.wires and terminal(rig)["dispatches"] == 0


def test_seed_can_be_omitted_explicitly(rig):
    with rig.make(seed=None) as client:
        client.complete(SYSTEM, CONVERSATION, TOOLS)
    assert "seed" not in rig.generations[0]


@pytest.mark.parametrize("url", ["https://127.0.0.1:11436/v1", "http://localhost:11436/v1",
    "http://127.0.0.1:11434/v1", "http://127.0.0.1:11436/v1?x=1", "http://x@127.0.0.1:11436/v1"])
def test_binding_rejects_other_destinations(binding, url):
    with pytest.raises(ValueError):
        t.RuntimeBinding.from_dict({**asdict(binding), "api_base": url})


@pytest.mark.parametrize("url", ["http://127.0.0.1:11436/api/generate", "http://127.0.0.1:34567/completion",
    "http://example.org:11436/v1/chat/completions", "http://127.0.0.1:11436/v1/chat/completions?x=1"])
def test_guard_rejects_unapproved_routes(binding, url):
    from research.native_agent.transport import TransportRefusal
    with pytest.raises(TransportRefusal):
        t.LoopbackGuard(binding).check_http("POST", url, b"{}")


def test_redirect_handler_never_builds_followup_request():
    assert t._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://example.org") is None


def test_existing_journal_directory_is_refused(rig):
    rig.make()
    with pytest.raises(FileExistsError):
        rig.make()


def test_use_requires_context_manager(rig):
    with pytest.raises(RuntimeError, match="context manager"):
        rig.make().complete(SYSTEM, CONVERSATION, TOOLS)


def test_native_parse_failure_keeps_observed_usage_and_raw_response(rig):
    payload = response()
    payload["choices"] = []
    rig.settings["payloads"] = [payload]
    with rig.make() as client, pytest.raises(client.native.LLMError, match="no choices"):
        client.complete(SYSTEM, CONVERSATION, TOOLS)
    saved = terminal(rig)
    assert saved["dispatches"] == 1 and saved["returned"] is False
    assert saved["usage"]["input_tokens"] == {"available": True, "value": 100}
    assert saved["usage"]["output_tokens"] == {"available": True, "value": 5}
    assert json.loads((rig.tmp / "client/0001-response.bin").read_bytes()) == payload


def test_closed_client_cannot_be_reused(rig):
    client = rig.make()
    with client:
        pass
    with pytest.raises(RuntimeError, match="One-shot client reuse"):
        with client:
            pass


def test_real_wire_retains_redirect_response_without_following(rig):
    client = rig.make()
    requests = []
    def opened(request, timeout):
        requests.append(request)
        raise HTTPError(request.full_url, 302, "redirect", {"Location": "http://example.org"}, BytesIO(b"raw redirect body"))
    client._opener = SimpleNamespace(open=opened)
    status, headers, body = WIRE_IMPLEMENTATION(client, "POST", client.binding.api_base + "/chat/completions",
                                               json.dumps({"model": client.model}).encode(), 1)
    assert status == 302 and body == b"raw redirect body"
    assert headers["Location"] == "http://example.org"
    assert len(requests) == 1


def test_pinned_source_loader_rejects_changed_bytes(monkeypatch, tmp_path):
    fake = tmp_path / "llm.py"
    fake.write_text("# changed\n")
    monkeypatch.setattr(t.importlib, "import_module", lambda name: SimpleNamespace(__file__=str(fake)))
    with pytest.raises(RuntimeError, match="upstream pin"):
        t.native_llm_module()


@pytest.fixture
def identity_rig(native, binding, tmp_path, monkeypatch):
    paths = {}
    for name in ("model", "server", "runner"):
        path = tmp_path / name
        path.write_bytes(("small invented " + name).encode())
        paths[name] = path
    b = t.RuntimeBinding.from_dict({**asdict(binding), "model_blob": str(paths["model"]),
        "server_executable": str(paths["server"]), "runner_executable": str(paths["runner"]),
        "model_blob_sha256": t.file_sha256(paths["model"]),
        "server_executable_sha256": t.file_sha256(paths["server"]),
        "runner_executable_sha256": t.file_sha256(paths["runner"])})
    args = [str(paths["runner"]), "--model", b.model_blob, "--port", str(b.runner_port),
        "--host", "127.0.0.1", "-c", "8192", "-np", "1", "--cache-type-k", "q8_0",
        "--cache-type-v", "q8_0", "--flash-attn", "on", "--offline"]
    state = {"server_exe": b.server_executable, "runner_exe": b.runner_executable,
             "server_born": b.server_create_time, "runner_born": b.runner_create_time,
             "args": args}
    def process(pid):
        name = "server" if pid == b.server_pid else "runner"
        return SimpleNamespace(exe=lambda: state[name + "_exe"],
            create_time=lambda: state[name + "_born"], cmdline=lambda: state["args"])
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=process))
    client = t.AuditedLIMBOClient(b, tmp_path / "client", max_requests=1,
        max_output_tokens=128, request_timeout_s=1200)
    return SimpleNamespace(client=client, state=state, paths=paths)


def test_live_identity_checks_all_file_hashes_and_repeated_stat(identity_rig):
    rig = identity_rig
    rig.client._verify_identity(initial=True)
    rig.client._verify_identity()
    rig.paths["model"].write_bytes(b"changed model bytes")
    with pytest.raises(RuntimeError, match="changed after"):
        rig.client._verify_identity()


@pytest.mark.parametrize("flag,value", [("-c", "16384"), ("-np", "2"),
    ("--cache-type-k", "f16"), ("--cache-type-v", "f16"), ("--flash-attn", "off"),
    ("--port", "9999"), ("--host", "0.0.0.0"), ("--model", "differentmodel")])
def test_identity_refuses_changed_runtime_command(identity_rig, flag, value):
    rig = identity_rig
    rig.state["args"][rig.state["args"].index(flag) + 1] = value
    with pytest.raises(RuntimeError, match="argument mismatch"):
        rig.client._verify_identity(initial=True)


@pytest.mark.parametrize("key,value", [("server_born", 1700000020), ("runner_born", 1700000020),
    ("server_exe", "D:/different.exe"), ("runner_exe", "D:/different.exe")])
def test_identity_refuses_pid_reuse_and_executable_change(identity_rig, key, value):
    identity_rig.state[key] = value
    with pytest.raises(RuntimeError, match="process identity"):
        identity_rig.client._verify_identity(initial=True)


def test_identity_refuses_missing_offline_flag(identity_rig):
    identity_rig.state["args"].remove("--offline")
    with pytest.raises(RuntimeError, match="not offline"):
        identity_rig.client._verify_identity(initial=True)


def test_initial_identity_rehashes_entire_bound_file(identity_rig):
    identity_rig.paths["model"].write_bytes(b"different content before first verification")
    with pytest.raises(RuntimeError, match="SHA-256 changed"):
        identity_rig.client._verify_identity(initial=True)
