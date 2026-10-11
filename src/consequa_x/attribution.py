"""Paired replay estimates for action selection and verified consequences.

An effect is ``baseline_rate - intervention_rate``. Positive values mean that
neutralizing/replacing the candidate reduced the target rate; negative values
mean that it increased it. These estimates are signed experimental effects,
not normalized responsibility shares or proof that a trace edge is causal.

Each runner call must start an isolated world and be reproducible for the same
intervention and seed. The schedule consists of ``seed, ..., seed + samples -
1``. One factual replay per seed is reused across candidates. Matching seeds
pairs the original and changed worlds; independent random streams across seeds
are the runner's responsibility. An interval describes this replay experiment,
not generalization to other agents, prompts, providers, or environments.

Intervals subtract Bonferroni-adjusted marginal Wilson bounds: each marginal
interval has nominal 97.5% coverage, giving nominal conservative 95% joint
coverage without assuming independence between the paired worlds. Wilson
coverage is approximate, especially at small sample counts; this is not an
exact finite-sample guarantee. The deliberately broad interval does not model
within-pair covariance. Missing consequence outcomes refuse the entire estimate
instead of turning unknowns into failures or selecting only complete pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite, sqrt
from statistics import NormalDist
from typing import Any, Iterable, Literal, Protocol, runtime_checkable


ReplayTarget = Literal["action", "consequence", "action_linked_consequence"]
REPLAY_TARGETS = ("action", "consequence", "action_linked_consequence")
_TARGETS = frozenset(REPLAY_TARGETS)
_TARGET_ATTRIBUTES = {
    "action": "action_selected",
    "consequence": "consequence_satisfied",
    "action_linked_consequence": "action_linked_consequence_satisfied",
}
_INTERVENTION_KINDS = frozenset({"neutralize", "replace"})
_CONTEXT_TYPES = frozenset({"user_input", "system_instruction", "retrieval", "memory_read"})
# Two two-sided 97.5% Wilson intervals form a nominal 95% joint bound.
_WILSON_Z = NormalDist().inv_cdf(0.9875)


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _integer(value: object, name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, not a boolean")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _finite_number(value: object, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(number) or not low <= number <= high:
        raise ValueError(f"{name} must be finite and between {low} and {high}")
    return number


def _copy_replacement(value: object, active: set[int] | None = None) -> object:
    """Validate and detach an ordinary JSON payload from its caller."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("replacement cannot contain nonfinite numbers")
        return value
    if not isinstance(value, (dict, list)):
        raise TypeError("replacement must contain only JSON values")
    if active is None:
        active = set()
    identity = id(value)
    if identity in active:
        raise ValueError("replacement cannot contain cyclic references")
    active.add(identity)
    try:
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise TypeError("replacement object keys must be strings")
            return {key: _copy_replacement(item, active) for key, item in value.items()}
        return [_copy_replacement(item, active) for item in value]
    finally:
        active.remove(identity)


@dataclass(frozen=True)
class Intervention:
    """A typed replay change, validated against history by the runner.

    ``neutralize`` uses the runner's declared neutral context representation.
    ``replace`` uses its declared semantic replacement rules. Deleting an
    arbitrary history item is not a supported intervention. A null replacement
    is allowed for ``replace`` when the runner's schema defines its meaning.
    Replacement payloads must be ordinary JSON values and are copied on
    construction. Each replay also receives a fresh copy, so a runner cannot
    mutate the payload used by a later sample.
    """

    event_id: str
    kind: str = "neutralize"
    replacement: object = None

    def __post_init__(self) -> None:
        _nonempty_string(self.event_id, "event_id")
        if not isinstance(self.kind, str) or self.kind not in _INTERVENTION_KINDS:
            raise ValueError("kind must be 'neutralize' or 'replace'")
        if self.kind == "neutralize" and self.replacement is not None:
            raise ValueError("neutralize does not accept a replacement")
        object.__setattr__(self, "replacement", _copy_replacement(self.replacement))

    def to_dict(self) -> dict[str, Any]:
        from .models import to_dict

        return to_dict(self)


@dataclass(frozen=True)
class ReplayOutcome:
    """A policy decision and an independently verified world-state outcome.

    ``None`` means the consequence remains unknown. A runner must not report
    a tool's response status or an agent's self-assessment as verification.
    The optional action-linked target requires evidence tying a qualifying
    consequence to the registered action. Ordinary state satisfaction alone
    does not establish that link. Older runners leave this target unknown.
    """

    action_selected: bool
    consequence_satisfied: bool | None
    action_linked_consequence_satisfied: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action_selected, bool):
            raise ValueError("action_selected must be a boolean")
        if self.consequence_satisfied is not None and not isinstance(
            self.consequence_satisfied, bool
        ):
            raise ValueError("consequence_satisfied must be a boolean or None")
        if self.action_linked_consequence_satisfied is not None and not isinstance(
            self.action_linked_consequence_satisfied, bool
        ):
            raise ValueError("action_linked_consequence_satisfied must be a boolean or None")

    def target_value(self, target: str) -> bool | None:
        """Read one declared replay target without deriving unknown outcomes."""
        if not isinstance(target, str) or target not in _TARGETS:
            raise ValueError(f"target must be one of {REPLAY_TARGETS!r}")
        return getattr(self, _TARGET_ATTRIBUTES[target])

    def to_dict(self) -> dict[str, Any]:
        from .models import to_dict

        record = to_dict(self)
        # Preserve the original two-field export for old runners. The optional
        # target is absent when unsupported or unknown, never encoded as false.
        if self.action_linked_consequence_satisfied is None:
            record.pop("action_linked_consequence_satisfied")
        return record


@runtime_checkable
class ReplayRunner(Protocol):
    """A resettable experiment, with shared randomness keyed by seed.

    Every call starts from the same initial conditions and an independent world.
    A call with ``None`` runs the factual context. Intervention validation and
    verification of the consequence belong to the runner. It must preserve a
    stable mapping from seed to exogenous randomness in both paired worlds.
    """

    def run(self, intervention: Intervention | None, seed: int) -> ReplayOutcome: ...


@dataclass(frozen=True)
class EffectEstimate:
    """An unnormalized rate difference from complete paired replay outcomes."""

    event_id: str
    target: str
    baseline_rate: float
    intervention_rate: float
    effect: float
    confidence_interval: tuple[float, float]
    samples: int
    seeds: tuple[int, ...]
    unknown_pairs: int = 0

    def __post_init__(self) -> None:
        _nonempty_string(self.event_id, "event_id")
        if not isinstance(self.target, str) or self.target not in _TARGETS:
            raise ValueError(f"target must be one of {REPLAY_TARGETS!r}")
        baseline = _finite_number(self.baseline_rate, "baseline_rate", 0.0, 1.0)
        changed = _finite_number(self.intervention_rate, "intervention_rate", 0.0, 1.0)
        effect = _finite_number(self.effect, "effect", -1.0, 1.0)
        if not isclose(effect, baseline - changed, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("effect must equal baseline_rate - intervention_rate")
        if not isinstance(self.confidence_interval, tuple) or len(self.confidence_interval) != 2:
            raise ValueError("confidence_interval must be a two-element tuple")
        lower = _finite_number(self.confidence_interval[0], "interval lower bound", -1.0, 1.0)
        upper = _finite_number(self.confidence_interval[1], "interval upper bound", -1.0, 1.0)
        if lower > upper or not lower <= effect <= upper:
            raise ValueError("confidence_interval must be ordered and contain effect")
        _integer(self.samples, "samples", minimum=2)
        if not isinstance(self.seeds, tuple) or len(self.seeds) != self.samples:
            raise ValueError("seeds must be a tuple with one seed per sample")
        for seed in self.seeds:
            _integer(seed, "seed")
        if len(set(self.seeds)) != self.samples:
            raise ValueError("sample seeds must be distinct")
        _integer(self.unknown_pairs, "unknown_pairs", minimum=0)
        if self.unknown_pairs:
            raise ValueError("a full estimate cannot contain unknown pairs")

    def to_dict(self) -> dict[str, Any]:
        from .models import to_dict

        return to_dict(self)


class InsufficientEvidenceError(ValueError):
    """A complete-pair estimate was refused because outcomes are missing."""

    def __init__(
        self,
        *,
        event_id: str,
        target: str,
        samples: int,
        known_pairs: int,
        unknown_pairs: int,
        seeds: tuple[int, ...],
    ) -> None:
        self.event_id = event_id
        self.target = target
        self.samples = samples
        self.known_pairs = known_pairs
        self.unknown_pairs = unknown_pairs
        self.seeds = seeds
        super().__init__(
            f"Cannot estimate {target} effect for {event_id!r}: "
            f"{unknown_pairs} of {samples} paired outcomes are unknown "
            f"({known_pairs} known pairs). No estimate is produced; "
            "unknown outcomes are neither failures nor discarded samples."
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": type(self).__name__,
            "event_id": self.event_id,
            "target": self.target,
            "samples": self.samples,
            "known_pairs": self.known_pairs,
            "unknown_pairs": self.unknown_pairs,
            "seeds": list(self.seeds),
        }


def _wilson_bounds(successes: int, samples: int) -> tuple[float, float]:
    rate = successes / samples
    z_squared = _WILSON_Z * _WILSON_Z
    denominator = 1.0 + z_squared / samples
    center = (rate + z_squared / (2.0 * samples)) / denominator
    half_width = (
        _WILSON_Z
        * sqrt(rate * (1.0 - rate) / samples + z_squared / (4.0 * samples * samples))
        / denominator
    )
    # Floating-point cancellation can exclude an observed rate of exactly
    # zero or one. The analytic Wilson endpoints are exact at these extremes.
    lower = 0.0 if successes == 0 else max(0.0, center - half_width)
    upper = 1.0 if successes == samples else min(1.0, center + half_width)
    return lower, upper


def _checked_run(
    runner: ReplayRunner, intervention: Intervention | None, seed: int
) -> ReplayOutcome:
    replay_intervention = (
        None
        if intervention is None
        else Intervention(intervention.event_id, intervention.kind, intervention.replacement)
    )
    outcome = runner.run(replay_intervention, seed)
    if not isinstance(outcome, ReplayOutcome):
        raise TypeError("ReplayRunner.run must return ReplayOutcome")
    return outcome


def leave_one_out(
    runner: ReplayRunner,
    interventions: Iterable[Intervention],
    *,
    samples: int = 20,
    seed: int = 0,
    target: str = "consequence",
) -> tuple[EffectEstimate, ...]:
    """Replay each single intervention against the same factual seed schedule.

    The output preserves intervention order and contains no responsibility
    normalization. For either consequence target, even one unknown pair raises
    :class:`InsufficientEvidenceError`; no partial tuple is returned. For the
    action target, an unknown consequence does not obscure a known decision.
    No intervention or baseline replay is run when candidates are empty.
    Candidate event IDs must be unique: an estimate identifies a single change
    to one event. Each interval applies to its own estimate and does not adjust
    for comparisons across multiple candidates.
    """

    _integer(samples, "samples", minimum=2)
    _integer(seed, "seed")
    if not isinstance(target, str) or target not in _TARGETS:
        raise ValueError(f"target must be one of {REPLAY_TARGETS!r}")
    if not callable(getattr(runner, "run", None)):
        raise TypeError("runner must implement run(intervention, seed)")
    candidates = tuple(interventions)
    if any(not isinstance(candidate, Intervention) for candidate in candidates):
        raise TypeError("interventions must contain Intervention records")
    if not candidates:
        return ()
    if len({candidate.event_id for candidate in candidates}) != len(candidates):
        raise ValueError("interventions must have unique event_id values")
    # Snapshot before running any world, then keep that snapshot private from
    # the runner; mutable caller-owned payloads cannot change later samples.
    candidates = tuple(
        Intervention(candidate.event_id, candidate.kind, candidate.replacement)
        for candidate in candidates
    )

    seeds = tuple(seed + offset for offset in range(samples))
    originals = tuple(_checked_run(runner, None, replay_seed) for replay_seed in seeds)
    estimates: list[EffectEstimate] = []
    for candidate in candidates:
        changed = tuple(_checked_run(runner, candidate, replay_seed) for replay_seed in seeds)
        factual_values = tuple(outcome.target_value(target) for outcome in originals)
        changed_values = tuple(outcome.target_value(target) for outcome in changed)
        if target != "action":
            unknown_pairs = sum(
                factual is None or counterfactual is None
                for factual, counterfactual in zip(factual_values, changed_values)
            )
            if unknown_pairs:
                raise InsufficientEvidenceError(
                    event_id=candidate.event_id,
                    target=target,
                    samples=samples,
                    known_pairs=samples - unknown_pairs,
                    unknown_pairs=unknown_pairs,
                    seeds=seeds,
                )

        baseline_count = sum(value is True for value in factual_values)
        intervention_count = sum(value is True for value in changed_values)
        baseline_rate = baseline_count / samples
        intervention_rate = intervention_count / samples
        factual_bounds = _wilson_bounds(baseline_count, samples)
        changed_bounds = _wilson_bounds(intervention_count, samples)
        interval = (
            max(-1.0, factual_bounds[0] - changed_bounds[1]),
            min(1.0, factual_bounds[1] - changed_bounds[0]),
        )
        estimates.append(
            EffectEstimate(
                event_id=candidate.event_id,
                target=target,
                baseline_rate=baseline_rate,
                intervention_rate=intervention_rate,
                effect=baseline_rate - intervention_rate,
                confidence_interval=interval,
                samples=samples,
                seeds=seeds,
            )
        )
    return tuple(estimates)


def recency_attribution(events: Iterable[Any], *, before_ms: int) -> str | None:
    """Return the last pre-decision context ID as a noncausal heuristic.

    Eligible types are user input, system instruction, retrieval, and memory
    read. Events at or after ``before_ms`` are excluded. Ties retain the later
    event in input order. This function never assigns a score or builds a causal
    graph link. The caller supplies the decision boundary explicitly.
    """

    _integer(before_ms, "before_ms", minimum=0)
    latest_id: str | None = None
    latest_time = -1
    for event in events:
        event_time = _integer(event.time_ms, "event.time_ms", minimum=0)
        event_type = getattr(event.type, "value", event.type)
        if event_type in _CONTEXT_TYPES and event_time < before_ms and event_time >= latest_time:
            latest_id = _nonempty_string(event.id, "event.id")
            latest_time = event_time
    return latest_id
