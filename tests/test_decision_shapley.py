"""Decision Shapley coverage and pair-level statistics have independent oracles.

Real fixed-length refund replays exercise capture, calls and failure handling.
The declared payoff adapter below tests cooperative-game mathematics only; its
AND/protective outcomes are not evidence of refund interaction recovery.
"""

from copy import deepcopy
from dataclasses import replace
import math
import random
from statistics import NormalDist

import pytest

from consequa_x.attribution import ReplayOutcome
from consequa_x.benchmark import decision_shapley as subject
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from consequa_x.benchmark.runner import ScenarioConfig, run_scenario
from consequa_x.benchmark.templates import DEFAULT_REFUND_TEMPLATE, REFUND_TASK_TEMPLATES
from consequa_x.models import EventType
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply, ScriptedRefundPolicy


class FixedLengthPolicy(ScriptedRefundPolicy):
    def __init__(self, *, failure_seeds=(), invalid_seeds=(), stop_fresh=False):
        self.requests = []
        self.failure_seeds = frozenset(failure_seeds)
        self.invalid_seeds = frozenset(invalid_seeds)
        self.stop_fresh = stop_fresh

    @property
    def metadata(self):
        return {"provider": "test", "policy": "fixed-length", "version": "1"}

    def decide(self, request, *, seed):
        self.requests.append((deepcopy(request), seed))
        if seed in self.failure_seeds:
            raise PolicyError("Deliberate provider failure")
        operation = "refund" if request.stage == "select" else (
            "retry" if request.attempts_remaining else "stop"
        )
        if seed in self.invalid_seeds:
            operation = "retry" if request.stage == "select" else "refund"
        if self.stop_fresh and seed >= 600:
            operation = "stop"
        return PolicyReply(PolicyDecision(operation), {"seed": seed})


class StopPolicy(FixedLengthPolicy):
    def decide(self, request, *, seed):
        self.requests.append((deepcopy(request), seed))
        return PolicyReply(PolicyDecision("stop"), {"seed": seed})


def recorded(policy=None, config=None, *, seed=0, policy_seed=None,
             template=DEFAULT_REFUND_TEMPLATE):
    return run_policy_scenario(
        config or ScenarioConfig("fixed-length-control", Fault.CLEAN, use_idempotency=False),
        policy or FixedLengthPolicy(), seed=seed, policy_seed=policy_seed,
        max_attempts=2, template=template,
    )


def analyze(original=None, policy=None, **kwargs):
    return subject.shapley_decisions(
        original or recorded(), BudgetedPolicy(policy or FixedLengthPolicy(), 1000),
        pairs=kwargs.pop("pairs", 2), endpoint_samples=kwargs.pop("endpoint_samples", 2),
        **kwargs,
    )


def by_target(result, target="consequence"):
    return tuple(item for item in result.results if item.target == target)


def payoff_adapter(monkeypatch, payoff):
    """Supply a declared game at the sampler boundary, retaining real replay."""
    real_replay = subject.replay_decision_coalition
    real_outcome = subject.episode_outcome
    labels, invocations, outcomes = {}, [], []

    def replay(*args, held_indices, continuation_seed, **kwargs):
        held_indices = tuple(held_indices)
        replayed = real_replay(*args, held_indices=held_indices,
                               continuation_seed=continuation_seed, **kwargs)
        invocations.append((held_indices, continuation_seed, replayed))
        if replayed.episode is not None:
            labels[id(replayed.episode)] = payoff(frozenset(held_indices), continuation_seed)
        return replayed

    def outcome(episode):
        outcomes.append(id(episode))
        if id(episode) not in labels:
            return real_outcome(episode)
        bad = labels[id(episode)]
        target = None if bad is None else not bad
        return ReplayOutcome(episode.action_selected, target, target)

    monkeypatch.setattr(subject, "replay_decision_coalition", replay)
    monkeypatch.setattr(subject, "episode_outcome", outcome)
    return invocations, outcomes


def normal_oracle(values, confidence=.95):
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = -NormalDist().inv_cdf((1 - confidence) / 2) * math.sqrt(variance / len(values))
    return mean - margin, mean + margin


def test_real_control_complete_zero_shares_and_actual_call_receipts():
    original = recorded()
    before = original.trace.to_json()
    policy = FixedLengthPolicy()
    result = analyze(original, policy,
                     targets=("action", "consequence", "action_linked_consequence"))
    assert result.factual == original and original.trace.to_json() == before
    assert result.pairs == result.endpoint_samples == 2
    assert result.samples_per_eval == 1 and result.calls == len(policy.requests) == 30
    assert result.initial_calls == 0 and not result.budget_exhausted
    assert len(result.slots) == len(result.branches) == 20
    assert [slot.continuation_seed for slot in result.slots] == list(range(100, 120))
    assert all(branch.replay.status == "completed" for branch in result.branches)
    for item in result.results:
        assert item.status == "estimated" and item.shapley_value == 0
        assert item.confidence_interval == (0., 0.) and item.interval_degenerate
        assert item.pair_values == (0., 0.) and item.known_pairs == 2
        assert item.coverage.planned == item.coverage.known == 16
        assert item.reason is None
    for endpoint in result.endpoint_checks:
        assert endpoint.status == "estimated" and endpoint.endpoint_difference == 0
        assert endpoint.coefficient_sum == endpoint.discrepancy == 0
        assert endpoint.confidence_interval == (0., 0.)
    assert result.summary()["completed_branches"] == 20


def test_antithetic_AND_game_equal_shares_and_dummy_zero(monkeypatch):
    invocations, outcomes = payoff_adapter(monkeypatch, lambda held, seed: {0, 1} <= held)
    result = analyze(targets=("consequence", "action_linked_consequence"), pairs=7)
    for target in result.targets:
        for item, expected in zip(by_target(result, target), (.5, .5, 0.), strict=True):
            assert item.shapley_value == expected
            assert item.pair_values == (expected,) * 7
            assert item.confidence_interval == (expected, expected)
        endpoint = next(item for item in result.endpoint_checks if item.target == target)
        assert endpoint.endpoint_difference == endpoint.coefficient_sum == 1
        assert endpoint.discrepancy == 0
    assert len(invocations) == len(result.slots) + 1  # One full factual probe.
    assert invocations[0][2].policy_calls == 0
    assert len(outcomes) == len(result.branches)  # All targets share one outcome cache.
    assert len(set(seed for _, seed, _ in invocations[1:])) == len(result.slots)


def test_protective_game_retains_negative_signed_share_without_normalization(monkeypatch):
    payoff_adapter(monkeypatch, lambda held, seed: 1 not in held)
    result = analyze()
    assert tuple(item.shapley_value for item in result.results) == (0., -1., 0.)
    assert result.endpoint_checks[0].endpoint_difference == -1
    assert result.endpoint_checks[0].coefficient_sum == -1
    assert all(item.status == "estimated" for item in result.results)


def test_pair_mean_interval_uses_two_pairs_not_four_walks_and_stays_unclipped(monkeypatch):
    payoff_adapter(monkeypatch, lambda held, seed: bool(held) or seed not in {108, 110})
    policy = StopPolicy()
    result = analyze(recorded(policy), policy)
    item = result.results[0]
    assert item.pair_values == (0., 1.) and item.shapley_value == .5
    assert item.confidence_interval == pytest.approx(normal_oracle((0., 1.)))
    assert item.confidence_interval[0] < 0 and item.confidence_interval[1] > 1
    endpoint = result.endpoint_checks[0]
    assert endpoint.endpoint_difference == 0
    assert endpoint.coefficient_sum == endpoint.discrepancy == .5


def test_independent_endpoint_interval_uses_empty_block_sample_variance(monkeypatch):
    payoff_adapter(monkeypatch, lambda held, seed: bool(held) or seed != 100)
    policy = StopPolicy()
    result = analyze(recorded(policy), policy)
    endpoint = result.endpoint_checks[0]
    assert endpoint.empty_bad_rate == .5 and endpoint.full_bad_rate == 1
    assert endpoint.endpoint_difference == .5
    assert endpoint.confidence_interval == pytest.approx(normal_oracle((0., 1.)))
    assert endpoint.coefficient_sum == 0 and endpoint.discrepancy == -.5


def test_multiple_draws_per_coalition_are_means_before_marginal_and_pair_average(monkeypatch):
    payoff_adapter(monkeypatch, lambda held, seed: bool(held) or seed % 2 == 0)
    policy = StopPolicy()
    result = analyze(recorded(policy), policy, samples_per_eval=2)
    assert len(result.slots) == 20
    assert result.results[0].shapley_value == .5
    assert result.results[0].pair_values == (.5, .5)
    assert result.results[0].confidence_interval == (.5, .5)
    assert result.results[0].coverage.known == 16


def test_schedule_permutations_and_reverse_coalition_chains_are_independently_verified():
    result = analyze(pairs=5, samples_per_eval=2, endpoint_samples=3, permutation_seed=19)
    assert len(result.slots) == 6 + 5 * 2 * 4 * 2
    generator = random.Random(19)
    expected_permutations = []
    for pair_index in range(5):
        order = list(range(3))
        generator.shuffle(order)
        expected_permutations.append(tuple(order))
        for walk, sequence in (("forward", order), ("reverse", list(reversed(order)))):
            slots = [slot for slot in result.slots
                     if slot.pair_index == pair_index and slot.walk == walk]
            assert len(slots) == 8
            for step in range(4):
                draws = [slot for slot in slots if slot.step == step]
                assert [slot.sample_index for slot in draws] == [0, 1]
                assert all(slot.held_indices == tuple(sorted(sequence[:step])) for slot in draws)
    assert result.permutations == tuple(expected_permutations)
    assert [slot.role for slot in result.slots[:6]] == ["endpoint_empty"] * 3 + ["endpoint_full"] * 3
    assert all(slot.index == index and slot.continuation_seed == 100 + index
               for index, slot in enumerate(result.slots))


def test_unknown_single_path_draw_refuses_entire_vector_without_dropping_pairs(monkeypatch):
    payoff_adapter(monkeypatch, lambda held, seed: None if seed == 104 else {0, 1} <= held)
    result = analyze(targets=("action", "consequence"))
    assert all(item.status == "estimated" for item in by_target(result, "action"))
    for item in by_target(result):
        assert item.status == "refused" and item.shapley_value is item.confidence_interval is None
        assert item.known_pairs == item.unknown_pairs == 1
        assert item.coverage.unknown == 1 and item.coverage.known == 15
        assert item.pair_values[0] is None and item.pair_values[1] is not None
        assert item.interval_degenerate is None and item.reason
    endpoint = next(item for item in result.endpoint_checks if item.target == "consequence")
    assert endpoint.status == "estimated" and endpoint.endpoint_difference == 1
    assert endpoint.coefficient_sum is endpoint.discrepancy is None


def test_endpoint_unknown_does_not_erase_complete_path_vector(monkeypatch):
    payoff_adapter(monkeypatch, lambda held, seed: None if seed == 100 else {0, 1} <= held)
    result = analyze()
    assert tuple(item.shapley_value for item in result.results) == (.5, .5, 0.)
    endpoint = result.endpoint_checks[0]
    assert endpoint.status == "refused" and endpoint.empty_coverage.unknown == 1
    assert endpoint.endpoint_difference is endpoint.discrepancy is None
    assert endpoint.coefficient_sum == 1


@pytest.mark.parametrize("failure_kind", ["provider", "protocol"])
def test_failed_path_retains_receipt_refuses_whole_vector_and_does_not_redraw(failure_kind):
    option = "failure_seeds" if failure_kind == "provider" else "invalid_seeds"
    policy = FixedLengthPolicy(**{option: (624,)})  # First path empty-coalition selection.
    result = analyze(policy=policy)
    assert len(result.branches) == len(result.slots) == 20
    failed = result.branches[4].replay
    assert failed.status == "failed" and failed.episode is None
    assert failed.policy_calls == 1 and failed.decisions[-1].reply is None
    assert not result.budget_exhausted
    for item in result.results:
        assert item.status == "refused" and item.failed_pairs == item.known_pairs == 1
        assert item.coverage.failed == 1 and item.coverage.known == 15
        assert item.shapley_value is None
    assert result.endpoint_checks[0].status == "estimated"
    assert len(set(branch.slot.continuation_seed for branch in result.branches)) == 20


def test_endpoint_provider_failure_does_not_refuse_otherwise_complete_coefficients():
    result = analyze(policy=FixedLengthPolicy(failure_seeds=(600,)))
    assert all(item.status == "estimated" for item in result.results)
    endpoint = result.endpoint_checks[0]
    assert endpoint.status == "refused" and endpoint.empty_coverage.failed == 1
    assert endpoint.coefficient_sum == 0 and endpoint.discrepancy is None


def test_policy_metadata_drift_retains_first_attempt_and_refuses_all_later_slots():
    class DriftingPolicy(FixedLengthPolicy):
        changed = False

        @property
        def metadata(self):
            return {**super().metadata, **({"changed": True} if self.changed else {})}

        def decide(self, request, *, seed):
            reply = super().decide(request, seed=seed)
            self.changed = True
            return reply

    policy = DriftingPolicy()
    result = analyze(policy=policy)
    assert result.calls == len(policy.requests) == 1
    assert len(result.branches) == len(result.slots) == 20
    assert all(branch.replay.status == "failed" for branch in result.branches)
    assert result.branches[0].replay.decisions[-1].reply is None
    assert all(item.status == "refused" and item.coverage.failed == 16 for item in result.results)
    assert result.policy_metadata == {"provider": "test", "policy": "fixed-length", "version": "1"}


def test_held_receipt_mutation_does_not_rewrite_factual_capture():
    original = recorded()
    before = original.trace.to_json()
    result = analyze(original)
    held = result.branches[2].replay.decisions[0]
    held.request["task"]["amount_minor"] = 1
    held.reply["metadata"]["decision_coalition_replay"]["factual_reply_metadata"]["seed"] = -123
    assert original.trace.to_json() == before


def test_stopping_before_held_positions_is_invalid_not_a_known_good_draw():
    result = analyze(policy=FixedLengthPolicy(stop_fresh=True))
    invalid = [branch for branch in result.branches if branch.replay.status == "invalid"]
    assert invalid and all(branch.replay.episode is None for branch in invalid)
    assert all(branch.replay.error_type == "DecisionCoalitionUnreachable" for branch in invalid)
    assert all(branch.replay.unreached_held_indices for branch in invalid)
    for item in result.results:
        assert item.status == "refused" and item.invalid_pairs == 2
        assert item.coverage.invalid > 0 and item.shapley_value is None
    assert result.summary()["invalid_branches"] == len(invalid)


def test_shared_factual_budget_finishes_zero_call_full_endpoints_before_failure():
    policy = FixedLengthPolicy()
    bounded = BudgetedPolicy(policy, 9)
    original = recorded(bounded)
    result = subject.shapley_decisions(original, bounded, pairs=2, endpoint_samples=2)
    assert result.initial_calls == 3 and result.calls == 6 and bounded.calls == 9
    assert result.budget_exhausted and len(result.branches) == 5
    assert [branch.replay.policy_calls for branch in result.branches] == [3, 3, 0, 0, 0]
    assert result.branches[-1].replay.error_type == "CallBudgetExceeded"
    assert result.branches[-1].replay.decisions[-1].policy_calls == 0
    assert result.endpoint_checks[0].status == "estimated"
    for item in result.results:
        assert item.status == "refused" and item.coverage.failed == 1
        assert item.coverage.unstarted == 15 and item.unstarted_pairs == 2
        assert item.coverage.known == item.coverage.unknown == item.coverage.invalid == 0


def test_exact_call_limit_completes_final_zero_call_walk_slot():
    policy = FixedLengthPolicy()
    result = subject.shapley_decisions(recorded(), BudgetedPolicy(policy, 30),
                                      pairs=2, endpoint_samples=2)
    assert result.calls == 30 and not result.budget_exhausted
    assert result.branches[-1].replay.policy_calls == 0
    assert len(result.slots) == len(result.branches) == 20
    assert all(item.status == "estimated" for item in result.results)


def test_exhausted_budget_retains_zero_call_failure_and_all_unstarted_slots():
    bounded = BudgetedPolicy(FixedLengthPolicy(), 3)
    original = recorded(bounded)
    result = subject.shapley_decisions(original, bounded, pairs=2, endpoint_samples=2)
    assert result.calls == 0 and len(result.branches) == 1 and result.budget_exhausted
    assert result.branches[0].replay.episode is None
    assert result.branches[0].replay.policy_calls == 0
    assert all(item.coverage.unstarted == 16 for item in result.results)
    assert result.endpoint_checks[0].empty_coverage.failed == 1
    assert result.endpoint_checks[0].full_coverage.unstarted == 2


def test_unknown_provenance_only_refuses_linked_target_with_identical_shared_calls():
    original = recorded(config=ScenarioConfig("missing-origin", Fault.CLEAN,
                                            include_provenance=False, use_idempotency=True))
    policy = FixedLengthPolicy()
    result = analyze(original, policy,
                     targets=("action", "consequence", "action_linked_consequence"))
    assert result.calls == len(policy.requests) == 30
    assert all(item.status == "estimated" for item in by_target(result, "action"))
    assert all(item.status == "estimated" for item in by_target(result))
    for item in by_target(result, "action_linked_consequence"):
        assert item.status == "refused" and item.coverage.unknown == 16
        assert item.unknown_pairs == 2
    assert result.endpoint_checks[-1].status == "refused"


def test_all_targets_reuse_exact_branch_replays_and_outcome_cache():
    original = recorded()
    single_policy, multiple_policy = FixedLengthPolicy(), FixedLengthPolicy()
    single = analyze(original, single_policy)
    multiple = analyze(original, multiple_policy,
                       targets=("action", "consequence", "action_linked_consequence"))
    assert single.branches == multiple.branches and single.slots == multiple.slots
    assert single_policy.requests == multiple_policy.requests
    assert single.calls == multiple.calls == 30
    assert single.results == by_target(multiple)
    assert single.endpoint_checks == tuple(item for item in multiple.endpoint_checks
                                           if item.target == "consequence")


def test_evaluator_truth_never_enters_estimation_or_summary():
    class ForbiddenTruth(tuple):
        def __iter__(self):
            raise AssertionError("Estimator inspected evaluator-only labels")

        def __getitem__(self, item):
            raise AssertionError("Estimator inspected evaluator-only labels")

        def __deepcopy__(self, memo):
            return self

    original = replace(recorded(), ground_truth=ForbiddenTruth(({"private": True},)))
    result = analyze(original)
    assert all(item.shapley_value == 0 for item in result.results)
    assert result.summary()["completed_branches"] == 20


def test_factual_unknown_is_not_an_observed_baseline_for_the_coalition_game(monkeypatch):
    payoff_adapter(monkeypatch, lambda held, seed: {0, 1} <= held)
    original = recorded(config=ScenarioConfig("unseen", Fault.CLEAN, read_lag_ms=400))
    result = analyze(original)
    assert original.trace.verifications[-1].status.value == "unknown"
    assert tuple(item.shapley_value for item in result.results) == (.5, .5, 0.)


@pytest.mark.parametrize("confidence", [.1, .95, math.nextafter(1., 0.)])
def test_valid_confidence_edge_stays_finite_for_pair_and_endpoint_intervals(monkeypatch, confidence):
    payoff_adapter(monkeypatch, lambda held, seed: bool(held) or seed not in {100, 108, 110})
    policy = StopPolicy()
    result = analyze(recorded(policy), policy, confidence=confidence)
    assert all(math.isfinite(value) for item in result.results for value in item.confidence_interval)
    assert all(math.isfinite(value) for endpoint in result.endpoint_checks
               for value in endpoint.confidence_interval)


@pytest.mark.parametrize("kwargs", [
    {"pairs": 0}, {"pairs": 1}, {"pairs": True}, {"pairs": 2.0},
    {"samples_per_eval": 0}, {"samples_per_eval": True}, {"samples_per_eval": 1.0},
    {"endpoint_samples": 0}, {"endpoint_samples": 1}, {"endpoint_samples": True},
    {"endpoint_samples": 2.0}, {"seed": -1}, {"seed": True}, {"seed": 100.0},
    {"seed": 0}, {"seed": MAX_TRIAL_SEED}, {"permutation_seed": -1},
    {"permutation_seed": True}, {"permutation_seed": 0.0}, {"permutation_seed": 2**31},
    {"confidence": 0}, {"confidence": 1}, {"confidence": True},
    {"confidence": float("nan")}, {"confidence": float("inf")},
    {"confidence": "0.95"}, {"confidence": 10**400},
    {"targets": ()}, {"targets": ("consequence", "consequence")},
    {"targets": (None,)}, {"targets": ("unsupported",)}, {"targets": "consequence"},
    {"template": None},
])
def test_invalid_configuration_is_refused_before_provider_calls(kwargs):
    policy = FixedLengthPolicy()
    with pytest.raises((TypeError, ValueError)):
        analyze(policy=policy, **kwargs)
    assert policy.requests == []


def test_full_schedule_overflow_is_refused_even_when_budget_would_fail_first():
    bounded = BudgetedPolicy(FixedLengthPolicy(), 1)
    with pytest.raises(ValueError, match="schedule"):
        subject.shapley_decisions(recorded(), bounded, pairs=2, endpoint_samples=2,
                                 seed=MAX_TRIAL_SEED - 10)
    assert bounded.calls == 0


def test_overlap_is_based_on_captured_policy_seed_not_factual_world_seed():
    original = recorded(seed=7, policy_seed=99)
    policy = FixedLengthPolicy()
    with pytest.raises(ValueError, match="overlaps"):
        analyze(original, policy, seed=98)
    assert policy.requests == []
    result = analyze(original, policy, seed=7)
    assert result.slots[0].continuation_seed == original.seed
    assert result.calls == 30


def test_entire_factual_capture_is_validated_before_first_fresh_call():
    original = recorded()
    events = list(original.trace.events)
    last = next(event for event in reversed(events) if event.type is EventType.AGENT_DECISION)
    data = deepcopy(last.data)
    data["policy_request"]["responses"][0]["result"]["fabricated"] = True
    events[events.index(last)] = replace(last, data=data)
    corrupted = replace(original, trace=replace(original.trace, events=tuple(events)))
    policy = FixedLengthPolicy()
    with pytest.raises(ValueError):
        analyze(corrupted, policy)
    assert policy.requests == []


@pytest.mark.parametrize("counter", [-1, 1001, True, 0.0])
def test_invalid_shared_budget_counter_is_refused_before_new_calls(counter):
    policy = FixedLengthPolicy()
    bounded = BudgetedPolicy(policy, 1000)
    bounded.calls = counter
    with pytest.raises(ValueError, match="counter"):
        subject.shapley_decisions(recorded(), bounded, pairs=2, endpoint_samples=2)
    assert policy.requests == []


def test_non_episode_or_unbounded_policy_is_refused_before_any_call():
    policy = FixedLengthPolicy()
    with pytest.raises(TypeError):
        subject.shapley_decisions(recorded(), policy, pairs=2, endpoint_samples=2)
    with pytest.raises(TypeError):
        subject.shapley_decisions(None, BudgetedPolicy(policy, 100), pairs=2, endpoint_samples=2)
    assert policy.requests == []


def test_policy_identity_wrong_template_and_uncaptured_trace_fail_preflight():
    class DifferentPolicy(FixedLengthPolicy):
        @property
        def metadata(self):
            return {**super().metadata, "version": "2"}

    policy = DifferentPolicy()
    with pytest.raises(ValueError):
        analyze(policy=policy)
    assert policy.requests == []
    standard = FixedLengthPolicy()
    original = recorded(template=REFUND_TASK_TEMPLATES["refund-support-note-v1"])
    for factual in (original, run_scenario()):
        with pytest.raises(ValueError):
            analyze(factual, standard)
        assert standard.requests == []


def test_nondefault_template_and_result_serialization_preserve_method_identity():
    template = REFUND_TASK_TEMPLATES["refund-support-note-v1"]
    result = analyze(recorded(template=template), template=template)
    assert result.template == template
    assert all(item.to_dict()["interval_degenerate"] is True for item in result.results)
    assert result.method_record()["interval_method"].startswith("normal pair-mean")
    text = " ".join(result.summary()["statistical_limits"]).lower()
    assert "normal" in text and "correlated" in text and "multiplicity" in text
    assert "zero-width" in text and "signed" in text and "positional" in text


def test_reproducible_fixed_fixture_and_permutation_stream():
    original = recorded()
    first = analyze(original, permutation_seed=71, pairs=5, samples_per_eval=2)
    second = analyze(original, permutation_seed=71, pairs=5, samples_per_eval=2)
    assert first == second and first.summary() == second.summary()
