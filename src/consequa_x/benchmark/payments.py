"""Deterministic payment fixture with separate provider and readback evidence.

This is a research simulator. ``reverse`` is synthetic compensation, not a
statement that a refund on any real payment provider can be reversed.
"""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
import json
from typing import Any

from consequa_x.models import Action, Observation, ResponseStatus, ToolResponse, thaw


class Fault(str, Enum):
    CLEAN = "clean"
    FAIL_BEFORE_DISPATCH = "fail_before_dispatch"
    TIMEOUT_BEFORE_COMMIT = "timeout_before_commit"
    TIMEOUT_AFTER_COMMIT = "timeout_after_commit"
    FALSE_SUCCESS = "false_success"
    DELAYED_VISIBILITY = "delayed_visibility"
    PARTIAL_EFFECT = "partial_effect"
    DUPLICATE_EFFECT = "duplicate_effect"
    WRONG_PARAMETER = "wrong_parameter"
    WRONG_TARGET = "wrong_target"


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


class PaymentWorld:
    """A reproducible world with an explicit virtual clock and bounded funds.

    Provider executions and external operations take one virtual millisecond.
    ``delayed_visibility`` sets a source-wide 50 ms readback lag, declared by
    the observation watermark. A view remains exhaustive for that watermark.
    """

    DEFAULT_VISIBILITY_LAG_MS = 50

    def __init__(
        self,
        payments: dict[str, int] | None = None,
        currency: str = "INR",
        seed: int = 0,
    ) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValueError("seed must be an integer")
        self.currency = _identifier(currency, "currency")
        selected = {"pay_42": 1_000_000} if payments is None else payments
        if not isinstance(selected, dict):
            raise ValueError("payments must be a dict of payment ids and balances")
        self._payments = {
            _identifier(payment_id, "payment_id"): _integer(balance, "balance")
            for payment_id, balance in selected.items()
        }
        self.seed = seed
        self._time_ms = 0
        self._request_counter = 0
        self._external_counter = 0
        self._observation_counter = 0
        self._visibility_lag_ms = 0
        self._effects: list[dict[str, Any]] = []
        self._compensations: list[dict[str, Any]] = []
        self._execution_attempts: list[dict[str, Any]] = []
        self._idempotency: dict[str, dict[str, Any]] = {}

    @property
    def time_ms(self) -> int:
        return self._time_ms

    def advance(self, milliseconds: int) -> None:
        self._time_ms += _integer(milliseconds, "milliseconds")

    def snapshot(self) -> dict[str, Any]:
        """Return all fixture state by value, for evaluator-controlled replay."""
        return deepcopy(
            {
                "payments": self._payments,
                "currency": self.currency,
                "seed": self.seed,
                "time_ms": self._time_ms,
                "request_counter": self._request_counter,
                "external_counter": self._external_counter,
                "observation_counter": self._observation_counter,
                "visibility_lag_ms": self._visibility_lag_ms,
                "effects": self._effects,
                "compensations": self._compensations,
                "execution_attempts": self._execution_attempts,
                "idempotency": self._idempotency,
            }
        )

    def fork(self) -> PaymentWorld:
        """Clone clocks, counters, history and caches without sharing state."""
        return deepcopy(self)

    @property
    def ground_truth(self) -> tuple[dict[str, Any], ...]:
        """Copied evaluator-only history, including attempts without effects.

        Attempt records expose injected faults and cache lineage to an evaluator,
        while public responses and independent readback omit this hidden state.
        Refund records describe the current fixture state; execution records
        preserve which effects were committed by each attempt.
        """
        records = self._effects + self._compensations + self._execution_attempts
        records.sort(key=lambda record: record.get("committed_at_ms", record.get("time_ms", 0)))
        return tuple(deepcopy(records))

    def _response(
        self,
        attempt_id: str,
        action_id: str,
        request_id: str,
        status: ResponseStatus,
        result: dict[str, Any],
    ) -> ToolResponse:
        return ToolResponse(
            attempt_id=attempt_id,
            action_id=action_id,
            status=status,
            time_ms=self.time_ms,
            provider_request_id=request_id,
            result=deepcopy(result),
        )

    def _commit(
        self,
        effect_id: str,
        payment_id: str,
        amount_minor: int,
        *,
        actor: str,
        action_id: str | None = None,
        attempt_id: str | None = None,
    ) -> None:
        self._payments[payment_id] -= amount_minor
        record: dict[str, Any] = {
            "kind": "refund",
            "effect_id": effect_id,
            "payment_id": payment_id,
            "amount_minor": amount_minor,
            "currency": self.currency,
            "committed_at_ms": self.time_ms,
            "status": "processed",
            "actor": actor,
        }
        if action_id is not None:
            record["action_id"] = action_id
        if attempt_id is not None:
            record["attempt_id"] = attempt_id
        self._effects.append(record)

    def refund(self, action: Action, attempt_id: str, fault: Fault = Fault.CLEAN) -> ToolResponse:
        """Execute an attempt; requested response fields do not prove effects.

        A stable idempotency key is scoped to the complete action name and
        argument payload. A committed attempt with a lost response can be
        retried safely and receives its cached processed provider result.
        """
        if not isinstance(action, Action):
            raise TypeError("action must be an Action")
        _identifier(attempt_id, "attempt_id")
        try:
            fault = Fault(fault)
        except (TypeError, ValueError) as exc:
            raise ValueError("unsupported payment fault") from exc
        self.advance(1)
        self._request_counter += 1
        request_id = f"req_{self.seed}_{self._request_counter:06d}"
        refund_id = f"rf_{self.seed}_{self._request_counter:06d}"
        arguments = action.arguments
        try:
            payload = json.dumps(
                {"name": action.name, "arguments": arguments},
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            request = json.loads(payload)
        except (TypeError, ValueError):
            # Invalid caller-mutated payloads must not put non-JSON data in gold.
            payload = None
            request = {"name": action.name, "arguments": None}
        request["idempotency_key"] = action.idempotency_key
        committed_effect_ids: list[str] = []
        result_effect_ids: list[str] = []
        cache_origin: dict[str, Any] | None = None
        fault_applied = False

        def finish(status: ResponseStatus, result: dict[str, Any]) -> ToolResponse:
            response = self._response(attempt_id, action.action_id, request_id, status, result)
            self._execution_attempts.append(
                {
                    "kind": "execution_attempt",
                    "action_id": action.action_id,
                    "actor": action.actor,
                    "attempt_id": attempt_id,
                    "provider_request_id": request_id,
                    "time_ms": self.time_ms,
                    "request": deepcopy(request),
                    "request_payload_valid": payload is not None,
                    "fault": fault.value,
                    "fault_applied": fault_applied,
                    "response_status": status.value,
                    "response_result": thaw(response.result),
                    "committed_effect_ids": list(committed_effect_ids),
                    "result_effect_ids": list(result_effect_ids),
                    "cache_hit": cache_origin is not None,
                    "cache_origin": deepcopy(cache_origin),
                }
            )
            return response

        def error(code: str) -> ToolResponse:
            return finish(ResponseStatus.ERROR, {"code": code})

        if action.registered_at_ms > self.time_ms:
            return error("action_not_registered")
        payment_id = arguments.get("payment_id")
        amount_minor = arguments.get("amount_minor")
        currency = arguments.get("currency", self.currency)
        if action.name not in {"refund", "refund_payment"}:
            return error("unsupported_action")
        if not isinstance(payment_id, str) or not payment_id.strip():
            return error("invalid_payment_id")
        if payment_id not in self._payments:
            return error("payment_not_found")
        if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
            return error("invalid_amount")
        if currency != self.currency:
            return error("currency_mismatch")
        if payload is None:
            return error("invalid_payload")
        key = action.idempotency_key
        if key is not None and key in self._idempotency:
            previous = self._idempotency[key]
            if previous["payload"] != payload:
                return error("idempotency_payload_mismatch")
            cache_origin = previous["origin"]
            result_effect_ids = previous["effect_ids"]
            return finish(ResponseStatus.SUCCESS, previous["result"])
        fault_applied = fault is not Fault.CLEAN
        if fault is Fault.FAIL_BEFORE_DISPATCH:
            return error("dispatch_failed")
        if fault is Fault.TIMEOUT_BEFORE_COMMIT:
            return finish(ResponseStatus.TIMEOUT, {"code": "timeout"})

        target = payment_id
        actual_amount = amount_minor
        count = 1
        if fault is Fault.WRONG_TARGET:
            alternatives = sorted(
                candidate
                for candidate, balance in self._payments.items()
                if candidate != payment_id and balance >= amount_minor
            )
            if not alternatives:
                return error("alternative_payment_unavailable")
            target = alternatives[0]
        elif fault is Fault.WRONG_PARAMETER:
            actual_amount = amount_minor - 1 if amount_minor > 1 else 2
        elif fault is Fault.PARTIAL_EFFECT:
            actual_amount = amount_minor // 2
            if actual_amount == 0:
                return error("partial_amount_unavailable")
        elif fault is Fault.DUPLICATE_EFFECT:
            count = 2
        # Fail atomically when the complete fault scenario exceeds funds.
        if amount_minor > self._payments[payment_id]:
            return error("insufficient_balance")
        if fault is not Fault.FALSE_SUCCESS:
            if actual_amount * count > self._payments[target]:
                return error("insufficient_balance")
            for index in range(count):
                effect_id = refund_id if index == 0 else f"{refund_id}_{index + 1}"
                self._commit(
                    effect_id,
                    target,
                    actual_amount,
                    actor=action.actor,
                    action_id=action.action_id,
                    attempt_id=attempt_id,
                )
                committed_effect_ids.append(effect_id)
        if fault is Fault.DELAYED_VISIBILITY:
            self._visibility_lag_ms = self.DEFAULT_VISIBILITY_LAG_MS
        result = {
            "refund_id": refund_id,
            "payment_id": payment_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "status": "processed",
        }
        result_effect_ids = list(committed_effect_ids)
        if key is not None:
            self._idempotency[key] = {
                "payload": payload,
                "result": deepcopy(result),
                "effect_ids": list(committed_effect_ids),
                "origin": {
                    "action_id": action.action_id,
                    "attempt_id": attempt_id,
                    "provider_request_id": request_id,
                    "time_ms": self.time_ms,
                },
            }
        if fault is Fault.TIMEOUT_AFTER_COMMIT:
            return finish(ResponseStatus.TIMEOUT, {"code": "timeout"})
        return finish(ResponseStatus.SUCCESS, result)

    def read_refunds(
        self,
        payment_id: str,
        *,
        lag_ms: int = 0,
        include_provenance: bool = True,
        available: bool = True,
    ) -> Observation:
        """Read exhaustive scoped history through a declared source watermark.

        Complete does not reveal whether an effect exists beyond that watermark.
        Future reversal state is omitted so historical snapshots are faithful.
        """
        _identifier(payment_id, "payment_id")
        _integer(lag_ms, "lag_ms")
        if not isinstance(include_provenance, bool) or not isinstance(available, bool):
            raise ValueError("readback availability and provenance must be booleans")
        effective_lag = max(lag_ms, self._visibility_lag_ms)
        as_of_ms = max(0, self.time_ms - effective_lag)
        self._observation_counter += 1
        records: list[dict[str, Any]] = []
        if available:
            for effect in self._effects:
                if effect["payment_id"] != payment_id or effect["committed_at_ms"] > as_of_ms:
                    continue
                record = {
                    key: deepcopy(effect[key])
                    for key in (
                        "effect_id",
                        "payment_id",
                        "amount_minor",
                        "currency",
                        "committed_at_ms",
                    )
                }
                reversed_at = effect.get("reversed_at_ms")
                record["status"] = (
                    "reversed"
                    if reversed_at is not None and reversed_at <= as_of_ms
                    else "processed"
                )
                if reversed_at is not None and reversed_at <= as_of_ms:
                    record["reversed_at_ms"] = reversed_at
                if include_provenance:
                    for key in ("action_id", "attempt_id", "actor"):
                        if key in effect:
                            record[key] = effect[key]
                records.append(record)
        return Observation(
            observation_id=f"obs_{self.seed}_{self._observation_counter:06d}",
            source="payment_ledger",
            observed_at_ms=self.time_ms,
            as_of_ms=as_of_ms,
            scope={
                "payment_id": payment_id,
                "currency": self.currency,
                "lag_ms": effective_lag,
            },
            records=tuple(records),
            complete=True,
            available=available,
        )

    def external_refund(
        self, payment_id: str, amount_minor: int, actor: str = "external_operator"
    ) -> str:
        _identifier(payment_id, "payment_id")
        _identifier(actor, "actor")
        _integer(amount_minor, "amount_minor", minimum=1)
        if payment_id not in self._payments:
            raise ValueError("payment not found")
        if amount_minor > self._payments[payment_id]:
            raise ValueError("insufficient balance")
        self.advance(1)
        self._external_counter += 1
        effect_id = f"ext_{self.seed}_{self._external_counter:06d}"
        self._commit(effect_id, payment_id, amount_minor, actor=actor)
        return effect_id

    def reverse(self, effect_id: str) -> None:
        """Log a one-time synthetic compensation and restore fixture funds."""
        _identifier(effect_id, "effect_id")
        effect = next(
            (record for record in self._effects if record["effect_id"] == effect_id),
            None,
        )
        if effect is None:
            raise ValueError("effect not found")
        if "reversed_at_ms" in effect:
            raise ValueError("effect already compensated")
        self.advance(1)
        effect["status"] = "reversed"
        effect["reversed_at_ms"] = self.time_ms
        self._payments[effect["payment_id"]] += effect["amount_minor"]
        self._compensations.append(
            {
                "kind": "synthetic_compensation",
                "effect_id": effect_id,
                "payment_id": effect["payment_id"],
                "amount_minor": effect["amount_minor"],
                "currency": self.currency,
                "time_ms": self.time_ms,
            }
        )
