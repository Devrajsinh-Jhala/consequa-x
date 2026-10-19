"""Offline report output and source preservation through the public command."""

from hashlib import sha256
import json

import pytest

from consequa_x import cli, render_report
from consequa_x.benchmark.runner import run_scenario


def capture(tmp_path):
    trace = run_scenario(seed=11).trace
    source = tmp_path / "trace.json"
    source.write_text(trace.to_json(), encoding="utf-8")
    return trace, source


@pytest.mark.parametrize("details", [False, True])
def test_report_matches_public_renderer_and_preserves_source(tmp_path, capsys, monkeypatch, details):
    trace, source = capture(tmp_path)
    before = sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "nested" / "report.html"

    def no_execution(*args, **kwargs):
        pytest.fail("The report command must not execute a scenario or replay")

    monkeypatch.setattr(cli, "run_scenario", no_execution)
    monkeypatch.setattr(cli, "explain", no_execution)
    monkeypatch.setattr(cli, "leave_one_out", no_execution)
    command = ["report", str(source), "--output", str(output)]
    if details:
        command.append("--include-details")
    assert cli.main(command) == 0
    assert output.read_text(encoding="utf-8") == render_report(trace, include_details=details)
    assert sha256(source.read_bytes()).hexdigest() == before
    assert "Saved offline report" in capsys.readouterr().out


@pytest.mark.parametrize("destination", ["source", "existing", "directory"])
def test_report_never_overwrites_input_or_existing_output(tmp_path, capsys, destination):
    _, source = capture(tmp_path)
    output = tmp_path / "existing.html"
    output.write_text("retain this evidence", encoding="utf-8")
    target = {"source": source, "existing": output, "directory": tmp_path}[destination]
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert cli.main(["report", str(source), "--output", str(target)]) == 2
    assert capsys.readouterr().err
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}


@pytest.mark.parametrize("mutation", ["json", "version", "extra", "duplicate"])
def test_invalid_report_input_creates_no_output_tree(tmp_path, capsys, mutation):
    trace, source = capture(tmp_path)
    value = trace.to_dict()
    if mutation == "json":
        text = "not json"
    elif mutation == "duplicate":
        text = trace.to_json().replace('"schema_version": "1.0"',
                                       '"schema_version": "1.0", "schema_version": "1.0"')
    else:
        if mutation == "version":
            value["schema_version"] = "9.0"
        else:
            value["unexpected"] = "refuse"
        text = json.dumps(value)
    source.write_text(text, encoding="utf-8")
    output = tmp_path / "not-created" / "report.html"
    assert cli.main(["report", str(source), "--output", str(output)]) == 2
    assert capsys.readouterr().err
    assert not output.parent.exists()
    assert source.read_text(encoding="utf-8") == text


def test_report_exclusive_creation_preserves_a_racing_writer(tmp_path, monkeypatch):
    _, source = capture(tmp_path)
    output = tmp_path / "report.html"
    renderer = cli.render_report

    def racing_renderer(*args, **kwargs):
        result = renderer(*args, **kwargs)
        output.write_text("created concurrently", encoding="utf-8")
        return result

    monkeypatch.setattr(cli, "render_report", racing_renderer)
    assert cli.main(["report", str(source), "--output", str(output)]) == 2
    assert output.read_text(encoding="utf-8") == "created concurrently"


def test_invalid_report_captured_values_do_not_leak_to_error_logs(tmp_path, capsys):
    trace, source = capture(tmp_path)
    value = trace.to_dict()
    value["SECRET_CAPTURED_VALUE"] = "SECRET_CAPTURED_VALUE"
    source.write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "report.html"
    assert cli.main(["report", str(source), "--output", str(output)]) == 2
    captured = capsys.readouterr()
    assert "SECRET_CAPTURED_VALUE" not in captured.err + captured.out
    assert "invalid schema-1.0 trace" in captured.err
    assert not output.exists()
