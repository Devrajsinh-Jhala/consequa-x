"""Summaries across traces and the append-only JSON Lines trace store."""

import json

import pytest

from consequa_x import (
    OutcomeContract, Summary, TraceRecorder, TraceStore, ValidationError, cli, summarize,
)
from test_multi_action import two_action_run


def unverified_trace(trace_id="run-unverified"):
    rec = TraceRecorder(trace_id, actor="agent|bot", time_base="relative_ms")
    rec.register("ship|1", "ship", {}, at_ms=0, contract=OutcomeContract(
        contract_id="ship-contract", predicate="record_present", expected={"id": "1"},
        deadline_ms=10))
    rec.assessment("success", at_ms=1)
    return rec.trace()


def test_summary_counts_actions_and_keeps_unknown_and_unverified_separate():
    summary = summarize([two_action_run().trace(), unverified_trace()])
    assert isinstance(summary, Summary)
    assert (summary.traces, summary.actions) == (2, 3)
    assert summary.state == {"satisfied": 1, "unverified": 1, "violated": 1}
    assert summary.alignment == {"contradicted": 2, "unassessable": 1}
    assert summary.responses == {"success": 1, "timeout": 1}
    assert summary.diagnoses["NO_VERIFICATION"] == 1
    flagged = {(item.trace_id, item.action_id) for item in summary.flagged}
    assert flagged == {("run-1", "refund-1"), ("run-1", "email-1")}
    text = summary.to_text()
    assert "Verified state (of 3 actions): satisfied 1, unverified 1, violated 1" in text
    assert "run-1 / email-1" in text
    markdown = summary.to_markdown()
    assert "| Verified state | `unverified` | 1 |" in markdown
    data = json.loads(summary.to_json())
    assert data["actions"] == 3 and data["flagged"][0]["codes"]
    empty = summarize([])
    assert (empty.traces, empty.actions) == (0, 0) and "none" in empty.to_text()
    with pytest.raises(TypeError):
        summarize([{"trace_id": "not a trace"}])


def test_markdown_escapes_table_cells():
    from consequa_x import Observation, RecordVerifier

    rec = TraceRecorder("trace|`x`", actor="agent", time_base="relative_ms")
    rec.register("a|1", "ship", {}, at_ms=0, contract=OutcomeContract(
        contract_id="c", predicate="record_present", expected={"id": "1"}, deadline_ms=10))
    rec.response(rec.dispatch(at_ms=1), "success", at_ms=2)
    rec.verify(Observation(observation_id="o", source="db", observed_at_ms=20, as_of_ms=20,
                           scope={"id": "1"}), verifier=RecordVerifier(scope_fields=("id",)))
    summary = summarize([rec.trace()])
    assert [item.action_id for item in summary.flagged] == ["a|1"]
    row = next(line for line in summary.to_markdown().splitlines() if r"a\|1" in line)
    assert row.startswith(r"| `trace\|'x'` | `a\|1` |") and row.count(" | ") == 2


def test_store_appends_validated_traces_and_reads_them_back(tmp_path):
    store = TraceStore(tmp_path / "runs" / "traces.jsonl")
    assert list(store) == [] and len(store) == 0
    first, second = two_action_run().trace(), unverified_trace()
    store.append(first)
    store.append(second)
    assert list(store) == [first, second] and len(store) == 2
    lines = store.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["trace_id"] == "run-1"
    with pytest.raises(ValidationError, match="already stored"):
        TraceStore(store.path).append(first)
    assert store.path.read_text(encoding="utf-8").splitlines() == lines
    with pytest.raises(TypeError):
        store.append(first.to_dict())


def test_store_reports_the_line_of_an_invalid_entry(tmp_path):
    path = tmp_path / "traces.jsonl"
    TraceStore(path).append(unverified_trace())
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"schema_version": "0.1", "trace_id": "old"}\n')
    with pytest.raises(ValidationError, match="line 2"):
        list(TraceStore(path))


def test_cli_summarizes_folders_and_stores_without_leaking_errors(tmp_path, capsys):
    folder = tmp_path / "run"
    folder.mkdir()
    trace = two_action_run().trace()
    (folder / "trace.json").write_text(trace.to_json(), encoding="utf-8")
    (folder / "manifest.json").write_text('{"files": []}', encoding="utf-8")
    TraceStore(folder / "more.jsonl").append(unverified_trace())
    assert cli.main(["summarize", str(folder)]) == 0
    out = capsys.readouterr().out
    assert "2 traces, 3 actions." in out and "Skipped 1 JSON files that are not traces." in out
    (folder / "broken.json").write_text('{"schema_version": "1.0", "trace_id": "SECRET", '
                                        '"actions": [{"SECRET_FIELD": 1}]}', encoding="utf-8")
    assert cli.main(["summarize", str(folder), "--format", "markdown"]) == 2
    out = capsys.readouterr().out
    assert "broken.json: ConsequaTypeError" in out or "broken.json: ValidationError" in out
    assert "SECRET_FIELD" not in out
    output = tmp_path / "summary.json"
    assert cli.main(["summarize", str(folder / "trace.json"), "--format", "json",
                     "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["actions"] == 2
    assert cli.main(["summarize", str(folder / "trace.json"), "--output", str(output)]) == 2
