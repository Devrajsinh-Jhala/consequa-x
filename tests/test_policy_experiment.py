"""Paired generation reuses factual data and accounts for every planned pair."""

from copy import deepcopy
from dataclasses import replace

import pytest

from consequa_x.attribution import Intervention, leave_one_out
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_experiment import branch_record, experiment_policy
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, RefundPolicyReplayRunner
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig, demo_scenarios
from consequa_x.models import EventType, Trace, VerificationStatus, to_dict
from consequa_x.policies import PolicyError, ScriptedRefundPolicy


class CountingPolicy(ScriptedRefundPolicy):
    def __init__(self):
        self.requests = []

    def decide(self, request, *, seed):
        self.requests.append((deepcopy(request), seed))
        return super().decide(request, seed=seed)


def scenario(name):
    return next(config for config in demo_scenarios() if config.name == name)


def result_for(experiment, candidate, target):
    return next(result for result in experiment.results
                if result.event_id == candidate and result.target == target)


def test_unsafe_retry_distinguishes_action_and_consequence_without_repeated_calls():
    policy = CountingPolicy()
    experiment = experiment_policy(
        policy, scenario("unsafe_retry"),
        (Intervention("retry_instruction"), Intervention("vip_policy")), samples=2, seed=7,
    )
    assert experiment.seeds == (7, 8)
    assert len(policy.requests) == experiment.calls == 12
    assert [branch.policy_calls for branch in experiment.branches] == [3, 3, 2, 2, 1, 1]
    assert [(branch.candidate_id, branch.seed) for branch in experiment.branches] == [
        (None, 7), (None, 8), ("retry_instruction", 7), ("retry_instruction", 8),
        ("vip_policy", 7), ("vip_policy", 8),
    ]
    action = result_for(experiment, "retry_instruction", "action").estimate
    consequence = result_for(experiment, "retry_instruction", "consequence").estimate
    assert action.effect == 0 and action.baseline_rate == action.intervention_rate == 1
    assert consequence.effect == -1
    assert consequence.baseline_rate == 0 and consequence.intervention_rate == 1
    assert result_for(experiment, "vip_policy", "action").estimate.effect == 1
    assert result_for(experiment, "vip_policy", "consequence").estimate.effect == 0
    assert experiment.summary()["estimates"] == {
        "action": {"estimated": 2, "refused": 0},
        "consequence": {"estimated": 2, "refused": 0},
    }
    assert all(result.known_pairs == 2 and result.reason is None for result in experiment.results)


def test_cached_estimates_equal_existing_estimator_on_the_identical_schedule():
    config = scenario("unsafe_retry")
    interventions = (Intervention("retry_instruction"), Intervention("customer_request"))
    experiment = experiment_policy(ScriptedRefundPolicy(), config, interventions,
                                   samples=3, seed=19)
    for target in ("action", "consequence"):
        expected = leave_one_out(RefundPolicyReplayRunner(config, ScriptedRefundPolicy()),
                                 interventions, samples=3, seed=19, target=target)
        actual = tuple(result.estimate for result in experiment.results if result.target == target)
        assert actual == expected
        assert all(estimate.seeds == (19, 20, 21) for estimate in actual)


def test_same_seed_preserves_contract_and_phase_keys_while_worlds_are_fresh():
    experiment = experiment_policy(
        ScriptedRefundPolicy(), scenario("unsafe_retry"),
        (Intervention("retry_instruction"),), samples=2, seed=5,
    )
    factual, changed = experiment.branches[:2], experiment.branches[2:]
    for original, intervened in zip(factual, changed, strict=True):
        assert original.episode.trace.action == intervened.episode.trace.action
        assert original.episode.trace.action.contract == intervened.episode.trace.action.contract
        original_decisions = [event for event in original.episode.trace.events
                              if event.type is EventType.AGENT_DECISION]
        changed_decisions = [event for event in intervened.episode.trace.events
                            if event.type is EventType.AGENT_DECISION]
        for left, right in zip(original_decisions, changed_decisions):
            assert left.data["model_seed"] == right.data["model_seed"]
            assert left.data["policy_request"]["task"] == right.data["policy_request"]["task"]
        original_refunds = [record for record in original.episode.ground_truth
                            if record.get("kind") == "refund"]
        changed_refunds = [record for record in intervened.episode.ground_truth
                           if record.get("kind") == "refund"]
        assert len(original_refunds) == 2 and len(changed_refunds) == 1
        assert original.episode.trace.verifications[-1].status is VerificationStatus.VIOLATED
        assert intervened.episode.trace.verifications[-1].status is VerificationStatus.SATISFIED
        assert Trace.from_json(original.episode.trace.to_json()) == original.episode.trace


def test_unknown_state_refuses_consequence_without_obscuring_known_action():
    experiment = experiment_policy(ScriptedRefundPolicy(), scenario("delayed_visibility"),
                                   (Intervention("vip_policy"),), samples=2)
    action = result_for(experiment, "vip_policy", "action")
    consequence = result_for(experiment, "vip_policy", "consequence")
    assert action.status == "estimated" and action.estimate.effect == 1
    assert action.known_pairs == 2 and action.unknown_pairs == 0
    assert consequence.status == "refused" and consequence.estimate is None
    assert consequence.known_pairs == 0 and consequence.unknown_pairs == 2
    assert consequence.failed_pairs == consequence.unstarted_pairs == 0
    assert "No pairs are dropped or redrawn" in consequence.reason
    assert experiment.summary()["failed_branches"] == 0


class FactualFirstSeedFails(CountingPolicy):
    def decide(self, request, *, seed):
        if seed == 0 and request.context["vip_policy"]:
            self.requests.append((deepcopy(request), seed))
            raise PolicyError("No usable policy response")
        return super().decide(request, seed=seed)


def test_provider_failure_is_retained_without_redraw_and_refuses_whole_pair_estimate():
    policy = FactualFirstSeedFails()
    experiment = experiment_policy(policy, scenario("clean"),
                                   (Intervention("vip_policy"),), samples=2)
    assert len(policy.requests) == experiment.calls == 5
    assert len(experiment.branches) == 4
    failed = experiment.branches[0]
    assert failed.episode is None and failed.error_type == "PolicyError"
    assert failed.policy_calls == 1 and failed.seed == 0
    assert experiment.summary()["completed_branches"] == 3
    for result in experiment.results:
        assert result.status == "refused" and result.estimate is None
        assert result.known_pairs == result.failed_pairs == 1
        assert result.unstarted_pairs == result.unknown_pairs == 0
        assert result.seeds == (0, 1)
    receipt = branch_record(failed)
    assert receipt["status"] == "failed"
    assert "verified_outcome" not in receipt and "trace" not in receipt


def test_failure_and_unknown_categories_are_disjoint_for_the_planned_pairs():
    experiment = experiment_policy(FactualFirstSeedFails(), scenario("delayed_visibility"),
                                   (Intervention("vip_policy"),), samples=2)
    action, consequence = experiment.results
    assert action.failed_pairs == 1 and action.known_pairs == 1
    assert action.unknown_pairs == action.unstarted_pairs == 0
    assert consequence.failed_pairs == 1 and consequence.unknown_pairs == 1
    assert consequence.known_pairs == consequence.unstarted_pairs == 0
    assert sum((consequence.failed_pairs, consequence.unknown_pairs,
                consequence.known_pairs, consequence.unstarted_pairs)) == 2


def test_missing_candidate_does_not_hide_the_failed_factual_companion():
    experiment = experiment_policy(ScriptedRefundPolicy(), scenario("clean"),
                                   (Intervention("vip_policy"),), samples=2, max_calls=3)
    summary = experiment.summary()
    assert summary["policy_calls"] == 3 and summary["budget_exhausted"]
    assert summary["completed_branches"] == summary["failed_branches"] == 1
    assert summary["not_started_branches"] == 2
    assert experiment.branches[-1].error_type == "CallBudgetExceeded"
    assert experiment.branches[-1].policy_calls == 1
    for result in experiment.results:
        assert result.failed_pairs == result.unstarted_pairs == 1
        assert result.known_pairs == result.unknown_pairs == 0
        assert result.status == "refused" and result.estimate is None


@pytest.mark.parametrize("budget,known,unstarted", [(4, 0, 2), (5, 1, 1)])
def test_budget_exhaustion_between_branches_preserves_unstarted_pairs(budget, known, unstarted):
    experiment = experiment_policy(ScriptedRefundPolicy(), scenario("clean"),
                                   (Intervention("vip_policy"),), samples=2, max_calls=budget)
    assert experiment.calls == budget and experiment.budget_exhausted
    assert experiment.summary()["failed_branches"] == 0
    assert experiment.summary()["not_started_branches"] == unstarted
    for result in experiment.results:
        assert result.known_pairs == known and result.unstarted_pairs == unstarted
        assert result.failed_pairs == result.unknown_pairs == 0
        assert result.status == "refused"


def test_exactly_sufficient_budget_completes_without_marking_exhaustion():
    experiment = experiment_policy(ScriptedRefundPolicy(), scenario("clean"),
                                   (Intervention("vip_policy"),), samples=2, max_calls=6)
    assert experiment.calls == experiment.max_calls == 6
    assert not experiment.budget_exhausted
    assert experiment.summary()["completed_branches"] == 4
    assert all(result.status == "estimated" for result in experiment.results)


def test_other_complete_candidates_keep_estimates_when_later_candidates_are_unstarted():
    experiment = experiment_policy(
        ScriptedRefundPolicy(), scenario("clean"),
        (Intervention("vip_policy"), Intervention("customer_request")), samples=2, max_calls=6,
    )
    assert experiment.budget_exhausted
    assert all(result.status == "estimated" for result in experiment.results[:2])
    assert all(result.status == "refused" and result.unstarted_pairs == 2
               for result in experiment.results[2:])
    assert experiment.summary()["not_started_branches"] == 2


@pytest.mark.parametrize("kwargs", [
    {"samples": 0}, {"samples": 1}, {"samples": True}, {"samples": 2.0},
    {"seed": -1}, {"seed": True}, {"seed": MAX_TRIAL_SEED},
    {"max_attempts": 0}, {"max_attempts": 6}, {"max_attempts": True},
    {"max_calls": 0}, {"max_calls": False},
])
def test_invalid_schedule_cannot_invoke_the_policy(kwargs):
    policy = CountingPolicy()
    with pytest.raises(ValueError):
        experiment_policy(policy, scenario("clean"), (Intervention("vip_policy"),), **kwargs)
    assert policy.requests == []


@pytest.mark.parametrize("candidates", [
    (), ("vip_policy",), (Intervention("vip_policy"), Intervention("vip_policy")),
    (Intervention("vip_policy"), Intervention("response_1")),
    (Intervention("vip_policy"), Intervention("retry_instruction", "replace", "retry")),
    (Intervention("vip_policy"), Intervention("distractor", "replace", False)),
    (Intervention("vip_policy", "replace", 1),),
    (Intervention("customer_request", "replace", None),),
])
def test_all_candidates_are_validated_before_even_a_factual_model_call(candidates):
    policy = CountingPolicy()
    with pytest.raises((TypeError, ValueError)):
        experiment_policy(policy, scenario("clean"), iter(candidates), samples=2)
    assert policy.requests == []


def test_generator_validation_finishes_before_any_policy_call():
    policy = CountingPolicy()

    def candidates():
        yield Intervention("vip_policy")
        assert policy.requests == []
        yield Intervention("refund_decision")

    with pytest.raises(ValueError, match="declared fixture context"):
        experiment_policy(policy, scenario("clean"), candidates(), samples=2)
    assert policy.requests == []


@pytest.mark.parametrize("event_id,replacement", [
    ("customer_request", True), ("vip_memory", True), ("vip_policy", True),
    ("retry_instruction", False), ("distractor", "A different irrelevant sentence."),
])
def test_typed_replacements_rerun_the_declared_context_only(event_id, replacement):
    config = replace(scenario("clean"), context=RefundContext(vip_policy=False))
    experiment = experiment_policy(
        ScriptedRefundPolicy(), config, (Intervention(event_id, "replace", replacement),), samples=2,
    )
    factual = experiment.branches[0].episode
    changed = experiment.branches[2].episode
    factual_context = {event.id: event.data["value"] for event in factual.trace.events[:5]}
    changed_context = {event.id: event.data["value"] for event in changed.trace.events[:5]}
    assert all(factual_context[key] == changed_context[key]
               for key in factual_context if key != event_id)
    if event_id == "vip_policy":
        assert not factual.action_selected and changed.action_selected
    if event_id == "distractor":
        assert changed_context["distractor"] == replacement
    assert factual.trace.action.contract == changed.trace.action.contract


def test_largest_accepted_seed_schedule_keeps_all_phase_keys_in_model_range():
    experiment = experiment_policy(ScriptedRefundPolicy(), scenario("clean"),
                                   (Intervention("vip_policy"),), samples=2, seed=MAX_TRIAL_SEED - 1)
    assert experiment.seeds[-1] == MAX_TRIAL_SEED
    for branch in experiment.branches:
        for event in branch.episode.trace.events:
            if event.type is EventType.AGENT_DECISION:
                assert 0 <= event.data["model_seed"] <= 2**31 - 1


def test_programming_errors_propagate_instead_of_becoming_semantic_failures():
    class UnexpectedFailure(ScriptedRefundPolicy):
        def decide(self, request, *, seed):
            raise RuntimeError("A programming error")

    with pytest.raises(RuntimeError, match="programming error"):
        experiment_policy(UnexpectedFailure(), scenario("clean"),
                          (Intervention("vip_policy"),), samples=2)


def test_report_metadata_includes_first_use_updates_and_is_detached():
    class UpdatingPolicy(CountingPolicy):
        metadata = {"provider": "test"}

        def decide(self, request, *, seed):
            self.metadata["inspection"] = {"local": True}
            return super().decide(request, seed=seed)

    policy = UpdatingPolicy()
    experiment = experiment_policy(policy, scenario("clean"),
                                   (Intervention("vip_policy"),), samples=2)
    assert experiment.policy_metadata == {"provider": "test", "inspection": {"local": True}}
    policy.metadata["inspection"]["local"] = False
    assert experiment.policy_metadata["inspection"]["local"] is True


def test_branch_artifact_names_are_unique_when_seeds_repeat_across_conditions(tmp_path):
    experiment = experiment_policy(ScriptedRefundPolicy(), ScenarioConfig(fault=Fault.CLEAN),
                                   (Intervention("vip_policy"),), samples=2)
    records = [branch_record(branch, root=tmp_path) for branch in experiment.branches]
    assert len({record["trace"] for record in records}) == 4
    assert records[0]["trace"] == "traces/branch_0000.json"
    assert records[2]["trace"] == "traces/branch_0002.json"
    assert records[0]["condition"] == "factual" and records[0]["candidate_id"] is None
    assert records[2]["condition"] == "intervened" and records[2]["candidate_id"] == "vip_policy"
    assert "ground_truth" not in records[0]
    assert to_dict(experiment.results[0])["estimate"]["seeds"] == [0, 1]


def test_one_off_invalid_metadata_is_rejected_before_a_generation_call():
    class BadMetadata(CountingPolicy):
        metadata = {"temperature": float("nan")}

    policy = BadMetadata()
    with pytest.raises(PolicyError, match="finite JSON"):
        experiment_policy(policy, scenario("clean"), (Intervention("vip_policy"),), samples=2)
    assert policy.requests == []
