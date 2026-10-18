# Same-evidence local trace judge

This separately frozen descriptive comparison judges the **84 original schedule
slots with `repetition == 0`**, retaining their original order. Selection is made
after factual collection, before judge outputs; it is not a held-out sample or
an external preregistration. The source pool contains 504 planned factual slots,
503 completed and one failed. Pool context is reported separately, never as a
504-slot judge score. All 84 selected factual inputs currently completed; the
runner also preserves unavailable selected inputs without a model call.

The comparator is one installed local Qwen3 4B checkpoint, tag
`qwen3:4b-instruct-2507-q4_K_M`, digest
`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`,
served at `http://127.0.0.1:11435`. Temperature is 0.2, output limit 192 tokens,
request timeout 180 seconds, and thinking is disabled. Unique judge seeds are
`1900000000 + selected-position`, unrelated to generator phase seeds. Requested
seeds do not prove independent or deterministic model outputs. This judge shares
a model family with some factual generators; generator strata must remain visible.
It is not independent human validation or a stronger-model claim.

## Information boundary

`public_input` reconstructs an allowlisted object from validated typed records:
registered action/contract and refund parameters, captured dispatch attempts,
public responses, and the last captured independent observation including its
availability, completeness, scope, watermark, refund records and provenance.
This is the same captured source evidence available to Consequa-X and the
independent public reference; responses/attempts supply public request context.
The judge does not receive additional tool access or world state.

All identity-bearing strings receive opaque, equality-preserving aliases per
input. A response refund identifier and an observation effect identifier retain
their equality when they originally agree. Original identifiers, generator names,
paths, case/fault labels, context wording, policy metadata, assessments, rationales,
verification verdicts, explanation text and evaluator truth are excluded. Arbitrary
extra dictionary fields are dropped. Source identity is rendered as the common
label `independent-readback`; the experiment trusts the captured source declaration
just as the existing deterministic auditors do. It does not authenticate a real
service.

The frozen prompt defines state satisfaction, provenance origin and action-linked
target satisfaction, including exact counts, deadline/persistence, unknown
readback and other-actor distinctions. Output is strictly the three enum-valued
fields `state`, `action_linked`, `origin`; no rationale or chain of thought is
requested. Invalid JSON, extra fields or invalid labels are failed samples.
An explicit provider `done_reason=length` is a failed sample even if its final
content happens to parse as valid JSON.
Unknown labels are legitimate abstentions and remain distinct from failures.

## Freeze, run, analyze

Review code, tests and this protocol before freezing:

```powershell
.venv/Scripts/python.exe scripts/run_matched_trace_judge.py freeze `
  --study-output output/matched-local-study-2026-10-18 `
  --study-analysis output/matched-local-analysis-2026-10-18 `
  --output output/matched-trace-judge-2026-10-18
```

Freeze makes no generation request. It checks the closed-study bindings, checks
every selected trace against its factual receipt, recomputes deterministic
reference/Consequa-X predictions against sealed analysis, inspects the installed
model without downloading/loading weights, and writes all inputs and protocol
before any judge call. The protocol binds source/runtime/test/doc hashes,
Python/package versions, prompt/schema/settings, model digest/metadata, original
source bytes, exact selected schedule and input hashes. The separately stored
`evaluation-context.json` contains gold/baselines and never enters a judge request.
Freeze requires a new or empty output directory; do not reuse previous artifacts.

```powershell
.venv/Scripts/python.exe scripts/run_matched_trace_judge.py run `
  --output output/matched-trace-judge-2026-10-18
.venv/Scripts/python.exe scripts/run_matched_trace_judge.py analyze `
  --study-output output/matched-trace-judge-2026-10-18 `
  --output output/matched-trace-judge-analysis-2026-10-18
```

Run checks the frozen source/input/environment and daemon/model identity before
starting. Existing local-only Ollama checks reject non-loopback or declared
remote routing. Every available input receives at most one attempted chat, with
no repair prompt, retry or replacement. Every request and received response is
saved as exact bytes with exclusive creation, and bound to an append-only hash
chain. Errors retain receipts. A transport, HTTP or identity failure stops that
invocation; malformed model output remains a failed sample and later slots may
continue. Resume visits only never-started slots, never an interrupted or failed
slot. The two-hour default wall budget begins with the first run and is retained
across resumes; the attempted-call cap is the number of available selected inputs.
Read-only model identity requests are not generation calls and are outside that
cap. A crashed process leaves its lock for explicit inspection; the script never
deletes an inherited lock or repairs a torn journal.

The analyzer refuses an active lock or changed inputs and rechecks saved requests,
responses, outputs and journal bindings. It reports completed, failed, interrupted,
unstarted and unavailable slots, including attempted calls from interrupted slots.
It preserves complete selected-slot denominators in generator/model/profile and
case strata. Baseline metrics use all selected available factual inputs; judge
metrics use available completed judge outputs plus explicit full-selected
operational yield. Different completion counts stay visible.
Analysis requires a terminal valid `run_stopped` event. A limited or resumable
infrastructure-stopped run is explicitly `final: false`, `collection_state:
incomplete`; it is never labeled a finished experiment. Processing all planned
slots closes the run, retaining interrupted slots. Exhausting the original fixed
wall budget produces the separately labeled `closed_wall_budget` disposition.

For each of the three targets report claims, correct/wrong claims, coverage,
wrong claims/claims, correct definite yield and correct definite claims/all 84
selected slots. Zero denominators are JSON null. Abstentions and unavailable
outputs are never correct claims. Origin gold can itself be unassessable: all
definite outputs and claims with unassessable gold remain visible separately.
Evidence support means the independent public rule derives that same definite
label from the allowed evidence. Correct guesses without such support are
reported separately. This is an automated evidence qualification rule, not human
rationale annotation. No pooled independent-task interval, significance test,
method superiority, causal responsibility, benchmark leaderboard score or real
service generalization follows from these fourteen fixed simulator cells.

Tests use captured fixtures and mock local HTTP; they do not call a live model.
GitHub Actions remains disabled, and all execution is local.
