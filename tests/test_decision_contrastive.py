"""Decision suffix effects use one factual baseline and retain incomplete draws.

The planted policy below depends only on its public request and seed. It makes
the second factual decision pivotal without changing policy implementations
between the recorded episode and any continuation.
"""

from copy import deepcopy
from dataclasses import replace
import json
import random

import pytest

from consequa_x.models import thaw
from consequa_x.benchmark.decision_contrastive import contrastive_decisions
from consequa_x.benchmark.evaluation import BudgetedPolicy
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from consequa_x.benchmark.runner import RefundContext, ScenarioConfig, run_scenario
from consequa_x.benchmark.templates import DEFAULT_REFUND_TEMPLATE, REFUND_TASK_TEMPLATES
from consequa_x.models import EventType, VerificationStatus
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply, ScriptedRefundPolicy


class SeedRetryPolicy(ScriptedRefundPolicy):
    """Only phase seed 1 retries; every fresh suffix otherwise stops safely."""

    def __init__(self, *, fail_seeds=(), invalid_seeds=(), stop_selection=False,
                 mixed_retries=False):
        self.requests = []
        self.fail_seeds = set(fail_seeds)
        self.invalid_seeds = set(invalid_seeds)
        self.stop_selection = stop_selection
        self.mixed_retries = mixed_retries

    @property
    def metadata(self):
        return {"provider": "test-fixture", "policy": "seed-retry", "version": "1"}

    def decide(self, request, *, seed):
        self.requests.append((deepcopy(request), seed))
        if seed in self.fail_seeds:
            raise PolicyError("Deliberate fixture provider failure")
        if seed in self.invalid_seeds:
            operation = "retry" if request.stage == "select" else "refund"
            return PolicyReply(PolicyDecision(operation), {"seed": seed})
        if request.stage == "select":
            operation = "stop" if self.stop_selection and seed >= 600 else "refund"
        else:
            retry = seed == 1 or (
                self.mixed_retries and seed % 6 == 1 and seed // 6 % 3 == 0
            )
            operation = "retry" if retry and request.attempts_remaining else "stop"
        return PolicyReply(PolicyDecision(operation), {"seed": seed})


def recorded(*, policy=None, config=None, seed=0, policy_seed=None,
             template=DEFAULT_REFUND_TEMPLATE):
    return run_policy_scenario(
        config or ScenarioConfig("planted-duplicate", Fault.CLEAN, use_idempotency=False),
        policy or SeedRetryPolicy(), seed=seed, policy_seed=policy_seed,
        max_attempts=2, template=template,
    )


def decision_events(episode):
    return tuple(event for event in episode.trace.events
                 if event.type is EventType.AGENT_DECISION)


def estimate(result, index, target="consequence"):
    return next(item for item in result.results
                if item.decision_index == index and item.target == target)


def locus(result, target="consequence"):
    return next(item for item in result.loci if item.target == target)


def analyze(original=None, policy=None, **kwargs):
    return contrastive_decisions(
        original or recorded(), BudgetedPolicy(policy or SeedRetryPolicy(), 100),
        samples=kwargs.pop("samples", 2), seed=kwargs.pop("seed", 100),
        bootstrap_samples=kwargs.pop("bootstrap_samples", 200),
        interval_method=kwargs.pop("interval_method", "percentile_bootstrap"), **kwargs,
    )


def test_stateless_planted_middle_decision_is_latest_statistical_rescue():
    original = recorded()
    original_json = original.trace.to_json()
    policy = SeedRetryPolicy()
    result = analyze(original, policy)
    events = decision_events(original)
    assert len(events) == 3
    assert original.trace.verifications[-1].status is VerificationStatus.VIOLATED
    assert result.factual == original and result.targets == ("consequence",)
    assert result.planned_seeds == ((100, 101), (102, 103), (104, 105))
    assert result.samples_per_decision == 2 and result.planned_branches == 6
    assert result.calls == len(policy.requests) == 8 and result.max_calls == 100
    assert not result.budget_exhausted
    assert [(branch.index, branch.decision_index, branch.continuation_seed)
            for branch in result.branches] == [
        (0, 0, 100), (1, 0, 101), (2, 1, 102),
        (3, 1, 103), (4, 2, 104), (5, 2, 105),
    ]
    for index, expected_effect in enumerate((-1.0, -1.0, 0.0)):
        item = estimate(result, index)
        assert item.event_id == events[index].id and item.status == "estimated"
        assert item.factual_bad is True and item.effect == expected_effect
        assert item.changed_bad_rate == expected_effect + 1
        assert item.confidence_interval == (expected_effect, expected_effect)
        assert item.known_samples == 2
        assert item.unknown_samples == item.failed_samples == item.unstarted_samples == 0
        assert item.seeds == result.planned_seeds[index]
        assert item.significant_rescue is (index < 2)
        assert item.interval_degenerate is True and item.reason is None
    found = locus(result)
    assert found.status == "identified" and found.decision_index == 1
    assert found.event_id == events[1].id
    for branch in result.branches:
        assert branch.replay.hold_count == branch.decision_index
        assert branch.replay.episode.trace.action == original.trace.action
        assert branch.replay.episode.seed == original.seed
    assert original.trace.to_json() == original_json


def test_early_selection_stop_keeps_the_consequence_target_and_action_effect():
    result = analyze(policy=SeedRetryPolicy(stop_selection=True),
                     targets=("action", "consequence"))
    for branch in result.branches[:2]:
        assert not branch.replay.episode.action_selected
        assert branch.replay.episode.trace.responses == ()
        assert branch.replay.episode.trace.verifications[-1].status is VerificationStatus.VIOLATED
        assert branch.replay.unreached_factual_indices == (1, 2)
    action = estimate(result, 0, "action")
    assert action.factual_bad is False and action.changed_bad_rate == action.effect == 1
    assert action.significant_rescue is False
    assert locus(result, "action").status == "no_rescue"
    assert estimate(result, 0).effect == 0
    assert locus(result).decision_index == 1


def test_factual_success_and_unchanged_suffixes_have_no_rescue():
    original = recorded(config=ScenarioConfig("clean-idempotent", Fault.CLEAN))
    result = analyze(original, targets=("action", "consequence", "action_linked_consequence"))
    assert original.trace.verifications[-1].status is VerificationStatus.SATISFIED
    assert result.calls == 8
    for item in result.results:
        assert item.status == "estimated" and item.factual_bad is False
        assert item.effect == 0 and item.confidence_interval == (0.0, 0.0)
        assert item.significant_rescue is False
    for found in result.loci:
        assert found.status == "no_rescue" and found.decision_index is None
        assert found.event_id is None


def test_unknown_provenance_refuses_linked_target_but_keeps_known_state():
    original = recorded(config=ScenarioConfig("missing-origin", Fault.CLEAN,
                                            include_provenance=False))
    policy = SeedRetryPolicy()
    result = analyze(original, policy,
                     targets=("action", "consequence", "action_linked_consequence"))
    assert result.calls == len(policy.requests) == 8
    for index in range(3):
        assert estimate(result, index, "action").status == "estimated"
        assert estimate(result, index).status == "estimated"
        linked = estimate(result, index, "action_linked_consequence")
        assert linked.status == "refused" and linked.factual_bad is None
        assert linked.unknown_samples == 2 and linked.known_samples == 0
        assert linked.failed_samples == linked.unstarted_samples == 0
        assert linked.changed_bad_rate is linked.effect is linked.confidence_interval is None
        assert linked.significant_rescue is None and linked.interval_degenerate is None
        assert linked.reason
    assert locus(result, "action_linked_consequence").status == "refused"
    assert locus(result).status == "no_rescue"


def test_unknown_factual_state_does_not_skip_shared_branch_collection():
    original = recorded(config=ScenarioConfig("unseen-readback", Fault.CLEAN, read_lag_ms=400))
    policy = SeedRetryPolicy()
    result = analyze(original, policy, targets=("action", "consequence"))
    assert original.trace.verifications[-1].status is VerificationStatus.UNKNOWN
    assert result.calls == len(policy.requests) == 8 and len(result.branches) == 6
    for index in range(3):
        unknown = estimate(result, index)
        assert unknown.status == "refused" and unknown.factual_bad is None
        assert unknown.unknown_samples == 2
        assert estimate(result, index, "action").status == "estimated"
    assert locus(result).status == "refused"


def test_known_factual_linked_violation_still_refuses_unknown_safe_suffixes():
    original = recorded(config=ScenarioConfig("duplicate-with-missing-origin", Fault.CLEAN,
                                            include_provenance=False, use_idempotency=False))
    result = analyze(original, targets=("consequence", "action_linked_consequence"))
    assert original.trace.verifications[-1].status is VerificationStatus.VIOLATED
    for index in (0, 1):
        state = estimate(result, index)
        linked = estimate(result, index, "action_linked_consequence")
        assert state.status == "estimated" and state.significant_rescue is True
        assert linked.factual_bad is True
        assert linked.status == "refused" and linked.unknown_samples == 2
        assert linked.known_samples == linked.failed_samples == linked.unstarted_samples == 0
        assert linked.effect is linked.confidence_interval is linked.significant_rescue is None
    assert estimate(result, 2, "action_linked_consequence").status == "estimated"
    assert locus(result).decision_index == 1
    assert locus(result, "action_linked_consequence").status == "refused"


@pytest.mark.parametrize("max_calls,expected_calls,counts", [
    (6, 3, [(1, 0, 1, 0), (0, 0, 0, 2), (0, 0, 0, 2)]),
    (8, 5, [(2, 0, 0, 0), (1, 0, 0, 1), (0, 0, 0, 2)]),
])
def test_shared_factual_call_budget_retains_partial_failure_and_unstarted_rows(
    max_calls, expected_calls, counts,
):
    policy = SeedRetryPolicy()
    bounded = BudgetedPolicy(policy, max_calls)
    original = recorded(policy=bounded)
    assert bounded.calls == 3
    result = contrastive_decisions(original, bounded, samples=2, seed=100,
                                   bootstrap_samples=200)
    assert result.calls == expected_calls and bounded.calls == max_calls
    assert len(policy.requests) == 3 + result.calls
    assert result.max_calls == max_calls and result.budget_exhausted
    assert result.planned_branches == 6
    for index, expected in enumerate(counts):
        item = estimate(result, index)
        assert (item.known_samples, item.unknown_samples, item.failed_samples,
                item.unstarted_samples) == expected
        assert sum(expected) == result.samples_per_decision
        assert item.seeds == result.planned_seeds[index]
        if expected[2] or expected[3]:
            assert item.status == "refused" and item.effect is None
    found = locus(result)
    assert found.status == "refused" and found.decision_index is None
    if max_calls == 6:
        failed = result.branches[-1].replay
        assert failed.episode is None and failed.error_type == "CallBudgetExceeded"
        assert failed.policy_calls == 1
        assert failed.decisions[-1].policy_calls == 0
        assert failed.decisions[-1].reply is None
    else:
        # A known earlier rescue cannot establish the latest locus when later
        # planned candidates have not been sampled.
        assert estimate(result, 0).significant_rescue is True
        assert all(branch.replay.episode is not None for branch in result.branches)


def test_exactly_sufficient_continuation_budget_is_complete():
    original = recorded()
    policy = SeedRetryPolicy()
    result = contrastive_decisions(original, BudgetedPolicy(policy, 8), samples=2, seed=100,
                                   bootstrap_samples=200)
    assert result.calls == result.max_calls == 8
    assert not result.budget_exhausted
    assert len(result.branches) == result.planned_branches == 6
    assert locus(result).status == "identified"


def test_exhausted_factual_recording_keeps_entire_plan_unstarted_without_new_calls():
    policy = SeedRetryPolicy()
    bounded = BudgetedPolicy(policy, 3)
    original = recorded(policy=bounded)
    result = contrastive_decisions(original, bounded, samples=2, seed=100,
                                   bootstrap_samples=20)
    assert result.calls == 0 and bounded.calls == len(policy.requests) == 3
    assert result.initial_calls == 3 and result.max_calls == 3
    assert result.budget_exhausted and result.branches == ()
    assert result.planned_branches == 6
    for item in result.results:
        assert item.status == "refused" and item.unstarted_samples == 2
        assert item.known_samples == item.unknown_samples == item.failed_samples == 0
    assert locus(result).status == "refused"


@pytest.mark.parametrize("failure_kind", ["provider", "protocol"])
def test_failures_retain_no_semantic_outcome_and_do_not_redraw(failure_kind):
    kwargs = {"fail_seeds" if failure_kind == "provider" else "invalid_seeds": (600,)}
    policy = SeedRetryPolicy(**kwargs)
    result = analyze(policy=policy)
    assert result.calls == len(policy.requests) == 7 and len(result.branches) == 6
    assert [branch.continuation_seed for branch in result.branches] == list(range(100, 106))
    failed = result.branches[0].replay
    assert failed.episode is None and failed.error_type == "PolicyError"
    assert failed.policy_calls == 1 and not failed.budget_exhausted
    assert failed.decisions[-1].reply is None
    item = estimate(result, 0)
    assert item.status == "refused"
    assert item.failed_samples == item.known_samples == 1
    assert item.unknown_samples == item.unstarted_samples == 0
    assert item.factual_bad is True and item.effect is None
    assert estimate(result, 1).status == estimate(result, 2).status == "estimated"
    assert locus(result).status == "refused"


def test_metadata_drift_fails_without_accepting_a_changed_policy_suffix():
    class DriftingPolicy(SeedRetryPolicy):
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
    assert len(result.branches) == 6
    assert all(branch.replay.episode is None for branch in result.branches)
    assert result.branches[0].replay.decisions[-1].reply is None
    assert all(item.status == "refused" and item.failed_samples == 2 for item in result.results)
    assert locus(result).status == "refused"


def test_nondefault_template_is_reproduced_without_identifier_leakage():
    template = REFUND_TASK_TEMPLATES["refund-support-note-v1"]
    original = recorded(template=template)
    policy = SeedRetryPolicy()
    result = analyze(original, policy, template=template)
    assert result.template == template
    assert result.policy_metadata == policy.metadata
    for request, _ in policy.requests:
        assert request.context == template.render_context(original.config.context)
        assert request.task["base_refund_policy"] == template.base_refund_policy
        public = json.dumps(request.to_dict())
        assert template.template_id not in public and template.family_id not in public
    for branch in result.branches:
        assert branch.replay.policy_metadata == result.policy_metadata


def test_multiple_targets_reuse_identical_branches_and_provider_requests():
    original = recorded()
    single_policy, all_policy = SeedRetryPolicy(), SeedRetryPolicy()
    single = analyze(original, single_policy)
    all_targets = analyze(original, all_policy,
                          targets=("action", "consequence", "action_linked_consequence"))
    assert single.calls == all_targets.calls == 8
    assert single_policy.requests == all_policy.requests
    assert single.branches == all_targets.branches
    assert tuple(item for item in all_targets.results if item.target == "consequence") == single.results
    assert len(all_targets.results) == 9 and len(all_targets.loci) == 3
    assert locus(all_targets, "action").status == "no_rescue"
    assert locus(all_targets, "action_linked_consequence").decision_index == 1


def test_evaluator_ground_truth_never_changes_estimates_or_provider_requests():
    original = recorded()
    changed = replace(original, ground_truth=({"kind": "fabricated", "refunds": 987654321},))
    first_policy, second_policy = SeedRetryPolicy(), SeedRetryPolicy()
    first = analyze(original, first_policy)
    second = analyze(changed, second_policy)
    assert original.trace == changed.trace
    assert first.results == second.results and first.loci == second.loci
    assert first_policy.requests == second_policy.requests
    assert original.ground_truth != changed.ground_truth


def test_estimation_and_summary_never_iterate_evaluator_ground_truth():
    class ForbiddenGroundTruth(tuple):
        def __iter__(self):
            raise AssertionError("Estimator read evaluator-owned ground truth")

        def __getitem__(self, key):
            raise AssertionError("Estimator read evaluator-owned ground truth")

        def __deepcopy__(self, memo):
            return self

    original = replace(recorded(), ground_truth=ForbiddenGroundTruth(({"private": True},)))
    result = analyze(original)
    assert locus(result).decision_index == 1
    assert result.summary()["completed_branches"] == 6


def test_mutable_factual_capture_is_detached_from_branch_receipts():
    original = recorded()
    before = original.trace.to_json()
    result = analyze(original)
    held = result.branches[2].replay.decisions[0]
    held.request["task"]["amount_minor"] = 123
    held.reply["metadata"]["decision_prefix_replay"]["factual_reply_metadata"]["seed"] = 999
    assert original.trace.to_json() == before


def independent_bootstrap(values, confidence, repeats, seed):
    """An oracle built from binary observations, separate from implementation."""
    generator = random.Random(seed)
    means = sorted(sum(values[generator.randrange(len(values))] for _ in values) / len(values)
                   for _ in range(repeats))

    def quantile(probability):
        fractional_index = probability * (len(means) - 1)
        low = int(fractional_index)
        high = min(low + 1, len(means) - 1)
        return means[low] + (means[high] - means[low]) * (fractional_index - low)

    return quantile((1 - confidence) / 2) - 1, quantile((1 + confidence) / 2) - 1


def test_mixed_binary_effect_intervals_match_independent_percentile_oracle():
    policy = SeedRetryPolicy(mixed_retries=True)
    result = analyze(policy=policy, samples=7, seed=100, confidence=0.8,
                     bootstrap_samples=37, bootstrap_seed=13)
    assert result.confidence == 0.8 and result.bootstrap_samples == 37
    assert result.bootstrap_seed == 13
    for index in (0, 1):
        bad_values = [int(seed % 3 == 0) for seed in result.planned_seeds[index]]
        item = estimate(result, index)
        expected_interval = independent_bootstrap(bad_values, 0.8, 37, 13)
        assert item.changed_bad_rate == sum(bad_values) / 7
        assert item.effect == sum(bad_values) / 7 - 1
        assert item.confidence_interval == pytest.approx(expected_interval)
        assert item.interval_degenerate is False
    assert estimate(result, 2).confidence_interval == (0.0, 0.0)


def test_schedule_statistics_and_receipts_are_reproducible_for_seeded_fixture():
    original = recorded()
    first = analyze(original, SeedRetryPolicy(mixed_retries=True), samples=7,
                    bootstrap_samples=37, bootstrap_seed=11)
    second = analyze(original, SeedRetryPolicy(mixed_retries=True), samples=7,
                     bootstrap_samples=37, bootstrap_seed=11)
    assert first == second and first.summary() == second.summary()


def test_valid_small_bootstrap_can_exclude_point_without_changing_the_effect():
    result = analyze(policy=SeedRetryPolicy(mixed_retries=True), samples=2, seed=102,
                     bootstrap_samples=2, bootstrap_seed=5)
    item = estimate(result, 0)
    # The draws are [False, False] and [True, False] under this seed, while the
    # recorded suffix values are [True, False]. A tiny bootstrap is imprecise,
    # but a percentile implementation must not silently clamp its interval.
    assert item.changed_bad_rate == 0.5 and item.effect == -0.5
    assert item.confidence_interval == pytest.approx((-0.9875, -0.5125))
    assert item.confidence_interval[1] < item.effect
    assert item.interval_degenerate is False


def test_summary_discloses_single_factual_baseline_and_degenerate_intervals():
    result = analyze()
    limits = result.summary()["statistical_limits"]
    text = " ".join(limits).lower()
    assert "factual" in text and ("single" in text or "one observed" in text)
    assert "multiplicity" in text
    assert "zero" in text and ("homogeneous" in text or "all-equal" in text)
    assert "variance" in text
    assert all(item.interval_degenerate for item in result.results)


@pytest.mark.parametrize("kwargs", [
    {"samples": 0}, {"samples": 1}, {"samples": -1}, {"samples": True}, {"samples": 2.0},
    {"seed": -1}, {"seed": True}, {"seed": 100.0}, {"seed": MAX_TRIAL_SEED},
    {"seed": 0},  # Overlaps the factual policy trial seed.
    {"targets": ()}, {"targets": ("consequence", "consequence")},
    {"targets": ("unsupported",)}, {"targets": "consequence"}, {"targets": (None,)},
    {"confidence": 0}, {"confidence": 1}, {"confidence": -0.1},
    {"confidence": True}, {"confidence": float("nan")},
    {"confidence": float("inf")}, {"confidence": "0.95"},
    {"bootstrap_samples": 0}, {"bootstrap_samples": 1},
    {"bootstrap_samples": True}, {"bootstrap_samples": 2.0},
    {"bootstrap_seed": -1}, {"bootstrap_seed": True}, {"bootstrap_seed": 1.0},
    {"template": None},
])
def test_argument_validation_happens_before_any_continuation_call(kwargs):
    policy = SeedRetryPolicy()
    bounded = BudgetedPolicy(policy, 100)
    arguments = {"samples": 2, "seed": 100, "bootstrap_samples": 20, **kwargs}
    with pytest.raises((TypeError, ValueError)):
        contrastive_decisions(recorded(), bounded, **arguments)
    assert bounded.calls == 0 and policy.requests == []


def test_factual_policy_seed_overlap_uses_capture_not_payment_world_seed():
    original = recorded(seed=7, policy_seed=99)
    policy = SeedRetryPolicy()
    bounded = BudgetedPolicy(policy, 20)
    with pytest.raises(ValueError):
        contrastive_decisions(original, bounded, samples=2, seed=98, bootstrap_samples=20)
    assert bounded.calls == 0 and policy.requests == []
    # This overlaps the world seed, but not the policy trial that was recorded.
    result = contrastive_decisions(original, bounded, samples=2, seed=7, bootstrap_samples=20)
    assert result.planned_seeds == ((7, 8), (9, 10))
    assert result.calls == 6


def test_full_schedule_overflow_is_preflight_even_when_budget_would_stop_early():
    policy = SeedRetryPolicy()
    bounded = BudgetedPolicy(policy, 1)
    with pytest.raises(ValueError):
        contrastive_decisions(recorded(), bounded, samples=2, seed=MAX_TRIAL_SEED - 3,
                             bootstrap_samples=20)
    assert bounded.calls == 0 and policy.requests == []


def test_full_factual_capture_is_checked_before_first_new_policy_call():
    original = recorded()
    events = list(original.trace.events)
    terminal = decision_events(original)[-1]
    data = thaw(terminal.data)
    data["policy_request"]["responses"][0]["result"]["fabricated"] = True
    events[events.index(terminal)] = replace(terminal, data=data)
    corrupted = replace(original, trace=replace(original.trace, events=tuple(events)))
    policy = SeedRetryPolicy()
    with pytest.raises(ValueError):
        analyze(corrupted, policy)
    assert policy.requests == []


def test_wrong_template_uncaptured_factual_or_unbudgeted_policy_fail_preflight():
    policy = SeedRetryPolicy()
    custom = recorded(template=REFUND_TASK_TEMPLATES["refund-support-note-v1"])
    for original in (custom, run_scenario()):
        with pytest.raises(ValueError):
            analyze(original, policy)
        assert policy.requests == []
    with pytest.raises(TypeError):
        contrastive_decisions(recorded(), policy, samples=2, seed=100, bootstrap_samples=20)
    assert policy.requests == []


def test_declared_policy_identity_mismatch_is_preflight():
    class DifferentPolicy(SeedRetryPolicy):
        @property
        def metadata(self):
            return {**super().metadata, "version": "2"}

    policy = DifferentPolicy()
    with pytest.raises(ValueError):
        analyze(policy=policy)
    assert policy.requests == []


def test_factual_early_stop_is_a_single_candidate_with_shared_targets():
    original = run_policy_scenario(
        ScenarioConfig("not-requested", Fault.CLEAN, context=RefundContext(customer_request=False)),
        ScriptedRefundPolicy(), seed=0,
    )
    policy = ScriptedRefundPolicy()
    result = contrastive_decisions(original, BudgetedPolicy(policy, 4), samples=2, seed=100,
                                   targets=("action", "consequence"), bootstrap_samples=20)
    assert len(decision_events(original)) == 1 and not original.action_selected
    assert result.planned_branches == len(result.branches) == result.calls == 2
    assert result.planned_seeds == ((100, 101),)
    assert all(item.factual_bad and item.changed_bad_rate == 1 and item.effect == 0
               for item in result.results)
    assert all(found.status == "no_rescue" for found in result.loci)
