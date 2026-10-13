"""Predeclared repeated synthetic calibration through the production replayers.

Each replicate captures a deliberately planted factual trajectory in a fresh
refund world. Both estimators receive the same capture, with separate budgets
and disjoint continuation seeds. Analytic target labels enter only the scoring
stage; refusals remain in the planned-trial denominator and are never redrawn.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from statistics import NormalDist
from typing import Callable

from ..attribution import ReplayTarget
from ..models import EventType, to_dict
from ..policies import PolicyError
from .calibration_mechanisms import (
    CALIBRATION_MECHANISMS, CalibrationMechanism, get_calibration_mechanism,
)
from .decision_contrastive import (
    DecisionContrastiveResult, _interval_method, _selected_targets, contrastive_decisions,
)
from .decision_shapley import DecisionShapleyResult, _interval_methods, shapley_decisions
from .evaluation import BudgetedPolicy
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .runner import Episode
from .targets import episode_outcome


CALIBRATION_CASES = tuple(CALIBRATION_MECHANISMS) + ("budget-stop-q50",)
INTERVAL_COMPARISON_CASES = CALIBRATION_CASES + ("protective-stop-q0", "protective-stop-q100")


def _mechanism(name):
    if name in ("protective-stop-q0", "protective-stop-q100"):
        return CalibrationMechanism(name, 0. if name.endswith("q0") else 1.)
    return get_calibration_mechanism("protective-stop-q50" if name == "budget-stop-q50" else name)


@dataclass(frozen=True)
class CalibrationPlan:
    """Research-sized defaults; use an explicit small repeat count for smoke checks.

    ``max_calls`` applies independently to each method's factual recording plus
    continuation calls. The budget control uses an explicit limit of three.
    The two methods cannot consume one another's call allowance.
    """

    mechanisms: tuple[str, ...] = CALIBRATION_CASES
    repeats: int = 32
    samples: int = 16
    pairs: int = 16
    samples_per_eval: int = 1
    endpoint_samples: int = 16
    bootstrap_samples: int = 2000
    confidence: float = 0.95
    seed: int = 100
    max_calls: int = 400
    targets: tuple[ReplayTarget, ...] = ("action", "consequence", "action_linked_consequence")
    contrastive_interval_method: str = "percentile_bootstrap"
    shapley_interval_method: str = "normal"
    endpoint_interval_method: str = "normal"

    def __post_init__(self):
        if (not isinstance(self.mechanisms, tuple) or not self.mechanisms
                or any(not isinstance(name, str) or name not in INTERVAL_COMPARISON_CASES
                       for name in self.mechanisms)
                or len(set(self.mechanisms)) != len(self.mechanisms)):
            raise ValueError("mechanisms must be a nonempty tuple of distinct registered names")
        for name, minimum in (("repeats", 1), ("samples", 2), ("pairs", 2),
                              ("samples_per_eval", 1), ("endpoint_samples", 2),
                              ("bootstrap_samples", 2), ("max_calls", 1)):
            if type(getattr(self, name)) is not int or getattr(self, name) < minimum:
                raise ValueError(f"{name} must be an integer of at least {minimum}")
        if type(self.seed) is not int or not 0 <= self.seed <= MAX_TRIAL_SEED:
            raise ValueError(f"seed must be an integer in 0..{MAX_TRIAL_SEED}")
        try:
            valid = (type(self.confidence) in {int, float} and math.isfinite(self.confidence)
                     and 0 < self.confidence < 1)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("confidence must be finite and strictly between 0 and 1")
        if not isinstance(self.targets, tuple):
            raise ValueError("targets must be a tuple of distinct replay targets")
        _selected_targets(self.targets)
        _interval_method(self.contrastive_interval_method)
        _interval_methods(self.shapley_interval_method, self.endpoint_interval_method)
        # Bound the entire declared experiment before allocating its schedule.
        total = sum(_trial_seed_count(self, _mechanism(name).decision_count)
                    for name in self.mechanisms) * self.repeats
        if self.seed + total - 1 > MAX_TRIAL_SEED:
            raise ValueError("Complete calibration seed schedule exceeds the model seed range")
        last_inference = (6 * (self.seed + total - 1) + 6
                          + 2 * len(self.mechanisms) * self.repeats - 1)
        if last_inference > 2**31 - 1:
            raise ValueError("Complete calibration inference seed schedule exceeds its valid range")


@dataclass(frozen=True)
class CalibrationTrialPlan:
    index: int
    mechanism: str
    replicate: int
    decision_count: int
    factual_seed: int
    contrastive_seed: int
    contrastive_branches: int
    shapley_seed: int
    shapley_branches: int
    permutation_seed: int
    bootstrap_seed: int
    max_calls: int


def _trial_seed_count(plan: CalibrationPlan, decisions: int) -> int:
    return (1 + decisions * plan.samples + 2 * plan.endpoint_samples
            + 2 * plan.pairs * (decisions + 1) * plan.samples_per_eval)


def predeclare_calibration(plan: CalibrationPlan) -> tuple[CalibrationTrialPlan, ...]:
    """Reserve every capture, continuation and inference RNG key before execution."""
    if not isinstance(plan, CalibrationPlan):
        raise TypeError("plan must be a CalibrationPlan")
    trials = []
    cursor = plan.seed
    total = sum(_trial_seed_count(plan, _mechanism(name).decision_count)
                for name in plan.mechanisms) * plan.repeats
    inference_start = 6 * (plan.seed + total - 1) + 6
    for name in plan.mechanisms:
        decisions = _mechanism(name).decision_count
        contrastive_count = decisions * plan.samples
        shapley_count = (2 * plan.endpoint_samples
                         + 2 * plan.pairs * (decisions + 1) * plan.samples_per_eval)
        for replicate in range(plan.repeats):
            factual_seed = cursor
            contrastive_seed = factual_seed + 1
            shapley_seed = contrastive_seed + contrastive_count
            permutation_seed = inference_start + 2 * len(trials)
            bootstrap_seed = permutation_seed + 1
            trials.append(CalibrationTrialPlan(
                len(trials), name, replicate, decisions, factual_seed,
                contrastive_seed, contrastive_count, shapley_seed, shapley_count,
                permutation_seed, bootstrap_seed, 3 if name == "budget-stop-q50" else plan.max_calls,
            ))
            cursor = shapley_seed + shapley_count
    return tuple(trials)


@dataclass(frozen=True)
class CalibrationError:
    operation: str
    error_type: str
    error: str


@dataclass(frozen=True)
class CalibrationTrial:
    seed_plan: CalibrationTrialPlan
    factual: Episode | None
    shapley_factual: Episode | None
    factual_decisions: tuple[dict, ...]
    shapley_factual_decisions: tuple[dict, ...]
    contrastive: DecisionContrastiveResult | None
    shapley: DecisionShapleyResult | None
    contrastive_factual_calls: int
    shapley_factual_calls: int
    contrastive_calls: int
    shapley_calls: int
    errors: tuple[CalibrationError, ...]

    @property
    def factual_calls(self) -> int:
        return self.contrastive_factual_calls + self.shapley_factual_calls

    @property
    def policy_calls(self) -> int:
        return self.factual_calls + self.contrastive_calls + self.shapley_calls

    def summary(self) -> dict:
        return {
            "seed_plan": to_dict(self.seed_plan),
            "factual_status": "completed" if self.factual is not None else "failed",
            "shapley_factual_status": "completed" if self.shapley_factual is not None else "failed",
            "factual_decisions": to_dict(self.factual_decisions),
            "shapley_factual_decisions": to_dict(self.shapley_factual_decisions),
            "calls": {"factual": self.factual_calls, "contrastive": self.contrastive_calls,
                      "shapley": self.shapley_calls, "total": self.policy_calls},
            "errors": to_dict(self.errors),
            "contrastive": None if self.contrastive is None else self.contrastive.summary(),
            "shapley": None if self.shapley is None else self.shapley.summary(),
        }


@dataclass(frozen=True)
class CompactCalibrationTrial:
    """Portable inference receipts; full episodes are discarded after the callback."""

    seed_plan: CalibrationTrialPlan
    factual: dict
    contrastive: dict | None
    shapley: dict | None
    contrastive_factual_calls: int
    shapley_factual_calls: int
    contrastive_calls: int
    shapley_calls: int
    errors: tuple[CalibrationError, ...]

    @property
    def factual_calls(self) -> int:
        return self.contrastive_factual_calls + self.shapley_factual_calls

    @property
    def policy_calls(self) -> int:
        return self.factual_calls + self.contrastive_calls + self.shapley_calls

    def to_dict(self) -> dict:
        return {"seed_plan": to_dict(self.seed_plan), "factual": deepcopy(self.factual),
                "contrastive": deepcopy(self.contrastive), "shapley": deepcopy(self.shapley),
                "calls": {"contrastive_factual": self.contrastive_factual_calls,
                          "shapley_factual": self.shapley_factual_calls,
                          "factual": self.factual_calls, "contrastive": self.contrastive_calls,
                          "shapley": self.shapley_calls, "total": self.policy_calls},
                "errors": to_dict(self.errors)}


def _factual_record(episode, decisions, calls):
    return {"status": "completed" if episode is not None else "failed", "calls": calls,
            "trace_sha256": (hashlib.sha256(json.dumps(
                episode.trace.to_dict(), sort_keys=True, separators=(",", ":"),
                ensure_ascii=True, allow_nan=False,
            ).encode("utf-8")).hexdigest()
                             if episode is not None else None),
            "trace_hash_encoding": "UTF-8 JSON, sorted keys, compact separators, ensure_ascii=True",
            "targets": (to_dict(episode_outcome(episode)) if episode is not None else None),
            "decisions": to_dict(decisions)}


def _branch_record(replay, targets):
    if replay is None:
        return {"status": "unstarted", "policy_calls": 0, "target_values": None,
                "error_type": None, "error": None, "budget_exhausted": False,
                "reached_decisions": [], "unreached_held_indices": None}
    outcome = episode_outcome(replay.episode) if replay.episode is not None else None
    return {"status": (replay.status if hasattr(replay, "status") else
                       "completed" if replay.episode is not None else "failed"),
            "policy_calls": replay.policy_calls,
            "target_values": ({target: outcome.target_value(target) for target in targets}
                              if outcome is not None else None),
            "error_type": replay.error_type, "error": replay.error,
            "budget_exhausted": replay.budget_exhausted,
            "reached_decisions": [{"index": receipt.index, "source": receipt.source,
                                   "stage": receipt.stage,
                                   "continuation_model_seed": receipt.continuation_model_seed,
                                   "factual_model_seed": receipt.factual_model_seed,
                                   "factual_event_id": receipt.factual_event_id,
                                   "policy_calls": receipt.policy_calls,
                                   "error_type": receipt.error_type, "error": receipt.error}
                                  for receipt in replay.decisions],
            "unreached_held_indices": (list(replay.unreached_held_indices)
                                      if hasattr(replay, "unreached_held_indices") else None)}


def compact_calibration_trial(trial: CalibrationTrial) -> CompactCalibrationTrial:
    """Retain all planned slots and statistical inputs without retaining episodes."""
    contrastive = None
    if trial.contrastive is not None:
        result = trial.contrastive
        reached = {branch.index: branch.replay for branch in result.branches}
        branches = []
        for position, seeds in enumerate(result.planned_seeds):
            for sample, seed in enumerate(seeds):
                index = position * result.samples_per_decision + sample
                branches.append({"index": index, "decision_index": position,
                                 "continuation_seed": seed,
                                 **_branch_record(reached.get(index), result.targets)})
        contrastive = {"summary": result.summary(), "method_record": result.method_record(),
                       "results": [entry.to_dict() for entry in result.results],
                       "loci": to_dict(result.loci), "branches": branches}
    shapley = None
    if trial.shapley is not None:
        result = trial.shapley
        reached = {branch.slot.index: branch.replay for branch in result.branches}
        shapley = {"summary": result.summary(), "method_record": result.method_record(),
                   "results": [entry.to_dict() for entry in result.results],
                   "endpoint_checks": to_dict(result.endpoint_checks),
                   "permutations": to_dict(result.permutations),
                   "slots": to_dict(result.slots),
                   "branches": [{"slot_index": slot.index,
                                 **_branch_record(reached.get(slot.index), result.targets)}
                                for slot in result.slots]}
    return CompactCalibrationTrial(
        trial.seed_plan,
        {"contrastive": _factual_record(trial.factual, trial.factual_decisions,
                                         trial.contrastive_factual_calls),
         "shapley": _factual_record(trial.shapley_factual, trial.shapley_factual_decisions,
                                    trial.shapley_factual_calls)},
        contrastive, shapley, trial.contrastive_factual_calls, trial.shapley_factual_calls,
        trial.contrastive_calls, trial.shapley_calls, trial.errors,
    )


@dataclass(frozen=True)
class CalibrationResult:
    plan: CalibrationPlan
    trials: tuple[CompactCalibrationTrial, ...]

    def protocol(self) -> dict:
        schedule = predeclare_calibration(self.plan)
        return {
            "name": "conditional_synthetic_refund_calibration",
            "version": 1,
            "plan": to_dict(self.plan),
            "trial_schedule": to_dict(schedule),
            "planned_trials": len(schedule),
            "planned_contrastive_branches": sum(item.contrastive_branches for item in schedule),
            "planned_shapley_branches": sum(item.shapley_branches for item in schedule),
            "evaluator_analytic_references": {
                name: _mechanism(name).analytic_reference() for name in self.plan.mechanisms
            },
            "factual_capture": "predeclared planted trajectory; no seed search or conditioning by redraw",
            "world_seed": "each trial's factual_seed; held fixed within both estimators",
            "policy_seed_schedule": "globally disjoint factual and continuation phase ranges",
            "inference_seed_schedule": "distinct keys beyond every model phase key; permutation then bootstrap per trial",
            "budget": "each independent method budget includes its own factual recording and continuations",
            "paired_factual": "two actual recordings with the same declared world/policy key; no fabricated counter",
            "missingness": "every declared trial retained; no complete-case substitution or redraw",
            "scoring": "analytic reference enters the scorer only; production replayers use real traces",
            "replicate_uncertainty": "nominal Wilson binomial interval at plan.confidence",
            "scope": "exploratory_synthetic_calibration",
            "repeat_count_interpretation": "larger repeat counts improve metric precision, not study validity",
            "scope_limit": "synthetic conditional mechanisms; no population or live-model accuracy claim",
        }

    def summary(self) -> dict:
        return analyze_calibration(self)


class _RecordingPolicy:
    def __init__(self, policy):
        self.policy = policy
        self.decisions: list[dict] = []

    @property
    def metadata(self):
        return deepcopy(self.policy.metadata)

    def decide(self, request, *, seed):
        receipt = {"index": len(self.decisions), "seed": seed, "request": to_dict(request),
                   "reply": None, "error_type": None, "error": None}
        try:
            reply = self.policy.decide(request, seed=seed)
            receipt["reply"] = to_dict(reply)
            return reply
        except (PolicyError, ValueError, TypeError) as error:
            receipt.update(error_type=type(error).__name__, error=str(error))
            raise
        finally:
            self.decisions.append(receipt)


def run_calibration(plan: CalibrationPlan, *,
                    on_trial: Callable[[CalibrationTrial], None] | None = None) -> CalibrationResult:
    """Execute the immutable schedule without dropping failed or refused trials.

    ``on_trial`` is an optional serial export/progress hook. It receives every
    completed trial record once; callback exceptions propagate, because an
    export failure must not silently claim a complete experiment.
    """
    schedule = predeclare_calibration(plan)
    if on_trial is not None and not callable(on_trial):
        raise TypeError("on_trial must be callable or None")
    trials = []
    for item in schedule:
        mechanism = _mechanism(item.mechanism)
        factual = None
        shapley_factual = None
        contrastive = None
        shapley = None
        errors = []
        captures = {}
        budgets = {}
        recorders = {}
        factual_calls = {}
        for method in ("contrastive", "shapley"):
            policy = mechanism.make_policy(factual_policy_seed=item.factual_seed)
            recorder = _RecordingPolicy(policy)
            bounded = BudgetedPolicy(recorder, item.max_calls)
            recorders[method] = recorder
            budgets[method] = bounded
            try:
                captured = run_policy_scenario(mechanism.scenario_config(), bounded,
                                              seed=item.factual_seed, policy_seed=item.factual_seed,
                                              max_attempts=2)
                count = sum(event.type is EventType.AGENT_DECISION for event in captured.trace.events)
                if count != item.decision_count:
                    raise ValueError("Factual decision count differs from the predeclared mechanism")
                captures[method] = captured
            except (PolicyError, ValueError, TypeError) as error:
                errors.append(CalibrationError(f"{method}_factual", type(error).__name__, str(error)))
            factual_calls[method] = bounded.calls
            # The recorder is only for the factual capture. Continuation receipts
            # belong to the production replayer and are retained in its result.
            bounded.policy = policy
        factual = captures.get("contrastive")
        shapley_factual = captures.get("shapley")
        if factual is not None:
            try:
                contrastive = contrastive_decisions(
                    factual, budgets["contrastive"], samples=plan.samples,
                    seed=item.contrastive_seed, targets=plan.targets, confidence=plan.confidence,
                    bootstrap_samples=plan.bootstrap_samples, bootstrap_seed=item.bootstrap_seed,
                    interval_method=plan.contrastive_interval_method,
                )
            except (PolicyError, ValueError, TypeError) as error:
                errors.append(CalibrationError("contrastive", type(error).__name__, str(error)))
        if shapley_factual is not None:
            try:
                shapley = shapley_decisions(
                    shapley_factual, budgets["shapley"], pairs=plan.pairs,
                    samples_per_eval=plan.samples_per_eval,
                    endpoint_samples=plan.endpoint_samples, seed=item.shapley_seed,
                    permutation_seed=item.permutation_seed, confidence=plan.confidence,
                    targets=plan.targets,
                    interval_method=plan.shapley_interval_method,
                    endpoint_interval_method=plan.endpoint_interval_method,
                )
            except (PolicyError, ValueError, TypeError) as error:
                errors.append(CalibrationError("shapley", type(error).__name__, str(error)))
        trial = CalibrationTrial(
            item, factual, shapley_factual, tuple(recorders["contrastive"].decisions),
            tuple(recorders["shapley"].decisions), contrastive, shapley,
            factual_calls["contrastive"], factual_calls["shapley"],
            budgets["contrastive"].calls - factual_calls["contrastive"],
            budgets["shapley"].calls - factual_calls["shapley"], tuple(errors),
        )
        if on_trial is not None:
            on_trial(trial)
        trials.append(compact_calibration_trial(trial))
    return CalibrationResult(plan, tuple(trials))


def calibration_protocol(plan: CalibrationPlan) -> dict:
    """Obtain the complete predeclared protocol before collecting any results."""
    return CalibrationResult(plan, ()).protocol()


def wilson_rate(successes: int, trials: int, confidence: float = 0.95) -> dict:
    """Nominal uncertainty for a repeated-replicate binary metric, retaining N=0."""
    if (type(successes) is not int or type(trials) is not int
            or not 0 <= successes <= trials):
        raise ValueError("successes and trials must be integers with 0 <= successes <= trials")
    try:
        valid = (type(confidence) in {int, float} and math.isfinite(confidence)
                 and 0 < confidence < 1)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("confidence must be finite and strictly between 0 and 1")
    if trials == 0:
        return {"numerator": 0, "denominator": 0, "rate": None, "confidence_interval": None,
                "confidence": confidence, "interval_method": "Wilson score"}
    probability = successes / trials
    z = -NormalDist().inv_cdf((1 - confidence) / 2)
    scale = 1 + z * z / trials
    center = (probability + z * z / (2 * trials)) / scale
    margin = z / scale * math.sqrt(
        probability * (1 - probability) / trials + z * z / (4 * trials * trials)
    )
    interval = (0. if successes == 0 else max(0., center - margin),
                1. if successes == trials else min(1., center + margin))
    return {"numerator": successes, "denominator": trials, "rate": probability,
            "confidence_interval": interval, "confidence": confidence,
            "interval_method": "Wilson score"}


def _numeric_metrics(observations: list[tuple[float, tuple[float, float] | None]],
                     reference: float | None, confidence: float) -> dict:
    errors = [] if reference is None else [value - reference for value, _ in observations]
    intervals = [] if reference is None else [interval for _, interval in observations
                                               if interval is not None]
    covered = sum(lower <= reference <= upper for lower, upper in intervals)
    bias = sum(errors) / len(errors) if errors else None
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors)) if errors else None
    bias_mcse = None
    rmse_mcse = None
    if len(errors) >= 2:
        bias_mcse = math.sqrt(sum((error - bias) ** 2 for error in errors)
                              / ((len(errors) - 1) * len(errors)))
        mean_square = rmse * rmse
        squared_mcse = math.sqrt(sum((error * error - mean_square) ** 2 for error in errors)
                                 / ((len(errors) - 1) * len(errors)))
        rmse_mcse = squared_mcse / (2 * rmse) if rmse else None
    all_intervals = [interval for _, interval in observations if interval is not None]
    all_degenerate = sum(lower == upper for lower, upper in all_intervals)
    sign_eligible = reference is not None and reference != 0
    sign_detected = sum((lower > 0 if reference > 0 else upper < 0)
                        for lower, upper in all_intervals) if sign_eligible else 0
    return {
        "reference": reference,
        "scored_estimates": len(errors),
        "bias": bias, "bias_mcse": bias_mcse, "rmse": rmse, "rmse_mcse": rmse_mcse,
        "rmse_mcse_method": "delta method over independent replicate squared errors",
        "interval_coverage": wilson_rate(covered, len(intervals), confidence),
        "available_estimates": len(observations),
        "available_intervals": len(all_intervals),
        "mean_interval_width": (sum(upper-lower for lower, upper in all_intervals) / len(all_intervals)
                                if all_intervals else None),
        "reference_sign_detection": wilson_rate(sign_detected, len(all_intervals) if sign_eligible else 0,
                                                 confidence),
        "degenerate_intervals": all_degenerate,
        "degenerate_interval_rate": wilson_rate(all_degenerate, len(all_intervals), confidence),
    }


def _refusal_reason(trial, method, estimate):
    if estimate is None:
        operations = {error.operation for error in trial.errors}
        return "factual_failure" if f"{method}_factual" in operations else "method_failure"
    suffix = "samples" if method == "contrastive" else "pairs"
    if method == "contrastive" and estimate["factual_bad"] is None:
        return "unknown_factual"
    for name in ("unstarted", "failed", "invalid", "unknown"):
        if estimate.get(f"{name}_{suffix}", 0):
            return name
    return "unavailable"


def _endpoint_refusal_reason(trial, endpoint):
    if endpoint is None:
        return _refusal_reason(trial, "shapley", None)
    for name in ("unstarted", "failed", "invalid", "unknown"):
        if (endpoint["empty_coverage"].get(name, 0)
                or endpoint["full_coverage"].get(name, 0)):
            return name
    return "unavailable"


def analyze_calibration(result: CalibrationResult) -> dict:
    """Score production results against external analytic fixture references.

    Numerical coverage uses eligible, available intervals, with their explicit
    denominator. Refusal rates use every predeclared replicate. A target with
    unavailable analytic truth is reported as ineligible, never scored as zero.
    Counts are grouped by mechanism/target/position rather than pooling
    correlated decisions or two targets from one reused set of branch draws.
    """
    if not isinstance(result, CalibrationResult):
        raise TypeError("result must be a CalibrationResult")
    schedule = predeclare_calibration(result.plan)
    if (len(result.trials) != len(schedule)
            or any(trial.seed_plan != planned for trial, planned in zip(result.trials, schedule))):
        raise ValueError("Calibration results must retain every trial in the predeclared order")
    estimate_rows = []
    endpoint_rows = []
    locus_rows = []
    branch_rows = []
    for name in result.plan.mechanisms:
        trials = tuple(trial for trial in result.trials if trial.seed_plan.mechanism == name)
        analytic = _mechanism(name).analytic_reference()
        for method in ("contrastive", "shapley"):
            statuses = {status: 0 for status in ("completed", "invalid", "failed", "unstarted")}
            outcomes = {target: {"known": 0, "unknown": 0} for target in result.plan.targets}
            errors = {}
            for trial in trials:
                receipt = getattr(trial, method)
                if receipt is None:
                    statuses["unstarted"] += getattr(trial.seed_plan, f"{method}_branches")
                    continue
                for branch in receipt["branches"]:
                    statuses[branch["status"]] += 1
                    if branch["error_type"] is not None:
                        label = branch["error_type"]
                        errors[label] = errors.get(label, 0) + 1
                    if branch["status"] == "completed":
                        for target in result.plan.targets:
                            label = ("unknown" if branch["target_values"][target] is None else "known")
                            outcomes[target][label] += 1
            branch_rows.append({"mechanism": name, "method": method,
                                "planned_branches": sum(statuses.values()),
                                "status_counts": statuses, "completed_target_outcomes": outcomes,
                                "error_type_counts": errors})
            if method == "shapley":
                mechanism = _mechanism(name)
                q = mechanism.retry_probability
                retry = mechanism.factual_operation == "retry"
                conditional = []
                for trial in trials:
                    if trial.shapley is None:
                        conditional.append(None)
                    else:
                        exponent = result.plan.samples_per_eval * sum(
                            abs(order.index(1) - order.index(2))
                            for order in trial.shapley["permutations"]
                        ) if retry else 0
                        conditional.append(q**exponent)
                marginal = ((2 * q**result.plan.samples_per_eval
                             + q**(2 * result.plan.samples_per_eval)) / 3) ** result.plan.pairs
                branch_rows[-1]["nominal_structural_path_availability"] = {
                    "probability": marginal if retry else 1.,
                    "given_permutations": conditional,
                    "conditions": "ideal independent Bernoulli draws; excludes budget and target unknownness",
                    "meaning": "all held positions reached, not an analytically defined Shapley game",
                }
        for target in result.plan.targets:
            truth = analytic["targets"][target]
            for method in ("contrastive", "shapley"):
                references = truth["contrastive_effects" if method == "contrastive" else
                                   "shapley_values"]
                null_positions = truth[f"{method}_null_positions"]
                for position in range(analytic["decision_count"]):
                    reference = references[position] if references is not None else None
                    eligible = reference is not None
                    if method == "shapley" and not truth["shapley_eligible"]:
                        reference = None
                        eligible = False
                    observations = []
                    estimated = 0
                    exclusions = 0
                    interval_count = 0
                    reasons = {}
                    for trial in trials:
                        method_result = getattr(trial, method)
                        estimate = None if method_result is None else next(
                            (entry for entry in method_result["results"]
                             if entry["target"] == target and entry["decision_index"] == position), None,
                        )
                        if estimate is not None and estimate["status"] == "estimated":
                            estimated += 1
                            value = estimate["effect" if method == "contrastive" else "shapley_value"]
                            observations.append((value, estimate["confidence_interval"]))
                            interval = estimate["confidence_interval"]
                            interval_count += interval is not None
                            if (interval is not None and reference == 0
                                    and (interval[0] > 0 or interval[1] < 0)):
                                exclusions += 1
                        else:
                            reason = _refusal_reason(trial, method, estimate)
                            reasons[reason] = reasons.get(reason, 0) + 1
                    row = {
                        "mechanism": name, "method": method, "target": target,
                        "decision_index": position, "planned_trials": len(trials),
                        "estimated_trials": estimated, "refused_trials": len(trials) - estimated,
                        "reference_eligible_trials": len(trials) if eligible else 0,
                        "reference_ineligible_trials": 0 if eligible else len(trials),
                        "reference_reason": None if eligible else truth["reasons"][method],
                        "refusal_reason_counts": reasons,
                        "availability_rate": wilson_rate(estimated, len(trials), result.plan.confidence),
                        "refusal_rate": wilson_rate(len(trials) - estimated, len(trials),
                                                    result.plan.confidence),
                        **_numeric_metrics(observations, reference, result.plan.confidence),
                        "analytic_null_position": position in null_positions,
                        "zero_reference_interval_exclusion": wilson_rate(
                            exclusions, interval_count if reference == 0 else 0,
                            result.plan.confidence,
                        ),
                        "false_distractor_flags": exclusions if position in null_positions else None,
                    }
                    row["eligible_unscored_trials"] = row["reference_eligible_trials"] - row["scored_estimates"]
                    row["interval_coverage_including_refusals"] = wilson_rate(
                        row["interval_coverage"]["numerator"], len(trials) if eligible else 0,
                        result.plan.confidence,
                    )
                    row["coverage_composite_meaning"] = "available estimate and truth-covered interval / all eligible planned trials"
                    estimate_rows.append(row)

            endpoints = []
            endpoint_estimated = 0
            residuals = []
            coefficient_sums = []
            endpoint_reasons = {}
            for trial in trials:
                if trial.shapley is None:
                    reason = _endpoint_refusal_reason(trial, None)
                    endpoint_reasons[reason] = endpoint_reasons.get(reason, 0) + 1
                    continue
                endpoint = next(entry for entry in trial.shapley["endpoint_checks"]
                                if entry["target"] == target)
                if endpoint["status"] == "estimated":
                    endpoint_estimated += 1
                    endpoints.append((endpoint["endpoint_difference"], endpoint["confidence_interval"]))
                else:
                    reason = _endpoint_refusal_reason(trial, endpoint)
                    endpoint_reasons[reason] = endpoint_reasons.get(reason, 0) + 1
                if endpoint["coefficient_sum"] is not None:
                    coefficient_sums.append((endpoint["coefficient_sum"], None))
                if endpoint["discrepancy"] is not None:
                    residuals.append(endpoint["discrepancy"])
            endpoint_eligible = truth["endpoint_eligible"]
            endpoint_reference = truth["endpoint_difference"] if endpoint_eligible else None
            endpoint_row = {
                "mechanism": name, "target": target, "planned_trials": len(trials),
                "estimated_trials": endpoint_estimated,
                "refused_trials": len(trials) - endpoint_estimated,
                "reference_eligible_trials": len(trials) if endpoint_eligible else 0,
                "reference_ineligible_trials": 0 if endpoint_eligible else len(trials),
                "reference_reason": truth["reasons"]["endpoint"],
                "refusal_reason_counts": endpoint_reasons,
                "availability_rate": wilson_rate(endpoint_estimated, len(trials), result.plan.confidence),
                "refusal_rate": wilson_rate(len(trials) - endpoint_estimated, len(trials),
                                            result.plan.confidence),
                **_numeric_metrics(endpoints, endpoint_reference, result.plan.confidence),
                "coefficient_sum": _numeric_metrics(coefficient_sums,
                                                    endpoint_reference if truth["shapley_eligible"] else None,
                                                    result.plan.confidence),
                "efficiency_residual": {
                    "available_trials": len(residuals),
                    "mean": sum(residuals) / len(residuals) if residuals else None,
                    "root_mean_square": (math.sqrt(sum(value * value for value in residuals)
                                                   / len(residuals)) if residuals else None),
                    "confidence_interval": None,
                },
                "efficiency_residual_inference": "descriptive discrepancy; no calibrated interval or test",
            }
            endpoint_row["eligible_unscored_trials"] = (
                endpoint_row["reference_eligible_trials"] - endpoint_row["scored_estimates"]
            )
            endpoint_row["interval_coverage_including_refusals"] = wilson_rate(
                endpoint_row["interval_coverage"]["numerator"],
                len(trials) if endpoint_eligible else 0, result.plan.confidence,
            )
            endpoint_row["coverage_composite_meaning"] = "available endpoint and truth-covered interval / all eligible planned trials"
            endpoint_rows.append(endpoint_row)

            selections = {"refused": 0, "no_rescue": 0}
            for position in range(analytic["decision_count"]):
                selections[str(position)] = 0
            matches = 0
            locus_eligible = truth["contrastive_eligible"]
            expected = truth["latest_population_rescue"] if locus_eligible else None
            for trial in trials:
                locus = None if trial.contrastive is None else next(
                    entry for entry in trial.contrastive["loci"] if entry["target"] == target
                )
                key = ("refused" if locus is None or locus["status"] == "refused" else
                       "no_rescue" if locus["status"] == "no_rescue" else str(locus["decision_index"]))
                selections[key] += 1
                if locus_eligible and key != "refused":
                    matches += ((key == "no_rescue" and expected is None)
                                or key == str(expected))
            locus_rows.append({
                "mechanism": name, "target": target, "planned_trials": len(trials),
                "reference_eligible_trials": len(trials) if locus_eligible else 0,
                "reference_reason": truth["reasons"]["contrastive"],
                "latest_population_rescue": expected,
                "selection_counts": selections,
                "population_rule_match_including_refusals": wilson_rate(
                    matches, len(trials) if locus_eligible else 0, result.plan.confidence,
                ),
                "population_rule_match_given_available": wilson_rate(
                    matches, len(trials) - selections["refused"] if locus_eligible else 0,
                    result.plan.confidence,
                ),
                "interpretation": "latest position with strictly negative population effect; nominal selection rule",
            })
    return {
        "planned_trials": len(schedule), "retained_trials": len(result.trials),
        "factual_failures": sum(trial.factual[method]["status"] != "completed"
                                for trial in result.trials for method in ("contrastive", "shapley")),
        "actual_policy_calls": {
            "factual": sum(trial.factual_calls for trial in result.trials),
            "contrastive": sum(trial.contrastive_calls for trial in result.trials),
            "shapley": sum(trial.shapley_calls for trial in result.trials),
            "total": sum(trial.policy_calls for trial in result.trials),
        },
        "paired_factual_disagreements": sum(
            trial.factual["contrastive"]["trace_sha256"] is not None
            and trial.factual["shapley"]["trace_sha256"] is not None
            and trial.factual["contrastive"]["trace_sha256"] != trial.factual["shapley"]["trace_sha256"]
            for trial in result.trials),
        "estimates": estimate_rows, "endpoints": endpoint_rows, "loci": locus_rows,
        "branches": branch_rows,
        "limits": [
            "Numerical metrics condition on analytic eligibility and available estimates; every denominator is shown.",
            "Refusal and locus match rates retain all planned replicates rather than treating refusals as successes.",
            "Wilson intervals are nominal binomial uncertainty over replicates, not validation of seed independence.",
            "Positions and reused targets are reported separately; their correlated intervals are not pooled.",
            "The factual trajectory is deliberately planted; calibration is conditional on that capture and mechanism.",
            "The nominal latest rescue rule is not a unique-cause or population accuracy certificate.",
            "Synthetic mechanism coverage does not establish live-model generalization or calibrated LLM uncertainty.",
        ],
    }
