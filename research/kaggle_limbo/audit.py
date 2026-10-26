"""Offline native replay plus the separately declared Kaggle GPU condition.

These checks validate retained GPU/runtime evidence, not a fresh GPU execution
or independent authentication of the machine that generated the evidence.
Historical CPU/Ollama episodes cannot satisfy this condition by relabeling.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import hashlib
import math
import re

from research.expanded_limbo import audit as native_audit


SCHEMA = "conseqax-kaggle-gpu-offline-audit-v1"
CONDITION_SCHEMA = "conseqax-kaggle-gpu-condition-v1"
ARCHIVE_SHA256 = "1e8ad2d2a394efdd235bee74deec237badd95142ffba77588140ab2a9ecec227"
CONDITION_KEYS = {"runtime_version", "archive_sha256", "gpu_name", "compute_capability",
                  "driver_version", "python_version", "library_versions"}


def validate_condition(condition):
    native_audit.require(type(condition) is dict and set(condition) == CONDITION_KEYS,
                         "GPU condition inventory differs")
    native_audit.require(condition["runtime_version"] == "0.40.10"
                         and condition["archive_sha256"] == ARCHIVE_SHA256,
                         "GPU condition uses another runtime archive")
    for name in ("gpu_name", "compute_capability", "driver_version", "python_version"):
        native_audit.require(type(condition[name]) is str and bool(condition[name].strip()),
                             "GPU condition lacks " + name)
    versions = condition["library_versions"]
    native_audit.require(type(versions) is dict and bool(versions)
                         and all(type(key) is str and bool(key) and type(value) is str and bool(value)
                                 for key, value in versions.items()),
                         "GPU condition library versions are not pinned")
    # Canonical serialization refuses nonfinite and non-JSON diagnostic values.
    native_audit.canonical(condition)


def verify_gpu_load_proof(proof, runtime):
    """Check the bound runner's saved all-layer offload line, not a VRAM ratio."""
    expected = {"schema", "runner_pid", "runner_create_time", "model_blob_sha256",
                "requested_gpu_layers", "offloaded_layers", "total_layers",
                "log_line", "log_line_sha256"}
    native_audit.require(type(proof) is dict and set(proof) == expected
                         and proof["schema"] == "conseqax-gpu-layer-offload-v1",
                         "Missing or invalid GPU layer-offload proof")
    native_audit.require(type(proof["runner_pid"]) is int and proof["runner_pid"] > 0
                         and proof["runner_pid"] == runtime["runner_pid"],
                         "GPU layer proof belongs to another runner PID")
    born = proof["runner_create_time"]
    native_audit.require(type(born) in (float, int) and math.isfinite(born) and born > 0
                         and born == runtime["runner_create_time"],
                         "GPU layer proof belongs to another runner creation time")
    native_audit.require(proof["model_blob_sha256"] == runtime["model_blob_sha256"],
                         "GPU layer proof names different model weights")
    native_audit.require(type(proof["requested_gpu_layers"]) is int
                         and proof["requested_gpu_layers"] == 999,
                         "GPU layer request is not the declared full-offload request")
    count, total = proof["offloaded_layers"], proof["total_layers"]
    native_audit.require(type(count) is int and type(total) is int and count > 0 and count == total,
                         "GPU layer proof does not establish all layers were offloaded")
    line = proof["log_line"]
    native_audit.require(type(line) is str and "\n" not in line and "\r" not in line,
                         "GPU offload proof needs one exact retained log line")
    matches = re.findall(r"\boffloaded (\d+)/(\d+) layers to GPU\b", line)
    native_audit.require(len(matches) == 1 and tuple(map(int, matches[0])) == (count, total),
                         "GPU offload line and declared layer counts differ")
    native_audit.require(proof["log_line_sha256"] == hashlib.sha256(line.encode("utf-8")).hexdigest(),
                         "GPU offload log-line hash differs")
    return proof


def verify_gpu_residency(proof, runtime):
    """Require positive GPU memory for the exact model; host buffers are allowed."""
    profiles = [row for row in proof["resident_response"].get("models", [])
                if row.get("name") == runtime["model"] or row.get("model") == runtime["model"]]
    native_audit.require(len(profiles) == 1, "GPU proof has no unique bound resident model")
    profile = profiles[0]
    size, vram = profile.get("size"), profile.get("size_vram")
    native_audit.require(type(size) is int and size > 0 and type(vram) is int and vram > 0,
                         "GPU residency sizes must be positive integer byte counts")
    native_audit.require(profile.get("digest") == runtime["model_digest"]
                         and profile.get("context_length") == runtime["context_tokens"],
                         "GPU resident digest/context differs from episode lease")
    native_audit.same(proof["runtime_binding"], runtime, "GPU proof uses another episode runtime lease")
    return {"size": size, "size_vram": vram}


def audit_kaggle_episode(directory, slot, *, lineage, expected_limits, expected_model):
    """Replay one sealed episode and validate every dispatched GPU proof.

    The caller must supply the frozen checkpoint lineage and the exact scheduled
    slot/model/limits. Changing ephemeral PIDs or a device UUID between sessions
    does not change the static GPU class/driver/software condition.
    """
    directory = Path(directory)
    condition = lineage["condition"]
    validate_condition(condition)
    model_dir = directory / "model"
    config = native_audit.load(model_dir / "kaggle-gpu-config.json")
    expanded = native_audit.load(model_dir / "expanded-client-config.json")
    native_audit.require(type(config) is dict and set(config) == {
        "schema", "condition", "runtime", "gpu_devices", "cpu_fallback_allowed", "gpu_load_proof"}
        and config["schema"] == CONDITION_SCHEMA and config["cpu_fallback_allowed"] is False,
        "Missing or invalid separate GPU-condition config")
    native_audit.same(config["condition"], condition, "GPU condition differs from frozen checkpoint lineage")
    native_audit.same(config["runtime"], expanded["runtime"], "GPU/expanded runtime lease differs")
    devices = config["gpu_devices"]
    native_audit.require(type(devices) is list and bool(devices)
                         and all(type(device) is dict and bool(device) for device in devices),
                         "GPU diagnostic device inventory is missing")
    native_audit.canonical(devices)
    selected = devices[0]
    for diagnostic, frozen in (("name", "gpu_name"), ("compute_capability", "compute_capability"),
                               ("driver_version", "driver_version")):
        native_audit.require(selected.get(diagnostic) == condition[frozen],
                             "GPU diagnostic device differs from frozen condition: " + frozen)
    native_audit.require(type(selected.get("uuid")) is str and bool(selected["uuid"]),
                         "GPU diagnostic instance UUID is missing")
    runtime = config["runtime"]
    load_proof = verify_gpu_load_proof(config["gpu_load_proof"], runtime)
    for key in ("server_executable", "runner_executable", "model_blob"):
        path = runtime[key]
        native_audit.require(type(path) is str and PurePosixPath(path).is_absolute()
                             and "\\" not in path and not path.lower().endswith(".exe"),
                             "GPU runtime retains a Windows or relative path: " + key)
    for key in ("server_executable_sha256", "runner_executable_sha256", "model_blob_sha256"):
        native_audit.require(type(runtime[key]) is str and re.fullmatch(r"[0-9a-f]{64}", runtime[key]) is not None,
                             "GPU runtime lacks an exact binary/weight hash")
    result = native_audit.audit_episode(directory, slot, expected_limits=expected_limits,
                                         expected_model=expected_model)
    proofs = []
    for path in sorted(model_dir.glob("*-terminal.json")):
        terminal = native_audit.load(path)
        if terminal["dispatches"] == 1:
            context_path = path.with_name(path.name.removesuffix("-terminal.json") + "-context.json")
            proofs.append(verify_gpu_residency(native_audit.load(context_path), runtime))
    native_audit.require(len(proofs) == result["model_dispatches"], "A GPU dispatch lacks a residency proof")
    native_audit.verify_manifest(directory)
    return {**result, "schema": SCHEMA, "gpu_condition": condition,
        "gpu_load_proof": load_proof,
        "gpu_context_proofs": len(proofs), "gpu_residency_bytes": proofs,
        "scope": {**result["scope"], "separate_kaggle_gpu_condition": True,
            "saved_gpu_residency_proof_consistency": True,
            "saved_full_layer_offload_proof_consistency": True,
            "VRAM_percentage_used_as_full_offload_proxy": False,
            "fresh_gpu_inference_during_audit": False,
            "independently_authenticated_gpu_hardware": False,
            "pooled_with_historical_cpu_cohort": False}}
