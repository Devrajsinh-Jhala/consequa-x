"""Positional held decisions remain explicit interventions under changed requests."""

from copy import deepcopy
from dataclasses import replace

from jsonschema import Draft202012Validator
import pytest

import consequa_x.benchmark.decision_coalition as coalition_module
from consequa_x.models import thaw
from consequa_x.benchmark.decision_coalition import replay_decision_coalition
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.payments import Fault, PaymentWorld
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig, run_scenario
from consequa_x.benchmark.templates import REFUND_TASK_TEMPLATES
from consequa_x.models import EventType, Trace, VerificationStatus
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply
from consequa_x.policies import ScriptedRefundPolicy
from consequa_x.schema import get_trace_schema


class RecordingPolicy(ScriptedRefundPolicy):
    def __init__(self, *, selection="refund", response_stop=False, retry_on_success=False,
                 failure=None, invalid=False):
        self.requests = []
        self.selection = selection
        self.response_stop = response_stop
        self.retry_on_success = retry_on_success
        self.failure = failure
        self.invalid = invalid

    def decide(self, request, *, seed):
        self.requests.append((deepcopy(request), seed))
        if self.failure:
            raise self.failure("The test provider failed")
        if self.invalid:
            return PolicyReply(PolicyDecision("refund"))
        if request.stage == "select" and self.selection == "stop":
            return PolicyReply(PolicyDecision("stop"), {"seed": seed})
        if request.stage == "after_response":
            if self.response_stop:
                return PolicyReply(PolicyDecision("stop"), {"seed": seed})
            if self.retry_on_success and request.attempts_remaining:
                return PolicyReply(PolicyDecision("retry"), {"seed": seed})
        return super().decide(request, seed=seed)


def factual(*, config=None, policy=None, seed=7, max_attempts=2, **kwargs):
    return run_policy_scenario(
        config or ScenarioConfig("clean", Fault.CLEAN), policy or RecordingPolicy(),
        seed=seed, max_attempts=max_attempts, **kwargs,
    )


def unsafe_factual(**kwargs):
    return factual(config=ScenarioConfig(
        "unsafe", context=RefundContext(retry_instruction=True), use_idempotency=False,
    ), **kwargs)


def decisions(episode):
    return [event for event in episode.trace.events if event.type is EventType.AGENT_DECISION]


def changed_capture(episode, index, edit):
    events = list(episode.trace.events)
    event = decisions(episode)[index]
    data = thaw(event.data)
    edit(data)
    events[events.index(event)] = replace(event, data=data)
    return replace(episode, trace=replace(episode.trace, events=tuple(events)))


@pytest.mark.parametrize("held_indices,expected_calls", [
    ((), 3), ((0,), 2), ((1,), 2), ((2,), 2), ((0, 2), 1), ((0, 1, 2), 0),
])
def test_arbitrary_coalitions_hold_positions_and_only_fresh_decisions_call_policy(
    held_indices, expected_calls,
):
    original = unsafe_factual()
    snapshot = original.trace.to_json()
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 10)
    replay = replay_decision_coalition(
        original, bounded, held_indices=held_indices, continuation_seed=29,
    )
    assert replay.status == "completed" and replay.episode is not None
    assert replay.policy_calls == bounded.calls == len(policy.requests) == expected_calls
    assert [seed for _, seed in policy.requests] == [
        174 + index for index in range(3) if index not in held_indices
    ]
    assert replay.episode.seed == original.seed == 7
    assert replay.episode.trace.action == original.trace.action
    assert replay.episode.trace.responses == original.trace.responses
    assert replay.episode.ground_truth == original.ground_truth
    assert replay.episode.trace.verifications == original.trace.verifications
    assert [item.source for item in replay.decisions] == [
        "held_factual" if index in held_indices else "resampled" for index in range(3)
    ]
    assert replay.unreached_factual_indices == replay.unreached_held_indices == ()
    assert original.trace.to_json() == snapshot
    Draft202012Validator(get_trace_schema()).validate(replay.episode.trace.to_dict())
    assert Trace.from_json(replay.episode.trace.to_json()) == replay.episode.trace


def test_input_order_is_canonical_and_generator_is_consumed_once():
    replay = replay_decision_coalition(
        unsafe_factual(), BudgetedPolicy(RecordingPolicy(), 3),
        held_indices=(item for item in [2, 0]), continuation_seed=3,
    )
    assert replay.held_indices == (0, 2) and replay.policy_calls == 1


def test_full_hold_succeeds_when_shared_budget_is_already_exhausted():
    original = unsafe_factual()
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 1)
    bounded.calls = 1
    replay = replay_decision_coalition(
        original, bounded, held_indices=[2, 1, 0], continuation_seed=11,
    )
    assert replay.status == "completed" and replay.policy_calls == 0
    assert bounded.calls == 1 and not policy.requests and not replay.budget_exhausted
    for receipt, captured, replayed in zip(
        replay.decisions, decisions(original), decisions(replay.episode), strict=True,
    ):
        assert receipt.policy_calls == 0
        assert replayed.data["policy_reply"]["decision"] == captured.data["policy_reply"]["decision"]
        reuse = replayed.data["policy_reply"]["metadata"]["decision_coalition_replay"]
        assert reuse["source"] == "forced_factual" and reuse["provider_call"] is False
        assert reuse["exact_request_match"] is True
        assert reuse["factual_index"] == receipt.index
        assert reuse["factual_model_seed"] == captured.data["model_seed"]
        assert reuse["factual_reply_metadata"] == captured.data["policy_reply"]["metadata"]
        assert replayed.data["policy"] == captured.data["policy"]
    assert replay.episode.trace.verifications[-1].status is VerificationStatus.VIOLATED


def test_held_decision_may_have_a_changed_public_response_with_explicit_reuse_metadata(monkeypatch):
    original = factual()
    real_refund = PaymentWorld.refund
    calls = 0

    def changed_branch_response(self, action, attempt_id, fault):
        nonlocal calls
        calls += 1
        response = real_refund(self, action, attempt_id, fault)
        if calls == 2:  # First world validates the factual; the second is the branch.
            return replace(response, result={**response.result, "new_public_field": True})
        return response

    monkeypatch.setattr(PaymentWorld, "refund", changed_branch_response)
    replay = replay_decision_coalition(
        original, BudgetedPolicy(RecordingPolicy(), 1), held_indices=(0, 1), continuation_seed=6,
    )
    assert replay.status == "completed" and replay.policy_calls == 0
    assert replay.episode.trace.responses != original.trace.responses
    assert replay.decisions[1].request["responses"][0]["result"]["new_public_field"] is True
    reuse = replay.decisions[1].reply["metadata"]["decision_coalition_replay"]
    assert reuse["exact_request_match"] is False
    assert replay.decisions[1].reply["decision"] == decisions(original)[1].data["policy_reply"]["decision"]


@pytest.mark.parametrize("held_indices,expected_unreached", [((1,), (1,)), ((1, 2), (1, 2))])
def test_early_stop_before_held_position_invalidates_branch_without_outcome(
    held_indices, expected_unreached,
):
    policy = RecordingPolicy(selection="stop")
    replay = replay_decision_coalition(
        unsafe_factual(), BudgetedPolicy(policy, 4),
        held_indices=held_indices, continuation_seed=3,
    )
    assert replay.status == "invalid" and replay.episode is None
    assert replay.error_type == "DecisionCoalitionUnreachable"
    assert replay.policy_calls == len(policy.requests) == 1
    assert replay.unreached_held_indices == expected_unreached
    assert replay.unreached_factual_indices == (1, 2)
    assert replay.decisions[0].reply["decision"]["operation"] == "stop"
    assert replay.decisions[0].error is None
    assert not replay.budget_exhausted
    assert "verified_outcome" not in replay.summary()


def test_early_stop_before_only_unheld_positions_is_a_completed_branch():
    original = unsafe_factual()
    policy = RecordingPolicy(response_stop=True)
    replay = replay_decision_coalition(
        original, BudgetedPolicy(policy, 4), held_indices=(0,), continuation_seed=3,
    )
    assert replay.status == "completed" and replay.episode is not None
    assert replay.policy_calls == 1 and replay.unreached_factual_indices == (2,)
    assert replay.unreached_held_indices == ()
    assert len(replay.episode.trace.responses) == 1


def test_early_response_stop_refuses_a_later_nonprefix_held_position():
    replay = replay_decision_coalition(
        unsafe_factual(), BudgetedPolicy(RecordingPolicy(response_stop=True), 4),
        held_indices=(0, 2), continuation_seed=3,
    )
    assert replay.status == "invalid" and replay.error_type == "DecisionCoalitionUnreachable"
    assert replay.policy_calls == 1 and replay.unreached_held_indices == (2,)
    assert [item.source for item in replay.decisions] == ["held_factual", "resampled"]


def test_extra_reached_positions_beyond_factual_are_fresh_decisions():
    original = factual()
    replay = replay_decision_coalition(
        original, BudgetedPolicy(RecordingPolicy(retry_on_success=True), 3),
        held_indices=(0,), continuation_seed=9,
    )
    assert replay.status == "completed" and replay.policy_calls == 2
    assert len(replay.decisions) == 3 and replay.factual_decision_count == 2
    assert replay.decisions[2].source == "resampled"
    assert replay.decisions[2].factual_event_id is replay.decisions[2].factual_model_seed is None


def test_incompatible_typed_stage_refuses_held_reply_without_provider_call(monkeypatch):
    original = factual()

    def different_stage(config, policy, **kwargs):
        from consequa_x.policies import PolicyRequest
        request = PolicyRequest("after_response", {}, {}, original.trace.responses[:1], 1)
        policy.decide(request, seed=kwargs["policy_seed"] * 6)
        raise AssertionError("Incompatible held stage must raise")

    monkeypatch.setattr(coalition_module, "run_policy_scenario", different_stage)
    policy = RecordingPolicy()
    replay = replay_decision_coalition(
        original, BudgetedPolicy(policy, 2), held_indices=(0,), continuation_seed=3,
    )
    assert replay.status == "invalid" and replay.error_type == "DecisionCoalitionIncompatible"
    assert replay.episode is None and replay.policy_calls == 0 and not policy.requests
    assert replay.decisions[0].reply is None
    assert replay.decisions[0].error_type == "DecisionCoalitionIncompatible"


def test_held_retry_is_validated_against_current_attempt_budget(monkeypatch):
    original = unsafe_factual()
    real_runner = coalition_module.run_policy_scenario

    def reduced_branch_attempts(config, policy, **kwargs):
        return real_runner(config, policy, **{**kwargs, "max_attempts": 1})

    monkeypatch.setattr(coalition_module, "run_policy_scenario", reduced_branch_attempts)
    replay = replay_decision_coalition(
        original, BudgetedPolicy(RecordingPolicy(), 2), held_indices=(0, 1), continuation_seed=3,
    )
    assert replay.status == "invalid" and replay.error_type == "DecisionCoalitionIncompatible"
    assert replay.policy_calls == 0 and len(replay.decisions) == 2
    assert replay.decisions[-1].request["attempts_remaining"] == 0
    assert "available attempt budget" in replay.error
    assert replay.decisions[-1].reply is None


def test_budget_failure_retains_reached_receipts_and_unreached_held_positions():
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 1)
    replay = replay_decision_coalition(
        unsafe_factual(), bounded, held_indices=(2,), continuation_seed=3,
    )
    assert replay.status == "failed" and replay.episode is None
    assert replay.error_type == "CallBudgetExceeded" and replay.budget_exhausted
    assert replay.policy_calls == bounded.calls == len(policy.requests) == 1
    assert [item.policy_calls for item in replay.decisions] == [1, 0]
    assert replay.decisions[-1].error_type == "CallBudgetExceeded"
    assert replay.decisions[-1].reply is None and replay.unreached_held_indices == (2,)


@pytest.mark.parametrize("failure", [PolicyError, ValueError, TypeError])
def test_expected_provider_failure_retains_attempt_receipt_without_semantic_episode(failure):
    policy = RecordingPolicy(failure=failure)
    replay = replay_decision_coalition(
        unsafe_factual(), BudgetedPolicy(policy, 3), held_indices=(0, 2), continuation_seed=3,
    )
    assert replay.status == "failed" and replay.episode is None
    assert replay.error_type == failure.__name__ and replay.policy_calls == 1
    assert replay.decisions[-1].reply is None
    assert replay.decisions[-1].policy_calls == 1
    assert replay.unreached_held_indices == (2,) and not replay.budget_exhausted


def test_invalid_provider_reply_counts_call_and_refuses_outcome():
    replay = replay_decision_coalition(
        unsafe_factual(), BudgetedPolicy(RecordingPolicy(invalid=True), 3),
        held_indices=(0, 2), continuation_seed=3,
    )
    assert replay.status == "failed" and replay.error_type == "PolicyError"
    assert replay.policy_calls == 1 and replay.episode is None
    assert replay.decisions[-1].reply is None


def test_metadata_drift_is_a_counted_provider_failure():
    class ChangingPolicy(RecordingPolicy):
        changed = False

        @property
        def metadata(self):
            return {**super().metadata, **({"changed": True} if self.changed else {})}

        def decide(self, request, *, seed):
            reply = super().decide(request, seed=seed)
            self.changed = True
            return reply

    policy = ChangingPolicy()
    replay = replay_decision_coalition(
        unsafe_factual(), BudgetedPolicy(policy, 4), held_indices=(0, 2), continuation_seed=3,
    )
    assert replay.status == "failed" and replay.error_type == "PolicyError"
    assert replay.policy_calls == len(policy.requests) == 1 and replay.episode is None
    assert replay.decisions[-1].reply is None and "changed during" in replay.error


def test_branches_reset_world_and_report_only_new_calls_from_shared_budget():
    original = unsafe_factual()
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 6)
    bounded.calls = 2
    first = replay_decision_coalition(original, bounded, held_indices=(0, 2), continuation_seed=5)
    second = replay_decision_coalition(original, bounded, held_indices=(0, 2), continuation_seed=6)
    assert first.policy_calls == second.policy_calls == 1 and bounded.calls == 4
    assert first.episode.ground_truth == second.episode.ground_truth == original.ground_truth
    assert first.episode.trace.responses == second.episode.trace.responses
    assert [seed for _, seed in policy.requests] == [31, 37]


def test_held_metadata_and_receipts_do_not_alias_factual_capture():
    original = factual()
    snapshot = original.trace.to_json()
    replay = replay_decision_coalition(
        original, BudgetedPolicy(RecordingPolicy(), 1), held_indices=(0, 1), continuation_seed=3,
    )
    replay.decisions[0].reply["metadata"]["decision_coalition_replay"]["factual_reply_metadata"]["seed"] = 99
    replay.decisions[0].request["task"]["amount_minor"] = 1
    held = decisions(replay.episode)[0].data["policy_reply"]["metadata"]["decision_coalition_replay"]
    with pytest.raises(TypeError, match="read-only"):
        held["factual_reply_metadata"]["seed"] = 98
    assert original.trace.to_json() == snapshot


@pytest.mark.parametrize("edit", [
    lambda data: data.pop("policy_request"),
    lambda data: data["policy_request"].update(extra="unsupported"),
    lambda data: data["policy_reply"].update(extra="unsupported"),
    lambda data: data["policy_request"]["task"].update(amount_minor=1),
    lambda data: data.update(model_seed=True),
    lambda data: data.update(model_seed=43),
    lambda data: data.update(selected=1),
    lambda data: data["policy_reply"]["decision"].update(operation="retry"),
])
def test_full_capture_validation_rejects_corruption_before_provider_calls(edit):
    original = changed_capture(factual(), 0, edit)
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 3)
    with pytest.raises((ValueError, TypeError)):
        replay_decision_coalition(original, bounded, held_indices=(), continuation_seed=3)
    assert bounded.calls == 0 and not policy.requests


def test_corrupt_unheld_after_response_capture_is_still_validated():
    original = changed_capture(factual(), 1, lambda data: data["policy_request"]["responses"][0]["result"].update(
        fabricated_public_value=True,
    ))
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="declared world"):
        replay_decision_coalition(original, BudgetedPolicy(policy, 2),
                                 held_indices=(0,), continuation_seed=3)
    assert not policy.requests


def test_inconsistent_factual_identity_is_rejected_even_for_empty_coalition():
    original = changed_capture(factual(), 1, lambda data: data["policy"].update(changed=True))
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="metadata changed"):
        replay_decision_coalition(original, BudgetedPolicy(policy, 2),
                                 held_indices=(), continuation_seed=3)
    assert not policy.requests


def test_declared_policy_identity_mismatch_is_a_preflight_error():
    class DifferentPolicy(RecordingPolicy):
        metadata = {"provider": "different"}

    policy = DifferentPolicy()
    with pytest.raises(ValueError, match="metadata differs"):
        replay_decision_coalition(factual(), BudgetedPolicy(policy, 2),
                                 held_indices=(), continuation_seed=3)
    assert not policy.requests


def test_template_must_reproduce_the_factual_capture_before_any_calls():
    template = REFUND_TASK_TEMPLATES["refund-support-note-v1"]
    original = factual(template=template)
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="template"):
        replay_decision_coalition(original, BudgetedPolicy(policy, 2),
                                 held_indices=(0,), continuation_seed=3)
    assert not policy.requests
    replay = replay_decision_coalition(original, BudgetedPolicy(policy, 2),
                                     held_indices=(0,), continuation_seed=3, template=template)
    assert replay.status == "completed" and replay.policy_calls == 1


@pytest.mark.parametrize("held_indices", [None, 1, (True,), (1.0,), (-1,), (2,), (0, 0), "0"])
def test_invalid_coalitions_are_rejected_without_calls(held_indices):
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 2)
    with pytest.raises((TypeError, ValueError)):
        replay_decision_coalition(factual(), bounded, held_indices=held_indices, continuation_seed=3)
    assert bounded.calls == 0 and not policy.requests


@pytest.mark.parametrize("seed", [-1, True, 1.0, MAX_TRIAL_SEED + 1])
def test_invalid_continuation_seed_is_rejected_before_calls(seed):
    policy = RecordingPolicy()
    with pytest.raises(ValueError):
        replay_decision_coalition(factual(), BudgetedPolicy(policy, 2),
                                 held_indices=(), continuation_seed=seed)
    assert not policy.requests


@pytest.mark.parametrize("attribute,value", [
    ("calls", -1), ("calls", 3), ("calls", True), ("calls", 1.0),
    ("max_calls", 0), ("max_calls", True), ("max_calls", 2.0),
])
def test_corrupt_shared_budget_counters_are_rejected_before_calls(attribute, value):
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 2)
    setattr(bounded, attribute, value)
    with pytest.raises(ValueError, match="counters"):
        replay_decision_coalition(factual(), bounded, held_indices=(), continuation_seed=3)
    assert not policy.requests


def test_uncaptured_episode_unbudgeted_policy_invalid_template_and_invalid_episode_are_rejected():
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="complete policy capture"):
        replay_decision_coalition(run_scenario(), BudgetedPolicy(policy, 3),
                                 held_indices=(), continuation_seed=3)
    with pytest.raises(TypeError, match="BudgetedPolicy"):
        replay_decision_coalition(factual(), policy, held_indices=(), continuation_seed=3)
    with pytest.raises(TypeError, match="template"):
        replay_decision_coalition(factual(), BudgetedPolicy(policy, 3),
                                 held_indices=(), continuation_seed=3, template=None)
    with pytest.raises(TypeError, match="Episode"):
        replay_decision_coalition(None, BudgetedPolicy(policy, 3),
                                 held_indices=(), continuation_seed=3)
    assert not policy.requests


def test_factual_model_phase_schedule_is_independent_of_replayed_world_seed():
    original = unsafe_factual(seed=7, policy_seed=19)
    replay = replay_decision_coalition(
        original, BudgetedPolicy(RecordingPolicy(), 3), held_indices=(0, 2), continuation_seed=31,
    )
    assert replay.status == "completed" and replay.episode.seed == replay.factual_seed == 7
    assert [item.factual_model_seed for item in replay.decisions] == [114, 115, 116]
    assert [item.continuation_model_seed for item in replay.decisions] == [186, 187, 188]
    assert replay.episode.ground_truth == original.ground_truth


def test_summary_records_partial_intervention_without_truth_labels():
    replay = replay_decision_coalition(
        unsafe_factual(), BudgetedPolicy(RecordingPolicy(response_stop=True), 3),
        held_indices=(0, 2), continuation_seed=4,
    )
    assert replay.summary() == {
        "status": "invalid", "held_indices": [0, 2], "continuation_seed": 4,
        "coalition_game": "strict", "inactive_held_indices": [],
        "factual_seed": 7, "factual_decision_count": 3, "reached_decisions": 2,
        "held_decisions": 1, "resampled_decisions": 1, "held_requests": 1,
        "resampled_requests": 1, "failed_decisions": 0,
        "unreached_factual_indices": [2], "unreached_held_indices": [2],
        "policy_calls": 1, "budget_exhausted": False,
        "error_type": "DecisionCoalitionUnreachable",
        "error": "Held decision positions were not reached: (2,)",
    }


def test_factual_early_stop_full_hold_requires_no_new_calls():
    original = factual(policy=RecordingPolicy(selection="stop"))
    replay = replay_decision_coalition(
        original, BudgetedPolicy(RecordingPolicy(), 1), held_indices=(0,),
        continuation_seed=MAX_TRIAL_SEED,
    )
    assert replay.status == "completed" and replay.policy_calls == 0
    assert not replay.episode.action_selected and len(replay.decisions) == 1


def test_replay_does_not_inspect_factual_evaluator_truth_or_explanation():
    class PoisonTruth:
        def __iter__(self):
            raise AssertionError("Evaluator truth must not be consulted")

    original = replace(factual(), ground_truth=PoisonTruth(), explanation=object())
    replay = replay_decision_coalition(
        original, BudgetedPolicy(RecordingPolicy(), 2), held_indices=(0, 1), continuation_seed=3,
    )
    assert replay.status == "completed" and replay.policy_calls == 0
