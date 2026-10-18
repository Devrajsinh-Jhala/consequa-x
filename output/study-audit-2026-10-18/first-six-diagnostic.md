# Collection prefix diagnostic

Audited 18 October 2026. Scope: the first six completed slots, episode_00000
through episode_00005, in frozen protocol
`e8859ef64006780298922ef24215f4e080fa84575032a65944268317a6ee55ab`.
This is an execution and target-semantics check, not an interim effectiveness
analysis or a stopping criterion.

The completed receipts, traces and evaluator ledgers were copied before
inspection and matched their retained SHA-256 values. A closed, hash-chained
journal prefix independently bound every receipt and all six raw requests and
HTTP-200 responses. No live model call, prompt change, replacement sample,
frozen-source edit or modification to the collection directory was made.

All six slots contain one genuine Gemma 3 1B / refund-policy-v2 selection call.
The raw provider output chooses `stop`, reports `unknown`, and says no outcome
has been observed. The schema offers both `refund` and `stop`; the runner has
not silently forced or substituted the stop operation. Visible requests contain
task, context, public response history, stage and remaining attempts. No injected
fault identity or evaluator ledger is supplied to the model.

No refund was dispatched in these six slots. Their fixed positive refund
contracts therefore have false global-state and false action-linked gold
targets, including when the eligible customer request was declined. Those two
targets are assessable despite the absence of a selected action. The origin
target is unknown because no effect exists, and correctly contributes no
assessable origin label. This measures factual contract satisfaction separately
from whether declining the eligible request was a good policy decision.

For five slots, the exhaustive empty readback covers the 120 ms horizon, so the
state verifier and same-information reference can establish violation and false
action-linked satisfaction. The state-only ablation establishes the violation
and retains its declared linkage abstention. For the delayed-readback slot,
the watermark is 0 ms, before the 120 ms horizon. Public auditors correctly
abstain even though the hidden simulator ledger determines both gold targets.
Response-only and structured self-report abstain in every audited slot because
there is no tool response and the reported status is unknown.

These slots provide no executed fault-handling observations. In the final
report, show selection/dispatch rates and exposed-versus-realized mechanisms
beside auditor results. A perfect score on exhaustive empty ledgers would not
establish robust refund execution, retry handling or successful service. Retain
all such episodes under the frozen plan; do not tune or replace them because
they declined to act. Execution-conditional views, if added, should supplement
the complete planned-denominator results and state their conditional scope.

Machine-readable details: `first-six-completed.json` and
`first-six-provider-binding.json`. Local evidence snapshots are under
`tmp/study-audit-2026-10-18-first-six/`.
