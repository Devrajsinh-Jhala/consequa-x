"""Evidence-aware consequence explanations for agent applications."""

__version__ = "1.2.0"

from .attribution import EffectEstimate, Intervention, leave_one_out, recency_attribution
from .capture import ActionCapture, Attempt, TraceRecorder, capture_tool
from .errors import (
    ConsequaError, ConsequaTypeError, ContractError, ReceiptError, RecorderError,
    SchemaVersionError, ValidationError,
)
from .explanation import ActionExplanation, TargetMatcher, TraceExplanation, explain
from .graph import ConsequenceGraph, build_graph
from .models import (
    Action, AgentAssessment, AssessmentStatus, Evidence, Event, EventType, FrozenDict,
    FrozenList, Observation,
    OriginStatus, OutcomeContract, ResponseStatus, TimeBase, ToolResponse, Trace,
    VerificationResult, VerificationStatus, thaw,
)
from .record_verifier import RecordTargetMatcher, RecordVerifier
from .policies import Policy, PolicyDecision, PolicyError, PolicyReply, PolicyRequest, ScriptedRefundPolicy
from .verification import RefundVerifier, Verifier, verify
from .report import render_report

__all__ = [
    "Action", "ActionCapture", "ActionExplanation", "AgentAssessment", "AssessmentStatus",
    "ConsequenceGraph", "EffectEstimate", "Evidence", "Event", "EventType", "Intervention",
    "Observation", "OriginStatus", "OutcomeContract", "RecordTargetMatcher", "RecordVerifier",
    "RefundVerifier", "TargetMatcher", "TimeBase", "Trace", "TraceExplanation",
    "Policy", "PolicyDecision", "PolicyError", "PolicyReply", "PolicyRequest", "ScriptedRefundPolicy",
    "ResponseStatus", "ToolResponse", "TraceRecorder", "VerificationResult", "VerificationStatus", "Verifier",
    "Attempt", "build_graph", "capture_tool", "explain",
    "FrozenDict", "FrozenList", "thaw",
    "ConsequaError", "ConsequaTypeError", "ContractError", "ReceiptError", "RecorderError",
    "SchemaVersionError", "ValidationError",
    "leave_one_out", "recency_attribution", "render_report", "verify",
]
