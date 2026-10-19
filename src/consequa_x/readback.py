"""Read back an action's outcome until the evidence can settle it.

Verification needs readback whose watermark covers the contract horizon, and a
replica or ledger may lag. ``poll_readback`` waits until the horizon, then reads
back and verifies repeatedly through the action's ``ActionCapture``, recording
every observation and receipt, until a receipt is ``satisfied`` or ``violated``
or the time limit passes. An ``unknown`` result after the limit is returned as
is: waiting longer is the caller's decision, never an inferred outcome.
"""

from __future__ import annotations

import time
from typing import Callable

from .capture import ActionCapture, TraceRecorder
from .errors import ConsequaTypeError, RecorderError
from .models import Observation, VerificationResult, VerificationStatus
from .verification import Verifier


def poll_readback(capture: ActionCapture | TraceRecorder,
                  read: Callable[[int], Observation], *,
                  until_ms: int, interval_ms: int, verifier: Verifier | None = None,
                  sleep: Callable[[float], None] = time.sleep) -> VerificationResult:
    """Verify fresh readback until the outcome is known or ``until_ms`` passes.

    ``read(n)`` performs the ``n``-th read (starting at 1) through an
    independent, read-only path and returns its ``Observation``; give each read
    its own ``observation_id``. Times use the recorder's clock and time base.
    The first read happens once the clock reaches the contract horizon (or
    immediately, if it already has). Reads repeat every ``interval_ms`` while the
    receipt is ``unknown`` and the clock is before ``until_ms``. ``sleep`` takes
    seconds; inject one that advances a simulated clock in tests. Returns the
    last receipt; every receipt stays recorded in the trace.
    """
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
    recorder = capture._recorder
    horizon = capture.action.contract.horizon_ms
    now = recorder.now()
    if now < horizon:
        sleep((horizon - now) / 1000)
    number = 0
    while True:
        number += 1
        observation = read(number)
        if not isinstance(observation, Observation):
            raise ConsequaTypeError("read must return an Observation")
        receipt = capture.verify(observation, verifier=verifier)
        now = recorder.now()
        if receipt.status is not VerificationStatus.UNKNOWN or now + interval_ms > until_ms:
            return receipt
        sleep(interval_ms / 1000)
