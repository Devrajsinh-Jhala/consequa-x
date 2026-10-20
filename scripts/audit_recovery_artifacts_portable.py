"""Recheck retained recovery artifacts from a relocated public Git clone.

This is a separate postcollection orchestration path. It reuses the exact
Git-bound frozen auditor's semantic functions, without modifying or monkeypatching
them. Original-host checks are deliberately not claimed. No framework, world,
controller, or runner is imported or executed, and no study is rerun.
"""

from __future__ import annotations

import argparse
import ast
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import subprocess
import tempfile
import types


SCHEMA = "recovery-controller-portable-artifact-audit-v1"
SOURCE_COMMIT = "22e88498cff0e2afd1549803fb4d9645902e74b9"
PROTOCOL_COMMIT = "3d3dd4ca663d3e16c7cb1ead4c59c724af9bedd7"
PROTOCOL_SHA256 = "b5c6a06bf1d758678e4d9890aa66872d4036634e2a4a4fd89626bd710bbc5aaa"
AUDITOR_PATH = "scripts/audit_recovery_controller_study.py"
REQUIRED_SOURCES = {
    AUDITOR_PATH,
    "scripts/run_recovery_controller_study.py",
    "scripts/build_recovery_human_review.py",
    "research/recovery_study/controllers.py",
    "research/recovery_study/world.py",
    "research/recovery_study/heldout_cases.json",
}
OMITTED_HOST_CHECKS = [
    "Original source worktree bytes, current HEAD, import origins, and original absolute source location are not checked; pinned Git object bytes are checked instead.",
    "The original Windows Python executable and its binary hash are not re-opened or executed. The current interpreter is not claimed to equal that interpreter.",
    "The original installed venv/package location and live installed inventory are not inspected. Recorded framework file hashes are checked against pinned source blobs only.",
    "Original absolute protocol/output paths are retained declarations, not required live locations. Their original existence and filesystem placement are not verified.",
    "Live canonical and protocol-local claim files on the collection host are not required or inspected. Any supplied/public-clone claim copy is checked only for byte equality to retained started.json.",
    "A retained claim and Git/start timestamps do not independently prove first-run exclusivity, collection chronology, absence of other runs, or the absence of deleted/replaced records outside the retained inventory.",
    "The live collection process, host environment/hardware, elapsed wall times, and installed dependency execution are not remeasured.",
]
LIMITATIONS = [
    "Pass means retained-artifact consistency and semantic recomputation within the declared scope; it is not original-host verification, authentication, or independent-human replication.",
    "The reused auditor's author also authored the controllers. Its separate implementation is not an externally authored evaluator.",
    "Source admission, provenance metadata, clocks, provider idempotency, and terminal guarantees remain application assumptions.",
    "No-new-model/service-call and no-retry assertions are retained declarations; saved artifacts alone cannot rule out unrecorded activity.",
    "Finite safety cutoff does not establish absence of arbitrarily late effects. Failed slots without snapshots remain operational failures with unavailable lifecycle semantics.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(data, label="JSON"):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate key in {label}: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"nonfinite number in {label}: {value}")

    result = json.loads(
        data.decode("utf-8-sig"), object_pairs_hook=unique, parse_constant=nonfinite
    )
    require(isinstance(result, dict), f"{label} must contain a JSON object")
    return result


def load_json(path):
    return json_bytes(Path(path).read_bytes(), Path(path).name)


def relative_path(name):
    require(
        isinstance(name, str) and name and "\\" not in name and ":" not in name,
        "path must be a canonical relative POSIX path",
    )
    part = PurePosixPath(name)
    require(
        not part.is_absolute()
        and part.as_posix() == name
        and all(item not in ("", ".", "..") for item in part.parts),
        "unsafe/noncanonical relative path",
    )
    return part


def safe_path(root, name):
    part = relative_path(name)
    path = root.joinpath(*part.parts)
    require(
        not any(item.is_symlink() for item in (path, *path.parents)),
        "retained artifact symlinks are forbidden",
    )
    require(path.resolve().is_relative_to(root.resolve()), "retained artifact path escapes root")
    return path


def full_commit(value):
    require(
        isinstance(value, str) and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value),
        "expected a full lowercase Git commit identity",
    )
    return value


def digest_string(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "invalid SHA-256 binding"
    )
    return value


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    require(result.returncode == 0, "required pinned Git object is unavailable: " + " ".join(args))
    return result.stdout


def git_blob(repo, commit, name):
    full_commit(commit)
    relative_path(name)
    return git(repo, "show", f"{commit}:{name}")


def declared_absolute(value):
    """Normalize host-path declarations lexically, never resolve or open them."""
    require(isinstance(value, str) and value, "missing original host path declaration")
    windows = PureWindowsPath(value)
    if windows.is_absolute():
        require(".." not in windows.parts, "noncanonical original Windows path declaration")
        return windows.as_posix().casefold()
    posix = PurePosixPath(value)
    require(posix.is_absolute() and ".." not in posix.parts, "original host path is not absolute")
    return posix.as_posix()


def verify_git_bindings(
    repo, protocol, started, protocol_digest, expected_source, expected_protocol
):
    """Validate immutable source/protocol objects; never inspect host worktrees."""
    source = protocol.get("source")
    require(isinstance(source, dict), "protocol has no source declaration")
    source_commit, protocol_commit = full_commit(expected_source), full_commit(expected_protocol)
    require(
        source.get("commit") == source_commit and started.get("protocol_commit") == protocol_commit,
        "source/protocol commit does not match explicitly expected pins",
    )
    for commit in (source_commit, protocol_commit):
        git(repo, "cat-file", "-e", commit + "^{commit}")
    protocol_path = protocol.get("protocol_git_path")
    committed_protocol = git_blob(repo, protocol_commit, protocol_path)
    require(
        sha(committed_protocol) == protocol_digest,
        "retained protocol differs from pinned committed blob",
    )
    git(repo, "merge-base", "--is-ancestor", source_commit, protocol_commit)
    declarations = source.get("files")
    require(
        isinstance(declarations, dict) and REQUIRED_SOURCES <= set(declarations),
        "protocol omits required frozen source bindings",
    )
    auditor_bytes = None
    for name, declaration in sorted(declarations.items()):
        relative_path(name)
        require(isinstance(declaration, dict), "invalid source file declaration")
        expected_sha = digest_string(declaration.get("sha256"))
        require(
            type(declaration.get("bytes")) is int and declaration["bytes"] >= 0,
            "invalid source byte length",
        )
        blob = git_blob(repo, source_commit, name)
        require(
            sha(blob) == expected_sha and len(blob) == declaration["bytes"],
            f"pinned source blob mismatch: {name}",
        )
        if name == AUDITOR_PATH:
            auditor_bytes = blob
    require(auditor_bytes is not None, "verified frozen auditor source is unavailable")
    runtime = protocol.get("runtime")
    require(
        isinstance(runtime, dict)
        and runtime.get("framework_version") == runtime.get("distribution_version") == "2.1.1",
        "recorded framework runtime is not declared 2.1.1",
    )
    digest_string(runtime.get("python_sha256"))
    declared_absolute(runtime.get("python_executable"))
    declared_absolute(runtime.get("framework_path"))
    runtime_files = runtime.get("runtime_file_sha256")
    require(
        isinstance(runtime_files, dict) and runtime_files,
        "recorded framework file inventory is missing",
    )
    source_package = {
        name.removeprefix("src/consequa_x/")
        for name in declarations
        if name.startswith("src/consequa_x/")
    }
    require(
        set(runtime_files) <= source_package,
        "recorded runtime has files absent from pinned package source",
    )
    for name, digest in runtime_files.items():
        relative_path(name)
        digest_string(digest)
        require(
            declarations[f"src/consequa_x/{name}"]["sha256"] == digest,
            f"recorded installed-framework hash differs from pinned source: {name}",
        )
    timestamp = git(repo, "show", "-s", "--format=%ct", protocol_commit)
    try:
        committed_at = int(timestamp)
        started_at = datetime.fromisoformat(started["started_utc"].replace("Z", "+00:00"))
        require(
            started_at.tzinfo is not None and started_at.utcoffset() is not None,
            "retained collection-start timestamp lacks a timezone",
        )
        require(
            0 <= committed_at <= started_at.timestamp(),
            "protocol Git timestamp postdates declared collection start",
        )
    except (TypeError, ValueError, OverflowError, AttributeError) as error:
        raise ValueError("invalid protocol/start timestamp binding: " + str(error)) from error
    return auditor_bytes, {
        "source_commit": source_commit,
        "protocol_commit": protocol_commit,
        "protocol_git_path": protocol_path,
        "protocol_committed_at_unix": committed_at,
        "declared_collection_started_utc": started["started_utc"],
        "source_files_verified_from_git": len(declarations),
        "recorded_framework_files_crosschecked_to_source": len(runtime_files),
        "frozen_auditor_sha256": declarations[AUDITOR_PATH]["sha256"],
    }


def verify_retained_claim(repo, protocol, started, started_bytes, protocol_digest, claim_file=None):
    require(
        started.get("protocol_sha256") == protocol_digest and started.get("retry_allowed") is False,
        "retained start/protocol/no-rerun declaration mismatch",
    )
    require(
        started.get("source_commit") == protocol["source"]["commit"],
        "retained start/source commit mismatch",
    )
    root = declared_absolute(protocol["source"]["root"])
    canonical = root.rstrip("/") + f"/output/.recovery-run-claims/{protocol_digest}.json"
    require(
        declared_absolute(started.get("canonical_claim_path")) == canonical,
        "retained canonical-claim path declaration differs from source/hash binding",
    )
    declared_absolute(started.get("output"))
    declared_absolute(started.get("protocol_path"))
    candidate = (
        Path(claim_file).absolute()
        if claim_file is not None
        else repo / "output/.recovery-run-claims" / f"{protocol_digest}.json"
    )
    verified = False
    if claim_file is not None or candidate.exists():
        require(
            candidate.is_file() and not candidate.is_symlink(),
            "retained public claim copy is unavailable/unsafe",
        )
        require(
            candidate.read_bytes() == started_bytes,
            "retained public claim copy differs from started.json",
        )
        verified = True
    return {
        "retained_started_sha256": sha(started_bytes),
        "retained_claim_copy_verified": verified,
        "retained_claim_copy_sha256": sha(started_bytes) if verified else None,
        "original_absolute_locations_checked": False,
        "live_claim_files_checked": False,
        "first_run_exclusivity_proven": False,
    }


def load_verified_auditor(data, expected_sha, source_commit):
    """Import exact checked Git bytes; never substitute or patch its functions."""
    require(sha(data) == digest_string(expected_sha), "frozen auditor hash mismatch before import")
    code = data.decode("utf-8-sig")
    tree = ast.parse(code, filename=AUDITOR_PATH)
    forbidden = ("consequa", "research", "world", "controllers", "run_recovery_controller_study")
    for node in ast.walk(tree):
        modules = (
            [item.name for item in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        require(
            not any(name.startswith(forbidden) for name in modules),
            "frozen auditor imports prohibited study/framework code",
        )
    module = types.ModuleType("verified_frozen_recovery_auditor")
    module.__file__ = f"git-object:{full_commit(source_commit)}:{AUDITOR_PATH}"
    exec(compile(tree, module.__file__, "exec"), module.__dict__)
    return module


def audit_retained_semantics(auditor, root, protocol, receipt, manifest):
    """Explicit portable orchestration over unmodified frozen semantic functions.

    The public entry point separately enforces the frozen full plan. Keeping
    this loop separate also permits small synthetic failure-accounting tests.
    """
    files = manifest["files"]
    expected_trials = {f"trials/{slot['trial_id']}.json.gz" for slot in protocol["schedule"]}
    require(
        {name for name in files if name.startswith("trials/")} == expected_trials,
        "trial artifact IDs do not exactly match frozen plan",
    )
    require(
        {name for name in files if "/" not in name}
        == {"started.json", "protocol.json", "summary.json", "analysis-rows.jsonl"},
        "unexpected/missing top-level collection artifacts",
    )
    analysis = [
        json_bytes(line.encode("utf-8"), "analysis row")
        for line in (root / "analysis-rows.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    require(len(analysis) == len(protocol["schedule"]), "analysis row denominator mismatch")
    compact, public_by_pair = [], {}
    databases_checked, missing_failed, database_paths = 0, [], set()
    with tempfile.TemporaryDirectory(prefix="portable-recovery-audit-") as temporary:
        db_path = Path(temporary) / "snapshot.sqlite"
        for index, slot in enumerate(protocol["schedule"]):
            trial_path = f"trials/{slot['trial_id']}.json.gz"
            trial = json_bytes(
                gzip.decompress(safe_path(root, trial_path).read_bytes()), "retained trial"
            )
            require(
                all(trial.get(key) == value for key, value in slot.items()),
                "retained trial identity differs from plan",
            )
            require(
                trial.get("status") in ("completed", "failed"),
                "planned failure was dropped/relabelled",
            )
            if "database" in trial:
                packed = trial["database"]["path"]
                require(
                    packed == f"databases/{slot['trial_id']}.sqlite.gz" and packed in files,
                    "trial database path is unplanned",
                )
                raw = gzip.decompress(safe_path(root, packed).read_bytes())
                require(
                    sha(raw) == trial["database"]["sha256_uncompressed"],
                    "uncompressed SQLite hash mismatch",
                )
                db_path.write_bytes(raw)
                database_paths.add(packed)
                require("public_case" in trial, "retained SQLite snapshot lacks public declaration")
                metrics = auditor.audit_trial(trial, db_path)
                databases_checked += 1
            else:
                require(trial["status"] == "failed", "completed trial lost its SQLite snapshot")
                metrics = auditor._failed_metrics(trial)
                missing_failed.append(slot["trial_id"])
            if "public_case" in trial:
                pair, declaration = (slot["case_id"], slot["seed"]), trial["public_case"]
                require(
                    pair not in public_by_pair or public_by_pair[pair] == declaration,
                    "public case/capabilities differ between paired arms",
                )
                public_by_pair[pair] = declaration
            row = {**slot, "status": trial["status"], "metrics": metrics}
            require(
                analysis[index] == row,
                "analysis row differs from independently audited retained trial",
            )
            compact.append(row)
            if (index + 1) % 1000 == 0:
                print(
                    json.dumps(
                        {"portable_audited_slots": index + 1, "planned": len(protocol["schedule"])}
                    ),
                    flush=True,
                )
    require(
        {name for name in files if name.startswith("databases/")} == database_paths,
        "database artifact IDs do not match retained declarations",
    )
    require(
        set(files)
        == expected_trials
        | database_paths
        | {"started.json", "protocol.json", "summary.json", "analysis-rows.jsonl"},
        "unplanned retained study artifact",
    )
    computed, recorded = (
        auditor.recompute_summary(compact, protocol),
        load_json(root / "summary.json"),
    )
    require(
        recorded.get("protocol_sha256") == receipt["protocol_sha256"],
        "summary protocol binding mismatch",
    )
    require(
        type(recorded.get("collection_seconds")) in (int, float)
        and math.isfinite(recorded["collection_seconds"])
        and recorded["collection_seconds"] >= 0,
        "invalid collection duration declaration",
    )
    auditor._same(
        computed,
        {
            key: value
            for key, value in recorded.items()
            if key not in {"protocol_sha256", "collection_seconds"}
        },
    )
    for key in ("planned_trials", "completed_trials", "failed_trials"):
        require(receipt[key] == computed[key], f"completion denominator mismatch: {key}")
    return computed, {
        "sqlite_snapshots_queried": databases_checked,
        "failed_slots_without_databases": missing_failed,
    }


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def audit_study(
    study_dir,
    repo_root,
    output_dir,
    *,
    expected_source=SOURCE_COMMIT,
    expected_protocol=PROTOCOL_COMMIT,
    expected_protocol_sha256=PROTOCOL_SHA256,
    claim_file=None,
):
    root, repo, output = (
        Path(study_dir).resolve(),
        Path(repo_root).resolve(),
        Path(output_dir).resolve(),
    )
    require(
        not output.exists() and not output.is_relative_to(root),
        "portable audit output must be a fresh separate directory",
    )
    receipt, manifest = (
        load_json(root / "completion-receipt.json"),
        load_json(root / "manifest.json"),
    )
    require(
        receipt.get("complete") is True and manifest.get("complete") is True,
        "collection is not declared complete",
    )
    require(
        sha((root / "manifest.json").read_bytes()) == receipt.get("manifest_sha256"),
        "completion/manifest hash mismatch",
    )
    files = manifest.get("files")
    require(
        isinstance(files, dict) and "protocol.json" in files, "manifest lacks a protocol binding"
    )
    for name, digest in files.items():
        relative_path(name)
        digest_string(digest)
    protocol_bytes = safe_path(root, "protocol.json").read_bytes()
    protocol_digest = digest_string(expected_protocol_sha256)
    require(
        sha(protocol_bytes)
        == protocol_digest
        == receipt.get("protocol_sha256")
        == files["protocol.json"],
        "retained protocol does not match expected immutable protocol hash",
    )
    protocol, started_bytes = (
        json_bytes(protocol_bytes, "protocol"),
        safe_path(root, "started.json").read_bytes(),
    )
    started = json_bytes(started_bytes, "retained start")
    require(
        "started.json" in files and sha(started_bytes) == files["started.json"],
        "retained start is not manifest bound",
    )
    for key in ("no_retries_or_replacements", "source_and_runtime_final_recheck"):
        require(receipt.get(key) is True, f"completion receipt lacks required declaration: {key}")
    require(
        receipt.get("new_model_calls") == receipt.get("external_application_calls") == 0,
        "completion receipt declares prohibited new calls",
    )
    auditor_bytes, bindings = verify_git_bindings(
        repo, protocol, started, protocol_digest, expected_source, expected_protocol
    )
    claims = verify_retained_claim(
        repo, protocol, started, started_bytes, protocol_digest, claim_file
    )
    auditor = load_verified_auditor(
        auditor_bytes, bindings["frozen_auditor_sha256"], bindings["source_commit"]
    )
    checked_receipt, checked_manifest = auditor.audit_artifact_manifest(root)
    require(
        checked_receipt == receipt and checked_manifest == manifest,
        "artifact metadata changed during verification",
    )
    auditor._validate_plan(protocol)
    computed, lifecycle = audit_retained_semantics(auditor, root, protocol, receipt, manifest)
    result = {
        "schema": SCHEMA,
        "passed": True,
        "verification_scope": "retained_artifact_semantics_only",
        "original_host_verified": False,
        "first_run_exclusivity_proven": False,
        "source_or_provider_authenticated": False,
        "study_rerun": False,
        "protocol_sha256": protocol_digest,
        "manifest_sha256": receipt["manifest_sha256"],
        "completion_receipt_sha256": sha((root / "completion-receipt.json").read_bytes()),
        "portable_audit_script_sha256": sha(Path(__file__).read_bytes()),
        "artifacts_hashed": len(files),
        "planned_trials": computed["planned_trials"],
        "completed_trials": computed["completed_trials"],
        "failed_trials": computed["failed_trials"],
        **bindings,
        **claims,
        **lifecycle,
        "omitted_original_host_checks": OMITTED_HOST_CHECKS,
        "limitations": LIMITATIONS,
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "recomputed-summary.json", computed)
    write_json(output / "portable-audit-receipt.json", result)
    write_json(
        output / "verified-source-bindings.json",
        {
            "source_commit": bindings["source_commit"],
            "protocol_commit": bindings["protocol_commit"],
            "protocol_sha256": protocol_digest,
            "source_files": protocol["source"]["files"],
            "recorded_runtime": protocol["runtime"],
        },
    )
    (output / "README.md").write_text(
        "# Portable retained-artifact recheck\n\n"
        "This receipt is deliberately separate from the original-host audit. It recomputes retained trial/SQLite semantics "
        "using the exact hash-verified frozen auditor source extracted from pinned Git objects, with no study rerun or framework import. "
        "The collection's original paths and binary/venv need not exist here.\n\n"
        "A pass concerns saved-artifact consistency only. Read omitted_original_host_checks and limitations in portable-audit-receipt.json. "
        "No authentication, live-host identity, first-run exclusivity, new external replication, or independent-human validation is asserted. "
        "The clone must contain both pinned Git commits and all source/protocol blobs; a shallow clone may need those objects fetched. "
        "An optional --claim-file supplies a publicly retained claim copy; otherwise a clone-local output/.recovery-run-claims/HASH.json "
        "is checked if present. Absence is explicit in the receipt and never replaced by a claim of live canonical-file verification.\n",
        encoding="utf-8",
    )
    inventory = {
        path.relative_to(output).as_posix(): sha(path.read_bytes())
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    write_json(
        output / "manifest.json",
        {
            "schema": SCHEMA,
            "complete": True,
            "files": inventory,
            "portable_audit_script_sha256": result["portable_audit_script_sha256"],
            "frozen_auditor_sha256": bindings["frozen_auditor_sha256"],
            "protocol_sha256": protocol_digest,
        },
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--claim-file",
        type=Path,
        help="optional publicly retained claim copy; never the required live original location",
    )
    parser.add_argument("--expected-source-commit", default=SOURCE_COMMIT)
    parser.add_argument("--expected-protocol-commit", default=PROTOCOL_COMMIT)
    parser.add_argument("--expected-protocol-sha256", default=PROTOCOL_SHA256)
    args = parser.parse_args(argv)
    try:
        result = audit_study(
            args.study_dir,
            args.repo_root,
            args.output,
            expected_source=args.expected_source_commit,
            expected_protocol=args.expected_protocol_commit,
            expected_protocol_sha256=args.expected_protocol_sha256,
            claim_file=args.claim_file,
        )
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, sqlite3.DatabaseError) as error:
        parser.exit(2, f"Portable artifact audit refused: {error}\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
