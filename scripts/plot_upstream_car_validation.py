"""Postcollection CAR/CX calibration figure; no collection code is imported.

This script refuses an incomplete study, verifies its terminal inventory and
every bound input byte, then plots a declared presentation coefficient. All
three coefficients remain in the exported CSV/JSON. It performs no simulation,
model call, point-parity test, timing comparison or inferential interval fit.

Run --verify-only without creating graphics. Actual rendering creates exactly
one vector PDF, one SVG and one PNG in a new output directory; the caller owns
the required PDF artifact-start marker and final visual inspection.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import shutil


SCHEMA = "upstream-car-refund-comparison-v1"
UPSTREAM_REVISION = "db90fa28b97164c35e7c524e4597b8cbdb3035af"
ENGINES = ("upstream_car", "consequa_x")
METHODS = ("contrastive", "shapley")
VARIANTS = {
    "contrastive": (
        ("upstream_bootstrap", "CAR bootstrap", "#306a91", "o"),
        ("cx_bootstrap", "CX bootstrap", "#98689c", "s"),
        ("cx_clopper_pearson", "CX Clopper-Pearson", "#197c60", "^"),
    ),
    "shapley": (
        ("upstream_normal", "CAR normal", "#306a91", "o"),
        ("cx_normal", "CX normal", "#98689c", "s"),
        ("cx_hoeffding", "CX Hoeffding", "#197c60", "^"),
    ),
}
MECHANISMS = (
    ("refund-p50-q50", "(p,q)=(.5,.5)"),
    ("refund-p20-q80", "(.2,.8)"),
    ("refund-p80-q20", "(.8,.2)"),
    ("refund-p100-q100", "(1,1)"),
    ("idempotent-p50-q50", "Idempotent (.5,.5)"),
    ("unknown-provenance-p50-q50", "Missing provenance"),
    ("lagged-readback-p50-q50", "Lagged readback"),
    ("budget-p50-q50", "Four-call budget"),
)
POSITION_NAMES = {0: "Selection", 1: "Timeout-retry", 2: "Terminal-stop"}


def file_hash(path):
    result = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def reject_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique_object, parse_constant=reject_constant)


def safe_member(root, name):
    """Manifest names must be relative, canonical POSIX paths inside the study."""
    if not isinstance(name, str) or "\\" in name:
        raise ValueError("Noncanonical manifest path")
    pure = PurePosixPath(name)
    if (pure.is_absolute() or not pure.parts or ":" in name
            or any(part in (".", "..") for part in pure.parts)
            or pure.as_posix() != name):
        raise ValueError("Manifest path escapes its study")
    candidate = root.joinpath(*pure.parts)
    for parent in (candidate, *candidate.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("Symlink input is refused")
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("Manifest path escapes its study")
    return candidate


def integer(value, label, maximum=None):
    if type(value) is not int or value < 0 or maximum is not None and value > maximum:
        raise ValueError(f"Invalid count: {label}")
    return value


def finite(value, label, *, nonnegative=False, allow_none=False):
    if allow_none and value is None:
        return value
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"Invalid finite number: {label}")
    if nonnegative and value < 0:
        raise ValueError(f"Negative number: {label}")
    return value


def same_fraction(actual, numerator, denominator, label):
    expected = numerator / denominator if denominator else None
    if actual is None and expected is None:
        return
    if actual is None or expected is None or not math.isclose(actual, expected, abs_tol=1e-12):
        raise ValueError(f"Inconsistent saved fraction: {label}")


def validate_summary(summary, protocol):
    """Validate units and undefined metrics without recomputing any experiment."""
    if summary.get("schema") != SCHEMA or not isinstance(summary.get("rows"), list):
        raise ValueError("Unexpected CAR summary schema")
    repeats = protocol["plan"]["repeats"]
    rows, seen = [], set()
    expected_keys = {(mechanism, method, variant, position)
                     for mechanism, _ in MECHANISMS for method in METHODS
                     for variant, *_ in VARIANTS[method] for position in range(3)}
    for saved in summary["rows"]:
        key = (saved.get("mechanism"), saved.get("method"), saved.get("variant"), saved.get("position"))
        if key not in expected_keys or key in seen:
            raise ValueError("Missing, duplicated or unknown coefficient cell")
        seen.add(key)
        mechanism, method, variant, position = key
        planned = integer(saved["planned"], "planned")
        available = integer(saved["available"], "available", planned)
        scored = integer(saved["scored"], "scored", available)
        if planned != repeats:
            raise ValueError("A coefficient denominator differs from the frozen repeat count")
        truth = protocol["references"][mechanism][method]
        expected_truth = None if truth is None else truth[position]
        reference = finite(saved["reference"], "reference", allow_none=True)
        if reference != expected_truth:
            raise ValueError("Summary reference differs from the frozen exact reference")
        if reference is None:
            if scored != 0 or saved["covered"] is not None:
                raise ValueError("Undefined reference cannot acquire a coverage score")
        else:
            if scored != available:
                raise ValueError("Known reference must retain every available estimate")
            integer(saved["covered"], "covered", scored)
        covered = saved["covered"]
        if covered is None:
            if saved["coverage_available"] is not None or saved["coverage_planned"] is not None:
                raise ValueError("Undefined coverage cannot become zero")
        else:
            same_fraction(saved["coverage_available"], covered, scored, "coverage_available")
            same_fraction(saved["coverage_planned"], covered, planned, "coverage_planned")
        mean_width = finite(saved["mean_width"], "mean_width", nonnegative=True, allow_none=True)
        if (available == 0) != (mean_width is None):
            raise ValueError("No-interval width must remain undefined")
        integer(saved["zero_width"], "zero_width", available)
        integer(saved["nonzero_flags"], "nonzero_flags", available)
        status = ("unknown_reference" if reference is None else
                  "no_numeric_estimate" if scored == 0 else "numeric")
        rows.append({
            "mechanism": mechanism, "method": method, "variant": variant,
            "position": position, "coefficient": POSITION_NAMES[position],
            "planned": planned, "available": available,
            "availability_numerator": available, "availability_denominator": planned,
            "availability": available / planned,
            "reference": reference, "scored": scored, "covered": covered,
            "coverage_numerator": covered, "coverage_denominator": scored if reference is not None else None,
            "coverage_available": saved["coverage_available"],
            "covered_per_planned_numerator": covered,
            "covered_per_planned_denominator": planned if reference is not None else None,
            "covered_per_planned": saved["coverage_planned"],
            "mean_width": mean_width, "zero_width": saved["zero_width"],
            "nonzero_flags": saved["nonzero_flags"], "display_status": status,
            "width_display_status": status,
            "coverage_fraction": f"{covered}/{scored}" if status == "numeric" else None,
            "availability_fraction": f"{available}/{planned}",
        })
    if seen != expected_keys:
        raise ValueError("Summary does not retain all coefficients, mechanisms and interval variants")
    return rows


def load_terminal_study(study_directory):
    """No plotting or output writes occur before terminal/hash validation passes."""
    root = Path(study_directory).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file() or (root / "incomplete-receipt.json").exists():
        raise ValueError("Terminal complete manifest is required; provisional results cannot be plotted")
    manifest = load_json(manifest_path)
    if (manifest.get("schema") != SCHEMA or manifest.get("complete") is not True
            or not isinstance(manifest.get("files"), dict)):
        raise ValueError("Terminal complete manifest is required")
    if any((root / name).exists() for name in ("runner.lock", "collection.lock")):
        raise ValueError("An active collection lock is present")
    files = manifest["files"]
    for name in ("protocol.json", "summary.json", "disposition.json", "paired-validation.json", "upstream-provenance.json"):
        if name not in files:
            raise ValueError("A required terminal artifact is absent from the manifest")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != set(files) | {"manifest.json"}:
        raise ValueError("Terminal inventory differs from the actual retained files")
    for name, expected in files.items():
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("Invalid manifest SHA-256 value")
        path = safe_member(root, name)
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError(f"Changed or missing manifest member: {name}")
    protocol = load_json(root / "protocol.json")
    if (protocol.get("schema") != SCHEMA
            or protocol.get("upstream", {}).get("revision") != UPSTREAM_REVISION
            or protocol.get("engines") != list(ENGINES)):
        raise ValueError("Unexpected frozen source or engine design")
    plan = protocol.get("plan", {})
    if (plan.get("repeats") != 64 or plan.get("samples") != 32
            or plan.get("pairs") != 32 or plan.get("endpoint_samples") != 16
            or plan.get("confidence") != .95
            or plan.get("mechanisms") != [name for name, _ in MECHANISMS]):
        raise ValueError("This presentation expects the complete declared 64-repeat design")
    trials = protocol.get("trials")
    if not isinstance(trials, list) or len(trials) != 1024:
        raise ValueError("Frozen schedule must retain all 1,024 paired groups")
    expected_groups = Counter((m, method) for m, _ in MECHANISMS for method in METHODS
                              for _ in range(plan["repeats"]))
    if Counter((trial["mechanism"], trial["method"]) for trial in trials) != expected_groups:
        raise ValueError("Incomplete group schedule")
    if [trial.get("group_index") for trial in trials] != list(range(1024)):
        raise ValueError("Group indexes must be complete and ordered")
    expected_trials = {f"trials/{trial['group_index']:05d}-{engine}.json.gz"
                       for trial in trials for engine in ENGINES}
    listed_trials = {name for name in files if name.startswith("trials/")}
    if (expected_trials != listed_trials or manifest.get("trial_files") != 2048
            or manifest.get("planned_trial_files") != 2048):
        raise ValueError("All 2,048 engine-trial files must be bound by the complete manifest")
    disposition = load_json(root / "disposition.json")
    groups = disposition.get("groups")
    if (disposition.get("schema") != SCHEMA or not isinstance(groups, list)
            or len(groups) != len(trials) or disposition.get("redraws") != 0):
        raise ValueError("Missing or inconsistent complete disposition record")
    for group, trial in zip(groups, trials, strict=True):
        if group.get("status") != "completed" or group.get("trial") != trial:
            raise ValueError("Every planned group must have a matching completed disposition")
    if disposition.get("counts") != {"completed": 1024}:
        raise ValueError("Disposition counts do not establish terminal completeness")
    summary = load_json(root / "summary.json")
    rows = validate_summary(summary, protocol)
    return {"root": root, "manifest": manifest, "protocol": protocol,
            "rows": rows, "verified_files": len(files),
            "manifest_sha256": file_hash(manifest_path)}


def availability_text(rows):
    values = [row["availability_fraction"] for row in rows]
    return "A=" + (values[0] + " each" if len(set(values)) == 1 else " | ".join(values))


def coverage_strip(rows):
    if all(row["display_status"] == "unknown_reference" for row in rows):
        return "N/A: unknown reference"
    if all(row["display_status"] == "no_numeric_estimate" for row in rows):
        return "N/A: no numeric interval"
    return " | ".join(row["coverage_fraction"] or "N/A" for row in rows)


def build(study_directory, output, *, position=1, stem="upstream-car-intervals"):
    if position not in POSITION_NAMES:
        raise ValueError("Select a declared coefficient position 0, 1 or 2")
    if not stem or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in stem):
        raise ValueError("Use a lowercase filename stem")
    closed = load_terminal_study(study_directory)
    out = Path(output).resolve()
    if out.exists():
        raise ValueError("Use a new output directory; generated artifacts are not overwritten")
    if out.is_relative_to(closed["root"]):
        raise ValueError("Keep postcollection figures outside the sealed study directory")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    out.mkdir(parents=True)
    (out / "source-inputs").mkdir()
    for name in ("protocol.json", "summary.json", "manifest.json", "disposition.json"):
        copied_name = "study-manifest.source.json" if name == "manifest.json" else name
        shutil.copyfile(closed["root"] / name, out / "source-inputs" / copied_name)
        expected = (closed["manifest_sha256"] if name == "manifest.json"
                    else closed["manifest"]["files"][name])
        if file_hash(out / "source-inputs" / copied_name) != expected:
            raise ValueError("A terminal input changed between verification and snapshot copying")
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.titlesize": 12, "axes.labelsize": 11, "xtick.labelsize": 10.5,
        "ytick.labelsize": 10.5, "legend.fontsize": 10.5,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.spines.top": False, "axes.spines.right": False,
        "svg.hashsalt": "consequa-upstream-car-postcollection",
    })
    rows = closed["rows"]
    indexed = {(r["mechanism"], r["method"], r["variant"], r["position"]): r for r in rows}
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 10.2))
    fig.subplots_adjust(left=.31, right=.98, top=.855, bottom=.16, hspace=.47, wspace=.25)
    fig.suptitle("Native CAR / Consequa-X 1.1.0 interval calibration", fontsize=15, y=.985)
    fig.text(.5, .948, f"{POSITION_NAMES[position]} coefficient (position {position}); 64 simulated repeats per fixed mechanism",
             ha="center", fontsize=11, color="#334155")
    for method_index, method in enumerate(METHODS):
        coverage_ax, width_ax = axes[method_index]
        variants = VARIANTS[method]
        selected = [indexed[m, method, variant, position]
                    for m, _ in MECHANISMS for variant, *_ in variants]
        widths = [r["mean_width"] for r in selected if r["display_status"] == "numeric"]
        max_width = max(widths, default=1)
        width_limit = max(.1, max_width * 1.12)
        labels = []
        for mechanism_index, (mechanism, label) in enumerate(MECHANISMS):
            y = len(MECHANISMS) - 1 - mechanism_index
            group = [indexed[mechanism, method, variant, position] for variant, *_ in variants]
            labels.append(label + "  " + availability_text(group) + "\n" + coverage_strip(group))
            if mechanism_index % 2 == 0:
                for ax in (coverage_ax, width_ax):
                    ax.axhspan(y - .49, y + .49, color="#f1f5f9", zorder=0)
            for variant_index, ((_, _, color, marker), row) in enumerate(zip(variants, group, strict=True)):
                offset_y = y + (.24, 0, -.24)[variant_index]
                if row["display_status"] == "numeric":
                    coverage_ax.scatter(100 * row["coverage_available"], offset_y,
                                        marker=marker, color=color, s=35, zorder=3)
                    width_ax.scatter(row["mean_width"], offset_y,
                                     marker=marker, color=color, s=35, zorder=3)
            if all(row["display_status"] != "numeric" for row in group):
                coverage_ax.text(50, y, "N/A", ha="center", va="center", fontsize=11, color="#64748b")
                width_ax.text(width_limit / 2, y, "N/A", ha="center", va="center", fontsize=11, color="#64748b")
        coverage_ax.axvline(95, color="#64748b", linestyle="--", linewidth=.8, zorder=1)
        coverage_ax.set(xlim=(-3, 105), xticks=(0, 25, 50, 75, 100),
                        title=f"({'ac'[method_index]}) {method.capitalize()}: coverage",
                        xlabel="Empirical interval coverage (%)")
        width_ax.set(xlim=(-.03 * width_limit, width_limit),
                     title=f"({'bd'[method_index]}) {method.capitalize()}: width",
                     xlabel="Mean interval width (effect units)")
        for ax in (coverage_ax, width_ax):
            ax.set_ylim(-.55, len(MECHANISMS) - .45)
            ax.set_yticks(list(range(len(MECHANISMS) - 1, -1, -1)))
            ax.grid(axis="x", color="#dbe3ec", linewidth=.6)
            ax.spines["left"].set_visible(False)
            ax.tick_params(axis="y", length=0)
        coverage_ax.set_yticklabels(labels, linespacing=1.0)
        width_ax.set_yticklabels([])
        handles = [Line2D([], [], color=color, marker=marker, linestyle="none", label=label, markersize=6)
                   for _, label, color, marker in variants]
        fig.legend(handles=handles, ncol=3, frameon=False, loc="center",
                   bbox_to_anchor=(.60, .901 if method_index == 0 else .497),
                   handletextpad=.35, columnspacing=1.1)
    fig.text(.02, .024,
             "Fraction strips are ordered CAR / CX original / CX conservative; A is primary availability /64.\n"
             "Coverage uses scored numeric intervals; unavailable draws never count as covered. Dashed line: nominal 95%.\n"
             "Unknown-reference and budget-refusal cells remain N/A. Fixed-mechanism descriptive calibration;\n"
             "no pooled task-population inference, method-superiority claim or timing speed ranking.",
             fontsize=10.5, linespacing=1.25, color="#334155")
    for suffix in ("pdf", "svg", "png"):
        options = {"dpi": 220} if suffix == "png" else {}
        fig.savefig(out / f"{stem}.{suffix}", **options)
    plt.close(fig)
    (out / "fractions.json").write_bytes((json.dumps(rows, indent=2, allow_nan=False) + "\n").encode())
    with (out / "fractions.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    readme = (
        "# Postcollection native CAR / Consequa-X interval presentation\n\n"
        f"Selected figure coefficient: {POSITION_NAMES[position]} (position {position}). "
        "Selection is an explicit postcollection presentation choice; all three coefficients "
        "and all 144 mechanism/method/interval-variant/position rows are retained in fractions.csv/json.\n\n"
        "The terminal complete manifest, all bound study files, every planned trial filename and "
        "all completed dispositions were checked before graphics were created. No provisional "
        "or incomplete result can be plotted. Plotting does not recompute experiments or infer "
        "point parity; any such claim requires the separate final scientific audit.\n\n"
        "Coverage is covered/scored numeric intervals. Primary availability is available/64; "
        "covered/planned is separately retained in data. With no numeric interval, coverage is "
        "undefined; a zero covered/planned yield is not interpreted as observed noncoverage. "
        "Unknown population references remain unscored. Width panels show reference-eligible "
        "numeric intervals only. Refusals are not deleted or coerced to numeric zero.\n\n"
        "The figure is 9.5 inches wide with annotation/legend/tick fonts at least 10.5 pt, "
        "approximately 7.9 pt at IEEE full width 7.16 inches. Inspect the produced PDF/PNG "
        "at print scale before manuscript inclusion. The caller must record the PDF artifact "
        "operation before actual rendering. This script creates exactly one PDF.\n\n"
        "These are 64 simulated repeats within each fixed mechanism, not independent task "
        "samples. Bootstrap/normal originals and conservative intervals are distinct variants. "
        "No pooled population inference, estimator superiority or intrinsic speedup is claimed.\n"
    )
    (out / "README.md").write_bytes(readme.encode())
    manifest = {
        "schema": "consequa-upstream-car-figure-v1", "postcollection_presentation": True,
        "script_sha256": file_hash(__file__), "matplotlib": matplotlib.__version__,
        "source_study": str(closed["root"]), "source_manifest_sha256": closed["manifest_sha256"],
        "source_input_hashes": {name: file_hash(out / "source-inputs" / name)
                                for name in ("protocol.json", "summary.json", "study-manifest.source.json", "disposition.json")},
        "terminal_bound_files_verified": closed["verified_files"],
        "source_revision": closed["protocol"]["source_revision"],
        "upstream_revision": UPSTREAM_REVISION,
        "nominal_confidence": .95, "repeats_per_fixed_mechanism": 64,
        "selected_figure_position": position, "all_positions_retained": [0, 1, 2],
        "fraction_rows": len(rows), "figure_count": 1,
        "print_width_inches": 7.16, "design_width_inches": 9.5,
        "minimum_design_font_pt": 10.5, "minimum_print_font_pt": 10.5 * 7.16 / 9.5,
        "model_calls": 0, "simulation_trials": 0, "point_parity_claimed": False,
        "files": {p.relative_to(out).as_posix(): file_hash(p) for p in sorted(out.rglob("*")) if p.is_file()},
    }
    (out / "manifest.json").write_bytes((json.dumps(manifest, indent=2, allow_nan=False) + "\n").encode())
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", required=True)
    parser.add_argument("--output")
    parser.add_argument("--position", type=int, choices=(0, 1, 2), default=1)
    parser.add_argument("--stem", default="upstream-car-intervals")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        result = load_terminal_study(args.study_dir)
        print(json.dumps({"terminal_complete": True, "verified_files": result["verified_files"],
                          "coefficient_rows": len(result["rows"]), "source_manifest_sha256": result["manifest_sha256"],
                          "graphics_created": 0, "model_calls": 0, "simulation_trials": 0}))
    else:
        if args.output is None:
            parser.error("--output is required unless --verify-only is set")
        result = build(args.study_dir, args.output, position=args.position, stem=args.stem)
        print(json.dumps({"output": str(Path(args.output).resolve()), "figures": result["figure_count"],
                          "fraction_rows": result["fraction_rows"]}))


if __name__ == "__main__":
    main()
