# Native external pilot: methods and limits draft

This is a prospective writing note, not an experiment result. The current
source implements the design below, but the main manuscript must add it as
completed evaluation only after the execution protocol, source freeze, complete
disposition table and automated audit are bound to retained artifacts. No
autonomous outcome or conference-readiness claim is made here.

## Methods paragraph

The proposed external pilot uses the maintained airline environment at upstream
revision `96a3ef92329baf908ffe9dfe188cea34e8701d2a` (Python distribution
`tau2` 1.0.1). Twelve task IDs are selected by a fixed metadata-based hash rule,
excluding development tasks, with six nonempty and six empty communication
requirements. One declared seed and four conditions yield 48 planned
trajectories on **12 distinct tasks**. The complete task order and rotating arm
order are frozen before evaluation. Every condition retains the native domain
policy, tool definitions, initialization, autonomous assistant, dynamic user,
and required DB plus COMMUNICATE reward. The assistant and simulated user use
the same local Qwen3 4B Instruct model; neither is a human assessor. The
assistant and field-contract compiler receive proposed actions and actual
public tool responses, while reference actions, evaluation criteria, expected
databases and the private user scenario remain outside their inputs. Actual
wrapper-inserted reads execute through the native orchestrator and remain in
the transcript. Native schemas are transmitted unchanged; the pinned local
provider's schema-title omission and serialization are disclosed. Before each
generation, an exact full-history render and runtime token-ID check rejects
context overflow or a changed model identity without trimming the history.

| Condition | Public information and interpretation | Dispatch guard |
| --- | --- | --- |
| B | Raw native preflight/post-return reads and a common recovery instruction; no derived field verdict and no ConseqaX import | None |
| C | Same prescribed read opportunities; standard-library arithmetic reports the declared current-field predicate | Fixed conservative guard |
| R | Same prescribed read opportunities; ConseqaX 2.1.1 emits a current-field receipt | None |
| G | Same prescribed read opportunities; ConseqaX 2.1.1 emits a current-field receipt | Same fixed guard as C |

The read schedule is determined from a proposed mutation and available public
IDs; subsequent dialogue and observations may diverge between conditions.
C and G implement the same application predicate and guard rules, providing
a strong classical comparison. C emits a compact report whereas G emits a
full receipt, so their model-visible context and token costs are not identical.
C/G contrasts cannot isolate verifier arithmetic from report representation.
The guard blocks an already dispatched identical payload and a changed payload
on a resource whose previous result remains unresolved. All conditions share
the proposed ceilings of 80 native steps, 48 combined assistant/user completion
invocations, 512 generated tokens per request, a 600-second request timeout,
and a parent-enforced 3,600-second trajectory limit, with no corrective retries.
Freeze the final values and source/protocol identifiers before describing
these as measured conditions.

## Endpoints and automated audit paragraph

The primary finite-pilot endpoint is full required native task reward over all
12 planned trajectories per condition. Failures and unstarted trajectories
remain in that denominator with zero operational success; an execution without
a returned native simulation has unavailable native reward and components,
not an invented failed semantic grade. Native premature terminations retain
their original zero reward and missing component outputs. Report substantive
and empty communication criteria separately: the latter pass vacuously under
the native evaluator. Required substring matching measures a narrow criterion,
not explanation quality. Secondary descriptive endpoints retain per-task
contrasts, current-field statuses, actual reads/writes, repeated identical
payload proposals and dispatches, guard blocks, model calls, available usage,
latency and unavailable accounting. A repeated request alone does not prove
an unwanted duplicate business effect.

A separate saved-artifact auditor, importing neither the collection runner nor
the research wrapper or transport, reconstructs every actual tool dispatch
chronologically, including read responses, and compares native responses and
before/after database hashes. It then regrades the saved trajectory through
the unchanged native evaluator with strict replay. Both checks are needed
because native strict replay skips nonmutating reads. Audit uses evaluator-only
initialization and reference data in a fresh process without generation or
network access. This is separately implemented automated checking within the
same AI-assisted project, not external replication or human validation.

## Limits paragraph

The corpus was exposed during the project's earlier model-free transfer
experiment. This pilot is a prospective autonomous execution condition on
externally authored, previously exposed tasks, not an author-unseen holdout.
Twelve deliberately stratified IDs and one model/seed do not support a full
benchmark score, task-population significance claim or broad service-level
generalization. The benchmark runs locally with synchronous tool responses;
no acknowledgement loss, delayed commit or external provider race is injected.
Its current public fields do not establish durable temporal satisfaction,
real settlement, safe-to-retry guarantees or action-linked causal origin.
Receipt origin therefore remains unknown. The fixed guard may suppress a
legitimate later identical request and may never activate in ordinary native
dialogue; both effects must be retained. Shared native task reward is distinct
from the wrapper's narrow field predicate. C/G agreement supports observed
conformance under shared application semantics, not algorithmic superiority.
Automated audit cannot establish human trust, rationale quality, subjective
helpfulness, authentic external source guarantees, or absence of shared author
and benchmark biases. No human participation is required or claimed.

## Editorial checks for the existing manuscript

- `conseqax-research.tex:56` says **independent observation**. Replace it with
  **separately captured observation**, matching the current Markdown source.
  Study A uses the same SQLite connection and ledger (`.tex:92`); readback is
  separate from the acknowledgement signal, not an independent source or
  trust domain.
- `.tex:38` says **Independent reference parity**. **Separately implemented
  reference parity** is more precise because the controller author and
  application transitions are shared, as already disclosed in `.tex:119`.
- Once validated native results are integrated, distinguish the existing
  **24 authored cases/12 purposive families** from the new **12 external task
  IDs**. Neither repeated timing seeds nor four arms increase the independent
  task count.
- Replace the existing future-work passage about the next external study only
  after its actually completed subset and remaining limits are known. Keep
  retained evidence, native task reward, receipt status, and any unsupported
  free-form assistant claim as distinct targets; there is no automated
  objective label for arbitrary natural-language claims in this pilot.

Source checks: `docs/native-controller-design-2026-10-21.md`,
`docs/native-external-analysis-design-2026-10-21.md`,
`docs/native-transport-development-2026-10-21.md`,
`research/native_agent/controller.py`, `harness.py`, `audit.py`, and
`transport.py`. These are development sources until the new source freeze is
committed. This note intentionally contains no pilot result numbers.
