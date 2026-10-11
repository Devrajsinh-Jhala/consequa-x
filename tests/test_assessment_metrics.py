"""Assessment abstention and hindsight claim coverage keep their denominators."""

import pytest

from consequa_x.attribution import Intervention
from consequa_x.benchmark.assessment_metrics import assessment_metrics
from consequa_x.benchmark.evaluation import evaluate_policy
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_experiment import experiment_policy
from consequa_x.benchmark.runner import ScenarioConfig
from consequa_x.models import AssessmentStatus, OriginStatus, VerificationStatus
from consequa_x.policies import PolicyDecision, PolicyError, PolicyReply, ScriptedRefundPolicy


def rate(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


class FixedAssessmentPolicy(ScriptedRefundPolicy):
    """Select the refund, then stop with a declared final reported assessment."""

    def __init__(self, assessment):
        self.assessment = assessment

    def decide(self, request, *, seed):
        decision = (
            PolicyDecision("refund", AssessmentStatus.UNKNOWN)
            if request.stage == "select"
            else PolicyDecision("stop", self.assessment)
        )
        return PolicyReply(decision)


class BrokenPolicy(ScriptedRefundPolicy):
    def decide(self, request, *, seed):
        raise PolicyError("No completed assessment")


def test_blanket_unknown_is_abstention_with_zero_claim_coverage_not_zero_error():
    metrics = assessment_metrics((AssessmentStatus.UNKNOWN, "unassessable") for _ in range(3))
    assert metrics["completed_assessments"] == metrics["abstentions"] == 3
    assert metrics["reported_assessment"] == {
        "success": 0, "failure": 0, "partial": 0, "unknown": 3,
    }
    assert metrics["definite_claims"] == metrics["assessable_claims"] == 0
    assert metrics["unassessable_claims"] == 0
    assert metrics["claim_coverage"] == metrics["assessable_claim_coverage"] == rate(0, 3)
    assert metrics["contradiction_rate"] == rate(0, 0)


def test_empty_completed_set_has_no_abstentions_and_undefined_rates():
    metrics = assessment_metrics(iter(()))
    assert metrics["completed_assessments"] == metrics["abstentions"] == 0
    assert metrics["reported_assessment"] == {
        "success": 0, "failure": 0, "partial": 0, "unknown": 0,
    }
    for key in ("claim_coverage", "assessable_claim_coverage", "contradiction_rate"):
        assert metrics[key] == rate(0, 0)


def test_mixed_claims_count_only_assessable_definite_claims_in_contradiction_rate():
    metrics = assessment_metrics([
        (AssessmentStatus.SUCCESS, "consistent"),
        (AssessmentStatus.FAILURE, "contradicted"),
        (AssessmentStatus.FAILURE, "unassessable"),
        (AssessmentStatus.UNKNOWN, "unassessable"),
    ])
    assert metrics["reported_assessment"] == {
        "success": 1, "failure": 2, "partial": 0, "unknown": 1,
    }
    assert metrics["definite_claims"] == 3
    assert metrics["assessable_claims"] == 2
    assert metrics["consistent_claims"] == metrics["contradicted_claims"] == 1
    assert metrics["unassessable_claims"] == metrics["abstentions"] == 1
    assert metrics["claim_coverage"] == rate(3, 4)
    assert metrics["assessable_claim_coverage"] == rate(2, 4)
    assert metrics["contradiction_rate"] == rate(1, 2)


def test_evaluation_distinguishes_known_contradiction_unknown_state_and_missing_origin():
    configs = (
        ScenarioConfig("clean", Fault.CLEAN),
        ScenarioConfig("failed_commit", Fault.TIMEOUT_BEFORE_COMMIT),
        ScenarioConfig("unknown_readback", Fault.DELAYED_VISIBILITY),
        ScenarioConfig("missing_origin", Fault.CLEAN, include_provenance=False),
    )
    result = evaluate_policy(FixedAssessmentPolicy(AssessmentStatus.SUCCESS), configs, samples=1)
    summary = result.summary()
    assert summary["assessment_alignment"] == {
        "consistent": 1, "contradicted": 1, "unassessable": 2,
    }
    metrics = summary["assessment_metrics"]
    assert metrics["completed_assessments"] == metrics["definite_claims"] == 4
    assert metrics["reported_assessment"] == {
        "success": 4, "failure": 0, "partial": 0, "unknown": 0,
    }
    assert metrics["assessable_claims"] == metrics["unassessable_claims"] == 2
    assert metrics["claim_coverage"] == rate(4, 4)
    assert metrics["assessable_claim_coverage"] == rate(2, 4)
    assert metrics["contradiction_rate"] == rate(1, 2)
    assert result.samples[2].episode.trace.verifications[-1].status is VerificationStatus.UNKNOWN
    assert result.samples[3].episode.trace.verifications[-1].origin is OriginStatus.UNKNOWN


@pytest.mark.parametrize("assessment", [AssessmentStatus.SUCCESS, AssessmentStatus.FAILURE])
def test_other_actor_state_satisfaction_does_not_establish_agent_claim_alignment(assessment):
    config = ScenarioConfig("other_actor", Fault.TIMEOUT_BEFORE_COMMIT, external_actor=True)
    result = evaluate_policy(FixedAssessmentPolicy(assessment), (config,), samples=1)
    verification = result.samples[0].episode.trace.verifications[-1]
    assert verification.status is VerificationStatus.SATISFIED
    assert verification.origin is OriginStatus.OTHER_ACTOR
    metrics = result.summary()["assessment_metrics"]
    assert metrics["definite_claims"] == metrics["unassessable_claims"] == 1
    assert metrics["assessable_claims"] == metrics["contradicted_claims"] == 0
    assert metrics["claim_coverage"] == rate(1, 1)
    assert metrics["assessable_claim_coverage"] == rate(0, 1)
    assert metrics["contradiction_rate"] == rate(0, 0)


def test_known_world_outcomes_do_not_turn_unknown_assessments_into_consistent_claims():
    result = evaluate_policy(
        FixedAssessmentPolicy(AssessmentStatus.UNKNOWN),
        (ScenarioConfig("clean", Fault.CLEAN),
         ScenarioConfig("failed_commit", Fault.TIMEOUT_BEFORE_COMMIT)),
        samples=1,
    )
    summary = result.summary()
    assert summary["verification"] == {"satisfied": 1, "violated": 1, "unknown": 0}
    assert summary["assessment_alignment"] == {
        "consistent": 0, "contradicted": 0, "unassessable": 2,
    }
    metrics = summary["assessment_metrics"]
    assert metrics["abstentions"] == 2
    assert metrics["consistent_claims"] == metrics["definite_claims"] == 0
    assert metrics["contradiction_rate"] == rate(0, 0)


def test_replay_uses_the_same_completed_assessment_metrics_for_all_branches():
    result = experiment_policy(
        FixedAssessmentPolicy(AssessmentStatus.UNKNOWN), ScenarioConfig("clean", Fault.CLEAN),
        (Intervention("distractor"),), samples=2,
    )
    summary = result.summary()
    assert summary["completed_branches"] == 4
    metrics = summary["assessment_metrics"]
    assert metrics["completed_assessments"] == metrics["abstentions"] == 4
    assert metrics["reported_assessment"] == {
        "success": 0, "failure": 0, "partial": 0, "unknown": 4,
    }
    assert metrics["claim_coverage"] == rate(0, 4)
    assert metrics["contradiction_rate"] == rate(0, 0)


@pytest.mark.parametrize("kind", ["evaluation", "replay"])
def test_all_failed_completed_schedule_has_no_assessments(kind):
    config = ScenarioConfig("clean", Fault.CLEAN)
    if kind == "evaluation":
        result = evaluate_policy(BrokenPolicy(), (config,), samples=2)
        failed_key, unstarted_key = "failed_samples", "not_started_samples"
        failed = 2
    else:
        result = experiment_policy(BrokenPolicy(), config, (Intervention("distractor"),), samples=2)
        failed_key, unstarted_key = "failed_branches", "not_started_branches"
        failed = 4
    summary = result.summary()
    assert summary[failed_key] == failed
    assert summary[unstarted_key] == 0
    assert not summary["budget_exhausted"]
    assert summary["assessment_metrics"] == assessment_metrics(())


@pytest.mark.parametrize("kind", ["evaluation", "replay"])
def test_failed_and_unstarted_runs_are_never_assessment_abstentions(kind):
    config = ScenarioConfig("clean", Fault.CLEAN)
    if kind == "evaluation":
        result = evaluate_policy(BrokenPolicy(), (config,), samples=2, max_calls=1)
        completed_key, failed_key, unstarted_key = (
            "completed_samples", "failed_samples", "not_started_samples",
        )
    else:
        result = experiment_policy(BrokenPolicy(), config, (Intervention("distractor"),),
                                   samples=2, max_calls=1)
        completed_key, failed_key, unstarted_key = (
            "completed_branches", "failed_branches", "not_started_branches",
        )
    summary = result.summary()
    assert summary[completed_key] == 0
    assert summary[failed_key] == 1
    assert summary[unstarted_key] > 0
    assert summary["assessment_metrics"] == assessment_metrics(())


@pytest.mark.parametrize("kind", ["evaluation", "replay"])
def test_partial_failure_leaves_completed_assessment_denominator_unchanged(kind):
    config = ScenarioConfig("clean", Fault.CLEAN)
    if kind == "evaluation":
        result = evaluate_policy(ScriptedRefundPolicy(), (config,), samples=3, max_calls=3)
    else:
        result = experiment_policy(ScriptedRefundPolicy(), config, (Intervention("distractor"),),
                                   samples=2, max_calls=3)
    metrics = result.summary()["assessment_metrics"]
    assert metrics["completed_assessments"] == metrics["definite_claims"] == 1
    assert metrics["reported_assessment"] == {
        "success": 1, "failure": 0, "partial": 0, "unknown": 0,
    }
    assert metrics["abstentions"] == 0
    assert metrics["claim_coverage"] == metrics["assessable_claim_coverage"] == rate(1, 1)
    assert metrics["contradiction_rate"] == rate(0, 1)


@pytest.mark.parametrize("kind", ["evaluation", "replay"])
def test_partial_assessment_is_preserved_without_becoming_abstention_or_definite_claim(kind):
    config = ScenarioConfig("partial", Fault.PARTIAL_EFFECT)
    policy = FixedAssessmentPolicy(AssessmentStatus.PARTIAL)
    if kind == "evaluation":
        result = evaluate_policy(policy, (config,), samples=1)
        completed = 1
    else:
        result = experiment_policy(policy, config, (Intervention("distractor"),), samples=2)
        completed = 4
    metrics = result.summary()["assessment_metrics"]
    assert metrics["completed_assessments"] == metrics["partial_assessments"] == completed
    assert metrics["reported_assessment"] == {
        "success": 0, "failure": 0, "partial": completed, "unknown": 0,
    }
    assert metrics["abstentions"] == metrics["definite_claims"] == 0
    assert metrics["assessable_claims"] == metrics["unassessable_claims"] == 0
    assert metrics["claim_coverage"] == rate(0, completed)
    assert metrics["contradiction_rate"] == rate(0, 0)
