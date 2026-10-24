"""Two-call invented account-tool roundtrip; not a LIMBO task or score.

This command generates locally when explicitly executed. It never executes a
service handler. The response is an openly invented transport fixture, distinct
from any native task, hidden evaluator state, fault schedule or benchmark score.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from research.limbo_agent.transport import AuditedLIMBOClient, RuntimeBinding, write_json


def run(binding, output, *, max_output_tokens, request_timeout_s, seed):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "conseqax-limbo-transport-roundtrip-v1", "passed": False,
              "scope": "Invented task-independent transport fixture only; no native benchmark task",
              "runtime": asdict(binding), "native_episodes": 0, "service_dispatches": 0,
              "model_invocation_cap": 2, "full_history_preserved": True}
    system = "You are an account assistant. Use available tools to look up account details. Answer the user's question using the tool result."
    conversation = [{"role": "user", "content": "What membership level is on my account? My user ID is LIMBO_TRANSPORT_FIXTURE."}]
    tools = [{"name": "get_user_details", "description": "Look up account details for a user ID.",
              "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}},
                             "required": ["user_id"]}}]
    try:
        with AuditedLIMBOClient(binding, output / "client", max_requests=2,
                max_output_tokens=max_output_tokens, request_timeout_s=request_timeout_s,
                seed=seed, absolute_deadline_monotonic=time.monotonic() + request_timeout_s * 2 + 300) as client:
            first = client.complete(system, conversation, tools)
            if len(first.tool_calls) != 1:
                raise RuntimeError("Probe expected exactly one structured account-tool request")
            call = first.tool_calls[0]
            arguments, error = call.parsed_arguments()
            if error or call.name != "get_user_details" or arguments != {"user_id": "LIMBO_TRANSPORT_FIXTURE"}:
                raise RuntimeError("Probe returned a different tool or changed its supplied identifier")
            conversation.append({"role": "assistant", "content": first.text,
                                 "tool_calls": [{"id": call.id, "name": call.name, "arguments": call.arguments}]})
            conversation.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": json.dumps({"user_id": "LIMBO_TRANSPORT_FIXTURE", "membership": "silver"})})
            second = client.complete(system, conversation, tools)
            if second.tool_calls or "silver" not in second.text.lower():
                raise RuntimeError("Probe follow-up did not use the retained account result")
            result["first_tool"] = {"id": call.id, "name": call.name, "arguments": arguments}
            result["followup_text"] = second.text
            result["passed"] = True
    except BaseException as error:
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        write_json(output / "probe-result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--request-timeout", type=float, default=1200)
    parser.add_argument("--seed", type=int, default=1701)
    args = parser.parse_args()
    binding = RuntimeBinding.from_dict(json.loads(Path(args.binding).read_text(encoding="utf-8")))
    result = run(binding, args.output, max_output_tokens=args.max_output_tokens,
                 request_timeout_s=args.request_timeout, seed=args.seed)
    print(json.dumps({"passed": result["passed"], "output": str(Path(args.output).resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
