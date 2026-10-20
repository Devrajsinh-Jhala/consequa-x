"""Retain native Tau/LiteLLM request construction without any HTTP dispatch.

This is transport inspection, not generation, task evaluation, or a mock success.
The send interceptor deliberately raises before network I/O; no fake response is
returned to the native code. All examples are invented and task-independent.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import traceback

OUT = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit")
EXPECTED = "96a3ef92329baf908ffe9dfe188cea34e8701d2a"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def git(*args):
    return subprocess.check_output(["git", "-C", str(SOURCE), *args], text=True).strip()


def hashes():
    paths = sorted((SOURCE / "src/tau2").rglob("*.py"))
    return {p.relative_to(SOURCE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in paths}


if git("rev-parse", "HEAD") != EXPECTED or git("status", "--porcelain", "--untracked-files=no"):
    raise RuntimeError("Pinned upstream source identity/cleanliness failed")
before = hashes()
os.environ.update({
    "PYTHON_DOTENV_DISABLED": "1",
    "TAU2_DATA_DIR": str(SOURCE / "data"),
    "LITELLM_LOCAL_MODEL_COST_MAP": "True",
    "LITELLM_TELEMETRY": "False",
    "DO_NOT_TRACK": "1",
})
for name in tuple(os.environ):
    upper = name.upper()
    if (upper.endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN"))
            or upper in {"GOOGLE_APPLICATION_CREDENTIALS", "AWS_SHARED_CREDENTIALS_FILE"}):
        os.environ.pop(name, None)

network_attempts = []
source_writes = []
credential_reads = []
subprocess_attempts = []
guard_active = True


class StoppedBeforeDispatch(BaseException):
    pass


def blocked_socket(event, *args, **kwargs):
    network_attempts.append({"event": event})
    raise StoppedBeforeDispatch("All socket traffic is blocked in wire-only inspection")


def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        blocked_socket(event)
    if event == "subprocess.Popen" and guard_active:
        subprocess_attempts.append({"event": event})
        raise StoppedBeforeDispatch("Subprocess disabled during inspection")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path, mode, flags = args
        resolved = Path(path).resolve()
        writing = ((mode and any(c in mode for c in "wax+"))
                   or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and resolved.is_relative_to(SOURCE):
            source_writes.append(str(resolved))
            raise StoppedBeforeDispatch("Pinned source writes are disabled")
        if not writing and (resolved.name == ".env" or resolved.name.startswith(".env.")
                            or resolved.name in {"credentials", ".pypirc", "Pypi token.txt"}):
            credential_reads.append(str(resolved))
            raise StoppedBeforeDispatch("Credential/dotenv reads are disabled")


sys.addaudithook(audit)
socket.socket.connect = lambda *a, **k: blocked_socket("socket.connect")
socket.socket.connect_ex = lambda *a, **k: blocked_socket("socket.connect_ex")
socket.create_connection = lambda *a, **k: blocked_socket("socket.create_connection")
socket.getaddrinfo = lambda *a, **k: blocked_socket("socket.getaddrinfo")
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE / "src"))

result = {
    "scope": "task-independent request construction only; all dispatch blocked",
    "python": sys.version, "executable": sys.executable,
    "upstream_commit": EXPECTED,
    "litellm": importlib.metadata.version("litellm"),
    "actual_generation_attempts": 0,
    "official_evaluation_tasks_read_or_run": 0,
    "fake_provider_responses": 0,
    "source_patch": False,
    "network_guard": "Python socket/DNS and imported subprocess refusal; not an OS-level firewall",
    "candidates": [],
}
exit_code = 0
try:
    import httpx
    from tau2.data_model.message import AssistantMessage, SystemMessage, ToolCall, ToolMessage, UserMessage
    from tau2.environment.tool import Tool
    from tau2.utils.llm_utils import generate, to_litellm_messages

    def read_toy_record(record_id: str) -> str:
        """Read a synthetic transport-test record.

        Args:
            record_id: Identifier of the synthetic record.
        """
        raise RuntimeError("This tool must not execute during wire inspection")

    tool = Tool(read_toy_record)

    def history():
        return [
            SystemMessage(role="system", content="Synthetic transport inspection. Use only the provided toy tool result."),
            UserMessage(role="user", content="Look up toy record TOY-ALPHA."),
            AssistantMessage(role="assistant", content=None, tool_calls=[
                ToolCall(id="call_transport_0001", name="read_toy_record", arguments={"record_id": "TOY-ALPHA"})]),
            ToolMessage(role="tool", id="call_transport_0001", content='{"record_id":"TOY-ALPHA","status":"ready"}'),
        ]

    cases = [
        {"id": "ollama-chat-native", "model": "ollama_chat/" + MODEL,
         "api_base": "http://127.0.0.1:11434", "num_ctx": 16384},
        {"id": "openai-compatible-local", "model": "openai/" + MODEL,
         "api_base": "http://127.0.0.1:11434/v1", "api_key": "local-dummy-unused",
         "extra_body": {"options": {"num_ctx": 16384}}},
    ]
    for settings in cases:
        settings = dict(settings)
        candidate_id = settings.pop("id")
        model = settings.pop("model")
        native_messages = history()
        candidate = {
            "id": candidate_id, "model": model,
            "kwargs": {**settings, "temperature": 0, "max_tokens": 128, "seed": 1701,
                       "num_retries": 0, "timeout": 60},
            "native_messages": [m.model_dump(exclude_none=True) for m in native_messages],
            "native_converted_messages": to_litellm_messages(native_messages),
            "tools_schema": [tool.openai_schema],
            "captured_requests": [], "status": "incomplete",
        }

        def capture(self, request, *args, **kwargs):
            raw = request.read()
            candidate["captured_requests"].append({
                "method": request.method, "url": str(request.url),
                "content_type": request.headers.get("content-type"),
                "body_utf8": raw.decode("utf-8"),
                "body_sha256": hashlib.sha256(raw).hexdigest(),
                "body_json": json.loads(raw),
                "sent": False,
            })
            raise StoppedBeforeDispatch("Exact request captured; HTTP dispatch deliberately refused")

        httpx.Client.send = capture
        try:
            generate(model=model, messages=native_messages, tools=[tool],
                     temperature=0, max_tokens=128, seed=1701, num_retries=0, timeout=60,
                     **settings)
            candidate["status"] = "unexpected_return"
            exit_code = 1
        except StoppedBeforeDispatch as error:
            candidate["status"] = "captured_without_dispatch" if candidate["captured_requests"] else "blocked_before_capture"
            candidate["stop_reason"] = str(error)
        except Exception as error:
            candidate["status"] = "construction_error"
            candidate["error_type"] = type(error).__name__
            candidate["error"] = str(error)
            candidate["traceback"] = traceback.format_exc()
        result["candidates"].append(candidate)
except BaseException as error:
    result["error_type"] = type(error).__name__
    result["error"] = str(error)
    result["traceback"] = traceback.format_exc()
    exit_code = 1
finally:
    guard_active = False
    result["network_attempts"] = network_attempts
    result["source_write_attempts"] = source_writes
    result["credential_read_attempts"] = credential_reads
    result["subprocess_attempts"] = subprocess_attempts
    result["source_hashes_before"] = before
    result["source_hashes_after"] = hashes()
    result["source_unchanged"] = before == result["source_hashes_after"]
    result["tracked_source_clean_after"] = not git("status", "--porcelain", "--untracked-files=no")
    result["passed_as_wire_capture"] = (len(result["candidates"]) == 2
        and all(c["status"] == "captured_without_dispatch" and len(c["captured_requests"]) == 1
                for c in result["candidates"])
        and result["source_unchanged"] and result["tracked_source_clean_after"]
        and not any([network_attempts, source_writes, credential_reads, subprocess_attempts]))
    if not result["passed_as_wire_capture"]:
        exit_code = 1
    (OUT / "wire-capture.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ["passed_as_wire_capture", "actual_generation_attempts", "source_unchanged", "network_attempts"]}))
    print(json.dumps([{"id": c["id"], "status": c["status"], "captured_requests": len(c["captured_requests"])} for c in result["candidates"]]))
sys.exit(exit_code)
