"""Offline saved-artifact audit of the prospective native airline pilot.

No controller, collection harness, model transport, ConseqaX or generation API is
imported. Official task material is evaluator-only and loaded after inventories
and the caller-pinned prospective Git anchor have been verified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.native_agent import audit as native_audit  # noqa: E402
from research.native_agent.protocol import (  # noqa: E402
    ARMS, canonical_path, canonical_sha, load_json, make_schedule, runtime_binding,
    select_metadata, sha_file, verify_artifact_manifest, verify_files, verify_frozen_protocol,
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def configure_offline(native_root):
    """Process-local import settings; never retain credential values."""
    for name in tuple(os.environ):
        upper = name.upper()
        if (upper.endswith(("_API_KEY", "_API_TOKEN", "_ACCESS_TOKEN")) or upper in {
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "OPENAI_BASE_URL",
            "OPENAI_API_BASE", "LITELLM_PROXY_API_BASE", "GOOGLE_APPLICATION_CREDENTIALS",
            "AWS_SHARED_CREDENTIALS_FILE"}):
            os.environ.pop(name, None)
    os.environ.update(PYTHON_DOTENV_DISABLED="1", TAU2_DATA_DIR=str(Path(native_root) / "data"),
        LITELLM_LOCAL_MODEL_COST_MAP="True", LITELLM_TELEMETRY="False", DO_NOT_TRACK="1",
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    sys.dont_write_bytecode = True


def verify_sources(protocol, source_root, native_root):
    """Check actual bytes and the source commit without trusting current HEAD."""
    source_root, native_root = Path(source_root).resolve(), Path(native_root).resolve()
    require(source_root == Path(protocol["source"]["root"]).resolve(), "Frozen source-root differs")
    require(ROOT.resolve() == source_root, "Run the auditor from the frozen execution-source checkout")
    verify_files(source_root, protocol["source"]["files"])
    for name, record in protocol["source"]["files"].items():
        expected = subprocess.check_output(["git", "-C", str(source_root), "show",
                                            protocol["source"]["commit"] + ":" + name])
        require(hashlib.sha256(expected).hexdigest() == record["git_blob_sha256"],
                "Frozen source Git blob differs: " + name)
        actual = (source_root / name).read_bytes()
        require(actual == expected or (b"\r\n" not in expected
                and actual == expected.replace(b"\n", b"\r\n")), "Source differs beyond checkout EOL")
    require(native_root == Path(protocol["native_root"]).resolve(), "Frozen native-root differs")
    native = native_audit.verify_native_source(native_root)
    require(native["commit"] == protocol["native"]["commit"], "Native source commit differs")
    require(set(native["files"]) <= set(protocol["native"]["files"]), "Native binding coverage incomplete")
    for name, record in protocol["native"]["files"].items():
        canonical_path(name)
        path = (native_root / name).resolve()
        require(path.is_relative_to(native_root) and path.is_file(), "Native bound path absent/escaped")
        require(sha_file(path) == record["runtime_sha256"]
                and path.stat().st_size == record["runtime_bytes"], "Native runtime binding differs")
        if name in native["files"]:
            require(native["files"][name] == record, "Native runtime/Git/EOL binding differs")
        else:
            expected = subprocess.check_output(["git", "-C", str(native_root), "show",
                                                native["commit"] + ":" + name])
            actual = path.read_bytes()
            require(hashlib.sha256(expected).hexdigest() == record["git_sha256"]
                    and len(expected) == record["git_bytes"], "Native metadata Git binding differs")
            require(actual == expected or (b"\r\n" not in expected
                    and actual == expected.replace(b"\n", b"\r\n")), "Native metadata differs beyond checkout EOL")


def read_journal(path):
    """Preserve valid prefix and parse diagnostics for interrupted JSONL files."""
    path = Path(path)
    if not path.is_file():
        return {"available": False, "rows": [], "errors": []}
    rows, errors = [], []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        try:
            row = json.loads(line)
            native_audit.strict_value(row)
            require(type(row) is dict and row.get("event_index") == index,
                    "Journal event index differs")
            rows.append(row)
        except (ValueError, TypeError) as exc:
            errors.append({"line": index + 1, "type": type(exc).__name__, "message": str(exc)})
            break
    return {"available": True, "rows": rows, "errors": errors}


def journal_diagnostics(episode, tool_metadata):
    """Bound saved observations; partial rows are not independently replayed."""
    episode = Path(episode)
    loaded = {name: read_journal(episode / (name + ".jsonl")) for name in
              ("model-calls", "tool-dispatch", "tool-dispatch-starts", "controller-events")}
    models = loaded["model-calls"]["rows"]
    starts = [row for row in models if row.get("kind") == "request_start"]
    returns = [row for row in models if row.get("kind") == "request_return"]
    errors = [row for row in models if row.get("kind") == "request_error"]
    start_ids = [row["call_index"] for row in starts]
    terminal_ids = [row["call_index"] for row in returns + errors]
    model_integrity = (start_ids == list(range(len(starts))) and len(set(terminal_ids)) == len(terminal_ids)
                       and set(terminal_ids) <= set(start_ids))
    tokens = {}
    for name in ("prompt_tokens", "completion_tokens"):
        values = [row.get("response", {}).get("usage", {}).get(name)
                  if isinstance(row.get("response", {}).get("usage"), dict) else None for row in returns]
        known = [value for value in values if type(value) is int and value >= 0]
        tokens[name] = {"sum_observed": sum(known), "observed_responses": len(known),
                       "unavailable_attempts": len(starts) - len(known)}
    calls = [row for row in loaded["tool-dispatch"]["rows"] if row.get("phase") == "episode"]
    tool_counts, repeated, consecutive, seen, last = Counter(), 0, 0, set(), None
    for row in calls:
        request = row["request"]
        metadata = tool_metadata.get(request["tool_name"], {})
        tool_counts["dispatches"] += 1
        tool_counts["tool_type_" + metadata.get("type", "unknown")] += 1
        tool_counts["returned" if row["outcome"]["status"] == "returned" else "raised"] += 1
        tool_counts["db_changed_calls"] += int(row["before"] != row["after"])
        if metadata.get("mutates_state") is True:
            tool_counts["mutating_dispatches"] += 1
            key = canonical_sha(request)
            repeated += int(key in seen)
            consecutive += int(key == last)
            seen.add(key)
            last = key
    events = loaded["controller-events"]["rows"]
    receipts = [row.get("receipt", {}) for row in events if row.get("event") == "receipt"]
    status_counts, origin_counts, receipt_invalid = Counter(), Counter(), 0
    for receipt in receipts:
        verification = receipt.get("verification", {})
        status, origin = verification.get("status"), verification.get("origin")
        status_counts[str(status)] += 1
        origin_counts[str(origin)] += 1
        receipt_invalid += int(status not in {"satisfied", "violated", "unknown"} or origin != "unknown")
    network = load_json(episode / "network-guard.json") if (episode / "network-guard.json").is_file() else None
    return {"model": {"attempted": len(starts), "returned": len(returns), "failed": len(errors),
                "pending": len(starts) - len(terminal_ids), "journal_call_accounting_valid": model_integrity,
                "tokens": tokens,
                "http_generation_dispatch_records": sum(row.get("kind") == "http" and
                    row.get("generation_request") is True for row in network.get("events", [])) if network else None},
            "tools": {**dict(tool_counts), "repeated_same_payload_mutating_dispatches": repeated,
                      "consecutive_same_payload_mutating_dispatches": consecutive},
            "controller": {"guard_blocks": sum(row.get("event") == "guard_block" for row in events),
                "scheduled_reads_by_phase": dict(Counter(row.get("phase") for row in events
                    if row.get("event") == "read_dispatch")),
                "receipt_count": len(receipts), "receipt_declared_status_counts": dict(status_counts),
                "receipt_declared_origin_counts": dict(origin_counts),
                "receipt_invalid_status_or_origin": receipt_invalid,
                "receipt_semantic_status_independently_recomputed": False},
            "journal_availability": {key: {"available": value["available"], "errors": value["errors"]}
                                     for key, value in loaded.items()},
            "scope": "Saved-journal diagnostics; only a passed native episode audit authenticates completed call results"}


def validate_matrix(protocol, receipt):
    schedule = protocol["schedule"]
    require(schedule == make_schedule(protocol["selection"]), "Frozen schedule is not the prescribed 48-slot matrix")
    rows = receipt["all_planned_slots"]
    require(len(rows) == len(schedule) == 48, "All 48 planned dispositions are required")
    for expected, observed in zip(schedule, rows):
        require(all(observed.get(key) == value for key, value in expected.items()), "Disposition/schedule differs")
        require(observed.get("status") in {"worker_returned", "execution_failed", "unstarted",
                "integrity_failed", "supervisor_failed"}, "Unknown collection disposition")
    require(receipt["protocol_sha256"] == canonical_sha(protocol), "Collection/protocol digest differs")
    return rows


def verify_completed_accounting(episode, diagnostics, execution):
    """Require complete resource/call journals for an audited saved simulation."""
    require(all(value["available"] and not value["errors"]
                for value in diagnostics["journal_availability"].values()),
            "Completed simulation has unavailable/malformed journals")
    model = diagnostics["model"]
    require(model["journal_call_accounting_valid"] and model["pending"] == 0,
            "Completed model request accounting differs")
    state = execution["model_requests"]
    require(all(state[key] == model[other] for key, other in
                (("attempted", "attempted"), ("completed", "returned"), ("failed", "failed"))),
            "Execution receipt/model journals differ")
    for key in ("prompt_tokens", "completion_tokens"):
        require(state[key] == model["tokens"][key]["sum_observed"], "Execution receipt/token journals differ")
    contexts = load_json(Path(episode) / "context-checks.json")["checks"]
    require(all(row.get("passed") is True for row in contexts)
            and len(contexts) == model["http_generation_dispatch_records"] == model["attempted"],
            "Completed generation/context dispatch accounting differs")
    network = load_json(Path(episode) / "network-guard.json")["events"]
    sends = [row for row in network if row.get("kind") == "http" and row.get("generation_request") is True]
    starts_model = [row for row in read_journal(Path(episode) / "model-calls.jsonl")["rows"]
                    if row.get("kind") == "request_start"]
    for context, send, invocation in zip(contexts, sends, starts_model):
        digest = hashlib.sha256(json.dumps(context["request"], sort_keys=True, allow_nan=False).encode()).hexdigest()
        require(context.get("request_sha256") == send.get("parsed_body_sha256") == digest,
                "Actual generation body/context receipt binding differs")
        verify_model_wire(invocation["request"], context["request"])
    terminal = read_journal(Path(episode) / "tool-dispatch.jsonl")["rows"]
    starts = read_journal(Path(episode) / "tool-dispatch-starts.jsonl")["rows"]
    require(len(starts) == len(terminal) == execution["actual_tool_dispatches"]
            == execution["completed_tool_dispatches"] and not execution["inflight_tool_dispatches"],
            "Completed tool-dispatch accounting differs")
    for index, (start, end) in enumerate(zip(starts, terminal)):
        require(start["call_index"] == end["call_index"] == index and all(
            start[key] == end[key] for key in ("phase", "request", "before")),
            "Tool start/terminal journal differs")


def verify_model_wire(native_request, actual_wire):
    """Check native inputs against the actual parsed HTTP body, without collector imports."""
    def messages(value):
        return [{key: item for key, item in message.items()
                 if not ((key == "content" and item is None and message.get("role") == "assistant"
                          and message.get("tool_calls"))
                         or (key == "tool_calls" and item is None and message.get("role") == "assistant"))}
                for message in value]
    def equal(left, right):
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)
    require(not set(actual_wire) - {"model", "messages", "tools", "tool_choice", "max_tokens", "temperature", "seed"},
            "Actual HTTP body contains unbound generation fields")
    require(equal(messages(native_request["messages"]), messages(actual_wire["messages"])),
            "Native model messages differ from actual HTTP history")
    require(equal(native_request.get("tools"), actual_wire.get("tools")),
            "Native tool schemas differ from actual HTTP schemas")
    require(native_request["model"].removeprefix("openai/") == actual_wire["model"],
            "Native/HTTP model names differ")
    for key in ("max_tokens", "temperature", "seed", "tool_choice"):
        require(equal(native_request.get(key), actual_wire.get(key)), "Native/HTTP generation parameter differs: " + key)


def summarize(rows):
    groups = {}
    for arm in ARMS:
        for stratum in (None, True, False):
            selected = [row for row in rows if row["arm"] == arm
                        and (stratum is None or row["nonempty_communication"] is stratum)]
            name = arm + ":" + ("all" if stratum is None else "nonempty" if stratum else "empty")
            groups[name] = {"planned_slots": len(selected),
                "operational_successes": sum(row["operational_success"] for row in selected),
                "native_reward_observed": sum(row.get("native_reward") is not None for row in selected),
                "native_reward_unavailable": sum(row.get("native_reward") is None for row in selected),
                "native_normal_terminations": sum(row.get("normal_termination") is True for row in selected),
                "native_premature_terminations": sum(row.get("normal_termination") is False for row in selected),
                "dispositions": dict(Counter(row["collection_disposition"] for row in selected)),
                "episode_audit_failures": sum(row.get("episode_audit_passed") is False for row in selected),
                "model_attempts_observed": sum(row.get("diagnostics", {}).get("model", {}).get("attempted", 0)
                                                for row in selected)}
            groups[name]["native_required_components"] = {}
            for component in ("DB", "COMMUNICATE"):
                observed = [(row.get("native_component_outcomes") or {}).get("reward_breakdown") or {}
                            for row in selected]
                values = [value[component] for value in observed if component in value]
                groups[name]["native_required_components"][component] = {
                    "observed": len(values), "unavailable": len(selected) - len(values),
                    "succeeded": sum(value == 1.0 for value in values),
                    "failed": sum(value == 0.0 for value in values)}
            groups[name]["saved_cost_observations"] = {
                "model_journals_available": sum(row.get("diagnostics", {}).get("journal_availability", {})
                    .get("model-calls", {}).get("available") is True for row in selected),
                "tool_journals_available": sum(row.get("diagnostics", {}).get("journal_availability", {})
                    .get("tool-dispatch", {}).get("available") is True for row in selected),
                "tool_dispatches_observed": sum(row.get("diagnostics", {}).get("tools", {}).get("dispatches", 0)
                                                for row in selected),
                "mutating_dispatches_observed": sum(row.get("diagnostics", {}).get("tools", {}).get("mutating_dispatches", 0)
                                                     for row in selected),
                "guard_blocks_observed": sum(row.get("diagnostics", {}).get("controller", {}).get("guard_blocks", 0)
                                              for row in selected),
                "token_sums_observed": {key: sum(row.get("diagnostics", {}).get("model", {}).get("tokens", {})
                    .get(key, {}).get("sum_observed", 0) for row in selected)
                    for key in ("prompt_tokens", "completion_tokens")},
                "token_usage_unavailable_attempts": {key: sum(row.get("diagnostics", {}).get("model", {}).get("tokens", {})
                    .get(key, {}).get("unavailable_attempts", 0) for row in selected)
                    for key in ("prompt_tokens", "completion_tokens")}}
    pairs = []
    for task_id in sorted({row["task_id"] for row in rows}):
        selected = {row["arm"]: row for row in rows if row["task_id"] == task_id}
        pairs.append({"task_id": task_id, "operational_success_by_arm": {
            arm: selected[arm]["operational_success"] for arm in ARMS},
            "native_reward_by_arm": {arm: selected[arm].get("native_reward") for arm in ARMS}})
    return {"groups": groups, "paired_tasks": pairs, "distinct_task_ids": len(pairs),
            "planned_slots": len(rows), "inference": "Finite exposed-corpus exploratory pilot; descriptive only"}


def execute(args):
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "conseqax-native-offline-audit-v1", "started_utc": utc(), "passed": False,
              "new_model_calls": 0, "human_labels": 0, "rows": []}
    try:
        collection = Path(args.collection).resolve()
        manifest = verify_artifact_manifest(collection)
        protocol, anchor = verify_frozen_protocol(args.protocol, args.protocol_commit)
        verify_sources(protocol, args.source_root, args.native_root)
        require(runtime_binding(args.wheel) == protocol["runtime"], "Offline audit scientific runtime differs")
        receipt = load_json(collection / "collection-receipt.json")
        matrix = validate_matrix(protocol, receipt)
        require(receipt.get("protocol_commit") == args.protocol_commit, "Collection protocol Git anchor differs")
        raw_tasks = load_json(Path(args.native_root) / "data/tau2/domains/airline/tasks.json")
        require(select_metadata(raw_tasks) == protocol["selection"], "Native selection metadata differs")
        result.update(protocol_anchor=anchor, collection_manifest_sha256=sha_file(collection / "manifest.json"),
                      collection_bound_files=len(manifest["files"]), source_commit=protocol["source"]["commit"])
        configure_offline(args.native_root)
        sys.path.insert(0, str(Path(args.native_root) / "src"))
        with native_audit.no_network() as network_attempts:
            prohibited = ("consequa_x", "research.native_agent.controller", "research.native_agent.transport",
                          "research.native_agent.harness", "scripts.run_native_external_benchmark")
            require(not any(name == prefix or name.startswith(prefix + ".") for name in sys.modules
                            for prefix in prohibited), "Collector/framework modules must not enter independent audit")
            import tau2
            require(Path(tau2.__file__).resolve() == Path(args.native_root).resolve() / "src/tau2/__init__.py",
                    "Native import origin differs from frozen source")
            from tau2.data_model.tasks import Task
            from tau2.domains.airline.environment import get_environment
            environment = get_environment(solo_mode=False)
            tool_metadata = {name: {"type": getattr(getattr(tool, "__tool_type__", None), "value", "unknown"),
                "mutates_state": getattr(tool, "__mutates_state__", None)}
                for name, tool in environment.tools.tools.items()}
            official = {str(task["id"]): task for task in raw_tasks}
            for slot in matrix:
                row = {**{key: slot[key] for key in ("slot", "task_id", "arm", "nonempty_communication")},
                    "collection_disposition": slot["status"], "operational_success": 0,
                    "required_task_basis": ["DB", "COMMUNICATE"],
                    "native_reward": None, "native_component_outcomes": None,
                    "episode_audit_passed": None, "normal_termination": None}
                episode = collection / f"slot-{slot['slot']:03d}-{slot['task_id']}-{slot['arm']}" / "episode"
                try:
                    row["diagnostics"] = journal_diagnostics(episode, tool_metadata)
                    if (episode / "native-simulation.json").is_file():
                        journal = read_journal(episode / "tool-dispatch.jsonl")
                        require(journal["available"] and not journal["errors"], "Completed native tool journal unavailable/malformed")
                        saved = load_json(episode / "native-simulation.json")
                        require(saved["id"] == slot["episode_id"], "Native simulation episode identity differs")
                        execution = load_json(episode / "execution-receipt.json")
                        verify_completed_accounting(episode, row["diagnostics"], execution)
                        audit = native_audit.audit_native_episode(saved, Task.model_validate(official[slot["task_id"]]),
                            journal["rows"], load_json(episode / "episode-start.json")["hashes"],
                            load_json(episode / "final-state.json")["hashes"], args.native_root)
                        row.update(episode_audit_passed=True, native_reward=audit["reward"]["reward"],
                            native_component_outcomes=audit["reward"], normal_termination=audit["normal_termination"])
                        write_new(output / f"episode-audit-{slot['slot']:03d}.json", audit)
                        row["operational_success"] = int(slot["status"] == "worker_returned"
                            and slot.get("exit_code") == 0 and execution["status"] == "native_returned"
                            and audit["reward"]["reward"] == 1.0)
                    elif slot["status"] == "worker_returned":
                        raise ValueError("Successful worker has no native simulation")
                except Exception as exc:
                    row.update(episode_audit_passed=False, error={"type": type(exc).__name__, "message": str(exc)})
                result["rows"].append(row)
                write_new(output / f"slot-audit-{slot['slot']:03d}.json", row)
            result["network_attempts"] = len(network_attempts)
        result["summary"] = summarize(result["rows"])
        result["native_simulations_audited"] = sum(row["episode_audit_passed"] is True for row in result["rows"])
        result["all_slots_attempted"] = not any(row["collection_disposition"] == "unstarted" for row in result["rows"])
        result["passed"] = not any(row["episode_audit_passed"] is False for row in result["rows"])
        result["limitations"] = [
            "Automated same-project code audit; no independent human validation.",
            "Twelve previously exposed tasks,48pairedslots; no population CI,p-value or broad readiness claim.",
            "Receipt statuses are retained declarations,not independently recomputed free-form claim accuracy.",
            "Repeated payloads and DB changes do not establish unwanted harm,causal origin or durability.",
            "Partial journal diagnostics retain unavailable observations and are not fabricated native rewards."]
    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
    finally:
        result["finished_utc"] = utc()
        write_new(output / "audit-result.json", result)
        files = {path.relative_to(output).as_posix(): sha_file(path)
                 for path in sorted(output.rglob("*")) if path.is_file()}
        write_new(output / "manifest.json", {"schema": "conseqax-native-offline-audit-artifacts-v1", "files": files})
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("collection", "protocol", "protocol-commit", "native-root", "wheel", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--source-root", default=str(ROOT))
    return execute(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
