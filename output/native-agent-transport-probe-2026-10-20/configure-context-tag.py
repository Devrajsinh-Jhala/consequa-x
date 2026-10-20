"""Create an isolated local context-profile tag from installed weights only.

No completion/generation endpoint is permitted. The original tag and global
service configuration are not changed. A preexisting research tag is a refusal.
"""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import socket
import sys

OUT = Path(__file__).resolve().parent
BASE = "qwen3:4b-instruct-2507-q4_K_M"
EXPECTED_DIGEST = "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
TAG = "conseqax-native-probe-20261020:ctx16k"
CTX = 16384


class MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memory():
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise RuntimeError("Windows memory status unavailable")
    return {"total_physical_bytes": status.ullTotalPhys,
            "available_physical_bytes": status.ullAvailPhys,
            "memory_load_percent": status.dwMemoryLoad}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


record = {
    "scope": "separate reversible local context-profile creation; no generation",
    "base_model": BASE, "expected_base_digest": EXPECTED_DIGEST,
    "research_tag": TAG, "requested_num_ctx": CTX,
    "started_utc": now(), "memory_before": memory(),
    "actual_generation_attempts": 0, "model_downloads_requested": 0,
    "global_service_changes": False, "original_tag_changes_requested": False,
    "network_policy": "Python audit allowlist for 127.0.0.1:11434; no proxy/client credentials",
    "network_refusals": [], "calls": [], "status": "incomplete",
}


def audit(event, args):
    if event == "socket.connect":
        address = args[1]
        if not (isinstance(address, tuple) and address[0] == "127.0.0.1" and address[1] == 11434):
            record["network_refusals"].append({"event": event, "address": str(address)})
            raise RuntimeError("Only existing loopback Ollama listener is permitted")
    elif event == "socket.getaddrinfo":
        if args[0] != "127.0.0.1" or int(args[1]) != 11434:
            record["network_refusals"].append({"event": event, "host": str(args[0]), "port": str(args[1])})
            raise RuntimeError("Only numeric loopback Ollama address may resolve")
    elif event in {"socket.sendto", "subprocess.Popen"}:
        raise RuntimeError("Datagrams and subprocesses are forbidden")


sys.addaudithook(audit)


def call(method, path, payload=None):
    allowed = {("GET", "/api/version"), ("GET", "/api/tags"), ("GET", "/api/ps"),
               ("POST", "/api/show"), ("POST", "/api/create")}
    if (method, path) not in allowed:
        raise RuntimeError("Endpoint not allowlisted; generation forbidden")
    if path == "/api/create" and payload != {
            "model": TAG, "from": BASE, "parameters": {"num_ctx": CTX}, "stream": False}:
        raise RuntimeError("Research-tag create payload differs from authorization")
    if path == "/api/show" and payload not in ({"model": BASE}, {"model": TAG}):
        raise RuntimeError("Show request not authorized")
    entry = {"started_utc": now(), "method": method, "path": path, "request": payload}
    record["calls"].append(entry)
    body = json.dumps(payload).encode() if payload is not None else None
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=60)
    try:
        connection.request(method, path, body=body,
                           headers={"Content-Type": "application/json"} if body else {})
        response = connection.getresponse()
        raw = response.read(16 * 1024 * 1024)
        entry.update(status=response.status, response_sha256=hashlib.sha256(raw).hexdigest(),
                     response=json.loads(raw), finished_utc=now())
        if response.status != 200:
            raise RuntimeError(f"Ollama metadata/configuration request failed: {response.status}")
        return entry["response"]
    finally:
        connection.close()


claim = OUT / "context-tag-started.json"
with claim.open("x", encoding="utf-8") as stream:
    json.dump({"started_utc": record["started_utc"], "research_tag": TAG,
               "base_model": BASE, "requested_num_ctx": CTX}, stream, indent=2)
    stream.write("\n")
code = 0
try:
    record["server_version"] = call("GET", "/api/version")
    tags_before = call("GET", "/api/tags")
    models = tags_before["models"]
    if any(m.get("name") == TAG or m.get("model") == TAG for m in models):
        raise RuntimeError("Research tag already exists; refusing overwrite")
    base_before = next(m for m in models if m.get("name") == BASE)
    if base_before["digest"] != EXPECTED_DIGEST:
        raise RuntimeError("Original installed model digest differs")
    show_before = call("POST", "/api/show", {"model": BASE})
    record["loaded_before"] = call("GET", "/api/ps")
    record["configuration_response"] = call("POST", "/api/create", {
        "model": TAG, "from": BASE, "parameters": {"num_ctx": CTX}, "stream": False})
    show_new = call("POST", "/api/show", {"model": TAG})
    show_after = call("POST", "/api/show", {"model": BASE})
    tags_after = call("GET", "/api/tags")
    base_after = next(m for m in tags_after["models"] if m.get("name") == BASE)
    new_tag = next(m for m in tags_after["models"] if m.get("name") == TAG)
    record["loaded_after"] = call("GET", "/api/ps")
    from_before = [line for line in show_before["modelfile"].splitlines() if line.startswith("FROM ")]
    from_new = [line for line in show_new["modelfile"].splitlines() if line.startswith("FROM ")]
    new_parameters = dict(line.split(maxsplit=1) for line in show_new["parameters"].splitlines())
    checks = {
        "original_tag_digest_unchanged": base_before["digest"] == base_after["digest"] == EXPECTED_DIGEST,
        "original_show_unchanged": digest(show_before) == digest(show_after),
        "same_weight_blob_in_generated_modelfile": bool(from_before) and from_before == from_new,
        "model_architecture_metadata_unchanged": show_before["model_info"] == show_new["model_info"],
        "explicit_num_ctx_verified": new_parameters.get("num_ctx") == str(CTX),
        "new_tag_not_loaded_by_creation": not any(m.get("name") == TAG or m.get("model") == TAG
                                                for m in record["loaded_after"]["models"]),
    }
    record["checks"] = checks
    record["new_tag_digest"] = new_tag["digest"]
    info = show_before["model_info"]
    kv_bytes = (int(info["qwen3.block_count"]) * int(info["qwen3.attention.head_count_kv"])
                * int(info["qwen3.attention.key_length"]) * 2 * 2 * CTX)
    required = base_before["size"] + kv_bytes + 1024 ** 3
    record["memory_after"] = memory()
    record["conservative_memory_gate"] = {
        "weights_size_bytes": base_before["size"], "context_tokens": CTX,
        "kv_estimate_bytes_if_fp16": kv_bytes,
        "scratch_and_os_headroom_bytes": 1024 ** 3,
        "required_available_bytes": required,
        "available_bytes": record["memory_after"]["available_physical_bytes"],
        "passed": record["memory_after"]["available_physical_bytes"] >= required,
        "interpretation": "A conservative pre-load gate, not a measured allocation or proof of OOM. Cache quantization was not altered or inferred.",
    }
    record["status"] = "configured_without_generation" if all(checks.values()) else "configuration_verification_failed"
    if not all(checks.values()):
        code = 1
except Exception as error:
    record["status"] = "failed"
    record["error_type"] = type(error).__name__
    record["error"] = str(error)
    code = 1
finally:
    record["finished_utc"] = now()
    (OUT / "context-tag-config.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: record.get(k) for k in ["status", "checks", "new_tag_digest", "conservative_memory_gate", "actual_generation_attempts", "error"]}))
sys.exit(code)
