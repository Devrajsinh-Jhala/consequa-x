"""Strict portable offline replay of a sealed LIMBO collection.

Historical runtime/interpreter/wheel paths are provenance, not replay inputs.
The explicitly committed scientific code and every pinned native Python source
remain byte-bound. No SDK, model weights, tokenizer or live server is required.
This reproduces saved trajectories; it is not an external replication study.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
from types import ModuleType
import uuid


ROOT = Path(__file__).resolve().parents[1]
PIN = "2db09fba22a0572a70639162a808906409f612a8"
ARMS = ("vanilla", "sdk_retry3", "guard", "conseqax_guard")
SCOPE = {"independent_native_policy_and_effect_replay": True,
    "conseqax_guard_replayed_as_declared_native_guard": True,
    "SDK_receipt_current_public_report_mapping_recomputation": True,
    "SDK_execution_or_independent_service_verifier_replay": False,
    "saved_context_render_token_proof_consistency": True,
    "independent_tokenizer_reconstruction": False,
    "human_or_network_used": False,
    "passed_means_all_slots_operational_or_successful": False}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def same(left, right, message):
    require(canonical(left) == canonical(right), message)


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON: " + value)))


def binding(path):
    data = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def git(root, *args):
    environment = {**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", "-c", "protocol.allow=never", "-C", str(root), *args],
                          check=True, capture_output=True, env=environment).stdout


def safe_file(root, name):
    require(type(name) is str and "\\" not in name and ":" not in name,
            "Nonportable or unsafe bound relative path")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and bool(relative.parts) and ".." not in relative.parts
            and relative.as_posix() == name, "Unsafe bound relative path")
    path = Path(root) / Path(*relative.parts)
    require(path.resolve().is_relative_to(Path(root).resolve()), "Bound file escapes its root")
    require(path.is_file() and not path.is_symlink(), "Missing or symbolic bound file: " + name)
    return path


def verify_files(root, expected):
    require(type(expected) is dict and bool(expected), "Empty immutable file binding")
    for name, identity in expected.items():
        same(binding(safe_file(root, name)), identity, "Immutable file changed: " + name)


def sealed_manifest(directory):
    directory = Path(directory).resolve()
    manifest_path = directory / "manifest.json"
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "Sealed manifest is missing")
    expected = load(manifest_path)
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*")
              if path.is_file() and path != manifest_path}
    require(type(expected) is dict and set(expected) == actual, "Sealed manifest inventory differs")
    for name, identity in expected.items():
        same(binding(safe_file(directory, name)), identity, "Sealed file changed: " + name)
    return expected


def verify_protocol_bytes(source_root, native_root, path, commit):
    """Bootstrap with stdlib only, before executing any frozen audit/native code."""
    source_root, native_root = Path(source_root).resolve(), Path(native_root).resolve()
    path = Path(path).resolve()
    require(bool(re.fullmatch("[0-9a-f]{40}", commit)), "An explicit exact 40-character protocol commit is required")
    relative = path.relative_to(source_root).as_posix()
    blob = git(source_root, "show", f"{commit}:{relative}")
    require(blob == path.read_bytes(), "Protocol differs from its explicit Git commit")
    value = load(path)
    require(value.get("schema") == "conseqax-limbo-protocol-v1"
            and value.get("native", {}).get("commit") == PIN, "Unsupported protocol/native pin")
    require(value.get("arms") == list(ARMS), "Protocol arms differ")
    verify_files(source_root, value["sources"])
    for name, identity in value["sources"].items():
        committed = git(source_root, "show", f"{commit}:{name}")
        same({"sha256": hashlib.sha256(committed).hexdigest(), "bytes": len(committed)}, identity,
             "Scientific source is not the committed frozen bytes: " + name)
    for name in ("research/limbo_agent/audit.py", "research/limbo_agent/protocol.py"):
        require(name in value["sources"], "Frozen independent audit source is missing: " + name)
    require(git(native_root, "rev-parse", "HEAD").decode().strip() == PIN,
            "Native checkout HEAD differs from the exact declared upstream pin")
    tracked = {name for name in git(native_root, "ls-tree", "-r", "--name-only", PIN, "limbo").decode().splitlines()
               if name.endswith(".py")}
    require(tracked == set(value["native"]["files"]), "Pinned native implementation inventory differs")
    actual = {path.relative_to(native_root).as_posix() for path in (native_root / "limbo").rglob("*.py")}
    require(actual == tracked, "Native Python namespace contains extra or missing implementation files")
    verify_files(native_root, value["native"]["files"])
    for name in tracked:
        committed = git(native_root, "show", f"{PIN}:{name}")
        current = safe_file(native_root, name).read_bytes()
        # Preserve the original native pin check's newline convention while
        # still requiring exact recorded byte hashes above (no coercion).
        require(committed.replace(b"\r\n", b"\n") == current.replace(b"\r\n", b"\n"),
                "Native implementation differs from its pinned Git source: " + name)
    return value


@contextmanager
def frozen_auditor(source_root):
    """Load only the already-verified protocol/audit; never collector or SDK."""
    prefix = "_conseqax_portable_frozen_" + uuid.uuid4().hex
    package = ModuleType(prefix)
    package.__path__ = [str(Path(source_root) / "research/limbo_agent")]
    names = [prefix, prefix + ".protocol", prefix + ".audit"]
    sys.modules[prefix] = package
    try:
        modules = {}
        for name in ("protocol", "audit"):
            path = Path(source_root) / "research/limbo_agent" / (name + ".py")
            spec = importlib.util.spec_from_file_location(prefix + "." + name, path)
            require(spec is not None and spec.loader is not None, "Cannot load frozen audit source")
            module = importlib.util.module_from_spec(spec)
            sys.modules[prefix + "." + name] = module
            # Execute the verified source itself, without trusting a stale or
            # foreign __pycache__ compiled under another interpreter.
            exec(compile(path.read_bytes(), str(path), "exec", dont_inherit=True), module.__dict__)
            modules[name] = module
        yield modules["protocol"], modules["audit"]
    finally:
        for name in names:
            sys.modules.pop(name, None)


@contextmanager
def bound_native_imports(native_root, files):
    """Compile bound native source bytes directly; never reuse bytecode caches."""
    root = Path(native_root).resolve()
    class SourceLoader(importlib.machinery.SourceFileLoader):
        def get_code(self, fullname):
            path = Path(self.path)
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
            same({"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}, files[relative],
                 "Native source changed at import: " + relative)
            return compile(data, str(path), "exec", dont_inherit=True)
    class SourceFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname != "limbo" and not fullname.startswith("limbo."):
                return None
            base = Path(*fullname.split("."))
            module_name = base.as_posix() + ".py"
            package_name = (base / "__init__.py").as_posix()
            relative = package_name if package_name in files else module_name
            require(relative in files, "Import outside the pinned native Python inventory: " + fullname)
            source = safe_file(root, relative)
            return importlib.util.spec_from_file_location(fullname, source,
                loader=SourceLoader(fullname, str(source)),
                submodule_search_locations=[str(source.parent)] if relative == package_name else None)
    finder = SourceFinder()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)


def validate_schedule(value, frozen_protocol, source_root):
    same(value["sources"], frozen_protocol.source_binding(source_root), "Scientific Python namespace inventory changed")
    schedule = value["schedule"]
    require(type(schedule) is list and len(schedule) == 96 and len(value["metadata"]) == 12,
            "The registered matrix must retain all 96 slots and 12 base templates")
    expected = frozen_protocol.make_schedule(value["metadata"], world_count=24,
        model=value["runtime_binding"]["model"], max_tool_calls=schedule[0]["spec"]["max_tool_calls"],
        seed=value["seed"])
    same(schedule, expected, "Schedule differs from registered metadata-only selection")
    require(len({(row["metadata"]["template"], row["metadata"]["index"]) for row in schedule}) == 12,
            "Registered base-instance count differs")


def validate_collection(collection, value, protocol_path, commit):
    collection = Path(collection).resolve()
    inventory = sealed_manifest(collection)
    same(load(collection / "protocol.json"), value, "Collection protocol differs")
    claim = load(collection / "claim.json")
    require(claim.get("protocol_commit") == commit
            and claim.get("protocol_sha256") == binding(protocol_path)["sha256"]
            and claim.get("retry_resume_replacement") is False,
            "Collection one-shot claim/protocol binding differs")
    record = load(collection / "collection.json")
    require(record.get("schema") == "conseqax-limbo-collection-v1"
            and record.get("protocol_commit") == commit, "Collection schema/commit differs")
    require(type(record.get("rows")) is list and len(record["rows"]) == len(value["schedule"]),
            "Collection omitted planned dispositions")
    allowed_top = {"claim.json", "protocol.json", "collection.json", "manifest.json"}
    stopped = False
    for planned, disposition in zip(value["schedule"], record["rows"]):
        for key in ("slot", "world_rank", "arm"):
            require(type(disposition.get(key)) is type(planned[key]) and disposition.get(key) == planned[key],
                    "Collection slot identity/order differs")
        status = disposition.get("status")
        directory_name = f"slot-{planned['slot']:03d}"
        disposition_name = f"disposition-{planned['slot']:03d}.json"
        if status == "unstarted_integrity_stop":
            stopped = True
            require(type(record.get("integrity_stop")) is str and bool(record["integrity_stop"])
                    and type(disposition.get("reason")) is str and bool(disposition["reason"])
                    and "directory" not in disposition, "Unstarted disposition lacks the recorded integrity stop")
            require(not (collection / directory_name).exists() and not (collection / disposition_name).exists(),
                    "Unstarted disposition has started slot artifacts")
            continue
        require(not stopped, "Started slot appears after the one-shot integrity stop")
        require(status in ("child_returned", "child_failed", "parent_deadline"), "Unknown collection disposition")
        require(disposition.get("directory") == directory_name, "Unsafe or mismatched slot directory")
        require(type(disposition.get("exit_code")) is int
                and (status == "parent_deadline" or
                     ((status == "child_returned") == (disposition["exit_code"] == 0))),
                "Parent status/exit code differs")
        allowed_top.update((directory_name, disposition_name))
        same(load(collection / disposition_name), disposition, "Disposition receipt differs from collection")
        slot_directory = collection / directory_name
        require(slot_directory.is_dir() and not slot_directory.is_symlink(), "Slot directory is missing/symbolic")
        sealed_manifest(slot_directory)
        same(load(slot_directory / "parent-terminal.json"), disposition, "Parent terminal differs from disposition")
        same(load(slot_directory / "worker-config.json"), {"protocol": value, "slot": planned},
             "Worker configuration differs from the frozen slot/protocol")
    require(stopped == (record.get("integrity_stop") is not None), "Collection integrity-stop state differs")
    if stopped:
        require(record["rows"][-1]["reason"] == record["integrity_stop"],
                "Final integrity-stop reason differs from the last recorded disposition")
    require({path.name for path in collection.iterdir()} == allowed_top, "Unplanned top-level collection artifact")
    return record, inventory


def check_native_imports(native_root, native_files):
    root = Path(native_root).resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "limbo" and not name.startswith("limbo."):
            continue
        origin = getattr(module, "__file__", None)
        require(origin is not None, "Native module lacks an inspectable source origin")
        path = Path(origin).resolve()
        require(path.is_relative_to(root), "A native module was imported from outside the pinned checkout")
        relative = path.relative_to(root).as_posix()
        require(relative in native_files, "Imported native implementation is outside the bound inventory")
        same(binding(path), native_files[relative], "Loaded native module source changed")


def current_environment():
    value = {"python_version": sys.version, "implementation": sys.implementation.name,
        "platform": platform.platform(), "machine": platform.machine(),
        "executable": {"path": sys.executable}, "SDK_installation_required": False,
        "third_party_replay_dependencies_required": [],
        "historical_environment_equality_required": False}
    if sys.executable and Path(sys.executable).is_file():
        value["executable"].update(binding(sys.executable))
    return value


def compare_official(path, result):
    path = Path(path).resolve()
    if path.is_dir():
        path /= "audit-result.json"
    manifest = sealed_manifest(path.parent)
    require(set(manifest) == {path.name}, "Official audit manifest inventory differs")
    official = load(path)
    require(official.get("schema") == "conseqax-limbo-audit-v1" and official.get("passed") is True,
            "Comparison requires the passed original official audit")
    require("portable_audit" not in official, "A portable audit cannot substitute for the original official audit")
    for key in ("schema", "passed", "protocol_commit", "protocol", "collection_manifest", "rows", "summary", "scope"):
        same(result[key], official.get(key), "Portable/original official audit differs: " + key)
    return {"path": str(path), **binding(path), "manifest": binding(path.parent / "manifest.json"),
            "semantic_agreement": True, "ignored_fields": ["utc"],
            "original_official_audit_remains_first_authority": True}


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def run(source_root, native_root, protocol_path, commit, collection, output, *, official=None):
    source_root, native_root = Path(source_root).resolve(), Path(native_root).resolve()
    protocol_path, collection = Path(protocol_path).resolve(), Path(collection).resolve()
    value = verify_protocol_bytes(source_root, native_root, protocol_path, commit)
    protocol_identity = binding(protocol_path)
    before = binding(collection / "manifest.json")
    record, inventory = validate_collection(collection, value, protocol_path, commit)
    output = Path(output).resolve()
    require(not output.is_relative_to(collection), "Audit output must be outside the sealed collection")
    output.mkdir(parents=True, exist_ok=False)
    try:
        with frozen_auditor(source_root) as (frozen_protocol, auditor):
            validate_schedule(value, frozen_protocol, source_root)
            verify_files(source_root, value["sources"])
            sys.path.insert(0, str(native_root))
            try:
                check_native_imports(native_root, value["native"]["files"])
                rows = []
                with auditor.no_network(), bound_native_imports(native_root, value["native"]["files"]):
                    for planned, disposition in zip(value["schedule"], record["rows"]):
                        if disposition["status"] == "unstarted_integrity_stop":
                            rows.append({"slot": planned["slot"], "world_rank": planned["world_rank"],
                                "arm": planned["arm"], "started": False, "operational": False,
                                "grade_available": False, "execution_success": False,
                                "native_grade": None, "audit_complete": False, "status": disposition["status"]})
                        else:
                            rows.append(auditor.audit_episode(collection / disposition["directory"], planned, value))
                check_native_imports(native_root, value["native"]["files"])
            finally:
                sys.path.remove(str(native_root))
            verify_files(source_root, value["sources"])
            verify_files(native_root, value["native"]["files"])
            same(sealed_manifest(collection), inventory, "Collection inventory changed during portable replay")
            same(binding(collection / "manifest.json"), before, "Collection manifest changed during portable replay")
            same(binding(protocol_path), protocol_identity, "Protocol changed during portable replay")
            result = {"schema": "conseqax-limbo-audit-v1", "passed": True,
                "utc": datetime.now(timezone.utc).isoformat(), "protocol_commit": commit,
                "protocol": protocol_identity, "collection_manifest": before, "rows": rows,
                "summary": auditor.summarize(rows), "scope": SCOPE.copy(),
                "portable_audit": {"schema": "conseqax-limbo-portable-audit-v1",
                    "helper": {"path": str(Path(__file__).resolve()), **binding(__file__)},
                    "source_root": str(source_root), "native_root": str(native_root),
                    "collection": str(collection), "historical_declared_environment": value["environment"],
                    "current_offline_environment": current_environment(),
                    "historical_paths_used_as_execution_requirements": False,
                    "historical_runtime_and_wheel_files_accessed": False, "model_generations": 0,
                    "SDK_reexecution": False, "network_allowed": False,
                    "limitations": [
                        "Saved native trajectories and grades are replayed; no new inference, external replication, independent population sample or new task result is obtained.",
                        "Exact committed/current scientific source bytes and exact recorded native bytes remain mandatory. Historical executable, environment, wheel and model paths are provenance only.",
                        "Native source-to-Git comparison retains the original newline convention; recorded file byte hashes are never normalized or relaxed.",
                        "Current interpreter and operating system are disclosed separately. Any semantic replay mismatch fails the audit rather than coercing results.",
                        "The saved context-render/token proof is checked for internal consistency; no independent tokenizer reconstruction or SDK execution occurs.",
                        "The original official audit remains first authority. Portable agreement does not replace its failures or establish an external replication."]}}
            if official is not None:
                result["portable_audit"]["comparison_to_original_official"] = compare_official(official, result)
            else:
                result["portable_audit"]["comparison_to_original_official"] = None
        write_json(output / "audit-result.json", result)
    except BaseException as exc:
        write_json(output / "failure.json", {"schema": "conseqax-limbo-portable-audit-failure-v1",
            "passed": False, "utc": datetime.now(timezone.utc).isoformat(),
            "error": type(exc).__name__ + ": " + str(exc), "protocol_commit": commit,
            "scope": "No result replacement; original collection and official audit remain unchanged"})
        raise
    finally:
        write_json(output / "manifest.json", {path.relative_to(output).as_posix(): binding(path)
            for path in output.rglob("*") if path.is_file() and path.name != "manifest.json"})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT, help="Checkout containing the unchanged frozen scientific files")
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-official", type=Path, help="Require exact semantic agreement with the sealed original official audit")
    args = parser.parse_args()
    result = run(args.source_root, args.native_root, args.protocol, args.protocol_commit,
                 args.collection, args.output, official=args.compare_official)
    print(json.dumps({"passed": result["passed"], "summary": result["summary"],
                      "portable_audit": True, "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
