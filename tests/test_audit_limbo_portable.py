"""Temporary synthetic collections; no invented native task grades/results."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import audit_limbo_portable as portable
from research.limbo_agent import protocol as frozen_protocol


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def initialize(root):
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic Portable Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")


def seal(directory):
    write_json(directory / "manifest.json", {path.relative_to(directory).as_posix(): portable.binding(path)
        for path in directory.rglob("*") if path.is_file() and path != directory / "manifest.json"})


@pytest.fixture(scope="module")
def base_fixture(tmp_path_factory):
    directory = tmp_path_factory.mktemp("portable-audit-synthetic")
    source, native = directory / "source", directory / "native"
    initialize(source)
    initialize(native)
    (native / "limbo").mkdir()
    (native / "limbo/__init__.py").write_text("# Synthetic pinned native namespace; no task construction.\n", encoding="utf-8")
    git(native, "add", "limbo")
    git(native, "commit", "-qm", "Synthetic native fixture only")
    native_commit = git(native, "rev-parse", "HEAD")
    bindings = frozen_protocol.source_binding(portable.ROOT)
    for name in bindings:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((portable.ROOT / name).read_bytes())
    metadata = []
    domains = ("billing", "data", "deploy", "mail", "social", "tickets")
    for index in range(12):
        domain = domains[index % 6]
        metadata.append({"template": f"synthetic_template_{index:02d}", "index": 20000 + index,
            "family": domain, "domains": [domain], "focals": [{"label": "invented_write",
                "tool": "invented.write", "domain": domain, "batch": index == 1,
                "verification": "public", "idempotency": "native", "reversible": True}]})
    value = {"schema": "conseqax-limbo-protocol-v1", "seed": 1701,
        "sources": bindings, "native": {"commit": native_commit,
            "files": {"limbo/__init__.py": portable.binding(native / "limbo/__init__.py")}},
        "arms": list(portable.ARMS), "metadata": metadata,
        "environment": {"python_version": "historical-unavailable-interpreter",
            "executable": {"path": "Z:/unavailable/original/python.exe", "sha256": "0" * 64, "bytes": 1}},
        "wheel": {"path": "Z:/unavailable/original/package.whl", "sha256": "1" * 64, "bytes": 2},
        "runtime_binding": {"model": "synthetic-no-model", "model_blob": "Z:/unavailable/model.bin"},
        "limits": {"max_requests": 16, "max_output_tokens": 512,
            "work": {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}},
        "schedule": frozen_protocol.make_schedule(metadata, world_count=24,
            model="synthetic-no-model", max_tool_calls=16)}
    protocol_path = source / "protocol.json"
    write_json(protocol_path, value)
    git(source, "add", ".")
    git(source, "commit", "-qm", "Synthetic frozen protocol only")
    commit = git(source, "rev-parse", "HEAD")
    collection = directory / "collection"
    collection.mkdir()
    reason = "Synthetic deliberate integrity stop; no generated tasks or native grades"
    rows = [{**{key: row[key] for key in ("slot", "world_rank", "arm")},
             "status": "unstarted_integrity_stop", "reason": reason} for row in value["schedule"]]
    write_json(collection / "claim.json", {"utc": "synthetic", "protocol_commit": commit,
        "protocol_sha256": portable.binding(protocol_path)["sha256"], "retry_resume_replacement": False})
    write_json(collection / "protocol.json", value)
    write_json(collection / "collection.json", {"schema": "conseqax-limbo-collection-v1",
        "utc": "synthetic", "protocol_commit": commit, "rows": rows, "integrity_stop": reason})
    seal(collection)
    return {"directory": directory, "source": source, "native": native, "collection": collection,
            "protocol": protocol_path, "value": value, "commit": commit, "native_commit": native_commit}


@pytest.fixture
def fixture(base_fixture, tmp_path, monkeypatch):
    directory = tmp_path / "relocated-synthetic"
    shutil.copytree(base_fixture["directory"], directory)
    monkeypatch.setattr(portable, "PIN", base_fixture["native_commit"])
    for name in list(sys.modules):
        if name == "limbo" or name.startswith("limbo."):
            monkeypatch.delitem(sys.modules, name)
    return {**base_fixture, "directory": directory, "source": directory / "source", "native": directory / "native",
            "collection": directory / "collection", "protocol": directory / "source/protocol.json",
            "value": portable.load(directory / "source/protocol.json")}


def verify(fixture):
    return portable.verify_protocol_bytes(fixture["source"], fixture["native"], fixture["protocol"], fixture["commit"])


def run(fixture, tmp_path, **kwargs):
    return portable.run(fixture["source"], fixture["native"], fixture["protocol"], fixture["commit"],
                        fixture["collection"], tmp_path / "portable-output", **kwargs)


def test_relocation_and_absent_historical_environment_do_not_relax_source_checks(fixture, tmp_path):
    assert verify(fixture) == fixture["value"]
    result = run(fixture, tmp_path)
    assert result["schema"] == "conseqax-limbo-audit-v1" and result["passed"] is True
    assert len(result["rows"]) == 96
    assert all(row["native_grade"] is None and row["started"] is False for row in result["rows"])
    assert result["summary"]["guard"]["unavailable_native_grade"] == 24
    assert result["portable_audit"]["historical_declared_environment"] == fixture["value"]["environment"]
    current = result["portable_audit"]["current_offline_environment"]
    assert current["python_version"] != "historical-unavailable-interpreter"
    assert current["SDK_installation_required"] is False
    assert result["portable_audit"]["model_generations"] == 0
    assert set(portable.sealed_manifest(tmp_path / "portable-output")) == {"audit-result.json"}


@pytest.mark.parametrize("change,match", [
    ("source", "Immutable file changed"),
    ("native", "Immutable file changed"),
    ("native_extra", "extra or missing"),
    ("protocol", "explicit Git commit"),
])
def test_frozen_code_and_protocol_remain_strict(fixture, change, match):
    if change == "source":
        path = fixture["source"] / "research/limbo_agent/audit.py"
    elif change == "native":
        path = fixture["native"] / "limbo/__init__.py"
    elif change == "native_extra":
        path = fixture["native"] / "limbo/untracked.py"
    else:
        path = fixture["protocol"]
    path.write_bytes((path.read_bytes() if path.exists() else b"") + b"\n")
    with pytest.raises(ValueError, match=match):
        verify(fixture)


def test_exact_protocol_commit_and_native_head_are_required(fixture):
    with pytest.raises(ValueError, match="40-character"):
        portable.verify_protocol_bytes(fixture["source"], fixture["native"], fixture["protocol"], "main")
    (fixture["native"] / "other.txt").write_text("Synthetic extra commit\n", encoding="utf-8")
    git(fixture["native"], "add", "other.txt")
    git(fixture["native"], "commit", "-qm", "Changed synthetic native HEAD")
    with pytest.raises(ValueError, match="checkout HEAD differs"):
        verify(fixture)


def test_changed_source_binding_cannot_be_hidden_in_a_new_protocol_commit(fixture):
    value = fixture["value"]
    value["sources"]["research/limbo_agent/audit.py"]["sha256"] = "b" * 64
    write_json(fixture["protocol"], value)
    git(fixture["source"], "add", "protocol.json")
    git(fixture["source"], "commit", "-qm", "Synthetic bad binding")
    fixture["commit"] = git(fixture["source"], "rev-parse", "HEAD")
    with pytest.raises(ValueError, match="Immutable file changed"):
        verify(fixture)


@pytest.mark.parametrize("mutation,match", [
    (lambda claim: claim.update(retry_resume_replacement=True), "one-shot claim"),
    (lambda claim: claim.update(protocol_commit="0" * 40), "one-shot claim"),
    (lambda claim: claim.update(protocol_sha256="0" * 64), "one-shot claim"),
])
def test_claim_is_bound_even_when_manifest_is_resealed(fixture, mutation, match):
    path = fixture["collection"] / "claim.json"
    claim = portable.load(path)
    mutation(claim)
    write_json(path, claim)
    seal(fixture["collection"])
    with pytest.raises(ValueError, match=match):
        portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])


@pytest.mark.parametrize("mutation,match", [
    (lambda record: record["rows"].pop(), "omitted planned"),
    (lambda record: record["rows"].__setitem__(1, copy.deepcopy(record["rows"][0])), "identity/order"),
    (lambda record: record["rows"][0].update(slot=True), "identity/order"),
    (lambda record: record["rows"][0].update(status="unstarted_unknown"), "Unknown collection"),
    (lambda record: record["rows"][0].update(reason=""), "recorded integrity stop"),
])
def test_all_planned_dispositions_retained_and_bound(fixture, mutation, match):
    path = fixture["collection"] / "collection.json"
    record = portable.load(path)
    mutation(record)
    write_json(path, record)
    seal(fixture["collection"])
    with pytest.raises(ValueError, match=match):
        portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])


def started_first(fixture):
    directory = fixture["collection"]
    record = portable.load(directory / "collection.json")
    first = record["rows"][0]
    first.pop("reason")
    first.update(status="child_failed", directory="slot-000", exit_code=1,
                 started_utc="synthetic", ended_utc="synthetic")
    slot = directory / "slot-000"
    slot.mkdir()
    write_json(slot / "parent-terminal.json", first)
    write_json(slot / "worker-config.json", {"protocol": fixture["value"], "slot": fixture["value"]["schedule"][0]})
    seal(slot)
    write_json(directory / "disposition-000.json", first)
    write_json(directory / "collection.json", record)
    seal(directory)
    return record, slot


def test_started_child_failure_disposition_and_worker_config_are_exact(fixture):
    record, slot = started_first(fixture)
    observed, _ = portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])
    assert observed == record
    config = portable.load(slot / "worker-config.json")
    config["slot"]["arm"] = "wrong"
    write_json(slot / "worker-config.json", config)
    seal(slot)
    seal(fixture["collection"])
    with pytest.raises(ValueError, match="Worker configuration differs"):
        portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])


def test_collector_integrity_reasons_can_change_but_final_reason_must_match(fixture):
    path = fixture["collection"] / "collection.json"
    record = portable.load(path)
    record["rows"][0]["reason"] = "Synthetic earlier distinct source check failure"
    write_json(path, record)
    seal(fixture["collection"])
    portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])
    record["rows"][-1]["reason"] = "Synthetic final reason mismatch"
    write_json(path, record)
    seal(fixture["collection"])
    with pytest.raises(ValueError, match="Final integrity-stop reason differs"):
        portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])


def test_deadline_disposition_preserved_even_if_child_finished_during_kill_race(fixture):
    record, slot = started_first(fixture)
    record["rows"][0].update(status="parent_deadline", exit_code=0)
    write_json(slot / "parent-terminal.json", record["rows"][0])
    write_json(fixture["collection"] / "disposition-000.json", record["rows"][0])
    write_json(fixture["collection"] / "collection.json", record)
    seal(slot)
    seal(fixture["collection"])
    portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])


def test_unsealed_collection_is_rejected_before_any_output(fixture, tmp_path):
    manifest = fixture["collection"] / "manifest.json"
    manifest.rename(manifest.with_suffix(".not-sealed"))
    with pytest.raises(FileNotFoundError):
        run(fixture, tmp_path)
    assert not (tmp_path / "portable-output").exists()


def test_manifest_bytes_extra_artifacts_and_unstarted_directories_rejected(fixture):
    path = fixture["collection"] / "claim.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Sealed file changed"):
        portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])
    seal(fixture["collection"])
    (fixture["collection"] / "extra.txt").write_text("extra", encoding="utf-8")
    seal(fixture["collection"])
    with pytest.raises(ValueError, match="Unplanned top-level"):
        portable.validate_collection(fixture["collection"], verify(fixture), fixture["protocol"], fixture["commit"])


def test_official_comparison_requires_exact_semantic_agreement(fixture, tmp_path):
    first = run(fixture, tmp_path)
    official_dir = tmp_path / "synthetic-official-audit"
    official_dir.mkdir()
    official = copy.deepcopy({key: value for key, value in first.items() if key != "portable_audit"})
    official["utc"] = "different-historical-time"
    write_json(official_dir / "audit-result.json", official)
    seal(official_dir)
    comparison = portable.compare_official(official_dir, first)
    assert comparison["semantic_agreement"] is True
    official["summary"]["guard"]["planned"] = 999
    write_json(official_dir / "audit-result.json", official)
    seal(official_dir)
    with pytest.raises(ValueError, match="differs: summary"):
        portable.compare_official(official_dir, first)


def test_portable_audit_cannot_substitute_for_official(fixture, tmp_path):
    result = run(fixture, tmp_path)
    with pytest.raises(ValueError, match="cannot substitute"):
        portable.compare_official(tmp_path / "portable-output", result)


def test_no_overwrite_or_output_inside_sealed_collection(fixture, tmp_path):
    run(fixture, tmp_path)
    before = portable.binding(tmp_path / "portable-output/manifest.json")
    with pytest.raises(FileExistsError):
        run(fixture, tmp_path)
    assert portable.binding(tmp_path / "portable-output/manifest.json") == before
    with pytest.raises(ValueError, match="outside the sealed"):
        portable.run(fixture["source"], fixture["native"], fixture["protocol"], fixture["commit"],
                     fixture["collection"], fixture["collection"] / "new-output")


def test_duplicate_keys_and_unsafe_bound_names_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"passed":false,"passed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON"):
        portable.load(path)
    for name in ("../outside", "C:/original/file", "a\\b", "/absolute", "a/../b", "a//b"):
        with pytest.raises(ValueError):
            portable.safe_file(tmp_path, name)


def test_stdlib_only_isolated_process_requires_no_sdk_or_historical_paths(fixture, tmp_path):
    entry = tmp_path / "isolated_portable_fixture.py"
    entry.write_text("\n".join([
        "import importlib.util, json, pathlib, sys",
        f"spec=importlib.util.spec_from_file_location('portable', {str(Path(portable.__file__).resolve())!r})",
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)",
        f"module.PIN={fixture['native_commit']!r}",
        f"result=module.run({str(fixture['source'])!r},{str(fixture['native'])!r},{str(fixture['protocol'])!r},"
        f"{fixture['commit']!r},{str(fixture['collection'])!r},{str(tmp_path / 'stdlib-output')!r})",
        "assert not any(name == 'consequa_x' or name.startswith('consequa_x.') for name in sys.modules)",
        "print(json.dumps({'passed':result['passed'],'sdk_imported':False,'planned':len(result['rows'])}))",
    ]), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-S", "-B", str(entry)], check=True,
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": ""})
    assert json.loads(completed.stdout) == {"passed": True, "sdk_imported": False, "planned": 96}


def test_frozen_audit_network_guard_is_used(fixture):
    import socket
    verify(fixture)
    with portable.frozen_auditor(fixture["source"]) as (_protocol, auditor):
        with auditor.no_network(), pytest.raises(RuntimeError, match="Network is forbidden"):
            socket.create_connection(("127.0.0.1", 11436))
    assert not any(name.startswith("_conseqax_portable_frozen_") for name in sys.modules)


def test_bound_native_loader_bypasses_bytecode_loader(fixture, monkeypatch):
    import importlib
    import importlib.machinery
    def refuse_cached_loader(*_args, **_kwargs):
        raise RuntimeError("Ordinary cached loader must not be used")
    monkeypatch.setattr(importlib.machinery.SourceFileLoader, "get_code", refuse_cached_loader)
    verify(fixture)
    try:
        with portable.frozen_auditor(fixture["source"]):
            with portable.bound_native_imports(fixture["native"], fixture["value"]["native"]["files"]):
                module = importlib.import_module("limbo")
    finally:
        sys.modules.pop("limbo", None)
    assert Path(module.__file__).resolve() == (fixture["native"] / "limbo/__init__.py").resolve()


def test_actual_native_failure_replay_under_stdlib_only_without_task_construction(fixture, tmp_path, monkeypatch):
    actual_native = os.environ.get("CONSEQAX_LIMBO_ROOT")
    if not actual_native:
        pytest.skip("Set CONSEQAX_LIMBO_ROOT for native failure-disposition replay without task grading")
    actual_native = Path(actual_native).resolve()
    identity = frozen_protocol.native_binding(actual_native)
    monkeypatch.setattr(portable, "PIN", identity["commit"])
    fixture["native"] = actual_native
    fixture["native_commit"] = identity["commit"]
    fixture["value"]["native"] = identity
    write_json(fixture["protocol"], fixture["value"])
    git(fixture["source"], "add", "protocol.json")
    git(fixture["source"], "commit", "-qm", "Synthetic unavailable slot with real pinned native implementation")
    fixture["commit"] = git(fixture["source"], "rev-parse", "HEAD")
    claim = portable.load(fixture["collection"] / "claim.json")
    claim.update(protocol_commit=fixture["commit"], protocol_sha256=portable.binding(fixture["protocol"])["sha256"])
    write_json(fixture["collection"] / "claim.json", claim)
    write_json(fixture["collection"] / "protocol.json", fixture["value"])
    record, _slot = started_first(fixture)
    record["protocol_commit"] = fixture["commit"]
    write_json(fixture["collection"] / "collection.json", record)
    seal(fixture["collection"])
    entry = tmp_path / "native_stdlib_failure_fixture.py"
    entry.write_text("\n".join([
        "import importlib.util, json, sys",
        f"spec=importlib.util.spec_from_file_location('portable', {str(Path(portable.__file__).resolve())!r})",
        "module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)",
        f"result=module.run({str(fixture['source'])!r},{str(actual_native)!r},{str(fixture['protocol'])!r},"
        f"{fixture['commit']!r},{str(fixture['collection'])!r},{str(tmp_path / 'native-stdlib-output')!r})",
        "assert 'limbo.agent' in sys.modules",
        "assert not any(name == 'consequa_x' or name.startswith('consequa_x.') for name in sys.modules)",
        "assert all(row['native_grade'] is None for row in result['rows'])",
        "print(json.dumps({'passed':result['passed'],'first':result['rows'][0]['status'],'grades_computed':0}))",
    ]), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-S", "-B", str(entry)], check=True,
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": ""})
    assert json.loads(completed.stdout) == {"passed": True, "first": "child_failed", "grades_computed": 0}
