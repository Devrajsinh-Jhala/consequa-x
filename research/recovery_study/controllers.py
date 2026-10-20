"""Research-only controllers over an admitted, public JSON interface.

The reference implementation uses the standard library and does not call a
package verifier. Only the ``consequax_*`` arms lazily import public 2.1.1 APIs.
No controller imports the application world, a corpus, or evaluator truth.
"""

from __future__ import annotations

import copy
import json
from typing import Any


METHODS = ("response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll")
_META = {"effect_id", "committed_at_ms", "removed_at_ms", "action_id", "actor", "attempt_id"}
_OBS_KEYS = {"observation_id", "source", "observed_at_ms", "as_of_ms", "scope", "records",
             "complete", "available"}


def _integer(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _json(value: Any) -> Any:
    """Copy strict JSON, without retaining a caller-owned mutable object."""
    def check(item):
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float:
            if not (-float("inf") < item < float("inf")):
                raise ValueError("nonfinite JSON number")
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError("public inputs must contain only JSON values")
    check(value)
    return json.loads(json.dumps(value, allow_nan=False))


def _observation(value: dict) -> dict:
    value = _json(value)
    if type(value) is not dict or set(value) != _OBS_KEYS:
        raise ValueError("readback must have exactly the public Observation JSON fields")
    if not all(_identifier(value[key]) for key in ("observation_id", "source")):
        raise ValueError("readback identifiers must be nonempty strings")
    for key in ("observed_at_ms", "as_of_ms"):
        _integer(value[key], key)
    if value["as_of_ms"] > value["observed_at_ms"]:
        raise ValueError("readback watermark cannot exceed observation time")
    if type(value["scope"]) is not dict or type(value["records"]) is not list:
        raise ValueError("readback needs an object scope and an array of records")
    if not all(type(row) is dict for row in value["records"]):
        raise ValueError("each readback record must be an object")
    if any(type(value[key]) is not bool for key in ("complete", "available")):
        raise ValueError("availability and completeness must be booleans")
    return value


def _unknown(reason: str) -> dict:
    return {"final_target_state": None, "this_action_linked_target": None,
            "reason": reason, "effect_ids": [], "target_effect_ids": []}


def _linkage(candidates: list[dict], action_id: str, actor: str) -> bool | None:
    """Separate an observed target from an authenticated this-action target.

    Omitted provenance is unknown, rather than proof of another origin. An
    explicit different action or actor can exclude this action. Conflicting
    action/actor metadata cannot authenticate a positive claim.
    """
    unresolved = False
    for row in candidates:
        origin, owner = row.get("action_id"), row.get("actor")
        if origin == action_id and owner in (None, actor):
            return True
        if origin == action_id and owner != actor:
            unresolved = True
        elif origin is None and owner in (None, actor):
            unresolved = True
    return None if unresolved else False


def _reference_evidence(obs: dict, *, expected: dict, scope: dict, source: str,
                        registered: int, deadline: int, horizon: int,
                        exact_count: int | None, action_id: str, actor: str) -> dict:
    """Independent interval/count rule; no package objects or calls are used.

    A snapshot includes historical removals. Its watermark is coverage through
    a time, never a promise that an outstanding request cannot commit later.
    """
    if obs["source"] != source:
        return _unknown("Readback source is outside the declared trust boundary")
    if not obs["available"]:
        return _unknown("Readback source is unavailable")
    if any(obs["scope"].get(key) != value for key, value in scope.items()):
        return _unknown("Readback scope does not cover this contract")
    if not obs["complete"]:
        return _unknown("Readback is not exhaustive for its scope")
    if obs["as_of_ms"] < horizon:
        return _unknown("Readback watermark precedes contract horizon")

    rows, seen = [], set()
    for row in obs["records"]:
        identity, committed = row.get("effect_id"), row.get("committed_at_ms")
        if (not _identifier(identity) or identity in seen or type(committed) is not int
                or not 0 <= committed <= obs["as_of_ms"]):
            return _unknown("Readback contains invalid or duplicate records")
        seen.add(identity)
        if any(key in row and not _identifier(row[key])
               for key in ("action_id", "actor", "attempt_id")):
            return _unknown("Readback contains invalid origin metadata")
        removed = row.get("removed_at_ms", obs["as_of_ms"] + 1)
        if type(removed) is not int or not committed <= removed <= obs["as_of_ms"] + 1:
            return _unknown("Readback has an invalid removal time")
        if "removed_at_ms" in row and removed > obs["as_of_ms"]:
            return _unknown("Readback has an invalid removal time")
        if any(key not in row or row[key] != value for key, value in scope.items()):
            return _unknown("Readback includes records outside its declared scope")
        if registered <= committed <= horizon:
            rows.append(row)

    matching = [row for row in rows if all(key in row and row[key] == value
                                         for key, value in expected.items())]
    candidates = [row for row in matching
                  if row["committed_at_ms"] <= deadline
                  and row.get("removed_at_ms", horizon + 1) > horizon]
    # Evaluate simultaneous changes together by counting at each change time.
    # This is independent from the package's incremental sweep implementation.
    sample_times = {deadline, horizon}
    for row in matching:
        for instant in (row["committed_at_ms"], row.get("removed_at_ms", horizon + 1)):
            if deadline <= instant <= horizon:
                sample_times.add(instant)
    peak = max(sum(row["committed_at_ms"] <= instant
                   < row.get("removed_at_ms", horizon + 1) for row in matching)
               for instant in sample_times)
    state = (bool(candidates) if exact_count is None else
             len(candidates) == exact_count and peak == exact_count)
    linked_ids = [row["effect_id"] for row in candidates
                  if row.get("action_id") == action_id and row.get("actor", actor) == actor]
    return {"final_target_state": state,
            "this_action_linked_target": (_linkage(candidates, action_id, actor) if state else False),
            "reason": "Complete, trusted evidence covers the target and stability horizon",
            "effect_ids": [row["effect_id"] for row in rows],
            "target_effect_ids": linked_ids}


class Controller:
    """Deterministic public-interface controller; times are relative integer ms.

    ``decide`` consumes a dispatch/read opportunity when returning that kind.
    The driver must deliver its corresponding response/readback before asking
    again. A timeout completes the response interface, not the provider's work.
    ``read_times`` and ``max_dispatches`` are common resource ceilings.
    """

    def __init__(self, method: str, *, action_id: str, actor: str, expected: dict,
                 scope: dict, deadline_ms: int, stability_ms: int, source: str,
                 read_times: list[int], max_dispatches: int = 2,
                 exact_count: int | None = 1, scope_fields: list[str] | None = None,
                 native_idempotency: bool = False):
        if method not in METHODS:
            raise ValueError(f"unknown method: {method}")
        if not all(_identifier(item) for item in (action_id, actor, source)):
            raise ValueError("action_id, actor and source must be nonempty strings")
        expected, scope = _json(expected), _json(scope)
        if (type(expected) is not dict or not expected or type(scope) is not dict or not scope
                or _META & expected.keys()
                or any(key not in expected or expected[key] != value
                       for key, value in scope.items())):
            raise ValueError("scope must be a nonempty subset of the business target")
        for value, label in ((deadline_ms, "deadline_ms"), (stability_ms, "stability_ms"),
                             (max_dispatches, "max_dispatches")):
            _integer(value, label)
        if max_dispatches < 1:
            raise ValueError("at least one dispatch must be allowed")
        if type(native_idempotency) is not bool:
            raise ValueError("native_idempotency must be a public boolean capability")
        if exact_count is not None:
            _integer(exact_count, "exact_count")
        if type(read_times) is not list:
            raise ValueError("read_times must be a list")
        for instant in read_times:
            _integer(instant, "read time")
        if read_times != sorted(set(read_times)):
            raise ValueError("read times must be strictly increasing")
        scope_fields = list(scope) if scope_fields is None else scope_fields
        if (type(scope_fields) is not list or not all(_identifier(key) for key in scope_fields)
                or len(set(scope_fields)) != len(scope_fields) or set(scope_fields) != set(scope)):
            raise ValueError("scope_fields must name every declared scope key exactly once")
        self.method, self.action_id, self.actor = method, action_id, actor
        self.expected, self.scope, self.source = expected, scope, source
        self.scope_fields = tuple(scope_fields)
        self.native_idempotency = native_idempotency
        self.deadline_ms, self.stability_ms = deadline_ms, stability_ms
        self.horizon_ms, self.exact_count = deadline_ms + stability_ms, exact_count
        self.read_times, self.max_dispatches = list(read_times), max_dispatches
        self._now = self._registered = 0
        self._begun = False
        self._dispatches = self._reads = self._waits = self._next_read = 0
        self._pending_response = self._pending_read = False
        self._responses: list[dict] = []
        self._observations: list[dict] = []
        self._decisions: list[dict] = []
        self._terminal: dict | None = None
        self._evidence = _unknown("No admitted readback has established the target")
        self._cx = self._capture = self._receipt = None
        self._advice: dict | None = None
        self._current_absence = False
        self._final_reads = 0
        self._provisional_verifications: list[dict] = []

    def _time(self, instant: int) -> None:
        _integer(instant, "time")
        if instant < self._now:
            raise ValueError("controller callbacks and decisions must be chronological")
        self._now = instant

    def _record(self, kind: str, reason: str, *, at_ms: int | None = None, **extra) -> dict:
        decision = {"kind": kind, "at_ms": self._now if at_ms is None else at_ms,
                    "reason": reason, **extra}
        self._decisions.append(copy.deepcopy(decision))
        if self._cx is not None:
            self._cx.decision(decision, at_ms=self._now)
        if kind == "wait":
            self._waits += 1
        if kind in ("stop", "abstain"):
            self._terminal = decision
        return copy.deepcopy(decision)

    def _dispatch(self, reason: str) -> dict:
        self._dispatches += 1
        self._pending_response = True
        self._current_absence = False
        attempt_id = f"{self.action_id}:attempt-{self._dispatches}"
        decision = self._record("dispatch", reason, action_id=self.action_id,
                                attempt_id=attempt_id, idempotency_key=self.action_id)
        if self._capture is not None:
            self._capture.dispatch(attempt_id=attempt_id, at_ms=self._now)
        return decision

    def begin(self, at_ms: int = 0) -> dict:
        if self._begun:
            raise ValueError("controller has already begun")
        self._time(at_ms)
        if at_ms > self.deadline_ms:
            raise ValueError("registration must not follow the deadline")
        self._begun, self._registered = True, at_ms
        if self.method.startswith("consequax_"):
            from consequa_x import OutcomeContract, TraceRecorder

            # Exact measured-version enforcement belongs to the study's
            # interpreter/runtime freeze, not these reusable development fixtures.
            self._cx = TraceRecorder(f"recovery:{self.action_id}", actor=self.actor,
                                     clock=lambda: self._now, time_base="relative_ms")
            contract = OutcomeContract(contract_id=f"{self.action_id}:target",
                                       predicate="record_present", expected=self.expected,
                                       deadline_ms=self.deadline_ms,
                                       stability_ms=self.stability_ms, exact_count=self.exact_count)
            self._capture = self._cx.register(self.action_id, "write_record", self.expected,
                                              contract=contract, at_ms=self._registered,
                                              idempotency_key=self.action_id)
        return self._dispatch("Initial registered action")

    def on_response(self, response: dict, response_at_ms: int) -> None:
        if not self._pending_response or self._terminal:
            raise ValueError("response requires an outstanding dispatched attempt")
        response = _json(response)
        if type(response) is not dict or response.get("status") not in ("success", "timeout", "error"):
            raise ValueError("response needs status success, timeout or error")
        allowed = {"status", "attempt_id", "response_at_ms", "result", "provider_request_id",
                   "terminal_not_committed"}
        if set(response) - allowed:
            raise ValueError("response contains fields outside the admitted public response schema")
        if response.get("response_at_ms", response_at_ms) != response_at_ms:
            raise ValueError("response time disagrees with callback time")
        if "terminal_not_committed" in response and type(response["terminal_not_committed"]) is not bool:
            raise ValueError("terminal_not_committed must be a boolean")
        attempt_id = f"{self.action_id}:attempt-{self._dispatches}"
        if response.get("attempt_id", attempt_id) != attempt_id:
            raise ValueError("response belongs to a different attempt")
        self._time(response_at_ms)
        self._pending_response = False
        self._responses.append({**response, "response_at_ms": response_at_ms})
        if self._capture is not None:
            self._capture.response(attempt_id, response["status"], at_ms=response_at_ms,
                                   provider_request_id=response.get("provider_request_id", attempt_id),
                                   result=response.get("result", {}))

    def on_readback(self, observation: dict) -> None:
        if not self._pending_read or self._terminal:
            raise ValueError("readback requires a requested read")
        obs = _observation(observation)
        self._time(obs["observed_at_ms"])
        if any(old["observation_id"] == obs["observation_id"] for old in self._observations):
            raise ValueError("readback observation IDs must be unique")
        self._pending_read = False
        self._observations.append(obs)
        if self.method == "response_retry":
            return
        if self.method.startswith("consequax_"):
            self._framework_evidence(obs)
        else:
            self._evidence = _reference_evidence(
                obs, expected=self.expected, scope=self.scope, source=self.source,
                registered=self._registered, deadline=self.deadline_ms, horizon=self.horizon_ms,
                exact_count=self.exact_count, action_id=self.action_id, actor=self.actor)
            provisional = _reference_evidence(
                obs, expected=self.expected, scope=self.scope, source=self.source,
                registered=self._registered, deadline=min(self.deadline_ms, self._now),
                horizon=self._now, exact_count=self.exact_count,
                action_id=self.action_id, actor=self.actor)
            self._current_absence = (provisional["final_target_state"] is not None
                                     and not provisional["effect_ids"])
            if self.method == "readback_state":
                self._evidence["this_action_linked_target"] = (
                    False if self._evidence["final_target_state"] is False else None)
                self._evidence["target_effect_ids"] = []

    def _framework_evidence(self, obs: dict) -> None:
        from consequa_x import Observation, RecordVerifier, retry_advice

        observation = Observation(**{**obs, "records": tuple(obs["records"])})
        if obs["source"] != self.source:
            # Record the original bytes' meaning without silently upgrading source trust.
            self._cx.observe(observation)
            self._receipt = None
            self._evidence = _unknown("Readback source is outside the declared trust boundary")
        else:
            self._receipt = self._capture.verify(
                observation, verifier=RecordVerifier(scope_fields=self.scope_fields))
            if self._receipt.status.value == "unknown":
                self._evidence = _unknown(self._receipt.reason)
            else:
                candidates = [row for row in obs["records"]
                              if self._registered <= row["committed_at_ms"] <= self.deadline_ms
                              and row.get("removed_at_ms", self.horizon_ms + 1) > self.horizon_ms
                              and all(key in row and row[key] == value
                                      for key, value in self.expected.items())]
                self._evidence = {
                    "final_target_state": self._receipt.status.value == "satisfied",
                    "this_action_linked_target": None,
                    "reason": self._receipt.reason, "effect_ids": list(self._receipt.effect_ids),
                    "target_effect_ids": list(self._receipt.target_effect_ids or ())}
                # Independently assemble the linked contract claim from public receipt
                # fields. Do not call the reference's provenance implementation.
                if self._receipt.status.value == "violated":
                    linked_claim = False
                elif self._receipt.target_effect_ids:
                    linked_claim = True
                elif not candidates:
                    linked_claim = False
                else:
                    excluded = []
                    for candidate in candidates:
                        identity, owner = candidate.get("action_id"), candidate.get("actor")
                        excluded.append((identity is not None and identity != self.action_id)
                                        or (identity is None and owner is not None
                                            and owner != self.actor))
                    linked_claim = False if all(excluded) else None
                self._evidence["this_action_linked_target"] = linked_claim
        self._current_absence = False
        if obs["source"] == self.source and self._now < self.deadline_ms:
            from dataclasses import replace

            # A temporary receipt answers only "no relevant effects through now".
            # It never replaces the registered final target or its captured receipt.
            provisional_contract = replace(self._capture.action.contract,
                                           contract_id=f"{self.action_id}:provisional:{self._reads}",
                                           deadline_ms=self._now, stability_ms=0)
            provisional_action = replace(self._capture.action, contract=provisional_contract)
            provisional = RecordVerifier(scope_fields=self.scope_fields).verify(
                provisional_action, observation)
            self._provisional_verifications.append(provisional.to_dict())
            self._current_absence = (provisional.status.value != "unknown"
                                     and not provisional.effect_ids)
        self._advice = retry_advice(self._receipt).to_dict()

    def _claim(self) -> bool | None:
        if self.method == "response_retry":
            if any(row["status"] == "success" for row in self._responses):
                return True
            return False if self._responses and self._responses[-1]["status"] == "error" else None
        return self._evidence["final_target_state"]

    def decide(self, now_ms: int) -> dict:
        if not self._begun:
            raise ValueError("begin must precede decisions")
        self._time(now_ms)
        if self._terminal:
            return copy.deepcopy(self._terminal)
        if self._pending_response or self._pending_read:
            raise ValueError("deliver the outstanding callback before deciding again")
        claim = self._claim()
        if claim is not None:
            return self._record("stop", "Declared reporting rule has a definite outcome")
        if self.method == "response_retry":
            if (self._responses and self._responses[-1]["status"] == "timeout"
                    and self._dispatches < self.max_dispatches and now_ms < self.deadline_ms):
                return self._dispatch("Bounded timeout retry with the unchanged logical operation ID")
            return self._record("abstain", "No acknowledged success within the dispatch budget")
        if (self.native_idempotency and self._responses
                and self._responses[-1]["status"] == "timeout"
                and self._dispatches < self.max_dispatches and now_ms < self.deadline_ms):
            return self._dispatch("Declared provider idempotency permits a bounded same-key "
                                  "retry of an ambiguous timeout before the original deadline")
        all_terminal = (len(self._responses) == self._dispatches
                        and all(row.get("terminal_not_committed") is True
                                for row in self._responses))
        if (all_terminal and self._current_absence and self._observations
                and self._observations[-1]["observed_at_ms"] == now_ms
                and self._dispatches < self.max_dispatches and now_ms < self.deadline_ms):
            return self._dispatch("Fresh complete absence plus every attempt's public terminal "
                                  "no-commit guarantee opens a pre-deadline retry window")
        if self.method == "consequax_one_read" and self._final_reads:
            return self._record("abstain", "Single final read did not establish the target")
        if self.method == "consequax_one_read" and not all_terminal:
            while (self._next_read < len(self.read_times)
                   and self.read_times[self._next_read] < self.horizon_ms):
                self._next_read += 1
        if self._next_read < len(self.read_times):
            scheduled = self.read_times[self._next_read]
            if now_ms < scheduled:
                return self._record("wait", "Await the next shared read opportunity", at_ms=scheduled)
            self._next_read += 1
            self._reads += 1
            if now_ms >= self.horizon_ms:
                self._final_reads += 1
            self._pending_read = True
            return self._record("read", "Query the shared admitted readback", scheduled_at_ms=scheduled)
        return self._record("abstain", "Read budget exhausted with unresolved target or provenance")

    def finalize(self) -> dict:
        """Return claims and charged resources, without querying or writing anything."""
        claim = self._claim()
        linked_claim = (claim if self.method == "response_retry"
                        else self._evidence["this_action_linked_target"])
        report = {"method": self.method, "action_id": self.action_id,
                  "reported_success": claim, "definite_report": claim is not None,
                  "reported_state": claim,
                  "reported_action_linked": linked_claim,
                  "action_linked_definite_report": linked_claim is not None,
                  "action_linked_abstained": linked_claim is None,
                  "reported_success_target": "global_fixed_target_state",
                  "native_idempotency": self.native_idempotency,
                  "abstained": claim is None,
                  "final_target_state": self._evidence["final_target_state"],
                  "this_action_linked_target": self._evidence["this_action_linked_target"],
                  "reason": self._evidence["reason"],
                  "dispatches": self._dispatches, "reads": self._reads, "waits": self._waits,
                  "final_reads": self._final_reads,
                  "dispatch_budget": self.max_dispatches, "read_budget": len(self.read_times),
                  "decisions": copy.deepcopy(self._decisions)}
        if self._cx is not None:
            report["framework_trace"] = self._cx.trace().to_dict()
            report["retry_advice"] = copy.deepcopy(self._advice)
            report["provisional_verifications"] = copy.deepcopy(self._provisional_verifications)
        return report

