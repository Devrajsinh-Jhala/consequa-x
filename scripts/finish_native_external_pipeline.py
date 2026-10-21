"""Auxiliary, one-shot orchestration; prepare-only is the default.

This script is outside the eight frozen scientific execution files. It never
creates development episodes, retries collection, changes measured source, or
enables Actions. Execute only after reviewing the printed plan.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


SOURCE_COMMIT = "8bd1cd88ab3644a9c6417e29308ab4b502b40484"
REPOSITORY = "Devrajsinh-Jhala/consequa-x"
BRANCH = "codex/native-external-2026-10-21"
SOURCE_PATHS = (
    "research/native_agent/__init__.py", "research/native_agent/controller.py",
    "research/native_agent/transport.py", "research/native_agent/harness.py",
    "research/native_agent/audit.py", "research/native_agent/protocol.py",
    "scripts/run_native_external_benchmark.py", "scripts/audit_native_external_benchmark.py",
)


class PipelineRefusal(RuntimeError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def require(condition, message):
    if not condition:
        raise PipelineRefusal(message)


def configuration(args):
    paper, frozen = Path(args.paper_root).resolve(), Path(args.frozen_root).resolve()
    study = Path(args.study_output).resolve()
    require(study.is_relative_to(paper / "output"), "Study output must stay inside the publishing checkout's output directory")
    return {"paper": paper, "frozen": frozen, "study": study,
        "aux": Path(args.aux_output).resolve(), "readiness": study / "readiness",
        "protocol": study / "protocol", "collection": study / "collection", "audit": study / "audit",
        "native": Path(args.native_root).resolve(), "models": Path(args.models).resolve(),
        "python": Path(args.python).resolve(), "gh": Path(args.gh).resolve(),
        "wheel": paper / "output/release-2.1.1-2026-10-19/consequa_x-2.1.1-py3-none-any.whl",
        "launch": paper / "output/native-transport-development-2026-10-21/restart-1645/isolated-q8-server-launch.json",
        "transport": paper / "output/native-development-2026-10-21/transport-smoke-005/transport-smoke-result.json",
        "native_smoke": paper / "output/native-development-2026-10-21/native-19-002",
        "guarded_smoke": paper / "output/native-development-2026-10-21/guarded-20-001"}


def measured_command(config, phase, *extra):
    return [str(config["python"]), "-B", str(config["frozen"] / "scripts/run_native_external_benchmark.py"), phase,
        "--native-root", str(config["native"]), "--models", str(config["models"]),
        "--wheel", str(config["wheel"]), "--server-launch", str(config["launch"]), *map(str, extra)]


def plan(config):
    anchor = "<40-character-published-protocol-commit>"
    protocol = config["protocol"] / "protocol.json"
    return {"mode": "prepare_only", "source_commit": SOURCE_COMMIT,
        "no_commands_executed": True, "no_files_written": True,
        "wait_for_terminal_receipts": [str(config[key] / "parent-receipt.json")
                                        for key in ("native_smoke", "guarded_smoke")],
        "stages": [
            {"stage": "verify_frozen_source_and_smokes", "required_source_commit": SOURCE_COMMIT},
            {"stage": "readiness", "command": measured_command(config, "readiness", "--output", config["readiness"],
                "--transport-result", config["transport"], "--native-episode", config["native_smoke"],
                "--guarded-episode", config["guarded_smoke"])},
            {"stage": "freeze", "command": measured_command(config, "freeze", "--output", config["protocol"],
                "--readiness", config["readiness"] / "readiness.json",
                "--request-timeout", "1200", "--timeout", "7200")},
            {"stage": "commit_protocol_only", "paths": [str(protocol), str(config["protocol"] / "protocol-receipt.json")]},
            {"stage": "verify_actions_disabled_and_fast_forward_publish", "branch": BRANCH, "main": "main",
                "push": ["git", "push", "--atomic", "origin", f"{anchor}:refs/heads/{BRANCH}", f"{anchor}:refs/heads/main"]},
            {"stage": "verify_remote_protocol_publication", "require_both_remote_refs": anchor},
            {"stage": "collect_once", "command": measured_command(config, "collect", "--output", config["collection"],
                "--protocol", protocol, "--protocol-commit", anchor)},
            {"stage": "independent_audit_even_after_collection_failure_if_manifest_exists", "command": [
                str(config["python"]), "-B", str(config["frozen"] / "scripts/audit_native_external_benchmark.py"),
                "--collection", str(config["collection"]), "--protocol", str(protocol), "--protocol-commit", anchor,
                "--native-root", str(config["native"]), "--wheel", str(config["wheel"]),
                "--source-root", str(config["frozen"]), "--output", str(config["audit"])]}],
        "auxiliary_output": str(config["aux"]), "study_output": str(config["study"]),
        "retry_resume_or_replacement": False}


class Commands:
    """Every subprocess has retained arguments, UTC times, exit code and logs."""

    def __init__(self, output, child_env):
        self.output, self.child_env, self.count = output, child_env, 0

    def run(self, name, command, cwd, *, check=True):
        directory = self.output / f"stage-{self.count:03d}-{name}"
        self.count += 1
        directory.mkdir(exist_ok=False)
        command = list(map(str, command))
        write_new(directory / "start.json", {"started_utc": utc(), "command": command, "cwd": str(cwd),
            "environment_values_recorded": False})
        started, code, error = time.monotonic(), None, None
        try:
            with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
                result = subprocess.run(command, cwd=str(cwd), env=self.child_env, stdout=stdout, stderr=stderr,
                    check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            code = result.returncode
        except BaseException as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            raise
        finally:
            write_new(directory / "receipt.json", {"finished_utc": utc(), "exit_code": code,
                "wall_seconds": time.monotonic() - started, "error": error})
        if check:
            require(code == 0, f"Stage {name} failed with exit code {code}; see retained stage logs")
        return code, (directory / "stdout.log").read_bytes()


class Pipeline:
    def __init__(self, config, commands, args):
        self.config, self.commands, self.args = config, commands, args

    def git(self, name, *arguments, root=None, check=True):
        return self.commands.run(name, ["git", "-C", str(root or self.config["paper"]), *arguments],
                                 self.config["paper"], check=check)

    def verify_source(self):
        frozen = self.config["frozen"]
        _, head = self.git("source-head", "rev-parse", "HEAD", root=frozen)
        require(head.decode().strip() == SOURCE_COMMIT, "Frozen source checkout moved")
        _, status = self.git("source-status", "status", "--porcelain", "--", *SOURCE_PATHS, root=frozen)
        require(not status.strip(), "Frozen measured source is dirty")
        files = {}
        for name in SOURCE_PATHS:
            _, committed = self.git("source-blob", "show", f"{SOURCE_COMMIT}:{name}", root=frozen)
            actual = (frozen / name).read_bytes()
            require(actual == committed or (b"\r\n" not in committed
                    and actual == committed.replace(b"\n", b"\r\n")), "Measured source differs from its pinned Git bytes")
            files[name] = {"sha256": hashlib.sha256(actual).hexdigest(), "bytes": len(actual)}
        return files

    def wait_for_smokes(self, source_files):
        deadline, bindings = time.monotonic() + self.args.wait_timeout, {}
        while len(bindings) != 2:
            for key, arm, task_id in (("native_smoke", "native", "19"), ("guarded_smoke", "G", "20")):
                slot = self.config[key]
                parent_path = slot / "parent-receipt.json"
                if key in bindings or not parent_path.exists():
                    continue
                parent = load_json(parent_path)
                require(parent.get("exit_code") == 0 and parent.get("hard_timeout") is False
                        and parent.get("supervisor_error") is None and not parent.get("cleanup_errors"),
                        f"{key} terminal parent receipt failed; no automatic development retry")
                episode = slot / "episode"
                paths = [parent_path, episode / "execution-receipt.json", episode / "worker-identity.json",
                         episode / "native-simulation.json"]
                require(all(path.is_file() for path in paths), f"{key} terminal artifacts missing")
                execution, identity, simulation = map(load_json, paths[1:])
                require(execution.get("status") == "native_returned" and execution.get("arm") == arm
                        and execution.get("task_id") == task_id and execution.get("capture_errors") == []
                        and execution.get("inflight_tool_dispatches") == []
                        and simulation.get("reward_info") is not None,
                        f"{key} lacks complete native grading or capture integrity")
                require(identity.get("source_files") == source_files, f"{key} source differs from the frozen eight files")
                bindings[key] = [{"path": str(path), "sha256": sha_file(path)} for path in paths]
            if len(bindings) == 2:
                break
            require(time.monotonic() < deadline, "Timed out waiting for explicit development terminal receipts")
            time.sleep(min(self.args.poll_seconds, max(0, deadline - time.monotonic())))
        write_new(self.config["aux"] / "verified-smokes.json", {"verified_utc": utc(),
            "source_commit": SOURCE_COMMIT, "source_files": source_files, "evidence": bindings,
            "task_reward_one_required": False})

    def actions_disabled(self):
        _, identity = self.commands.run("publishing-repository", [self.config["gh"], "repo", "view", "--json", "nameWithOwner"],
                                       self.config["paper"])
        require(json.loads(identity).get("nameWithOwner", "").lower() == REPOSITORY.lower(),
                "Publishing checkout resolves to a different GitHub repository")
        _, raw = self.commands.run("actions-permissions", [self.config["gh"], "api",
            f"repos/{REPOSITORY}/actions/permissions"], self.config["paper"])
        require(json.loads(raw).get("enabled") is False, "GitHub Actions must already be disabled")

    def publish_protocol(self):
        paper, protocol_dir = self.config["paper"], self.config["protocol"]
        paths = [(protocol_dir / name).relative_to(paper).as_posix()
                 for name in ("protocol.json", "protocol-receipt.json")]
        _, branch = self.git("publishing-branch", "branch", "--show-current")
        require(branch.decode().strip() == BRANCH, "Publishing checkout changed branch")
        _, staged = self.git("index-before", "diff", "--cached", "--name-only")
        require(not staged.strip(), "Refusing to commit an existing staged change")
        self.git("source-ancestor", "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD")
        self.git("stage-protocol-only", "add", "--", *paths)
        _, staged = self.git("index-protocol-only", "diff", "--cached", "--name-only")
        require(set(staged.decode().splitlines()) == set(paths), "Staged inventory must contain exactly the two protocol files")
        self.git("commit-protocol", "commit", "-m", "Freeze native external pilot protocol before collection", "--", *paths)
        _, raw_commit = self.git("protocol-head", "rev-parse", "HEAD")
        commit = raw_commit.decode().strip()
        require(re.fullmatch("[0-9a-f]{40}", commit) is not None, "Protocol commit is not an immutable full SHA")
        _, changed = self.git("committed-inventory", "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
        require(set(changed.decode().splitlines()) == set(paths), "Protocol commit changed files outside the two allowed paths")
        for path in paths:
            _, committed = self.git("protocol-committed-bytes", "show", f"{commit}:{path}")
            require((paper / path).read_bytes() == committed, "Protocol file bytes changed after commit")
        self.actions_disabled()
        self.git("fetch-publishing-refs", "fetch", "origin", "main", BRANCH)
        for ref in ("main", BRANCH):
            self.git("remote-fast-forward", "merge-base", "--is-ancestor", f"origin/{ref}", commit)
        self.git("publish-atomic-fast-forward", "push", "--atomic", "origin",
                 f"{commit}:refs/heads/{BRANCH}", f"{commit}:refs/heads/main")
        _, published = self.git("verify-published-refs", "ls-remote", "--heads", "origin", BRANCH, "main")
        refs = dict(line.split()[::-1] for line in published.decode().splitlines())
        require(refs == {f"refs/heads/{BRANCH}": commit, "refs/heads/main": commit},
                "Remote refs do not both publish the exact protocol commit")
        write_new(self.config["aux"] / "publication-receipt.json", {"verified_published_utc": utc(),
            "protocol_commit": commit, "remote_refs": refs, "protocol_sha256": sha_file(protocol_dir / "protocol.json"),
            "protocol_receipt_sha256": sha_file(protocol_dir / "protocol-receipt.json"),
            "actions_enabled": False, "fast_forward_only": True})
        return commit

    def execute(self):
        config = self.config
        source = self.verify_source()
        self.wait_for_smokes(source)
        self.actions_disabled()
        for stage in plan(config)["stages"][1:3]:
            require(self.verify_source() == source, "Measured source changed between prerequisite stages")
            self.commands.run(stage["stage"], stage["command"], config["frozen"])
        commit = self.publish_protocol()
        require(self.verify_source() == source, "Measured source changed before official collection")
        commands = plan(config)["stages"]
        collect = [value.replace("<40-character-published-protocol-commit>", commit)
                   for value in commands[-2]["command"]]
        collect_code, _ = self.commands.run("collect-once", collect, config["frozen"], check=False)
        require((config["collection"] / "manifest.json").is_file(),
                "Collection did not seal a manifest; retained partial outputs require investigation")
        require(self.verify_source() == source, "Frozen independent auditor source changed")
        audit = [value.replace("<40-character-published-protocol-commit>", commit)
                 for value in commands[-1]["command"]]
        audit_code, _ = self.commands.run("independent-audit", audit, config["frozen"], check=False)
        return {"protocol_commit": commit, "collect_exit_code": collect_code, "audit_exit_code": audit_code,
            "status": "completed" if collect_code == audit_code == 0 else "completed_with_failures",
            "collection_attempts": 1, "corrective_reruns": 0}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group()
    mode.add_argument("--prepare-only", action="store_true", help="Print the plan without writes or commands (default)")
    mode.add_argument("--execute", action="store_true", help="Run the reviewed one-shot pipeline")
    result.add_argument("--paper-root", default="D:/ConsequaX-Research/paper-writing")
    result.add_argument("--frozen-root", default="D:/ConsequaX-Research/paper-frozen-native-2026-10-21")
    result.add_argument("--study-output", default="D:/ConsequaX-Research/paper-writing/output/native-official-pipeline-2026-10-21")
    result.add_argument("--aux-output", default="D:/ConsequaX-Research/paper-writing/output/native-finish-pipeline-2026-10-21")
    result.add_argument("--native-root", default="C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit")
    result.add_argument("--models", default="C:/Users/DELL/.ollama/models")
    result.add_argument("--python", default="D:/ConsequaX-Research/native-agent-pilot-venv/Scripts/python.exe")
    result.add_argument("--gh", default="C:/Program Files/GitHub CLI/gh.exe")
    result.add_argument("--poll-seconds", type=float, default=30)
    result.add_argument("--wait-timeout", type=float, default=21600)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    require(0 < args.poll_seconds <= 60 and args.wait_timeout > 0, "Invalid bounded polling interval or wait timeout")
    config = configuration(args)
    if not args.execute:
        print(json.dumps(plan(config), indent=2))
        return 0
    require(not config["study"].exists(), "Study output already exists; resume/replacement is refused")
    require(not config["aux"].exists(), "Auxiliary output already exists; repeated execution is refused")
    require(not (config["protocol"] / "exclusive-collection-claim.json").exists(), "Official collection was already claimed")
    require(not config["aux"].is_relative_to(config["study"])
            and not config["study"].is_relative_to(config["aux"]), "Auxiliary and scientific output directories must be separate")
    config["aux"].mkdir(parents=True, exist_ok=False)
    write_new(config["aux"] / "pipeline-claim.json", {"claimed_utc": utc(), "source_commit": SOURCE_COMMIT,
        "auxiliary_script_sha256": sha_file(__file__), "plan": plan(config), "execute_explicit": True})
    env = os.environ.copy()
    env["PYTHONPATH"] = str(config["frozen"]) + os.pathsep + str(config["native"] / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    started, terminal = utc(), None
    try:
        terminal = Pipeline(config, Commands(config["aux"], env), args).execute()
        return 0 if terminal["status"] == "completed" else 1
    except BaseException as exc:
        terminal = {"status": "failed", "error_type": type(exc).__name__, "message": str(exc),
                    "corrective_reruns": 0}
        return 1
    finally:
        write_new(config["aux"] / "pipeline-receipt.json", {"started_utc": started, "finished_utc": utc(), **terminal})
        files = {path.relative_to(config["aux"]).as_posix(): {"sha256": sha_file(path), "bytes": path.stat().st_size}
                 for path in sorted(config["aux"].rglob("*")) if path.is_file()}
        write_new(config["aux"] / "manifest.json", {"schema": "conseqax-auxiliary-native-pipeline-v1", "files": files})


if __name__ == "__main__":
    raise SystemExit(main())
