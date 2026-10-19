"""Polling readback until the evidence settles, and retry advice from receipts."""

import pytest

from consequa_x import (
    Observation, OutcomeContract, RecordVerifier, RecorderError, RetryAdvice, TraceRecorder,
    VerificationStatus, poll_readback, retry_advice,
)


VERIFIER = RecordVerifier(scope_fields=("order_id",))
ROW = {"effect_id": "rf-1", "order_id": "o-1", "committed_at_ms": 20,
       "action_id": "refund-1", "actor": "agent"}


def setup():
    now = [0]
    rec = TraceRecorder("run", actor="agent", clock=lambda: now[0])
    capture = rec.register("refund-1", "issue_refund", {"order_id": "o-1"}, contract=OutcomeContract(
        contract_id="c", predicate="record_present", expected={"order_id": "o-1"},
        deadline_ms=50, stability_ms=10))
    now[0] = 5
    rec.response(capture.dispatch(), "timeout")

    def sleep(seconds):
        now[0] += round(seconds * 1000)

    return rec, capture, now, sleep


def lagging_replica(now, lag_ms, records=(ROW,), available=True):
    def read(number):
        return Observation(observation_id=f"read-{number}", source="replica",
                           observed_at_ms=now[0], as_of_ms=max(0, now[0] - lag_ms),
                           scope={"order_id": "o-1"}, records=records, available=available)
    return read


def test_poller_waits_for_the_horizon_and_rereads_a_lagging_replica():
    rec, capture, now, sleep = setup()
    receipt = poll_readback(capture, lagging_replica(now, lag_ms=15), until_ms=500,
                            interval_ms=10, verifier=VERIFIER, sleep=sleep)
    assert receipt.status is VerificationStatus.SATISFIED
    trace = rec.trace()
    # First read at the horizon (60): watermark 45 is too early. Second at 70: watermark 55.
    # Third at 80: watermark 65 covers the horizon.
    assert [item.observed_at_ms for item in trace.observations] == [60, 70, 80]
    assert [item.status.value for item in trace.verifications] == ["unknown", "unknown", "satisfied"]
    assert retry_advice(trace).advice is RetryAdvice.DO_NOT_RETRY


def test_poller_returns_unknown_at_the_limit_instead_of_guessing():
    rec, capture, now, sleep = setup()
    receipt = poll_readback(rec, lagging_replica(now, lag_ms=0, available=False),
                            until_ms=100, interval_ms=25, verifier=VERIFIER, sleep=sleep)
    assert receipt.status is VerificationStatus.UNKNOWN
    assert [item.observed_at_ms for item in rec.trace().observations] == [60, 85]
    advice = retry_advice(receipt)
    assert advice.advice is RetryAdvice.WAIT and "unavailable" in advice.reason


def test_poller_checks_its_inputs():
    rec, capture, now, sleep = setup()
    with pytest.raises(RecorderError, match="positive"):
        poll_readback(capture, lagging_replica(now, 0), until_ms=10, interval_ms=0, sleep=sleep)
    with pytest.raises(RecorderError, match="nonnegative"):
        poll_readback(capture, lagging_replica(now, 0), until_ms=-1, interval_ms=5, sleep=sleep)
    with pytest.raises(TypeError, match="Observation"):
        poll_readback(capture, lambda number: {"not": "an observation"}, until_ms=100,
                      interval_ms=5, sleep=sleep)
    with pytest.raises(TypeError):
        poll_readback(object(), lagging_replica(now, 0), until_ms=100, interval_ms=5)


def check(records):
    rec, capture, now, sleep = setup()
    now[0] = 100
    return capture.verify(lagging_replica(now, 0, records=records)(1), verifier=VERIFIER)


def test_retry_advice_follows_the_verified_outcome():
    assert retry_advice(None).advice is RetryAdvice.WAIT
    done = retry_advice(check((ROW,)))
    assert done.advice is RetryAdvice.DO_NOT_RETRY and "this action" in done.reason
    staff = {"effect_id": "rf-2", "order_id": "o-1", "committed_at_ms": 20, "actor": "staff"}
    by_other = retry_advice(check((staff,)))
    assert by_other.advice is RetryAdvice.DO_NOT_RETRY and "another actor" in by_other.reason
    reversed_row = {**ROW, "removed_at_ms": 30}
    escalate = retry_advice(check((reversed_row,)))
    assert escalate.advice is RetryAdvice.ESCALATE and escalate.effect_ids == ("rf-1",)
    permitted = retry_advice(check(()))
    assert permitted.advice is RetryAdvice.RETRY_PERMITTED
    assert "idempotency key" in permitted.reason
    assert permitted.to_dict()["advice"] == "retry_permitted"
    with pytest.raises(TypeError):
        retry_advice({"status": "satisfied"})
