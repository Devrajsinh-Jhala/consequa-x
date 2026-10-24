"""Preserve and audit a stopped official LIMBO matrix without resuming it.

The new archive is a post-collection copy seal, not a historical collector
terminal. Only originally sealed native returns receive offline replay/grades.
An unfinished episode and every unstarted slot retain unavailable outcomes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import sys


HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
HELPER = HERE.with_name("audit_limbo_portable.py")
_spec = importlib.util.spec_from_file_location("_limbo_portable_interruption_support", HELPER)
portable = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portable)
require, same, load = portable.require, portable.same, portable.load
binding, write_json = portable.binding, portable.write_json
SUPPORT = (
    "output/limbo-protocol-2026-10-24",
    "output/limbo-pipeline-2026-10-24",
    "output/limbo-pipeline-launch-2026-10-24",
    "output/limbo-prelaunch-2026-10-24",
    "output/limbo-resource-observer-2026-10-23",
    "output/limbo-runtime-2026-10-23",
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def inventory(root):
    """Exact file bytes; links and filesystem redirects are never copied."""
    root = Path(root).resolve()
    require(root.is_dir(), "Missing preservation input directory")
    result = {}
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Symbolic preservation input")
        if path.is_file():
            require(path.resolve().is_relative_to(root), "Preservation input escapes root")
            result[path.relative_to(root).as_posix()] = binding(path)
    return result


def check_claim(collection, value, protocol_path, commit):
    same(load(collection / "protocol.json"), value, "Original collection protocol differs")
    claim = load(collection / "claim.json")
    require(claim.get("protocol_commit") == commit
            and claim.get("protocol_sha256") == binding(protocol_path)["sha256"]
            and claim.get("retry_resume_replacement") is False,
            "Original one-shot claim differs")
    require(not (collection / "collection.json").exists()
            and not (collection / "manifest.json").exists(),
            "This helper requires an interrupted collection without a final collector seal")


def inspect_slots(collection, value):
    """Validate the contiguous saved prefix; never invent terminal receipts."""
    collection = Path(collection)
    allowed = {"claim.json", "protocol.json"}
    rows = []
    stopped = False
    partial_seen = False
    for planned in value["schedule"]:
        slot = planned["slot"]
        name = f"slot-{slot:03d}"
        directory = collection / name
        disposition = collection / f"disposition-{slot:03d}.json"
        if not directory.exists():
            require(not disposition.exists(), "Disposition exists without its slot directory")
            stopped = True
            rows.append((planned, "unstarted_interruption", None))
            continue
        require(not stopped and directory.is_dir() and not directory.is_symlink(),
                "Noncontiguous or symbolic started slot")
        allowed.add(name)
        same(load(directory / "worker-config.json"), {"protocol": value, "slot": planned},
             "Interrupted/complete worker configuration differs")
        if not disposition.exists():
            require(not partial_seen, "Multiple unfinished slots violate serial collection")
            require(not (directory / "manifest.json").exists()
                    and not (directory / "parent-terminal.json").exists()
                    and not (directory / "worker-terminal.json").exists()
                    and not (directory / "native-result.json").exists(),
                    "Partial slot contains a terminal or seal requiring explicit separate handling")
            partial_seen = True
            stopped = True
            rows.append((planned, "interrupted_terminal_unavailable", directory))
            continue
        require(not partial_seen, "Completed slot appears after interruption")
        allowed.add(disposition.name)
        receipt = load(disposition)
        for key in ("slot", "world_rank", "arm"):
            require(type(receipt.get(key)) is type(planned[key])
                    and receipt[key] == planned[key], "Completed disposition identity differs")
        require(receipt.get("directory") == name
                and receipt.get("status") == "child_returned"
                and type(receipt.get("exit_code")) is int and receipt["exit_code"] == 0,
                "Only sealed completed native returns can be replayed by this helper")
        same(load(directory / "parent-terminal.json"), receipt, "Original parent terminal differs")
        portable.sealed_manifest(directory)
        rows.append((planned, "sealed_native_return", directory))
    require({path.name for path in collection.iterdir()} == allowed,
            "Unplanned original collection artifact")
    require(stopped, "Collection is not interrupted")
    return rows


def preserve(source_root, native_root, protocol_path, commit, collection, archive,
             *, support=SUPPORT, backup_root=None):
    source_root, native_root = Path(source_root).resolve(), Path(native_root).resolve()
    protocol_path, collection = Path(protocol_path).resolve(), Path(collection).resolve()
    value = portable.verify_protocol_bytes(source_root, native_root, protocol_path, commit)
    check_claim(collection, value, protocol_path, commit)
    inspect_slots(collection, value)
    archive = Path(archive).resolve()
    require(not archive.is_relative_to(collection), "Archive must be outside original collection")
    inputs = {collection.relative_to(source_root).as_posix(): collection}
    for name in support:
        directory = source_root / name
        if directory.exists():
            inputs[name] = directory
    before = {name: inventory(directory) for name, directory in inputs.items()}
    backup = None
    if backup_root is not None:
        backup_root = Path(backup_root).resolve()
        for name, original in before.items():
            same(inventory(backup_root / name), original, "Read-only backup differs: " + name)
        backup = {"root": str(backup_root), "all_preserved_input_bytes_equal": True}
    archive.mkdir(parents=True, exist_ok=False)
    for name, directory in inputs.items():
        destination = archive / "preserved" / name
        shutil.copytree(directory, destination)
        same(inventory(destination), before[name], "Preserved copy differs: " + name)
    for name in value["sources"]:
        destination = archive / "frozen-scientific-source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(portable.safe_file(source_root, name), destination)
    for name in value["native"]["files"]:
        destination = archive / "frozen-native-source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(portable.safe_file(native_root, name), destination)
    for helper in (HERE, HELPER):
        destination = archive / "finalization-source" / helper.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(helper, destination)
    for name, directory in inputs.items():
        same(inventory(directory), before[name], "Original input changed during copy: " + name)
    record = {"schema": "conseqax-limbo-official-interruption-preservation-v1", "utc": utc(),
        "protocol_commit": commit, "protocol": binding(protocol_path),
        "original_collection_relative": collection.relative_to(source_root).as_posix(),
        "input_snapshots": before, "backup_comparison": backup,
        "scope": {"post_collection_copy_seal": True, "original_inputs_modified": False,
            "historical_collector_terminal_created": False, "interruption_cause_established": False,
            "historical_process_exit_codes_known": False, "model_calls": 0,
            "collection_resumed": False, "slots_replaced": False,
            "new_archive_manifest_does_not_retroactively_seal_the_original_run": True}}
    write_json(archive / "preservation.json", record)
    write_json(archive / "manifest.json", inventory(archive))
    portable.sealed_manifest(archive)
    return record


def valid_prefix(path):
    if not path.exists():
        return [], {"available": False, "complete_accounting": False}
    data = path.read_bytes()
    rows = []
    error = None
    for number, line in enumerate(data.splitlines(), 1):
        try:
            item = json.loads(line)
            require(type(item) is dict, "Journal row is not an object")
            rows.append(item)
        except (ValueError, UnicodeDecodeError) as exc:
            error = {"line": number, "type": type(exc).__name__}
            break
    return rows, {"available": True, "valid_prefix_records": len(rows),
        "trailing_newline": not data or data.endswith(b"\n"), "first_invalid": error,
        "complete_accounting": False,
        "events": dict(Counter(item.get("event", "unknown") for item in rows))}


def interrupted_row(directory, planned, value, auditor):
    base = {"slot": planned["slot"], "world_rank": planned["world_rank"], "arm": planned["arm"],
        "started": directory is not None, "operational": False, "grade_available": False,
        "execution_success": False, "native_grade": None, "audit_complete": False,
        "status": "unstarted_interruption" if directory is None else "interrupted_terminal_unavailable",
        "unavailable_reason": "No original native terminal/grade; no new run or reconstructed terminal"}
    if directory is None:
        return base
    directory = Path(directory)
    records, model_journal = valid_prefix(directory / "model/model-calls.jsonl")
    runtime_records, runtime_journal = valid_prefix(directory / "runtime.jsonl")
    terminals = sorted((directory / "model").glob("*-terminal.json"))
    known = []
    for number, terminal_path in enumerate(terminals, 1):
        require(terminal_path.name == f"{number:04d}-terminal.json", "Noncontiguous partial invocation terminals")
        # The saved input JSON is sorted and loses native dictionary insertion
        # order. Exact native wire reconstruction requires native orchestration;
        # doing that here would reconstruct an unfinished task. Check only raw
        # response/metering consistency, without claiming trajectory replay.
        terminal = check_partial_model_terminal(directory / "model", number)
        known.append(terminal)
    relevant = [row for row in records if row.get("event") != "client_ready"]
    endings = [index for index, row in enumerate(relevant)
               if row.get("event") in ("request_return", "request_error")]
    require(len(endings) == len(known), "Saved partial journal/terminal inventory differs")
    prefix_end = endings[-1] + 1 if endings else 0
    auditor.validate_model_journal(relevant[:prefix_end], known, value["limits"]["max_requests"])
    tail = relevant[prefix_end:]
    require(len(tail) <= 2 and (not tail or
        (tail[0].get("event") == "request_start" and tail[0].get("invocation") == len(known) + 1))
        and (len(tail) < 2 or (tail[1].get("event") == "before_dispatch"
            and tail[1].get("invocation") == len(known) + 1)),
        "Partial journal has more than one or an unordered unfinished invocation")
    starts = [row for row in records if row.get("event") == "request_start"]
    dispatches = [row for row in records if row.get("event") == "before_dispatch"]
    require(all(row.get("invocation") == number for number, row in enumerate(starts, 1)),
            "Partial model invocation order differs")
    require(all(row.get("dispatches") == 1 for row in dispatches), "Repeated partial generation send")
    require(len(dispatches) <= value["limits"]["max_requests"], "Partial dispatch allowance exceeded")
    require(len(known) <= len(starts), "Partial terminals exceed invocation starts")
    require(len({row.get("invocation") for row in dispatches}) == len(dispatches),
            "Duplicate partial generation invocation")
    for dispatch in dispatches:
        number = dispatch["invocation"]
        require(type(number) is int and 1 <= number <= len(starts), "Partial dispatch lacks its start")
        request = directory / "model" / f"{number:04d}-request.bin"
        require(request.is_file() and binding(request)["sha256"] == dispatch.get("request_sha256"),
                "Partial dispatch request bytes differ")
    missing = len(starts) - len(known)
    usage = {}
    for name in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
        amounts = [(item.get("usage") or {}).get(name, {}).get("value") for item in known]
        usage[name] = {"observed_prefix_total": sum(item for item in amounts if item is not None),
            "unknown_started_invocations": missing + sum(item is None for item in amounts),
            "unrecorded_work_possible": True, "complete_for_actual_episode": False}
    base["observed_journal_prefix"] = {"complete_accounting": False,
        "actual_work_may_exceed_saved_prefix": True, "model": model_journal, "runtime": runtime_journal,
        "model_invocations_started": len(starts), "generation_dispatch_attempts": len(dispatches),
        "saved_model_terminals_checked_for_raw_response_metering_consistency": len(known),
        "missing_terminal_for_started_invocations": missing,
        "partial_saved_response_checks_are_not_a_native_trajectory_replay": True,
        "runtime_boundary_enter_counts": dict(Counter(row.get("op") for row in runtime_records
                                                       if row.get("event") == "enter")),
        "native_grade_or_final_physical_state_inferred": False, "usage": usage}
    return base


def check_partial_model_terminal(model_directory, number):
    prefix = Path(model_directory) / f"{number:04d}"
    terminal = load(str(prefix) + "-terminal.json")
    require(terminal.get("invocation") == number and terminal.get("dispatches") in (0, 1),
            "Invalid partial invocation terminal identity")
    raw_path = Path(str(prefix) + "-response.bin")
    if not raw_path.exists():
        require(terminal.get("returned") is False, "Returned partial invocation lacks raw response")
        return terminal
    raw = raw_path.read_bytes()
    metadata = load(str(prefix) + "-response-meta.json")
    require(metadata.get("body_sha256") == binding(raw_path)["sha256"], "Partial raw response hash differs")
    if metadata.get("status") != 200:
        require(terminal.get("returned") is False, "Non-200 partial response counted as returned")
        return terminal
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        require(terminal.get("returned") is False and terminal.get("usage") is None,
                "Malformed partial response establishes a return or usage")
        return terminal
    require(type(payload) is dict, "Partial raw response is not an object")
    usage = payload.get("usage") or {}
    require(type(usage) is dict, "Partial raw usage is not an object")
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    actual = {"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "cached_tokens": prompt_details.get("cached_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens", completion_details.get("reasoning_tokens"))}
    for name, amount in actual.items():
        available = type(amount) is int and amount >= 0
        same((terminal.get("usage") or {}).get(name),
             {"available": available, "value": amount if available else None},
             "Partial raw response and usage terminal differ")
    return terminal


def audit(source_root, native_root, protocol_path, commit, archive, output):
    source_root, native_root = Path(source_root).resolve(), Path(native_root).resolve()
    archive, output = Path(archive).resolve(), Path(output).resolve()
    value = portable.verify_protocol_bytes(source_root, native_root, protocol_path, commit)
    before = portable.sealed_manifest(archive)
    record = load(archive / "preservation.json")
    require(record.get("protocol_commit") == commit, "Archive protocol commit differs")
    same(record["protocol"], binding(protocol_path), "Archive protocol identity differs")
    for name, expected in record["input_snapshots"].items():
        same(inventory(archive / "preserved" / name), expected, "Archive input snapshot differs")
    collection = archive / "preserved" / record["original_collection_relative"]
    check_claim(collection, value, Path(protocol_path), commit)
    slots = inspect_slots(collection, value)
    require(not output.is_relative_to(archive), "Derived audit must be outside the copy-only archive")
    output.mkdir(parents=True, exist_ok=False)
    try:
        with portable.frozen_auditor(source_root) as (frozen_protocol, auditor):
            portable.validate_schedule(value, frozen_protocol, source_root)
            sys.path.insert(0, str(native_root))
            try:
                portable.check_native_imports(native_root, value["native"]["files"])
                with auditor.no_network(), portable.bound_native_imports(native_root, value["native"]["files"]):
                    rows = [auditor.audit_episode(directory, planned, value)
                        if status == "sealed_native_return"
                        else interrupted_row(directory, planned, value, auditor)
                        for planned, status, directory in slots]
                portable.check_native_imports(native_root, value["native"]["files"])
            finally:
                sys.path.remove(str(native_root))
            require(len(rows) == 96, "All planned slots must remain in the interrupted cohort")
            portable.verify_files(source_root, value["sources"])
            portable.verify_files(native_root, value["native"]["files"])
            same(portable.sealed_manifest(archive), before, "Archive changed during independent replay")
            result = {"schema": "conseqax-limbo-audit-v1", "passed": True,
                "utc": utc(), "protocol_commit": commit, "protocol": binding(protocol_path),
                "collection_manifest": binding(archive / "manifest.json"), "rows": rows,
                "summary": auditor.summarize(rows),
                "counts": {"planned_slots": 96, "audited_available_native_grades": sum(row["grade_available"] for row in rows),
                    "interrupted_without_terminal": sum(row["status"] == "interrupted_terminal_unavailable" for row in rows),
                    "unstarted": sum(not row["started"] for row in rows),
                    "unavailable_native_grades": sum(row["native_grade"] is None for row in rows)},
                "scope": {**portable.SCOPE, "post_collection_derived_finalization": True,
                    "original_collection_had_final_collector_seal": False,
                    "original_collector_terminal_exit_or_cause_inferred": False,
                    "unavailable_grades_are_semantic_failures": False,
                    "all_planned_operational_rates_keep_96_slot_denominator": True,
                    "new_model_calls": 0, "partial_slot_replayed_or_graded": False,
                    "collection_resumed": False, "replacement_slots": False,
                    "passed_means_full_matrix_completed": False},
                "interrupted_collection": {"schema": "conseqax-limbo-interrupted-official-audit-v1",
                    "archive": str(archive), "collection_manifest_field_refers_to": "new_post_collection_copy_archive_manifest",
                    "no_original_final_collection_manifest_exists": True,
                    "original_sealed_returns_only_replayed": True,
                    "original_pipeline_and_observer_prefixes_preserved": True},
                "current_offline_environment": portable.current_environment(),
                "historical_environment": value["environment"],
                "helper_sources": {HERE.name: binding(HERE), HELPER.name: binding(HELPER)}}
        write_json(output / "audit-result.json", result)
    except BaseException as exc:
        write_json(output / "failure.json", {"passed": False, "utc": utc(),
            "error": type(exc).__name__ + ": " + str(exc), "original_run_replaced": False})
        raise
    finally:
        write_json(output / "manifest.json", inventory(output))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preserve", "audit"))
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--collection", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "preserve":
        require(args.collection is not None, "Preservation requires original collection")
        result = preserve(args.source_root, args.native_root, args.protocol, args.protocol_commit,
            args.collection, args.archive, backup_root=args.backup_root)
        print(json.dumps({"preserved": True, "archive": str(args.archive.resolve()), "scope": result["scope"]}))
    else:
        require(args.output is not None, "Independent audit requires separate output")
        result = audit(args.source_root, args.native_root, args.protocol, args.protocol_commit,
            args.archive, args.output)
        print(json.dumps({"passed": result["passed"], "counts": result["counts"], "summary": result["summary"]}))


if __name__ == "__main__":
    main()
