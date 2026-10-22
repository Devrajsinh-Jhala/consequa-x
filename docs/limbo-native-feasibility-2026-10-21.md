# LIMBO native benchmark feasibility - 21 October 2026

Status: read-only source feasibility assessment, not a benchmark result or an
execution protocol. This proposes a later stage after the current matched
airline pilot; it does not replace, stop or amend that pilot. No repository was
cloned, dependency installed, model called, external write made or GitHub Action
triggered. No task-definition file, test fixture, case-study file or episode
archive was opened for this assessment.

## Artifact and local-provider feasibility

The author's public [LIMBO repository](https://github.com/jaxblack/limbo-bench)
identifies itself as the artifact for
[arXiv:2609.29095v1](https://arxiv.org/abs/2609.29095v1).
Read-only `git ls-remote` resolved main to
`2db09fba22a0572a70639162a808906409f612a8`; tag `v1.0` resolves to
`83c59e31f8477a5fb6f186dfcc9f3d10fa336b8a`. Main includes later
[audit corrections and exploratory real-API tooling](https://github.com/jaxblack/limbo-bench/commit/2db09fba22a0572a70639162a808906409f612a8).
Pin one revision; do not equate main, the release and the original preprint.
Code is MIT; released episode records and generated figures/tables are CC BY
4.0. The latter were not downloaded.

The pinned [provider client](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/limbo/llm.py#L85-L251)
accepts `LIMBO_BASE_URL` and OpenAI-compatible `/chat/completions`. An ordinary
Qwen tag chooses chat rather than Responses. The minimal client requires a
nonempty `LIMBO_API_KEY`; a nonsecret placeholder can satisfy that check for
Ollama. No paid key, LLM judge or real service account is inherently required.
Actual structured-call compatibility has not been tested.

Stock defaults are eight HTTP attempts, a 240-second request timeout, 8,192
output tokens and per-model concurrency six. Context fit is not explicitly
checked; absent usage is converted to zero, and unsuccessful transport attempts
do not provide complete token accounting. Do not mistake these defaults for
the existing airline protocol's limits.

The public [episode API](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/limbo/agent.py#L20-L144)
offers `run_episode(spec, client=...)`. A separate frozen launcher can supply an
upstream `LLMClient` with declared output, timeout, temperature, attempt and
concurrency settings while retaining the upstream environment and grader. The
stock CLI does not expose those provider ceilings. Its
[runner](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/limbo/runner.py#L54-L134)
defaults to eight workers and skips finished records on restart, while earlier
LLM/harness errors are eligible again. A prospective study needs its own
first-attempt accounting, failure retention, hard deadline and no-resume rule.

## Native faults, grading and strong controls

The author's [runtime](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/limbo/runtime.py)
implements pre/post-commit ambiguity, fixed and heavy-tailed late commits,
partial batches and duplicate delivery, among other faults. Pending commits
settle before grading. Delays advance a virtual clock, rather than necessarily
sleeping for their simulated duration. The unchanged
[grader](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/limbo/grader.py#L137-L169)
uses committed effects and final world state for task success, exactly-once
success, executed/live/compensated duplicates, collateral changes and extraneous
writes. These implementations are authored outside this project; inspecting
them does not establish their correctness or production-service validity.

The public [recovery policies](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/limbo/policies.py)
already provide capable conventional comparators:

| Control | Public implementation semantics |
| --- | --- |
| `vanilla`, `aware`, `reflect` | Direct model decisions, reliability instructions, or an extra reflection message after errors. |
| `sdk_retry3`, `rules` | Up to three additional tool retries; the latter retries 429/503 only. These tool policies differ from HTTP model-request retries. |
| `vbr`, `waitN` | Check a pending write before a repeated intent; `waitN` additionally waits an assumed in-flight bound plus documented visibility lag. |
| `guard` | Adds supported idempotency keys, lag-aware verification, partial-batch handling, unverifiable-repeat blocking and model-visible annotations. Component ablations exist. |
| `oracle`, `outcome_oracle` | Privileged reference conditions; the latter can inspect in-flight work. They are not deployable baselines. |

Controls use declared tool contracts and intent matching; normal guards do not
receive the oracle's privileged truth flag. Verification invokes
`runtime.verify`, not necessarily an ordinary model-issued read tool call.
Verify its information and cost boundary before claiming equal read spend.
Compare the same fault/world, contract variant, model configuration and public
information opportunities. Report automatic tool work separately from model
proposals. Native versus `keys_everywhere` is a provider-contract manipulation;
granting keys only to the package would confound a framework comparison.

## Automated-only scope and next gates

Escalation is a simulated operator, not a message to a person. The runner's
`--no-human` option makes that simulated operator unavailable; this is an
explicit experimental condition, not removal of real participants. Its choice
must be frozen consistently across conditions. No recruitment is required.

The pinned [README](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/README.md#quick-start)
specifies Python 3.11+ and standard-library benchmark execution.
[Analysis requirements](https://github.com/jaxblack/limbo-bench/blob/2db09fba22a0572a70639162a808906409f612a8/requirements.txt)
are NumPy, pandas, SciPy, statsmodels and Matplotlib. Minimal execution needs no
production agent CLI. No measured RAM or local-model latency requirement is
published. Inference: model memory and generation should dominate this small
simulator's cost; neither its overhead nor full-history context fit is measured.

Recommendation: after the airline pilot, consider a separately frozen,
serial LIMBO study with unchanged native faults/grading and strong upstream
controls. First verify dependency imports, invented task-independent tool
roundtrips, complete prompt/token preservation, resource limits, failed-call
accounting and independent replay. Freeze selection before generation, preserve
all planned dispositions, and keep evaluator-only targets/ledgers outside the
package adapter. This targets ambiguous-commit recovery more directly, but
remains a simulated external benchmark and supplies no result, superiority,
novelty or conference-readiness claim today.

## Later sparse-source and grading clarification — 21 October 2026

The opening status records the initial feasibility assessment. Subsequently,
a separate sparse checkout was created at
`D:/ConsequaX-Research/limbo-pinned-2db09fba`, detached at
`2db09fba22a0572a70639162a808906409f612a8`. The later public-API preflight is
retained in `research/limbo_agent/identity-preflight-2026-10-21.json`; its
inspection covers eleven explicitly allowed public/documentation files and
three public schema declarations, not tasks, fixtures or released archives.
The follow-up source review checked those eleven actual file hashes and the
preflight source hash against that record. No upstream module, task episode or
model was executed. This remains source feasibility and declaration metadata,
not an import/dependency proof, benchmark result or execution protocol.

The pinned grader's metric names require these qualifications:

- `TS` requires target minimum live counts and no **graded** collateral change;
  native `EOS` adds only `dup_executed == 0`.
- `exact_state` means each target's final live count equals its expected count.
  It does not test complete-world equality or exclude collateral/extraneous
  writes. `clean_success` is `TS and dup_live == 0`.
- Status targets have `executed == 0` because `_effect_matches` has no status
  branch, so repeated status writes cannot increase native executed duplicates.
  Upsert execution counts use matching `CREATE` effects for the table/key and
  then cap that count at final matching live records. Refund execution counts
  are not capped by the final live count.
- `dup_compensated` is `max(0, dup_executed - dup_live)`, not an independently
  counted number of compensation operations. Executed/duplicate counts are
  domain-specific grader abstractions rather than universal physical counts.

These statements follow public `limbo/grader.py:38–68,145–178` at the pinned
revision. They qualify interpretation without changing upstream grading or
the active airline study. The more detailed prospective adapter design is in
`research/limbo_agent/DESIGN.md`; no comparative performance, human validation
or external replication is established by this follow-up inspection.
