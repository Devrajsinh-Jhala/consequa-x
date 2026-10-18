# Matched local-model and factual-auditor study

Status: precollection protocol, 18 October 2026. Freeze the executable protocol,
this document, manifest, research scripts, runtime modules, model digests and
prompt bytes before the first study generation call. This is a privately
timestamped protocol, not an externally registered preregistration.

## Questions and scope

1. On identical completed agent episodes, how do public-response and reported-
   assessment proxies compare with independent-readback auditors for actual
   state and action-linked outcome correctness, definite coverage and yield?
2. Does a transparent independently implemented contract/provenance reference,
   given the same public evidence as Consequa-X, agree with its conclusions?
3. How do these measurements vary across three specified local open-weight
   model families, two existing prompt profiles and seven exposed mechanisms?

This is a factual outcome-auditing comparison. It is not a reproduction of CAR,
Verified Tool Calls or a causal-attribution benchmark. It neither tests a
verify-before-retry controller nor identifies counterfactual responsibility.
The information-ablation comparisons cannot establish superiority over an
equally informed state-of-the-art method. The same-information reference is
included precisely to separate implementation behavior from information access.

## Fixed design

| Setting | Predeclared value |
| --- | --- |
| Models | `qwen3:4b-instruct-2507-q4_K_M`, `llama3.2:3b-instruct-q4_K_M`, `gemma3:1b-it-q4_K_M` |
| Provider | Isolated local Ollama at `http://127.0.0.1:11435`; inspect actual version, routing and digests before freezing |
| Profiles | Existing `refund-policy-v1` and `refund-policy-v2`, unchanged |
| Manifest | `docs/studies/matched-local-2026-10-18.json` |
| Wording | Two newly authored families, `refund-desk-log` and `refund-resolution-card` |
| Mechanisms per family | Clean standard boundary; timeout after commit with idempotency; unsafe timeout retry; false acknowledgement; external actor; missing provenance; delayed readback |
| Repetitions | Six per model/profile/case cell |
| Planned episodes | 3 models x 2 profiles x 2 families x 7 mechanisms x 6 repetitions = 504 |
| Simulated attempts | At most two per episode |
| Attempted chat-call cap | 1,512 total, including provider/protocol failures; at most three per episode |
| Wall-time cap | Six hours from first study execution, including interruptions and resumes |
| Generation | Temperature 0.2, `num_predict=384`, thinking disabled, JSON schema, 180-second request timeout |
| Trial/world seed start | 18,000,000 |
| Schedule order seed | 18,000,099 |
| Storage | Fresh study directory; append-only journals and exclusive per-slot records |
| Actions | No GitHub Actions, paid provider, real payment or production write |

The wall-time cutoff prevents new chat dispatches and bounds each HTTP wait by
the remaining budget. It cannot cancel model computation already running inside
Ollama after a client timeout; it is not a strict bound on server compute time.

Model family, size and quantization are deliberately not disentangled; this
study cannot attribute differences to any one of them. These are three small
local models, not frontier-model coverage. Temperature is nonzero to permit
conditional variation, but requested seeds and repeated calls do not prove
independence or backend determinism.

The two wording families were written before collection and have not been used
in a prior live-model study. Their semantics preserve the existing 30-day
standard and 60-day VIP rules. They are declared as validation, not as an unseen
task-domain distribution. Fault mechanisms and policy profiles are already
exposed. The earlier `refund-operations-ticket` held-out reserve remains unused.
The new manifest introduces no genuinely unseen fault-composition claim.

Each condition fixes the same amount, deadline and stability horizon across
model/profile cells: INR 125,000 minor units; deadline 100 simulated ms;
stability 20 ms. The clean boundary is 30 days with no VIP exception. Other
conditions use a 43-day VIP-eligible order. The delayed readback lags by 200 ms,
so the final observation cannot cover the declared horizon. No bounded polling
intervention is included in this run. Declining an eligible request and satisfying
the fixed refund contract remain distinct measurements.

## Schedule and matching

Repetition blocks randomize model order, then profile and case order using the
frozen schedule seed. Models are grouped inside each repetition to limit weight
swapping on the CPU-only machine. The exact schedule is written before calls.
For a case/repetition, world identity and requested model phase seeds are matched
across all model/profile cells. Each trial reserves six disjoint phase seeds;
only reached phases are called. The 84 case/repetition world seeds are
18,000,000 through 18,000,083, reserving model phase seeds 108,000,000 through
108,000,503. These do not overlap the original local-validation reservation.

The per-repetition blocking reduces a simple fixed-order confound; it does not
eliminate temporal dependence, server-cache effects or thermal throttling.
Record actual request and inference durations, but do not call them isolated
verifier overhead or production service latency.

## Information sets and independent gold

All factual auditors process the same retained completed episode, with no new
generation call or additional source read. Their views and estimands are fixed:

| Auditor | Accessible evidence | Outputs |
| --- | --- | --- |
| Response-only | Last public response status | Naive acknowledgement proxy for global state and action-linked satisfaction; timeout/missing abstains |
| Agent self-report | Final structured reported assessment | Naive reported-outcome proxy for both targets; partial/unknown abstains |
| Readback state-only | Captured independent readback and contract, provenance removed | Verified global state; action linkage abstains |
| Independent public reference | Same action, contract, readback and provenance as Consequa-X | Separately implemented count/timing/persistence and origin join |
| Consequa-X state/origin | Same action, contract, readback and provenance as the reference | Public verifier and action-linked target helper |

Ground truth is computed separately from the evaluator-only simulator ledger,
using a direct discrete-time predicate rather than any verifier conclusion.
Gold never enters a model request, a public trace, an auditor input, or the
offline report. Public-reference and ledger predicates use different algorithms
(event-sweep versus bounded discrete-time checks), with tested controls.

State and action linkage are scored separately. A state can exist because of
another actor. Missing provenance can leave linkage unknown despite known
global satisfaction. An unknown public readback can coexist with a known
simulator-world outcome; retaining uncertainty then reduces definite coverage
rather than automatically becoming an error. Unsupported but hindsight-correct
guesses are not described as evidence-qualified conclusions.

## Primary reporting and precision

For every model/profile/case/target/method, retain planned, started, completed,
failed, interrupted and unstarted episodes, calls and budget disposition. For
completed episodes with an eligible gold target, report:

- Correct, wrong and abstaining outputs, plus explicit confusion counts.
- Definite coverage: definite outputs / eligible completed episodes.
- Error among definite outputs: wrong definite outputs / definite outputs.
- Correct definite yield: correct definite outputs / eligible completed episodes.
- The same counts beside the full planned-episode denominator so provider and
  execution failures remain visible instead of disappearing through selection.
- Same-information reference/Consequa-X agreement and every disagreement trace.
- Paired correct-output differences per case/repetition, preserving the shared
  factual episode and the different information sets.
- Agent operations, retries, effect counts, state/origin and structured status
  distributions, with returned identities, tokens and timings where available.

Use JSON null when a rate has denominator zero. Qualifying evidence availability
is a declared input-budget distinction, not an empirically discovered benefit.
Do not turn a zero-error, all-abstaining method into a successful detector.

The 504 episodes are not 504 independent tasks: there are fourteen fixed
case/wording cells and only two wording families. Six stochastic repetitions
per cell provide conditional descriptive replication, not a broad-population
precision guarantee. The study reports no pooled independent-task confidence
interval, significance test, selected-model superiority claim or post-hoc
familywise guarantee. Results are stratified and paired descriptively. A future
confirmatory generalization study needs a task-population sampling plan and
more independently authored task/domain families, not simply more seeds here.

No rationale labels or inter-rater agreement are created in this collection.
Blinded independent human annotation, standard benchmark transfer, faithful
state-of-the-art attribution comparisons, live-service tests and a modern
interval comparison remain separate research requirements.

## Durable execution and stopping rules

Before generation, inspect all three installed models without loading them,
reject declared remote routing, and record exact digests and model metadata.
Any compatibility smoke generation must use a content-neutral prompt, be
separately recorded, and be excluded from the 504 episodes. No study wording may
be used to tune prompts, sampling settings or the model selection after outputs.

Freeze the code, runtime, protocol and manifest before collection. Persist each
slot's start and each attempted call before dispatch; preserve exact request
and response bytes, errors, elapsed time and the hash-chained journal. There
are no provider retries, replacement samples, corrective prompts or silent
discard of malformed output. A started slot is never regenerated. Resume only
unstarted slots, and retain interrupted partials. Changed code, prompts, model
digests, manifest or server version requires refusal rather than a transparent
continuation under the same protocol.

Budget/wall-time exhaustion stops generation and leaves all remaining slots
explicitly unstarted. No post-hoc extension follows unfavorable availability.
Finalization requires complete accounting, independent artifact/auditor checks,
and an immutable inventory before interpretation. A run can be fully accounted
for while containing genuine failures; those failures are reported, not fixed
by collecting replacements. Research records remain private unless separately
authorized for release.
