"""Fake dependent commands and clocks only; never inspect a real process/model."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import finish_limbo_poststudy as finish


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def seal(directory):
    save(directory / "manifest.json", {path.relative_to(directory).as_posix(): finish.binding(path)
        for path in directory.rglob("*") if path.is_file() and path != directory / "manifest.json"})


@pytest.fixture
def config(tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "native").mkdir()
    for relative in (*finish.SOURCES, "frozen.py", "python.exe"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Synthetic placeholder; no actual stage or native code.\n", encoding="utf-8")
    config = finish.Config(
        root=tmp_path, pipeline=tmp_path / "output/original-pipeline", pipeline_pid=123,
        pipeline_created_time=1000.125, protocol=tmp_path / "output/protocol/protocol.json",
        protocol_commit="a" * 40, collection=tmp_path / "output/original-collection",
        official_audit=tmp_path / "output/original-audit", analysis=tmp_path / "output/original-analysis",
        native_root=tmp_path / "native", output=tmp_path / "output/poststudy",
        portable_audit_output=tmp_path / "output/portable-audit",
        manuscript_output=tmp_path / "output/proposed-manuscript", python=tmp_path / "python.exe",
        interrupted_analysis=tmp_path / "output/interrupted-analysis",
        interrupted_protocol=tmp_path / "output/interrupted-protocol/protocol.json",
        interrupted_protocol_commit="b" * 40)
    save(config.interrupted_protocol, {"synthetic": "original interrupted protocol"})
    save(config.interrupted_analysis / "results.json", {"inputs": {
        "protocol_commit": config.interrupted_protocol_commit,
        "protocol": {"path": str(config.interrupted_protocol), **finish.binding(config.interrupted_protocol)}}})
    save(config.interrupted_analysis / "inputs/audit-result.json", {
        "passed": True, "interrupted_collection": {"synthetic": "copied original bytes; no fabricated terminal"}})
    seal(config.interrupted_analysis)
    save(config.protocol, {"sources": {"frozen.py": finish.binding(tmp_path / "frozen.py")}})
    sources = {name: finish.binding(tmp_path / name) for name in (
        "frozen.py", "scripts/run_limbo_completion_pipeline.py", "scripts/analyze_limbo_external_benchmark.py")}
    save(config.pipeline / "claim.json", {
        "schema": "conseqax-limbo-one-shot-completion-pipeline-v1",
        "protocol_commit": config.protocol_commit,
        "protocol": {"path": str(config.protocol), **finish.binding(config.protocol)},
        "outputs": {"collection_output": str(config.collection), "audit_output": str(config.official_audit),
                    "analysis_output": str(config.analysis)}, "native_root": str(config.native_root),
        "source_files": sources, "python": {"path": str(config.python), **finish.binding(config.python)}})
    return config


def complete_original(config, *, pipeline_seal=True, complete=True):
    save(config.collection / "collection.json", {"synthetic": True})
    seal(config.collection)
    official = {"schema": "conseqax-limbo-audit-v1", "passed": True,
        "protocol_commit": config.protocol_commit, "protocol": finish.binding(config.protocol),
        "collection_manifest": finish.binding(config.collection / "manifest.json"),
        "rows": [{"synthetic": True}], "summary": {"synthetic": True}, "scope": {"synthetic": True}}
    save(config.official_audit / "audit-result.json", official)
    seal(config.official_audit)
    save(config.analysis / "results.json", {
        "analysis_source": finish.binding(config.root / "scripts/analyze_limbo_external_benchmark.py"),
        "inputs": {"protocol_commit": config.protocol_commit,
            "collection_manifest": finish.binding(config.collection / "manifest.json"),
            **{name: {"path": str(path), **finish.binding(path)} for name, path in (
                ("audit", config.official_audit / "audit-result.json"),
                ("audit_manifest", config.official_audit / "manifest.json"), ("protocol", config.protocol))}}})
    seal(config.analysis)
    save(config.pipeline / "terminal-result.json", {
        "schema": "conseqax-limbo-completion-pipeline-terminal-v1", "protocol_commit": config.protocol_commit,
        "status": "complete" if complete else "analysis_failed", "artifact_chain_complete": complete,
        "error": None, "exit_code": 0, "stages": [
            {"stage": stage, "returncode": 0, "known_subprocess_closed": True}
            for stage in ("collector", "audit", "pdf_marker", "analysis")],
        **{name: finish.binding(directory / "manifest.json") for name, directory in (
            ("collection_manifest", config.collection), ("audit_manifest", config.official_audit),
            ("analysis_manifest", config.analysis))}})
    if pipeline_seal:
        seal(config.pipeline)


class FakeCommands:
    def __init__(self, config, *, portable_code=0, portable_passed=True, manuscript_code=0,
                 review_pending=True, change_source=False, interrupt=False):
        self.config = config
        self.portable_code = portable_code
        self.portable_passed = portable_passed
        self.manuscript_code = manuscript_code
        self.review_pending = review_pending
        self.change_source = change_source
        self.interrupt = interrupt
        self.calls = []

    def __call__(self, command, *, cwd, env, stdout, stderr):
        assert Path(cwd) == self.config.root
        assert env["PYTHONPATH"] == str(self.config.root)
        assert (self.config.output / "claim.json").is_file()
        stage = Path(command[2]).name
        self.calls.append(stage)
        stdout.write(b"Synthetic dependent stage only\n")
        if self.interrupt:
            raise KeyboardInterrupt("Synthetic child terminal unknown")
        if stage == "audit_limbo_portable.py":
            assert command[command.index("--compare-official") + 1] == str(self.config.official_audit / "audit-result.json")
            result = finish.load(self.config.official_audit / "audit-result.json")
            result["passed"] = self.portable_passed
            result["portable_audit"] = {"schema": "conseqax-limbo-portable-audit-v1",
                "comparison_to_original_official": {
                    "semantic_agreement": True, "original_official_audit_remains_first_authority": True,
                    "path": str(self.config.official_audit / "audit-result.json"),
                    **finish.binding(self.config.official_audit / "audit-result.json")}}
            save(self.config.portable_audit_output / "audit-result.json", result)
            seal(self.config.portable_audit_output)
            if self.change_source:
                (self.config.root / "scripts/build_final_limbo_paper.py").write_text("changed\n", encoding="utf-8")
            return SimpleNamespace(returncode=self.portable_code)
        assert stage == "prepare_final_limbo_manuscript.py"
        assert command[command.index("--interrupted-analysis") + 1] == str(self.config.interrupted_analysis)
        assert command[command.index("--interrupted-protocol-commit") + 1] == self.config.interrupted_protocol_commit
        save(self.config.manuscript_output / "preparation-receipt.json", {
            "schema": "conseqax-final-paper-preparation-v1", "status": "REVIEW_PENDING" if self.review_pending else "COMPLETE",
            "visual_review_pending": self.review_pending, "proposed_sources_require_lead_review": True,
            "new_model_calls": 0, "new_pdf_created": False, "protocol_commit": self.config.protocol_commit,
            "protocol": finish.binding(self.config.protocol),
            "analysis_manifest": finish.binding(self.config.analysis / "manifest.json"),
            "both_cohorts_retained_separately": True, "cohorts_pooled": False,
            "interrupted_cohort": {"protocol_commit": self.config.interrupted_protocol_commit,
                "analysis_manifest": finish.binding(self.config.interrupted_analysis / "manifest.json")}})
        seal(self.config.manuscript_output)
        return SimpleNamespace(returncode=self.manuscript_code)


def no_pid_read(*_args):
    raise AssertionError("A completed seal must not require its former PID to remain alive")


def assert_failed_closed(config, result):
    assert result["exit_code"] == 1
    assert result["paper_stage"] == "NOT_PREPARED"
    assert result["new_model_calls"] == 0
    assert result["new_pdf_created"] is False
    finish.verify_manifest(config.output)


def test_waits_in_thirty_second_read_only_intervals_then_stages_once(config):
    fake, sleeps, observations = FakeCommands(config), [], []

    def observe(*_args):
        observations.append("only bound PID")
        return {"status": "matching", "actual_create_time": config.pipeline_created_time}

    def sleep(seconds):
        sleeps.append(seconds)
        complete_original(config)

    result = finish.run(config, runner=fake, observer=observe, sleeper=sleep)
    assert sleeps == [30]
    assert observations == ["only bound PID"]
    assert fake.calls == ["audit_limbo_portable.py", "prepare_final_limbo_manuscript.py"]
    assert result["status"] == result["paper_stage"] == "REVIEW_PENDING"
    assert result["exit_code"] == 0
    assert result["new_pdf_created"] is False
    finish.verify_manifest(config.output)
    with pytest.raises(ValueError, match="NEW directory"):
        finish.run(config, runner=fake, observer=observe, sleeper=sleep)
    assert len(fake.calls) == 2


def test_already_sealed_pipeline_needs_no_live_pid(config):
    complete_original(config)
    fake = FakeCommands(config)
    result = finish.run(config, runner=fake, observer=no_pid_read, sleeper=lambda _: pytest.fail("No wait needed"))
    assert result["status"] == "REVIEW_PENDING"
    assert len(fake.calls) == 2


@pytest.mark.parametrize("status", ["pid_gone", "pid_reused", "command_identity_changed"])
def test_identity_loss_before_seal_stops_without_any_command(config, status):
    fake = FakeCommands(config)
    result = finish.run(config, runner=fake, observer=lambda *_: {"status": status},
                        sleeper=lambda _: pytest.fail("Identity loss must not be retried"))
    assert result["status"] == "ORIGINAL_PIPELINE_INTERRUPTED"
    assert fake.calls == []
    assert not config.collection.exists()
    assert_failed_closed(config, result)


def test_terminal_without_manifest_is_not_a_complete_pipeline(config):
    complete_original(config, pipeline_seal=False)
    fake = FakeCommands(config)
    result = finish.run(config, runner=fake, observer=lambda *_: {"status": "pid_gone"})
    assert result["status"] == "ORIGINAL_PIPELINE_INTERRUPTED"
    assert fake.calls == []
    assert_failed_closed(config, result)


def test_seal_arriving_during_pid_exit_observation_is_accepted(config):
    fake = FakeCommands(config)

    def observe(*_args):
        complete_original(config)
        return {"status": "pid_gone"}

    result = finish.run(config, runner=fake, observer=observe, sleeper=lambda _: pytest.fail("Seal is already ready"))
    assert result["status"] == "REVIEW_PENDING"
    assert len(fake.calls) == 2


def test_source_change_during_wait_refuses_dependent_work(config):
    fake = FakeCommands(config)

    def sleep(_seconds):
        (config.root / "scripts/audit_limbo_portable.py").write_text("changed while waiting\n", encoding="utf-8")

    result = finish.run(config, runner=fake, observer=lambda *_: {"status": "matching"}, sleeper=sleep)
    assert result["status"] == "ORIGINAL_PIPELINE_WAIT_FAILED"
    assert "source changed" in result["error"]
    assert fake.calls == []
    assert_failed_closed(config, result)


def test_interrupted_cohort_changed_during_wait_stops_without_new_stage(config):
    fake = FakeCommands(config)

    def sleep(_seconds):
        save(config.interrupted_analysis / "results.json", {"tampered": True})

    result = finish.run(config, runner=fake, observer=lambda *_: {"status": "matching"}, sleeper=sleep)
    assert result["status"] == "ORIGINAL_PIPELINE_WAIT_FAILED"
    assert fake.calls == []
    assert_failed_closed(config, result)


def test_ordinary_successful_audit_cannot_replace_original_interruption_evidence(config):
    save(config.interrupted_analysis / "inputs/audit-result.json", {"passed": True})
    seal(config.interrupted_analysis)
    fake = FakeCommands(config)
    result = finish.run(config, runner=fake, observer=no_pid_read)
    assert result["status"] == "PREFLIGHT_FAILED"
    assert "interruption provenance" in result["error"]
    assert fake.calls == []


def test_failed_original_chain_does_not_get_portable_audit(config):
    complete_original(config, complete=False)
    fake = FakeCommands(config)
    result = finish.run(config, runner=fake, observer=no_pid_read)
    assert fake.calls == []
    assert result["status"] == "ORIGINAL_PIPELINE_INTEGRITY_CHECK"
    assert_failed_closed(config, result)


def test_tampered_original_data_prevents_new_commands(config):
    complete_original(config)
    (config.collection / "collection.json").write_text("tampered", encoding="utf-8")
    fake = FakeCommands(config)
    result = finish.run(config, runner=fake, observer=no_pid_read)
    assert fake.calls == []
    assert "bytes differ" in result["error"]
    assert_failed_closed(config, result)


@pytest.mark.parametrize("changes", [{"portable_code": 4}, {"portable_passed": False}])
def test_portable_failure_never_runs_manuscript_preparer(config, changes):
    complete_original(config)
    fake = FakeCommands(config, **changes)
    result = finish.run(config, runner=fake, observer=no_pid_read)
    assert fake.calls == ["audit_limbo_portable.py"]
    assert result["status"] == "PORTABLE_AUDIT_FAILED"
    assert not config.manuscript_output.exists()
    assert_failed_closed(config, result)


def test_source_changed_after_portable_pass_refuses_preparer(config):
    complete_original(config)
    fake = FakeCommands(config, change_source=True)
    result = finish.run(config, runner=fake, observer=no_pid_read)
    assert fake.calls == ["audit_limbo_portable.py"]
    assert "source changed" in result["error"]
    assert_failed_closed(config, result)


def test_manuscript_must_retain_review_pending(config):
    complete_original(config)
    fake = FakeCommands(config, review_pending=False)
    result = finish.run(config, runner=fake, observer=no_pid_read)
    assert fake.calls == ["audit_limbo_portable.py", "prepare_final_limbo_manuscript.py"]
    assert result["status"] == "MANUSCRIPT_PREPARATION_FAILED"
    assert_failed_closed(config, result)


def test_unknown_dependent_child_terminal_is_left_unsealed(config):
    complete_original(config)
    fake = FakeCommands(config, interrupt=True)
    result = finish.run(config, runner=fake, observer=no_pid_read)
    assert fake.calls == ["audit_limbo_portable.py"]
    assert result["stages"][0]["known_subprocess_closed"] is False
    assert not (config.output / "manifest.json").exists()
    assert not (config.output / "terminal-result.json").exists()


def test_new_outputs_cannot_overlap_original_sealed_artifacts(config):
    original = (config.pipeline / "claim.json").read_bytes()
    unsafe = replace(config, manuscript_output=config.pipeline / "child")
    with pytest.raises(ValueError, match="overlap"):
        finish.run(unsafe, runner=FakeCommands(config), observer=no_pid_read)
    assert (config.pipeline / "claim.json").read_bytes() == original
    assert not config.output.exists()


def test_pid_observer_reads_only_requested_pid_and_rejects_reuse(config, monkeypatch):
    calls = []

    class Process:
        def __init__(self, pid):
            calls.append(pid)

        def create_time(self):
            return config.pipeline_created_time + .001

        def kill(self):
            raise AssertionError("No process control")

    class Missing(Exception):
        pass

    monkeypatch.setitem(finish.sys.modules, "psutil", SimpleNamespace(Process=Process, NoSuchProcess=Missing, AccessDenied=Missing))
    result = finish.observe_pipeline(config, finish.load(config.pipeline / "claim.json"))
    assert result["status"] == "pid_reused"
    assert calls == [config.pipeline_pid]
