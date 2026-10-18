# Pinned upstream CAR comparison on the scripted-simulator refund game

This is an isolated research experiment. It imports the authors' unmodified
CAR v0.2.0 source at
[`db90fa28b97164c35e7c524e4597b8cbdb3035af`](https://github.com/jaineet17/causal-agent-replay/tree/db90fa28b97164c35e7c524e4597b8cbdb3035af),
dated 9 July 2026. The paper is [CAR v1](https://arxiv.org/html/2606.08275v1),
dated 6 June 2026. This distinguishes the executed implementation revision from
the article version. No upstream source enters the framework wheel, and no
GitHub Actions or live model calls are used.

## Question and design frozen before collection

Can Consequa-X's independently implemented decision replay adapters recover the
same scripted-simulator game, sampled decisions and signed estimates as the actual
upstream contrastive and Shapley implementations? What uncertainty, refusal and
computation do the implementations report at a fixed sampling design? This is
implementation compatibility and conditional simulation calibration, not a
claim that Consequa-X outperforms CAR or an external-domain benchmark score.

`scripts/run_upstream_car_study.py` has separate `plan` and `run` commands.
The default plan uses 64 repeats in each of eight mechanisms, contrastive
K=32, and 32 forward/reverse Shapley pairs with one fresh draw per coalition
occurrence. Sixteen additional independent draws at each endpoint run before
both Shapley implementations. There are 1,024 paired groups and 2,048 engine
trials; each retains 96 contrastive or 288 Shapley planned draw slots. Repeats
are simulated draws within fixed mechanisms, not 512 independent tasks.

The frozen `workers` setting defaults to four. Complete paired groups run in
independent spawn-based processes on Windows, each with its own upstream
imports and refund environment. Seeds are allocated by schedule index before
dispatch and do not depend on worker completion order. Only the parent writes
exclusive trial paths; final inventories and summaries follow schedule order.
Integration compares serial and parallel semantic digests after excluding
elapsed-time fields. Timings under concurrent CPU contention are descriptive
execution costs, not an intrinsic speed ranking between estimators.

At nominal .95 coverage, 64 repeats give a binomial Monte Carlo standard error
of about .027. This is modest descriptive precision and does not establish
calibrated 95% population coverage or superiority. Every available coefficient
is compared to an independently enumerated population reference; unavailable
coefficients never count as covered. Coverage among available repeats and
covered/planned yield have separate denominators. No pooled independent-task
confidence intervals or unplanned significance tests are produced.

The eight cases are selection/retry probabilities (.5,.5), (.2,.8), (.8,.2),
(1,1); (.5,.5) with idempotency; missing provenance; lagged readback; and a
four-call budget control. The first five use the state consequence target.
The missing-provenance case uses supported action-linked satisfaction, so its
unknown evidence matters. Lag and budget controls use state satisfaction.
The zero-effect/dummy cases retain the terminal stop as a factual player.

The factual refund/retry/stop is a declared intervention at reserved model
phase keys, matching the existing scripted refund interaction experiment. It
is not a naturally sampled factual episode or evidence about model failure
frequency. All continuations invoke the same `RefundInteractionPolicy`,
public request schema, exactly-one-refund contract, fresh payment world and
production readback/verifier. The policy receives no evaluator truth or
readback. The exact reference independently enumerates the four Bernoulli
selection/retry combinations and their simulated refund counts; it does not
read sampled estimates or ask a model to judge them.

For p=q=.5 without idempotency, the reference Shapley vector is
[-.125,.375,0], the endpoint difference is .25, and contrastive effects are
[-.25,-.5,0]. These explain different estimands and signs. Neither vector is a
set of normalized responsibility percentages.

## Matching and declared adapter changes

The native functions are
[`contrastive_attribution`](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/contrastive.py)
and
[`shapley_attribution`](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/shapley.py).
Their algorithms, NumPy bootstrap stream, SciPy normal quantiles and reverse
permutation pairing are unchanged. CAR's `n_permutations` counts averaged
forward/reverse pairs here. Native percentile bootstrap is the primary CAR
contrastive interval; native normal intervals are the primary CAR Shapley
intervals. CX bootstrap/normal and conservative Clopper-Pearson/Hoeffding
alternatives use the same recorded CX draws without new calls.

Both engines use the same world seed, factual intervention, fresh branch phase
keys and permutation order. This deliberate coupling validates request,
decision, readback and point-estimate parity. Bootstrap numerical intervals
can differ because CX uses Python's random stream and the upstream uses
NumPy's stream. Interval-stream differences are not evidence of different
causal estimands. Shared random draws do not establish live-model determinism.

CAR's native positional coalition engine ignores held positions after a
normal terminal action. Therefore this study uses CX's explicitly named
`on_reach` game, not its stricter unreachable-position refusal game. Refund
and retry become native tool actions; stop becomes native final. Typed public
policy requests are transported in synthetic CAR messages. This is an adapter
to the same scripted policy, not a provider-native Ollama recording.

CAR exposes no environment-factory hook. The serial adapter reconstructs a
fresh production payment world from its current deterministic decision prefix
at every transition, then resets that prefix after every scored rollout. It
never caches coalition payoffs or reuses a sampled continuation. Extra glue
worlds, deterministic decision reuses, tool dispatches and glue elapsed time
are counted separately from fresh stochastic policy calls. Total trial wall
time includes the adapter's overhead, factual capture, inference and readback.
Equal actual-policy-call caps do not mean equal total computation.

The native `Budget` charges whole coalition rollout batches, rather than
fresh policy calls. Its charged path rollouts are retained separately. A
second wrapper shares an actual-call cap across factual recording, supplemental
endpoints and fresh continuation decisions, exactly as CX does. Held decisions
cost zero fresh calls. The four-call control cannot silently increase its cap.
Upstream Shapley can return a partial vector after budget truncation; this raw
diagnostic is retained but excluded from primary numeric results.

CAR has no abstention outcome. The adapter records `unavailable` on unknown
readback only to allow complete draw collection. Native internal coefficients
that treat this label as not-bad are explicitly ineligible diagnostics. A
complete-method wrapper emits primary estimates only if the factual target
and **every planned draw** are known and complete. The same gate applies to
CX. Unknown, invalid, failed, unstarted or partial work cannot gain a numerical
advantage by dropping draws. A finite all-known sample does not make a
population game with positive unknown mass reference-eligible.

Independent endpoint sampling is a declared research-wrapper addition for
native CAR, matched to the CX adapter's extra endpoint overhead and seed
schedule. It changes no native Shapley path estimator. Endpoints and path
rollout counts remain separate. All semantic draw mismatches stop collection
and preserve the receipts, except predeclared budget-control differences in
the engines' start/refusal timing, which are retained for inspection.

## Reproducible isolated execution

Use Python >=3.12 with numpy, scipy, pydantic and structlog in a separate research
environment. Record the resolved dependency versions. Keep the framework's
installed runtime environment unchanged. Fetch the upstream commit into a
separate ignored checkout; the loader refuses a wrong or dirty revision and
records all imported-source hashes. The upstream metadata declares Apache-2.0;
this experiment fetches it rather than redistributing its source in our wheel.

After reviewing and committing the harness, freeze a new protocol:

```powershell
<research-python> scripts/run_upstream_car_study.py plan --source-revision <committed-source> --output <new-protocol.json>
<research-python> scripts/run_upstream_car_study.py run --protocol <new-protocol.json> --upstream-root <pinned-clean-checkout> --output <fresh-study-directory>
```

The runner verifies the frozen local source hashes and source Git revision,
including its tests and this design document, and refuses changed interpreter
or numpy/scipy/pydantic/structlog versions recorded in the prospective protocol.
It then creates a new destination. It never overwrites or resumes an interrupted
trial. Retained integration checks use smaller settings in temporary paths;
they are not final-study observations and do not choose successful seeds.
Integration executes in the reserved 80,000,000 key window and size/timing
profiling uses 90,000,000; the default final study reserves 70,000,000 onward.
The same local source/environment bindings and all upstream source hashes are
checked again before any completion manifest is written.
If a worker, semantic comparison, or source binding fails, no group is
redrawn. The parent stops new dispatches, drains already dispatched work, and
preserves completed engine files with explicit failed and unstarted group
dispositions. An incomplete receipt has file hashes and no completed manifest.

Each trial is an exclusive deterministic-timestamp `.json.gz` file containing
the complete planned-slot inventory, reached public policy requests/replies,
actual-call counts, semantic outcomes, actual readback observations and
verification evidence, plus completed trace hashes. It retains the factual
trace in full. Counterfactual traces are reconstructible from their retained
decision receipts and bound source; their full duplicated event histories are
not saved. This lossless compact format avoids a large single Git file and
reduces disk use. Raw upstream diagnostics, wrapper primary estimates,
execution overhead and refusal gates are distinct fields.

The paired audit unwraps CX's additional held-reply receipt metadata to compare
the original factual reply metadata with CAR's. It retains both original raw
receipts unchanged. Public request bytes, decisions, fresh metadata, response
and readback evidence, actual calls and point estimates must still agree.

Final outputs include per-coefficient conditional error/coverage summaries,
paired semantic validation, all exclusive trial files and a SHA-256 manifest.
Missing completion manifests indicate incomplete collection. A manifest checks
bytes, not authenticity. Independent review and any paper integration follow
collection; the new design alone does not finish the paper or establish
cross-domain or human-annotated validity.
