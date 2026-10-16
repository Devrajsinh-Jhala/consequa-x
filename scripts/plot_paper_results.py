"""Render paper figures from a sealed, independently audited sampling study.

Requires Matplotlib only as an optional authoring dependency. This script never
imports Consequa-X, reruns policies or changes the sealed study. Existing output
files are refused. The output manifest retains every plotted source row and
binds the script, all sealed inputs, the independent audit and generated assets.
"""

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath


SOURCE = "0bd744df4fc8784e4cf1a1e2eb62f892c6f3c8c9"
MANIFEST = "3ee00dfb6ac66db219bc25b1248a1645b8f86deeecae6c9c46a8419cc1235af4"
CASE_LABELS = {
    "refund-p50-q50": "Unsafe p=.50, q=.50",
    "refund-p20-q80": "Unsafe p=.20, q=.80",
    "refund-p80-q20": "Unsafe p=.80, q=.20",
    "refund-p100-q100": "Deterministic p=q=1",
    "idempotent-p50-q50": "Idempotent p=q=.50",
    "unknown-provenance-p50-q50": "Unknown provenance",
    "lagged-readback-p50-q50": "Lagged readback",
    "budget-p50-q50": "Call-budget control",
}
VARIANTS = ("normal", "hoeffding_exact_endpoints")
COLORS = ("#31688e", "#b26b25")
MARKERS = ("o", "s")
STEMS = ("data-interval-tradeoffs", "data-branch-disposition")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def load(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def verified_inputs(study, audit_path, expected_source, expected_manifest):
    manifest_path = study / "manifest.json"
    require(digest(manifest_path) == expected_manifest, "Unexpected study manifest hash")
    manifest = load(manifest_path)
    require(
        manifest["status"] == "completed" and manifest["completed"] is True,
        "A completed sealed study is required",
    )
    names = set()
    for item in manifest["artifacts"]:
        name = item["path"]
        require(type(name) is str, "Artifact path must be text")
        relative = PurePosixPath(name)
        require(
            relative.as_posix() == name
            and not relative.is_absolute()
            and all(part not in ("", ".", "..") and ":" not in part and "\\" not in part
                    for part in name.split("/")),
            "Unsafe sealed artifact path",
        )
        require(name not in names and name != "manifest.json", "Duplicate/circular artifact")
        names.add(name)
        path = (study / name).resolve()
        require(path.is_relative_to(study), "Artifact leaves the sealed study")
        require(type(item["bytes"]) is int and path.stat().st_size == item["bytes"],
                "Changed artifact size: " + name)
        require(digest(path) == item["sha256"], "Changed artifact bytes: " + name)
    require(
        names == {path.relative_to(study).as_posix() for path in study.rglob("*")
                  if path.is_file() and path != manifest_path},
        "Missing or extra sealed study files",
    )
    # Bind the audit before opening the summary or protocol for interpretation.
    audit = load(audit_path)
    require(audit["status"] == "passed" and type(audit["assertions"]) is int
            and audit["assertions"] > 0, "A passed independent audit is required")
    require(audit["manifest_sha256"] == expected_manifest
            and audit["source_revision"] == expected_source, "Audit belongs to another study")
    summary, protocol = load(study / "summary.json"), load(study / "protocol.json")
    require(protocol["source_revision"] == expected_source, "Unexpected frozen source")
    for audit_field, summary_field in (("trials", "retained_trials"),
                                      ("branches", "planned_branches"),
                                      ("actual_policy_calls", "actual_policy_calls")):
        require(audit[audit_field] == summary[summary_field], "Changed audit count")
    require(audit["generation_calls"] == 0
            and summary["additional_comparison_policy_calls"] == 0,
            "This figure requires the synthetic same-draw study")
    require(protocol["plan"]["repeats"] == 128
            and protocol["plan"]["confidence"] == .95
            and protocol["plan"]["mechanisms"] == list(CASE_LABELS),
            "The declared figure design requires all eight registered cases")
    return summary, protocol, audit, manifest


def check_rate(rate):
    k, n = rate["numerator"], rate["denominator"]
    require(type(k) is int and type(n) is int and 0 <= k <= n <= 128,
            "Invalid plotted rate denominator")
    if n:
        require(rate["rate"] == k / n, "Changed plotted rate")
        low, high = rate["confidence_interval"]
        require(0 <= low <= high <= 1, "Invalid Wilson rate bounds")
    else:
        require(rate["rate"] is None and rate["confidence_interval"] is None,
                "Undefined rate must stay undefined")


def figure_rows(summary):
    rows = [row for row in summary["coefficient_rows"]
            if row["coalition_game"] == "on_reach" and row["target"] == "consequence"
            and row["decision_index"] == 1]
    keys = [(row["mechanism"], row["decision_index"], row["variant"]) for row in rows]
    require(len(keys) == len(set(keys)) == 16, "Missing or repeated plotted coefficient row")
    require(set(keys) == {(name, position, method) for name in CASE_LABELS
                          for position in (1,) for method in VARIANTS},
            "The figure must retain all cases and variants for the preselected retry decision")
    for row in rows:
        require(row["planned_trials"] == 128
                and row["available_estimates"] + row["refused_estimates"] == 128,
                "Changed availability denominator")
        require(sum(row["refusal_counts"].values()) == row["refused_estimates"],
                "Changed refusal accounting")
        require(row["reference_eligible_trials"] == (128 if row["reference"] is not None else 0),
                "Changed population-reference eligibility count")
        for field in ("interval_coverage", "reference_sign_detection", "false_nonzero_flag"):
            check_rate(row[field])
        require(row["interval_coverage"]["denominator"] == (
            row["available_intervals"] if row["reference"] is not None else 0),
            "Coverage must require both an interval and a defined reference")
        width = row["mean_interval_width"]
        require(width is None if not row["available_intervals"]
                else type(width) in (int, float) and math.isfinite(width) and width >= 0,
                "Invalid plotted interval width")
    branches = summary["branch_rows"]
    keys = [(row["mechanism"], row["coalition_game"]) for row in branches]
    require(len(set(keys)) == len(keys) == 16
            and set(keys) == {(name, game) for name in CASE_LABELS
                             for game in ("strict", "on_reach")},
            "Missing or repeated mechanism/game branch row")
    for row in branches:
        require(set(row["status_counts"]) == {"completed", "invalid", "failed", "unstarted"}
                and all(type(value) is int and value >= 0
                        for value in row["status_counts"].values())
                and sum(row["status_counts"].values()) == row["planned_branches"] == 40960,
                "Statuses must partition every planned branch")
        require(0 <= row["inactive_held_branches"] <= row["status_counts"]["completed"],
                "Inactive holds are a subset of completed branches")
    return rows, branches


def rate_point(ax, rate, y, *, color, marker, filled=True, error=True):
    if rate["denominator"] == 0:
        return
    center = rate["rate"] * 100
    bounds = rate["confidence_interval"]
    err = [[center - bounds[0] * 100], [bounds[1] * 100 - center]] if error else None
    ax.errorbar(center, y, xerr=err, fmt=marker, ms=3.7,
                markerfacecolor=color if filled else "white", markeredgecolor=color,
                markeredgewidth=.75, color=color, elinewidth=.7, capsize=1.4, zorder=3)


def style_axis(ax):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="both", length=2.2, width=.5)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#e6e6e6", linewidth=.5, zorder=0)


def interval_figure(rows, plt, line2d):
    fig, axes = plt.subplots(1, 3, figsize=(6.9, 3.6), sharey=True,
                             gridspec_kw={"width_ratios": [1.05, 1, 1.05]})
    fig.subplots_adjust(left=.30, right=.985, bottom=.20, top=.86, wspace=.24)
    labels = []
    by_key = {(row["mechanism"], row["decision_index"], row["variant"]): row for row in rows}
    for case_index, (name, label) in enumerate(CASE_LABELS.items()):
        base = 7 - case_index
        first = by_key[name, 1, "normal"]
        labels.append(label + "\nA/R=" + str(first["available_estimates"])
                      + "/" + str(first["reference_eligible_trials"]))
        for ax in axes:
            if case_index % 2 == 0:
                ax.axhspan(base - .49, base + .49, color="#f7f7f7", zorder=-2)
        if not first["available_estimates"]:
            text = "undefined" if first["reference"] is None else "refused"
            for ax in axes:
                ax.text(.5, base, text, ha="center", va="center", fontsize=8,
                        color="#666666", transform=ax.get_yaxis_transform())
            continue
        for position in (1,):
            for variant_index, variant in enumerate(VARIANTS):
                row = by_key[name, position, variant]
                y = base + (.12 if variant_index == 0 else -.12)
                color, marker = COLORS[variant_index], MARKERS[variant_index]
                rate_point(axes[0], row["interval_coverage"], y,
                           color=color, marker=marker)
                axes[1].plot(row["mean_interval_width"], y, marker=marker, ms=3.7,
                             color=color, linestyle="none", markeredgewidth=.7)
                nonzero = row["reference"] not in (None, 0)
                rate_point(axes[2], row["reference_sign_detection"] if nonzero
                           else row["false_nonzero_flag"], y, color=color,
                           marker=marker, filled=nonzero)
    axes[0].axvline(95, color="#555555", lw=.8, ls=(0, (3, 2)), zorder=1)
    axes[0].set(xlim=(80, 102), xticks=[80, 90, 95, 100],
                xlabel="Coverage (%)", title="(a) Nominal 95% intervals")
    axes[1].set(xlim=(-.025, 1.025), xticks=[0, .5, 1],
                xlabel="Mean interval width", title="(b) Precision cost")
    axes[2].set(xlim=(-5, 105), xticks=[0, 50, 100],
                xlabel="Rate (%)", title="(c) Sign / false flag")
    axes[0].set_yticks(list(range(7, -1, -1)), labels)
    for ax in axes:
        ax.set_ylim(-.5, 7.5)
        style_axis(ax)
        ax.set_title(ax.get_title(), fontsize=8.2, pad=8)
    handles = [line2d([], [], color=COLORS[i], marker=MARKERS[i], linestyle="none",
                      label=label, markersize=4)
               for i, label in enumerate(("Normal", "Hoeffding (same draws)"))]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.54, .99),
               ncol=2, frameon=False, columnspacing=1, handletextpad=.3, fontsize=8)
    fig.text(.30, .073, "Retry only. A/R: available / reference-eligible counts (128 planned each), not a fraction.",
             fontsize=8)
    fig.text(.30, .023, "Panel (c): filled = correct sign; open = false nonzero flag at a zero reference.",
             fontsize=8)
    return fig


def branch_figure(rows, plt, patch):
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 3.6), sharey=True,
                             gridspec_kw={"width_ratios": [2.2, 1]})
    fig.subplots_adjust(left=.335, right=.985, bottom=.19, top=.87, wspace=.19)
    by_key = {(row["mechanism"], row["coalition_game"]): row for row in rows}
    statuses = ("completed", "invalid", "failed", "unstarted")
    colors = (COLORS[0], COLORS[1], "#494949", "#e6e6e6")
    hatches = (None, "///", "xxx", "...")
    ticks, labels = [], []
    for case_index, (name, label) in enumerate(CASE_LABELS.items()):
        base = 7 - case_index
        if case_index % 2 == 0:
            for ax in axes:
                ax.axhspan(base - .49, base + .49, color="#f7f7f7", zorder=-2)
        axes[0].text(-.16, base, label, transform=axes[0].get_yaxis_transform(),
                     ha="right", va="center", fontsize=8)
        for game_index, game in enumerate(("strict", "on_reach")):
            row = by_key[name, game]
            y = base + (.18 if game_index == 0 else -.18)
            left = 0
            for status, color, hatch in zip(statuses, colors, hatches):
                width = row["status_counts"][status] / row["planned_branches"] * 100
                axes[0].barh(y, width, height=.25, left=left, color=color, hatch=hatch,
                             edgecolor="white" if status == "completed" else "#777777",
                             linewidth=.3, zorder=2)
                left += width
            if name == "budget-p50-q50":
                counts = row["status_counts"]
                axes[0].text(51, y, f"{counts['completed']} completed / "
                             f"{counts['failed']} failed / {counts['unstarted']:,} unstarted",
                             ha="center", va="center", fontsize=8, color="#333333",
                             bbox={"facecolor": "#f5f5f5", "edgecolor": "none", "pad": .5},
                             zorder=3)
            ticks.append(y)
            labels.append("S" if game == "strict" else "R")
            inactive = row["inactive_held_branches"] / row["planned_branches"] * 100
            axes[1].plot(inactive, y, marker="o" if game_index == 0 else "s", ms=3.5,
                         color=COLORS[0], markerfacecolor="white" if game_index == 0
                         else COLORS[0], linestyle="none", zorder=3)
            axes[1].text(inactive + .8, y, str(row["inactive_held_branches"]),
                         va="center", ha="left", fontsize=8)
    axes[0].set_yticks(ticks, labels)
    axes[0].set(xlim=(0, 100), xticks=[0, 25, 50, 75, 100],
                xlabel="Share of planned branches (%)", title="(a) All planned branch slots")
    axes[1].set(xlim=(-.5, 25), xticks=[0, 10, 20],
                xlabel="Share of planned branches (%)", title="(b) Inactive-held subset")
    for ax in axes:
        ax.set_ylim(-.5, 7.5)
        style_axis(ax)
        ax.set_title(ax.get_title(), fontsize=8.2, pad=8)
    handles = [patch(facecolor=color, edgecolor="#777777", hatch=hatch, label=status.title())
               for status, color, hatch in zip(statuses, colors, hatches)]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.57, .995),
               ncol=4, frameon=False, columnspacing=1.1, handletextpad=.35, fontsize=8)
    fig.text(.335, .065, "S: strict; R: on-reach. Each row retains 40,960 planned branches (128 trials).",
             fontsize=8)
    fig.text(.335, .025, "Inactive holds belong to completed branches; labels in (b) give exact counts.",
             fontsize=8)
    return fig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="output/interaction-sampling-2026-10-15")
    parser.add_argument("--audit", default="output/interaction-sampling-audits-2026-10-15/independent.json")
    parser.add_argument("--output", default="paper/figures")
    parser.add_argument("--expected-source", default=SOURCE)
    parser.add_argument("--expected-manifest", default=MANIFEST)
    args = parser.parse_args(argv)
    study, audit_path, destination = (Path(value).resolve()
                                      for value in (args.study, args.audit, args.output))
    require(not destination.is_relative_to(study), "Figures must stay outside the sealed study")
    files = [destination / (stem + "." + suffix) for stem in STEMS
             for suffix in ("pdf", "svg", "png")] + [destination / "data-figures.json"]
    require(all(not path.exists() for path in files), "Existing figure files are refused")
    summary, protocol, audit, sealed_manifest = verified_inputs(
        study, audit_path, args.expected_source, args.expected_manifest)
    rows, branches = figure_rows(summary)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["STIXGeneral"], "mathtext.fontset": "stix",
        "font.size": 8, "axes.labelsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "svg.hashsalt": "consequa-x-audited-paper-figures", "axes.linewidth": .55,
        "savefig.facecolor": "white", "hatch.linewidth": .35,
    })
    figures = (interval_figure(rows, plt, Line2D), branch_figure(branches, plt, Patch))
    destination.mkdir(parents=True, exist_ok=True)
    for stem, fig in zip(STEMS, figures):
        for suffix in ("pdf", "svg", "png"):
            metadata = {"Creator": "Consequa-X audited figure generator"}
            if suffix == "pdf":
                metadata.update({"CreationDate": None, "ModDate": None})
            elif suffix == "svg":
                metadata["Date"] = None
            fig.savefig(destination / (stem + "." + suffix), dpi=220, metadata=metadata)
        plt.close(fig)
    result = {
        "schema_version": "consequa-x-paper-data-figures-v1",
        "source_revision": args.expected_source,
        "inputs": {
            "sealed_manifest_sha256": args.expected_manifest,
            "sealed_artifacts_verified": sealed_manifest["artifacts"],
            "summary_sha256": digest(study / "summary.json"),
            "protocol_sha256": digest(study / "protocol.json"),
            "independent_audit_sha256": digest(audit_path),
            "script_sha256": digest(__file__),
        },
        "audit": audit,
        "settings": {
            "matplotlib": matplotlib.__version__,
            "sizes_inches": {STEMS[0]: [6.9, 3.6], STEMS[1]: [6.9, 3.6]},
            "minimum_font_points": 8,
            "palette": list(COLORS), "interval_method_markers": list(MARKERS),
            "figure_one_target": "consequence", "figure_one_game": "on_reach",
            "figure_one_decision_index": 1,
            "availability_label": "A/R means available-estimate and population-reference-eligible "
                                  "trial counts, respectively; each count is out of 128 planned "
                                  "trials, not an availability or coverage fraction",
            "rate_uncertainty": "Saved nominal 95% Wilson intervals; no multiplicity adjustment",
            "new_policy_calls": 0, "new_model_calls": 0,
            "pooling": "none; every plotted marker is one saved case/player/method row",
        },
        "plotted_coefficient_rows": rows,
        "plotted_branch_rows": branches,
        "plan": protocol["plan"],
        "captions": {
            STEMS[0]: "On-reach global-consequence retry coefficient for every registered mechanism. "
                "Normal and Hoeffding intervals use identical retained draws. A/R gives two counts: "
                "available estimates and population-reference-eligible trials, respectively, "
                "each from 128 planned trials per case. A/R is not a coverage fraction. "
                "Coverage is conditional on availability and a defined reference; "
                "whiskers are nominal 95% Wilson uncertainty for repeated-trial rates. Mean widths "
                "show the precision cost. Filled sign-panel symbols report correct reference-sign "
                "detection for nonzero coefficients; open symbols report false nonzero flags at zero "
                "references. Undefined lagged evidence and budget refusals are not zero coverage. "
                "Rows and interval methods share data and are not independent replications.",
            STEMS[1]: "Branch disposition for all eight mechanisms under strict (S) and on-reach (R) "
                "games. Each row retains all 40,960 planned slots from 128 trials. Stacked statuses "
                "partition completed, invalid, failed and unstarted branches; narrow budget-control "
                "segments remain in the exact source counts. Inactive-held branches are a subset "
                "of completed branches, displayed separately with exact counts. Completed execution "
                "includes known violations and unknown target evidence and does not imply outcome "
                "verification or an available coefficient vector.",
        },
        "limits": [
            "Synthetic planted-factual study; no held-out model generalization claim.",
            "No fresh sampling, data fitting, confidence-interval recomputation or model calls.",
            "95% coverage line is a nominal target, not a guarantee of observed finite-sample rates.",
            "Zero-denominator rates stay undefined; lagged and budget rows carry no numeric coverage.",
            "Wilson uncertainty is unadjusted for multiple displayed comparisons.",
            "No pooled point-interaction uncertainty or sign claim is plotted.",
            "Hash binding detects changed bytes and is not external provider authentication.",
        ],
        "artifacts": [{"path": path.name, "bytes": path.stat().st_size,
                       "sha256": digest(path)} for path in files[:-1]],
    }
    files[-1].write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8", newline="\n")
    print(json.dumps({"status": "completed", "files": [str(path) for path in files],
                      "verified_sealed_files": len(sealed_manifest["artifacts"]),
                      "plotted_coefficients": len(rows), "plotted_branch_groups": len(branches)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
