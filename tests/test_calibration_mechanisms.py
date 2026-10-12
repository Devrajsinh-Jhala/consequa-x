"""Independent analytic games and real payment outcomes for calibration fixtures."""

from copy import deepcopy
from dataclasses import replace
import itertools
import json
import math
import random

import pytest

from consequa_x.benchmark import calibration_mechanisms as subject
from consequa_x.benchmark.decision_coalition import replay_decision_coalition
from consequa_x.benchmark.decision_contrastive import contrastive_decisions
from consequa_x.benchmark.decision_shapley import shapley_decisions
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED
from consequa_x.benchmark.targets import episode_outcome
from consequa_x.models import EventType, ResponseStatus, ToolResponse, VerificationStatus
from consequa_x.policies import PolicyError, PolicyRequest


def timeout_request(*, remaining=1, status=ResponseStatus.TIMEOUT):
    return PolicyRequest(
        "after_response", {"idempotency_available": False}, {},
        (ToolResponse("attempt", status, 6, "request", {"code": "timeout"}),), remaining,
    )


def retry_draw(trial_seed, probability):
    return random.Random(trial_seed * 6 + 1).random() < probability


def independent_shares(values, n):
    """Exhaustive factorial-weight definition, independent of antithetic walks."""
    shares = []
    for index in range(n):
        total = 0.
        for mask in range(1 << n):
            if mask & (1 << index):
                continue
            size = mask.bit_count()
            weight = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
            total += weight * (values[mask | (1 << index)] - values[mask])
        shares.append(total)
    return shares


def test_registry_is_fixed_and_immutable():
    assert tuple(subject.CALIBRATION_MECHANISMS) == (
        "protective-stop-q10", "protective-stop-q50", "protective-stop-q90",
        "retry-pivot-q10", "retry-pivot-q50", "retry-pivot-q90",
        "idempotent-stop-q50", "unknown-provenance-stop-q50", "lagged-readback-stop-q50",
    )
    with pytest.raises(TypeError):
        subject.CALIBRATION_MECHANISMS["other"] = object()
    with pytest.raises(ValueError):
        subject.get_calibration_mechanism("missing")
    with pytest.raises(ValueError):
        subject.get_calibration_mechanism([])


@pytest.mark.parametrize("probability", [.1, .5, .9])
def test_protective_population_shares_and_prefix_effects_are_different(probability):
    mechanism = subject.CalibrationMechanism("protective", probability)
    reference = mechanism.analytic_reference()
    assert reference["decision_count"] == 2
    assert reference["population_not_finite_seed_claim"] is True
    assert reference["coalition_valid_probabilities"] == [1.] * 4
    for target in ("consequence", "action_linked_consequence"):
        truth = reference["targets"][target]
        game = [probability, probability, 0., 0.]
        assert truth["coalition_bad_rates"] == game
        assert truth["shapley_values"] == pytest.approx(independent_shares(game, 2))
        assert truth["shapley_values"] == [0., -probability]
        assert truth["shapley_null_positions"] == [0]
        # Prefix replay of an irrelevant selection still resamples its suffix.
        assert truth["contrastive_effects"] == [probability, probability]
        assert truth["contrastive_null_positions"] == []
        assert truth["latest_population_rescue"] is None
        assert truth["endpoint_difference"] == -probability
        assert all(truth[name] for name in ("contrastive_eligible", "shapley_eligible", "endpoint_eligible"))
    action = reference["targets"]["action"]
    assert action["factual_bad"] is False
    assert action["shapley_values"] == action["contrastive_effects"] == [0., 0.]


@pytest.mark.parametrize("probability", [.1, .5, .9])
def test_retry_population_has_pivot_and_undefined_held_tail_game(probability):
    mechanism = subject.CalibrationMechanism("retry", probability, "retry")
    reference = mechanism.analytic_reference()
    assert reference["decision_count"] == 3
    assert reference["coalition_valid_probabilities"] == [1., 1., 1., 1., probability, probability, 1., 1.]
    for target in subject.TARGETS:
        truth = reference["targets"][target]
        assert truth["shapley_eligible"] is False
        assert truth["shapley_values"] is None
        assert truth["coalition_bad_rates"][4:6] == [None, None]
        assert truth["endpoint_eligible"] is True
        if target != "action":
            assert truth["factual_bad"] is True
            assert truth["contrastive_effects"] == [probability - 1, probability - 1, 0.]
            assert truth["latest_population_rescue"] == 1
            assert truth["contrastive_null_positions"] == [2]
            assert truth["endpoint_difference"] == 1 - probability
        else:
            assert truth["contrastive_effects"] == [0., 0., 0.]
            assert truth["endpoint_difference"] == 0.


def test_idempotency_population_is_zero_for_every_target_and_coalition():
    mechanism = subject.get_calibration_mechanism("idempotent-stop-q50")
    for truth in mechanism.analytic_reference()["targets"].values():
        assert truth["factual_bad"] is False
        assert truth["changed_bad_rates"] == truth["contrastive_effects"] == [0., 0.]
        assert truth["coalition_bad_rates"] == [0.] * 4
        assert truth["shapley_values"] == [0., 0.]
        assert truth["endpoint_difference"] == 0.


def test_missing_provenance_and_stale_readback_refuse_only_affected_references():
    provenance = subject.get_calibration_mechanism("unknown-provenance-stop-q50").analytic_reference()
    assert provenance["targets"]["consequence"]["shapley_values"] == [0., -.5]
    affected = provenance["targets"]["action_linked_consequence"]
    assert affected["factual_bad"] is None
    assert affected["contrastive_effects"] == [None, None]
    assert affected["shapley_values"] is None and affected["endpoint_difference"] is None
    assert not any(affected[name] for name in ("contrastive_eligible", "shapley_eligible", "endpoint_eligible"))
    lagged = subject.get_calibration_mechanism("lagged-readback-stop-q50").analytic_reference()
    for target in ("consequence", "action_linked_consequence"):
        assert lagged["targets"][target]["factual_bad"] is None
        assert lagged["targets"][target]["shapley_values"] is None
    assert lagged["targets"]["action"]["shapley_values"] == [0., 0.]


def test_reference_is_independent_of_captures_rollouts_and_mutable_return_values(monkeypatch):
    mechanism = subject.get_calibration_mechanism("protective-stop-q50")

    def forbidden(*args, **kwargs):
        raise AssertionError("An analytic oracle must not call the episode runner")

    monkeypatch.setattr(subject, "run_policy_scenario", forbidden)
    original = mechanism.analytic_reference()
    original["targets"]["consequence"]["contrastive_effects"][0] = 999
    assert mechanism.analytic_reference()["targets"]["consequence"]["contrastive_effects"] == [.5, .5]


def test_reserved_phase_intervention_is_exact_predeclared_and_public():
    policy = subject.SeededRetryCalibrationPolicy(.5, "stop", factual_policy_seed=7)
    request = timeout_request()
    before = deepcopy(request.to_dict())
    assert random.Random(43).random() < .5
    reserved = policy.decide(request, seed=43)
    assert reserved.decision.operation == "stop"
    assert reserved.metadata["decision_source"] == "reserved_factual_intervention"
    assert random.Random(49).random() < .5
    other = policy.decide(request, seed=49)
    assert other.decision.operation == "retry"
    assert other.metadata["decision_source"] == "seeded_bernoulli_retry"
    assert request.to_dict() == before
    conditioning = policy.metadata["conditioning"]
    assert conditioning["reserved_timeout_model_seed"] == 43
    assert conditioning["naturally_sampled_factual"] is False
    assert policy.metadata["hidden_evidence_inputs"] is False
    json.dumps(policy.metadata, allow_nan=False)


@pytest.mark.parametrize("operation", ["stop", "retry"])
def test_conditioned_captures_use_world_seed_and_distinct_policy_seed(operation):
    mechanism = subject.CalibrationMechanism("capture", .1, operation)
    episode = mechanism.capture_factual(seed=17, policy_seed=7)
    decisions = [event for event in episode.trace.events if event.type is EventType.AGENT_DECISION]
    assert episode.seed == 17 and episode.trace.trace_id == "trace:17"
    assert len(decisions) == mechanism.decision_count
    assert [event.data["model_seed"] for event in decisions] == list(range(42, 42 + len(decisions)))
    assert decisions[1].data["policy_reply"]["decision"]["operation"] == operation
    for event in decisions:
        assert event.data["policy"] == mechanism.make_policy(factual_policy_seed=7).metadata
        request = event.data["policy_request"]
        assert set(request) == {"stage", "task", "context", "responses", "attempts_remaining"}
        assert not {"fault", "ground_truth", "verification", "observations"} & request["task"].keys()
    refunds = [record for record in episode.ground_truth if record["kind"] == "refund"]
    assert len(refunds) == (1 if operation == "stop" else 2)
    assert episode.trace.verifications[-1].status is (
        VerificationStatus.SATISFIED if operation == "stop" else VerificationStatus.VIOLATED
    )


@pytest.mark.parametrize("name", list(subject.CALIBRATION_MECHANISMS))
def test_factual_outcome_matches_reference_without_using_gold_as_an_input(name):
    mechanism = subject.get_calibration_mechanism(name)
    original = mechanism.capture_factual(seed=3, policy_seed=9)
    outcome = episode_outcome(original)
    values = (outcome.action_selected, outcome.consequence_satisfied, outcome.action_linked_consequence_satisfied)
    for target, actual in zip(subject.TARGETS, values, strict=True):
        expected_bad = mechanism.analytic_reference()["targets"][target]["factual_bad"]
        assert (None if actual is None else not actual) == expected_bad
    # Replacing evaluator truth does not change any independently verified target.
    assert episode_outcome(replace(original, ground_truth=({"kind": "poison"},))) == outcome


@pytest.mark.parametrize("name", ["protective-stop-q10", "protective-stop-q50", "protective-stop-q90",
                                 "idempotent-stop-q50"])
@pytest.mark.parametrize("trial_seed", [100, 101])
def test_every_valid_coalition_runs_real_world_and_matches_seeded_payment_counts(name, trial_seed):
    mechanism = subject.get_calibration_mechanism(name)
    original = mechanism.capture_factual()
    original_bytes = original.trace.to_json()
    policy = mechanism.make_policy()
    for mask in range(4):
        held = tuple(index for index in range(2) if mask & (1 << index))
        budgeted = BudgetedPolicy(policy, 10)
        replayed = replay_decision_coalition(original, budgeted, held_indices=held,
                                            continuation_seed=trial_seed)
        assert replayed.status == "completed" and replayed.episode is not None
        sampled_retry = not mask & 2 and retry_draw(trial_seed, mechanism.retry_probability)
        expected_count = 1 + int(sampled_retry and not mechanism.use_idempotency)
        refunds = [record for record in replayed.episode.ground_truth if record["kind"] == "refund"]
        assert len(refunds) == expected_count
        outcome = episode_outcome(replayed.episode)
        assert outcome.action_selected is True
        assert outcome.consequence_satisfied is outcome.action_linked_consequence_satisfied is (expected_count == 1)
        assert replayed.policy_calls == budgeted.calls
    assert original.trace.to_json() == original_bytes


def test_real_missing_provenance_violation_is_known_but_good_state_linkage_is_unknown():
    mechanism = subject.get_calibration_mechanism("unknown-provenance-stop-q50")
    original = mechanism.capture_factual()
    seen = set()
    for trial_seed in (100, 101, 102, 103):
        replayed = replay_decision_coalition(original, BudgetedPolicy(mechanism.make_policy(), 10),
                                            held_indices=(), continuation_seed=trial_seed)
        assert replayed.status == "completed"
        outcome = episode_outcome(replayed.episode)
        duplicate = retry_draw(trial_seed, .5)
        assert outcome.consequence_satisfied is (not duplicate)
        assert outcome.action_linked_consequence_satisfied is (False if duplicate else None)
        seen.add(duplicate)
    assert seen == {False, True}


def test_real_held_terminal_stop_can_be_unreachable_and_receipt_preserves_invalidity():
    mechanism = subject.get_calibration_mechanism("retry-pivot-q50")
    original = mechanism.capture_factual()
    for trial_seed in (100, 101, 102, 103):
        replayed = replay_decision_coalition(original, BudgetedPolicy(mechanism.make_policy(), 10),
                                            held_indices=(2,), continuation_seed=trial_seed)
        if retry_draw(trial_seed, .5):
            assert replayed.status == "completed"
            assert episode_outcome(replayed.episode).consequence_satisfied is False
        else:
            assert replayed.status == "invalid" and replayed.episode is None
            assert replayed.error_type == "DecisionCoalitionUnreachable"
            assert replayed.unreached_held_indices == (2,)
            assert replayed.policy_calls == 2


def test_real_contrastive_draws_match_independent_seed_schedule_calculation():
    mechanism = subject.get_calibration_mechanism("protective-stop-q50")
    samples = 16
    result = contrastive_decisions(
        mechanism.capture_factual(), BudgetedPolicy(mechanism.make_policy(), 1000),
        samples=samples, seed=100, targets=subject.TARGETS, bootstrap_samples=200,
    )
    for estimate in result.results:
        expected = (0. if estimate.target == "action" else sum(
            retry_draw(seed, .5) for seed in range(100 + estimate.decision_index * samples,
                                                  100 + (estimate.decision_index + 1) * samples)
        ) / samples)
        assert estimate.status == "estimated"
        assert estimate.effect == estimate.changed_bad_rate == expected
    assert all(locus.status == "no_rescue" for locus in result.loci)


def test_real_shapley_protective_game_has_negative_share_and_nonzero_sampling_dummy():
    mechanism = subject.get_calibration_mechanism("protective-stop-q50")
    result = shapley_decisions(
        mechanism.capture_factual(), BudgetedPolicy(mechanism.make_policy(), 5000),
        pairs=8, samples_per_eval=2, endpoint_samples=16, seed=100, targets=subject.TARGETS,
    )
    assert all(branch.replay.status == "completed" for branch in result.branches)
    for target in ("consequence", "action_linked_consequence"):
        values = [estimate.shapley_value for estimate in result.results if estimate.target == target]
        assert values[1] < 0
        # Occurrences use fresh seeds, so the selection dummy is zero only in
        # population. The test does not require a sampled point to equal zero.
        assert all(estimate.status == "estimated" for estimate in result.results if estimate.target == target)
    assert all(estimate.shapley_value == 0 for estimate in result.results if estimate.target == "action")


@pytest.mark.parametrize("probability", [0., 1.])
@pytest.mark.parametrize("operation", ["stop", "retry"])
def test_probability_endpoints_have_exact_analytic_games_where_defined(probability, operation):
    mechanism = subject.CalibrationMechanism("endpoint", probability, operation)
    for target, truth in mechanism.analytic_reference()["targets"].items():
        if truth["shapley_eligible"]:
            assert truth["shapley_values"] == independent_shares(truth["coalition_bad_rates"], mechanism.decision_count)
        if target != "action":
            assert truth["changed_bad_rates"][:2] == [probability, probability]


def test_probability_one_missing_provenance_duplicate_has_known_game():
    mechanism = subject.CalibrationMechanism("duplicate", 1., "retry", include_provenance=False)
    truth = mechanism.analytic_reference()["targets"]["action_linked_consequence"]
    assert truth["factual_bad"] is True
    assert truth["changed_bad_rates"] == [1., 1., 1.]
    assert truth["coalition_bad_rates"] == [1.] * 8
    assert truth["shapley_values"] == [0., 0., 0.]


@pytest.mark.parametrize("probability", [True, -1., 1.1, float("nan"), float("inf"), "0.5", None])
def test_invalid_probability_is_rejected(probability):
    with pytest.raises(ValueError):
        subject.CalibrationMechanism("invalid", probability)
    with pytest.raises(ValueError):
        subject.SeededRetryCalibrationPolicy(probability)


@pytest.mark.parametrize("seed", [True, -1, MAX_TRIAL_SEED + 1, 1.5, None])
def test_invalid_reserved_trial_seed_is_rejected(seed):
    with pytest.raises(ValueError):
        subject.SeededRetryCalibrationPolicy(.5, factual_policy_seed=seed)


@pytest.mark.parametrize("field,value", [("name", ""), ("name", 1), ("factual_operation", "refund"),
                                         ("use_idempotency", 1), ("include_provenance", None),
                                         ("read_lag_ms", True), ("read_lag_ms", -1)])
def test_invalid_mechanism_configuration_is_rejected(field, value):
    kwargs = {"name": "invalid", "retry_probability": .5, field: value}
    with pytest.raises(ValueError):
        subject.CalibrationMechanism(**kwargs)


@pytest.mark.parametrize("seed", [True, -1, 2**31, 1.5])
def test_invalid_decision_seed_is_rejected(seed):
    with pytest.raises(PolicyError):
        subject.SeededRetryCalibrationPolicy(.5).decide(timeout_request(), seed=seed)


def test_non_timeout_or_no_attempt_boundary_never_forces_a_retry():
    policy = subject.SeededRetryCalibrationPolicy(.5, "retry")
    for remaining, status in itertools.product((0, 1), (ResponseStatus.SUCCESS, ResponseStatus.ERROR)):
        assert policy.decide(timeout_request(remaining=remaining, status=status), seed=1).decision.operation == "stop"
    assert policy.decide(timeout_request(remaining=0), seed=1).decision.operation == "stop"
    with pytest.raises(PolicyError):
        policy.decide(None, seed=1)
