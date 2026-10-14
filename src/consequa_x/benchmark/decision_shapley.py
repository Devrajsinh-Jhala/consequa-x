"""Bounded positional decision Shapley sampling with antithetic walk pairs.

This independently written binary adaptation attributes a held-decision game,
not the difference between one factual label and a sampled continuation. Each
coalition occurrence gets a fresh replay; missing evidence refuses the whole
target vector, and an independent endpoint experiment checks its total scale.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import math
import random
from statistics import NormalDist
from typing import Iterable, Literal

from ..attribution import ReplayTarget
from ..models import EventType, Trace, to_dict
from ..policies import PolicyError
from .decision_coalition import (
    DecisionCoalitionReplay, replay_decision_coalition, validate_coalition_game,
)
from .decision_contrastive import REFERENCE_REVISION, _selected_targets
from .evaluation import BudgetedPolicy, CallBudgetExceeded
from .intervals import binomial_difference_interval, bounded_mean_interval
from .policy_runner import MAX_TRIAL_SEED
from .runner import Episode
from .targets import episode_outcome
from .templates import DEFAULT_REFUND_TEMPLATE, RefundTaskTemplate


SHAPLEY_INTERVAL_METHODS = ("normal", "hoeffding")
ENDPOINT_INTERVAL_METHODS = ("normal", "clopper_pearson_difference")


@dataclass(frozen=True)
class DecisionShapleySlot:
    """One predeclared replay, including slots never started under the budget."""

    index: int
    role: Literal["endpoint_empty", "endpoint_full", "walk"]
    pair_index: int | None
    walk: Literal["forward", "reverse"] | None
    step: int | None
    held_indices: tuple[int, ...]
    sample_index: int
    continuation_seed: int


@dataclass(frozen=True)
class DecisionShapleyBranch:
    slot: DecisionShapleySlot
    replay: DecisionCoalitionReplay


@dataclass(frozen=True)
class DecisionShapleyCoverage:
    planned: int
    known: int
    unknown: int
    invalid: int
    failed: int
    unstarted: int


@dataclass(frozen=True)
class DecisionShapleyEstimate:
    decision_index: int
    event_id: str
    target: ReplayTarget
    status: Literal["estimated", "refused"]
    shapley_value: float | None
    confidence_interval: tuple[float, float] | None
    pair_values: tuple[float | None, ...]
    known_pairs: int
    unknown_pairs: int
    invalid_pairs: int
    failed_pairs: int
    unstarted_pairs: int
    coverage: DecisionShapleyCoverage
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
class DecisionShapleyEndpointCheck:
    """Independent endpoint effect; discrepancy is a descriptive point only."""

    target: ReplayTarget
    status: Literal["estimated", "refused"]
    empty_bad_rate: float | None
    full_bad_rate: float | None
    endpoint_difference: float | None
    confidence_interval: tuple[float, float] | None
    empty_coverage: DecisionShapleyCoverage
    full_coverage: DecisionShapleyCoverage
    coefficient_sum: float | None
    discrepancy: float | None
    reason: str | None = None


@dataclass(frozen=True)
class DecisionShapleyResult:
    factual: Episode
    slots: tuple[DecisionShapleySlot, ...]
    branches: tuple[DecisionShapleyBranch, ...]
    results: tuple[DecisionShapleyEstimate, ...]
    endpoint_checks: tuple[DecisionShapleyEndpointCheck, ...]
    permutations: tuple[tuple[int, ...], ...]
    policy_metadata: dict
    targets: tuple[ReplayTarget, ...]
    pairs: int
    samples_per_eval: int
    endpoint_samples: int
    calls: int
    initial_calls: int
    max_calls: int
    budget_exhausted: bool
    template: RefundTaskTemplate
    confidence: float
    permutation_seed: int
    interval_method: str = "normal"
    endpoint_interval_method: str = "normal"
    coalition_game: str = "strict"

    def method_record(self) -> dict:
        return {
            "name": ("car_style_binary_decision_shapley" if self.coalition_game == "strict" else
                     "binary_on_reach_decision_shapley"),
            "coalition_game": self.coalition_game,
            "reference_revision": REFERENCE_REVISION,
            "game": "bad outcome probability with a positional factual held-decision coalition",
            "bad_encoding": "not target_value; unknown remains unknown",
            "effect_sign": "v(held union decision) minus v(held)",
            "effect_meaning": "positive contributes bad; negative is protective; raw signed shares",
            "walk_sampling": "uniform Python-shuffled permutation and its reverse per pair",
            "pairs": self.pairs,
            "samples_per_eval": self.samples_per_eval,
            "fresh_coalition_sampling": "every occurrence and sample has its own replay seed; no cache",
            "interval_method": ("normal pair-mean interval; sample variance ddof=1 divided by pairs"
                                if self.interval_method == "normal" else "two-sided Hoeffding pair-mean bound"),
            "pair_value_bounds": [-1., 1.],
            "interval_assumptions": "independent known pair vectors from the defined coalition game",
            "interval_clipping": self.interval_method == "hoeffding",
            "confidence": self.confidence,
            "independent_unit": "one averaged forward/reverse contribution vector",
            "permutation_seed": self.permutation_seed,
            "permutation_rng": "python.random.Random (MT19937)",
            "continuation_seed_schedule": "seed + slot.index; every trial reserves six phase keys",
            "schedule_order": "empty endpoints, full endpoints, then forward/reverse walks per pair",
            "endpoint_samples": self.endpoint_samples,
            "endpoint_difference": "independent full-held mean minus independent empty-held mean",
            "endpoint_interval": ("normal interval with independent full/empty variance contributions"
                                  if self.endpoint_interval_method == "normal" else
                                  "two exact binomial marginal intervals with split failure allowance"),
            "endpoint_interval_method": self.endpoint_interval_method,
            "endpoint_interval_assumptions": "independent known binary draws within each endpoint law",
            "discrepancy": "sum of estimated signed shares minus independent endpoint difference",
            "discrepancy_inference": "descriptive point only; no interval or forced normalization",
            "multiplicity_adjustment": "none",
            "missingness_policy": "any missing path draw refuses the whole target vector; no redraws",
            "endpoint_missingness": "endpoint diagnostics refused separately from path coefficients",
            "pair_status_priority": "unstarted, failed, invalid, unknown, known",
            "budget_unit": "actual attempted policy calls, including provider failures",
            "budget_stop": "zero-call full-held slots allowed at limit; stop after budget refusal",
            "deviations": [
                "Python RNG and disjoint continuation seeds differ from upstream streams.",
                "Minimum two pairs and endpoint samples, with 16-pair default and strict input checks.",
                "Actual call budgets retain invalid, partial failure and unstarted receipts.",
                ("Unreached or stage-incompatible held positions invalidate their planned sample."
                 if self.coalition_game == "strict" else
                 "Normally unreached held positions are inactive; reached incompatible positions remain invalid."),
                "Unknown or incomplete path evidence refuses the whole target attribution vector.",
                "Independent endpoint diagnostics do not normalize the sampled coefficients.",
            ],
        }

    def summary(self) -> dict:
        statuses = {name: sum(branch.replay.status == name for branch in self.branches)
                    for name in ("completed", "invalid", "failed")}
        return {
            "factual_decision_count": len(self.permutations[0]),
            "pairs": self.pairs,
            "permutations": self.pairs * 2,
            "samples_per_eval": self.samples_per_eval,
            "endpoint_samples_per_coalition": self.endpoint_samples,
            "planned_branches": len(self.slots),
            "attempted_branches": len(self.branches),
            "completed_branches": statuses["completed"],
            "invalid_branches": statuses["invalid"],
            "failed_branches": statuses["failed"],
            "not_started_branches": len(self.slots) - len(self.branches),
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
            "endpoint_checks": to_dict(self.endpoint_checks),
            "method": self.method_record(),
            "statistical_limits": [
                "Intervals condition on one captured factual episode and simulator world.",
                "Forward and reverse walks within a pair are correlated and count as one unit.",
                "Normal intervals are approximate; bounded/exact alternatives can be conservative and wide.",
                "There is no multiplicity correction across decisions or targets.",
                "Only the normal options yield zero-width intervals at homogeneous samples; this does not prove certainty.",
                "Concentration and binomial statements require their declared sampling assumptions.",
                "Requested seeds do not establish independent model draws or hidden-state equality.",
                "Signed shares are neither probabilities nor normalized responsibility percentages.",
                "Independent endpoint discrepancy is a descriptive diagnostic, not a calibrated test.",
                ("The strict positional game invalidates unreached held positions."
                 if self.coalition_game == "strict" else
                 "The on-reach game treats normally unreached held positions as inactive; it is a different intervention game."),
            ],
        }


def _variance(values: tuple[float, ...]) -> float:
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _normal_interval(values: tuple[float, ...], confidence: float) -> tuple[float, float]:
    mean = sum(values) / len(values)
    margin = -NormalDist().inv_cdf((1 - confidence) / 2) * math.sqrt(
        _variance(values) / len(values)
    )
    return mean - margin, mean + margin


def _interval_methods(interval_method, endpoint_interval_method):
    if type(interval_method) is not str or interval_method not in SHAPLEY_INTERVAL_METHODS:
        raise ValueError("interval_method must be normal or hoeffding")
    if (type(endpoint_interval_method) is not str
            or endpoint_interval_method not in ENDPOINT_INTERVAL_METHODS):
        raise ValueError("endpoint_interval_method must be normal or clopper_pearson_difference")


def _pair_interval(values, confidence, method):
    return (_normal_interval(tuple(values), confidence) if method == "normal" else
            bounded_mean_interval(values, confidence=confidence))


def _endpoint_interval(empty, full, confidence, method):
    if method == "clopper_pearson_difference":
        return binomial_difference_interval(sum(full), len(full), sum(empty), len(empty),
                                             confidence=confidence)
    point = sum(full) / len(full) - sum(empty) / len(empty)
    margin = -NormalDist().inv_cdf((1 - confidence) / 2) * math.sqrt(
        _variance(tuple(empty)) / len(empty) + _variance(tuple(full)) / len(full))
    return point - margin, point + margin


def _sample_values(slots, cache, target):
    values, statuses = {}, {}
    for slot in slots:
        item = cache.get(slot.index)
        value = None
        if item is None:
            status = "unstarted"
        elif item[0].replay.status == "invalid":
            status = "invalid"
        elif item[0].replay.episode is None:
            status = "failed"
        else:
            target_value = item[1].target_value(target)
            status = "unknown" if target_value is None else "known"
            if target_value is not None:
                value = not target_value
        values[slot.index], statuses[slot.index] = value, status
    return values, statuses


def _pair_observations(permutations, path_slots, values, statuses, samples_per_eval, count):
    vectors, labels = [], []
    for pair_index, forward in enumerate(permutations):
        pair_slots = tuple(slot for slot in path_slots if slot.pair_index == pair_index)
        pair_labels = tuple(statuses[slot.index] for slot in pair_slots)
        status = next((name for name in ("unstarted", "failed", "invalid", "unknown")
                       if name in pair_labels), "known")
        labels.append(status)
        if status != "known":
            vectors.append(None)
            continue
        vector = [0.] * count
        for walk, order in (("forward", forward), ("reverse", tuple(reversed(forward)))):
            means = []
            for step in range(count+1):
                draws = tuple(values[slot.index] for slot in pair_slots
                              if slot.walk == walk and slot.step == step)
                if len(draws) != samples_per_eval:
                    raise ValueError("Pair walk has an incomplete declared sample block")
                means.append(sum(draws) / samples_per_eval)
            for step, position in enumerate(order):
                vector[position] += (means[step+1]-means[step])/2
        vectors.append(tuple(vector))
    return vectors, labels


def with_shapley_intervals(result: DecisionShapleyResult, *, interval_method: str,
                           endpoint_interval_method: str) -> DecisionShapleyResult:
    """Compare pair/endpoint intervals on the same draws, keeping all refusals.

    No new policy calls occur. Signed points, pair vectors, coverage, budgets
    and the independent endpoint discrepancy remain unchanged.
    """
    if not isinstance(result, DecisionShapleyResult):
        raise TypeError("result must be a DecisionShapleyResult")
    _interval_methods(interval_method, endpoint_interval_method)
    validate_coalition_game(result.coalition_game)
    events = tuple(event for event in result.factual.trace.events
                   if event.type is EventType.AGENT_DECISION)
    count = len(events)
    expected = {(target, i) for target in result.targets for i in range(count)}
    if (len(result.results) != len(expected)
            or {(item.target, item.decision_index) for item in result.results} != expected
            or len(result.permutations) != result.pairs
            or any(len(order) != count or set(order) != set(range(count))
                   for order in result.permutations)):
        raise ValueError("Result inventory or permutation schedule changed after estimation")
    planned = {slot.index: slot for slot in result.slots}
    if len(planned) != len(result.slots) or set(planned) != set(range(len(result.slots))):
        raise ValueError("Result slot inventory is incomplete or duplicated")
    if (len({branch.slot.index for branch in result.branches}) != len(result.branches)
            or any(planned.get(branch.slot.index) != branch.slot
                   or branch.replay.coalition_game != result.coalition_game
                   for branch in result.branches)):
        raise ValueError("Branch receipts no longer match their declared schedule/game")
    cache = {branch.slot.index: (branch, episode_outcome(branch.replay.episode)
                                if branch.replay.episode is not None else None)
             for branch in result.branches}
    path_slots = tuple(slot for slot in result.slots if slot.role == "walk")
    recomputed = {}
    for target in result.targets:
        target_items = [item for item in result.results if item.target == target]
        if any(item.status == "estimated" for item in target_items) and not all(
            item.status == "estimated" for item in target_items
        ):
            raise ValueError("A stored target vector has mixed estimate/refusal statuses")
        if not any(item.status == "estimated" for item in target_items):
            continue
        values, statuses = _sample_values(result.slots, cache, target)
        vectors, labels = _pair_observations(result.permutations, path_slots, values, statuses,
                                              result.samples_per_eval, count)
        recomputed[target] = (vectors, _coverage(labels),
                              _coverage(statuses[slot.index] for slot in path_slots))
    estimates = []
    for item in result.results:
        if item.status == "refused":
            estimates.append(item)
            continue
        vectors, coverage, path_coverage = recomputed[item.target]
        pair_values = tuple(vector[item.decision_index] if vector is not None else None
                            for vector in vectors)
        if (coverage.known != result.pairs or pair_values != item.pair_values
                or sum(pair_values) / result.pairs != item.shapley_value
                or path_coverage != item.coverage or item.event_id != events[item.decision_index].id
                or (item.known_pairs, item.unknown_pairs, item.invalid_pairs,
                    item.failed_pairs, item.unstarted_pairs) !=
                   (coverage.known, coverage.unknown, coverage.invalid, coverage.failed, coverage.unstarted)):
            raise ValueError("Estimated pair vector or point no longer matches replay evidence")
        estimates.append(replace(item, confidence_interval=_pair_interval(
            item.pair_values, result.confidence, interval_method)))
    endpoints = []
    if (len(result.endpoint_checks) != len(result.targets)
            or {item.target for item in result.endpoint_checks} != set(result.targets)):
        raise ValueError("Endpoint inventory changed after estimation")
    for item in result.endpoint_checks:
        target_estimates = [entry for entry in estimates if entry.target == item.target]
        coefficient_sum = (sum(entry.shapley_value for entry in target_estimates)
                           if all(entry.status == "estimated" for entry in target_estimates) else None)
        discrepancy = (coefficient_sum-item.endpoint_difference
                       if coefficient_sum is not None and item.endpoint_difference is not None else None)
        if coefficient_sum != item.coefficient_sum or discrepancy != item.discrepancy:
            raise ValueError("Recorded endpoint coefficient sum/discrepancy changed after estimation")
        if item.status == "refused":
            endpoints.append(item)
            continue
        _, statuses = _sample_values(result.slots, cache, item.target)
        by_role = {}
        for role in ("endpoint_empty", "endpoint_full"):
            values = []
            expected_coverage = _coverage(statuses[slot.index] for slot in result.slots
                                          if slot.role == role)
            stored_coverage = item.empty_coverage if role == "endpoint_empty" else item.full_coverage
            if expected_coverage != stored_coverage:
                raise ValueError("Recorded endpoint coverage no longer matches replay evidence")
            for slot in result.slots:
                if slot.role != role:
                    continue
                stored = cache.get(slot.index)
                outcome = stored[1] if stored is not None else None
                value = outcome.target_value(item.target) if outcome is not None else None
                if value is None:
                    raise ValueError("Previously estimated endpoint evidence became unavailable")
                values.append(not value)
            if len(values) != result.endpoint_samples:
                raise ValueError("Endpoint sample count differs from the declared plan")
            by_role[role] = values
        empty, full = by_role["endpoint_empty"], by_role["endpoint_full"]
        if (sum(empty) / len(empty) != item.empty_bad_rate
                or sum(full) / len(full) != item.full_bad_rate
                or item.full_bad_rate - item.empty_bad_rate != item.endpoint_difference):
            raise ValueError("Endpoint mean changed after the original estimate")
        endpoints.append(replace(item, confidence_interval=_endpoint_interval(
            empty, full, result.confidence, endpoint_interval_method)))
    return replace(result, results=tuple(estimates), endpoint_checks=tuple(endpoints),
                   interval_method=interval_method, endpoint_interval_method=endpoint_interval_method)


def _coverage(statuses: Iterable[str]) -> DecisionShapleyCoverage:
    labels = tuple(statuses)
    counts = {status: labels.count(status)
              for status in ("known", "unknown", "invalid", "failed", "unstarted")}
    return DecisionShapleyCoverage(len(labels), **counts)


def _missing_reason(label: str, coverage: DecisionShapleyCoverage) -> str:
    return (
        f"Cannot estimate {label}: {coverage.known} of {coverage.planned} planned draws known, "
        f"{coverage.unknown} unknown, {coverage.invalid} invalid, {coverage.failed} failed, "
        f"{coverage.unstarted} unstarted. No draws are dropped or redrawn."
    )


def shapley_decisions(
    factual: Episode,
    continuation_policy: BudgetedPolicy,
    *,
    pairs: int = 16,
    samples_per_eval: int = 1,
    endpoint_samples: int = 16,
    seed: int = 100,
    permutation_seed: int = 0,
    confidence: float = 0.95,
    targets: Iterable[ReplayTarget] = ("consequence",),
    template: RefundTaskTemplate = DEFAULT_REFUND_TEMPLATE,
    interval_method: str = "hoeffding",
    endpoint_interval_method: str = "clopper_pearson_difference",
    coalition_game: str = "strict",
) -> DecisionShapleyResult:
    """Estimate signed decision contributions using fresh positional coalitions.

    Empty/full endpoint samples run first, independently from the walk samples.
    Each pair shuffles a uniform permutation, evaluates its complete coalition
    chain, and evaluates its reversed chain with fresh seeds. Coalition means
    use all ``samples_per_eval`` draws; marginal vectors are averaged within a
    pair before intervals treat the pairs as independent units. The default
    Hoeffding bound uses their declared [-1,1] range; normal is an explicit
    approximate comparator. Endpoint bounds default to two exact binomial
    marginals with a split failure allowance.

    A target's whole coefficient vector requires every path draw to be known.
    Independent endpoint failures do not erase otherwise complete coefficients.
    Full factual capture and policy identity validation precede new policy calls.
    """
    if not isinstance(factual, Episode):
        raise TypeError("factual must be an Episode")
    if not isinstance(factual.trace, Trace):
        raise TypeError("factual.trace must be a Trace")
    if not isinstance(continuation_policy, BudgetedPolicy):
        raise TypeError("continuation_policy must be a BudgetedPolicy")
    _interval_methods(interval_method, endpoint_interval_method)
    validate_coalition_game(coalition_game)
    for name, value, minimum in (("pairs", pairs, 2),
                                 ("samples_per_eval", samples_per_eval, 1),
                                 ("endpoint_samples", endpoint_samples, 2)):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer of at least {minimum}")
    if type(seed) is not int or not 0 <= seed <= MAX_TRIAL_SEED:
        raise ValueError(f"seed must be an integer in 0..{MAX_TRIAL_SEED}")
    if type(permutation_seed) is not int or not 0 <= permutation_seed <= 2**31 - 1:
        raise ValueError("permutation_seed must be an integer in 0..2147483647")
    try:
        valid_confidence = (type(confidence) in {int, float} and math.isfinite(confidence)
                            and 0 < confidence < 1)
    except OverflowError:
        valid_confidence = False
    if not valid_confidence:
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
    count = len(events)
    planned = 2 * endpoint_samples + 2 * pairs * (count + 1) * samples_per_eval
    if seed + planned - 1 > MAX_TRIAL_SEED:
        raise ValueError(f"Continuation seed schedule must stay in 0..{MAX_TRIAL_SEED}")
    probe = replay_decision_coalition(
        factual, continuation_policy, held_indices=range(count),
        continuation_seed=seed, template=template, coalition_game=coalition_game,
    )
    if probe.episode is None:
        raise ValueError("Full factual reconstruction failed: " + (probe.error or "unknown error"))
    factual_policy_seed = events[0].data["model_seed"] // 6
    if seed <= factual_policy_seed <= seed + planned - 1:
        raise ValueError("Continuation seed schedule overlaps the factual policy phase seeds")
    metadata = deepcopy(probe.policy_metadata)
    rng = random.Random(permutation_seed)
    permutations = []
    slots = []

    def plan(role, pair_index, walk, step, held_indices, sample_index):
        index = len(slots)
        slots.append(DecisionShapleySlot(index, role, pair_index, walk, step,
                                        tuple(sorted(held_indices)), sample_index, seed + index))

    for role, held_indices in (("endpoint_empty", ()), ("endpoint_full", tuple(range(count)))):
        for sample_index in range(endpoint_samples):
            plan(role, None, None, None, held_indices, sample_index)
    for pair_index in range(pairs):
        permutation = list(range(count))
        rng.shuffle(permutation)
        permutations.append(tuple(permutation))
        for walk, order in (("forward", permutation), ("reverse", list(reversed(permutation)))):
            for step in range(count + 1):
                for sample_index in range(samples_per_eval):
                    plan("walk", pair_index, walk, step, order[:step], sample_index)
    initial_calls = continuation_policy.calls
    branches = []
    exhausted = False
    for slot in slots:
        before = continuation_policy.calls
        try:
            replay = replay_decision_coalition(
                factual, continuation_policy, held_indices=slot.held_indices,
                continuation_seed=slot.continuation_seed, template=template,
                coalition_game=coalition_game,
            )
        except (PolicyError, ValueError, TypeError) as error:
            replay = DecisionCoalitionReplay(
                slot.held_indices, slot.continuation_seed, factual.seed, count, deepcopy(metadata),
                (), continuation_policy.calls - before,
                error_type=type(error).__name__, error=str(error),
                budget_exhausted=isinstance(error, CallBudgetExceeded),
                coalition_game=coalition_game,
            )
        branches.append(DecisionShapleyBranch(slot, replay))
        if replay.budget_exhausted:
            exhausted = True
            break

    # Evaluate permitted outcomes once per completed branch, shared by all
    # targets. No evaluator-owned truth or reported assessment enters the game.
    cache = {branch.slot.index: (branch, episode_outcome(branch.replay.episode)
                                if branch.replay.episode is not None else None)
             for branch in branches}
    results = []
    endpoint_checks = []
    path_slots = tuple(slot for slot in slots if slot.role == "walk")
    for target in selected:
        values, statuses = _sample_values(slots, cache, target)
        path_coverage = _coverage(statuses[slot.index] for slot in path_slots)
        pair_vectors, pair_statuses = _pair_observations(
            permutations, path_slots, values, statuses, samples_per_eval, count)
        pair_counts = _coverage(pair_statuses)
        estimable = pair_counts.known == pairs
        for decision_index, event in enumerate(events):
            pair_values = tuple(vector[decision_index] if vector is not None else None
                                for vector in pair_vectors)
            point = interval = None
            reason = None
            if estimable:
                point = sum(pair_values) / pairs
                interval = _pair_interval(pair_values, float(confidence), interval_method)
            else:
                reason = _missing_reason(f"the complete {target} Shapley vector", path_coverage)
            results.append(DecisionShapleyEstimate(
                decision_index, event.id, target, "estimated" if estimable else "refused",
                point, interval, pair_values, pair_counts.known, pair_counts.unknown,
                pair_counts.invalid, pair_counts.failed, pair_counts.unstarted, path_coverage, reason,
            ))
        empty_slots = tuple(slot for slot in slots if slot.role == "endpoint_empty")
        full_slots = tuple(slot for slot in slots if slot.role == "endpoint_full")
        empty_coverage = _coverage(statuses[slot.index] for slot in empty_slots)
        full_coverage = _coverage(statuses[slot.index] for slot in full_slots)
        endpoint_estimable = (empty_coverage.known == endpoint_samples
                              and full_coverage.known == endpoint_samples)
        empty_rate = full_rate = endpoint_difference = interval = reason = None
        if endpoint_estimable:
            empty = tuple(values[slot.index] for slot in empty_slots)
            full = tuple(values[slot.index] for slot in full_slots)
            empty_rate = sum(empty) / endpoint_samples
            full_rate = sum(full) / endpoint_samples
            endpoint_difference = full_rate - empty_rate
            interval = _endpoint_interval(empty, full, float(confidence), endpoint_interval_method)
        else:
            reason = _missing_reason(f"{target} empty endpoint", empty_coverage) + " " + (
                _missing_reason(f"{target} full endpoint", full_coverage)
            )
        coefficient_sum = (sum(result.shapley_value for result in results if result.target == target)
                           if estimable else None)
        discrepancy = (coefficient_sum - endpoint_difference
                       if estimable and endpoint_estimable else None)
        endpoint_checks.append(DecisionShapleyEndpointCheck(
            target, "estimated" if endpoint_estimable else "refused", empty_rate, full_rate,
            endpoint_difference, interval, empty_coverage, full_coverage, coefficient_sum,
            discrepancy, reason,
        ))
    return DecisionShapleyResult(
        factual, tuple(slots), tuple(branches), tuple(results), tuple(endpoint_checks),
        tuple(permutations), metadata, selected, pairs, samples_per_eval, endpoint_samples,
        continuation_policy.calls - initial_calls, initial_calls, continuation_policy.max_calls,
        exhausted, template, float(confidence), permutation_seed,
        interval_method, endpoint_interval_method, coalition_game,
    )
