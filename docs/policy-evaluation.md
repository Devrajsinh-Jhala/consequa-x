# Policy evaluation

Consequa-X can run a policy against the isolated refund simulator, capture the
policy's decisions, and verify the resulting state independently. The policy
can be a deterministic scripted baseline or a local model served by Ollama.
The payment operations remain simulated in both cases.

The integration is designed to be tested without installing Ollama or pulling
model weights. A passing scripted or mocked-server test is an integration
result, not an evaluation of a language model. No real-model result should be
claimed until an installed model has completed a recorded run.

## Run the offline baseline

From an environment with the package installed:

```console
consequa-x model-eval --provider scripted --samples 2 --seed 0 --max-calls 100 --max-attempts 2 --output output/model-evaluation
```

`scripted` is the default provider. `--samples` selects episodes per case; it is
not the number of model calls. Each episode asks for an initial selection and,
if a refund is selected, a decision after each tool response. An episode with
two attempts can therefore require three policy calls. `--max-calls` bounds
policy calls across the command. Use `--cases clean,timeout_after_commit` to
restrict the suite while developing an adapter.

The command exports portable traces, explanations, separate evaluator truth,
run settings, aggregate results, a report, and a file-integrity manifest. Keep
the evaluator material out of policy prompts and explainer inputs. Check the
report's provider before treating its rates as language-model measurements.
Use a new or empty output directory for each run so old samples cannot be
mistaken for current results.

## Run an already installed local model

Installing Ollama and choosing or downloading a model are separate steps. The
framework does not install Ollama, pull a model, or select one automatically.
After a local service and an appropriate model are available:

```console
consequa-x model-eval --provider ollama --model YOUR_INSTALLED_MODEL --samples 2 --seed 0 --max-calls 100 --max-attempts 2 --output output/ollama-smoke
```

Replace `YOUR_INSTALLED_MODEL` with the exact installed model name. The default
service address is `http://127.0.0.1:11434`. The adapter accepts a local
`--base-url`, plus `--temperature`, `--timeout`, and `--num-predict` controls.
`--prompt-version refund-policy-v2` selects an opt-in prompt profile. The default
remains the exact original `refund-policy-v1`. V2 clarifies that context strings
are visible facts, `attempts_remaining` counts additional attempts, timestamps
are simulated time, and a timeout warrants an unknown assessment without a
successful acknowledgement. It also adds stop-after-success and retry guidance.
This is a pilot-informed policy refinement, not a fix to a request-encoding bug;
comparisons are exploratory. It receives no hidden readback or evaluator labels,
and the adapter never rewrites a valid model decision to enforce the guidance.
The Python constructor accepts `prompt_version="refund-policy-v2"` too.

It uses the Ollama chat endpoint with a JSON Schema output format and validates
the returned decision locally. Ollama documents these interfaces in its
[chat API](https://docs.ollama.com/api/chat) and
[structured-output guide](https://docs.ollama.com/capabilities/structured-outputs).

The CLI checks the local installed-model list before starting; a missing
service or model stops that preflight without creating a completed evaluation.
Before the first chat, `OllamaPolicy.validate_local_model()` also reads
`/api/show` and rejects a declared `remote_model` or `remote_host`. The adapter
caches this inspection for the current model and server address; changing
either triggers another inspection, and `force=True` explicitly refreshes it.
This uses server-declared metadata and a loopback connection, not a proof of
where an untrusted server performs inference. The local server must be trusted.
Malformed responses and timeouts during episodes become failure receipts in
`results.json`. Exhausting the call budget leaves a partial report and an
explicit count of samples not started. None of these errors becomes a
fabricated `violated` outcome or a successful model episode. Failed episodes
have no completed trace or verifier result; inspect their receipts alongside
the number of completed episodes.

The command returns exit status `2` for a failed provider/protocol sample or
exhausted budget. A completed evaluation returns `0` even if some simulated
refund contracts are `violated`; those are valid measurements. Inspect the
report to distinguish an unsuccessful refund from an unsuccessful evaluation.

## What the policy sees

`PolicyRequest` is the boundary between an agent policy and the benchmark.

| Field | Purpose |
| --- | --- |
| `stage` | `select` before the first attempt, or `after_response` after a returned response. |
| `task` | The ordinary refund task and supported parameters. |
| `context` | Named, visible textual context: customer request, VIP memory, retrieved exception, retry instruction, and distractor. |
| `responses` | The captured public tool responses, including an ambiguous timeout. |
| `attempts_remaining` | Remaining simulated execution attempts. |

The fixed system policy gives the ordinary 30-day refund rule. Visible retrieved
context can supply a 60-day VIP exception. Interventions change the declared
context before the policy decides; they do not append a secret evaluation
label. A model must infer its decision from the visible content, rather than
receiving a precomputed permission flag.

The policy returns a `PolicyDecision` with an operation (`refund`, `retry`, or
`stop`), a reported assessment, and a rationale. A `PolicyReply` also carries
adapter metadata. `Policy.decide(request, seed=...)` and the `Policy.metadata`
property are the extension points for other providers. The runner enforces the
stage and attempt limits rather than executing arbitrary tools named by the
model.

The policy does **not** receive the injected fault identity, scenario name,
simulator gold log, independent readback, or verifier verdict. Independent
readback takes place after policy execution. A timeout after commit and a
timeout before commit are intentionally ambiguous at the response boundary.
The model's rationale is a recorded explanation, not an authenticated account
of hidden reasoning.

`ScriptedRefundPolicy` reads this same visible boundary. It is a baseline for
testing the harness, not a reproduction of CAR or a strong attribution-method
comparator. It checks whether the expected context strings are present and
applies the configured age limits; it does not interpret arbitrary language.

## Outcomes and interpretation

Three different measurements must remain separate:

1. **Consequence:** the fixed refund contract is `satisfied`, `violated`, or
   `unknown` using horizon-aware independent readback.
2. **Origin:** readback links the effect to the current action, another actor,
   or neither confidently.
3. **Assessment alignment:** the agent's reported assessment agrees with the
   supported action-linked outcome, contradicts it, or is unassessable.

A refund by another actor can satisfy the state contract without making the
agent's failure assessment incorrect. Missing or stale readback gives
`unknown`, not failure. A policy that stops without selecting the action still
faces the same fixed consequence contract. This avoids scoring only episodes
in which a model happened to choose the original action.

Both evaluation and replay summaries include `assessment_metrics`. Counts cover
completed episodes only: `success`, `failure`, `partial`, and `unknown` remain
distinct. Definite claims are success/failure; unknown is abstention, and partial
is retained separately. Claim coverage divides definite claims by completed
assessments. Assessable claim coverage divides consistent/contradicted definite
claims by completed assessments. Contradiction rate divides contradictions by
assessable claims. Each rate records its numerator and denominator, with a null
value when the denominator is zero. Definite claims with unknown verification
or insufficient origin remain unassessable. Provider failures and unstarted
episodes stay in their separate run counts.

These metrics describe hindsight alignment with supported action-linked state.
They do not grade what the policy could know from public responses: a timeout
can justify unknown even when later readback resolves success. Report coverage,
abstention, and contradiction together; blanket abstention is not improved
accuracy. The [first live pilot](../output/live-pilot-2026-10-10/README.md) preserves
the original v1 observations used to motivate this exploratory refinement.

Simulation time determines the contract deadline and stability horizon.
Provider-reported inference duration, when available, is recorded separately
and does not advance the simulator clock. Results therefore do not measure
deadline compliance in a real payment system.

## Replay and reproducibility

`run_policy_scenario` starts a fresh world for each episode. Policy calls are
stateless over the request and seed; provider runtime state is not snapshotted.
`RefundPolicyReplayRunner` supports the same declared context interventions as
the fixture runner and can supply outcomes to `leave_one_out`. Replay remains
isolated simulation; no live financial effects are repeated.

Ollama exposes generation seeds and options such as temperature and maximum
predicted tokens in its
[parameter documentation](https://docs.ollama.com/modelfile#valid-parameters-and-values).
The adapter records its requested settings. Treat identical seeds as a
best-effort replay control, not a guarantee across model revisions, Ollama
versions, hardware, quantization, or divergent prompts. Measure replay
agreement in the study rather than assuming it.

Before publishing results, save the repository revision, model name and weight
digest, Ollama version, hardware, generation settings, exact prompts and
responses, seeds, and failures. A model tag alone is insufficient provenance.
Current trace events record the visible policy request, parsed decision,
requested settings, prompt version, returned model identity, and three hashes:
`request_sha256` for the public request JSON, `system_prompt_sha256` for the
selected versioned system prompt, and `request_payload_sha256` for the full encoded request
including messages, schema, and generation options. The adapter also records
its local-model inspection and provider token counts and timings when supplied.
It checks that the returned model identity matches the requested one, allowing
an omitted default `:latest` tag. The records do not preserve the full
HTTP envelope or automatically discover the Ollama version. The CLI saves the
installed model's identity and digest when the local model-list response
supplies them. Keep the source revision for the fixed system prompt and
supplement the run record before a formal study.
The exported integrity manifest detects changed files; it does not authenticate
the model server or the source of readback evidence.

See [the study plan](study-plan.md) for the experiments still needed for a
research-paper claim.
