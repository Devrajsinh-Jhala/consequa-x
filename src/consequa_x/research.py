"""Research interfaces: replay-based attribution and policy adapters.

These support the studies behind ConseqaX (paired interventions, decision
replay, calibration). Applications that capture, verify and explain their own
agents do not need them, so they are imported from here rather than from the
top-level ``consequa_x`` namespace. The benchmark simulators live in
``consequa_x.benchmark``.
"""

from .attribution import (
    EffectEstimate, InsufficientEvidenceError, Intervention, ReplayOutcome, ReplayRunner,
    leave_one_out, recency_attribution,
)
from .policies import (
    Policy, PolicyDecision, PolicyError, PolicyReply, PolicyRequest, ScriptedRefundPolicy,
)

__all__ = [
    "EffectEstimate", "InsufficientEvidenceError", "Intervention", "Policy", "PolicyDecision",
    "PolicyError", "PolicyReply", "PolicyRequest", "ReplayOutcome", "ReplayRunner",
    "ScriptedRefundPolicy", "leave_one_out", "recency_attribution",
]
