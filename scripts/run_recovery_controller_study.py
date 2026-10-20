"""Freeze and execute a version-bound, finite-suite recovery-controller study.

Development uses synthetic fixtures. The independently authored case file is
read only by freeze/run, never used to select policies or tune measured outputs.
No model, remote service, or production application is invoked by this runner.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCHEMA = "conseqa-recovery-controller-study-v1"
METHODS = ("response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll")
ENDPOINTS = (
    "operational_safe_recovery", "original_completion", "recovery_completion", "safe_recovery", "duplicate_event",
    "unwanted_event", "state_false_success", "action_linked_false_success",
    "state_wrong_definite", "action_linked_wrong_definite", "state_definite",
    "state_abstention", "action_linked_definite", "action_linked_abstention",
    "dispatches", "reads", "waits", "decision_time_ms", "own_effect_count",
    "duplicate_count", "unwanted_effect_count",
)
CONTRASTS = (("consequax_poll", "response_retry"), ("consequax_poll", "readback_state"),
             ("consequax_poll", "reference"), ("consequax_poll", "consequax_one_read"))


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


def binding(path):
    p = Path(path)
    return {"sha256": sha(p), "bytes": p.stat().st_size}


def source_files(root):
    paths = list((root / "src/consequa_x").rglob("*.py"))
    paths += list((root / "src/consequa_x/schemas").glob("*.json"))
    paths += list((root / "research/recovery_study").glob("*.py"))
    paths += [root / "research/recovery_study/heldout_cases.json"]
    paths += [root / p for p in (
        "scripts/run_recovery_controller_study.py", "scripts/build_recovery_human_review.py",
        "scripts/audit_recovery_controller_study.py", "tests/test_recovery_world.py",
        "tests/test_recovery_controllers.py", "tests/test_recovery_study_runner.py",
        "tests/test_recovery_human_review.py", "tests/test_recovery_controller_audit.py",
        "docs/recovery-world-design.md", "docs/recovery-controller-design.md",
        "docs/recovery-study-design-review.md", "docs/stronger-paper-research-questions.md")]
    return {p.relative_to(root).as_posix(): binding(p) for p in sorted(set(paths))}


def runtime():
    import consequa_x
    package = Path(consequa_x.__file__).resolve().parent
    files = [p for p in package.rglob("*") if p.is_file() and p.suffix in (".py", ".json")]
    return {"python_executable": str(Path(sys.executable).resolve()),
            "python_sha256": sha(sys.executable), "python_version": sys.version,
            "framework_version": consequa_x.__version__,
            "distribution_version": importlib.metadata.version("consequa-x"),
            "framework_path": str(package),
            "runtime_file_sha256": {p.relative_to(package).as_posix(): sha(p) for p in sorted(files)}}


def validate_case(case):
    required = {"case_id", "family_id", "domain", "operation_id", "actor", "target",
                "deadline_ms", "stability_ms", "recovery_deadline_ms", "safety_horizon_ms",
                "scope", "scope_fields", "_world"}
    if not required <= case.keys():
        raise ValueError("Missing case fields")
    d, h = case["deadline_ms"], case["deadline_ms"] + case["stability_ms"]
    r, s = case["recovery_deadline_ms"], case["safety_horizon_ms"]
    if not (0 < d <= h <= r <= s and h + 80 <= s):
        raise ValueError("Invalid fixed/recovery/safety or polling horizon")
    if case.get("initial_at_ms", 0) != 0 or case["target"]["predicate"] != "record_present":
        raise ValueError("Unsupported registration/predicate in this study")


def read_schedule(case):
    h = case["deadline_ms"] + case["stability_ms"]
    return sorted(set([case["deadline_ms"] // 2, h, h + 40, h + 80]))


def schedule(cases, seeds):
    rows = []
    for case_index, case in enumerate(cases):
        for seed in range(seeds):
            offset = (case_index + seed) % len(METHODS)
            for method in METHODS[offset:] + METHODS[:offset]:
                rows.append({"trial_id": f"trial_{len(rows):06d}", "case_id": case["case_id"],
                             "family_id": case["family_id"], "domain": case["domain"],
                             "seed": seed, "method": method})
    return rows


def freeze(args):
    from research.recovery_study.world import load_cases
    if args.seeds < 1:
        raise ValueError("The seed count must be positive")
    revision = git(ROOT, "rev-parse", "HEAD")
    if revision != args.expected_source_commit:
        raise ValueError("Source HEAD differs from the requested freeze")
    files = source_files(ROOT)
    for name, declaration in files.items():
        blob = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{revision}:{name}"])
        if hashlib.sha256(blob).hexdigest() != declaration["sha256"]:
            raise ValueError(f"Uncommitted source cannot be frozen: {name}")
    env = runtime()
    if env["framework_version"] != "2.1.1" or env["distribution_version"] != "2.1.1":
        raise ValueError("Use the isolated installed 2.1.1 environment")
    for name, digest in env["runtime_file_sha256"].items():
        if files[f"src/consequa_x/{name}"]["sha256"] != digest:
            raise ValueError(f"Installed framework differs from frozen source: {name}")
    cases = load_cases()
    for case in cases:
        validate_case(case)
    ids = [c["case_id"] for c in cases]
    if len(ids) != len(set(ids)) or len(cases) != 24 or len({c["family_id"] for c in cases}) != 12:
        raise ValueError("Authored corpus identities/counts differ from the design")
    protocol = {"schema": SCHEMA, "frozen_utc": now(), "case_count": len(cases),
        "protocol_git_path": f"output/{args.output.name}/protocol.json",
        "family_count": 12, "seed_count": args.seeds, "methods": list(METHODS),
        "schedule": schedule(cases, args.seeds), "source": {"root": str(ROOT), "commit": revision, "files": files},
        "runtime": env, "framework_build_revision": "b73ecd00fc9b4b8b3f9b8182aa8ed652419d7e54",
        "human_review_builder_sha256": files["scripts/build_recovery_human_review.py"]["sha256"],
        "design": {"type": "AI-assisted author-separated held-out finite synthetic SQLite application challenge suite",
            "author_separation": "World/case author did not inspect controllers or old studies; controller author did not inspect held-out case file. Root orchestrator inspected public interfaces and synthetic development fixtures, not held-out case values before this freeze.",
            "development": "Only separate synthetic fixtures; no held-out episodes executed before source/protocol commit.",
            "dispatch_cap": 2, "read_opportunities": "sorted unique [deadline//2,H,H+40,H+80], H=deadline+stability",
            "matching": "Same case/seed/stable operation key/provider semantics/budget ceilings; methods rotated by case-index+seed. Differing actions may cause different live readbacks; no claim of identical realized evidence across differing histories.",
            "native_capability": "Every method receives the same provider idempotency semantics. Strong policies exploit a declared native same-key deduplication guarantee for bounded ambiguous-timeout retries; absent that guarantee they require explicit terminal resolution and fresh absence.",
            "terminal_gate": "Fresh admitted complete absence plus explicit terminal-no-commit guarantee for EVERY attempted request; study application policy, not framework finality.",
            "primary": "Operational safe-recovery yield over EVERY scheduled slot: completed run whose global target meets recovery deadline and persists through safety horizon, with no own duplicate or unwanted effect through that cutoff. Failed slots contribute zero operational success; their physical/semantic outcomes remain unknown, not false. Original SLA is a separate unchanged target.",
            "contrasts": [list(p) for p in CONTRASTS], "endpoints": list(ENDPOINTS),
            "analysis": "Exact finite-suite counts, per-case/per-family values, paired case-seed differences and equal-family means. No task-population p-values/CIs, no model ranking, no claim that 128 repeats create independent tasks. Strong-reference parity is conformance, not superiority. Missing/failed slots stay in planned denominators; incomplete contrasts are descriptive only.",
            "failures": "Exclusive first run; retain every error, no retries/replacements or case exclusions, process all scheduled slots. Runner failure leaves incomplete artifacts; no resume.",
            "human_review": "All case×method seed-0 rows, no replacements; allowlisted public fixed-target evidence and claims, identifiers blinded, exact evidence/claim duplicates collapsed. Humans recruited by maintainer later; no generated human labels.",
            "new_model_calls": 0, "external_application_calls": 0, "limitations": [
                "Authorship separation is AI-assisted, not independent human authorship.",
                "Finite authored challenge cases, not a sampled task population or autonomous LLM benchmark.",
                "Source admission, terminal guarantees and provider idempotency are explicit application assumptions.",
                "Duplicate event means more own committed effects than the positive logical-operation count through the safety cutoff, including effects later removed; global simultaneous target count is reported separately.",
                "Finite safety cutoff does not establish exactly-once execution under arbitrarily late commits.",
                "Generic framework retry advice alone does not establish provider finality."]}}
    args.output.mkdir(parents=True, exist_ok=False)
    dump(args.output / "protocol.json", protocol)
    dump(args.output / "protocol.sha256.json", binding(args.output / "protocol.json"))
    print(json.dumps({"protocol_sha256": sha(args.output / "protocol.json"),
                      "planned_trials": len(protocol["schedule"]), "source_commit": revision}))


def metrics(report, truth, decision_at_ms):
    if not truth["horizon_reached"] or not truth["safety_horizon_reached"]:
        raise ValueError("Evaluator horizon not reached")
    state, linked = report["reported_state"], report["reported_action_linked"]
    duplicate, unwanted = truth["duplicate_count"] > 0, truth["own_unwanted_effect_count"] > 0
    recovery = bool(truth["eventual_recovery_satisfied"])
    return {"completed": True, "operational_safe_recovery": recovery and not duplicate and not unwanted,
        "original_completion": bool(truth["target_satisfied"]),
        "recovery_completion": recovery, "safe_recovery": recovery and not duplicate and not unwanted,
        "duplicate_event": duplicate, "unwanted_event": unwanted,
        "state_false_success": state is True and truth["target_satisfied"] is False,
        "action_linked_false_success": linked is True and truth["linked_target_satisfied"] is False,
        "state_wrong_definite": state is not None and state != truth["target_satisfied"],
        "action_linked_wrong_definite": linked is not None and linked != truth["linked_target_satisfied"],
        "state_definite": state is not None, "state_abstention": state is None,
        "action_linked_definite": linked is not None, "action_linked_abstention": linked is None,
        "dispatches": report["dispatches"], "reads": report["reads"], "waits": report["waits"],
        "decision_time_ms": decision_at_ms, "own_effect_count": truth["own_effect_count"],
        "duplicate_count": truth["duplicate_count"], "unwanted_effect_count": truth["own_unwanted_effect_count"]}


def execute(case, seed, method, db_path):
    from research.recovery_study.controllers import Controller
    from research.recovery_study.world import World, public_case
    public = public_case(case)
    public["registered_at_ms"] = public["initial_at_ms"]
    row = {"public_case": public, "trajectory": []}
    with World(case, seed, db_path) as world:
        row["source_receipt"] = world.source_receipt
        inputs = dict(action_id=public["operation_id"], actor=public["actor"],
            expected=public["target"]["expected"], scope=public["scope"],
            deadline_ms=public["deadline_ms"], stability_ms=public["stability_ms"],
            source=world.source_receipt["source"], read_times=read_schedule(public), max_dispatches=2,
            exact_count=public["target"]["exact_count"], scope_fields=public["scope_fields"],
            native_idempotency=public["native_idempotency"])
        row["controller_inputs"] = inputs
        policy = Controller(method, **inputs)
        instant = public["initial_at_ms"]
        decision = policy.begin(instant)
        try:
            for _ in range(64):
                target = decision["at_ms"]
                if type(target) is not int or target < instant or target > public["safety_horizon_ms"]:
                    raise ValueError("Policy time is nonmonotonic/outside safety cutoff")
                instant = target
                kind = decision["kind"]
                row["trajectory"].append({"kind": kind, "at_ms": instant, "decision": decision})
                if kind == "dispatch":
                    response = world.dispatch(public["operation_id"], public["actor"], instant)
                    if decision["attempt_id"] != response["attempt_id"]:
                        raise ValueError("Policy/provider attempt IDs differ")
                    instant = response["response_at_ms"]
                    row["trajectory"].append({"kind": "response", "at_ms": instant, "response": response})
                    policy.on_response(response, instant)
                elif kind == "read":
                    observation = world.readback(instant)
                    row["trajectory"].append({"kind": "readback", "at_ms": instant, "observation": observation})
                    policy.on_readback(observation)
                elif kind == "wait":
                    world.advance(instant)
                elif kind in ("stop", "abstain"):
                    break
                else:
                    raise ValueError(f"Unknown policy decision: {kind}")
                decision = policy.decide(instant)
            else:
                raise ValueError("Policy exhausted the fixed 64-transition budget")
            report = policy.finalize()
            truth = world.truth(public["safety_horizon_ms"])
            if report["dispatches"] != truth["metrics"]["dispatch_calls"]:
                raise ValueError("Dispatch accounting mismatch")
            if report["reads"] != truth["metrics"]["readback_calls"]:
                raise ValueError("Read accounting mismatch")
            row.update(status="completed", report=report, truth=truth, decision_at_ms=instant,
                       metrics=metrics(report, truth, instant))
        except Exception as exc:
            row.update(status="failed", error_type=type(exc).__name__, error=str(exc),
                       decision_at_ms=instant, metrics={"completed": False, "operational_safe_recovery": False})
            try:
                row["truth"] = world.truth(public["safety_horizon_ms"])
            except Exception as truth_error:
                row["truth_error"] = str(truth_error)
    return row


def aggregate(rows):
    result = {"planned": len(rows), "completed": sum(r["status"] == "completed" for r in rows)}
    result["failed"] = result["planned"] - result["completed"]
    result["metrics"] = {}
    for name in ENDPOINTS:
        values = [r["metrics"][name] for r in rows if name in r["metrics"]]
        total = sum(values)
        result["metrics"][name] = {"sum": total, "observed": len(values),
            "unavailable": len(rows) - len(values), "mean": total / len(values) if values else None}
    return result


def summarize(rows, protocol):
    summary = {"schema": SCHEMA, "planned_trials": len(protocol["schedule"]),
               "completed_trials": sum(r["status"] == "completed" for r in rows),
               "failed_trials": sum(r["status"] != "completed" for r in rows),
               "methods": [], "families": [], "cases": [], "paired_contrasts": [],
               "inference_scope": protocol["design"]["analysis"]}
    for label, key in (("methods", "method"), ("families", "family_id"), ("cases", "case_id")):
        groups = defaultdict(list)
        for row in rows:
            grouping = (row[key],) if label == "methods" else (row[key], row["method"])
            groups[grouping].append(row)
        for group, members in sorted(groups.items()):
            descriptor = {key: group[0]}
            if label != "methods":
                descriptor["method"] = group[1]
            summary[label].append({**descriptor, **aggregate(members)})
    indexed = {(r["case_id"], r["seed"], r["method"]): r for r in rows}
    pairs = sorted({(r["case_id"], r["seed"]) for r in rows})
    for left, right in CONTRASTS:
        contrast = {"left": left, "right": right, "planned_pairs": len(pairs), "metrics": {}}
        for endpoint in ENDPOINTS:
            differences = defaultdict(list)
            for case, seed in pairs:
                a, b = indexed[(case, seed, left)], indexed[(case, seed, right)]
                if endpoint in a["metrics"] and endpoint in b["metrics"]:
                    differences[a["family_id"]].append(a["metrics"][endpoint] - b["metrics"][endpoint])
            by_family = [{"family_id": family, "pairs": len(values), "sum_difference": sum(values),
                          "mean_difference": sum(values) / len(values)} for family, values in sorted(differences.items())]
            count = sum(p["pairs"] for p in by_family)
            contrast["metrics"][endpoint] = {"pairs": count, "unavailable_pairs": len(pairs) - count,
                "mean_difference": sum(p["sum_difference"] for p in by_family) / count if count else None,
                "equal_family_mean_difference": sum(p["mean_difference"] for p in by_family) / len(by_family) if by_family else None,
                "by_family": by_family}
        summary["paired_contrasts"].append(contrast)
    return summary


def verify_frozen(protocol):
    source = protocol["source"]
    if ROOT.resolve() != Path(source["root"]).resolve():
        raise ValueError("Executing checkout differs from the frozen source root")
    if git(source["root"], "rev-parse", "HEAD") != source["commit"]:
        raise ValueError("Frozen source worktree moved")
    for name, expected in source["files"].items():
        if binding(Path(source["root"]) / name) != expected:
            raise ValueError(f"Frozen source changed: {name}")
    from research.recovery_study import controllers, world
    for module, name in ((controllers, "controllers.py"), (world, "world.py")):
        if Path(module.__file__).resolve() != ROOT / "research/recovery_study" / name:
            raise ValueError("Research module was imported from outside the frozen checkout")
    if runtime() != protocol["runtime"]:
        raise ValueError("Installed framework/interpreter identity changed")


def reserve_run(protocol_path, protocol, digest, output, protocol_commit):
    """One exclusive claim per protocol hash in its bound source checkout.

    The caller's copy/location of protocol.json cannot create a second claim.
    This prevents accidental reruns; it does not prevent an operator manually
    deleting claims or modifying the frozen code, which would be a deviation.
    """
    canonical = ROOT / "output/.recovery-run-claims" / f"{digest}.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    claim = {"started_utc": now(), "protocol_sha256": digest, "retry_allowed": False,
             "output": str(output.resolve()), "protocol_commit": protocol_commit,
             "canonical_claim_path": str(canonical.resolve()),
             "protocol_path": str(protocol_path.resolve()), "source_commit": protocol["source"]["commit"]}
    dump(canonical, claim)
    return claim


def run(args):
    from research.recovery_study.world import load_cases
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    digest = sha(args.protocol)
    if digest != args.expected_protocol_sha256 or protocol["schema"] != SCHEMA:
        raise ValueError("Protocol hash/schema mismatch")
    verify_frozen(protocol)
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor",
                    protocol["source"]["commit"], args.protocol_commit], check=True)
    blob = subprocess.check_output(["git", "-C", str(ROOT), "show",
        f"{args.protocol_commit}:{protocol['protocol_git_path']}"])
    if hashlib.sha256(blob).hexdigest() != digest:
        raise ValueError("Prospective committed protocol differs")
    if int(git(ROOT, "show", "-s", "--format=%ct", args.protocol_commit)) > time.time():
        raise ValueError("Protocol commit is in the future")
    if args.output.exists() or args.database_root.exists():
        raise FileExistsError("Output and database roots must both be new")
    claim = reserve_run(args.protocol, protocol, digest, args.output, args.protocol_commit)
    args.output.mkdir(parents=True, exist_ok=False)
    dump(args.protocol.parent / "run-claim.json", claim)
    dump(args.output / "started.json", claim)
    shutil.copyfile(args.protocol, args.output / "protocol.json")
    for name in ("trials", "databases"):
        (args.output / name).mkdir()
    args.database_root.mkdir(parents=True, exist_ok=False)
    cases = {c["case_id"]: c for c in load_cases()}
    compact = []
    started = time.monotonic()
    with (args.output / "analysis-rows.jsonl").open("x", encoding="utf-8", newline="\n") as analysis:
        for slot in protocol["schedule"]:
            at = time.monotonic()
            database = args.database_root / f"{slot['trial_id']}.sqlite"
            try:
                row = execute(cases[slot["case_id"]], slot["seed"], slot["method"], database)
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
            encoded = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode()
            with (args.output / "trials" / f"{slot['trial_id']}.json.gz").open("xb") as dst:
                with gzip.GzipFile(fileobj=dst, mode="wb", filename="", mtime=0) as zipped:
                    zipped.write(encoded)
            small = {**slot, "status": row["status"], "metrics": row["metrics"]}
            compact.append(small)
            analysis.write(json.dumps(small, sort_keys=True, allow_nan=False) + "\n")
            analysis.flush()
            if len(compact) % 500 == 0:
                print(json.dumps({"completed_slots": len(compact), "planned": len(protocol["schedule"]),
                    "failed": sum(r["status"] != "completed" for r in compact)}), flush=True)
    verify_frozen(protocol)
    summary = summarize(compact, protocol)
    summary.update(protocol_sha256=digest, collection_seconds=time.monotonic() - started)
    dump(args.output / "summary.json", summary)
    inventory = {p.relative_to(args.output).as_posix(): sha(p)
                 for p in sorted(args.output.rglob("*")) if p.is_file()}
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
    freezing.add_argument("--seeds", type=int, default=128)
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
