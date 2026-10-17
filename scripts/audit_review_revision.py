"""Recompute bounded paper-review arithmetic from retained project evidence.

Uses only the standard library and reads existing evidence without changing it.
An optional review ZIP is inspected only to hash two known members; no attached
code is executed, imported, extracted, or deserialized as executable objects.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
STATUS_NAMES = ("completed", "invalid", "failed", "unstarted")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def wilson(k: int, n: int, alpha: float = 0.05) -> list[float]:
    z = NormalDist().inv_cdf(1 - alpha / 2)
    denominator = 1 + z * z / n
    center = (k / n + z * z / (2 * n)) / denominator
    half = z * math.sqrt(k / n * (1 - k / n) / n + z * z / (4 * n * n)) / denominator
    return [0 if k == 0 else center - half, 1 if k == n else center + half]


def load_csv(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def calculate(review_pack: Path | None) -> dict:
    branches = load_csv("output/interaction-sampling-findings-2026-10-15/branches.csv")
    availability = load_csv("output/interaction-sampling-findings-2026-10-15/availability.csv")
    totals = {
        name: sum(int(row[f"status_counts.{name}"]) for row in branches)
        for name in STATUS_NAMES
    }
    planned = sum(int(row["planned_branches"]) for row in branches)
    calls = sum(int(row["calls.total"]) for row in branches)
    require(sum(totals.values()) == planned == 655360, "Repeated-study branch totals differ")
    require(calls == 628535, "Repeated-study actual-call total differs")
    for row in branches:
        require(
            sum(int(row[f"status_counts.{name}"]) for name in STATUS_NAMES)
            == int(row["planned_branches"]),
            "A repeated-study stratum does not partition its planned branches",
        )

    cost_rows = []
    for row in branches:
        matches = [
            item for item in availability
            if item["mechanism"] == row["mechanism"]
            and item["coalition_game"] == row["coalition_game"]
            and item["target"] == "consequence"
        ]
        require(len(matches) == 1, "Expected exactly one matching global-vector availability row")
        count = int(matches[0]["coefficient_vectors.available_estimates"])
        cost_rows.append({
            "mechanism": row["mechanism"],
            "game": row["coalition_game"],
            "actual_calls": int(row["calls.total"]),
            "available_global_vectors": count,
            "calls_per_available_global_vector": int(row["calls.total"]) / count if count else None,
        })

    half_width = math.sqrt(2 * math.log(2 / 0.05) / 32)
    means = []
    widths = []
    clips = 0
    trial_path = ROOT / (
        "output/interaction-sampling-2026-10-15/trials/"
        "refund-p80-q20__on_reach.jsonl.gz"
    )
    with gzip.open(trial_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            trial = json.loads(line)
            estimates = [
                item for item in trial["variants"]["hoeffding_exact_endpoints"]["estimates"]
                if item["target"] == "consequence" and item["decision_index"] == 1
            ]
            require(len(estimates) == 1, "Expected one on-reach global retry coefficient per trial")
            estimate = estimates[0]
            values = estimate["pair_values"]
            require(
                len(values) == 32 and all(-1 <= value <= 1 for value in values),
                "Expected 32 signed bounded pair observations",
            )
            mean = sum(values) / 32
            expected = [max(-1, mean - half_width), min(1, mean + half_width)]
            interval = estimate["confidence_interval"]
            require(abs(mean - estimate["shapley_value"]) < 1e-12, "Saved pair mean differs")
            require(
                len(interval) == 2
                and all(abs(a - b) < 1e-12 for a, b in zip(expected, interval)),
                "Saved clipped Hoeffding interval differs",
            )
            means.append(mean)
            widths.append(expected[1] - expected[0])
            clips += int(mean + half_width > 1)
    require(len(widths) == 128, "Expected all 128 retained p80q20 on-reach trials")

    retained = ROOT / "output/interaction-sampling-2026-10-15"
    manifest_path = retained / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    size_groups = {}
    for item in manifest["artifacts"]:
        file_path = (retained / item["path"]).resolve()
        require(file_path.is_relative_to(retained.resolve()), "Manifest member is outside study root")
        actual_size = file_path.stat().st_size
        require(actual_size == item["bytes"], "A manifest-listed file size differs")
        group = item["path"].split("/")[0] if "/" in item["path"] else "root_metadata"
        size_groups.setdefault(group, {"files": 0, "bytes": 0})
        size_groups[group]["files"] += 1
        size_groups[group]["bytes"] += actual_size

    review_inspection = {"status": "not provided", "code_executed": False}
    if review_pack is not None:
        with ZipFile(review_pack) as archive:
            sim = archive.read("Consequa-X_Review/3_reproduction_code/sim.py")
            results_bytes = archive.read("Consequa-X_Review/3_reproduction_code/sim_results.json")
        review_inspection = {
            "status": "two known members hashed only",
            "sim_py_sha256": hashlib.sha256(sim).hexdigest(),
            "sim_results_sha256": hashlib.sha256(results_bytes).hexdigest(),
            "code_executed": False,
        }

    prior_studies = {}
    for label, name in [
        ("original_calibration", "output/calibration-probe-2026-10-11/summary.json"),
        ("shared_draw_followup", "output/interval-comparison-2026-10-13/raw/summary.json"),
    ]:
        summary = json.loads((ROOT / name).read_text(encoding="utf-8"))
        partition = {
            status: sum(row["status_counts"][status] for row in summary["branches"])
            for status in STATUS_NAMES
        }
        denominator = sum(row["planned_branches"] for row in summary["branches"])
        require(sum(partition.values()) == denominator, "Prior-study branch partition differs")
        prior_studies[label] = {
            "planned_branches": denominator,
            **partition,
            "actual_calls": summary["actual_policy_calls"],
            "not_completed_proportion": 1 - partition["completed"] / denominator,
        }

    return {
        "schema_version": "paper_review_arithmetic_v1",
        "scope": (
            "Independent arithmetic/retained-byte inspection only; no generation, model, "
            "external API or review-code execution"
        ),
        "revision_date": "2026-10-18",
        "wilson_95": {
            f"{k}/{n}": wilson(k, n) for k, n in [(6, 10), (118, 128), (128, 128), (92, 128)]
        },
        "hoeffding": {
            "pairs32_half_width": half_width,
            "pairs32_unclipped_width": 2 * half_width,
            "pairs16_unclipped_width": 2 * math.sqrt(2 * math.log(2 / 0.05) / 16),
            "p80q20_retry_mean": sum(means) / len(means),
            "p80q20_retry_mean_clipped_width": sum(widths) / len(widths),
            "p80q20_upper_clipped_trials": clips,
        },
        "repeated_branch_totals": {
            "planned": planned,
            **totals,
            "calls": calls,
            "completed_proportion": totals["completed"] / planned,
            "not_completed_proportion": 1 - totals["completed"] / planned,
        },
        "global_vector_costs": cost_rows,
        "retained_manifest_size_groups": size_groups,
        "retained_manifest_listed_bytes": sum(item["bytes"] for item in size_groups.values()),
        "retained_manifest_bytes": manifest_path.stat().st_size,
        "review_data_only_inspection": review_inspection,
        "prior_study_branch_counts": prior_studies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New JSON receipt; refuses overwrite")
    parser.add_argument("--review-pack", type=Path, help="Optional ZIP; hashes two known members only")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite existing audit output")
    try:
        result = calculate(args.review_pack)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError, KeyError, BadZipFile) as error:
        parser.exit(2, f"Audit failed: {error}\n")
    print("Paper-review arithmetic passed; wrote a new JSON receipt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
