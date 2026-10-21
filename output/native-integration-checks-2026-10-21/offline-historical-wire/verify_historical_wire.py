"""Offline real-SDK serialization replay of excluded development requests only.

Every HTTP send is intercepted before a socket and returns an explicitly
synthetic completion. These fixtures are not model outputs or task outcomes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.native_agent.harness import record_completions  # noqa: E402
from research.native_agent.transport import (  # noqa: E402
    LITELLM_MODEL, LOCAL_MODEL, LocalOnlyGuard, configure_local_environment,
    native_wire_equivalent,
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


class OfflineGuard(LocalOnlyGuard):
    def address(self, address, kind="network"):
        if getattr(self._thread, "socketpair", 0):
            return super().address(address, kind)
        self.refuse(kind, "All real connections forbidden during historical serialization replay")


class Journal:
    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(deepcopy(row))


def main():
    output = Path(__file__).resolve().parent
    historical = ROOT / "output/native-development-2026-10-21/native-19-000/episode"
    inputs = [historical / "model-calls.jsonl", historical / "context-events.jsonl"]
    bindings = {str(path.relative_to(ROOT)): {"sha256": digest(path), "bytes": path.stat().st_size}
                for path in inputs}
    implementations = {name: {"sha256": digest(ROOT / name), "bytes": (ROOT / name).stat().st_size}
        for name in ("research/native_agent/transport.py", "research/native_agent/harness.py")}
    starts = [json.loads(line) for line in inputs[0].read_text(encoding="utf-8").splitlines()
              if json.loads(line).get("kind") == "request_start"]
    contexts = [json.loads(line)["receipt"] for line in inputs[1].read_text(encoding="utf-8").splitlines()
                if json.loads(line).get("kind") == "context_gate_result"]
    assert len(starts) == len(contexts) == 14
    assert [row["call_index"] for row in starts] == list(range(14))
    historical_matches = [native_wire_equivalent(context["request"]["messages"], start["request"]["messages"])
                          for start, context in zip(starts, contexts)]
    assert all(historical_matches)
    configure_local_environment(output / "absent-data")
    with OfflineGuard(allow_generation=True, api_base="http://127.0.0.1:11436/v1") as guard:
        import httpx

        wires, previews = [], []

        def synthetic_send(client, request, *args, **kwargs):
            assert str(request.url) == "http://127.0.0.1:11436/v1/chat/completions"
            wires.append(json.loads(request.read()))
            return httpx.Response(200, json={"id": "synthetic-historical-replay", "object": "chat.completion",
                "created": 0, "model": LOCAL_MODEL, "choices": [{"index": 0,
                    "message": {"role": "assistant", "content": "Synthetic serialization fixture only"},
                    "finish_reason": "stop"}], "usage": {
                        "prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}}, request=request)

        httpx.Client.send = synthetic_send
        guard.attach_httpx()
        import litellm

        assert version("litellm") == "1.82.6" and version("openai") == "3.35.1"
        assert litellm.num_retries is None and litellm.model_fallbacks is None
        litellm.cache = None
        guard.require_native_invocation = True
        guard.before_generation = lambda payload: previews.append(deepcopy(payload))
        journal = Journal()
        state = record_completions(litellm, journal, 14, invoke_scope=guard.native_invocation)
        cases = []
        for start, historical_context in zip(starts, contexts):
            request = deepcopy(start["request"])
            original = deepcopy(request)
            assert request["model"] == LITELLM_MODEL
            response = litellm.completion(**request, api_key="local-dummy-unused")
            assert response.choices[0].message.content == "Synthetic serialization fixture only"
            assert request == original and guard._thread.native_invocation is None
            assert len(wires) == start["call_index"] + 1
            wire = wires[-1]
            assert native_wire_equivalent(wire["messages"], request["messages"])
            assert native_wire_equivalent(wire["messages"], historical_context["request"]["messages"])
            assert canonical_digest(wire) == canonical_digest(historical_context["request"])
            cases.append({"native_call_index": start["call_index"], "fake_http_sends": 1,
                "historical_wire_body_sha256": canonical_digest(historical_context["request"]),
                "reconstructed_wire_body_sha256": canonical_digest(wire), "same_wire_body": True,
                "same_native_messages_under_documented_null_equivalence": True, "input_unchanged": True})
        assert state["attempted"] == state["completed"] == state["provider_returned"] == 14
        assert state["failed"] == 0 and len(wires) == len(previews) == 14
        assert len([row for row in guard.events if row.get("generation_request")]) == 14
        assert not [row for row in guard.events if row.get("allowed") is False]
    assert all(digest(ROOT / name) == record["sha256"] for name, record in bindings.items())
    assert all(digest(ROOT / name) == record["sha256"] for name, record in implementations.items())
    result = {"schema": "conseqax-offline-historical-native-wire-replay-v1", "passed": True,
        "finished_utc": datetime.now(timezone.utc).isoformat(), "source": {
            "path": str(Path(__file__).relative_to(ROOT)), "sha256": digest(__file__)},
        "implementation_sources": implementations, "historical_inputs": bindings,
        "historical_inputs_unchanged": True, "versions": {name: version(name) for name in ("litellm", "openai", "httpx")},
        "cases": cases, "native_completion_invocations": 14, "synthetic_http_sends": 14,
        "actual_network_connections": 0, "actual_model_generations": 0,
        "official_evaluation_episodes": 0, "scope": "Excluded historical development requests; synthetic replies only"}
    write_new(output / "result.json", result)
    files = {path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
             for path in sorted(output.iterdir()) if path.is_file()}
    write_new(output / "manifest.json", {"schema": "conseqax-offline-historical-wire-evidence-v1",
        "complete": True, "files": files})
    print(json.dumps({"passed": True, "retained_historical_pairs": len(cases),
        "synthetic_http_sends": len(wires), "actual_network_connections": 0, "actual_model_generations": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
