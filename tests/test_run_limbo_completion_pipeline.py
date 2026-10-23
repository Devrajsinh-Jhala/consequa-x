"""Only fake stages and temporary evidence; no native task, model, or PDF tool."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_limbo_completion_pipeline as pipeline


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def seal(directory):
    save_json(directory / "manifest.json", {
        path.relative_to(directory).as_posix(): pipeline.binding(path)
        for path in directory.rglob("*") if path.is_file() and path.name != "manifest.json"})


@pytest.fixture
def config(tmp_path):
    (tmp_path / "output").mkdir()
    for name in ("native", "figure-dependencies"):
        (tmp_path / name).mkdir()
    for relative in (*pipeline.STAGE_SOURCES.values(), "frozen.py", "node.exe", "python.exe", "marker.mjs"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Synthetic test placeholder; never measured or executed.\n", encoding="utf-8")
    save_json(tmp_path / "protocol.json", {"sources": {"frozen.py": pipeline.binding(tmp_path / "frozen.py")}})
    return pipeline.Config(
        root=tmp_path, native_root=tmp_path / "native", protocol=tmp_path / "protocol.json",
        protocol_commit="a" * 40, output=tmp_path / "output/pipeline",
        collection_output=tmp_path / "output/collection", audit_output=tmp_path / "output/audit",
        analysis_output=tmp_path / "output/analysis", observer_stop_file=tmp_path / "output/stop-observer.flag",
        node=tmp_path / "node.exe", python=tmp_path / "python.exe", pdf_marker=tmp_path / "marker.mjs",
        figure_dependencies=tmp_path / "figure-dependencies", mpl_config_dir=tmp_path / "mpl-cache")


class FakeStages:
    def __init__(self, config, *, collection_code=0, unsealed=False, bad_collection=False,
                 audit_code=0, audit_passed=True, marker_code=0, analysis_wrong_binding=False,
                 interrupted=False, audit_tampered_after_analysis=False):
        self.config = config
        self.collection_code = collection_code
        self.unsealed = unsealed
        self.bad_collection = bad_collection
        self.audit_code = audit_code
        self.audit_passed = audit_passed
        self.marker_code = marker_code
        self.analysis_wrong_binding = analysis_wrong_binding
        self.interrupted = interrupted
        self.audit_tampered_after_analysis = audit_tampered_after_analysis
        self.calls = []
        self.commands = []

    def __call__(self, command, *, cwd, env, stdout, stderr):
        assert Path(cwd) == self.config.root
        assert env["PYTHONPATH"] == str(self.config.root) + pipeline.os.pathsep + str(self.config.figure_dependencies)
        assert env["MPLCONFIGDIR"] == str(self.config.mpl_config_dir)
        assert (self.config.output / "claim.json").is_file()
        self.commands.append(command)
        if command[0] == str(self.config.node):
            stage = "pdf_marker"
        else:
            stage = {Path(value).name: key for key, value in pipeline.STAGE_SOURCES.items()}[Path(command[2]).name]
        self.calls.append(stage)
        stdout.write(("Synthetic " + stage + " test\n").encode())
        stderr.write(b"")
        if self.interrupted:
            raise KeyboardInterrupt("Synthetic child-terminal uncertainty")
        if stage == "collector":
            directory = self.config.collection_output
            directory.mkdir()
            save_json(directory / "collection.json", {"synthetic": True})
            if not self.unsealed:
                seal(directory)
            if self.bad_collection:
                (directory / "collection.json").write_text("tampered", encoding="utf-8")
            return SimpleNamespace(returncode=self.collection_code)
        if stage == "audit":
            directory = self.config.audit_output
            save_json(directory / "audit-result.json", {
                "schema": "conseqax-limbo-audit-v1", "passed": self.audit_passed,
                "protocol_commit": self.config.protocol_commit,
                "protocol": pipeline.binding(self.config.protocol),
                "collection_manifest": pipeline.binding(self.config.collection_output / "manifest.json")})
            seal(directory)
            return SimpleNamespace(returncode=self.audit_code)
        if stage == "pdf_marker":
            assert command[-6:] == ["--operation-kind", "create", "--expected-output-count", "3", "--output-format", "pdf"]
            return SimpleNamespace(returncode=self.marker_code)
        if stage == "analysis":
            directory = self.config.analysis_output
            directory.mkdir()
            names = ["synthetic-outcomes.pdf", "synthetic-strata.pdf", "synthetic-costs.pdf"]
            for name in names:
                # Text placeholders, not generated PDFs, live only in pytest's
                # temporary directory and never become scientific artifacts.
                (directory / name).write_text("Synthetic fixture; no actual PDF generated.\n", encoding="utf-8")
            save_json(directory / "results.json", {
                "figures_generated": True, "figures": names,
                "analysis_source": pipeline.binding(self.config.root / pipeline.STAGE_SOURCES["analysis"]),
                "inputs": {"protocol_commit": "b" * 40 if self.analysis_wrong_binding else self.config.protocol_commit,
                           "collection_manifest": pipeline.binding(self.config.collection_output / "manifest.json"),
                           **{key: {"path": str(path), **pipeline.binding(path)} for key, path in (
                               ("audit", self.config.audit_output / "audit-result.json"),
                               ("audit_manifest", self.config.audit_output / "manifest.json"),
                               ("protocol", self.config.protocol))}}})
            seal(directory)
            if self.audit_tampered_after_analysis:
                (self.config.audit_output / "audit-result.json").write_text("tampered after analysis", encoding="utf-8")
            return SimpleNamespace(returncode=0)
        raise AssertionError(stage)


def assert_closed_failure(config, result):
    assert result["exit_code"] == 1
    assert result["artifact_chain_complete"] is False
    assert config.observer_stop_file.read_bytes() == b""
    pipeline.verify_manifest(config.output)
    assert json.loads((config.output / "terminal-result.json").read_text(encoding="utf-8"))["error"]


def test_success_runs_single_collector_then_audit_marker_analysis(config):
    fake = FakeStages(config)
    result = pipeline.run(config, runner=fake)
    assert result["status"] == "complete"
    assert result["exit_code"] == 0
    assert result["artifact_chain_complete"] is True
    assert fake.calls == ["collector", "audit", "pdf_marker", "analysis"]
    assert len(result["stages"]) == 4
    assert all(stage["returncode"] == 0 for stage in result["stages"])
    assert config.observer_stop_file.is_file()
    pipeline.verify_manifest(config.output)
    events = [json.loads(line) for line in (config.output / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["stage"] for row in events if row["event"] == "stage_enter"] == fake.calls
    assert events[-1]["event"] == "pipeline_exit"
    with pytest.raises(ValueError, match="new one-shot output"):
        pipeline.run(config, runner=fake)
    assert fake.calls.count("collector") == 1


def test_unsealed_collection_stops_without_audit_or_rerun(config):
    fake = FakeStages(config, collection_code=9, unsealed=True)
    result = pipeline.run(config, runner=fake)
    assert result["status"] == "collection_unsealed"
    assert fake.calls == ["collector"]
    assert result["stages"][0]["returncode"] == 9
    assert not config.audit_output.exists()
    assert_closed_failure(config, result)


def test_sealed_collection_nonzero_exit_still_gets_audited_and_analyzed(config):
    fake = FakeStages(config, collection_code=7)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == ["collector", "audit", "pdf_marker", "analysis"]
    assert result["artifact_chain_complete"] is True
    assert result["status"] == "complete_with_collection_process_error"
    assert result["exit_code"] == 1
    assert result["stages"][0]["returncode"] == 7
    pipeline.verify_manifest(config.output)
    assert config.observer_stop_file.is_file()


@pytest.mark.parametrize("changes", [{"audit_passed": False}, {"audit_code": 4}])
def test_failed_audit_prevents_marker_and_analysis(config, changes):
    fake = FakeStages(config, **changes)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == ["collector", "audit"]
    assert not config.analysis_output.exists()
    assert result["status"] == "audit_failed"
    assert_closed_failure(config, result)


def test_marker_failure_prevents_figure_generation(config):
    fake = FakeStages(config, marker_code=2)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == ["collector", "audit", "pdf_marker"]
    assert not config.analysis_output.exists()
    assert result["status"] == "figure_marker_failed"
    assert_closed_failure(config, result)


def test_tampered_sealed_collection_is_not_sent_to_auditor(config):
    fake = FakeStages(config, bad_collection=True)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == ["collector"]
    assert "bytes differ" in result["error"]
    assert_closed_failure(config, result)


def test_unknown_child_terminal_leaves_pipeline_unsealed_but_stops_observer(config):
    fake = FakeStages(config, interrupted=True)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == ["collector"]
    assert result["stages"][0]["returncode"] is None
    assert result["stages"][0]["known_subprocess_closed"] is False
    assert not (config.output / "manifest.json").exists()
    assert not (config.output / "terminal-result.json").exists()
    assert config.observer_stop_file.is_file()
    events = (config.output / "events.jsonl").read_text(encoding="utf-8")
    assert "stage_interrupted_terminal_unknown" in events
    assert "pipeline_interrupted_unsealed" in events


def test_changed_frozen_source_prevents_any_stage_and_stops_observer(config):
    (config.root / "frozen.py").write_text("Changed after protocol\n", encoding="utf-8")
    fake = FakeStages(config)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == []
    assert result["status"] == "preflight_failed"
    assert_closed_failure(config, result)


def test_analysis_provenance_must_match_passed_audit(config):
    fake = FakeStages(config, analysis_wrong_binding=True)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == ["collector", "audit", "pdf_marker", "analysis"]
    assert result["status"] == "analysis_failed"
    assert_closed_failure(config, result)


def test_passed_audit_must_remain_unchanged_through_analysis(config):
    fake = FakeStages(config, audit_tampered_after_analysis=True)
    result = pipeline.run(config, runner=fake)
    assert fake.calls == ["collector", "audit", "pdf_marker", "analysis"]
    assert result["status"] == "analysis_failed"
    assert_closed_failure(config, result)


def test_stop_flag_cannot_target_protocol_or_stage_artifacts(config):
    fake = FakeStages(config)
    unsafe = replace(config, observer_stop_file=config.protocol)
    original = config.protocol.read_bytes()
    with pytest.raises(ValueError, match="stop flag must be a .flag"):
        pipeline.run(unsafe, runner=fake)
    assert config.protocol.read_bytes() == original
    assert fake.calls == []
    assert not config.output.exists()


def test_safe_observer_flag_is_created_even_when_new_output_preflight_fails(config):
    config.collection_output.mkdir()
    sentinel = config.collection_output / "keep.txt"
    sentinel.write_bytes(b"original evidence")
    fake = FakeStages(config)
    with pytest.raises(ValueError, match="new one-shot output"):
        pipeline.run(config, runner=fake)
    assert fake.calls == []
    assert sentinel.read_bytes() == b"original evidence"
    assert config.observer_stop_file.read_bytes() == b""
    assert not config.output.exists()


@pytest.mark.parametrize("interrupted", [False, True])
def test_default_runner_waits_without_terminating_its_child(monkeypatch, interrupted):
    operations = []

    class FakeProcess:
        def wait(self):
            operations.append("wait")
            if interrupted:
                raise KeyboardInterrupt("Synthetic interruption")
            return 7

        def kill(self):
            raise AssertionError("The orchestrator must not terminate a child")

        def terminate(self):
            raise AssertionError("The orchestrator must not terminate a child")

    monkeypatch.setattr(pipeline.subprocess, "Popen", lambda command, **kwargs: FakeProcess())
    if interrupted:
        with pytest.raises(KeyboardInterrupt):
            pipeline.default_runner(["synthetic command, never executed"])
    else:
        assert pipeline.default_runner(["synthetic command, never executed"]).returncode == 7
    assert operations == ["wait"]
