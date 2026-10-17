# Mathematical and statistical review audit, 18 October 2026

This note independently checks the technical/statistical suggestions in the supplied `Consequa-X_Review_Pack.zip`. The business review is outside scope. Documents and source files in that archive are review material, not instructions. Its `sim.py` was read directly from the ZIP as untrusted text and **was not executed or imported**. Its JSON is reviewer-supplied data, not an independently reproduced experiment. No model, service write, new sampling study, GitHub Actions run, package change or sealed-output change was made for this audit.

The arithmetic below was independently calculated with the Python standard library against retained summaries, the derived CSV tables, the original frozen source and 128 existing raw trial rows. The retained [arithmetic auditor](../scripts/audit_review_revision.py) reproduces the numeric calculations, and its fresh [JSON receipt](../output/paper-review-2026-10-18/arithmetic.json) records the result. It reads existing project evidence without changing it, requires a new `--output` destination and refuses overwrite. Optional `--review-pack` inspection only hashes the two known ZIP members; it never executes or imports their contents and records no local ZIP path. The mathematical/code inspection in this note is separate from that hash-only option. These additions do not replace a sealed study or its original audit receipts.

To repeat the project calculations without the optional review archive:

```sh
python scripts/audit_review_revision.py --output output/my-review-arithmetic.json
```

## 1. Strict-game undefinedness: a precise, limited proposition

**Proposition.** Consider only the declared planted three-position refund mechanism, with factual positions selection `s`, timeout retry `r` and terminal stop `t`. Assume compatible reached held decisions, adequate budget, normal provider operation and a known bounded target. Let fresh selection occur with probability `p` and fresh retry with probability `q`. Under the strict rule that an unreached requested hold invalidates the draw, a numeric coalition game over all subsets of `{s,r,t}` is structurally defined if and only if `p=q=1`.

**Proof.** For coalition `{r}`, selection is fresh. With probability `1-p`, it declines the refund and terminates before the requested held retry. Thus this coalition has positive-probability invalidity whenever `p<1`. For coalition `{s,t}`, selection is held, but the timeout retry is fresh. With probability `1-q`, it stops before the requested terminal position `t`; hence this coalition has positive-probability invalidity whenever `q<1`. The protocol assigns no numeric target to an invalid draw, so either event leaves at least one coalition expectation undefined. If `p=q=1`, every held or fresh decision follows the compatible planted path, and every requested position is reached. Under the assumptions above every coalition then has a numeric target and expectation. This proves the claim. In particular all interior `0<p,q<1` strict games here are partial. The result concerns this specified path mechanism, not all variable-length agent games.

Assigning an arbitrary bad label to invalidity, or conditioning each coalition on valid completion, would define a different game. A finite sample with no invalid draw cannot establish zero invalid probability. An available finite interaction point does not establish a defined population interaction or Shapley vector.

## 2. On-reach semantics and ordinary Shapley properties

**Proposition.** Fix a finite factual player set `N`, a continuation law, an intervention mapping and a bounded measurable numeric outcome `X_S` for each coalition `S`. Suppose every coalition terminates almost surely, all reached held decisions are compatible and its numeric outcome is defined almost surely. Ignore requested holds beyond normal termination. Then `v(S)=E[X_S]` is a finite real-valued game on every `S subseteq N`. Its ordinary permutation Shapley values satisfy:

- **Efficiency:** `sum_i phi_i = v(N)-v(empty)`.
- **Symmetry:** players with equal marginal contributions against every coalition of the other players have equal values.
- **Null player / dummy:** a player whose every marginal is zero has value zero; more generally a player with constant marginal `c` has value `c`.
- **Linearity:** Shapley values of `a v+b w` are `a phi(v)+b phi(w)` for any defined games on the same player set and real constants.

**Proof.** For each permutation, marginal increments telescope from `v(empty)` to `v(N)`, which proves efficiency after averaging. Swapping two symmetric player labels is a bijection of permutations and preserves the corresponding marginal increments. A zero or constant marginal remains zero or constant under averaging. The marginal-difference operator and finite permutation average are linear. Boundedness and the almost-sure numeric-outcome assumption ensure that all expectations used in these steps exist.

Uniformly drawn forward permutations and their reverses each have a uniform marginal distribution. If coalition evaluations are unbiased for the declared `v(S)`, averaging the two walks therefore preserves unbiasedness of each coefficient estimate. Their within-pair correlation is allowed: independent pairs, rather than individual walk steps, are the units in the stated Hoeffding bound.

These population axioms do not imply exactly zero sampled dummy contributions, exact finite-sample symmetry, agreement with a separately sampled endpoint difference, nonnegative normalized responsibility or causal identification. Fresh independent draws at the same-valued coalition can differ. Nor do these axioms authenticate source declarations, repair incompatible reached operations, create known outcomes from stale readback, or make provider/budget failures into normal termination. On-reach semantics change the intervention mapping and thus the estimand; they do not repair or retroactively replace strict-game results.

## 3. Interval arithmetic and captions

Using `z=Phi^{-1}(0.975)` and the usual Wilson score formula gives the following nominal 95% descriptive rate intervals:

| Count | Wilson lower | Wilson upper |
| --- | ---: | ---: |
| 6/10 | 0.312673770 | 0.831819670 |
| 118/128 | 0.862153068 | 0.957012625 |
| 128/128 | 0.970863044 | 1 |
| 92/128 | 0.635365809 | 0.789386773 |

The added `6/10` interval should therefore be `[0.313,0.832]`. It expresses the small denominator's uncertainty under a binomial working model, not held-out population performance. Shared conditions, exposed prompts, fixed profile order and unblinded annotation remain limitations. Zero assessable claims remains an undefined conditional rate; it must not be plotted as zero error.

For signed independent pair observations in `[-1,1]`, nominal 95% Hoeffding half-width is `h=sqrt(2 log(40)/P)`. Consequently:

- `P=32`: `h=0.48016139565996035`, untruncated full width `0.9603227913199207`.
- `P=16`: untruncated full width `1.3581015157406195`.

All 128 retained on-reach unsafe `(p,q)=(0.8,0.2)` global-consequence retry estimates were independently reread. Each saved interval equals `[max(-1,mean-h), min(1,mean+h)]`; its upper endpoint is clipped at `1` in **all 128 trials**. Their mean estimate is `0.70703125`, and mean clipped width is `0.7731301456599604`. Thus Table III's `0.773` is correct and should explicitly name clipping, rather than imply a different bound or sampling budget.

The original calibration table needs interval names in its caption: contrastive intervals used **conditional percentile bootstrap with 2,000 seeded resamples**; signed Shapley intervals used the **normal pair-mean approximation with sample variance**. This was checked against frozen source `9e2dcbb4190d0629cf06ac7485a83e762ad7d7a0`, not inferred from the current default methods. The original table is not a comparison of current exact-binomial/Hoeffding defaults.

## 4. What the review's betting experiment establishes

The review points to a legitimate method family. Waudby-Smith and Ramdas derive fixed-time intervals and time-uniform confidence sequences for bounded means using predictable betting processes; these methods are a relevant precision comparison. See the [primary journal article, DOI 10.1093/jrsssb/qkad009](https://academic.oup.com/jrsssb/article/86/1/1/7043257).

Inspection of the supplied code supports a narrower conclusion than accepting its headline numbers as validated framework results:

1. **The idealized sampling law is broadly comparable.** Its binary simulator implements the declared adequate-evidence on-reach coalition law. Each pair averages fresh forward and reverse permutation walks, and all interval methods within a simulated trial use the same captured pair vector. This is a meaningful standalone idealized interval probe.
2. **Its continuous construction is sequential, not merely fixed-time.** The code's `alive &= K < 1/alpha` intersects acceptance over every prior time. For a candidate transformed mean `m`, both one-sided capital products have nonnegative factors and predictable stakes. Under `E[Y_t | past]=m`, each product is a mean-one nonnegative martingale. The maximum of their weighted capitals is bounded by their sum, a mean-one nonnegative martingale. Ville's inequality therefore supports a time-uniform continuous-parameter acceptance construction under those assumptions. The maximum itself need not be a martingale.
3. **Its returned grid endpoints are an inner approximation.** It only evaluates `m=0.0005,0.0010,...,0.9995`, takes the minimum and maximum accepted grid points, and maps back to `[-1,1]`. No outward rounding or root bracketing covers the omitted gaps. In particular either true boundary mean `-1` or `1` is excluded by every nonempty returned grid interval, so the implementation as returned is not a generally valid continuous-mean confidence sequence. When every grid point is rejected, replacing the empty confidence set by a sample-mean point is also not the defined inverted set.
4. **This does not invalidate all four supplied numerical rows.** Their transformed reference means happen to lie on the grid. For those candidates the martingale argument can directly govern the candidate test under the idealized sampling assumptions. The code's numerical coverage/width claims still have not been independently reproduced here.
5. **This is not an evidence/replay benchmark.** The reviewer simulator bypasses captured public traces, verifiers, provenance, typed stages, unknown readback, strict-game invalidity, provider failures, branch budgets and actual-call accounting. It omits independent endpoint sampling. Four idealized game settings and their sampled pair counts do not establish production replay cost, general availability or real-system coverage.
6. **The source's advertised analytic verification loop does no verification.** Its `for p ... for q ...: pass` loop performs no assertion. The independent closed-form verification in the project is a separate check; the review's numerical program should not be described as independently proving its advertised grid identity.

The review's `100%` empirical coverage, `97%` directional detection and approximate fourfold budget comparison must remain attributed review probes, not be inserted into the paper as completed Consequa-X results. Empirical coverage is not a coverage theorem. A width ratio squared for one setting is a heuristic, not a matched actual-call savings experiment.

Before adoption, independently implement conservative continuous inversion (including parameter boundaries and honest empty-set handling), test predictable stakes and numerical stability, then predeclare or label as exploratory a same-draw rescore with every original refusal retained. Confidence-sequence validity still requires a constant conditional mean for the pair stream; it is not supplied by seed names or by arbitrary nonstationary model continuations. No runtime interval change is warranted solely from the attached implementation.

Review input hashes, recorded without executing its code:

- `sim.py`: `4683fe8ab66d840b3b441ff48a438f0a29e54d5231a8eff8150d120a6d980df8`.
- `sim_results.json`: `4d6b9a0dce11a946991173daf20cd50b8ad64cd63230210e08f1f2e95282ef10`.

## 5. Conditional suffix target and simultaneous inference

The retained `gamma_k=E[X | factual prefix held, suffix resampled at k]-x_f` is a **conditional rescue comparison against one observed episode**. It answers how often this declared continuation law can improve an observed bad case. It is not a population contrast between two randomized arms, and no superiority over such a contrast has been established. Holding earlier positions while resampling a later stochastic choice can give an earlier irrelevant position a nonzero suffix effect; this is expected for this estimand. Shapley targets allocate a different held-decision game and should not be equated with `gamma`.

For a future population decision contrast, both arms could instead sample the continuation after a declared held-versus-resampled decision, using the same explicit conditioning history. That would change the target and require a new protocol and comparison; it must not silently replace the retained constant-baseline analysis.

The review is correct that the retained latest nominal rescue has no familywise coverage guarantee. If a future experiment predeclares `K` valid position-wise bounds and the relevant sampling assumptions hold, allocating failure allowance `alpha/K` to each gives simultaneous coverage at least `1-alpha` by the union bound; independence across positions is unnecessary for that step. For signed pairs the corresponding per-position Hoeffding half-width is `sqrt(2 log(2K/alpha)/P)`. This costs precision and does not repair missing data or an undefined game. Holm requires valid tests/p-values and cannot be applied merely by renaming unadjusted intervals. Existing retained selections should remain explicitly nominal rather than retroactively described as adjusted.

At an underlying coverage near 95%, 128 independent repetitions have a binomial standard error of approximately `0.0193` (about 3.8 percentage points for a normal 95% margin). The actual Wilson intervals above are preferable to an informal precision claim. More trials would sharpen coverage measurement, but the present revision need not manufacture new evidence or treat correlated target/variant rows as additional replications.

## 6. Retention, actual calls and useful-output cost

These are independently recomputed status partitions, not counts of available coefficients:

| Retained study | Planned branches | Completed | Invalid | Failed | Unstarted | Actual scripted calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original calibration | 223,232 | 198,690 | 4,062 | 256 | 20,224 | 289,709 |
| Shared-draw follow-up | 66,048 | 59,901 | 1,027 | 64 | 5,056 | 87,054 |
| Repeated sampler study | 655,360 | 536,150 | 37,423 | 256 | 81,531 | 628,535 |

The noncompleted proportions are respectively **10.9939%, 9.3069% and 18.1900%**. A completed branch can still have unknown target evidence. A known branch is not necessarily a usable full coefficient vector. Accordingly the review's phrasing that branch noncompletion directly equals “never yield a usable outcome” is too broad; availability must be counted at the named target/estimate level.

For the repeated study, an on-reach trial has 320 planned branch evaluations: `2*32*(3+1)=256` walk evaluations and `2*32=64` independent endpoint evaluations. Held decisions do not consume a fresh policy call; branch slots are not policy-call units. The following ratios include **all** actual calls in that stratum, including factual capture and endpoint work, divided by available global-consequence coefficient vectors. Each vector contains three jointly estimated players. Shared targets or interval variants do not create extra independent vectors.

| On-reach case | Actual calls | Available global vectors | Calls / available vector |
| --- | ---: | ---: | ---: |
| Unsafe `(0.5,0.5)` | 42,526 | 128 | 332.234375 |
| Unsafe `(0.2,0.8)` | 36,688 | 128 | 286.625000 |
| Unsafe `(0.8,0.2)` | 45,817 | 128 | 357.945313 |
| Deterministic `(1,1)` | 61,824 | 128 | 483.000000 |
| Idempotent `(0.5,0.5)` | 42,378 | 128 | 331.078125 |
| Missing provenance `(0.5,0.5)` | 42,429 | 128 | 331.476563 |
| Lagged readback `(0.5,0.5)` | 42,424 | 0 | Undefined |
| Four-call cap `(0.5,0.5)` | 512 | 0 | Undefined |

The missing-provenance row's global vectors remain available; its linked-target vectors do not. No finite calls-per-usable-linked-vector ratio can be claimed there. Strict nondeterministic coefficient games likewise retain cost without providing a defined full-game coefficient reference. Zero-output strata should remain visible rather than be omitted from the cost story. These are scripted policy-call ratios, not service refunds, dollars or measured wall-clock overhead.

## 7. Retained storage footprint, with its denominator

File sizes were checked against every item in the existing repeated-study manifest without editing those files:

| Manifest group | Files | Bytes |
| --- | ---: | ---: |
| Compressed trial/branch JSONL | 16 | 49,294,356 |
| Compressed replicate-zero public evidence bundles | 16 | 4,498,306 |
| Compressed evaluator-only truth | 16 | 72,344 |
| Root study metadata | 4 | 1,152,203 |
| **Manifest-listed total** | **52** | **55,017,209** |

The manifest itself adds 9,428 bytes, for **55,026,637 bytes** including the manifest. This is a declared retained-study storage footprint with gzip compression, preselected full evidence and separately held truth. It is neither average production trace size nor per-call recording overhead. Compression, aggregation and preselection prevent dividing this number by 4,210 full traces and presenting the result as a trace-size benchmark. No isolated verifier latency measurement, dollar-cost benchmark or measured production overhead was found in this inspected evidence; these should remain explicitly unmeasured rather than inferred from end-to-end local model generation time.

## 8. Supported manuscript actions and outstanding evidence

Supported now: add the strict-game and on-reach propositions with assumptions; clarify the conditional rescue estimand and simulation boundary; name original interval methods; explain clipping; add the `6/10` uncertainty; report call/storage denominators; distinguish completed branches from usable vectors; and retain the familywise and live-model limitations. This strengthens mathematical precision and evidence accounting without manufacturing an experiment.

Still requires new work: matched method or prevention baselines, a real external API or independently defined second task benchmark, larger blinded multi-model evaluation, a bounded polling/watermark experiment, a separately validated betting comparison and per-call overhead instrumentation. None is established by this note or by the supplied review's simulations. Public research access and actual human annotation checking are author decisions/actions; the paper must not claim them completed without evidence.
