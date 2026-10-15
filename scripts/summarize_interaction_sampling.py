"""Derive complete tables from a sealed, independently audited interaction study.

No policy/model calls, source-package imports, interval recomputation or changes
to the sealed study. The passed audit receipt must match its manifest, source
and counts. All input files are rehashed before summaries are read.
"""

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath


TARGETS = ("action", "consequence", "action_linked_consequence")
VARIANTS = ("normal", "hoeffding_exact_endpoints")
RATE_FIELDS = ("interval_coverage", "reference_sign_detection", "false_nonzero_flag")
COUNT_FIELDS = (
    "planned_trials",
    "available_estimates",
    "refused_estimates",
    "reference_eligible_trials",
    "reference_eligible_available",
    "available_intervals",
)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def _load(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _verify_inventory(root, manifest):
    _require(
        manifest["completed"] is True and manifest["status"] == "completed",
        "A completed sealed study is required",
    )
    names = set()
    for item in manifest["artifacts"]:
        name = item["path"]
        _require(type(name) is str, "Artifact paths must be strings")
        canonical = PurePosixPath(name)
        _require(
            canonical.as_posix() == name
            and not canonical.is_absolute()
            and all(
                part not in ("", ".", "..") and ":" not in part and "\\" not in part
                for part in name.split("/")
            ),
            "Unsafe artifact path",
        )
        _require(name not in names and name != "manifest.json", "Duplicate or circular artifact")
        names.add(name)
        path = (root / name).resolve()
        _require(path.is_relative_to(root), "Artifact escapes the sealed study")
        _require(
            type(item["bytes"]) is int and path.stat().st_size == item["bytes"],
            "Artifact size changed: " + name,
        )
        _require(_digest(path) == item["sha256"], "Artifact bytes changed: " + name)
    _require(
        names
        == {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path != root / "manifest.json"
        },
        "The sealed artifact inventory changed",
    )
    return len(names)


def _rate_checks(rate, denominator):
    k, n = rate["numerator"], rate["denominator"]
    _require(
        type(k) is int and type(n) is int and 0 <= k <= n == denominator,
        "Invalid rate numerator/denominator",
    )
    if n:
        _require(rate["rate"] == k / n, "A rate changed after audit")
        low, high = rate["confidence_interval"]
        _require(0 <= low <= high <= 1, "Invalid rate uncertainty")
    else:
        _require(
            rate["rate"] is None and rate["confidence_interval"] is None,
            "A zero denominator must remain undefined",
        )


def _row_checks(row, repeats, *, interaction=False):
    for field in COUNT_FIELDS:
        _require(
            type(row[field]) is int and 0 <= row[field] <= repeats,
            "Invalid summary count: " + field,
        )
    _require(row["planned_trials"] == repeats, "Changed planned denominator")
    available, refused = row["available_estimates"], row["refused_estimates"]
    _require(available + refused == repeats, "Dropped refused estimates")
    _require(
        sum(row.get("refusal_counts", {}).values()) == refused or interaction,
        "Refusal reasons do not partition refused estimates",
    )
    eligible = row["reference"] is not None
    _require(
        row["reference_eligible_trials"] == (repeats if eligible else 0),
        "Changed reference eligibility",
    )
    _require(
        row["reference_eligible_available"] == (available if eligible else 0),
        "Changed eligible available denominator",
    )
    intervals = row["available_intervals"]
    _require(intervals == (0 if interaction else available), "Changed interval availability")
    _rate_checks(row["interval_coverage"], intervals if eligible else 0)
    _rate_checks(
        row["reference_sign_detection"], intervals if row["reference"] not in (None, 0) else 0
    )
    _rate_checks(row["false_nonzero_flag"], intervals if row["reference"] == 0 else 0)
    _require(0 <= row["degenerate_intervals"] <= intervals, "Invalid degeneracy count")
    width = row["mean_interval_width"]
    _require(
        (
            width is None
            if not intervals
            else type(width) in (int, float) and math.isfinite(width) and width >= 0
        ),
        "Invalid interval width",
    )
    for field in ("bias", "rmse", "bias_mcse"):
        value = row[field]
        should_exist = eligible and available >= (2 if field == "bias_mcse" else 1)
        _require(
            (type(value) in (int, float) and math.isfinite(value))
            if should_exist
            else value is None,
            "Changed numerical-reference eligibility: " + field,
        )


def _index(rows, keys, expected):
    result = {}
    for row in rows:
        key = tuple(row[field] for field in keys)
        _require(key not in result, "Duplicate summary row")
        result[key] = row
    _require(set(result) == expected, "Missing or extra summary rows")
    return result


def _flatten(value, prefix=""):
    result = {}
    for key, item in value.items():
        name = prefix + str(key)
        if type(item) is dict:
            result.update(_flatten(item, name + "."))
        elif type(item) is list:
            result[name] = json.dumps(item, separators=(",", ":"))
        else:
            result[name] = item
    return result


def _write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path, rows):
    flattened = [_flatten(row) for row in rows]
    fields = list(dict.fromkeys(key for row in flattened for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(flattened)


def _paired(rows, kind):
    normal = [row for row in rows if row["variant"] == "normal"]
    bounded = {
        (row["mechanism"], row["coalition_game"], row["target"], row["decision_index"]): row
        for row in rows
        if row["variant"] == "hoeffding_exact_endpoints"
    }
    result = []
    for row in normal:
        key = tuple(
            row[field] for field in ("mechanism", "coalition_game", "target", "decision_index")
        )
        other = bounded[key]
        for field in (*COUNT_FIELDS, "reference", "bias", "bias_mcse", "rmse", "refusal_counts"):
            _require(row[field] == other[field], "Interval variants changed points or eligibility")
        result.append(
            {
                "kind": kind,
                **{
                    field: row[field]
                    for field in ("mechanism", "coalition_game", "target", "decision_index")
                },
                **{
                    field: row[field]
                    for field in (*COUNT_FIELDS, "reference", "bias", "bias_mcse", "rmse")
                },
                "normal": {
                    field: row[field]
                    for field in (*RATE_FIELDS, "mean_interval_width", "degenerate_intervals")
                },
                "bounded_exact": {
                    field: other[field]
                    for field in (*RATE_FIELDS, "mean_interval_width", "degenerate_intervals")
                },
                "coverage_count_change": other["interval_coverage"]["numerator"]
                - row["interval_coverage"]["numerator"],
                "comparison_additional_calls": 0,
            }
        )
    return result


def _number(value):
    return "undefined" if value is None else f"{value:.5g}"


def _fraction(rate):
    n = rate["denominator"]
    return f"{rate['numerator']}/{n}" if n else "undefined (0/0)"


def summarize(directory, audit_file, output, *, expected_source):
    root, destination, audit_path = (
        Path(directory).resolve(),
        Path(output).resolve(),
        Path(audit_file).resolve(),
    )
    _require(
        not destination.is_relative_to(root), "Derived files must stay outside the sealed study"
    )
    _require(
        not destination.exists() or (destination.is_dir() and not any(destination.iterdir())),
        "Use a new or empty derived-results directory",
    )
    manifest_path = root / "manifest.json"
    manifest = _load(manifest_path)
    inventory_count = _verify_inventory(root, manifest)
    manifest_hash = _digest(manifest_path)
    protocol, summary, audit = (
        _load(root / "protocol.json"),
        _load(root / "summary.json"),
        _load(audit_path),
    )
    _require(protocol["source_revision"] == expected_source, "Unexpected frozen source")
    _require(
        audit["status"] == "passed"
        and type(audit["assertions"]) is int
        and audit["assertions"] > 0,
        "A passed independent audit receipt is required",
    )
    _require(
        audit["manifest_sha256"] == manifest_hash and audit["source_revision"] == expected_source,
        "The audit does not belong to this sealed source/artifact",
    )
    for audit_field, summary_field in (
        ("trials", "retained_trials"),
        ("branches", "planned_branches"),
        ("actual_policy_calls", "actual_policy_calls"),
    ):
        _require(
            audit[audit_field] == summary[summary_field], "Audit count does not match saved results"
        )
    _require(
        audit["generation_calls"] == 0 and summary["additional_comparison_policy_calls"] == 0,
        "This analysis requires the declared synthetic same-draw study",
    )
    plan = protocol["plan"]
    names, games, repeats = plan["mechanisms"], plan["games"], plan["repeats"]
    groups = {(name, game) for name in names for game in games}
    branches = _index(summary["branch_rows"], ("mechanism", "coalition_game"), groups)
    branches_per_trial = 2 * plan["endpoint_samples"] + 8 * plan["pairs"] * plan["samples_per_eval"]
    _require(
        summary["planned_trials"] == summary["retained_trials"] == len(groups) * repeats,
        "Changed total trial denominator",
    )
    _require(
        summary["planned_branches"] == len(groups) * repeats * branches_per_trial,
        "Changed total branch denominator",
    )
    for row in branches.values():
        _require(
            row["planned_trials"] == repeats
            and row["planned_branches"] == repeats * branches_per_trial,
            "Changed per-game branch denominator",
        )
        _require(
            sum(row["status_counts"].values()) == row["planned_branches"],
            "Branch statuses do not partition all planned slots",
        )
        calls = row["calls"]
        _require(
            calls["factual"] == 3 * repeats
            and calls["factual"] + calls["continuations"] == calls["total"]
            and calls["additional_comparison"] == 0,
            "Changed policy-call accounting",
        )
    _require(
        sum(row["calls"]["total"] for row in branches.values()) == summary["actual_policy_calls"],
        "Changed total policy-call accounting",
    )
    coefficients = _index(
        summary["coefficient_rows"],
        ("mechanism", "coalition_game", "variant", "target", "decision_index"),
        {
            (name, game, variant, target, position)
            for name, game in groups
            for variant in VARIANTS
            for target in TARGETS
            for position in range(3)
        },
    )
    endpoints = _index(
        summary["endpoint_rows"],
        ("mechanism", "coalition_game", "variant", "target", "decision_index"),
        {
            (name, game, variant, target, "endpoint")
            for name, game in groups
            for variant in VARIANTS
            for target in TARGETS
        },
    )
    _index(
        summary["interaction_rows"],
        ("mechanism", "coalition_game", "target"),
        {(name, game, target) for name, game in groups for target in TARGETS},
    )
    for row in summary["coefficient_rows"] + summary["endpoint_rows"]:
        _row_checks(row, repeats)
    for row in summary["interaction_rows"]:
        _row_checks(row, repeats, interaction=True)
    availability = []
    for name in names:
        for game in games:
            for target in TARGETS:
                row = coefficients[name, game, "normal", target, 0]
                fields = (*COUNT_FIELDS, "refusal_counts")
                for variant in VARIANTS:
                    for position in range(3):
                        other = coefficients[name, game, variant, target, position]
                        _require(
                            all(row[field] == other[field] for field in fields),
                            "A whole-vector availability denominator changed",
                        )
                endpoint = endpoints[name, game, "normal", target, "endpoint"]
                availability.append(
                    {
                        "mechanism": name,
                        "coalition_game": game,
                        "target": target,
                        "coefficient_vectors": {field: row[field] for field in fields},
                        "independent_endpoints": {field: endpoint[field] for field in fields},
                        "reference_note": "defined population game"
                        if row["reference"] is not None
                        else "population coefficient reference undefined; numeric finite estimates are not coverage",
                    }
                )
    comparisons = _paired(summary["coefficient_rows"], "coefficient") + _paired(
        summary["endpoint_rows"], "independent_endpoint"
    )
    result = {
        "schema_version": "refund-interaction-sampling-derived-v1",
        "derived_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": expected_source,
        "package_version": protocol["package_version"],
        "plan": plan,
        "execution": protocol["execution"],
        "inputs": {
            "study_directory": str(root),
            "sealed_files_verified": inventory_count,
            "manifest_sha256": manifest_hash,
            "protocol_sha256": _digest(root / "protocol.json"),
            "summary_sha256": _digest(root / "summary.json"),
            "audit_receipt_sha256": _digest(audit_path),
            "postprocessor_sha256": _digest(__file__),
        },
        "audit": audit,
        "planned_trials": summary["planned_trials"],
        "retained_trials": summary["retained_trials"],
        "planned_branches": summary["planned_branches"],
        "actual_policy_calls": summary["actual_policy_calls"],
        "additional_comparison_policy_calls": summary["additional_comparison_policy_calls"],
        "branch_rows": summary["branch_rows"],
        "coefficient_rows": summary["coefficient_rows"],
        "endpoint_rows": summary["endpoint_rows"],
        "interaction_rows": summary["interaction_rows"],
        "availability_rows": availability,
        "interval_comparison_rows": comparisons,
        "limits": [
            "Synthetic planted-factual refund study; no model calls or held-out model generalization",
            "Games/targets/players/variants share data; rows are not independent replications",
            "Coverage conditions on available estimates and defined population references; refusals stay explicit",
            "Rate uncertainty is nominal Wilson, with no multiplicity adjustment",
            "Interactions are point-only pooled diagnostics; no interval or sign claim",
            "Pairing compares interval variants on identical retained draws; count changes are descriptive, not a paired significance test",
            "Hashes and an audit receipt detect changed bytes; they do not authenticate external providers",
        ],
    }
    destination.mkdir(parents=True, exist_ok=True)
    _write_json(destination / "analysis.json", result)
    for filename, key in (
        ("branches.csv", "branch_rows"),
        ("coefficients.csv", "coefficient_rows"),
        ("endpoints.csv", "endpoint_rows"),
        ("interactions.csv", "interaction_rows"),
        ("availability.csv", "availability_rows"),
        ("interval-comparisons.csv", "interval_comparison_rows"),
    ):
        _write_csv(destination / filename, result[key])
    lines = [
        "# Repeated physical refund sampling: derived findings",
        "",
        f"Frozen source `{expected_source}`; package `{protocol['package_version']}`. "
        f"Retained {summary['retained_trials']:,}/{summary['planned_trials']:,} trials, "
        f"{summary['planned_branches']:,} planned branches and {summary['actual_policy_calls']:,} actual scripted calls. "
        "Interval comparison made zero additional calls. No model was called.",
        "",
        f"The independent audit passed {audit['assertions']:,} assertions and checked "
        f"{audit['full_traces']:,} complete preselected traces. Its receipt matches the sealed manifest "
        f"`{manifest_hash}`; this postprocessor rehashed all {inventory_count} sealed files.",
        "",
        "The CSV files and analysis.json retain every mechanism/game/target/position/variant row. "
        "Availability.csv counts whole coefficient vectors once, rather than counting three players "
        "or two interval variants as independent trials. Undefined references and zero-denominator rates remain undefined.",
        "",
        "## Every case and game: branch retention",
        "",
        "Completed counts executed branches, including known violations and unknown target evidence.",
        "",
        "| Case | Game | Completed | Invalid | Failed | Unstarted | Calls | Inactive-held branches |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in names:
        for game in games:
            row = branches[name, game]
            status = row["status_counts"]
            lines.append(
                f"| {name} | {game} | {status['completed']} | {status['invalid']} | "
                f"{status['failed']} | {status['unstarted']} | {row['calls']['total']} | "
                f"{row['inactive_held_branches']} |"
            )
    lines += [
        "",
        "## On-reach consequence coefficients",
        "",
        "All registered cases are shown. Coverage and sign/false-nonzero columns are explicit k/n; "
        "nominal rate intervals are retained in the complete tables. Width and sign detection must "
        "accompany coverage. A zero sign denominator is not evidence of zero error.",
        "",
        "| Case | Player | Variant | Reference | Available/planned | Coverage k/n | Mean width | Sign k/n | False nonzero k/n | Bias | RMSE |",
        "| --- | ---: | --- | ---: | ---: | --- | ---: | --- | --- | ---: | ---: |",
    ]
    for row in summary["coefficient_rows"]:
        if row["coalition_game"] != "on_reach" or row["target"] != "consequence":
            continue
        lines.append(
            f"| {row['mechanism']} | {row['decision_index']} | {row['variant']} | {_number(row['reference'])} | "
            f"{row['available_estimates']}/{row['planned_trials']} | {_fraction(row['interval_coverage'])} | "
            f"{_number(row['mean_interval_width'])} | {_fraction(row['reference_sign_detection'])} | "
            f"{_fraction(row['false_nonzero_flag'])} | {_number(row['bias'])} | {_number(row['rmse'])} |"
        )
    lines += ["", "## Interpretation limits", ""] + ["- " + value for value in result["limits"]]
    (destination / "FINDINGS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    _write_json(
        destination / "manifest.json",
        {
            "completed": True,
            "status": "completed",
            "source_revision": expected_source,
            "input_study_manifest_sha256": manifest_hash,
            "artifacts": [
                {"path": path.name, "bytes": path.stat().st_size, "sha256": _digest(path)}
                for path in sorted(destination.iterdir())
                if path.is_file()
            ],
        },
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected-source", required=True)
    args = parser.parse_args(argv)
    result = summarize(
        args.directory, args.audit, args.output, expected_source=args.expected_source
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(Path(args.output).resolve()),
                "retained_trials": result["retained_trials"],
                "planned_branches": result["planned_branches"],
                "actual_policy_calls": result["actual_policy_calls"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
