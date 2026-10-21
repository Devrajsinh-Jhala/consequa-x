"""Lean authorized server render/token checks; zero model generation requests."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback

ROOT = Path("D:/ConsequaX-Research/paper-writing")
OUT = Path(__file__).resolve().parent
MODELS = Path("C:/Users/DELL/.ollama/models")
SOURCE = Path("C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit")
spec = importlib.util.spec_from_file_location("transport", ROOT / "research/native_agent/transport.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
transport.configure_local_environment(SOURCE / "data")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


record = {"started_utc": datetime.now(timezone.utc).isoformat(), "executable": sys.executable,
          "scope": "pre-generation isolated parallel2 q8_0 server renderer/tokenizer validation",
          "actual_generation_attempts": 0, "official_tasks_read": 0,
          "native_wire_sources": {}, "checks": [], "memory_gate": None,
          "transport_source_sha256": sha(ROOT / "research/native_agent/transport.py")}
exit_code = 1
try:
    with transport.LocalOnlyGuard(protected_roots=[SOURCE, MODELS], allow_render_only=True,
                                  api_base="http://127.0.0.1:11436/v1") as guard:
        httpx = guard.attach_httpx()
        import psutil
        with httpx.Client(trust_env=False, timeout=240) as client:
            for name, path in [("version", "/api/version"), ("tags", "/api/tags"), ("loaded_before", "/api/ps")]:
                response = client.get(guard.server_base + path)
                response.raise_for_status()
                record[name] = response.json()
            if record["loaded_before"].get("models"):
                raise RuntimeError("Expected empty isolated research server")
            memory = int(psutil.virtual_memory().available)
            record["memory_gate"] = {"available_bytes": memory,
                                      "weights_bytes": 2497293803, "q8_0_kv_bytes": 2566914048, "parallel_slots":2, "context_tokens_per_slot":16384,
                                      "reserve_bytes": 1073741824, "required_bytes": 6137949675,
                                      "passed": memory >= 6137949675,
                                      "q8_0_formula": "2 * f16KV * (34/32) / 2; block scale overhead included"}
            if not record["memory_gate"]["passed"]:
                raise RuntimeError("Fresh isolated q8_0 conservative memory gate refused loading")
            for name in ["full_native_opening", "full_native_tool_followup", "wrapped_two_system_opening"]:
                if name == "wrapped_two_system_opening":
                    source = ROOT / "output/native-development-2026-10-21/wrapped-opening-render/result.json"
                else:
                    source = OUT.parent.parent / ("native-wire-v2-" + name + ".json")
                record["native_wire_sources"][source.name] = sha(source)
                original = json.loads(source.read_text(encoding="utf-8"))
                if name == "wrapped_two_system_opening":
                    source_request = {"body": original["receipt"]["request"]}
                else:
                    source_request = original["observed"]
                payload = deepcopy(source_request["body"])
                payload["_debug_render_only"] = True
                payload["keep_alive"] = -1
                response = client.post(guard.api_base + "/chat/completions", json=payload)
                response.raise_for_status()
                response_body = response.json()
                prompt = response_body.get("_debug_info", {}).get("rendered_template")
                if not isinstance(prompt, str):
                    raise RuntimeError("Server did not return debug-only rendered prompt")
                record["checks"].append({"name": name, "original_native_request": source_request,
                                          "request": payload, "response": response_body,
                                          "runtime_rendered_prompt": prompt})
                (OUT / "isolated-q8-render.partial.json").write_text(json.dumps(record, indent=2) + "\n")
            response = client.get(guard.server_base + "/api/ps")
            response.raise_for_status()
            record["loaded_after"] = response.json()
            blob = MODELS / "blobs" / ("sha256-" + transport.MODEL_BLOB_SHA256)
            runners = []
            for process in psutil.process_iter(["pid", "ppid", "exe", "cmdline"]):
                try:
                    identity = process.info
                    args = identity["cmdline"] or []
                    if (identity["exe"] and Path(identity["exe"]).name == "llama-server.exe"
                            and any(Path(arg).name == blob.name for arg in args)):
                        runners.append(identity)
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            launch = json.loads((OUT.parent / "isolated-q8-server-launch.json").read_text())
            runners = [runner for runner in runners if runner["ppid"] == launch["server_pid"]]
            record["matching_research_runners"] = runners
            if len(runners) != 1:
                raise RuntimeError("Expected one private runner under isolated server PID")
            runner = runners[0]
            args = runner["cmdline"]
            port = int(args[args.index("--port") + 1])
            guard.register_tokenizer_runner(port=port, pid=runner["pid"], executable=runner["exe"],
                                            executable_sha256=sha(runner["exe"]), model_blob=str(blob),
                                            model_blob_sha256=transport.MODEL_BLOB_SHA256)
            record["tokenizer_runner_binding"] = guard.tokenizer_runner
            metadata = transport.read_gguf_metadata(blob)
            tokenizer = transport.tokenizer_from_gguf(metadata)
            for check in record["checks"]:
                payload = check["request"]
                offline = transport.render_gguf_template(metadata, payload["messages"], payload["tools"])
                prompt = check["runtime_rendered_prompt"]
                check["same_rendered_bytes"] = offline == prompt
                check["offline_rendered_prompt"] = offline
                check["context_receipt"] = transport.context_gate(prompt, tokenizer)
                token_request = {"content": prompt, "add_special": True, "parse_special": True, "with_pieces": False}
                response = client.post(f"http://127.0.0.1:{port}/tokenize", json=token_request)
                response.raise_for_status()
                check["runtime_tokenizer_request"] = token_request
                check["runtime_tokenizer_response"] = response.json()
                actual = response.json().get("tokens")
                expected = tokenizer.encode(prompt, add_special_tokens=False).ids
                check["same_runtime_token_ids"] = actual == expected
                check["runtime_prompt_tokens"] = len(actual) if isinstance(actual, list) else None
            record["available_after_bytes"] = int(psutil.virtual_memory().available)
            record["passed"] = all(check["same_rendered_bytes"] and check["same_runtime_token_ids"]
                                   for check in record["checks"])
            exit_code = 0 if record["passed"] else 1
except BaseException as error:
    record["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    record["passed"] = False
finally:
    if "guard" in globals():
        record["network_events"] = guard.events
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (OUT / "isolated-q8-render-result.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": record["passed"], "error": record.get("error"),
                      "memory_gate": record["memory_gate"], "generation_attempts": 0,
                      "checks": [{k: c.get(k) for k in ["name", "same_rendered_bytes", "same_runtime_token_ids", "runtime_prompt_tokens"]}
                                 for c in record["checks"]]}, indent=2))
sys.exit(exit_code)
