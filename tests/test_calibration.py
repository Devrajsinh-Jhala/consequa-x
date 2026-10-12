"""Repeated calibration exercises real refund replay and explicit scoring denominators."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math

import pytest

from consequa_x.benchmark import calibration as subject
from consequa_x.benchmark.calibration_mechanisms import get_calibration_mechanism
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED
from consequa_x.models import Trace


def small_plan(**kwargs):
    options = {"mechanisms": ("protective-stop-q50",), "repeats": 2, "samples": 2,
               "pairs": 2, "endpoint_samples": 2, "bootstrap_samples": 20}
    options.update(kwargs)
    return subject.CalibrationPlan(**options)


@pytest.fixture(scope="module")
def repeated():
    captures = []
    result = subject.run_calibration(small_plan(), on_trial=captures.append)
    return result, captures


def selected_row(summary, *, method="contrastive", target="consequence", position=0):
    return next(row for row in summary["estimates"] if row["method"] == method
                and row["target"] == target and row["decision_index"] == position)


def test_default_exploratory_plan_and_independent_budget_control():
    plan = subject.CalibrationPlan()
    assert plan.repeats == 32 and plan.max_calls == 400
    assert len(plan.mechanisms) == 10
    schedule = subject.predeclare_calibration(plan)
    assert len(schedule) == 320
    assert all(item.max_calls == (3 if item.mechanism == "budget-stop-q50" else 400)
               for item in schedule)
    protocol = subject.calibration_protocol(plan)
    assert protocol["scope"] == "exploratory_synthetic_calibration"
    assert len(protocol["evaluator_analytic_references"]) == 10
    assert protocol["planned_trials"] == 320
    assert protocol["plan"]["repeats"] == 32
    assert subject.calibration_protocol(small_plan(repeats=128))["scope"] == protocol["scope"]


def test_all_model_and_inference_rng_keys_disjoint_before_any_execution():
    plan = small_plan(mechanisms=("protective-stop-q50", "retry-pivot-q50"), repeats=5,
                      samples=3, pairs=3, samples_per_eval=2, endpoint_samples=4)
    schedule = subject.predeclare_calibration(plan)
    trial_keys = set()
    inference_keys = set()
    for item in schedule:
        reserved = [item.factual_seed]
        reserved.extend(range(item.contrastive_seed,
                              item.contrastive_seed + item.contrastive_branches))
        reserved.extend(range(item.shapley_seed, item.shapley_seed + item.shapley_branches))
        assert not trial_keys.intersection(reserved)
        trial_keys.update(reserved)
        assert item.contrastive_branches == item.decision_count * plan.samples
        assert item.shapley_branches == (2 * plan.endpoint_samples
                                        + 2 * plan.pairs * (item.decision_count + 1)
                                        * plan.samples_per_eval)
        assert item.permutation_seed not in inference_keys
        assert item.bootstrap_seed not in inference_keys
        inference_keys.update((item.permutation_seed, item.bootstrap_seed))
    phase_keys = {6 * key + phase for key in trial_keys for phase in range(6)}
    assert not phase_keys.intersection(inference_keys)
    assert min(inference_keys) > max(phase_keys)
    assert max(inference_keys) <= 2**31 - 1


@pytest.mark.parametrize("changes", [
    {"mechanisms": ()}, {"mechanisms": ("unknown",)},
    {"mechanisms": ("protective-stop-q50", "protective-stop-q50")},
    {"mechanisms": ["protective-stop-q50"]}, {"repeats": 0}, {"repeats": True},
    {"samples": 1}, {"pairs": 1}, {"samples_per_eval": 0}, {"endpoint_samples": 1},
    {"bootstrap_samples": 1}, {"max_calls": 0}, {"max_calls": False},
    {"confidence": 0}, {"confidence": 1}, {"confidence": float("nan")},
    {"confidence": float("inf")}, {"confidence": True}, {"seed": -1}, {"seed": True},
    {"seed": MAX_TRIAL_SEED}, {"targets": ("bad-target",)},
    {"targets": ("consequence", "consequence")}, {"targets": ["consequence"]},
])
def test_invalid_complete_plan_rejected_before_policy_calls(changes, monkeypatch):
    calls = []
    monkeypatch.setattr(subject, "run_policy_scenario", lambda *a, **k: calls.append(k))
    with pytest.raises(ValueError):
        subject.run_calibration(small_plan(**changes))
    assert not calls


def test_inference_range_also_checked_before_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(subject, "run_policy_scenario", lambda *a, **k: calls.append(k))
    # Two twenty-one-key model plans fit, but their four inference keys do not.
    with pytest.raises(ValueError, match="inference seed"):
        subject.run_calibration(small_plan(repeats=2, seed=MAX_TRIAL_SEED - 41))
    assert not calls
    # One plan exactly fits the remaining two inference keys at this boundary.
    valid = subject.predeclare_calibration(small_plan(repeats=1, seed=MAX_TRIAL_SEED - 20))
    assert valid[0].permutation_seed == 2**31 - 2
    assert valid[0].bootstrap_seed == 2**31 - 1


def test_public_plan_and_callback_types():
    with pytest.raises(TypeError, match="CalibrationPlan"):
        subject.predeclare_calibration({})
    with pytest.raises(TypeError, match="callable"):
        subject.run_calibration(small_plan(), on_trial=1)
    with pytest.raises(TypeError, match="CalibrationResult"):
        subject.analyze_calibration({})


def test_real_repeated_captures_and_methods_have_exact_actual_cost(repeated):
    result, raw = repeated
    assert len(raw) == len(result.trials) == 2
    assert all(isinstance(trial, subject.CompactCalibrationTrial) for trial in result.trials)
    for compact, trial in zip(result.trials, raw):
        assert trial.factual is not trial.shapley_factual
        assert trial.factual.trace.to_json() == trial.shapley_factual.trace.to_json()
        assert trial.contrastive_factual_calls == trial.shapley_factual_calls == 2
        assert trial.contrastive.initial_calls == trial.shapley.initial_calls == 2
        assert trial.contrastive_calls == sum(branch.replay.policy_calls
                                               for branch in trial.contrastive.branches)
        assert trial.shapley_calls == sum(branch.replay.policy_calls
                                          for branch in trial.shapley.branches)
        assert trial.contrastive_calls == trial.contrastive.calls
        assert trial.shapley_calls == trial.shapley.calls
        assert trial.policy_calls == 4 + trial.contrastive_calls + trial.shapley_calls
        assert compact.policy_calls == trial.policy_calls
        assert len(compact.contrastive["branches"]) == compact.seed_plan.contrastive_branches
        assert len(compact.shapley["branches"]) == compact.seed_plan.shapley_branches
        assert compact.contrastive["method_record"] == trial.contrastive.method_record()
        assert compact.shapley["method_record"] == trial.shapley.method_record()
        for method in ("contrastive", "shapley"):
            record = compact.factual[method]
            episode = trial.factual if method == "contrastive" else trial.shapley_factual
            encoded = json.dumps(episode.trace.to_dict(), sort_keys=True, separators=(",", ":"),
                                 allow_nan=False, ensure_ascii=True).encode("utf-8")
            assert record["trace_sha256"] == hashlib.sha256(encoded).hexdigest()
            assert Trace.from_json(encoded.decode()).action == episode.trace.action
    summary = result.summary()
    assert summary["planned_trials"] == summary["retained_trials"] == 2
    assert summary["paired_factual_disagreements"] == summary["factual_failures"] == 0
    assert summary["actual_policy_calls"]["total"] == sum(trial.policy_calls for trial in raw)


def test_budget_control_retains_partial_failures_and_all_unstarted_slots():
    raw = []
    result = subject.run_calibration(small_plan(mechanisms=("budget-stop-q50",), repeats=1),
                                    on_trial=raw.append)
    trial = raw[0]
    assert trial.policy_calls == result.trials[0].policy_calls == 6
    assert trial.contrastive_factual_calls == trial.shapley_factual_calls == 2
    assert trial.contrastive_calls == trial.shapley_calls == 1
    for method in ("contrastive", "shapley"):
        replayed = getattr(trial, method)
        assert replayed.initial_calls == 2 and replayed.max_calls == 3
        assert replayed.budget_exhausted and replayed.calls == 1
        assert len(replayed.branches) == 1 and replayed.branches[0].replay.episode is None
        compact = getattr(result.trials[0], method)
        assert compact["branches"][0]["status"] == "failed"
        assert compact["branches"][0]["target_values"] is None
        assert all(branch["status"] == "unstarted" for branch in compact["branches"][1:])
        assert all(entry["status"] == "refused" for entry in compact["results"])
    summary = result.summary()
    assert summary["actual_policy_calls"] == {"factual": 4, "contrastive": 1,
                                              "shapley": 1, "total": 6}
    assert all(row["refusal_rate"]["rate"] == 1 for row in summary["estimates"])
    assert all(row["interval_coverage"]["denominator"] == 0 for row in summary["estimates"])
    assert all(row["interval_coverage_including_refusals"]["denominator"] == 1
               for row in summary["estimates"])
    assert summary["branches"][0]["status_counts"] == {"completed": 0, "invalid": 0,
                                                        "failed": 1, "unstarted": 3}


def test_failed_factuals_still_retain_both_methods_and_all_trial_denominators():
    result = subject.run_calibration(small_plan(repeats=2, max_calls=1))
    assert len(result.trials) == 2
    for trial in result.trials:
        assert trial.contrastive is trial.shapley is None
        assert trial.factual_calls == 2 and trial.policy_calls == 2
        assert [error.operation for error in trial.errors] == ["contrastive_factual", "shapley_factual"]
        assert all(record["status"] == "failed" and record["trace_sha256"] is None
                   for record in trial.factual.values())
    summary = result.summary()
    assert summary["factual_failures"] == 4
    assert summary["actual_policy_calls"]["total"] == 4
    assert all(row["refusal_reason_counts"] == {"factual_failure": 2}
               for row in summary["estimates"])


def test_one_method_preflight_failure_does_not_skip_other_or_redraw(monkeypatch):
    real = subject.shapley_decisions
    invocations = []

    def failing_contrastive(*args, **kwargs):
        invocations.append(kwargs["seed"])
        raise ValueError("Deliberate estimator preflight refusal")

    monkeypatch.setattr(subject, "contrastive_decisions", failing_contrastive)
    result = subject.run_calibration(small_plan())
    assert len(invocations) == len(result.trials) == 2
    assert all(trial.contrastive is None and trial.shapley is not None for trial in result.trials)
    assert all(trial.contrastive_calls == 0 and trial.shapley_calls > 0 for trial in result.trials)
    assert subject.shapley_decisions is real
    assert selected_row(result.summary())["refusal_reason_counts"] == {"method_failure": 2}


def test_callback_failures_are_export_failures_not_complete_calibration():
    received = []

    def failing(trial):
        received.append(trial.seed_plan.index)
        raise RuntimeError("Cannot save research evidence")

    with pytest.raises(RuntimeError, match="save research evidence"):
        subject.run_calibration(small_plan(), on_trial=failing)
    assert received == [0]


def test_unknown_target_evidence_keeps_other_targets_separate():
    result = subject.run_calibration(small_plan(
        mechanisms=("unknown-provenance-stop-q50", "lagged-readback-stop-q50"), repeats=1,
    ))
    summary = result.summary()
    unknown_link = next(row for row in summary["estimates"]
                        if row["mechanism"] == "unknown-provenance-stop-q50"
                        and row["method"] == "contrastive"
                        and row["target"] == "action_linked_consequence")
    assert unknown_link["reference_eligible_trials"] == unknown_link["scored_estimates"] == 0
    assert unknown_link["refusal_reason_counts"] == {"unknown_factual": 1}
    assert unknown_link["bias"] is unknown_link["interval_coverage"]["rate"] is None
    state = next(row for row in summary["estimates"]
                 if row["mechanism"] == "unknown-provenance-stop-q50"
                 and row["method"] == "contrastive" and row["target"] == "consequence")
    assert state["scored_estimates"] == state["reference_eligible_trials"] == 1
    for row in summary["estimates"]:
        if row["mechanism"] == "lagged-readback-stop-q50":
            if row["target"] == "action":
                assert row["estimated_trials"] == row["scored_estimates"] == 1
            else:
                assert row["reference_ineligible_trials"] == row["refused_trials"] == 1


def test_retry_population_game_unavailable_even_when_small_path_happens_to_complete():
    result = subject.run_calibration(small_plan(mechanisms=("retry-pivot-q90",), repeats=5))
    summary = result.summary()
    for row in summary["estimates"]:
        if row["method"] == "shapley":
            assert row["reference_ineligible_trials"] == 5
            assert row["scored_estimates"] == 0 and row["reference"] is None
            assert row["interval_coverage"]["denominator"] == 0
            assert row["bias"] is row["rmse"] is None
    assert any(row["estimated_trials"] for row in summary["estimates"]
               if row["method"] == "shapley")
    assert all(row["coefficient_sum"]["reference"] is None for row in summary["endpoints"])
    branches = next(row for row in summary["branches"] if row["method"] == "shapley")
    nominal = branches["nominal_structural_path_availability"]
    assert nominal["probability"] == pytest.approx(((2 * .9 + .9**2) / 3) ** 2)
    for trial, conditional in zip(result.trials, nominal["given_permutations"]):
        exponent = sum(abs(order.index(1) - order.index(2))
                       for order in trial.shapley["permutations"])
        assert conditional == pytest.approx(.9**exponent)


def test_analyzer_rejects_dropped_reordered_or_duplicate_trials(repeated):
    result, _ = repeated
    for trials in (result.trials[:1], result.trials[::-1], (result.trials[0], result.trials[0])):
        with pytest.raises(ValueError, match="every trial"):
            replace(result, trials=trials).summary()


def changed_contrastive(trial, value, interval, *, status="estimated"):
    record = deepcopy(trial.contrastive)
    entry = next(row for row in record["results"] if row["target"] == "consequence"
                 and row["decision_index"] == 0)
    entry.update(effect=value, confidence_interval=interval, status=status)
    if status == "refused":
        entry.update(effect=None, confidence_interval=None, unknown_samples=2)
    return replace(trial, contrastive=record)


def test_scoring_bias_rmse_mcse_have_independent_arithmetic_oracle(repeated):
    result, _ = repeated
    # Deliberate scorer inputs, not substituted simulator outcomes or evidence.
    modified = replace(result, trials=(changed_contrastive(result.trials[0], .25, (.1, .4)),
                                      changed_contrastive(result.trials[1], .75, (.6, .9))))
    row = selected_row(modified.summary())
    assert row["reference"] == .5
    assert row["scored_estimates"] == row["available_estimates"] == 2
    assert row["bias"] == 0 and row["bias_mcse"] == pytest.approx(.25)
    assert row["rmse"] == .25 and row["rmse_mcse"] == 0
    assert row["interval_coverage"]["numerator"] == 0
    assert row["interval_coverage"]["denominator"] == 2
    assert row["availability_rate"]["rate"] == 1


def test_score_denominators_distinguish_available_coverage_from_all_planned_composite(repeated):
    result, _ = repeated
    modified = replace(result, trials=(changed_contrastive(result.trials[0], .5, (.5, .5)),
                                      changed_contrastive(result.trials[1], None, None, status="refused")))
    row = selected_row(modified.summary())
    assert row["refused_trials"] == row["scored_estimates"] == row["eligible_unscored_trials"] == 1
    assert row["interval_coverage"]["rate"] == 1
    assert row["interval_coverage"]["denominator"] == 1
    assert row["interval_coverage_including_refusals"]["rate"] == .5
    assert row["availability_rate"]["rate"] == .5
    assert row["refusal_reason_counts"] == {"unknown": 1}
    assert row["rmse_mcse"] is None


def test_zero_error_rmse_delta_mcse_is_unavailable(repeated):
    result, _ = repeated
    modified = replace(result, trials=tuple(changed_contrastive(trial, .5, (.5, .5))
                                           for trial in result.trials))
    row = selected_row(modified.summary())
    assert row["rmse"] == row["bias_mcse"] == 0
    assert row["rmse_mcse"] is None


def test_degenerate_interval_availability_does_not_require_analytic_truth():
    metrics = subject._numeric_metrics([(0., (0., 0.)), (.1, (-.2, .4))], None, .95)
    assert metrics["scored_estimates"] == metrics["interval_coverage"]["denominator"] == 0
    assert metrics["available_intervals"] == 2 and metrics["degenerate_intervals"] == 1
    assert metrics["degenerate_interval_rate"]["rate"] == .5


@pytest.mark.parametrize("successes,trials,expected", [
    (0, 1, (0., .7934506856227626)), (1, 1, (.20654931437723745, 1.)),
    (5, 10, (.236593090512564, .763406909487436)),
    (95, 100, (.8882495307680809, .9784563208456321)),
])
def test_wilson_rates_against_independent_standard_quantiles(successes, trials, expected):
    rate = subject.wilson_rate(successes, trials)
    assert rate["rate"] == successes / trials
    assert rate["confidence_interval"] == pytest.approx(expected)


def test_empty_denominator_not_zero_rate_and_extreme_confidence_finite():
    assert subject.wilson_rate(0, 0)["rate"] is None
    assert subject.wilson_rate(0, 0)["confidence_interval"] is None
    rate = subject.wilson_rate(1, 2, math.nextafter(1., 0.))
    assert all(math.isfinite(value) and 0 <= value <= 1 for value in rate["confidence_interval"])
    for args in ((-1, 1), (2, 1), (True, 1), (1, True), (0, -1), (0, 1, True),
                 (0, 1, float("inf")), (0, 1, 1)):
        with pytest.raises(ValueError):
            subject.wilson_rate(*args)


def test_outcome_truth_never_enter_production_estimators(monkeypatch):
    mechanism = get_calibration_mechanism("protective-stop-q50")
    reference_method = type(mechanism).analytic_reference

    def poisoned_reference(self):
        raise AssertionError("External scoring truth was read during execution")

    monkeypatch.setattr(type(mechanism), "analytic_reference", poisoned_reference)
    result = subject.run_calibration(small_plan(repeats=1))
    assert result.trials[0].contrastive is not None and result.trials[0].shapley is not None
    monkeypatch.setattr(type(mechanism), "analytic_reference", reference_method)
    assert result.summary()["retained_trials"] == 1


def test_compact_receipts_are_json_portable_and_do_not_retain_full_episodes(repeated):
    result, _ = repeated
    records = [trial.to_dict() for trial in result.trials]
    encoded = json.dumps(records, allow_nan=False)
    decoded = json.loads(encoded)
    assert len(decoded) == 2
    for trial in result.trials:
        assert isinstance(trial.factual, dict)
        assert all("trace" not in branch and "episode" not in branch
                   for method in (trial.contrastive, trial.shapley) for branch in method["branches"])
    original = result.trials[0].contrastive["results"][0]["status"]
    records[0]["contrastive"]["results"][0]["status"] = "changed"
    assert result.trials[0].contrastive["results"][0]["status"] == original
