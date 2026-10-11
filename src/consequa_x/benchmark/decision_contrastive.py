"""Decision-level suffix replay against one observed factual outcome.

This independently written CAR-style binary adaptation keeps its estimates
separate from paired context leave-one-out effects. It uses the captured
factual outcome once, fresh continuation seeds, and changed-minus-factual bad
probability. Missing evidence refuses inference; it never becomes a good draw.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
import random
from typing import Iterable, Literal

from ..attribution import REPLAY_TARGETS, ReplayTarget
from ..models import EventType, Trace, to_dict
from ..policies import PolicyError
from .decision_replay import DecisionPrefixReplay, replay_decision_prefix
from .evaluation import BudgetedPolicy, CallBudgetExceeded
from .policy_runner import MAX_TRIAL_SEED
from .runner import Episode
from .targets import episode_outcome
from .templates import DEFAULT_REFUND_TEMPLATE, RefundTaskTemplate


REFERENCE_REVISION = "db90fa28b97164c35e7c524e4597b8cbdb3035af"


@dataclass(frozen=True)
class DecisionContrastiveBranch:
    """An attempted suffix sample; the full plan also retains unstarted slots."""

    index: int
    decision_index: int
    continuation_seed: int
    replay: DecisionPrefixReplay


@dataclass(frozen=True)
class DecisionContrastiveEstimate:
    decision_index: int
    event_id: str
    target: ReplayTarget
    status: Literal["estimated", "refused"]
    factual_bad: bool | None
    changed_bad_rate: float | None
    effect: float | None
    confidence_interval: tuple[float, float] | None
    known_samples: int
    unknown_samples: int
    failed_samples: int
    unstarted_samples: int
    seeds: tuple[int, ...]
    significant_rescue: bool | None
    reason: str | None = None

    @property
    def interval_degenerate(self) -> bool | None:
        if self.confidence_interval is None:
            return None
        return self.confidence_interval[0] == self.confidence_interval[1]

    def to_dict(self) -> dict:
        result = to_dict(self)
        result["interval_degenerate"] = self.interval_degenerate
        return result


@dataclass(frozen=True)
class DecisionContrastiveLocus:
    target: ReplayTarget
    status: Literal["identified", "no_rescue", "refused"]
    decision_index: int | None = None
    event_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class DecisionContrastiveResult:
    factual: Episode
    branches: tuple[DecisionContrastiveBranch, ...]
    results: tuple[DecisionContrastiveEstimate, ...]
    loci: tuple[DecisionContrastiveLocus, ...]
    policy_metadata: dict
    targets: tuple[ReplayTarget, ...]
    samples_per_decision: int
    planned_seeds: tuple[tuple[int, ...], ...]
    planned_branches: int
    calls: int
    initial_calls: int
    max_calls: int
    budget_exhausted: bool
    template: RefundTaskTemplate
    confidence: float
    bootstrap_samples: int
    bootstrap_seed: int

    def method_record(self) -> dict:
        return {
            "name": "car_style_binary_decision_contrastive",
            "reference_revision": REFERENCE_REVISION,
            "baseline": "one_observed_factual_outcome",
            "bad_encoding": "not target_value; unknown remains unknown",
            "effect_sign": "changed_bad_rate_minus_factual_bad",
            "intervention": "hold decisions before position; resample position and suffix",
            "decision_order": "ascending factual decision positions",
            "continuation_seed_schedule": "seed + decision_index * samples + sample_index",
            "interval_method": "conditional_percentile_bootstrap",
            "confidence": self.confidence,
            "bootstrap_samples": self.bootstrap_samples,
            "bootstrap_seed": self.bootstrap_seed,
            "bootstrap_rng": "python.random.Random (MT19937), reset per estimate",
            "bootstrap_baseline": "constant observed label; no RNG draws for baseline",
            "quantile_method": "linear interpolation between sorted bootstrap effects",
            "multiplicity_adjustment": "none",
            "rescue_rule": "effect < 0 and confidence_interval upper bound < 0",
            "locus_rule": "latest rescuing position; every position must be estimable",
            "missingness_policy": "refuse whole affected estimate; no drops or redraws",
            "budget_unit": "actual attempted policy calls, including provider failures",
            "minimum_samples_per_decision": 2,
            "deviations": [
                "Python RNG and a constant baseline differ from upstream NumPy seed draws.",
                "Minimum two samples and strict finite input validation.",
                "Call budget retains partial failure and unstarted receipts instead of aborting.",
                "Unknown evidence refuses estimates; incomplete positions refuse the final locus.",
            ],
        }

    def summary(self) -> dict:
        completed = sum(branch.replay.episode is not None for branch in self.branches)
        return {
            "factual_decision_count": len(self.planned_seeds),
            "samples_per_decision": self.samples_per_decision,
            "planned_branches": self.planned_branches,
            "attempted_branches": len(self.branches),
            "completed_branches": completed,
            "failed_branches": len(self.branches) - completed,
            "not_started_branches": self.planned_branches - len(self.branches),
            "policy_calls": self.calls,
            "shared_budget_calls_before": self.initial_calls,
            "shared_budget_calls_after": self.initial_calls + self.calls,
            "max_calls": self.max_calls,
            "budget_exhausted": self.budget_exhausted,
            "estimates": {
                target: {status: sum(result.target == target and result.status == status
                                     for result in self.results)
                         for status in ("estimated", "refused")}
                for target in self.targets
            },
            "loci": to_dict(self.loci),
            "method": self.method_record(),
            "statistical_limits": [
                "Intervals condition on one observed factual episode and world.",
                "There is no multiplicity correction across positions or targets.",
                "Homogeneous binary samples can yield zero-width bootstrap intervals; "
                "this does not prove zero population variance or certain rescue.",
                "Requested seeds do not establish independent samples or hidden-state equality.",
                "The selected locus is a nominal statistical rule, not proof of unique causation.",
            ],
        }


def _linear_quantile(ordered: list[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _bootstrap_interval(values: tuple[bool, ...], factual_bad: bool, *,
                        confidence: float, bootstrap_samples: int,
                        bootstrap_seed: int) -> tuple[float, float]:
    # This is deliberately a separate estimator from paired Wilson differences.
    # One observed factual label stays constant in every bootstrap replicate.
    rng = random.Random(bootstrap_seed)
    count = len(values)
    effects = sorted(
        sum(values[rng.randrange(count)] for _ in range(count)) / count - int(factual_bad)
        for _ in range(bootstrap_samples)
    )
    tail = (1 - confidence) / 2
    return _linear_quantile(effects, tail), _linear_quantile(effects, 1 - tail)


def _selected_targets(targets: Iterable[ReplayTarget]) -> tuple[ReplayTarget, ...]:
    if isinstance(targets, str):
        raise ValueError("targets must be a nonempty iterable of distinct replay targets")
    selected = tuple(targets)
    if (not selected or any(not isinstance(target, str) or target not in REPLAY_TARGETS
                            for target in selected) or len(set(selected)) != len(selected)):
        raise ValueError("targets must be a nonempty iterable of distinct replay targets")
    return selected


def contrastive_decisions(
    factual: Episode,
    continuation_policy: BudgetedPolicy,
    *,
    samples: int = 16,
    seed: int = 100,
    targets: Iterable[ReplayTarget] = ("consequence",),
    template: RefundTaskTemplate = DEFAULT_REFUND_TEMPLATE,
    confidence: float = 0.95,
    bootstrap_samples: int = 2000,
    bootstrap_seed: int = 0,
) -> DecisionContrastiveResult:
    """Sample every factual decision's suffix and estimate binary bad outcomes.

    The supplied budget can already include the factual recording or other
    work. ``calls`` is only this operation's continuation-call delta. Earlier
    decisions are held with exact input checks; each sample gets a distinct
    policy seed schedule while the factual simulator world stays fixed.

    The complete factual capture, selected targets, schedule, template and
    declared policy identity are validated before new provider calls. Every
    target reuses one collected branch cache. Any missing outcome refuses that
    candidate's whole estimate, and any refused candidate prevents a final
    locus for its target. No sample is dropped, replaced, or redrawn.
    """
    if not isinstance(factual, Episode):
        raise TypeError("factual must be an Episode")
    if not isinstance(factual.trace, Trace):
        raise TypeError("factual.trace must be a Trace")
    if not isinstance(continuation_policy, BudgetedPolicy):
        raise TypeError("continuation_policy must be a BudgetedPolicy")
    if type(samples) is not int or samples < 2:
        raise ValueError("samples must be an integer of at least 2")
    if type(seed) is not int or not 0 <= seed <= MAX_TRIAL_SEED:
        raise ValueError(f"seed must be an integer in 0..{MAX_TRIAL_SEED}")
    if type(bootstrap_samples) is not int or bootstrap_samples < 2:
        raise ValueError("bootstrap_samples must be an integer of at least 2")
    if type(bootstrap_seed) is not int or bootstrap_seed < 0:
        raise ValueError("bootstrap_seed must be a nonnegative integer")
    if type(confidence) not in {int, float} or not math.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence must be finite and strictly between 0 and 1")
    if not isinstance(template, RefundTaskTemplate):
        raise TypeError("template must be a RefundTaskTemplate")
    if (type(continuation_policy.max_calls) is not int or continuation_policy.max_calls < 1
            or type(continuation_policy.calls) is not int
            or not 0 <= continuation_policy.calls <= continuation_policy.max_calls):
        raise ValueError("BudgetedPolicy must have a valid call counter and positive limit")
    selected = _selected_targets(targets)
    events = tuple(event for event in factual.trace.events if event.type is EventType.AGENT_DECISION)
    if not events:
        raise ValueError("factual trace must contain captured policy decisions")
    planned_branches = len(events) * samples
    if seed + planned_branches - 1 > MAX_TRIAL_SEED:
        raise ValueError(f"Continuation seed schedule must stay in 0..{MAX_TRIAL_SEED}")
    # Full held replay validates every capture without invoking the provider,
    # even if the shared call budget is already exhausted.
    probe = replay_decision_prefix(factual, continuation_policy, hold_count=len(events),
                                   continuation_seed=seed, template=template)
    if probe.episode is None:
        raise ValueError("Full factual reconstruction failed: " + (probe.error or "unknown error"))
    factual_policy_seed = events[0].data["model_seed"] // 6
    if seed <= factual_policy_seed <= seed + planned_branches - 1:
        raise ValueError("Continuation seed schedule overlaps the factual policy phase seeds")
    planned_seeds = tuple(tuple(seed + position * samples + offset for offset in range(samples))
                          for position in range(len(events)))
    metadata = deepcopy(probe.policy_metadata)
    factual_outcome = episode_outcome(factual)
    initial_calls = continuation_policy.calls
    branches = []
    exhausted = False
    for position, seeds in enumerate(planned_seeds):
        for continuation_seed in seeds:
            if continuation_policy.calls >= continuation_policy.max_calls:
                exhausted = True
                break
            before = continuation_policy.calls
            try:
                replay = replay_decision_prefix(
                    factual, continuation_policy, hold_count=position,
                    continuation_seed=continuation_seed, template=template,
                )
            except (PolicyError, ValueError, TypeError) as error:
                # Preflight was valid. Later identity/capture drift is a failed
                # planned draw, not a reason to lose already collected receipts.
                replay = DecisionPrefixReplay(
                    position, continuation_seed, factual.seed, len(events), deepcopy(metadata),
                    (), continuation_policy.calls - before,
                    error_type=type(error).__name__, error=str(error),
                    budget_exhausted=isinstance(error, CallBudgetExceeded),
                )
            branches.append(DecisionContrastiveBranch(len(branches), position,
                                                       continuation_seed, replay))
            if replay.budget_exhausted:
                exhausted = True
                break
        if exhausted:
            break

    # Compute allowed target evidence once per completed world. Evaluator truth
    # and agent assessment are not inputs to the binary outcome mapping.
    cache = {(branch.decision_index, branch.continuation_seed):
             (branch, episode_outcome(branch.replay.episode)
              if branch.replay.episode is not None else None)
             for branch in branches}
    results = []
    for position, seeds in enumerate(planned_seeds):
        for target in selected:
            factual_value = factual_outcome.target_value(target)
            factual_bad = None if factual_value is None else not factual_value
            counts = {key: 0 for key in ("known", "unknown", "failed", "unstarted")}
            changed = []
            for continuation_seed in seeds:
                item = cache.get((position, continuation_seed))
                if item is None:
                    counts["unstarted"] += 1
                elif item[0].replay.episode is None:
                    counts["failed"] += 1
                else:
                    value = item[1].target_value(target)
                    if value is None:
                        counts["unknown"] += 1
                    else:
                        counts["known"] += 1
                        changed.append(not value)
            point = rate = interval = rescue = None
            reason = None
            status = "refused"
            if factual_bad is not None and counts["known"] == samples:
                rate = sum(changed) / samples
                point = rate - int(factual_bad)
                interval = _bootstrap_interval(
                    tuple(changed), factual_bad, confidence=confidence,
                    bootstrap_samples=bootstrap_samples, bootstrap_seed=bootstrap_seed,
                )
                rescue = point < 0 and interval[1] < 0
                status = "estimated"
            else:
                reason = (
                    f"Cannot estimate {target}: factual target is "
                    f"{'unknown' if factual_bad is None else 'known'}; "
                    f"{counts['known']} of {samples} suffix samples known, "
                    f"{counts['unknown']} unknown, {counts['failed']} failed, "
                    f"{counts['unstarted']} unstarted. No draws are dropped or redrawn."
                )
            results.append(DecisionContrastiveEstimate(
                position, events[position].id, target, status, factual_bad, rate, point, interval,
                counts["known"], counts["unknown"], counts["failed"], counts["unstarted"],
                seeds, rescue, reason,
            ))
    loci = []
    for target in selected:
        candidates = tuple(result for result in results if result.target == target)
        refused = sum(result.status == "refused" for result in candidates)
        if refused:
            loci.append(DecisionContrastiveLocus(
                target, "refused", reason=f"{refused} factual decision positions lack complete "
                "estimates; a latest rescue locus cannot be declared.",
            ))
        else:
            rescues = tuple(result for result in candidates if result.significant_rescue)
            if rescues:
                latest = rescues[-1]
                loci.append(DecisionContrastiveLocus(target, "identified", latest.decision_index,
                                                     latest.event_id))
            else:
                loci.append(DecisionContrastiveLocus(
                    target, "no_rescue", reason="No position satisfies the declared negative "
                    "effect and interval criterion.",
                ))
    return DecisionContrastiveResult(
        factual, tuple(branches), tuple(results), tuple(loci), metadata, selected, samples,
        planned_seeds, planned_branches, continuation_policy.calls - initial_calls, initial_calls,
        continuation_policy.max_calls, exhausted, template, float(confidence), bootstrap_samples,
        bootstrap_seed,
    )
