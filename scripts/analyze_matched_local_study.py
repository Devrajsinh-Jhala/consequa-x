"""Matched factual-trace audit ablations with explicit information/target budgets.

Never calls a model. Gold uses the evaluator-only simulator ledger, not verifier
verdicts. Public reference rules are implemented separately from ledger gold
and from Consequa-X's verifier. No causal-responsibility comparison is made.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from consequa_x.benchmark.targets import action_linked_consequence
from consequa_x.models import Trace
from consequa_x.policies import PolicyError
from consequa_x.verification import verify

try:
    from .run_matched_local_study import Journal, read_json, validate_freeze, write_new
except ImportError:
    from run_matched_local_study import Journal, read_json, validate_freeze, write_new


METHODS = ("response_only", "agent_self_report", "readback_state_only",
           "independent_public_reference", "consequa_state_origin")
EPISODE_STATUSES = ("completed", "failed", "interrupted_partial", "unstarted")
STRATIFICATION_AXES = (("model", "prompt_version"), ("case_id",), ("family_id",),
                       ("model", "prompt_version", "case_id"), ("repetition",))


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def ledger_gold(action, history):
    """Independent, evaluator-only discrete-time oracle for this simulator.

    Exact-count stability is enumerated at every integer simulator tick, while
    public reference rules use an event sweep. Neither calls verify/targets.
    """
    contract, expected = action.contract, action.contract.expected
    if contract.predicate != "refund_processed" or contract.horizon_ms > 100000:
        raise ValueError("Ledger gold supports bounded simulator refund contracts only")
    relevant = [row for row in history if row.get("kind") == "refund"
                and row["payment_id"] == expected["payment_id"]
                and action.registered_at_ms <= row["committed_at_ms"] <= contract.horizon_ms]
    payload = [row for row in relevant if row["amount_minor"] == expected["amount_minor"]
               and row["currency"] == expected["currency"]]
    eligible = [row for row in payload if row["committed_at_ms"] <= contract.deadline_ms
                and row.get("reversed_at_ms", contract.horizon_ms + 1) > contract.horizon_ms]
    if contract.exact_count is None:
        state = bool(eligible)
    else:
        state = len(eligible) == contract.exact_count and all(
            sum(row["committed_at_ms"] <= tick < row.get("reversed_at_ms", contract.horizon_ms + 1)
                for row in payload) == contract.exact_count
            for tick in range(contract.deadline_ms, contract.horizon_ms + 1))
    linked = [row for row in eligible if row.get("action_id") == action.action_id
              and row.get("actor") == action.actor]
    if not state:
        action_linked = False
    elif contract.exact_count == 0:
        action_linked = None
    else:
        action_linked = bool(linked) if contract.exact_count is None else len(linked) == contract.exact_count
    if any(row.get("action_id") == action.action_id and row.get("actor") == action.actor
           for row in relevant):
        origin = "confirmed"
    elif relevant and all(row.get("actor") and row["actor"] != action.actor
                          and row.get("action_id") != action.action_id for row in relevant):
        origin = "other_actor"
    else:
        origin = "unknown"
    return {"state": state, "action_linked": action_linked, "origin": origin,
            "refund_effects": len([row for row in history if row.get("kind") == "refund"])}


def public_reference(action, observation):
    """Transparent independent same-information contract/provenance baseline.

    Trusts the same declared source metadata as Consequa-X. It does not use the
    package verifier, target mapper, agent assessment, response, or hidden truth.
    """
    unknown = {"state": None, "action_linked": None, "origin": "unknown"}
    c, expected = action.contract, action.contract.expected
    if (c.predicate != "refund_processed" or not observation.available or not observation.complete
            or observation.as_of_ms < c.horizon_ms
            or observation.scope.get("payment_id") != expected.get("payment_id")
            or observation.scope.get("currency", expected.get("currency")) != expected.get("currency")):
        return unknown
    seen, scoped = set(), []
    for row in observation.records:
        required = {"effect_id", "payment_id", "amount_minor", "currency", "committed_at_ms", "status"}
        if not required <= row.keys():
            return unknown
        if (not isinstance(row["effect_id"], str) or not row["effect_id"].strip()
                or row["effect_id"] in seen or type(row["committed_at_ms"]) is not int
                or not 0 <= row["committed_at_ms"] <= observation.as_of_ms
                or type(row["amount_minor"]) is not int or row["amount_minor"] <= 0
                or row["payment_id"] != expected.get("payment_id")
                or not isinstance(row["currency"], str) or not row["currency"].strip()
                or not isinstance(row["status"], str)
                or row["status"] not in {"processed", "reversed"}):
            return unknown
        if any(key in row and (not isinstance(row[key], str) or not row[key].strip())
               for key in ("actor", "action_id", "attempt_id")):
            return unknown
        reversed_at = row.get("reversed_at_ms")
        if ("reversed_at_ms" in row and (type(reversed_at) is not int
            or not row["committed_at_ms"] <= reversed_at <= observation.as_of_ms)):
            return unknown
        if (row["status"] == "processed" and reversed_at is not None) or (
                row["status"] == "reversed" and reversed_at is None):
            return unknown
        seen.add(row["effect_id"])
        if action.registered_at_ms <= row["committed_at_ms"] <= c.horizon_ms:
            scoped.append(row)
    payload = [row for row in scoped if row["currency"] == expected["currency"]
               and row["amount_minor"] == expected["amount_minor"]]
    surviving = [row for row in payload if row["committed_at_ms"] <= c.deadline_ms
                 and row.get("reversed_at_ms", c.horizon_ms + 1) > c.horizon_ms]
    changes = defaultdict(int)
    for row in payload:
        changes[row["committed_at_ms"]] += 1
        if "reversed_at_ms" in row:
            changes[row["reversed_at_ms"]] -= 1
    count, peak = 0, 0
    for stamp in sorted({c.deadline_ms, *changes}):
        count += changes[stamp]
        if c.deadline_ms <= stamp <= c.horizon_ms:
            peak = max(peak, count)
    state = bool(surviving) if c.exact_count is None else (
        len(surviving) == c.exact_count and peak == c.exact_count)
    linked_all = [row for row in scoped if row.get("action_id") == action.action_id
                  and row.get("actor", action.actor) == action.actor]
    other_only = bool(scoped) and all(row.get("actor") and row["actor"] != action.actor
                                     and row.get("action_id") != action.action_id for row in scoped)
    origin = "confirmed" if linked_all else "other_actor" if other_only else "unknown"
    linked_surviving = [row for row in surviving if row in linked_all]
    sufficient = bool(linked_surviving) if c.exact_count is None else len(linked_surviving) == c.exact_count
    if not state:
        linked = False
    elif c.exact_count == 0:
        linked = None
    elif sufficient:
        linked = True
    elif other_only:
        linked = False
    else:
        linked = None
    return {"state": state, "action_linked": linked, "origin": origin}


def matched_predictions(trace):
    response = trace.responses[-1].status.value if trace.responses else None
    response_value = {"success": True, "error": False}.get(response)
    reported_value = {"success": True, "failure": False}.get(trace.latest_assessment().status.value)
    # Remove all provenance before state-only verification, including action and
    # actor names. The omitted information cannot affect its state prediction.
    observation = trace.observations[-1]
    stripped = replace(observation, records=tuple(
        {key: value for key, value in row.items() if key not in {"actor", "action_id", "attempt_id"}}
        for row in observation.records))
    state_receipt = verify(trace.single_action, stripped)
    full_receipt = verify(trace.single_action, observation)
    state_map = {"satisfied": True, "violated": False}
    return {
        "response_only": {"state": response_value, "action_linked": response_value, "origin": "unknown"},
        "agent_self_report": {"state": reported_value, "action_linked": reported_value, "origin": "unknown"},
        "readback_state_only": {"state": state_map.get(state_receipt.status.value),
                                "action_linked": None, "origin": "unknown"},
        "independent_public_reference": public_reference(trace.single_action, observation),
        "consequa_state_origin": {"state": state_map.get(full_receipt.status.value),
                                  "action_linked": action_linked_consequence(trace.single_action, full_receipt),
                                  "origin": full_receipt.origin.value},
    }


def summarize(rows, *, planned_episodes=None):
    result = {}
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        planned = len(selected) if planned_episodes is None else planned_episodes
        if planned < len(selected):
            raise ValueError("Completed semantic rows exceed their planned episode denominator")
        targets = {}
        for target in ("state", "action_linked"):
            eligible = [row for row in selected if row["gold"][target] is not None]
            claims = [row for row in eligible if row["prediction"][target] is not None]
            wrong = sum(row["prediction"][target] != row["gold"][target] for row in claims)
            targets[target] = {
                "completed": len(selected), "gold_assessable": len(eligible),
                "claims": len(claims), "correct_claims": len(claims)-wrong, "wrong_claims": wrong,
                "abstentions": len(eligible)-len(claims),
                "coverage": rate(len(claims), len(eligible)), "claim_error": rate(wrong, len(claims)),
                "correct_yield": rate(len(claims)-wrong, len(eligible)),
                "planned_episodes": planned,
                "full_planned_correct_yield": rate(len(claims)-wrong, planned),
                "false_positive": sum(row["prediction"][target] is True and row["gold"][target] is False for row in claims),
                "false_negative": sum(row["prediction"][target] is False and row["gold"][target] is True for row in claims),
                "evidence_supported_claims": sum(row["evidence_supported"][target] is True for row in claims),
                "unsupported_correct_guesses": sum(row["prediction"][target] == row["gold"][target]
                                                   and row["evidence_supported"][target] is False for row in claims),
            }
        origins = [row for row in selected if row["gold"]["origin"] != "unknown"]
        origin_claims = [row for row in origins if row["prediction"]["origin"] != "unknown"]
        wrong_origin = sum(row["prediction"]["origin"] != row["gold"]["origin"] for row in origin_claims)
        targets["origin"] = {
            "completed": len(selected), "gold_assessable": len(origins), "claims": len(origin_claims),
            "correct_claims": len(origin_claims)-wrong_origin, "wrong_claims": wrong_origin,
            "abstentions": len(origins)-len(origin_claims),
            "coverage": rate(len(origin_claims), len(origins)),
            "claim_error": rate(wrong_origin, len(origin_claims)),
            "correct_yield": rate(len(origin_claims)-wrong_origin, len(origins)),
            "planned_episodes": planned,
            "full_planned_correct_yield": rate(len(origin_claims)-wrong_origin, planned),
        }
        result[method] = targets
    return result


def episode_accounting(receipts, calls):
    """Count all frozen slots, including groups with no completed output.

    A failed or missing execution has no fabricated semantic prediction. The
    full-planned yield nevertheless retains it in the operational denominator.
    """
    statuses = Counter(receipt["status"] for receipt in receipts)
    if set(statuses) - set(EPISODE_STATUSES):
        raise ValueError("Unknown episode disposition")
    slots = {receipt["slot"]["slot_id"] for receipt in receipts}
    if len(slots) != len(receipts):
        raise ValueError("Duplicate episode slot in accounting")
    return {
        "planned_episodes": len(receipts),
        "started_episodes": len(receipts) - statuses["unstarted"],
        "episode_status": {key: statuses[key] for key in EPISODE_STATUSES},
        "attempted_chat_calls": sum(event["slot_id"] in slots for event in calls),
    }


def build_strata(rows, receipts, calls):
    """Partition the frozen schedule rather than only successful semantic rows."""
    groups = {}
    for axes in STRATIFICATION_AXES:
        planned_buckets, row_buckets = defaultdict(list), defaultdict(list)
        for receipt in receipts:
            key = json.dumps({axis: receipt["slot"][axis] for axis in axes}, sort_keys=True)
            planned_buckets[key].append(receipt)
        for row in rows:
            key = json.dumps({axis: row["slot"][axis] for axis in axes}, sort_keys=True)
            row_buckets[key].append(row)
        if set(row_buckets) - set(planned_buckets):
            raise ValueError("Semantic row falls outside the frozen schedule strata")
        groups["/".join(axes)] = {}
        for key, selected in sorted(planned_buckets.items()):
            accounting = episode_accounting(selected, calls)
            groups["/".join(axes)][key] = {
                **accounting,
                "summary": summarize(row_buckets[key], planned_episodes=accounting["planned_episodes"]),
            }
    return groups


def paired_comparisons(rows):
    """Descriptive paired differences on identical completed factual slots."""
    by_slot = defaultdict(dict)
    for row in rows:
        by_slot[row["slot"]["slot_id"]][row["method"]] = row
    comparisons = {}
    for baseline in METHODS:
        if baseline == "consequa_state_origin":
            continue
        result = {}
        for target in ("state", "action_linked"):
            counts = Counter()
            for methods in by_slot.values():
                left, right = methods["consequa_state_origin"], methods[baseline]
                gold = left["gold"][target]
                if gold is None:
                    continue
                counts["paired_episodes"] += 1
                cx, other = left["prediction"][target], right["prediction"][target]
                counts["consequa_claims"] += cx is not None
                counts["baseline_claims"] += other is not None
                counts["identical_prediction_including_abstention"] += cx is other
                cx_correct, other_correct = cx is not None and cx == gold, other is not None and other == gold
                label = ("both_correct" if cx_correct and other_correct else "consequa_only_correct"
                         if cx_correct else "baseline_only_correct" if other_correct else "neither_correct")
                counts[label] += 1
            total = counts["paired_episodes"]
            result[target] = {key: counts[key] for key in (
                "paired_episodes", "consequa_claims", "baseline_claims", "both_correct",
                "consequa_only_correct", "baseline_only_correct", "neither_correct",
                "identical_prediction_including_abstention")}
            result[target]["correct_yield_difference"] = rate(
                counts["consequa_only_correct"]-counts["baseline_only_correct"], total)
            result[target]["coverage_difference"] = rate(
                counts["consequa_claims"]-counts["baseline_claims"], total)
        comparisons[f"consequa_state_origin-vs-{baseline}"] = result
    return comparisons


def analyze(out):
    out = Path(out).resolve()
    protocol = validate_freeze(out)
    journal = Journal(out / "request-journal.jsonl")
    # Verify every retained request/response and completed receipt journal binding.
    slots = {slot["slot_id"]: slot for slot in protocol["schedule"]}
    seen_calls = set()
    for event in journal.records:
        for prefix in ("request", "response"):
            if f"{prefix}_file" in event:
                path = out / event[f"{prefix}_file"]
                if sha256(path.read_bytes()).hexdigest() != event[f"{prefix}_sha256"]:
                    raise ValueError("Captured provider bytes changed")
        if event["event"] == "chat_started":
            if event["call_id"] in seen_calls or event["slot_id"] not in slots:
                raise ValueError("Duplicate or undeclared chat call")
            seen_calls.add(event["call_id"])
            slot = slots[event["slot_id"]]
            payload = read_json(out / event["request_file"])
            if (payload["model"] != slot["model"]
                or payload["options"]["seed"] not in slot["reserved_phase_seeds"]
                or payload["options"]["temperature"] != protocol["settings"]["temperature"]
                or payload["options"]["num_predict"] != protocol["settings"]["num_predict"]
                or sha256(payload["messages"][0]["content"].encode("utf-8")).hexdigest()
                   != protocol["prompt_sha256"][slot["prompt_version"]]):
                raise ValueError("Chat request differs from frozen generation settings/profile")
    rows, receipts, counts = [], [], Counter()
    for slot in protocol["schedule"]:
        folder = out / "episodes" / slot["slot_id"]
        if not (folder / "started.json").exists():
            counts["unstarted"] += 1
            receipts.append({"slot": slot, "status": "unstarted"})
            continue
        if read_json(folder / "started.json")["slot"] != slot:
            raise ValueError("Started slot does not match the frozen schedule")
        if read_json(folder / "started.json")["protocol_sha256"] != read_json(out / "protocol.sha256.json")["sha256"]:
            raise ValueError("Started episode protocol binding changed")
        if not (folder / "receipt.json").exists():
            counts["interrupted_partial"] += 1
            receipts.append({"slot": slot, "status": "interrupted_partial"})
            continue
        receipt = read_json(folder / "receipt.json")
        if receipt["slot"] != slot or receipt["status"] not in {"completed", "failed"}:
            raise ValueError("Invalid episode receipt")
        bindings = [event for event in journal.records if event["event"] == "episode_finished"
                    and event["slot_id"] == slot["slot_id"]]
        if len(bindings) != 1 or bindings[0]["receipt_sha256"] != sha256((folder / "receipt.json").read_bytes()).hexdigest():
            raise ValueError("Episode receipt does not match its journal binding")
        counts[receipt["status"]] += 1
        receipts.append(receipt)
        if receipt["status"] != "completed":
            continue
        for name, claimed in receipt["artifact_sha256"].items():
            if sha256((folder / name).read_bytes()).hexdigest() != claimed:
                raise ValueError("Completed episode artifact changed")
        trace = Trace.from_json((folder / "trace.json").read_text(encoding="utf-8"))
        truth = read_json(folder / "evaluator-truth.json")
        gold = ledger_gold(trace.single_action, truth["records"])
        predictions = matched_predictions(trace)
        for method, prediction in predictions.items():
            support = {target: (None if prediction[target] is None else (
                method not in {"response_only", "agent_self_report"}
                and predictions["independent_public_reference"][target] is not None
                and prediction[target] == predictions["independent_public_reference"][target]))
                for target in ("state", "action_linked")}
            rows.append({"slot": slot, "method": method, "prediction": prediction, "gold": gold,
                         "evidence_supported": support,
                         "action_selected": truth["action_selected"],
                         "reported_status": trace.latest_assessment().status.value,
                         "response_count": len(trace.responses), "policy_calls": receipt["policy_calls"]})
    calls = [event for event in journal.records if event["event"] == "chat_started"]
    if len(calls) > protocol["max_chat_calls"]:
        raise ValueError("Frozen chat budget exceeded")
    status = {key: counts[key] for key in EPISODE_STATUSES}
    if sum(status.values()) != protocol["planned_episodes"]:
        raise ValueError("Episode denominators do not sum to the frozen plan")
    resources = {"received_responses": 0, "measured_transport_seconds": 0.0,
                 "provider_counts": {key: {"sum": 0, "available_calls": 0} for key in (
                     "prompt_eval_count", "eval_count", "total_duration", "load_duration",
                     "prompt_eval_duration", "eval_duration")}}
    for event in journal.records:
        if event["event"] in {"chat_received", "chat_transport_failed"}:
            resources["measured_transport_seconds"] += event["elapsed_seconds"]
        if event["event"] == "chat_received":
            resources["received_responses"] += 1
            try:
                envelope = read_json(out / event["response_file"])
            except (UnicodeError, PolicyError):
                continue
            if not isinstance(envelope, dict):
                continue
            for key, value in resources["provider_counts"].items():
                if type(envelope.get(key)) is int and envelope[key] >= 0:
                    value["sum"] += envelope[key]
                    value["available_calls"] += 1
    return {
        "schema_version": "consequa-matched-audit-analysis-v1",
        "protocol_sha256": read_json(out / "protocol.sha256.json")["sha256"],
        "planned_episodes": protocol["planned_episodes"], "episode_status": status,
        "attempted_chat_calls": len(calls), "max_chat_calls": protocol["max_chat_calls"],
        "generation_resources": resources,
        "transport_failures": sum(event["event"] == "chat_transport_failed" for event in journal.records),
        "journal_sha256": sha256((out / "request-journal.jsonl").read_bytes()).hexdigest()
            if (out / "request-journal.jsonl").exists() else None,
        "started_episodes": protocol["planned_episodes"] - counts["unstarted"],
        "summary": summarize(rows, planned_episodes=protocol["planned_episodes"]),
        "paired_comparisons": paired_comparisons(rows),
        "paired_comparisons_per_case": {
            case: paired_comparisons([row for row in rows if row["slot"]["case_id"] == case])
            for case in sorted({slot["case_id"] for slot in protocol["schedule"]})},
        "strata": build_strata(rows, receipts, calls), "episodes": receipts, "rows": rows,
        "evidence_support_definition": "A definite effect claim counts as evidence-supported only "
             "when its auditor's allowed information includes independent readback and the "
             "independent public reference derives that same definite target. Response-only and "
             "status-only self-report have no independent readback in their declared budgets. "
             "This conservative evidence-qualification rule is separate from hindsight correctness "
             "and is not a human rationale/certainty annotation.",
        "full_planned_yield_definition": "Correct definite outputs divided by all frozen slots "
             "in the group, including failed, partial, unstarted and gold-unassessable slots. "
             "This is a descriptive operational yield, not semantic accuracy with invented "
             "negative labels for missing executions. Completed-episode rates remain separate.",
        "interpretation": "Fixed simulator cases and exposed mechanisms; wording robustness only. "
                          "Offline auditors share factual traces but declared information sets differ. "
                          "Independent public reference shares Consequa-X's information set. "
                          "No causal attribution, human rationale audit, named-system reproduction, "
                          "statistical superiority or population generalization is established.",
    }


def markdown(analysis):
    lines = ["# Matched local-model factual audit", "", analysis["interpretation"], "",
             f"Planned episodes: {analysis['planned_episodes']}; statuses: "
             f"`{json.dumps(analysis['episode_status'], sort_keys=True)}`.",
             f"Attempted chat calls: {analysis['attempted_chat_calls']} / {analysis['max_chat_calls']}.", "",
             "| Auditor | Target | Claims / assessable | Wrong / claims | Correct / assessable | Correct / planned |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for method, targets in analysis["summary"].items():
        for target, value in targets.items():
            lines.append(f"| {method} | {target} | {value['claims']} / {value['gold_assessable']} | "
                         f"{value['wrong_claims']} / {value['claims']} | "
                         f"{value['correct_claims']} / {value['gold_assessable']} | "
                         f"{value['correct_claims']} / {value['planned_episodes']} |")
    lines.extend(["", "Zero denominators produce JSON null. Abstention is not counted as a correct claim.",
                  "Failed, partial and unstarted episodes remain explicit outside completed semantic targets.",
                  analysis["full_planned_yield_definition"],
                  "Each JSON stratum retains its full planned, started, disposition and call counts, "
                  "including strata with no completed episodes.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-output", required=True)
    parser.add_argument("--output", required=True, help="Fresh JSON analysis file; never overwritten")
    args = parser.parse_args()
    result = analyze(args.study_output)
    path = Path(args.output)
    write_new(path, result)
    with path.with_suffix(".md").open("x", encoding="utf-8") as stream:
        stream.write(markdown(result))
    print(json.dumps({"output": str(path.resolve()), "episodes": result["episode_status"],
                      "chat_calls": result["attempted_chat_calls"]}))


if __name__ == "__main__":
    main()
