# Native local-runtime amendment, 21 October 2026

This is a development-stage amendment before any official evaluation episode.
It does not amend a collected benchmark score. At this decision there had been
one actual task-independent generation HTTP attempt, zero returned completions,
zero executed native dialogue episodes, and zero executed native tools. The
first two-request development reservation is conservatively consumed in full;
the actual attempted-request count remains one. No human evaluation is planned.
GitHub Actions remain disabled.

The exact installed Qwen3 4B weights loaded with a 16,384-token context,
`q8_0` key/value cache and Flash Attention on the CPU. Fresh full opening,
tool-result follow-up and nested Unicode history previews matched the offline
provider-normalized rendering and every runtime token ID. These render-only
checks establish prompt preservation for their inputs, not generation ability.

The first generated structured-call fixture submitted a complete 4,563-token
prompt. The server log reported 1,024 prompt tokens in 48.54 seconds and 2,048
in 147.12 seconds (13.92 tokens/second at that boundary). The client reached its
180-second timeout before a completion returned. The original failed receipt,
request, error, allowed-HTTP record and server log are preserved. The development
smoke writer captured the gate receipts only on a successful return, so this
failed attempt's full gate response was not retained. Its preview/tokenization
HTTP hashes survive, but they do not recover those response bodies. Progressive
context-receipt capture is required before the next generated test and the
official source freeze. This retention defect is a development limitation and
must not be silently repaired in the original record. This is a transport
development failure; it is not a task failure or evidence of framework benefit.

The next candidate condition increases the per-request timeout to **600
seconds** and the parent-enforced trajectory deadline to **3,600 seconds**.
The model, digest, 16,384-token per-slot context, temperature zero, seed, maximum
512 output tokens, complete native policy/history, no retries and native
evaluation remain fixed. These time limits must apply to every arm and both
native model roles. Changing them after official collection begins is forbidden.

The separately owned research server may allocate **two q8_0 context slots**
while the research client continues to send **one model request at a time**.
The purpose is to test whether the native assistant and dynamic user can retain
their separate prompt prefixes across alternating turns. This is an inference
cache condition, not reused completion outputs, concurrent trajectories or a
change to the model policy. No cache-speed benefit is presumed before it is
measured. The cold-load conservative gate is 2,497,293,803 weight bytes plus
2 Ã— 1,283,457,024 KV bytes plus 1,073,741,824 reserve bytes:
**6,137,949,675 bytes available**. If that gate fails, retain the refusal;
do not silently reduce context, precision or the required reserve.

Two-slot startup must prove a full 16,384-token context **per slot** (not a
16,384-token total shared by two slots), the actual q8_0 K/V allocation, Flash
Attention, the same loaded manifest/model bytes, executable identities and
live prompt/token parity. The source/protocol freeze must bind the selected
actual configuration, including its slot capacity. Native concurrency remains
one. The normal Ollama service and other applications are outside this research
server change.

Only after the new resource condition, generated structured-call roundtrip,
unmodified native dialogue smoke and wrapped native dialogue smoke pass their
declared integration checks may an official prospective protocol be frozen.
Smoke integration success means a real native trajectory and native grading
returned with consistent saved artifacts; it does not require native task
reward one and does not permit task-success-based configuration selection.

## Subsequent development observations

Under the verified two-slot profile, transport attempt `001` also reached its
600-second client timeout before returning a completion. Its full gate receipt
was retained successfully. A separate budgeted attempt `002` reused 4,096 cached
prefix tokens from that same task-independent prompt and returned 47 generated
tokens. Provider usage reported the complete 4,563-token prompt, with the cached
subset separately disclosed. It is not appropriate to present this warm-prefix
latency as a cold-request cost.

Attempt `002` failed the declared structured-call check: the assistant declined
the request because the authored fixture explicitly described a synthetic
transport task, outside the native airline policy. This was a returned model
refusal, not prompt truncation or a native benchmark task failure. No tool was
executed, and the result stays failed. The next separately reserved development
fixture asks an ordinary airline account lookup using an invented user ID,
keeps the complete policy and all 14 schemas, and uses the native `tool_choice:
auto` setting. Its tool result is an explicitly artificial transport fixture,
not a saved native environment result or evaluation score. This development
fixture correction precedes all native development and official episodes.
The tested execution source must be recommitted before prospective freezing.

Cached-token accounting is specified in the
[separate source-backed note](native-token-accounting-2026-10-21.md). Complete
render/token equality stays required; cached tokens are not added twice.

## Session restart and final integration allowance

The first unmodified native development episode on excluded ID 19 completed
14 model requests and five native tool calls. Independent offline replay,
initial/final DB comparison and unchanged ALL regrading passed. Its native
reward was zero: the DB target failed; its empty communication requirement
passed vacuously. This is a completed integration check, not an official pilot
score or a task-success-based readiness selection.

When work resumed later on 21 October, the research server and runner had stopped.
The measured native episode and all old identities remain unchanged. Development
readiness now requires identical static model/tag/binary/cache/context settings
across smoke checks, while retaining each process's distinct PID, port,
creation time and launch receipt. Those ephemeral values need not be equal
across separate development sessions. The official protocol still pins the
actual live server/runner lease and stops after a lease/integrity change.

Before any official generation, the shared excluded-task development allowance
was increased from 36 to 64 completion invocations to permit fresh exact-source
integration checks after the restart and accounting fixes. The first 14 calls
remain consumed. IDs 19/20, required native grading and no task-reward-one rule
remain unchanged. The separate task-independent allowance stays12 requests;
eight were conservatively reserved before this amendment. No official 48-slot
request, step, context or time ceiling is enlarged by this development change.

An offline dependency check also found that LiteLLM1.82.6 can internally retry
certain error messages despite an explicit zero retry argument. The final
collector must independently authorize only one generation HTTP dispatch per
recorded native completion and refuse a rewritten or repeated request before
transmission. This repair precedes official collection. It does not change the
already audited first native run: its 14 completion invocations and 14 generation
HTTP records agree, without failures or extra attempts.

The fresh strict-source smoke `native-19-001` retained one returned user-model
completion and one assistant completion refused before transmission. The
provider omits `tool_calls: null` on ordinary assistant-history turns. The new
exact-history guard initially treated this absence as a changed request.
An offline comparison of all 14 retained request/wire pairs from the first
native development run confirmed the same null omission. The next source
permits only absent/null `tool_calls` on assistant messages, in addition to the
already documented absent/null content on actual tool-call turns. Non-null
calls, arguments, IDs, roles, text and ordering remain bound. The refused
attempt and its two completion invocations remain in development accounting;
it does not count as a passed integration check or an official task result.

The model runner also maintains a dynamic host-memory prompt cache. Its log
declares an 8 GiB cache limit in addition to the fixed q8 KV allocation; the cold
gate is not a guarantee about maximum later process memory. A separately
recorded read-only resource observer can retain actual research-process RSS,
CPU and system available memory without changing inference or closing other
applications. Prompt caches persist across serial trajectories. Rotating arm
order does not remove shared-host load and cache effects; wall times must be
reported descriptively rather than as isolated causal SDK overhead.

Before the first guarded development episode, its reservation is set to at
most 30 combined assistant/user completions, with the same 600-second request
and 3,600-second trajectory limits. The fresh unmodified check remains at 18.
This permits a complete wrapped conversation without imposing the earlier
18-call development cap on it. The shared 64 ceiling stays fixed: the old 14
calls plus the two-invocation serialization failure, a full 18-call fresh native
reservation and a 30-call guarded reservation fit exactly. Any released unused
allowance still requires complete terminal accounting. No guarded task result
has been seen when making this declaration, and no official ceiling changes.

## Full-history CPU timeout amendment before official collection

The fresh exact-source unmodified check `native-19-002` returned native grading
after 12 model completions and five actual tools, with no request errors.
Its native reward remains zero. The first guarded check `guarded-20-000`
retained seven invocations, six completions and one 600-second timeout. All
seven complete-history context gates passed. The timed-out prompt contained
6,871 tokens, including 1,116 uncached tokens; the runner logged 481.92 seconds
for its next 1,024-token prompt batch. No package receipt had been emitted.
This is a retained execution failure with unavailable native task reward,
not a failed semantic grade or evidence against the field predicate.

Before any official generation or protocol freeze, the next candidate uses
a **1,200-second request timeout** and a **7,200-second trajectory deadline**.
The eventual official protocol must apply these exact limits to every arm and
both model roles. Model bytes, context, precision, prompt/history preservation,
seed, output cap, request count, task selection and controller stay unchanged.
The already completed unmodified integration check used the stricter earlier
time limits; it is retained as development evidence, rather than represented
as a matched official result under the new limits.

The final guarded development attempt is `guarded-20-001`, reserving the
remaining **29** combined completions within the unchanged shared ceiling of
64: 14 earlier calls + 2 serialization-failure invocations + 12 fresh native
calls + 7 guarded-timeout invocations = 35 consumed. There is no task-reward-one
readiness rule and no change to policy based on task reward. A new timeout or
integration failure stays failed; no official trajectory has been replaced.
## Terminal follow-up recorded 22 October 2026

The final guarded development check `guarded-20-001` ended on 21 October at
17:50:14 UTC with an execution failure. Nine model invocations were dispatched;
eight returned and the ninth hit the 1,200-second request timeout. Five actual
tools completed, all reads. No mutation, package receipt, guard block, native
simulation or native reward was returned. The final prompt required 9,273 of
16,384 context tokens including the declared output allowance and margin; its
fit did not establish completion within the wall-time ceiling.

The parent did not hit its hard trajectory deadline. Its exit status was 1,
with no recorded capture/cleanup error. The settlement consumes nine requests
and releases 20 unused requests, leaving the excluded native-development total
at **44 of 64**, and the task-independent transport allowance remains exhausted.
No failure is relabeled as native reward zero. Neither guarded attempt validated
the package receipt path.

The one-shot auxiliary pipeline correctly refused to continue at 17:50:20 UTC
on the failed guarded parent receipt. It created no readiness output, published
no official protocol and collected no official pilot trajectories. No automatic
retry or resumed replacement run is authorized by this pipeline. Any new runtime
condition needs an explicit prospective record, complete failed-run retention
and unchanged planned-denominator accounting.

The separately finalized resource observer retains only its actually recorded
interval and discloses an unavailable original closing status. During the
timed-out request it observed sustained runner CPU activity and at least
2.207 GiB of sampled available system RAM. This does not identify the causal
bottleneck or rule out paging. The next benchmark integration work prepares
a public-information boundary for the pinned external fault simulator; it does
not supply a new execution result or silently replace this failed condition.
