"""Public-only refund policies and independent population interaction laws.

The factual refund/retry/stop is planted at three declared phase keys. Fresh
choices either follow a seeded Bernoulli law or one explicitly named component
of its four-point deterministic mixture. Neither policy sees evaluator truth.
"""

from dataclasses import dataclass
import math
import random
from types import MappingProxyType

from ..models import AssessmentStatus, ResponseStatus
from ..policies import PolicyDecision, PolicyError, PolicyReply, PolicyRequest, validate_seed
from .decision_coalition import validate_coalition_game
from .payments import Fault
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .runner import RefundContext, ScenarioConfig


TARGETS = ("action", "consequence", "action_linked_consequence")
COMPONENTS = ((False, False), (False, True), (True, False), (True, True))


def _probability(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite probability in 0..1")


@dataclass(frozen=True)
class RefundInteractionPolicy:
    selection_probability: float
    retry_probability: float
    factual_policy_seed: int
    fresh_selection: bool | None = None
    fresh_retry: bool | None = None

    def __post_init__(self):
        _probability(self.selection_probability, "selection_probability")
        _probability(self.retry_probability, "retry_probability")
        if type(self.factual_policy_seed) is not int or not 0 <= self.factual_policy_seed <= MAX_TRIAL_SEED:
            raise ValueError("factual_policy_seed is outside the valid world/model phase schedule")
        if not ((self.fresh_selection is None and self.fresh_retry is None)
                or (type(self.fresh_selection) is bool and type(self.fresh_retry) is bool)):
            raise ValueError("fresh component choices must both be booleans or both be None")

    @property
    def metadata(self):
        component = self.fresh_selection is not None
        return {
            "provider": "synthetic", "policy": "conditioned-refund-interaction", "version": "1",
            "selection_probability": self.selection_probability,
            "retry_probability": self.retry_probability,
            "fresh_rule": {
                "kind": "deterministic_mixture_component" if component else "seeded_bernoulli",
                "selection": self.fresh_selection, "retry": self.fresh_retry,
                "rng": None if component else "python_random.Random(model_phase_seed)",
                "is_live_stochastic_sample": False,
            },
            "conditioning": {
                "kind": "predeclared_factual_refund_retry_stop_intervention",
                "naturally_sampled_factual": False,
                "reserved_model_phase_seeds": [self.factual_policy_seed * 6 + i for i in range(3)],
                "operations": ["refund", "retry", "stop"],
            },
            "hidden_evidence_inputs": False,
        }

    def decide(self, request: PolicyRequest, *, seed: int):
        if not isinstance(request, PolicyRequest):
            raise PolicyError("Expected a PolicyRequest")
        validate_seed(seed)
        base = self.factual_policy_seed * 6
        if seed in (base, base + 1, base + 2):
            operation = ("refund", "retry", "stop")[seed - base]
            source = "reserved_factual_intervention"
        elif request.stage == "select":
            selected = (random.Random(seed).random() < self.selection_probability
                        if self.fresh_selection is None else self.fresh_selection)
            operation = "refund" if selected else "stop"
            source = self.metadata["fresh_rule"]["kind"]
        elif request.responses[-1].status is ResponseStatus.TIMEOUT and request.attempts_remaining:
            retry = (random.Random(seed).random() < self.retry_probability
                     if self.fresh_retry is None else self.fresh_retry)
            operation = "retry" if retry else "stop"
            source = self.metadata["fresh_rule"]["kind"]
        else:
            operation, source = "stop", "fixed_final_stop"
        return PolicyReply(PolicyDecision(operation, AssessmentStatus.UNKNOWN,
            "Transparent fixture choice from the declared public-stage rule."),
            {"seed": seed, "decision_source": source})


@dataclass(frozen=True)
class RefundInteractionMechanism:
    name: str
    selection_probability: float = .5
    retry_probability: float = .5
    use_idempotency: bool = False
    include_provenance: bool = True
    read_lag_ms: int = 0
    max_calls: int = 100

    def __post_init__(self):
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("name must be a nonempty string")
        _probability(self.selection_probability, "selection_probability")
        _probability(self.retry_probability, "retry_probability")
        if type(self.use_idempotency) is not bool or type(self.include_provenance) is not bool:
            raise ValueError("idempotency and provenance flags must be booleans")
        if type(self.read_lag_ms) is not int or self.read_lag_ms < 0:
            raise ValueError("read_lag_ms must be a nonnegative integer")
        if type(self.max_calls) is not int or self.max_calls < 3:
            raise ValueError("max_calls must leave three calls for the factual capture")

    def make_policy(self, *, factual_policy_seed, component=None):
        if component is not None and component not in COMPONENTS:
            raise ValueError("component must be one of the four Boolean choice pairs")
        return RefundInteractionPolicy(self.selection_probability, self.retry_probability,
            factual_policy_seed, *(component if component is not None else (None, None)))

    def scenario_config(self):
        return ScenarioConfig(name=self.name, fault=Fault.TIMEOUT_AFTER_COMMIT,
            context=RefundContext(retry_instruction=True), use_idempotency=self.use_idempotency,
            include_provenance=self.include_provenance, read_lag_ms=self.read_lag_ms)

    def capture_factual(self, *, seed, policy_seed):
        return run_policy_scenario(self.scenario_config(), self.make_policy(factual_policy_seed=policy_seed),
                                   seed=seed, policy_seed=policy_seed, max_attempts=2)

    def component_weights(self):
        p, q = self.selection_probability, self.retry_probability
        return tuple((p if selected else 1 - p) * (q if retry else 1 - q)
                     for selected, retry in COMPONENTS)

    def analytic_reference(self, *, coalition_game="on_reach"):
        """Closed-form population law, independent of rollout or sampled keys.

        An unknown or invalid component of positive mass refuses a coalition;
        no conditioning on known, valid, or reached branches is performed.
        """
        validate_coalition_game(coalition_game)
        p, q = self.selection_probability, self.retry_probability
        selected = [1. if mask & 1 else p for mask in range(8)]
        retry = [1. if mask & 2 else q for mask in range(8)]
        valid = [1. if coalition_game == "on_reach" else (
            selected[mask] * retry[mask] if mask & 4 else selected[mask] if mask & 2 else 1.)
            for mask in range(8)]
        targets = {}
        for target in TARGETS:
            bad = [1 - s if target == "action" or self.use_idempotency
                   else 1 - s * (1 - r) for s, r in zip(selected, retry)]
            unknown = [0. if target == "action" else 1. if self.read_lag_ms else (
                (s if self.use_idempotency else s * (1 - r))
                if target == "action_linked_consequence" and not self.include_provenance else 0.)
                for s, r in zip(selected, retry)]
            values = [value if valid[mask] == 1 and unknown[mask] == 0 else None
                      for mask, value in enumerate(bad)]
            eligible = all(value is not None for value in values)
            if eligible:
                if target == "action" or self.use_idempotency:
                    shares, interaction = [-(1 - p), 0., 0.], 0.
                else:
                    shares = [-(1 - p) * (1 - q) / 2, (1 + p) * (1 - q) / 2, 0.]
                    interaction = (1 - p) * (1 - q)
            else:
                shares, interaction = None, None
            endpoint_eligible = values[0] is not None and values[7] is not None
            targets[target] = {
                "coalition_bad_rates": values, "unknown_probabilities": unknown,
                "shapley_eligible": eligible, "shapley_values": shares,
                "selection_retry_interaction": interaction,
                "endpoint_eligible": endpoint_eligible,
                "endpoint_difference": values[7] - values[0] if endpoint_eligible else None,
                "reason": None if eligible else "positive invalid or unknown population mass",
            }
        return {"name": self.name, "coalition_game": coalition_game, "decision_count": 3,
                "selection_probability": p, "retry_probability": q,
                "population_not_finite_seed_claim": True,
                "coalition_valid_probabilities": valid, "targets": targets}


INTERACTION_MECHANISMS = MappingProxyType({item.name: item for item in (
    RefundInteractionMechanism("refund-p50-q50"),
    RefundInteractionMechanism("refund-p20-q80", .2, .8),
    RefundInteractionMechanism("refund-p80-q20", .8, .2),
    RefundInteractionMechanism("refund-p100-q100", 1., 1.),
    RefundInteractionMechanism("idempotent-p50-q50", use_idempotency=True),
    RefundInteractionMechanism("unknown-provenance-p50-q50", include_provenance=False),
    RefundInteractionMechanism("lagged-readback-p50-q50", read_lag_ms=1000),
    RefundInteractionMechanism("budget-p50-q50", max_calls=4),
)})
