"""Task-independent multi-family schema/history and bounded live tool-call gate."""
from dataclasses import asdict
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.expanded_limbo.transport import ExpandedLIMBOClient  # noqa:E402
from research.limbo_agent.transport import RuntimeBinding  # noqa:E402
from research.limbo_agent.protocol import file_binding, utc, write_new  # noqa:E402
from research.limbo_agent.harness import manifest, plain  # noqa:E402


def check(native_root, binding_path, output, *, live=False):
    sys.path.insert(0, str(Path(native_root).resolve()))
    from limbo.services import build_tools
    from limbo.prompts import GENERAL_TOOL_SCHEMAS
    binding = RuntimeBinding.from_dict(json.loads(Path(binding_path).read_text(encoding="utf-8")))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    schemas = [tool.schema("neutral") for _, tool in sorted(build_tools("native").items())]
    schemas += GENERAL_TOOL_SCHEMAS
    invented = {"name": "lookup_echo", "description": "Return an invented read-only transport-test value.",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}},
                       "required": ["name"]}}
    checks = []
    with ExpandedLIMBOClient(binding, output / "client", max_requests=2,
            max_output_tokens=128, request_timeout_s=300, seed=2501, temperature=.2) as client:
        cases = [
            ("public-schemas", schemas, [{"role": "system", "content": "Public schema-only research transport check."},
                {"role": "user", "content": "Do not execute anything."}]),
            ("tool-history", [invented], [{"role": "system", "content": "Invented read-only tool history."},
                {"role": "user", "content": "Look up the test item."},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "invented-call-1", "type": "function",
                    "function": {"name": "lookup_echo", "arguments": "{\"name\":\"test-item\"}"}}]},
                {"role": "tool", "tool_call_id": "invented-call-1", "content": "{\"ok\":true,\"value\":7}"}]),
        ]
        for label, tools, messages in cases:
            payload = {"model": binding.model, "messages": messages,
                "tools": [{"type": "function", "function": tool} for tool in tools],
                "max_tokens": 128, "temperature": .2, "seed": 2501}
            client._current = {"prefix": output / label, "number": 0, "dispatched": 0}
            try:
                receipt = client._context_check(payload)
            finally:
                client._current = None
            checks.append({"label": label, "passed": receipt["passed"],
                           "context": receipt["context"]})
        calls = []
        if live:
            for item in ("test-item", "second-item"):
                turn = client.complete(
                    "This is an invented transport check. Call lookup_echo exactly once with the requested name. Do not answer in prose.",
                    [{"role": "user", "content": "Call lookup_echo with name " + item}], [invented])
                write_new(output / (item + "-parsed-turn.json"), plain(turn))
                native_calls = turn.tool_calls
                if (len(native_calls) != 1 or native_calls[0].name != "lookup_echo"
                        or native_calls[0].parsed_arguments() != ({"name": item}, None)):
                    raise ValueError("Checkpoint did not return the declared invented native tool call")
                calls.append({"input": item, "returned_native_call": True})
    value = {"schema": "conseqax-expanded-transport-preflight-v1", "utc": utc(),
        "passed": True, "runtime": asdict(binding), "native_tasks": 0,
        "public_tool_schema_count": len(schemas), "schema_history_checks": checks,
        "actual_generation_dispatches": len(calls), "live_tool_call_checks": calls,
        "independent_offline_template_tokenizer_parity": False,
        "preflight_source": {"path": str(Path(__file__).resolve()), **file_binding(__file__)},
        "transport_source": {"path": str(ROOT / "research/expanded_limbo/transport.py"),
                             **file_binding(ROOT / "research/expanded_limbo/transport.py")},
        "scope": "Invented transport examples only; not model accuracy or native benchmark results"}
    write_new(output / "preflight.json", value)
    write_new(output / "manifest.json", manifest(output))
    print(json.dumps({"passed": True, "model": binding.model, "native_tasks": 0,
                      "generation_dispatches": len(calls), "output": str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", required=True)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    check(args.native_root, args.binding, args.output, live=args.live)


if __name__ == "__main__":
    main()
