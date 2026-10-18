"""Post-freeze descriptive execution audit of a closed matched local study.

Never calls a model, repairs a study, or writes to its input directory. This
addition was motivated by the first-six no-action diagnostic after collection
began; it supplements, rather than changes, the frozen primary analysis.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

from consequa_x.models import EventType, Trace

try:
    from .run_matched_local_study import Journal, read_json, validate_freeze, write_new
except ImportError:
    from run_matched_local_study import Journal, read_json, validate_freeze, write_new


STATUSES = ("completed", "failed", "interrupted_partial", "unstarted")
AXES = (("model",), ("prompt_version",), ("model", "prompt_version"), ("case_id",),
        ("family_id",), ("repetition",), ("model", "prompt_version", "case_id"))
DISCLOSURE = (
    "Post-freeze descriptive addition prompted by the first-six completed-slot "
    "no-action diagnostic. No generation setting, prompt, sample, frozen primary "
    "metric or stopping rule was changed. Execution-conditional measurements "
    "supplement complete planned-denominator reporting; they are not a new "
    "confirmatory hypothesis or an independent task-population estimate."
)


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def intended_conditions(scenario):
    return {key: scenario[key] for key in ("fault", "use_idempotency", "external_actor",
                                         "include_provenance", "read_lag_ms")}


def episode_execution(trace, truth):
    """Join actual tool events to evaluator execution receipts, not case names."""
    decisions = [event.data for event in trace.events if event.type is EventType.AGENT_DECISION]
    operations = [item["policy_reply"]["decision"]["operation"] for item in decisions]
    if not operations or operations[0] not in {"refund", "stop"}:
        raise ValueError("Completed trace lacks a valid selection decision")
    selected = operations[0] == "refund"
    if type(truth["action_selected"]) is not bool or truth["action_selected"] != selected:
        raise ValueError("Trace selection disagrees with evaluator receipt")
    attempts = [row for row in truth["records"] if row.get("kind") == "execution_attempt"]
    effects = [row for row in truth["records"] if row.get("kind") == "refund"]
    intents = [event for event in trace.events if event.type is EventType.ACTION_INTENT]
    dispatches = [event for event in trace.events if event.type is EventType.ACTION_DISPATCH]
    if not len(attempts) == len(intents) == len(trace.responses):
        raise ValueError("Attempt, intent and public-response counts disagree")
    by_attempt = {row["attempt_id"]: row for row in attempts}
    by_effect = {row["effect_id"]: row for row in effects}
    if len(by_attempt) != len(attempts) or len(by_effect) != len(effects):
        raise ValueError("Duplicate evaluator attempt or effect identity")
    if any(response.attempt_id not in by_attempt
           or by_attempt[response.attempt_id]["response_status"] != response.status.value
           for response in trace.responses):
        raise ValueError("Public response does not match its evaluator attempt")
    expected_dispatches = {row["attempt_id"] for row in attempts
                           if row["response_result"].get("code") != "dispatch_failed"}
    observed_dispatches = [event.data["attempt_id"] for event in dispatches]
    if len(set(observed_dispatches)) != len(observed_dispatches) or set(observed_dispatches) != expected_dispatches:
        raise ValueError("Trace dispatch events disagree with execution receipts")
    if not selected and (attempts or dispatches or intents):
        raise ValueError("Unselected action nevertheless contains tool attempts")
    for row in attempts:
        if type(row["fault_applied"]) is not bool or type(row["cache_hit"]) is not bool:
            raise ValueError("Invalid fault/cache receipt")
        for effect_id in row["committed_effect_ids"]:
            if effect_id not in by_effect or by_effect[effect_id].get("attempt_id") != row["attempt_id"]:
                raise ValueError("Attempt references an unbound committed effect")

    action, observation = trace.action, trace.observations[-1]
    expected = action.contract.expected
    matching = [row for row in effects if all(row.get(key) == value for key, value in expected.items())]
    agent_effects = [row for row in effects if row.get("action_id") == action.action_id
                     and row.get("actor") == action.actor]
    external_effects = [row for row in effects if row.get("actor") and row["actor"] != action.actor]
    injected = Counter(row["fault"] for row in attempts if row["fault_applied"] and row["fault"] != "clean")
    scoped_visible = [row for row in effects if row["payment_id"] == expected["payment_id"]
                      and row["committed_at_ms"] <= observation.as_of_ms]
    public_rows = {row["effect_id"]: row for row in observation.records}
    omitted = sum(any(key in row and key not in public_rows[row["effect_id"]]
                      for key in ("actor", "action_id", "attempt_id"))
                  for row in scoped_visible if row["effect_id"] in public_rows)
    scenario = truth["scenario"]
    signals = {
        "timeout_with_new_commit_attempts": sum(row["response_status"] == "timeout"
            and bool(row["committed_effect_ids"]) for row in attempts),
        "timeout_without_new_commit_attempts": sum(row["response_status"] == "timeout"
            and not row["committed_effect_ids"] for row in attempts),
        "success_without_new_commit_or_cache_attempts": sum(row["response_status"] == "success"
            and not row["committed_effect_ids"] and not row["cache_hit"] for row in attempts),
        "cache_hit_attempts": sum(row["cache_hit"] for row in attempts),
        "wrong_payment_effects": sum(row["payment_id"] != expected["payment_id"] for row in agent_effects),
        "wrong_amount_effects": sum(row["amount_minor"] != expected["amount_minor"] for row in agent_effects),
        "excess_payload_matching_effects": max(0, len(matching) - 1),
        "external_effects": len(external_effects),
        "public_records_with_omitted_origin_fields": omitted,
        "readback_horizon_gap_ms": max(0, action.contract.horizon_ms - observation.as_of_ms),
    }
    return {
        "action_selected": selected, "dispatch_count": len(dispatches),
        "attempt_count": len(attempts),
        "retry_intent_count": operations.count("retry"),
        "retry_attempt_count": max(0, len(attempts) - 1),
        "repeat_dispatch_count": max(0, len(dispatches) - 1),
        "structured_assessment": trace.assessment.status.value,
        "operations": operations, "model_decision_count": len(operations),
        "response_status_history": [response.status.value for response in trace.responses],
        "refund_effect_count": len(effects), "agent_effect_count": len(agent_effects),
        "external_effect_count": len(external_effects),
        "payload_matching_effect_count": len(matching),
        "reversed_effect_count": sum("reversed_at_ms" in row for row in effects),
        "intended_conditions": intended_conditions(scenario),
        "realized_fault_attempt_counts": dict(sorted(injected.items())),
        "manifestation_signals": signals,
        "visible_ledger_record_count": len(observation.records),
        "hidden_records_with_public_visibility_opportunity": len(scoped_visible),
    }


def aggregate(episodes):
    statuses = Counter(row["status"] for row in episodes)
    if set(statuses) - set(STATUSES):
        raise ValueError("Unknown episode status")
    completed = [row for row in episodes if row["status"] == "completed"]
    executions = [row["execution"] for row in completed]
    selected = sum(row["action_selected"] for row in executions)
    dispatched = sum(row["dispatch_count"] > 0 for row in executions)
    assessments, responses, histories, operations, faults = (Counter() for _ in range(5))
    signals = Counter()
    for row in executions:
        assessments[row["structured_assessment"]] += 1
        responses.update(row["response_status_history"])
        histories[" -> ".join(row["response_status_history"]) or "(none)"] += 1
        operations.update(row["operations"])
        faults.update(row["realized_fault_attempt_counts"])
        signals.update(row["manifestation_signals"])
    result = {
        "planned_episodes": len(episodes),
        "started_episodes": len(episodes) - statuses["unstarted"],
        "episode_status": {key: statuses[key] for key in STATUSES},
        "attempted_model_calls": sum(row["attempted_model_calls"] for row in episodes),
        "attempted_model_calls_by_episode_status": {
            status: sum(row["attempted_model_calls"] for row in episodes if row["status"] == status)
            for status in STATUSES},
        "completed_episodes": len(completed), "action_selected_episodes": selected,
        "dispatched_episodes": dispatched,
        "scheduled_provider_mode_counts": dict(sorted(Counter(
            row["scheduled_conditions"]["fault"] for row in episodes).items())),
        "scheduled_provider_mode_counts_completed": dict(sorted(Counter(
            row["scheduled_conditions"]["fault"] for row in completed).items())),
        "scheduled_nonclean_episodes": sum(row["scheduled_conditions"]["fault"] != "clean" for row in episodes),
        "nonclean_fault_exercised_episodes": sum(bool(row["realized_fault_attempt_counts"]) for row in executions),
        "nonclean_fault_unexercised_completed_episodes": sum(
            row["intended_conditions"]["fault"] != "clean" and not row["realized_fault_attempt_counts"]
            for row in executions),
        "provenance_omission_configured_episodes": sum(
            not row["scheduled_conditions"]["include_provenance"] for row in episodes),
        "provenance_omission_realized_completed_episodes": sum(
            row["manifestation_signals"]["public_records_with_omitted_origin_fields"] > 0 for row in executions),
        "readback_horizon_gap_completed_episodes": sum(
            row["manifestation_signals"]["readback_horizon_gap_ms"] > 0 for row in executions),
        "rates": {
            "action_selected_per_completed": rate(selected, len(completed)),
            "action_selected_per_planned": rate(selected, len(episodes)),
            "dispatched_per_completed": rate(dispatched, len(completed)),
            "dispatched_per_planned": rate(dispatched, len(episodes)),
            "dispatched_per_selected": rate(dispatched, selected),
        },
        "assessment_status_counts": dict(sorted(assessments.items())),
        "response_status_counts": dict(sorted(responses.items())),
        "response_history_counts": dict(sorted(histories.items())),
        "operation_counts": dict(sorted(operations.items())),
        "realized_fault_attempt_counts": dict(sorted(faults.items())),
        "manifestation_signal_sums": dict(sorted(signals.items())),
        "completed_execution_measurements_only": True,
    }
    for field in ("dispatch_count", "attempt_count", "retry_intent_count", "retry_attempt_count",
                  "repeat_dispatch_count", "refund_effect_count", "agent_effect_count",
                  "external_effect_count", "payload_matching_effect_count", "reversed_effect_count"):
        result[field] = sum(row[field] for row in executions)
    result["completed_model_decision_count"] = sum(row["model_decision_count"] for row in executions)
    return result


def require_closed(directory):
    if (directory / "runner.lock").exists():
        raise ValueError("Study runner lock exists; refuse live finalization")
    path = directory / "request-journal.jsonl"
    journal = Journal(path)
    if not journal.records or journal.records[-1]["event"] != "run_stopped":
        raise ValueError("Study does not have a terminal run_stopped event")
    return journal


def summarize(directory, analysis_path, disposition_path):
    directory = Path(directory).resolve()
    journal = require_closed(directory)
    protocol = validate_freeze(directory)
    inventory = {}

    def capture(path, *, expected=None):
        path = Path(path).resolve()
        payload = path.read_bytes()
        digest = sha256(payload).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError(f"Changed bound input: {path.name}")
        inventory[str(path)] = {"sha256": digest, "bytes": len(payload)}
        return payload

    protocol_sha = sha256(capture(directory / "protocol.json")).hexdigest()
    capture(directory / "protocol.sha256.json")
    capture(directory / "study-plan.source.json", expected=protocol["manifest_sha256"])
    for name, binding in protocol["source_inventory"].items():
        capture(directory / name, expected=binding["sha256"])
    journal_sha = sha256(capture(directory / "request-journal.jsonl")).hexdigest()
    analysis_path, disposition_path = Path(analysis_path).resolve(), Path(disposition_path).resolve()
    analysis_sha = sha256(capture(analysis_path)).hexdigest()
    capture(disposition_path)
    analysis, disposition = read_json(analysis_path), read_json(disposition_path)
    if (disposition.get("schema_version") != "consequa-matched-study-disposition-v1"
            or disposition.get("final") is not True or disposition.get("no_active_runner") is not True
            or disposition.get("collection_state") not in {"completed", "stopped"}
            or disposition.get("protocol_sha256") != protocol_sha
            or disposition.get("journal_sha256") != journal_sha
            or disposition.get("analysis_sha256") != analysis_sha):
        raise ValueError("Final disposition does not bind the closed study and primary analysis")
    if disposition["collection_state"] == "stopped" and (
            not isinstance(disposition.get("stopped_reason"), str) or not disposition["stopped_reason"].strip()):
        raise ValueError("Stopped study requires an explicit final disposition reason")
    if analysis.get("protocol_sha256") != protocol_sha or analysis.get("journal_sha256") != journal_sha:
        raise ValueError("Primary analysis does not bind the same study/journal")

    schedule = {slot["slot_id"]: slot for slot in protocol["schedule"]}
    if len(schedule) != protocol["planned_episodes"]:
        raise ValueError("Frozen schedule denominator or identities disagree")
    calls, finishes, received, call_ids = defaultdict(list), defaultdict(list), defaultdict(list), set()
    for event in journal.records:
        for prefix in ("request", "response"):
            if f"{prefix}_file" in event:
                path = (directory / event[f"{prefix}_file"]).resolve()
                if not path.is_relative_to(directory):
                    raise ValueError("Journal artifact path escapes study directory")
                capture(path, expected=event[f"{prefix}_sha256"])
        if event["event"] == "chat_started":
            if event["slot_id"] not in schedule or event["call_id"] in call_ids:
                raise ValueError("Attempted model call outside frozen schedule")
            call_ids.add(event["call_id"])
            calls[event["slot_id"]].append(event)
        elif event["event"] == "episode_finished":
            if event["slot_id"] not in schedule:
                raise ValueError("Episode finish outside frozen schedule")
            finishes[event["slot_id"]].append(event)
        elif event["event"] == "chat_received":
            received[event["call_id"]].append(event)
    if set(received) - call_ids:
        raise ValueError("Provider response has no recorded model-call attempt")
    cases = {case["case_id"]: case for case in protocol["selected_cases"]}
    episodes = []
    for name, slot in schedule.items():
        folder = directory / "episodes" / name
        row = {"slot": slot, "attempted_model_calls": len(calls[name]),
               "scheduled_conditions": intended_conditions(cases[slot["case_id"]]["scenario"])}
        if not (folder / "started.json").exists():
            if calls[name] or finishes[name]:
                raise ValueError("Unstarted slot has calls or a finish receipt")
            row["status"] = "unstarted"
        else:
            capture(folder / "started.json")
            started = read_json(folder / "started.json")
            if started["slot"] != slot or started["protocol_sha256"] != protocol_sha:
                raise ValueError("Started slot differs from frozen schedule")
            if not (folder / "receipt.json").exists():
                if finishes[name]:
                    raise ValueError("Journal finish has no episode receipt")
                row["status"] = "interrupted_partial"
            else:
                if len(finishes[name]) != 1:
                    raise ValueError("Episode requires exactly one journal finish")
                capture(folder / "receipt.json", expected=finishes[name][0]["receipt_sha256"])
                receipt = read_json(folder / "receipt.json")
                if (receipt["slot"] != slot or receipt["status"] not in {"completed", "failed"}
                        or receipt["policy_calls"] != len(calls[name])):
                    raise ValueError("Episode receipt/schedule/model-call counts disagree")
                row["status"] = receipt["status"]
                if row["status"] == "completed":
                    if any(len(received[call["call_id"]]) != 1
                           or received[call["call_id"]][0]["status"] != 200
                           or received[call["call_id"]][0].get("truncated", False)
                           for call in calls[name]):
                        raise ValueError("Completed episode lacks a complete provider response per call")
                    if set(receipt["artifact_sha256"]) != {"trace.json", "explanation.json", "evaluator-truth.json"}:
                        raise ValueError("Completed receipt has unexpected artifacts")
                    for artifact, expected in receipt["artifact_sha256"].items():
                        capture(folder / artifact, expected=expected)
                    trace = Trace.from_json((folder / "trace.json").read_text(encoding="utf-8"))
                    truth = read_json(folder / "evaluator-truth.json")
                    if (truth["scenario"].get("name") != slot["case_id"]
                            or any(truth["scenario"].get(key) != value
                                   for key, value in cases[slot["case_id"]]["scenario"].items())):
                        raise ValueError("Evaluator scenario differs from its frozen case")
                    row["execution"] = episode_execution(trace, truth)
                    if row["execution"]["model_decision_count"] != receipt["policy_calls"]:
                        raise ValueError("Completed policy-decision and model-call counts disagree")
        episodes.append(row)
    totals = aggregate(episodes)
    if analysis.get("episode_status") != totals["episode_status"]:
        raise ValueError("Primary analysis and execution audit dispositions disagree")
    if disposition["collection_state"] == "completed" and (
            totals["episode_status"]["unstarted"] or totals["episode_status"]["interrupted_partial"]):
        raise ValueError("Completed disposition has unstarted or interrupted slots")
    groups = {}
    for axes in AXES:
        buckets = defaultdict(list)
        for row in episodes:
            key = json.dumps({axis: row["slot"][axis] for axis in axes}, sort_keys=True)
            buckets[key].append(row)
        groups["/".join(axes)] = {key: aggregate(rows) for key, rows in sorted(buckets.items())}
    # Refuse a concurrent restart, appended journal, or altered immutable input.
    require_closed(directory)
    for path, binding in inventory.items():
        if sha256(Path(path).read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError("Study input changed during postprocessing")
    return {
        "schema_version": "consequa-matched-execution-summary-v1",
        "protocol_sha256": protocol_sha, "journal_sha256": journal_sha,
        "analysis_sha256": analysis_sha, "source_revision": protocol["source_revision"],
        "postprocessor_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "postprocessing_disclosure": DISCLOSURE,
        "collection_disposition": disposition,
        "episode_status": totals["episode_status"],
        "summary": totals, "strata": groups, "episodes": episodes,
        "interpretation": {
            "counts": "Execution/effect measures cover completed immutable traces only. Failed/partial "
                      "execution is not treated as zero activity; its measurements are unavailable. "
                      "Model-call counts cover all statuses using the provider request journal.",
            "faults": "Intended condition labels are distinct from evaluator-reported injected fault "
                      "paths and observable response/effect/source-lag manifestations. A no-action "
                      "episode does not exercise its scheduled tool fault. Clean attempts are not faults.",
            "injection": "fault_applied identifies entry into the simulator fault branch; it does not "
                         "by itself prove the named effect manifested. Consult manifestation signals.",
            "retries": "Retry intention, repeat provider attempt and repeat actual dispatch are "
                       "separate counts. A dispatch event excludes fail-before-dispatch attempts.",
            "effects": "Ledger counts describe commits, including reversed effects. Excess payload "
                       "matches are raw lifetime multiplicity, not a stability-contract verdict.",
            "provenance": "Origin omission counts require an actual publicly visible effect record "
                           "whose hidden origin fields were suppressed. Configured omission without "
                           "such a record is not measured as realized provenance loss.",
            "lag": "Horizon gap sums are descriptive milliseconds across observations, not latency "
                   "estimates. A stale watermark can be realized even without a dispatched refund.",
        },
    }, {"schema_version": "consequa-matched-execution-input-inventory-v1", "files": inventory}


def markdown(result):
    lines = ["# Matched study execution diagnostic", "", result["postprocessing_disclosure"], "",
             "| Model/profile | Completed/planned | Selected/completed | Dispatched/completed | Tool attempts | Retry attempts | Refund effects |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for key, value in result["strata"]["model/prompt_version"].items():
        axes = json.loads(key)
        label = f"{axes['model']} / {axes['prompt_version']}"
        lines.append(f"| {label} | {value['completed_episodes']}/{value['planned_episodes']} | "
                     f"{value['action_selected_episodes']}/{value['completed_episodes']} | "
                     f"{value['dispatched_episodes']}/{value['completed_episodes']} | "
                     f"{value['attempt_count']} | {value['retry_attempt_count']} | {value['refund_effect_count']} |")
    lines.extend(["", "JSON retains full-planned rates, missing-execution dispositions, structured "
                  "assessment/response histories, condition labels and realized exposure separately.",
                  "Empty-ledger correctness does not establish refund execution or fault handling.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-output", required=True)
    parser.add_argument("--analysis", required=True, help="Frozen-primary analyzer output JSON")
    parser.add_argument("--disposition", required=True, help="Explicit final closed-study disposition JSON")
    parser.add_argument("--output-dir", required=True, help="Fresh directory; never writes into the study")
    args = parser.parse_args()
    output = Path(args.output_dir).resolve()
    study = Path(args.study_output).resolve()
    if output.is_relative_to(study) or output.exists():
        parser.error("Output must be a fresh directory outside the study")
    result, inventory = summarize(study, args.analysis, args.disposition)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "input-inventory.json", inventory)
    result["input_inventory_sha256"] = sha256((output / "input-inventory.json").read_bytes()).hexdigest()
    write_new(output / "execution-summary.json", result)
    with (output / "execution-summary.md").open("x", encoding="utf-8") as stream:
        stream.write(markdown(result))
    print(json.dumps({"output": str(output), "episode_status": result["episode_status"],
                      "summary_sha256": sha256((output / "execution-summary.json").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
