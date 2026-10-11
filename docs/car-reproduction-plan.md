# Strong comparison baseline: remaining CAR reproduction

Reviewed against the [CAR v1 paper](https://arxiv.org/html/2606.08275v1) and the
[official implementation](https://github.com/jaineet17/causal-agent-replay/tree/db90fa28b97164c35e7c524e4597b8cbdb3035af)
at revision `db90fa28b97164c35e7c524e4597b8cbdb3035af`. The implementation revision
is later than the paper; a final comparator must state which version it follows.

CAR intervenes on recorded decisions and runs affected continuations under the
same policy. Contrastive replay holds preceding decisions factual, resamples
from each candidate decision, and locates the latest statistically supported
rescue point. Its Shapley procedure uses antithetic permutation evaluations to
allocate interaction effects. These requirements go beyond removing one
context field and comparing fresh whole episodes. See the primary
[contrastive](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/contrastive.py)
and [Shapley](https://github.com/jaineet17/causal-agent-replay/blob/db90fa28b97164c35e7c524e4597b8cbdb3035af/src/car/attribute/shapley.py)
implementations for the versioned algorithms.

## Foundation now available

The framework now has [isolated decision-prefix replay](decision-replay.md) and
shared state/action-linked evidence targets. Prefix replay validates recorded
public inputs, separates the world seed from continuation model keys, checks
declared policy identity, and counts only fresh continuation calls. It makes no
claim to be a complete CAR implementation. No upstream source is vendored.

[Decision contrastive replay](decision-contrastive.md) now implements the binary
suffix estimand, observed factual baseline, ascending decision tests, and latest
nominal negative-rescue rule. It records explicit deviations for its Python
bootstrap stream, minimum two samples, actual-call budget, missing-evidence
refusals, and incomplete-locus refusal. Its intervals are conditional and have
no multiplicity adjustment. It remains an independently written adaptation,
not a complete upstream numerical reproduction or a matched-baseline result.

[Positional coalition and Shapley replay](decision-shapley.md) now forces
captured decisions at compatible typed stages and records unreachable held
positions as invalid. Fresh forward/reverse coalition chains yield one paired
contribution vector, with normal intervals and independent endpoint diagnostics.
This strict invalid-coalition refusal is a declared game restriction and can
prevent attribution on variable-length refund trajectories. Mathematical
interaction oracles validate the estimator separately from the refund adapter;
they do not establish domain interaction recovery or calibrated inference.

## Required next implementation

1. Validate the contrastive adaptation on frozen independent mechanisms and
   measure interval coverage, erroneous locus selection, and refusal coverage.
   Homogeneous bootstrap draws may produce zero-width intervals; nominal rescue
   is not proof of population certainty or unique causation.
2. Extend and validate positional coalitions for variable-length typed trajectories.
   A changed branch may stop before a factual position or reach it in an
   incompatible stage. Record unreachable/invalid coalitions explicitly; do not
   force a refund into a retry slot or manufacture an outcome.
3. Validate the fresh antithetic permutation Shapley adaptation and independent
   endpoint diagnostics on fixed-length and variable-length mechanisms. Measure
   bias, interval coverage, and refusal coverage without silently changing the
   game or caching fresh coalition evaluations.
4. Validate recovery on independently planted pivotal decisions, interaction
   mechanisms, irrelevant factors, incomplete readback, and budget exhaustion
   before declaring a live comparison.

## Fair comparison

Use identical continuation policy, verifier and provenance evidence, fixed
contract, candidate intervention units, fresh-world access, and actual policy-call
budget for each method. Report factual-recording cost, replay validation compute,
tokens, latency, and refusal coverage separately. Code that holds declared
metadata fixed still cannot establish identical hidden model state.

CAR's native players are decision steps; this project's existing replay players
are upstream context fields. Factor-recovery scores cannot fairly compare those
different intervention spaces without an explicitly declared adaptation. Any
context-coalition method should be named as such and documented with its changed
game. The final research contribution and paper claims remain contingent on
implemented matched baselines and evidence from a separately frozen study.
