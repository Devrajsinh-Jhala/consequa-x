"""Compare what the evidence supports in two traces, action by action.

Typical uses: the same task before and after a fix, a factual run against a
replay, or two agents on one task. Actions are matched by ``action_id``. For
each matched action the comparison reports changes in the contract, the tool
responses, the agent's latest assessment, the verified state and origin, the
assessment alignment and the diagnosis codes. Comparing explanations says
nothing about why they differ.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from .errors import ConsequaTypeError
from .explanation import explain
from .models import Trace


@dataclass(frozen=True)
class ActionChange:
    action_id: str
    aspect: str
    left: object
    right: object


@dataclass(frozen=True)
class Comparison:
    left_trace_id: str
    right_trace_id: str
    only_left: tuple[str, ...]
    only_right: tuple[str, ...]
    changes: tuple[ActionChange, ...]

    @property
    def same(self) -> bool:
        """True when every action matches and no compared aspect changed."""
        return not (self.only_left or self.only_right or self.changes)

    def to_dict(self) -> dict:
        return {"left_trace_id": self.left_trace_id, "right_trace_id": self.right_trace_id,
                "same": self.same, "only_left": list(self.only_left),
                "only_right": list(self.only_right),
                "changes": [{"action_id": item.action_id, "aspect": item.aspect,
                             "left": item.left, "right": item.right} for item in self.changes]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_text(self) -> str:
        lines = [f"Comparing {self.left_trace_id} (left) with {self.right_trace_id} (right)."]
        if self.same:
            lines.append("No differences in actions, responses, assessments or verified outcomes.")
        for label, items in (("Only in left", self.only_left), ("Only in right", self.only_right)):
            if items:
                lines.append(f"{label}: {', '.join(items)}")
        for item in self.changes:
            lines.append(f"{item.action_id}: {item.aspect} {_show(item.left)} -> {_show(item.right)}")
        return "\n".join(lines)


def _show(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return "none" if value is None else str(value)


def _aspects(trace: Trace, explained) -> dict[str, dict[str, object]]:
    result = {}
    for item in explained.actions:
        action = trace.get_action(item.action_id)
        receipt = item.consequence
        result[item.action_id] = {
            "contract": action.contract.to_dict(),
            "responses": [response.status.value for response in trace.responses_for(action.action_id)],
            "assessment": item.agent_assessment.status.value if item.agent_assessment else None,
            "state": receipt.status.value if receipt else "unverified",
            "origin": receipt.origin.value if receipt else "unverified",
            "alignment": item.assessment_alignment,
            "diagnoses": list(item.codes),
        }
    return result


def compare(left: Trace, right: Trace) -> Comparison:
    """Compare two traces action by action; see the module documentation."""
    if not isinstance(left, Trace) or not isinstance(right, Trace):
        raise ConsequaTypeError("compare requires two Trace records")
    before, after = _aspects(left, explain(left)), _aspects(right, explain(right))
    changes = []
    for action_id in (item.action_id for item in left.actions):
        if action_id not in after:
            continue
        for aspect, value in before[action_id].items():
            if after[action_id][aspect] != value:
                shown = (value, after[action_id][aspect]) if aspect != "contract" else (
                    "declared", "changed")
                changes.append(ActionChange(action_id, aspect, *shown))
    return Comparison(
        left_trace_id=left.trace_id, right_trace_id=right.trace_id,
        only_left=tuple(key for key in before if key not in after),
        only_right=tuple(key for key in after if key not in before),
        changes=tuple(changes),
    )
