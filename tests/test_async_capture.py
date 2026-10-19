"""Asynchronous agents: awaited tools, async verifiers and async readback polling."""

import asyncio

import pytest

from consequa_x import (
    Observation, OutcomeContract, RecordVerifier, ResponseStatus, TraceRecorder,
    VerificationStatus, apoll_readback, averify, capture_tool, verify,
)


VERIFIER = RecordVerifier(scope_fields=("order_id",))


def recorder():
    now = [0]
    rec = TraceRecorder("run", actor="agent", clock=lambda: now[0])
    capture = rec.register("refund-1", "issue_refund", {"order_id": "o-1"}, contract=OutcomeContract(
        contract_id="c", predicate="record_present", expected={"order_id": "o-1"},
        deadline_ms=50, stability_ms=10))
    return rec, capture, now


def readback(now, number, *, lag=0):
    return Observation(observation_id=f"read-{number}", source="replica", observed_at_ms=now[0],
                       as_of_ms=max(0, now[0] - lag), scope={"order_id": "o-1"},
                       records=({"effect_id": "rf-1", "order_id": "o-1", "committed_at_ms": 20,
                                 "action_id": "refund-1", "actor": "agent"},))


def test_capture_tool_and_acall_record_awaited_tools_including_timeouts():
    rec, capture, now = recorder()

    @capture_tool(capture)
    async def issue_refund(order_id):
        await asyncio.sleep(0)
        return {"accepted": order_id}

    async def times_out():
        raise TimeoutError("provider did not answer")

    async def run():
        assert await issue_refund("o-1") == {"accepted": "o-1"}
        with pytest.raises(TimeoutError):
            await capture.acall(times_out)
        assert await rec.acall(lambda: {"sync": True}) == {"sync": True}

    asyncio.run(run())
    responses = rec.trace().responses
    assert [item.status for item in responses] == [
        ResponseStatus.SUCCESS, ResponseStatus.TIMEOUT, ResponseStatus.SUCCESS]
    assert responses[0].result == {"accepted": "o-1"}
    assert responses[1].result == {"exception": "TimeoutError"}


def test_async_verifiers_need_averify_and_are_checked_like_sync_ones():
    rec, capture, now = recorder()
    now[0] = 100

    class AsyncVerifier:
        async def verify(self, action, observation):
            await asyncio.sleep(0)
            return VERIFIER.verify(action, observation)

    observation = readback(now, 1)
    with pytest.raises(TypeError, match="averify"):
        verify(capture.action, observation, verifier=AsyncVerifier())
    receipt = asyncio.run(averify(capture.action, observation, verifier=AsyncVerifier()))
    assert receipt.status is VerificationStatus.SATISFIED

    class WrongAction:
        async def verify(self, action, observation):
            receipt = VERIFIER.verify(action, observation)
            return receipt.__class__(**{**receipt.__dict__, "action_id": "other"})

    with pytest.raises(ValueError, match="action_id"):
        asyncio.run(averify(capture.action, observation, verifier=WrongAction()))
    assert asyncio.run(rec.averify(readback(now, 2), verifier=AsyncVerifier())).status \
        is VerificationStatus.SATISFIED


def test_apoll_readback_awaits_reads_and_sleeps():
    rec, capture, now = recorder()
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
        now[0] += round(seconds * 1000)

    async def read(number):
        return readback(now, number, lag=15)

    receipt = asyncio.run(apoll_readback(capture, read, until_ms=500, interval_ms=10,
                                         verifier=VERIFIER, sleep=sleep))
    assert receipt.status is VerificationStatus.SATISFIED
    assert slept == [0.06, 0.01, 0.01]
    assert len(rec.trace().verifications) == 3
