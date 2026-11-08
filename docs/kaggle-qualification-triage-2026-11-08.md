# Kaggle model qualification failure, 2026-11-08

Status: the full GPU study is not qualified. Do not describe the offline test
count, successful installation or a parsed model response as a completed GPU
benchmark. No measured episode starts until the three-model preflight passes.

Follow-up: the supplied `results.zip` has now been independently checked for
byte/history consistency. It confirms Granite is the failed family and Qwen
and Llama passed. No measured slot started. The audit and preserved local
engineering outcomes are in
`output/kaggle-qualification-audit-2026-11-08/`. A prospective Granite format
correction has produced correct actual tool calls locally; this does not grant
the revised GPU condition readiness. The following triage notes preserve the
earlier evidence and its original uncertainty.

The reported run reached the exact `lookup_echo(name="test-item")` assertion
in `research/kaggle_limbo/run.py`, after `client.complete` returned and the
collector saved `sessions/<session>/<family>/parsed-turn.json`. Reaching that
assertion establishes that imports, GPU binding checks, provider render and
context checks, the generation HTTP response and native parsing completed for
that invocation. It does not establish that the model made the required tool
call. The generic exception does not identify which family failed or whether
the observed failure was no call, wrong arguments, multiple calls or truncation.

Historical evidence requiring resolution exists locally in
`output/expanded-granite2b-transport-preflight-2026-10-25/`:

- `test-item-parsed-turn.json` contains text `{"name": "test-item"}` and zero
  tool calls, with `finish_reason: stop` and nine output tokens.
- Its recorded request used temperature 0.2, seed 2501 and 128 output tokens.
- Its retained context proof includes the tool declaration and fits the
  declared context. That response was not cut off at the output-token limit.
- The Qwen and Llama local checks produced the requested structured call.

These are historical local qualification checks, not new Kaggle results or
measured native episodes. Their prompts differ slightly from the Kaggle check.
The unresolved Granite result should have been addressed before asking for
the full three-model run. It cannot conclusively identify the current failing
Kaggle model without the saved response.

Next diagnostic input: preserve the entire latest saved Kaggle output. Inspect
the failed family's `parsed-turn.json` and `client/0001-response.bin`,
`0001-request.bin`, `0001-context.json`, and `0001-terminal.json` without
dispatching another generation. The current gate mixes transport validation
and model instruction-following; any revision must distinguish those scopes
explicitly and preserve the observed failure.

Do not edit the frozen bundle, accept prose JSON as an actual tool call, retry
until a favorable response appears, silently substitute a model, or pool
different source/runtime conditions. A source/protocol revision requires its
own pinned bundle and declaration. Keep GitHub Actions disabled and use no
human labels or paid inference.
