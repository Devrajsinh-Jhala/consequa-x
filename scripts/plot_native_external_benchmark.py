"""Plot audited finite-pilot counts without treating paired arms as new tasks."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import ModuleType


ARMS = ("B", "C", "R", "G")
CAPTION_LIMITS = "Paired finite exposed-corpus pilot, not 48 independent tasks. Green requires operational success as well as audited native reward 1. Other planned slots include unavailable native rewards and collection failures; see disposition table. No population intervals or algorithm-superiority inference."


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_renderer():
    """Use the reviewed validator, including from a standalone artifact copy.

    Execute exactly the bytes retained alongside the plot, rather than relying
    on a mutable import search path or assuming the repository is still there.
    """
    directory = Path(__file__).resolve().parent
    path = directory / "renderer.source.py"
    if not path.is_file():
        path = directory / "render_native_paper_results.py"
    source = path.read_bytes()
    renderer = ModuleType("native_plot_audit_validator")
    renderer.__file__ = str(path)
    exec(compile(source, str(path), "exec"), renderer.__dict__)
    return renderer, path, source


def plot_counts(rows):
    """Count only validated rows; the audit's convenience summary is unused."""
    table = []
    for stratum in (True, False):
        for arm in ARMS:
            group = [row for row in rows if row["arm"] == arm and row["nonempty_communication"] is stratum]
            if len(group) != 6:
                raise ValueError("Every plotted arm/stratum requires six planned slots")
            success = sum(row["operational_success"] for row in group)
            zero = sum(row["episode_audit_passed"] is True and row["native_reward"] == 0 for row in group)
            other = 6 - success - zero
            if other < 0:
                raise ValueError("Plotted native outcome counts overlap")
            table.append({"arm": arm, "nonempty_communication": stratum,
                "native_reward1_operational": success, "audited_native_reward0": zero,
                "other_planned_slots": other, "planned": 6})
    return table


def draw_plot(output, rows, source_table):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
        "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False,
        "axes.spines.right": False, "axes.axisbelow": True})
    labels = ("B: raw reads", "C: classical + guard", "R: receipt", "G: receipt + guard")
    y = np.arange(4)
    figure, axes = plt.subplots(1, 2, figsize=(7.2, 3.45), sharey=True)
    for axis, stratum in zip(axes, (True, False)):
        selected = [row for row in source_table if row["nonempty_communication"] is stratum]
        successes = [row["native_reward1_operational"] for row in selected]
        audited_zero = [row["audited_native_reward0"] for row in selected]
        remainder = [row["other_planned_slots"] for row in selected]
        axis.barh(y, successes, color="#176b54", label="Operational native reward 1")
        axis.barh(y, audited_zero, left=successes, color="#cb8451", label="Audited native reward 0")
        axis.barh(y, remainder, left=np.array(successes) + audited_zero, color="#e0e3e5",
                  hatch="///", edgecolor="#869098", linewidth=.4, label="Other planned slots")
        for position, success in enumerate(successes):
            axis.text(6.12, position, f"{success}/6", va="center", fontsize=8)
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
    figure.suptitle(f"Native airline pilot: 12 distinct tasks, 48 paired slots ({attempted} attempted)", fontsize=10)
    figure.tight_layout(rect=(0, .10, 1, .91), w_pad=1.6)
    for extension in ("pdf", "svg", "png"):
        figure.savefig(output / f"native-airline-pilot.{extension}", dpi=220, bbox_inches="tight")
    plt.close(figure)


def execute(audit_path, output, protocol_commit):
    renderer, renderer_path, renderer_source = load_renderer()
    contents, inputs = renderer.verify_inventory(audit_path)
    result, rows, _ = renderer.validate_audit(contents, protocol_commit)
    source_table = plot_counts(rows)
    output = Path(output).absolute()
    renderer.require(not output.exists(), "Output directory must be new")
    renderer.require(not output.resolve().is_relative_to(Path(audit_path).absolute().parent.resolve()),
                     "Output cannot be inside sealed audit input")
    plot_source = Path(__file__).read_bytes()
    output.mkdir(parents=True, exist_ok=False)
    draw_plot(output, rows, source_table)
    (output / "plotter.source.py").write_bytes(plot_source)
    (output / "renderer.source.py").write_bytes(renderer_source)
    table = {"schema": "conseqax-native-pilot-plot-inputs-v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "audit_sha256": inputs["files"]["audit-result.json"]["sha256"],
        "plot_source_sha256": sha256(plot_source),
        "input_audit": inputs, "protocol_anchor": result["protocol_anchor"],
        "execution_source_commit": result["source_commit"],
        "collection_manifest_sha256": result["collection_manifest_sha256"],
        "plotter": {"path": str(Path(__file__).resolve()), "artifact_copy": "plotter.source.py",
                    "sha256": sha256(plot_source), "bytes": len(plot_source)},
        "validator_renderer": {"path": str(renderer_path.resolve()), "artifact_copy": "renderer.source.py",
                               "sha256": sha256(renderer_source), "bytes": len(renderer_source)},
        "counts_recomputed_from_rows": True, "audit_summary_not_used": True,
        "planned_slots": len(rows), "distinct_task_ids": len({row["task_id"] for row in rows}),
        "attempted_slots": sum(row["collection_disposition"] != "unstarted" for row in rows),
        "rows": source_table,
        "caption_limits": CAPTION_LIMITS, "validation_limits": list(renderer.LIMITS)}
    renderer.write_json(output / "plot-inputs.json", table)
    files = {path.name: sha256(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()}
    renderer.write_json(output / "manifest.json", {"schema": "conseqax-native-pilot-figure-v2", "files": files})
    return {"output": str(output), "audit_sha256": table["audit_sha256"], "protocol_commit": protocol_commit}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protocol-commit", required=True,
                        help="Caller-pinned immutable protocol commit; must match the reviewed audit binding")
    args = parser.parse_args(argv)
    print(json.dumps(execute(args.audit, args.output, args.protocol_commit)))


if __name__ == "__main__":
    main()
