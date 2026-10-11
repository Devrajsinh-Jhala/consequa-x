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

## Required next implementation

1. Implement decision-level contrastive effects with a declared outcome
   encoding, observed factual baseline, suffix sample count, intervals, and
   latest significant rescue rule. Preserve unknown evidence and failed draws.
2. Define valid positional coalitions for variable-length typed trajectories.
   A changed branch may stop before a factual position or reach it in an
   incompatible stage. Record unreachable/invalid coalitions explicitly; do not
   force a refund into a retry slot or manufacture an outcome.
3. Implement fresh antithetic permutation Shapley sampling and independent
   endpoint checks. A cache across coalition evaluations can change the sampled
   game and must not silently replace the specified stochastic estimator.
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
