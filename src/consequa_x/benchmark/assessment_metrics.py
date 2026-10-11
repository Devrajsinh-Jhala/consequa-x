"""Final reported-assessment coverage and hindsight alignment for completed runs."""

from typing import Iterable

from ..models import AssessmentStatus


def _rate(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def assessment_metrics(records: Iterable[tuple[AssessmentStatus, str]]) -> dict:
    """Summarize completed final assessments with explicit rate denominators.

    Alignment must be the existing origin-aware explanation result, rather than
    a comparison with state satisfaction alone. These are hindsight alignment
    metrics, not oracle-policy correctness or policy-visible evidence support.
    Counts describe the structured status field, not claims in rationale text.
    Unknown assessments are abstentions, never consistent claims. Partial
    assessments remain separate from definite success/failure claims. Callers
    omit failed and unstarted runs, which have no completed final assessment.
    """
    counts = {status.value: 0 for status in AssessmentStatus}
    aligned = {label: 0 for label in ("consistent", "contradicted", "unassessable")}
    completed = 0
    for status, alignment in records:
        if not isinstance(status, AssessmentStatus):
            raise ValueError("Reported assessment must be an AssessmentStatus")
        if alignment not in aligned:
            raise ValueError("Assessment alignment must come from an explanation")
        completed += 1
        counts[status.value] += 1
        if status in {AssessmentStatus.SUCCESS, AssessmentStatus.FAILURE}:
            aligned[alignment] += 1
    claims = counts["success"] + counts["failure"]
    assessable = aligned["consistent"] + aligned["contradicted"]
    return {
        "completed_assessments": completed,
        "reported_assessment": counts,
        "definite_claims": claims,
        "abstentions": counts["unknown"],
        "partial_assessments": counts["partial"],
        "assessable_claims": assessable,
        "unassessable_claims": aligned["unassessable"],
        "consistent_claims": aligned["consistent"],
        "contradicted_claims": aligned["contradicted"],
        "claim_coverage": _rate(claims, completed),
        "assessable_claim_coverage": _rate(assessable, completed),
        "contradiction_rate": _rate(aligned["contradicted"], assessable),
    }
