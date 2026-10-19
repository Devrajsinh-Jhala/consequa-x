"""Decide what verified evidence says about retrying a consequential action.

A timed-out tool call tempts an agent to retry, and a retry after a hidden
success duplicates the effect: a second refund, a second order. ``retry_advice``
reads the latest verification receipt and returns advice with its reason. It is
advice derived from captured evidence, not a guarantee: an attempt still in
flight can commit after the readback, so a retry should still carry an
idempotency key where the downstream system supports one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import ConsequaTypeError
from .models import OriginStatus, Trace, VerificationResult, VerificationStatus, to_dict


class RetryAdvice(str, Enum):
    DO_NOT_RETRY = "do_not_retry"
    """The requested outcome holds; a retry would duplicate it."""
    WAIT = "wait"
    """The outcome is not established yet; retrying now risks a duplicate."""
    ESCALATE = "escalate"
    """Effects exist but do not satisfy the contract; a person should decide."""
    RETRY_PERMITTED = "retry_permitted"
    """No relevant effect was observed in a complete readback through the horizon."""


@dataclass(frozen=True)
class RetryDecision:
    advice: RetryAdvice
    reason: str
    effect_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return to_dict(self)


def retry_advice(evidence: VerificationResult | Trace | None, *,
                 action_id: str | None = None) -> RetryDecision:
    """Advise on retrying, from a receipt or from a trace's latest receipt.

    - no receipt or an ``unknown`` one: ``WAIT``. Missing or incomplete
      readback never permits a retry;
    - ``satisfied``: ``DO_NOT_RETRY``, whoever produced the effect;
    - ``violated`` with relevant effects (wrong values, duplicates, reversals):
      ``ESCALATE``;
    - ``violated`` with no relevant effect: ``RETRY_PERMITTED``. The readback
      was complete and covered the horizon, but an attempt still in flight can
      commit later, so use an idempotency key.

    With a ``Trace``, ``action_id`` names the action (optional when there is
    only one).
    """
    if isinstance(evidence, Trace):
        evidence = evidence.latest_verification(action_id)
    elif evidence is not None and not isinstance(evidence, VerificationResult):
        raise ConsequaTypeError("retry_advice requires a VerificationResult, a Trace or None")
    if evidence is None:
        return RetryDecision(RetryAdvice.WAIT, "No independent readback has been verified yet.")
    if evidence.status is VerificationStatus.UNKNOWN:
        return RetryDecision(RetryAdvice.WAIT,
                             f"The outcome is not established: {evidence.reason or 'unknown'}.")
    if evidence.status is VerificationStatus.SATISFIED:
        who = {OriginStatus.CONFIRMED: "this action",
               OriginStatus.OTHER_ACTOR: "another actor"}.get(evidence.origin, "an unconfirmed actor")
        return RetryDecision(RetryAdvice.DO_NOT_RETRY,
                             f"The requested outcome already holds, produced by {who}.",
                             evidence.effect_ids)
    if evidence.effect_ids:
        return RetryDecision(RetryAdvice.ESCALATE,
                             "Relevant effects exist but do not satisfy the contract.",
                             evidence.effect_ids)
    return RetryDecision(RetryAdvice.RETRY_PERMITTED,
                         "A complete readback through the horizon shows no relevant effect. "
                         "An attempt still in flight could commit later; retry with an "
                         "idempotency key.")
