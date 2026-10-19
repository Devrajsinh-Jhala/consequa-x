"""Read back an action's outcome until the evidence can settle it.

Verification needs readback whose watermark covers the contract horizon, and a
replica or ledger may lag. ``poll_readback`` waits until the horizon, then reads
back and verifies repeatedly through the action's ``ActionCapture``, recording
every observation and receipt, until a receipt is ``satisfied`` or ``violated``
or the time limit passes. An ``unknown`` result after the limit is returned as
is: waiting longer is the caller's decision, never an inferred outcome.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Awaitable, Callable

from .capture import ActionCapture, TraceRecorder
from .errors import ConsequaTypeError, RecorderError
from .models import Observation, VerificationResult, VerificationStatus
from .verification import Readback, Verifier


def _start(capture, read, until_ms, interval_ms):
    if isinstance(capture, TraceRecorder):
        capture = capture._sole()
    if not isinstance(capture, ActionCapture):
        raise ConsequaTypeError("poll_readback requires an ActionCapture or a TraceRecorder")
    if not callable(read):
        raise ConsequaTypeError("read must be callable")
    for value, label in ((until_ms, "until_ms"), (interval_ms, "interval_ms")):
        if type(value) is not int or value < 0:
            raise RecorderError(f"{label} must be a nonnegative integer")
    if interval_ms == 0:
        raise RecorderError("interval_ms must be positive")
    return capture


def _observation(value: Any) -> Readback:
    if isinstance(value, Observation) or (
            isinstance(value, (tuple, list)) and value
            and all(isinstance(item, Observation) for item in value)):
        return value
    raise ConsequaTypeError("read must return an Observation (or a nonempty sequence of them)")


def poll_readback(capture: ActionCapture | TraceRecorder,
                  read: Callable[[int], Readback], *,
                  until_ms: int, interval_ms: int, verifier: Verifier | None = None,
                  sleep: Callable[[float], None] = time.sleep) -> VerificationResult:
    """Verify fresh readback until the outcome is known or ``until_ms`` passes.

    ``read(n)`` performs the ``n``-th read (starting at 1) through an
    independent, read-only path and returns its ``Observation``; give each read
    its own ``observation_id``. For a verifier that reads several sources, such
    as ``CompositeVerifier``, ``read`` returns a tuple with one observation per
    source. Times use the recorder's clock and time base.
    The first read happens once the clock reaches the contract horizon (or
    immediately, if it already has). Reads repeat every ``interval_ms`` while the
    receipt is ``unknown`` and the clock is before ``until_ms``. ``sleep`` takes
    seconds; inject one that advances a simulated clock in tests. Returns the
    last receipt; every receipt stays recorded in the trace.
    """
    capture = _start(capture, read, until_ms, interval_ms)
    recorder = capture._recorder
    horizon = capture.action.contract.horizon_ms
    now = recorder.now()
    if now < horizon:
        sleep((horizon - now) / 1000)
    number = 0
    while True:
        number += 1
        receipt = capture.verify(_observation(read(number)), verifier=verifier)
        now = recorder.now()
        if receipt.status is not VerificationStatus.UNKNOWN or now + interval_ms > until_ms:
            return receipt
        sleep(interval_ms / 1000)


async def apoll_readback(capture: ActionCapture | TraceRecorder,
                         read: Callable[[int], Readback | Awaitable[Readback]], *,
                         until_ms: int, interval_ms: int, verifier: Verifier | None = None,
                         sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                         ) -> VerificationResult:
    """``poll_readback`` for asynchronous agents.

    ``read`` may be a coroutine function, the verifier's ``verify`` may be a
    coroutine, and waiting uses ``asyncio.sleep`` unless ``sleep`` is given.
    """
    capture = _start(capture, read, until_ms, interval_ms)
    recorder = capture._recorder
    horizon = capture.action.contract.horizon_ms
    now = recorder.now()
    if now < horizon:
        await sleep((horizon - now) / 1000)
    number = 0
    while True:
        number += 1
        value = read(number)
        if inspect.isawaitable(value):
            value = await value
        receipt = await capture.averify(_observation(value), verifier=verifier)
        now = recorder.now()
        if receipt.status is not VerificationStatus.UNKNOWN or now + interval_ms > until_ms:
            return receipt
        await sleep(interval_ms / 1000)
