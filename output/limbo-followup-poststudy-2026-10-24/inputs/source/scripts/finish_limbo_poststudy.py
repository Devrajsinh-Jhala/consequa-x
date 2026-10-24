"""One-shot dependent offline work after a specific existing pipeline seals.

Waits read-only for the bound pipeline; never starts, resumes, retries, repairs,
or replaces collection. After the exact complete seal it runs portable replay
once and stages a manuscript once. The final paper stage remains REVIEW_PENDING.
No model, network, PDF authoring, Git command, scheduler, process control, or
human contact is implemented here. Existing figure files may only be copied.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import math
import json
import os
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_limbo_completion_pipeline as common  # noqa: E402

SOURCES = (
    "scripts/finish_limbo_poststudy.py",
    "scripts/audit_limbo_portable.py",
    "scripts/prepare_final_limbo_manuscript.py",
    "scripts/build_final_limbo_paper.py",
    "scripts/analyze_limbo_external_benchmark.py",
    "scripts/run_limbo_completion_pipeline.py",
)
POLL_SECONDS = 30
require = common.require
binding = common.binding
load = common.load
write_new = common.write_new
verify_manifest = common.verify_manifest


class PipelineInterrupted(RuntimeError):
    """The original process identity disappeared before a complete seal."""


@dataclass(frozen=True)
class Config:
    root: Path
    pipeline: Path
    pipeline_pid: int
    pipeline_created_time: float
    protocol: Path
    protocol_commit: str
    collection: Path
    official_audit: Path
    analysis: Path
    native_root: Path
    output: Path
    portable_audit_output: Path
    manuscript_output: Path
    interrupted_analysis: Path
    interrupted_protocol: Path
    interrupted_protocol_commit: str
    python: Path = Path(sys.executable)

    def resolved(self):
        root = self.root.resolve()
        fields = {}
        for key in self.__dataclass_fields__:
            if key in ("root", "pipeline_pid", "pipeline_created_time", "protocol_commit", "interrupted_protocol_commit"):
                continue
            path = Path(getattr(self, key))
            fields[key] = (root / path).resolve() if not path.is_absolute() else path.resolve()
        return replace(self, root=root, **fields)


def validate_paths(config):
    require(type(config.pipeline_pid) is int and config.pipeline_pid > 0, "A positive original pipeline PID is required")
    require(type(config.pipeline_created_time) in (float, int)
            and math.isfinite(config.pipeline_created_time) and config.pipeline_created_time > 0,
            "Use the original exact psutil creation epoch, not a rounded wall time")
    require(re.fullmatch(r"[0-9a-f]{40}", config.protocol_commit) is not None,
            "An exact 40-character protocol commit is required")
    require(re.fullmatch(r"[0-9a-f]{40}", config.interrupted_protocol_commit) is not None
            and config.interrupted_protocol_commit != config.protocol_commit,
            "The interrupted cohort requires its distinct exact protocol commit")
    inputs = (config.pipeline, config.collection, config.official_audit, config.analysis, config.protocol.parent,
              config.interrupted_analysis, config.interrupted_protocol.parent)
    outputs = (config.output, config.portable_audit_output, config.manuscript_output)
    for path in outputs:
        require(config.root / "output" in path.parents and not path.exists(),
                "Every poststudy output must be a NEW directory under this research workspace/output")
        require(not path.is_symlink(), "Poststudy output symlinks are refused")
        for original in inputs:
            require(path != original and path not in original.parents and original not in path.parents,
                    "Poststudy outputs cannot overlap an original input artifact")
    for number, first in enumerate(outputs):
        for second in outputs[number + 1:]:
            require(first != second and first not in second.parents and second not in first.parents,
                    "Poststudy output directories must be distinct and disjoint")
    require(config.pipeline.is_dir() and config.native_root.is_dir(), "Original pipeline/native directories are absent")


def prepare_claim(config):
    live_claim_path = config.pipeline / "claim.json"
    live_claim = load(live_claim_path)
    require(live_claim.get("schema") == "conseqax-limbo-one-shot-completion-pipeline-v1",
            "Original pipeline claim schema differs")
    require(live_claim.get("protocol_commit") == config.protocol_commit
            and live_claim.get("protocol") == {"path": str(config.protocol), **binding(config.protocol)},
            "Requested protocol differs from the already-running original pipeline")
    require(live_claim.get("outputs") == {
        "collection_output": str(config.collection), "audit_output": str(config.official_audit),
        "analysis_output": str(config.analysis)}, "Requested original stage paths differ from pipeline claim")
    require(Path(live_claim["native_root"]).resolve() == config.native_root, "Requested native source path differs")
    protocol = load(config.protocol)
    interrupted_manifest = verify_manifest(config.interrupted_analysis)
    interrupted_result = load(config.interrupted_analysis / "results.json")
    require(interrupted_result.get("inputs", {}).get("protocol_commit") == config.interrupted_protocol_commit
            and {key: interrupted_result["inputs"]["protocol"][key] for key in ("sha256", "bytes")}
                == binding(config.interrupted_protocol), "Interrupted analysis/protocol identity differs")
    interrupted_audit = load(config.interrupted_analysis / "inputs/audit-result.json")
    require(interrupted_audit.get("passed") is True and bool(interrupted_audit.get("interrupted_collection")),
            "The retained original cohort needs passed replay with explicit interruption provenance")
    sources = protocol["sources"].copy()
    for name, expected in sources.items():
        require(live_claim["source_files"].get(name) == expected,
                "Original pipeline source binding differs from protocol: " + name)
    for name in SOURCES:
        actual = binding(common.confined(config.root, name))
        if name in ("scripts/analyze_limbo_external_benchmark.py", "scripts/run_limbo_completion_pipeline.py"):
            require(live_claim["source_files"].get(name) == actual,
                    "Frozen pipeline/analyzer changed after original launch: " + name)
        sources[name] = actual
    for name, expected in sources.items():
        require(binding(common.confined(config.root, name)) == expected,
                "A held scientific/helper source differs: " + name)
        destination = config.output / "inputs/source" / name
        common.copy_new(common.confined(config.root, name), destination)
        require(binding(destination) == expected, "Source changed during claim copy: " + name)
    common.copy_new(config.protocol, config.output / "inputs/protocol.json")
    common.copy_new(live_claim_path, config.output / "inputs/original-pipeline-claim.json")
    common.copy_new(config.interrupted_protocol, config.output / "inputs/interrupted-protocol.json")
    for path in sorted(config.interrupted_analysis.rglob("*")):
        if path.is_file():
            common.copy_new(path, config.output / "inputs/interrupted-analysis" / path.relative_to(config.interrupted_analysis))
    claim = {
        "schema": "conseqax-limbo-poststudy-claim-v1", "utc": common.utc(),
        "protocol_commit": config.protocol_commit,
        "protocol": {"path": str(config.protocol), **binding(config.protocol)},
        "original_pipeline_claim": {"path": str(live_claim_path), **binding(live_claim_path)},
        "original_pipeline_process": {"pid": config.pipeline_pid,
                                      "exact_create_time_epoch_seconds": config.pipeline_created_time},
        "source_files": sources, "python": {"path": str(config.python), **binding(config.python)},
        "original_paths": {name: str(getattr(config, name)) for name in
                           ("pipeline", "collection", "official_audit", "analysis", "native_root")},
        "new_outputs": {name: str(getattr(config, name)) for name in ("portable_audit_output", "manuscript_output")},
        "poll_interval_seconds": POLL_SECONDS, "collection_launches": 0,
        "interrupted_cohort": {"analysis_path": str(config.interrupted_analysis),
            "analysis_manifest": interrupted_manifest, "protocol_commit": config.interrupted_protocol_commit,
            "protocol": {"path": str(config.interrupted_protocol), **binding(config.interrupted_protocol)}},
        "both_cohorts_required": True, "cohorts_pooled": False,
        "model_requests": 0, "network_requests": 0, "process_control_actions": 0,
        "retries_resume_replacement_or_scheduling": False,
        "scope": "Dependent offline replay and static manuscript staging only; REVIEW_PENDING, no final PDF or acceptance claim",
    }
    require(binding(config.output / "inputs/protocol.json") == binding(config.protocol)
            and binding(config.output / "inputs/original-pipeline-claim.json") == binding(live_claim_path),
            "A pipeline/protocol input changed during claim copy")
    require(verify_manifest(config.interrupted_analysis) == interrupted_manifest
            and verify_manifest(config.output / "inputs/interrupted-analysis") == interrupted_manifest
            and binding(config.output / "inputs/interrupted-protocol.json") == binding(config.interrupted_protocol),
            "Original interrupted inputs changed during claim copy")
    write_new(config.output / "claim.json", claim)
    return claim, live_claim


def verify_sources(config, claim):
    for name, expected in claim["source_files"].items():
        require(binding(common.confined(config.root, name)) == expected, "Held poststudy source changed: " + name)
    for path, expected in ((config.protocol, claim["protocol"]),
                           (config.pipeline / "claim.json", claim["original_pipeline_claim"]),
                           (config.python, claim["python"])):
        require(binding(path) == {key: expected[key] for key in ("sha256", "bytes")},
                "A held poststudy runtime/input changed: " + str(path))
    require(verify_manifest(config.interrupted_analysis) == claim["interrupted_cohort"]["analysis_manifest"]
            and binding(config.interrupted_protocol) == {key: claim["interrupted_cohort"]["protocol"][key]
                for key in ("sha256", "bytes")}, "A retained interrupted-cohort input changed")


def observe_pipeline(config, original_claim):
    """Inspect only the original PID; no enumeration, signal, or control."""
    import psutil
    try:
        process = psutil.Process(config.pipeline_pid)
        actual = process.create_time()
        if actual != config.pipeline_created_time:
            return {"status": "pid_reused", "actual_create_time": actual}
        if not process.is_running() or process.status() in (psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE):
            return {"status": "pid_gone", "actual_create_time": actual}
        command = process.cmdline()
        def normalized(path):
            return os.path.normcase(os.path.abspath(path))
        expected_script = normalized(config.root / "scripts/run_limbo_completion_pipeline.py")
        expected_python = normalized(original_claim["python"]["path"])
        if not command or normalized(command[0]) != expected_python or expected_script not in {
                normalized(argument) for argument in command[1:] if not argument.startswith("--")}:
            return {"status": "command_identity_changed", "actual_create_time": actual}
        for flag, value in (("--output", str(config.pipeline)), ("--protocol", str(config.protocol))):
            if (flag not in command or command.index(flag) + 1 >= len(command)
                    or normalized(command[command.index(flag) + 1]) != normalized(value)):
                return {"status": "command_identity_changed", "actual_create_time": actual}
        if ("--protocol-commit" not in command or command.index("--protocol-commit") + 1 >= len(command)
                or command[command.index("--protocol-commit") + 1] != config.protocol_commit):
            return {"status": "command_identity_changed", "actual_create_time": actual}
        if process.create_time() != actual or not process.is_running():
            return {"status": "pid_changed_during_observation", "actual_create_time": actual}
        return {"status": "matching", "actual_create_time": actual}
    except psutil.NoSuchProcess:
        return {"status": "pid_gone"}
    except psutil.AccessDenied as exc:
        return {"status": "identity_unreadable", "error": type(exc).__name__ + ": " + str(exc)}


def has_terminal_seal(config):
    return ((config.pipeline / "terminal-result.json").is_file()
            and (config.pipeline / "manifest.json").is_file())


def wait_for_seal(config, claim, original_claim, journal, *, observer, sleeper):
    while True:
        verify_sources(config, claim)
        if has_terminal_seal(config):
            return
        observation = observer(config, original_claim)
        journal.append(event="pipeline_wait_observation", observation=observation,
                       terminal_present=(config.pipeline / "terminal-result.json").is_file(),
                       manifest_present=(config.pipeline / "manifest.json").is_file())
        if observation.get("status") != "matching":
            # The process can legitimately write its final seal and exit between
            # the first file check and PID read. Recheck before calling it interrupted.
            if has_terminal_seal(config):
                continue
            raise PipelineInterrupted("Original pipeline identity lost before seal: " + str(observation))
        sleeper(POLL_SECONDS)


def verify_original_chain(config):
    pipeline_manifest = verify_manifest(config.pipeline)
    terminal = load(config.pipeline / "terminal-result.json")
    require(terminal.get("schema") == "conseqax-limbo-completion-pipeline-terminal-v1"
            and terminal.get("artifact_chain_complete") is True
            and terminal.get("status") in ("complete", "complete_with_collection_process_error")
            and terminal.get("protocol_commit") == config.protocol_commit and terminal.get("error") is None,
            "Original pipeline did not complete its sealed artifact chain")
    stages = terminal.get("stages", [])
    require([stage.get("stage") for stage in stages] == ["collector", "audit", "pdf_marker", "analysis"]
            and all(stage.get("known_subprocess_closed") is True and type(stage.get("returncode")) is int for stage in stages)
            and all(stage["returncode"] == 0 for stage in stages[1:]),
            "Original pipeline has missing, open, or failed downstream stages")
    bindings = {name: verify_manifest(directory) for name, directory in (
        ("collection_manifest", config.collection), ("audit_manifest", config.official_audit),
        ("analysis_manifest", config.analysis))}
    require(all(terminal.get(key) == value for key, value in bindings.items()),
            "Original stage manifests differ from the sealed pipeline terminal")
    official = load(config.official_audit / "audit-result.json")
    require(official.get("schema") == "conseqax-limbo-audit-v1" and official.get("passed") is True
            and "portable_audit" not in official
            and official.get("protocol_commit") == config.protocol_commit
            and official.get("protocol") == binding(config.protocol)
            and official.get("collection_manifest") == bindings["collection_manifest"],
            "Original official audit does not bind this exact protocol and collection")
    analysis = load(config.analysis / "results.json")
    inputs = analysis.get("inputs", {})
    require(inputs.get("protocol_commit") == config.protocol_commit
            and inputs.get("collection_manifest") == bindings["collection_manifest"],
            "Original analysis protocol/collection provenance differs")
    for key, path in (("audit", config.official_audit / "audit-result.json"),
                      ("audit_manifest", config.official_audit / "manifest.json"), ("protocol", config.protocol)):
        require(inputs.get(key) == {"path": str(path), **binding(path)}, "Original analysis input differs: " + key)
    original_claim = load(config.pipeline / "claim.json")
    require(analysis.get("analysis_source") == original_claim["source_files"]["scripts/analyze_limbo_external_benchmark.py"],
            "Original analysis source differs from the original pipeline claim")
    return {"pipeline_manifest": pipeline_manifest, **bindings,
            "pipeline_terminal": binding(config.pipeline / "terminal-result.json"),
            "pipeline_exit_code": terminal["exit_code"]}, official


def child_environment(config):
    allow = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT",
             "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
    values = {key: value for key, value in os.environ.items() if key.upper() in allow}
    values.update(PYTHONPATH=str(config.root), PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUTF8="1")
    return values


def execute(config, claim, journal, name, command, records, runner):
    verify_sources(config, claim)
    record = {"stage": name, "command": command, "started_utc": common.utc(),
              "returncode": None, "known_subprocess_closed": False}
    records.append(record)
    journal.append(event="stage_enter", stage=name, command=command)
    stdout_path, stderr_path = [config.output / (name + suffix) for suffix in (".stdout.log", ".stderr.log")]
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            try:
                completed = runner(command, cwd=str(config.root), env=child_environment(config), stdout=stdout, stderr=stderr)
                require(type(completed.returncode) is int, "A concrete dependent-work exit code is required")
                record["returncode"], record["known_subprocess_closed"] = completed.returncode, True
            except OSError:
                record["known_subprocess_closed"] = True
                raise
            finally:
                for stream in (stdout, stderr):
                    stream.flush()
                    os.fsync(stream.fileno())
    except BaseException as exc:
        record["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        record.update(ended_utc=common.utc(), stdout={"path": stdout_path.name, **binding(stdout_path)},
                      stderr={"path": stderr_path.name, **binding(stderr_path)})
        journal.append(event="stage_return" if record["known_subprocess_closed"] else "stage_terminal_unknown", **record)
    return record["returncode"]


def run(config, *, runner=common.default_runner, observer=observe_pipeline, sleeper=time.sleep):
    config = config.resolved()
    validate_paths(config)
    config.output.mkdir(parents=True, exist_ok=False)
    journal = common.Journal(config.output / "events.jsonl")
    stages = []
    result = {"schema": "conseqax-limbo-poststudy-terminal-v1", "started_utc": common.utc(),
              "status": "PREFLIGHT_FAILED", "paper_stage": "NOT_PREPARED", "exit_code": 1,
              "protocol_commit": config.protocol_commit, "stages": stages, "error": None,
              "new_model_calls": 0, "new_pdf_created": False, "official_collection_restart": False,
              "final_pdf_or_conference_acceptance_claim": False}
    try:
        claim, original_claim = prepare_claim(config)
        journal.append(event="claim_sealed", binding=binding(config.output / "claim.json"))
        result["status"] = "WAITING_FOR_ORIGINAL_PIPELINE"
        wait_for_seal(config, claim, original_claim, journal, observer=observer, sleeper=sleeper)
        result["status"] = "ORIGINAL_PIPELINE_INTEGRITY_CHECK"
        original, official = verify_original_chain(config)
        result["original_chain"] = original
        journal.append(event="original_pipeline_chain_verified", bindings=original)
        portable_command = [str(config.python), "-B", str(config.root / "scripts/audit_limbo_portable.py"),
            "--native-root", str(config.native_root), "--protocol", str(config.protocol),
            "--protocol-commit", config.protocol_commit, "--collection", str(config.collection),
            "--compare-official", str(config.official_audit / "audit-result.json"),
            "--output", str(config.portable_audit_output)]
        result["status"] = "PORTABLE_AUDIT_FAILED"
        require(execute(config, claim, journal, "portable_audit", portable_command, stages, runner) == 0,
                "Portable audit returned a nonzero exit code; no manuscript stage")
        result["portable_audit_manifest"] = verify_manifest(config.portable_audit_output)
        portable = load(config.portable_audit_output / "audit-result.json")
        require(portable.get("schema") == "conseqax-limbo-audit-v1" and portable.get("passed") is True
                and portable.get("portable_audit", {}).get("schema") == "conseqax-limbo-portable-audit-v1",
                "Portable replay did not produce a passed bound audit")
        for key in ("schema", "passed", "protocol_commit", "protocol", "collection_manifest", "rows", "summary", "scope"):
            require(portable.get(key) == official.get(key), "Portable/original official semantics differ: " + key)
        comparison = portable["portable_audit"].get("comparison_to_original_official", {})
        require(comparison.get("semantic_agreement") is True
                and comparison.get("original_official_audit_remains_first_authority") is True
                and comparison.get("path") == str(config.official_audit / "audit-result.json")
                and {key: comparison.get(key) for key in ("sha256", "bytes")}
                    == binding(config.official_audit / "audit-result.json"),
                "Portable replay lacks exact agreement with the first-authority original audit")
        manuscript_command = [str(config.python), "-B", str(config.root / "scripts/prepare_final_limbo_manuscript.py"),
            "--analysis", str(config.analysis), "--protocol", str(config.protocol),
            "--protocol-commit", config.protocol_commit,
            "--interrupted-analysis", str(config.interrupted_analysis),
            "--interrupted-protocol", str(config.interrupted_protocol),
            "--interrupted-protocol-commit", config.interrupted_protocol_commit,
            "--output", str(config.manuscript_output)]
        result["status"] = "MANUSCRIPT_PREPARATION_FAILED"
        require(execute(config, claim, journal, "prepare_manuscript", manuscript_command, stages, runner) == 0,
                "Manuscript preparation returned a nonzero exit code")
        result["manuscript_manifest"] = verify_manifest(config.manuscript_output)
        prepared = load(config.manuscript_output / "preparation-receipt.json")
        require(prepared.get("schema") == "conseqax-final-paper-preparation-v1"
                and prepared.get("status") == "REVIEW_PENDING"
                and prepared.get("visual_review_pending") is True
                and prepared.get("proposed_sources_require_lead_review") is True
                and prepared.get("new_model_calls") == 0 and prepared.get("new_pdf_created") is False,
                "Static manuscript must retain review-pending status with no new inference/PDF claim")
        require(prepared.get("protocol_commit") == config.protocol_commit
                and prepared.get("protocol") == binding(config.protocol)
                and prepared.get("analysis_manifest") == original["analysis_manifest"],
                "Prepared manuscript provenance differs from the completed original analysis")
        require(prepared.get("both_cohorts_retained_separately") is True and prepared.get("cohorts_pooled") is False
                and prepared.get("interrupted_cohort", {}).get("protocol_commit") == config.interrupted_protocol_commit
                and prepared["interrupted_cohort"].get("analysis_manifest")
                    == claim["interrupted_cohort"]["analysis_manifest"],
                "Prepared manuscript must retain the original interrupted denominator separately")
        verify_sources(config, claim)
        after, _ = verify_original_chain(config)
        require(after == original, "An original sealed artifact changed during dependent work")
        require(verify_manifest(config.portable_audit_output) == result["portable_audit_manifest"],
                "Portable audit changed during manuscript staging")
        result.update(status="REVIEW_PENDING", paper_stage="REVIEW_PENDING", exit_code=0)
    except BaseException as exc:
        if isinstance(exc, PipelineInterrupted):
            result["status"] = "ORIGINAL_PIPELINE_INTERRUPTED"
        elif result["status"] == "WAITING_FOR_ORIGINAL_PIPELINE":
            result["status"] = "ORIGINAL_PIPELINE_WAIT_FAILED"
        result["error"] = type(exc).__name__ + ": " + str(exc)
        journal.append(event="dependent_work_stopped", status=result["status"], error=result["error"])
    finally:
        result["ended_utc"] = common.utc()
        known_closed = all(stage["known_subprocess_closed"] for stage in stages)
        journal.append(event="poststudy_exit" if known_closed else "poststudy_interrupted_unsealed",
                       status=result["status"], paper_stage=result["paper_stage"], exit_code=result["exit_code"],
                       all_dependent_children_known_closed=known_closed)
        journal.close()
        if known_closed:
            write_new(config.output / "terminal-result.json", result)
            write_new(config.output / "manifest.json", {path.relative_to(config.output).as_posix(): binding(path)
                for path in sorted(config.output.rglob("*")) if path.is_file()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("pipeline", "protocol", "collection", "official-audit", "analysis", "native-root", "output",
                 "portable-audit-output", "manuscript-output", "interrupted-analysis", "interrupted-protocol"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--pipeline-pid", required=True, type=int)
    parser.add_argument("--pipeline-created-time", required=True, type=float)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--interrupted-protocol-commit", required=True)
    args = parser.parse_args()
    result = run(Config(root=ROOT, **vars(args)))
    print(json.dumps({"status": result["status"], "paper_stage": result["paper_stage"],
                      "exit_code": result["exit_code"], "error": result["error"]}, sort_keys=True))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
