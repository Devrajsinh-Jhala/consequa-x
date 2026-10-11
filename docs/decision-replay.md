# Decision-prefix replay

`replay_decision_prefix` reconstructs a recorded refund episode in a fresh
simulator, holds a declared factual decision prefix, and queries the unchanged
policy for the continuation. This is a replay primitive for future comparison
methods; it does not compute causal attribution or reproduce CAR.

```python
from consequa_x.benchmark.decision_replay import replay_decision_prefix
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.policy_runner import run_policy_scenario
from consequa_x.benchmark.runner import ScenarioConfig
from consequa_x.policies import ScriptedRefundPolicy

policy = ScriptedRefundPolicy()
factual = run_policy_scenario(ScenarioConfig(), policy, seed=0)
continuation = BudgetedPolicy(policy, max_calls=6)
branch = replay_decision_prefix(
    factual, continuation, hold_count=1, continuation_seed=100,
)
print(branch.summary())
```

`hold_count` counts captured policy decisions, starting at selection. Holding
all decisions reuses the entire recording and spends zero new policy calls.
The factual recording in this example is outside the continuation budget and
must be accounted for separately. One `BudgetedPolicy` can be shared across
repetitions to enforce a global continuation-call limit.

## What is preserved and checked

The factual configuration, simulator seed, world identities, outcome contract,
attempt budget, and task template remain fixed. A separately validated
`continuation_seed` selects model phase keys. Every branch starts a fresh
payment world; its held operations reconstruct the prefix rather than sharing
mutable state with another branch.

Before any continuation provider call, the primitive decodes the captured
requests/replies, checks their stage and seed schedule, and reconstructs the
complete factual trace with recorded decisions. A wrong template, incomplete or
inconsistent capture, or changed declared policy metadata is rejected. Each
held decision must again receive exactly its recorded public request, including
tool responses. Held replies carry explicit reuse metadata and cannot be
mistaken for fresh inference. Continuation replies retain their provider data,
and actual requested phase seeds are recorded in the trace and decision receipts.

Declared metadata equality checks configuration identity; it cannot prove that
the policy implementation or model's hidden runtime state is unchanged. Seed
requests also do not guarantee deterministic model output.

## Failures and cost

Branch receipts retain held/resampled requests, completed decisions, actual
attempted provider-call counts, failures, budget refusal, and unreached factual
decision positions. Earlier or longer continuations are allowed within the
original attempt budget. A failed branch has no episode or invented outcome.
Factual validation uses captured decisions and simulated payments, so it makes
no provider calls; its local compute cost is still real and separately measurable.

The [CAR reproduction plan](car-reproduction-plan.md) describes the estimators
and matching requirements still needed. [Decision contrastive replay](decision-contrastive.md)
uses this primitive to estimate suffix effects against a single observed outcome.
The existing context leave-one-out estimator remains a distinct baseline.
