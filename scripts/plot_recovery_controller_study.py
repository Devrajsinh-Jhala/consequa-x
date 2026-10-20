"""Export fixed publication figures only after completed collection and audit.

This postcollection source does not import the framework, application world,
runner, or auditor. It never opens a trial/database or executes a study. All
display choices below are fixed before the script is first given measured data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil


SCHEMA = "recovery-controller-publication-exports-v1"
STUDY_SCHEMA = "conseqa-recovery-controller-study-v1"
AUDIT_SCHEMA = "recovery-controller-postcollection-audit-v1"
METHODS = ("response_retry", "readback_state", "reference", "consequax_one_read", "consequax_poll")
NAMES = {
    "response_retry": "Response retry",
    "readback_state": "Readback state",
    "reference": "Independent ref.",
    "consequax_one_read": "ConseqaX one read",
    "consequax_poll": "ConseqaX poll",
}
SHORT = {
    "response_retry": "retry",
    "readback_state": "state",
    "reference": "reference",
    "consequax_one_read": "one read",
    "consequax_poll": "poll",
}
CONTRASTS = tuple(("consequax_poll", right) for right in METHODS[:-1])
ENDPOINTS = (
    "operational_safe_recovery",
    "original_completion",
    "recovery_completion",
    "safe_recovery",
    "duplicate_event",
    "unwanted_event",
    "state_false_success",
    "action_linked_false_success",
    "state_wrong_definite",
    "action_linked_wrong_definite",
    "state_definite",
    "state_abstention",
    "action_linked_definite",
    "action_linked_abstention",
    "dispatches",
    "reads",
    "waits",
    "decision_time_ms",
    "own_effect_count",
    "duplicate_count",
    "unwanted_effect_count",
)
BINARY = set(ENDPOINTS[:14])
PRIMARY = "operational_safe_recovery"
COLORS = {
    "safe": "#0072B2",
    "original": "#E69F00",
    "recovery": "#009E73",
    "duplicate": "#D55E00",
    "unwanted": "#CC79A7",
    "correct": "#0072B2",
    "incorrect": "#D55E00",
    "abstain": "#999999",
    "reads": "#0072B2",
    "dispatches": "#E69F00",
}
SPEC = {
    "method_order": list(METHODS),
    "family_order": "ascending literal family_id; every planned family",
    "contrasts": [list(pair) for pair in CONTRASTS],
    "primary": PRIMARY,
    "summary_figure_inches": [9.5, 11.2],
    "heatmap_figure_inches": [9.5, 8.3],
    "minimum_font_points": 10.5,
    "png_dpi": 300,
    "heatmap_limits": [-1, 1],
    "heatmap_colormap": "RdBu",
    "heatmap_midpoint": 0,
    "rate_ticks": [0, 0.5, 1],
    "resource_ticks": [0, 1, 2, 3, 4],
    "uncertainty_intervals": False,
    "population_inference": False,
    "denominators": {
        "operational_safe_recovery": "all planned slots; operational failure is false",
        "semantic_rates": "observed slots; unavailable slots explicitly shown",
        "state_claim_yields": "all planned slots; failures remain unavailable, not abstentions",
        "resource_means": "observed slots only; counts, not wall latency",
        "family_primary_difference": "paired case-seed differences within each family",
        "equal_family_primary_difference": "unweighted arithmetic mean of all 12 family differences",
    },
    "colors": COLORS,
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def strict_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f"nonfinite JSON value: {value}")

    value = json.loads(
        Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique, parse_constant=invalid
    )
    require(isinstance(value, dict), f"JSON artifact must contain an object: {Path(path).name}")
    return value


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def safe_path(root, relative):
    require(
        isinstance(relative, str) and relative and "\\" not in relative and ":" not in relative,
        "manifest path is not a canonical relative POSIX path",
    )
    part = PurePosixPath(relative)
    require(
        not part.is_absolute()
        and part.as_posix() == relative
        and not any(item in ("", ".", "..") for item in part.parts),
        "unsafe manifest path",
    )
    target = root.joinpath(*part.parts)
    require(target.resolve().is_relative_to(root), "manifest path escapes study root")
    return target


def count(value, label):
    require(type(value) is int and value >= 0, f"invalid nonnegative count: {label}")
    return value


def signed_count(value, label):
    require(type(value) is int, f"invalid integer: {label}")
    return value


def fraction_text(value):
    return "" if value is None else f"{value.numerator}/{value.denominator}"


def ratio(numerator, denominator):
    return Fraction(numerator, denominator) if denominator else None


def check_mean(recorded, exact, label):
    if exact is None:
        require(recorded is None, f"undefined mean must be null: {label}")
    else:
        require(
            type(recorded) in (int, float)
            and math.isfinite(recorded)
            and math.isclose(recorded, float(exact), rel_tol=1e-12, abs_tol=1e-12),
            f"mean disagrees with exact arithmetic: {label}",
        )


def same_summary(left, right, path="root"):
    """Compare audited structure/counts exactly and finite float means tolerantly.

    The runner uses sum while the independent auditor uses math.fsum. Their
    float means may differ in the last bit even after the audit has passed.
    Integer counts and booleans retain their exact types and values; they are
    never coerced into floating-point or interchanged with each other.
    """
    require(type(left) is type(right), f"summary type mismatch at {path}")
    if isinstance(left, dict):
        require(set(left) == set(right), f"summary keys mismatch at {path}")
        for key in left:
            same_summary(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, list):
        require(len(left) == len(right), f"summary length mismatch at {path}")
        for index, (a, b) in enumerate(zip(left, right)):
            same_summary(a, b, f"{path}[{index}]")
    elif type(left) is float:
        require(
            math.isfinite(left)
            and math.isfinite(right)
            and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12),
            f"summary numeric mismatch at {path}",
        )
    else:
        require(left == right, f"summary value mismatch at {path}")


def validate_group(row, planned):
    require(
        count(row.get("planned"), "group planned") == planned, "group planned denominator differs"
    )
    completed, failed = (
        count(row.get("completed"), "group completed"),
        count(row.get("failed"), "group failed"),
    )
    require(completed + failed == planned, "group completion accounting differs")
    require(
        set(row.get("metrics", {})) == set(ENDPOINTS),
        "summary endpoint set differs from declared source",
    )
    for name, metric in row["metrics"].items():
        total = count(metric.get("sum"), name + " sum")
        observed, unavailable = (
            count(metric.get("observed"), name + " observed"),
            count(metric.get("unavailable"), name + " unavailable"),
        )
        require(
            observed + unavailable == planned, f"endpoint denominator accounting differs: {name}"
        )
        require(
            observed == (planned if name == PRIMARY else completed),
            f"unexpected observed denominator: {name}",
        )
        if name in BINARY:
            require(total <= observed, f"binary endpoint sum exceeds denominator: {name}")
        if name == PRIMARY:
            require(total <= completed, "operational failures cannot count as safe recoveries")
        check_mean(metric.get("mean"), ratio(total, observed), name)
    metrics = row["metrics"]
    for prefix in ("state", "action_linked"):
        definite, abstain = (
            metrics[prefix + "_definite"]["sum"],
            metrics[prefix + "_abstention"]["sum"],
        )
        wrong, false_success = (
            metrics[prefix + "_wrong_definite"]["sum"],
            metrics[prefix + "_false_success"]["sum"],
        )
        require(
            definite + abstain == completed and false_success <= wrong <= definite,
            f"claim partition accounting differs: {prefix}",
        )
    require(
        metrics["safe_recovery"]["sum"] == metrics[PRIMARY]["sum"],
        "safe recovery numerator differs from operational endpoint",
    )


def validate_summary(summary, protocol, receipt, audit):
    """Check exact public-summary arithmetic without reading trial outcomes."""
    require(
        summary.get("schema") == protocol.get("schema") == STUDY_SCHEMA, "unsupported study schema"
    )
    require(set(protocol.get("methods", [])) == set(METHODS), "planned method set differs")
    schedule = protocol.get("schedule")
    require(isinstance(schedule, list) and schedule, "missing frozen schedule")
    slots, trial_ids = set(), set()
    grouped = {"methods": Counter(), "families": Counter(), "cases": Counter()}
    family_domains, family_pairs, case_pairs = defaultdict(set), defaultdict(set), defaultdict(set)
    case_families, pair_methods = {}, defaultdict(set)
    for slot in schedule:
        require(isinstance(slot, dict), "invalid schedule row")
        for key in ("trial_id", "case_id", "family_id", "domain", "method"):
            require(isinstance(slot.get(key), str) and slot[key], f"missing schedule {key}")
        seed = count(slot.get("seed"), "schedule seed")
        method, case, family = slot["method"], slot["case_id"], slot["family_id"]
        require(
            method in METHODS
            and slot["trial_id"] not in trial_ids
            and (case, seed, method) not in slots,
            "duplicate or unsupported scheduled slot",
        )
        slots.add((case, seed, method))
        trial_ids.add(slot["trial_id"])
        require(
            case_families.setdefault(case, family) == family, "case assigned to multiple families"
        )
        pair_methods[(case, seed)].add(method)
        grouped["methods"][(method,)] += 1
        grouped["families"][(family, method)] += 1
        grouped["cases"][(case, method)] += 1
        family_domains[family].add(slot["domain"])
        family_pairs[family].add((case, seed))
        case_pairs[case].add(seed)
    require(
        all(value == set(METHODS) for value in pair_methods.values()),
        "incomplete planned method blocks",
    )
    require(len(family_pairs) == 12, "publication design requires all 12 planned families")
    require(
        len(case_pairs) == protocol.get("case_count")
        and len(family_pairs) == protocol.get("family_count"),
        "protocol case/family counts differ from schedule",
    )
    seed_count = count(protocol.get("seed_count"), "seed count")
    require(
        seed_count and all(seeds == set(range(seed_count)) for seeds in case_pairs.values()),
        "case seed coverage differs from frozen schedule",
    )
    for key in ("planned_trials", "completed_trials", "failed_trials"):
        value = count(summary.get(key), key)
        require(value == receipt.get(key) == audit.get(key), f"summary/receipts disagree on {key}")
    require(
        summary["planned_trials"] == len(schedule)
        and summary["completed_trials"] + summary["failed_trials"] == len(schedule),
        "summary planned denominator differs from schedule",
    )
    indexed = {}
    for section, expected in grouped.items():
        rows = summary.get(section)
        require(isinstance(rows, list), f"summary missing {section}")
        seen = {}
        for row in rows:
            require(isinstance(row, dict), "summary group must be an object")
            key = (
                (row.get("method"),)
                if section == "methods"
                else (
                    row.get("family_id" if section == "families" else "case_id"),
                    row.get("method"),
                )
            )
            require(
                key in expected and key not in seen, f"unknown/duplicate {section} summary group"
            )
            validate_group(row, expected[key])
            seen[key] = row
        require(set(seen) == set(expected), f"summary does not cover all {section}")
        indexed[section] = seen
    for group_key, summary_key in (
        ("planned", "planned_trials"),
        ("completed", "completed_trials"),
        ("failed", "failed_trials"),
    ):
        require(
            sum(row[group_key] for row in indexed["methods"].values()) == summary[summary_key],
            "method totals do not reconcile to study summary",
        )
    for section in ("families", "cases"):
        for method in METHODS:
            members = [row for key, row in indexed[section].items() if key[-1] == method]
            overall = indexed["methods"][(method,)]
            for key in ("planned", "completed", "failed"):
                require(
                    sum(row[key] for row in members) == overall[key],
                    f"{section} count reconciliation differs",
                )
            for endpoint in ENDPOINTS:
                for key in ("sum", "observed", "unavailable"):
                    require(
                        sum(row["metrics"][endpoint][key] for row in members)
                        == overall["metrics"][endpoint][key],
                        f"{section} metric reconciliation differs",
                    )
    contrast_rows = summary.get("paired_contrasts")
    require(
        isinstance(contrast_rows, list) and len(contrast_rows) == len(CONTRASTS),
        "contrast coverage differs",
    )
    paired, planned_pairs = {}, len(pair_methods)
    for contrast in contrast_rows:
        identity = (contrast.get("left"), contrast.get("right"))
        require(
            identity in CONTRASTS and identity not in paired, "unexpected/duplicate paired contrast"
        )
        require(
            contrast.get("planned_pairs") == planned_pairs, "paired planned denominator differs"
        )
        require(set(contrast.get("metrics", {})) == set(ENDPOINTS), "paired endpoint set differs")
        for endpoint, metric in contrast["metrics"].items():
            n = count(metric.get("pairs"), "paired observations")
            require(
                n + count(metric.get("unavailable_pairs"), "unavailable pairs") == planned_pairs,
                "paired denominator accounting differs",
            )
            families, total, family_means, used = set(), 0, [], 0
            require(isinstance(metric.get("by_family"), list), "missing paired family rows")
            for row in metric["by_family"]:
                family = row.get("family_id")
                require(
                    family in family_pairs and family not in families,
                    "unknown/duplicate paired family",
                )
                families.add(family)
                n_family = count(row.get("pairs"), "family pairs")
                total_family = signed_count(row.get("sum_difference"), "family difference")
                require(
                    0 < n_family <= len(family_pairs[family]), "invalid paired family denominator"
                )
                if endpoint in BINARY:
                    require(
                        abs(total_family) <= n_family, "binary difference exceeds pair denominator"
                    )
                exact = Fraction(total_family, n_family)
                check_mean(row.get("mean_difference"), exact, "paired family mean")
                total += total_family
                used += n_family
                family_means.append(exact)
                if endpoint == PRIMARY:
                    left, right = (indexed["families"][(family, method)] for method in identity)
                    require(
                        n_family == len(family_pairs[family])
                        and total_family
                        == left["metrics"][PRIMARY]["sum"] - right["metrics"][PRIMARY]["sum"],
                        "primary paired difference does not reconcile to family totals",
                    )
            require(used == n, "family pair counts do not reconcile")
            check_mean(metric.get("mean_difference"), ratio(total, n), "paired mean")
            equal = sum(family_means, Fraction()) / len(family_means) if family_means else None
            check_mean(metric.get("equal_family_mean_difference"), equal, "equal-family mean")
            if endpoint == PRIMARY:
                require(
                    families == set(family_pairs) and n == planned_pairs,
                    "primary operational endpoint must retain every planned pair/family",
                )
        paired[identity] = contrast
    return {
        "groups": indexed,
        "contrasts": paired,
        "families": sorted(family_pairs),
        "domains": {family: sorted(family_domains[family]) for family in sorted(family_pairs)},
    }


def verify_inputs(study_dir, audit_dir):
    """The summary is not read until every retained study byte is verified."""
    root, audit_root = Path(study_dir).resolve(), Path(audit_dir).resolve()
    receipt, manifest = (
        strict_json(root / "completion-receipt.json"),
        strict_json(root / "manifest.json"),
    )
    require(
        receipt.get("complete") is True and manifest.get("complete") is True,
        "refusing incomplete collection",
    )
    require(
        sha(root / "manifest.json") == receipt.get("manifest_sha256"),
        "completion manifest hash mismatch",
    )
    files = manifest.get("files")
    require(isinstance(files, dict) and files, "study manifest has no artifact bindings")
    for relative, expected in files.items():
        require(
            isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
            "invalid artifact SHA-256",
        )
        path = safe_path(root, relative)
        require(
            path.is_file() and sha(path) == expected, f"retained artifact hash mismatch: {relative}"
        )
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    require(
        actual == set(files) | {"manifest.json", "completion-receipt.json"},
        "missing or unmanifested study artifacts",
    )
    require(
        {"protocol.json", "summary.json"} <= set(files),
        "required summary/protocol is not manifest bound",
    )
    protocol_sha = sha(root / "protocol.json")
    require(protocol_sha == receipt.get("protocol_sha256"), "completion protocol hash mismatch")
    audit = strict_json(audit_root / "audit-receipt.json")
    require(
        audit.get("schema") == AUDIT_SCHEMA and audit.get("passed") is True,
        "independent audit has not passed",
    )
    require(
        audit.get("protocol_sha256") == protocol_sha
        and audit.get("manifest_sha256") == receipt["manifest_sha256"]
        and audit.get("artifacts_hashed") == len(files),
        "audit is not bound to this completed study",
    )
    protocol = strict_json(root / "protocol.json")
    audit_binding = (
        protocol.get("source", {})
        .get("files", {})
        .get("scripts/audit_recovery_controller_study.py", {})
    )
    require(
        audit.get("audit_script_sha256") == audit_binding.get("sha256")
        and isinstance(audit.get("audit_script_sha256"), str),
        "audit source differs from frozen protocol",
    )
    summary = strict_json(root / "summary.json")
    require(summary.get("protocol_sha256") == protocol_sha, "summary protocol hash mismatch")
    recomputed = strict_json(audit_root / "recomputed-summary.json")
    same_summary(
        recomputed,
        {
            key: value
            for key, value in summary.items()
            if key not in ("protocol_sha256", "collection_seconds")
        },
    )
    validated = validate_summary(summary, protocol, receipt, audit)
    return {
        "study_root": root,
        "audit_root": audit_root,
        "receipt": receipt,
        "manifest": manifest,
        "protocol": protocol,
        "summary": summary,
        "audit": audit,
        "validated": validated,
        "protocol_sha256": protocol_sha,
        "manifest_sha256": receipt["manifest_sha256"],
    }


def metric_row(section, group, endpoint, metric):
    exact = ratio(metric["sum"], metric["observed"])
    return {
        "group": section,
        "method": group["method"],
        "family_id": group.get("family_id", ""),
        "case_id": group.get("case_id", ""),
        "endpoint": endpoint,
        "planned": group["planned"],
        "completed": group["completed"],
        "failed": group["failed"],
        "numerator": metric["sum"],
        "observed_denominator": metric["observed"],
        "unavailable": metric["unavailable"],
        "mean_exact": fraction_text(exact),
        "mean": float(exact) if exact is not None else None,
    }


def csv_file(path, rows, columns=None):
    require(rows or columns, "CSV requires rows or declared columns")
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def claim_rows(bundle):
    rows = []
    for method in METHODS:
        group = bundle["validated"]["groups"]["methods"][(method,)]
        metrics, planned = group["metrics"], group["planned"]
        categories = {
            "correct_definite": metrics["state_definite"]["sum"]
            - metrics["state_wrong_definite"]["sum"],
            "incorrect_definite": metrics["state_wrong_definite"]["sum"],
            "abstention": metrics["state_abstention"]["sum"],
            "unavailable": group["failed"],
        }
        require(
            sum(categories.values()) == planned,
            "global claim yields do not partition planned slots",
        )
        for name, numerator in categories.items():
            rows.append(
                {
                    "method": method,
                    "category": name,
                    "numerator": numerator,
                    "planned_denominator": planned,
                    "yield_exact": fraction_text(Fraction(numerator, planned)),
                    "yield": numerator / planned,
                    "failed": group["failed"],
                }
            )
    return rows


def export_tables(bundle, output):
    summary, validated = bundle["summary"], bundle["validated"]
    rows = [
        metric_row(section, group, endpoint, group["metrics"][endpoint])
        for section in ("methods", "families", "cases")
        for group in sorted(
            summary[section],
            key=lambda row: (
                row.get("family_id", row.get("case_id", "")),
                METHODS.index(row["method"]),
            ),
        )
        for endpoint in ENDPOINTS
    ]
    csv_file(output / "summary-metrics.csv", rows)
    write_json(
        output / "summary-metrics.json",
        {"schema": SCHEMA, "denominators": SPEC["denominators"], "rows": rows},
    )
    contrasts, families, heatmap = [], [], []
    for identity in CONTRASTS:
        contrast = validated["contrasts"][identity]
        for endpoint in ENDPOINTS:
            metric = contrast["metrics"][endpoint]
            by_family = sorted(metric["by_family"], key=lambda row: row["family_id"])
            total = sum(row["sum_difference"] for row in by_family)
            mean = ratio(total, metric["pairs"])
            equal = (
                sum(
                    (Fraction(row["sum_difference"], row["pairs"]) for row in by_family), Fraction()
                )
                / len(by_family)
                if by_family
                else None
            )
            contrasts.append(
                {
                    "left": identity[0],
                    "right": identity[1],
                    "endpoint": endpoint,
                    "planned_pairs": contrast["planned_pairs"],
                    "pairs": metric["pairs"],
                    "unavailable_pairs": metric["unavailable_pairs"],
                    "sum_difference": total,
                    "mean_difference_exact": fraction_text(mean),
                    "mean_difference": float(mean) if mean is not None else None,
                    "families_observed": len(by_family),
                    "families_planned": len(validated["families"]),
                    "equal_family_mean_difference_exact": fraction_text(equal),
                    "equal_family_mean_difference": float(equal) if equal is not None else None,
                }
            )
            for row in by_family:
                exact = Fraction(row["sum_difference"], row["pairs"])
                item = {
                    "left": identity[0],
                    "right": identity[1],
                    "endpoint": endpoint,
                    "family_id": row["family_id"],
                    "domains": ";".join(validated["domains"][row["family_id"]]),
                    "sum_difference": row["sum_difference"],
                    "pairs": row["pairs"],
                    "difference_exact": fraction_text(exact),
                    "mean_difference": float(exact),
                }
                families.append(item)
                if endpoint == PRIMARY:
                    heatmap.append(item)
    csv_file(output / "paired-contrasts.csv", contrasts)
    csv_file(output / "paired-family-contrasts.csv", families)
    csv_file(output / "family-safe-recovery-contrasts.csv", heatmap)
    csv_file(output / "state-claim-yields.csv", claim_rows(bundle))
    resources = []
    for method in METHODS:
        group = validated["groups"]["methods"][(method,)]
        for endpoint in ("reads", "dispatches", "waits", "decision_time_ms"):
            item = metric_row("methods", group, endpoint, group["metrics"][endpoint])
            item["unit"] = "logical_simulated_ms" if endpoint == "decision_time_ms" else "count"
            item["interpretation"] = (
                "logical decision time; not wall latency"
                if endpoint == "decision_time_ms"
                else "charged controller resource count"
            )
            resources.append(item)
    csv_file(output / "resources-and-logical-decision-time.csv", resources)
    write_json(
        output / "paired-contrasts.json",
        {"schema": SCHEMA, "contrasts": contrasts, "families": families},
    )
    write_json(output / "figure-specification.json", SPEC)
    export_tex(bundle, output)


def tex_escape(value):
    return "".join(
        {
            "\\": r"\textbackslash{}",
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }.get(char, char)
        for char in value
    )


def export_tex(bundle, output):
    lines = [
        "% Generated only after completion and independent audit. No inference intervals.",
        "% Operational denominator: planned. Semantic denominator: observed.",
        "% Every fraction below is its original numerator/denominator, not a rounded percentage.",
        r"\begin{tabular}{lrrrr}",
        r"Method & Operational safe & Fixed SLA & Recovery & Failed \\",
        r"\hline",
    ]
    claim_lines = [
        r"\begin{tabular}{lrrrr}",
        r"Method & Correct definite & Incorrect definite & Abstain & False success \\",
        r"\hline",
    ]
    for method in METHODS:
        group = bundle["validated"]["groups"]["methods"][(method,)]
        metrics = group["metrics"]
        rates = [
            (
                f"{metrics[name]['sum']}/{metrics[name]['observed']}"
                if metrics[name]["observed"]
                else r"\textemdash"
            )
            for name in (PRIMARY, "original_completion", "recovery_completion")
        ]
        lines.append(
            tex_escape(NAMES[method])
            + " & "
            + " & ".join(rates + [f"{group['failed']}/{group['planned']}"])
            + r" \\"
        )
        counts = [
            metrics["state_definite"]["sum"] - metrics["state_wrong_definite"]["sum"],
            metrics["state_wrong_definite"]["sum"],
            metrics["state_abstention"]["sum"],
        ]
        values = [f"{value}/{group['planned']}" for value in counts]
        fs = metrics["state_false_success"]
        values.append(f"{fs['sum']}/{fs['observed']}" if fs["observed"] else r"\textemdash")
        claim_lines.append(tex_escape(NAMES[method]) + " & " + " & ".join(values) + r" \\")
    lines += (
        [
            r"\end{tabular}",
            "",
            "% Yields use all planned slots; failures are unavailable, not abstentions.",
        ]
        + claim_lines
        + [r"\end{tabular}", ""]
    )
    (output / "recovery-exact-values.tex").write_text("\n".join(lines), encoding="utf-8")


def rate_label(metric, *, planned=None):
    denominator = metric["observed"] if planned is None else planned
    unavailable = metric["unavailable"]
    return (f"{metric['sum']}/{denominator}" if denominator else "undef.; N=0") + (
        f" [U={unavailable}]" if unavailable else ""
    )


def render_figures(bundle, output):
    # Optional presentation dependency is imported only after every input guard.
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    import numpy as np

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "axes.titlesize": 11.5,
            "axes.labelsize": 10.5,
            "xtick.labelsize": 10.5,
            "ytick.labelsize": 10.5,
            "legend.fontsize": 10.5,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "savefig.dpi": SPEC["png_dpi"],
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    groups = bundle["validated"]["groups"]["methods"]
    fig, axes = plt.subplots(2, 2, figsize=SPEC["summary_figure_inches"])
    fig.subplots_adjust(left=0.185, right=0.985, top=0.82, bottom=0.21, hspace=0.51, wspace=0.15)
    fig.suptitle(
        "Finite-suite recovery and global-state reports", x=0.03, y=0.982, ha="left", fontsize=14
    )
    fig.text(
        0.03,
        0.944,
        "Audited full-ledger outcomes and report correctness · exact counts · all five frozen methods",
        fontsize=10.5,
    )
    y = np.arange(len(METHODS))
    labels = [
        NAMES[method] + f"\nfailed {groups[(method,)]['failed']}/{groups[(method,)]['planned']}"
        for method in METHODS
    ]

    def grouped(ax, series, title, *, resource=False, show_names=True):
        n = len(series)
        offsets = (np.arange(n) - (n - 1) / 2) * 0.205
        for offset, (legend, color, provider) in zip(offsets, series):
            values, texts = [], []
            for method in METHODS:
                value, text = provider(groups[(method,)])
                values.append(value if value is not None else 0)
                texts.append(text)
            ax.barh(y + offset, values, height=0.175, color=color, label=legend)
            for yi, text in zip(y + offset, texts):
                ax.text(
                    4.13 if resource else 1.035, yi, text, va="center", ha="left", fontsize=10.5
                )
        ax.set_yticks(y, labels if show_names else [""] * len(METHODS))
        ax.set_ylim(4.60, -0.80)
        ax.set_xlim(0, 7.4 if resource else 1.85)
        ax.set_xticks(
            SPEC["resource_ticks"] if resource else SPEC["rate_ticks"],
            [str(v) for v in SPEC["resource_ticks"]] if resource else ["0%", "50%", "100%"],
        )
        ax.set_xlabel(
            "Mean charged count (observed slots)" if resource else "Fraction of denominator"
        )
        ax.set_title(title, loc="left", pad=52)
        ax.legend(
            loc="lower left",
            bbox_to_anchor=(-0.01, 1.005),
            borderaxespad=0,
            frameon=False,
            ncol=1,
            handlelength=1.2,
            labelspacing=0.18,
        )
        ax.grid(axis="x", alpha=0.18)
        ax.set_axisbelow(True)
        ax.text(
            4.13 if resource else 1.035,
            -0.64,
            "exact sum / N" if resource else "exact n / N",
            fontsize=10.5,
        )
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)

    def endpoint(name):
        def provide(group):
            metric = group["metrics"][name]
            value = ratio(metric["sum"], metric["observed"])
            return (float(value) if value is not None else None, rate_label(metric))

        return provide

    grouped(
        axes[0, 0],
        [
            ("Operational safe (planned)", COLORS["safe"], endpoint(PRIMARY)),
            ("Original fixed SLA (observed)", COLORS["original"], endpoint("original_completion")),
            ("Recovery (observed)", COLORS["recovery"], endpoint("recovery_completion")),
        ],
        "A  Recovery outcomes",
    )
    grouped(
        axes[0, 1],
        [
            ("Own duplicate event", COLORS["duplicate"], endpoint("duplicate_event")),
            ("Own unwanted event", COLORS["unwanted"], endpoint("unwanted_event")),
        ],
        "B  Safety events (observed)",
        show_names=False,
    )

    def yield_endpoint(category):
        def provide(group):
            metrics, n = group["metrics"], group["planned"]
            total = (
                {
                    "correct": metrics["state_definite"]["sum"]
                    - metrics["state_wrong_definite"]["sum"],
                    "incorrect": metrics["state_wrong_definite"]["sum"],
                    "abstain": metrics["state_abstention"]["sum"],
                }
            )[category]
            return total / n, f"{total}/{n}" + (
                f" [U={group['failed']}]" if group["failed"] else ""
            )

        return provide

    grouped(
        axes[1, 0],
        [
            ("Correct definite", COLORS["correct"], yield_endpoint("correct")),
            ("Incorrect definite", COLORS["incorrect"], yield_endpoint("incorrect")),
            ("Explicit abstention", COLORS["abstain"], yield_endpoint("abstain")),
        ],
        "C  Global-state claim yields (planned)",
    )
    grouped(
        axes[1, 1],
        [
            ("Readbacks", COLORS["reads"], endpoint("reads")),
            ("Dispatches", COLORS["dispatches"], endpoint("dispatches")),
        ],
        "D  Mean resources",
        resource=True,
        show_names=False,
    )
    fs = []
    for method in METHODS:
        metric = groups[(method,)]["metrics"]["state_false_success"]
        value = f"{metric['sum']}/{metric['observed']}" if metric["observed"] else "undefined (N=0)"
        fs.append(f"{SHORT[method]} {value}")
    footer = [
        "N is the displayed denominator; [U=n] marks unavailable semantic/resource slots (omitted when zero).",
        "Operational safe uses every planned slot; failed execution counts as false. Original SLA stays fixed.",
        "Claim yields use planned slots: correct + incorrect + abstention + unavailable = all planned.",
        "Global-state false-success counts / observed: " + "; ".join(fs[:3]) + ";",
        "    " + "; ".join(fs[3:]) + ". False success is a subset of incorrect definite claims.",
        "Resources are charged counts. Logical decision time is exported separately; it is not wall latency.",
    ]
    for index, line in enumerate(footer):
        fig.text(0.03, 0.155 - index * 0.023, line, fontsize=10.5, ha="left", va="top")
    save_figure(fig, output / "recovery-method-overview")
    plt.close(fig)

    families, contrast_map = bundle["validated"]["families"], bundle["validated"]["contrasts"]
    matrix, equal = [], []
    lookup = {}
    for identity in CONTRASTS:
        rows = contrast_map[identity]["metrics"][PRIMARY]["by_family"]
        lookup[identity] = {
            row["family_id"]: Fraction(row["sum_difference"], row["pairs"]) for row in rows
        }
        equal.append(sum(lookup[identity].values(), Fraction()) / len(families))
    for family in families:
        matrix.append([float(lookup[identity][family]) for identity in CONTRASTS])
    fig, ax = plt.subplots(figsize=SPEC["heatmap_figure_inches"])
    fig.subplots_adjust(left=0.42, right=0.88, bottom=0.20, top=0.84)
    im = ax.imshow(
        matrix,
        cmap=SPEC["heatmap_colormap"],
        norm=TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1),
        aspect="auto",
    )
    family_labels = [
        family + "\n" + ", ".join(bundle["validated"]["domains"][family]) for family in families
    ]
    ax.set_yticks(range(len(families)), family_labels)
    ax.set_xticks(range(len(CONTRASTS)), ["Poll minus\n" + SHORT[right] for _, right in CONTRASTS])
    ax.tick_params(axis="both", length=0, pad=8)
    ax.set_xticks(np.arange(-0.5, len(CONTRASTS), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(families), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1)
    ax.tick_params(which="minor", length=0)
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            ax.text(
                j,
                i,
                f"{value:+.3f}",
                ha="center",
                va="center",
                fontsize=10.5,
                color="white" if abs(value) >= 0.6 else "#171717",
            )
    colorbar = fig.colorbar(im, ax=ax, fraction=0.055, pad=0.035, ticks=[-1, -0.5, 0, 0.5, 1])
    colorbar.set_label("Paired operational-safe rate difference", fontsize=10.5)
    fig.suptitle(
        "Operational safe recovery across every planned family",
        x=0.03,
        y=0.98,
        ha="left",
        fontsize=14,
    )
    fig.text(
        0.03,
        0.935,
        "ConseqaX poll minus comparator · fixed scale [−1, +1] · positive favors polling",
        fontsize=10.5,
    )
    fig.text(
        0.03,
        0.14,
        "All 12 family IDs are sorted literally; domain labels come only from the frozen schedule.",
        fontsize=10.5,
    )
    fig.text(
        0.03,
        0.112,
        "Cells are paired case-seed means. Exact sum-difference / pairs and domains are in the companion CSV.",
        fontsize=10.5,
    )
    fig.text(
        0.03,
        0.084,
        "Equal-family means (all 12): "
        + "; ".join(
            f"vs {SHORT[right]} {float(value):+.4f}" for (_, right), value in zip(CONTRASTS, equal)
        ),
        fontsize=10.5,
    )
    fig.text(
        0.03,
        0.056,
        "Every planned primary pair is retained; operational failures count as false. No population inference.",
        fontsize=10.5,
    )
    save_figure(fig, output / "recovery-family-primary-contrasts")
    plt.close(fig)


def save_figure(fig, stem):
    # Fixed canvas dimensions and adequate margins are intentional; no automatic
    # tight-crop changes the publication scale across the two fixed figures.
    for extension in ("pdf", "svg", "png"):
        fig.savefig(stem.with_suffix("." + extension), dpi=SPEC["png_dpi"], facecolor="white")


def publish(bundle, output):
    output = Path(output).resolve()
    require(not output.exists(), "output must be a fresh directory")
    require(
        not output.is_relative_to(bundle["study_root"])
        and not output.is_relative_to(bundle["audit_root"]),
        "export output must be separate from retained study and audit",
    )
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "source-inputs"
    inputs.mkdir()
    copies = [
        (bundle["study_root"] / "summary.json", "summary.source.json"),
        (bundle["study_root"] / "protocol.json", "protocol.source.json"),
        (bundle["study_root"] / "manifest.json", "manifest.source.json"),
        (bundle["study_root"] / "completion-receipt.json", "completion-receipt.source.json"),
        (bundle["audit_root"] / "audit-receipt.json", "audit-receipt.source.json"),
        (bundle["audit_root"] / "recomputed-summary.json", "recomputed-summary.source.json"),
        (Path(__file__).resolve(), "plotting-code.source.py"),
    ]
    for source, name in copies:
        shutil.copyfile(source, inputs / name)
    export_tables(bundle, output)
    render_figures(bundle, output)
    (output / "README.md").write_text(
        "# Audited recovery study publication exports\n\n"
        "The figures show every frozen method and every planned family; all choices are declared in figure-specification.json. "
        "These are exact finite-suite descriptions, with no confidence intervals or task-population inference.\n\n"
        "The primary operational-safe endpoint uses all planned slots and assigns false to operational failures. "
        "Original-SLA, recovery, safety-event, and resource summaries use their displayed observed denominators; unavailable values are explicit. "
        "Global-state claim yields use planned denominators, leaving failed slots unavailable rather than labeling them abstentions. "
        "Correct definite yield equals definite minus wrong definite; false success is a subset of wrong definite. "
        "Report correctness here is judged against audited full-ledger truth; it does not establish contemporaneous evidence support or completed human review. "
        "The family heatmap uses paired primary differences within each family and reports the equal-family mean across all 12 families.\n\n"
        "CSV files retain original numerators/denominators and reduced exact rational means. "
        "Resources and logical simulated decision time are in resources-and-logical-decision-time.csv. "
        "Logical decision time is not measured wall latency; the collection duration in the copied summary is not an endpoint. "
        "Missing/zero denominators are undefined rather than zero.\n\n"
        "Source JSON files have .source.json names so artifact snapshot tools do not reinterpret nested study receipts/manifests. "
        "The output manifest binds every rendered figure, table, copied input, and the plotting source. "
        "A complete output manifest confirms export completion, not independent visual review of the figures.\n",
        encoding="utf-8",
    )
    files = {
        path.relative_to(output).as_posix(): sha(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "schema": SCHEMA,
        "complete": True,
        "protocol_sha256": bundle["protocol_sha256"],
        "study_manifest_sha256": bundle["manifest_sha256"],
        "audit_receipt_sha256": sha(bundle["audit_root"] / "audit-receipt.json"),
        "plotting_code_sha256": sha(__file__),
        "files": files,
        "verification": "every retained study artifact hashed; passed bound audit; exact public-summary arithmetic checked",
    }
    write_json(output / "manifest.json", manifest)
    return {
        "complete": True,
        "schema": SCHEMA,
        "output": str(output),
        "artifacts": len(files),
        "manifest_sha256": sha(output / "manifest.json"),
        "protocol_sha256": bundle["protocol_sha256"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", required=True, type=Path)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="verify completed inputs and exact arithmetic; write nothing",
    )
    args = parser.parse_args(argv)
    try:
        bundle = verify_inputs(args.study_dir, args.audit_dir)
        if args.verify_only:
            result = {
                "verified": True,
                "protocol_sha256": bundle["protocol_sha256"],
                "planned_trials": bundle["summary"]["planned_trials"],
                "output_written": False,
            }
        else:
            result = publish(bundle, args.output)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        parser.exit(2, f"Export refused: {error}\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
