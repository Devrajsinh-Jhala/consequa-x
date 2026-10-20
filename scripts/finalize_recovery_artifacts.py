"""Seal already collected recovery bytes after absent terminal packaging.

This separately disclosed postcollection operation never executes a world,
controller, framework, or model, and never regenerates an existing artifact.
The unchanged frozen semantic auditor must subsequently pass.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


PROTOCOL_SHA = "b5c6a06bf1d758678e4d9890aa66872d4036634e2a4a4fd89626bd710bbc5aaa"
SOURCE_COMMIT = "22e88498cff0e2afd1549803fb4d9645902e74b9"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def load(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"nonfinite JSON: {value}")

    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "symlink in retained study")
        if path.is_file():
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = {
                "sha256": sha(data),
                "bytes": len(data),
                "mtime_ns_advisory": path.stat().st_mtime_ns,
            }
    return result


def write_new(path, data):
    with Path(path).open("xb") as stream:
        stream.write(data)


def finalize(study, frozen_root, output):
    root, frozen_root, output = (Path(path).resolve() for path in (study, frozen_root, output))
    require(
        not output.exists() and not output.is_relative_to(root),
        "finalization record must be fresh and separate",
    )
    require(
        not (root / "manifest.json").exists() and not (root / "completion-receipt.json").exists(),
        "one or both terminal files already exist; do not overwrite or repair them",
    )
    protocol_bytes = (root / "protocol.json").read_bytes()
    require(sha(protocol_bytes) == PROTOCOL_SHA, "unexpected protocol")
    protocol = load(protocol_bytes)
    require(
        protocol["source"]["commit"] == SOURCE_COMMIT
        and Path(protocol["source"]["root"]).resolve() == frozen_root,
        "unexpected frozen source identity",
    )
    require(
        subprocess.check_output(["git", "-C", str(frozen_root), "rev-parse", "HEAD"])
        .decode()
        .strip()
        == SOURCE_COMMIT,
        "frozen HEAD changed",
    )
    source = frozen_root / "scripts/audit_recovery_controller_study.py"
    require(
        sha(source.read_bytes())
        == protocol["source"]["files"]["scripts/audit_recovery_controller_study.py"]["sha256"],
        "frozen auditor differs",
    )
    spec = importlib.util.spec_from_file_location("frozen_packaging_checks", source)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    started = load((root / "started.json").read_bytes())
    audit._validate_plan(protocol)
    source_binding = audit._verify_source_runtime(protocol)
    protocol_binding = audit._verify_protocol_commit(protocol, started, PROTOCOL_SHA)
    claim_binding = audit._verify_run_claim(
        protocol, started, root / "started.json", root, PROTOCOL_SHA
    )
    # This is a host packaging check, not independent evidence of original process termination.
    process_probe = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'run_recovery_controller_study[.]py' }).Count",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    require(
        process_probe.stdout.strip() == "0",
        "matching collector process is still present or process check is inconclusive",
    )
    original = inventory(root)
    expected = {"started.json", "protocol.json", "analysis-rows.jsonl", "summary.json"}
    for slot in protocol["schedule"]:
        expected.update(
            {f"trials/{slot['trial_id']}.json.gz", f"databases/{slot['trial_id']}.sqlite.gz"}
        )
    require(
        set(original) == expected, "original inventory is not the full exact scheduled collection"
    )
    rows = [load(line) for line in (root / "analysis-rows.jsonl").read_bytes().splitlines()]
    require(len(rows) == len(protocol["schedule"]), "journal is incomplete")
    for index, (slot, compact) in enumerate(zip(protocol["schedule"], rows)):
        require(
            all(compact.get(key) == value for key, value in slot.items()),
            "journal schedule/order differs",
        )
        require(compact.get("status") in {"completed", "failed"}, "invalid retained disposition")
        trial_name = f"trials/{slot['trial_id']}.json.gz"
        raw = load(gzip.decompress((root / trial_name).read_bytes()))
        require(
            all(raw.get(key) == value for key, value in slot.items()), "raw trial schedule differs"
        )
        require(
            raw["status"] == compact["status"] and raw["metrics"] == compact["metrics"],
            "raw trial/journal differ",
        )
        db_name = f"databases/{slot['trial_id']}.sqlite.gz"
        require(raw["database"]["path"] == db_name, "database/trial identity differs")
        require(
            sha(gzip.decompress((root / db_name).read_bytes()))
            == raw["database"]["sha256_uncompressed"],
            "compressed database integrity differs",
        )
        if (index + 1) % 2000 == 0:
            print(json.dumps({"retained_slots_checked": index + 1}), flush=True)
    summary = load((root / "summary.json").read_bytes())
    require(summary["protocol_sha256"] == PROTOCOL_SHA, "summary protocol differs")
    computed = audit.recompute_summary(rows, protocol)
    audit._same(
        computed,
        {
            key: value
            for key, value in summary.items()
            if key not in {"protocol_sha256", "collection_seconds"}
        },
    )
    require(
        original == inventory(root),
        "existing retained bytes/timestamps changed during finalization checks",
    )
    require(
        subprocess.check_output(["git", "-C", str(frozen_root), "rev-parse", "HEAD"])
        .decode()
        .strip()
        == SOURCE_COMMIT,
        "frozen HEAD changed during finalization",
    )
    audit._verify_source_runtime(protocol)
    audit._verify_protocol_commit(protocol, started, PROTOCOL_SHA)
    audit._verify_run_claim(protocol, started, root / "started.json", root, PROTOCOL_SHA)
    process_recheck = subprocess.run(process_probe.args, capture_output=True, check=True, text=True)
    require(process_recheck.stdout.strip() == "0", "collector appeared during packaging checks")
    stamp = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema": protocol["schema"],
        "complete": True,
        "files": {name: record["sha256"] for name, record in original.items()},
    }
    manifest_bytes = encoded(manifest)
    output.mkdir(parents=True, exist_ok=False)
    original_bytes = encoded(
        {"files": original, "mtime_scope": "advisory filesystem metadata only"}
    )
    write_new(output / "original-inventory.json", original_bytes)
    shutil.copyfile(__file__, output / "finalizer.source.py")
    record = {
        "schema": "recovery-postcollection-artifact-finalization-v1",
        "finalized_utc": stamp,
        "source_commit": SOURCE_COMMIT,
        "finalizer_runtime": {
            "python_executable": str(Path(sys.executable).resolve()),
            "python_executable_sha256": sha(Path(sys.executable).read_bytes()),
            "python_version": sys.version,
            "argv": sys.argv,
            "study_root": str(root),
            "frozen_root": str(frozen_root),
            "finalization_output": str(output),
        },
        "protocol_sha256": PROTOCOL_SHA,
        "original_inventory_sha256": sha(original_bytes),
        "finalizer_sha256": sha(Path(__file__).read_bytes()),
        "new_study_manifest_sha256": sha(manifest_bytes),
        "retained_files": len(original),
        "planned_trials": len(rows),
        "completed_trials": computed["completed_trials"],
        "failed_trials": computed["failed_trials"],
        "original_runner_completion_receipt_present": False,
        "original_runner_exit_status_available": False,
        "termination_cause": "unknown; terminal packaging absent when session work resumed",
        "collector_processes_observed_before_packaging": 0,
        "world_execution_performed": False,
        "new_model_calls": 0,
        "new_external_application_calls": 0,
        "existing_artifacts_regenerated": False,
        "original_bytes_unchanged_during_checks": True,
        "recheck_utc": stamp,
        "source_binding": source_binding,
        "protocol_binding": protocol_binding,
        "claim_binding": claim_binding,
        "deviation": "All scheduled raw trials, database snapshots, journal rows, and summary were retained, but the original runner emitted no terminal manifest/receipt. This separate operation creates only those missing packaging files; it does not resume or rerun measured worlds. This is a disclosed packaging deviation from the no-resume prospective protocol, not uninterrupted or fully protocol-conformant runner completion.",
        "required_followup": "The unchanged frozen independent semantic auditor must pass before results are reported.",
        "limitations": [
            "Hashes here start at the postcollection inventory, not a cryptographic attestation of original execution or no earlier tampering.",
            "No original exit status or precise termination cause is available; filesystem times are advisory.",
            "Canonical claims and saved logs cannot prove absence of off-record runs, deleted records, or external activity.",
            "The true recheck is this postcollection host recheck; no original process-completion attestation is invented.",
        ],
    }
    record_bytes = encoded(record)
    write_new(output / "finalization-record.json", record_bytes)
    receipt = {
        "schema": protocol["schema"],
        "complete": True,
        "completed_utc": stamp,
        "protocol_sha256": PROTOCOL_SHA,
        "manifest_sha256": sha(manifest_bytes),
        "planned_trials": len(rows),
        "completed_trials": computed["completed_trials"],
        "failed_trials": computed["failed_trials"],
        "new_model_calls": 0,
        "external_application_calls": 0,
        "no_retries_or_replacements": True,
        "source_and_runtime_final_recheck": True,
        "final_recheck_utc": stamp,
        "completion_mode": "postcollection_artifact_finalization",
        "original_runner_completion_receipt_present": False,
        "world_execution_performed_during_finalization": False,
        "postcollection_finalization_record_sha256": sha(record_bytes),
    }
    require(
        not (root / "manifest.json").exists() and not (root / "completion-receipt.json").exists(),
        "terminal files appeared concurrently",
    )
    write_new(root / "manifest.json", manifest_bytes)
    receipt_bytes = encoded(receipt)
    write_new(root / "completion-receipt.json", receipt_bytes)
    write_new(output / "completion-receipt.source.json", receipt_bytes)
    (output / "README.md").write_text(
        "# Postcollection packaging deviation\n\n"
        + record["deviation"]
        + "\n\n"
        + record["required_followup"]
        + "\n",
        encoding="utf-8",
    )
    files = {
        path.relative_to(output).as_posix(): sha(path.read_bytes())
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    write_new(
        output / "manifest.json",
        encoded({"complete": True, "schema": record["schema"], "files": files}),
    )
    return {
        "packaging_created": True,
        "completed_trials": computed["completed_trials"],
        "failed_trials": computed["failed_trials"],
        "manifest_sha256": sha(manifest_bytes),
        "finalization_record_sha256": sha(record_bytes),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", required=True, type=Path)
    parser.add_argument("--frozen-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(finalize(args.study_dir, args.frozen_root, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
