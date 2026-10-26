"""Prepare, freeze or execute the separate expanded LIMBO research condition.

Metadata and freezing make no model request. Collection requires an explicitly
committed protocol and independently completed readiness; no implicit retries.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.expanded_limbo.harness import (  # noqa: E402
    collect_block, load, run_episode_worker, scientific_sources, verify_files,
    verify_readiness,
)
from research.expanded_limbo.protocol import (  # noqa: E402
    build_protocol, candidate_indices, extract_metadata, file_binding, require,
)
from research.limbo_agent.harness import installed_wheel_binding, manifest  # noqa: E402
from research.limbo_agent.protocol import native_binding, utc, write_new  # noqa: E402


def source_commit_gate(sources):
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True).stdout.strip()
    for name, expected in sources.items():
        raw = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{name}"],
                             check=True, capture_output=True).stdout
        require({"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} == expected,
                "Commit the tested scientific sources before freezing: " + name)
    return commit


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    subs = command.add_subparsers(dest="command", required=True)
    for name in ("metadata", "freeze", "collect-block", "_episode"):
        part = subs.add_parser(name)
        part.add_argument("--native-root", type=Path, required=True)
        part.add_argument("--output", type=Path, required=True)
        if name == "metadata":
            part.add_argument("--exposure", type=Path, required=True)
            part.add_argument("--instances-per-template", type=int, default=4)
            part.add_argument("--selection-seed", default="conseqax-expanded-limbo-2026-10-25-v1")
        elif name == "freeze":
            part.add_argument("--metadata", type=Path, required=True)
            part.add_argument("--exposure", type=Path, required=True)
            part.add_argument("--models", type=Path, required=True)
            part.add_argument("--readiness", type=Path, required=True)
            part.add_argument("--wheel", type=Path, required=True)
            part.add_argument("--instances-per-template", type=int, default=4)
            part.add_argument("--selection-seed", default="conseqax-expanded-limbo-2026-10-25-v1")
            part.add_argument("--generation-seeds", nargs="+", type=int, default=[1701, 2718])
            part.add_argument("--temperature", type=float, default=0.2)
            part.add_argument("--worlds-per-block", type=int, default=12)
            part.add_argument("--max-tool-calls", type=int, default=16)
        elif name == "collect-block":
            part.add_argument("--protocol", type=Path, required=True)
            part.add_argument("--protocol-commit", required=True)
            part.add_argument("--wheel", type=Path, required=True)
            part.add_argument("--runtime-binding", type=Path, required=True)
            part.add_argument("--block-id", required=True)
        else:
            part.add_argument("--config", type=Path, required=True)
    return command


def main():
    args = parser().parse_args()
    if args.command == "_episode":
        run_episode_worker(ROOT, args.native_root, args.config, args.output)
        return
    if args.command == "collect-block":
        value = collect_block(ROOT, args.native_root, args.protocol, args.protocol_commit,
            args.wheel, args.runtime_binding, args.block_id, args.output)
        print(json.dumps({"block_id": value["block_id"], "planned": value["planned"],
            "dispositions": dict(Counter(row["status"] for row in value["rows"]))}))
        return
    # Bind source before trusted task construction; no model is imported or run.
    native = native_binding(args.native_root)
    sources = scientific_sources(ROOT)
    exposure = load(args.exposure)
    verify_files(ROOT, exposure["sources"])
    if args.command == "metadata":
        indices = candidate_indices(sorted(exposure["by_template"]), exposure,
            instances_per_template=args.instances_per_template, selection_seed=args.selection_seed)
        metadata = extract_metadata(args.native_root, indices)
        args.output.mkdir(parents=True, exist_ok=False)
        write_new(args.output / "metadata.json", metadata)
        write_new(args.output / "index-plan.json", indices)
        write_new(args.output / "exposure.json", exposure)
        write_new(args.output / "receipt.json", {"utc": utc(), "selection_seed": args.selection_seed,
            "instances_per_template": args.instances_per_template, "native": native, "sources": sources,
            "model_generations": 0, "task_value_fields_emitted": False})
        write_new(args.output / "manifest.json", manifest(args.output))
        print(json.dumps({"base_instances": len(metadata), "templates": len(indices),
                          "model_generations": 0, "status": "metadata_only_not_a_measured_freeze"}))
        return
    require(args.command == "freeze", "Unsupported command")
    require(not args.output.exists(), "Refuse an existing protocol directory")
    commit = source_commit_gate(sources)
    installed_wheel_binding(args.wheel)
    models, readiness = load(args.models), load(args.readiness)
    protocol = build_protocol(load(args.metadata), models, exposure,
        selection_seed=args.selection_seed, instances_per_template=args.instances_per_template,
        generation_seeds=args.generation_seeds, temperature=args.temperature,
        worlds_per_block=args.worlds_per_block, max_tool_calls=args.max_tool_calls,
        source_files=sources, native_files=native["files"], wheel_binding=file_binding(args.wheel),
        limits=readiness["limits"], readiness_binding=file_binding(args.readiness))
    verify_readiness(protocol, args.readiness)
    args.output.mkdir(parents=True, exist_ok=False)
    write_new(args.output / "protocol.json", protocol)
    with (args.output / "readiness.json").open("xb") as stream:
        stream.write(args.readiness.read_bytes())
    write_new(args.output / "freeze-receipt.json", {"utc": utc(), "source_commit": commit,
        "protocol": file_binding(args.output / "protocol.json"), "model_generations": 0,
        "status": "commit_and_publish_protocol_before_measured_generation"})
    write_new(args.output / "manifest.json", manifest(args.output))
    print(json.dumps({"counts": protocol["counts"], "model_generations": 0,
                      "status": "protocol_written_requires_explicit_publication_before_collection"}))


if __name__ == "__main__":
    main()
