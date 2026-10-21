# Native pilot protocol review — 21 October 2026

This is a source and metadata review, not a benchmark result. No generation,
official episode, human labeling, or hosted judge was invoked. The review read
public implementation code and inspected only ID, required-basis and
communication-presence metadata in the official task file. Official scenarios,
reference actions and expected databases were not inspected to derive controller
behavior. GitHub Actions are outside this review and must remain disabled.

## Corrections to make before freezing

1. **B is a raw-readback controller baseline.** The analysis-design document
   currently calls B an ordinary native model agent. `controller.py` intercepts
   proposed writes in all four arms and schedules the same deterministic actual
   pre/post public reads. All four also receive `COMMON_INSTRUCTION`. B omits a
   derived verdict and a dispatch guard; it is not an untouched native-agent
   baseline. The controller-design table correctly describes its behavior.
2. **The nonempty stratum is exhaustive after development exclusions.** The
   runtime task file has 50 airline tasks, all requiring DB+COMMUNICATE. Excluding
   IDs 19 and 20 leaves six nonempty and 42 empty communication tasks. The six
   selected nonempty tasks therefore exhaust that eligible stratum. The empty
   stratum uses the six lowest declared selection hashes. Report this intentional
   imbalance and do not call the 12-task subset representative of all 50 tasks.
3. **C/G is a matched application-conformance comparator.** Both derive the same
   field arithmetic, but C presents a compact report and G a full framework
   receipt. They need not produce identical model inputs, tokens, dialogue or
   task outcomes. Record these differences rather than describing the conditions
   as byte-identical or presuming superiority over the classical controller.
4. **Counterbalance actual schedule positions.** Hash-integer modulo four need
   not allocate equal positions. A deterministic sorted task rank modulo four
   yields each arm in each position three times over 12 tasks. Freeze the exact
   task order, arm permutations and slot IDs before any official generation.

## Verified metadata-only selection

Pinned upstream commit:
`96a3ef92329baf908ffe9dfe188cea34e8701d2a`.

The actual Windows checkout file `data/tau2/domains/airline/tasks.json` is
159,049 bytes, SHA-256
`34dfcf0622792d0d0fa32aa491d21582e1b5d3ec1948e7743bae881885f878ea`.
This is its runtime-byte hash; immutable Git-byte and checkout-EOL bindings must
also be included in the source inventory.

For each eligible ID, selection uses SHA-256 of UTF-8
`consequa-native-pilot-v1|airline|<id>`, ascending within presence strata.

| Stratum | Eligible after exclusions | Selected IDs in ascending selection-hash order |
| --- | ---: | --- |
| Nonempty communication | 6 | 7, 23, 18, 11, 14, 3 |
| Empty communication | 42 | 45, 32, 39, 15, 30, 44 |

Freeze one seed and four conditions as **48 planned slots on 12 distinct task
IDs**. The selected corpus was previously exposed in model-free work. This is a
new autonomous execution condition on an exposed corpus, not an author-unseen
holdout, independent task collection or full benchmark result.

## Required prospective execution binding

The execution protocol and its machine-readable manifest should bind all of the
following before official generation:

- The committed collector, controller, transport, independent auditor and
  analysis source, with exact file inventory and immutable Git commit. Freeze
  clean actual bytes in a dedicated checkout; keep prior sealed studies intact.
- The native commit plus actual runtime and immutable Git hashes for every used
  source, policy, database and task file. Accept only exact bytes or a recorded
  pure LF-to-CRLF checkout transformation. Bind native configuration and project
  metadata too, even though the audit helper's 272-file inventory covers only
  the native package and airline data.
- Exact Python executable/version, dependency lock, installed module origins,
  the selected ConseqaX 2.1.1 wheel and payload hashes, native import origins,
  local server executable/version/hash, original/profile tag digests and weight
  blob hash. A version string or a Git-clean status alone is insufficient.
- The selected task IDs, excluded development IDs, metadata selection hashes,
  criterion-presence counts, exact 48-slot order and per-slot unique identifier.
  Repeat the required-basis check before each live task and before offline
  grading. Unexpected required components stop the run instead of invoking a
  judge or quietly changing the evaluation.
- The complete native assistant policy/tools, common recovery instruction,
  role configuration, seed, temperature, full context, cache format, local API
  endpoint, output ceiling, request timeout and disabled retries. Bind the
  successful exact server-render/tokenizer checks and memory/load condition.
  Unresolved prompt preservation or parameter behavior remains a failed gate.
- Native max steps and consecutive tool-error limit; combined assistant+user
  attempted-request cap; hard parent wall deadline; no auto review, optional NL,
  voice, cloud routing, retrieval, prompt shrinking or corrective retry. Define
  invocation attempts separately from actual HTTP generations and rendering or
  tokenization requests. Charge all inserted real tool calls against the same
  native interaction ceilings.
- Exact disposition and stop rules. Ordinary model/task failures remain slots;
  failed integrity/source/routing checks stop collection and leave remaining
  slots explicitly unstarted. No replacement, exclusion, repair-and-resume or
  silent restart is allowed under the same frozen run claim. A repaired repeat
  needs a separately versioned protocol and full preserved earlier attempt.

The parent supervisor should make an exclusive run claim and start one fresh
worker per slot. A hard deadline must stop and reap the worker and retain its
partial journals and in-flight dispatch records. Do not treat a deadline flag
checked only between native turns as a hard deadline. Never include credentials
or secret environment-variable values in runtime receipts.

## Required retained artifacts and independent checks

Retain full native model requests and responses for assistant and dynamic user,
usage including unavailable usage, controller events, native trajectories,
evaluation results, source/configuration checks, tool-dispatch starts and
terminals, initial/final evaluator-only snapshots and hashes, standard output,
errors, and a terminal supervisor disposition for every planned slot. Initial
state/history belongs to a separate phase and is applied exactly once. Keep the
official user scenario and gold criteria out of assistant/compiler inputs; they
remain native-user/evaluator material.

At finalization, inventory exact relative filenames, bytes and SHA-256 hashes
without overwriting raw artifacts. Record collection start/end, all 48 slots,
attempted/completed/failed/unstarted counts, process exits, timeouts, pending tool
calls, generation counts and immutable protocol/source identities. An incomplete
collection still receives a truthful partial terminal receipt. Do not copy a
partial source manifest under a self-contained `manifest.json` filename.

`audit.py` provides offline native initialization, full chronological read/write
replay and unchanged ALL strict regrading. The caller must first verify the
prospective manifest, full file inventory and source bindings. The auditor
deliberately does not import the research controller, model transport, collector
or ConseqaX. It must run in a fresh process with network refused and inspect
saved data only. Native strict replay skips nonmutating and unknown tools;
therefore its success cannot substitute for the chronological call replay.

The tool observer records before/after `make_tool_call`, before outer
success-only `sync_tools`. This is appropriate for the pinned airline
environment, where synchronization is a no-op, but the boundary must be named.
Raised exceptions and returned error objects remain distinct. A journaled tool
dispatch with no final transcript result after interruption is evidence of a
partial execution, not a successful completed call. Current complete-simulation
audit rejects a denominator mismatch; do not manufacture a tool result or native
simulation to force it through. Such slots need preserved partial diagnostics
and unavailable semantic reward unless the native evaluator returned one.

Completed native simulations must preserve native termination and reward even
when premature termination gives reward zero with unavailable components.
Harness errors and unstarted slots have operational success zero, but no
invented native reward object. Normal native airline grading evaluates required
DB and communication checks; empty communication checks are vacuous, not
substantive language validation. Additional action diagnostics are not reward.

## Interpretation limits to retain in the paper

Report all-slot operational success, exact native reward/component availability,
both communication strata, per-task arm contrasts, actual tool and model costs,
unknown receipt origin, guard blocks, repeated payloads and observed database
changes. Present current-field status separately from full native task reward.
Do not equate duplicate requests with unwanted harm, field match with policy
compliance, or a synchronous post-return read with causal provenance, settlement,
durability, deadline satisfaction or safe retry. The fixed guard can block a
legitimate later identical intent, and no natural repeat proposals may occur.

Do not assign semantic unsupported-claim labels from prose keywords or an
undeclared AI judge. No unrestricted prose-accuracy endpoint is implemented.
No population significance, broad generalization, human validation, formal
novelty or top-conference-readiness claim follows from this small local-model
pilot. Null or negative outcomes are valid paper findings.

## Collector review and synthetic protocol checks

The first review of `scripts/run_native_external_benchmark.py` identified the
following execution-integrity requirements before its freeze/collect phases may
run. This is a review list, not a claim that these checks have passed:

- Verify the original protocol receipt's canonical and file SHA-256 bindings
  before using its schedule. Recomputing a digest from a modified protocol at
  collection time does not authenticate the original prospective freeze.
- Verify the frozen server-launch/readiness bindings. Confirm actual cache and
  flash-attention configuration from the loaded research process, not only a
  tag's weight digest and context size. Bind and verify actual weight bytes,
  server/runner executable bytes, process identity and listener ownership.
- Derive or enforce every worker ceiling from the verified protocol; direct
  worker arguments must not bypass official bounds. Distinguish fatal
  source/runtime/routing-integrity errors from ordinary model/task failures so
  the collector stops remaining slots on an integrity error.
- Enforce the shared development request budgets across retained attempts, not
  merely a per-process ceiling that resets with every invocation. A new
  development allowance requires a dated amendment before extra calls.
- Require readiness evidence for complete-prompt structured-call/follow-up
  compatibility and native plus wrapped development smoke, binding exact tested
  source/configuration and raw artifact inventories. A standalone truthy
  `passed` field is insufficient.
- Finalize truthfully on worker launch errors, interrupted waits and cleanup
  errors. Reap any live worker and retain the partial all-slot matrix. Merely
  observing that a simulation file exists is not proof that a native reward
  object is available; report parsed availability or use a narrower label.

`tests/test_native_protocol.py` contains 24 synthetic tests. They initially
exposed 12 missing checks: malformed communication-presence types, malformed
selected-task denominators, unbound nested manifest files, unchecked declared
file sizes and noncanonical inventory paths. After root's implementation
corrections, all 24 passed locally in 0.45 seconds. The tests also check exact
arm-position balance, paired schedule completeness, deterministic metadata-only
selection and exclusions, required-judge refusal, Git/CRLF source identity, and
framework wheel/version/payload identity. They read no official task definitions
and invoke no generation, native environment or network. These tests do not
substitute for the live readiness gates or collected-artifact audit.

The follow-up independent CLI is
[`audit_native_external_benchmark.py`](../scripts/audit_native_external_benchmark.py).
It accepts an explicit immutable protocol Git commit, verifies the full saved
inventory and frozen source/runtime/native bindings, then performs offline
native initialization, chronological call replay and unchanged required
regrading. It imports neither the collector, controller, model transport nor
framework. It requires execution from the frozen source checkout and rejects
those modules if already imported. It preserves all 48 planned dispositions,
operational zeros versus unavailable native rewards, required-component
availability, both communication strata, per-task pairings and saved cost
observations. Receipt statuses remain declared JSON observations, not an
unimplemented semantic prose-accuracy endpoint.

The final targeted check in this review passed **39 synthetic tests** (29
protocol tests and ten independent-CLI tests) in 1.28 seconds, with Ruff clean.
These additional tests cover an edited protocol with a locally rehashed receipt
still failing the immutable Git anchor, malformed JSONL prefixes, partial
request/token availability, all-slot denominators, native mutation flags,
receipt-declaration scope, complete generation/context accounting and refusal
before native imports when the collection manifest is invalid. No actual
collection or native model execution was performed for these checks.
