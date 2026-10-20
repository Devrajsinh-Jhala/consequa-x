"""Small synthetic portability fixtures; no corpus, world, framework or outputs.

Git objects below exist only in pytest's temporary repositories. SQLite rows
are hand-written. Nothing executes the frozen controller/application study.
"""

from copy import deepcopy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_recovery_artifacts_portable.py"
SPEC = importlib.util.spec_from_file_location("synthetic_portable_audit", SCRIPT)
portable = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(portable)
FROZEN_BYTES = (ROOT / "scripts/audit_recovery_controller_study.py").read_bytes()


def encoded(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()


def run_git(repo, *args, data=None):
    environment = os.environ.copy()
    environment.update(
        GIT_AUTHOR_NAME="Synthetic fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Synthetic fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_AUTHOR_DATE="2001-01-01T00:00:00+00:00",
        GIT_COMMITTER_DATE="2001-01-01T00:00:00+00:00",
    )
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args],
            input=data,
            capture_output=True,
            env=environment,
            check=True,
        )
        .stdout.decode()
        .strip()
    )


def tree_object(repo, files):
    nested = {}
    for path, data in files.items():
        children = nested
        parts = path.split("/")
        for part in parts[:-1]:
            children = children.setdefault(part, {})
        children[parts[-1]] = run_git(repo, "hash-object", "-w", "--stdin", data=data)

    def tree(children):
        entries = []
        for name, child in sorted(children.items()):
            kind, mode, oid = (
                ("tree", "040000", tree(child))
                if isinstance(child, dict)
                else ("blob", "100644", child)
            )
            entries.append(f"{mode} {kind} {oid}\t{name}\n")
        return run_git(repo, "mktree", data="".join(entries).encode())

    return tree(nested)


def git_fixture(tmp_path):
    if not shutil.which("git"):
        pytest.skip("Git is required for immutable-object portability checks")
    repo = tmp_path / "relocated-clone"
    repo.mkdir()
    run_git(repo, "init")
    files = {name: b"# synthetic public-source placeholder\n" for name in portable.REQUIRED_SOURCES}
    files[portable.AUDITOR_PATH] = FROZEN_BYTES
    files["src/consequa_x/__init__.py"] = (
        b"# synthetic frozen framework declaration; never imported\n"
    )
    source = run_git(
        repo, "commit-tree", tree_object(repo, files), data=b"synthetic source fixture\n"
    )
    protocol = {
        "schema": "conseqa-recovery-controller-study-v1",
        "protocol_git_path": "output/synthetic/protocol.json",
        "source": {
            "root": "Z:/nonexistent-original-machine/source",
            "commit": source,
            "files": {
                name: {"sha256": portable.sha(data), "bytes": len(data)}
                for name, data in files.items()
            },
        },
        "runtime": {
            "framework_version": "2.1.1",
            "distribution_version": "2.1.1",
            "python_executable": "Z:/nonexistent-original-machine/venv/python.exe",
            "python_sha256": "a" * 64,
            "framework_path": "Z:/nonexistent-original-machine/venv/site-packages/consequa_x",
            "runtime_file_sha256": {
                "__init__.py": portable.sha(files["src/consequa_x/__init__.py"])
            },
        },
    }
    protocol_bytes = encoded(protocol)
    commit = run_git(
        repo,
        "commit-tree",
        tree_object(repo, {**files, protocol["protocol_git_path"]: protocol_bytes}),
        "-p",
        source,
        data=b"synthetic protocol fixture\n",
    )
    digest = portable.sha(protocol_bytes)
    started = {
        "source_commit": source,
        "protocol_commit": commit,
        "protocol_sha256": digest,
        "started_utc": "2001-01-02T00:00:00+00:00",
        "retry_allowed": False,
        "canonical_claim_path": f"Z:/nonexistent-original-machine/source/output/.recovery-run-claims/{digest}.json",
        "output": "Z:/nonexistent-original-machine/retained-study",
        "protocol_path": "Z:/nonexistent-original-machine/source/output/synthetic/protocol.json",
    }
    return repo, protocol, started, digest, source, commit


def frozen_auditor():
    return portable.load_verified_auditor(FROZEN_BYTES, portable.sha(FROZEN_BYTES), "a" * 40)


def test_git_objects_and_declarations_work_without_original_host_paths(tmp_path):
    repo, protocol, started, digest, source, commit = git_fixture(tmp_path)
    blob, result = portable.verify_git_bindings(repo, protocol, started, digest, source, commit)
    assert blob == FROZEN_BYTES
    assert result["source_commit"] == source
    assert result["recorded_framework_files_crosschecked_to_source"] == 1
    claims = portable.verify_retained_claim(repo, protocol, started, encoded(started), digest)
    assert claims["retained_claim_copy_verified"] is False
    assert claims["first_run_exclusivity_proven"] is False
    assert claims["live_claim_files_checked"] is False
    # No checkout is populated, and the original Z: paths are only strings.
    assert not (repo / portable.AUDITOR_PATH).exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "source-byte",
        "source-pin",
        "protocol-pin",
        "protocol-hash",
        "runtime-declaration",
        "start-time",
    ],
)
def test_git_source_protocol_and_runtime_declaration_tampering_rejected(tmp_path, mutation):
    repo, protocol, started, digest, source, commit = git_fixture(tmp_path)
    if mutation == "source-byte":
        protocol["source"]["files"][portable.AUDITOR_PATH]["sha256"] = "0" * 64
    elif mutation == "source-pin":
        source = "b" * 40
    elif mutation == "protocol-pin":
        commit = "c" * 40
    elif mutation == "protocol-hash":
        digest = "0" * 64
    elif mutation == "runtime-declaration":
        protocol["runtime"]["runtime_file_sha256"]["__init__.py"] = "0" * 64
    else:
        started["started_utc"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        portable.verify_git_bindings(repo, protocol, started, digest, source, commit)


def test_frozen_auditor_hash_is_checked_before_execution_and_import_boundary():
    payload = b"raise RuntimeError('unverified source executed')\n"
    with pytest.raises(ValueError, match="before import"):
        portable.load_verified_auditor(payload, "0" * 64, "a" * 40)
    forbidden = b"import research.recovery_study.world\n"
    with pytest.raises(ValueError, match="prohibited"):
        portable.load_verified_auditor(forbidden, portable.sha(forbidden), "a" * 40)
    assert frozen_auditor().METHODS[-1] == "consequax_poll"


def test_retained_claim_copy_is_optional_but_cannot_disagree(tmp_path):
    repo, protocol, started, digest, _, _ = git_fixture(tmp_path)
    claim = tmp_path / "public-claim-copy.json"
    claim.write_bytes(encoded(started))
    result = portable.verify_retained_claim(
        repo, protocol, started, encoded(started), digest, claim
    )
    assert result["retained_claim_copy_verified"] is True
    claim.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="differs"):
        portable.verify_retained_claim(repo, protocol, started, encoded(started), digest, claim)
    changed = deepcopy(started)
    changed["canonical_claim_path"] = "Z:/unrelated/claim.json"
    with pytest.raises(ValueError, match="canonical-claim"):
        portable.verify_retained_claim(repo, protocol, changed, encoded(changed), digest)


def empty_inventory_database(path):
    """Independent zero-effect fixture for a failed retained slot's lifecycle audit."""
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE effects(effect_id TEXT PRIMARY KEY, committed_at_ms INTEGER, removed_at_ms INTEGER,
          payload_json TEXT, reported_origin_json TEXT, causal_action_id TEXT, causal_actor TEXT, causal_attempt_id TEXT);
        CREATE TABLE pending_events(seq INTEGER PRIMARY KEY, due_ms INTEGER, kind TEXT, event_json TEXT, applied INTEGER);
        CREATE TABLE idempotency(operation_id TEXT PRIMARY KEY, actor TEXT, first_attempt_id TEXT);
        CREATE TABLE inventory_stock(stock_key TEXT PRIMARY KEY, available INTEGER);
        CREATE TABLE inventory_reservations(effect_id TEXT PRIMARY KEY, stock_key TEXT, quantity INTEGER, state TEXT);
        CREATE TABLE support_tickets(ticket_id TEXT PRIMARY KEY, status TEXT, queue TEXT);
        CREATE TABLE ticket_transitions(effect_id TEXT PRIMARY KEY, ticket_id TEXT, status TEXT, queue TEXT, state TEXT);
        CREATE TABLE delivery_registrations(effect_id TEXT PRIMARY KEY, artifact_id TEXT, delivery_channel TEXT, checksum TEXT, state TEXT);
        """)
        db.execute(
            "INSERT INTO inventory_stock VALUES(?,20)", ('["synthetic-store","synthetic-item"]',)
        )
    return path


def small_retained_fixture(tmp_path, auditor, *, with_database=True):
    root = tmp_path / "synthetic-retained"
    root.mkdir()
    (root / "trials").mkdir()
    (root / "databases").mkdir()
    payload = {
        "warehouse": "synthetic-store",
        "sku": "synthetic-item",
        "quantity": 2,
        "reservation_ref": "synthetic-ref",
    }
    pc = {
        "operation_id": "synthetic-op",
        "actor": "synthetic-agent",
        "initial_at_ms": 0,
        "domain": "inventory_reservation",
        "target": {"predicate": "record_present", "expected": payload, "exact_count": 1},
        "payload": payload,
        "deadline_ms": 50,
        "stability_ms": 30,
        "recovery_deadline_ms": 120,
        "safety_horizon_ms": 180,
        "scope_fields": ["warehouse", "sku", "reservation_ref"],
        "scope": {key: payload[key] for key in ("warehouse", "sku", "reservation_ref")},
        "native_idempotency": False,
    }
    schedule = [
        {
            "trial_id": f"synthetic-{index}",
            "case_id": "synthetic-case",
            "family_id": "synthetic-family",
            "domain": "inventory_reservation",
            "seed": 0,
            "method": method,
        }
        for index, method in enumerate(auditor.METHODS)
    ]
    protocol = {
        "schema": "conseqa-recovery-controller-study-v1",
        "schedule": schedule,
        "methods": list(auditor.METHODS),
        "case_count": 1,
        "family_count": 1,
        "seed_count": 1,
        "design": {"analysis": "Synthetic fixture only"},
    }
    rows = []
    for index, slot in enumerate(schedule):
        row = {
            **slot,
            "status": "failed",
            "metrics": {"completed": False, "operational_safe_recovery": False},
        }
        trial = {
            **row,
            "public_case": pc,
            "trajectory": [],
            "source_receipt": {"source": "synthetic-ledger"},
        }
        if with_database and index == 0:
            db = empty_inventory_database(tmp_path / "synthetic.sqlite")
            raw = db.read_bytes()
            name = f"databases/{slot['trial_id']}.sqlite.gz"
            (root / name).write_bytes(gzip.compress(raw, mtime=0))
            trial["database"] = {"path": name, "sha256_uncompressed": portable.sha(raw)}
        (root / "trials" / f"{slot['trial_id']}.json.gz").write_bytes(
            gzip.compress(encoded(trial), mtime=0)
        )
        rows.append(row)
    (root / "protocol.json").write_bytes(encoded(protocol))
    digest = portable.sha(encoded(protocol))
    (root / "started.json").write_bytes(b"{}\n")
    (root / "analysis-rows.jsonl").write_bytes(b"".join(encoded(row) for row in rows))
    summary = auditor.recompute_summary(rows, protocol)
    (root / "summary.json").write_bytes(
        encoded({**summary, "protocol_sha256": digest, "collection_seconds": 0})
    )
    receipt = {
        "protocol_sha256": digest,
        "planned_trials": 5,
        "completed_trials": 0,
        "failed_trials": 5,
    }
    manifest = {
        "files": {
            path.relative_to(root).as_posix(): portable.sha(path.read_bytes())
            for path in root.rglob("*")
            if path.is_file()
        }
    }
    return root, protocol, receipt, manifest


def test_small_semantic_loop_queries_sqlite_and_retains_failed_denominators(tmp_path):
    auditor = frozen_auditor()
    root, protocol, receipt, manifest = small_retained_fixture(tmp_path, auditor)
    summary, lifecycle = portable.audit_retained_semantics(
        auditor, root, protocol, receipt, manifest
    )
    assert summary["failed_trials"] == 5 and summary["completed_trials"] == 0
    assert lifecycle["sqlite_snapshots_queried"] == 1
    assert len(lifecycle["failed_slots_without_databases"]) == 4
    for group in summary["methods"]:
        assert group["metrics"]["operational_safe_recovery"]["observed"] == 1
        assert group["metrics"]["operational_safe_recovery"]["sum"] == 0
        assert group["metrics"]["safe_recovery"]["observed"] == 0
    # The public full-audit entry enforces the real frozen plan separately.
    with pytest.raises(ValueError):
        auditor._validate_plan(protocol)


@pytest.mark.parametrize(
    "mutation", ["sqlite-state", "raw-hash", "analysis-row", "summary", "completed-no-database"]
)
def test_semantic_loop_rejects_retained_tampering(tmp_path, mutation):
    auditor = frozen_auditor()
    root, protocol, receipt, manifest = small_retained_fixture(tmp_path, auditor)
    path = root / "trials/synthetic-0.json.gz"
    trial = portable.json_bytes(gzip.decompress(path.read_bytes()))
    if mutation == "sqlite-state":
        db = tmp_path / "altered.sqlite"
        db.write_bytes(gzip.decompress((root / trial["database"]["path"]).read_bytes()))
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE inventory_stock SET available=-1")
        raw = db.read_bytes()
        (root / trial["database"]["path"]).write_bytes(gzip.compress(raw, mtime=0))
        trial["database"]["sha256_uncompressed"] = portable.sha(raw)
    elif mutation == "raw-hash":
        trial["database"]["sha256_uncompressed"] = "0" * 64
    elif mutation == "analysis-row":
        rows = (root / "analysis-rows.jsonl").read_text().splitlines()
        value = json.loads(rows[0])
        value["metrics"]["operational_safe_recovery"] = True
        rows[0] = json.dumps(value)
        (root / "analysis-rows.jsonl").write_text("\n".join(rows) + "\n")
    elif mutation == "summary":
        value = portable.load_json(root / "summary.json")
        value["failed_trials"] = 4
        (root / "summary.json").write_bytes(encoded(value))
    else:
        trial.pop("database")
        trial["status"] = "completed"
    path.write_bytes(gzip.compress(encoded(trial), mtime=0))
    with pytest.raises(ValueError):
        portable.audit_retained_semantics(auditor, root, protocol, receipt, manifest)


def test_incomplete_or_wrong_protocol_refuses_before_output(tmp_path):
    root = tmp_path / "incomplete"
    root.mkdir()
    (root / "completion-receipt.json").write_bytes(encoded({"complete": False}))
    (root / "manifest.json").write_bytes(encoded({"complete": False}))
    output = tmp_path / "not-created"
    with pytest.raises(ValueError, match="not declared complete"):
        portable.audit_study(root, tmp_path, output)
    assert not output.exists()


@pytest.mark.parametrize(
    "name",
    ["../escape", "trials/../escape", "trials//escape", "C:/escape", "trials\\escape", "/escape"],
)
def test_noncanonical_paths_are_rejected(name):
    with pytest.raises(ValueError):
        portable.relative_path(name)
