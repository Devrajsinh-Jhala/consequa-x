"""Copy and bind installed Ollama CPU runtime files without touching models.

Copies ollama.exe and every top-level lib/ollama file. GPU subdirectories are
excluded. A one-shot new destination and pre/copy/post hashes detect an updater
race; no listener is started and no download or model operation is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re


def binding(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return {"sha256": result.hexdigest(), "bytes": Path(path).stat().st_size}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def plan(source):
    source = Path(source).resolve(strict=True)
    library = source / "lib/ollama"
    require((source / "ollama.exe").is_file() and (library / "llama-server.exe").is_file(),
            "Installed CPU runtime entrypoints are missing")
    paths = [source / "ollama.exe", *sorted(p for p in library.iterdir() if p.is_file())]
    require(all(not path.is_symlink() for path in paths), "Symlinked runtime files are refused")
    required = {"ggml-base.dll", "ggml.dll", "libllama.dll", "libllama-common.dll",
                "libllama-server-impl.dll", "libomp.dll"}
    require(required.issubset({path.name for path in paths}), "Required CPU runtime libraries are missing")
    return {path.relative_to(source).as_posix(): binding(path) for path in paths}


def copy_private(source, destination, version):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version), "An explicit numeric runtime version is required")
    require(destination.name == "ollama-runtime-" + version,
            "Destination directory must explicitly name the runtime version")
    require(not destination.exists(), "Refuse overwriting an existing private runtime")
    require(source != destination and source not in destination.parents,
            "Private runtime must be outside the installed updater directory")
    before = plan(source)
    destination.mkdir(parents=True, exist_ok=False)
    for relative in before:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with (source / relative).open("rb") as original, target.open("xb") as copied:
            for chunk in iter(lambda: original.read(1024 * 1024), b""):
                copied.write(chunk)
            copied.flush()
            os.fsync(copied.fileno())
    after, copied = plan(source), plan(destination)
    require(before == after == copied, "Runtime changed during copying; preserve failed output and do not launch")
    receipt = {"schema": "conseqax-private-cpu-runtime-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(), "declared_version": version,
        "source": str(source), "destination": str(destination), "files": copied,
        "source_before_equals_source_after_equals_private_copy": True,
        "excluded_subdirectories": sorted(p.name for p in (source / "lib/ollama").iterdir() if p.is_dir()),
        "model_generations": 0, "model_loads": 0, "downloads": 0,
        "scope": "Installed CPU binaries and license files only; model store and normal service untouched",
        "copy_source": {"path": str(Path(__file__).resolve()), "binding": binding(__file__)}}
    with (destination / "private-runtime-manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    result = copy_private(args.source, args.destination, args.version)
    print(json.dumps({"status": "copied_verified_not_launched", "files": len(result["files"]),
                      "bytes": sum(item["bytes"] for item in result["files"].values()),
                      "destination": result["destination"]}))


if __name__ == "__main__":
    main()
