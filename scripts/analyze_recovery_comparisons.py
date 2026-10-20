"""Describe all matched pairs and public-capability strata after the bound audit.

This presentation/checking layer does not execute the collection, application,
framework, or auditor. It reports discrepancies rather than assuming parity.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import json
from pathlib import Path
import shutil


def load_guard():
    path = Path(__file__).with_name("plot_recovery_controller_study.py")
    spec = importlib.util.spec_from_file_location("recovery_publication_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def action_sequence(trial):
    """Compare actions/times and dispatch identities, not diagnostic wording."""
    result = []
    for event in trial["trajectory"]:
        if event["kind"] not in {"dispatch", "read", "wait", "stop", "abstain"}:
            continue
        row = {"kind": event["kind"], "at_ms": event["at_ms"]}
        if event["kind"] == "dispatch":
            decision = event["decision"]
            row["dispatch_identity"] = {
                key: decision[key]
                for key in ("action_id", "attempt_id", "actor", "idempotency_key")
                if key in decision
            }
        result.append(row)
    return result


def compare_pair(left, right):
    if left["status"] != "completed" or right["status"] != "completed":
        return {"comparable": False, "mismatches": [], "claims": {}}
    fields = {
        "final_state_claim": (left["report"]["reported_state"], right["report"]["reported_state"]),
        "final_action_linked_claim": (
            left["report"]["reported_action_linked"],
            right["report"]["reported_action_linked"],
        ),
        "endpoint_vector": (left["metrics"], right["metrics"]),
        "action_sequence": (action_sequence(left), action_sequence(right)),
        "full_ledger_truth": (left["truth"], right["truth"]),
    }
    return {
        "comparable": True,
        "mismatches": [name for name, (a, b) in fields.items() if a != b],
        "claims": {
            name: {"left": a, "right": b}
            for name, (a, b) in fields.items()
            if name.startswith("final_")
        },
    }


def aggregate(rows, endpoints):
    completed = sum(row["status"] == "completed" for row in rows)
    metrics = {}
    for endpoint in endpoints:
        values = [row["metrics"][endpoint] for row in rows if endpoint in row["metrics"]]
        total = sum(values)
        metrics[endpoint] = {
            "sum": total,
            "observed": len(values),
            "unavailable": len(rows) - len(values),
            "mean": total / len(values) if values else None,
        }
    return {
        "planned": len(rows),
        "completed": completed,
        "failed": len(rows) - completed,
        "metrics": metrics,
    }


def analyze(study, audit, output):
    guard = load_guard()
    bundle = guard.verify_inputs(study, audit)
    output = Path(output).resolve()
    guard.require(not output.exists(), "analysis requires a fresh output directory")
    guard.require(
        not output.is_relative_to(bundle["study_root"])
        and not output.is_relative_to(bundle["audit_root"]),
        "analysis must be separate",
    )
    trials, capabilities = {}, {}
    for slot in bundle["protocol"]["schedule"]:
        with gzip.open(
            bundle["study_root"] / "trials" / (slot["trial_id"] + ".json.gz"),
            "rt",
            encoding="utf-8",
        ) as stream:
            row = json.load(stream)
        key = (slot["case_id"], slot["seed"], slot["method"])
        guard.require(key not in trials, "duplicate pair key")
        trials[key] = row
        flag = row.get("public_case", {}).get("native_idempotency")
        if type(flag) is bool:
            previous = capabilities.setdefault(slot["case_id"], flag)
            guard.require(previous is flag, "public capability changes across paired cells")
    comparisons = []
    for left_method, right_method in (
        ("reference", "consequax_poll"),
        ("readback_state", "consequax_poll"),
    ):
        pairs, mismatch_counts = [], {}
        identities = sorted({(case, seed) for case, seed, _ in trials})
        for case, seed in identities:
            left, right = trials[(case, seed, left_method)], trials[(case, seed, right_method)]
            outcome = compare_pair(left, right)
            for name in outcome["mismatches"]:
                mismatch_counts[name] = mismatch_counts.get(name, 0) + 1
            pairs.append(
                {
                    "case_id": case,
                    "seed": seed,
                    "left_trial": left["trial_id"],
                    "right_trial": right["trial_id"],
                    **outcome,
                }
            )
        comparisons.append(
            {
                "left": left_method,
                "right": right_method,
                "planned_pairs": len(pairs),
                "comparable_pairs": sum(row["comparable"] for row in pairs),
                "mismatch_counts": mismatch_counts,
                "pairs": pairs,
            }
        )
    strata = []
    schedule = bundle["protocol"]["schedule"]
    for dimension in ("native_idempotency", "domain"):
        partitions = {}
        for slot in schedule:
            label = (
                (
                    str(capabilities[slot["case_id"]]).lower()
                    if slot["case_id"] in capabilities
                    else "unavailable"
                )
                if dimension == "native_idempotency"
                else slot["domain"]
            )
            partitions.setdefault((label, slot["method"]), []).append(
                trials[(slot["case_id"], slot["seed"], slot["method"])]
            )
        for (label, method), rows in sorted(partitions.items()):
            strata.append(
                {
                    "dimension": dimension,
                    "stratum": label,
                    "method": method,
                    **aggregate(rows, guard.ENDPOINTS),
                }
            )
    output.mkdir(parents=True, exist_ok=False)
    guard.write_json(
        output / "comparisons.json",
        {"schema": "recovery-paired-conformance-v1", "comparisons": comparisons},
    )
    guard.write_json(
        output / "descriptive-strata.json",
        {"schema": "recovery-descriptive-strata-v1", "groups": strata},
    )
    with (output / "descriptive-strata.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "dimension",
                "stratum",
                "method",
                "planned",
                "completed",
                "failed",
                "endpoint",
                "sum",
                "observed",
                "unavailable",
                "mean",
            ],
        )
        writer.writeheader()
        for group in strata:
            for endpoint, metric in group["metrics"].items():
                writer.writerow(
                    {
                        **{key: value for key, value in group.items() if key != "metrics"},
                        "endpoint": endpoint,
                        **metric,
                    }
                )
    copies = [
        (Path(__file__), "analysis-code.source.py"),
        (Path(guard.__file__), "publication-guard.source.py"),
        (bundle["study_root"] / "protocol.json", "protocol.source.json"),
        (bundle["study_root"] / "manifest.json", "study-manifest.source.json"),
        (bundle["audit_root"] / "audit-receipt.json", "audit-receipt.source.json"),
    ]
    for source, name in copies:
        shutil.copyfile(source, output / name)
    (output / "README.md").write_text(
        "# Matched recovery checks and descriptive strata\n\n"
        "Every planned case/seed pair is retained. Final state/linkage claims, the endpoint vector, "
        "controller action kinds/times/dispatch identities, and full-ledger truth are compared. "
        "Diagnostic decision wording and package-specific report metadata are not parity targets. "
        "Mismatches are reported, not rejected. A shared application state machine means reference "
        "agreement is implementation conformance, not superiority or external replication.\n\n"
        "Capability/domain strata are descriptive views of all scheduled cells, not new independent "
        "task samples. Failed execution contributes zero only to the operational primary; unavailable "
        "semantic/resource values retain their missing denominator. Capabilities use consistent "
        "public declarations; a wholly unavailable declaration remains an unavailable stratum. "
        "These views do not add population inference or independent human evidence-support labels.\n",
        encoding="utf-8",
    )
    files = {
        path.relative_to(output).as_posix(): guard.sha(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    guard.write_json(
        output / "manifest.json",
        {
            "schema": "recovery-paired-descriptive-exports-v1",
            "complete": True,
            "protocol_sha256": bundle["protocol_sha256"],
            "study_manifest_sha256": bundle["manifest_sha256"],
            "audit_receipt_sha256": guard.sha(bundle["audit_root"] / "audit-receipt.json"),
            "files": files,
        },
    )
    return [
        {
            key: row[key]
            for key in ("left", "right", "planned_pairs", "comparable_pairs", "mismatch_counts")
        }
        for row in comparisons
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", required=True, type=Path)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.study_dir, args.audit_dir, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
