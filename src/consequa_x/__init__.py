"""Evidence-aware consequence explanations for agent applications."""

__version__ = "1.1.0"

from .attribution import EffectEstimate, Intervention, leave_one_out, recency_attribution
from .explanation import ConsequenceExplanation, TargetMatcher, explain
from .graph import ConsequenceGraph, build_graph
from .models import (
    Action, AgentAssessment, AssessmentStatus, Evidence, Event, EventType, Observation,
    OriginStatus, OutcomeContract, ResponseStatus, ToolResponse, Trace,
    VerificationResult, VerificationStatus,
)
from .policies import Policy, PolicyDecision, PolicyError, PolicyReply, PolicyRequest, ScriptedRefundPolicy
from .verification import RefundVerifier, Verifier, verify
from .report import render_report

__all__ = [
    "Action", "AgentAssessment", "AssessmentStatus", "ConsequenceExplanation",
    "ConsequenceGraph", "EffectEstimate", "Evidence", "Event", "EventType", "Intervention",
    "Observation", "OriginStatus", "OutcomeContract", "RefundVerifier", "TargetMatcher", "Trace",
    "Policy", "PolicyDecision", "PolicyError", "PolicyReply", "PolicyRequest", "ScriptedRefundPolicy",
    "ResponseStatus", "ToolResponse", "VerificationResult", "VerificationStatus", "Verifier",
    "build_graph", "explain",
    "leave_one_out", "recency_attribution", "render_report", "verify",
]
