"""Crash/resume integrity fixtures only; no model, network or GPU requests."""
import json
import stat
import zipfile

import pytest

from research.kaggle_limbo.checkpoint import CheckpointStore, SessionBudget, atomic_bytes


LINEAGE = {"protocol": {"sha256": "a" * 64, "bytes": 123},
    "sources": {"research.py": {"sha256": "b" * 64, "bytes": 456}},
    "runtime_static": {"gpu": "synthetic", "driver": "fixture"}}
SCHEDULE = [{"slot": i, "arm": "synthetic", "model_id": "fixture"} for i in range(4)]


def new_store(root):
    return CheckpointStore(root, LINEAGE, SCHEDULE)


def complete(store, slot, session="first"):
    store.reserve(slot, session)
    directory = store.slot_directory(slot)
    (directory / "response.json").write_text('{"fixture":true}\n', encoding="utf-8")
    store.finish(slot, "completed")


def test_completed_and_reserved_interrupted_slots_never_repeat(tmp_path):
    with new_store(tmp_path / "state") as store:
        complete(store, 0)
        store.reserve(1, "first")
        (store.slot_directory(1) / "partial.jsonl").write_text('{"dispatch":1}\n')
        assert store.next_unstarted()["slot"] == 2
    with new_store(tmp_path / "state") as store:
        recovered = store.reconcile_orphans("second")
        assert len(recovered) == 1 and recovered[0]["status"] == "interrupted"
        assert store.next_unstarted()["slot"] == 2
        assert store.snapshot()["statuses"]["interrupted"] == 1
        assert (store.slot_directory(1) / "partial.jsonl").read_text() == '{"dispatch":1}\n'
        for slot in (0, 1):
            with pytest.raises(ValueError, match="cannot repeat"):
                store.reserve(slot, "second")


def test_session_observations_allow_new_pid_but_static_lineage_is_fixed(tmp_path):
    root = tmp_path / "state"
    with new_store(root) as store:
        store.begin_session("first", {"pid": 100, "gpu_uuid": "one"})
    with new_store(root) as store:
        store.begin_session("second", {"pid": 200, "gpu_uuid": "two"})
        assert len(store.events) == 2
    with pytest.raises(ValueError, match="lineage"):
        CheckpointStore(root, {**LINEAGE, "protocol": {"sha256": "c" * 64, "bytes": 123}}, SCHEDULE)


def test_single_writer_lock_and_release(tmp_path):
    root = tmp_path / "state"
    with new_store(root):
        with pytest.raises(ValueError, match="active writer"):
            new_store(root)
    with new_store(root) as store:
        assert store.next_unstarted()["slot"] == 0


def test_atomic_exclusive_publication_never_overwrites(tmp_path):
    path = tmp_path / "event.json"
    atomic_bytes(path, b"first")
    with pytest.raises(FileExistsError):
        atomic_bytes(path, b"second")
    assert path.read_bytes() == b"first"
    assert not list(tmp_path.glob(".atomic-*"))


@pytest.mark.parametrize("tamper", ["file", "extra_file", "event", "schedule", "missing_event"])
def test_reopen_rejects_tampered_sealed_history(tmp_path, tamper):
    root = tmp_path / "state"
    with new_store(root) as store:
        complete(store, 0)
    if tamper == "file":
        (root / "slots/slot-00000/episode/response.json").write_text("changed")
    elif tamper == "extra_file":
        (root / "slots/slot-00000/episode/extra.txt").write_text("unexpected")
    elif tamper == "event":
        path = root / "events/000001.json"
        record = json.loads(path.read_text())
        record["status"] = "failed"
        path.write_text(json.dumps(record))
    elif tamper == "schedule":
        (root / "schedule.json").write_text("[]")
    else:
        (root / "events/000000.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        new_store(root)


@pytest.mark.parametrize("suffix", ["", ".zip"])
def test_export_import_keeps_exact_evidence_and_pending_prefix(tmp_path, suffix):
    with new_store(tmp_path / "first") as first:
        complete(first, 0)
        first.reserve(1, "first")
        (first.slot_directory(1) / "prefix.jsonl").write_bytes(b'{"started":true}\n')
        original = (first.root / "events/000000.json").read_bytes()
        first.export(tmp_path / ("snapshot" + suffix))
    with new_store(tmp_path / "second") as second:
        second.import_snapshot(tmp_path / ("snapshot" + suffix))
        assert second.next_unstarted()["slot"] == 2
        assert second.snapshot()["pending"] == [1]
        assert (second.root / "events/000000.json").read_bytes() == original
        assert (second.slot_directory(1) / "prefix.jsonl").read_bytes() == b'{"started":true}\n'
        second.reconcile_orphans("second")
        assert second.snapshot()["pending"] == []


def test_ancestor_and_extension_merge_but_divergent_fork_refused(tmp_path):
    early, late = tmp_path / "early.zip", tmp_path / "late.zip"
    with new_store(tmp_path / "first") as first:
        complete(first, 0)
        first.export(early)
        complete(first, 1)
        first.export(late)
    with new_store(tmp_path / "second") as second:
        second.import_snapshot(late)
        assert second.import_snapshot(early)["terminal"] == 2
    with new_store(tmp_path / "fork") as fork:
        fork.reserve(0, "different-attempt")
        fork.export(tmp_path / "fork.zip")
    with new_store(tmp_path / "second") as second:
        with pytest.raises(ValueError, match="fork"):
            second.import_snapshot(tmp_path / "fork.zip")
        assert second.snapshot()["terminal"] == 2


def test_snapshot_inventory_tamper_rejected_without_touching_destination(tmp_path):
    with new_store(tmp_path / "first") as first:
        complete(first, 0)
        first.export(tmp_path / "snapshot")
    (tmp_path / "snapshot/slots/slot-00000/episode/response.json").write_text("changed")
    with new_store(tmp_path / "second") as second:
        with pytest.raises(ValueError, match="tamper"):
            second.import_snapshot(tmp_path / "snapshot")
        assert second.snapshot()["started"] == 0


@pytest.mark.parametrize("unsafe", ["../escape", "/absolute", "C:/absolute", "a\\..\\escape", "a//b"])
def test_zip_paths_never_escape_staging(tmp_path, unsafe):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(unsafe, b"bad")
    with new_store(tmp_path / "state") as store:
        with pytest.raises(ValueError, match="Unsafe"):
            store.import_snapshot(archive)
        assert store.snapshot()["started"] == 0
    assert not (tmp_path / "escape").exists()


def test_zip_symlink_and_duplicate_alias_refused(tmp_path):
    for mode in ("symlink", "duplicate"):
        archive = tmp_path / (mode + ".zip")
        with zipfile.ZipFile(archive, "w") as output:
            if mode == "symlink":
                info = zipfile.ZipInfo("link")
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                output.writestr(info, b"../../escape")
            else:
                output.writestr("a", b"one")
                output.writestr("A", b"two")
        with new_store(tmp_path / mode) as store:
            with pytest.raises(ValueError):
                store.import_snapshot(archive)


def test_zip_extraction_resource_limits(tmp_path):
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("large", b"x" * 10000)
    with new_store(tmp_path / "state") as store:
        with pytest.raises(ValueError, match="limits"):
            store.import_snapshot(archive, max_bytes=9999)


def test_budget_preserves_uniform_episode_cap_and_flush_time(tmp_path):
    now = [0.0]
    budget = SessionBudget(seconds=8 * 3600, flush_margin=1800, episode_allowance=7200,
                           clock=lambda: now[0])
    now[0] = 8 * 3600 - 7200 - 1800
    assert budget.can_start_next()
    now[0] += 0.001
    assert not budget.can_start_next()
    with new_store(tmp_path / "state") as store:
        with pytest.raises(ValueError, match="cutoff"):
            store.reserve(0, "session", budget=budget)
        assert store.next_unstarted()["slot"] == 0


def test_current_active_episode_cannot_be_reconciled_as_old_orphan(tmp_path):
    with new_store(tmp_path / "state") as store:
        store.reserve(0, "current")
        with pytest.raises(ValueError, match="current session"):
            store.reconcile_orphans("current")
        assert store.snapshot()["pending"] == [0]


def test_partial_import_marker_blocks_dispatch_after_restart(tmp_path):
    root = tmp_path / "state"
    with new_store(root) as store:
        store.reserve(0, "session")
    (root / "IMPORT-IN-PROGRESS.json").write_text("{}")
    with pytest.raises(ValueError, match="Interrupted import"):
        new_store(root)


def test_directory_import_does_not_write_to_read_only_source(tmp_path, monkeypatch):
    from pathlib import Path
    with new_store(tmp_path / "first") as first:
        complete(first, 0)
        first.export(tmp_path / "snapshot")
    original = Path.open

    def checked(path, mode="r", *args, **kwargs):
        if path.is_relative_to(tmp_path / "snapshot"):
            assert not any(flag in mode for flag in "wax+"), "Source snapshot must stay read-only"
        return original(path, mode, *args, **kwargs)

    with new_store(tmp_path / "second") as second:
        monkeypatch.setattr(Path, "open", checked)
        second.import_snapshot(tmp_path / "snapshot")
        assert second.snapshot()["terminal"] == 1


def test_latest_raw_tree_preserves_reservation_newer_than_last_export(tmp_path):
    root = tmp_path / "first"
    with new_store(root) as first:
        complete(first, 0)
        first.export(tmp_path / "older.zip")
        first.reserve(1, "crashed-session")
        (first.slot_directory(1) / "new-dispatch.jsonl").write_bytes(b'{"dispatch":true}\n')
    with new_store(tmp_path / "second") as second:
        second.import_snapshot(root, allow_live_tree=True)
        assert second.snapshot()["pending"] == [1]
        assert second.next_unstarted()["slot"] == 2
        second.reconcile_orphans("resumed-session")
        assert second.terminals[1]["status"] == "interrupted"
        assert (second.slot_directory(1) / "new-dispatch.jsonl").read_bytes() == b'{"dispatch":true}\n'
        with pytest.raises(ValueError, match="cannot repeat"):
            second.reserve(1, "resumed-session")


def test_raw_tree_import_requires_opt_in_and_rejects_corrupt_sealed_bytes(tmp_path):
    root = tmp_path / "first"
    with new_store(root) as first:
        complete(first, 0)
    with new_store(tmp_path / "second") as second:
        with pytest.raises(ValueError, match="allow_live_tree"):
            second.import_snapshot(root)
        (root / "slots/slot-00000/episode/response.json").write_bytes(b"tampered")
        with pytest.raises(ValueError, match="Sealed"):
            second.import_snapshot(root, allow_live_tree=True)
        assert second.snapshot()["started"] == 0


def test_raw_tree_import_rejects_foreign_lineage_before_any_reservation(tmp_path):
    with CheckpointStore(tmp_path / "foreign", {"protocol": "different fixture"}, SCHEDULE) as foreign:
        foreign.reserve(0, "foreign-session")
    with new_store(tmp_path / "second") as second:
        with pytest.raises(ValueError, match="lineage mismatch"):
            second.import_snapshot(tmp_path / "foreign", allow_live_tree=True)
        assert second.snapshot()["started"] == 0
