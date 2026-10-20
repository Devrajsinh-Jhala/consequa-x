"""Offline Ollama transformer and native policy/schema size inspection only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

OUT = Path(__file__).resolve().parent
SOURCE = Path("C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit")
EXPECTED = "96a3ef92329baf908ffe9dfe188cea34e8701d2a"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def git(*args):
    return subprocess.check_output(["git", "-C", str(SOURCE), *args], text=True).strip()


if git("rev-parse", "HEAD") != EXPECTED or git("status", "--porcelain", "--untracked-files=no"):
    raise RuntimeError("Pinned native source changed")
os.environ.update({"PYTHON_DOTENV_DISABLED": "1", "TAU2_DATA_DIR": str(SOURCE / "data"),
                   "LITELLM_LOCAL_MODEL_COST_MAP": "True", "LITELLM_TELEMETRY": "False",
                   "DO_NOT_TRACK": "1"})
for name in tuple(os.environ):
    if name.upper().endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN")):
        os.environ.pop(name, None)
network_attempts = []
task_read_attempts = []
guard_active = True


def audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        network_attempts.append(event)
        raise RuntimeError("Offline transform inspection forbids networking")
    if event == "subprocess.Popen" and guard_active:
        raise RuntimeError("Imported subprocesses forbidden")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path, mode, flags = args
        resolved = Path(path).resolve()
        writing = ((mode and any(c in mode for c in "wax+"))
                   or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing and resolved.is_relative_to(SOURCE):
            raise RuntimeError("Pinned source write forbidden")
        if not writing and resolved.is_relative_to(SOURCE / "data") and "tasks" in resolved.name:
            task_read_attempts.append(str(resolved))
            raise RuntimeError("Official evaluation task definitions must not be read")
        if not writing and (resolved.name == ".env" or resolved.name.startswith(".env.")
                            or resolved.name in {"credentials", ".pypirc", "Pypi token.txt"}):
            raise RuntimeError("Credential/dotenv reads forbidden")


sys.addaudithook(audit)
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE / "src"))

from tau2.agent.llm_agent import LLMAgent
from tau2.data_model.message import AssistantMessage, SystemMessage, ToolCall, ToolMessage, UserMessage
from tau2.domains.airline.environment import get_environment
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import to_litellm_messages
from litellm.llms.ollama.chat.transformation import OllamaChatConfig


def read_toy_record(record_id: str) -> str:
    """Read a synthetic transport-test record.

    Args:
        record_id: Identifier of the synthetic record.
    """
    raise RuntimeError("Tool execution forbidden in this probe")


toy_tool = Tool(read_toy_record)
history = [
    SystemMessage(role="system", content="Synthetic transport inspection. Use only the provided toy tool result."),
    UserMessage(role="user", content="Look up toy record TOY-ALPHA."),
    AssistantMessage(role="assistant", content=None, tool_calls=[
        ToolCall(id="call_transport_0001", name="read_toy_record", arguments={"record_id": "TOY-ALPHA"})]),
    ToolMessage(role="tool", id="call_transport_0001", content='{"record_id":"TOY-ALPHA","status":"ready"}'),
]
converted = to_litellm_messages(history)
wire = OllamaChatConfig().transform_request(
    model=MODEL,
    messages=to_litellm_messages(history),
    optional_params={"tools": [toy_tool.openai_schema], "num_ctx": 16384,
                     "num_predict": 128, "temperature": 0, "seed": 1701},
    litellm_params={}, headers={})
wire_bytes = json.dumps(wire, separators=(",", ":"), ensure_ascii=False).encode()
env = get_environment()
tools = env.get_tools()
agent = LLMAgent(tools=tools, domain_policy=env.get_policy(),
                 llm="openai/conseqax-native-probe-20261020:ctx16k", llm_args={})
system = agent.system_prompt
schemas = [t.openai_schema for t in tools]
full_native_input = {"messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": "Hello. This is a synthetic policy-size inspection, not an evaluation task."}],
                     "tools": schemas}
native_bytes = json.dumps(full_native_input, ensure_ascii=False, separators=(",", ":")).encode()
transform_path = Path(sys.modules["litellm.llms.ollama.chat.transformation"].__file__)
result = {
    "scope": "offline transformer inspection and task-independent native airline policy/schema sizing",
    "actual_generation_attempts": 0, "tool_executions": 0,
    "evaluation_task_reads": task_read_attempts, "network_attempts": network_attempts,
    "upstream_commit": EXPECTED,
    "transformer_file": str(transform_path),
    "transformer_sha256": hashlib.sha256(transform_path.read_bytes()).hexdigest(),
    "native_converted_messages": converted,
    "ollama_body": wire,
    "ollama_body_utf8": wire_bytes.decode(),
    "ollama_body_sha256": hashlib.sha256(wire_bytes).hexdigest(),
    "prior_assistant_tool_call_preserved": bool(wire["messages"][2].get("tool_calls")),
    "prior_tool_result_id_preserved": wire["messages"][3].get("tool_call_id") == "call_transport_0001",
    "tools_schema_preserved": wire.get("tools") == [toy_tool.openai_schema],
    "explicit_context_preserved": wire.get("options", {}).get("num_ctx") == 16384,
    "native_policy_input": full_native_input,
    "native_policy_size": {
        "system_prompt_utf8_bytes": len(system.encode()),
        "native_tool_count": len(tools),
        "tool_schemas_utf8_bytes": len(json.dumps(schemas, ensure_ascii=False, separators=(",", ":")).encode()),
        "serialized_complete_input_utf8_bytes": len(native_bytes),
        "serialized_complete_input_sha256": hashlib.sha256(native_bytes).hexdigest(),
        "exact_prompt_tokens": None,
        "tokenizer_status": "No verified exact installed Qwen3 offline tokenizer; no generation/tokenization endpoint called. Serialized bytes are not token counts.",
        "context_fit_verified": False,
        "dialogue_headroom_verified": False,
    },
}
guard_active = False
result["tracked_source_clean_after"] = not git("status", "--porcelain", "--untracked-files=no")
(OUT / "offline-transform.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: result[k] for k in ["prior_assistant_tool_call_preserved", "prior_tool_result_id_preserved", "tools_schema_preserved", "explicit_context_preserved", "native_policy_size", "network_attempts", "tracked_source_clean_after"]}))
