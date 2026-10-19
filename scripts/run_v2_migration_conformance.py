"""Freeze, then execute a strictly offline, post-hoc 1.1-to-2.0 conformance study.

No model, collector, service, replay, simulator, or evaluator truth is executed.
The ``freeze`` command only inventories inputs; ``run`` consumes that inventory
once. See docs/v2-migration-conformance.md for the bounded interpretation.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "consequa-v2-migration-conformance-v1"
OLD_REVISION = "940ebfcc0059c992977dd8e9f112361ff5b31edd"
RESEARCH_FILES = (
    "scripts/run_v2_migration_conformance.py",
    "tests/test_v2_migration_conformance.py",
    "docs/v2-migration-conformance.md",
)
CORE = ("status", "origin", "effect_ids", "attributable_effect_ids")
LEGACY_RECEIPT = (
    "contract_id", "status", "observed_at_ms", "evidence", "origin", "effect_ids",
    "attributable_effect_ids", "reason",
)
PLAN = {
    "design": "post-hoc offline migration conformance; retained factual single-action traces",
    "planned_slots": 504,
    "retained_traces": 503,
    "historical_failed_slots": 1,
    "historical_model_calls": 896,
    "new_model_calls": 0,
    "new_action_executions": 0,
    "verifiers": {"refund_processed": "public built-in RefundVerifier, via verify"},
    "receipt_observation_binding": "exactly one evidence item; join by observation_id; no fallback",
    "latest_rule": "last recorded receipt/assessment for the action, preserving recorded order",
    "state_mapping": {"satisfied": True, "violated": False, "unknown": None},
    "origin_mapping": {"confirmed": "confirmed", "other_actor": "other_actor", "unknown": "unknown"},
    "assessment_mapping": {
        "success": "success", "failure": "failure", "partial": "partial", "unknown": "unknown",
    },
    "alignment_mapping": {
        "consistent": "consistent", "contradicted": "contradicted", "unassessable": "unassessable",
    },
    "action_linked_mapping": "each pinned version's benchmark.targets.action_linked_consequence",
    "migration_reproduction_rule": list(CORE),
    "receipt_identity_fields": [
        "contract_id", "observed_at_ms", "effect_ids", "attributable_effect_ids",
        "evidence[*].observation_id", "evidence[*].source", "evidence[*].as_of_ms",
    ],
    "primary_metrics": [
        "migration_success", "structural_legacy_projection_equal", "schema_roundtrip_equal",
        "migration_receipts_preserved", "old_reverify_core_equal", "fresh_core_equal",
        "fresh_state_equal", "fresh_origin_equal", "fresh_action_linked_equal",
        "fresh_receipt_identity_equal", "assessment_status_preserved",
        "migration_alignment_equal", "fresh_alignment_equal",
        "old_recorded_explanation_alignment_equal", "old_analysis_prediction_equal",
    ],
    "secondary_metrics": [
        "fresh_full_legacy_receipts_equal", "old_reverify_full_receipts_equal",
        "migration_codes_equal", "fresh_codes_equal", "migration_reproduced_receipt_count",
        "migration_not_reproduced_receipt_count", "target_matching_unavailable",
        "target_matching_empty", "target_matching_nonempty", "alignment_became_unassessable",
    ],
    "denominators": (
        "Every trace-level metric reports true/false/unavailable among all 503 retained traces; "
        "also show success/504 planned slots without scoring the failed slot as disagreement. "
        "Receipt-level counts report their own observed receipt denominator. Equal null states "
        "or unassessable alignments are agreement only, not known-state coverage."
    ),
    "diagnosis_policy": (
        "Compare exact ordered codes secondarily, retain all additions/removals; no normalization. "
        "2.0 may add UNASSESSABLE_ASSESSMENT for known refund outcomes with unknown/partial "
        "reports or unsupported target linkage. Display labels/messages/graphs are not invariants."
    ),
    "failures": "retain every failure/unavailable value; no retries, replacements, or exclusions",
    "inference": "descriptive paired conformance counts only; no p-values or population generalization",
    "limitations": [
        "0.1 never recorded its clock origin: migrate to relative_ms, not an inferred epoch",
        "one recorded action becomes a one-item list; no general multi-action validation",
        "migration preserves recorded conclusions by construction; fresh verification is separate",
        "target matches/findings are rederived metadata, absent from the legacy receipt",
        "only the retained refund predicate is measured; custom verifier fixtures are development only",
        "historical policies, labels, gold, analysis, and collection provenance remain unchanged",
    ],
    "development_disclosure": (
        "Runner development may use four existing tests/fixtures/v0.1 migration examples and "
        "synthetic mutation/error fixtures, including an isolated frozen-1.1 integration check. "
        "These are development checks, excluded from the 503-trace measured corpus."
    ),
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    # Exclusive creation is deliberate: even incomplete runs remain reviewable.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8",
    ).strip()


def inventory(root: Path, paths: list[Path] | None = None) -> dict:
    chosen = paths if paths is not None else [p for p in root.rglob("*") if p.is_file()]
    return {p.relative_to(root).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size}
            for p in sorted(chosen) if "__pycache__" not in p.parts and p.suffix != ".pyc"}


def source_pin(root: Path, revision: str, *, research: bool) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("An explicit full 40-character source commit is required")
    if git(root, "rev-parse", "HEAD") != revision:
        raise ValueError(f"Source HEAD differs from expected commit: {root}")
    paths = [p for p in (root / "src" / "consequa_x").rglob("*") if p.is_file()
             and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    paths.append(root / "pyproject.toml")
    if research:
        paths.extend(root / p for p in (*RESEARCH_FILES, "docs/migrating-to-2.0.md",
                                      "tests/test_migrate.py"))
        paths.extend(p for p in (root / "tests/fixtures/v0.1").rglob("*") if p.is_file())
    relative = [p.relative_to(root).as_posix() for p in paths]
    # Use directory pathspecs as well as existing files: a deleted tracked
    # runtime/fixture must not disappear from the advertised source inventory.
    checked = ["src/consequa_x", "pyproject.toml"]
    if research:
        checked.extend((*RESEARCH_FILES, "docs/migrating-to-2.0.md", "tests/test_migrate.py",
                        "tests/fixtures/v0.1"))
    dirty = git(root, "status", "--porcelain", "--", *checked)
    if dirty:
        raise ValueError("Commit all pinned runtime/runner/tests/docs before freezing: " + dirty)
    # A tracked clean source at this exact commit is required, while unrelated
    # paper/research changes in the worktree are explicitly permitted.
    git(root, "ls-files", "--error-unmatch", "--", *relative)
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if version != ("2.0.0" if research else "1.1.0"):
        raise ValueError(f"Unexpected source package version: {version}")
    return {"root": str(root), "commit": revision, "source_package_version": version,
            "files": inventory(root, paths)}


def check_inventory(root: Path, expected: dict, *, exact: bool = True) -> None:
    actual = inventory(root) if exact else inventory(root, [root / name for name in expected])
    if actual != expected:
        changed = sorted(name for name in set(actual) | set(expected)
                         if actual.get(name) != expected.get(name))
        raise ValueError(f"Frozen input/source inventory changed at {root}: {changed[:12]}")


def check_source(pin: dict, *, research: bool) -> None:
    actual = source_pin(Path(pin["root"]), pin["commit"], research=research)
    if actual != pin:
        raise ValueError(f"Frozen source changed: {pin['root']}")


def slot_indices(schedule: list[dict], episodes: list[dict], method_rows: list[dict]) -> tuple[dict, dict]:
    """Refuse duplicate/missing slots before any dictionary could hide them."""
    scheduled_ids = [item["slot_id"] for item in schedule]
    episode_ids = [item["slot"]["slot_id"] for item in episodes]
    prediction_ids = [item["slot"]["slot_id"] for item in method_rows]
    if (len(scheduled_ids) != 504 or len(set(scheduled_ids)) != 504
            or len(episode_ids) != 504 or len(set(episode_ids)) != 504
            or set(scheduled_ids) != set(episode_ids)):
        raise ValueError("Schedule and analysis episodes require the same 504 unique slot IDs")
    completed = {item["slot"]["slot_id"] for item in episodes if item["status"] == "completed"}
    if (len(completed) != 503 or len(prediction_ids) != 503
            or len(set(prediction_ids)) != 503 or set(prediction_ids) != completed):
        raise ValueError("Baseline rows require exactly the 503 unique completed slot IDs")
    return ({item["slot"]["slot_id"]: item for item in episodes},
            {item["slot"]["slot_id"]: item["prediction"] for item in method_rows})


def historical_inputs(study: Path, analysis_dir: Path) -> tuple[list[dict], list[dict], dict]:
    """Inventory/identity checks only; no trace interpretation or verifier call."""
    analysis = read_json(analysis_dir / "analysis.json")
    disposition = read_json(analysis_dir / "final-disposition.json")
    finalization = read_json(analysis_dir / "finalization-receipt.json")
    historical_protocol = read_json(study / "protocol.json")
    if (analysis["planned_episodes"] != 504 or analysis["attempted_chat_calls"] != 896
            or analysis["episode_status"] != {"completed": 503, "failed": 1,
                                               "interrupted_partial": 0, "unstarted": 0}
            or not disposition["final"] or not finalization["final"]
            or historical_protocol["package_version"] != "1.1.0"):
        raise ValueError("The closed 504-slot/503-retained/896-call 1.1.0 study is required")
    if digest(analysis_dir / "analysis.json") != finalization["analysis_sha256"]:
        raise ValueError("Historical analysis differs from its finalization receipt")
    if digest(study / "protocol.json") != finalization["protocol_sha256"]:
        raise ValueError("Historical protocol differs from its finalization receipt")
    if digest(study / "request-journal.jsonl") != finalization["journal_sha256"]:
        raise ValueError("Historical request journal differs from its finalization receipt")
    closed = read_json(analysis_dir / "closed-study-inventory.json")
    if digest(analysis_dir / "closed-study-inventory.json") != finalization[
            "closed_study_inventory_sha256"]:
        raise ValueError("Historical closed-study inventory differs from finalization receipt")
    check_inventory(study, closed["files"])
    schedule = historical_protocol["schedule"]
    method_rows = [item for item in analysis["rows"] if item["method"] == "consequa_state_origin"]
    episodes, predictions = slot_indices(schedule, analysis["episodes"], method_rows)
    retained, failed = [], []
    for slot in schedule:
        slot_id = slot["slot_id"]
        if not re.fullmatch(r"episode_\d{5}", slot_id):
            raise ValueError("Invalid historical slot ID")
        episode = episodes[slot_id]
        receipt_path = study / "episodes" / slot_id / "receipt.json"
        receipt = read_json(receipt_path)
        if receipt != episode or receipt["slot"] != slot:
            raise ValueError(f"Analysis/receipt/schedule mismatch: {slot_id}")
        common = {"slot": slot, "status": receipt["status"],
                  "receipt": receipt_path.relative_to(study).as_posix(),
                  "receipt_sha256": digest(receipt_path)}
        if receipt["status"] != "completed":
            if receipt["status"] != "failed" or (receipt_path.parent / "trace.json").exists():
                raise ValueError("The failed slot must remain failed without a substituted trace")
            failed.append({**common, "error_type": receipt["error_type"], "error": receipt["error"]})
            continue
        for filename, sha in receipt["artifact_sha256"].items():
            if digest(receipt_path.parent / filename) != sha:
                raise ValueError(f"Historical artifact receipt mismatch: {slot_id}/{filename}")
        trace_path = receipt_path.parent / "trace.json"
        explanation_path = receipt_path.parent / "explanation.json"
        retained.append({**common, "trace": trace_path.relative_to(study).as_posix(),
                         "trace_sha256": digest(trace_path),
                         "explanation": explanation_path.relative_to(study).as_posix(),
                         "explanation_sha256": digest(explanation_path),
                         "old_analysis_prediction": predictions[slot_id]})
    if len(retained) != 503 or len(failed) != 1 or len(predictions) != 503:
        raise ValueError("Expected 503 retained traces, 503 baseline rows, and one failed slot")
    return retained, failed, historical_protocol


def freeze(args: argparse.Namespace) -> dict:
    study, analysis_dir = args.study_dir.resolve(), args.analysis_dir.resolve()
    current = source_pin(ROOT, args.expected_current_commit, research=True)
    legacy = source_pin(args.legacy_root.resolve(), args.expected_legacy_commit, research=False)
    retained, failed, old_protocol = historical_inputs(study, analysis_dir)
    # The frozen 1.1 source is checked against the collector's recorded runtime
    # inventory, not merely its version string or a similarly named checkout.
    for name, sha in old_protocol["code_sha256"].items():
        if name.startswith("runtime/"):
            relative = "src/consequa_x/" + name.removeprefix("runtime/")
            if legacy["files"][relative]["sha256"] != sha:
                raise ValueError(f"Frozen 1.1 source differs from historical runtime: {relative}")
    protocol = {
        "schema_version": SCHEMA, "frozen_utc": utc(), "plan": PLAN,
        "current": current, "legacy": legacy,
        "study_root": str(study), "analysis_root": str(analysis_dir),
        "study_inventory": inventory(study), "analysis_inventory": inventory(analysis_dir),
        "inputs": retained, "failed_slots": failed,
        "python": {"executable": str(Path(sys.executable).resolve()), "version": sys.version,
                   "sha256": digest(Path(sys.executable))},
        "legacy_python": python_pin(args.legacy_python.resolve()),
        "runtime_metadata": {
            "current": source_runtime_pin(Path(sys.executable), ROOT),
            "legacy": source_runtime_pin(args.legacy_python.resolve(), args.legacy_root.resolve()),
        },
        "execution_policy": "One exclusive run-claim.json next to protocol; no resume or retry",
    }
    out = args.output_dir.resolve()
    if out == study or out == analysis_dir or study in out.parents or analysis_dir in out.parents:
        raise ValueError("Protocol output must be outside the historical input directories")
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "protocol.json", protocol)
    write_json(out / "protocol.sha256.json", {"sha256": digest(out / "protocol.json")})
    return {"protocol": str(out / "protocol.json"), "sha256": digest(out / "protocol.json"),
            "retained": len(retained), "failed": len(failed), "measured_run_executed": False}


def legacy_projection(receipt: dict) -> dict:
    return {name: receipt[name] for name in LEGACY_RECEIPT}


def core(receipt: dict) -> dict:
    return {name: receipt[name] for name in CORE}


def receipt_identity(receipt: dict) -> dict:
    return {"contract_id": receipt["contract_id"], "observed_at_ms": receipt["observed_at_ms"],
            "effect_ids": receipt["effect_ids"],
            "attributable_effect_ids": receipt["attributable_effect_ids"],
            "evidence": [{key: item[key] for key in ("observation_id", "source", "as_of_ms")}
                         for item in receipt["evidence"]]}


def canonical(action: Any, receipt: Any, linked: Any) -> dict:
    return {"state": PLAN["state_mapping"][receipt.status.value],
            "origin": receipt.origin.value, "action_linked": linked(action, receipt)}


def binding(trace: Any, receipt: Any) -> Any:
    if len(receipt.evidence) != 1:
        raise ValueError("Receipt does not bind exactly one recorded observation")
    matches = [item for item in trace.observations
               if item.observation_id == receipt.evidence[0].observation_id]
    if len(matches) != 1:
        raise ValueError("Receipt observation_id does not identify one recorded observation")
    return matches[0]


def error_record(error: Exception) -> dict:
    return {"type": type(error).__name__, "message": str(error)}


def python_pin(executable: Path) -> dict:
    data = subprocess.check_output(
        [str(executable), "-I", "-B", "-c",
         "import json,sys; print(json.dumps({'executable':sys.executable,'version':sys.version}))"],
        text=True, encoding="utf-8",
    )
    pin = json.loads(data)
    pin["executable"] = str(Path(pin["executable"]).resolve())
    pin["sha256"] = digest(executable)
    return pin


def source_runtime_pin(executable: Path, source: Path) -> dict:
    # Import/code metadata inspection only: no migrate, verify, explain, collector,
    # policy, or benchmark execution occurs while the protocol is being frozen.
    code = (
        "import importlib.util,json,sys; "
        f"spec=importlib.util.spec_from_file_location('conformance_metadata',{str(Path(__file__).resolve())!r}); "
        "runner=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner); "
        f"sys.path.insert(0,{str(source.resolve() / 'src')!r}); "
        "import consequa_x; print(json.dumps(runner.runtime_metadata(consequa_x)))"
    )
    metadata = json.loads(subprocess.check_output(
        [str(executable), "-I", "-B", "-c", code], text=True, encoding="utf-8"))
    if Path(metadata["imported_module"]).resolve().parent != source.resolve() / "src/consequa_x":
        raise ValueError("Source metadata inspection imported a different checkout")
    return metadata


def runtime_metadata(module: Any) -> dict:
    try:
        distribution = importlib.metadata.distribution("consequa-x")
        metadata = {"version": distribution.version, "path": str(distribution.locate_file(""))}
    except importlib.metadata.PackageNotFoundError:
        metadata = None
    return {"imported_source_version": module.__version__, "imported_module": str(module.__file__),
            "ambient_distribution_metadata": metadata,
            "metadata_policy": "Imported pinned source defines behavior; ambient metadata is disclosed"}


def old_semantics(trace: Any, explain_fn: Any, verify_fn: Any, linked: Any) -> dict:
    """Called only inside the separate process importing the pinned 1.1 source."""
    recorded = [item.to_dict() for item in trace.verifications]
    result = {"recorded_receipts": recorded, "assessment_status": trace.assessment.status.value}
    errors = []
    try:
        explanation = explain_fn(trace)
        result.update(recorded_prediction=canonical(trace.action, trace.verifications[-1], linked),
                      recorded_alignment=explanation.assessment_alignment,
                      recorded_codes=list(explanation.diagnoses))
    except Exception as error:
        errors.append({"stage": "legacy_recorded_explanation", **error_record(error)})
    try:
        fresh = [verify_fn(trace.action, binding(trace, receipt)) for receipt in trace.verifications]
        result.update(fresh_receipts=[item.to_dict() for item in fresh],
                      fresh_prediction=canonical(trace.action, fresh[-1], linked))
        refreshed = replace(trace, verifications=tuple(fresh))
        explanation = explain_fn(refreshed)
        result.update(fresh_alignment=explanation.assessment_alignment,
                      fresh_codes=list(explanation.diagnoses))
    except Exception as error:
        errors.append({"stage": "legacy_fresh_verification_or_explanation", **error_record(error)})
    if errors:
        result.update(error=errors[0], stage_errors=errors)
    return result


def legacy_worker(source: Path) -> None:
    # -I ignores PYTHONPATH/user site; only this explicit old checkout is added.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source.resolve() / "src"))
    import consequa_x
    from consequa_x import Trace, explain, verify
    from consequa_x.benchmark.targets import action_linked_consequence

    if (consequa_x.__version__ != "1.1.0"
            or Path(consequa_x.__file__).resolve().parent != source.resolve() / "src/consequa_x"):
        raise ValueError("Legacy worker did not import exactly the pinned 1.1.0 source")
    results = {}
    for item in json.load(sys.stdin):
        try:
            trace = Trace.from_json(Path(item["path"]).read_text(encoding="utf-8"))
            results[item["slot_id"]] = old_semantics(trace, explain, verify, action_linked_consequence)
        except Exception as error:
            results[item["slot_id"]] = {"error": error_record(error), "error_stage": "legacy_parse"}
    json.dump({"runtime": runtime_metadata(consequa_x), "results": results}, sys.stdout,
              sort_keys=True, allow_nan=False)


def get_legacy(source: Path, items: list[dict], *, python: Path | None = None) -> dict:
    completed = subprocess.run(
        [str(python or sys.executable), "-I", "-B", str(Path(__file__).resolve()),
         "--legacy-worker", str(source)],
        input=json.dumps(items), capture_output=True, text=True, encoding="utf-8", check=False,
        cwd=str(source),
    )
    if completed.returncode:
        raise RuntimeError("Isolated 1.1 worker failed: " + completed.stderr[-4000:])
    return json.loads(completed.stdout)


def structural_projection(trace: dict) -> dict:
    """Undo only the declared 0.1-to-1.0 structural/new-field additions."""
    action = {**trace["actions"][0], "trace_id": trace["trace_id"]}
    assessment = {k: v for k, v in trace["assessments"][0].items()
                  if k not in {"assessment_id", "action_id"}}
    return {"schema_version": "0.1", "trace_id": trace["trace_id"], "action": action,
            "events": [{**event, "trace_id": trace["trace_id"]} for event in trace["events"]],
            "responses": [{k: v for k, v in response.items() if k != "action_id"}
                          for response in trace["responses"]],
            "assessment": assessment, "observations": trace["observations"],
            "verifications": [legacy_projection(item) for item in trace["verifications"]]}


def compare_trace(raw: dict, saved_explanation: dict, old: dict,
                  historical_prediction: dict) -> tuple[dict, dict | None]:
    """Measured logic; tests call this exclusively on disclosed development fixtures."""
    from consequa_x import MigrationReport, Trace, migrate_trace

    report = MigrationReport()
    try:
        trace = migrate_trace(raw, report=report)
    except Exception as error:
        return {"error": error_record(error), "error_stage": "migration",
                "metrics": {"migration_success": False}, "old": old}, None
    try:
        return compare_migrated(raw, saved_explanation, old, historical_prediction, trace, report)
    except Exception as error:
        migrated = trace.to_dict()
        return {
            "error": error_record(error), "error_stage": "verification_or_explanation",
            "migration_report": dict(report), "old": old,
            "target_matching": {
                "unavailable": sum(r["target_effect_ids"] is None for r in migrated["verifications"]),
                "empty": sum(r["target_effect_ids"] == [] for r in migrated["verifications"]),
                "nonempty": sum(bool(r["target_effect_ids"]) for r in migrated["verifications"]),
            },
            "clock_origin_unrecoverable": True, "time_base": trace.time_base.value,
            "metrics": {
                "migration_success": True,
                "structural_legacy_projection_equal": structural_projection(migrated) == raw,
                "schema_roundtrip_equal": Trace.from_json(trace.to_json()) == trace,
                "migration_receipts_preserved": [legacy_projection(r) for r in migrated["verifications"]]
                == [legacy_projection(r) for r in raw["verifications"]],
                "assessment_status_preserved": trace.assessments[0].status.value
                == raw["assessment"]["status"],
            },
        }, migrated


def compare_migrated(raw: dict, saved_explanation: dict, old: dict,
                     historical_prediction: dict, trace: Any, report: dict) -> tuple[dict, dict]:
    from consequa_x import Trace, explain, verify
    from consequa_x.benchmark.targets import action_linked_consequence

    if len(trace.actions) != 1 or len(trace.assessments) != 1:
        raise ValueError("Migration did not produce exactly one action and one assessment")
    action = trace.single_action
    if action.contract.predicate != "refund_processed":
        raise ValueError("Measured protocol supports only refund_processed")
    migrated = trace.to_dict()
    migrated_receipts = migrated["verifications"]
    measures: dict[str, bool | None] = {
        name: None for name in PLAN["primary_metrics"] + [
            "fresh_full_legacy_receipts_equal", "old_reverify_full_receipts_equal",
            "migration_codes_equal", "fresh_codes_equal",
        ]
    }
    measures.update(
        migration_success=True,
        structural_legacy_projection_equal=structural_projection(migrated) == raw,
        schema_roundtrip_equal=Trace.from_json(trace.to_json()) == trace,
        migration_receipts_preserved=[legacy_projection(r) for r in migrated_receipts]
        == [legacy_projection(r) for r in raw["verifications"]],
        assessment_status_preserved=trace.assessments[0].status.value == raw["assessment"]["status"],
    )
    detail = {
        "migration_report": dict(report), "old": old,
        "historical_analysis_prediction": historical_prediction,
        "target_matching": {
            "unavailable": sum(r["target_effect_ids"] is None for r in migrated_receipts),
            "empty": sum(r["target_effect_ids"] == [] for r in migrated_receipts),
            "nonempty": sum(bool(r["target_effect_ids"]) for r in migrated_receipts),
        },
        "clock_origin_unrecoverable": True, "time_base": trace.time_base.value,
    }
    errors = []
    try:
        new_explanation = explain(trace).for_action(action.action_id)
        detail.update(migration_alignment=new_explanation.assessment_alignment,
                      migration_codes=list(new_explanation.codes))
    except Exception as error:
        errors.append({"stage": "migration_explanation", **error_record(error)})
    try:
        fresh = [verify(action, binding(trace, receipt)) for receipt in trace.verifications]
        if not fresh:
            raise ValueError("No recorded receipt to reverify")
        fresh_dicts = [receipt.to_dict() for receipt in fresh]
        prediction = canonical(action, fresh[-1], action_linked_consequence)
        detail.update(fresh_receipts=fresh_dicts, fresh_prediction=prediction,
                      fresh_target_matching={
                          "unavailable": sum(r["target_effect_ids"] is None for r in fresh_dicts),
                          "empty": sum(r["target_effect_ids"] == [] for r in fresh_dicts),
                          "nonempty": sum(bool(r["target_effect_ids"]) for r in fresh_dicts),
                      })
    except Exception as error:
        errors.append({"stage": "fresh_verification", **error_record(error)})
    if "fresh_receipts" in detail:
        try:
            fresh_trace = replace(trace, verifications=tuple(fresh))
            fresh_explanation = explain(fresh_trace).for_action(action.action_id)
            detail.update(fresh_alignment=fresh_explanation.assessment_alignment,
                          fresh_codes=list(fresh_explanation.codes))
        except Exception as error:
            errors.append({"stage": "fresh_explanation", **error_record(error)})
    if "fresh_receipts" in old:
        old_receipts = old["fresh_receipts"]
        measures.update(
            old_reverify_core_equal=[core(r) for r in old_receipts]
            == [core(r) for r in old["recorded_receipts"]],
            old_reverify_full_receipts_equal=old_receipts == old["recorded_receipts"],
        )
        if "fresh_receipts" in detail:
            measures.update(
                fresh_core_equal=[core(r) for r in detail["fresh_receipts"]]
                == [core(r) for r in old_receipts],
                fresh_receipt_identity_equal=[receipt_identity(r) for r in detail["fresh_receipts"]]
                == [receipt_identity(r) for r in old_receipts],
                fresh_full_legacy_receipts_equal=[legacy_projection(r) for r in detail["fresh_receipts"]]
                == [legacy_projection(r) for r in old_receipts],
            )
    if "fresh_prediction" in old:
        measures["old_analysis_prediction_equal"] = old["fresh_prediction"] == historical_prediction
        if "fresh_prediction" in detail:
            for name in ("state", "origin", "action_linked"):
                measures[f"fresh_{name}_equal"] = (
                    detail["fresh_prediction"][name] == old["fresh_prediction"][name])
    if "recorded_alignment" in old:
        measures["old_recorded_explanation_alignment_equal"] = (
            old["recorded_alignment"] == saved_explanation["assessment_alignment"])
    if "recorded_alignment" in old and "migration_alignment" in detail:
        measures["migration_alignment_equal"] = detail["migration_alignment"] == old["recorded_alignment"]
        detail["alignment_became_unassessable"] = (
            old["recorded_alignment"] != "unassessable"
            and detail["migration_alignment"] == "unassessable")
    if "fresh_alignment" in old and "fresh_alignment" in detail:
        measures["fresh_alignment_equal"] = detail["fresh_alignment"] == old["fresh_alignment"]
    changes = {}
    for phase, old_name in (("migration", "recorded_codes"), ("fresh", "fresh_codes")):
        if old_name in old and f"{phase}_codes" in detail:
            codes = detail[f"{phase}_codes"]
            measures[f"{phase}_codes_equal"] = codes == old[old_name]
            changes[f"{phase}_added"] = sorted(set(codes) - set(old[old_name]))
            changes[f"{phase}_removed"] = sorted(set(old[old_name]) - set(codes))
    detail["code_changes"] = changes
    if errors:
        detail.update(error=errors[0], error_stage=errors[0]["stage"], stage_errors=errors)
    return {"metrics": measures, **detail}, migrated


def summarize(rows: list[dict], failed: list[dict]) -> dict:
    names = PLAN["primary_metrics"] + ["fresh_full_legacy_receipts_equal",
                                       "old_reverify_full_receipts_equal",
                                       "migration_codes_equal", "fresh_codes_equal"]
    metrics = {}
    for name in names:
        counts = Counter(str(row.get("metrics", {}).get(name)) for row in rows)
        metrics[name] = {"equal_or_success": counts["True"], "different_or_failed": counts["False"],
                         "unavailable": counts["None"], "retained_denominator": len(rows),
                         "success_over_504_planned": counts["True"] / 504}
    targets = {key: sum(row.get("target_matching", {}).get(key, 0) for row in rows)
               for key in ("unavailable", "empty", "nonempty")}
    fresh_targets = {key: sum(row.get("fresh_target_matching", {}).get(key, 0) for row in rows)
                     for key in ("unavailable", "empty", "nonempty")}
    return {
        "schema_version": SCHEMA, "completed_utc": utc(), "plan": PLAN,
        "retained_traces": len(rows), "planned_slots": 504, "historical_failed_slots": failed,
        "processing_errors": sum("error" in row or "error" in row.get("old", {})
                                 for row in rows), "metrics": metrics,
        "migration_receipts_reproduced": sum(row.get("migration_report", {}).get("reproduced", 0)
                                             for row in rows),
        "migration_receipts_not_reproduced": sum(
            row.get("migration_report", {}).get("not_reproduced", 0) for row in rows),
        "migrated_target_matching_receipts": targets,
        "migrated_target_matching_receipt_denominator": sum(targets.values()),
        "fresh_target_matching_receipts": fresh_targets,
        "fresh_target_matching_receipt_denominator": sum(fresh_targets.values()),
        "alignment_became_unassessable": sum(row.get("alignment_became_unassessable", False)
                                             for row in rows),
        "fresh_state_counts": dict(Counter(str(row["fresh_prediction"]["state"])
                                            for row in rows if "fresh_prediction" in row)),
        "fresh_state_unavailable": sum("fresh_prediction" not in row for row in rows),
        "fresh_alignment_counts": dict(Counter(row.get("fresh_alignment", "processing_unavailable")
                                                for row in rows)),
        "interpretation": "Offline post-hoc conformance on retained single-action factual traces only",
    }


def run(args: argparse.Namespace) -> dict:
    protocol_path = args.protocol.resolve()
    if digest(protocol_path) != args.expected_protocol_sha256:
        raise ValueError("Protocol hash differs from the explicitly supplied frozen hash")
    protocol = read_json(protocol_path)
    if protocol["schema_version"] != SCHEMA or protocol["plan"] != PLAN:
        raise ValueError("Protocol schema/analysis plan differs from this pinned runner")
    check_source(protocol["current"], research=True)
    check_source(protocol["legacy"], research=False)
    study = Path(protocol["study_root"])
    check_inventory(study, protocol["study_inventory"])
    check_inventory(Path(protocol["analysis_root"]), protocol["analysis_inventory"])
    expected_python = protocol["python"]
    if (Path(sys.executable).resolve() != Path(expected_python["executable"])
            or digest(Path(sys.executable)) != expected_python["sha256"]
            or sys.version != expected_python["version"]):
        raise ValueError("Use the exact Python interpreter pinned at freeze time")
    if python_pin(Path(protocol["legacy_python"]["executable"])) != protocol["legacy_python"]:
        raise ValueError("The isolated legacy Python interpreter changed after freeze")
    if {
        "current": source_runtime_pin(Path(sys.executable), Path(protocol["current"]["root"])),
        "legacy": source_runtime_pin(Path(protocol["legacy_python"]["executable"]),
                                     Path(protocol["legacy"]["root"])),
    } != protocol["runtime_metadata"]:
        raise ValueError("Imported source or ambient distribution metadata changed after freeze")
    import consequa_x
    if (consequa_x.__version__ != "2.0.0"
            or Path(consequa_x.__file__).resolve().parent != Path(protocol["current"]["root"])
            / "src/consequa_x"):
        raise ValueError("Set PYTHONPATH to the pinned paper-writing/src 2.0 source")
    out = args.output_dir.resolve()
    forbidden = [study, Path(protocol["analysis_root"]), protocol_path.parent,
                 Path(protocol["legacy"]["root"]) / "src", ROOT / "src"]
    if any(out == path or path in out.parents for path in forbidden):
        raise ValueError("Run output must be a new directory outside inputs/protocol/runtime source")
    if out.exists():
        raise FileExistsError("Run output already exists; no overwrite/resume is supported")
    claim = {"started_utc": utc(), "protocol_sha256": args.expected_protocol_sha256,
             "output_dir": str(out), "pid": os.getpid(), "retry_allowed": False}
    write_json(protocol_path.parent / "run-claim.json", claim)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / "started.json", claim)
    write_json(out / "protocol.json", protocol)
    try:
        legacy_result = get_legacy(Path(protocol["legacy"]["root"]), [
            {"slot_id": item["slot"]["slot_id"], "path": str(study / item["trace"])}
            for item in protocol["inputs"]],
            python=Path(protocol["legacy_python"]["executable"]))
        old = legacy_result["results"]
        write_json(out / "runtime-metadata.json", {
            "current": runtime_metadata(consequa_x), "legacy": legacy_result["runtime"]})
        rows = []
        artifacts = out / "episodes"
        artifacts.mkdir()
        for item in protocol["inputs"]:
            slot_id = item["slot"]["slot_id"]
            try:
                row, migrated = compare_trace(read_json(study / item["trace"]),
                                              read_json(study / item["explanation"]), old[slot_id],
                                              item["old_analysis_prediction"])
                folder = artifacts / slot_id
                folder.mkdir()
                if migrated is not None:
                    write_json(folder / "migrated-trace.json", migrated)
            except Exception as error:
                row = {"error": error_record(error), "error_stage": "input_or_artifact_io", "metrics": {}}
            row.update(slot=item["slot"], trace_sha256=item["trace_sha256"])
            rows.append(row)
            write_json(artifacts / f"{slot_id}.json", row)
        # Recheck all source/input bytes after computation, before a final receipt.
        check_source(protocol["current"], research=True)
        check_source(protocol["legacy"], research=False)
        check_inventory(study, protocol["study_inventory"])
        check_inventory(Path(protocol["analysis_root"]), protocol["analysis_inventory"])
        summary = summarize(rows, protocol["failed_slots"])
        summary["protocol_sha256"] = args.expected_protocol_sha256
        write_json(out / "summary.json", summary)
        write_json(out / "artifacts-inventory.json", inventory(out))
        write_json(out / "completion-receipt.json", {
            "completed_utc": utc(), "protocol_sha256": args.expected_protocol_sha256,
            "summary_sha256": digest(out / "summary.json"),
            "artifacts_inventory_sha256": digest(out / "artifacts-inventory.json"),
            "historical_inputs_unchanged": True, "new_model_calls": 0,
            "processing_errors": summary["processing_errors"], "retry_allowed": False,
        })
        return {"output": str(out), "summary": str(out / "summary.json"),
                "retained": len(rows), "processing_errors": summary["processing_errors"]}
    except Exception as error:
        write_json(out / "fatal-error.json", {"utc": utc(), "error": error_record(error),
                                               "retry_allowed": False})
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freezer = sub.add_parser("freeze", help="Pin source and inputs; never execute measured logic")
    freezer.add_argument("--study-dir", type=Path, default=ROOT / "output/matched-local-study-2026-10-18")
    freezer.add_argument("--analysis-dir", type=Path,
                         default=ROOT / "output/matched-local-analysis-2026-10-18")
    freezer.add_argument("--legacy-root", type=Path, required=True)
    freezer.add_argument("--legacy-python", type=Path, default=Path(sys.executable))
    freezer.add_argument("--expected-current-commit", required=True)
    freezer.add_argument("--expected-legacy-commit", default=OLD_REVISION)
    freezer.add_argument("--output-dir", type=Path, required=True)
    runner = sub.add_parser("run", help="Execute exactly once from an existing frozen protocol")
    runner.add_argument("--protocol", type=Path, required=True)
    runner.add_argument("--expected-protocol-sha256", required=True)
    runner.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = freeze(args) if args.command == "freeze" else run(args)
        print(json.dumps(result, sort_keys=True))
        return 2 if result.get("processing_errors") else 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--legacy-worker":
        legacy_worker(Path(sys.argv[2]))
    else:
        raise SystemExit(main())
