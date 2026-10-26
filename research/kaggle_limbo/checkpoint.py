"""Append-only, protocol-bound continuation across ephemeral notebook sessions.

A reservation consumes a slot before any dispatch. Interrupted reservations
are never retried. OS advisory locks, rather than recorded PIDs, select the one
writer. Hashes establish byte consistency, not independent authenticity.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import math
import stat
import tempfile
import time
import uuid
import zipfile


SCHEMA = "conseqax-kaggle-checkpoint-v1"
TERMINALS = {"completed", "native_error_return", "failed", "interrupted", "refused"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def binding(path):
    path = Path(path)
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return {"sha256": value.hexdigest(), "bytes": path.stat().st_size}


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON object key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def relative(name):
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name
            and not any(ord(c) < 32 for c in name), "Unsafe checkpoint path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix() == name
            and all(part not in {".", "..", ""} for part in path.parts), "Unsafe checkpoint path")
    return path


def _safe(path):
    path = Path(path)
    require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(),
            "Symlinks and junctions are forbidden in checkpoint trees")


def inventory(root):
    root = Path(root)
    _safe(root)
    result, folded = {}, set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            _safe(Path(directory) / name)
        for name in files:
            path = Path(directory) / name
            _safe(path)
            require(stat.S_ISREG(path.stat().st_mode), "Only regular checkpoint files are allowed")
            key = path.relative_to(root).as_posix()
            relative(key)
            if key == ".writer.lock" or key == "checkpoint.json" or name.startswith(".atomic-"):
                continue
            require(key.casefold() not in folded, "Case-colliding checkpoint paths")
            folded.add(key.casefold())
            result[key] = binding(path)
    return result


def _sync_dir(directory):
    if os.name == "nt":
        return  # File data is flushed; stdlib does not expose Windows directory FlushFileBuffers.
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_bytes(path, raw, *, replace=False):
    """Publish complete fsynced bytes; exclusive publication never overwrites."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _safe(path.parent)
    temporary = path.parent / (".atomic-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Hard-link publication is atomic and fails if the destination exists.
            os.link(temporary, path)
            temporary.unlink()
        _sync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


class SessionBudget:
    def __init__(self, seconds=8 * 3600, flush_margin=30 * 60,
                 episode_allowance=7200, *, clock=time.monotonic, started_at=None):
        for value in (seconds, flush_margin, episode_allowance):
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "Invalid session budget")
        require(seconds > flush_margin + episode_allowance, "Session cannot fit a full frozen episode")
        self.clock, self.seconds = clock, seconds
        self.started_at = clock() if started_at is None else started_at
        self.flush_margin, self.episode_allowance = flush_margin, episode_allowance

    @property
    def remaining(self):
        return max(0, self.seconds - (self.clock() - self.started_at))

    def can_start_next(self):
        return self.remaining >= self.episode_allowance + self.flush_margin

    def require_start(self):
        require(self.can_start_next(), "Session cutoff: preserve full episode cap plus checkpoint margin")


class CheckpointStore:
    def __init__(self, root, lineage, schedule):
        self.root = Path(root).resolve()
        require(type(lineage) is dict and bool(lineage), "Static lineage is required")
        require(type(schedule) is list and bool(schedule)
                and all(type(r.get("slot")) is int for r in schedule)
                and [r.get("slot") for r in schedule] == list(range(len(schedule))),
                "Complete contiguous planned slot identities are required")
        canonical(lineage)
        self.lineage, self.schedule = lineage, schedule
        self.events, self.reservations, self.terminals = [], {}, {}
        self.lock = None
        self.root.mkdir(parents=True, exist_ok=True)
        _safe(self.root)
        self._acquire()
        try:
            if not (self.root / "identity.json").exists():
                require(not [p for p in self.root.iterdir() if p.name != ".writer.lock"],
                        "Refuse to initialize a nonempty checkpoint directory")
                atomic_bytes(self.root / "schedule.json", canonical(schedule))
                atomic_bytes(self.root / "identity.json", canonical({"schema": SCHEMA,
                    "lineage": lineage, "schedule": binding(self.root / "schedule.json"),
                    "planned_slots": len(schedule)}))
            self._read(validate_payloads=True)
        except BaseException:
            self.close()
            raise

    def _acquire(self):
        if (self.root / ".writer.lock").exists():
            _safe(self.root / ".writer.lock")
        self.lock = (self.root / ".writer.lock").open("a+b")
        self.lock.seek(0, 2)
        if self.lock.tell() == 0:
            self.lock.write(b"0")
            self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lock.close()
            self.lock = None
            raise ValueError("Checkpoint already has an active writer") from error

    def close(self):
        if self.lock is not None:
            self.lock.close()  # OS automatically releases the lock, including on process death.
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def _read(self, *, validate_payloads):
        require(self.lock is not None, "Checkpoint writer is closed")
        require(not (self.root / "IMPORT-IN-PROGRESS.json").exists(),
                "Interrupted import requires a fresh import from the preserved original snapshot")
        identity = load(self.root / "identity.json")
        require(identity["schema"] == SCHEMA and identity["lineage"] == self.lineage,
                "Protocol/source/model/runtime static lineage differs")
        require(binding(self.root / "schedule.json") == identity["schedule"]
                and load(self.root / "schedule.json") == self.schedule
                and identity["planned_slots"] == len(self.schedule), "Planned schedule changed")
        events, reservations, terminals, previous = [], {}, {}, None
        paths = sorted((self.root / "events").glob("*.json")) if (self.root / "events").exists() else []
        for sequence, path in enumerate(paths):
            require(path.name == f"{sequence:06d}.json", "Missing or reordered checkpoint event")
            _safe(path)
            record = load(path)
            checksum = record.get("content_sha256")
            require(checksum == hashlib.sha256(canonical({k: v for k, v in record.items()
                if k != "content_sha256"})).hexdigest(), "Checkpoint event checksum changed")
            require(record["sequence"] == sequence and record["previous_sha256"] == previous,
                    "Conflicting or corrupted checkpoint history")
            require(record["identity"] == binding(self.root / "identity.json"), "Event lineage changed")
            slot = record.get("slot")
            if record["kind"] in {"reserve", "terminal"}:
                require(type(slot) is int and 0 <= slot < len(self.schedule), "Invalid checkpoint slot")
                require(record["slot_sha256"] == hashlib.sha256(canonical(self.schedule[slot])).hexdigest(),
                        "Scheduled slot identity changed")
            if record["kind"] == "reserve":
                require(slot not in reservations, "Started slot was reserved twice")
                reservations[slot] = {**record, "event_sha256": binding(path)["sha256"]}
            elif record["kind"] == "terminal":
                require(slot in reservations and slot not in terminals, "Terminal without one reservation")
                require(record["reservation_sha256"] == reservations[slot]["event_sha256"]
                        and record["status"] in TERMINALS, "Terminal reservation/status changed")
                if validate_payloads:
                    expected_prefix = f"slots/slot-{slot:05d}/episode/"
                    actual_files = {expected_prefix + name: value
                        for name, value in inventory(self.slot_directory(slot)).items()}
                    require(actual_files == record["episode_files"], "Sealed episode inventory changed")
                    for name, expected in record["episode_files"].items():
                        relative(name)
                        require(name.startswith(expected_prefix), "Terminal references another slot")
                        target = self.root / name
                        _safe(target)
                        require(target.resolve().is_relative_to(self.root)
                                and binding(target) == expected, "Sealed episode bytes changed: " + name)
                terminals[slot] = record
            else:
                require(record["kind"] == "session", "Unknown checkpoint event kind")
            events.append(record)
            previous = binding(path)["sha256"]
        self.events, self.reservations, self.terminals = events, reservations, terminals

    def _append(self, record):
        require(self.lock is not None, "Checkpoint writer is closed")
        require(not (self.root / "IMPORT-IN-PROGRESS.json").exists(), "Interrupted import blocks dispatch")
        sequence = len(self.events)
        previous = binding(self.root / "events" / f"{sequence - 1:06d}.json")["sha256"] if sequence else None
        record = {"sequence": sequence, "previous_sha256": previous,
                  "identity": binding(self.root / "identity.json"), **record}
        record["content_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
        atomic_bytes(self.root / "events" / f"{sequence:06d}.json", canonical(record))
        self._read(validate_payloads=False)
        return record

    def begin_session(self, session_id, runtime_identity):
        require(isinstance(session_id, str) and session_id, "Explicit unique session ID required")
        require(not any(r["kind"] == "session" and r["session_id"] == session_id for r in self.events),
                "Session ID was already used")
        return self._append({"kind": "session", "session_id": session_id,
            "observed_runtime": runtime_identity, "created_unix_s": time.time()})

    def next_unstarted(self):
        return next((row for row in self.schedule if row["slot"] not in self.reservations), None)

    def slot_directory(self, slot):
        require(type(slot) is int and 0 <= slot < len(self.schedule), "Unknown planned slot")
        return self.root / "slots" / f"slot-{slot:05d}" / "episode"

    def reserve(self, slot, session_id, *, budget=None):
        require(type(slot) is int and 0 <= slot < len(self.schedule), "Unknown planned slot")
        require(slot not in self.reservations, "Completed or started-interrupted slot cannot repeat")
        require(isinstance(session_id, str) and session_id, "Session identity required")
        if budget is not None:
            budget.require_start()
        record = self._append({"kind": "reserve", "slot": slot, "session_id": session_id,
            "slot_sha256": hashlib.sha256(canonical(self.schedule[slot])).hexdigest(),
            "created_unix_s": time.time(), "nonce": uuid.uuid4().hex})
        self.slot_directory(slot).mkdir(parents=True, exist_ok=True)
        return record

    def finish(self, slot, status, episode_dir=None, *, details=None):
        require(slot in self.reservations and slot not in self.terminals,
                "Only a reserved, unfinished slot can receive a terminal")
        require(status in TERMINALS, "Unknown terminal status")
        target = self.slot_directory(slot)
        target.mkdir(parents=True, exist_ok=True)
        if episode_dir is not None and Path(episode_dir).resolve() != target.resolve():
            _safe(Path(episode_dir))
            source = Path(episode_dir).resolve(strict=True)
            require(not target.resolve().is_relative_to(source),
                    "Episode source cannot contain its checkpoint destination")
            files = inventory(source)
            for name, expected in files.items():
                destination = target / name
                require(not destination.exists(), "Refuse to replace episode evidence")
                atomic_bytes(destination, (source / name).read_bytes())
                require(binding(destination) == expected, "Episode changed during preservation")
            require(inventory(source) == files, "Episode changed while copying")
        files = {f"slots/slot-{slot:05d}/episode/" + name: value
                 for name, value in inventory(target).items()}
        return self._append({"kind": "terminal", "slot": slot, "status": status,
            "slot_sha256": hashlib.sha256(canonical(self.schedule[slot])).hexdigest(),
            "reservation_sha256": self.reservations[slot]["event_sha256"],
            "session_id": self.reservations[slot]["session_id"], "episode_files": files,
            "details": {} if details is None else details, "created_unix_s": time.time()})

    seal_terminal = finish

    def reconcile_orphans(self, resuming_session_id=None):
        """Call only after previous notebook/episode processes have stopped."""
        result = []
        for slot, reservation in list(self.reservations.items()):
            if slot not in self.terminals:
                require(resuming_session_id is None or reservation["session_id"] != resuming_session_id,
                        "Do not reconcile the current session's active episode")
                result.append(self.finish(slot, "interrupted", details={
                    "reason": "prior session ended after reservation; no retry or semantic grade invented",
                    "reconciled_by_session": resuming_session_id}))
        return result

    def snapshot(self):
        self._read(validate_payloads=True)
        return {"planned": len(self.schedule), "started": len(self.reservations),
            "terminal": len(self.terminals), "pending": sorted(set(self.reservations) - set(self.terminals)),
            "unstarted": len(self.schedule) - len(self.reservations),
            "statuses": {status: sum(r["status"] == status for r in self.terminals.values())
                         for status in sorted(TERMINALS)},
            "last_event_sha256": binding(self.root / "events" / f"{len(self.events)-1:06d}.json")["sha256"]
                                 if self.events else None}

    def export(self, destination):
        """Export an exact tree or deflated ZIP. Stop writers before pending-prefix export."""
        state = self.snapshot()
        files = inventory(self.root)
        destination = Path(destination).resolve()
        require(not destination.exists() and not destination.is_relative_to(self.root),
                "Export needs a new path outside the active checkpoint")
        receipt = {"schema": SCHEMA, "files": files, "state": state,
                   "identity": binding(self.root / "identity.json")}
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.lower() == ".zip":
            temporary = destination.parent / (".atomic-" + uuid.uuid4().hex)
            try:
                with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED,
                                     compresslevel=6, allowZip64=True) as archive:
                    for name in sorted(files):
                        archive.write(self.root / name, arcname=name)
                    archive.writestr("checkpoint.json", canonical(receipt))
                with temporary.open("r+b") as stream:
                    os.fsync(stream.fileno())
                require(inventory(self.root) == files, "Checkpoint changed during export")
                os.link(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
        else:
            destination.mkdir()
            for name, expected in files.items():
                atomic_bytes(destination / name, (self.root / name).read_bytes())
                require(binding(destination / name) == expected, "Checkpoint changed during export")
            require(inventory(self.root) == files, "Checkpoint changed during export")
            atomic_bytes(destination / "checkpoint.json", canonical(receipt))
        _sync_dir(destination.parent)
        return receipt

    export_checkpoint = export

    def import_snapshot(self, source, *, allow_live_tree=False,
                        max_files=500000, max_bytes=40 * 1024**3):
        """Merge only an ancestor/extension of this exact history; reject forks."""
        with checked_snapshot(source, max_files=max_files, max_bytes=max_bytes,
                              allow_live_tree=allow_live_tree) as tree:
            require(not tree.resolve().is_relative_to(self.root)
                    and not self.root.is_relative_to(tree.resolve()),
                    "Imported source and destination trees must be separate")
            identity = load(tree / "identity.json")
            require(identity == load(self.root / "identity.json"), "Checkpoint protocol/static lineage mismatch")
            incoming = sorted((tree / "events").glob("*.json")) if (tree / "events").exists() else []
            current = sorted((self.root / "events").glob("*.json")) if (self.root / "events").exists() else []
            for a, b in zip(current, incoming):
                require(a.name == b.name and a.read_bytes() == b.read_bytes(), "Conflicting checkpoint history fork")
            # Validate the complete incoming chain and its terminal payloads in isolation.
            # Kaggle inputs are read-only. Validate without creating a lock or
            # modifying the supplied snapshot's bytes.
            other = object.__new__(CheckpointStore)
            other.root, other.lineage, other.schedule = tree, self.lineage, self.schedule
            other.lock = True
            other._read(validate_payloads=True)
            validated_source_files = inventory(tree)
            if len(incoming) < len(current):
                return self.snapshot()  # Older immutable ancestor adds no new observations.
            source_files = inventory(tree)
            require(source_files == validated_source_files, "Source changed after checkpoint validation")
            sealed = {name for record in self.terminals.values() for name in record["episode_files"]}
            updates = []
            for name, expected in source_files.items():
                target = self.root / name
                if target.exists():
                    if binding(target) == expected:
                        continue
                    require(name not in sealed and name.startswith("slots/"), "Sealed checkpoint bytes conflict")
                    old, new = target.read_bytes(), (tree / name).read_bytes()
                    require(new.startswith(old), "Unsealed episode history is not an append-only extension")
                updates.append((name, expected))
            marker = self.root / "IMPORT-IN-PROGRESS.json"
            atomic_bytes(marker, canonical({"source_identity": binding(tree / "identity.json"),
                "source_event_count": len(incoming), "scope": "Refuse dispatch after incomplete import"}))
            try:
                # Copy evidence before referencing terminal events; marker blocks dispatch on crash.
                for name, expected in sorted(updates, key=lambda item: item[0].startswith("events/")):
                    target = self.root / name
                    atomic_bytes(target, (tree / name).read_bytes(), replace=target.exists())
                    require(binding(target) == expected, "Imported checkpoint bytes changed")
                require(inventory(tree) == source_files, "Source changed during checkpoint import")
                marker.unlink()
                _sync_dir(self.root)
                return self.snapshot()
            except BaseException:
                # Preserve marker and every prefix. A fresh import can reconstruct this tree.
                raise


@contextmanager
def checked_snapshot(source, *, max_files, max_bytes, allow_live_tree=False):
    """Never call extractall: reject traversal, aliases, symlinks and oversized ZIPs."""
    _safe(Path(source))
    source = Path(source).resolve(strict=True)
    temporary = None
    try:
        if source.is_dir():
            tree = source
        else:
            require(source.suffix.lower() == ".zip", "Expected a checkpoint directory or ZIP")
            temporary = tempfile.TemporaryDirectory(prefix="conseqax-checkpoint-")
            tree = Path(temporary.name)
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                require(len(infos) <= max_files + 1, "Checkpoint ZIP has too many members")
                names, total = set(), 0
                for info in infos:
                    name = info.filename.rstrip("/") if info.is_dir() else info.filename
                    relative(name)
                    require(name.casefold() not in names, "Duplicate or aliased ZIP member")
                    names.add(name.casefold())
                    mode = info.external_attr >> 16
                    require(stat.S_IFMT(mode) in {0, stat.S_IFREG, stat.S_IFDIR}, "ZIP symlinks/special files forbidden")
                    require(not info.flag_bits & 1, "Encrypted checkpoints are unsupported")
                    total += info.file_size
                    require(total <= max_bytes and info.file_size <= 512 * 1024**2,
                            "Checkpoint ZIP exceeds extraction limits")
                for info in infos:
                    target = tree / info.filename
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as stream, target.open("xb") as output:
                        count = 0
                        while chunk := stream.read(1024 * 1024):
                            count += len(chunk)
                            require(count <= info.file_size, "ZIP member exceeds declared size")
                            output.write(chunk)
                        require(count == info.file_size, "Truncated ZIP member")
                        output.flush()
                        os.fsync(output.fileno())
        files = inventory(tree)
        require(len(files) <= max_files and sum(r["bytes"] for r in files.values()) <= max_bytes,
                "Checkpoint tree exceeds import limits")
        if (tree / "checkpoint.json").exists():
            receipt = load(tree / "checkpoint.json")
            require(receipt["schema"] == SCHEMA and receipt["files"] == files
                    and receipt["identity"] == binding(tree / "identity.json"), "Checkpoint inventory/tamper failure")
        else:
            require(source.is_dir() and allow_live_tree,
                    "A manifest-free raw checkpoint requires explicit allow_live_tree")
            require((tree / "identity.json").is_file() and (tree / "schedule.json").is_file(),
                    "Raw checkpoint lacks immutable identity and schedule")
            # Event chains and every sealed payload are validated by the caller
            # before merging. Pending bytes stay an ungraded interrupted prefix.
        yield tree
    finally:
        if temporary is not None:
            temporary.cleanup()
