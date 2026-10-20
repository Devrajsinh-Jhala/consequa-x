"""End-to-end checks of captured assessments, readback, and isolated replay."""

from dataclasses import replace

from jsonschema import Draft202012Validator
import pytest

from consequa_x.attribution import (
    InsufficientEvidenceError,
    Intervention,
    leave_one_out,
)
from consequa_x.benchmark.payments import Fault, PaymentWorld
from consequa_x.benchmark.runner import (
    RefundContext,
    RefundReplayRunner,
    ScenarioConfig,
    demo_scenarios,
    run_scenario,
)
from consequa_x.explanation import explain
from consequa_x.models import (
    AssessmentStatus,
    OriginStatus,
    ResponseStatus,
    Trace,
    VerificationStatus,
)
from consequa_x.schema import get_trace_schema, validate_trace
from consequa_x.verification import verify


def scenarios_by_name():
    return {config.name: config for config in demo_scenarios()}


@pytest.mark.parametrize("config", demo_scenarios(), ids=lambda config: config.name)
def test_every_demo_scenario_is_reproducible_and_portable(config):
    episode = run_scenario(config, seed=17)
    assert episode == run_scenario(config, seed=17)
    Draft202012Validator(get_trace_schema()).validate(episode.trace.to_dict())
    assert validate_trace(episode.trace.to_json()) == episode.trace
    assert Trace.from_dict(episode.trace.to_dict()) == episode.trace
    assert explain(episode.trace) == episode.explanation


@pytest.mark.parametrize("name,status,origin,diagnosis", [
    ("clean", VerificationStatus.SATISFIED, OriginStatus.CONFIRMED, "CONSISTENT_OUTCOME"),
    ("timeout_after_commit", VerificationStatus.SATISFIED, OriginStatus.CONFIRMED,
     "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE"),
    ("timeout_before_commit", VerificationStatus.VIOLATED, OriginStatus.UNKNOWN,
     "CONSEQUENCE_VIOLATION"),
    ("false_success", VerificationStatus.VIOLATED, OriginStatus.UNKNOWN,
     "RESPONSE_EFFECT_DIVERGENCE"),
    ("partial_effect", VerificationStatus.VIOLATED, OriginStatus.CONFIRMED, "PARTIAL_EFFECT"),
    ("delayed_visibility", VerificationStatus.UNKNOWN, OriginStatus.UNKNOWN, "UNKNOWN_OUTCOME"),
    ("delayed_reconciled", VerificationStatus.SATISFIED, OriginStatus.CONFIRMED,
     "CONSISTENT_OUTCOME"),
    ("unsafe_retry", VerificationStatus.VIOLATED, OriginStatus.CONFIRMED, "DUPLICATE_EFFECT"),
    ("safe_retry", VerificationStatus.SATISFIED, OriginStatus.CONFIRMED,
     "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE"),
    ("external_actor", VerificationStatus.SATISFIED, OriginStatus.OTHER_ACTOR,
     "EXTERNAL_ACTOR_EFFECT"),
    ("missing_provenance", VerificationStatus.SATISFIED, OriginStatus.UNKNOWN,
     "UNCONFIRMED_ORIGIN"),
    ("synthetic_compensation", VerificationStatus.VIOLATED, OriginStatus.CONFIRMED,
     "REVERSED_EFFECT"),
])
def test_demo_outcomes_are_grounded_in_the_declared_contract(name, status, origin, diagnosis):
    episode = run_scenario(scenarios_by_name()[name])
    result = episode.trace.verifications[-1]
    assert result.status is status
    assert result.origin is origin
    assert diagnosis in episode.explanation.single_action.codes


def test_lost_response_does_not_hide_committed_effect_or_rewrite_agent_assessment():
    episode = run_scenario(seed=9)
    assert episode.action_selected
    assert episode.trace.responses[0].status is ResponseStatus.TIMEOUT
    assert episode.trace.latest_assessment().status is AssessmentStatus.FAILURE
    result = episode.trace.verifications[-1]
    assert result.status is VerificationStatus.SATISFIED
    assert result.origin is OriginStatus.CONFIRMED
    assert result.effect_ids == result.attributable_effect_ids
    assert episode.explanation.single_action.diagnosis == "ASSESSMENT_DIVERGENCE / ACKNOWLEDGEMENT_EFFECT_DIVERGENCE"
    assert episode.explanation.single_action.assessment_alignment == "contradicted"
    assert set(episode.explanation.single_action.codes) == {
        "ASSESSMENT_DIVERGENCE", "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE",
    }


def test_same_selected_refund_and_response_sequence_can_have_different_effects():
    configs = scenarios_by_name()
    safe = run_scenario(configs["safe_retry"], seed=6)
    unsafe = run_scenario(configs["unsafe_retry"], seed=6)
    assert safe.action_selected == unsafe.action_selected is True
    assert safe.trace.single_action.arguments == unsafe.trace.single_action.arguments
    assert safe.trace.single_action.contract == unsafe.trace.single_action.contract
    assert [response.status for response in safe.trace.responses] == [
        response.status for response in unsafe.trace.responses
    ] == [ResponseStatus.TIMEOUT, ResponseStatus.SUCCESS]
    assert safe.trace.latest_assessment().status == unsafe.trace.latest_assessment().status
    assert safe.trace.verifications[-1].status is VerificationStatus.SATISFIED
    assert unsafe.trace.verifications[-1].status is VerificationStatus.VIOLATED
    assert len(safe.trace.verifications[-1].effect_ids) == 1
    assert len(unsafe.trace.verifications[-1].effect_ids) == 2
    assert "DUPLICATE_EFFECT" in unsafe.explanation.single_action.codes
    assert "DUPLICATE_EFFECT" not in safe.explanation.single_action.codes


def test_external_actor_state_satisfaction_does_not_claim_agent_effect_origin():
    episode = run_scenario(scenarios_by_name()["external_actor"])
    result = episode.trace.verifications[-1]
    assert result.status is VerificationStatus.SATISFIED
    assert result.origin is OriginStatus.OTHER_ACTOR
    assert result.effect_ids and result.attributable_effect_ids == ()
    assert "EXTERNAL_ACTOR_EFFECT" in episode.explanation.single_action.codes
    assert episode.explanation.single_action.assessment_alignment == "unassessable"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" not in episode.explanation.single_action.codes
    assert episode.explanation.single_action.diagnosis == " / ".join(episode.explanation.single_action.codes)


def test_missing_origin_does_not_prevent_state_verification_or_infer_provenance():
    episode = run_scenario(scenarios_by_name()["missing_provenance"])
    result = episode.trace.verifications[-1]
    assert result.status is VerificationStatus.SATISFIED
    assert result.origin is OriginStatus.UNKNOWN
    assert result.attributable_effect_ids == ()
    assert "UNCONFIRMED_ORIGIN" in episode.explanation.single_action.codes
    assert episode.explanation.single_action.assessment_alignment == "unassessable"
    for record in episode.trace.observations[-1].records:
        assert not {"action_id", "attempt_id", "actor"} & record.keys()


def test_cautious_timeout_assessment_is_not_called_an_incorrect_belief():
    episode = run_scenario(ScenarioConfig(timeout_assessment=AssessmentStatus.UNKNOWN))
    assert episode.trace.verifications[-1].status is VerificationStatus.SATISFIED
    assert episode.explanation.single_action.assessment_alignment == "unassessable"
    assert "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE" in episode.explanation.single_action.codes
    assert "ASSESSMENT_DIVERGENCE" not in episode.explanation.single_action.codes
    assert episode.explanation.single_action.diagnosis == " / ".join(episode.explanation.single_action.codes)


def test_delayed_readback_remains_unknown_until_horizon_is_covered():
    configs = scenarios_by_name()
    delayed = run_scenario(configs["delayed_visibility"])
    reconciled = run_scenario(configs["delayed_reconciled"])
    assert delayed.trace.verifications[-1].status is VerificationStatus.UNKNOWN
    assert delayed.explanation.single_action.assessment_alignment == "unassessable"
    assert "ASSESSMENT_DIVERGENCE" not in delayed.explanation.single_action.codes
    assert len(reconciled.trace.observations) == len(reconciled.trace.verifications) == 2
    assert [result.status for result in reconciled.trace.verifications] == [
        VerificationStatus.UNKNOWN, VerificationStatus.SATISFIED,
    ]
    assert reconciled.trace.verifications[0] == delayed.trace.verifications[0]
    assert reconciled.trace.observations[0].as_of_ms < reconciled.trace.single_action.contract.horizon_ms
    assert reconciled.trace.observations[-1].as_of_ms >= reconciled.trace.single_action.contract.horizon_ms
    assert reconciled.explanation.single_action.consequence == reconciled.trace.verifications[-1]


@pytest.mark.parametrize("stability,status", [
    (0, VerificationStatus.SATISFIED), (20, VerificationStatus.VIOLATED),
])
def test_compensation_is_evaluated_at_contract_horizon(stability, status):
    action = run_scenario(ScenarioConfig("clean", Fault.CLEAN)).trace.single_action
    action = replace(action, contract=replace(action.contract, stability_ms=stability))
    world = PaymentWorld(seed=4)
    world.advance(action.registered_at_ms)
    world.refund(action, "first")
    world.advance(101 - world.time_ms)
    effect_id = world.read_refunds("pay_42").records[0]["effect_id"]
    world.reverse(effect_id)
    world.advance(200 - world.time_ms)
    observation = world.read_refunds("pay_42")
    assert observation.records[0]["reversed_at_ms"] == 102
    assert verify(action, observation).status is status


def nested_keys(value):
    if isinstance(value, dict):
        yield from value
        for item in value.values():
            yield from nested_keys(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from nested_keys(item)


def test_evaluator_truth_does_not_enter_public_trace_or_explanation():
    episode = run_scenario(scenarios_by_name()["unsafe_retry"])
    assert any("fault_applied" in record for record in episode.ground_truth)
    hidden = {
        "ground_truth", "fault_applied", "fault", "cache_origin",
        "committed_effect_ids", "execution_attempts", "selection_draw", "retry_draw",
    }
    assert not hidden & set(nested_keys(episode.trace.to_dict()))
    assert not hidden & set(nested_keys(episode.explanation.to_dict()))
    tampered_gold = replace(episode, ground_truth=({"planted_driver": "distractor"},))
    assert explain(tampered_gold.trace) == episode.explanation


def test_counterfactual_without_selected_action_keeps_same_consequence_target():
    original = run_scenario(seed=11)
    changed = run_scenario(seed=11, intervention=Intervention("customer_request"))
    assert original.action_selected and not changed.action_selected
    assert changed.trace.single_action == original.trace.single_action
    assert changed.trace.responses == ()
    assert changed.trace.latest_assessment().status is AssessmentStatus.UNKNOWN
    assert changed.trace.verifications[-1].status is VerificationStatus.VIOLATED
    assert changed.trace.verifications[-1].contract_id == original.trace.verifications[-1].contract_id


@pytest.mark.parametrize("intervention", [
    Intervention("refund_decision"),
    Intervention("vip_policy", "replace", "false"),
    Intervention("customer_request", "replace", None),
    Intervention("distractor", "replace", True),
])
def test_replay_refuses_non_context_candidates_and_malformed_typed_replacements(intervention):
    with pytest.raises(ValueError):
        run_scenario(intervention=intervention)


def test_retry_context_affects_consequence_but_not_initial_action_selection():
    runner = RefundReplayRunner(scenarios_by_name()["unsafe_retry"])
    candidate = (Intervention("retry_instruction"),)
    (action,) = leave_one_out(runner, candidate, samples=8, seed=23, target="action")
    (consequence,) = leave_one_out(runner, candidate, samples=8, seed=23, target="consequence")
    assert action.baseline_rate == action.intervention_rate == 1
    assert action.effect == 0
    assert consequence.baseline_rate == 0 and consequence.intervention_rate == 1
    assert consequence.effect == -1
    assert action.seeds == consequence.seeds == tuple(range(23, 31))
    assert action.confidence_interval[0] <= 0 <= action.confidence_interval[1]
    assert consequence.confidence_interval[0] <= -1 <= consequence.confidence_interval[1]


def test_unknown_readback_refuses_consequence_estimate_but_preserves_action_target():
    runner = RefundReplayRunner(scenarios_by_name()["delayed_visibility"])
    candidates = (Intervention("vip_policy"),)
    with pytest.raises(InsufficientEvidenceError) as caught:
        leave_one_out(runner, candidates, samples=4, target="consequence")
    assert caught.value.unknown_pairs == 4
    assert caught.value.known_pairs == 0
    (action,) = leave_one_out(runner, candidates, samples=4, target="action")
    assert action.effect == 1


def test_seeded_policy_draws_remain_aligned_after_irrelevant_context_replacement():
    config = ScenarioConfig(context=RefundContext(retry_instruction=True),
                            selection_probability=0.55, retry_probability=0.45)
    runner = RefundReplayRunner(config)
    intervention = Intervention("distractor", "replace", "Different unrelated context.")
    outcomes = []
    for seed in range(32):
        factual = runner.run(None, seed)
        changed = runner.run(intervention, seed)
        assert factual == changed == runner.run(None, seed)
        outcomes.append(factual.action_selected)
    assert any(outcomes) and not all(outcomes)
