"""Stdlib postcollection integrity/lifecycle audit; never runs the frozen study.

This code imports no world, runner, controller, framework, or statistical helper.
It reads every retained SQLite snapshot independently. Its author also authored
the controllers; synthetic audit-test author also authored the world. This is
implementation separation, not independent-human or external replication.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import tempfile


class AuditError(ValueError):
    """A retained artifact violates a declared integrity or lifecycle invariant."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _safe_path(root, relative):
    require(isinstance(relative, str) and "\\" not in relative, "nonportable artifact path")
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and parts.parts and ":" not in relative
            and all(part not in (".", "..") for part in parts.parts), "unsafe artifact path")
    path = root.joinpath(*parts.parts)
    require(not any(parent.is_symlink() for parent in (path, *path.parents)),
            "symlinks are forbidden in retained artifact paths")
    require(path.resolve().is_relative_to(root.resolve()), "artifact path escapes study root")
    return path


def _int(value, name):
    require(type(value) is int and value >= 0, f"invalid {name}")
    return value


def _peak(rows, start, end):
    """Independent interval-point count, including simultaneous changes."""
    points = {start, end}
    for row in rows:
        for instant in (row["committed_at_ms"], row.get("removed_at_ms", end + 1)):
            if start <= instant <= end:
                points.add(instant)
    return max(sum(row["committed_at_ms"] <= instant
                   < row.get("removed_at_ms", end + 1) for row in rows) for instant in points)


def _target(rows, expected, deadline, horizon, exact):
    matching = [row for row in rows if all(row.get(k) == v for k, v in expected.items())]
    eligible = [row for row in matching if row["committed_at_ms"] <= deadline
                and row.get("removed_at_ms", horizon + 1) > horizon]
    peak = _peak(matching, deadline, horizon)
    satisfied = bool(eligible) if exact is None else len(eligible) == exact and peak == exact
    return matching, eligible, peak, satisfied


def _business_tables(db, domain, effects):
    tables = {"inventory_reservation": "inventory_reservations",
              "support_transition": "ticket_transitions",
              "delivery_registration": "delivery_registrations"}
    require(domain in tables, "unsupported persisted application domain")
    for candidate, table in tables.items():
        business = {row["effect_id"]: dict(row) for row in db.execute(f"SELECT * FROM {table}")}
        if candidate != domain:
            require(not business, "effects leaked into another domain's business table")
            continue
        require(set(business) == set(effects), "audit/business effect identities disagree")
        for identity, effect in effects.items():
            payload, row = effect["payload"], business[identity]
            removed = effect["removed_at_ms"] is not None
            if domain == "inventory_reservation":
                require(json.loads(row["stock_key"]) == [payload["warehouse"], payload["sku"]],
                        "reservation stock identity differs from audit payload")
                require(row["quantity"] == payload["quantity"], "reservation quantity mismatch")
                state = "released" if removed else "active"
            elif domain == "support_transition":
                require(all(row[k] == payload[k] for k in ("ticket_id", "status", "queue")),
                        "ticket transition differs from audit payload")
                state = "reversed" if removed else "active"
            else:
                require(all(row[k] == payload[k]
                            for k in ("artifact_id", "delivery_channel", "checksum")),
                        "delivery registration differs from audit payload")
                state = "revoked" if removed else "active"
            require(row["state"] == state, "business lifecycle state disagrees with tombstone")
    if domain == "inventory_reservation":
        stock_rows = list(db.execute("SELECT * FROM inventory_stock"))
        known_stocks = {row["stock_key"] for row in stock_rows}
        for effect in effects.values():
            key = json.dumps([effect["payload"]["warehouse"], effect["payload"]["sku"]],
                             separators=(",", ":"))
            require(key in known_stocks, "reservation references nonexistent stock")
            require(type(effect["payload"]["quantity"]) is int and effect["payload"]["quantity"] > 0,
                    "persisted reservation has invalid quantity")
        for row in stock_rows:
            require(type(row["available"]) is int and row["available"] >= 0,
                    "negative or noninteger inventory availability")
    if domain == "support_transition":
        by_ticket = defaultdict(list)
        for effect in effects.values():
            by_ticket[effect["payload"]["ticket_id"]].append(effect)
        tickets = {row["ticket_id"]: dict(row) for row in db.execute("SELECT * FROM support_tickets")}
        require(set(by_ticket) <= set(tickets), "transition has no persisted ticket")
        for identity, rows in by_ticket.items():
            active = [row for row in rows if row["removed_at_ms"] is None]
            ticket = tickets[identity]
            if active:
                latest = max(active, key=lambda row: (row["committed_at_ms"], row["effect_id"]))
                require((ticket["status"], ticket["queue"]) ==
                        (latest["payload"]["status"], latest["payload"]["queue"]),
                        "ticket current state disagrees with active lifecycle")
            else:
                latest_time = max(row["removed_at_ms"] for row in rows)
                possible_queues = {row["payload"]["queue"] for row in rows
                                   if row["removed_at_ms"] == latest_time}
                require(ticket["status"] == "open" and ticket["queue"] in possible_queues,
                        "reversed ticket has inconsistent current state")


def audit_database(db_path: Path, public_case: dict, truth_at_ms: int) -> dict:
    """Read immutable persisted audit/business tables and recompute both targets."""
    at = _int(truth_at_ms, "truth time")
    db_path = Path(db_path).resolve()
    require(db_path.is_file(), "SQLite snapshot is missing")
    connection = sqlite3.connect(db_path.as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        require(connection.execute("PRAGMA quick_check").fetchone()[0] == "ok", "SQLite integrity failure")
        require(not connection.execute("PRAGMA foreign_key_check").fetchall(), "foreign key violation")
        effects, records = {}, []
        for raw in connection.execute("SELECT * FROM effects ORDER BY committed_at_ms,effect_id"):
            row = dict(raw)
            committed = _int(row["committed_at_ms"], "commit time")
            require(committed <= at, "persisted commit exceeds evaluation horizon")
            if row["removed_at_ms"] is not None:
                require(committed <= _int(row["removed_at_ms"], "removal time") <= at,
                        "invalid persisted lifecycle interval")
            payload, reported = json.loads(row["payload_json"]), json.loads(row["reported_origin_json"])
            require(type(payload) is dict and type(reported) is dict, "nonobject stored payload")
            require(set(reported) <= {"action_id", "actor", "attempt_id"},
                    "unexpected stored origin field")
            for key, causal in (("action_id", "causal_action_id"), ("actor", "causal_actor"),
                                ("attempt_id", "causal_attempt_id")):
                require(key not in reported or reported[key] == row[causal],
                        "reported origin contradicts persisted causal ownership")
            require(row["effect_id"] not in effects, "duplicate audit effect identity")
            row["payload"] = payload
            effects[row["effect_id"]] = row
            record = {**payload, **reported, "effect_id": row["effect_id"],
                      "committed_at_ms": committed, "_causal_action_id": row["causal_action_id"],
                      "_causal_actor": row["causal_actor"], "_causal_attempt_id": row["causal_attempt_id"]}
            if row["removed_at_ms"] is not None:
                record["removed_at_ms"] = row["removed_at_ms"]
            records.append(record)
        _business_tables(connection, public_case["domain"], effects)
        events = []
        for raw in connection.execute("SELECT * FROM pending_events ORDER BY due_ms,seq"):
            row = dict(raw)
            _int(row["due_ms"], "pending event time")
            require(row["kind"] in ("commit", "remove") and row["applied"] in (0, 1),
                    "invalid persisted pending event")
            require(bool(row["applied"]) == (row["due_ms"] <= at),
                    "pending event application does not cover evaluation horizon")
            row["event"] = json.loads(row["event_json"])
            events.append(row)
        committed_plans = {event["event"]["effect_id"]: event for event in events
                           if event["kind"] == "commit"}
        for identity, effect in effects.items():
            require(identity in committed_plans, "persisted effect has no scheduled lifecycle event")
            event = committed_plans[identity]
            require(event["applied"] == 1 and event["due_ms"] == effect["committed_at_ms"],
                    "persisted commit time disagrees with lifecycle schedule")
            require(event["event"]["payload"] == effect["payload"], "scheduled/audit payload mismatch")
            origin = event["event"]["origin"]
            require(all(origin.get(key) == effect[column] for key, column in
                        (("action_id", "causal_action_id"), ("actor", "causal_actor"),
                         ("attempt_id", "causal_attempt_id"))), "scheduled causal origin mismatch")
            require(event["event"]["reported_origin"] == json.loads(effect["reported_origin_json"]),
                    "scheduled reported origin mismatch")
            if effect["removed_at_ms"] is not None:
                removed = effect["removed_at_ms"]
                explicit = any(item["kind"] == "remove" and item["applied"]
                               and item["due_ms"] == removed
                               and item["event"]["effect_id"] == identity for item in events)
                superseded = public_case["domain"] == "support_transition" and any(
                    item["kind"] == "commit" and item["applied"] and item["due_ms"] == removed
                    and item["event"]["effect_id"] in effects
                    and item["event"]["payload"]["ticket_id"] == effect["payload"]["ticket_id"]
                    and any(item["event"]["payload"][key] != effect["payload"][key]
                            for key in ("status", "queue")) for item in events)
                require(explicit or superseded, "removal tombstone lacks an applied lifecycle cause")
        pending_count = sum(not row["applied"] for row in events)
        idempotency = [dict(row) for row in connection.execute("SELECT * FROM idempotency")]
    finally:
        connection.close()

    expected, scope = public_case["target"]["expected"], public_case["scope"]
    exact = public_case["target"]["exact_count"]
    registered = public_case.get("registered_at_ms", public_case.get("initial_at_ms", 0))
    deadline, horizon = public_case["deadline_ms"], public_case["deadline_ms"] + public_case["stability_ms"]
    recovery, safety = public_case["recovery_deadline_ms"], public_case["safety_horizon_ms"]
    relevant = [row for row in records if registered <= row["committed_at_ms"] <= horizon
                and all(row.get(k) == v for k, v in scope.items())]
    matching, eligible, peak, satisfied = _target(relevant, expected, deadline, horizon, exact)
    def own(row):
        return (row["_causal_action_id"] == public_case["operation_id"]
                and row["_causal_actor"] == public_case["actor"])
    own_original, linked = [row for row in relevant if own(row)], [row for row in eligible if own(row)]
    safety_rows = [row for row in records if row["committed_at_ms"] <= safety]
    own_rows = [row for row in safety_rows if own(row)]
    _, recovery_eligible, recovery_peak, recovery_ok = _target(safety_rows, expected, recovery, safety, exact)
    linked_recovery = [row for row in recovery_eligible if own(row)]
    unwanted = [row for row in own_rows if any(row.get(k) != v for k, v in expected.items())
                or row["committed_at_ms"] > recovery]
    duplicate_count = max(0, len(own_rows) - (1 if exact is None else exact))
    return {"at_ms": at, "horizon_reached": at >= horizon,
            "target_satisfied": satisfied if at >= horizon else None,
            "stable_target": satisfied if at >= horizon else None,
            "eligible_target_count": len(eligible), "peak_target_count": peak,
            "target_count": sum(row["committed_at_ms"] <= horizon
                                < row.get("removed_at_ms", horizon + 1) for row in matching),
            "linked_target_count": len(linked),
            "linked_target_satisfied": (satisfied and (bool(linked) if exact is None else len(linked) == exact))
                if at >= horizon else None,
            "sla_duplicate_count": max(0, len(own_original) - (1 if exact is None else exact)),
            "safety_horizon_reached": at >= safety,
            "eventual_recovery_satisfied": recovery_ok if at >= safety else None,
            "linked_recovery_satisfied": (recovery_ok and (bool(linked_recovery) if exact is None
                                                         else len(linked_recovery) == exact))
                if at >= safety else None,
            "linked_recovery_target_count": len(linked_recovery),
            "recovery_eligible_target_count": len(recovery_eligible),
            "recovery_peak_target_count": recovery_peak,
            "own_unwanted_effect_count": len(unwanted),
            "own_unwanted_effect_ids": [row["effect_id"] for row in unwanted],
            "own_effect_count": len(own_rows),
            "own_reversed_effect_count": sum(row.get("removed_at_ms", safety + 1) <= safety for row in own_rows),
            "duplicate_count": duplicate_count,
            "duplicate_effect_ids": [row["effect_id"] for row in own_rows] if duplicate_count else [],
            "records": records, "pending_event_count": pending_count,
            "metrics": {"committed_effects": len(records),
                        "removed_effects": sum("removed_at_ms" in row for row in records)},
            "_events": events, "_idempotency": idempotency}


RESPONSE_KEYS = {"status", "attempt_id", "response_at_ms", "result", "provider_request_id",
                 "terminal_not_committed"}
OBSERVATION_KEYS = {"observation_id", "source", "observed_at_ms", "as_of_ms", "scope",
                    "records", "complete", "available"}
DECISION_KEYS = {"kind", "at_ms", "reason", "action_id", "attempt_id", "idempotency_key",
                 "scheduled_at_ms"}
FORBIDDEN_INPUT_KEYS = {"case_id", "family_id", "_world", "truth", "evaluator_truth",
                        "hidden_config", "ground_truth"}


def _no_hidden(value):
    if isinstance(value, dict):
        forbidden = set(value) & FORBIDDEN_INPUT_KEYS
        forbidden.update(key for key in value if key.startswith("_causal"))
        require(not forbidden, f"hidden evaluator fields reached controller input: {sorted(forbidden)}")
        for child in value.values():
            _no_hidden(child)
    elif isinstance(value, list):
        for child in value:
            _no_hidden(child)


def _public_trajectory(trial):
    pc = trial["public_case"]
    business = set(pc["target"]["expected"]) | set(pc.get("payload", {})) | set(pc["scope"])
    rows, last_time, outstanding = trial["trajectory"], -1, None
    counts = Counter()
    responses, observations = [], []
    for event in rows:
        at = _int(event["at_ms"], "trajectory time")
        require(at >= last_time, "trajectory time moved backwards")
        last_time = at
        kind = event["kind"]
        require(kind in {"dispatch", "response", "read", "readback", "wait", "stop", "abstain"},
                "unknown trajectory event kind")
        if "decision" in event:
            decision = event["decision"]
            require(set(decision) <= DECISION_KEYS, "unallowlisted controller decision field")
            _no_hidden(decision)
        if kind == "dispatch":
            counts["dispatches"] += 1
            decision = event["decision"]
            expected_attempt = f"{pc['operation_id']}:attempt-{counts['dispatches']}"
            require(outstanding is None, "dispatch occurred before previous public response")
            require(decision.get("action_id") == pc["operation_id"]
                    and decision.get("idempotency_key") == pc["operation_id"]
                    and decision.get("attempt_id") == expected_attempt,
                    "dispatch changed stable action/attempt identity")
            require(at <= pc["deadline_ms"] if counts["dispatches"] == 1 else at < pc["deadline_ms"],
                    "dispatch cannot meet the original fixed deadline")
            if counts["dispatches"] > 1 and trial.get("method") != "response_retry":
                native = (pc.get("native_idempotency") is True and responses
                          and responses[-1][1]["status"] == "timeout")
                all_terminal = (len(responses) == counts["dispatches"] - 1
                                and all(response.get("terminal_not_committed") is True
                                        for _, response in responses))
                absent = False
                if observations:
                    read_at, latest = observations[-1]
                    registration = pc.get("registered_at_ms", pc.get("initial_at_ms", 0))
                    absent = (read_at == at and latest["as_of_ms"] >= at
                              and latest["complete"] and latest["available"]
                              and latest["source"] == trial["source_receipt"]["source"]
                              and all(latest["scope"].get(key) == value for key, value in pc["scope"].items())
                              and not any(registration <= record["committed_at_ms"] <= at
                                          for record in latest["records"]))
                require(native or (all_terminal and absent), "readback controller retried without an admitted safety gate")
            outstanding = expected_attempt
        elif kind == "response":
            response = event["response"]
            require(set(response) <= RESPONSE_KEYS,
                    f"unallowlisted response fields: {sorted(set(response) - RESPONSE_KEYS)}")
            _no_hidden(response)
            require(response.get("status") in {"success", "error", "timeout"}, "invalid response status")
            require(response.get("attempt_id") == outstanding, "response attempt mismatch")
            require(response.get("response_at_ms", at) == at, "response callback time mismatch")
            if "terminal_not_committed" in response:
                require(type(response["terminal_not_committed"]) is bool, "invalid terminal flag")
            outstanding = None
            responses.append((at, response))
        elif kind == "readback":
            counts["reads"] += 1
            obs = event["observation"]
            require(set(obs) == OBSERVATION_KEYS, "unallowlisted observation fields")
            _no_hidden(obs)
            require(obs["observed_at_ms"] == at and 0 <= obs["as_of_ms"] <= at,
                    "invalid admitted readback time")
            require(type(obs["available"]) is bool and type(obs["complete"]) is bool,
                    "invalid readback completeness/availability type")
            for record in obs["records"]:
                require(set(record) <= business | {"effect_id", "committed_at_ms", "removed_at_ms",
                                                   "action_id", "actor", "attempt_id"},
                        "unallowlisted readback record field")
            observations.append((at, obs))
        elif kind == "wait":
            counts["waits"] += 1
    require(outstanding is None or trial.get("status") == "failed", "trial ended before response callback")
    return counts, responses, observations


def _check_observations(observations, database, source_receipt):
    by_id = {row["effect_id"]: row for row in database["records"]}
    seen = set()
    for at, obs in observations:
        require(obs["observation_id"] not in seen, "duplicate readback observation ID")
        seen.add(obs["observation_id"])
        require(obs["source"] == source_receipt["source"], "readback source mismatch")
        actual = {}
        for identity, record in by_id.items():
            if record["committed_at_ms"] > obs["as_of_ms"]:
                continue
            historical = {key: value for key, value in record.items() if not key.startswith("_causal")}
            if historical.get("removed_at_ms", at + 1) > obs["as_of_ms"]:
                historical.pop("removed_at_ms", None)
            if all(historical.get(key) == value for key, value in obs["scope"].items()):
                actual[identity] = historical
        returned = set()
        for record in obs["records"]:
            identity = record.get("effect_id")
            require(identity in actual and identity not in returned, "readback fabricates/duplicates an effect")
            returned.add(identity)
            historical = actual[identity]
            omitted = set(historical) - set(record)
            require(omitted <= {"action_id", "actor", "attempt_id"}, "readback omits business/lifecycle data")
            require(all(key in historical and historical[key] == value for key, value in record.items()),
                    "readback record differs from actual historical SQLite state")
        if not obs["available"]:
            require(not returned and not obs["complete"], "unavailable readback claims data/completeness")
        if obs["complete"]:
            require(returned == set(actual), "complete readback omits persisted history")


def recompute_metrics(trial, database):
    report = trial["report"]
    state, linked = report.get("reported_state"), report.get("reported_action_linked")
    require(state is None or type(state) is bool, "invalid reported state claim")
    require(linked is None or type(linked) is bool, "invalid reported linked claim")
    original, recovery = database["target_satisfied"], database["eventual_recovery_satisfied"]
    duplicate, unwanted = database["duplicate_count"] > 0, database["own_unwanted_effect_count"] > 0
    safe_recovery = bool(recovery) and not duplicate and not unwanted
    return {"completed": True, "operational_safe_recovery": safe_recovery,
            "original_completion": bool(original),
            "recovery_completion": bool(recovery), "duplicate_event": duplicate,
            "unwanted_event": unwanted, "safe_recovery": safe_recovery,
            "state_false_success": state is True and original is False,
            "action_linked_false_success": linked is True and database["linked_target_satisfied"] is False,
            "state_wrong_definite": state is not None and state != original,
            "action_linked_wrong_definite": linked is not None and linked != database["linked_target_satisfied"],
            "state_definite": state is not None, "state_abstention": state is None,
            "action_linked_definite": linked is not None, "action_linked_abstention": linked is None,
            "dispatches": report["dispatches"], "reads": report["reads"], "waits": report["waits"],
            "decision_time_ms": trial["decision_at_ms"], "own_effect_count": database["own_effect_count"],
            "duplicate_count": database["duplicate_count"],
            "unwanted_effect_count": database["own_unwanted_effect_count"]}


def _failed_metrics(trial):
    metrics = trial["metrics"]
    require(isinstance(metrics, dict)
            and set(metrics) == {"completed", "operational_safe_recovery"}
            and all(value is False for value in metrics.values()),
            "failed trial must retain operational failure and no semantic endpoint metrics")
    return {"completed": False, "operational_safe_recovery": False}


def audit_trial(trial: dict, db_path: Path) -> dict:
    """Check admitted trajectory, DB lifecycle truth, counters and recorded metrics."""
    counts, responses, observations = _public_trajectory(trial)
    pc = trial["public_case"]
    at = trial.get("truth", {}).get("at_ms", pc["safety_horizon_ms"])
    database = audit_database(db_path, pc, at)
    for _, response in responses:
        if response.get("terminal_not_committed") is True:
            attempt = response["attempt_id"]
            require(not any(event["kind"] == "commit"
                            and event["event"]["origin"].get("attempt_id") == attempt
                            for event in database["_events"]),
                    "terminal no-commit flag contradicts persisted attempt lifecycle")
            require(not any(row["_causal_attempt_id"] == attempt for row in database["records"]),
                    "terminal no-commit flag contradicts actual effect")
            if pc.get("native_idempotency"):
                for identity in database["_idempotency"]:
                    if identity["operation_id"] == pc["operation_id"]:
                        first = int(identity["first_attempt_id"].rsplit("-", 1)[1])
                        current = int(attempt.rsplit("-", 1)[1])
                        require(current <= first, "native replay incorrectly claims terminal finality")
    _check_observations(observations, database, trial["source_receipt"])
    if trial.get("status") == "failed":
        return _failed_metrics(trial)
    require(trial.get("status") == "completed", "invalid retained trial status")
    require(at >= pc["safety_horizon_ms"], "completed trial lacks safety-horizon follow-through")
    truth = trial["truth"]
    for key, actual in database.items():
        if key.startswith("_") or key == "metrics":
            continue
        require(key in truth and truth[key] == actual, f"persisted truth mismatch: {key}")
    for key, actual in database["metrics"].items():
        require(truth["metrics"][key] == actual, f"actual database counter mismatch: {key}")
    require(counts["dispatches"] <= 2 and counts["reads"] <= 4, "shared call/query budget was exceeded")
    require(trial["report"].get("native_idempotency") == pc.get("native_idempotency", False),
            "controller provider capability differs from paired public declaration")
    native_replays = 0
    for identity in database["_idempotency"]:
        require(pc.get("native_idempotency") and identity["operation_id"] == pc["operation_id"]
                and identity["actor"] == pc["actor"], "persisted idempotency identity/capability mismatch")
        first = int(identity["first_attempt_id"].rsplit("-", 1)[1])
        require(1 <= first <= counts["dispatches"], "idempotency reservation has no dispatched attempt")
        native_replays += counts["dispatches"] - first
    business_rejections = 0
    actual_ids = {row["effect_id"] for row in database["records"]}
    commit_sequence = {event["event"]["effect_id"]: (event["due_ms"], event["seq"])
                       for event in database["_events"] if event["kind"] == "commit"}
    for event in database["_events"]:
        if event["kind"] != "commit" or not event["applied"] or event["event"]["effect_id"] in actual_ids:
            continue
        plan = event["event"]
        native_suppression = plan.get("native") and any(
            row["_causal_action_id"] == plan["origin"].get("action_id")
            and row["_causal_actor"] == plan["origin"]["actor"]
            and commit_sequence[row["effect_id"]] < (event["due_ms"], event["seq"])
            for row in database["records"])
        if not native_suppression:
            require(pc["domain"] == "inventory_reservation", "applied noninventory commit lost its actual effect")
            business_rejections += 1
    call_metrics = {"dispatch_calls": counts["dispatches"], "readback_calls": counts["reads"],
                    "available_readbacks": sum(obs["available"] for _, obs in observations),
                    "records_returned": sum(len(obs["records"]) for _, obs in observations),
                    "identity_rejections": 0, "native_replays": native_replays,
                    "new_requests": counts["dispatches"] - native_replays,
                    "business_rejections": business_rejections}
    for key, actual in call_metrics.items():
        require(truth["metrics"][key] == actual, f"actual call/event counter mismatch: {key}")
    for key in ("dispatches", "reads", "waits"):
        require(trial["report"][key] == counts[key], f"trajectory/report counter mismatch: {key}")
    dispatch_log, readback_log = truth["dispatch_log"], truth["readback_log"]
    require(len(dispatch_log) == counts["dispatches"] and len(readback_log) == counts["reads"],
            "world call log counters differ from actual trajectory")
    for (_, response), logged in zip(responses, dispatch_log):
        require(all(logged.get(key) == value for key, value in response.items()), "public response/log mismatch")
    for (at, obs), logged in zip(observations, readback_log):
        expected = {"at_ms": at, "observation_id": obs["observation_id"], "as_of_ms": obs["as_of_ms"],
                    "records_returned": len(obs["records"]), "available": obs["available"],
                    "complete": obs["complete"]}
        require(logged == expected, "admitted readback/world log mismatch")
    if "framework_trace" in trial["report"]:
        _no_hidden(trial["report"]["framework_trace"])
    metrics = recompute_metrics(trial, database)
    require(trial["metrics"] == metrics, "recorded endpoint metric mismatch")
    return metrics


ENDPOINTS = ("operational_safe_recovery", "original_completion", "recovery_completion", "safe_recovery", "duplicate_event",
             "unwanted_event", "state_false_success", "action_linked_false_success",
             "state_wrong_definite", "action_linked_wrong_definite", "state_definite",
             "state_abstention", "action_linked_definite", "action_linked_abstention",
             "dispatches", "reads", "waits", "decision_time_ms", "own_effect_count",
             "duplicate_count", "unwanted_effect_count")
METHODS = ("response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll")
CONTRASTS = tuple(("consequax_poll", method) for method in METHODS if method != "consequax_poll")


def _aggregate(rows):
    completed = sum(row["status"] == "completed" for row in rows)
    metrics = {}
    for name in ENDPOINTS:
        values = [row["metrics"][name] for row in rows if name in row["metrics"]]
        metrics[name] = {"sum": sum(values), "observed": len(values),
                         "unavailable": len(rows) - len(values),
                         "mean": math.fsum(values) / len(values) if values else None}
    return {"planned": len(rows), "completed": completed,
            "failed": len(rows) - completed, "metrics": metrics}


def recompute_summary(rows, protocol):
    """Independent finite-suite totals/paired differences, no inferential sampling."""
    summary = {"schema": protocol["schema"], "planned_trials": len(protocol["schedule"]),
               "completed_trials": sum(row["status"] == "completed" for row in rows),
               "failed_trials": sum(row["status"] != "completed" for row in rows),
               "inference_scope": protocol["design"]["analysis"]}
    for label, field in (("methods", "method"), ("families", "family_id"), ("cases", "case_id")):
        partitions = defaultdict(list)
        for row in rows:
            key = (row[field],) if label == "methods" else (row[field], row["method"])
            partitions[key].append(row)
        summary[label] = []
        for key in sorted(partitions):
            descriptor = {field: key[0]}
            if len(key) == 2:
                descriptor["method"] = key[1]
            summary[label].append({**descriptor, **_aggregate(partitions[key])})
    paired = {(row["case_id"], row["seed"], row["method"]): row for row in rows}
    units = sorted({(row["case_id"], row["seed"]) for row in rows})
    contrasts = []
    for left, right in CONTRASTS:
        endpoints = {}
        for name in ENDPOINTS:
            grouped = defaultdict(list)
            for case, seed in units:
                a, b = paired[(case, seed, left)], paired[(case, seed, right)]
                if name in a["metrics"] and name in b["metrics"]:
                    grouped[a["family_id"]].append(a["metrics"][name] - b["metrics"][name])
            family_rows = [{"family_id": family, "pairs": len(values),
                            "sum_difference": sum(values),
                            "mean_difference": math.fsum(values) / len(values)}
                           for family, values in sorted(grouped.items())]
            count = sum(row["pairs"] for row in family_rows)
            endpoints[name] = {"pairs": count, "unavailable_pairs": len(units) - count,
                               "mean_difference": math.fsum(row["sum_difference"] for row in family_rows) / count
                                   if count else None,
                               "equal_family_mean_difference": math.fsum(row["mean_difference"] for row in family_rows)
                                   / len(family_rows) if family_rows else None,
                               "by_family": family_rows}
        contrasts.append({"left": left, "right": right, "planned_pairs": len(units), "metrics": endpoints})
    summary["paired_contrasts"] = contrasts
    return summary


def _same(left, right, path="root"):
    if isinstance(left, dict) and isinstance(right, dict):
        require(set(left) == set(right), f"summary keys mismatch at {path}")
        for key in left:
            _same(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, list) and isinstance(right, list):
        require(len(left) == len(right), f"summary length mismatch at {path}")
        for index, (a, b) in enumerate(zip(left, right)):
            _same(a, b, f"{path}[{index}]")
    elif type(left) is float or type(right) is float:
        require(isinstance(left, (int, float)) and isinstance(right, (int, float))
                and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12),
                f"summary numeric mismatch at {path}")
    else:
        require(left == right, f"summary value mismatch at {path}")


def audit_artifact_manifest(study_dir):
    """Bind every retained byte/path to the completion receipt before analysis."""
    root = Path(study_dir).resolve()
    receipt_path, manifest_path = root / "completion-receipt.json", root / "manifest.json"
    receipt, manifest = load_json(receipt_path), load_json(manifest_path)
    require(receipt.get("complete") is True and manifest.get("complete") is True,
            "study collection is not declared complete")
    require(sha256(manifest_path.read_bytes()) == receipt["manifest_sha256"], "manifest hash mismatch")
    files = manifest["files"]
    for name, digest in files.items():
        path = _safe_path(root, name)
        require(path.is_file() and sha256(path.read_bytes()) == digest, f"artifact hash mismatch: {name}")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(actual == set(files) | {"manifest.json", "completion-receipt.json"},
            "retained artifact inventory contains missing or unmanifested files")
    require("protocol.json" in files and sha256((root / "protocol.json").read_bytes())
            == receipt["protocol_sha256"], "protocol completion hash mismatch")
    return receipt, manifest


def _verify_source_runtime(protocol):
    source, runtime = protocol["source"], protocol["runtime"]
    required_sources = {"research/recovery_study/controllers.py", "research/recovery_study/world.py",
                        "research/recovery_study/heldout_cases.json", "scripts/run_recovery_controller_study.py",
                        "scripts/audit_recovery_controller_study.py", "scripts/build_recovery_human_review.py"}
    require(required_sources <= set(source["files"]), "protocol omitted a required study source binding")
    source_root = Path(source["root"]).resolve()
    for name, declaration in source["files"].items():
        path = _safe_path(source_root, name)
        data = path.read_bytes()
        require(sha256(data) == declaration["sha256"] and len(data) == declaration["bytes"],
                f"frozen source file mismatch: {name}")
        result = subprocess.run(["git", "-C", str(source_root), "show", f"{source['commit']}:{name}"],
                                capture_output=True, check=False)
        require(result.returncode == 0 and sha256(result.stdout) == declaration["sha256"],
                f"source binding differs from committed Git blob: {name}")
    require(runtime["framework_version"] == runtime["distribution_version"] == "2.1.1",
            "runtime is not the declared installed 2.1.1")
    require(sha256(Path(runtime["python_executable"]).read_bytes()) == runtime["python_sha256"],
            "interpreter executable binding mismatch")
    package = Path(runtime["framework_path"]).resolve()
    actual_names = {path.relative_to(package).as_posix() for path in package.rglob("*")
                    if path.is_file() and path.suffix in (".py", ".json")}
    require(actual_names == set(runtime["runtime_file_sha256"]), "installed package file inventory mismatch")
    for name, digest in runtime["runtime_file_sha256"].items():
        require(sha256(_safe_path(package, name).read_bytes()) == digest, f"installed package file changed: {name}")
        require(source["files"][f"src/consequa_x/{name}"]["sha256"] == digest,
                f"installed package differs from frozen source: {name}")
    return {"source_commit": source["commit"], "source_files_verified": len(source["files"]),
            "installed_package_files_verified": len(actual_names), "framework_version": "2.1.1"}


def _verify_protocol_commit(protocol, started, expected_digest):
    """Verify prospective Git provenance independently of the runner's claim."""
    source = protocol["source"]
    source_root = Path(source["root"]).resolve()
    relative = protocol["protocol_git_path"]
    _safe_path(source_root, relative)
    commits = (source["commit"], started["protocol_commit"])
    for commit in commits:
        require(isinstance(commit, str) and len(commit) in (40, 64)
                and all(character in "0123456789abcdef" for character in commit),
                "source/protocol commit must be a full Git object identity")
    source_commit, protocol_commit = commits
    blob = subprocess.run(["git", "-C", str(source_root), "show", f"{protocol_commit}:{relative}"],
                          capture_output=True, check=False)
    require(blob.returncode == 0 and sha256(blob.stdout) == expected_digest,
            "retained protocol differs from the prospectively committed protocol blob")
    ancestry = subprocess.run(["git", "-C", str(source_root), "merge-base", "--is-ancestor",
                               source_commit, protocol_commit], capture_output=True, check=False)
    require(ancestry.returncode == 0, "frozen source commit is not an ancestor of the protocol commit")
    timestamp = subprocess.run(["git", "-C", str(source_root), "show", "-s", "--format=%ct", protocol_commit],
                               capture_output=True, check=False)
    require(timestamp.returncode == 0, "protocol commit timestamp is unavailable")
    try:
        committed_at = int(timestamp.stdout)
        started_at = datetime.fromisoformat(started["started_utc"].replace("Z", "+00:00"))
        require(started_at.tzinfo is not None and started_at.utcoffset() is not None,
                "collection start timestamp lacks a timezone")
        require(0 <= committed_at <= started_at.timestamp(), "protocol commit postdates collection start")
    except (TypeError, ValueError, OverflowError, AttributeError) as error:
        if isinstance(error, AuditError):
            raise
        raise AuditError("invalid protocol/start timestamp") from error
    return {"protocol_commit": protocol_commit, "protocol_git_path": relative,
            "protocol_committed_at_unix": committed_at, "collection_started_utc": started["started_utc"]}


def _verify_run_claim(protocol, started, started_path, study_root, expected_digest):
    source_root = Path(protocol["source"]["root"]).resolve()
    canonical = _safe_path(source_root, f"output/.recovery-run-claims/{expected_digest}.json")
    require(started.get("canonical_claim_path") == str(canonical.resolve()),
            "canonical run claim path differs from the protocol-bound source location")
    require(started.get("source_commit") == protocol["source"]["commit"],
            "collection start source commit differs from protocol")
    require(started.get("output") == str(study_root.resolve()),
            "collection start output path differs from the audited study")
    started_bytes = started_path.read_bytes()
    require(canonical.is_file() and canonical.read_bytes() == started_bytes,
            "canonical run claim bytes differ from retained collection start")
    name = started.get("protocol_path")
    require(isinstance(name, str) and Path(name).is_absolute() and str(Path(name).resolve()) == name,
            "collection protocol path is not a resolved absolute path")
    supplied = Path(name)
    require(supplied.is_file() and sha256(supplied.read_bytes()) == expected_digest,
            "supplied protocol file differs from the frozen protocol hash")
    local_claim = supplied.parent / "run-claim.json"
    require(not local_claim.is_symlink() and local_claim.is_file() and local_claim.read_bytes() == started_bytes,
            "protocol-local run claim bytes differ from retained collection start")
    return {"canonical_claim_path": str(canonical), "canonical_claim_sha256": sha256(started_bytes)}


def _validate_plan(protocol):
    require(tuple(protocol["methods"]) == METHODS, "declared five controller arms differ")
    require((protocol["case_count"], protocol["family_count"], protocol["seed_count"]) == (24, 12, 128),
            "declared finite-suite denominators differ from frozen design")
    planned = protocol["schedule"]
    require(len(planned) == 24 * 128 * 5, "planned trial denominator is incomplete")
    identities, paired = set(), defaultdict(set)
    cases, families, domains = {}, set(), set()
    case_order = []
    for index, slot in enumerate(planned):
        require(set(slot) == {"trial_id", "case_id", "family_id", "domain", "seed", "method"},
                "unexpected schedule descriptor")
        identity = slot["trial_id"]
        require(identity == f"trial_{index:06d}", "planned trial numbering/order differs")
        require(identity not in identities, "duplicate planned trial ID")
        identities.add(identity)
        _safe_path(Path.cwd(), f"trials/{identity}.json.gz")
        require(type(slot["seed"]) is int and 0 <= slot["seed"] < 128, "seed outside declared range")
        require(slot["method"] in METHODS, "unplanned method")
        pair = (slot["case_id"], slot["seed"])
        require(slot["method"] not in paired[pair], "duplicate paired case-seed arm")
        paired[pair].add(slot["method"])
        descriptor = (slot["family_id"], slot["domain"])
        require(slot["case_id"] not in cases or cases[slot["case_id"]] == descriptor,
                "case family/domain changes across arms")
        cases[slot["case_id"]] = descriptor
        if slot["case_id"] not in case_order:
            case_order.append(slot["case_id"])
        case_index, seed, arm_index = index // (128 * 5), (index // 5) % 128, index % 5
        require(len(case_order) > case_index and slot["case_id"] == case_order[case_index] and slot["seed"] == seed
                and slot["method"] == METHODS[(case_index + seed + arm_index) % 5],
                "planned case-seed method rotation differs from matched design")
        families.add(slot["family_id"])
        domains.add(slot["domain"])
    require(len(cases) == 24 and len(families) == 12 and len(paired) == 24 * 128,
            "case/family/paired denominator mismatch")
    require(all(methods == set(METHODS) for methods in paired.values()), "incomplete paired arm set")
    require(domains == {"inventory_reservation", "support_transition", "delivery_registration"},
            "declared application domains differ")


def audit_study(study_dir: Path, output_dir: Path) -> dict:
    """Audit a completed collection into a fresh directory, never repair originals."""
    root, output = Path(study_dir).resolve(), Path(output_dir).resolve()
    require(not output.exists() and not output.is_relative_to(root), "audit output must be a fresh separate directory")
    receipt, manifest = audit_artifact_manifest(root)
    for key in ("no_retries_or_replacements", "source_and_runtime_final_recheck"):
        require(receipt.get(key) is True, f"collection receipt lacks required invariant: {key}")
    require(receipt.get("new_model_calls") == receipt.get("external_application_calls") == 0,
            "collection receipt declares prohibited new model/service calls")
    protocol = load_json(root / "protocol.json")
    started = load_json(root / "started.json")
    require(started.get("protocol_sha256") == receipt["protocol_sha256"]
            and started.get("retry_allowed") is False, "collection start/protocol/no-rerun binding mismatch")
    protocol_binding = _verify_protocol_commit(protocol, started, receipt["protocol_sha256"])
    claim_binding = _verify_run_claim(protocol, started, root / "started.json", root, receipt["protocol_sha256"])
    _validate_plan(protocol)
    binding = _verify_source_runtime(protocol)
    expected_trials = {f"trials/{slot['trial_id']}.json.gz" for slot in protocol["schedule"]}
    require({name for name in manifest["files"] if name.startswith("trials/")} == expected_trials,
            "trial artifact IDs do not exactly match the frozen plan")
    require({name for name in manifest["files"] if "/" not in name}
            == {"started.json", "protocol.json", "summary.json", "analysis-rows.jsonl"},
            "unexpected/missing top-level collection artifacts")
    analysis = [json.loads(line) for line in (root / "analysis-rows.jsonl").read_text(encoding="utf-8").splitlines()]
    require(len(analysis) == len(protocol["schedule"]), "analysis row denominator mismatch")
    compact, public_by_pair = [], {}
    databases_checked, missing_failed_databases = 0, []
    database_paths = set()
    with tempfile.TemporaryDirectory(prefix="recovery-audit-") as temporary:
        db_path = Path(temporary) / "snapshot.sqlite"
        for index, slot in enumerate(protocol["schedule"]):
            trial_path = f"trials/{slot['trial_id']}.json.gz"
            require(trial_path in manifest["files"], "planned trial is missing from manifest")
            trial = json.loads(gzip.decompress(_safe_path(root, trial_path).read_bytes()))
            require(all(trial.get(key) == value for key, value in slot.items()), "retained trial identity differs from plan")
            require(trial.get("status") in ("completed", "failed"), "planned failure was dropped/relabelled")
            if "database" in trial:
                packed = trial["database"]["path"]
                require(packed == f"databases/{slot['trial_id']}.sqlite.gz" and packed in manifest["files"],
                        "trial database path is unplanned")
                raw = gzip.decompress(_safe_path(root, packed).read_bytes())
                database_paths.add(packed)
                require(sha256(raw) == trial["database"]["sha256_uncompressed"], "uncompressed SQLite hash mismatch")
                db_path.write_bytes(raw)
                require("public_case" in trial, "retained SQLite snapshot lacks public declaration")
                metrics = audit_trial(trial, db_path)
                databases_checked += 1
            else:
                require(trial["status"] == "failed", "completed trial lost its SQLite snapshot")
                metrics = _failed_metrics(trial)
                missing_failed_databases.append(slot["trial_id"])
            if "public_case" in trial:
                pair = (slot["case_id"], slot["seed"])
                declaration = trial["public_case"]
                require(pair not in public_by_pair or public_by_pair[pair] == declaration,
                        "public case/capabilities differ between paired arms")
                public_by_pair[pair] = declaration
            row = {**slot, "status": trial["status"], "metrics": metrics}
            require(analysis[index] == row, "analysis row differs from retained independently audited trial")
            compact.append(row)
            if (index + 1) % 1000 == 0:
                print(json.dumps({"audited_slots": index + 1, "planned": len(protocol["schedule"])}), flush=True)
    require({name for name in manifest["files"] if name.startswith("databases/")} == database_paths,
            "database artifact IDs do not exactly match retained trial declarations")
    require(set(manifest["files"]) == expected_trials | database_paths
            | {"started.json", "protocol.json", "summary.json", "analysis-rows.jsonl"},
            "unplanned retained study artifact")
    independently_computed = recompute_summary(compact, protocol)
    recorded = load_json(root / "summary.json")
    require(recorded.get("protocol_sha256") == receipt["protocol_sha256"], "summary protocol binding mismatch")
    require(type(recorded.get("collection_seconds")) in (int, float)
            and math.isfinite(recorded["collection_seconds"]) and recorded["collection_seconds"] >= 0,
            "invalid collection duration")
    comparable = {key: value for key, value in recorded.items()
                  if key not in {"protocol_sha256", "collection_seconds"}}
    _same(independently_computed, comparable)
    for key in ("planned_trials", "completed_trials", "failed_trials"):
        require(receipt[key] == independently_computed[key], f"completion receipt denominator mismatch: {key}")
    output.mkdir(parents=True, exist_ok=False)
    (output / "recomputed-summary.json").write_text(json.dumps(independently_computed, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
    result = {"schema": "recovery-controller-postcollection-audit-v1", "passed": True,
              "protocol_sha256": receipt["protocol_sha256"], "manifest_sha256": receipt["manifest_sha256"],
              "audit_script_sha256": sha256(Path(__file__).read_bytes()),
              "artifacts_hashed": len(manifest["files"]), "sqlite_snapshots_queried": databases_checked,
              "planned_trials": len(compact), "completed_trials": independently_computed["completed_trials"],
              "failed_trials": independently_computed["failed_trials"],
              "failed_slots_without_databases": missing_failed_databases, **binding, **protocol_binding, **claim_binding,
              "limitations": ["Auditor author also authored controllers; audit-test author also authored world. "
                              "This is independent code from world/evaluator/runner, not independent-human or external replication.",
                              "Source admission and provider guarantees are application assumptions; logs and persisted schedule "
                              "consistency cannot establish authentication or rule out off-record external calls.",
                              "Finite safety cutoff does not establish absence of arbitrarily late effects.",
                              "Missing failed-slot snapshots remain failures and cannot receive a lifecycle audit.",
                              "Recorded elapsed wall times are checked for shape only, not independently remeasured."]}
    (output / "audit-receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit_study(args.study_dir, args.output), sort_keys=True))
    except (AuditError, OSError, KeyError, json.JSONDecodeError, sqlite3.DatabaseError) as error:
        parser.exit(1, f"Audit failed: {error}\n")


if __name__ == "__main__":
    main()
