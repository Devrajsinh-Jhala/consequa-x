"""Load existing local weights under a verified private CPU runtime and no job.

This auxiliary launcher creates only a separately named local research listener.
It requests one empty-prompt load and zero completions. It never replaces an
alias, retries a run, controls another service, installs, or downloads a model.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import time
import urllib.request

import psutil

from launch_durable_research import file_binding, is_process_in_job, launch, require, write_new


BLOB_SHA = "85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9"
BASE_TAG = "qwen3:4b-instruct-2507-q4_K_M"
SERVER = "http://127.0.0.1:11436"


def utc():
    return datetime.now(timezone.utc).isoformat()


def verify_private(directory):
    directory = Path(directory).resolve(strict=True)
    manifest_path = directory / "private-runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["schema"] == "conseqax-private-cpu-runtime-v1", "Unknown private runtime manifest")
    require(Path(manifest["destination"]).resolve() == directory, "Private runtime path differs")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
              if p.is_file() and p != manifest_path}
    require(actual == set(manifest["files"]), "Private runtime file inventory changed")
    for relative, expected in manifest["files"].items():
        path = directory / relative
        require(directory in path.resolve().parents and not path.is_symlink(), "Unsafe private runtime path")
        require(file_binding(path) == expected, "Private runtime file changed: " + relative)
    require(manifest["source_before_equals_source_after_equals_private_copy"] is True,
            "Private copy was not verified")
    return manifest


def start(private_runtime, models, output, tag):
    output = Path(output).resolve()
    models = Path(models).resolve(strict=True)
    private_runtime = Path(private_runtime).resolve(strict=True)
    require(not output.exists(), "Refuse existing one-shot runtime output")
    require(tag.startswith("conseqax-limbo-") and tag.endswith(":ctx8k"), "Require new explicit research alias")
    private = verify_private(private_runtime)
    executable = private_runtime / "ollama.exe"
    blob = models / ("blobs/sha256-" + BLOB_SHA)
    base_manifest = models / "manifests-v2/ollama.com/library/qwen3/4b-instruct-2507-q4_K_M"
    require(blob.is_file() and base_manifest.is_file(), "Existing model weights/manifest are required; no downloads")
    with socket.socket() as test:
        test.bind(("127.0.0.1", 11436))
    required = blob.stat().st_size + 612 * 1024**2 + 1024**3
    available = psutil.virtual_memory().available
    require(available >= required, f"Cold memory gate: {available} available, {required} required")
    require(file_binding(blob)["sha256"] == BLOB_SHA, "Existing GGUF digest differs")
    before = file_binding(base_manifest)
    output.mkdir(parents=True, exist_ok=False)
    environment = {"OLLAMA_HOST": "127.0.0.1:11436", "OLLAMA_MODELS": str(models),
        "OLLAMA_NO_CLOUD": "1", "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_CONTEXT_LENGTH": "8192", "OLLAMA_KEEP_ALIVE": "-1",
        "OLLAMA_NOPRUNE": "1", "OLLAMA_DEBUG": "1"}
    record = {"schema": "conseqax-durable-limbo-runtime-v1", "started_utc": utc(),
        "scope": "One isolated private CPU listener; existing weights; zero completion requests",
        "private_runtime_manifest": {"path": str(private_runtime / "private-runtime-manifest.json"),
                                    **file_binding(private_runtime / "private-runtime-manifest.json")},
        "declared_runtime_version": private["declared_version"], "process_only_environment": environment,
        "model_generation_attempts": 0, "model_load_requests": 0, "model_downloads": 0,
        "normal_service_modified": False, "base_manifest_before": before,
        "cold_memory_gate": {"available_bytes": available, "required_bytes": required,
            "scope": "Weights + expected single8k q8 KV +1GiB reserve, not maximum later memory"},
        "source": {"path": str(Path(__file__).resolve()), **file_binding(__file__)}}
    write_new(output / "start.json", record)
    launched = launch([str(executable), "serve"], private_runtime, output / "durable-server-launch",
        environment, [private_runtime / "private-runtime-manifest.json", executable,
                      private_runtime / "lib/ollama/llama-server.exe"], mechanism="wmi_two_stage",
                      job_policy="ambient_non_killing")
    identity = launched["target"]
    server = psutil.Process(identity["pid"])
    require(abs(server.create_time() - identity["create_time"]) < .001, "Research server identity changed")
    require(launched["target"].get("listed_in_supervisor_non_killing_ambient_job") is True,
            "Research server must be listed in the verified non-killing ambient job")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(path, payload=None, timeout=120):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(SERVER + path, data=data, headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=timeout) as response:
            return json.load(response)

    for attempt in range(40):
        try:
            version = api("/api/version", timeout=2)
            break
        except Exception:
            require(server.is_running() and abs(server.create_time() - identity["create_time"]) < .001,
                    "Research listener exited; unrelated processes are untouched")
            time.sleep(.5)
    else:
        raise RuntimeError("Research listener readiness failed; preserve output and do not duplicate launch")
    require(version.get("version") == private["declared_version"], "Live runtime version differs from private copy")
    tags = api("/api/tags")["models"]
    require(not any(item["name"] == tag for item in tags), "Refuse replacing existing research model alias")
    created = api("/api/create", {"model": tag, "from": BASE_TAG, "parameters": {
        "num_ctx": 8192, "num_predict": 512, "temperature": 0, "seed": 1701}, "stream": False})
    write_new(output / "alias-create.json", created)
    show = api("/api/show", {"model": tag})
    write_new(output / "model-show.json", show)
    loaded = api("/api/generate", {"model": tag, "prompt": "", "stream": False,
        "keep_alive": -1, "options": {"num_ctx": 8192, "num_predict": 0}})
    write_new(output / "load-only.json", loaded)
    require(loaded.get("done_reason") == "load" and not loaded.get("response"), "Expected load-only response")
    resident = [item for item in api("/api/ps")["models"] if item["name"] == tag]
    require(len(resident) == 1 and resident[0]["context_length"] == 8192, "Resident context differs")
    write_new(output / "resident-model.json", resident[0])
    candidates = [p for p in server.children(recursive=True) if p.name().lower() == "llama-server.exe"]
    require(len(candidates) == 1, "Expected one private CPU model runner")
    runner = candidates[0]
    require(Path(runner.exe()).resolve() == (private_runtime / "lib/ollama/llama-server.exe").resolve(),
            "Runner did not use the private CPU binary")
    require(is_process_in_job(runner.pid) is True, "Model runner ambient job membership unexpectedly differs")
    args = runner.cmdline()
    port = int(args[args.index("--port") + 1])
    require(str(blob).lower() in " ".join(args).lower(), "Runner model path differs")
    runtime_binding = {"api_base": SERVER + "/v1", "model": tag, "model_digest": resident[0]["digest"],
        "model_blob": str(blob), "model_blob_sha256": BLOB_SHA, "server_pid": server.pid,
        "server_executable": server.exe(), "server_executable_sha256": file_binding(server.exe())["sha256"],
        "server_create_time": server.create_time(), "runner_pid": runner.pid, "runner_executable": runner.exe(),
        "runner_executable_sha256": file_binding(runner.exe())["sha256"], "runner_create_time": runner.create_time(),
        "runner_port": port, "context_tokens": 8192, "parallel_slots": 1}
    verify_private(private_runtime)
    require(file_binding(base_manifest) == before, "Original base model manifest changed")
    write_new(output / "runtime-binding.json", runtime_binding)
    record.update({"finished_utc": utc(), "server_pid": server.pid, "runner_pid": runner.pid,
        "server_in_any_windows_job": is_process_in_job(server.pid),
        "runner_in_any_windows_job": is_process_in_job(runner.pid),
        "job_policy": "ambient_non_killing",
        "job_scope": "Escapes tool kill-on-close job; retained ambient Windows job is allowed; no reboot/logoff survival promise",
        "version_response": version, "model_load_requests": 1,
        "base_manifest_after": file_binding(base_manifest), "runtime_binding": runtime_binding})
    write_new(output / "launch-receipt.json", record)
    return runtime_binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-runtime", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    result = start(args.private_runtime, args.models, args.output, args.tag)
    print(json.dumps({"status": "resident_candidate_not_a_completed_study", "binding": str(args.output / "runtime-binding.json"),
        "server_pid": result["server_pid"], "runner_pid": result["runner_pid"],
        "generation_attempts": 0, "load_requests": 1}))


if __name__ == "__main__":
    main()
