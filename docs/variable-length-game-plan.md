# Variable-length decision games and refund interactions

Status: implementation specification, 13 October 2026. This is a separate
intervention game; it must not reinterpret the retained strict calibration data.

## Two explicit games

The current strict game forces a captured decision at each held factual
position, checking its typed stage and current operation validity. If an earlier
resampled decision terminates the episode before a held position, that draw is
invalid. The population game can consequently be undefined even when a finite
sample happens to contain only valid draws.

Add an opt-in **on-reach** game. Force a held captured decision only if the
rollout reaches its factual position. Normal earlier termination makes later
held positions inactive. Keep the actually completed trajectory and independently
verified outcome; do not fabricate a reply, tool action, or outcome at an
unreached position. Record requested, reached and inactive held positions in
every branch receipt. A reached but incompatible stage/operation remains
invalid under either game. Provider failure, budget exhaustion and unknown
evidence retain the existing refusal rules. The strict game remains the default.

The on-reach value is the expected bad target of this explicit policy
intervention. Inactivity is part of that intervention, not complete-case
conditioning on a position being reached. Its value must not be named as the
strict game's Shapley value. Holding a terminal decision may be a dummy player
for payment effects while still changing a recorded assessment.

## A real refund interaction

Use the ordinary payment simulator with timeout-after-commit, exactly-one-refund
contract, two attempts and complete independent readback. Plant a factual
refund, retry and final stop at declared reserved phase keys. Every fresh
selection refunds with probability `p`, otherwise stops. Every fresh timeout
decision retries with probability `q`, otherwise stops. Final decisions stop.
The policy reads public requests only; simulator fault and reference labels
stay outside its inputs. Its identity and factual conditioning are recorded.

The three factual players are selection, timeout retry and terminal stop. In
the on-reach game with no idempotency, the expected bad consequence is:

| Held selection | Held retry | Bad probability |
| --- | --- | --- |
| No | No | `1 - p(1-q)` |
| Yes | No | `q` |
| No | Yes | `1` |
| Yes | Yes | `1` |

The terminal player is a payment dummy. The selection/retry interaction
contrast `v(01)-v(0)-v(1)+v(empty)` is `(1-p)(1-q)` (here `01` means both
nonterminal players). For `p=q=.5`, the consequence shares are `-.125`, `.375`,
and `0`; the independently defined endpoint difference is `.25`. For the
action-selection target the shares are `-(1-p)`, `0`, `0`. These target
differences come from actual absent and duplicate refunds, not an injected
payoff at the estimator boundary.

With idempotency, a selected refund stays exactly once regardless of retry.
Its consequence game equals the selection game: retry interaction and retry
share become zero. Also retain missing-provenance, lagged-readback and small
call-budget controls. These test disappearance of an interaction and refusal
coverage, not just recovery in the favorable condition.

## Validation and retained evidence

First enumerate the four deterministic fresh selection/retry choices for each
of the eight held coalitions. Run every choice in a fresh payment world, read
its public trace and independent verification, and compute the weighted game
from the declared Bernoulli law. Verify all coalition values, signed shares,
endpoint totals, interaction contrasts, inactive positions and actual costs
against the independent formulas. Do not replace the production outcome
adapter with a mathematical payoff oracle.

Then test the fresh permutation sampler on a separately frozen repeated
schedule, preserving strict and on-reach results as different games. The
comparison must expose reachability and numeric availability, conservative
interval width, bias/RMSE, reference eligibility, unknowns, provider failures,
unstarted slots and actual policy calls. Parameter or fault choices must be
declared before running and must not be selected for favorable recovery.

This establishes an interaction within the refund adapter. It does not yet
establish joint context/fault attribution, cross-domain recovery, live-model
independence, or superiority over a matched strong baseline. Those remain
separate requirements for the research paper.
