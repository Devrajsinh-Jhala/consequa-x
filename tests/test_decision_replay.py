"""Captured prefix replay preserves worlds and counts only fresh decisions."""

from copy import deepcopy
from dataclasses import replace

from jsonschema import Draft202012Validator
import pytest

from consequa_x.benchmark.decision_replay import replay_decision_prefix
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.payments import Fault, PaymentWorld
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig, run_scenario
from consequa_x.benchmark.templates import REFUND_TASK_TEMPLATES
from consequa_x.models import AssessmentStatus, EventType, Trace, VerificationStatus
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply, ScriptedRefundPolicy
from consequa_x.schema import get_trace_schema


class RecordingPolicy(ScriptedRefundPolicy):
    def __init__(self, *, selection="refund", retry_on_success=False, fail=False, invalid=False):
        self.requests = []
        self.selection = selection
        self.retry_on_success = retry_on_success
        self.fail = fail
        self.invalid = invalid

    def decide(self, request, *, seed):
        self.requests.append((deepcopy(request), seed))
        if self.fail:
            raise PolicyError("The test provider failed")
        if self.invalid:
            return PolicyReply(PolicyDecision("refund"))
        if request.stage == "select" and self.selection == "stop":
            return PolicyReply(PolicyDecision("stop"), {"seed": seed})
        if request.stage == "after_response" and self.retry_on_success and request.attempts_remaining:
            return PolicyReply(PolicyDecision("retry"), {"seed": seed})
        return super().decide(request, seed=seed)


def factual(*, config=None, seed=7, max_attempts=2, policy=None, **kwargs):
    return run_policy_scenario(
        config or ScenarioConfig("clean", Fault.CLEAN), policy or RecordingPolicy(),
        seed=seed, max_attempts=max_attempts, **kwargs,
    )


def unsafe_factual():
    return factual(config=ScenarioConfig("unsafe", context=RefundContext(retry_instruction=True),
                                         use_idempotency=False))


def decisions(episode):
    return [event for event in episode.trace.events if event.type is EventType.AGENT_DECISION]


def change_capture(episode, index, edit):
    events = list(episode.trace.events)
    event = decisions(episode)[index]
    data = deepcopy(event.data)
    edit(data)
    events[events.index(event)] = replace(event, data=data)
    return replace(episode, trace=replace(episode.trace, events=tuple(events)))


@pytest.mark.parametrize("hold_count,expected_calls", [(0, 2), (1, 1), (2, 0)])
def test_prefix_holds_exact_decisions_and_resamples_with_fresh_phase_seeds(hold_count, expected_calls):
    original = factual()
    original_json = original.trace.to_json()
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 10)
    replay = replay_decision_prefix(original, bounded, hold_count=hold_count, continuation_seed=29)
    assert replay.episode is not None and replay.error_type is None
    assert replay.policy_calls == bounded.calls == len(policy.requests) == expected_calls
    assert [seed for _, seed in policy.requests] == list(range(29 * 6 + hold_count, 29 * 6 + 2))
    assert replay.episode.seed == original.seed == 7
    assert replay.episode.trace.action == original.trace.action
    assert replay.episode.ground_truth == original.ground_truth
    assert replay.episode.trace.responses == original.trace.responses
    assert replay.episode.trace.verifications == original.trace.verifications
    assert [item.source for item in replay.decisions] == (
        ["held_factual"] * hold_count + ["resampled"] * (2 - hold_count)
    )
    assert [item.continuation_model_seed for item in replay.decisions] == [174, 175]
    assert [event.data["model_seed"] for event in decisions(replay.episode)] == [174, 175]
    assert replay.unreached_factual_indices == ()
    assert original.trace.to_json() == original_json
    Draft202012Validator(get_trace_schema()).validate(replay.episode.trace.to_dict())
    assert Trace.from_json(replay.episode.trace.to_json()) == replay.episode.trace


def test_full_hold_succeeds_with_exhausted_shared_budget_without_claiming_new_generation():
    original = unsafe_factual()
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 1)
    bounded.calls = 1  # A previous branch has used this shared budget.
    replay = replay_decision_prefix(original, bounded, hold_count=3, continuation_seed=11)
    assert replay.episode is not None and replay.policy_calls == 0 and bounded.calls == 1
    assert policy.requests == [] and not replay.budget_exhausted
    for receipt, original_event, replayed_event in zip(
        replay.decisions, decisions(original), decisions(replay.episode), strict=True,
    ):
        assert receipt.policy_calls == 0
        assert replayed_event.data["policy_reply"]["decision"] == original_event.data["policy_reply"]["decision"]
        metadata = replayed_event.data["policy_reply"]["metadata"]
        assert set(metadata) == {"decision_prefix_replay"}
        reuse = metadata["decision_prefix_replay"]
        assert reuse["source"] == "held_factual" and reuse["provider_call"] is False
        assert reuse["factual_model_seed"] == original_event.data["model_seed"]
        assert reuse["factual_reply_metadata"] == original_event.data["policy_reply"]["metadata"]
        assert replayed_event.data["policy"] == original_event.data["policy"]
    assert replay.episode.trace.verifications[-1].status is VerificationStatus.VIOLATED


def test_held_reply_metadata_is_detached_from_the_factual_trace():
    original = factual()
    original_snapshot = original.trace.to_json()
    replay = replay_decision_prefix(original, BudgetedPolicy(RecordingPolicy(), 2),
                                    hold_count=2, continuation_seed=4)
    held = decisions(replay.episode)[0].data["policy_reply"]["metadata"]["decision_prefix_replay"]
    held["factual_reply_metadata"]["seed"] = 999
    replay.decisions[0].request["task"]["amount_minor"] = 1
    assert original.trace.to_json() == original_snapshot


def test_fresh_selection_can_stop_early_and_reports_unreached_factual_decisions():
    original = unsafe_factual()
    policy = RecordingPolicy(selection="stop")
    replay = replay_decision_prefix(original, BudgetedPolicy(policy, 4),
                                    hold_count=0, continuation_seed=3)
    assert replay.episode is not None and not replay.episode.action_selected
    assert replay.policy_calls == 1 and replay.factual_decision_count == 3
    assert replay.unreached_factual_indices == (1, 2)
    assert replay.summary()["unreached_factual_indices"] == [1, 2]
    assert replay.episode.trace.responses == ()
    assert replay.episode.trace.verifications[-1].status is VerificationStatus.VIOLATED


def test_resampled_suffix_can_be_longer_than_the_factual_trace():
    original = factual()
    policy = RecordingPolicy(retry_on_success=True)
    replay = replay_decision_prefix(original, BudgetedPolicy(policy, 4),
                                    hold_count=1, continuation_seed=9)
    assert replay.episode is not None and replay.policy_calls == 2
    assert len(replay.decisions) == 3 and replay.factual_decision_count == 2
    assert replay.decisions[-1].factual_event_id is None
    assert replay.decisions[-1].factual_model_seed is None
    assert replay.unreached_factual_indices == ()
    assert [seed for _, seed in policy.requests] == [55, 56]
    assert len(replay.episode.trace.responses) == 2


def test_budget_failure_retains_attempted_decision_and_has_no_semantic_outcome():
    original = unsafe_factual()
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 1)
    replay = replay_decision_prefix(original, bounded, hold_count=1, continuation_seed=17)
    assert replay.episode is None and replay.error_type == "CallBudgetExceeded"
    assert replay.budget_exhausted and replay.policy_calls == bounded.calls == 1
    assert [receipt.policy_calls for receipt in replay.decisions] == [0, 1, 0]
    assert replay.decisions[-1].error_type == "CallBudgetExceeded"
    assert replay.decisions[-1].reply is None
    assert replay.unreached_factual_indices == ()
    assert replay.summary()["resampled_decisions"] == 1
    assert replay.summary()["resampled_requests"] == 2
    assert replay.summary()["failed_decisions"] == 1
    assert "verified_outcome" not in replay.summary()


@pytest.mark.parametrize("kwargs", [{"fail": True}, {"invalid": True}])
def test_provider_and_protocol_errors_count_the_attempt_without_fabricated_episode(kwargs):
    original = unsafe_factual()
    policy = RecordingPolicy(**kwargs)
    replay = replay_decision_prefix(original, BudgetedPolicy(policy, 3),
                                    hold_count=1, continuation_seed=2)
    assert replay.episode is None and replay.error_type == "PolicyError"
    assert replay.policy_calls == len(policy.requests) == 1
    assert not replay.budget_exhausted
    assert [receipt.policy_calls for receipt in replay.decisions] == [0, 1]
    assert replay.decisions[-1].reply is None
    assert replay.unreached_factual_indices == (2,)


def test_each_branch_resets_the_world_and_shared_budget_counts_only_its_new_calls():
    original = unsafe_factual()
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 5)
    first = replay_decision_prefix(original, bounded, hold_count=1, continuation_seed=5)
    second = replay_decision_prefix(original, bounded, hold_count=1, continuation_seed=6)
    assert first.policy_calls == second.policy_calls == 2 and bounded.calls == 4
    assert first.episode.ground_truth == second.episode.ground_truth == original.ground_truth
    assert first.episode.trace.action == second.episode.trace.action == original.trace.action
    assert first.episode.trace.responses == second.episode.trace.responses
    assert [seed for _, seed in policy.requests] == [31, 32, 37, 38]


def test_prefix_mismatch_is_a_refused_branch_with_no_provider_call(monkeypatch):
    original = factual()
    real_refund = PaymentWorld.refund
    refunds = 0

    def changed_second_world(self, action, attempt_id, fault):
        nonlocal refunds
        refunds += 1
        response = real_refund(self, action, attempt_id, fault)
        # Preflight is the first fresh world; the branch is a separate second
        # world. A changed public response invalidates its held continuation.
        if refunds == 2:
            return replace(response, result={**response.result, "new_public_field": True})
        return response

    monkeypatch.setattr(PaymentWorld, "refund", changed_second_world)
    policy = RecordingPolicy()
    replay = replay_decision_prefix(original, BudgetedPolicy(policy, 3),
                                    hold_count=2, continuation_seed=6)
    assert replay.episode is None and replay.error_type == "DecisionPrefixMismatch"
    assert replay.policy_calls == 0 and policy.requests == []
    assert len(replay.decisions) == 2 and replay.decisions[-1].reply is None


class DifferentPolicy(RecordingPolicy):
    metadata = {"provider": "other", "version": "1"}


def test_policy_identity_mismatch_is_preflight_error():
    policy = DifferentPolicy()
    with pytest.raises(ValueError, match="metadata differs"):
        replay_decision_prefix(factual(), BudgetedPolicy(policy, 3),
                               hold_count=1, continuation_seed=1)
    assert policy.requests == []


def test_policy_metadata_drift_is_refused_before_the_next_provider_call():
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
    replay = replay_decision_prefix(unsafe_factual(), BudgetedPolicy(policy, 4),
                                    hold_count=1, continuation_seed=2)
    assert replay.episode is None and replay.error_type == "PolicyError"
    assert replay.policy_calls == len(policy.requests) == 1
    assert replay.decisions[-1].policy_calls == 1
    assert "changed during" in replay.error
    assert replay.decisions[-1].reply is None


@pytest.mark.parametrize("edit", [
    lambda data: data.pop("policy_request"),
    lambda data: data["policy_request"].update(extra="unsupported"),
    lambda data: data["policy_reply"].update(extra="unsupported"),
    lambda data: data["policy_reply"]["decision"].update(extra="unsupported"),
    lambda data: data["policy_reply"]["decision"].update(operation="retry"),
    lambda data: data.update(model_seed=True),
    lambda data: data.update(model_seed=43),
    lambda data: data.update(selected=1),
    lambda data: data["policy_request"]["task"].update(amount_minor=1),
    lambda data: data["policy_request"].update(attempts_remaining=6),
])
def test_invalid_factual_captures_fail_preflight_before_any_new_policy_call(edit):
    bad = change_capture(factual(), 0, edit)
    policy = RecordingPolicy()
    bounded = BudgetedPolicy(policy, 2)
    with pytest.raises((ValueError, TypeError)):
        replay_decision_prefix(bad, bounded, hold_count=0, continuation_seed=4)
    assert bounded.calls == 0 and policy.requests == []


def test_corrupt_after_response_capture_is_checked_even_when_only_selection_is_held():
    bad = change_capture(factual(), 1, lambda data: data["policy_request"]["responses"][0]["result"].update(
        fabricated_public_value=True,
    ))
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="declared world"):
        replay_decision_prefix(bad, BudgetedPolicy(policy, 3), hold_count=1, continuation_seed=4)
    assert policy.requests == []


def test_inconsistent_factual_policy_metadata_is_rejected():
    bad = change_capture(factual(), 1, lambda data: data["policy"].update(changed=True))
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="metadata changed"):
        replay_decision_prefix(bad, BudgetedPolicy(policy, 3), hold_count=1, continuation_seed=4)
    assert policy.requests == []


def test_template_must_reproduce_the_exact_factual_request():
    template = REFUND_TASK_TEMPLATES["refund-support-note-v1"]
    original = factual(template=template)
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="template"):
        replay_decision_prefix(original, BudgetedPolicy(policy, 2), hold_count=1, continuation_seed=2)
    assert policy.requests == []
    replay = replay_decision_prefix(original, BudgetedPolicy(policy, 2),
                                    hold_count=1, continuation_seed=2, template=template)
    assert replay.episode is not None and replay.policy_calls == 1


@pytest.mark.parametrize("name,value", [
    ("hold_count", -1), ("hold_count", True), ("hold_count", 3), ("hold_count", 1.0),
    ("continuation_seed", -1), ("continuation_seed", True),
    ("continuation_seed", MAX_TRIAL_SEED + 1), ("continuation_seed", 1.0),
    ("template", None),
])
def test_invalid_arguments_are_rejected_without_calls(name, value):
    kwargs = {"hold_count": 1, "continuation_seed": 4, name: value}
    policy = RecordingPolicy()
    with pytest.raises((TypeError, ValueError)):
        replay_decision_prefix(factual(), BudgetedPolicy(policy, 3), **kwargs)
    assert policy.requests == []


def test_uncaptured_fixture_episode_and_unbudgeted_policy_are_rejected():
    policy = RecordingPolicy()
    with pytest.raises(ValueError, match="complete policy capture"):
        replay_decision_prefix(run_scenario(), BudgetedPolicy(policy, 3),
                               hold_count=0, continuation_seed=3)
    with pytest.raises(TypeError, match="BudgetedPolicy"):
        replay_decision_prefix(factual(), policy, hold_count=0, continuation_seed=3)
    assert policy.requests == []


def test_factual_model_schedule_can_differ_from_the_world_seed():
    original = factual(seed=7, policy_seed=19)
    replay = replay_decision_prefix(original, BudgetedPolicy(RecordingPolicy(), 3),
                                    hold_count=1, continuation_seed=31)
    assert replay.episode is not None and replay.factual_seed == replay.episode.seed == 7
    assert [item.factual_model_seed for item in replay.decisions] == [114, 115]
    assert [item.continuation_model_seed for item in replay.decisions] == [186, 187]
    assert replay.episode.ground_truth == original.ground_truth


def test_summary_distinguishes_held_and_resampled_decisions_without_hidden_outcomes():
    replay = replay_decision_prefix(factual(), BudgetedPolicy(RecordingPolicy(), 3),
                                    hold_count=1, continuation_seed=4)
    assert replay.summary() == {
        "status": "completed", "hold_count": 1, "continuation_seed": 4, "factual_seed": 7,
        "factual_decision_count": 2, "reached_decisions": 2, "held_decisions": 1,
        "resampled_decisions": 1, "unreached_factual_indices": [], "policy_calls": 1,
        "held_requests": 1, "resampled_requests": 1, "failed_decisions": 0,
        "budget_exhausted": False, "error_type": None, "error": None,
    }


def test_factual_early_stop_full_prefix_needs_no_new_calls():
    original = factual(policy=RecordingPolicy(selection="stop"))
    replay = replay_decision_prefix(original, BudgetedPolicy(RecordingPolicy(), 2),
                                    hold_count=1, continuation_seed=MAX_TRIAL_SEED)
    assert replay.episode is not None and not replay.episode.action_selected
    assert replay.policy_calls == 0 and len(replay.decisions) == 1
    assert replay.decisions[0].continuation_model_seed == MAX_TRIAL_SEED * 6
    assert replay.episode.trace.assessment.status is AssessmentStatus.UNKNOWN
