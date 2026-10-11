"""Action-linked outcomes require qualifying independent provenance witnesses."""

from dataclasses import replace

import pytest

from consequa_x.attribution import (
    InsufficientEvidenceError, Intervention, ReplayOutcome, leave_one_out,
)
from consequa_x.benchmark.runner import demo_scenarios, run_scenario
from consequa_x.benchmark.targets import action_linked_consequence, episode_outcome
from consequa_x.models import (
    Action, Observation, OriginStatus, OutcomeContract, VerificationStatus,
)
from consequa_x.verification import verify


def action(*, exact_count=1):
    expected = {"payment_id": "pay_42", "amount_minor": 200_000, "currency": "INR"}
    return Action(
        "action_1", "trace_1", "agent", "refund", expected, 10,
        OutcomeContract("contract_1", "refund_processed", expected, 100,
                        exact_count=exact_count, stability_ms=20),
    )


def effect(**changes):
    return {
        "effect_id": "effect_1", "payment_id": "pay_42", "amount_minor": 200_000,
        "currency": "INR", "committed_at_ms": 40, "status": "processed",
        "action_id": "action_1", "actor": "agent", **changes,
    }


def observation(*records, **changes):
    values = {
        "observation_id": "obs_1", "source": "independent_ledger",
        "observed_at_ms": 200, "as_of_ms": 200, "scope": {"payment_id": "pay_42"},
        "records": tuple(records), "complete": True, "available": True,
    }
    return Observation(**{**values, **changes})


@pytest.mark.parametrize("committed_at", [10, 40, 100])
def test_confirmed_qualifying_witness_covers_registration_and_deadline(committed_at):
    registered = action()
    result = verify(registered, observation(effect(committed_at_ms=committed_at)))
    assert action_linked_consequence(registered, result) is True


def test_reversal_after_horizon_preserves_the_bounded_action_linked_outcome():
    registered = action()
    result = verify(registered, observation(effect(status="reversed", reversed_at_ms=121)))
    assert result.status is VerificationStatus.SATISFIED
    assert action_linked_consequence(registered, result) is True


@pytest.mark.parametrize("changes", [
    {"amount_minor": 100_000}, {"currency": "USD"}, {"committed_at_ms": 101},
    {"status": "reversed", "reversed_at_ms": 100},
])
def test_confirmed_unqualified_record_does_not_link_an_external_contract_witness(changes):
    registered = action(exact_count=None)
    external = effect(effect_id="external", actor="operator", action_id="operator_action")
    result = verify(registered, observation(effect(**changes), external))
    assert result.status is VerificationStatus.SATISFIED
    assert result.origin is OriginStatus.CONFIRMED
    assert result.attributable_effect_ids == ("effect_1",)
    assert action_linked_consequence(registered, result) is None


def test_exactly_one_external_correct_effect_with_a_linked_partial_effect_remains_unknown():
    registered = action()
    external = effect(effect_id="external", actor="operator", action_id="operator_action")
    result = verify(registered, observation(effect(amount_minor=100_000), external))
    assert result.status is VerificationStatus.SATISFIED
    assert result.origin is OriginStatus.CONFIRMED
    assert result.attributable_effect_ids == ("effect_1",)
    assert action_linked_consequence(registered, result) is None


def test_explicitly_external_witness_is_state_success_but_not_action_linked_success():
    registered = action()
    result = verify(registered, observation(effect(actor="operator", action_id="other_action")))
    assert result.status is VerificationStatus.SATISFIED
    assert result.origin is OriginStatus.OTHER_ACTOR
    assert action_linked_consequence(registered, result) is False


def test_external_actor_without_action_id_is_still_explicit_external_provenance():
    registered = action()
    record = effect(actor="operator")
    del record["action_id"]
    result = verify(registered, observation(record))
    assert result.origin is OriginStatus.OTHER_ACTOR
    assert action_linked_consequence(registered, result) is False


def test_missing_provenance_does_not_turn_state_success_into_action_failure():
    registered = action()
    record = effect()
    del record["action_id"], record["actor"]
    result = verify(registered, observation(record))
    assert result.status is VerificationStatus.SATISFIED
    assert action_linked_consequence(registered, result) is None


@pytest.mark.parametrize("records", [(), (effect(amount_minor=100_000),),
                                     (effect(actor="operator", action_id="other",
                                             amount_minor=100_000),)])
def test_violated_state_is_false_independently_of_origin(records):
    registered = action()
    result = verify(registered, observation(*records))
    assert result.status is VerificationStatus.VIOLATED
    assert action_linked_consequence(registered, result) is False


@pytest.mark.parametrize("changes", [{"available": False}, {"complete": False},
                                    {"as_of_ms": 119}])
def test_unknown_readback_remains_unknown_even_with_a_present_witness(changes):
    registered = action()
    result = verify(registered, observation(effect(), **changes))
    assert result.status is VerificationStatus.UNKNOWN
    assert action_linked_consequence(registered, result) is None


@pytest.mark.parametrize("changed_details", [
    {"complete": False}, {"available": False}, {"watermark_ms": 119},
    {"records": []}, {"scope": {}},
    {"expected": {}}, {"horizon_ms": 100},
])
def test_origin_label_without_supported_evidence_cannot_establish_external_failure(changed_details):
    registered = action()
    result = verify(registered, observation(effect(actor="operator", action_id="other")))
    evidence = replace(result.evidence[-1], details={**result.evidence[-1].details, **changed_details})
    unsupported = replace(result, evidence=(evidence,))
    assert action_linked_consequence(registered, unsupported) is None


def test_external_origin_label_cannot_override_a_matching_agent_record():
    registered = action()
    result = verify(registered, observation(effect()))
    mislabeled = replace(result, origin=OriginStatus.OTHER_ACTOR, attributable_effect_ids=())
    assert action_linked_consequence(registered, mislabeled) is None


def test_invalid_attempt_metadata_cannot_establish_a_link_even_with_a_confirmed_origin():
    registered = action()
    result = verify(registered, observation(effect()))
    details = {**result.evidence[-1].details, "records": [effect(attempt_id="")]}
    unsupported = replace(result, evidence=(replace(result.evidence[-1], details=details),))
    assert action_linked_consequence(registered, unsupported) is None


def test_unknown_companion_provenance_cannot_cover_a_positive_exact_count():
    registered = action(exact_count=2)
    unknown = effect(effect_id="effect_2")
    del unknown["actor"], unknown["action_id"]
    result = verify(registered, observation(effect(), unknown))
    assert result.status is VerificationStatus.SATISFIED
    assert result.origin is OriginStatus.CONFIRMED
    assert action_linked_consequence(registered, result) is None


def test_positive_exact_count_requires_all_required_qualifying_linked_witnesses():
    registered = action(exact_count=2)
    other = effect(effect_id="effect_2", actor="operator", action_id="other")
    result = verify(registered, observation(effect(), other))
    assert result.status is VerificationStatus.SATISFIED
    assert action_linked_consequence(registered, result) is None
    result = verify(registered, observation(effect(), effect(effect_id="effect_2")))
    assert action_linked_consequence(registered, result) is True


def test_at_least_one_count_requires_one_linked_witness_but_absence_contract_is_unsupported():
    registered = action(exact_count=None)
    result = verify(registered, observation(
        effect(), effect(effect_id="external", actor="operator", action_id="other"),
    ))
    assert action_linked_consequence(registered, result) is True
    absent = action(exact_count=0)
    assert action_linked_consequence(absent, verify(absent, observation())) is None
    assert action_linked_consequence(absent, verify(absent, observation(effect()))) is False


def test_unrelated_contract_result_remains_unknown():
    registered = action()
    result = verify(registered, observation(effect()))
    assert action_linked_consequence(registered, replace(result, contract_id="other")) is None


@pytest.mark.parametrize("name,world,linked", [
    ("clean", True, True), ("external_actor", True, False),
    ("missing_provenance", True, None), ("false_success", False, False),
    ("delayed_visibility", None, None),
])
def test_episode_mapping_reads_evidence_and_never_hidden_truth_or_assessment(name, world, linked):
    config = next(config for config in demo_scenarios() if config.name == name)
    episode = run_scenario(config)
    mapped = episode_outcome(replace(episode, ground_truth=()))
    assert mapped.consequence_satisfied is world
    assert mapped.action_linked_consequence_satisfied is linked


def test_replay_estimates_can_select_the_action_linked_target_without_state_conflation():
    class Runner:
        def run(self, intervention, seed):
            return ReplayOutcome(True, True, intervention is None)

    estimate, = leave_one_out(Runner(), (Intervention("context"),), samples=2,
                             target="action_linked_consequence")
    assert estimate.target == "action_linked_consequence"
    assert estimate.baseline_rate == estimate.effect == 1
    assert estimate.intervention_rate == 0


def test_old_runner_leaves_optional_target_unknown_and_refuses_without_redraw():
    class Runner:
        calls = []

        def run(self, intervention, seed):
            self.calls.append((intervention, seed))
            return ReplayOutcome(True, True)

    runner = Runner()
    with pytest.raises(InsufficientEvidenceError) as caught:
        leave_one_out(runner, (Intervention("context"),), samples=2,
                      target="action_linked_consequence")
    assert caught.value.unknown_pairs == 2 and caught.value.known_pairs == 0
    assert len(runner.calls) == 4
    assert ReplayOutcome(True, True).to_dict() == {
        "action_selected": True, "consequence_satisfied": True,
    }
    assert ReplayOutcome(True, True, False).to_dict()["action_linked_consequence_satisfied"] is False


@pytest.mark.parametrize("value", [0, 1, "unknown", [], {}])
def test_action_linked_outcome_requires_a_boolean_or_none(value):
    with pytest.raises(ValueError, match="action_linked_consequence_satisfied"):
        ReplayOutcome(True, True, value)
