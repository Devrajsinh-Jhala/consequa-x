"""Interval comparisons reuse real evidence, budgets and original refusals."""

from dataclasses import replace

import pytest

from consequa_x.benchmark.calibration_mechanisms import get_calibration_mechanism
from consequa_x.benchmark.decision_contrastive import contrastive_decisions, with_contrastive_interval
from consequa_x.benchmark.decision_shapley import shapley_decisions, with_shapley_intervals
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.models import Trace


def setup(name="protective-stop-q50", max_calls=400):
    mechanism = get_calibration_mechanism(name)
    policy = mechanism.make_policy()
    return mechanism.capture_factual(), BudgetedPolicy(policy, max_calls)


def test_contrastive_variants_share_every_draw_and_point_without_new_calls():
    factual, policy = setup()
    original = contrastive_decisions(factual, policy, samples=16, bootstrap_samples=200,
                                     interval_method="percentile_bootstrap",
                                     targets=("action", "consequence", "action_linked_consequence"))
    before = policy.calls
    for method in ("wilson", "clopper_pearson", "percentile_bootstrap"):
        updated = with_contrastive_interval(original, interval_method=method)
        assert updated.factual is original.factual and updated.branches is original.branches
        assert updated.planned_seeds is original.planned_seeds
        assert updated.calls == original.calls and policy.calls == before
        for old, new in zip(original.results, updated.results):
            assert old.effect == new.effect and old.changed_bad_rate == new.changed_bad_rate
            assert old.status == new.status and old.seeds == new.seeds
        assert updated.interval_method == method
        if method != "percentile_bootstrap":
            action = next(item for item in updated.results if item.target == "action")
            assert action.confidence_interval[0] == 0 < action.confidence_interval[1]
            assert updated.method_record()["bootstrap_samples"] is None
        else:
            assert updated.results == original.results and updated.loci == original.loci


@pytest.mark.parametrize("name,max_calls", [("unknown-provenance-stop-q50", 400),
                                             ("lagged-readback-stop-q50", 400),
                                             ("protective-stop-q50", 1)])
def test_contrastive_original_refusals_cannot_be_rescued_by_interval_choice(name, max_calls):
    factual, policy = setup(name, max_calls)
    original = contrastive_decisions(factual, policy, samples=2, bootstrap_samples=20,
                                     targets=("action", "consequence", "action_linked_consequence"))
    updated = with_contrastive_interval(original, interval_method="clopper_pearson")
    assert any(item.status == "refused" for item in original.results)
    for old, new in zip(original.results, updated.results):
        if old.status == "refused":
            assert old is new and new.confidence_interval is None
    assert updated.calls == original.calls


def test_changed_saved_contrastive_mean_rejects_the_comparison():
    factual, policy = setup()
    result = contrastive_decisions(factual, policy, samples=2, bootstrap_samples=20)
    altered = replace(result, results=(replace(result.results[0], changed_bad_rate=.123),
                                      *result.results[1:]))
    with pytest.raises(ValueError, match="mean changed"):
        with_contrastive_interval(altered, interval_method="clopper_pearson")


def test_shapley_variants_preserve_signed_points_pair_units_and_endpoint_discrepancy():
    factual, policy = setup()
    original = shapley_decisions(factual, policy, pairs=4, endpoint_samples=4,
                                 interval_method="normal", endpoint_interval_method="normal",
                                 targets=("action", "consequence", "action_linked_consequence"))
    before = policy.calls
    updated = with_shapley_intervals(original, interval_method="hoeffding",
                                     endpoint_interval_method="clopper_pearson_difference")
    assert updated.slots is original.slots and updated.branches is original.branches
    assert updated.permutations is original.permutations
    assert policy.calls == before and updated.calls == original.calls
    for old, new in zip(original.results, updated.results):
        assert new.shapley_value == old.shapley_value and new.pair_values == old.pair_values
        assert new.status == old.status and new.coverage == old.coverage
        assert -1 <= new.confidence_interval[0] < new.confidence_interval[1] <= 1
    for old, new in zip(original.endpoint_checks, updated.endpoint_checks):
        assert new.endpoint_difference == old.endpoint_difference
        assert new.coefficient_sum == old.coefficient_sum and new.discrepancy == old.discrepancy
        assert -1 <= new.confidence_interval[0] <= new.confidence_interval[1] <= 1
    restored = with_shapley_intervals(original, interval_method="normal", endpoint_interval_method="normal")
    assert restored.results == original.results and restored.endpoint_checks == original.endpoint_checks


@pytest.mark.parametrize("name,max_calls", [("retry-pivot-q10", 400),
                                             ("unknown-provenance-stop-q50", 400),
                                             ("lagged-readback-stop-q50", 400),
                                             ("protective-stop-q50", 1)])
def test_shapley_invalid_unknown_and_budget_refusals_stay_refused(name, max_calls):
    factual, policy = setup(name, max_calls)
    original = shapley_decisions(factual, policy, pairs=2, endpoint_samples=2,
                                 targets=("action", "consequence", "action_linked_consequence"))
    updated = with_shapley_intervals(original, interval_method="hoeffding",
                                     endpoint_interval_method="clopper_pearson_difference")
    assert any(item.status == "refused" for item in original.results)
    for old, new in zip(original.results, updated.results):
        if old.status == "refused":
            assert old is new and new.confidence_interval is None
    for old, new in zip(original.endpoint_checks, updated.endpoint_checks):
        if old.status == "refused":
            assert old is new and new.confidence_interval is None


def test_new_options_validate_before_policy_calls_and_can_run_directly():
    factual, policy = setup()
    for call in (
        lambda: contrastive_decisions(factual, policy, interval_method="missing"),
        lambda: shapley_decisions(factual, policy, interval_method="missing"),
        lambda: shapley_decisions(factual, policy, endpoint_interval_method="missing"),
    ):
        with pytest.raises(ValueError):
            call()
        assert policy.calls == 0
    result = shapley_decisions(factual, policy, pairs=2, endpoint_samples=2,
                               interval_method="hoeffding", endpoint_interval_method="clopper_pearson_difference")
    assert all(item.confidence_interval[0] < item.confidence_interval[1] for item in result.results)
    assert result.method_record()["interval_clipping"] is True


@pytest.mark.parametrize("mutation", ["point_and_pairs", "pairs_same_mean", "missing_branch",
                                      "coefficient_sum", "coverage", "game"])
def test_shapley_rescoring_rejects_stale_vectors_and_receipts(mutation):
    factual, policy = setup()
    original = shapley_decisions(factual, policy, pairs=4, endpoint_samples=4)
    altered = original
    if mutation == "point_and_pairs":
        item = replace(original.results[0], shapley_value=1., pair_values=(1.,)*4)
        altered = replace(original, results=(item, *original.results[1:]))
    elif mutation == "pairs_same_mean":
        old = original.results[0]
        values = (old.pair_values[0]+.125, old.pair_values[1]-.125, *old.pair_values[2:])
        altered = replace(original, results=(replace(old, pair_values=values), *original.results[1:]))
    elif mutation == "missing_branch":
        index = next(i for i, branch in enumerate(original.branches) if branch.slot.role == "walk")
        altered = replace(original, branches=original.branches[:index]+original.branches[index+1:])
    elif mutation == "coefficient_sum":
        altered = replace(original, endpoint_checks=(replace(original.endpoint_checks[0], coefficient_sum=9.),))
    elif mutation == "coverage":
        endpoint = original.endpoint_checks[0]
        altered = replace(original, endpoint_checks=(replace(endpoint,
            empty_coverage=replace(endpoint.empty_coverage, known=0, unknown=4)),))
    else:
        altered = replace(original, coalition_game="on_reach")
    before = policy.calls
    with pytest.raises(ValueError):
        with_shapley_intervals(altered, interval_method="hoeffding",
                              endpoint_interval_method="clopper_pearson_difference")
    assert policy.calls == before


def test_annotation_cache_preserves_value_and_type_validation_on_every_trace():
    factual, _ = setup()
    raw = factual.trace.to_dict()
    first = Trace.from_dict(raw)
    changed = factual.trace.to_dict()
    changed["assessment"]["rationale"] = "A different captured statement."
    second = Trace.from_dict(changed)
    assert first.assessment.rationale != second.assessment.rationale
    invalid = factual.trace.to_dict()
    invalid["assessment"]["time_ms"] = True
    with pytest.raises(TypeError):
        Trace.from_dict(invalid)


def test_public_defaults_preserve_uncertainty_in_constant_real_replays():
    factual, policy = setup("idempotent-stop-q50")
    contrastive = contrastive_decisions(factual, policy, samples=2)
    assert contrastive.interval_method == "clopper_pearson"
    assert all(item.effect == 0 and item.confidence_interval[0] == 0
               and item.confidence_interval[1] > 0 for item in contrastive.results)
    factual, policy = setup("idempotent-stop-q50")
    shapley = shapley_decisions(factual, policy, pairs=2, endpoint_samples=2)
    assert shapley.interval_method == "hoeffding"
    assert shapley.endpoint_interval_method == "clopper_pearson_difference"
    assert shapley.coalition_game == "strict"
    assert all(item.shapley_value == 0 and item.confidence_interval[0] < 0
               < item.confidence_interval[1] for item in shapley.results)
    assert all(item.endpoint_difference == 0 and item.confidence_interval[0] < 0
               < item.confidence_interval[1] for item in shapley.endpoint_checks)
