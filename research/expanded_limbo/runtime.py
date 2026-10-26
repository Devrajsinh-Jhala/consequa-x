"""Isolated serial model setup for the new, separately declared study.

Only this setup module can download a declared public model or create research
aliases. Episode clients remain offline/loopback-only. Normal Ollama services
and their manifests are never changed. PID plus birth time and binary hashes
bind every later load/unload/stop operation.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import socket
import time
import urllib.request

import psutil

from research.limbo_agent.protocol import file_binding, utc, write_new
from research.limbo_agent.harness import manifest
from research.limbo_agent.transport import RuntimeBinding
from research.native_agent.transport import read_gguf_metadata
from scripts.launch_expanded_research import launch
from scripts.start_durable_limbo_runtime import verify_private

SERVER = "http://127.0.0.1:11436"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def content_binding(content):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def api(path, payload=None, *, timeout=120):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
    request = urllib.request.Request(SERVER + path, data=data,
        headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def bound_server(path):
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = record["server"]
    process = psutil.Process(identity["pid"])
    require(abs(process.create_time() - identity["create_time"]) < .001,
            "Research listener PID birth changed")
    require(Path(process.exe()).resolve() == Path(identity["executable"]).resolve(),
            "Research listener executable changed")
    require(file_binding(process.exe()) == identity["executable_binding"],
            "Research listener binary bytes changed")
    require(api("/api/version").get("version") == record["version"],
            "Research listener runtime version changed")
    return record, process


def start_server(private_runtime, models, output):
    private_runtime, models = Path(private_runtime).resolve(), Path(models).resolve()
    output = Path(output).resolve()
    require(models.is_dir() and not output.exists(), "Existing models and new setup output required")
    private = verify_private(private_runtime)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 11436))
    output.mkdir(parents=True, exist_ok=False)
    environment = {"OLLAMA_HOST": "127.0.0.1:11436", "OLLAMA_MODELS": str(models),
        "OLLAMA_NO_CLOUD": "1", "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_CONTEXT_LENGTH": "8192", "OLLAMA_KEEP_ALIVE": "-1",
        "OLLAMA_NOPRUNE": "1", "OLLAMA_DEBUG": "1"}
    launched = launch([str(private_runtime / "ollama.exe"), "serve"], private_runtime,
        output / "server-launch", environment,
        [private_runtime / "private-runtime-manifest.json", private_runtime / "ollama.exe",
         private_runtime / "lib/ollama/llama-server.exe"],
        mechanism="wmi_two_stage", job_policy="ambient_non_killing")
    process = psutil.Process(launched["target"]["pid"])
    for _ in range(60):
        try:
            version = api("/api/version", timeout=2)
            break
        except Exception:
            require(process.is_running(), "New listener exited; no alternate automatic launch")
            time.sleep(.5)
    else:
        raise RuntimeError("New isolated research listener did not become ready")
    require(version["version"] == private["declared_version"], "Private runtime version differs")
    receipt = {"schema": "conseqax-expanded-runtime-server-v1", "started_utc": utc(),
        "version": version["version"], "models_directory": str(models),
        "private_runtime": str(private_runtime), "process_only_environment": environment,
        "server": {"pid": process.pid, "create_time": process.create_time(),
                   "executable": process.exe(), "executable_binding": file_binding(process.exe())},
        "normal_service_modified": False, "generation_attempts": 0,
        "durability": "Detached from tool lifetime; does not survive reboot/logoff"}
    write_new(output / "server.json", receipt)
    return receipt


def acquire_model(server_path, tag, output, *, allow_download=False):
    record, _ = bound_server(server_path)
    output = Path(output).resolve()
    require(not output.exists(), "Refuse replacing a model acquisition record")
    require(tag in {"qwen3:4b-instruct-2507-q4_K_M", "llama3.2:3b-instruct-q4_K_M",
                    "granite3.3:2b"}, "Only the three declared public research checkpoints are allowed")
    output.mkdir(parents=True, exist_ok=False)
    tags = api("/api/tags")["models"]
    present = [item for item in tags if item["name"] == tag or item["model"] == tag]
    downloaded = False
    if not present:
        require(allow_download, "Declared model absent; explicit setup download required")
        result = api("/api/pull", {"model": tag, "stream": False}, timeout=10800)
        write_new(output / "pull-result.json", result)
        require(result.get("status") == "success", "Model download did not complete")
        downloaded = True
        present = [item for item in api("/api/tags")["models"]
                   if item["name"] == tag or item["model"] == tag]
    require(len(present) == 1, "Exact model tag is not uniquely present")
    show = api("/api/show", {"model": tag, "verbose": True})
    write_new(output / "show.json", show)
    store = Path(record["models_directory"])
    # Both historical Ollama layouts are supported as read-only provenance.
    name, model_tag = tag.split(":", 1)
    candidates = [store / "manifests-v2/ollama.com/library" / name / model_tag,
                  store / "manifests/registry.ollama.ai/library" / name / model_tag]
    existing = [path for path in candidates if path.is_file()]
    require(bool(existing), "Downloaded model manifest is unavailable")
    image = json.loads(existing[0].read_text(encoding="utf-8"))
    layers = [layer for layer in image["layers"]
              if layer["mediaType"] == "application/vnd.ollama.image.model"]
    require(len(layers) == 1, "One text-model GGUF payload is required")
    blob = store / "blobs" / layers[0]["digest"].replace(":", "-")
    weights = file_binding(blob)
    require("sha256:" + weights["sha256"] == layers[0]["digest"], "Model GGUF digest mismatch")
    metadata = read_gguf_metadata(blob)
    tokenizer = {key: value for key, value in metadata.items() if key.startswith("tokenizer.ggml.")}
    result = {"schema": "conseqax-expanded-model-acquisition-v1", "utc": utc(),
        "tag": tag, "downloaded": downloaded, "generation_attempts": 0,
        "weights_path": str(blob), "weights": weights, "model_digest": present[0]["digest"],
        "tokenizer": content_binding(canonical(tokenizer)),
        "chat_template": content_binding(show["template"]),
        "gguf_chat_template": content_binding(metadata["tokenizer.chat_template"]),
        "license": content_binding(show.get("license", "")),
        "details": show.get("details"), "capabilities": show.get("capabilities"),
        "model_show": file_binding(output / "show.json"),
        "manifest": {"path": str(existing[0]), **file_binding(existing[0])},
        "normal_service_modified": False}
    require("tools" in (show.get("capabilities") or []), "Checkpoint lacks native tool support")
    write_new(output / "acquisition.json", result)
    write_new(output / "manifest.json", manifest(output))
    return result


def load_model(server_path, acquisition_path, alias, output):
    record, server = bound_server(server_path)
    acquired = json.loads(Path(acquisition_path).read_text(encoding="utf-8"))
    output = Path(output).resolve()
    require(not output.exists() and alias.startswith("conseqax-expanded-"),
            "New owned alias/load directory required")
    require(file_binding(acquired["weights_path"]) == acquired["weights"], "Model bytes changed")
    require(not api("/api/ps")["models"], "Unload the preceding research model before switching")
    available = psutil.virtual_memory().available
    metadata = read_gguf_metadata(acquired["weights_path"])
    architecture = metadata["general.architecture"]
    heads = metadata[architecture + ".attention.head_count"]
    key_heads = metadata.get(architecture + ".attention.head_count_kv", heads)
    key_length = metadata.get(architecture + ".attention.key_length",
                              metadata[architecture + ".embedding_length"] // heads)
    value_length = metadata.get(architecture + ".attention.value_length", key_length)
    # q8_0 stores 32 values plus a 2-byte scale per block. Allow 10% alignment
    # overhead; retain a full GiB for compute buffers and other system work.
    kv_bytes = int((key_length + value_length) * key_heads
        * metadata[architecture + ".block_count"] * 8192 * 34 / 32 * 1.1)
    required = acquired["weights"]["bytes"] + kv_bytes + 1024**3
    require(available >= required, "Insufficient cold memory for this model plus context/reserve")
    output.mkdir(parents=True, exist_ok=False)
    require(not any(item["name"] == alias for item in api("/api/tags")["models"]),
            "Refuse replacing a prior model research alias")
    created = api("/api/create", {"model": alias, "from": acquired["tag"],
        "parameters": {"num_ctx": 8192, "num_predict": 512, "temperature": .2}, "stream": False})
    write_new(output / "alias-create.json", created)
    loaded = api("/api/generate", {"model": alias, "prompt": "", "stream": False,
        "keep_alive": -1, "options": {"num_ctx": 8192, "num_predict": 0}}, timeout=300)
    write_new(output / "load-only.json", loaded)
    require(loaded.get("done_reason") == "load" and not loaded.get("response"),
            "Expected an empty load-only response")
    resident = [item for item in api("/api/ps")["models"] if item["name"] == alias]
    require(len(resident) == 1 and resident[0]["context_length"] == 8192,
            "Resident context mismatch")
    candidates = [process for process in server.children(recursive=True)
                  if process.name().lower() == "llama-server.exe"]
    require(len(candidates) == 1, "Expected exactly one private native model runner")
    runner = candidates[0]
    require(Path(runner.exe()).resolve()
            == (Path(record["private_runtime"]) / "lib/ollama/llama-server.exe").resolve(),
            "Runner executable is outside the bound private runtime")
    args = runner.cmdline()
    require(str(Path(acquired["weights_path"])) in args, "Loaded GGUF path changed")
    binding = RuntimeBinding(api_base=SERVER + "/v1", model=alias,
        model_digest=resident[0]["digest"], model_blob=acquired["weights_path"],
        model_blob_sha256=acquired["weights"]["sha256"], server_pid=server.pid,
        server_executable=server.exe(), server_executable_sha256=file_binding(server.exe())["sha256"],
        server_create_time=server.create_time(), runner_pid=runner.pid,
        runner_executable=runner.exe(), runner_executable_sha256=file_binding(runner.exe())["sha256"],
        runner_create_time=runner.create_time(), runner_port=int(args[args.index("--port") + 1]),
        context_tokens=8192, parallel_slots=1)
    write_new(output / "runtime-binding.json", asdict(binding))
    write_new(output / "load-receipt.json", {"schema": "conseqax-expanded-model-load-v1", "utc": utc(),
        "runtime": asdict(binding), "acquisition": {"path": str(Path(acquisition_path).resolve()),
                                                    **file_binding(acquisition_path)},
        "available_memory_bytes": available, "required_memory_bytes": required,
        "expected_q8_kv_bytes": kv_bytes,
        "memory_gate_scope": "GGUF weights + q8 KV estimate with 10% allowance + 1GiB compute/system reserve; not a guarantee of later free RAM",
        "generation_attempts": 0, "load_only_requests": 1, "normal_service_modified": False})
    return asdict(binding)


def unload_model(server_path, binding_path, output):
    bound_server(server_path)
    binding = RuntimeBinding.from_dict(json.loads(Path(binding_path).read_text(encoding="utf-8")))
    require(not Path(output).exists(), "Refuse replacing unload receipt")
    result = api("/api/generate", {"model": binding.model, "prompt": "", "stream": False,
        "keep_alive": 0, "options": {"num_predict": 0}}, timeout=180)
    require(not result.get("response"), "Unload must not generate text")
    for _ in range(100):
        if not api("/api/ps")["models"]:
            break
        time.sleep(.2)
    require(not api("/api/ps")["models"], "Research model remains resident")
    write_new(output, {"utc": utc(), "model": binding.model, "result": result,
                       "generation_attempts": 0, "normal_service_modified": False})
