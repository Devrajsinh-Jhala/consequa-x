"""An append-only JSON Lines file of traces.

``TraceStore`` keeps one schema 1.0 trace per line. Appending validates the
trace and writes it whole; reading decodes every line strictly and reports the
line number of anything invalid instead of skipping it. The store never rewrites
or removes earlier lines, so it can be kept as evidence. Use one store per
process: appends are not coordinated across processes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .errors import ConsequaTypeError, ValidationError
from .models import Trace


class TraceStore:
    """Append traces to, and read them from, a JSON Lines file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._trace_ids: set[str] | None = None

    def append(self, trace: Trace) -> None:
        """Validate ``trace`` and add it as one line; earlier lines are untouched.

        Trace IDs must be unique within a store.
        """
        if not isinstance(trace, Trace):
            raise ConsequaTypeError("TraceStore.append requires a Trace")
        line = Trace.from_dict(trace.to_dict()).to_json()
        if self._trace_ids is None:
            self._trace_ids = {item.trace_id for item in self}
        if trace.trace_id in self._trace_ids:
            raise ValidationError(f"trace_id is already stored: {trace.trace_id!r}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
        self._trace_ids.add(trace.trace_id)

    def __iter__(self) -> Iterator[Trace]:
        """Yield every stored trace in order; an invalid line raises ``ValidationError``."""
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    yield Trace.from_json(line)
                except (TypeError, ValueError, RecursionError) as error:
                    raise ValidationError(f"{self.path.name} line {number}: {error}") from None

    def __len__(self) -> int:
        return sum(1 for _ in self)
