"""Pinned Linux/CUDA Ollama setup, with exact GGUFs and no CPU fallback."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import http.client
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.error
import urllib.request

import psutil

from research.kaggle_limbo.bundle import binding
from research.limbo_agent.transport import RuntimeBinding

VERSION = "0.40.10"
ARCHIVE_SHA = "1e8ad2d2a394efdd235bee74deec237badd95142ffba77588140ab2a9ecec227"
ARCHIVE_BYTES = 1509264197
ARCHIVE_URL = "https://github.com/ollama/ollama/releases/download/v0.40.10/ollama-linux-amd64.tar.zst"
# This immutable GitHub asset ID declares the same pinned size and SHA256.
ARCHIVE_API_URL = "https://api.github.com/repos/ollama/ollama/releases/assets/669809428"
ARCHIVE_FALLBACK_URL = "https://ollama.com/download/ollama-linux-amd64.tar.zst?version=0.40.10"
BASE = "http://127.0.0.1:11436"
DOWNLOAD_ATTEMPTS = 5
RETRY_HTTP_STATUS = frozenset((408, 429, 500, 502, 503, 504))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _download_time_remaining():
    """Setup shares the original notebook window; retries cannot extend it."""
    started = os.environ.get("CONSEQAX_SESSION_START_MONOTONIC")
    if started is None:
        return 7 * 3600
    started = float(started)
    now = time.monotonic()
    require(math.isfinite(started) and 0 <= started <= now, "Invalid setup session timer")
    remaining = 7 * 3600 - (now - started)
    if remaining <= 0:
        raise RuntimeError("Setup session deadline reached. Preserve outputs and use a fresh session.")
    return remaining


def _download_part(url, partial, expected):
    """Append only a matching HTTP range; a server ignoring Range restarts safely."""
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "ConseqaX-frozen-benchmark", "Accept-Encoding": "identity",
               "Accept": "application/octet-stream"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    timeout = min(180, _download_time_remaining())
    # Always reopen the original source URL, not a possibly expired signed redirect.
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = response.status
        require(status in (200, 206), "Unexpected setup download response")
        require(response.headers.get("Content-Encoding", "identity").lower() == "identity",
                "Encoded download cannot be compared with pinned byte ranges")
        if status == 206:
            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
            require(match is not None, "Download has no valid Content-Range")
            start, end, total = map(int, match.groups())
            require(start == offset and start <= end < total == expected["bytes"],
                    "Download range differs from the pinned offset/size")
            body_bytes = end - start + 1
        else:
            # Some origins ignore Range. Never append their complete response.
            offset, body_bytes = 0, expected["bytes"]
        length = response.headers.get("Content-Length")
        require(length is None or (length.isdecimal() and int(length) == body_bytes),
                "Download Content-Length differs from pinned response size")
        mode = "ab" if offset else ("wb" if partial.exists() else "xb")
        received, reported = 0, time.monotonic()
        with partial.open(mode) as stream:
            def write_chunk(chunk):
                nonlocal received, reported
                require(received + len(chunk) <= body_bytes
                        and offset + received + len(chunk) <= expected["bytes"],
                        "Download exceeds the pinned size")
                stream.write(chunk)
                received += len(chunk)
                if time.monotonic() - reported >= 30:
                    print(f"  Downloaded {(offset + received) / 1024**2:.0f} / "
                          f"{expected['bytes'] / 1024**2:.0f} MiB", flush=True)
                    reported = time.monotonic()

            try:
                while True:
                    _download_time_remaining()
                    try:
                        chunk = response.read(1024**2)
                    except http.client.IncompleteRead as exc:
                        write_chunk(exc.partial)
                        raise
                    if not chunk:
                        break
                    write_chunk(chunk)
            finally:
                stream.flush()
                os.fsync(stream.fileno())
        if received != body_bytes or offset + received != expected["bytes"]:
            raise http.client.IncompleteRead(b"", expected["bytes"] - offset - received)


def download(url, destination, expected, *, fallback_urls=()):
    """Retry setup-only GETs, retaining ranges; never retry a measured model call.

    Only a complete file with the exact frozen SHA256 and size is installed.
    No response body, signed redirect URL or HTTP error object is logged.
    """
    require(set(expected) == {"sha256", "bytes"}
            and isinstance(expected["sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]) is not None
            and type(expected["bytes"]) is int and expected["bytes"] > 0,
            "A pinned SHA256 and positive byte length are required")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(not destination.is_symlink(), "Refuse a linked download destination")
    if destination.exists():
        require(binding(destination) == expected, "Cached download bytes changed")
        return
    partial = destination.with_name(destination.name + ".download")
    require(not partial.is_symlink(), "Refuse a linked partial download")
    sources = (url, *fallback_urls)
    for attempt in range(DOWNLOAD_ATTEMPTS):
        _download_time_remaining()
        count = partial.stat().st_size if partial.exists() else 0
        require(count <= expected["bytes"], "Partial download exceeds the pinned size")
        if count != expected["bytes"]:
            print(f"Setup download {destination.name}: attempt {attempt + 1}/{DOWNLOAD_ATTEMPTS}, "
                  f"{count / 1024**2:.0f}/{expected['bytes'] / 1024**2:.0f} MiB cached", flush=True)
            failure = None
            try:
                _download_part(sources[attempt % len(sources)], partial, expected)
            except urllib.error.HTTPError as exc:
                retryable = exc.code in RETRY_HTTP_STATUS
                failure = f"HTTP {exc.code}"
                exc.close()
                if not retryable:
                    raise RuntimeError(f"Setup download stopped ({failure}); no model episode was retried.") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead) as exc:
                failure = type(exc).__name__
            if failure is not None:
                if attempt + 1 == DOWNLOAD_ATTEMPTS:
                    raise RuntimeError(f"Setup download could not finish after {DOWNLOAD_ATTEMPTS} attempts "
                        f"({failure}). Partial bytes are retained. Rerun only the setup cell within "
                        "this session's budget, or use a fresh session. No benchmark episode was retried.") from None
                delay = 2 ** (attempt + 1)
                print(f"  Temporary setup download failure ({failure}); retrying in {delay}s.", flush=True)
                if _download_time_remaining() <= delay:
                    raise RuntimeError("Insufficient setup time to retry. Use a fresh session.") from None
                time.sleep(delay)
                continue
        require(binding(partial) == expected, "Download hash/length differs; unverified bytes were not installed")
        partial.rename(destination)
        print(f"Verified setup download {destination.name}", flush=True)
        return


def api(path, payload=None, timeout=300):
    data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
    request = urllib.request.Request(BASE + path, data=data,
        headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def gpu_inventory():
    command = ["nvidia-smi", "--query-gpu=index,uuid,name,compute_cap,driver_version,memory.total",
               "--format=csv,noheader,nounits"]
    try:
        raw = subprocess.run(command, check=True, text=True, capture_output=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Enable a Kaggle NVIDIA GPU; CPU fallback is disabled") from exc
    devices = []
    for line in raw.strip().splitlines():
        values = [value.strip() for value in line.split(",")]
        require(len(values) == 6, "Unrecognized nvidia-smi GPU inventory")
        devices.append(dict(zip(("index", "uuid", "name", "compute_capability", "driver_version", "memory_mib"), values)))
    require(bool(devices), "No CUDA GPU is visible")
    return devices


def condition(devices):
    selected = devices[0]
    return {"runtime_version": VERSION, "archive_sha256": ARCHIVE_SHA,
        "gpu_name": selected["name"], "compute_capability": selected["compute_capability"],
        "driver_version": selected["driver_version"], "python_version": platform.python_version(),
        "library_versions": {name: importlib.metadata.version(name)
                             for name in ("psutil", "zstandard", "consequa-x")}}


def install_runtime(directory):
    require(platform.system() == "Linux" and platform.machine() in ("x86_64", "AMD64"),
            "This notebook requires Kaggle Linux x86_64 with an NVIDIA GPU")
    directory = Path(directory).resolve()
    marker = directory / "installed.json"
    if marker.exists():
        record = load(marker)
        require(record["archive_sha256"] == ARCHIVE_SHA
                and binding(directory / "bin/ollama") == record["ollama"], "Pinned runtime changed")
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "ollama-linux-amd64.tar.zst"
    download(ARCHIVE_URL, archive, {"sha256": ARCHIVE_SHA, "bytes": ARCHIVE_BYTES},
             fallback_urls=(ARCHIVE_API_URL, ARCHIVE_FALLBACK_URL))
    import zstandard
    with archive.open("rb") as stream, zstandard.ZstdDecompressor().stream_reader(stream) as decoded:
        with tarfile.open(fileobj=decoded, mode="r|") as source:
            for member in source:
                target = (directory / member.name).resolve()
                require(target.is_relative_to(directory) and not member.isdev(), "Unsafe runtime archive member")
                source.extract(member, directory, filter="data")
    require((directory / "bin/ollama").is_file(), "Pinned Linux archive has no Ollama binary")
    save(marker, {"archive_sha256": ARCHIVE_SHA, "archive_bytes": ARCHIVE_BYTES,
                  "ollama": binding(directory / "bin/ollama")})
    return directory


def start_server(runtime_dir, models_dir, devices):
    runtime_dir, models_dir = Path(runtime_dir).resolve(), Path(models_dir).resolve()
    state = runtime_dir / "server.json"
    if state.exists():
        record = load(state)
        process = psutil.Process(record["pid"])
        require(abs(process.create_time() - record["create_time"]) < .001
                and Path(process.exe()).resolve() == Path(record["executable"]), "Research listener identity changed")
        return record
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 11436))
    environment = dict(os.environ)
    for key in tuple(environment):
        if key.upper().endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN")):
            environment.pop(key)
    environment.update(OLLAMA_HOST="127.0.0.1:11436", OLLAMA_MODELS=str(models_dir),
        OLLAMA_NO_CLOUD="1", OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="1",
        OLLAMA_CONTEXT_LENGTH="8192", OLLAMA_KV_CACHE_TYPE="q8_0", OLLAMA_FLASH_ATTENTION="1",
        OLLAMA_KEEP_ALIVE="-1", OLLAMA_NOPRUNE="1", OLLAMA_DEBUG="1", CUDA_VISIBLE_DEVICES=devices[0]["uuid"],
        LD_LIBRARY_PATH=str(runtime_dir / "lib/ollama") + os.pathsep + environment.get("LD_LIBRARY_PATH", ""))
    models_dir.mkdir(parents=True, exist_ok=True)
    with (runtime_dir / "server.stdout.log").open("ab") as out, (runtime_dir / "server.stderr.log").open("ab") as err:
        child = subprocess.Popen([str(runtime_dir / "bin/ollama"), "serve"], env=environment,
            stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
    process = psutil.Process(child.pid)
    record = {"pid": process.pid, "create_time": process.create_time(),
              "executable": process.exe(), "models_dir": str(models_dir), "runtime_dir": str(runtime_dir)}
    save(state, record)
    for _ in range(60):
        try:
            require(api("/api/version", timeout=2)["version"] == VERSION, "Unexpected Ollama version")
            return record
        except (OSError, urllib.error.URLError):
            require(child.poll() is None, "GPU runtime exited during startup")
            time.sleep(.5)
    raise RuntimeError("Pinned GPU runtime did not become ready")


def install_models(study_dir, models_dir, protocol):
    """Install exact saved OCI metadata and hash-addressed model blobs, no latest tags."""
    study_dir, models_dir = Path(study_dir), Path(models_dir)
    catalog = load(study_dir / "assets/model-catalog.json")
    for model in protocol["models"]:
        item = catalog[model["id"]]
        model_root = study_dir / "assets/models" / item["family"]
        image = load(model_root / "registry-manifest.json")
        for layer in [image["config"], *image["layers"]]:
            digest = layer["digest"].removeprefix("sha256:")
            target = models_dir / "blobs" / ("sha256-" + digest)
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = {"sha256": digest, "bytes": layer["size"]}
            bundled = model_root / ("sha256-" + digest)
            if bundled.exists():
                require(binding(bundled) == expected, "Bundled model metadata differs")
                if not target.exists():
                    shutil.copyfile(bundled, target)
                require(binding(target) == expected, "Installed model metadata differs")
            else:
                url = "https://registry.ollama.ai/v2/library/" + item["registry_name"] + "/blobs/sha256:" + digest
                print("Fetching pinned", item["family"], "weights (cached when available)", flush=True)
                download(url, target, expected)
        name, tag = model["id"].split(":", 1)
        manifest = models_dir / "manifests/registry.ollama.ai/library" / name / tag
        manifest.parent.mkdir(parents=True, exist_ok=True)
        raw = (model_root / "registry-manifest.json").read_bytes()
        if manifest.exists():
            require(manifest.read_bytes() == raw, "Pinned model manifest changed")
        else:
            manifest.write_bytes(raw)


def unload():
    for model in api("/api/ps").get("models", []):
        api("/api/generate", {"model": model["name"], "prompt": "", "stream": False,
                              "keep_alive": 0, "options": {"num_predict": 0}})
    for _ in range(100):
        if not api("/api/ps").get("models"):
            return
        time.sleep(.2)
    raise RuntimeError("Previous model did not unload")


def load_model(server, model, lease_dir):
    unload()
    lease_dir = Path(lease_dir)
    lease_dir.mkdir(parents=True, exist_ok=False)
    log_path = Path(server["runtime_dir"]) / "server.stderr.log"
    log_offset = log_path.stat().st_size
    # Load only; all measured invocations still use the native chat serializer.
    loaded = api("/api/generate", {"model": model["id"], "prompt": "", "stream": False,
        "keep_alive": -1, "options": {"num_ctx": 8192, "num_predict": 0, "num_gpu": 999}}, timeout=300)
    save(lease_dir / "load-only.json", loaded)
    require(loaded.get("done_reason") == "load" and not loaded.get("response"), "Load-only request generated text")
    resident = [m for m in api("/api/ps")["models"] if m["name"] == model["id"]]
    require(len(resident) == 1 and type(resident[0].get("size")) is int and resident[0]["size"] > 0
            and type(resident[0].get("size_vram")) is int and resident[0]["size_vram"] > 0,
            "Positive GPU residency required; CPU-only fallback is refused")
    process = psutil.Process(server["pid"])
    runners = [p for p in process.children(recursive=True)
               if Path(p.exe()).name in ("ollama", "llama-server")
               and "--model" in p.cmdline()]
    require(len(runners) == 1, "Expected one bound GPU model runner")
    runner, blob = runners[0], str(Path(server["models_dir"]) / "blobs" / ("sha256-" + model["weights"]["sha256"]))
    args = runner.cmdline()
    require(args[args.index("--model") + 1] == blob, "GPU runner loaded different model bytes")
    require("-ngl" in args and args[args.index("-ngl") + 1] == "999", "All model layers must be requested on GPU")
    with log_path.open("rb") as stream:
        stream.seek(log_offset)
        segment = stream.read().decode("utf-8", errors="replace")
    matches = [(line, re.search(r"offloaded (\d+)/(\d+) layers to GPU", line))
               for line in segment.splitlines() if re.search(r"offloaded (\d+)/(\d+) layers to GPU", line)]
    require(bool(matches), "GPU load lacks an explicit layer-offload report; no measured execution allowed")
    line, matched = matches[-1]
    offloaded, total = map(int, matched.groups())
    require(offloaded == total and total > 0, "Some model layers remained on CPU")
    proof = {"schema": "conseqax-gpu-layer-offload-v1", "runner_pid": runner.pid,
        "runner_create_time": runner.create_time(), "model_blob_sha256": model["weights"]["sha256"],
        "requested_gpu_layers": 999, "offloaded_layers": offloaded, "total_layers": total,
        "log_line": line, "log_line_sha256": hashlib.sha256(line.encode()).hexdigest()}
    save(lease_dir / "gpu-load-proof.json", proof)
    binding_value = RuntimeBinding(api_base=BASE + "/v1", model=model["id"],
        model_digest=resident[0]["digest"], model_blob=blob, model_blob_sha256=model["weights"]["sha256"],
        server_pid=process.pid, server_executable=process.exe(),
        server_executable_sha256=binding(process.exe())["sha256"], server_create_time=process.create_time(),
        runner_pid=runner.pid, runner_executable=runner.exe(), runner_executable_sha256=binding(runner.exe())["sha256"],
        runner_create_time=runner.create_time(), runner_port=int(args[args.index("--port") + 1]),
        context_tokens=8192, parallel_slots=1)
    save(lease_dir / "runtime-binding.json", asdict(binding_value))
    return binding_value
