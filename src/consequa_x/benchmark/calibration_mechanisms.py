"""Predeclared synthetic refund mechanisms with analytic population references.

The factual timeout choice is a benchmark intervention at one declared phase
key, not a naturally sampled factual trajectory. Every other timeout choice
uses a seeded Bernoulli retry law. Policies read public requests only; the
reference below never observes a rollout, its labels, or its sampled seeds.
All effects still come from the ordinary isolated ``PaymentWorld`` runner.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from types import MappingProxyType
from typing import Literal

from ..models import AssessmentStatus, ResponseStatus
from ..policies import PolicyDecision, PolicyError, PolicyReply, PolicyRequest, validate_seed
from .payments import Fault
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .runner import Episode, RefundContext, ScenarioConfig


TARGETS = ("action", "consequence", "action_linked_consequence")


@dataclass(frozen=True)
class SeededRetryCalibrationPolicy:
    """Transparent benchmark policy, including its reserved factual phase key.

    Selection always refunds and the final response always stops. A timeout
    with attempts remaining retries with probability ``retry_probability``
    except at the exact reserved key, where the predeclared factual operation
    is forced. The same policy identity must be used for factual and replay.
    This conditioning is deliberately not a model or population factual draw.
    """

    retry_probability: float
    factual_operation: Literal["stop", "retry"] = "stop"
    factual_policy_seed: int = 0

    def __post_init__(self) -> None:
        _probability(self.retry_probability)
        _operation(self.factual_operation)
        _trial_seed(self.factual_policy_seed)

    @property
    def metadata(self) -> dict:
        return {
            "provider": "synthetic",
            "policy": "conditioned-bernoulli-refund-calibration",
            "version": "1",
            "retry_probability": self.retry_probability,
            "selection": "always_refund",
            "conditioning": {
                "kind": "predeclared_factual_timeout_intervention",
                "naturally_sampled_factual": False,
                "reserved_timeout_model_seed": self.factual_policy_seed * 6 + 1,
                "operation": self.factual_operation,
            },
            "continuation_rng": "python_random.Random(model_phase_seed)",
            "hidden_evidence_inputs": False,
        }

    def decide(self, request: PolicyRequest, *, seed: int) -> PolicyReply:
        if not isinstance(request, PolicyRequest):
            raise PolicyError("Expected a PolicyRequest")
        validate_seed(seed)
        # Only the public stage, remaining attempts and response status are used.
        # No task fault, independent readback, or evaluator truth is supplied.
        if request.stage == "select":
            decision = PolicyDecision("refund", rationale="The fixture always selects the refund.")
            source = "fixed_selection"
        elif request.responses[-1].status is ResponseStatus.TIMEOUT and request.attempts_remaining:
            forced = seed == self.factual_policy_seed * 6 + 1
            retry = self.factual_operation == "retry" if forced else (
                random.Random(seed).random() < self.retry_probability
            )
            decision = PolicyDecision("retry" if retry else "stop", AssessmentStatus.UNKNOWN,
                                      "The fixture applies its declared timeout retry rule.")
            source = "reserved_factual_intervention" if forced else "seeded_bernoulli_retry"
        else:
            decision = PolicyDecision("stop", AssessmentStatus.UNKNOWN,
                                      "The fixture stops after the final or non-timeout response.")
            source = "fixed_final_stop"
        return PolicyReply(decision, {"seed": seed, "decision_source": source})


def _probability(value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("retry_probability must be a finite probability in 0..1")


def _operation(value: str) -> None:
    if type(value) is not str or value not in {"stop", "retry"}:
        raise ValueError("factual_operation must be stop or retry")


def _trial_seed(value: int) -> None:
    if type(value) is not int or not 0 <= value <= MAX_TRIAL_SEED:
        raise ValueError(f"factual_policy_seed must be an integer in 0..{MAX_TRIAL_SEED}")


@dataclass(frozen=True)
class CalibrationMechanism:
    """One world configuration and its independently specified retry law."""

    name: str
    retry_probability: float
    factual_operation: Literal["stop", "retry"] = "stop"
    use_idempotency: bool = False
    include_provenance: bool = True
    read_lag_ms: int = 0

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("name must be a nonempty string")
        _probability(self.retry_probability)
        _operation(self.factual_operation)
        if type(self.use_idempotency) is not bool or type(self.include_provenance) is not bool:
            raise ValueError("use_idempotency and include_provenance must be booleans")
        if type(self.read_lag_ms) is not int or self.read_lag_ms < 0:
            raise ValueError("read_lag_ms must be a nonnegative integer")

    @property
    def decision_count(self) -> int:
        return 2 if self.factual_operation == "stop" else 3

    def make_policy(self, *, factual_policy_seed: int = 0) -> SeededRetryCalibrationPolicy:
        return SeededRetryCalibrationPolicy(
            self.retry_probability, self.factual_operation, factual_policy_seed,
        )

    def scenario_config(self) -> ScenarioConfig:
        return ScenarioConfig(
            name=self.name, fault=Fault.TIMEOUT_AFTER_COMMIT,
            context=RefundContext(retry_instruction=True),
            use_idempotency=self.use_idempotency,
            include_provenance=self.include_provenance, read_lag_ms=self.read_lag_ms,
        )

    def capture_factual(self, *, seed: int = 0, policy_seed: int = 0) -> Episode:
        """Convenience capture; budgeted callers should use the ordinary runner."""
        return run_policy_scenario(
            self.scenario_config(), self.make_policy(factual_policy_seed=policy_seed),
            seed=seed, policy_seed=policy_seed, max_attempts=2,
        )

    def analytic_reference(self) -> dict:
        """Describe the ideal Bernoulli game without running or reading episodes.

        Coalition arrays use integer bit masks: bit ``i`` holds decision ``i``.
        An undefined coalition retains ``None`` rather than a conditional mean
        among valid rollouts. Retry factuals can stop before their held final
        decision, so they have no complete Shapley population game for q < 1.
        Endpoint truth remains available when both complete endpoints are known.
        """
        n, q = self.decision_count, self.retry_probability
        retry_factual = self.factual_operation == "retry"
        valid = [q if n == 3 and mask & 4 and not mask & 2 else 1.
                 for mask in range(1 << n)]
        targets = {}
        for target in TARGETS:
            evidence_unknown = target != "action" and (
                bool(self.read_lag_ms)
                or (target == "action_linked_consequence" and not self.include_provenance)
            )
            # Without provenance, a duplicate still violates the state contract
            # and has a known false linked target. The protective factual and
            # held-stop coalitions nevertheless remain unknown.
            factual_known_violation = retry_factual and not self.use_idempotency
            factual_bad = (False if target == "action" else (
                None if self.read_lag_ms else (
                    True if factual_known_violation else (None if evidence_unknown else False)
                )
            ))
            numeric = not evidence_unknown
            if target == "action":
                changed = [0.] * n
                coalition = [0. if probability == 1 else None for probability in valid]
            elif numeric:
                fresh_bad = 0. if self.use_idempotency else float(q)
                changed = [fresh_bad, fresh_bad] + ([float(bool(factual_bad))] if n == 3 else [])
                coalition = [
                    None if valid[mask] < 1 else (
                        float(bool(factual_bad)) if mask & 2 else fresh_bad
                    )
                    for mask in range(1 << n)
                ]
            else:
                # With missing provenance, a fresh draw that necessarily
                # duplicates is still a known violation. All other fresh laws
                # have positive unknown probability and no binary mean.
                fresh_bad = (1. if not self.read_lag_ms and not self.use_idempotency and q == 1
                             else None)
                changed = [fresh_bad, fresh_bad] + (
                    [float(factual_bad) if factual_bad is not None else None] if n == 3 else []
                )
                coalition = [
                    None if valid[mask] < 1 else (
                        float(factual_bad) if factual_bad is not None else None
                    ) if mask & 2 else fresh_bad for mask in range(1 << n)
                ]
            effects = [None if rate is None or factual_bad is None else rate - int(factual_bad)
                       for rate in changed]
            contrastive_eligible = factual_bad is not None and all(value is not None for value in effects)
            shapley_eligible = all(value is not None for value in coalition)
            endpoint_eligible = coalition[0] is not None and coalition[-1] is not None
            if shapley_eligible:
                # The initial selection is always the same operation; holding
                # the timeout choice alone changes the population retry rate.
                shares = [0., coalition[2] - coalition[0]] + ([0.] if n == 3 else [])
            else:
                shares = None
            latest = max((i for i, effect in enumerate(effects) if effect is not None and effect < 0),
                         default=None) if contrastive_eligible else None
            unknown_reason = "independent outcome evidence is unknown"
            invalid_reason = "a fresh timeout stop can make held terminal decision 2 unreachable"
            targets[target] = {
                "factual_bad": factual_bad,
                "changed_bad_rates": changed,
                "contrastive_effects": effects,
                "latest_population_rescue": latest,
                "coalition_bad_rates": coalition,
                "contrastive_eligible": contrastive_eligible,
                "shapley_eligible": shapley_eligible,
                "endpoint_eligible": endpoint_eligible,
                "shapley_values": shares,
                "endpoint_difference": coalition[-1] - coalition[0] if endpoint_eligible else None,
                "contrastive_null_positions": [i for i, effect in enumerate(effects) if effect == 0],
                "shapley_null_positions": [i for i, share in enumerate(shares or ()) if share == 0],
                "reasons": {
                    "contrastive": None if contrastive_eligible else unknown_reason,
                    "shapley": None if shapley_eligible else (
                        invalid_reason if any(probability < 1 for probability in valid) else unknown_reason
                    ),
                    "endpoint": None if endpoint_eligible else unknown_reason,
                },
            }
        return {
            "name": self.name, "decision_count": n,
            "retry_probability": q,
            "conditioning": "fixed factual timeout intervention; ideal Bernoulli continuation law",
            "population_not_finite_seed_claim": True,
            "coalition_valid_probabilities": valid,
            "targets": targets,
        }


CALIBRATION_MECHANISMS = MappingProxyType({
    **{f"protective-stop-q{int(q * 100)}": CalibrationMechanism(f"protective-stop-q{int(q * 100)}", q)
       for q in (.1, .5, .9)},
    **{f"retry-pivot-q{int(q * 100)}": CalibrationMechanism(f"retry-pivot-q{int(q * 100)}", q, "retry")
       for q in (.1, .5, .9)},
    "idempotent-stop-q50": CalibrationMechanism("idempotent-stop-q50", .5, use_idempotency=True),
    "unknown-provenance-stop-q50": CalibrationMechanism("unknown-provenance-stop-q50", .5,
                                                       include_provenance=False),
    "lagged-readback-stop-q50": CalibrationMechanism("lagged-readback-stop-q50", .5, read_lag_ms=1000),
})


def get_calibration_mechanism(name: str) -> CalibrationMechanism:
    if type(name) is not str or name not in CALIBRATION_MECHANISMS:
        raise ValueError(f"Unknown calibration mechanism: {name!r}")
    return CALIBRATION_MECHANISMS[name]
