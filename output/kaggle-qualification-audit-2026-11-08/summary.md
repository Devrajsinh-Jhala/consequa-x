# Saved Kaggle qualification audit

The uploaded archive is intact. Its checkpoint ZIP, 54 bound evidence files,
raw output, event chain and schedule agree. All 3,456 measured slots remain
unstarted. This archive contains model qualification calls, not benchmark task
results.

| Model | Original Kaggle tool call | GPU layers | Corrected local first call | Local tool-result response |
| --- | --- | --- | --- | --- |
| Qwen 4B | Correct structured call | 37/37 | Correct structured call | `test-item` |
| Llama 3B | Correct structured call | 29/29 | Correct structured call | `test-item` |
| Granite 2.5B | Empty API response, no call | 41/41 | Correct structured call | Correct name in a sentence |

Granite's original API response reports 22 completion tokens and a normal stop,
but contains neither text nor tool calls. This is not a native-parser loss or
context overflow. Raw generated text before Ollama's tool parser was not saved;
the API response cannot establish that the model generated nothing.

The original Granite provider template appends its native tool-format guidance
only when there is no custom system message. The supplied benchmark system
message suppresses that branch. The prospective correction copies the existing
vendor guidance into the custom-system-with-tools branch, retains all native
messages/history, and applies identically across all four arms. Its new template
is 7,042 bytes, SHA256
`18d85e85522dce58d0d31f5a5d953e5897f25fb8e1fba18426a3bce73c7747ab`.
Weights and tokenizer bytes do not change. Original OCI provenance is retained.

The first corrected local Granite probe made the exact required call on its
first attempt and completed a tool-result followup. Subsequent engineering
checks exercised the same explicit two-stage system instruction across all
three families, ending the followup at the tool result. Their six retained
responses include correct first calls for all three and usable followups. This
is CPU engineering evidence, not a prospective GPU qualification pass or proof
of general task accuracy.

Development failures are preserved: an early Qwen setup-only display/OCI check
stopped before generation; an additional-user-reminder test induced a repeated
Llama call; and Granite's full-sentence readback failed a strict bare-echo gate.
The latter is not a transport failure. `local-engineering.json` retains those
original verdicts and separately replays the new usability checker on saved
responses; it does not relabel the old checks as prospective passes.

The new `tool-roundtrip-v3` readiness definition still requires the first exact
structured call. The followup must carry usable native text or structurally
usable calls; exact wording and extra calls remain separate diagnostics. The
benchmark's native task grader evaluates actual performance. No prose is
converted into a tool call, and unsuccessful calls are not retried until a
favorable result appears. No measured task instances were used for these
engineering changes.

The corrected source/template condition needs its own frozen bundle and live
GPU readiness checks before any measured episode. It must not import the old
failed qualification as its active checkpoint. Preserve that archive separately;
it contains zero started tasks. GitHub Actions remains disabled.

Primary implementation references: [IBM tokenizer configuration](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct/blob/main/tokenizer_config.json),
[pinned Ollama tool parser](https://github.com/ollama/ollama/blob/v0.40.10/tools/tools.go),
and [pinned tool-tag extraction](https://github.com/ollama/ollama/blob/v0.40.10/tools/template.go).
