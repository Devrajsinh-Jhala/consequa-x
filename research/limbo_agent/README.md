# Prospective external fault-benchmark integration

This directory prepares a later LIMBO integration. It contains no measured
benchmark result. The [design](DESIGN.md), retained identity preflight and
separate source-review receipt pin the allowed upstream public API inspection.
No task definitions, released episode archives or service handler bodies were
used for this preparation, and no upstream module or model was executed.

`boundary.py` is a trusted-code public runtime view. It copies declared public
metadata and observations, delegates actual tool/verification/wait operations,
rejects privileged verification before dispatch, and journals work and failures.
The trusted runner retains native objects and callbacks. This is not a Python
or operating-system security sandbox against hostile introspection.

The 60 focused tests in `tests/test_limbo_public_boundary.py` use invented API
fakes only. They check data aliases, hidden attributes, exact false-only public
verification, uncertainty/partial statuses, delegated work, ceilings, delayed
effects during waits and audit-sink failures. They are engineering checks, not
60 native benchmark episodes or evidence of framework superiority.

The stock guard directly accesses native `tools`, `world` and `events`. A
reviewed public policy adapter, validation of actual per-domain verification
shapes/costs, native guard parity, replay, complete local transport/context
checks, and a separately frozen schedule/protocol remain necessary. This
scaffold does not replace the retained failed airline condition. GitHub Actions
remains disabled, with no humans or paid inference involved.
