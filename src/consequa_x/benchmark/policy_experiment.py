"""Bounded paired context replay from one collection of policy episodes.

Every factual seed is generated once. The same completed episode cache supports
both action and consequence estimates; estimation makes no policy calls. Failed,
unstarted, and unknown pairs remain separate and refuse the affected estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from ..attribution import EffectEstimate, Intervention, ReplayOutcome, leave_one_out
from ..models import VerificationStatus
from ..policies import Policy, PolicyError
from .assessment_metrics import assessment_metrics
from .evaluation import BudgetedPolicy, CallBudgetExceeded
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .runner import Episode, ScenarioConfig, _intervene


@dataclass(frozen=True)
class ExperimentBranch:
    """One attempted world; a failure receipt has no completed episode."""

    index: int
    candidate_id: str | None
    seed: int
    policy_calls: int
    episode: Episode | None = None
    error_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ExperimentEstimate:
    """Coverage over every planned pair, including refused whole estimates."""

    event_id: str
    target: Literal["action", "consequence"]
    status: Literal["estimated", "refused"]
    estimate: EffectEstimate | None
    known_pairs: int
    unknown_pairs: int
    failed_pairs: int
    unstarted_pairs: int
    seeds: tuple[int, ...]
    reason: str | None = None


@dataclass(frozen=True)
class PolicyExperiment:
    branches: tuple[ExperimentBranch, ...]
    results: tuple[ExperimentEstimate, ...]
    policy_metadata: dict
    samples_per_condition: int
    seeds: tuple[int, ...]
    planned_branches: int
    calls: int
    max_calls: int
    budget_exhausted: bool
    config: ScenarioConfig
    interventions: tuple[Intervention, ...]
    max_attempts: int

    def summary(self) -> dict:
        completed = sum(branch.episode is not None for branch in self.branches)
        estimates = {
            target: {
                status: sum(result.target == target and result.status == status
                            for result in self.results)
                for status in ("estimated", "refused")
            }
            for target in ("action", "consequence")
        }
        return {
            "samples_per_condition": self.samples_per_condition,
            "candidate_count": len(self.interventions),
            "condition_count": len(self.interventions) + 1,
            "planned_branches": self.planned_branches,
            "attempted_branches": len(self.branches),
            "completed_branches": completed,
            "failed_branches": len(self.branches) - completed,
            "not_started_branches": self.planned_branches - len(self.branches),
            "policy_calls": self.calls,
            "max_calls": self.max_calls,
            "budget_exhausted": self.budget_exhausted,
            "estimates": estimates,
            "assessment_metrics": assessment_metrics(
                (branch.episode.trace.assessment.status,
                 branch.episode.explanation.assessment_alignment)
                for branch in self.branches if branch.episode is not None
            ),
        }


def _episode_outcome(episode: Episode) -> ReplayOutcome:
    status = episode.trace.verifications[-1].status
    consequence = None if status is VerificationStatus.UNKNOWN else (
        status is VerificationStatus.SATISFIED
    )
    return ReplayOutcome(episode.action_selected, consequence)


def _policy_metadata(bounded: BudgetedPolicy) -> dict:
    try:
        metadata = bounded.metadata
    except (TypeError, ValueError) as error:
        raise PolicyError("policy.metadata must contain finite JSON values") from error
    if type(metadata) is not dict:
        raise PolicyError("policy.metadata must be a JSON object")
    return metadata


class _CachedReplayRunner:
    """Existing estimators can only read the collected factual/changed pair."""

    def __init__(self, branches: dict[tuple[str | None, int], ExperimentBranch],
                 candidate: Intervention):
        self.branches = branches
        self.candidate = candidate

    def run(self, intervention: Intervention | None, seed: int) -> ReplayOutcome:
        if intervention is not None and intervention != self.candidate:
            raise ValueError("The cached runner only supports its declared intervention")
        candidate_id = None if intervention is None else intervention.event_id
        branch = self.branches.get((candidate_id, seed))
        if branch is None or branch.episode is None:
            raise ValueError("The cached runner requires a completed planned branch")
        return _episode_outcome(branch.episode)


def _estimate_from_cache(branches: dict[tuple[str | None, int], ExperimentBranch],
                         candidate: Intervention, seeds: tuple[int, ...],
                         target: Literal["action", "consequence"]) -> ExperimentEstimate:
    counts = {name: 0 for name in ("known", "unknown", "failed", "unstarted")}
    for seed in seeds:
        pair = (branches.get((None, seed)), branches.get((candidate.event_id, seed)))
        # Categories are disjoint. An observed failure takes priority over the
        # missing companion branch, and missing branches precede unknown state.
        if any(branch is not None and branch.episode is None for branch in pair):
            counts["failed"] += 1
        elif any(branch is None for branch in pair):
            counts["unstarted"] += 1
        elif target == "consequence" and any(
            _episode_outcome(branch.episode).consequence_satisfied is None for branch in pair
        ):
            counts["unknown"] += 1
        else:
            counts["known"] += 1
    estimate = None
    reason = None
    status: Literal["estimated", "refused"] = "refused"
    if counts["known"] == len(seeds):
        # Each target/candidate uses the same stored branch data. Repeated cache
        # reads here do not redraw a policy decision or start another world.
        estimate, = leave_one_out(
            _CachedReplayRunner(branches, candidate), (candidate,), samples=len(seeds),
            seed=seeds[0], target=target,
        )
        status = "estimated"
    else:
        reason = (
            f"Cannot estimate {target} effect: {counts['known']} of {len(seeds)} planned "
            f"pairs are usable; {counts['unknown']} unknown, {counts['failed']} failed, "
            f"{counts['unstarted']} unstarted. No pairs are dropped or redrawn."
        )
    return ExperimentEstimate(
        candidate.event_id, target, status, estimate, counts["known"], counts["unknown"],
        counts["failed"], counts["unstarted"], seeds, reason,
    )


def experiment_policy(policy: Policy, config: ScenarioConfig,
                      interventions: Iterable[Intervention], *, samples: int = 20,
                      seed: int = 0, max_calls: int = 400,
                      max_attempts: int = 2) -> PolicyExperiment:
    """Collect isolated paired branches before estimating either target.

    Execution order is all factual seeds, then all seeds for each candidate in
    input order. The generation budget spans the complete experiment. Provider
    and protocol failures produce receipts without semantic outcome labels.
    No failed branch is retried. Even one unusable planned pair refuses its
    entire candidate/target estimate; completed action choices remain usable
    when the consequence verifier reports unknown.

    Shared model phase seeds pair corresponding calls, but do not guarantee
    deterministic model output or reproduce a remote model's hidden state.
    """
    if not isinstance(config, ScenarioConfig):
        raise TypeError("config must be a ScenarioConfig")
    if type(samples) is not int or samples < 2:
        raise ValueError("samples must be an integer of at least 2")
    if type(seed) is not int or seed < 0 or seed + samples - 1 > MAX_TRIAL_SEED:
        raise ValueError(f"Paired seed schedule must stay in 0..{MAX_TRIAL_SEED}")
    if type(max_attempts) is not int or not 1 <= max_attempts <= 5:
        raise ValueError("max_attempts must be an integer in 1..5")
    candidates = tuple(interventions)
    if not candidates:
        raise ValueError("interventions must contain at least one candidate")
    if any(not isinstance(candidate, Intervention) for candidate in candidates):
        raise TypeError("interventions must contain Intervention records")
    if len({candidate.event_id for candidate in candidates}) != len(candidates):
        raise ValueError("interventions must have unique event_id values")
    candidates = tuple(Intervention(item.event_id, item.kind, item.replacement)
                       for item in candidates)
    # Validate every context ID and its typed replacement before a factual call.
    for candidate in candidates:
        _intervene(config.context, candidate)
    bounded = BudgetedPolicy(policy, max_calls)
    _policy_metadata(bounded)
    seeds = tuple(seed + offset for offset in range(samples))
    records: list[ExperimentBranch] = []
    exhausted = False
    for candidate in (None, *candidates):
        candidate_id = None if candidate is None else candidate.event_id
        for replay_seed in seeds:
            if bounded.calls >= max_calls:
                exhausted = True
                break
            calls_before = bounded.calls
            index = len(records)
            try:
                episode = run_policy_scenario(
                    config, bounded, seed=replay_seed, intervention=candidate,
                    max_attempts=max_attempts,
                )
                branch = ExperimentBranch(index, candidate_id, replay_seed,
                                          bounded.calls - calls_before, episode)
            except PolicyError as error:
                exhausted = isinstance(error, CallBudgetExceeded)
                branch = ExperimentBranch(
                    index, candidate_id, replay_seed, bounded.calls - calls_before,
                    error_type=type(error).__name__, error=str(error),
                )
            records.append(branch)
            if exhausted:
                break
        if exhausted:
            break
    cache = {(branch.candidate_id, branch.seed): branch for branch in records}
    results = tuple(
        _estimate_from_cache(cache, candidate, seeds, target)
        for candidate in candidates for target in ("action", "consequence")
    )
    return PolicyExperiment(
        tuple(records), results, _policy_metadata(bounded), samples, seeds,
        samples * (len(candidates) + 1),
        bounded.calls, max_calls, exhausted, config, candidates, max_attempts,
    )


def branch_record(branch: ExperimentBranch, *, root: Path | None = None) -> dict:
    """Export a receipt; hidden fixture truth belongs only in its own artifact."""
    record = {
        "index": branch.index,
        "condition": "factual" if branch.candidate_id is None else "intervened",
        "candidate_id": branch.candidate_id,
        "seed": branch.seed,
        "policy_calls": branch.policy_calls,
        "status": "completed" if branch.episode is not None else "failed",
    }
    if branch.episode is None:
        record.update(error_type=branch.error_type, error=branch.error)
    else:
        episode = branch.episode
        result = episode.trace.verifications[-1]
        record.update(
            scenario=episode.config.name,
            action_selected=episode.action_selected,
            verified_outcome=result.status.value,
            effect_origin=result.origin.value,
            reported_assessment=episode.trace.assessment.status.value,
            assessment_alignment=episode.explanation.assessment_alignment,
            diagnosis=episode.explanation.diagnosis,
        )
        if root is not None:
            stem = f"branch_{branch.index:04d}.json"
            record.update(trace=f"traces/{stem}", explanation=f"explanations/{stem}",
                          evaluator_truth=f"evaluator_truth/{stem}")
    return record
