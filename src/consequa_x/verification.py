"""Read-only verification; a tool acknowledgement is never verification evidence."""

from typing import Protocol

from .models import (
    Action,
    Evidence,
    Observation,
    OriginStatus,
    VerificationResult,
    VerificationStatus,
)


class Verifier(Protocol):
    def verify(self, action: Action, observation: Observation) -> VerificationResult: ...


class RefundVerifier:
    """Check a bounded refund predicate against an exhaustive source snapshot.

    The target is a processed refund committed between registration and deadline,
    still processed through the contract's stability horizon. Exact counts must
    remain constant from the deadline through that horizon, including retries
    committed during that interval. ``exact_count=None`` requires at least one
    such witness; zero explicitly requires no matching processed refunds.
    The source watermark must cover the horizon even for a positive witness.
    Origin metadata is evaluated separately from postcondition satisfaction.
    """

    def verify(self, action: Action, observation: Observation) -> VerificationResult:
        contract = action.contract
        if contract.predicate != "refund_processed":
            raise ValueError(f"Unsupported predicate: {contract.predicate!r}")
        expected = contract.expected
        if set(expected) != {"payment_id", "amount_minor", "currency"}:
            raise ValueError("refund_processed expects payment_id, amount_minor, and currency")
        if not _identifier(expected["payment_id"]):
            raise ValueError("Expected payment_id must be a nonempty string")
        if type(expected["amount_minor"]) is not int or expected["amount_minor"] <= 0:
            raise ValueError("Expected amount_minor must be a positive integer")
        if not _identifier(expected["currency"]):
            raise ValueError("Expected currency must be a nonempty string")
        if contract.deadline_ms < action.registered_at_ms:
            raise ValueError("Contract deadline precedes action registration")

        details = {
            "scope": dict(observation.scope),
            "watermark_ms": observation.as_of_ms,
            "horizon_ms": contract.horizon_ms,
            "complete": observation.complete,
            "available": observation.available,
            "expected": dict(expected),
            "records": [dict(record) for record in observation.records],
        }
        def result(status, reason, origin=OriginStatus.UNKNOWN, effect_ids=(), linked_ids=()):
            evidence = (Evidence(
                observation_id=observation.observation_id,
                source=observation.source,
                as_of_ms=observation.as_of_ms,
                details=details,
            ),)
            return VerificationResult(
                contract_id=contract.contract_id,
                status=status,
                observed_at_ms=observation.observed_at_ms,
                evidence=evidence,
                origin=origin,
                effect_ids=effect_ids,
                attributable_effect_ids=linked_ids,
                reason=reason,
            )

        if not observation.available:
            return result(VerificationStatus.UNKNOWN, "Readback source is unavailable")
        if observation.scope.get("payment_id") != expected["payment_id"] or (
            "currency" in observation.scope
            and observation.scope["currency"] != expected["currency"]
        ):
            return result(VerificationStatus.UNKNOWN, "Readback scope does not cover this payment")
        if not observation.complete:
            return result(VerificationStatus.UNKNOWN, "Readback is not exhaustive for its scope")
        if observation.as_of_ms < contract.horizon_ms:
            return result(VerificationStatus.UNKNOWN, "Readback watermark precedes contract horizon")

        relevant = []
        seen_ids = set()
        for record in observation.records:
            fields = {"effect_id", "payment_id", "amount_minor", "currency", "committed_at_ms", "status"}
            if not fields <= record.keys():
                return result(VerificationStatus.UNKNOWN, "Readback contains an incomplete effect record")
            if (
                not _identifier(record["effect_id"])
                or record["effect_id"] in seen_ids
                or type(record["committed_at_ms"]) is not int
                or not 0 <= record["committed_at_ms"] <= observation.as_of_ms
                or type(record["amount_minor"]) is not int
                or record["amount_minor"] <= 0
                or not _identifier(record["payment_id"])
                or not _identifier(record["currency"])
                or not isinstance(record["status"], str)
                or record["status"] not in {"processed", "reversed"}
            ):
                return result(VerificationStatus.UNKNOWN, "Readback contains invalid or duplicate effect records")
            seen_ids.add(record["effect_id"])
            if any(key in record and not _identifier(record[key])
                   for key in ("action_id", "attempt_id", "actor")):
                return result(VerificationStatus.UNKNOWN, "Readback contains invalid origin metadata")
            reversed_at = record.get("reversed_at_ms")
            if "reversed_at_ms" in record and (
                type(reversed_at) is not int
                or not record["committed_at_ms"] <= reversed_at <= observation.as_of_ms
            ):
                return result(VerificationStatus.UNKNOWN, "Readback has an invalid compensation time")
            if record["status"] == "reversed" and reversed_at is None:
                return result(VerificationStatus.UNKNOWN, "Compensation lacks a temporal witness")
            if record["status"] == "processed" and reversed_at is not None:
                return result(VerificationStatus.UNKNOWN, "Effect state contradicts its compensation time")
            if record["payment_id"] != expected["payment_id"]:
                return result(VerificationStatus.UNKNOWN, "Readback includes records outside its declared scope")
            if action.registered_at_ms <= record["committed_at_ms"] <= contract.horizon_ms:
                relevant.append(record)

        payload_matches = [record for record in relevant if (
            record["amount_minor"] == expected["amount_minor"]
            and record["currency"] == expected["currency"]
        )]
        matching = [record for record in payload_matches
                    if record.get("reversed_at_ms", contract.horizon_ms + 1) > contract.horizon_ms]
        eligible = [record for record in matching
                    if record["committed_at_ms"] <= contract.deadline_ms]
        peak_count = _peak_count(payload_matches, contract.deadline_ms, contract.horizon_ms)
        effect_ids = tuple(record["effect_id"] for record in relevant)
        linked_ids = tuple(record["effect_id"] for record in relevant
                           if record.get("action_id") == action.action_id
                           and record.get("actor", action.actor) == action.actor)
        if linked_ids:
            origin = OriginStatus.CONFIRMED
        elif relevant and all(record.get("actor") and record["actor"] != action.actor
                              and record.get("action_id") != action.action_id
                              for record in relevant):
            origin = OriginStatus.OTHER_ACTOR
        else:
            origin = OriginStatus.UNKNOWN

        details["matching_count"] = len(matching)
        details["eligible_count"] = len(eligible)
        details["peak_matching_count"] = peak_count
        details["relevant_count"] = len(relevant)
        count_ok = bool(eligible) if contract.exact_count is None else (
            len(eligible) == contract.exact_count and peak_count == contract.exact_count
        )
        if count_ok:
            return result(VerificationStatus.SATISFIED,
                          "Refund predicate is satisfied through the declared horizon",
                          origin, effect_ids, linked_ids)
        return result(VerificationStatus.VIOLATED,
                      "Refund predicate is violated in an exhaustive horizon-covering snapshot",
                      origin, effect_ids, linked_ids)


def _identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _peak_count(records: list[dict], deadline_ms: int, horizon_ms: int) -> int:
    """Maximum matching processed count during the closed stability interval.

    Changes sharing a timestamp are atomic in this snapshot model. A reversal
    at the deadline has already removed its refund from the starting count.
    """
    count = sum(record["committed_at_ms"] <= deadline_ms
                and record.get("reversed_at_ms", horizon_ms + 1) > deadline_ms
                for record in records)
    peak = count
    changes: dict[int, int] = {}
    for record in records:
        committed_at = record["committed_at_ms"]
        reversed_at = record.get("reversed_at_ms", horizon_ms + 1)
        if deadline_ms < committed_at <= horizon_ms:
            changes[committed_at] = changes.get(committed_at, 0) + 1
        if deadline_ms < reversed_at <= horizon_ms:
            changes[reversed_at] = changes.get(reversed_at, 0) - 1
    for time_ms in sorted(changes):
        count += changes[time_ms]
        peak = max(peak, count)
    return peak


def verify(action: Action, observation: Observation) -> VerificationResult:
    """Verify a registered built-in outcome contract without executing a write."""
    return RefundVerifier().verify(action, observation)
