"""Prospective protocol fixtures only; no official tasks or provider calls."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import zipfile

import pytest

from research.native_agent import protocol as p


def tasks():
    rows = []
    for index in range(8):
        for present in (True, False):
            rows.append({"id": f"development-{'present' if present else 'empty'}-{index}",
                         "evaluation_criteria": {
                             "reward_basis": ["DB", "COMMUNICATE"],
                             "communicate_info": ["Invented communication criterion"] if present else []},
                         "user_scenario": object(), "reference_actions": object()})
    for ident in p.EXCLUDED:
        rows.append({"id": ident, "evaluation_criteria": {
            "reward_basis": ["COMMUNICATE", "DB"], "communicate_info": ["Development only"]}})
    return rows


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_selection_is_order_invariant_uses_only_metadata_and_excludes_development_ids():
    fixture = tasks()
    before = deepcopy(fixture)
    selected = p.select_metadata(fixture)
    assert selected == p.select_metadata(list(reversed(fixture)))
    # Privileged scenario/reference objects do not enter any output.
    json.dumps(selected, allow_nan=False)
    assert [row["id"] for row in fixture] == [row["id"] for row in before]
    assert len(selected["selected_metadata"]) == 12
    assert not (p.EXCLUDED & {row["task_id"] for row in selected["selected_metadata"]})
    for present in (True, False):
        eligible = [row for row in selected["all_metadata"]
                    if row["nonempty_communication"] is present and not row["excluded_development"]]
        expected = sorted(eligible, key=lambda row: hashlib.sha256(
            f"consequa-native-pilot-v1|airline|{row['task_id']}".encode()).hexdigest())[:6]
        assert [row for row in selected["selected_metadata"]
                if row["nonempty_communication"] is present] == expected


@pytest.mark.parametrize("basis", [["DB"], ["DB", "NL_ASSERTION"], ["DB", "COMMUNICATE", "ACTION"]])
def test_unexpected_required_basis_refuses_before_schedule(basis):
    fixture = tasks()
    fixture[0]["evaluation_criteria"]["reward_basis"] = basis
    with pytest.raises(ValueError, match="reward|component|basis"):
        p.select_metadata(fixture)


def test_duplicate_ids_and_insufficient_strata_are_not_silently_replaced():
    fixture = tasks()
    with pytest.raises(ValueError, match="Duplicate"):
        p.select_metadata(fixture + [deepcopy(fixture[0])])
    too_small = [row for row in fixture if row["id"] != "development-present-0"
                 and row["id"] != "development-present-1" and row["id"] != "development-present-2"]
    with pytest.raises(ValueError, match="fewer than six"):
        p.select_metadata(too_small)


@pytest.mark.parametrize("value", ["a string is not a list", {}, [3], [None], True])
def test_malformed_communication_metadata_is_not_a_truthiness_stratum(value):
    fixture = tasks()
    fixture[0]["evaluation_criteria"]["communicate_info"] = value
    with pytest.raises((ValueError, TypeError), match="communicat|metadata|criterion"):
        p.select_metadata(fixture)


def test_none_and_empty_communication_lists_are_valid_empty_metadata():
    fixture = tasks()
    fixture[1]["evaluation_criteria"]["communicate_info"] = None
    result = p.select_metadata(fixture)
    assert not next(row for row in result["all_metadata"]
                    if row["task_id"] == fixture[1]["id"])["nonempty_communication"]


def test_schedule_is_paired_exhaustive_unique_and_exactly_position_balanced():
    metadata = p.select_metadata(tasks())
    schedule = p.make_schedule(metadata, seed=91)
    assert len(schedule) == 48
    assert [row["slot"] for row in schedule] == list(range(48))
    assert len({row["episode_id"] for row in schedule}) == 48
    assert Counter((row["arm"], row["position"]) for row in schedule) == Counter(
        {(arm, position): 3 for arm in p.ARMS for position in range(4)})
    for ident in {row["task_id"] for row in schedule}:
        group = [row for row in schedule if row["task_id"] == ident]
        assert {row["arm"] for row in group} == set(p.ARMS)
        assert {row["seed"] for row in group} == {91}
        assert len({row["task_rank"] for row in group}) == 1
    shuffled = deepcopy(metadata)
    shuffled["selected_metadata"].reverse()
    assert schedule == p.make_schedule(shuffled, seed=91)


@pytest.mark.parametrize("corruption", ["missing", "duplicate", "unbalanced"])
def test_schedule_refuses_malformed_selected_denominator(corruption):
    metadata = p.select_metadata(tasks())
    if corruption == "missing":
        metadata["selected_metadata"].pop()
    elif corruption == "duplicate":
        metadata["selected_metadata"][-1] = deepcopy(metadata["selected_metadata"][0])
    else:
        metadata["selected_metadata"][0]["nonempty_communication"] = False
    with pytest.raises(ValueError, match="selected|schedule|strat|unique|twelve|12"):
        p.make_schedule(metadata)


def test_manifest_binds_every_nested_file_and_detects_changed_or_extra_payload(tmp_path):
    path = tmp_path / "slot" / "result.json"
    write_json(path, {"invented_reward": 0})
    manifest = {"files": {"slot/result.json": p.sha_file(path)}}
    write_json(tmp_path / "manifest.json", manifest)
    assert p.verify_artifact_manifest(tmp_path) == manifest
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        p.verify_artifact_manifest(tmp_path)
    manifest["files"]["slot/result.json"] = p.sha_file(path)
    write_json(tmp_path / "manifest.json", manifest)
    (tmp_path / "unbound.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        p.verify_artifact_manifest(tmp_path)


def test_nested_manifest_named_files_are_not_silently_outside_inventory(tmp_path):
    write_json(tmp_path / "manifest.json", {"files": {}})
    write_json(tmp_path / "nested" / "manifest.json", {"unexpected": "payload"})
    with pytest.raises(ValueError, match="inventory"):
        p.verify_artifact_manifest(tmp_path)
    nested = tmp_path / "nested" / "manifest.json"
    write_json(tmp_path / "manifest.json", {"files": {"nested/manifest.json": p.sha_file(nested)}})
    assert p.verify_artifact_manifest(tmp_path)["files"]["nested/manifest.json"] == p.sha_file(nested)


def test_inventory_refuses_parent_path_escape_and_wrong_declared_size(tmp_path):
    root = tmp_path / "bound"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    with pytest.raises(ValueError, match="changed|absent|path|relative"):
        p.verify_files(root, {"../outside.txt": {"sha256": p.sha_file(outside), "bytes": 7}})
    inside = root / "payload.txt"
    inside.write_text("payload", encoding="utf-8")
    with pytest.raises(ValueError, match="size|bytes|changed"):
        p.verify_files(root, {"payload.txt": {"sha256": p.sha_file(inside), "bytes": 99}})


@pytest.mark.parametrize("name", ["./payload.txt", "a/../payload.txt"])
def test_inventory_refuses_noncanonical_relative_aliases(tmp_path, name):
    (tmp_path / "payload.txt").write_text("bound payload", encoding="utf-8")
    (tmp_path / "a").mkdir()
    with pytest.raises(ValueError, match="path|relative|canonical"):
        p.verify_files(tmp_path, {name: {"sha256": p.sha_file(tmp_path / "payload.txt"), "bytes": 13}})


def test_source_binding_checks_committed_bytes_and_all_execution_modules(tmp_path, monkeypatch):
    original = b"# invented source\n"
    for name in p.SOURCE_PATHS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original.replace(b"\n", b"\r\n"))
    def git(command):
        if "rev-parse" in command:
            return b"invented-immutable-commit\n"
        if "status" in command:
            return b""
        return original
    monkeypatch.setattr(p.subprocess, "check_output", git)
    bound = p.source_binding(tmp_path)
    assert set(bound["files"]) == set(p.SOURCE_PATHS)
    assert {"research/native_agent/controller.py", "research/native_agent/transport.py",
            "research/native_agent/audit.py", "research/native_agent/harness.py",
            "research/native_agent/protocol.py", "scripts/run_native_external_benchmark.py"} <= set(bound["files"])
    (tmp_path / p.SOURCE_PATHS[0]).write_bytes(b"# edited source\n")
    with pytest.raises(ValueError, match="differs"):
        p.source_binding(tmp_path)


def test_dirty_collection_source_cannot_freeze(tmp_path, monkeypatch):
    def git(command):
        return b"modified source\n" if "status" in command else b"invented-commit\n"
    monkeypatch.setattr(p.subprocess, "check_output", git)
    with pytest.raises(ValueError, match="committed and clean"):
        p.source_binding(tmp_path)


def runtime_fixture(tmp_path, monkeypatch):
    package = tmp_path / "installed"
    files = {"consequa_x/__init__.py": b"__version__ = '2.1.1'\n",
             "consequa_x/schemas/invented.json": b"{}\n"}
    wheel = tmp_path / "invented.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
            path = package / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    distribution = SimpleNamespace(version="2.1.1", metadata={"Name": "consequa-x"},
        locate_file=lambda name: package / name, read_text=lambda name: "invented metadata")
    monkeypatch.setattr(p, "WHEEL_SHA256", p.sha_file(wheel))
    monkeypatch.setattr(p.importlib.metadata, "distribution", lambda name: distribution)
    monkeypatch.setattr(p.importlib.metadata, "distributions", lambda: [distribution])
    return wheel, package, distribution


def test_framework_runtime_binds_exact_wheel_payload_and_discloses_dependency_coverage(tmp_path, monkeypatch):
    wheel, package, _ = runtime_fixture(tmp_path, monkeypatch)
    result = p.runtime_binding(wheel)
    assert result["framework_version"] == "2.1.1"
    assert result["framework_payload"]["consequa_x/__init__.py"]["sha256"] == p.sha_file(
        package / "consequa_x/__init__.py")
    assert "not all dependency payload" in result["dependency_coverage"]
    (package / "consequa_x/schemas/invented.json").write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError, match="differs from wheel"):
        p.runtime_binding(wheel)


def test_framework_version_or_wheel_change_cannot_freeze(tmp_path, monkeypatch):
    wheel, _, distribution = runtime_fixture(tmp_path, monkeypatch)
    distribution.version = "2.1.2"
    with pytest.raises(ValueError, match="2.1.1"):
        p.runtime_binding(wheel)
    distribution.version = "2.1.1"
    with wheel.open("ab") as stream:
        stream.write(b"changed wheel bytes")
    with pytest.raises(ValueError, match="wheel identity"):
        p.runtime_binding(wheel)


def test_frozen_protocol_requires_immutable_git_bytes_even_if_local_receipt_is_rehashed(tmp_path, monkeypatch):
    path = tmp_path / "protocol.json"
    receipt_path = tmp_path / "protocol-receipt.json"
    write_json(path, {"invented": "prospective setting"})
    write_json(receipt_path, {"protocol_sha256": p.canonical_sha(p.load_json(path)),
                             "protocol_file_sha256": p.sha_file(path)})
    immutable = {"protocol.json": path.read_bytes(), "protocol-receipt.json": receipt_path.read_bytes()}
    def git(command):
        if "--show-toplevel" in command:
            return str(tmp_path).encode()
        return immutable[command[-1].split(":", 1)[1]]
    monkeypatch.setattr(p.subprocess, "check_output", git)
    protocol, anchor = p.verify_frozen_protocol(path, "1" * 40)
    assert protocol["invented"] == "prospective setting" and anchor["protocol_commit"] == "1" * 40
    write_json(path, {"invented": "changed setting"})
    write_json(receipt_path, {"protocol_sha256": p.canonical_sha(p.load_json(path)),
                             "protocol_file_sha256": p.sha_file(path)})
    with pytest.raises(ValueError, match="caller-pinned Git"):
        p.verify_frozen_protocol(path, "1" * 40)


@pytest.mark.parametrize("commit", [None, "main", "A" * 40, "0" * 39])
def test_protocol_anchor_cannot_be_an_unpinned_branch_or_noncanonical_commit(tmp_path, commit):
    with pytest.raises(ValueError, match="immutable protocol commit"):
        p.verify_frozen_protocol(tmp_path / "protocol.json", commit)
