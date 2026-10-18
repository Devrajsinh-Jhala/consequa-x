"""Finalize one closed matched study without generation, repair, or redraws.

This wrapper and its execution diagnostics were added after collection began.
They preserve the frozen primary analyzer and disclose their descriptive role.
An output directory is created only after closed-study integrity checks pass.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

try:
    from . import analyze_matched_local_study as primary
    from . import summarize_matched_execution as execution
    from .run_matched_local_study import read_json, validate_freeze, write_new
except ImportError:
    import analyze_matched_local_study as primary
    import summarize_matched_execution as execution
    from run_matched_local_study import read_json, validate_freeze, write_new


STOP_EVENTS = {"run_infrastructure_stop", "wall_time_exhausted", "call_budget_exhausted",
               "chat_transport_failed", "chat_identity_failed", "model_identity_failed"}


def file_inventory(directory):
    """Hash every regular file, with no exclusions or traversal through links."""
    directory = Path(directory).resolve()
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Cannot seal a study/artifact directory containing symbolic links")
        if path.is_file():
            resolved = path.resolve()
            if not resolved.is_relative_to(directory):
                raise ValueError("Artifact escapes its inventory directory")
            data = path.read_bytes()
            result[path.relative_to(directory).as_posix()] = {
                "sha256": sha256(data).hexdigest(), "bytes": len(data)}
    return result


def accounting(directory, protocol):
    counts = Counter()
    schedule = protocol["schedule"]
    if len({slot["slot_id"] for slot in schedule}) != protocol["planned_episodes"]:
        raise ValueError("Frozen schedule does not have its declared unique planned slots")
    for slot in schedule:
        folder = directory / "episodes" / slot["slot_id"]
        started, receipt = folder / "started.json", folder / "receipt.json"
        if not started.exists():
            if receipt.exists():
                raise ValueError("Unstarted slot has an episode receipt")
            counts["unstarted"] += 1
        elif not receipt.exists():
            counts["interrupted_partial"] += 1
        else:
            value = read_json(receipt)
            if value["slot"] != slot or value["status"] not in {"completed", "failed"}:
                raise ValueError("Episode receipt differs from its frozen slot")
            counts[value["status"]] += 1
    result = {status: counts[status] for status in execution.STATUSES}
    if sum(result.values()) != protocol["planned_episodes"]:
        raise ValueError("Final disposition does not cover every planned slot")
    return result


def disposition_for(protocol, protocol_sha, journal, journal_sha, analysis_sha, statuses):
    residual = statuses["unstarted"] + statuses["interrupted_partial"]
    starts = [index for index, event in enumerate(journal.records) if event["event"] == "run_started"]
    last_run = journal.records[starts[-1]:] if starts else journal.records
    stop_events = [event for event in last_run if event["event"] in STOP_EVENTS]
    if not residual:
        state, reason, source = "completed", "", "all_frozen_slots_finalized"
    else:
        state, source = "stopped", "journal_event"
        types = {event["event"] for event in stop_events}
        if "wall_time_exhausted" in types:
            reason = "Frozen wall-time limit reached; residual frozen slots remain explicitly unstarted or partial."
        elif "call_budget_exhausted" in types:
            reason = "Frozen attempted-call budget reached; residual frozen slots remain explicitly unstarted or partial."
        elif types:
            reason = "The final invocation stopped after a recorded infrastructure/identity failure; residual slots are retained."
        else:
            source = "disclosed_incomplete_execution"
            reason = ("Execution ended before every frozen slot was started or finalized. The terminal "
                      "run_stopped event supplies no infrastructure or budget reason. Residual slots "
                      "are disclosed, with no replacement samples collected by this finalizer.")
    return {
        "schema_version": "consequa-matched-study-disposition-v1",
        "final": True, "collection_state": state, "no_active_runner": True,
        "runner_gate": "No runner.lock and a terminal, valid hash-chained run_stopped event; "
                       "all closed-study file hashes rechecked before final receipt.",
        "protocol_sha256": protocol_sha, "journal_sha256": journal_sha,
        "analysis_sha256": analysis_sha,
        "planned_episodes": protocol["planned_episodes"],
        "started_episodes": protocol["planned_episodes"] - statuses["unstarted"],
        "episode_status": statuses, "stopped_reason": reason, "reason_source": source,
        "stop_events": stop_events,
        "postprocessing_disclosure": execution.DISCLOSURE,
    }


def finalize(study, output):
    study, output = Path(study).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(study):
        raise ValueError("Output must be a fresh directory outside the closed study")
    journal = execution.require_closed(study)
    protocol = validate_freeze(study)
    initial_inventory = file_inventory(study)
    journal_sha = initial_inventory["request-journal.jsonl"]["sha256"]
    protocol_sha = initial_inventory["protocol.json"]["sha256"]
    statuses = accounting(study, protocol)
    analysis = primary.analyze(study)
    if (analysis["episode_status"] != statuses
            or analysis["planned_episodes"] != protocol["planned_episodes"]
            or analysis["protocol_sha256"] != protocol_sha
            or analysis["journal_sha256"] != journal_sha):
        raise ValueError("Primary analysis does not match the closed-study inventory/accounting")
    execution.require_closed(study)
    if file_inventory(study) != initial_inventory:
        raise ValueError("Closed study changed during primary analysis")

    output.mkdir(parents=True, exist_ok=False)
    analysis_path = output / "analysis.json"
    write_new(analysis_path, analysis)
    with (output / "analysis.md").open("x", encoding="utf-8") as stream:
        stream.write(primary.markdown(analysis))
    analysis_sha = sha256(analysis_path.read_bytes()).hexdigest()
    disposition = disposition_for(protocol, protocol_sha, journal, journal_sha, analysis_sha, statuses)
    disposition_path = output / "final-disposition.json"
    write_new(disposition_path, disposition)

    diagnostics, diagnostic_inventory = execution.summarize(study, analysis_path, disposition_path)
    diagnostic_dir = output / "execution"
    diagnostic_dir.mkdir(exist_ok=False)
    diagnostic_input = diagnostic_dir / "input-inventory.json"
    write_new(diagnostic_input, diagnostic_inventory)
    diagnostics["input_inventory_sha256"] = sha256(diagnostic_input.read_bytes()).hexdigest()
    write_new(diagnostic_dir / "execution-summary.json", diagnostics)
    with (diagnostic_dir / "execution-summary.md").open("x", encoding="utf-8") as stream:
        stream.write(execution.markdown(diagnostics))

    execution.require_closed(study)
    if file_inventory(study) != initial_inventory:
        raise ValueError("Closed study changed during execution postprocessing; output is unsealed")
    study_inventory_path = output / "closed-study-inventory.json"
    write_new(study_inventory_path, {
        "schema_version": "consequa-closed-matched-study-inventory-v1",
        "protocol_sha256": protocol_sha, "journal_sha256": journal_sha,
        "file_count": len(initial_inventory), "files": initial_inventory,
    })
    artifact_inventory = file_inventory(output)
    artifact_inventory_path = output / "analysis-artifacts-inventory.json"
    write_new(artifact_inventory_path, {
        "schema_version": "consequa-matched-analysis-artifacts-inventory-v1",
        "excludes": ["analysis-artifacts-inventory.json", "finalization-receipt.json"],
        "files": artifact_inventory,
    })
    # The receipt is the final output. A failed finalization leaves an unsealed
    # fresh directory for inspection; no partial output is silently replaced.
    execution.require_closed(study)
    if file_inventory(study) != initial_inventory:
        raise ValueError("Closed study changed before sealing; no final receipt written")
    receipt = {
        "schema_version": "consequa-matched-study-finalization-v1",
        "final": True, "protocol_sha256": protocol_sha, "journal_sha256": journal_sha,
        "analysis_sha256": analysis_sha, "source_revision": protocol["source_revision"],
        "episode_status": statuses, "planned_episodes": protocol["planned_episodes"],
        "collection_state": disposition["collection_state"],
        "stopped_reason": disposition["stopped_reason"],
        "closed_study_inventory_sha256": sha256(study_inventory_path.read_bytes()).hexdigest(),
        "analysis_artifacts_inventory_sha256": sha256(artifact_inventory_path.read_bytes()).hexdigest(),
        "postprocessor_sources": {
            Path(__file__).name: sha256(Path(__file__).read_bytes()).hexdigest(),
            Path(execution.__file__).name: sha256(Path(execution.__file__).read_bytes()).hexdigest(),
        },
        "postprocessing_disclosure": execution.DISCLOSURE,
        "scope": "Runs the unchanged frozen primary analyzer; adds disclosed descriptive execution "
                 "diagnostics and complete file inventories. Does not generate calls, repair data, "
                 "replace samples, claim external preregistration, or create paper figures.",
    }
    write_new(output / "finalization-receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-output", required=True)
    parser.add_argument("--output-dir", required=True, help="Fresh directory outside the study")
    args = parser.parse_args()
    result = finalize(args.study_output, args.output_dir)
    print(json.dumps({"output": str(Path(args.output_dir).resolve()),
                      "episode_status": result["episode_status"],
                      "collection_state": result["collection_state"],
                      "protocol_sha256": result["protocol_sha256"]}))


if __name__ == "__main__":
    main()
