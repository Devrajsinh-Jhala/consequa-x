# Native transport preflight — 20 October 2026

**Disposition: autonomous pilot not started. Zero model generation attempts.**
This folder records task-independent transport inspection and an isolated local
context-profile configuration. It contains no autonomous benchmark results or
official evaluation task scenarios, IDs, gold actions, or expected databases.
The existing metadata inspection, both failed original routing candidates, and
the subsequently created profile remain separate development conditions.

## What was verified

- Ollama metadata identifies version 0.40.6 and the installed
  `qwen3:4b-instruct-2507-q4_K_M`, digest
  `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`.
  Advertised tool support is metadata, not a successful emitted call.
- The untouched native Tau message converter and installed LiteLLM 1.82.6
  construct a local OpenAI-compatible request preserving prior assistant tool
  calls, function arguments, call IDs, tool-result association, and native
  schemas. The HTTP request was intercepted and refused before dispatch.
- Direct invocation of the unchanged LiteLLM Ollama chat transformer drops the
  prior assistant tool calls and the tool-result ID. It preserves the schema
  and `num_ctx`. The native Ollama route therefore fails the history gate.
- A previously absent, separate tag
  `conseqax-native-probe-20261020:ctx16k` was created from the already installed
  exact weights with `num_ctx=16384`. Its digest is
  `7f091551b95c30f4ff31a067faa273f56a3563b556cfd3d9f80d47c9b5d20ffc`.
  Original tag digest and complete show metadata remained unchanged; the
  generated profiles reference the same weight blob and architecture metadata.
  Creation did not load the new tag. No model download, weight change, original
  model/profile edit, or service-global edit was requested.

The [official Ollama compatibility documentation](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size)
was checked on 20 October 2026: `/v1` has no request-level context-size setting.
The `options.num_ctx` extension captured in the original candidate was therefore
not treated as an accepted server setting. The separate local profile supplies
an explicit recorded configuration, subject to later loaded-state validation.

## Why generation was withheld

The declared conservative memory gate required 5,986,954,731 available bytes:
2,497,293,803 bytes model size + 2,415,919,104 bytes estimated fp16 KV cache at
16k + 1 GiB scratch/OS headroom. Only 4,024,180,736 bytes were available at the
gate. KV estimation uses installed architecture metadata (36 layers, eight KV
heads, 128 head dimensions, K and V, two bytes per element). This is not an OOM
measurement or an assertion about the unknown active cache type. No source or
service settings were altered to fit memory, and no model was loaded.

The complete native airline policy and its 14 native tool schemas were sized
without official task files or tool execution: 8,033 system-prompt bytes,
10,505 schema bytes, 18,872 bytes for the combined serialized input with a
synthetic opening. These are UTF-8 byte lengths, **not token counts**. Exact
installed-Qwen3 prompt tokens, context fit, and dialogue headroom remain
unverified. A smaller context was not substituted on an estimate.

The generation-attempt allowance was at most 12; attempted 0, unused budget 12.
This is a ceiling, not 12 planned evaluation slots. No toy generation, native
read call, model-generated user dialogue, or benchmark episode took place.

## Retained inspection failures

`probe-wire-no-dispatch.py` calls the unchanged native `generate` only as far as
request construction, with all socket connections and HTTP dispatch refused.
Its first Ollama request was a model-metadata `/api/show` request; it must not
be described as a captured chat wire. The OpenAI-compatible request did reach
the final chat-completions send boundary and is retained in `wire-capture.json`.
No provider response, successful or otherwise, was fabricated.

The overall wire-inspection guard result is **failed** because it recorded a
blocked socket connection, whose destination was not recorded by that first
guard. The retained log additionally shows a refused asyncio cleanup
socketpair connection after result serialization. All sockets were refused;
this record is not a successful loopback-only generation preflight. The later
`probe-offline-transform.py` resolves the actual Ollama body without network
access and records zero network attempts. The upstream tracked checkout was
clean after both inspections. Failed records were retained unchanged.

## Files

| File | Meaning |
| --- | --- |
| `metadata.json`, `metadata-journal.jsonl` | Initial read-only local metadata requests, retained unchanged |
| `probe-wire-no-dispatch.py`, `wire-capture.json`, `wire-capture.log` | Failed full request-construction guard, with original candidates and no dispatch |
| `probe-offline-transform.py`, `offline-transform.json`, `offline-transform.log` | Direct installed transformer body and complete native policy/schema size inspection |
| `configure-context-tag.py`, `context-tag-started.json`, `context-tag-config.json`, `context-tag-config.log` | Exclusive profile-creation claim, exact API requests/responses, original/new identities, and failed memory gate |
| `generation-disposition.json` | Aggregate development-attempt count and unpassed gates |
| `transport-manifest.json`, `transport-manifest.sha256.json` | SHA-256 file inventory, excluding the manifest and its detached checksum |

The isolated environment and normal native import preflight are recorded in the
[dependency preflight](../native-agent-preflight-2026-10-20/README.md). The
[prospective autonomous design](../../docs/native-agent-validation-design-2026-10-20.md)
separates these checks from a future native airline required-reward pilot.

Before such a pilot, demonstrate sufficient measured memory, exact complete
prompt/context checks, model-emitted native structured calls and follow-up,
then native assistant/user smoke. The network guard must distinguish narrowly
scoped process-internal event-loop wakeups from provider traffic without
permitting arbitrary sockets. No Actions, upstream package edits, official
task episodes, staging, or publication occurred in this subtask.
