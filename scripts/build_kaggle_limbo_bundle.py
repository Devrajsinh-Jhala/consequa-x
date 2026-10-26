"""Package the fixed GPU-study proposal and small source/metadata payload.

No model load, download, generation, native episode, or measured freeze occurs.
The bundle excludes model weights, credentials, CPU results and runtime logs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.expanded_limbo.protocol import (  # noqa: E402
    build_protocol, candidate_indices, extract_metadata, file_binding, require,
)
from research.limbo_agent.protocol import native_binding  # noqa: E402


WHEEL_SHA256 = "c86c02aacac53d51bd4335238c4f44b96098db9af354662b23722fab60ed3b98"
MODELS = (("qwen4b", "qwen", "qwen3"), ("llama3b", "llama", "llama3.2"),
          ("granite2b", "granite", "granite3.3"))
LIMITS = {"max_requests": 16, "max_output_tokens": 512, "request_timeout_s": 300,
    "episode_timeout_s": 1800,
    "work": {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}}
SELECTION_SEED = "conseqax-kaggle-full-2026-10-26-v1"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def copy_new(source, target):
    source, target = Path(source), Path(target)
    require(source.is_file() and not source.is_symlink(), "Expected regular source: " + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, target.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    require(file_binding(source) == file_binding(target), "Source changed during packaging")


def selected_sources(root):
    root = Path(root)
    names = {p.relative_to(root).as_posix() for directory in (
        "research/kaggle_limbo", "research/expanded_limbo", "research/obligation_shield",
        "research/limbo_agent") for p in (root / directory).glob("*.py")}
    names.update({"research/native_agent/transport.py", "research/native_agent/__init__.py",
        "scripts/run_expanded_limbo.py", "scripts/launch_expanded_research.py",
        "scripts/launch_durable_research.py", "scripts/start_durable_limbo_runtime.py",
        "scripts/build_kaggle_limbo_bundle.py", "LICENSE"})
    for optional in ("research/__init__.py", "scripts/__init__.py", "docs/KAGGLE_BENCHMARK.md"):
        if (root / optional).is_file():
            names.add(optional)
    return sorted(names)


def check_source_commit(root, commit, names, *, engineering=False):
    require(isinstance(commit, str) and len(commit) == 40
            and all(c in "0123456789abcdef" for c in commit), "Full immutable source commit required")
    resolved = subprocess.run(["git", "-C", str(root), "rev-parse", commit + "^{commit}"],
                             check=True, capture_output=True, text=True).stdout.strip()
    require(resolved == commit, "Source commit did not resolve exactly")
    mismatch = []
    for name in names:
        actual = (Path(root) / name).read_bytes()
        saved = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{name}"], capture_output=True)
        if saved.returncode or saved.stdout != actual:
            mismatch.append(name)
    require(engineering or not mismatch, "Commit the exact tested source bytes first: " + ", ".join(mismatch))
    return mismatch


def make_exposure(original_path):
    original = load(original_path)
    rows = original["metadata"]
    require(len(rows) == 12 and len({r["template"] for r in rows}) == 12,
            "Original template/index inventory differs")
    return {"complete_known_exposure_attested": True,
        "sources": {"original-limbo-protocol-2026-10-24.json": file_binding(original_path)},
        "by_template": {r["template"]: sorted({0, 1, r["index"]}) for r in rows}}


def package_model(root, payload, slug, family, registry_name, requirement_binding):
    acquired_path = root / f"output/expanded-model-{slug}-2026-10-25/acquisition.json"
    acquired = load(acquired_path)
    manifest_path = Path(acquired["manifest"]["path"])
    require(file_binding(manifest_path) == {k: acquired["manifest"][k] for k in ("sha256", "bytes")},
            "Model OCI manifest changed: " + family)
    image = load(manifest_path)
    destination = payload / "assets/models" / family
    copy_new(manifest_path, destination / "registry-manifest.json")
    weights = []
    for layer in [image["config"], *image["layers"]]:
        digest = layer["digest"]
        require(digest.startswith("sha256:") and len(digest) == 71, "Invalid OCI digest")
        expected = {"sha256": digest[7:], "bytes": layer["size"]}
        if layer["mediaType"] == "application/vnd.ollama.image.model":
            weights.append(expected)
            continue
        require(0 < layer["size"] <= 16 * 1024**2, "Refuse unexpectedly large model metadata layer")
        blob = Path(acquired["weights_path"]).parent / ("sha256-" + digest[7:])
        require(file_binding(blob) == expected, "Model metadata blob changed")
        copy_new(blob, destination / blob.name)
    require(weights == [acquired["weights"]], "OCI and acquired weight identities differ")
    model_id = f"conseqax-kaggle-{slug}:full-v1"
    record = {"id": model_id, "family": family, "checkpoint": acquired["tag"],
        "quantization": acquired["details"]["quantization_level"], "weights": acquired["weights"],
        "tokenizer": acquired["tokenizer"], "chat_template": acquired["chat_template"],
        "license": acquired["license"], "context_tokens": 8192,
        "transport_preflight": requirement_binding}
    catalog = {"family": family, "registry_name": registry_name, "original_tag": acquired["tag"],
        "registry_manifest": (destination / "registry-manifest.json").relative_to(payload).as_posix(),
        "registry_manifest_binding": file_binding(destination / "registry-manifest.json"),
        "weights": acquired["weights"], "model_weights_included": False,
        "preflight_binding_scope": "Requirement document only; GPU readiness not completed in this proposal"}
    return record, catalog


def deterministic_zip(payload, archive):
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as output:
        for path in sorted(p for p in payload.rglob("*") if p.is_file()):
            name = "conseqax-kaggle-study/" + path.relative_to(payload).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)


def build(root, native_root, commit, output, *, engineering=False):
    root, native_root, output = [Path(p).resolve() for p in (root, native_root, output)]
    require(not output.exists(), "Refuse an existing release output")
    names = selected_sources(root)
    mismatch = check_source_commit(root, commit, names, engineering=engineering)
    native = native_binding(native_root)
    output.mkdir(parents=True, exist_ok=False)
    payload = output / "conseqax-kaggle-study"
    payload.mkdir()
    for name in names:
        copy_new(root / name, payload / name)
    for name in native["files"]:
        copy_new(native_root / name, payload / "native" / name)
    copy_new(native_root / "LICENSE", payload / "native/LICENSE")
    wheel = root / "output/release-2.1.1-2026-10-19/consequa_x-2.1.1-py3-none-any.whl"
    require(file_binding(wheel)["sha256"] == WHEEL_SHA256, "Scientific SDK wheel identity differs")
    copy_new(wheel, payload / "assets" / wheel.name)
    requirement = payload / "assets/GPU-PREFLIGHT-REQUIREMENTS.json"
    write_new(requirement, {"schema": "conseqax-kaggle-gpu-preflight-requirements-v1",
        "passed": False, "is_completed_preflight": False, "measured_generations": 0,
        "requires_before_measured_freeze": ["pinned Linux runtime/archive", "matching GPU condition",
            "all three exact model weights and metadata", "actual structured tool-call and follow-up per family",
            "complete provider render plus runner token context checks", "GPU residency per dispatch",
            "unchanged native physical replay and shield certificate checks"],
        "scope": "This file is a requirement binding, never evidence that GPU preflight passed"})
    models, catalog = [], {}
    for slug, family, registry_name in MODELS:
        model, item = package_model(root, payload, slug, family, registry_name, file_binding(requirement))
        models.append(model)
        catalog[model["id"]] = item
    write_new(payload / "assets/model-catalog.json", catalog)
    exposure = make_exposure(root / "output/limbo-protocol-2026-10-24/protocol.json")
    indices = candidate_indices(sorted(exposure["by_template"]), exposure,
        instances_per_template=4, selection_seed=SELECTION_SEED)
    metadata = extract_metadata(native_root, indices)
    source_files = {name: file_binding(payload / name) for name in names if name.endswith(".py")}
    proposal = build_protocol(metadata, models, exposure, selection_seed=SELECTION_SEED,
        instances_per_template=4, generation_seeds=(1701, 2718), temperature=0.2,
        worlds_per_block=12, max_tool_calls=16, source_files=source_files,
        native_files=native["files"], wheel_binding=file_binding(wheel), limits=LIMITS,
        readiness_binding=None)
    require(proposal["counts"]["planned_slots"] == 3456, "The full matrix must retain all 3456 slots")
    write_new(payload / "study-design.json", proposal)
    write_new(payload / "assets/exposure-ledger.json", exposure)
    write_new(payload / "assets/study-scope.json", {"schema": "conseqax-kaggle-proposal-scope-v1",
        "source_commit": commit, "engineering_only": engineering, "uncommitted_source_paths": mismatch,
        "measured_generations": 0, "gpu_preflight_passed": False, "measured_protocol_frozen": False,
        "proposal_readiness": None, "counts": proposal["counts"],
        "historical_CPU_results_included_or_pooled": False,
        "model_preflight_fields_bind_requirements_not_completed_proof": True,
        "before_first_measured_generation": "Validate actual GPU preflight; bind actual GPU condition, static source/runtime/model identities and completed readiness in a separate immutable execution declaration"})
    files = {p.relative_to(payload).as_posix(): file_binding(p)
             for p in sorted(payload.rglob("*")) if p.is_file()}
    write_new(payload / "bundle-manifest.json", {"schema": "conseqax-kaggle-source-bundle-v1",
        "source_commit": commit, "engineering_only": engineering, "files": files})
    archive = output / "conseqax-kaggle-benchmark.zip"
    deterministic_zip(payload, archive)
    receipt = {"schema": "conseqax-kaggle-bundle-build-v1", "source_commit": commit,
        "engineering_only": engineering, "bound_payload_files": len(files),
        "archive": {"name": archive.name, **file_binding(archive)},
        "source_manifest": file_binding(payload / "bundle-manifest.json"),
        "counts": proposal["counts"], "model_weights_included": False,
        "measured_generations": 0, "GPU_readiness_or_measured_freeze_completed": False}
    write_new(output / "build-receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-root", type=Path,
                        default=Path("C:/Code/ConsequaX-Research/limbo-pinned-2db09fba"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--engineering", action="store_true",
        help="Allow uncommitted engineering sources; mark bundle nonfinal and unsuitable for measured use")
    args = parser.parse_args()
    receipt = build(args.root, args.native_root, args.source_commit, args.output,
                    engineering=args.engineering)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
