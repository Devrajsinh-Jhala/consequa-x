# Prospective native autonomous validation — 20 October 2026

Status: feasibility assessment and proposed protocol, not executed agent results.
No model generation, model download, paid call, service/configuration change,
source-package edit, staging, commit, or publication was performed. This assessment
did not inspect `heldout_cases.json` or partial recovery-study outputs. It used
public benchmark source, the existing state-transfer protocol/runner, dependency
metadata, and a network-blocked native import probe.

## Recommendation

Build a separate, serial research harness around the **unchanged native text
agent, native dynamic user simulator, native tools, and native required reward**.
First attempt a 12-task **airline-only autonomous pilot** after offline dependency
and tool-call compatibility checks. Airline requires DB and COMMUNICATE, both
available without an LLM judge. This would be a complete required-criteria
evaluation of a declared 12-task subset, not a complete benchmark or leaderboard
result. Do not replace autonomous dialogue with reference-action replay.

A 12-task mixed retail/airline pilot is the next stage, but **all three roles
(assistant, user, required retail judge) cannot currently be configured to local
Ollama solely through the pinned runner's public settings**. Assistant and user
can; the required retail NL judge cannot. Its model and arguments are imported
module constants. A mixed full-required-criteria pilot needs a small, explicit,
versioned evaluator-configuration adaptation, or later upstream support. Until
that exists and is validated, report retail DB/communication diagnostics as
components only. Do not call them a full retail evaluation.

There is no demonstrated tool-call compatibility, memory fit, latency, task
success, judge validity, effect size, or acceptance probability yet. With 16 GB
RAM and about 4 GB free, serial execution of the one installed model is the only
proposed mode; even that needs a measured resource preflight.

## Source identity and what already exists

The cached maintained checkout is
`C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit`, HEAD
`96a3ef92329baf908ffe9dfe188cea34e8701d2a`, tracked source clean at inspection.
The repository is branded tau3-bench but its distribution remains `tau2` 1.0.1.
Its [project metadata](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/pyproject.toml#L5-L35)
requires Python `>=3.12,<3.14` and LiteLLM `>=1.80.15,<1.82.7`.

The existing [state-transfer design](D:/ConsequaX-Research/paper-writing/docs/tau-benchmark-validation.md)
and [runner](D:/ConsequaX-Research/paper-writing/scripts/run_tau_benchmark_validation.py:1)
explicitly measure model-free state transfer. Their 164 tasks / 656 controlled
replays are not autonomous trajectories or independently sampled agents.
`payload_contract` takes only the intended tool payload and public preflight
readback (runner lines 279–284); `TauRecordVerifier` checks requested record
fields and preserves unknown origin (392–419). Those pieces can inform a new
adapter, but `execute_case`, the reference-action schedule, fabricated controls,
and the hard-coded illustrative times in `audit_capture` (422–429) cannot serve
as the new autonomous experiment. Freeze a new protocol and output location;
never modify or append to the sealed state-transfer or recovery experiments.

## Actual public interfaces and scoring

| Role/component | Evidence in this exact revision | Consequence |
| --- | --- | --- |
| Assistant and user provider routing | [CLI settings, lines 74–103](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/cli.py#L74-L103); [LLMAgent, 127–134](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/agent/llm_agent.py#L127-L134); [user generation, 232–240](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/user/user_simulator.py#L232-L240) | Arbitrary model strings and kwargs reach LiteLLM. Use the installed tag as `ollama_chat/qwen3:4b-instruct-2507-q4_K_M` with explicit loopback `api_base`. This is a candidate route, not a successful compatibility test. |
| Native tool transport | [generate, 430–483](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/utils/llm_utils.py#L430-L483) | Sends native OpenAI-style tool schemas and `tool_choice=auto`; expects structured `message.tool_calls` and JSON arguments. Prose describing a call is not a tool call. |
| Retail judge routing | [config, 24–26](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/config.py#L24-L26); [NL evaluator, 8 and 121–135](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/evaluator/evaluator_nl_assertions.py#L121-L135) | Fixed `gpt-4.1-2025-04-14`; no judge model/kwargs argument to `calculate_reward` or the runner. `--review-model` controls optional conversation review, not required NL grading. |
| Required reward | [evaluator, 196–256](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/evaluator/evaluator.py#L196-L256) | `ALL` evaluates required NL when in `reward_basis` and multiplies only the task's required components. Action-reference similarity is diagnostic, not task success. |
| Runner default | [run_tasks, 872–880](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/runner/batch.py#L872-L880); [run_domain, 1110–1117](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/runner/batch.py#L1110-L1117) | Actual source defaults to `ALL`. The pinned evaluation document's line 148 claim that the CLI forces `ALL_WITH_NL_ASSERTIONS` disagrees with source. Set `EvaluationType.ALL` explicitly in the new Python harness. |
| Native DB and communication | [DB evaluator, 85–129](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/evaluator/evaluator_env.py#L85-L129); [communication, 27–41 and 61–85](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/evaluator/evaluator_communicate.py#L61-L85) | Fresh replay of actual native calls must match the gold final DB; communication checks required substrings. Preserve strict replay. Never manufacture a successful native write from an acknowledgement. |

Metadata-only inspection of pinned `data/tau2/domains/{retail,airline}/tasks.json`
found: retail 114 tasks, 112 with basis DB+NL_ASSERTION and two DB-only; 43 retail
tasks have nonempty NL assertions. Airline has 50 DB+COMMUNICATE tasks, seven with
nonempty `communicate_info`. Airline also contains experimental NL assertions,
but they are outside its required reward basis. Empty criteria use the native
vacuous result; record them as empty rather than claiming substantive language
or communication validation.

The native [LLMAgent factory, 489–504](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/agent/llm_agent.py#L489-L504)
does not consume the task supplied to the factory. Use `llm_agent`, never
`llm_agent_gt` (which reads evaluation actions) or a solo/ticket agent. Native
[build_user, 157–177](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/runner/build.py#L157-L177)
passes the official user scenario to the user simulator. Keep that privileged
scenario out of assistant/controller inputs. The native evaluator may read gold
after the episode; the agent and contract compiler may not.

For Stage A, the complete native reward path is `TextRunConfig` with
`llm_agent`/`user_simulator`, `build_text_orchestrator` (native domain environment,
agent and user), then `run_simulation(..., evaluation_type=EvaluationType.ALL)`,
then `evaluate_simulation`. Normal termination invokes EnvironmentEvaluator,
ActionEvaluator diagnostics, and CommunicateEvaluator; only DB and COMMUNICATE
multiply into airline task reward. NL is not invoked under `ALL` for these
airline bases. [Simulation execution, 58–85](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/runner/simulation.py#L58-L85)
calls that unchanged evaluation path. Retain every component result, original
task `reward_basis`, termination reason, and strict-replay disposition.

## Missing environment and exact next checks

The DB-only target `D:/ConsequaX-Research/tau-native-dependencies` is insufficient
for native autonomous imports. A bytecode-disabled, dotenv-disabled import with
sockets blocked stopped at `llm_utils.py:14`, `ModuleNotFoundError: litellm`.
It made no generation request. The available base Python is 3.12.10, whereas the
prior state-transfer freeze recorded 3.12.14; do not silently reuse that runtime
identity. Combined base/target metadata also lacks declared `psutil` and the
usual LiteLLM OpenAI/tiktoken dependencies. The DB target alone lacks many more
declared runner dependencies. Inventory is not an installed working environment.

Next implementation work, in order:

1. Create a dedicated native-agent research environment using Python 3.12 or
   3.13. Resolve and pin every declared base dependency and transitive package,
   particularly the permitted LiteLLM range, without changing ConsequaX or the
   sealed DB-only target. Record interpreter path/hash and complete lock.
2. Repeat the no-network import check with normal `tau2` initializers. The
   existing namespace bypass is evidence only for DB-component integration.
   Native runner imports pull voice-related facades even in text mode
   (`tau2/__init__.py:13`; `registry.py:7–9`; audio agent lines 80–82; OpenAI
   audio initializer lines 5–32). Install only demonstrated import dependencies
   in the isolated environment; do not assume installing the base list fixes
   every eager-import problem. No audio provider needs to execute.
3. Check the installed Ollama version, exact model digest, quantization,
   advertised capabilities, context configuration, and free RAM using metadata
   requests only. Record these afresh. Do not pull or substitute a model.
4. After a new execution authorization, use at most 12 **development-only**
   local requests to exercise native prompt+schema generation, a native read
   tool call, follow-up after a ToolMessage, ordinary user dialogue, stop
   behavior, and the JSON judge format on disclosed toy assertions. Use prior
   adapter-development tasks retail:0 / airline:19,20 only for end-to-end smoke;
   these are excluded from the proposed pilot. Allow at most 36 additional
   attempted requests across those three smoke episodes, for 48 development
   requests total; never consume evaluation IDs while tuning. Stop on malformed
   calls, silent emulation, prompt/context truncation, OOM, or unresolved API
   parameters. Freeze the actual working transport and prompts after smoke.

Current [LiteLLM Ollama documentation](https://docs.litellm.ai/docs/providers/ollama)
describes `ollama_chat`, `api_base`, and native tools, but also warns that unknown
tool support may fall back to JSON-mode emulation. The
[Ollama tool-calling documentation](https://docs.ollama.com/capabilities/tool-calling)
defines structured calls and follow-up tool messages. These primary docs were
checked on 20 October 2026; they do not establish behavior for the as-yet
uninstalled permitted LiteLLM version and exact local quantization. Disable or
refuse emulated tool calls for a claim of native tool calling. Do not rewrite
the upstream instruction to accommodate a model until a separately versioned
prompt-adapted condition is declared.

## Prospective 12-ID pilot and matched conditions

Selection uses only public ID and criterion-presence metadata, never model
outcomes or reference actions. Exclude the three disclosed development IDs.
Within each declared stratum, sort ascending SHA-256 of UTF-8
`consequa-native-pilot-v1|<domain>|<task-id>`. Preserve the task bytes and original
native initialization. Seal source hashes and the selected manifest before any
evaluation generation.

| Stage | Proposed distinct official tasks | Scope |
| --- | --- | --- |
| A: first executable pilot | Airline nonempty COMMUNICATE: `7,23,18,11,14,3`; airline empty COMMUNICATE: `45,32,39,15,30,44` | 12 distinct domain-qualified IDs; all native required DB+COMMUNICATE criteria. No required LLM judge. |
| B: mixed pilot, only after judge configuration is resolved | Retail nonempty NL: `44,76,109`; retail empty NL: `74,50,52`; airline nonempty COMMUNICATE: `7,23,18`; airline empty COMMUNICATE: `45,32,39` | 12 distinct IDs, six per domain. All required criteria only if the three nonempty retail NL tasks are actually graded. |

Stage B reuses six Stage A airline IDs if both stages run. Do not sum them into
24 independent tasks: their union has 18. These are exploratory, deliberately
stratified subsets with prior public/model-free exposure, not a hidden holdout or
a representative corpus success estimate. Twelve unique tasks meet the minimum
independent-ID target; repetitions, seeds, arms, and call attempts do not increase
that number. Shared domain/task families may still create dependence.

Three arms provide the smallest useful receipt/guard ablation:

- **B, matched baseline:** native LLMAgent + native user; raw public preflight
  and post-write readbacks, with a plain recovery instruction.
- **R, receipt:** the same model, native information and reads, plus ConsequaX
  outcome/origin receipt computed from those observations.
- **G, receipt + guard:** R plus a fixed controller that may prevent an unsafe
  repeated mutation or request clarification from the native user. It must not
  decide the desired task outcome from gold actions or hidden task text.

All arms use the same native provider semantics, initialization, full policy,
tools, user scenario/persona, model digest, temperature, requested seeds, context
capacity, step/tool/token/time budget, raw observations and readback schedule.
Readbacks must be executed and recorded as actual native read calls in every
arm, not privileged DB access or free information for the framework. The only
added semantic information is R/G's derived interpretation of identical facts.
Charge all extra reads and context tokens to the shared budget. A separate
unmodified-runner smoke establishes native integration; B is already a matched
research comparator because of the shared readback schedule.

Register the research wrapper via the public agent-factory interface
([registry, 106–134](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/registry.py#L106-L134)).
Keep native environment bodies and required evaluator bodies intact. The wrapper
may propose/withhold a call or add an agent-visible receipt; the immutable native
trajectory must contain only actually dispatched calls and their real native
results. A suppressed call is a controller event, not a fake tool success. Run
strict native replay and verify readbacks do not change DB hashes. Preserve the
full model-visible receipt/prompt transcript alongside the native trajectory.
This is an augmented autonomous harness, not an assertion that the CLI alone
implements ConsequaX.

Use one requested seed per task per arm initially; deterministic generation is
not promised. Counterbalance B/R/G order by fixed hash-derived task schedule and
reset the environment/user/agent for every arm. Dialogue may legitimately diverge
after an intervention; match user policy and initial seed, not a replayed user
transcript. No corrective reruns, replacement tasks, outcome-based exclusions,
or configuration changes after evaluation begins.

Candidate conservative caps to confirm in development and then freeze: serial
execution, one trial, 80 native steps, 5 consecutive native tool errors, 48 total
attempted assistant+user requests per trajectory, 512 generated tokens per
request, 180-second request timeout and 20-minute episode wall-clock ceiling.
Set both runner-level task retries and LiteLLM `num_retries` explicitly to zero;
the pinned defaults otherwise retry (`simulation.py:432–438`, `llm_utils.py:379–380`).
Set `auto_review=False`, `hallucination_retries=0`, no live/voice/retrieval mode,
and explicit local endpoint allowlisting. A hard external supervisor is needed
because the native timeout is checked between steps; it does not reliably cancel
an in-flight blocking request. Context capacity must fit the complete native
policy, tools, and accumulated dialogue; do not silently truncate or summarize.
The future network guard must cover imports and generation, allow only the
existing loopback Ollama listener, disable dotenv credential loading, and reject
provider fallback, remote model/metadata retrieval, and any attempted hosted
judge call. Record a rejected call as a failure. No paid-service key or proxy is
needed; do not introduce one or change Ollama services/configuration.

One stage is 12 tasks × 3 arms = 36 trajectories, with at most 1,728 attempted
dialogue requests under this candidate cap, plus separately logged smoke. This
is an upper limit, not an estimated runtime. Stage B additionally needs nine
judge requests (three nonempty retail tasks × three arms), with no judge retries.
Resource failures and unstarted slots stay in the disposition table. Native
premature terminations receive reward zero before component grading
([evaluator, 119–129](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/evaluator/evaluator.py#L119-L129));
record missing component grades as unavailable, never implicitly passed.

## Action identity, terminal assumptions, and limits

Freeze a stable logical operation key from episode/domain, actor identity,
user-confirmed intent epoch, native tool name, and canonical payload. Retries of
that logical operation retain the key; each transport/model proposal gets a new
attempt ID. A distinct user-confirmed new operation gets a distinct epoch even
if its payload repeats. Never let a fresh random native tool-call ID alone reset
duplicate detection. Log the key derivation before dispatch and do not put the
key into unsupported native tool arguments. Registration defines the proposed
action, not proof that it implements the user's true goal; native grading checks
task success independently of the payload contract.
Changing payload or intent while an earlier operation remains unresolved must
not clear that operation's key or pending state; require an explicit, logged
intent revision and preserve the unresolved predecessor.

The benchmark's in-process calls return after synchronous execution and
`sync_tools` ([environment, 465–490](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/src/tau2/environment/environment.py#L465-L490)).
For this native-only pilot, a post-return read of that instance can witness
current simulator fields under a declared single-threaded ordering. It does not
prove real-world settlement, an asynchronous commit deadline, action-linked
provenance, or durability beyond the simulation. If the wrapper cannot establish
dispatch completion, retain unknown and do not infer terminal failure from an
empty read. Missing, partial, stale, or out-of-scope reads must remain unknown.
Keep action origin unknown when the native provider supplies no provenance.

Do not add framework-only provider deduplication. Native booking allocates another
reservation ID on another call (airline tools 76–89); certificates allocate another
payment entry (488–514). Cancellation reverses payment history and explicitly
does not release seats (339–367). A stable audit key is not native idempotency.
Log all writes, payment-history changes, new bookings/certificates, rejected
duplicates, unresolved operations and guard blocks in an evaluator-only ledger;
never expose that privileged ledger to a policy. A finite pilot does not certify
all financial side effects.

Do not inject lost acknowledgements or delayed commits in the first native pilot:
they are not supplied by this synchronous environment. A later fault-wrapper
extension must be preregistered separately and preserve both actual native
results and agent-visible faulted receipts; it cannot masquerade as an unchanged
official trajectory or quietly relax strict replay. With no retry-triggering
events, guard inactivity or no improvement is a valid possible result.

## Retail judge adaptation and reporting gate

Do not route the fixed GPT model name through a hidden alias/proxy or silently
rename the local model. An OpenAI-compatible endpoint alone does not change the
judge's requested model. The smallest later adaptation is an external, hashed
research bootstrap that explicitly sets the NL evaluator module's imported
model/argument constants to the named local Ollama model before evaluation. It
leaves the evaluator method body unchanged but is **runtime configuration
adaptation through a nonpublic interface**, not a supported runner option.
Disclose it and retain original/module/runtime identities. No such adaptation
was made during this assessment.

Validate judge coverage separately: the native parser accepts a `results` array
without checking that every requested assertion appears, and `all([])` passes
(NL evaluator lines 46–52, 127–135). Require exactly one well-typed result per
input assertion, with no omissions, duplicates or extras; malformed/incomplete
grading is unavailable, not a pass. Preserve native raw output and the external
coverage gate. Do not improve scores by retrying an invalid judge. Using the
same 4B model as assistant, user and judge is not independent validation of
qualitative truth. A later blinded human audit should assess judge/user validity;
none has occurred here.

Primary reporting is the paired task-level native required reward, component
grades, unresolved/failure disposition, and raw side-effect/read/model-call costs
for all scheduled arms. Separately report unsupported success claims, duplicate
mutations, guard blocks and receipt unknowns. Preserve disagreements between
native reward and field-contract satisfaction: neither defines the other.
With 12 IDs, present the paired table and descriptive differences; do not claim
population superiority, judge reliability, or recovery effectiveness from a small
pilot. The honest immediate deliverable is a dependency-locked harness plus a
successful native smoke, followed by Stage A only if those checks succeed.
