"""Prospective native-pilot identities and deterministic, metadata-only schedule.

No model, native agent, controller, or task scenario is imported here. Runtime
bindings are explicit; manifests describe their coverage rather than implying
an operating-system sandbox or a fully reproducible floating-point execution.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import zipfile


ARMS = ("B", "C", "R", "G")
EXCLUDED = {"19", "20"}
RESEARCH_API_BASE = "http://127.0.0.1:11436/v1"
MODEL_DIGEST = "7f091551b95c30f4ff31a067faa273f56a3563b556cfd3d9f80d47c9b5d20ffc"
WHEEL_SHA256 = "c86c02aacac53d51bd4335238c4f44b96098db9af354662b23722fab60ed3b98"
SOURCE_PATHS = (
    "research/native_agent/__init__.py", "research/native_agent/controller.py",
    "research/native_agent/transport.py", "research/native_agent/harness.py",
    "research/native_agent/audit.py", "research/native_agent/protocol.py",
    "scripts/run_native_external_benchmark.py",
    "scripts/audit_native_external_benchmark.py",
)


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def select_metadata(tasks):
    """Inspect only ID, required-basis names and communication emptiness."""
    rows = []
    for task in tasks:
        criteria = task["evaluation_criteria"]
        basis = criteria["reward_basis"]
        if set(basis) != {"DB", "COMMUNICATE"}:
            raise ValueError("Unexpected required task reward/judge component")
        task_id = str(task["id"])
        communication = criteria.get("communicate_info")
        if communication is not None and (type(communication) is not list
                                          or not all(type(item) is str for item in communication)):
            raise ValueError("Invalid communication criterion metadata")
        rows.append({"task_id": task_id, "required_basis": sorted(basis),
                     "nonempty_communication": bool(communication),
                     "excluded_development": task_id in EXCLUDED,
                     "selection_hash": hashlib.sha256(
                         f"consequa-native-pilot-v1|airline|{task_id}".encode()).hexdigest()})
    if len({row["task_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate native task ID")
    selected = []
    for stratum in (True, False):
        eligible = sorted((row for row in rows if not row["excluded_development"]
                           and row["nonempty_communication"] is stratum),
                          key=lambda row: row["selection_hash"])
        if len(eligible) < 6:
            raise ValueError("Pilot stratum has fewer than six eligible IDs")
        selected.extend(eligible[:6])
    return {"all_metadata": sorted(rows, key=lambda row: row["task_id"]),
            "selected_metadata": selected}


def make_schedule(metadata, seed=1701):
    selected = metadata["selected_metadata"]
    if (len(selected) != 12 or len({row["task_id"] for row in selected}) != 12
            or any(sum(row["nonempty_communication"] is stratum for row in selected) != 6
                   for stratum in (True, False))):
        raise ValueError("Pilot schedule requires12unique selected IDs and six per stratum")
    ordered = sorted(metadata["selected_metadata"], key=lambda row: row["selection_hash"])
    schedule = []
    for rank, row in enumerate(ordered):
        rotation = rank % len(ARMS)
        for position, arm in enumerate(ARMS[rotation:] + ARMS[:rotation]):
            schedule.append({"slot": len(schedule), "task_rank": rank, "position": position,
                             "task_id": row["task_id"], "arm": arm, "seed": seed,
                             "episode_id": f"native-airline-{row['task_id']}-{arm}-s{seed}",
                             "nonempty_communication": row["nonempty_communication"]})
    return schedule


def source_binding(root):
    root = Path(root).resolve()
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    dirty = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--",
                                     *SOURCE_PATHS]).decode().strip()
    if dirty:
        raise ValueError("Execution source must be committed and clean before freeze")
    files = {name: {"sha256": sha_file(root / name), "bytes": (root / name).stat().st_size}
             for name in SOURCE_PATHS}
    for name in SOURCE_PATHS:
        expected = subprocess.check_output(["git", "-C", str(root), "show", f"{commit}:{name}"])
        actual = (root / name).read_bytes()
        if not (actual == expected or (b"\r\n" not in expected
                                     and actual == expected.replace(b"\n", b"\r\n"))):
            raise ValueError(f"Execution source differs from committed bytes: {name}")
        files[name]["git_blob_sha256"] = hashlib.sha256(expected).hexdigest()
    return {"commit": commit, "root": str(root), "files": files}


def runtime_binding(wheel):
    wheel = Path(wheel).resolve()
    if sha_file(wheel) != WHEEL_SHA256:
        raise ValueError("Framework wheel identity differs")
    distribution = importlib.metadata.distribution("consequa-x")
    if distribution.version != "2.1.1":
        raise ValueError("Scientific runtime must use framework 2.1.1")
    payload = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("consequa_x/") and not name.endswith("/"):
                expected = archive.read(name)
                actual_path = Path(distribution.locate_file(name)).resolve()
                actual = actual_path.read_bytes()
                if actual != expected:
                    raise ValueError(f"Installed framework differs from wheel: {name}")
                payload[name] = {"sha256": hashlib.sha256(actual).hexdigest(), "bytes": len(actual)}
    if not payload or "consequa_x/__init__.py" not in payload:
        raise ValueError("Incomplete framework payload")
    dependencies = []
    for item in importlib.metadata.distributions():
        bindings = {}
        for name in ("METADATA", "RECORD", "direct_url.json"):
            content = item.read_text(name)
            if content is not None:
                bindings[name] = hashlib.sha256(content.encode()).hexdigest()
        dependencies.append({"name": item.metadata["Name"], "version": item.version,
                             "distribution_record_hashes": bindings})
    return {"python": sys.version, "executable": str(Path(sys.executable).resolve()),
            "executable_sha256": sha_file(sys.executable), "platform": platform.platform(),
            "framework_version": distribution.version, "framework_wheel": str(wheel),
            "framework_wheel_sha256": WHEEL_SHA256,
            "framework_root": str(Path(distribution.locate_file("consequa_x")).resolve()),
            "framework_payload": payload,
            "dependency_coverage": "Version and installed metadata/RECORD bindings; not all dependency payload files rehashed",
            "dependencies": sorted(dependencies, key=lambda item: item["name"].lower())}


def verify_files(root, inventory):
    root = Path(root).resolve()
    for name, record in inventory.items():
        canonical_path(name)
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha_file(path) != record["sha256"]:
            raise ValueError(f"Bound file changed or absent: {name}")
        if path.stat().st_size != record["bytes"]:
            raise ValueError(f"Bound file bytes changed: {name}")


def canonical_path(name):
    path = PurePosixPath(name)
    if (not isinstance(name, str) or name in {"", "."} or path.is_absolute() or path.as_posix() != name
            or any(part == ".." for part in path.parts) or "\\" in name or ":" in name):
        raise ValueError("Manifest paths must be canonical relative POSIX paths")


def verify_artifact_manifest(directory):
    directory = Path(directory).resolve()
    manifest = load_json(directory / "manifest.json")
    files = manifest["files"]
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
              if p.is_file() and p != directory / "manifest.json"}
    if actual != set(files):
        raise ValueError("Artifact inventory mismatch")
    for name, digest in files.items():
        canonical_path(name)
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or sha_file(path) != digest:
            raise ValueError(f"Artifact digest mismatch: {name}")
    return manifest


def verify_frozen_protocol(protocol_path, protocol_commit):
    """Require the caller's explicit immutable Git anchor, not an editable receipt.

    The protocol commit is later than the execution-source commit. A detached
    source checkout can therefore stay fixed while the protocol is published
    separately before official collection. Both JSON files must be exact Git
    blob bytes: this is not a line-ending-normalized source-file comparison.
    """
    if (not isinstance(protocol_commit, str) or len(protocol_commit) != 40
            or any(char not in "0123456789abcdef" for char in protocol_commit)):
        raise ValueError("An explicit40character immutable protocol commit is required")
    path = Path(protocol_path).resolve()
    root = Path(subprocess.check_output(["git", "-C", str(path.parent),
                                       "rev-parse", "--show-toplevel"]).decode().strip()).resolve()
    for file in (path, path.parent / "protocol-receipt.json"):
        name = file.relative_to(root).as_posix()
        expected = subprocess.check_output(["git", "-C", str(root), "show", f"{protocol_commit}:{name}"])
        if file.read_bytes() != expected:
            raise ValueError("Prospective protocol/receipt differs from caller-pinned Git commit")
    protocol, receipt = load_json(path), load_json(path.parent / "protocol-receipt.json")
    if (receipt["protocol_sha256"] != canonical_sha(protocol)
            or receipt["protocol_file_sha256"] != sha_file(path)):
        raise ValueError("Prospective protocol receipt hash mismatch")
    return protocol, {"protocol_commit": protocol_commit, "protocol_git_root": str(root),
                      "protocol_git_path": path.relative_to(root).as_posix(),
                      "protocol_file_sha256": sha_file(path), "protocol_sha256": canonical_sha(protocol)}
