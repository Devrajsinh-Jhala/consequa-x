# Audited external LIMBO results

Protocol commit: `8b25d4c7769c5c593333c9d3eeeceb8ae001dba4`.

12 base instances; 24 task/fault conditions; four arms; 96 planned slots.

| Arm | Planned | Grades available | Error returns | TS true/planned | EOS true/planned | Missing grades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 24 | 24 | 0 | 21/24 | 16/24 | 0 |
| SDK retry | 24 | 24 | 0 | 24/24 | 14/24 | 0 |
| Native guard | 24 | 24 | 1 | 21/24 | 16/24 | 0 |
| ConseqaX guard | 24 | 24 | 2 | 20/24 | 15/24 | 0 |

All-planned numerators retain missing/error dispositions. An error return can still have an audited physical grade after native flush.

| Arm | Execute attempts | Public verifications | Explicit waits | Model dispatches | Rows with complete work accounting |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 151 | 0 | 0 | 124 | 24/24 |
| SDK retry | 157 | 0 | 10 | 126 | 24/24 |
| Native guard | 168 | 3 | 0 | 156 | 24/24 |
| ConseqaX guard | 159 | 3 | 0 | 146 | 24/24 |

Observed cost totals exclude unquantified work in rows without complete audited accounting. Boundary advances are not policy waits.

## Matched within-world EOS contrasts

| Left − right | Planned numerator difference | Both grades available | Left-only true | Right-only true | At least one unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| vanilla − sdk_retry3 | 2 | 24 | 3 | 1 | 0 |
| vanilla − guard | 0 | 24 | 2 | 2 | 0 |
| vanilla − conseqax_guard | 1 | 24 | 3 | 2 | 0 |
| sdk_retry3 − guard | -2 | 24 | 1 | 3 | 0 |
| sdk_retry3 − conseqax_guard | -1 | 24 | 2 | 3 | 0 |
| guard − conseqax_guard | 1 | 24 | 1 | 0 | 0 |

## Scope and limitations

- This is a finite purposeful coverage matrix: 12 base instances, 24 task/fault conditions and four arms; 96 slots are not independent tasks.
- Primary TS/EOS numerators count only independently replayed true native grades over every planned slot. Missing grades remain unknown, and do not count as success.
- Operational means audited native-grade availability, including error returns after native flush; execution_success is a separate secondary endpoint.
- Comparisons are paired within the same native world. Clean/fault base parameters match, but native random seeds depend on mode; clean/fault worlds are not identical random worlds.
- Strata use assigned faults, never post-treatment fault triggering. Template and domain variation are descriptive; no task-population intervals, significance, equivalence or superiority inference is made.
- The ConseqaX arm is an actual receipt integration of the same native guard. Declared policy conformance supports integration, not independent algorithmic novelty or proof that separately generated trajectories must coincide.
- Native EOS is TS and zero recorded duplicate executions, not universal exactly-once. Native upsert/status accounting and target scope can hide some repeat writes; exact_state checks target live counts only.
- Native dup_compensated is max(0, dup_executed minus dup_live), not a count of compensation calls. Extraneous writes and collateral records are reported separately from EOS.
- Boundary execute/verify/advance/flush entries count attempted calls, not physical effects. Advance includes nested tool latency; only outer advances count explicit policy wait attempts.
- Native virtual time and observed host wall time are separate descriptive costs. This serial local run does not identify a general runtime-speed advantage.
- Cost sums cover rows with audited complete accounting. Failed/unstarted slots can have additional unquantified observed-prefix work; missing actual work is not zero.
- Token sums retain known usage even on failed invocations. Missing usage stays unknown; cached input tokens are a subset of input tokens and are never added twice.
- SDK receipts verify current native public reports with unknown origin; they do not establish production service durability, settlement or causal responsibility.
- The independent audit recomputes receipt contents and replays the unchanged native guard and effects. It does not independently re-execute the SDK or reconstruct tokenizer identities from scratch.
- No humans, paid inference or GitHub Actions were used in this analysis.
