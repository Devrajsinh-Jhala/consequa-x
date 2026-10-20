"""Deterministic, isolated SQLite applications; no controller or framework imports.

``_world`` is evaluator-owned configuration. Only dispatch responses, readback
observations and ``public_case`` belong in a controller's input. ``truth`` and
the database file are evaluator-only. Every timing unit is relative milliseconds.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


SOURCE = "sqlite-application-ledger/v1"
DOMAINS = {"inventory_reservation", "support_transition", "delivery_registration"}
ORIGIN_FIELDS = {"action_id", "actor", "attempt_id"}


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Load sealed cases for the evaluator, never for controller construction."""
    path = path or Path(__file__).with_name("heldout_cases.json")
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def public_case(case: dict[str, Any]) -> dict[str, Any]:
    """Return the requested task and declared application capabilities only."""
    names = ("case_id", "family_id", "domain", "operation_id", "actor", "target",
             "deadline_ms", "stability_ms", "initial_at_ms", "payload",
             "scope_fields", "scope", "native_idempotency", "recovery_deadline_ms", "safety_horizon_ms")
    return {name: deepcopy(case[name]) for name in names}


def _encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _time(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("time must be a nonnegative integer")
    return value


class World:
    """Run one logical operation against a fresh, local application database.

    A dispatch schedules actual SQLite commits, independently of its returned
    status. Native idempotency, when declared, reserves the logical operation at
    acceptance, including while work is pending. An actor change is rejected.
    Readback is a faithful historical query, with explicit cache, pagination or
    availability limitations. Nothing in the public APIs reads evaluator truth.
    """

    def __init__(self, case: dict[str, Any], seed: int, db_path: Path):
        self.case = deepcopy(case)
        self.config = deepcopy(case.get("_world", {}))
        self.seed = seed
        self.domain = case["domain"]
        if self.domain not in DOMAINS:
            raise ValueError("unsupported application domain")
        self.expected = deepcopy(case["target"]["expected"])
        self.scope = deepcopy(case["scope"])
        self.scope_fields = tuple(case["scope_fields"])
        if not self.scope_fields or any(self.expected.get(k) != self.scope[k]
                                        for k in self.scope_fields):
            raise ValueError("scope must cover the target's scope fields")
        self.deadline = _time(case["deadline_ms"])
        self.horizon = self.deadline + _time(case["stability_ms"])
        self.recovery_deadline = _time(case["recovery_deadline_ms"])
        self.safety_horizon = _time(case["safety_horizon_ms"])
        if not self.horizon <= self.recovery_deadline <= self.safety_horizon:
            raise ValueError("original horizon <= recovery deadline <= safety horizon is required")
        self.now = _time(case.get("initial_at_ms", 0))
        self.operation_id = case["operation_id"]
        self.actor = case["actor"]
        self.native = bool(case["native_idempotency"])
        self.metrics = {key: 0 for key in (
            "dispatch_calls", "new_requests", "native_replays", "identity_rejections",
            "readback_calls", "available_readbacks", "records_returned", "committed_effects",
            "removed_effects", "business_rejections")}
        self.dispatch_log: list[dict[str, Any]] = []
        self.readback_log: list[dict[str, Any]] = []
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if self.db_path.exists():
            raise FileExistsError("each world requires a fresh SQLite file")
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE effects (
                effect_id TEXT PRIMARY KEY, committed_at_ms INTEGER NOT NULL,
                removed_at_ms INTEGER, payload_json TEXT NOT NULL,
                reported_origin_json TEXT NOT NULL, causal_action_id TEXT,
                causal_actor TEXT NOT NULL, causal_attempt_id TEXT);
            CREATE TABLE pending_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, due_ms INTEGER NOT NULL,
                kind TEXT NOT NULL, event_json TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE idempotency (
                operation_id TEXT PRIMARY KEY, actor TEXT NOT NULL, first_attempt_id TEXT NOT NULL);
            CREATE TABLE inventory_stock (stock_key TEXT PRIMARY KEY, available INTEGER NOT NULL);
            CREATE TABLE inventory_reservations (
                effect_id TEXT PRIMARY KEY REFERENCES effects(effect_id), stock_key TEXT NOT NULL,
                quantity INTEGER NOT NULL, state TEXT NOT NULL);
            CREATE TABLE support_tickets (ticket_id TEXT PRIMARY KEY, status TEXT NOT NULL, queue TEXT NOT NULL);
            CREATE TABLE ticket_transitions (
                effect_id TEXT PRIMARY KEY REFERENCES effects(effect_id), ticket_id TEXT NOT NULL,
                status TEXT NOT NULL, queue TEXT NOT NULL, state TEXT NOT NULL);
            CREATE TABLE delivery_registrations (
                effect_id TEXT PRIMARY KEY REFERENCES effects(effect_id), artifact_id TEXT NOT NULL,
                delivery_channel TEXT NOT NULL, checksum TEXT NOT NULL, state TEXT NOT NULL);
        """)
        if self.domain == "inventory_reservation":
            self.db.execute("INSERT INTO inventory_stock VALUES (?, ?)", (
                self._stock_key(self.expected), self.config.get("inventory_capacity", 10000)))
        if self.domain == "support_transition":
            self.db.execute("INSERT INTO support_tickets VALUES (?, ?, ?)", (
                self.expected["ticket_id"], "open", self.expected["queue"]))
        for index, event in enumerate(self.config.get("external_events", [])):
            due = _time(event["at_ms"]) + self._jitter(f"external/{index}", event.get("jitter_ms", 0))
            origin = {"action_id": event.get("action_id", f"external-operation-{index}"),
                      "actor": event.get("actor", "external-operator"),
                      "attempt_id": f"external-attempt-{index}"}
            self._schedule_commit(due, event, origin, f"external-{index}")
        self.db.commit()
        self.advance(self.now)

    @property
    def source_receipt(self) -> dict[str, Any]:
        """Application admission declaration, with no case mechanism disclosure."""
        return {"source": SOURCE, "trusted": True, "application_owned": True,
                "scope_fields": list(self.scope_fields), "scope": deepcopy(self.scope),
                "clock": "simulation-relative-ms", "commit_clock_authoritative": True,
                "watermark_semantics": "all events at or before as_of_ms have been applied",
                "history_semantics": "commits plus removal tombstones through as_of_ms",
                "completeness_semantics": "complete covers declared scope and lifecycle history",
                "provenance_semantics": "stored application audit fields; absent means unknown",
                "provider_resolution": "terminal_not_committed true certifies only this attempt has terminated "
                    "without an effect and cannot commit later; it makes no claim about other attempts or retries",
                "native_idempotency": self.native}

    def _jitter(self, key: str, width: int) -> int:
        width = _time(width)
        digest = hashlib.sha256(f"{self.seed}:{key}".encode()).digest()
        return int.from_bytes(digest[:8], "big") % (width + 1)

    @staticmethod
    def _stock_key(payload: dict[str, Any]) -> str:
        return _encoded([payload["warehouse"], payload["sku"]])

    def _schedule(self, at_ms: int, kind: str, event: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO pending_events(due_ms,kind,event_json) VALUES(?,?,?)",
                        (_time(at_ms), kind, _encoded(event)))

    def _schedule_commit(self, at_ms: int, plan: dict[str, Any],
                         origin: dict[str, str], prefix: str) -> None:
        payload = deepcopy(self.case["payload"])
        payload.update(plan.get("value_overrides", {}))
        reported = {k: v for k, v in origin.items()
                    if k in plan.get("provenance", sorted(ORIGIN_FIELDS))}
        copies = plan.get("copies", 1)
        if type(copies) is not int or copies < 1:
            raise ValueError("copies must be a positive integer")
        for copy in range(copies):
            self._schedule(at_ms + copy * plan.get("copy_spacing_ms", 0), "commit", {
                "effect_id": f"{prefix}:effect-{copy + 1}", "payload": payload,
                "origin": origin, "reported_origin": reported,
                "remove_after_ms": plan.get("remove_after_ms"),
                "native": self.native and not prefix.startswith("external-")})

    def dispatch(self, operation_id: str, actor: str, at_ms: int) -> dict[str, Any]:
        """Dispatch/retry a stable logical identity; never return hidden commit state."""
        self.advance(at_ms)
        self.metrics["dispatch_calls"] += 1
        attempt = f"{operation_id}:attempt-{self.metrics['dispatch_calls']}"
        if operation_id != self.operation_id or actor != self.actor:
            self.metrics["identity_rejections"] += 1
            response = {"status": "error", "response_at_ms": at_ms + 1,
                        "attempt_id": attempt, "result": {"code": "identity_conflict"}}
        else:
            plans = self.config.get("dispatch_plans", [{}])
            plan = plans[min(self.metrics["dispatch_calls"] - 1, len(plans) - 1)]
            if plan.get("terminal_not_committed", False) and plan.get("commit_delay_ms", 0) is not None:
                raise ValueError("a terminal no-commit response cannot schedule a commit")
            existing = self.db.execute("SELECT * FROM idempotency WHERE operation_id=?",
                                       (operation_id,)).fetchone()
            replay = self.native and existing is not None
            if replay:
                self.metrics["native_replays"] += 1
            else:
                self.metrics["new_requests"] += 1
                delay = plan.get("commit_delay_ms", 0)
                if delay is not None:
                    if self.native:
                        self.db.execute("INSERT INTO idempotency VALUES(?,?,?)",
                                        (operation_id, actor, attempt))
                    origin = {"action_id": operation_id, "actor": actor, "attempt_id": attempt}
                    self._schedule_commit(at_ms + _time(delay), plan, origin, attempt)
            status = plan.get("status", "success")
            if status not in {"success", "timeout", "error"}:
                raise ValueError("invalid public response status")
            response = {"status": status,
                        "response_at_ms": at_ms + _time(plan.get("response_delay_ms", 5)),
                        "attempt_id": attempt, "result": {"code": {
                            "success": "accepted", "timeout": "transport_timeout",
                            "error": "request_failed"}[status]}}
            if plan.get("terminal_not_committed", False) and not replay:
                response["terminal_not_committed"] = True
        self.dispatch_log.append({"operation_id": operation_id, "actor": actor,
                                  "at_ms": at_ms, **deepcopy(response)})
        self.db.commit()
        self.advance(at_ms)
        return deepcopy(response)

    def advance(self, at_ms: int) -> None:
        """Apply all due application events in (due time, insertion order)."""
        _time(at_ms)
        if at_ms < self.now:
            raise ValueError("application time cannot move backwards")
        while True:
            row = self.db.execute("SELECT * FROM pending_events WHERE applied=0 AND due_ms<=? "
                                  "ORDER BY due_ms,seq LIMIT 1", (at_ms,)).fetchone()
            if row is None:
                break
            event = json.loads(row["event_json"])
            if row["kind"] == "commit":
                self._commit(row["due_ms"], event)
            else:
                self._remove(row["due_ms"], event["effect_id"])
            self.db.execute("UPDATE pending_events SET applied=1 WHERE seq=?", (row["seq"],))
        self.db.commit()
        self.now = at_ms

    def _commit(self, at_ms: int, event: dict[str, Any]) -> None:
        origin, payload = event["origin"], event["payload"]
        if event["native"] and self.db.execute(
                "SELECT 1 FROM effects WHERE causal_action_id=? AND causal_actor=?",
                (origin["action_id"], origin["actor"])).fetchone():
            return
        if self.domain == "inventory_reservation":
            stock = self._stock_key(payload)
            quantity = payload["quantity"]
            if type(quantity) is not int or quantity < 1:
                self.metrics["business_rejections"] += 1
                return
            changed = self.db.execute("UPDATE inventory_stock SET available=available-? "
                                      "WHERE stock_key=? AND available>=?", (quantity, stock, quantity))
            if changed.rowcount != 1:
                self.metrics["business_rejections"] += 1
                return
        elif self.domain == "support_transition":
            superseded = self.db.execute("SELECT t.effect_id FROM ticket_transitions t JOIN effects e "
                                         "USING(effect_id) WHERE ticket_id=? AND removed_at_ms IS NULL "
                                         "AND (status<>? OR queue<>?)", (
                                             payload["ticket_id"], payload["status"], payload["queue"])).fetchall()
            for old in superseded:
                self._remove(at_ms, old["effect_id"])
        self.db.execute("INSERT INTO effects VALUES(?,?,?,?,?,?,?,?)", (
            event["effect_id"], at_ms, None, _encoded(payload), _encoded(event["reported_origin"]),
            origin.get("action_id"), origin["actor"], origin.get("attempt_id")))
        effect = event["effect_id"]
        if self.domain == "inventory_reservation":
            self.db.execute("INSERT INTO inventory_reservations VALUES(?,?,?,?)",
                            (effect, stock, quantity, "active"))
        elif self.domain == "support_transition":
            self.db.execute("INSERT INTO ticket_transitions VALUES(?,?,?,?,?)", (
                effect, payload["ticket_id"], payload["status"], payload["queue"], "active"))
            self.db.execute("INSERT INTO support_tickets VALUES(?,?,?) ON CONFLICT(ticket_id) "
                            "DO UPDATE SET status=excluded.status,queue=excluded.queue", (
                                payload["ticket_id"], payload["status"], payload["queue"]))
        else:
            self.db.execute("INSERT INTO delivery_registrations VALUES(?,?,?,?,?)", (
                effect, payload["artifact_id"], payload["delivery_channel"], payload["checksum"], "active"))
        self.metrics["committed_effects"] += 1
        if event["remove_after_ms"] is not None:
            self._schedule(at_ms + _time(event["remove_after_ms"]), "remove", {"effect_id": effect})

    def _remove(self, at_ms: int, effect_id: str) -> None:
        row = self.db.execute("SELECT * FROM effects WHERE effect_id=? AND removed_at_ms IS NULL",
                              (effect_id,)).fetchone()
        if row is None:
            return
        self.db.execute("UPDATE effects SET removed_at_ms=? WHERE effect_id=?", (at_ms, effect_id))
        payload = json.loads(row["payload_json"])
        if self.domain == "inventory_reservation":
            self.db.execute("UPDATE inventory_reservations SET state='released' WHERE effect_id=?", (effect_id,))
            self.db.execute("UPDATE inventory_stock SET available=available+? WHERE stock_key=?",
                            (payload["quantity"], self._stock_key(payload)))
        elif self.domain == "support_transition":
            self.db.execute("UPDATE ticket_transitions SET state='reversed' WHERE effect_id=?", (effect_id,))
            latest = self.db.execute("SELECT status,queue FROM ticket_transitions t JOIN effects e "
                                    "USING(effect_id) WHERE ticket_id=? AND removed_at_ms IS NULL "
                                    "ORDER BY committed_at_ms DESC,effect_id DESC LIMIT 1",
                                    (payload["ticket_id"],)).fetchone()
            self.db.execute("UPDATE support_tickets SET status=?,queue=? WHERE ticket_id=?", (
                latest["status"] if latest else "open", latest["queue"] if latest else payload["queue"],
                payload["ticket_id"]))
        else:
            self.db.execute("UPDATE delivery_registrations SET state='revoked' WHERE effect_id=?", (effect_id,))
        self.metrics["removed_effects"] += 1

    def _records(self, as_of_ms: int, *, causal: bool = False) -> list[dict[str, Any]]:
        records = []
        for row in self.db.execute("SELECT * FROM effects WHERE committed_at_ms<=? "
                                   "ORDER BY committed_at_ms,effect_id", (as_of_ms,)):
            record = json.loads(row["payload_json"])
            record.update(json.loads(row["reported_origin_json"]))
            record.update(effect_id=row["effect_id"], committed_at_ms=row["committed_at_ms"])
            if row["removed_at_ms"] is not None and row["removed_at_ms"] <= as_of_ms:
                record["removed_at_ms"] = row["removed_at_ms"]
            if causal:
                record["_causal_action_id"] = row["causal_action_id"]
                record["_causal_actor"] = row["causal_actor"]
                record["_causal_attempt_id"] = row["causal_attempt_id"]
            records.append(record)
        return records

    def readback(self, at_ms: int) -> dict[str, Any]:
        """Capture only admitted application JSON, with honest scope/watermark flags."""
        self.advance(at_ms)
        self.metrics["readback_calls"] += 1
        view = deepcopy(self.config.get("readback", {}))
        for window in view.pop("windows", []):
            if window.get("start_ms", 0) <= at_ms < window.get("until_ms", 2**63):
                view.update({k: v for k, v in window.items() if k not in {"start_ms", "until_ms"}})
        as_of = max(0, at_ms - _time(view.get("lag_ms", 0)))
        scope = deepcopy(view.get("scope", self.scope))
        available, complete = view.get("available", True), view.get("complete", True)
        records = [r for r in self._records(as_of)
                   if all(r.get(k) == value for k, value in scope.items())]
        if view.get("active_only", False):
            records = [r for r in records if "removed_at_ms" not in r]
            complete = False  # active-only views cannot attest lifecycle history
        for record in records:
            for field in view.get("omit_provenance", []):
                if field not in ORIGIN_FIELDS:
                    raise ValueError("only audit provenance may be omitted")
                record.pop(field, None)
        if "record_limit" in view:
            records = records[:view["record_limit"]]
            complete = False  # pagination never claims exhaustive scope
        if not available:
            records, complete = [], False
        observation = {"observation_id": f"observation-{at_ms}-{self.metrics['readback_calls']}",
                       "source": SOURCE, "observed_at_ms": at_ms, "as_of_ms": as_of,
                       "scope": scope, "records": records, "complete": bool(complete),
                       "available": bool(available)}
        self.metrics["available_readbacks"] += int(bool(available))
        self.metrics["records_returned"] += len(records)
        self.readback_log.append({"at_ms": at_ms, "observation_id": observation["observation_id"],
                                  "as_of_ms": as_of, "records_returned": len(records),
                                  "available": bool(available), "complete": bool(complete)})
        return deepcopy(observation)

    def truth(self, at_ms: int) -> dict[str, Any]:
        """Evaluator-only causality and lifecycle receipt; never a public readback."""
        self.advance(at_ms)
        records = self._records(at_ms, causal=True)
        relevant = [r for r in records if self.case.get("initial_at_ms", 0) <= r["committed_at_ms"] <= self.horizon
                    and all(r.get(k) == value for k, value in self.scope.items())]
        matching = [r for r in relevant if all(r.get(k) == v for k, v in self.expected.items())]
        def removed(record):
            return record.get("removed_at_ms", self.horizon + 1)
        eligible = [r for r in matching if r["committed_at_ms"] <= self.deadline and removed(r) > self.horizon]
        count = sum(r["committed_at_ms"] <= self.deadline < removed(r) for r in matching)
        peak = count
        changes: dict[int, int] = {}
        for record in matching:
            for time, delta in ((record["committed_at_ms"], 1), (removed(record), -1)):
                if self.deadline < time <= self.horizon:
                    changes[time] = changes.get(time, 0) + delta
        for time in sorted(changes):
            count += changes[time]
            peak = max(peak, count)
        linked = [r for r in relevant if r["_causal_action_id"] == self.operation_id
                  and r["_causal_actor"] == self.actor]
        linked_targets = [r for r in eligible if r in linked]
        exact = self.case["target"]["exact_count"]
        satisfied = bool(eligible) if exact is None else len(eligible) == exact and peak == exact
        duplicate_count = max(0, len(linked) - (exact if exact is not None else 1))
        reached = at_ms >= self.horizon
        safety_records = [r for r in records if r["committed_at_ms"] <= self.safety_horizon]
        own_records = [r for r in safety_records if r["_causal_action_id"] == self.operation_id
                       and r["_causal_actor"] == self.actor]
        recovery_matches = [r for r in safety_records if all(r.get(k) == v for k, v in self.expected.items())]
        def safety_removed(record):
            return record.get("removed_at_ms", self.safety_horizon + 1)
        recovery_eligible = [r for r in recovery_matches if r["committed_at_ms"] <= self.recovery_deadline
                             and safety_removed(r) > self.safety_horizon]
        recovery_count = sum(r["committed_at_ms"] <= self.recovery_deadline < safety_removed(r)
                             for r in recovery_matches)
        recovery_peak, recovery_changes = recovery_count, {}
        for record in recovery_matches:
            for time, delta in ((record["committed_at_ms"], 1), (safety_removed(record), -1)):
                if self.recovery_deadline < time <= self.safety_horizon:
                    recovery_changes[time] = recovery_changes.get(time, 0) + delta
        for time in sorted(recovery_changes):
            recovery_count += recovery_changes[time]
            recovery_peak = max(recovery_peak, recovery_count)
        recovery_ok = bool(recovery_eligible) if exact is None else (
            len(recovery_eligible) == exact and recovery_peak == exact)
        linked_recovery = [r for r in recovery_eligible if r in own_records]
        safety_reached = at_ms >= self.safety_horizon
        own_duplicates = max(0, len(own_records) - (exact if exact is not None else 1))
        unwanted = [r for r in own_records if any(r.get(k) != v for k, v in self.expected.items())
                    or r["committed_at_ms"] > self.recovery_deadline]
        return {"at_ms": at_ms, "horizon_reached": reached,
                "target_satisfied": satisfied if reached else None,
                "stable_target": satisfied if reached else None,
                "eligible_target_count": len(eligible), "peak_target_count": peak,
                "target_count": sum(r["committed_at_ms"] <= self.horizon < removed(r) for r in matching),
                "linked_target_count": len(linked_targets),
                "linked_target_satisfied": (satisfied and (bool(linked_targets) if exact is None
                                             else len(linked_targets) == exact)) if reached else None,
                "sla_duplicate_count": duplicate_count,
                "safety_horizon_reached": safety_reached,
                "eventual_recovery_satisfied": recovery_ok if safety_reached else None,
                "linked_recovery_satisfied": (recovery_ok and (bool(linked_recovery) if exact is None
                                               else len(linked_recovery) == exact)) if safety_reached else None,
                "linked_recovery_target_count": len(linked_recovery),
                "recovery_eligible_target_count": len(recovery_eligible),
                "recovery_peak_target_count": recovery_peak,
                "own_unwanted_effect_count": len(unwanted),
                "own_unwanted_effect_ids": [r["effect_id"] for r in unwanted],
                "own_effect_count": len(own_records),
                "own_reversed_effect_count": sum(safety_removed(r) <= self.safety_horizon for r in own_records),
                "duplicate_count": own_duplicates,
                "duplicate_effect_ids": [r["effect_id"] for r in own_records] if own_duplicates else [],
                "records": records, "metrics": deepcopy(self.metrics),
                "dispatch_log": deepcopy(self.dispatch_log), "readback_log": deepcopy(self.readback_log),
                "pending_event_count": self.db.execute("SELECT COUNT(*) FROM pending_events WHERE applied=0").fetchone()[0],
                "source_receipt": self.source_receipt}

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> World:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
