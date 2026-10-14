"""Render an exportable research figure from an audited finite-grid artifact.

Requires matplotlib in an audit/plot environment, not the framework runtime.
Each marker is an enumerated grid point; connecting lines are guides only.
"""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    data = json.loads((args.root/"finite-binomial.json").read_text(encoding="utf-8"))
    plt.rcParams.update({"font.size": 10, "svg.fonttype": "none", "pdf.fonttype": 42})
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), layout="constrained")
    styles = {
        "percentile_bootstrap_limit": ("Bootstrap limit", "#c45a22", "s"),
        "wilson": ("Wilson", "#2377aa", "^"),
        "clopper_pearson": ("Clopper–Pearson", "#218657", "o"),
    }
    for column, total in enumerate((16, 64)):
        for name, (label, color, marker) in styles.items():
            rows = sorted((r for r in data["rows"] if r["samples"] == total and r["method"] == name),
                          key=lambda r: r["probability"])
            x = [r["probability"] for r in rows]
            for ax, field in ((axes[0, column], "coverage"), (axes[1, column], "expected_width")):
                ax.plot(x, [r[field] for r in rows], label=label, color=color, marker=marker,
                        markersize=4, linewidth=1.4)
        axes[0, column].axhline(data["confidence"], color="0.35", linestyle="--", linewidth=1,
                               label=f"Nominal {data['confidence']:.0%}")
        axes[0, column].set_title(f"Independent binary draws, n = {total}")
        for ax in axes[:, column]:
            ax.set_xlabel("Population bad-outcome probability q")
            ax.set_xlim(-.02, 1.02)
            ax.grid(alpha=.15)
        axes[0, column].set_ylim(0, 1.025)
        axes[1, column].set_ylim(bottom=0)
    axes[0, 0].set_ylabel("Exact inclusive interval coverage")
    axes[1, 0].set_ylabel("Expected interval width")
    axes[0, 1].legend(loc="lower center", frameon=False)
    fig.suptitle("Small-sample binary uncertainty: coverage and width", fontsize=14)
    fig.supxlabel("Exact rational probability weights; float interval boundaries. Bootstrap is the infinite-resample limit.\n"
                  "Markers show the declared grid; lines are guides. These are distribution calculations, not live-model results.",
                  fontsize=9)
    output = args.root/"figures"
    output.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg", "pdf"):
        fig.savefig(output/f"finite-binomial.{extension}", dpi=200)
    plt.close(fig)
    (output/"environment.json").write_text(json.dumps({"matplotlib": matplotlib.__version__,
        "source": "finite-binomial.json", "script": "scripts/plot_interval_comparison.py"},
        indent=2)+"\n", encoding="utf-8")
    print(f"Saved PNG, SVG and PDF research figure in {output.resolve()}")


if __name__ == "__main__":
    main()
