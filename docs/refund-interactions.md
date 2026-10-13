# Refund selection, retry and terminal interactions

This milestone implements the separate games specified in
[variable-length-game-plan.md](variable-length-game-plan.md). It uses the ordinary
isolated payment simulator, its exactly-one-refund contract, and independent
ledger readback. It does not substitute an analytic payoff for the production
outcome adapter.

`RefundInteractionPolicy` plants factual refund, retry and final stop at the
three reserved model phase keys `6 * factual_policy_seed + (0, 1, 2)`. This is a
declared factual intervention, not a naturally sampled factual trajectory.
Every other selection refunds with probability `p`; every fresh timeout retries
with probability `q`; final or non-timeout responses stop. The policy reads
only the typed public request, returned response status, and remaining attempts.
Fault labels, readback and evaluator records are outside its inputs.

The sampler uses a separately seeded `random.Random(model_phase_seed)` draw.
The finite exporter instead enumerates the four Boolean selection/retry choice
pairs. Its policy metadata explicitly says `deterministic_mixture_component`
and records both choices. Their weights are `(1-p)(1-q)`, `(1-p)q`, `p(1-q)` and
`pq`. These are four deterministic components of the declared population law,
not four independent stochastic observations or live-model samples.

Within each factual/replay experiment the public policy identity is unchanged.
Held positions force the captured decision and assessment. The same planted
three-player factual trajectory is used for all eight masks of that component.
Each branch resets its actual factual payment world. Components and games have
separate, predeclared phase windows beginning at world/model schedule key
4,000,000 (model phase keys at least 24,000,000). Both zero-weight and positive
weight components remain in the retained evidence.

For the on-reach game with no idempotency, the expected bad consequence rates
are `1-p(1-q)` for neither decision held, `q` for held selection, `1` for held
retry, and `1` for both held. The terminal position is a payment dummy.
Selection/retry interaction is `(1-p)(1-q)`. The signed Shapley shares are
`[-(1-p)(1-q)/2, (1+p)(1-q)/2, 0]`. At `p=q=.5`, they are
`[-.125, .375, 0]`, the interaction is `.25`, and the independent population
endpoint difference is `.25`. The action-selection shares are `[-(1-p), 0, 0]`.

Idempotency prevents the second refund from creating a duplicate. Its
consequence game then equals the selection game: retry share and interaction
are zero. Missing provenance retains a known violated state but can refuse the
linked-consequence target for a satisfied refund. A readback watermark before
the contract horizon refuses consequence targets even when evaluator records
contain commits. Neither control turns missing evidence into an unfavorable
outcome.

The strict game retains its reachability refusal. A held retry requires the
selection to occur, and a held terminal decision requires both selection and
retry. Its valid probability is consequently below one for some masks unless
`p=q=1`. Such a coalition has no unconditional numeric value in the strict
game. A favorable finite draw does not make the population game defined.
The on-reach game retains normal early termination as a completed episode and
records the later held positions as inactive. Reached incompatible decisions,
provider failure and budget exhaustion still refuse outcomes.

The predeclared exporter cases are `.5/.5`, `.2/.8`, `.8/.2`, and `1/1`, followed
by `.5/.5` idempotency, missing-provenance, stale-readback, and small-budget
controls. There are 512 planned branches: eight cases, two games, four choice
components and eight masks. Each component/game has its own actual-call budget,
including three factual calls. The small-budget case permits four calls and
retains failed and unstarted masks. It neither enlarges budgets nor drops the
missing mixture mass. Numerical summaries require every positive-weight
component of the relevant coalition to complete with a known target.

Freeze the checked source before retaining a research artifact, then run:

```powershell
.venv/Scripts/python.exe -m consequa_x.benchmark.interaction_export --output output/refund-interactions-2026-10-13 --source-revision <frozen-commit>
.venv/Scripts/python.exe scripts/audit_refund_interactions.py output/refund-interactions-2026-10-13
```

The installed CLI provides the same export as `consequa-x refund-interactions
--source-revision <frozen-commit> --output <new-directory>`. Use `--mechanism`
repeatedly to select registered cases; the default retains all eight.

The callable interface is
`export_refund_interactions(output, *, source_revision, seed=4_000_000, mechanisms=None)`.
Source provenance is caller supplied; the exporter does not inspect Git. A
nonempty destination is rejected. The complete schedule, reference laws, case
settings, budgets, source identifier and limitations are written before the
first actual policy call. Interrupted runs retain partial files and have no
completion manifest.

`evidence.jsonl.gz` contains every factual capture and branch slot, actual
decision receipts, budgets, public traces and explanations. Invalid, failed or
unstarted branches have no fabricated trace or target. Strict unreachable
branches retain their decision receipts; the strict replay primitive discards
their completed episode when it declares that intervention invalid.
`evaluator-truth.jsonl.gz` separately contains simulator configuration and
execution records for retained completed episodes. `summary.json` records the
weighted values, all missing/invalid/failure masses, signed shares, interaction,
endpoint difference and actual calls. A hash manifest covers the completed
artifact. Gzip timestamps are fixed to zero.

The independent auditor imports only Python's standard library. It reconstructs
phase schedules, actual cost, inactive positions, readback targets, payment
commits, exact mixture weights and Shapley contributions averaged across all six
permutations. Tests also exercise the genuine seeded sampler through actual
payment replay with the Hoeffding pair bound and exact-binomial endpoint bound.
Those integration checks demonstrate that the sampler works with the new game;
they do not establish repeated-run interval coverage or a detection-power claim.

This enumeration establishes a real refund selection/retry interaction under an
explicit positional intervention. Repeated permutation-sampler calibration,
live-model independence, joint context/fault attribution, strong matched
baselines and cross-domain recovery remain separate research requirements.
No paid model calls or GitHub Actions are used by this milestone.
