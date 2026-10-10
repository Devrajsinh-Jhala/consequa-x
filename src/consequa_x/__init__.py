"""Evidence-aware consequence explanations for agent applications."""

__version__ = "0.1.0a1"

from .attribution import EffectEstimate, Intervention, leave_one_out, recency_attribution
from .explanation import ConsequenceExplanation, explain
from .graph import ConsequenceGraph, build_graph
from .models import (
    Action, AgentAssessment, AssessmentStatus, Event, EventType, Observation,
    OriginStatus, OutcomeContract, Trace, VerificationResult, VerificationStatus,
)
from .verification import RefundVerifier, Verifier, verify

__all__ = [
    "Action", "AgentAssessment", "AssessmentStatus", "ConsequenceExplanation",
    "ConsequenceGraph", "EffectEstimate", "Event", "EventType", "Intervention",
    "Observation", "OriginStatus", "OutcomeContract", "RefundVerifier", "Trace",
    "VerificationResult", "VerificationStatus", "Verifier", "build_graph", "explain",
    "leave_one_out", "recency_attribution", "verify",
]
