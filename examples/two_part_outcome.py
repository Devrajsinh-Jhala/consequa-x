"""A two-part outcome: a refund *and* a closed ticket, checked against two SQLite files.

Standard library only, offline and deterministic. A scripted support agent calls
one ``resolve_case`` tool that should refund the order in the payments ledger
and close the customer's ticket in the CRM. Its outcome contract is
``all_of(refund, ticket)``: both parts must hold. ConseqaX reads each part
back from its own system through a separate read-only connection and verifies
them together with ``CompositeVerifier``.

Two modes:

- ``ticket_left_open`` (default): the refund is written, but the CRM update is
  dropped. The tool still answers ``success`` and the agent reports success. The
  first readback comes while the CRM replica lags, so the outcome stays
  ``unknown`` even though the refund part is satisfied. The second readback
  covers the horizon: the ticket part is violated, so the whole outcome is.
- ``both_done``: both effects are written and the outcome is satisfied.

Run from this folder with ConseqaX 2.1 or newer installed::

    python two_part_outcome.py --mode ticket_left_open --output two-part-run

The output folder must be new. It receives both databases, the captured trace,
its explanation and a self-contained HTML report. No money moves and no ticket
system is called. Times are simulated milliseconds.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from consequa_x import (
    CompositeVerifier, Observation, OutcomeContract, RecordVerifier, TraceRecorder, all_of,
    explain, render_report,
)


MODES = ("ticket_left_open", "both_done")
ORDER = {"order_id": "o-17", "amount_minor": 5000, "currency": "INR"}
TICKET = {"ticket_id": "t-9", "state": "closed"}
MESSAGE = "Order o-17 arrived damaged. Please refund the INR 50 and close ticket t-9."
AGENT = "support-agent"
PAYMENTS, CRM = "payments (read-only)", "crm (read-only)"
# Both parts by 200 ms; the refund must persist to 250 ms and the closure to 260 ms.
REFUND = OutcomeContract(contract_id="refund-o-17", predicate="record_present",
                         expected=dict(ORDER), deadline_ms=200, exact_count=1, stability_ms=50)
CLOSURE = OutcomeContract(contract_id="close-t-9", predicate="record_present",
                          expected=dict(TICKET), deadline_ms=200, exact_count=1, stability_ms=60)
CONTRACT = all_of("resolve-o-17", REFUND, CLOSURE)
VERIFIER = CompositeVerifier(
    {"refund-o-17": RecordVerifier(scope_fields=("order_id",)),
     # The CRM readback asks only for closure events of t-9, and says so in its scope.
     "close-t-9": RecordVerifier(scope_fields=("ticket_id", "state"))},
    sources={"refund-o-17": PAYMENTS, "close-t-9": CRM})
REFUNDS = """CREATE TABLE refunds (
    effect_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, amount_minor INTEGER NOT NULL,
    currency TEXT NOT NULL, committed_at_ms INTEGER NOT NULL, action_id TEXT,
    attempt_id TEXT, actor TEXT)"""
TICKET_EVENTS = """CREATE TABLE ticket_events (
    effect_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, state TEXT NOT NULL,
    committed_at_ms INTEGER NOT NULL, action_id TEXT, attempt_id TEXT, actor TEXT)"""


class SimulatedClock:
    """Deterministic milliseconds, so every run of a mode records the same trace."""

    def __init__(self) -> None:
        self.ms = 0

    def __call__(self) -> int:
        return self.ms

    def advance_to(self, ms: int) -> None:
        if ms < self.ms:
            raise ValueError("the simulated clock never runs backwards")
        self.ms = ms


def create(path: Path, schema: str) -> Path:
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(schema)
    return path


def insert(path: Path, table: str, row: dict) -> None:
    columns = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(row.values()))


def resolve_case(payments: Path, crm: Path, clock: SimulatedClock, mode: str, *,
                 action_id: str, attempt_id: str) -> dict:
    """The tool: refund, then close the ticket. It stores request metadata with each effect."""
    origin = {"action_id": action_id, "attempt_id": attempt_id, "actor": AGENT}
    clock.advance_to(12)
    insert(payments, "refunds", {"effect_id": "rf-1", **ORDER, "committed_at_ms": clock(),
                                 **origin})
    clock.advance_to(15)
    if mode == "both_done":
        insert(crm, "ticket_events", {"effect_id": "tk-close-1", **TICKET,
                                      "committed_at_ms": clock(), **origin})
    # In ticket_left_open the CRM call is dropped, but the tool reports success anyway.
    clock.advance_to(18)
    return {"refund_id": "rf-1", "ticket": "closed", "status": "accepted"}


def snapshot(path: Path, destination: Path, clock: SimulatedClock) -> int:
    """Copy a database as a lagging replica; returns its watermark."""
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(destination)) as replica:
        source.backup(replica)
    return clock()


def read(path: Path, query: str, parameters: tuple, *, observation_id: str, source: str,
         scope: dict, observed_at_ms: int, watermark_ms: int) -> Observation:
    """Run one query over a read-only connection and capture it as an observation."""
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, parameters).fetchall()
    records = tuple({key: row[key] for key in row.keys() if row[key] is not None} for row in rows)
    return Observation(observation_id=observation_id, source=source,
                       observed_at_ms=observed_at_ms, as_of_ms=watermark_ms, scope=scope,
                       records=records)


def read_both(payments: Path, crm: Path, number: int, now: int, crm_watermark: int):
    return (
        read(payments, "SELECT * FROM refunds WHERE order_id = ? ORDER BY effect_id",
             (ORDER["order_id"],), observation_id=f"payments-{number}", source=PAYMENTS,
             scope={"order_id": ORDER["order_id"]}, observed_at_ms=now, watermark_ms=now),
        read(crm, "SELECT * FROM ticket_events WHERE ticket_id = ? AND state = ? "
                  "ORDER BY effect_id", (TICKET["ticket_id"], TICKET["state"]),
             observation_id=f"crm-{number}", source=CRM, scope=dict(TICKET),
             observed_at_ms=now, watermark_ms=crm_watermark),
    )


def run(mode: str, output: Path) -> dict:
    """Run one mode into a new folder and return its summary."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    clock = SimulatedClock()
    payments = create(output / "payments.sqlite", REFUNDS)
    crm = create(output / "crm.sqlite", TICKET_EVENTS)
    rec = TraceRecorder(f"two-part-{mode}", actor=AGENT, clock=clock)

    # 1. The agent reads the request and decides to resolve the case.
    message = rec.context("user_input", {"text": MESSAGE})
    clock.advance_to(2)
    rec.decision({"tool": "resolve_case", "reason": "damaged on arrival"}, inputs=(message,))
    clock.advance_to(3)
    rec.register("resolve-o-17", "resolve_case", {**ORDER, "ticket_id": TICKET["ticket_id"]},
                 contract=CONTRACT)

    # 2. One tool call performs both effects; the recorder captures it.
    clock.advance_to(5)
    with rec.attempt(data={"tool": "resolve_case"}) as attempt:
        attempt.result = resolve_case(payments, crm, clock, mode, action_id="resolve-o-17",
                                      attempt_id=attempt.attempt_id)

    # 3. The agent reports what the tool told it.
    clock.advance_to(20)
    rec.assessment("success", rationale="The tool refunded the order and closed the ticket.")

    # 4. Readback from each system. The CRM replica lags behind at first.
    clock.advance_to(140)
    crm_replica = output / "crm-replica.sqlite"
    lagging = snapshot(crm, crm_replica, clock)
    clock.advance_to(300)
    first = rec.verify(read_both(payments, crm_replica, 1, clock(), lagging), verifier=VERIFIER)
    clock.advance_to(400)
    second = rec.verify(read_both(payments, crm, 2, clock(), clock()), verifier=VERIFIER)

    trace = rec.trace()
    explanation = explain(trace)
    (output / "trace.json").write_text(trace.to_json(indent=2), encoding="utf-8")
    (output / "explanation.json").write_text(
        json.dumps(explanation.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    (output / "report.html").write_text(render_report(trace), encoding="utf-8")
    action = explanation.single_action
    return {
        "mode": mode, "tool_response": trace.responses[-1].status.value,
        "agent_reported": trace.latest_assessment().status.value,
        "first_state": first.status.value, "state": second.status.value,
        "origin": second.origin.value, "alignment": action.assessment_alignment,
        "diagnoses": list(action.codes), "reason": second.reason,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=MODES, default="ticket_left_open")
    parser.add_argument("--output", type=Path, help="A new folder (default: two-part-MODE)")
    args = parser.parse_args(argv)
    output = args.output or Path(f"two-part-{args.mode}")
    summary = run(args.mode, output)
    labels = (("tool_response", "tool response"), ("agent_reported", "agent reported"),
              ("first_state", "first readback"), ("state", "state"), ("origin", "origin"),
              ("alignment", "alignment"))
    for key, label in labels:
        print(f"{label:>15}: {summary[key]}")
    print(f"{'diagnoses':>15}: {', '.join(summary['diagnoses'])}")
    print(f"{'verifier':>15}: {summary['reason']}")
    print(f"Open {(output / 'report.html').resolve()} in your browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
