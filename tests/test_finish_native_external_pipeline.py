"""Auxiliary sequencing tests; no Git mutations, model calls or network use."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import finish_native_external_pipeline as p


@pytest.fixture
def settings(tmp_path):
    paper = tmp_path / "paper"
    argv = ["--paper-root", str(paper), "--frozen-root", str(tmp_path / "frozen"),
        "--study-output", str(paper / "output" / "study"), "--aux-output", str(tmp_path / "aux"),
        "--native-root", str(tmp_path / "native"), "--models", str(tmp_path / "models"),
        "--python", str(tmp_path / "python.exe"), "--gh", str(tmp_path / "gh.exe")]
    args = p.parser().parse_args(argv)
    return SimpleNamespace(args=args, argv=argv, config=p.configuration(args))


def test_default_prepare_only_prints_plan_without_writes_or_processes(settings, monkeypatch, capsys):
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **k: pytest.fail("Preparation launched a subprocess"))
    assert p.main(settings.argv) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["no_files_written"] is planned["no_commands_executed"] is True
    assert planned["source_commit"] == p.SOURCE_COMMIT
    assert not settings.config["aux"].exists() and not settings.config["study"].exists()
    freeze = next(stage for stage in planned["stages"] if stage["stage"] == "freeze")["command"]
    assert Path(freeze[freeze.index("--readiness") + 1]).name == "readiness.json"
    assert freeze[freeze.index("--request-timeout") + 1] == "1200"
    assert freeze[freeze.index("--timeout") + 1] == "7200"
    assert settings.config["guarded_smoke"].name == "guarded-20-001"
    assert "<40-character-published-protocol-commit>" in planned["stages"][-2]["command"]


@pytest.mark.parametrize("existing", ["study", "aux"])
def test_execute_refuses_preexisting_outputs_before_any_process(settings, monkeypatch, existing):
    settings.config[existing].mkdir(parents=True)
    monkeypatch.setattr(p.subprocess, "run", lambda *a, **k: pytest.fail("Existing run launched a process"))
    with pytest.raises(p.PipelineRefusal, match="already exists"):
        p.main([*settings.argv, "--execute"])


def test_refuses_output_outside_publishing_checkout(settings):
    settings.args.study_output = str(settings.config["paper"].parent / "elsewhere")
    with pytest.raises(p.PipelineRefusal, match="inside the publishing"):
        p.configuration(settings.args)


def smoke(config, key, source, *, code=0):
    slot = config[key]
    episode = slot / "episode"
    episode.mkdir(parents=True)
    p.write_new(slot / "parent-receipt.json", {"exit_code": code, "hard_timeout": False,
        "supervisor_error": None, "cleanup_errors": []})
    p.write_new(episode / "execution-receipt.json", {"status": "native_returned", "capture_errors": [],
        "inflight_tool_dispatches": [], "arm": "native" if key == "native_smoke" else "G",
        "task_id": "19" if key == "native_smoke" else "20"})
    p.write_new(episode / "worker-identity.json", {"source_files": source})
    p.write_new(episode / "native-simulation.json", {"reward_info": {"reward": 0}})


def test_failed_native_terminal_receipt_stops_immediately_even_guarded_absent(settings, monkeypatch):
    smoke(settings.config, "native_smoke", {}, code=1)
    monkeypatch.setattr(p.time, "sleep", lambda *a: pytest.fail("Failed native receipt was polled/retried"))
    with pytest.raises(p.PipelineRefusal, match="terminal parent receipt failed"):
        p.Pipeline(settings.config, None, settings.args).wait_for_smokes({})
    assert not settings.config["guarded_smoke"].exists()


def test_smoke_wait_uses_terminal_receipts_and_accepts_native_reward_zero(settings, monkeypatch):
    source = {"fixture.py": {"sha256": "a" * 64, "bytes": 1}}
    settings.config["aux"].mkdir()
    smoke(settings.config, "native_smoke", source)
    polls = []

    def wait(seconds):
        polls.append(seconds)
        smoke(settings.config, "guarded_smoke", source)

    monkeypatch.setattr(p.time, "sleep", wait)
    p.Pipeline(settings.config, None, settings.args).wait_for_smokes(source)
    receipt = p.load_json(settings.config["aux"] / "verified-smokes.json")
    assert polls == [30] and receipt["task_reward_one_required"] is False
    assert set(receipt["evidence"]) == {"native_smoke", "guarded_smoke"}


@pytest.mark.parametrize("change", ["source", "capture", "grading"])
def test_smoke_integrity_failures_refuse_readiness(settings, change):
    for key in ("native_smoke", "guarded_smoke"):
        smoke(settings.config, key, {})
    episode = settings.config["guarded_smoke"] / "episode"
    if change == "source":
        path, value = episode / "worker-identity.json", {"source_files": {"changed": {}}}
    elif change == "capture":
        path = episode / "execution-receipt.json"
        value = p.load_json(path)
        value["capture_errors"] = [{"error": "fixture"}]
    else:
        path, value = episode / "native-simulation.json", {"reward_info": None}
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(p.PipelineRefusal):
        p.Pipeline(settings.config, None, settings.args).wait_for_smokes({})


def test_frozen_source_is_checked_against_full_git_blobs(settings):
    config = settings.config
    blobs = {name: b"pinned source\n" for name in p.SOURCE_PATHS}
    for name, blob in blobs.items():
        path = config["frozen"] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob.replace(b"\n", b"\r\n"))
    pipeline = p.Pipeline(config, None, settings.args)

    def git(name, *arguments, **kwargs):
        if name == "source-head":
            return 0, p.SOURCE_COMMIT.encode()
        if name == "source-status":
            return 0, b""
        return 0, blobs[arguments[-1].split(":", 1)[1]]

    pipeline.git = git
    source = pipeline.verify_source()
    assert set(source) == set(p.SOURCE_PATHS)
    (config["frozen"] / p.SOURCE_PATHS[0]).write_text("tampered", encoding="utf-8")
    with pytest.raises(p.PipelineRefusal, match="pinned Git bytes"):
        pipeline.verify_source()


class FakeCommands:
    """Every apparent Git/model operation is an in-memory test double."""
    def __init__(self, config, *, collect_code=0):
        self.config, self.calls, self.staged = config, [], []
        self.commit, self.collect_code = "a" * 40, collect_code
        self.initial_staged = []
        self.actions = False
        self.diverged = False
        self.bad_blob = False
        self.publish_wrong_ref = False

    def run(self, name, command, cwd, *, check=True):
        command = list(map(str, command))
        self.calls.append((name, command, check))
        code, output = 0, b""
        if name == "publishing-repository":
            output = json.dumps({"nameWithOwner": p.REPOSITORY}).encode()
        elif name == "actions-permissions":
            output = json.dumps({"enabled": self.actions}).encode()
        elif name == "publishing-branch":
            output = p.BRANCH.encode()
        elif name == "index-before":
            output = "\n".join(self.initial_staged).encode()
        elif name == "stage-protocol-only":
            self.staged = command[command.index("--") + 1:]
        elif name in {"index-protocol-only", "committed-inventory"}:
            output = "\n".join(self.staged).encode()
        elif name == "protocol-head":
            output = self.commit.encode()
        elif name == "protocol-committed-bytes":
            path = command[-1].split(":", 1)[1]
            output = b"changed" if self.bad_blob else (self.config["paper"] / path).read_bytes()
        elif name == "remote-fast-forward" and self.diverged:
            code = 1
        elif name == "verify-published-refs":
            published = "b" * 40 if self.publish_wrong_ref else self.commit
            output = f"{published}\trefs/heads/main\n{published}\trefs/heads/{p.BRANCH}\n".encode()
        elif name == "readiness":
            self.config["readiness"].mkdir(parents=True)
            p.write_new(self.config["readiness"] / "readiness.json", {"fixture": True})
        elif name == "freeze":
            self.config["protocol"].mkdir(parents=True)
            for file in ("protocol.json", "protocol-receipt.json"):
                p.write_new(self.config["protocol"] / file, {"fixture": True})
        elif name == "collect-once":
            self.config["collection"].mkdir(parents=True)
            p.write_new(self.config["collection"] / "manifest.json", {"files": {}})
            code = self.collect_code
        elif name == "independent-audit":
            self.config["audit"].mkdir(parents=True)
        if check:
            p.require(code == 0, "Synthetic command refused: " + name)
        return code, output


@pytest.fixture
def publication(settings):
    settings.config["aux"].mkdir()
    settings.config["protocol"].mkdir(parents=True)
    for name in ("protocol.json", "protocol-receipt.json"):
        p.write_new(settings.config["protocol"] / name, {"fixture": True})
    commands = FakeCommands(settings.config)
    return settings, commands, p.Pipeline(settings.config, commands, settings.args)


def test_publication_commits_only_protocol_checks_full_blobs_and_pushes_normally(publication):
    settings, commands, pipeline = publication
    assert pipeline.publish_protocol() == commands.commit
    stages = [row[0] for row in commands.calls]
    assert stages.index("index-before") < stages.index("stage-protocol-only")
    assert stages.count("protocol-committed-bytes") == 2
    assert stages.index("protocol-committed-bytes") < stages.index("publish-atomic-fast-forward")
    push = next(command for name, command, _ in commands.calls if name == "publish-atomic-fast-forward")
    assert "--atomic" in push and not any("force" in argument or argument.startswith("+") for argument in push)
    assert push[-2:] == [f"{commands.commit}:refs/heads/{p.BRANCH}", f"{commands.commit}:refs/heads/main"]
    assert p.load_json(settings.config["aux"] / "publication-receipt.json")["actions_enabled"] is False


@pytest.mark.parametrize("failure", ["initial_staged", "actions", "diverged", "bad_blob", "publish_wrong_ref"])
def test_publication_refuses_staged_changes_actions_drift_divergence_or_wrong_publication(publication, failure):
    _, commands, pipeline = publication
    setattr(commands, failure, ["unrelated.txt"] if failure == "initial_staged" else True)
    with pytest.raises(p.PipelineRefusal):
        pipeline.publish_protocol()
    names = [row[0] for row in commands.calls]
    assert "collect-once" not in names
    if failure == "initial_staged":
        assert "stage-protocol-only" not in names and "commit-protocol" not in names
    if failure != "publish_wrong_ref":
        assert "publish-atomic-fast-forward" not in names


def test_serial_execution_audits_sealed_collection_even_after_nonzero_return(settings):
    config = settings.config
    config["aux"].mkdir()
    for key in ("native_smoke", "guarded_smoke"):
        smoke(config, key, {})
    commands = FakeCommands(config, collect_code=1)
    pipeline = p.Pipeline(config, commands, settings.args)
    pipeline.verify_source = lambda: {}
    result = pipeline.execute()
    names = [row[0] for row in commands.calls]
    assert names.index("readiness") < names.index("freeze") < names.index("verify-published-refs")
    assert names.index("verify-published-refs") < names.index("collect-once") < names.index("independent-audit")
    assert names.count("collect-once") == names.count("independent-audit") == 1
    assert result["status"] == "completed_with_failures" and result["corrective_reruns"] == 0
    for name in ("collect-once", "independent-audit"):
        command = next(command for label, command, _ in commands.calls if label == name)
        assert command[command.index("--protocol-commit") + 1] == commands.commit
        assert str(config["frozen"]) in command[2]


def test_command_logging_records_failures_without_environment_values(settings, monkeypatch):
    config = settings.config
    config["aux"].mkdir()
    called = []

    def failed(command, **kwargs):
        called.append(deepcopy(command))
        assert kwargs["env"]["SECRET_FIXTURE"] == "never-record-me"
        kwargs["stdout"].write(b"synthetic output")
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(p.subprocess, "run", failed)
    commands = p.Commands(config["aux"], {"SECRET_FIXTURE": "never-record-me"})
    with pytest.raises(p.PipelineRefusal, match="exit code 7"):
        commands.run("fixture", ["never-executed", "argument"], config["paper"])
    assert called == [["never-executed", "argument"]]
    paths = list(config["aux"].rglob("*.json"))
    assert len(paths) == 2 and all("never-record-me" not in path.read_text() for path in paths)
    assert p.load_json(next(config["aux"].rglob("receipt.json")))["exit_code"] == 7
