# Native token accounting — 21 October 2026

This source review precedes any official pilot or native development episode.
It changes no source, collected record, request, response or generation
allowance. Development attempts remain distinct from benchmark outcomes.

## Expected semantics of the pinned local provider

Ollama 0.40.6's `llamaServerTimings.promptEvalCount()` returns the sum of
`cache_n` and `prompt_n` when the cached count is present; otherwise it returns
`prompt_n`. Both completion and chat final-response paths use that method,
while retaining the cached count separately. Thus the expected prompt count
includes the reused prefix, rather than counting only newly evaluated tokens.
The tagged raw file has SHA-256
`4d9477c32d90ed8c3436aa67480a2ac55234dd401038d097bb33ab8101c4461c`
(91,825 bytes); its chat-request log statement occurs at the same source line
2024 shown by the installed service. This is a source check, not a substitute
for comparing the actual response. See the pinned
[timing conversion](https://github.com/ollama/ollama/blob/v0.40.6/llm/llama_server.go#L1632).

The OpenAI compatibility adapter copies this count to `usage.prompt_tokens`
and exposes the cached subset as
`usage.prompt_tokens_details.cached_tokens`. It sets `total_tokens` to prompt
plus completion tokens. Adding the cached subset again would double count it.
See [ToUsage](https://github.com/ollama/ollama/blob/v0.40.6/openai/openai.go).
The [API metric definition](https://github.com/ollama/ollama/blob/v0.40.6/api/types.go)
uses a nullable cached-count field: absence is distinct from an observed zero.

## Prospective reporting rule

The existing check comparing a complete gate token count with a successful
response's `usage.prompt_tokens` should remain exact. Cache reuse alone is
not a reason to relax it. A discrepancy must retain both original counts and
the raw response and must not be repaired by an assumed cached-prefix sum.

Keep three separate quantities: the complete gated input-token count for each
request allowed toward dispatch; provider-reported total prompt and completion
tokens when available; and the reported cached prompt subset. Derive uncached
prompt tokens as total minus cached only when both are valid observed counts
and the cached subset lies between zero and the total. Missing cached usage
does not establish a cold request.

Timeouts remain attempted requests even when no response usage exists. Their
gate count describes the input submitted, not completed model computation.
Retained server progress logs can corroborate partial processing but cannot
silently replace missing final usage. In particular, later cache reuse must
not erase the cost or failure of the attempt that populated the cache.

Full input tokens, newly processed tokens, wall time and monetary API charges
are different endpoints. Serial requests using two KV slots do not guarantee
fixed role-to-slot assignment or equal cache reuse across arms. Report the
observed cache condition and arm order, and make no intrinsic speed claim from
this one local run. Completed-response timing fields are not automatically
available through the selected OpenAI route; retain actual fields rather than
inventing them from the provider's type declarations.

## Development observation status

At this review, `transport-smoke-002` has a retained gate and dispatch record
and its server log shows a 4,096-token cached prefix for the 4,563-token prompt.
No final response has yet been read by this reviewer. These log observations
are not a successful generation result or proof of final usage equality.

After the response finished at `2026-10-21T05:53:47.575207+00:00`, read-only
inspection confirmed `usage.prompt_tokens = 4563`, exactly matching the
successful full-render/token-ID gate. The response reports 4,096 cached prompt
tokens, 47 completion tokens and 4,610 total tokens. The derived uncached prompt
count is 467. No `timings` object is present in the raw response. This confirms
the expected count semantics for this request, without adding the cached subset
twice or relaxing equality.

The overall structured-call smoke still failed correctly: the model returned
ordinary text declining the synthetic transport request under the airline
policy, with `finish_reason: stop` and no tool call. A valid usage result is
not a passed tool-call compatibility check. No native tool or official task
was executed. The raw response SHA-256 is
`e7977bee80f7d9a8f431fcc750268a6854b8fa2a274d9164332c9dc9950ec7f9`;
the original failure receipt SHA-256 is
`12075d3ff51a73f701f87996d7dd91c8b6b954561cec5bc7e88a081ad5a661c6`.
They remain unchanged in
`output/native-development-2026-10-21/transport-smoke-002/`.
