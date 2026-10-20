"""Portable saved-artifact audit for the controlled availability follow-up.

Only the SHA-bound original semantic auditor is executed. No world, controller,
collection driver, framework, or model is imported. Default verification checks
retained bytes and Git objects; it does not attest the original execution host.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys
import tempfile
import types


SCHEMA = "conseqa-recovery-availability-sweep-v1"
ENGINE_COMMIT = "22e88498cff0e2afd1549803fb4d9645902e74b9"
ORIGINAL_PROTOCOL = "b5c6a06bf1d758678e4d9890aa66872d4036634e2a4a4fd89626bd710bbc5aaa"
AUDITOR_PATH = "scripts/audit_recovery_controller_study.py"
AUDITOR_SHA = "6a5a02d654a9d56d50ac10920b47b5543addb116eae123d119c8bcaf70ecaf91"
METHODS = ("response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll")
DOMAINS = ("inventory_reservation", "support_transition", "delivery_registration")
FACTORS = {"lag_ms": [0, 40, 80, 95], "unavailable_until_ms": [0, 170, 210, 250],
           "incomplete_until_ms": [0, 170, 210, 250]}
PUBLIC_FIELDS = ("case_id", "family_id", "domain", "operation_id", "actor", "target",
                 "deadline_ms", "stability_ms", "initial_at_ms", "payload", "scope_fields",
                 "scope", "native_idempotency", "recovery_deadline_ms", "safety_horizon_ms")
PHYSICAL_METRICS = ("operational_safe_recovery", "original_completion", "recovery_completion",
                    "safe_recovery", "duplicate_event", "unwanted_event", "own_effect_count",
                    "duplicate_count", "unwanted_effect_count")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def decode(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "duplicate JSON key")
            value[key] = item
        return value

    def invalid(value):
        raise ValueError(f"nonfinite JSON token: {value}")

    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid)


def relative(name):
    require(isinstance(name, str) and "\\" not in name and ":" not in name, "unsafe relative path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.parts and all(p not in {".", ".."} for p in path.parts),
            "unsafe relative path")
    require(str(path) == name, "noncanonical relative path")
    return name


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def blob(root, commit, name):
    relative(name)
    require(isinstance(commit, str) and len(commit) == 40
            and all(c in "0123456789abcdef" for c in commit), "invalid Git commit identity")
    return git(root, "show", f"{commit}:{name}")


def bound_bytes(data, declaration, label):
    require(declaration == {"sha256": digest(data), "bytes": len(data)}, f"byte binding differs: {label}")


def semantic_auditor(git_root):
    data = blob(git_root, ENGINE_COMMIT, AUDITOR_PATH)
    require(digest(data) == AUDITOR_SHA, "original semantic auditor source hash differs")
    module = types.ModuleType("pinned_recovery_semantic_auditor")
    module.__file__ = f"{ENGINE_COMMIT}:{AUDITOR_PATH}"
    exec(compile(data, module.__file__, "exec"), module.__dict__)
    return module


def validate_plan(protocol):
    """Validate the full grid independently, without importing its generator."""
    require(protocol["schema"] == SCHEMA, "unexpected sweep schema")
    require(tuple(protocol["methods"]) == METHODS, "policy set/order differs")
    require((protocol["case_count"], protocol["profile_count"], protocol["domain_count"],
             protocol["seed_count"]) == (192, 64, 3, 1), "controlled dimensions differ")
    require(protocol["design"]["factors"] == FACTORS, "declared factor levels differ")
    fixed = {"deadline_ms": 100, "stability_ms": 50, "horizon_ms": 150,
             "recovery_deadline_ms": 250, "safety_horizon_ms": 330, "commit_at_ms": 10,
             "success_response_at_ms": 2, "native_idempotency": True, "dispatch_cap": 2,
             "read_opportunities_ms": [50, 150, 190, 230]}
    require(protocol["design"]["fixed"] == fixed, "declared fixed conditions differ")
    require(protocol["original_study_protocol_sha256"] == ORIGINAL_PROTOCOL,
            "original-study provenance differs")
    cases = protocol["cases"]
    require(len(cases) == 192, "case denominator differs")
    coverage, profiles, identifiers, operations = set(), {}, set(), set()
    expected_rows = []
    for index, case in enumerate(cases):
        p = case["_availability_profile"]
        require(set(p) == {"profile_id", *FACTORS}, "profile fields differ")
        values = tuple(p[key] for key in FACTORS)
        require(all(type(p[key]) is int and p[key] in levels for key, levels in FACTORS.items()),
                "undeclared factor level")
        require(case["domain"] in DOMAINS, "undeclared domain")
        identity = (case["domain"], *values)
        require(identity not in coverage, "duplicate controlled cell")
        coverage.add(identity)
        require(case["case_id"] not in identifiers and case["operation_id"] not in operations,
                "reused case/operation identity")
        identifiers.add(case["case_id"])
        operations.add(case["operation_id"])
        require(case["family_id"] == p["profile_id"], "family/profile mismatch")
        require(p["profile_id"] not in profiles or profiles[p["profile_id"]] == values,
                "profile identity aliases different conditions")
        profiles[p["profile_id"]] = values
        for key in ("deadline_ms", "stability_ms", "recovery_deadline_ms", "safety_horizon_ms"):
            require(type(case[key]) is int and case[key] == fixed[key], "case temporal target differs")
        require(case["initial_at_ms"] == 0 and case["native_idempotency"] is True,
                "case registration/provider capability differs")
        require(case["target"] == {"predicate": "record_present", "expected": case["payload"],
                                   "exact_count": 1}, "controlled target differs")
        fields = {"inventory_reservation": ["warehouse", "sku", "reservation_ref"],
                  "support_transition": ["ticket_id"],
                  "delivery_registration": ["artifact_id", "delivery_channel"]}[case["domain"]]
        require(case["scope_fields"] == fields
                and case["scope"] == {key: case["payload"][key] for key in fields},
                "controlled scope differs")
        world = case["_world"]
        require(set(world) == {"dispatch_plans", "readback"}
                and world["dispatch_plans"] == [{"status": "success", "response_delay_ms": 2,
                                                 "commit_delay_ms": 10}],
                "world has an undeclared physical intervention")
        view = world["readback"]
        require(set(view) == {"lag_ms", "windows"} and view["lag_ms"] == p["lag_ms"],
                "world lag/profile differs")
        windows = []
        for field, flag in (("unavailable_until_ms", "available"), ("incomplete_until_ms", "complete")):
            if p[field]:
                windows.append({"start_ms": 0, "until_ms": p[field], flag: False})
        require(view["windows"] == windows, "world windows/profile differ")
        offset = index % len(METHODS)
        for method in METHODS[offset:] + METHODS[:offset]:
            expected_rows.append({"trial_id": f"trial_{len(expected_rows):06d}",
                                  "case_id": case["case_id"], "family_id": case["family_id"],
                                  "domain": case["domain"], "seed": 0, "method": method, **p})
    required = set(itertools.product(DOMAINS, *FACTORS.values()))
    require(coverage == required and len(profiles) == 64, "factorial coverage is incomplete")
    require(protocol["schedule"] == expected_rows, "schedule/rotation/metadata differs")
    return {case["case_id"]: case for case in cases}


def recorded_path(root, *parts):
    """Preserve declared Windows paths when rechecking on another host."""
    cls = PureWindowsPath if PureWindowsPath(root).drive else PurePosixPath
    value = cls(root)
    require(value.is_absolute(), "recorded path is not absolute")
    return str(value.joinpath(*parts))


def verify_bindings(protocol, started, study, protocol_dir, git_root, verify_host=False):
    require(started["schema"] == SCHEMA and started["retry_allowed"] is False,
            "start schema/no-rerun declaration differs")
    source, engine, runtime = protocol["source"], protocol["engine"], protocol["runtime"]
    require(engine["commit"] == ENGINE_COMMIT, "original engine identity differs")
    needed_own = {"scripts/run_recovery_availability_sweep.py", "tests/test_recovery_availability_sweep.py",
                  "docs/recovery-availability-sweep.md", "scripts/audit_recovery_availability_sweep.py",
                  "tests/test_recovery_availability_audit.py"}
    require(needed_own <= set(source["files"]), "new source binding omits required code/tests/design")
    needed_engine = {"research/recovery_study/__init__.py", "research/recovery_study/world.py",
                     "research/recovery_study/controllers.py", "scripts/run_recovery_controller_study.py",
                     AUDITOR_PATH}
    require(needed_engine <= set(engine["files"]), "engine binding is incomplete")
    for declaration in (source, engine):
        for name, expected in declaration["files"].items():
            bound_bytes(blob(git_root, declaration["commit"], name), expected, name)
    require(engine["files"][AUDITOR_PATH]["sha256"] == AUDITOR_SHA, "semantic auditor pin differs")
    require(started["source_commit"] == source["commit"]
            and started["original_engine_commit"] == ENGINE_COMMIT, "start source identity differs")
    payload = (study / "protocol.json").read_bytes()
    protocol_sha = digest(payload)
    require(started["protocol_sha256"] == protocol_sha, "start/protocol digest differs")
    require((protocol_dir / "protocol.json").read_bytes() == payload, "mapped protocol copy differs")
    protocol_commit = started["protocol_commit"]
    require(blob(git_root, protocol_commit, protocol["protocol_git_path"]) == payload,
            "prospectively committed protocol differs")
    case_bytes = (study / "cases.json").read_bytes()
    case_binding = {key: protocol["cases_json"][key] for key in ("sha256", "bytes")}
    bound_bytes(case_bytes, case_binding, "cases.json")
    require(decode(case_bytes) == {"schema": SCHEMA, "cases": protocol["cases"]},
            "case artifact differs from protocol")
    require((protocol_dir / "cases.json").read_bytes() == case_bytes
            and blob(git_root, protocol_commit, protocol["cases_json"]["git_path"]) == case_bytes,
            "mapped/committed case bytes differ")
    subprocess.run(["git", "-C", str(git_root), "merge-base", "--is-ancestor",
                    source["commit"], protocol_commit], check=True, capture_output=True)
    start = datetime.fromisoformat(started["started_utc"].replace("Z", "+00:00"))
    require(start.utcoffset() is not None, "start timestamp has no timezone")
    committed = int(git(git_root, "show", "-s", "--format=%ct", protocol_commit))
    require(0 <= committed <= start.timestamp(), "protocol commit postdates collection")
    canonical = recorded_path(source["root"], "output", ".availability-sweep-run-claims", f"{protocol_sha}.json")
    require(started["canonical_claim_path"] == canonical, "canonical claim declaration differs")
    require(recorded_path(started["protocol_path"]) == started["protocol_path"],
            "original protocol path is not absolute/canonical")
    require(started["protocol_git_path"] == protocol["protocol_git_path"]
            and started["cases_git_path"] == protocol["cases_json"]["git_path"],
            "claim protocol/case Git paths differ")
    started_bytes = (study / "started.json").read_bytes()
    require((protocol_dir / "run-claim.json").read_bytes() == started_bytes, "mapped run claim differs")
    declared_output = recorded_path(started["output"])
    declared_database = recorded_path(started["database_root"])
    path_class = PureWindowsPath if PureWindowsPath(declared_output).drive else PurePosixPath
    a, b = path_class(declared_output), path_class(declared_database)
    require(a != b and a not in b.parents and b not in a.parents,
            "recorded output/database roots coincide or nest")
    require(runtime["framework_version"] == runtime["distribution_version"] == "2.1.1",
            "recorded installed framework version differs")
    names = git(git_root, "ls-tree", "-r", "--name-only", ENGINE_COMMIT,
                "src/consequa_x").decode().splitlines()
    expected_runtime = {name.removeprefix("src/consequa_x/"): digest(blob(git_root, ENGINE_COMMIT, name))
                        for name in names if PurePosixPath(name).suffix in {".py", ".json"}}
    require(runtime["runtime_file_sha256"] == expected_runtime, "recorded runtime/Git payload differs")
    require(isinstance(runtime["python_sha256"], str) and len(runtime["python_sha256"]) == 64
            and all(c in "0123456789abcdef" for c in runtime["python_sha256"]),
            "recorded interpreter hash is malformed")
    recorded_path(runtime["python_executable"])
    recorded_path(runtime["framework_path"])
    host_checks = False
    if verify_host:
        require(Path(canonical).read_bytes() == started_bytes, "original host canonical claim differs")
        require(Path(started["protocol_path"]).read_bytes() == payload, "original host protocol differs")
        require(str(study.resolve()) == started["output"], "original host output identity differs")
        for name, expected in source["files"].items():
            bound_bytes((Path(source["root"]) / name).read_bytes(), expected, f"host:{name}")
        require(digest(Path(runtime["python_executable"]).read_bytes()) == runtime["python_sha256"],
                "recorded host interpreter bytes differ")
        package = Path(runtime["framework_path"])
        actual = {p.relative_to(package).as_posix(): digest(p.read_bytes()) for p in package.rglob("*")
                  if p.is_file() and p.suffix in {".py", ".json"}}
        require(actual == expected_runtime, "recorded host installed bytes differ")
        host_checks = True
    return {"source_commit": source["commit"], "engine_commit": ENGINE_COMMIT,
            "protocol_commit": protocol_commit, "protocol_sha256": protocol_sha,
            "protocol_committed_at_unix": committed, "runtime_files_bound_to_git": len(expected_runtime),
            "verification_scope": "retained artifacts plus immutable Git blobs; original host declarations are not attested",
            "recorded_host_byte_checks_performed": host_checks,
            "canonical_claim_scope": "mapped protocol-local byte copy plus declared original path; original file checked only in host mode"}


def check_public_profile(trial, case):
    expected = {key: case[key] for key in PUBLIC_FIELDS}
    expected["registered_at_ms"] = 0
    require(trial.get("public_case") == expected, "public case differs from bound controlled case")
    inputs = {"action_id": case["operation_id"], "actor": case["actor"],
              "expected": case["target"]["expected"], "scope": case["scope"], "deadline_ms": 100,
              "stability_ms": 50, "source": trial["source_receipt"]["source"],
              "read_times": [50, 150, 190, 230], "max_dispatches": 2, "exact_count": 1,
              "scope_fields": case["scope_fields"], "native_idempotency": True}
    require(trial.get("controller_inputs") == inputs, "controller inputs differ from public allowlist")
    profile = case["_availability_profile"]
    ready = False
    for event in trial["trajectory"]:
        if event["kind"] != "readback":
            continue
        at, observation = event["at_ms"], event["observation"]
        require(at in [50, 150, 190, 230], "read outside declared opportunities")
        require(observation["as_of_ms"] == max(0, at - profile["lag_ms"])
                and observation["available"] is (at >= profile["unavailable_until_ms"])
                and observation["complete"] is (at >= profile["incomplete_until_ms"]
                                                 and at >= profile["unavailable_until_ms"]),
                "admitted read does not implement frozen availability profile")
        ready |= observation["available"] and observation["complete"] and observation["as_of_ms"] >= 150
    return bool(ready)


def observed_analysis(trials, protocol):
    """Report observed comparisons, retaining discrepancies rather than enforcing hypotheses."""
    methods = {method: Counter(planned=192) for method in METHODS}
    by_case = defaultdict(dict)
    rows = []
    for trial in trials:
        method, case = trial["method"], trial["case_id"]
        counts = methods[method]
        by_case[case][method] = trial
        if trial["status"] != "completed":
            counts["failed"] += 1
            rows.append({"trial_id": trial["trial_id"], "case_id": case, "method": method, "completed": False})
            continue
        counts["completed"] += 1
        ready = trial["_audit_evidence_ready"]
        report = trial["report"]
        state, linked = report["reported_state"], report["reported_action_linked"]
        counts["horizon_evidence_ready"] += int(ready)
        for target, claim in (("state", state), ("action_linked", linked)):
            counts[f"{target}_true"] += int(claim is True)
            counts[f"{target}_false"] += int(claim is False)
            counts[f"{target}_unknown"] += int(claim is None)
        counts["true_state_without_horizon_evidence"] += int(state is True and not ready)
        counts["ready_but_no_true_state"] += int(ready and state is not True)
        for key in ("reads", "dispatches", "decision_time_ms", *PHYSICAL_METRICS):
            counts[key] += trial["metrics"][key]
        rows.append({"trial_id": trial["trial_id"], "case_id": case, "method": method,
                     **{key: trial[key] for key in ("profile_id", *FACTORS)}, "completed": True,
                     "evidence_ready": ready, "reported_state": state, "reported_action_linked": linked,
                     "reads": report["reads"], "dispatches": report["dispatches"]})
    comparisons = []
    for left, right in (("reference", "consequax_poll"), ("readback_state", "consequax_poll"),
                        ("consequax_one_read", "consequax_poll")):
        mismatches = Counter()
        comparable = 0
        for arms in by_case.values():
            a, b = arms[left], arms[right]
            if a["status"] != "completed" or b["status"] != "completed":
                continue
            comparable += 1
            for key in ("reported_state", "reported_action_linked"):
                mismatches[key] += int(a["report"][key] != b["report"][key])
            for label, getter in (("endpoint_vector", lambda r: r["metrics"]),
                                  ("dispatch_decisions", lambda r: [x for x in r["trajectory"] if x["kind"] == "dispatch"]),
                                  ("physical_records", lambda r: r["truth"]["records"]),
                                  ("physical_metrics", lambda r: {k: r["metrics"][k] for k in PHYSICAL_METRICS})):
                mismatches[label] += int(getter(a) != getter(b))
        comparisons.append({"left": left, "right": right, "planned_pairs": 192,
                            "comparable_pairs": comparable, "mismatch_counts": dict(mismatches)})
    invariant, complete = 0, 0
    for arms in by_case.values():
        if all(row["status"] == "completed" for row in arms.values()):
            complete += 1
            values = [row["truth"]["records"] for row in arms.values()]
            invariant += int(all(value == values[0] for value in values))
    expected_known = {method: 0 for method in METHODS}
    for case in protocol["cases"]:
        profile = case["_availability_profile"]
        for method in METHODS:
            times = [150] if method == "consequax_one_read" else [150, 190, 230]
            available = any(at - profile["lag_ms"] >= 150
                            and at >= profile["unavailable_until_ms"]
                            and at >= profile["incomplete_until_ms"] for at in times)
            expected_known[method] += int(method == "response_retry" or available)
    return {"methods": {method: dict(counts) for method, counts in methods.items()},
            "coverage_rows": rows, "paired_comparisons": comparisons,
            "complete_five_arm_cells": complete, "physical_record_invariant_cells": invariant,
            "analytical_expected_true_state_counts": expected_known,
            "hypothesis_scope": "Analytical counts are diagnostics, not an audit pass condition. Observed disagreements remain results."}


def audit_study(study_dir, output_dir, git_root, protocol_dir, verify_host=False):
    root, output, git_root, protocol_dir = (Path(p).resolve() for p in
                                           (study_dir, output_dir, git_root, protocol_dir))
    require(not output.exists() and not output.is_relative_to(root), "audit output must be fresh and separate")
    audit = semantic_auditor(git_root)
    for name in ("manifest.json", "completion-receipt.json", "protocol.json", "started.json", "summary.json", "cases.json"):
        decode((root / name).read_bytes())
    receipt, manifest = audit.audit_artifact_manifest(root)
    require(receipt["schema"] == manifest["schema"] == SCHEMA, "terminal schema differs")
    for key in ("no_retries_or_replacements", "source_and_runtime_final_recheck"):
        require(receipt.get(key) is True, "missing collection invariant")
    require(receipt["new_model_calls"] == receipt["external_application_calls"] == 0, "prohibited calls declared")
    protocol, started = decode((root / "protocol.json").read_bytes()), decode((root / "started.json").read_bytes())
    cases = validate_plan(protocol)
    bindings = verify_bindings(protocol, started, root, protocol_dir, git_root, verify_host)
    require(receipt["protocol_sha256"] == bindings["protocol_sha256"], "terminal protocol digest differs")
    planned_trials = {f"trials/{slot['trial_id']}.json.gz" for slot in protocol["schedule"]}
    base = {"started.json", "protocol.json", "cases.json", "summary.json", "analysis-rows.jsonl"}
    require({p for p in manifest["files"] if p.startswith("trials/")} == planned_trials,
            "raw trial denominator differs")
    journal = [decode(line) for line in (root / "analysis-rows.jsonl").read_bytes().splitlines()]
    require(len(journal) == 960, "journal denominator differs")
    compact, trials, databases = [], [], set()
    with tempfile.TemporaryDirectory(prefix="availability-audit-") as temp:
        db = Path(temp) / "snapshot.sqlite"
        for index, slot in enumerate(protocol["schedule"]):
            trial = decode(gzip.decompress((root / f"trials/{slot['trial_id']}.json.gz").read_bytes()))
            require(trial["schema"] == SCHEMA and all(trial.get(k) == v for k, v in slot.items()),
                    "raw trial identity differs")
            require(trial["status"] in {"completed", "failed"}, "invalid retained disposition")
            if "database" in trial:
                packed = f"databases/{slot['trial_id']}.sqlite.gz"
                require(trial["database"]["path"] == packed and packed in manifest["files"],
                        "database path differs")
                raw = gzip.decompress((root / packed).read_bytes())
                require(digest(raw) == trial["database"]["sha256_uncompressed"], "uncompressed DB hash differs")
                databases.add(packed)
                db.write_bytes(raw)
                metrics = audit.audit_trial(trial, db)
                ready = check_public_profile(trial, cases[slot["case_id"]])
            else:
                require(trial["status"] == "failed", "completed slot has no snapshot")
                metrics, ready = audit._failed_metrics(trial), False
            row = {**slot, "status": trial["status"], "metrics": metrics}
            require(row == journal[index], "independently audited journal differs")
            compact.append(row)
            trial["_audit_evidence_ready"] = ready
            trials.append(trial)
            if (index + 1) % 100 == 0:
                print(json.dumps({"audited_slots": index + 1, "planned": 960}), flush=True)
    require(set(manifest["files"]) == base | planned_trials | databases, "unexpected retained inventory")
    computed = audit.recompute_summary(compact, protocol)
    summary = decode((root / "summary.json").read_bytes())
    require(summary["protocol_sha256"] == bindings["protocol_sha256"]
            and summary["controlled_profile_count"] == 64 and summary["domain_count"] == 3,
            "summary source/dimension metadata differs")
    require(type(summary["collection_seconds"]) in {int, float}
            and math.isfinite(summary["collection_seconds"]) and summary["collection_seconds"] >= 0,
            "invalid collection duration")
    audit._same(computed, {key: value for key, value in summary.items()
                          if key not in {"protocol_sha256", "collection_seconds", "controlled_profile_count", "domain_count"}})
    for key in ("planned_trials", "completed_trials", "failed_trials"):
        require(receipt[key] == computed[key], "terminal denominator differs")
    analysis = observed_analysis(trials, protocol)
    result = {"schema": "conseqa-availability-postcollection-audit-v1", "passed": True,
              **bindings, "manifest_sha256": receipt["manifest_sha256"], "artifacts_hashed": len(manifest["files"]),
              "sqlite_snapshots_queried": len(databases), "planned_trials": 960,
              "completed_trials": computed["completed_trials"], "failed_trials": computed["failed_trials"],
              "audit_script_sha256": digest(Path(__file__).read_bytes()), "semantic_auditor_sha256": AUDITOR_SHA,
              "audit_python_executable": str(Path(sys.executable).resolve()), "audit_python_version": sys.version,
              "limitations": ["Same project AI-assisted authors; no independent human or external replication.",
                              "Portable checks verify retained bytes and Git content, not actual original runtime execution or canonical-claim exclusivity.",
                              "Source admission/provider laws and uniform-safe scenario design remain assumptions.",
                              "Coverage discrepancies are retained diagnostics, not reasons to exclude worlds or force hypotheses.",
                              "Complete controlled finite grid; no bootstrap, population confidence interval, p-value, or autonomous-agent generalization."]}
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("audit-receipt.json", result), ("recomputed-summary.json", computed),
                        ("coverage-analysis.json", analysis)):
        (output / name).write_bytes(encoded(value))
    for source_name, target in (("protocol.json", "protocol.source.json"), ("manifest.json", "study-manifest.source.json"),
                                ("completion-receipt.json", "completion-receipt.source.json"),
                                ("cases.json", "cases.source.json"), ("started.json", "started.source.json")):
        (output / target).write_bytes((root / source_name).read_bytes())
    (output / "audit-code.source.py").write_bytes(Path(__file__).read_bytes())
    files = {path.name: digest(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()}
    (output / "manifest.json").write_bytes(encoded({"schema": result["schema"], "complete": True, "files": files}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--git-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--protocol-dir", type=Path, required=True)
    parser.add_argument("--verify-recorded-host", action="store_true")
    args = parser.parse_args()
    print(json.dumps(audit_study(args.study_dir, args.output, args.git_root, args.protocol_dir,
                                 args.verify_recorded_host), sort_keys=True))


if __name__ == "__main__":
    main()
