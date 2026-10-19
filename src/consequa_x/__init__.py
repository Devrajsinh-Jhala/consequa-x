"""Evidence-aware consequence explanations for agent applications.

Research interfaces (replay attribution, policy adapters) are in
``consequa_x.research``.
"""

__version__ = "1.2.0"

from .capture import ActionCapture, Attempt, TraceRecorder, capture_tool
from .errors import (
    ConsequaError, ConsequaTypeError, ContractError, ReceiptError, RecorderError,
    SchemaVersionError, ValidationError,
)
from .explanation import CORE_DIAGNOSES, ActionExplanation, Diagnosis, TraceExplanation, explain
from .graph import ConsequenceGraph, build_graph
from .guard import RetryAdvice, RetryDecision, retry_advice
from .migrate import MigrationReport, migrate_trace
from .models import (
    Action, AgentAssessment, AssessmentStatus, Event, EventType, Evidence, Finding, FrozenDict,
    FrozenList, Observation, OriginStatus, OutcomeContract, ResponseStatus, TimeBase,
    ToolResponse, Trace, VerificationResult, VerificationStatus, thaw,
)
from .readback import apoll_readback, poll_readback
from .record_verifier import RecordVerifier
from .report import render_report
from .store import TraceStore
from .summary import Summary, summarize
from .verification import RefundVerifier, Verifier, averify, verify

__all__ = [
    # Records and statuses
    "Action", "AgentAssessment", "AssessmentStatus", "Event", "EventType", "Evidence", "Finding",
    "FrozenDict", "FrozenList", "Observation", "OriginStatus", "OutcomeContract",
    "ResponseStatus", "TimeBase", "ToolResponse", "Trace", "VerificationResult",
    "VerificationStatus", "thaw",
    # Capture
    "ActionCapture", "Attempt", "TraceRecorder", "capture_tool",
    # Verification
    "RecordVerifier", "RefundVerifier", "Verifier", "apoll_readback", "averify",
    "poll_readback", "verify",
    # Acting on evidence
    "RetryAdvice", "RetryDecision", "retry_advice",
    # Explanation and presentation
    "ActionExplanation", "CORE_DIAGNOSES", "ConsequenceGraph", "Diagnosis", "TraceExplanation",
    "build_graph", "explain", "render_report",
    # Collections of traces
    "Summary", "TraceStore", "summarize",
    # Migration
    "MigrationReport", "migrate_trace",
    # Errors
    "ConsequaError", "ConsequaTypeError", "ContractError", "ReceiptError", "RecorderError",
    "SchemaVersionError", "ValidationError",
]
