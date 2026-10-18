"""The SQLite agent-loop example runs offline and shows three distinct outcomes."""

import importlib.util
from pathlib import Path
import socket

import pytest

from consequa_x import Trace


SPEC = importlib.util.spec_from_file_location(
    "agent_loop_sqlite", Path(__file__).resolve().parents[1] / "examples/agent_loop_sqlite.py")
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)

EXPECTED = {
    "timeout_after_commit": ("timeout", "failure", "satisfied", "confirmed", "contradicted",
                             ["ASSESSMENT_DIVERGENCE", "ACKNOWLEDGEMENT_EFFECT_DIVERGENCE"]),
    "other_actor": ("timeout", "failure", "satisfied", "other_actor", "unassessable",
                    ["UNASSESSABLE_ASSESSMENT", "EXTERNAL_ACTOR_EFFECT"]),
    "stale_readback": ("success", "success", "unknown", "unknown", "unassessable",
                       ["UNKNOWN_OUTCOME", "UNVERIFIED_ASSESSMENT"]),
}


@pytest.fixture
def no_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("the example must not use the network")

    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket, "create_connection", refused)


@pytest.mark.parametrize("mode", example.MODES)
def test_each_mode_records_the_expected_evidence(mode, tmp_path, no_network):
    summary = example.run(mode, tmp_path / mode)
    assert (summary["tool_response"], summary["agent_reported"], summary["state"],
            summary["origin"], summary["alignment"], summary["diagnoses"]) == EXPECTED[mode]
    files = {path.name for path in (tmp_path / mode).iterdir()}
    assert {"refunds.sqlite", "trace.json", "explanation.json", "report.html"} <= files
    trace = Trace.from_json((tmp_path / mode / "trace.json").read_text(encoding="utf-8"))
    assert trace.action.contract.predicate == "record_present"


def test_runs_are_deterministic_and_never_reuse_an_output(tmp_path, no_network):
    example.run("timeout_after_commit", tmp_path / "first")
    example.run("timeout_after_commit", tmp_path / "second")
    assert ((tmp_path / "first/trace.json").read_bytes()
            == (tmp_path / "second/trace.json").read_bytes())
    with pytest.raises(FileExistsError):
        example.run("timeout_after_commit", tmp_path / "first")
    with pytest.raises(ValueError, match="mode must be one of"):
        example.run("unknown_mode", tmp_path / "third")


def test_command_line_prints_the_summary(tmp_path, capsys, no_network):
    assert example.main(["--mode", "other_actor", "--output", str(tmp_path / "cli")]) == 0
    printed = capsys.readouterr().out
    assert "origin: other_actor" in printed and "report.html" in printed
