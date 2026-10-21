# Native local transport development — 21 October 2026

This is task-independent integration work for the pinned native Tau text agent,
not a benchmark result. No official cases or expected outcomes were inspected
for these transport checks. Render/tokenization checks do not generate; the
separate authorized development generation and its failure are identified
below. Historical sealed preflight outputs remain unchanged.

The external bootstrap is `research/native_agent/transport.py`. It preserves
the native `LLMAgent`, `UserSimulator`, `generate`, message conversion, HTTP tool
schemas and model-response parser. The provider normalizes the schema before
rendering, as described below. No upstream file or installed provider
package is edited. The model route is explicitly local OpenAI compatibility
through LiteLLM 1.82.6, using the separate existing Qwen context-profile tag.
Its dummy API-key value is not a paid-service credential.

## Child initialization and request gate

Initialize a fresh supervised Python research child in this order:

1. Load this standard-library-only bootstrap and verify the frozen source
   identities. Call `configure_local_environment(native_root / "data")` to
   remove provider credentials and proxy routing by variable name, disable
   dotenv, telemetry, remote cost metadata, and Hugging Face downloads.
2. Enter `LocalOnlyGuard(protected_roots=[native_root, model_root],
   allow_render_only=True, allow_generation=False)` before any native import.
   Call `guard.attach_httpx()`; importing httpx itself is guarded.
3. Build an exact vocabulary encoder with `read_gguf_metadata(blob)` and
   `tokenizer_from_gguf(metadata)`. These read 5,933,090 metadata bytes of the
   installed GGUF, not its tensors, and do not load a model runtime. The
   Qwen2 BPE vocabulary, merges and special-token IDs come from that exact
   installed model, rather than a different model's tokenizer or a byte estimate.
4. After a successful conservative memory gate, a separately authorized
   `_debug_render_only: true` request may load the isolated research tag and
   return the actual server-rendered prompt without generation. Capture its
   loaded profile and discover the corresponding `llama-server.exe` PID,
   command line, binary hash, port, exact model blob, and context capacity.
5. Bind only that private runner's `POST /tokenize` via
   `guard.register_tokenizer_runner(...)`. Confirm the offline full rendered
   prompt equals the server preview byte for byte, and confirm every tokenizer
   token ID against the running model. No private completion endpoint is allowed.
6. For an authorized generation phase, instantiate
   `gate = ServerContextGate(guard, metadata, tokenizer, on_receipt=logger)`;
   assign `guard.before_generation = gate`; then set
   `guard.allow_generation = True`. Every actual outgoing native HTTP chat body
   is previewed with only `_debug_render_only` added, checked for full-history
   byte equality, tokenized by the bound runtime, and tested against its context
   budget before the original unmodified request can be sent. The gate itself
   never generates. It records preview, token IDs, profile, identity and counts.

`local_model_kwargs()` fixes local endpoint, temperature zero, no retries,
and at most 512 output tokens. The caller must also enforce its request-count
and wall-clock budgets and preserve actual finish reasons and failures.
The first actual completion's `prompt_eval_count` must be compared with the
preflight count; a disagreement is a gate failure, not an invitation to trim
history or replace the episode.

## Guard boundary and native transport semantics

Only the selected numeric loopback listener is generally permitted:
`127.0.0.1:11434` by default, or the explicitly selected research server
`127.0.0.1:11436`. Selecting the research listener does not also permit the
normal listener. All other destinations,
DNS, UDP, imported subprocesses, dotenv/credential reads, writes to protected
native/model roots, other model names, download/create/admin paths, multiple
completions, and streaming are refused. Python's own standard-library
`socketpair` connection is permitted only inside its thread-local construction
scope, so asyncio can create and clean up its internal wake-up channel. An
explicit bound private-port exception permits only `POST /tokenize`.
Refusals inherit from `BaseException` so provider retry handling cannot swallow
them. This is defense in depth for trusted Python code, not an OS firewall or a
sandbox for hostile native extensions. The local Ollama service's own network
behavior is not contained by a Python child hook; model/profile identity must
therefore be verified local before requests.

Native wire checking permits one documented serialization equivalence: the
OpenAI client omits `content: null` on an assistant turn carrying tool calls.
All roles, ordered messages, non-null content, tool-call IDs/names/arguments,
tool-result association and tool schemas must otherwise match. The original
strict-equality prechecks that identified this harmless omission are retained
as failures, not rewritten as successes.

The installed Ollama 0.40.6 OpenAI request schema supports the explicit debug
render extension, but does not support `truncate` as a public OpenAI field.
Consequently no assertion is made that `extra_body.truncate=false` disables
server truncation. Instead the gate demands byte equality with the complete
offline prompt; server removal of any history causes refusal before generation.
Its renderer and tokenizer checks must pass under the exact runtime rather
than being inferred from documentation. Source references are the pinned
[OpenAI request conversion](https://github.com/ollama/ollama/blob/v0.40.6/openai/openai.go)
and [native prompt processing](https://github.com/ollama/ollama/blob/v0.40.6/server/prompt.go).

## Provider schema normalization and exact rendering

The initial live debug-only check loaded the exact Qwen model on an isolated
CPU runner with a 16,384-token context and requested `q8_0` KV cache. Both
server prompts differed from the original offline rendering by 299 tokens.
This failed parity check is retained unchanged in
`isolated-q8-render-result.json`; its recorded `passed: false` remains correct
for the renderer used at that time. The check dispatched no generation.

The difference was traced to the pinned provider's
[typed tool schemas](https://github.com/ollama/ollama/blob/v0.40.6/api/types.go).
`ToolFunctionParameters` and `ToolProperty` serialize in Go declaration order,
ordered property maps retain insertion order, and arbitrary `$defs`/`items`
maps serialize in key order. Typed nodes omit `title`, while arbitrary nested
JSON retains it. All 14 captured tool schemas are equal after removing only
`title` annotations; the policy/history before and after the tool block are
already byte-identical. There is no evidence of history truncation in these
two retained checks. This statement does not establish behavior for future
requests without their individual checks.

`ollama_tools_for_render()` now predicts that exact provider representation
offline. It never changes the native HTTP body. Unknown keywords at typed
schema nodes other than `title` cause refusal rather than silently allowing
the provider to discard a constraint. Empty `enum`/`anyOf` constraints are
also refused because provider omission would change their meaning.
Arbitrary `$defs` and `items` preserve every keyword. The actual model prompt
therefore contains provider-normalized schemas, not byte-identical original
schema JSON. All four comparison arms use this same disclosed condition.

The offline predictor also mirrors the provider's parsing of prior assistant
tool-call argument strings: ordered outer argument keys are retained, nested
object keys use Go map order, and JSON strings such as Unicode escapes are
rendered as their decoded values. This affects only the predicted prompt;
the native request body, tool-call IDs and tool-result associations are never
rewritten. Non-finite numbers and integers beyond exact float64 range are
refused. Any remaining number-format or template difference still causes the
live byte-parity gate to refuse generation. The per-request resident check
also requires the exact research manifest digest, not only the model name and
context capacity.

Re-rendering the two retained native requests with the corrected predictor
matches their saved actual server prompts exactly: 18,553/18,818 characters
and 4,547/4,599 runtime tokens. Runtime token IDs in the original live check
already matched the reconstructed GGUF vocabulary exactly. A new live
check is still required for the restarted server before generation; offline
rechecking a historical response does not itself establish current residency.

Every context-gate invocation now retains a terminal receipt, including
failures before dispatch. The callback receives the actual request copy,
available identity/context/preview/tokenization evidence, and the refusal.
Allowed HTTP event records distinguish generation requests from render-only
previews. These count requests allowed past the gate toward HTTP dispatch;
they do not prove that the server received or completed the request.

## Results to date and resource disposition

The no-generation tests cover actual refused connections, asyncio socketpair
cleanup, DNS/subprocess/credential/source-write refusals, HTTP model/path
allowlisting, context overflow, metadata-only parsing, native wire equivalence,
and private tokenizer route isolation. The 43 focused tests pass in the native
dependency environment, with pytest supplied from the separate test environment;
Ruff also passes. Native full opening and a task-independent tool-result
follow-up construct correctly with 14 unchanged HTTP tool schemas. Their
initial offline counts were 4,846/4,898 tokens before accounting for provider
normalization; the actual retained server renders contain 4,547/4,599 tokens.
Including 512 generation tokens and 64 reserved tokens requires 5,123/5,175
tokens respectively. Full per-request parity remains mandatory.

An earlier post-import memory check refused model loading: 4,604,674,048 bytes
available versus the previously declared conservative 5,986,954,731-byte
requirement. `/api/ps` contained no loaded model. Therefore the first three
prechecks dispatched no generation and did not load a model; those particular
receipts contain no measured renderer/tokenizer parity or autonomous result.
The later isolated `q8_0` condition has a conservative requirement of
4,854,492,651 bytes: 2,497,293,803 weight bytes, 1,283,457,024 KV bytes
(including block-scale overhead), and 1 GiB reserve. A lean preflight passed
that gate and loaded the model without generation; its later renderer check
failed as explained above. After the application restart, a new render probe
under `restart-1045/` refused before loading because only 2,932,023,296 bytes
were available. It records zero generations and no renderer checks.
The prior statement about the first three prechecks does not apply to these
later separately recorded attempts. No autonomous performance result exists.

After the user freed memory, the fresh `restart-1045/render-v5/` probe passed
the same conservative load gate with 5,775,028,224 bytes available. It loaded
the exact model on research runner PID 3476 and verified the full native
opening and tool follow-up byte for byte against the corrected predictor;
every runtime token ID also matched (4,547/4,599 tokens). A separate full-policy
synthetic booking-history render with nested objects, Unicode arguments and an
integral floating-point value also passed the complete context gate (4,741
prompt tokens). Its prior tool message was a transport fixture; no native
tool was executed. The actual runner log confirms `q8_0` keys and values,
1,224 MiB KV allocation and enabled Flash Attention at 16,384 context tokens.
That process-only server kept this model resident with `keep_alive=-1` until
the subsequent development failure and explicit resource amendment below.
These render-only checks contain zero actual generations and no autonomous
benchmark reward.

## Prospective two-slot resource and timeout amendment

The separately retained first task-independent actual generation attempt,
`output/native-development-2026-10-21/transport-smoke-000/`, timed out after
180 seconds. Its context gate passed for the complete 4,563-token request,
but no provider response or tool execution was obtained. The attempt remains
counted, with unavailable response usage. Slow cold prompt processing motivated
a prospective request-timeout change to 600 seconds and a trajectory hard limit
of 3,600 seconds before any official native evaluation. These amendments do
not change the output cap, seed, model weights or full-history requirement.

The same prospective amendment requests two model KV slots so serial assistant
and user requests can retain separate prompt prefixes. It does not run native
clients concurrently or reduce the context capacity per request. Only the
previously identified research-owned server PID 1788 and its child runner 3476
were stopped after the client returned. Executable paths and hashes, runner
parent, model path and port were verified before termination. The normal local
service and other applications were untouched; the stop receipt is retained.

The `parallel2-1110/` research server changes only `OLLAMA_NUM_PARALLEL` from
one to two, retaining `q8_0` KV, Flash Attention, 16,384 tokens per slot,
the exact existing model manifests, numeric listener and `keep_alive=-1`.
The conservative cold requirement is 6,137,949,675 bytes: 2,497,293,803 weight
bytes, two 1,283,457,024-byte KV allocations, and 1 GiB reserve. The lean fresh
preload check passed with 7,354,044,416 bytes available. Both full native
opening/follow-up render and runtime token-ID comparisons passed unchanged.

The actual new runner log proves `-c 32768 -np 2`, two slots each containing
16,384 context tokens, `q8_0` keys and values, 2,448 MiB total KV allocation,
and enabled Flash Attention. `/api/ps` reports the expected per-request
16,384 context capacity. Server PID 16044 and runner PID 13568/private port
59484 identify this load; future executions must verify their own live
identities rather than trusting a historical PID. The new render checks
contain zero generations. Their success does not yet establish generation
latency, tool-call compatibility, native reward or successful autonomous
benchmark execution. The requested timeouts and two-slot condition must be
bound in the prospective official protocol before collection.

The retained work-in-progress receipts are in
`output/native-transport-development-2026-10-21/`. A changed context profile,
resource threshold or transport condition must be explicitly declared and
validated before official evaluation, never substituted silently after scores.
