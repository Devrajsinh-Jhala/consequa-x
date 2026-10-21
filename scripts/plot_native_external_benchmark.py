"""Plot audited finite-pilot counts without treating paired arms as new tasks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    audit_path = Path(args.audit).resolve()
    result = json.loads(audit_path.read_text(encoding="utf-8"))
    if result.get("passed") is not True or len(result.get("rows", [])) != 48:
        raise ValueError("A passed complete48-slot artifact audit is required")
    rows, summary = result["rows"], result["summary"]
    if summary["distinct_task_ids"] != 12 or summary["planned_slots"] != 48:
        raise ValueError("Plot denominator differs from frozen12-task pilot")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
        "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False,
        "axes.spines.right": False, "axes.axisbelow": True})
    arms = ("B", "C", "R", "G")
    labels = ("B: raw reads", "C: classical + guard", "R: receipt", "G: receipt + guard")
    y = np.arange(4)
    figure, axes = plt.subplots(1, 2, figsize=(7.2, 3.45), sharey=True)
    source_table = []
    for axis, stratum in zip(axes, (True, False)):
        selected = [[row for row in rows if row["arm"] == arm
                     and row["nonempty_communication"] is stratum] for arm in arms]
        if any(len(group) != 6 for group in selected):
            raise ValueError("Every plotted arm/stratum requires six planned slots")
        successes = [sum(row["operational_success"] for row in group) for group in selected]
        audited_zero = [sum(row.get("episode_audit_passed") is True
                           and row.get("native_reward") == 0 for row in group) for group in selected]
        remainder = [6 - a - b for a, b in zip(successes, audited_zero)]
        if any(value < 0 for value in remainder):
            raise ValueError("Plotted native outcome counts overlap")
        axis.barh(y, successes, color="#176b54", label="Native reward 1")
        axis.barh(y, audited_zero, left=successes, color="#cb8451", label="Audited native reward 0")
        axis.barh(y, remainder, left=np.array(successes) + audited_zero, color="#e0e3e5",
                  hatch="///", edgecolor="#869098", linewidth=.4, label="Other planned slots")
        for position, (arm, success, zero, other) in enumerate(zip(arms, successes, audited_zero, remainder)):
            axis.text(6.12, position, f"{success}/6", va="center", fontsize=8)
            source_table.append({"arm": arm, "nonempty_communication": stratum,
                "native_reward1_operational": success, "audited_native_reward0": zero,
                "other_planned_slots": other, "planned": 6})
        axis.set_xlim(0, 7)
        axis.set_xticks(range(7))
        axis.set_xlabel("Planned trajectories (6 per arm)")
        axis.set_title("Nonempty communication criteria" if stratum else "Empty criteria (native vacuous check)",
                       fontsize=8.5)
        axis.grid(axis="x", alpha=.18)
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    handles, legend_labels = axes[0].get_legend_handles_labels()
    figure.legend(handles, legend_labels, loc="lower center", ncol=3, frameon=False, fontsize=7.5)
    attempted = sum(row["collection_disposition"] != "unstarted" for row in rows)
    figure.suptitle(f"Native airline pilot:12 distinct tasks,48 paired slots ({attempted} attempted)", fontsize=10)
    figure.tight_layout(rect=(0, .10, 1, .91), w_pad=1.6)
    for extension in ("pdf", "svg", "png"):
        figure.savefig(output / f"native-airline-pilot.{extension}", dpi=220, bbox_inches="tight")
    plt.close(figure)
    table = {"audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        "plot_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rows": source_table,
        "caption_limits": "Paired finite exposed-corpus pilot,not48independenttasks. Other planned slots include unavailable native rewards and collection failures; see disposition table. No population intervals or algorithm-superiority inference."}
    (output / "plot-inputs.json").write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in output.iterdir() if path.is_file()}
    (output / "manifest.json").write_text(json.dumps({"schema": "conseqax-native-pilot-figure-v1",
                                                     "files": files}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "audit_sha256": table["audit_sha256"]}))


if __name__ == "__main__":
    main()
