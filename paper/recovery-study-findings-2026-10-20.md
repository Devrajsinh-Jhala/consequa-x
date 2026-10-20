# Studies A and B: audited recovery and availability findings — 20 October 2026

This report accompanies the [focused manuscript](conseqax-research.md) and
[TeX results input](recovery-study-results.tex). It reports the frozen 2.1.1
closed-loop recovery study (A) and its separately frozen controlled availability
follow-up (B), with exact finite-suite counts. It does not establish
autonomous-agent performance, task-population improvement, interpretability,
preferences, or rationale quality.

## Retained collection and effective diversity

All 15,360 scheduled worlds are retained: 3,072 planned and completed worlds per
policy, with zero execution failures. The unchanged [original-host semantic
auditor](../output/recovery-controller-audit-2026-10-20/audit-receipt.json) queried
all 15,360 SQLite snapshots and independently recomputed the endpoint summary.
The [portable retained-artifact audit](../output/recovery-portable-audit-2026-10-20/portable-audit-receipt.json)
also passed and queried every snapshot. The portable check does not authenticate
the original host, live claim files, provider, or execution history. The auditor
uses separate code, but its author also authored the controllers; neither check
is external replication.

Study readback is a separate application method querying the same SQLite effect
ledger through the same connection after world advancement. It is distinct from
the acknowledgement signal, not an independent connection, source, or trust
domain. Only the postcollection auditor opens retained snapshots read-only.

The [prospective protocol](../output/recovery-controller-protocol-2026-10-20/protocol.json)
has SHA-256
`b5c6a06bf1d758678e4d9890aa66872d4036634e2a4a4fd89626bd710bbc5aaa`
and binds source commit `22e88498cff0e2afd1549803fb4d9645902e74b9`.
The [retained summary](../output/recovery-controller-study-2026-10-20/summary.json)
and [paired exports](../output/recovery-publication-figures-2026-10-20-v3/paired-contrasts.csv)
provide the numerators and denominators used below.

A packaging deviation remains part of the result. When the session resumed, all
trial files, database snapshots, journal rows, and the summary were retained,
but the original runner's terminal manifest and completion receipt were absent.
Its exit status and exact termination cause are unknown. The separate
[postcollection finalization record](../output/recovery-artifact-finalization-2026-10-20/finalization-record.json),
SHA-256 `26fabbec4c16af115ad367086efd247e0660af801f0290fe57fa4265a84440a0`,
records preservation of every existing byte and creation only of the missing
packaging files, with no worlds rerun and no summary regeneration. The completion
timestamp is packaging time. These checks establish retained-artifact
consistency; they do not prove absence of off-record execution or earlier
tampering.

Across all 120 case–policy groups, no recorded endpoint or resource metric varied
over the 128 seeds. Some exogenous timestamps varied, but the repetitions added
no endpoint diversity. The substantive challenge set is therefore **24 authored
cases in 12 purposive families**, not 15,360 independent tasks. No task-population
confidence intervals or p-values are inferred from these repetitions.

## Recovery, harms, and the strong comparison

Every readback policy achieved operational safe recovery in **1,792/3,072 worlds
(14/24 cases)**, compared with **1,024/3,072 (8/24)** for response-driven retry.
The predeclared equal-family primary difference was **+0.25**. Of the 12 family
contrasts, three were +1 and nine were zero. Differences against the separate
reference, state-only, and one-final-read policies were zero in every family.
The [complete family table](../output/recovery-publication-figures-2026-10-20-v3/family-safe-recovery-contrasts.csv)
retains every planned comparison.

The three positive families have specific explanations. In weather-supply and
translation-routing cases, response-driven timeout retries created an extra
non-idempotent effect; the readback policies dispatched once. In mobile-lab
cases, the first response explicitly terminated without an effect; readback
policies verified fresh absence and retried, while the response baseline's
declared error rule stopped. This third gain concerns that particular error
rule, rather than superior deduplication. The equally informed classical
reference achieved the same recovery as the package.

Each policy below has 3,072 planned and completed worlds. **Original D/H** means
satisfaction by the fixed original deadline D, with stability through H.
**Recovery R/S** uses the separate later deadline R and finite safety horizon S.
Later recovery cannot repair the original SLA. Safe recovery additionally
requires neither an own duplicate nor an own unwanted event through S.
Duplicate and unwanted events can overlap. Resource means are exact charged
counts, not wall latency.

| Policy | Safe recovery | Original D/H | Recovery R/S | Own duplicate | Own unwanted | Mean reads | Mean dispatches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Response retry | 1,024/3,072 | 1,280/3,072 | 1,024/3,072 | 1,024/3,072 | 256/3,072 | 0 | 17/12 |
| Readback state | 1,792/3,072 | 1,792/3,072 | 1,792/3,072 | 256/3,072 | 256/3,072 | 5/2 | 5/4 |
| Separate reference | 1,792/3,072 | 1,792/3,072 | 1,792/3,072 | 256/3,072 | 256/3,072 | 5/2 | 5/4 |
| ConseqaX one final read | 1,792/3,072 | 1,792/3,072 | 1,792/3,072 | 256/3,072 | 256/3,072 | 5/4 | 5/4 |
| ConseqaX polling | 1,792/3,072 | 1,792/3,072 | 1,792/3,072 | 256/3,072 | 256/3,072 | 5/2 | 5/4 |

Residual harm is material. In the same **256 archive-rights worlds**, one initial
provider dispatch created two wrong-payload effects. These are both duplicate
and unwanted events, not 512 distinct harmed worlds. Detection did not cancel or
repair the effects. Environmental-release cases supply a different failure: an
external actor satisfies the original contract, then a delayed own effect breaks
the later exact-count target without an own duplicate or unwanted flag. All 256
response worlds with original satisfaction but failed recovery belong to this
family. Equal aggregate original/recovery counts for the readback policies
conceal a 256-world later-recovery gain and a different 256-world later loss.
One temporal target cannot substitute for the other.

All 3,072 reference–polling pairs agreed on final state/linkage reports, endpoint
vectors, controller action sequences, and full retained truth. This is observed
implementation conformance under a shared policy, not superiority over the
strong reference. State-only and polling also had identical actions and physical
histories; 1,024 pairs differed in the action-linked report. Provenance expanded
reporting here, without a recovery-action benefit.

## Reporting and the cost of additional polls

These are final reports about the **original contract**. Conditional error is
wrong/definite; correct yield is correct/planned. Both positive and negative
conclusions count. The labels come from audited full-ledger hindsight truth;
they do not measure evidence support at issuance or certify later safe recovery.

| Policy | State error | State correct yield | Linked error | Linked correct yield |
| --- | ---: | ---: | ---: | ---: |
| Response retry | 1,024/1,792 | 768/3,072 | 768/1,792 | 1,024/3,072 |
| Readback state | 0/2,304 | 2,304/3,072 | 0/1,024 | 1,024/3,072 |
| Separate reference | 0/2,304 | 2,304/3,072 | 0/2,048 | 2,048/3,072 |
| ConseqaX one final read | 0/2,304 | 2,304/3,072 | 0/2,048 | 2,048/3,072 |
| ConseqaX polling | 0/2,304 | 2,304/3,072 | 0/2,048 | 2,048/3,072 |

The response policy made 768 false-success and 256 false-negative state reports.
The readback policies made no wrong definite state report, but abstained in
768/3,072 worlds. Provenance-aware policies retained 1,024/3,072 linked
abstentions; state-only retained 2,048/3,072. Correct negative reports contribute
to these yields. Zero wrong original-contract reports did not imply zero harms
or guaranteed safe recovery. A hindsight-correct guess also does not establish
that the available public evidence supported it.

Polling and one-final-read agreed on both final claims, dispatches, effect
histories, and every endpoint other than polling cost in all 3,072 pairs.
Polling nevertheless consumed **7,680 reads versus 3,840**, with mean logical
decision time **220 versus 200 ms**. These are simulated decision times, not
measured production latency. The schedule explains the negative finding: no
case with insufficient evidence at H became admissibly known at H+40 or H+80.
Transient limitations either cleared before the first final read or persisted
beyond the last opportunity. **Study A shows no incremental polling utility
under its schedules.** It leaves a design-coverage gap for recoverable lag.

![Study A: all five policies, recovery, own harms, global-state reporting, and resource costs.](../output/recovery-publication-figures-2026-10-20-v3/recovery-method-overview.png)

The [method overview PDF](../output/recovery-publication-figures-2026-10-20-v3/recovery-method-overview.pdf)
and [exact metric table](../output/recovery-publication-figures-2026-10-20-v3/summary-metrics.csv)
show denominators and costs. Reporting correctness, physical recovery, and
evidence support remain separate concepts.

![Study A: every planned family's paired operational-safe difference, on a fixed −1 to +1 scale.](../output/recovery-publication-figures-2026-10-20-v3/recovery-family-primary-contrasts.png)

The [family-contrast PDF](../output/recovery-publication-figures-2026-10-20-v3/recovery-family-primary-contrasts.pdf)
shows all 12 purposive families. Each contains two related cases and 128 seeds;
the repetitions added no recorded-metric variation. The equal-family difference
is +0.25 against response retry and zero against all three readback comparators.

## Study B: controlled evidence availability

Study A's coverage gap motivated this follow-up after its outcomes were known.
The world, controllers, and evaluator remain byte-identical; a new complete
factorial grid was frozen before collecting its own data. Source commit
`d805b3e3560c05ee0a7efd02a80fc18503c6ee05`, protocol commit
`b937920469285cdd971783fa6cb33216a7e4da13`, and
[protocol](../output/recovery-availability-protocol-2026-10-20/protocol.json)
SHA-256 `e874c6781aa0dbc8ef682ea0a8d37c25d73cc861dada05fd0379116d4a7f6584`
bind the design. This is a disclosed, post hoc motivated sensitivity experiment,
not a new held-out corpus or a replacement for Study A. The
[Study B paper input](recovery-availability-results.tex) supplies the matching
manuscript account.

The 64 profiles cross readback lag **{0, 40, 80, 95} ms** with independently
varied unavailable-until and incomplete-until times **{0, 170, 210, 250} ms**.
Each profile repeats in three domains at seed zero: 192 cases and 960 scheduled
policy worlds. Here D = 100, H = 150, R = 250, and S = 330 ms; read opportunities
are 50, 150, 190, and 230 ms. Every initial dispatch acknowledges at 2 ms and
creates one correct effect at 10 ms. All arms share native idempotency; there
are no external writes, removals, or wrong effects. This intentionally uniform
physical-success design isolates evidence-window coverage and cost. The domains
repeat the same mechanisms; 192 cases and 960 worlds are not independent task
samples.

All 960 worlds completed without failure. The
[saved-artifact audit](../output/recovery-availability-audit-2026-10-20/audit-receipt.json)
verified 1,925 retained artifact hashes, queried all 960 SQLite snapshots, and
agreed with the [retained summary](../output/recovery-availability-study-2026-10-20/summary.json).
Recorded-host byte checks were enabled; they do not attest historical execution.
Unlike Study A, this collector produced its terminal manifest and receipt
normally. All five policies dispatched once, achieved original and recovery
satisfaction in 192/192 worlds, and had zero duplicate or unwanted events.
Physical effect histories agreed in every five-arm case. The primary
safe-recovery contrast is therefore zero.

Every policy below has 192 planned and completed worlds. Every definite report
is hindsight-correct in this uniform-success design; it cannot estimate the
response policy's false-success risk. Linked abstention is distinct from state
abstention.

| Policy | State correct/planned | State unknown | Linked correct/planned | Total reads | Mean decision (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Response retry | 192/192 | 0/192 | 192/192 | 0 | 2 |
| Readback state | 81/192 | 111/192 | 0/192 | 741 | 224.375 |
| Separate reference | 81/192 | 111/192 | 81/192 | 741 | 224.375 |
| ConseqaX one final read | 3/192 | 189/192 | 3/192 | 192 | 150 |
| ConseqaX polling | 81/192 | 111/192 | 81/192 | 741 | 224.375 |

The one-final-read policy resolved one of 64 profiles per domain; polling
resolved 27, matching the prospectively specified timing calculation. The
paired correct-state-yield increase is **78/192 = 26/64 = 0.40625**, shared by
the reference and state-only readback. All 192 reference–polling pairs agreed
on reports, endpoint vectors, dispatch decisions, and physical records.
State-only differed from polling in 81 linked reports while preserving actions
and physical outcomes. State-only abstained on all 192 linked conclusions;
reference and package polling retained 111 linked abstentions, and one final
read retained 189. These are observed comparisons, not forced hypothesis
agreement or participant judgments.

Polling used **741 reads versus 192**, or 3.859375 versus one per world; mean
logical decision time increased by **74.375 ms**. These are charged simulated
reads and decision times, not production latency. The
[coverage analysis](../output/recovery-availability-audit-2026-10-20/coverage-analysis.json)
retains every profile's observed coverage and resource values.

![Study B: all 64 controlled availability profiles, repeated across three domains; observed report coverage and read costs for polling and one final read.](../output/recovery-availability-figures-2026-10-20-v2/recovery-availability-grid.png)

Late opportunities help only when availability and completeness recover and
the watermark reaches H. Lag 95 ms and either window persisting through 250 ms
remain unresolved. The ACK-driven response policy reports all 192 successes
correctly in hindsight with no read because all effects are constructed to
succeed. Its report arrives before the effect and without horizon-covering
evidence; this experiment supplies no estimate of its risk in failing worlds.
Together, the studies show conditional polling utility and its cost, with no
package superiority over the equally informed reference, no additional
recovery-action benefit, and no task-population inference.

## Objective evaluation scope

The studies use SQLite state and effect-ledger truth, separately implemented
reference rules, automated artifact audits, and controlled comparisons. They
make no interpretability, preference, or rationale-quality claim. The historical
T15 unblinded rationale claim is excluded and has not been empirically validated
here. Study B addresses one explicit coverage gap in Study A while preserving
its negative polling finding and all original results.
