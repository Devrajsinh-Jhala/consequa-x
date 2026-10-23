"""Copy and seal an interrupted excluded-development prefix without grading it.

This auxiliary preservation tool never imports benchmark or SDK code, contacts a
server, settles a budget, modifies an input, or controls a process. It deliberately
does not manufacture the missing worker, parent, native-grade, or observer terminal
records. A current host boot-time observation cannot establish why work stopped.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


EPISODE = Path("output/limbo-development-2026-10-22/guard-migration-001")
OBSERVER = Path("output/limbo-resource-observer-2026-10-22")
RUNTIME = Path("output/limbo-runtime-2026-10-22")
RESERVATION = Path("output/limbo-development-2026-10-22/native-ledger/reservation-001.json")
SETTLEMENT = RESERVATION.with_name("settlement-001.json")
DEFAULT_OUTPUT = Path("output/limbo-interruption-2026-10-23")


def binding(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": Path(path).stat().st_size}


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def confined(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Input paths must be confined relative paths")
    result = root / relative
    if result.is_symlink() or root not in result.resolve().parents:
        raise ValueError("Symlinks and paths outside the research root are refused")
    return result


def inventory(root, directory):
    result = []
    for path in sorted(confined(root, directory).rglob("*")):
        if path.is_symlink():
            raise ValueError("A preserved input tree contains a symlink")
        if path.is_file():
            relative = path.relative_to(root)
            confined(root, relative)
            result.append(relative)
    return result


def jsonl_prefix(path):
    rows = []
    invalid_line = None
    for number, raw in enumerate(path.read_bytes().splitlines(), 1):
        try:
            rows.append(json.loads(raw))
        except (ValueError, UnicodeDecodeError):
            invalid_line = number
            break
    return rows, invalid_line


def preserve(root, output, host_observation):
    root = Path(root).resolve()
    output = confined(root, output)
    if output.exists():
        raise FileExistsError("A new output directory is required; originals are never updated")
    if confined(root, SETTLEMENT).exists():
        raise ValueError("Reservation 001 already has a settlement; this preservation policy is stale")
    directories = (EPISODE, OBSERVER, RUNTIME)
    before = {str(directory): inventory(root, directory) for directory in directories}
    config = json.loads(confined(root, EPISODE / "worker-config.json").read_text(encoding="utf-8"))
    sources = config["protocol"]["sources"]
    for relative, expected in sources.items():
        if not relative.endswith(".py") or not relative.startswith(("research/limbo_agent/", "research/native_agent/", "scripts/")):
            raise ValueError("Unexpected execution source path")
        if binding(confined(root, relative)) != expected:
            raise ValueError(f"Execution source no longer matches interrupted run: {relative}")
    inputs = sorted({path for paths in before.values() for path in paths} | {
        RESERVATION,
        Path("scripts/observe_limbo_resources.py"),
        Path("scripts/observe_native_resources.py"),
        Path("scripts/preserve_interrupted_limbo_development.py"),
        *map(Path, sources),
    })
    # Capture every input before any copy, then verify the entire set after all
    # copies. This is a stable snapshot check, not a claim of atomic filesystem I/O.
    originals = {str(path).replace("\\", "/"): {
        **binding(confined(root, path)), "mtime_ns": confined(root, path).stat().st_mtime_ns
    } for path in inputs}
    output.mkdir(parents=True, exist_ok=False)
    for relative in inputs:
        target = output / "copies" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(confined(root, relative), target)
        key = str(relative).replace("\\", "/")
        expected = {key_: originals[key][key_] for key_ in ("bytes", "sha256")}
        if binding(target) != expected:
            raise ValueError(f"Copied bytes differ: {key}")
    for relative in inputs:
        key = str(relative).replace("\\", "/")
        actual = {**binding(confined(root, relative)), "mtime_ns": confined(root, relative).stat().st_mtime_ns}
        if actual != originals[key]:
            raise ValueError(f"Input changed during preservation: {key}")
    if any(inventory(root, directory) != before[str(directory)] for directory in directories):
        raise ValueError("An input tree inventory changed during preservation")
    if confined(root, SETTLEMENT).exists():
        raise ValueError("A budget settlement appeared during preservation")
    copies = output / "copies"
    episode = copies / EPISODE
    journal, invalid_journal_line = jsonl_prefix(episode / "model/model-calls.jsonl")
    framework, invalid_framework_line = jsonl_prefix(episode / "framework.jsonl")
    samples, invalid_resource_line = jsonl_prefix(copies / OBSERVER / "resources.jsonl")
    dispatches = [row for row in journal if row.get("event") == "before_dispatch"]
    returns = [row for row in journal if row.get("event") == "request_return"]
    invocations = []
    for row in dispatches:
        invocation = row["invocation"]
        stem = f"{invocation:04d}"
        terminal_path = episode / "model" / f"{stem}-terminal.json"
        terminal = json.loads(terminal_path.read_text(encoding="utf-8")) if terminal_path.exists() else None
        invocations.append({
            "invocation": invocation, "before_dispatch_recorded": True,
            "raw_request_present": (episode / "model" / f"{stem}-request.bin").is_file(),
            "raw_response_present": (episode / "model" / f"{stem}-response.bin").is_file(),
            "transport_terminal_present": terminal is not None,
            "transport_terminal": terminal,
            "server_acceptance_from_before_dispatch_alone": "unknown",
            "missing_response_or_usage_is_not_zero": True,
        })
    absence = {
        "episode/" + name: not (episode / name).exists()
        for name in ("worker-terminal.json", "parent-terminal.json", "native-result.json", "world.json", "manifest.json")
    }
    absence.update({
        "observer/" + name: not (copies / OBSERVER / name).exists()
        for name in ("terminal-summary.json", "manifest.json")
    })
    reservation = json.loads((copies / RESERVATION).read_text(encoding="utf-8"))
    report = {
        "schema": "conseqax-limbo-interrupted-development-preservation-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Copy-only post-interruption preservation of an excluded-development prefix, not an episode audit or grade",
        "host_observation": host_observation,
        "interruption_cause": "unknown; missing terminal records and current boot observation do not establish cause",
        "originals_unchanged_during_copy": True,
        "original_file_count": len(originals),
        "input_directories": [str(path).replace("\\", "/") for path in directories],
        "execution_sources_match_saved_worker_config": True,
        "terminal_record_absence": absence,
        "native_grade": None,
        "grade_available": False,
        "native_replay_performed": False,
        "new_native_terminal_or_world_invented": False,
        "new_model_requests": 0,
        "network_requests": 0,
        "process_control_actions": 0,
        "model_journal_prefix": {
            "complete_lines": len(journal), "first_invalid_line": invalid_journal_line,
            "before_dispatch_count": len(dispatches),
            "request_return_count": len(returns),
            "request_return_usage": [{"invocation": row["invocation"], "usage": row.get("usage")} for row in returns],
            "invocations": invocations,
            "total_completed_generations_and_tokens": "unknown; only the saved returned prefix is known",
        },
        "framework_journal_prefix": {
            "complete_lines": len(framework), "first_invalid_line": invalid_framework_line,
            "package_receipts_recorded": sum(row.get("operation") == "package_receipt" and row.get("phase") == "return" for row in framework),
        },
        "resource_journal_prefix": {
            "complete_lines": len(samples), "first_invalid_line": invalid_resource_line,
            "first_recorded_utc": samples[0].get("recorded_utc") if samples else None,
            "last_recorded_utc": samples[-1].get("recorded_utc") if samples else None,
            "prefix_is_not_a_complete_observation_interval": True,
        },
        "budget": {
            "reservation_file": str(RESERVATION).replace("\\", "/"),
            "reserved": reservation["reserved"], "remaining_held": reservation["reserved"],
            "settlement_present": False, "settlement_created": False, "released": 0,
            "reason": "Complete terminal accounting is absent; the full reservation remains held, irrespective of observed prefix calls",
        },
        "limitations": [
            "This new preservation manifest seals copied prefixes after interruption; it is not the missing contemporaneous episode or observer manifest.",
            "No native grade, final state, late flush, complete token cost, successful SDK path, or completed fault-handling claim follows from these prefixes.",
            "A before_dispatch journal entry establishes a client-side attempt, not server acceptance or completion.",
            "Runtime logs are preserved verbatim, without reconstructing a native grade or interpreting missing responses as zero work.",
            "No GitHub Actions API or workflow is used by this helper.",
        ],
    }
    write_new(output / "preserved-inputs.json", originals)
    write_new(output / "preservation-report.json", report)
    text = (
        "# Interrupted LIMBO development evidence\n\n"
        "This copy-only bundle preserves the excluded guard-migration-001 prefix, its old resource observations, runtime records and logs, budget reservation, and matching execution sources. Original files were checked before and after copying and were not changed.\n\n"
        f"The saved journal contains {len(dispatches)} before-dispatch entries and {len(returns)} returned-response entries. A before-dispatch entry does not establish server acceptance. Missing response bytes, token counts, and work after the last saved prefix remain unknown.\n\n"
        "No worker or parent terminal, native result, final world, or original episode manifest has been reconstructed. There is no native grade or new replay. This bundle cannot satisfy development readiness and must never enter the official study denominator.\n\n"
        f"Reservation 001 remains fully held ({reservation['reserved']} calls); no settlement or release was written. The current boot-time observation records the host state when this bundle was created and does not establish the interruption's cause.\n\n"
        "`preserved-inputs.json` binds every original relative path, exact copied bytes, SHA-256, and original modification time. `manifest.json` binds this bundle's files. The preservation seal is post-interruption and does not replace missing contemporaneous terminal accounting. No model, network, benchmark, process-control, or GitHub Actions operation was performed.\n"
    )
    with (output / "README.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    files = {str(path.relative_to(output)).replace("\\", "/"): binding(path)
             for path in sorted(output.rglob("*")) if path.is_file()}
    write_new(output / "manifest.json", {"schema": "conseqax-preserved-prefix-manifest-v1", "files": files})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    import psutil
    boot_time = psutil.boot_time()
    observation = {
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "current_boot_time_epoch_seconds": boot_time,
        "current_boot_time_utc": datetime.fromtimestamp(boot_time, timezone.utc).isoformat(),
        "method": "psutil.boot_time(); no process enumeration, termination, or model requests",
    }
    report = preserve(args.root, args.output, observation)
    print(json.dumps({"output": str((args.root / args.output).resolve()),
                      "original_file_count": report["original_file_count"],
                      "before_dispatch_count": report["model_journal_prefix"]["before_dispatch_count"],
                      "request_return_count": report["model_journal_prefix"]["request_return_count"],
                      "native_grade_available": report["grade_available"],
                      "budget_held": report["budget"]["remaining_held"]}, sort_keys=True))


if __name__ == "__main__":
    main()
