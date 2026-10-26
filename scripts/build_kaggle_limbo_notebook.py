"""Build the portable Kaggle notebook without executing a model or contacting Kaggle.

Release packaging supplies the exact archive hash and source commit after freezing
the study bundle. An unbound engineering notebook deliberately refuses live use.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import textwrap


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_NAME = "ConseqaX_Full_Benchmark_Kaggle.ipynb"


def _cell(kind: str, source: str, identifier: str) -> dict:
    cell = {"cell_type": kind, "id": identifier, "metadata": {},
            "source": textwrap.dedent(source).strip().splitlines(keepends=True)}
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    return cell


def build_notebook(bundle_sha256: str | None = None,
                   source_commit: str | None = None,
                   manifest_sha256: str | None = None) -> dict:
    if (source_commit is None) != (bundle_sha256 is None and manifest_sha256 is None):
        raise ValueError("Supply the exact source commit and at least one bundle integrity pin")
    if bundle_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", bundle_sha256):
        raise ValueError("bundle SHA256 must be 64 lowercase hexadecimal characters")
    if source_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be a full 40-character lowercase Git commit")
    if manifest_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
        raise ValueError("manifest SHA256 must be 64 lowercase hexadecimal characters")
    config = f'''
        import os
        import time
        # Rerunning a cell must not reset this session's deadline.
        if "_SESSION_STARTED_AT" not in globals():
            _SESSION_STARTED_AT = time.monotonic()
        os.environ["CONSEQAX_SESSION_START_MONOTONIC"] = str(_SESSION_STARTED_AT)
        # Usually leave these two paths alone: a unique attached input is found for you.
        BUNDLE_PATH = None       # Optional: delivered ZIP, unpacked study folder, or bundle-manifest.json
        RESUME_FROM = None       # Optional: entire previous saved output, active folder, or clean checkpoint.zip
        OUTPUT_DIR = "/kaggle/working/conseqax-benchmark"
        SESSION_HOURS = 7        # Total study window, including setup; leave hour 8 for saving.
        EXPECTED_BUNDLE_SHA256 = {bundle_sha256!r}
        EXPECTED_SOURCE_COMMIT = {source_commit!r}
        EXPECTED_MANIFEST_SHA256 = {manifest_sha256!r}
    '''
    cells = [
        _cell("markdown", '''
            <div style="padding:30px;border-radius:18px;background:#101d2c;color:#f0f5fb">
            <div style="color:#b9ed78;letter-spacing:2px;font-size:12px">CONSEQA-X · REPRODUCIBLE RESEARCH</div>
            <h1 style="color:#fff;margin:12px 0">One study. Saveable sessions.</h1>
            <p style="font-size:18px;line-height:1.6">Run the complete, predeclared <b>3,456-slot</b>
            benchmark on Kaggle GPU, then carry your progress into the next session.</p>
            <p style="color:#b8c8da">Frozen study bundle → GPU checks → resumable collection → saved evidence</p>
            </div>

            This notebook runs local models. It needs no API key or paid model provider.
            It does not publish results or trigger GitHub Actions. Collection is followed
            by a separate evidence audit; raw model output is not an audited paper result.
        ''', "welcome"),
        _cell("markdown", '''
            ## 1 · Prepare your Kaggle session

            In **Notebook settings**, turn **GPU** and **Internet** on. Use a GPU
            session with an **8-hour time window** and enough free output storage.
            Attach the delivered `conseqax-kaggle-benchmark.zip` as an **Input**.
            Kaggle may unpack the uploaded ZIP automatically; both the original ZIP
            and its extracted study files are supported and checked against release pins.

            Continuing a previous session? Also attach that notebook version's
            **entire latest saved output** as an **Input**, including the active
            `conseqax-benchmark` folder and `checkpoint.zip`. The active ledger can
            contain starts recorded after the ZIP was exported, so it takes priority.
            A standalone ZIP is suitable only when no newer raw output exists.

            After configuring settings and Inputs, choose **Save Version → Save & Run All
            once**. This starts a fresh background session, runs the notebook from top
            to bottom, and saves that version's outputs. **Do not run the study
            interactively first and then choose Save & Run All just to save it**:
            that launches another execution without the newly collected checkpoint.

            The study's **7-hour deadline includes setup**,
            leaving the eighth hour for saving. The runner also reserves time before
            that deadline to finish a slot and flush its evidence, so it stops starting
            new slots earlier. Kaggle can stop a session sooner; confirm the background
            version's output files are available when it finishes.

            **Already collected data interactively?** Use **Quick Save with outputs
            preserved** and verify the complete output was saved. Do not launch a fresh
            **Save & Run All** until the new checkpoint/output is attached as an Input.

            The exact archive hash and source commit below are filled by release
            packaging. An unbound development copy stops before installation or collection.
        ''', "prepare"),
        _cell("code", config, "configuration"),
        _cell("markdown", '''
            ## 2 · Open the frozen study

            The next cell checks the archive's exact hash (or the unpacked manifest's
            exact hash), every packaged file, and
            the pinned source commit before executing packaged code. It never fetches
            a moving branch. If more than one matching study or previous checkpoint
            is attached, set the corresponding path above; guessing is unsafe.
        ''', "bundle-explanation"),
        _cell("code", BOOTSTRAP, "open-bundle"),
        _cell("markdown", '''
            ## 3 · Prepare the local runtime

            This installs the pinned dependencies and downloads the declared local
            models. Setup verifies the GPU/runtime conditions and records their
            identities. A missing GPU, failed download, changed bundle, or incompatible
            continuation stops the study. Do not change model, protocol, precision,
            or runtime settings between sessions.
        ''', "setup-explanation"),
        _cell("code", SETUP, "runtime-setup"),
        _cell("markdown", '''
            ## 4 · Run this session

            The packaged schedule fixes **3,456 slots** before collection. Its
            checkpoint ledger records a slot's start before a model is called.
            **Finished or already-started slots are never automatically run again.**
            If a session stops mid-slot, that slot remains interrupted or unresolved;
            resuming proceeds to untouched slots. This avoids silently replacing a
            failed attempt with a better outcome. Completion counts must distinguish
            successful, failed, interrupted, and unstarted slots.

            In the background version, this cell runs automatically. The session timer includes setup time and
            refuses to start after its deadline. The runner also
            enforces its own wall-clock deadline and checkpoint validation.
        ''', "run-explanation"),
        _cell("code", RUN, "collect"),
        _cell("markdown", '''
            ## 5 · Save, then continue next time

            This export cell runs automatically at the end of the background version.
            If collecting interactively, export even if collection stopped early,
            then Quick Save with outputs preserved. It creates a
            portable **`/kaggle/working/checkpoint.zip`** beside the active study
            folder and keeps the underlying evidence. **Save and attach the whole
            latest output**, especially after an interruption. The runner validates
            the raw ledger's hash chain and sealed evidence before continuing; raw
            started reservations take priority over an older ZIP. Never choose an
            older ZIP while a newer raw output is available, as that could repeat work.

            1. When the background version finishes, confirm and retain its complete
               saved output. For an existing interactive run, use **Quick Save with
               outputs**, not a fresh Save & Run All.
            2. Open a new GPU session with Internet enabled.
            3. Attach the same frozen study ZIP and the **entire latest saved output**
               as Inputs, keeping its `conseqax-benchmark` folder intact.
            4. Choose **Save Version → Save & Run All once** for the new session.
               A unique prior checkpoint is selected automatically; otherwise set
               `RESUME_FROM` explicitly before launching it.
            5. Repeat until no untouched slots remain. Preserve interruptions in
               the final report rather than restarting them.

            **Before paper claims:** independently audit the collected evidence and
            report availability and errors alongside the native metrics. This
            notebook was checked offline; an actual Kaggle GPU run is still required
            to establish hardware compatibility and measured throughput. Finishing
            all slots within a particular number of sessions is not guaranteed.
        ''', "save-explanation"),
        _cell("code", EXPORT, "export"),
    ]
    return {"nbformat": 4, "nbformat_minor": 5, "cells": cells,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                         "name": "python3"},
                         "language_info": {"name": "python", "version": "3.11"},
                         "conseqax": {"schema": "conseqax-kaggle-notebook-v1",
                                      "planned_slots": 3456,
                                      "bundle_sha256": bundle_sha256,
                                      "manifest_sha256": manifest_sha256,
                                      "source_commit": source_commit,
                                      "actual_kaggle_gpu_tested": False}}}


BOOTSTRAP = r'''
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile

# Engineering tests can inspect the plan without GPU, installation, or model calls.
DRY_RUN = os.environ.get("CONSEQAX_NOTEBOOK_DRY_RUN") == "1"
if "_SESSION_STARTED_AT" not in globals():
    _SESSION_STARTED_AT = time.monotonic()
INPUT_ROOT = Path(os.environ.get("CONSEQAX_NOTEBOOK_INPUT_ROOT", "/kaggle/input"))
TEMP_ROOT = Path(os.environ.get("CONSEQAX_NOTEBOOK_TEMP_ROOT", "/kaggle/temp"))
COMMAND_PLAN = []

def require_pins():
    if EXPECTED_BUNDLE_SHA256 is None and EXPECTED_MANIFEST_SHA256 is None:
        raise RuntimeError("Use the released notebook bound to your delivered study: its archive hash is missing, and no unpacked manifest hash is supplied.")
    for label, value in (("archive", EXPECTED_BUNDLE_SHA256), ("manifest", EXPECTED_MANIFEST_SHA256)):
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)):
            raise RuntimeError(f"The released study needs a valid pinned {label} SHA256.")
    if not isinstance(EXPECTED_SOURCE_COMMIT, str) or not re.fullmatch(r"[0-9a-f]{40}", EXPECTED_SOURCE_COMMIT):
        raise RuntimeError("The notebook needs the exact frozen study source commit.")
    if not isinstance(SESSION_HOURS, (int, float)) or isinstance(SESSION_HOURS, bool) or not 0 < SESSION_HOURS <= 7:
        raise RuntimeError("SESSION_HOURS must be greater than zero and at most 7.")

def unique_path(explicit, candidates, label, optional=False):
    if explicit:
        selected = Path(explicit).expanduser().resolve()
        if not selected.exists():
            raise RuntimeError(f"{label} does not exist: {selected}")
        return selected
    choices = sorted({p.resolve() for p in candidates}, key=str)
    if not choices and optional:
        return None
    if len(choices) != 1:
        raise RuntimeError(f"Attach exactly one {label}, or set its path explicitly. Found {len(choices)}.")
    return choices[0]

def discover_bundle():
    if BUNDLE_PATH:
        selected = unique_path(BUNDLE_PATH, [], "study input")
        if selected.is_file() and selected.name == "conseqax-kaggle-benchmark.zip":
            return "zip", selected
        if selected.is_file() and selected.name == "bundle-manifest.json":
            return "tree", selected
        if selected.is_dir():
            manifests = list(selected.rglob("bundle-manifest.json"))
            return "tree", unique_path(None, manifests, "unpacked study manifest")
        raise RuntimeError("Select the delivered ZIP, unpacked study folder, or bundle-manifest.json.")
    archives = list(INPUT_ROOT.rglob("conseqax-kaggle-benchmark.zip"))
    if archives:
        return "zip", unique_path(None, archives, "study ZIP")
    manifests = []
    for candidate in INPUT_ROOT.rglob("bundle-manifest.json"):
        try:
            if candidate.stat().st_size > 4 * 1024 * 1024:
                continue
            record = json.loads(candidate.read_bytes())
            if (isinstance(record, dict)
                    and record.get("schema") == "conseqax-kaggle-source-bundle-v1"
                    and record.get("source_commit") == EXPECTED_SOURCE_COMMIT):
                manifests.append(candidate)
        except (OSError, ValueError, UnicodeError):
            continue
    return "tree", unique_path(None, manifests, "unpacked study manifest matching the pinned commit")

def raw_checkpoint(folder):
    if (folder / "identity.json").is_file():
        if not (folder / "schedule.json").is_file():
            raise RuntimeError("A raw checkpoint is incomplete: identity.json exists but schedule.json is missing. Preserve the whole saved output.")
        return folder.resolve()
    return None

def prefer_raw_checkpoint(selected):
    # A clean export and its active ledger are one campaign. The ledger may retain
    # starts newer than the ZIP; only the runner decides whether its evidence is valid.
    folder = selected if selected.is_dir() else selected.parent
    for candidate in (folder, folder / "conseqax-benchmark"):
        raw = raw_checkpoint(candidate)
        if raw is not None:
            return raw
    if selected.is_dir():
        if (selected / "checkpoint.json").is_file():
            return selected
        if (selected / "checkpoint.zip").is_file():
            return selected / "checkpoint.zip"
        raise RuntimeError("Select the entire saved output, a raw active ledger, or checkpoint.zip.")
    if selected.name != "checkpoint.zip":
        raise RuntimeError("Select the previous output folder or checkpoint.zip.")
    return selected

def discover_resume():
    if RESUME_FROM:
        selected = unique_path(RESUME_FROM, [], "previous checkpoint")
        return prefer_raw_checkpoint(selected)
    roots = set()
    for identity in INPUT_ROOT.rglob("identity.json"):
        roots.add(raw_checkpoint(identity.parent))
    for marker in INPUT_ROOT.rglob("checkpoint.json"):
        roots.add(prefer_raw_checkpoint(marker.parent))
    for archive in INPUT_ROOT.rglob("checkpoint.zip"):
        preferred = prefer_raw_checkpoint(archive)
        if preferred == archive and archive.parent.resolve() in roots:
            continue  # The exported directory and its ZIP are the same snapshot.
        roots.add(preferred)
    return unique_path(None, roots, "previous checkpoint", optional=True)

def open_bundle(archive, destination):
    if EXPECTED_BUNDLE_SHA256 is None:
        raise RuntimeError("ZIP input requires its released archive SHA256 pin.")
    with archive.open("rb") as stream:
        archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if archive_hash != EXPECTED_BUNDLE_SHA256:
        raise RuntimeError("Study ZIP hash differs from the released notebook. No code was executed.")
    if destination.exists():
        raise RuntimeError("Study extraction already exists. Restart the kernel/session rather than replacing frozen files.")
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if len(members) > 20000 or sum(m.file_size for m in members) > 512 * 1024 * 1024:
            raise RuntimeError("Study archive exceeds the notebook's safe extraction limits.")
        seen = set()
        for member in members:
            name = member.filename
            parts = PurePosixPath(name).parts
            if (not parts or parts[0] != "conseqax-kaggle-study" or "\\" in name
                    or PurePosixPath(name).is_absolute() or any(p in ("..", ".") or ":" in p for p in parts)
                    or "\x00" in name or name in seen
                    or str(PurePosixPath(name)) != name.rstrip("/")):
                raise RuntimeError("Unsafe or duplicate study archive member.")
            seen.add(name)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                raise RuntimeError("Study archive contains a link or special file.")
            if member.flag_bits & 1:
                raise RuntimeError("Encrypted study archive is unsupported.")
        manifest_name = "conseqax-kaggle-study/bundle-manifest.json"
        manifest = json.loads(source.read(manifest_name))
        if manifest.get("schema") != "conseqax-kaggle-source-bundle-v1":
            raise RuntimeError("Unsupported study bundle manifest schema.")
        if manifest.get("source_commit") != EXPECTED_SOURCE_COMMIT:
            raise RuntimeError("Study source commit differs from the released notebook.")
        bindings = manifest.get("files")
        if not isinstance(bindings, dict) or not bindings:
            raise RuntimeError("Study bundle has no pinned file inventory.")
        inventory = {m.filename[len("conseqax-kaggle-study/"):] for m in members if not m.is_dir()}
        if inventory != set(bindings) | {"bundle-manifest.json"}:
            raise RuntimeError("Study archive and manifest inventories differ.")
        for relative, binding in bindings.items():
            data = source.read("conseqax-kaggle-study/" + relative)
            if (not isinstance(binding, dict) or type(binding.get("bytes")) is not int
                    or len(data) != binding["bytes"] or hashlib.sha256(data).hexdigest() != binding.get("sha256")):
                raise RuntimeError(f"Study source binding failed: {relative}")
        destination.mkdir(parents=True, exist_ok=False)
        try:
            for member in members:
                if not member.is_dir():
                    target = destination.joinpath(*PurePosixPath(member.filename).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as incoming, target.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
        except BaseException:
            # Preserve the incomplete directory for inspection; never execute it.
            raise
    return destination / "conseqax-kaggle-study"

def open_unpacked_bundle(manifest_path, destination):
    if EXPECTED_MANIFEST_SHA256 is None:
        raise RuntimeError("Unpacked study input requires the released manifest SHA256 pin.")
    tree = manifest_path.parent
    if manifest_path.is_symlink() or tree.is_symlink():
        raise RuntimeError("Unpacked study manifest/root must not be a symbolic link.")
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("Unpacked study manifest SHA256 differs from the release pin. No code was executed.")
    manifest = json.loads(manifest_bytes)
    if (manifest.get("schema") != "conseqax-kaggle-source-bundle-v1"
            or manifest.get("source_commit") != EXPECTED_SOURCE_COMMIT):
        raise RuntimeError("Unpacked study schema or source commit differs from the released notebook.")
    bindings = manifest.get("files")
    if not isinstance(bindings, dict) or not bindings or len(bindings) > 20000:
        raise RuntimeError("Unpacked study manifest has an invalid file inventory.")
    observed = set()
    for path in tree.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("Unpacked study contains a symbolic link.")
        if not path.is_dir():
            if not stat.S_ISREG(path.stat().st_mode):
                raise RuntimeError("Unpacked study contains a special file.")
            observed.add(path.relative_to(tree).as_posix())
    if observed != set(bindings) | {"bundle-manifest.json"}:
        raise RuntimeError("Unpacked study and manifest inventories differ.")
    payload = {}
    total_bytes = 0
    for relative, binding in bindings.items():
        if not isinstance(relative, str):
            raise RuntimeError("Unsafe unpacked study path.")
        parts = PurePosixPath(relative).parts
        if (not parts or PurePosixPath(relative).is_absolute() or "\\" in relative
                or "\x00" in relative or any(p in ("..", ".") or ":" in p for p in parts)
                or str(PurePosixPath(relative)) != relative):
            raise RuntimeError("Unsafe unpacked study path.")
        source = tree.joinpath(*parts)
        if not source.resolve().is_relative_to(tree.resolve()):
            raise RuntimeError("Unpacked study path escapes its root.")
        data = source.read_bytes()
        total_bytes += len(data)
        if total_bytes > 512 * 1024 * 1024:
            raise RuntimeError("Unpacked study exceeds the safe copy size limit.")
        if (not isinstance(binding, dict) or type(binding.get("bytes")) is not int
                or len(data) != binding["bytes"] or hashlib.sha256(data).hexdigest() != binding.get("sha256")):
            raise RuntimeError(f"Unpacked study source binding failed: {relative}")
        payload[relative] = data
    if destination.exists():
        raise RuntimeError("Study extraction already exists. Restart the kernel/session rather than replacing frozen files.")
    copied = destination / "conseqax-kaggle-study"
    copied.mkdir(parents=True, exist_ok=False)
    for relative, data in {**payload, "bundle-manifest.json": manifest_bytes}.items():
        target = copied.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return copied

def run_command(arguments):
    command = [sys.executable, "-m", *map(str, arguments)]
    COMMAND_PLAN.append(command)
    if DRY_RUN:
        print("DRY RUN ·", " ".join(command))
        return
    subprocess.run(command, cwd=STUDY_DIR, check=True)

require_pins()
BUNDLE_MODE, BUNDLE = discover_bundle()
PREVIOUS_CHECKPOINT = discover_resume()
if DRY_RUN:
    STUDY_DIR = TEMP_ROOT / "conseqax-frozen-source" / "conseqax-kaggle-study"
    print("OFFLINE TEST: GPU, extraction, downloads, installation, and model calls are skipped.")
else:
    if not Path("/kaggle").is_dir():
        raise RuntimeError("Run this released notebook in a Kaggle GPU session.")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                         check=True, capture_output=True, text=True)
    if not gpu.stdout.strip():
        raise RuntimeError("No GPU detected. Enable GPU in Kaggle Notebook settings.")
    print("GPU detected:", gpu.stdout.strip())
    opener = open_bundle if BUNDLE_MODE == "zip" else open_unpacked_bundle
    STUDY_DIR = opener(BUNDLE, TEMP_ROOT / "conseqax-frozen-source")
run_command(["research.kaggle_limbo.bundle", "verify", "--study-dir", STUDY_DIR])
print("Frozen study:", EXPECTED_SOURCE_COMMIT)
print("Previous checkpoint:", PREVIOUS_CHECKPOINT or "None — first session")
print("Output:", OUTPUT_DIR)
'''

SETUP = r'''
run_command(["research.kaggle_limbo.setup", "--study-dir", STUDY_DIR,
             "--runtime-dir", TEMP_ROOT / "conseqax-runtime",
             "--models-dir", TEMP_ROOT / "conseqax-models"])
print("Runtime setup finished. Continue only if this cell completed successfully.")
'''

RUN = r'''
# The runner reads the first-cell timestamp from the inherited environment.
# Pass the original 7-hour window: subtracting setup here would count it twice.
elapsed_seconds = time.monotonic() - _SESSION_STARTED_AT
remaining_hours = float(SESSION_HOURS) - elapsed_seconds / 3600
if remaining_hours <= 0:
    raise RuntimeError("The study deadline has been reached. Export and save; continue in a new session.")
collection_args = ["research.kaggle_limbo.run", "--study-dir", STUDY_DIR,
                   "--output", OUTPUT_DIR, "--session-hours", str(SESSION_HOURS)]
if PREVIOUS_CHECKPOINT is not None:
    collection_args.extend(["--resume-from", PREVIOUS_CHECKPOINT])
print(f"Time remaining before study deadline: {remaining_hours:.2f} hours. Planned matrix: 3,456 slots.")
run_command(collection_args)
'''

EXPORT = r'''
run_command(["research.kaggle_limbo.run", "--study-dir", STUDY_DIR,
             "--output", OUTPUT_DIR, "--export-only"])
print("Confirm this background version saved its complete output. Interactive runs: Quick Save with outputs; do not start a fresh Save & Run All to save results.")
print("Portable continuation:", Path(OUTPUT_DIR).parent / "checkpoint.zip")
print("No result or publication claim is made by this export.")
'''


def kernel_metadata() -> dict:
    # No owner/kernel id: importing or uploading remains a user action.
    return {"title": "ConseqaX · Full Resumable GPU Benchmark", "code_file": NOTEBOOK_NAME,
            "language": "python", "kernel_type": "notebook", "is_private": True,
            "enable_gpu": True, "enable_internet": True, "dataset_sources": [],
            "competition_sources": [], "kernel_sources": []}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-sha256")
    parser.add_argument("--source-commit")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "notebooks")
    parser.add_argument("--require-bound", action="store_true")
    args = parser.parse_args(argv)
    if args.require_bound and not (args.source_commit and (args.bundle_sha256 or args.manifest_sha256)):
        parser.error("release generation requires --source-commit and an archive or manifest SHA256")
    try:
        notebook = build_notebook(args.bundle_sha256, args.source_commit, args.manifest_sha256)
    except ValueError as exc:
        parser.error(str(exc))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in ((NOTEBOOK_NAME, notebook), ("kernel-metadata.json", kernel_metadata())):
        (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    print("Wrote notebook and Kaggle metadata; no models, GPU session, or publication was started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
