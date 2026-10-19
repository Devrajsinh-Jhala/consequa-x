"""The two-part outcome example runs offline and keeps a lagging part unknown."""

import importlib.util
from pathlib import Path
import socket

import pytest

from consequa_x import Trace, explain, retry_advice


SPEC = importlib.util.spec_from_file_location(
    "two_part_outcome", Path(__file__).resolve().parents[1] / "examples/two_part_outcome.py")
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)

EXPECTED = {
    "ticket_left_open": ("success", "success", "unknown", "violated", "confirmed", "contradicted",
                         ["ASSESSMENT_DIVERGENCE", "RESPONSE_EFFECT_DIVERGENCE",
                          "CONSEQUENCE_VIOLATION", "PART_VIOLATED"]),
    "both_done": ("success", "success", "unknown", "satisfied", "confirmed", "consistent",
                  ["CONSISTENT_OUTCOME"]),
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
    assert (summary["tool_response"], summary["agent_reported"], summary["first_state"],
            summary["state"], summary["origin"], summary["alignment"],
            summary["diagnoses"]) == EXPECTED[mode]
    files = {path.name for path in (tmp_path / mode).iterdir()}
    assert {"payments.sqlite", "crm.sqlite", "crm-replica.sqlite", "trace.json",
            "explanation.json", "report.html"} <= files
    trace = Trace.from_json((tmp_path / mode / "trace.json").read_text(encoding="utf-8"))
    assert trace.single_action.contract.predicate == "all_of"
    assert [item.observation_id for item in trace.observations] == [
        "payments-1", "crm-1", "payments-2", "crm-2"]
    # The first readback leaves the lagging CRM part unknown, so the whole outcome is.
    first = trace.verifications[0]
    assert first.status.value == "unknown" and first.target_effect_ids is None
    assert [item.details["status"] for item in first.evidence] == ["satisfied", "unknown"]


def test_a_left_open_ticket_escalates_instead_of_retrying(tmp_path, no_network):
    example.run("ticket_left_open", tmp_path / "run")
    trace = Trace.from_json((tmp_path / "run/trace.json").read_text(encoding="utf-8"))
    # The refund part happened, so retrying the whole action would duplicate it.
    assert retry_advice(trace).advice.value == "escalate"
    assert explain(trace).single_action.assessment_alignment == "contradicted"


def test_runs_are_deterministic_and_never_reuse_an_output(tmp_path, no_network):
    example.run("ticket_left_open", tmp_path / "first")
    example.run("ticket_left_open", tmp_path / "second")
    assert ((tmp_path / "first/trace.json").read_bytes()
            == (tmp_path / "second/trace.json").read_bytes())
    with pytest.raises(FileExistsError):
        example.run("ticket_left_open", tmp_path / "first")
    with pytest.raises(ValueError, match="mode must be one of"):
        example.run("unknown_mode", tmp_path / "third")


def test_command_line_prints_the_summary(tmp_path, capsys, no_network):
    assert example.main(["--output", str(tmp_path / "cli")]) == 0
    printed = capsys.readouterr().out
    assert "first readback: unknown" in printed and "state: violated" in printed
    assert "close-t-9 violated" in printed
