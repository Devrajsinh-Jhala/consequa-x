# Audited external LIMBO results

Protocol commit: `267cd1a3e846c46c009f20accbf302746e064875`.

12 base instances; 24 task/fault conditions; four arms; 96 planned slots.

| Arm | Planned | Grades available | Error returns | TS true/planned | EOS true/planned | Missing grades |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 24 | 1 | 0 | 1/24 | 1/24 | 23 |
| SDK retry | 24 | 2 | 0 | 2/24 | 2/24 | 22 |
| Native guard | 24 | 2 | 0 | 1/24 | 1/24 | 22 |
| ConseqaX guard | 24 | 1 | 0 | 1/24 | 1/24 | 23 |

All-planned numerators retain missing/error dispositions. An error return can still have an audited physical grade after native flush.

| Arm | Execute attempts | Public verifications | Explicit waits | Model dispatches | Rows with complete work accounting |
| --- | ---: | ---: | ---: | ---: | ---: |
| Vanilla | 3 | 0 | 0 | 2 | 1/24 |
| SDK retry | 7 | 0 | 1 | 4 | 2/24 |
| Native guard | 8 | 0 | 0 | 9 | 2/24 |
| ConseqaX guard | 3 | 0 | 0 | 2 | 1/24 |

Observed cost totals exclude unquantified work in rows without complete audited accounting. Boundary advances are not policy waits.

## Matched within-world EOS contrasts

| Left − right | Planned numerator difference | Both grades available | Left-only true | Right-only true | At least one unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| vanilla − sdk_retry3 | -1 | 1 | 0 | 0 | 23 |
| vanilla − guard | 0 | 1 | 0 | 0 | 23 |
| vanilla − conseqax_guard | 0 | 1 | 0 | 0 | 23 |
| sdk_retry3 − guard | 1 | 2 | 1 | 0 | 22 |
| sdk_retry3 − conseqax_guard | 1 | 1 | 0 | 0 | 23 |
| guard − conseqax_guard | 0 | 1 | 0 | 0 | 23 |

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
