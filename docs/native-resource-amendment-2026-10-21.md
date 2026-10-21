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
2 × 1,283,457,024 KV bytes plus 1,073,741,824 reserve bytes:
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
keeps the complete policy and all14schemas, and uses the native `tool_choice:
auto` setting. Its tool result is an explicitly artificial transport fixture,
not a saved native environment result or evaluation score. This development
fixture correction precedes all native development and official episodes.
The tested execution source must be recommitted before prospective freezing.

Cached-token accounting is specified in the
[separate source-backed note](native-token-accounting-2026-10-21.md). Complete
render/token equality stays required; cached tokens are not added twice.

## Session restart and final integration allowance

The first unmodified native development episode on excluded ID19 completed
14 model requests and five native tool calls. Independent offline replay,
initial/final DB comparison and unchanged ALL regrading passed. Its native
reward was zero: the DB target failed; its empty communication requirement
passed vacuously. This is a completed integration check, not an official pilot
score or a task-success-based readiness selection.

When work resumed later on21October, the research server and runner had stopped.
The measured native episode and all old identities remain unchanged. Development
readiness now requires identical static model/tag/binary/cache/context settings
across smoke checks, while retaining each process's distinct PID, port,
creation time and launch receipt. Those ephemeral values need not be equal
across separate development sessions. The official protocol still pins the
actual live server/runner lease and stops after a lease/integrity change.

Before any official generation, the shared excluded-task development allowance
was increased from36 to64 completion invocations to permit fresh exact-source
integration checks after the restart and accounting fixes. The first14 calls
remain consumed. IDs19/20, required native grading and no task-reward-one rule
remain unchanged. The separate task-independent allowance stays12 requests;
eight were conservatively reserved before this amendment. No official48-slot
request, step, context or time ceiling is enlarged by this development change.

An offline dependency check also found that LiteLLM1.82.6 can internally retry
certain error messages despite an explicit zero retry argument. The final
collector must independently authorize only one generation HTTP dispatch per
recorded native completion and refuse a rewritten or repeated request before
transmission. This repair precedes official collection. It does not change the
already audited first native run: its14 completion invocations and14 generation
HTTP records agree, without failures or extra attempts.
