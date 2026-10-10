"""Bounded policy evaluation with failures separate from verified outcomes."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..models import to_dict
from ..policies import Policy, PolicyError
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .runner import Episode, ScenarioConfig, demo_scenarios


class CallBudgetExceeded(PolicyError):
    """The evaluation refused another policy call before invoking the provider."""


class BudgetedPolicy:
    """Count attempted decisions, including provider and protocol failures."""

    def __init__(self, policy: Policy, max_calls: int):
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        self.policy = policy
        self.max_calls = max_calls
        self.calls = 0

    @property
    def metadata(self):
        return to_dict(self.policy.metadata)

    def decide(self, request, *, seed):
        if self.calls >= self.max_calls:
            raise CallBudgetExceeded("The policy-call budget is exhausted")
        self.calls += 1
        return self.policy.decide(request, seed=seed)


@dataclass(frozen=True)
class EvaluationSample:
    index: int
    scenario: str
    seed: int
    policy_calls: int
    episode: Episode | None = None
    error_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PolicyEvaluation:
    samples: tuple[EvaluationSample, ...]
    policy_metadata: dict
    planned_samples: int
    max_calls: int
    calls: int
    budget_exhausted: bool

    def summary(self) -> dict:
        counts = {name: 0 for name in ("satisfied", "violated", "unknown")}
        origin = {name: 0 for name in ("confirmed", "other_actor", "unknown")}
        alignment = {name: 0 for name in ("consistent", "contradicted", "unassessable")}
        completed = 0
        for sample in self.samples:
            if sample.episode is None:
                continue
            completed += 1
            verification = sample.episode.trace.verifications[-1]
            counts[verification.status.value] += 1
            origin[verification.origin.value] += 1
            label = sample.episode.explanation.assessment_alignment
            alignment[label] = alignment.get(label, 0) + 1
        return {
            "planned_samples": self.planned_samples,
            "attempted_samples": len(self.samples),
            "completed_samples": completed,
            "failed_samples": len(self.samples) - completed,
            "not_started_samples": self.planned_samples - len(self.samples),
            "policy_calls": self.calls,
            "max_calls": self.max_calls,
            "budget_exhausted": self.budget_exhausted,
            "verification": counts,
            "origin": origin,
            "assessment_alignment": alignment,
            "known_outcome_samples": counts["satisfied"] + counts["violated"],
        }


def evaluate_policy(policy: Policy, configs: Iterable[ScenarioConfig] | None = None, *,
                    samples: int = 2, seed: int = 0, max_calls: int = 100,
                    max_attempts: int = 2) -> PolicyEvaluation:
    """Evaluate fresh worlds; provider/protocol failures never become violations.

    Model calls are serial and bounded. A failed episode is retained as a failure
    receipt, not dropped or replaced by a second draw. No model-level attribution
    or generalization claim follows from these template-level smoke evaluations.
    """
    if type(samples) is not int or samples < 1:
        raise ValueError("samples must be a positive integer")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be in 1..5")
    configurations = tuple(demo_scenarios() if configs is None else configs)
    if not configurations or any(not isinstance(config, ScenarioConfig) for config in configurations):
        raise ValueError("configs must contain at least one ScenarioConfig")
    if len({config.name for config in configurations}) != len(configurations):
        raise ValueError("scenario names must be unique")
    if seed + len(configurations) * samples - 1 > MAX_TRIAL_SEED:
        raise ValueError("Evaluation seed schedule exceeds the model seed range")
    bounded = BudgetedPolicy(policy, max_calls)
    records = []
    exhausted = False
    for config in configurations:
        for _ in range(samples):
            if bounded.calls >= max_calls:
                exhausted = True
                break
            index = len(records)
            calls_before = bounded.calls
            try:
                episode = run_policy_scenario(config, bounded, seed=seed + index,
                                              max_attempts=max_attempts)
                record = EvaluationSample(index, config.name, seed + index,
                                          bounded.calls - calls_before, episode)
            except PolicyError as error:
                exhausted = isinstance(error, CallBudgetExceeded)
                record = EvaluationSample(index, config.name, seed + index,
                                          bounded.calls - calls_before,
                                          error_type=type(error).__name__, error=str(error))
            records.append(record)
            if exhausted:
                break
        if exhausted:
            break
    return PolicyEvaluation(tuple(records), bounded.metadata, len(configurations) * samples,
                            max_calls, bounded.calls, exhausted)


def evaluation_sample_record(sample: EvaluationSample, *, root: Path | None = None) -> dict:
    """Return an evaluator receipt without duplicating hidden truth into a trace."""
    record = {
        "index": sample.index, "scenario": sample.scenario, "seed": sample.seed,
        "policy_calls": sample.policy_calls,
        "status": "completed" if sample.episode is not None else "failed",
    }
    if sample.episode is None:
        record.update(error_type=sample.error_type, error=sample.error)
    else:
        episode = sample.episode
        result = episode.trace.verifications[-1]
        record.update(
            action_selected=episode.action_selected,
            verified_outcome=result.status.value,
            effect_origin=result.origin.value,
            reported_assessment=episode.trace.assessment.status.value,
            assessment_alignment=episode.explanation.assessment_alignment,
            diagnosis=episode.explanation.diagnosis,
        )
        if root is not None:
            stem = f"episode_{sample.index:04d}.json"
            record.update(trace=f"traces/{stem}", explanation=f"explanations/{stem}",
                          evaluator_truth=f"evaluator_truth/{stem}")
    return record
