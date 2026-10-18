"""Frozen, one-call local trace judging of the closed study's repetition-zero subset.

This is a post-collection descriptive comparator, not a held-out benchmark,
independent human annotation, or causal attribution experiment. Never edits the
factual study. Freeze must complete before any /api/chat request is permitted.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

import consequa_x
from consequa_x.models import EventType, Trace
from consequa_x.policies import PolicyError, strict_json_loads

try:
    from .run_matched_local_study import (
        InfrastructurePolicyError, Journal, RecordingPolicy, digest, encoded,
        inspect_models, now, read_json, write_bytes_new, write_new,
    )
    from .analyze_matched_local_study import matched_predictions
except ImportError:
    from run_matched_local_study import (
        InfrastructurePolicyError, Journal, RecordingPolicy, digest, encoded,
        inspect_models, now, read_json, write_bytes_new, write_new,
    )
    from analyze_matched_local_study import matched_predictions


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "consequa-matched-trace-judge-v1"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"
MODEL_DIGEST = "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
SEED_BASE = 1900000000
SETTINGS = {"base_url": "http://127.0.0.1:11435", "temperature": 0.2,
            "num_predict": 192, "timeout": 180.0}
READBACK_METHODS = {"local_trace_judge", "independent_public_reference", "consequa_state_origin"}
OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "state": {"type": "string", "enum": ["satisfied", "violated", "unknown"]},
        "action_linked": {"type": "string", "enum": ["satisfied", "not_satisfied", "unknown"]},
        "origin": {"type": "string", "enum": ["confirmed", "other_actor", "unknown"]},
    },
    "required": ["state", "action_linked", "origin"],
}
PROMPT = """Audit a captured refund action using only the supplied public evidence.
Return exactly the three JSON fields in the schema; no rationale or other text.
The independent observation is the readback. Tool responses describe requests,
not proof of their effects. Identifiers are opaque; equality still matters.
State asks whether the registered outcome contract was satisfied. Match payment,
amount and currency. A qualifying effect commits at or after registration and by
the inclusive deadline and remains unreversed through deadline+stability_ms.
For exact_count, that count must hold throughout the inclusive stability window;
extra matching effects during that window violate it. A reversal at the horizon
does not persist through it. Effects committed after the horizon are irrelevant.
Unavailable, incomplete, malformed, wrongly scoped or horizon-stale readback is
unknown: never infer absence from missing data.
Origin asks whether any relevant observed refund (including wrong-amount or
reversed effects) is linked to this action_id and actor. Say confirmed if so;
other_actor only if all relevant effects explicitly belong to other actors and
none links this action; otherwise unknown. Origin does not imply target success.
Action_linked asks whether the satisfied target is supported by sufficient
qualifying effects linked to this action and actor. A known state violation
means not_satisfied. A satisfied state caused only by other actors means
not_satisfied. Missing provenance means unknown, not an invented causal link.
Do not attribute the outcome merely because a request or success response exists.
An exact_count of zero has unknown action_linked. Use unknown whenever the
available evidence cannot establish the requested target. This is evidence
auditing, not counterfactual causal responsibility.
"""


def code_hashes():
    paths = [Path(__file__), ROOT / "scripts/run_matched_local_study.py",
             ROOT / "scripts/analyze_matched_local_study.py",
             ROOT / "tests/test_matched_trace_judge.py", ROOT / "docs/matched-trace-judge.md"]
    package = Path(consequa_x.__file__).resolve().parent
    paths.extend(p for p in package.rglob("*") if p.is_file()
                 and (p.suffix in {".py", ".json"} or p.name == "py.typed"))
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in sorted(paths)}


def public_input(trace):
    """Structural allowlist: never serialize a whole trace or arbitrary containers.

    Only stable public refund fields survive. All identity-bearing values use
    one equality-preserving alias map, including response refund_id/effect_id.
    Context, decisions, rationale, assessments, receipts and labels are omitted.
    """
    if not isinstance(trace, Trace):
        raise TypeError("Expected a validated Trace")
    aliases = {}

    def alias(value):
        if value is None:
            return None
        if type(value) is not str or not value.strip():
            raise ValueError("Public identity must be a nonempty string")
        if value not in aliases:
            aliases[value] = f"id-{len(aliases) + 1:04d}"
        return aliases[value]

    identity_keys = {"action_id", "actor", "payment_id", "attempt_id", "effect_id",
                     "refund_id", "idempotency_key", "provider_request_id", "observation_id"}

    def fields(source, allowed):
        return {key: alias(source[key]) if key in identity_keys else source[key]
                for key in allowed if key in source}

    action = trace.action
    contract = action.contract
    output = {"action": {
        "action_id": alias(action.action_id), "actor": alias(action.actor),
        "name": action.name, "registered_at_ms": action.registered_at_ms,
        "arguments": fields(action.arguments, ("payment_id", "amount_minor", "currency")),
        "idempotency_key": alias(action.idempotency_key),
        "contract": {
            "predicate": contract.predicate,
            "expected": fields(contract.expected, ("payment_id", "amount_minor", "currency")),
            "deadline_ms": contract.deadline_ms, "stability_ms": contract.stability_ms,
            "exact_count": contract.exact_count,
        }}, "attempts": [], "responses": []}
    for event in trace.events:
        if event.type is EventType.ACTION_DISPATCH:
            output["attempts"].append({"time_ms": event.time_ms,
                **fields(event.data, ("action_id", "attempt_id"))})
    for response in trace.responses:
        output["responses"].append({
            "attempt_id": alias(response.attempt_id), "time_ms": response.time_ms,
            "status": response.status.value,
            "provider_request_id": alias(response.provider_request_id),
            "result": fields(response.result, ("refund_id", "payment_id", "amount_minor",
                                                 "currency", "status", "code")),
        })
    observation = trace.observations[-1]
    output["observation"] = {
        "observation_id": alias(observation.observation_id), "source": "independent-readback",
        "observed_at_ms": observation.observed_at_ms, "as_of_ms": observation.as_of_ms,
        "available": observation.available, "complete": observation.complete,
        "scope": fields(observation.scope, ("payment_id", "currency", "lag_ms")),
        "records": [fields(row, ("effect_id", "payment_id", "amount_minor", "currency",
                    "committed_at_ms", "status", "reversed_at_ms", "actor", "action_id",
                    "attempt_id")) for row in observation.records],
    }
    return output


def parse_prediction(envelope):
    if envelope.get("done_reason") == "length":
        raise PolicyError("Judge output reached the token limit")
    message = envelope.get("message")
    if envelope.get("done") is not True or type(message) is not dict:
        raise PolicyError("Judge did not return a completed chat response")
    if message.get("role") != "assistant" or type(message.get("content")) is not str:
        raise PolicyError("Judge chat message is malformed")
    if message.get("tool_calls"):
        raise PolicyError("Judge returned unsupported tool calls")
    result = strict_json_loads(message["content"])
    if type(result) is not dict or set(result) != set(OUTPUT_SCHEMA["required"]):
        raise PolicyError("Judge must return exactly the three declared fields")
    for key, spec in OUTPUT_SCHEMA["properties"].items():
        if type(result[key]) is not str or result[key] not in spec["enum"]:
            raise PolicyError("Judge returned an invalid target label")
    return {"state": {"satisfied": True, "violated": False, "unknown": None}[result["state"]],
            "action_linked": {"satisfied": True, "not_satisfied": False, "unknown": None}[
                result["action_linked"]], "origin": result["origin"]}


def request_payload(input_value, seed, settings=SETTINGS):
    return {"model": MODEL, "stream": False, "think": False, "format": OUTPUT_SCHEMA,
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": encoded(input_value).decode().rstrip("\n")}],
            "options": {"seed": seed, "temperature": settings["temperature"],
                        "num_predict": settings["num_predict"]}}


def load_pool(study, analysis):
    """Check sealed bindings before selecting slots, without new factual generation."""
    study, analysis = Path(study).resolve(), Path(analysis).resolve()
    protocol = read_json(study / "protocol.json")
    protocol_hash = digest((study / "protocol.json").read_bytes())
    if read_json(study / "protocol.sha256.json")["sha256"] != protocol_hash:
        raise ValueError("Factual protocol hash changed")
    disposition = read_json(analysis / "final-disposition.json")
    receipt = read_json(analysis / "finalization-receipt.json")
    saved = read_json(analysis / "analysis.json")
    analysis_hash = digest((analysis / "analysis.json").read_bytes())
    if (disposition.get("final") is not True or receipt.get("final") is not True
            or disposition["protocol_sha256"] != protocol_hash
            or receipt["protocol_sha256"] != protocol_hash
            or saved["protocol_sha256"] != protocol_hash
            or receipt["analysis_sha256"] != analysis_hash
            or disposition["analysis_sha256"] != analysis_hash
            or (study / "runner.lock").exists()):
        raise ValueError("Factual pool is not a matching closed study")
    if (protocol["planned_episodes"] != 504 or len(protocol["schedule"]) != 504
            or saved["planned_episodes"] != 504 or saved["episode_status"] != {
                "completed": 503, "failed": 1, "interrupted_partial": 0, "unstarted": 0}):
        raise ValueError("This protocol requires the declared closed 504-slot pool")
    by_slot = {row["slot"]["slot_id"]: row for row in saved["episodes"]}
    if len(by_slot) != 504 or set(by_slot) != {s["slot_id"] for s in protocol["schedule"]}:
        raise ValueError("Factual receipts do not cover the complete pool")
    selected = [slot for slot in protocol["schedule"] if slot["repetition"] == 0]
    if len(selected) != 84:
        raise ValueError("Repetition-zero selection must contain exactly 84 slots")
    external = {}
    for path in (study / "protocol.json", study / "protocol.sha256.json",
                 analysis / "analysis.json", analysis / "final-disposition.json",
                 analysis / "finalization-receipt.json"):
        external[str(path)] = digest(path.read_bytes())
    rows = defaultdict(dict)
    for row in saved["rows"]:
        slot_id, method = row["slot"]["slot_id"], row["method"]
        if method in rows[slot_id]:
            raise ValueError("Duplicate sealed baseline row")
        rows[slot_id][method] = row
    prepared = []
    for index, slot in enumerate(selected):
        slot_id = slot["slot_id"]
        factual = by_slot[slot_id]
        if factual["slot"] != slot:
            raise ValueError("Factual receipt schedule differs")
        entry = {"slot": slot, "judge_seed": SEED_BASE + index,
                 "input_status": "available" if factual["status"] == "completed" else "unavailable",
                 "factual_status": factual["status"]}
        receipt_path = study / "episodes" / slot_id / "receipt.json"
        if read_json(receipt_path) != factual:
            raise ValueError("Selected factual receipt differs from sealed analysis")
        external[str(receipt_path)] = digest(receipt_path.read_bytes())
        if entry["input_status"] == "available":
            trace_path = receipt_path.parent / "trace.json"
            trace_bytes = trace_path.read_bytes()
            if digest(trace_bytes) != factual["artifact_sha256"]["trace.json"]:
                raise ValueError("Selected factual trace changed")
            external[str(trace_path)] = digest(trace_bytes)
            trace = Trace.from_json(trace_bytes.decode("utf-8"))
            predictions = matched_predictions(trace)
            for method in ("independent_public_reference", "consequa_state_origin"):
                if predictions[method] != rows[slot_id][method]["prediction"]:
                    raise ValueError("Recomputed baseline differs from sealed analysis")
            entry["input"] = public_input(trace)
            entry["evaluation"] = {"gold": rows[slot_id]["consequa_state_origin"]["gold"],
                                   "baselines": predictions}
        prepared.append(entry)
    return prepared, external, {"planned": 504, "completed": 503, "failed": 1,
        "protocol_sha256": protocol_hash, "analysis_sha256": analysis_hash}


def inspect(settings=SETTINGS):
    result = inspect_models((MODEL,), settings)
    if result["models"][MODEL]["tag"].get("digest") != MODEL_DIGEST:
        raise PolicyError("Judge requires the fixed installed Qwen model digest")
    return result


def freeze(study, analysis, output, *, max_wall_seconds=7200, inspector=inspect):
    if not math.isfinite(max_wall_seconds) or max_wall_seconds <= 0:
        raise ValueError("Wall budget must be finite and positive")
    out = Path(output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("Freeze requires a new or empty output directory")
    prepared, external, pool = load_pool(study, analysis)
    sources = code_hashes()
    identity = inspector(SETTINGS)
    if identity["models"][MODEL]["tag"].get("digest") != MODEL_DIGEST:
        raise PolicyError("Judge model digest is not the declared model")
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True).stdout.strip()
    schedule, context = [], {}
    for entry in prepared:
        slot_id = entry["slot"]["slot_id"]
        record = {k: entry[k] for k in ("slot", "judge_seed", "input_status", "factual_status")}
        if entry["input_status"] == "available":
            name = f"inputs/{slot_id}.json"
            content = encoded(entry["input"])
            write_bytes_new(out / name, content)
            record.update(input_file=name, input_sha256=digest(content))
            context[slot_id] = entry["evaluation"]
        schedule.append(record)
    write_new(out / "evaluation-context.json", context)
    protocol = {"schema_version": SCHEMA, "frozen_utc": now(), "source_revision": revision,
        "package_version": importlib.metadata.version("consequa-x"), "python": sys.version,
        "code_sha256": sources, "external_source_sha256": external, "settings": SETTINGS,
        "model": MODEL, "model_digest": MODEL_DIGEST, "identity": identity,
        "prompt": PROMPT, "prompt_sha256": digest(PROMPT.encode()), "output_schema": OUTPUT_SCHEMA,
        "output_schema_sha256": digest(encoded(OUTPUT_SCHEMA)), "pool_context": pool,
        "selection": "All frozen factual schedule slots with repetition == 0, in original order; "
                     "fixed after factual collection and before judge outputs; not held out.",
        "selected_planned": len(schedule), "available_inputs": len(context),
        "max_chat_calls": len(context), "max_wall_seconds": max_wall_seconds,
        "evaluation_context_sha256": digest((out / "evaluation-context.json").read_bytes()),
        "schedule": schedule,
        "interpretation": "Post-collection descriptive comparator on 14 fixed wording/mechanism "
                          "cells; requested seeds do not establish independence. One Qwen judge "
                          "overlaps a factual generator family. No human validation, causal "
                          "identification, benchmark score, or method superiority is established.",
        "failure_policy": "One attempted chat per available input; never regenerate any started "
                          "slot. Invalid output is failure, unknown is abstention, missing input "
                          "has no semantic output. Infrastructure failure stops the invocation; "
                          "resume only never-started slots within the original wall budget.",
        "support_definition": "Evidence-supported means the independent public reference "
                              "derives the same definite label from the allowed readback; "
                              "correct unsupported guesses remain separately counted. This is "
                              "rule-based evidence qualification, not a rationale annotation."}
    write_new(out / "protocol.json", protocol)
    write_new(out / "protocol.sha256.json", {"sha256": digest((out / "protocol.json").read_bytes())})
    return {"output": str(out), "selected_planned": len(schedule), "available_inputs": len(context),
            "protocol_sha256": digest((out / "protocol.json").read_bytes())}


def validate_freeze(out):
    out = Path(out)
    protocol = read_json(out / "protocol.json")
    if (protocol.get("schema_version") != SCHEMA or digest((out / "protocol.json").read_bytes())
            != read_json(out / "protocol.sha256.json")["sha256"]):
        raise ValueError("Judge protocol changed or unsupported")
    if protocol["code_sha256"] != code_hashes():
        raise ValueError("Frozen judge/research/runtime source changed")
    if (protocol["package_version"] != importlib.metadata.version("consequa-x")
            or protocol["python"] != sys.version or protocol["settings"] != SETTINGS
            or protocol["prompt"] != PROMPT or protocol["output_schema"] != OUTPUT_SCHEMA
            or protocol["model"] != MODEL or protocol["model_digest"] != MODEL_DIGEST):
        raise ValueError("Frozen judge environment or definition changed")
    for path, expected in protocol["external_source_sha256"].items():
        if digest(Path(path).read_bytes()) != expected:
            raise ValueError("Frozen factual source or sealed analysis changed")
    if digest((out / "evaluation-context.json").read_bytes()) != protocol["evaluation_context_sha256"]:
        raise ValueError("Private evaluation context changed")
    for slot in protocol["schedule"]:
        if slot["input_status"] == "available":
            if digest((out / slot["input_file"]).read_bytes()) != slot["input_sha256"]:
                raise ValueError("Frozen judge input changed")
    return protocol


class TraceJudge(RecordingPolicy):
    def judge(self, input_value, seed):
        self.validate_local_model(force=True)
        envelope = self._request("/api/chat", request_payload(input_value, seed, {
            "temperature": self.temperature, "num_predict": self.num_predict}))
        return parse_prediction(envelope)


def check_identity(current, frozen):
    if (current["server_version"] != frozen["server_version"]
            or current["models"][MODEL]["tag"]["digest"] != MODEL_DIGEST
            or current["models"][MODEL]["inspection"] != frozen["models"][MODEL]["inspection"]):
        raise PolicyError("Judge daemon/model identity changed since freeze")


def audit_run(out, protocol):
    """Bind saved outputs to exact requests; interrupted slots never become draws."""
    out = Path(out)
    journal = Journal(out / "request-journal.jsonl")
    slots = {entry["slot"]["slot_id"]: entry for entry in protocol["schedule"]}
    calls, finishes, starts = Counter(), defaultdict(list), defaultdict(list)
    for index, event in enumerate(journal.records):
        if event["index"] != index:
            raise ValueError("Judge journal index changed")
        for prefix in ("request", "response"):
            if f"{prefix}_file" in event:
                content = (out / event[f"{prefix}_file"]).read_bytes()
                if digest(content) != event[f"{prefix}_sha256"]:
                    raise ValueError("Captured judge provider bytes changed")
        slot_id = event.get("slot_id")
        if slot_id is not None and slot_id not in slots:
            raise ValueError("Journal has an undeclared slot")
        if event["event"] == "chat_started":
            calls[slot_id] += 1
            entry = slots[slot_id]
            if entry["input_status"] != "available":
                raise ValueError("Judge call made for unavailable input")
            expected = request_payload(read_json(out / entry["input_file"]), entry["judge_seed"])
            if read_json(out / event["request_file"]) != expected:
                raise ValueError("Judge request differs from frozen input/settings")
        if event["event"] == "judge_started":
            starts[slot_id].append(event)
        if event["event"] == "judge_finished":
            finishes[slot_id].append(event)
    if sum(calls.values()) > protocol["max_chat_calls"] or any(n > 1 for n in calls.values()):
        raise ValueError("Judge exceeded one-call-per-input budget")
    receipts = []
    for slot_id, entry in slots.items():
        folder = out / "judgments" / slot_id
        start, final = folder / "started.json", folder / "receipt.json"
        if not start.exists():
            if final.exists() or calls[slot_id] or starts[slot_id] or finishes[slot_id]:
                raise ValueError("Judge output exists without a start")
            receipts.append({"slot_id": slot_id, "status": "unstarted", "attempted_calls": 0})
            continue
        if (len(starts[slot_id]) != 1 or digest(start.read_bytes()) != starts[slot_id][0]["started_sha256"]
                or read_json(start)["entry"] != entry
                or read_json(start)["protocol_sha256"] != read_json(out / "protocol.sha256.json")["sha256"]):
            raise ValueError("Started judge slot binding changed")
        if not final.exists():
            if finishes[slot_id]:
                raise ValueError("Finished journal slot lacks receipt")
            receipts.append({"slot_id": slot_id, "status": "interrupted_partial",
                             "attempted_calls": calls[slot_id]})
            continue
        if len(finishes[slot_id]) != 1 or digest(final.read_bytes()) != finishes[slot_id][0]["receipt_sha256"]:
            raise ValueError("Judge receipt journal binding changed")
        receipt = read_json(final)
        if receipt["slot_id"] != slot_id or receipt["attempted_calls"] != calls[slot_id]:
            raise ValueError("Judge receipt slot/call accounting changed")
        if receipt["status"] == "completed":
            if calls[slot_id] != 1:
                raise ValueError("Completed judge needs exactly one call")
            events = [e for e in journal.records if e["event"] == "chat_received" and e["slot_id"] == slot_id]
            if len(events) != 1 or events[0]["status"] != 200:
                raise ValueError("Completed judge lacks a received response")
            if parse_prediction(read_json(out / events[0]["response_file"])) != receipt["prediction"]:
                raise ValueError("Judge prediction differs from captured response")
        elif receipt["status"] == "input_unavailable":
            if entry["input_status"] != "unavailable" or calls[slot_id] or "prediction" in receipt:
                raise ValueError("Unavailable input has invented judge output")
        elif receipt["status"] != "failed" or "prediction" in receipt:
            raise ValueError("Invalid judge disposition")
        receipts.append(receipt)
    return journal, receipts


def run(output, *, limit=None, inspector=inspect, judge_factory=TraceJudge):
    out = Path(output).resolve()
    protocol = validate_freeze(out)
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("Run limit must be positive")
    lock = out / "runner.lock"
    write_new(lock, {"pid": os.getpid(), "started_utc": now()})
    try:
        journal, _ = audit_run(out, protocol)
        identity = inspector(protocol["settings"])
        check_identity(identity, protocol["identity"])
        previous = [e for e in journal.records if e["event"] == "run_started"]
        beginning = previous[0]["utc"] if previous else now()
        deadline = datetime.fromisoformat(beginning).timestamp() + protocol["max_wall_seconds"]
        journal.append("run_started", frozen_deadline_utc=datetime.fromtimestamp(deadline, timezone.utc).isoformat())
        started = 0
        stopped_reason = "all_never_started_slots_processed"
        for entry in protocol["schedule"]:
            slot_id = entry["slot"]["slot_id"]
            folder = out / "judgments" / slot_id
            if (folder / "started.json").exists():
                continue
            if time.time() >= deadline:
                stopped_reason = "wall_time_budget"
                break
            if limit is not None and started >= limit:
                stopped_reason = "slot_limit"
                break
            start_record = {"entry": entry, "utc": now(),
                            "protocol_sha256": read_json(out / "protocol.sha256.json")["sha256"]}
            write_new(folder / "started.json", start_record)
            journal.append("judge_started", slot_id=slot_id,
                           started_sha256=digest((folder / "started.json").read_bytes()))
            started += 1
            before = time.monotonic()
            recent = len(journal.records)
            receipt = {"slot_id": slot_id, "status": "input_unavailable"}
            infrastructure_failure = False
            if entry["input_status"] == "available":
                judge = judge_factory(MODEL, directory=out, slot=slot_id, journal=journal,
                    max_calls=protocol["max_chat_calls"], deadline_utc=deadline,
                    expected_digest=MODEL_DIGEST, **protocol["settings"])
                try:
                    receipt.update(status="completed", prediction=judge.judge(
                        read_json(out / entry["input_file"]), entry["judge_seed"]))
                except PolicyError as error:
                    infrastructure_failure = isinstance(error, InfrastructurePolicyError)
                    receipt = {"slot_id": slot_id, "status": "failed",
                               "error_type": type(error).__name__, "error": str(error),
                               "infrastructure_failure": infrastructure_failure}
            receipt.update(attempted_calls=sum(e["event"] == "chat_started" for e in journal.records[recent:]),
                           elapsed_seconds=time.monotonic() - before, finished_utc=now())
            write_new(folder / "receipt.json", receipt)
            journal.append("judge_finished", slot_id=slot_id,
                           receipt_sha256=digest((folder / "receipt.json").read_bytes()))
            print(json.dumps({"slot_id": slot_id, "status": receipt["status"]}), flush=True)
            if infrastructure_failure or (receipt["status"] == "failed" and receipt["attempted_calls"] == 0):
                journal.append("run_infrastructure_stop", slot_id=slot_id)
                stopped_reason = "infrastructure_failure"
                break
        journal.append("run_stopped", newly_started_slots=started, stopped_reason=stopped_reason)
        return {"newly_started_slots": started, "selected_planned": protocol["selected_planned"]}
    finally:
        lock.unlink()


def ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def summarize(entries, receipts, context):
    """Selected-slot operational denominators; never manufacture pool-level scores."""
    by_id = {r["slot_id"]: r for r in receipts}
    statuses = Counter(by_id[e["slot"]["slot_id"]]["status"] for e in entries)
    methods = ("local_trace_judge", "independent_public_reference", "consequa_state_origin")
    result = {"selected_planned": len(entries), "available_factual_inputs": sum(
        e["input_status"] == "available" for e in entries), "judge_status": dict(statuses),
        "attempted_chat_calls": sum(by_id[e["slot"]["slot_id"]].get("attempted_calls", 0)
                                    for e in entries), "methods": {}}
    for method in methods:
        targets = {}
        for target in ("state", "action_linked", "origin"):
            completed = assessable = claims = correct = wrong = supported = unsupported_correct = 0
            all_definite = unassessable_claims = all_supported = 0
            false_positive = false_negative = 0
            for entry in entries:
                slot_id = entry["slot"]["slot_id"]
                if entry["input_status"] != "available":
                    continue
                evaluation = context[slot_id]
                if method == "local_trace_judge":
                    receipt = by_id[slot_id]
                    if receipt["status"] != "completed":
                        continue
                    prediction = receipt["prediction"][target]
                else:
                    prediction = evaluation["baselines"][method][target]
                completed += 1
                gold = evaluation["gold"][target]
                known_gold = gold != "unknown" if target == "origin" else gold is not None
                known_prediction = prediction != "unknown" if target == "origin" else prediction is not None
                reference = evaluation["baselines"]["independent_public_reference"][target]
                reference_known = reference != "unknown" if target == "origin" else reference is not None
                qualified = (method in READBACK_METHODS and known_prediction and reference_known
                             and prediction == reference)
                all_definite += known_prediction
                all_supported += qualified
                if not known_gold:
                    unassessable_claims += known_prediction
                    continue
                assessable += 1
                if not known_prediction:
                    continue
                claims += 1
                correct += prediction == gold
                wrong += prediction != gold
                if target != "origin":
                    false_positive += prediction is True and gold is False
                    false_negative += prediction is False and gold is True
                supported += qualified
                unsupported_correct += prediction == gold and not qualified
            targets[target] = {"completed_outputs": completed, "gold_assessable_outputs": assessable,
                "claims": claims, "correct_claims": correct, "wrong_claims": wrong,
                "abstentions": assessable - claims, "evidence_supported_claims": supported,
                "all_definite_outputs": all_definite,
                "claims_with_unassessable_gold": unassessable_claims,
                "all_evidence_supported_claims": all_supported,
                "unsupported_correct_guesses": unsupported_correct, "false_positive": false_positive,
                "false_negative": false_negative, "coverage": ratio(claims, assessable),
                "claim_error": ratio(wrong, claims), "correct_yield": ratio(correct, assessable),
                "selected_planned_correct_yield": ratio(correct, len(entries)),
                "selected_available_input_correct_yield": ratio(correct, result["available_factual_inputs"])}
        result["methods"][method] = targets
    return result


def analyze(output, destination):
    out, dest = Path(output).resolve(), Path(destination).resolve()
    if (out / "runner.lock").exists():
        raise ValueError("Cannot finalize judge analysis while runner lock exists")
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Analysis requires a new or empty output directory")
    protocol = validate_freeze(out)
    journal, receipts = audit_run(out, protocol)
    if (not journal.records or journal.records[-1]["event"] != "run_stopped"
            or not any(event["event"] == "run_started" for event in journal.records)):
        raise ValueError("Analysis requires a terminal valid run_stopped event")
    statuses = Counter(receipt["status"] for receipt in receipts)
    stopped_reason = journal.records[-1].get("stopped_reason")
    if stopped_reason not in {"all_never_started_slots_processed", "wall_time_budget",
                              "slot_limit", "infrastructure_failure"}:
        raise ValueError("Missing or invalid explicit run-stop reason")
    final = not statuses["unstarted"] or stopped_reason == "wall_time_budget"
    disposition = ("closed_wall_budget" if stopped_reason == "wall_time_budget" else
                   "closed_with_interrupted_partial" if final and statuses["interrupted_partial"] else
                   "completed" if final else "incomplete")
    context = read_json(out / "evaluation-context.json")
    strata = {}
    for axes in (("model", "prompt_version"), ("case_id",), ("model",)):
        buckets = defaultdict(list)
        for entry in protocol["schedule"]:
            key = json.dumps({axis: entry["slot"][axis] for axis in axes}, sort_keys=True)
            buckets[key].append(entry)
        strata["/".join(axes)] = {key: summarize(entries, receipts, context)
                                  for key, entries in sorted(buckets.items())}
    result = {"schema_version": SCHEMA + "-analysis", "protocol_sha256": digest(
        (out / "protocol.json").read_bytes()), "pool_context": protocol["pool_context"],
        "final": final, "collection_state": disposition, "stopped_reason": stopped_reason,
        "selection": protocol["selection"], "interpretation": protocol["interpretation"],
        "support_definition": protocol["support_definition"],
        "summary": summarize(protocol["schedule"], receipts, context),
        "strata": strata, "receipts": receipts,
        "journal_sha256": digest((out / "request-journal.jsonl").read_bytes())
                           if (out / "request-journal.jsonl").exists() else None,
        "attempted_calls_including_partial": sum(e["event"] == "chat_started" for e in journal.records)}
    result["summary"]["attempted_chat_calls"] = result["attempted_calls_including_partial"]
    write_new(dest / "analysis.json", result)
    lines = ["# Matched local trace judge", "", protocol["selection"], "",
        f"Collection state: {disposition}; final: {str(final).lower()}; stop reason: {stopped_reason}.", "",
        "Pool context: 504 factual slots, 503 completed and one failed. These are not judge denominators.",
        f"Selected judge slots: {protocol['selected_planned']}; available factual inputs: {protocol['available_inputs']}.",
        f"Judge dispositions: {json.dumps(result['summary']['judge_status'], sort_keys=True)}.", "",
        "| Method | Target | Claims / assessable outputs | Wrong / claims | Correct / selected planned |",
        "| --- | --- | ---: | ---: | ---: |"]
    for method, targets in result["summary"]["methods"].items():
        for target, metric in targets.items():
            lines.append(f"| {method} | {target} | {metric['claims']} / {metric['gold_assessable_outputs']} | "
                         f"{metric['wrong_claims']} / {metric['claims']} | "
                         f"{metric['correct_claims']} / {protocol['selected_planned']} |")
    lines.extend(["", "Zero denominators are undefined. Abstentions, failures and unavailable inputs "
                  "do not count as correct claims.", "", protocol["support_definition"], "",
                  protocol["interpretation"], ""])
    write_bytes_new(dest / "analysis.md", "\n".join(lines).encode())
    write_new(dest / "manifest.json", {"files": {p.name: digest(p.read_bytes())
        for p in sorted(dest.iterdir()) if p.is_file()}})
    return {"output": str(dest), "judge_status": result["summary"]["judge_status"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freezer = commands.add_parser("freeze")
    freezer.add_argument("--study-output", required=True)
    freezer.add_argument("--study-analysis", required=True)
    freezer.add_argument("--output", required=True)
    freezer.add_argument("--max-wall-seconds", type=float, default=7200)
    runner = commands.add_parser("run")
    runner.add_argument("--output", required=True)
    runner.add_argument("--limit", type=int)
    analyzer = commands.add_parser("analyze")
    analyzer.add_argument("--study-output", required=True)
    analyzer.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            result = freeze(args.study_output, args.study_analysis, args.output,
                            max_wall_seconds=args.max_wall_seconds)
        elif args.command == "run":
            result = run(args.output, limit=args.limit)
        else:
            result = analyze(args.study_output, args.output)
        print(json.dumps(result))
    except (PolicyError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
