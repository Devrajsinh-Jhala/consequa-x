"""Public command checks for portable exports and evidence-only explanation."""

from hashlib import sha256
import json

from jsonschema import Draft202012Validator
import pytest

from consequa_x import __version__
from consequa_x import cli
from consequa_x.benchmark.runner import run_scenario
from consequa_x.explanation import explain
from consequa_x.models import Trace


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_demo_exports_portable_traces_and_separates_evaluator_truth(tmp_path, capsys):
    output = tmp_path / "demo"
    assert cli.main(["demo", "--output", str(output), "--seed", "7"]) == 0
    assert "Generated 12 offline scenarios" in capsys.readouterr().out
    validator = Draft202012Validator(read_json(output / "trace-schema.json"))
    cases = read_json(output / "evaluator_truth" / "cases.json")
    assert len(cases) == 12
    manifest = read_json(output / "manifest.json")
    assert manifest["package_version"] == __version__
    assert len(manifest["artifacts"]) == 36
    manifest_paths = set()
    for artifact in manifest["artifacts"]:
        path = output / artifact["path"]
        assert sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        manifest_paths.add(artifact["path"])

    for index, case in enumerate(cases):
        trace_path = output / case["trace"]
        exported = read_json(trace_path)
        validator.validate(exported)
        trace = Trace.from_json(trace_path.read_text(encoding="utf-8"))
        assert trace.to_dict() == exported
        assert trace.trace_id == f"trace:{7 + index}"
        assert trace.action.action_id == f"refund:{7 + index}"
        assert case["scenario"] not in trace.trace_id
        assert "ground_truth" not in exported
        assert "scenario" not in exported
        assert "config" not in exported
        explanation_path = output / case["explanation"]
        assert read_json(explanation_path) == explain(trace).to_dict()
        truth_path = output / "evaluator_truth" / trace_path.name
        assert read_json(truth_path)["scenario"] == case["scenario"]
        assert truth_path.relative_to(output).as_posix() in manifest_paths
        assert case["trace"] in manifest_paths
        assert case["explanation"] in manifest_paths


def test_explain_reads_only_the_supplied_trace(tmp_path, capsys, monkeypatch):
    trace = run_scenario(seed=11).trace
    path = tmp_path / "trace.json"
    path.write_text(trace.to_json(), encoding="utf-8")

    def refuse_replay(*args, **kwargs):
        raise AssertionError("Existing-trace explanation must never run a replay")

    monkeypatch.setattr(cli, "run_scenario", refuse_replay)
    monkeypatch.setattr(cli, "RefundReplayRunner", refuse_replay)
    monkeypatch.setattr(cli, "leave_one_out", refuse_replay)
    assert cli.main(["explain", str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == explain(trace).to_dict()
    assert sorted(item.name for item in tmp_path.iterdir()) == ["trace.json"]

    exported = tmp_path / "nested" / "explanation.json"
    assert cli.main(["explain", str(path), "--output", str(exported)]) == 0
    assert read_json(exported) == explain(trace).to_dict()


def test_experiment_reproduces_seeds_and_distinguishes_targets(tmp_path, capsys):
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        assert cli.main(["experiment", "--output", str(output), "--samples", "20",
                         "--seed", "3"]) == 0
    capsys.readouterr()
    assert (first / "results.json").read_bytes() == (second / "results.json").read_bytes()
    assert (first / "README.md").read_bytes() == (second / "README.md").read_bytes()
    results = read_json(first / "results.json")
    assert results["samples_per_condition"] == 20
    assert results["seed"] == 3
    assert "no LLM evaluation" in results["claim"]
    assert len(results["results"]) == 4
    deterministic = {row["target"]: row for row in results["results"]
                     if row["config"]["name"] == "deterministic_retry_fixture"}
    effects = {target: {estimate["event_id"]: estimate["effect"]
                        for estimate in row["estimates"]}
               for target, row in deterministic.items()}
    assert effects["action"]["retry_instruction"] == 0
    assert effects["consequence"]["retry_instruction"] == -1
    for row in results["results"]:
        assert row["policy_type"] == "programmatic_fixture"
        assert row["replay_mode"] == "isolated_simulation"
        for estimate in row["estimates"]:
            assert estimate["samples"] == 20
            assert len(estimate["seeds"]) == 20
            assert estimate["unknown_pairs"] == 0


@pytest.mark.parametrize("samples", ["19", "0", "-1"])
def test_experiment_rejects_insufficient_samples_without_creating_output(tmp_path, capsys, samples):
    output = tmp_path / "rejected"
    assert cli.main(["experiment", "--output", str(output), "--samples", samples]) == 2
    captured = capsys.readouterr()
    assert "at least 20 samples" in captured.err
    assert captured.out == ""
    assert not output.exists()


def test_explain_rejects_non_trace_json_without_creating_an_output(tmp_path, capsys):
    source = tmp_path / "not-a-trace.json"
    source.write_text('{"schema_version":"0.1","scenario":"clean"}', encoding="utf-8")
    output = tmp_path / "not-created" / "explanation.json"
    assert cli.main(["explain", str(source), "--output", str(output)]) == 2
    assert "consequa-x:" in capsys.readouterr().err
    assert not output.exists()


def test_version_matches_installed_public_api(capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--version"])
    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == __version__


@pytest.mark.parametrize("command", ["demo", "experiment"])
def test_export_commands_refuse_existing_evidence_before_running(tmp_path, capsys, monkeypatch, command):
    output = tmp_path / "previous-run"
    output.mkdir()
    witness = output / "evidence.json"
    witness.write_bytes(b"saved evidence")
    def refuse(*args, **kwargs):
        pytest.fail("Rejected output must not start a simulation or replay")
    monkeypatch.setattr(cli, "run_scenario", refuse)
    monkeypatch.setattr(cli, "RefundReplayRunner", refuse)
    assert cli.main([command, "--output", str(output)]) == 2
    assert "new or empty" in capsys.readouterr().err
    assert witness.read_bytes() == b"saved evidence"
    assert list(output.iterdir()) == [witness]


@pytest.mark.parametrize("same_source", [True, False])
def test_explanation_output_preserves_source_and_existing_file(tmp_path, capsys, same_source):
    source = tmp_path / "trace.json"
    encoded = run_scenario(seed=0).trace.to_json().encode()
    source.write_bytes(encoded)
    output = source if same_source else tmp_path / "previous-explanation.json"
    if not same_source:
        output.write_bytes(b"previous explanation")
    previous = output.read_bytes()
    assert cli.main(["explain", str(source), "--output", str(output)]) == 2
    assert "consequa-x:" in capsys.readouterr().err
    assert source.read_bytes() == encoded and output.read_bytes() == previous
