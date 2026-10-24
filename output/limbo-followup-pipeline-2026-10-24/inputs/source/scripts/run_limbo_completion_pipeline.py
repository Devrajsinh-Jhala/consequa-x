"""Run one published LIMBO collection, independent audit, then real analysis.

This auxiliary orchestrator performs no model operation except the single existing
collector subprocess. It never retries, resumes, replaces a slot, changes Git or
Actions, contacts a paid provider, grades a task, or controls an existing process.
Only the explicitly supplied observer stop flag is created in its finalizer.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
NODE = Path("C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
PDF_MARKER = Path("C:/Users/DELL/.codex/plugins/cache/openai-primary-runtime/pdf/26.1022.11436/skills/pdf/container_tools/mark_artifact_operation_started.mjs")
FIGURE_DEPENDENCIES = Path("D:/ConsequaX-Research/figure-dependencies")
MPL_CACHE = Path("D:/ConsequaX-Research/figure-matplotlib-cache")
STAGE_SOURCES = {
    "collector": "scripts/run_limbo_external_benchmark.py",
    "audit": "scripts/audit_limbo_external_benchmark.py",
    "analysis": "scripts/analyze_limbo_external_benchmark.py",
    "pipeline": "scripts/run_limbo_completion_pipeline.py",
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": Path(path).stat().st_size}


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON: " + value)))


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def copy_new(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Path(source).open("rb") as original, destination.open("xb") as copied:
        for chunk in iter(lambda: original.read(1024 * 1024), b""):
            copied.write(chunk)
        copied.flush()
        os.fsync(copied.fileno())


def confined(directory, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts, "Unsafe manifest/source path")
    target = directory / relative
    require(not target.is_symlink() and directory in target.resolve().parents,
            "A manifest/source path escapes its directory or is a symlink")
    return target


def verify_manifest(directory):
    directory = Path(directory).resolve()
    manifest = load(directory / "manifest.json")
    require(type(manifest) is dict, "A sealed manifest must be a file-binding map")
    actual = set()
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "Artifact symlinks are refused")
        if path.is_file() and path != directory / "manifest.json":
            actual.add(path.relative_to(directory).as_posix())
    require(set(manifest) == actual, "Sealed artifact inventory differs")
    for relative, expected in manifest.items():
        require(binding(confined(directory, relative)) == expected,
                "Sealed artifact bytes differ: " + relative)
    return binding(directory / "manifest.json")


class Journal:
    def __init__(self, path):
        self.stream = Path(path).open("x", encoding="utf-8", newline="\n")

    def append(self, **event):
        self.stream.write(json.dumps({"utc": utc(), **event}, sort_keys=True, allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


@dataclass(frozen=True)
class Config:
    root: Path
    native_root: Path
    protocol: Path
    protocol_commit: str
    output: Path
    collection_output: Path
    audit_output: Path
    analysis_output: Path
    observer_stop_file: Path
    node: Path = NODE
    pdf_marker: Path = PDF_MARKER
    figure_dependencies: Path = FIGURE_DEPENDENCIES
    mpl_config_dir: Path = MPL_CACHE
    python: Path = Path(sys.executable)

    def resolved(self):
        root = self.root.resolve()
        fields = {}
        for key in self.__dataclass_fields__:
            if key in ("root", "protocol_commit"):
                continue
            value = Path(getattr(self, key))
            fields[key] = (root / value).resolve() if not value.is_absolute() else value.resolve()
        return replace(self, root=root, **fields)


def validate_stop_flag(config):
    artifact_root = config.root / "output"
    outputs = (config.output, config.collection_output, config.audit_output, config.analysis_output)
    flag = config.observer_stop_file
    require(artifact_root in flag.parents and flag.suffix == ".flag",
            "The explicit observer stop flag must be a .flag file under this research workspace's output directory")
    require(not flag.is_symlink(), "Observer stop-flag symlinks are refused")
    require(all(flag != path and path not in flag.parents for path in outputs),
            "The observer stop flag cannot be inside any sealed stage output")
    require(flag.parent.is_dir(), "The observer stop flag's parent must already exist")


def validate_paths(config):
    require(re.fullmatch(r"[0-9a-f]{40}", config.protocol_commit) is not None,
            "An exact 40-character published protocol commit is required")
    artifact_root = config.root / "output"
    outputs = (config.output, config.collection_output, config.audit_output, config.analysis_output)
    for path in outputs:
        require(artifact_root in path.parents, "New artifacts must stay inside this research workspace's output directory")
        require(not path.exists(), "A new one-shot output directory is required: " + str(path))
        require(not path.is_symlink(), "Output symlinks are refused")
        require(path != config.protocol and path not in config.protocol.parents,
                "An output must not contain the input protocol")
    for index, first in enumerate(outputs):
        for second in outputs[index + 1:]:
            require(first != second and first not in second.parents and second not in first.parents,
                    "Pipeline, collection, audit, and analysis directories must be distinct and disjoint")


def environment(config):
    allow = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT",
             "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)")
    result = {key: value for key, value in os.environ.items() if key.upper() in allow}
    result.update(PYTHONPATH=os.pathsep.join((str(config.root), str(config.figure_dependencies))),
                  MPLCONFIGDIR=str(config.mpl_config_dir), PYTHONDONTWRITEBYTECODE="1",
                  PYTHONNOUSERSITE="1", PYTHONUTF8="1", NO_PROXY="127.0.0.1,localhost",
                  no_proxy="127.0.0.1,localhost")
    return result


def prepare_claim(config):
    require(config.native_root.is_dir(), "The pinned native source directory is absent")
    require(config.figure_dependencies.is_dir(), "The existing figure dependency directory is absent")
    require(not config.observer_stop_file.exists(), "The observer stop flag already exists")
    protocol = load(config.protocol)
    sources = protocol["sources"]
    require(type(sources) is dict and bool(sources), "The frozen execution-source binding is absent")
    files = {}
    for relative, expected in sources.items():
        actual = binding(confined(config.root, relative))
        require(actual == expected, "Execution source differs from the frozen protocol: " + relative)
        files[relative] = actual
    for relative in STAGE_SOURCES.values():
        files[relative] = binding(confined(config.root, relative))
    protocol_binding = binding(config.protocol)
    copy_new(config.protocol, config.output / "inputs/protocol.json")
    for relative, expected in files.items():
        target = config.output / "inputs/source" / relative
        copy_new(confined(config.root, relative), target)
        require(binding(target) == expected, "Source changed during provenance copying: " + relative)
    require(binding(config.output / "inputs/protocol.json") == protocol_binding,
            "Protocol changed during provenance copying")
    claim = {
        "schema": "conseqax-limbo-one-shot-completion-pipeline-v1", "created_utc": utc(),
        "protocol_commit": config.protocol_commit,
        "protocol": {"path": str(config.protocol), **protocol_binding},
        "source_files": files,
        "native_root": str(config.native_root),
        "python": {"path": str(config.python), **binding(config.python)},
        "node": {"path": str(config.node), **binding(config.node)},
        "pdf_marker": {"path": str(config.pdf_marker), **binding(config.pdf_marker)},
        "outputs": {key: str(getattr(config, key)) for key in
                    ("collection_output", "audit_output", "analysis_output")},
        "observer_stop_file": str(config.observer_stop_file),
        "figure_dependencies": str(config.figure_dependencies),
        "mpl_config_dir": str(config.mpl_config_dir),
        "one_shot": {"collector_attempts": 1, "retry": False, "resume": False,
                     "replacement": False, "slot_selection": False},
        "publication_verification": "Exact commit supplied by operator; existing collector and auditor independently verify Git-bound protocol before collection/audit; no Git operation is implemented by this orchestrator",
        "scope": "Collection, independent audit, and three figure PDFs only; no manuscript completion or visual-quality claim",
    }
    write_new(config.output / "claim.json", claim)
    return claim


def verify_claim(config, claim):
    require(binding(config.protocol) == {key: claim["protocol"][key] for key in ("sha256", "bytes")},
            "The claimed protocol changed")
    for relative, expected in claim["source_files"].items():
        require(binding(confined(config.root, relative)) == expected,
                "A claimed execution or stage source changed: " + relative)
    for key in ("python", "node", "pdf_marker"):
        require(binding(getattr(config, key)) == {field: claim[key][field] for field in ("sha256", "bytes")},
                "A claimed stage runtime/marker changed: " + key)


def default_runner(command, **kwargs):
    # Unlike subprocess.run's exception cleanup, this wrapper never kills a
    # child. An interrupted wait has unknown child liveness and is deliberately
    # left unsealed by execute_stage; later preservation must retain that fact.
    process = subprocess.Popen(command, **kwargs)
    return subprocess.CompletedProcess(command, process.wait())


def execute_stage(config, claim, journal, name, command, records, runner):
    verify_claim(config, claim)
    started = time.monotonic()
    record = {"stage": name, "command": command, "returncode": None,
              "started_utc": utc(), "known_subprocess_closed": False}
    records.append(record)
    journal.append(event="stage_enter", stage=name, command=command)
    stdout_path = config.output / (name + ".stdout.log")
    stderr_path = config.output / (name + ".stderr.log")
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            try:
                completed = runner(command, cwd=str(config.root), env=environment(config),
                                   stdout=stdout, stderr=stderr)
                require(type(completed.returncode) is int, "Subprocess did not return a concrete exit code")
                record["returncode"] = completed.returncode
                record["known_subprocess_closed"] = True
            except OSError:
                # Popen/run raises OSError when the requested executable cannot
                # be spawned. There is no running child to manufacture an exit for.
                record["known_subprocess_closed"] = True
                raise
            finally:
                stdout.flush()
                stderr.flush()
                os.fsync(stdout.fileno())
                os.fsync(stderr.fileno())
    except BaseException as exc:
        record["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        record.update(ended_utc=utc(), wall_s=time.monotonic() - started,
                      stdout={"path": stdout_path.name, **binding(stdout_path)},
                      stderr={"path": stderr_path.name, **binding(stderr_path)})
        journal.append(event="stage_return" if record["known_subprocess_closed"] else "stage_interrupted_terminal_unknown", **record)
    return record["returncode"]


def stop_observer(flag):
    result = {"path": str(flag), "created": False, "already_present": False}
    try:
        with flag.open("xb") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        result["created"] = True
    except FileExistsError:
        result["already_present"] = True
    return result


def run(config, *, runner=default_runner):
    config = config.resolved()
    # Invalid paths never authorize touching an arbitrary file. Once validated,
    # every normal/error path creates only this explicit observer stop flag.
    validate_stop_flag(config)
    try:
        validate_paths(config)
        config.output.mkdir(parents=True, exist_ok=False)
        journal = Journal(config.output / "events.jsonl")
    except BaseException:
        # No output is overwritten and no terminal is invented if a new journal
        # could not be opened, but the safely validated observer is still stopped.
        stop_observer(config.observer_stop_file)
        raise
    records = []
    result = {"schema": "conseqax-limbo-completion-pipeline-terminal-v1", "started_utc": utc(),
              "protocol_commit": config.protocol_commit, "status": "preflight_failed", "exit_code": 1,
              "artifact_chain_complete": False, "stages": records, "error": None}
    try:
        journal.append(event="pipeline_enter", protocol_commit=config.protocol_commit)
        claim = prepare_claim(config)
        journal.append(event="claim_sealed", binding=binding(config.output / "claim.json"))
        python = str(config.python)
        collector = [python, "-B", str(config.root / STAGE_SOURCES["collector"]), "collect",
                     "--native-root", str(config.native_root), "--protocol", str(config.protocol),
                     "--protocol-commit", config.protocol_commit, "--output", str(config.collection_output)]
        collection_code = execute_stage(config, claim, journal, "collector", collector, records, runner)
        result["status"] = "collection_unsealed"
        require((config.collection_output / "manifest.json").is_file(),
                "Collector left no sealed collection manifest; no audit, analysis, or retry is permitted")
        collection_binding = verify_manifest(config.collection_output)
        result["collection_manifest"] = collection_binding
        journal.append(event="collection_seal_verified", binding=collection_binding,
                       collector_exit_code=collection_code)
        auditor = [python, "-B", str(config.root / STAGE_SOURCES["audit"]),
                   "--native-root", str(config.native_root), "--protocol", str(config.protocol),
                   "--protocol-commit", config.protocol_commit, "--collection", str(config.collection_output),
                   "--output", str(config.audit_output)]
        result["status"] = "audit_failed"
        require(execute_stage(config, claim, journal, "audit", auditor, records, runner) == 0,
                "Independent auditor returned a nonzero exit code")
        result["audit_manifest"] = verify_manifest(config.audit_output)
        audit = load(config.audit_output / "audit-result.json")
        require(audit.get("schema") == "conseqax-limbo-audit-v1" and audit.get("passed") is True,
                "The independent audit did not pass")
        require(audit.get("protocol_commit") == config.protocol_commit
                and audit.get("protocol") == binding(config.protocol)
                and audit.get("collection_manifest") == collection_binding,
                "The passed audit does not bind this exact protocol and collection")
        require(verify_manifest(config.collection_output) == collection_binding,
                "The collection changed after independent audit")
        journal.append(event="passed_audit_seal_verified", binding=result["audit_manifest"])
        marker = [str(config.node), str(config.pdf_marker), "--operation-kind", "create",
                  "--expected-output-count", "3", "--output-format", "pdf"]
        result["status"] = "figure_marker_failed"
        require(execute_stage(config, claim, journal, "pdf_marker", marker, records, runner) == 0,
                "Required PDF authoring marker did not succeed; figures were not generated")
        analyzer = [python, "-B", str(config.root / STAGE_SOURCES["analysis"]),
                    "--audit", str(config.audit_output / "audit-result.json"),
                    "--protocol", str(config.protocol), "--protocol-commit", config.protocol_commit,
                    "--output", str(config.analysis_output)]
        result["status"] = "analysis_failed"
        require(execute_stage(config, claim, journal, "analysis", analyzer, records, runner) == 0,
                "Analyzer returned a nonzero exit code")
        result["analysis_manifest"] = verify_manifest(config.analysis_output)
        analysis = load(config.analysis_output / "results.json")
        pdfs = [name for name in analysis.get("figures", []) if Path(name).suffix == ".pdf"]
        require(analysis.get("figures_generated") is True and len(pdfs) == len(set(pdfs)) == 3,
                "Analysis did not produce exactly the three declared figure PDFs")
        for name in pdfs:
            require(confined(config.analysis_output, name).is_file(), "A declared PDF figure is absent")
        require({path.relative_to(config.analysis_output).as_posix()
                 for path in config.analysis_output.rglob("*.pdf")} == set(pdfs),
                "The actual PDF inventory differs from the three marked figures")
        require(analysis.get("inputs", {}).get("protocol_commit") == config.protocol_commit
                and analysis["inputs"].get("collection_manifest") == collection_binding,
                "Analysis provenance differs from the audited collection")
        for key, path in (("audit", config.audit_output / "audit-result.json"),
                          ("audit_manifest", config.audit_output / "manifest.json"),
                          ("protocol", config.protocol)):
            require(analysis["inputs"].get(key) == {"path": str(path), **binding(path)},
                    "Analysis input provenance differs: " + key)
        require(analysis.get("analysis_source") == claim["source_files"][STAGE_SOURCES["analysis"]],
                "The analysis result does not bind the claimed analyzer source")
        require(verify_manifest(config.collection_output) == collection_binding,
                "The collection changed after analysis")
        require(verify_manifest(config.audit_output) == result["audit_manifest"],
                "The passed audit changed after analysis")
        verify_claim(config, claim)
        result["artifact_chain_complete"] = True
        result["status"] = "complete" if collection_code == 0 else "complete_with_collection_process_error"
        result["exit_code"] = 0 if collection_code == 0 else 1
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        journal.append(event="pipeline_error", status=result["status"], error=result["error"])
    finally:
        try:
            result["observer_stop"] = stop_observer(config.observer_stop_file)
        except OSError as exc:
            result["observer_stop"] = {"path": str(config.observer_stop_file),
                                       "error": type(exc).__name__ + ": " + str(exc)}
            result["exit_code"] = 1
        result["ended_utc"] = utc()
        known_closed = all(record["known_subprocess_closed"] for record in records)
        journal.append(event="pipeline_exit" if known_closed else "pipeline_interrupted_unsealed",
                       status=result["status"], exit_code=result["exit_code"],
                       observer_stop=result["observer_stop"], all_stage_children_known_closed=known_closed)
        journal.close()
        if known_closed:
            write_new(config.output / "terminal-result.json", result)
            manifest = {path.relative_to(config.output).as_posix(): binding(path)
                        for path in sorted(config.output.rglob("*")) if path.is_file()}
            write_new(config.output / "manifest.json", manifest)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--collection-output", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    parser.add_argument("--analysis-output", required=True, type=Path)
    parser.add_argument("--observer-stop-file", required=True, type=Path)
    parser.add_argument("--node", type=Path, default=NODE)
    parser.add_argument("--pdf-marker", type=Path, default=PDF_MARKER)
    parser.add_argument("--figure-dependencies", type=Path, default=FIGURE_DEPENDENCIES)
    parser.add_argument("--mpl-config-dir", type=Path, default=MPL_CACHE)
    args = parser.parse_args()
    config = Config(root=ROOT, **vars(args)).resolved()
    result = run(config)
    print(json.dumps({"status": result["status"], "exit_code": result["exit_code"],
                      "artifact_chain_complete": result["artifact_chain_complete"],
                      "output": str(config.output)}, sort_keys=True))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
