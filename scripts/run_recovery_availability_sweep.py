"""Freeze and run a disclosed, controlled availability follow-up.

This post hoc motivated factorial study supplements the original negative
finding. Its generated cases are controlled interventions, not held-out tasks.
No model, remote application, or production service is called.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCHEMA = "conseqa-recovery-availability-sweep-v1"
ORIGINAL_SOURCE_COMMIT = "22e88498cff0e2afd1549803fb4d9645902e74b9"
ORIGINAL_PROTOCOL_SHA256 = "b5c6a06bf1d758678e4d9890aa66872d4036634e2a4a4fd89626bd710bbc5aaa"
METHODS = ("response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll")
DOMAINS = ("inventory_reservation", "support_transition", "delivery_registration")
LAGS = (0, 40, 80, 95)
WINDOW_ENDS = (0, 170, 210, 250)
ENGINE_FILES = ("research/recovery_study/__init__.py", "research/recovery_study/world.py",
                "research/recovery_study/controllers.py", "scripts/run_recovery_controller_study.py",
                "scripts/audit_recovery_controller_study.py")
OWN_FILES = ("scripts/run_recovery_availability_sweep.py", "tests/test_recovery_availability_sweep.py",
             "docs/recovery-availability-sweep.md", "scripts/audit_recovery_availability_sweep.py",
             "tests/test_recovery_availability_audit.py")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def dump(path, value):
    with Path(path).open("xb") as stream:
        stream.write(json_bytes(value))


def binding(path):
    return {"sha256": sha(path), "bytes": Path(path).stat().st_size}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


def git_blob(root, revision, name):
    return subprocess.check_output(["git", "-C", str(root), "show", f"{revision}:{name}"])


def byte_binding(value):
    return {"sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}


def engine_binding(root):
    files = {}
    for name in ENGINE_FILES:
        expected = byte_binding(git_blob(root, ORIGINAL_SOURCE_COMMIT, name))
        if binding(root / name) != expected:
            raise ValueError(f"Original engine changed from 22e8849: {name}")
        files[name] = expected
    return {"commit": ORIGINAL_SOURCE_COMMIT, "files": files}


def load_engine():
    """Import only the unchanged, locally hash-bound original driver."""
    path = ROOT / "scripts/run_recovery_controller_study.py"
    spec = importlib.util.spec_from_file_location("availability_original_recovery_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != path.resolve():
        raise ValueError("Original runner imported from another checkout")
    return module


def runtime():
    import consequa_x

    package = Path(consequa_x.__file__).resolve().parent
    if package != (Path(sysconfig.get_paths()["purelib"]) / "consequa_x").resolve():
        raise ValueError("Framework must be the isolated installed distribution, not a source checkout")
    files = sorted(p for p in package.rglob("*") if p.is_file() and p.suffix in (".py", ".json"))
    value = {"python_executable": str(Path(sys.executable).resolve()), "python_sha256": sha(sys.executable),
             "python_version": sys.version, "framework_version": consequa_x.__version__,
             "distribution_version": importlib.metadata.version("consequa-x"),
             "framework_path": str(package),
             "runtime_file_sha256": {p.relative_to(package).as_posix(): sha(p) for p in files}}
    if value["framework_version"] != "2.1.1" or value["distribution_version"] != "2.1.1":
        raise ValueError("Use the isolated installed 2.1.1 environment")
    expected_names = git(ROOT, "ls-tree", "-r", "--name-only", ORIGINAL_SOURCE_COMMIT, "src/consequa_x").splitlines()
    expected = {name.removeprefix("src/consequa_x/"):
                hashlib.sha256(git_blob(ROOT, ORIGINAL_SOURCE_COMMIT, name)).hexdigest()
                for name in expected_names if Path(name).suffix in (".py", ".json")}
    if value["runtime_file_sha256"] != expected:
        raise ValueError("Installed framework payload differs from original 22e8849 Git bytes")
    return value


def controlled_case(domain, lag_ms, unavailable_until_ms, incomplete_until_ms, *, prefix="availability"):
    """Build a declared intervention; callers must separately validate its grid."""
    if domain not in DOMAINS:
        raise ValueError("Unsupported controlled domain")
    delays = (lag_ms, unavailable_until_ms, incomplete_until_ms)
    if any(type(value) is not int or value < 0 for value in delays):
        raise ValueError("Controlled delays must be nonnegative integers")
    profile = f"lag{lag_ms:03d}-unavailable{unavailable_until_ms:03d}-incomplete{incomplete_until_ms:03d}"
    identity = f"{prefix}-{domain}-{profile}"
    payloads = {
        "inventory_reservation": {"warehouse": f"{identity}-warehouse", "sku": f"{identity}-sku",
                                  "quantity": 2, "reservation_ref": f"{identity}-reservation"},
        "support_transition": {"ticket_id": f"{identity}-ticket", "status": "resolved", "queue": "service"},
        "delivery_registration": {"artifact_id": f"{identity}-artifact", "delivery_channel": "direct",
                                   "checksum": f"{identity}-checksum"},
    }
    fields = {"inventory_reservation": ["warehouse", "sku", "reservation_ref"],
              "support_transition": ["ticket_id"],
              "delivery_registration": ["artifact_id", "delivery_channel"]}[domain]
    payload = payloads[domain]
    windows = []
    if unavailable_until_ms:
        windows.append({"start_ms": 0, "until_ms": unavailable_until_ms, "available": False})
    if incomplete_until_ms:
        windows.append({"start_ms": 0, "until_ms": incomplete_until_ms, "complete": False})
    return {"case_id": identity, "family_id": profile, "domain": domain,
            "operation_id": f"{identity}-operation", "actor": "availability-agent", "initial_at_ms": 0,
            "target": {"predicate": "record_present", "expected": deepcopy(payload), "exact_count": 1},
            "payload": deepcopy(payload), "deadline_ms": 100, "stability_ms": 50,
            "recovery_deadline_ms": 250, "safety_horizon_ms": 330, "scope_fields": fields,
            "scope": {key: payload[key] for key in fields}, "native_idempotency": True,
            "_availability_profile": {"profile_id": profile, "lag_ms": lag_ms,
                                      "unavailable_until_ms": unavailable_until_ms,
                                      "incomplete_until_ms": incomplete_until_ms},
            "_world": {"dispatch_plans": [{"status": "success", "response_delay_ms": 2,
                                             "commit_delay_ms": 10}],
                       "readback": {"lag_ms": lag_ms, "windows": windows}}}


def generated_cases():
    return [controlled_case(domain, lag, unavailable, incomplete)
            for domain in DOMAINS for lag in LAGS
            for unavailable in WINDOW_ENDS for incomplete in WINDOW_ENDS]


def validate_cases(cases):
    if cases != generated_cases():
        raise ValueError("Cases differ from the full declared controlled grid")
    ids = [case["case_id"] for case in cases]
    if len(cases) != 192 or len(set(ids)) != 192:
        raise ValueError("Controlled grid identities/counts differ")


def schedule(cases):
    rows = []
    for index, case in enumerate(cases):
        offset = index % len(METHODS)
        for method in METHODS[offset:] + METHODS[:offset]:
            rows.append({"trial_id": f"trial_{len(rows):06d}", "case_id": case["case_id"],
                         "family_id": case["family_id"], "domain": case["domain"], "seed": 0,
                         "method": method, **case["_availability_profile"]})
    return rows


def validate_protocol(protocol):
    if protocol["schema"] != SCHEMA:
        raise ValueError("Protocol schema mismatch")
    validate_cases(protocol["cases"])
    if protocol["schedule"] != schedule(protocol["cases"]):
        raise ValueError("Protocol schedule differs from the declared matching/rotation")
    expected = byte_binding(json_bytes({"schema": SCHEMA, "cases": protocol["cases"]}))
    if {key: protocol["cases_json"][key] for key in ("sha256", "bytes")} != expected:
        raise ValueError("Case JSON byte binding differs")
    if (protocol["methods"] != list(METHODS) or protocol["case_count"] != 192
            or protocol["profile_count"] != 64 or protocol["domain_count"] != 3 or protocol["seed_count"] != 1):
        raise ValueError("Protocol dimensions differ")


def freeze(args):
    revision = git(ROOT, "rev-parse", "HEAD")
    if revision != args.expected_source_commit:
        raise ValueError("Source HEAD differs from requested freeze")
    files = {name: binding(ROOT / name) for name in OWN_FILES}
    for name, expected in files.items():
        if byte_binding(git_blob(ROOT, revision, name)) != expected:
            raise ValueError(f"Uncommitted source cannot be frozen: {name}")
    engine = engine_binding(ROOT)
    original_driver = load_engine()
    environment = runtime()
    cases = generated_cases()
    validate_cases(cases)
    case_payload = {"schema": SCHEMA, "cases": cases}
    protocol = {"schema": SCHEMA, "frozen_utc": now(), "case_count": 192,
        "profile_count": 64, "domain_count": 3, "seed_count": 1, "methods": list(METHODS),
        "protocol_git_path": f"output/{args.output.name}/protocol.json",
        "cases_json": {**byte_binding(json_bytes(case_payload)), "git_path": f"output/{args.output.name}/cases.json"},
        "cases": cases, "schedule": schedule(cases),
        "source": {"root": str(ROOT), "commit": revision, "origin": git(ROOT, "remote", "get-url", "origin"),
                   "files": files}, "engine": engine, "runtime": environment,
        "original_study_protocol_sha256": ORIGINAL_PROTOCOL_SHA256,
        "design": {"type": "Post hoc motivated, prospectively frozen controlled availability factorial follow-up",
            "motivation": "The completed and audited original study did not expose an incremental polling benefit. This follow-up deliberately intervenes on evidence availability; it supplements and does not replace that original negative result.",
            "authorship": "Explicit controlled case generation by the study developers; not independently authored, externally validated, or held-out tasks.",
            "factors": {"lag_ms": list(LAGS), "unavailable_until_ms": list(WINDOW_ENDS),
                        "incomplete_until_ms": list(WINDOW_ENDS)},
            "fixed": {"deadline_ms": 100, "stability_ms": 50, "horizon_ms": 150,
                      "recovery_deadline_ms": 250, "safety_horizon_ms": 330,
                      "commit_at_ms": 10, "success_response_at_ms": 2, "native_idempotency": True,
                      "dispatch_cap": 2, "read_opportunities_ms": [50, 150, 190, 230]},
            "matching": "One seed (0), every profile in all three domains and all five unchanged original policies. Method order rotates by case index. Same stable logical identity/provider semantics/budget ceilings; realized read histories may differ.",
            "hypotheses": {"physical": "Every completed arm has one correct committed effect by D, persistent through S, with no duplicate/unwanted event and no dispatch differences.",
                "one_final_read": "A definite correct global-state claim in 1/64 profiles per domain: all three delays zero.",
                "polling_reference_state": "A definite correct global-state claim in 27/64 profiles per domain: lag<=80 and both window ends<=210. Conditions intersect at the available read time, not independently sampled probabilities.",
                "response_retry": "The response-based policy reports success on the immediate ACK in all profiles; this is not evidence-grounded verification. The uniform-positive design cannot measure its false-success risk."},
            "primary": "Operational safe-recovery over every scheduled slot, as in the original study. Failed slots contribute zero operational success; missing physical/semantic outcomes remain unavailable. The uniform-safe design is expected to show no primary improvement.",
            "secondary": "Correct definite global-state reporting yield, original/recovery completion, action-linked reporting, harmful effects, and charged reads/dispatches. Endpoint definitions and original summarizer are unchanged.",
            "endpoints": list(original_driver.ENDPOINTS),
            "contrasts": [list(pair) for pair in original_driver.CONTRASTS],
            "analysis": "Exact full-grid finite counts and profile/domain/case tables; paired differences and equal-profile means over the full 64-profile grid. No population confidence intervals, bootstrap, p-values, task generalization, or autonomous-agent benchmark claim. No multiplicity-based selection; all planned factors/endpoints retained.",
            "failures": "Exclusive first run; no retry/resume/replacement or exclusions. Keep every scheduled error, journal, compressed raw record and SQLite snapshot. A collection interruption remains incomplete; repair requires a disclosed new protocol.",
            "limitations": ["Motivated after observing the original study; no confirmatory claim about that earlier negative finding.",
                "Polling availability benefit, if observed, is shared by the unchanged strong reference and state-only controller; no framework superiority or recovery-action benefit follows.",
                "Admitted source, exhaustive history, commit watermarks and provider guarantees are application assumptions.",
                "No false-ACK, late commit, wrong payload, external actor, removal, adversarial provenance or task-population diversity in this controlled grid.",
                "Finite safety horizon cannot establish unbounded exactly-once behavior.",
                "One seed per deterministic controlled cell; three domains repeat the same mechanism, not independent population samples."],
            "new_model_calls": 0, "external_application_calls": 0}}
    validate_protocol(protocol)
    args.output.mkdir(parents=True, exist_ok=False)
    dump(args.output / "cases.json", case_payload)
    dump(args.output / "protocol.json", protocol)
    dump(args.output / "protocol.sha256.json", binding(args.output / "protocol.json"))
    print(json.dumps({"protocol_sha256": sha(args.output / "protocol.json"),
                      "planned_trials": len(protocol["schedule"]), "source_commit": revision}))


def verify_frozen(protocol):
    source = protocol["source"]
    if ROOT.resolve() != Path(source["root"]).resolve():
        raise ValueError("Executing checkout differs from frozen source root")
    if git(ROOT, "rev-parse", "HEAD") != source["commit"]:
        raise ValueError("Frozen source worktree moved")
    if git(ROOT, "remote", "get-url", "origin") != source["origin"]:
        raise ValueError("Frozen source origin changed")
    if set(source["files"]) != set(OWN_FILES):
        raise ValueError("Frozen source inventory differs")
    for name, expected in source["files"].items():
        if binding(ROOT / name) != expected or byte_binding(git_blob(ROOT, source["commit"], name)) != expected:
            raise ValueError(f"Frozen source changed: {name}")
    if engine_binding(ROOT) != protocol["engine"]:
        raise ValueError("Original engine binding differs")
    from research.recovery_study import controllers, world

    for module, name in ((controllers, "controllers.py"), (world, "world.py")):
        if Path(module.__file__).resolve() != ROOT / "research/recovery_study" / name:
            raise ValueError("Research module imported from another checkout")
    if runtime() != protocol["runtime"]:
        raise ValueError("Installed framework/interpreter identity changed")


def verify_prospective_commit(protocol, digest, protocol_commit):
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor",
                    protocol["source"]["commit"], protocol_commit], check=True)
    if hashlib.sha256(git_blob(ROOT, protocol_commit, protocol["protocol_git_path"])).hexdigest() != digest:
        raise ValueError("Prospective committed protocol differs")
    case_blob = git_blob(ROOT, protocol_commit, protocol["cases_json"]["git_path"])
    if byte_binding(case_blob) != {key: protocol["cases_json"][key] for key in ("sha256", "bytes")}:
        raise ValueError("Prospective committed case JSON differs")
    if int(git(ROOT, "show", "-s", "--format=%ct", protocol_commit)) > time.time():
        raise ValueError("Protocol commit is in the future")


def reserve_run(protocol_path, protocol, digest, output, database_root, protocol_commit):
    canonical = ROOT / "output/.availability-sweep-run-claims" / f"{digest}.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    claim = {"schema": SCHEMA, "started_utc": now(), "protocol_sha256": digest,
             "retry_allowed": False, "output": str(output.resolve()),
             "database_root": str(database_root.resolve()), "protocol_commit": protocol_commit,
             "canonical_claim_path": str(canonical.resolve()), "protocol_path": str(protocol_path.resolve()),
             "protocol_git_path": protocol["protocol_git_path"],
             "cases_git_path": protocol["cases_json"]["git_path"],
             "source_commit": protocol["source"]["commit"], "original_engine_commit": ORIGINAL_SOURCE_COMMIT}
    dump(canonical, claim)
    return claim


def validate_roots(output, database_root):
    a, b = output.resolve(), database_root.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("Output and database roots must be separate, nonnested directories")
    if output.exists() or database_root.exists():
        raise FileExistsError("Output and database roots must both be new")


def run(args):
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    digest = sha(args.protocol)
    if digest != args.expected_protocol_sha256:
        raise ValueError("Protocol hash mismatch")
    validate_protocol(protocol)
    verify_frozen(protocol)
    verify_prospective_commit(protocol, digest, args.protocol_commit)
    case_bytes = (args.protocol.parent / "cases.json").read_bytes()
    if byte_binding(case_bytes) != {key: protocol["cases_json"][key] for key in ("sha256", "bytes")}:
        raise ValueError("Local case JSON differs from frozen protocol")
    validate_roots(args.output, args.database_root)
    engine = load_engine()
    claim = reserve_run(args.protocol, protocol, digest, args.output, args.database_root, args.protocol_commit)
    args.output.mkdir(parents=True, exist_ok=False)
    dump(args.protocol.parent / "run-claim.json", claim)
    dump(args.output / "started.json", claim)
    shutil.copyfile(args.protocol, args.output / "protocol.json")
    shutil.copyfile(args.protocol.parent / "cases.json", args.output / "cases.json")
    for name in ("trials", "databases"):
        (args.output / name).mkdir()
    args.database_root.mkdir(parents=True, exist_ok=False)
    cases = {case["case_id"]: case for case in protocol["cases"]}
    compact = []
    started = time.monotonic()
    with (args.output / "analysis-rows.jsonl").open("x", encoding="utf-8", newline="\n") as journal:
        for slot in protocol["schedule"]:
            at = time.monotonic()
            database = args.database_root / f"{slot['trial_id']}.sqlite"
            try:
                row = engine.execute(cases[slot["case_id"]], slot["seed"], slot["method"], database)
            except Exception as exc:
                row = {"status": "failed", "error_type": type(exc).__name__, "error": str(exc),
                       "metrics": {"completed": False, "operational_safe_recovery": False}}
            row.update(schema=SCHEMA, **slot, wall_seconds=time.monotonic() - at)
            if database.exists():
                packed = f"databases/{slot['trial_id']}.sqlite.gz"
                with database.open("rb") as src, (args.output / packed).open("xb") as dst:
                    with gzip.GzipFile(fileobj=dst, mode="wb", filename="", mtime=0) as zipped:
                        shutil.copyfileobj(src, zipped)
                row["database"] = {"path": packed, "sha256_uncompressed": sha(database)}
            with (args.output / "trials" / f"{slot['trial_id']}.json.gz").open("xb") as dst:
                with gzip.GzipFile(fileobj=dst, mode="wb", filename="", mtime=0) as zipped:
                    zipped.write(json_bytes(row))
            small = {**slot, "status": row["status"], "metrics": row["metrics"]}
            compact.append(small)
            journal.write(json.dumps(small, sort_keys=True, allow_nan=False) + "\n")
            journal.flush()
            if len(compact) % 100 == 0:
                print(json.dumps({"completed_slots": len(compact), "planned": len(protocol["schedule"]),
                                  "failed": sum(row["status"] != "completed" for row in compact)}), flush=True)
    validate_protocol(protocol)
    verify_frozen(protocol)
    summary = engine.summarize(compact, protocol)
    summary.update(schema=SCHEMA, protocol_sha256=digest, collection_seconds=time.monotonic() - started,
                   controlled_profile_count=64, domain_count=3)
    dump(args.output / "summary.json", summary)
    inventory = {path.relative_to(args.output).as_posix(): sha(path)
                 for path in sorted(args.output.rglob("*")) if path.is_file()}
    dump(args.output / "manifest.json", {"schema": SCHEMA, "complete": True, "files": inventory})
    dump(args.output / "completion-receipt.json", {"schema": SCHEMA, "complete": True,
        "completed_utc": now(), "protocol_sha256": digest, "manifest_sha256": sha(args.output / "manifest.json"),
        "planned_trials": len(protocol["schedule"]), "completed_trials": summary["completed_trials"],
        "failed_trials": summary["failed_trials"], "new_model_calls": 0, "external_application_calls": 0,
        "no_retries_or_replacements": True, "source_and_runtime_final_recheck": True})
    print(json.dumps({"complete": True, "completed": summary["completed_trials"],
                      "failed": summary["failed_trials"], "summary_sha256": sha(args.output / "summary.json")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freezing = sub.add_parser("freeze")
    freezing.add_argument("--expected-source-commit", required=True)
    freezing.add_argument("--output", type=Path, required=True)
    running = sub.add_parser("run")
    running.add_argument("--protocol", type=Path, required=True)
    running.add_argument("--expected-protocol-sha256", required=True)
    running.add_argument("--protocol-commit", required=True)
    running.add_argument("--output", type=Path, required=True)
    running.add_argument("--database-root", type=Path, required=True)
    args = parser.parse_args()
    (freeze if args.command == "freeze" else run)(args)


if __name__ == "__main__":
    main()
