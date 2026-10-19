# External validation findings and evidence boundaries

Updated 19 October 2026 after collection closure, sealed offline 2.0 conformance and the current 2.1.1 release.

These additions follow the timestamped internal plan in
`protocol-external-validation-2026-10-18.md`. Each execution has its own
prospective source and input freeze. They do not replace the original
503-completed/504-planned factual study or its recorded failure. The judge
subset was selected after factual collection and before any judge output;
it is not a held-out task sample. No GitHub Actions or paid model calls are
used by this work.

## Same-evidence local judge

The fixed repetition-zero rule selected 84 traces, with all 84 public inputs
available. One frozen local Qwen3 4B model returned 84 valid outputs in 84
calls, without redraw or corrective retry. Its input contains the same public
contract, attempted action, response, readback and provenance as the deterministic
auditors, with consistent opaque identifiers. Gold, fault/generator labels,
prior verdicts, explanations and paths were withheld. The inputs contain 17
distinct serialized evidence patterns. Repeated patterns and requested seeds
do not establish independent tasks.

| Method | Target | Definite / gold-assessable | Wrong / definite | Correct / all 84 planned |
|---|---|---:|---:|---:|
| Local judge | Global state | 60/84 | 9/60 | 51/84 |
| Independent reference; Consequa-X each | Global state | 72/84 | 0/72 | 72/84 |
| Local judge | Action-linked outcome | 0/84 | Undefined (0/0) | 0/84 |
| Independent reference; Consequa-X each | Action-linked outcome | 64/84 | 0/64 | 64/84 |
| Local judge | Effect origin | 52/52 | 12/52 | 40/84 |
| Independent reference; Consequa-X each | Effect origin | 36/52 | 0/36 | 36/84 |

The judge made 60 definite origin claims overall: 52 on assessable gold and
eight additional claims with unassessable gold. The latter are neither correct
nor wrong in the semantic table. The judge abstained on all 84 action-linked
outcomes; zero-denominator error is undefined, not perfect performance.

Using the independent public-evidence reference as a rule-based qualification,
43 judge state claims and 24 judge origin claims are supported. Eight correct
state guesses and 16 correct origin guesses lack that support. This check is
not a human rationale annotation. The two deterministic implementations agree
exactly on all three targets. One small local judge, overlapping a generator
family, cannot establish superiority over model judges generally.

The sealed analysis is
`output/matched-trace-judge-analysis-2026-10-18/analysis.json`, SHA-256
`117ea516eadd2e171fef5f8ffbe7337f5d70dd32add6647a3ee6496f2a51528f`.
A separate analyst recomputed fractions and strata from all raw response
bytes, checked the 338-event journal and 168 raw request/response files, and
audited input exclusions. See `output/matched-trace-judge-audit-2026-10-18/`.
This is independent code/artefact review within the project, not independent
human validation of the task labels.

## Maintained benchmark task/tool state transfer

The pinned maintained `sierra-research/tau2-bench` revision
`96a3ef92329baf908ffe9dfe188cea34e8701d2a` supplies all 114 retail and 50
airline canonical tasks, native environments, tools and DB evaluator. Four
fixed controls per task yield 656 completed cells, zero failed and zero
unstarted. The controls replay native reference actions, omit writes, return
a false success acknowledgement without writing, or alter the first write.
There are 900 structurally valid immediate-operation captures and no model
calls. A namespace-only bootstrap bypasses unused model/voice imports; the
upstream tool and relevant evaluator bodies remain unchanged and hash-bound.

| Domain | Control | Native task DB matches | Immediate requested-field predicates satisfied |
|---|---|---:|---:|
| Retail | Reference replay | 114/114 | 174/176 |
| Retail | Omit writes | 11/114 | 2/176 |
| Retail | False success response | 11/114 | 2/176 |
| Retail | Alter first write | 13/114 | 72/176 |
| Airline | Reference replay | 50/50 | 49/49 |
| Airline | Omit writes | 24/50 | 0/49 |
| Airline | False success response | 24/50 | 0/49 |
| Airline | Alter first write | 24/50 | 23/49 |

Every withheld-readback control remains unknown, as does action origin without
a native witness. Assessment alignment is unassessable for this custom record
contract. Reference task DB equality (164/164) is self-replay consistency by
design, not task success. Field satisfaction (223/225 reference operations)
is not predicate accuracy against an independent oracle. The task DB target
and an immediate operation-field target differ.

Task 64 includes a rejected exchange followed by a successful pending-order
modification, illustrating an error/fallback path. Task 105 includes a rejected
exchange and an unmeasured natural-language assertion requiring both exchanges.
Tasks 22 and 110 have address predicates already satisfied without a write;
task 22 includes changing and then restoring the address. No dataset-bug claim
or action-origin inference follows from these cases.

The DB component excludes communication criteria and retail natural-language
assertions. The experiment does not run the original autonomous agent, user
simulator or all native grading components, and is not a benchmark pass rate
or leaderboard result. Development inspection included retail task 0 and
airline tasks 19/20; the canonical corpus is not held out. The final audit was
performed by the adapter author, not an independent implementer or human panel.

The sealed `summary.json` SHA-256 is
`2d042cbd8f138c9f31f82d1c33e91786f4e2237c27bcc5a6805714ffbc50c75e`.
The per-episode hashes, schedule checks and contextual task review are in
`output/tau3-state-transfer-audit-2026-10-18/`. Its tracked trajectory-call
count excludes extra preflight/readback lookups and native evaluator replays;
it must not be reported as total execution cost.

## Native CAR comparison: closed collection and final audit

The committed prospective protocol pins native CAR revision
`db90fa28b97164c35e7c524e4597b8cbdb3035af`, local source `940ebfc`, eight fixed
mechanisms, 64 repetitions and two algorithms. All 1,024 paired groups and
2,048 engine files were retained with zero redraws. The terminal manifest
SHA-256 is `36e80b2afaeaacb5d5b4695ba997fe949b8d4cc84ce63154791e87a9ccec556d`.
It binds 2,053 files; the source checkout used for execution remains unchanged.
The 393,216 canonical planned slots are not all completed numeric draws.
The [final independent artifact audit](../output/upstream-car-audit-2026-10-18/final-audit.md) now checks all retained files, source bindings
and 1,024 semantic group digests. All factual traces and successful fresh-call
totals agree. The primary gate admits 640 paired groups with exact point parity
and withholds 384 for both engines; no non-budget semantic discrepancy was
found. The audit independently reproduces point estimates, coverage, bias,
RMSE and widths, using the retained engine interval endpoints rather than
reimplementing each interval algorithm. Its SHA-256 is
`fa4e6c08d26db580d001a4b8d7b8fae9ffbd1ac99f072418e66c1e424bc537e8`.

The postcollection audit found one collector deviation in the 64 native
contrastive four-call-budget groups. The native sampler starts 32 coroutine
rollouts together, while the bridge advances its slot only on successful
scoring. Zero-spend refusals consequently coalesce under one failed slot.
The canonical inventory is 40 known, 64 failed and 6,040 unstarted slots;
it is not a one-to-one actual-start inventory. Source and saved records support
2,048 first-coalition invocations: 40 completed and 2,008 refused, with 4,096
later-coalition invocations unstarted. Individual refused-coroutine identities
were not retained. Fresh-call totals and the cap remain auditable, and all
affected vectors are already ineligible. No eligible estimate is changed.
See `output/upstream-car-audit-2026-10-18/protocol-deviation.{md,json}` for the
exact 40/24 shapes, source ranges and SHA-bound original examples. This is a
disclosed collector limitation, not an amendment to the prospective protocol.

The [results/cost context](../output/upstream-car-audit-2026-10-18/final-findings-context.md) retains canonical draw dispositions and method-level
resource counters. Each engine used 209,666 fresh scripted policy calls:
65,747 contrastive and 143,919 Shapley, including 1,536 factual calls per
method. There were no live model calls. Native recorded bridge world runs are
216,998 contrastive and 628,674 Shapley, with 249,211 and 719,093 tool dispatches.
CX retains 43,048 and 129,052 completed replay worlds plus 512 preflights per
method. Native reconstruction/probe/closing worlds and CX completed worlds
have different scopes; their counts must not be combined or interpreted as
intrinsic estimator efficiency. Full native glue event histories were not
retained, so those counters are reported recorded resource measurements.
Per-trial elapsed sums include four-worker contention and adapter work.

[Figure 9 exports](../output/upstream-car-figures-2026-10-19-v2/README.md) select retry position 1 after collection, with all
144 mechanism/method/interval/position rows retained in the fraction files.
For p=q=0.5, native contrastive bootstrap covers 62/64, 59/64 and 64/64 at
positions 0, 1 and 2; CX bootstrap covers 62/64, 60/64 and 64/64. Native and CX
normal Shapley cover 63/64, 60/64 and 61/64; Hoeffding covers 64/64 at all three
positions with mean width 0.960323. This disclosed example does not replace the
full condition table or support a pooled superiority claim. The audit supplies
computational checking, not independent human review or live-model causal
accuracy. The study remains a scripted adapter/conditional-calibration result.


## Software provenance and remaining human work

The source repository is public and the current published release is 2.1.1.
The 2.1 line adds composite verifiers, several readback sources, OpenTelemetry
and optional SDK integrations while retaining schema 1.0/the 2.0 API. The
[release record](../output/release-2.1.1-2026-10-19/README.md) and
[source/publication review](../output/claude-2.1.1-paper-review-2026-10-19/README.md)
concern engineering evidence; these additions have no new scientific feature
evaluation here. Retained release checks include three actual-model integration
smoke loops (local-Ollama OpenAI Agents/LangChain, remote-Haiku Claude Agent SDK).
The Claude loop's MCP server is in-process; no external/deployed MCP service or
live OTel collector/backend validation follows. Records/default refund verifier
class body/explanation/target/numerical code match frozen 2.0, but the public
multi-readback verification wrappers changed. The measured compatibility arm
therefore remains frozen 2.0.

The completed current-release review binds source
`3ff37d57e8f8f09cad8c1e3b15a8377f451a2500` and build
`b73ecd00fc9b4b8b3f9b8182aa8ed652419d7e54`: 36 existing runtime paths match
measured 2.0 byte for byte, 12 change and six are added, with no deletions.
All 54 wheel payloads match the recorded build source. Retained publication
receipts state 15:15 UTC on 19 October; the review checked local archive bytes,
not the current registry. No measured 2.1.1 corpus conformance follows.
The historical 1.1.1 metadata-only review and additive 1.2 review remain dated
records. Breaking 2.0 changes schema 0.1 to 1.0, action/assessment cardinality,
time bases, immutable record construction, target matching and explanation.
Its source/wheel comparison is in
`output/claude-2.0-paper-review-2026-10-19/`: 18 old payloads unchanged,
18 modified, one old schema path removed and 12 files added. Several estimator
modules are byte-identical, but replay and evidence transport changed; no
end-to-end 2.0 equivalence follows from those identical modules.

The matched factual, judge, native tool-state transfer and CAR studies remain
1.1.0/schema-0.1 experiments with their original source pins. Earlier studies
retain their own original versions. Analysis uses bound historical sources
rather than weakening a validation guard. A separately frozen offline 2.0
conformance run is now sealed on all 503 retained factual traces. It preserves
the original 504-slot denominator and failed slot without retries or replacements.
The [prospective analysis protocol](../output/v2-migration-protocol-2026-10-19/protocol.json)
has SHA-256 `ec736f462be44c1c442bb4a7b9c071006a1ec7e9dd9915f6e0c4c53d7e196e1e`
and pins 2.0 source `f64bf49f1a99c22f67d8f393a01dea4e6e22fe04`.

The [sealed summary](../output/v2-migration-conformance-2026-10-19/summary.json)
reports 503/503 successful migrations, exact legacy structural projections and
schema round-trips. Fresh isolated 1.1.0 versus 2.0 verification agrees on all
503 canonical states, origins, action-linked outcomes, receipt identities and
assessment alignments; full legacy receipt projections also agree. This includes
72 unknown states, alongside 257 satisfied and 174 violated states. Alignment
remains 48 consistent, 108 contradicted and 347 unassessable, with no newly lost
assessability. All 503 receipts reproduce; migrated target matches are nonempty
for 144, empty for 287 and unavailable for 72. Legacy clock origin remains
unrecoverable, recorded as `relative_ms`.

Exact diagnosis-code lists differ on 275/503 traces and match on 228/503, in both
the migrated and fresh explanations. Independent evidence arithmetic identifies
`UNASSESSABLE_ASSESSMENT` additions on all 275 and `CONSISTENT_OUTCOME`
removals on 24 of those traces. These changes are retained rather than normalized
away; canonical agreement is not complete explanation identity. The
[completion receipt](../output/v2-migration-conformance-2026-10-19/completion-receipt.json)
records zero processing errors, zero new model calls and unchanged historical
inputs. The [independent saved-artifact audit](../output/v2-migration-audit-2026-10-19/README.md)
completed 71,383 checks with zero errors, using saved artifacts and public-evidence
arithmetic without framework/runner execution. This computational check is not
independent human validation.

This is post-hoc compatibility on an exposed single-action refund
corpus, not accuracy, held-out generalization, validation of general 2.0
multi-action/polling/async/retry behavior, or validation of the current 2.1.1
composite/OTel/SDK additions.

The raw studies were copied byte-for-byte into a separate paper worktree so
package development can continue independently. Absolute paths in original
protocols describe the original execution location and are preserved. A
relocated integrity audit resolves relative artefact paths and checks their
hashes; it does not pretend to rerun a location-bound frozen collector.

An offline blinded review package contains the 17 unique public evidence
patterns, an explicit rubric and blank labels. No human labels have been
collected. Its primary human-review denominator is 17; expanding with the
retained 84-trace weights would be descriptive only. A second pack retains all
84 cards for trace-by-trace audit. These packs prepare the remaining review;
they do not satisfy it. Venue selection, an immutable long-term archive and
any full autonomous-agent evaluation remain separate decisions/work.
