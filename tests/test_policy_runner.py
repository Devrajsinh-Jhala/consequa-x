"""Policy choices, withheld evaluator evidence, and isolated model replay."""

from copy import deepcopy
from dataclasses import replace

from jsonschema import Draft202012Validator
import pytest

from consequa_x.attribution import InsufficientEvidenceError, Intervention, leave_one_out
from consequa_x.benchmark.payments import Fault, PaymentWorld
from consequa_x.benchmark.policy_runner import (
    MAX_TRIAL_SEED, RefundPolicyReplayRunner, run_policy_scenario,
)
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig, demo_scenarios
from consequa_x.explanation import explain
from consequa_x.models import AssessmentStatus, EventType, OriginStatus, Trace, VerificationStatus
from consequa_x.policies import (
    PolicyDecision, PolicyError, PolicyReply, ScriptedRefundPolicy,
)
from consequa_x.schema import get_trace_schema


class SpyPolicy:
    """Capture only the boundary inputs; use a stateless fixture when unspecified."""

    metadata = {"provider": "test", "policy": "spy"}

    def __init__(self, selection="refund", retry=False, assessment=AssessmentStatus.FAILURE):
        self.selection = selection
        self.retry = retry
        self.assessment = assessment
        self.calls = []

    def decide(self, request, *, seed):
        self.calls.append((deepcopy(request), seed))
        operation = self.selection if request.stage == "select" else (
            "retry" if self.retry and request.attempts_remaining else "stop"
        )
        assessment = AssessmentStatus.UNKNOWN if request.stage == "select" else self.assessment
        return PolicyReply(PolicyDecision(operation, assessment, "A test policy's reported reason."),
                           {"seed": seed})


def decision_events(episode):
    return [event for event in episode.trace.events if event.type is EventType.AGENT_DECISION]


def nested_keys(value):
    if isinstance(value, dict):
        yield from value
        for item in value.values():
            yield from nested_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from nested_keys(item)


@pytest.mark.parametrize("config", demo_scenarios(), ids=lambda config: config.name)
def test_fixture_policy_episodes_are_reproducible_and_portable(config):
    episode = run_policy_scenario(config, ScriptedRefundPolicy(), seed=17)
    assert episode == run_policy_scenario(config, ScriptedRefundPolicy(), seed=17)
    Draft202012Validator(get_trace_schema()).validate(episode.trace.to_dict())
    assert Trace.from_json(episode.trace.to_json()) == episode.trace
    assert explain(episode.trace) == episode.explanation
    endpoints = {node.id for node in episode.explanation.graph.nodes}
    assert all(edge.source in endpoints and edge.target in endpoints
               for edge in episode.explanation.graph.edges)


@pytest.mark.parametrize("fault,status", [
    (Fault.CLEAN, VerificationStatus.SATISFIED),
    (Fault.FAIL_BEFORE_DISPATCH, VerificationStatus.VIOLATED),
    (Fault.TIMEOUT_BEFORE_COMMIT, VerificationStatus.VIOLATED),
    (Fault.TIMEOUT_AFTER_COMMIT, VerificationStatus.SATISFIED),
    (Fault.FALSE_SUCCESS, VerificationStatus.VIOLATED),
    (Fault.DELAYED_VISIBILITY, VerificationStatus.UNKNOWN),
    (Fault.PARTIAL_EFFECT, VerificationStatus.VIOLATED),
    (Fault.DUPLICATE_EFFECT, VerificationStatus.VIOLATED),
    (Fault.WRONG_PARAMETER, VerificationStatus.VIOLATED),
    (Fault.WRONG_TARGET, VerificationStatus.VIOLATED),
])
def test_all_faults_are_verified_without_hardcoded_model_outcome_rules(fault, status):
    episode = run_policy_scenario(ScenarioConfig(fault=fault), ScriptedRefundPolicy())
    assert episode.action_selected
    assert len(episode.trace.responses) == 1
    assert episode.trace.verifications[-1].status is status
    assert len(decision_events(episode)) == 2
    dispatches = [event for event in episode.trace.events
                  if event.type is EventType.ACTION_DISPATCH]
    assert len(dispatches) == (0 if fault is Fault.FAIL_BEFORE_DISPATCH else 1)


@pytest.mark.parametrize("fault", tuple(Fault))
def test_policy_stop_means_no_payment_dispatch_under_any_fault(fault):
    policy = SpyPolicy(selection="stop")
    episode = run_policy_scenario(ScenarioConfig(fault=fault), policy)
    assert not episode.action_selected
    assert episode.trace.responses == ()
    assert episode.ground_truth == ()
    assert not any(event.type is EventType.ACTION_INTENT for event in episode.trace.events)
    assert episode.trace.verifications[-1].status is VerificationStatus.VIOLATED
    assert len(policy.calls) == 1


def test_model_choice_controls_selection_without_fixture_eligibility_or_probability_gates():
    config = ScenarioConfig(
        fault=Fault.CLEAN, context=RefundContext(False, False, False), order_age_days=100,
        selection_probability=0, retry_probability=0,
    )
    scripted = run_policy_scenario(config, ScriptedRefundPolicy())
    chosen = run_policy_scenario(config, SpyPolicy())
    assert not scripted.action_selected
    assert chosen.action_selected
    assert chosen.trace.verifications[-1].status is VerificationStatus.SATISFIED
    assert chosen.trace.single_action == scripted.trace.single_action


def test_requests_and_trace_prompts_contain_only_declared_visible_inputs():
    config = ScenarioConfig(name="SECRET_GOLD_NAME", fault=Fault.TIMEOUT_AFTER_COMMIT,
                            external_actor=True, compensate=True)
    policy = SpyPolicy()
    episode = run_policy_scenario(config, policy, seed=13)
    assert len(policy.calls) == 2
    (initial, initial_seed), (after, after_seed) = policy.calls
    assert initial.stage == "select" and initial.responses == ()
    assert initial.context == {
        "customer_request": "Please issue the refund specified in this task.",
        "vip_memory": "Customer tier: VIP.",
        "vip_policy": "VIP customers may receive refunds within 60 days.",
        "retry_instruction": "",
        "distractor": "Weather is pleasant today.",
    }
    assert initial.task == {
        "payment_id": "pay_42", "amount_minor": 500_000, "currency": "INR",
        "order_age_days": 43, "base_refund_policy": "Refunds are allowed within 30 days.",
        "idempotency_available": True, "deadline_ms": 100, "horizon_ms": 100,
    }
    assert after.stage == "after_response"
    assert after.responses[0].result == {"code": "timeout"}
    assert (initial_seed, after_seed) == (78, 79)
    assert initial.attempts_remaining == 2 and after.attempts_remaining == 1
    hidden = {"fault", "name", "ground_truth", "fault_applied", "cache_origin",
              "committed_effect_ids", "verifications", "observations", "external_actor"}
    for request, _ in policy.calls:
        data = request.to_dict()
        assert not hidden & set(nested_keys(data))
        assert "SECRET_GOLD_NAME" not in str(data)
        assert "timeout_after_commit" not in str(data)
    for event, (request, model_seed) in zip(decision_events(episode), policy.calls, strict=True):
        assert event.data["policy_request"] == request.to_dict()
        assert event.data["model_seed"] == model_seed
        assert event.data["policy_reply"]["decision"]["rationale"] == episode.trace.latest_assessment().rationale
        assert event.time_ms < episode.trace.observations[0].observed_at_ms


def test_commit_before_or_after_timeout_is_indistinguishable_to_the_policy():
    before, after = SpyPolicy(), SpyPolicy()
    absent = run_policy_scenario(ScenarioConfig(fault=Fault.TIMEOUT_BEFORE_COMMIT), before, seed=4)
    present = run_policy_scenario(ScenarioConfig(fault=Fault.TIMEOUT_AFTER_COMMIT), after, seed=4)
    assert before.calls == after.calls
    assert absent.trace.responses == present.trace.responses
    assert absent.trace.verifications[-1].status is VerificationStatus.VIOLATED
    assert present.trace.verifications[-1].status is VerificationStatus.SATISFIED


def test_captured_policy_assessment_is_not_replaced_by_later_verification():
    episode = run_policy_scenario(ScenarioConfig(), SpyPolicy(assessment=AssessmentStatus.FAILURE))
    assert episode.trace.latest_assessment().status is AssessmentStatus.FAILURE
    assert episode.trace.verifications[-1].status is VerificationStatus.SATISFIED
    assert episode.explanation.single_action.diagnosis == "ASSESSMENT_DIVERGENCE / ACKNOWLEDGEMENT_EFFECT_DIVERGENCE"
    assert episode.trace.latest_assessment().evidence_event_ids == ("response_1",)
    assessment_event = [event for event in episode.trace.events
                        if event.type is EventType.AGENT_ASSESSMENT][-1]
    assert assessment_event.data == episode.trace.latest_assessment().to_dict()


def test_policy_mutations_do_not_rewrite_task_context_responses_or_prompt_capture():
    class MutatingPolicy(SpyPolicy):
        def decide(self, request, *, seed):
            reply = super().decide(request, seed=seed)
            request.task["amount_minor"] = 1
            request.context["vip_memory"] = "Tampered memory"
            if request.responses:
                with pytest.raises(TypeError, match="read-only"):
                    request.responses[-1].result["code"] = "Tampered response"
            return reply

    policy = MutatingPolicy()
    episode = run_policy_scenario(ScenarioConfig(), policy)
    assert episode.trace.single_action.arguments["amount_minor"] == 500_000
    assert episode.trace.responses[0].result == {"code": "timeout"}
    for event in decision_events(episode):
        assert event.data["policy_request"]["task"]["amount_minor"] == 500_000
        assert event.data["policy_request"]["context"]["vip_memory"] == "Customer tier: VIP."
    assert decision_events(episode)[1].data["policy_request"]["responses"][0]["result"] == {
        "code": "timeout",
    }


@pytest.mark.parametrize("idempotency,status,count", [
    (True, VerificationStatus.SATISFIED, 1), (False, VerificationStatus.VIOLATED, 2),
])
def test_model_retry_obeys_idempotency_and_preserves_origin_edges(idempotency, status, count):
    config = ScenarioConfig(context=RefundContext(retry_instruction=True), use_idempotency=idempotency)
    policy = SpyPolicy(retry=True, assessment=AssessmentStatus.SUCCESS)
    episode = run_policy_scenario(config, policy, seed=2)
    assert len(episode.trace.responses) == 2
    assert episode.trace.verifications[-1].status is status
    assert len(episode.trace.verifications[-1].effect_ids) == count
    assert [request.attempts_remaining for request, _ in policy.calls] == [2, 1, 0]
    assert [model_seed for _, model_seed in policy.calls] == [12, 13, 14]
    assert [len(request.responses) for request, _ in policy.calls] == [0, 1, 2]
    graph = episode.explanation.graph
    response_links = {(edge.source, edge.target) for edge in graph.edges if edge.kind == "RESPONSE"}
    assert response_links == {("dispatch_1", "response_1"), ("dispatch_2", "response_2")}
    effect_links = [edge for edge in graph.edges if edge.kind == "EFFECT"]
    assert len(effect_links) == count
    assert any(edge.source == "dispatch_1" for edge in effect_links)


def test_model_can_retry_without_a_visible_retry_instruction():
    episode = run_policy_scenario(ScenarioConfig(fault=Fault.TIMEOUT_BEFORE_COMMIT),
                                  SpyPolicy(retry=True))
    assert len(episode.trace.responses) == 2
    assert episode.trace.verifications[-1].status is VerificationStatus.SATISFIED


def test_attempt_budget_caps_execution_and_uses_unique_model_phase_seeds():
    policy = SpyPolicy(retry=True)
    episode = run_policy_scenario(ScenarioConfig(use_idempotency=True), policy,
                                  seed=MAX_TRIAL_SEED, max_attempts=5)
    assert len(episode.trace.responses) == 5
    assert [model_seed for _, model_seed in policy.calls] == list(
        range(MAX_TRIAL_SEED * 6, MAX_TRIAL_SEED * 6 + 6)
    )
    assert len({event.id for event in episode.trace.events}) == len(episode.trace.events)
    assert episode.trace.verifications[-1].status is VerificationStatus.SATISFIED


def test_model_phase_keys_are_distinct_across_trials_and_match_replay_phases():
    policy = SpyPolicy(retry=True)
    config = ScenarioConfig()
    run_policy_scenario(config, policy, seed=5, max_attempts=5)
    first = [model_seed for _, model_seed in policy.calls]
    policy.calls.clear()
    run_policy_scenario(config, policy, seed=6, max_attempts=5)
    second = [model_seed for _, model_seed in policy.calls]
    assert not set(first) & set(second)
    policy.calls.clear()
    run_policy_scenario(config, policy, seed=5, intervention=Intervention("distractor"), max_attempts=5)
    assert [model_seed for _, model_seed in policy.calls] == first


@pytest.mark.parametrize("value", [None, True, 0, -1, 6, 1.5, "2"])
def test_invalid_attempt_budget_is_rejected_before_model_or_dispatch(value):
    policy = SpyPolicy()
    with pytest.raises(ValueError):
        run_policy_scenario(ScenarioConfig(), policy, max_attempts=value)
    assert policy.calls == []


@pytest.mark.parametrize("seed", [True, -1, 1.5, "1", MAX_TRIAL_SEED + 1])
def test_invalid_trial_seed_is_rejected_before_model(seed):
    policy = SpyPolicy()
    with pytest.raises(ValueError):
        run_policy_scenario(ScenarioConfig(), policy, seed=seed)
    assert policy.calls == []


@pytest.mark.parametrize("reply", [None, {"operation": "refund"},
                                  PolicyReply(PolicyDecision("retry"))])
def test_malformed_initial_reply_is_an_error_and_never_dispatches(reply, monkeypatch):
    class InvalidPolicy:
        metadata = {"provider": "test"}

        def decide(self, request, *, seed):
            return reply

    def forbidden_refund(*args, **kwargs):
        pytest.fail("Malformed model output must not dispatch a refund")

    monkeypatch.setattr(PaymentWorld, "refund", forbidden_refund)
    with pytest.raises(PolicyError):
        run_policy_scenario(ScenarioConfig(), InvalidPolicy())


def test_provider_or_after_response_policy_errors_abort_without_false_outcome():
    class FailingPolicy(SpyPolicy):
        def decide(self, request, *, seed):
            if request.stage == "after_response":
                raise PolicyError("The local model did not return a usable decision")
            return super().decide(request, seed=seed)

    with pytest.raises(PolicyError, match="local model"):
        run_policy_scenario(ScenarioConfig(), FailingPolicy())


@pytest.mark.parametrize("metadata", [None, "test", {"invalid": float("nan")}, {1: "key"}])
def test_invalid_declared_metadata_is_a_policy_error_before_model_execution(metadata):
    policy = SpyPolicy()
    policy.metadata = metadata
    with pytest.raises(PolicyError, match="metadata"):
        run_policy_scenario(ScenarioConfig(), policy)
    assert policy.calls == []


def test_retry_at_exhausted_budget_is_an_error():
    class UnboundedPolicy(SpyPolicy):
        def decide(self, request, *, seed):
            return PolicyReply(PolicyDecision("refund" if request.stage == "select" else "retry"))

    with pytest.raises(PolicyError, match="budget"):
        run_policy_scenario(ScenarioConfig(), UnboundedPolicy(), max_attempts=1)


def test_intervention_changes_visible_context_with_fixed_action_target_and_model_phase_keys():
    policy = SpyPolicy()
    factual = run_policy_scenario(ScenarioConfig(), policy, seed=7)
    changed = run_policy_scenario(ScenarioConfig(), policy, seed=7,
                                  intervention=Intervention("vip_memory"))
    assert factual.trace.single_action == changed.trace.single_action
    assert changed.action_selected
    assert decision_events(changed)[0].data["policy_request"]["context"]["vip_memory"] == ""
    assert [event.data["model_seed"] for event in decision_events(factual)] == [
        event.data["model_seed"] for event in decision_events(changed)
    ]
    assert changed.trace.events[1].id == "vip_memory"
    assert changed.trace.events[1].data == {"value": ""}


def test_replay_without_action_keeps_target_and_starts_fresh_world():
    runner = RefundPolicyReplayRunner(ScenarioConfig(), ScriptedRefundPolicy())
    original = runner.run(None, 8)
    changed = runner.run(Intervention("customer_request"), 8)
    assert original.action_selected and original.consequence_satisfied
    assert not changed.action_selected and changed.consequence_satisfied is False
    assert original == runner.run(None, 8)
    assert runner.mode == "isolated_simulation" and runner.snapshot_isolation


def test_policy_replay_retry_credit_distinguishes_action_from_consequence():
    config = ScenarioConfig(context=RefundContext(retry_instruction=True), use_idempotency=False)
    runner = RefundPolicyReplayRunner(config, ScriptedRefundPolicy())
    candidate = (Intervention("retry_instruction"),)
    (action,) = leave_one_out(runner, candidate, samples=4, target="action")
    (consequence,) = leave_one_out(runner, candidate, samples=4, target="consequence")
    assert action.effect == 0
    assert consequence.effect == -1


def test_unknown_readback_remains_unknown_and_refuses_policy_consequence_estimates():
    runner = RefundPolicyReplayRunner(ScenarioConfig(fault=Fault.DELAYED_VISIBILITY),
                                     ScriptedRefundPolicy())
    assert runner.run(None, 0).consequence_satisfied is None
    with pytest.raises(InsufficientEvidenceError):
        leave_one_out(runner, (Intervention("distractor"),), samples=2, target="consequence")


def test_external_actor_provenance_and_delayed_reconciliation_are_unchanged_by_policy_interface():
    external = run_policy_scenario(
        ScenarioConfig(fault=Fault.TIMEOUT_BEFORE_COMMIT, external_actor=True), SpyPolicy(),
    )
    assert external.trace.verifications[-1].origin is OriginStatus.OTHER_ACTOR
    assert external.explanation.single_action.assessment_alignment == "unassessable"
    policy = SpyPolicy()
    reconciled = run_policy_scenario(
        ScenarioConfig(fault=Fault.DELAYED_VISIBILITY, reconcile_readback=True), policy,
    )
    assert [result.status for result in reconciled.trace.verifications] == [
        VerificationStatus.UNKNOWN, VerificationStatus.SATISFIED,
    ]
    assert len(policy.calls) == 2  # No model calls are made after revealing readback.
    assert len(reconciled.trace.observations) == 2


@pytest.mark.parametrize("intervention", [
    Intervention("refund_decision"), Intervention("customer_request", "replace", "yes"),
    Intervention("distractor", "replace", True),
])
def test_only_declared_typed_context_interventions_are_supported(intervention):
    policy = SpyPolicy()
    with pytest.raises(ValueError):
        run_policy_scenario(ScenarioConfig(), policy, intervention=intervention)
    assert policy.calls == []


def test_changed_gold_cannot_change_public_explanation():
    episode = run_policy_scenario(ScenarioConfig(), SpyPolicy())
    changed = replace(episode, ground_truth=({"invented_cause": "distractor"},))
    assert explain(changed.trace) == episode.explanation
