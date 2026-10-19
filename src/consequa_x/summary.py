"""Counts across many traces: what was verified, what diverged, what stayed unknown.

``summarize`` explains every action in every trace and counts the results. All
counts are over actions, and the denominator is always stated: unknown and
unverified outcomes are categories of their own, never folded into failures or
successes. Output formats: plain text, Markdown (for issues and CI comments) and
JSON.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from typing import Iterable

from .errors import ConsequaTypeError
from .explanation import explain
from .models import Trace


# Codes that call for attention: the record contradicts what was reported or expected.
ATTENTION = ("ASSESSMENT_DIVERGENCE", "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE",
             "RESPONSE_EFFECT_DIVERGENCE", "CONSEQUENCE_VIOLATION", "EXTERNAL_ACTOR_EFFECT",
             "EXCESS_EFFECTS", "DUPLICATE_EFFECT", "PARAMETER_MISMATCH", "PARTIAL_EFFECT",
             "REVERSED_EFFECT", "REMOVED_EFFECT")


@dataclass(frozen=True)
class Flagged:
    """One action whose diagnoses call for attention."""

    trace_id: str
    action_id: str
    codes: tuple[str, ...]


@dataclass(frozen=True)
class Summary:
    """Counts over every action of every summarized trace."""

    traces: int
    actions: int
    state: dict[str, int]
    origin: dict[str, int]
    alignment: dict[str, int]
    responses: dict[str, int]
    diagnoses: dict[str, int]
    flagged: tuple[Flagged, ...] = field(default=())

    def to_dict(self) -> dict:
        return {"traces": self.traces, "actions": self.actions, "state": dict(self.state),
                "origin": dict(self.origin), "alignment": dict(self.alignment),
                "responses": dict(self.responses), "diagnoses": dict(self.diagnoses),
                "flagged": [{"trace_id": item.trace_id, "action_id": item.action_id,
                             "codes": list(item.codes)} for item in self.flagged]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    def _rows(self) -> list[tuple[str, dict[str, int]]]:
        return [("Verified state", self.state), ("Effect origin", self.origin),
                ("Assessment alignment", self.alignment)]

    def to_text(self) -> str:
        lines = [f"{self.traces} traces, {self.actions} actions."]
        for title, counts in self._rows():
            lines.append(f"{title} (of {self.actions} actions): " + _counts(counts))
        total = sum(self.responses.values())
        lines.append(f"Tool responses (of {total}): " + _counts(self.responses))
        lines.append(f"Diagnoses (actions with each code, of {self.actions}): "
                     + _counts(self.diagnoses))
        if self.flagged:
            lines.append(f"Needs attention ({len(self.flagged)} actions):")
            lines.extend(f"  {item.trace_id} / {item.action_id}: {', '.join(item.codes)}"
                         for item in self.flagged)
        else:
            lines.append("Needs attention: none.")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [f"**{self.traces} traces, {self.actions} actions.** Counts are over actions; "
                 "`unknown` and `unverified` are kept separate from failures.", ""]
        lines += ["| Measure | Value | Actions |", "| --- | --- | ---: |"]
        for title, counts in self._rows() + [("Diagnosis", self.diagnoses)]:
            for value, count in counts.items():
                lines.append(f"| {title} | `{value}` | {count} |")
        total = sum(self.responses.values())
        lines += ["", f"Tool responses ({total}): " + _counts(self.responses, code=True), ""]
        if self.flagged:
            lines += [f"**Needs attention ({len(self.flagged)} actions)**", "",
                      "| Trace | Action | Diagnoses |", "| --- | --- | --- |"]
            lines += [f"| `{_cell(item.trace_id)}` | `{_cell(item.action_id)}` | "
                      + " ".join(f"`{code}`" for code in item.codes) + " |"
                      for item in self.flagged]
        else:
            lines.append("Needs attention: none.")
        return "\n".join(lines)


def _counts(counts: dict[str, int], *, code: bool = False) -> str:
    if not counts:
        return "none"
    return ", ".join((f"`{key}` {value}" if code else f"{key} {value}")
                     for key, value in counts.items())


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("`", "'").replace("\n", " ")


def summarize(traces: Iterable[Trace]) -> Summary:
    """Explain and count every action of every trace.

    Actions without verification count as ``unverified`` state and origin.
    Flagged actions are those with any code in ``ATTENTION``.
    """
    state, origin, alignment, responses, diagnoses = (Counter() for _ in range(5))
    flagged, trace_count, action_count = [], 0, 0
    for trace in traces:
        if not isinstance(trace, Trace):
            raise ConsequaTypeError("summarize requires Trace records")
        trace_count += 1
        responses.update(item.status.value for item in trace.responses)
        for item in explain(trace).actions:
            action_count += 1
            receipt = item.consequence
            state[receipt.status.value if receipt else "unverified"] += 1
            origin[receipt.origin.value if receipt else "unverified"] += 1
            alignment[item.assessment_alignment] += 1
            diagnoses.update(set(item.codes))
            attention = tuple(code for code in item.codes if code in ATTENTION)
            if attention:
                flagged.append(Flagged(trace.trace_id, item.action_id, attention))
    return Summary(traces=trace_count, actions=action_count, state=_ordered(state),
                   origin=_ordered(origin), alignment=_ordered(alignment),
                   responses=_ordered(responses), diagnoses=_ordered(diagnoses),
                   flagged=tuple(flagged))


def _ordered(counter: Counter) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))
