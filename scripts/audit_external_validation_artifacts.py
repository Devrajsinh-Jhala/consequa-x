"""Portable integrity/accounting audit; not semantic or independent human validation.

Standard library only. Never imports the framework, collectors or upstream tools.
Historical absolute inputs require explicit --relocate OLD=NEW mappings. Local
historical source bytes can be checked against their pinned Git objects. No
protocol is rewritten, and missing bindings are fatal, including dependency files.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile


JUDGE = "output/matched-trace-judge-2026-10-18"
TAU = "output/tau3-state-transfer-2026-10-18"
ANALYSIS = "output/matched-trace-judge-analysis-2026-10-18"
JUDGE_SHA = "4439983d1f861eaffaffbc4140750a8a1740653baa8eb7037ae5df600ca074ae"
TAU_SHA = "cf3f80e687b4a5094e54748964d46af032eb47406bd0d506fa15b33f20ac0d29"
SCOPE = "Portable integrity/accounting audit, not independent semantic or human validation"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def digest(blob):
    return sha256(blob).hexdigest()


def pairs(values):
    output = {}
    for key, value in values:
        require(key not in output, "Duplicate JSON object key")
        output[key] = value
    return output


def decode(blob):
    return json.loads(blob, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def same(left, right, message):
    require(encoded(left) == encoded(right), message)


def relative_name(name):
    require(type(name) is str and bool(name), "Artifact path must be a string")
    path = PurePosixPath(name)
    require(bool(path.parts) and not path.is_absolute() and path.as_posix() == name and ".." not in path.parts
            and "\\" not in name and ":" not in name, "Artifact path escape or noncanonical path")
    return path


def safe_path(base, name):
    relative_name(name)
    path = Path(base) / name
    require(path.resolve().is_relative_to(Path(base).resolve()) and not path.is_symlink(),
            "Artifact path leaves declared root")
    return path


class Audit:
    def __init__(self, root, relocations=()):
        self.root = Path(root).resolve()
        self.maps = []
        self.checked = 0
        self.git_blobs = 0
        for entry in relocations:
            old, separator, new = entry.partition("=")
            require(separator and old and new, "Relocation must be OLD=NEW")
            old = old.replace("\\", "/").rstrip("/")
            require(".." not in PurePosixPath(old).parts, "Invalid historical relocation prefix")
            require(not any(prefix.casefold() == old.casefold() for prefix, _ in self.maps),
                    "Duplicate relocation prefix")
            self.maps.append((old, Path(new).resolve()))
        self.maps.sort(key=lambda item: len(item[0]), reverse=True)

    def read(self, path, expected=None):
        require(not Path(path).is_symlink(), "Symlink input refused")
        blob = Path(path).read_bytes()
        if expected is not None:
            require(re.fullmatch(r"[0-9a-f]{64}", expected) is not None, "Invalid SHA-256 declaration")
            require(digest(blob) == expected, "Bound file bytes changed")
        self.checked += 1
        return blob

    def json(self, path, expected=None):
        return decode(self.read(path, expected))

    def relocate(self, historical):
        historical = historical.replace("\\", "/")
        for prefix, destination in self.maps:
            if historical.casefold().startswith(prefix.casefold() + "/"):
                return safe_path(destination, historical[len(prefix) + 1:])
            if historical.casefold() == prefix.casefold():
                return destination
        raise ValueError("Missing explicit relocation for a historical absolute binding")

    def historical_code(self, name, expected, revision):
        path = safe_path(self.root, name)
        if path.is_file() and digest(path.read_bytes()) == expected:
            self.checked += 1
            return
        require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "Invalid pinned source revision")
        result = subprocess.run(["git", "-C", str(self.root), "show", f"{revision}:{name}"],
                                capture_output=True, check=True)
        require(digest(result.stdout) == expected, "Pinned Git source bytes differ from frozen hash")
        self.git_blobs += 1

    def absolute_bindings(self, bindings):
        for name, expected in bindings.items():
            self.read(self.relocate(name), expected)


def sealed_protocol(audit, directory, expected):
    blob = audit.read(directory / "protocol.json", expected)
    seal = audit.json(directory / "protocol.sha256.json")
    require(seal.get("sha256") == digest(blob), "Original protocol seal changed")
    return decode(blob), digest(blob)


def inventory(directory, pattern, expected):
    actual = {path.relative_to(directory).as_posix() for path in directory.glob(pattern) if path.is_file()}
    same(sorted(actual), sorted(expected), "Relative artifact inventory has omitted or extra slots/files")


def parse_prediction(envelope):
    require(envelope.get("done") is True and envelope.get("done_reason") != "length",
            "Judge response did not complete")
    message = envelope.get("message", {})
    require(message.get("role") == "assistant" and not message.get("tool_calls"), "Invalid judge message")
    value = decode(message["content"])
    require(set(value) == {"state", "action_linked", "origin"}, "Invalid judge output schema")
    mapping = {"state": {"satisfied": True, "violated": False, "unknown": None},
               "action_linked": {"satisfied": True, "not_satisfied": False, "unknown": None},
               "origin": {"confirmed": "confirmed", "other_actor": "other_actor", "unknown": "unknown"}}
    require(all(type(value[key]) is str and value[key] in table for key, table in mapping.items()),
            "Invalid judge target enum")
    return {key: table[value[key]] for key, table in mapping.items()}


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def judge_summary(entries, receipts, context):
    """Recount declared labels only: never infer a semantic verdict from evidence."""
    result = {"selected_planned": len(entries), "available_factual_inputs": len(entries),
              "judge_status": {"completed": len(entries)}, "attempted_chat_calls": len(entries), "methods": {}}
    by_id = {row["slot_id"]: row for row in receipts}
    for method in ("local_trace_judge", "independent_public_reference", "consequa_state_origin"):
        targets = {}
        for target in ("state", "action_linked", "origin"):
            counts = Counter()
            for entry in entries:
                key = entry["slot"]["slot_id"]
                evaluation = context[key]
                prediction = (by_id[key]["prediction"][target] if method == "local_trace_judge"
                              else evaluation["baselines"][method][target])
                gold = evaluation["gold"][target]
                reference = evaluation["baselines"]["independent_public_reference"][target]
                known = (lambda x: x != "unknown") if target == "origin" else (lambda x: x is not None)
                definite, assessable = known(prediction), known(gold)
                qualified = definite and known(reference) and prediction == reference
                counts["all_definite_outputs"] += definite
                counts["all_evidence_supported_claims"] += qualified
                if not assessable:
                    counts["claims_with_unassessable_gold"] += definite
                    continue
                counts["gold_assessable_outputs"] += 1
                if not definite:
                    continue
                counts["claims"] += 1
                counts["correct_claims"] += prediction == gold
                counts["wrong_claims"] += prediction != gold
                counts["evidence_supported_claims"] += qualified
                counts["unsupported_correct_guesses"] += prediction == gold and not qualified
                if target != "origin":
                    counts["false_positive"] += prediction is True and gold is False
                    counts["false_negative"] += prediction is False and gold is True
            keys = ("gold_assessable_outputs", "claims", "correct_claims", "wrong_claims",
                    "evidence_supported_claims", "all_definite_outputs", "claims_with_unassessable_gold",
                    "all_evidence_supported_claims", "unsupported_correct_guesses", "false_positive", "false_negative")
            metric = {key: counts[key] for key in keys}
            metric.update(completed_outputs=len(entries), abstentions=counts["gold_assessable_outputs"] - counts["claims"])
            metric.update(coverage=ratio(counts["claims"], counts["gold_assessable_outputs"]),
                claim_error=ratio(counts["wrong_claims"], counts["claims"]),
                correct_yield=ratio(counts["correct_claims"], counts["gold_assessable_outputs"]),
                selected_planned_correct_yield=ratio(counts["correct_claims"], len(entries)),
                selected_available_input_correct_yield=ratio(counts["correct_claims"], len(entries)))
            targets[target] = metric
        result["methods"][method] = targets
    return result


def audit_judge(audit, directory, analysis=None, *, expected_slots=84, expected_protocol_hash=JUDGE_SHA):
    directory = Path(directory)
    require(not (directory / "runner.lock").exists(), "Judge collection is active")
    protocol, protocol_hash = sealed_protocol(audit, directory, expected_protocol_hash)
    entries = protocol["schedule"]
    require(len(entries) == protocol["selected_planned"] == protocol["available_inputs"] == expected_slots,
            "Judge planned inventory changed")
    for name, expected in protocol["code_sha256"].items():
        audit.historical_code(name, expected, protocol["source_revision"])
    audit.absolute_bindings(protocol["external_source_sha256"])
    context = audit.json(directory / "evaluation-context.json", protocol["evaluation_context_sha256"])
    slots = {entry["slot"]["slot_id"]: entry for entry in entries}
    require(len(slots) == expected_slots, "Duplicate judge slot")
    same(sorted(context), sorted(slots), "Evaluation context inventory changed")
    lines = audit.read(directory / "request-journal.jsonl").splitlines(keepends=True)
    previous, events = None, []
    for index, line in enumerate(lines):
        require(line.endswith(b"\n"), "Torn judge journal")
        row = decode(line)
        claimed = row.pop("sha256")
        require(row["index"] == index and row["previous_sha256"] == previous
                and digest(encoded(row)) == claimed, "Judge journal chain changed")
        previous = claimed
        events.append(row)
    require(len(events) == 2 + 4 * expected_slots and events[0]["event"] == "run_started"
            and events[-1]["event"] == "run_stopped"
            and events[-1]["stopped_reason"] == "all_never_started_slots_processed", "Judge closure/inventory changed")
    receipts, expected_calls = [], set()
    for offset, entry in enumerate(entries):
        slot = entry["slot"]["slot_id"]
        relative_name(slot)
        require(entry["input_status"] == "available", "Unavailable judge input in completed audit")
        value = audit.json(safe_path(directory, entry["input_file"]), entry["input_sha256"])
        group = events[1 + offset * 4:5 + offset * 4]
        same([row["event"] for row in group], ["judge_started", "chat_started", "chat_received", "judge_finished"],
             "Judge slot event order changed")
        require(all(row["slot_id"] == slot for row in group), "Judge journal slot order changed")
        started = audit.json(safe_path(directory, f"judgments/{slot}/started.json"), group[0]["started_sha256"])
        same(started["entry"], entry, "Judge start schedule binding changed")
        require(started["protocol_sha256"] == protocol_hash, "Judge start protocol binding changed")
        request_event, response_event = group[1:3]
        require(request_event["call_id"] == response_event["call_id"] == slot + "-call-00", "Judge call identity changed")
        require(response_event["status"] == 200 and response_event["truncated"] is False, "Judge raw response failed")
        request = audit.json(safe_path(directory, request_event["request_file"]), request_event["request_sha256"])
        expected = {"model": protocol["model"], "stream": False, "think": False, "format": protocol["output_schema"],
            "messages": [{"role": "system", "content": protocol["prompt"]},
                         {"role": "user", "content": encoded(value).decode().rstrip("\n")}],
            "options": {"seed": entry["judge_seed"], "temperature": protocol["settings"]["temperature"],
                        "num_predict": protocol["settings"]["num_predict"]}}
        same(request, expected, "Judge request differs from frozen public input/settings")
        envelope = audit.json(safe_path(directory, response_event["response_file"]), response_event["response_sha256"])
        receipt = audit.json(safe_path(directory, f"judgments/{slot}/receipt.json"), group[3]["receipt_sha256"])
        require(receipt["status"] == "completed" and receipt["attempted_calls"] == 1
                and receipt["slot_id"] == slot, "Judge completed receipt changed")
        same(receipt["prediction"], parse_prediction(envelope), "Judge prediction differs from raw response")
        receipts.append(receipt)
        expected_calls.update((request_event["request_file"], response_event["response_file"]))
    inventory(directory, "calls/**/*", expected_calls)
    inventory(directory, "inputs/**/*", {entry["input_file"] for entry in entries})
    inventory(directory, "judgments/**/*", {f"judgments/{slot}/{name}.json" for slot in slots for name in ("started", "receipt")})
    summary = judge_summary(entries, receipts, context)
    if analysis is not None:
        verify_manifest(audit, Path(analysis) / "manifest.json")
        saved = audit.json(Path(analysis) / "analysis.json")
        require(saved["final"] is True and saved["collection_state"] == "completed"
                and saved["protocol_sha256"] == protocol_hash and saved["attempted_calls_including_partial"] == expected_slots,
                "Judge analysis closure changed")
        require(saved["journal_sha256"] == digest((directory / "request-journal.jsonl").read_bytes()), "Analysis journal binding changed")
        same(saved["summary"], summary, "Judge analysis fractions changed")
        same(saved["receipts"], receipts, "Judge analysis receipt inventory changed")
        for axes, buckets in saved["strata"].items():
            expected_buckets = defaultdict(list)
            for entry in entries:
                key = json.dumps({axis: entry["slot"][axis] for axis in axes.split("/")}, sort_keys=True)
                expected_buckets[key].append(entry)
            same(sorted(buckets), sorted(expected_buckets), "Judge stratum inventory changed")
            for key, subset in expected_buckets.items():
                same(buckets[key], judge_summary(subset, receipts, context), "Judge stratum fractions changed")
    return {"completed": len(receipts), "attempted_calls": len(receipts), "journal_events": len(events),
            "protocol_sha256": protocol_hash, "source_revision": protocol["source_revision"], "summary": summary}


def audit_tau(audit, directory, *, expected_cells=656, expected_captures=900, expected_protocol_hash=TAU_SHA):
    directory = Path(directory)
    require(not (directory / "runner.lock").exists(), "Tau collection is active")
    protocol, protocol_hash = sealed_protocol(audit, directory, expected_protocol_hash)
    summary = audit.json(directory / "summary.json")
    require(len(protocol["schedule"]) == summary["planned"] == expected_cells and summary["model_calls"] == 0,
            "Tau planned/model inventory changed")
    require(summary["upstream_commit"] == protocol["upstream_commit"], "Tau upstream revision changed")
    local = {"runner": "scripts/run_tau_benchmark_validation.py", "protocol": "docs/tau-benchmark-validation.md",
             "tests": "tests/test_tau_benchmark_validation.py"}
    for name, expected in protocol["local_hashes"].items():
        path = "src/consequa_x/" + name[8:] if name.startswith("runtime/") else local[name]
        audit.historical_code(path, expected, protocol["source_revision"])
    source = audit.relocate(protocol["source"])
    for name, expected in protocol["upstream_hashes"].items():
        audit.read(safe_path(source, name), expected)
    audit.absolute_bindings(protocol["loaded_dependency_hashes"])
    expected_files, expected_starts = set(), set()
    counts, actions, captures, starts = Counter(), Counter(), 0, {}
    native_records, native_executed = 0, 0
    for index, slot in enumerate(protocol["schedule"]):
        require(slot["slot"] == index, "Tau slot order changed")
        name, start_name = f"episodes/episode_{index:04d}.json", f"started/episode_{index:04d}.json"
        expected_files.add(name)
        expected_starts.add(start_name)
        row = audit.json(safe_path(directory, name), summary["files"][name])
        started_bytes = audit.read(safe_path(directory, start_name))
        started = decode(started_bytes)
        starts[start_name] = digest(started_bytes)
        same({key: started[key] for key in slot}, slot, "Tau start schedule/hash binding changed")
        for key in ("slot", "domain", "task_id", "variant"):
            same(row[key], slot[key], "Tau episode schedule binding changed")
        require(row["source_task_sha256"] == slot["task_sha256"] and row["model_calls"] == 0
                and row["disposition"] == "completed", "Tau episode task/disposition changed")
        native_records += len(row["native_calls"])
        require(all(type(call["executed"]) is bool for call in row["native_calls"]),
                "Tau native call execution flag changed")
        native_executed += sum(call["executed"] for call in row["native_calls"])
        match = row["native_db_component"]["db_check"]["db_match"]
        require(type(match) is bool, "Invalid native DB match label")
        counts[(row["domain"], row["variant"], str(match))] += 1
        for capture in row["action_audits"]:
            require(capture["audit_disposition"] == "captured" and capture["inputs_unchanged"] is True
                    and capture["withheld_status"] == "unknown", "Tau capture accounting changed")
            verification = capture["trace"]["verifications"][-1]
            require(verification["origin"] == "unknown" and capture["explanation"]["assessment_alignment"] == "unassessable",
                    "Tau origin/assessment accounting changed")
            require(verification["status"] in ("satisfied", "violated", "unknown"), "Invalid Tau state label")
            actions[(row["domain"], row["variant"], verification["status"])] += 1
            captures += 1
    same(sorted(summary["files"]), sorted(expected_files), "Tau sealed episode inventory changed")
    inventory(directory, "episodes/**/*", expected_files)
    inventory(directory, "started/**/*", expected_starts)
    same(summary["dispositions"], {"completed": expected_cells, "failed": 0, "unstarted": 0}, "Tau dispositions changed")
    same(summary["native_db_component_counts"], [{"domain": d, "variant": v, "db_match": s == "True", "count": n}
         for (d, v, s), n in sorted(counts.items())], "Tau native DB fractions changed")
    same(summary["action_field_counts"], [{"domain": d, "variant": v, "status": s, "count": n}
         for (d, v, s), n in sorted(actions.items())], "Tau action-field fractions changed")
    require(captures == expected_captures, "Tau capture count changed")
    author_receipt = audit.root / "output/tau3-state-transfer-audit-2026-10-18/final-audit.json"
    if author_receipt.exists():
        saved = audit.json(author_receipt)
        require(saved["protocol_sha256"] == protocol_hash
                and saved["summary_sha256"] == digest((directory / "summary.json").read_bytes()), "Tau author-receipt bindings changed")
        same(saved["start_hash_manifest"], starts, "Tau start file bytes changed")
    return {"completed_cells": expected_cells, "captures": captures, "withheld_unknown": captures,
            "source_revision": protocol["source_revision"], "upstream_commit": protocol["upstream_commit"],
            "native_call_records": native_records, "native_calls_executed": native_executed,
            "upstream_files_checked": len(protocol["upstream_hashes"]),
            "dependency_files_checked": len(protocol["loaded_dependency_hashes"]),
            "model_calls": 0, "protocol_sha256": protocol_hash, "summary_sha256": digest((directory / "summary.json").read_bytes())}


def verify_manifest(audit, manifest):
    manifest = Path(manifest)
    value = audit.json(manifest)
    require(type(value.get("files")) is dict and value["files"], "Missing manifest inventory")
    for name, record in value["files"].items():
        expected = record["sha256"] if isinstance(record, dict) else record
        audit.read(safe_path(manifest.parent, name), expected)
    if "inputs" in value:
        audit.absolute_bindings(value["inputs"])
    fractions = manifest.parent / "fractions.json"
    if fractions.exists():
        for row in audit.json(fractions):
            same(row["value"], None if row["denominator"] in (None, 0) else row["numerator"] / row["denominator"],
                 "Figure fraction arithmetic changed")
    return {"manifest_sha256": digest(manifest.read_bytes()), "files_checked": len(value["files"])}


def audit_review_pack(audit, receipt):
    receipt = Path(receipt)
    value = audit.json(receipt)
    archive = safe_path(receipt.parent, value["archive"])
    blob = audit.read(archive, value["archive_sha256"])
    require(len(blob) == value["archive_bytes"], "Review archive size changed")
    with zipfile.ZipFile(archive) as members:
        names = members.namelist()
        require(len(names) == len(set(names)) == value["archive_members"], "Review ZIP inventory changed")
        for name in names:
            relative_name(name)
            require(not any(word in name.casefold() for word in ("private", "mapping", "answer_key")),
                    "Private reviewer mapping must not be included in public archive")
        manifest = decode(members.read("manifest.json"))
        same(sorted(names), sorted([*manifest["files"], "manifest.json"]), "Review public inventory changed")
        for name, record in manifest["files"].items():
            data = members.read(name)
            require(len(data) == record["bytes"] and digest(data) == record["sha256"], "Review public member changed")
    return {"archive_sha256": digest(blob), "public_members": len(names),
            "human_validation": "not established by packet integrity; private mappings never read or emitted"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True, help="New audit directory; never overwrite")
    parser.add_argument("--relocate", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--manifest", action="append", default=[], help="Optional figure/analysis manifest, relative to root")
    parser.add_argument("--review-pack", action="append", default=[], help="Optional public build-receipt, relative to root")
    args = parser.parse_args(argv)
    audit = Audit(args.root, args.relocate)
    output = Path(args.output).resolve()
    require(not output.exists(), "Audit output must be fresh")
    judge = audit_judge(audit, safe_path(audit.root, JUDGE), safe_path(audit.root, ANALYSIS))
    tau = audit_tau(audit, safe_path(audit.root, TAU))
    manifests = [verify_manifest(audit, safe_path(audit.root, name)) for name in args.manifest]
    packs = [audit_review_pack(audit, safe_path(audit.root, name)) for name in args.review_pack]
    result = {"scope": SCOPE, "passed": True, "judge": judge, "tau": tau,
              "audited_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
              "auditor_sha256": digest(Path(__file__).read_bytes()),
              "artifact_root": str(audit.root),
              "explicit_relocations": [{"historical_prefix": old, "local_prefix": str(new)}
                                       for old, new in audit.maps],
              "optional_manifests": manifests, "public_review_packs": packs,
              "bound_files_read": audit.checked, "pinned_git_blobs_checked": audit.git_blobs,
              "model_calls": 0, "native_tool_executions": 0,
              "limits": "Hash/accounting consistency does not authenticate sources, independently validate predicates or supply human judgments."}
    output.mkdir(parents=True, exist_ok=False)
    with (output / "audit.json").open("xb") as stream:
        stream.write(encoded(result))
    (output / "README.md").write_text("# Portable external-validation artifact audit\n\n" + SCOPE
        + ".\n\nThe audit passed with no framework imports, model calls or native tool execution. "
        "See audit.json for closed-study counts, hashes and checking scope. Historical protocols were not rewritten. "
        "No reviewer private mapping was read or emitted.\n\n"
        "The auditor checks the original protocol seals, bound local/upstream/dependency file bytes, "
        "the public judge inputs and exact raw requests/responses, its ordered hash-chained journal, "
        "completed receipts, and recomputed reported fractions/strata. For Tau it checks every planned "
        "episode and start, capture labels, withheld/origin accounting, native call execution counts, "
        "and summary counts. Explicit path relocations are recorded in audit.json; changed working source "
        "is accepted only when its original bytes match the pinned Git object. Missing bindings fail.\n\n"
        "This is artifact integrity and accounting, not source authentication, an independent semantic "
        "oracle, human annotation, or an autonomous-agent benchmark result. Optional figure and review-pack "
        "checks establish their declared hashes and inventory, not the validity of their scientific interpretation.\n",
        encoding="utf-8")
    print(json.dumps({"passed": True, "judge_completed": judge["completed"], "tau_cells": tau["completed_cells"],
                      "captures": tau["captures"], "scope": SCOPE}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Audit failed: {error}", file=sys.stderr)
        raise SystemExit(2)
