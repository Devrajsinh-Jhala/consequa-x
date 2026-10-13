"""Replay positional coalitions of captured decisions in isolated worlds.

A held position forces its captured decision at the same typed policy stage.
Earlier fresh decisions may change its public request, so this intervention does
not require the exact request equality used by decision-prefix replay. An absent
held position invalidates a branch by default. The separate on-reach game
records normally terminated later held positions as inactive.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable, Literal

from ..models import to_dict
from ..policies import PolicyError, PolicyReply, PolicyRequest, validate_reply
from .decision_replay import (
    DecisionReplayReceipt, _Capture, _json_key, _metadata, _validate_factual,
)
from .evaluation import BudgetedPolicy, CallBudgetExceeded
from .policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from .runner import Episode
from .templates import DEFAULT_REFUND_TEMPLATE, RefundTaskTemplate


COALITION_GAMES = ("strict", "on_reach")


def validate_coalition_game(game):
    if type(game) is not str or game not in COALITION_GAMES:
        raise ValueError("coalition_game must be strict or on_reach")


class DecisionCoalitionIncompatible(PolicyError):
    """A forced factual decision is incompatible with its reached boundary."""


class DecisionCoalitionUnreachable(PolicyError):
    """A completed rollout stopped before a required held position."""


@dataclass(frozen=True)
class DecisionCoalitionReplay:
    """One coalition branch, including partial receipts after failure."""

    held_indices: tuple[int, ...]
    continuation_seed: int
    factual_seed: int
    factual_decision_count: int
    policy_metadata: dict
    decisions: tuple[DecisionReplayReceipt, ...]
    policy_calls: int
    episode: Episode | None = None
    error_type: str | None = None
    error: str | None = None
    budget_exhausted: bool = False
    coalition_game: str = "strict"

    @property
    def status(self) -> Literal["completed", "invalid", "failed"]:
        if self.episode is not None:
            return "completed"
        if self.error_type in {
            "DecisionCoalitionIncompatible", "DecisionCoalitionUnreachable",
        }:
            return "invalid"
        return "failed"

    @property
    def unreached_factual_indices(self) -> tuple[int, ...]:
        return tuple(range(min(len(self.decisions), self.factual_decision_count),
                           self.factual_decision_count))

    @property
    def unreached_held_indices(self) -> tuple[int, ...]:
        return tuple(index for index in self.held_indices if index >= len(self.decisions))

    @property
    def inactive_held_indices(self) -> tuple[int, ...]:
        """Only normal termination in the declared on-reach game is inactivity."""
        return (self.unreached_held_indices
                if self.coalition_game == "on_reach" and self.episode is not None else ())

    def summary(self) -> dict:
        return {
            "status": self.status,
            "coalition_game": self.coalition_game,
            "inactive_held_indices": list(self.inactive_held_indices),
            "held_indices": list(self.held_indices),
            "continuation_seed": self.continuation_seed,
            "factual_seed": self.factual_seed,
            "factual_decision_count": self.factual_decision_count,
            "reached_decisions": len(self.decisions),
            "held_decisions": sum(item.source == "held_factual" and item.reply is not None
                                  for item in self.decisions),
            "resampled_decisions": sum(item.source == "resampled" and item.reply is not None
                                       for item in self.decisions),
            "held_requests": sum(item.source == "held_factual" for item in self.decisions),
            "resampled_requests": sum(item.source == "resampled" for item in self.decisions),
            "failed_decisions": sum(item.error_type is not None for item in self.decisions),
            "unreached_factual_indices": list(self.unreached_factual_indices),
            "unreached_held_indices": list(self.unreached_held_indices),
            "policy_calls": self.policy_calls,
            "budget_exhausted": self.budget_exhausted,
            "error_type": self.error_type,
            "error": self.error,
        }


class _CoalitionPolicy:
    def __init__(self, captures: tuple[_Capture, ...], policy: BudgetedPolicy,
                 held_indices: tuple[int, ...]):
        self.captures = captures
        self.policy = policy
        self.held_indices = frozenset(held_indices)
        self.receipts: list[DecisionReplayReceipt] = []
        self._metadata = deepcopy(captures[0].policy_metadata)

    @property
    def metadata(self):
        return deepcopy(self._metadata)

    def decide(self, request: PolicyRequest, *, seed: int) -> PolicyReply:
        index = len(self.receipts)
        capture = self.captures[index] if index < len(self.captures) else None
        source = "held_factual" if index in self.held_indices else "resampled"
        before = self.policy.calls
        request_data = to_dict(request)
        reply = None
        error = None
        try:
            if source == "held_factual":
                if request.stage != capture.request.stage:
                    raise DecisionCoalitionIncompatible(
                        "Held decision reached a different typed policy stage",
                    )
                reply = PolicyReply(deepcopy(capture.reply.decision), {
                    "decision_coalition_replay": {
                        "source": "forced_factual", "provider_call": False,
                        "factual_index": index,
                        "factual_event_id": capture.event_id,
                        "factual_model_seed": capture.model_seed,
                        "requested_continuation_model_seed": seed,
                        "exact_request_match": _json_key(request) == _json_key(capture.request),
                        "factual_reply_metadata": deepcopy(capture.reply.metadata),
                    },
                })
                try:
                    validate_reply(request, reply)
                except (PolicyError, TypeError, ValueError) as caught:
                    raise DecisionCoalitionIncompatible(
                        f"Held decision is invalid for the current public request: {caught}",
                    ) from caught
            else:
                if _json_key(_metadata(self.policy)) != _json_key(self._metadata):
                    raise PolicyError("Continuation policy metadata differs from factual policy")
                reply = self.policy.decide(deepcopy(request), seed=seed)
                if _json_key(_metadata(self.policy)) != _json_key(self._metadata):
                    raise PolicyError("Continuation policy metadata changed during its decision")
                validate_reply(request, reply)
            reply = deepcopy(reply)
            return reply
        except (PolicyError, TypeError, ValueError) as caught:
            error = caught
            raise
        finally:
            self.receipts.append(DecisionReplayReceipt(
                index, source, request.stage, seed,
                capture.event_id if capture else None, capture.model_seed if capture else None,
                self.policy.calls - before, request_data,
                to_dict(reply) if reply is not None and error is None else None,
                type(error).__name__ if error else None, str(error) if error else None,
            ))


def replay_decision_coalition(
    factual: Episode,
    continuation_policy: BudgetedPolicy,
    *,
    held_indices: Iterable[int],
    continuation_seed: int,
    template: RefundTaskTemplate = DEFAULT_REFUND_TEMPLATE,
    coalition_game: str = "strict",
) -> DecisionCoalitionReplay:
    """Reset the factual world and force the requested positional decisions.

    Full factual captures and declared policy identity are validated without
    provider calls before running a branch. Held decisions consume zero calls;
    fresh decisions use a shared actual-call budget. New reached positions beyond
    the factual trace are fresh. A branch may stop before unheld positions, but
    stopping before a held position invalidates a strict-game branch. In the
    explicit on-reach game, normally unreached held positions are inactive;
    the completed episode and its verified outcome remain the actual rollout.
    A reached but incompatible held decision is invalid under either game.

    Forced decisions are positional interventions, including their captured
    assessment and reported rationale. They need not be decisions the policy
    would choose under a changed request. Same-stage and current-reply validity
    checks keep this distinction explicit. Seeds do not establish model
    independence or hidden-state identity.
    """
    if not isinstance(factual, Episode):
        raise TypeError("factual must be an Episode")
    validate_coalition_game(coalition_game)
    if not isinstance(continuation_policy, BudgetedPolicy):
        raise TypeError("continuation_policy must be a BudgetedPolicy")
    if (type(continuation_policy.max_calls) is not int or continuation_policy.max_calls < 1
            or type(continuation_policy.calls) is not int
            or not 0 <= continuation_policy.calls <= continuation_policy.max_calls):
        raise ValueError("BudgetedPolicy counters must be integers within its valid call limit")
    if type(continuation_seed) is not int or not 0 <= continuation_seed <= MAX_TRIAL_SEED:
        raise ValueError(f"continuation_seed must be an integer in 0..{MAX_TRIAL_SEED}")
    if type(factual.seed) is not int or not 0 <= factual.seed <= MAX_TRIAL_SEED:
        raise ValueError(f"factual seed must be an integer in 0..{MAX_TRIAL_SEED}")
    if not isinstance(template, RefundTaskTemplate):
        raise TypeError("template must be a RefundTaskTemplate")
    try:
        positions = tuple(held_indices)
    except TypeError as caught:
        raise TypeError("held_indices must be an iterable of decision indices") from caught
    if any(type(index) is not int or index < 0 for index in positions):
        raise ValueError("held_indices must contain nonnegative integers")
    if len(set(positions)) != len(positions):
        raise ValueError("held_indices must not contain duplicate positions")
    held = tuple(sorted(positions))
    captures = _validate_factual(factual, template)
    if any(index >= len(captures) for index in held):
        raise ValueError("held_indices exceed the factual captured decision range")
    metadata = _metadata(continuation_policy)
    if _json_key(metadata) != _json_key(captures[0].policy_metadata):
        raise ValueError("Continuation policy metadata differs from factual policy")
    coalition_policy = _CoalitionPolicy(captures, continuation_policy, held)
    before = continuation_policy.calls
    episode = None
    error = None
    try:
        episode = run_policy_scenario(
            factual.config, coalition_policy, seed=factual.seed, policy_seed=continuation_seed,
            max_attempts=captures[0].request.attempts_remaining, template=template,
        )
        unreached = tuple(index for index in held if index >= len(coalition_policy.receipts))
        if unreached and coalition_game == "strict":
            raise DecisionCoalitionUnreachable(f"Held decision positions were not reached: {unreached}")
    except (PolicyError, TypeError, ValueError) as caught:
        error = caught
        episode = None
    return DecisionCoalitionReplay(
        held, continuation_seed, factual.seed, len(captures), deepcopy(metadata),
        tuple(coalition_policy.receipts), continuation_policy.calls - before, episode,
        type(error).__name__ if error else None, str(error) if error else None,
        isinstance(error, CallBudgetExceeded),
        coalition_game,
    )
