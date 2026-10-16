"""Draw conceptual IEEE figures without changing runtime or retained evidence.

Requires Matplotlib only. PDF output is vector with embedded TrueType fonts;
SVG keeps editable text. All times in the retry diagram are illustrative,
not recorded benchmark measurements. Existing outputs are never overwritten.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle


REPO = Path(__file__).resolve().parents[1]
BLUE = "#244F77"
GREEN = "#24644B"
ORANGE = "#9A4B10"
INK = "#20272B"
GRAY = "#5E6870"
PALE_BLUE = "#EEF4F9"
PALE_GREEN = "#EDF5F0"
PALE_ORANGE = "#FFF3E8"
PALE_GRAY = "#F6F7F8"
SOURCES = (
    "src/consequa_x/models.py",
    "src/consequa_x/verification.py",
    "src/consequa_x/explanation.py",
    "src/consequa_x/graph.py",
    "src/consequa_x/benchmark/payments.py",
    "src/consequa_x/benchmark/policy_runner.py",
    "src/consequa_x/benchmark/decision_shapley.py",
    "src/consequa_x/benchmark/targets.py",
)


def configuration() -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Liberation Serif", "DejaVu Serif"],
        "font.size": 9,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "svg.hashsalt": "consequa-x-paper-conceptual-v1",
        "axes.unicode_minus": False,
    })


def canvas(height: float):
    fig, ax = plt.subplots(figsize=(6.9, height))
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(0, 6.9)
    ax.set_ylim(0, height)
    ax.axis("off")
    return fig, ax


def text(ax, x, y, value, *, size=9, weight="normal", ha="center", va="center",
         color=INK, **kwargs):
    return ax.text(x, y, value, fontsize=size, fontweight=weight, ha=ha, va=va,
                   color=color, linespacing=1.15, **kwargs)


def box(ax, x, y, width, height, value, *, edge=BLUE, face=PALE_BLUE,
        style="solid", size=9, weight="normal"):
    patch = FancyBboxPatch((x, y), width, height,
                           boxstyle="round,pad=0.018,rounding_size=0.04",
                           linewidth=1.0, edgecolor=edge, facecolor=face,
                           linestyle=style)
    ax.add_patch(patch)
    text(ax, x + width / 2, y + height / 2, value, size=size, weight=weight)
    return patch


def arrow(ax, start, end, *, color=GRAY, style="solid", width=1.05,
          connection="arc3", mutation=9):
    patch = FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=mutation,
                            color=color, linewidth=width, linestyle=style,
                            connectionstyle=connection, shrinkA=2, shrinkB=2)
    ax.add_patch(patch)
    return patch


def architecture():
    fig, ax = canvas(4.65)
    # Upper panel is the evidence-only path. No incoming arrow authenticates a source.
    ax.add_patch(Rectangle((0.10, 2.43), 6.70, 2.09, facecolor="white",
                           edgecolor=GRAY, linewidth=0.9))
    text(ax, 0.24, 4.36, "Evidence core: captured records; no tool execution",
         ha="left", size=10, weight="bold")

    box(ax, 0.25, 3.48, 1.77, 0.65,
        "Application capture\nAction + contract; events, attempts\nresponses; reported assessment", size=8.4)
    box(ax, 0.25, 2.69, 1.77, 0.59,
        "Independent readback\nScope, completeness, watermark", size=8.8)
    box(ax, 2.36, 2.69, 1.33, 0.59,
        "Explicit Verifier\nState + origin receipt", edge=GREEN, face=PALE_GREEN, size=8.7)
    box(ax, 4.05, 3.48, 0.99, 0.65, "Trace\nSchema 0.1", size=9.5, weight="bold")
    box(ax, 5.40, 3.48, 1.12, 0.65,
        "explain(trace)\nEvidence graph\n+ diagnoses", size=9.2)
    box(ax, 5.19, 2.69, 1.54, 0.59,
        "Domain TargetMatcher\nQualifies assessment target", edge=GREEN,
        face=PALE_GREEN, size=8.6)

    arrow(ax, (2.04, 3.805), (4.03, 3.805), color=BLUE)
    arrow(ax, (2.04, 2.985), (2.34, 2.985), color=GREEN)
    arrow(ax, (3.71, 2.985), (4.55, 3.46), color=GREEN)
    arrow(ax, (5.06, 3.805), (5.38, 3.805), color=BLUE)
    arrow(ax, (5.96, 3.30), (5.96, 3.46), color=GREEN)
    text(ax, 3.025, 3.34, "trusted adapter", size=8, color=GRAY)
    text(ax, 0.24, 2.53,
         "Source trust and domain semantics are application responsibilities.",
         ha="left", size=8.3, color=GRAY)

    # The dotted area is explicitly optional and cannot be mistaken for explain().
    ax.add_patch(Rectangle((0.10, 0.48), 6.70, 1.73, facecolor=PALE_GRAY,
                           edgecolor=GRAY, linewidth=0.9, linestyle=(0, (4, 3))))
    text(ax, 0.24, 2.055, "Optional research path: explicit replay invocation",
         ha="left", size=10, weight="bold")
    box(ax, 0.26, 1.14, 1.49, 0.64,
        "Declared intervention\n+ continuation policy", face="white", size=8.8)
    box(ax, 2.10, 1.14, 2.05, 0.64,
        "Replay adapter\nFresh isolated world\nPublic-only policy inputs", face="white", size=8.8)
    box(ax, 4.53, 1.14, 1.99, 0.64,
        "Intervention estimates\n+ refusal records", face="white", size=9)
    arrow(ax, (1.77, 1.46), (2.08, 1.46), color=BLUE)
    arrow(ax, (4.17, 1.46), (4.51, 1.46), color=BLUE)
    # Optional estimates enter explain explicitly, not through a hidden replay.
    # Route through open space, never across the TargetMatcher box or its text.
    ax.plot([4.85, 4.85, 5.57], [1.80, 3.38, 3.38], color=BLUE,
            linewidth=1.05, linestyle=(0, (4, 3)))
    arrow(ax, (5.57, 3.38), (5.57, 3.48), style=(0, (4, 3)), color=BLUE)
    ax.add_patch(Rectangle((0.26, 0.63), 6.26, 0.30,
                           facecolor="white", edgecolor=GRAY, linewidth=0.8))
    text(ax, 3.39, 0.78,
         "Evaluator-only simulator truth → independent audit; never a policy / explainer input",
         size=8.5)
    text(ax, 0.15, 0.24,
         "Solid arrows: evidence flow. Dashed arrow: optional supplied estimate.\n"
         "A provenance link supports origin; it does not establish counterfactual necessity.",
         ha="left", size=8.3, color=GRAY)
    return fig


def timing():
    fig, ax = canvas(4.12)
    text(ax, 0.18, 3.95, "One committed effect can coexist with a timeout response",
         ha="left", size=10, weight="bold")
    initial = [
        (0.19, 1.20, "5 ms\nFirst dispatch"),
        (1.80, 1.20, "15 ms\nCommit effect #1"),
        (3.41, 1.34, "20 ms\nTimeout response"),
        (5.16, 1.54, "22 ms\nReport FAILURE"),
    ]
    for x, width, value in initial:
        box(ax, x, 2.97, width, 0.62, value, size=9.1)
    for left, right in zip(initial, initial[1:]):
        arrow(ax, (left[0] + left[1] + 0.02, 3.28), (right[0] - 0.02, 3.28), color=BLUE)
    text(ax, 0.19, 2.73,
         "Contract: exactly one matching effect by 50 ms, persisting through 70 ms.",
         ha="left", size=9)
    text(ax, 0.19, 2.54,
         "Both final readbacks: observed at 80 ms; complete scope; watermark = 70 ms.",
         ha="left", size=8.8)

    # Equal boxes express event order, intentionally not a linear time scale.
    for y, title, edge, face, style, cells in (
        (1.55, "(a) Retry without idempotency", ORANGE, PALE_ORANGE, (0, (4, 2)), (
            "30 ms\nRetry; no key", "35 ms\nCommit effect #2", "80 ms readback\n2 effects: VIOLATED")),
        (0.47, "(b) Retry with the same operation key and payload", GREEN, PALE_GREEN, "solid", (
            "30 ms\nRetry; same key", "35 ms\nReuse effect #1", "80 ms readback\n1 effect: SATISFIED")),
    ):
        text(ax, 0.19, y + 0.77, title, ha="left", size=9.3, weight="bold", color=edge)
        positions = ((0.19, 1.62), (2.43, 1.72), (4.77, 1.93))
        for (x, width), value in zip(positions, cells):
            box(ax, x, y, width, 0.62, value, edge=edge, face=face,
                style=style, size=9.2)
        for (x, width), (next_x, _) in zip(positions, positions[1:]):
            arrow(ax, (x + width + 0.02, y + 0.31),
                  (next_x - 0.02, y + 0.31), color=edge, style=style)
    text(ax, 0.19, 0.17,
         "Illustrative event order, not to scale. Assume matching payloads and persistence.\n"
         "Idempotency is a declared provider property; source metadata must support origin.",
         ha="left", size=8.3, color=GRAY)
    return fig


CAPTIONS = {
    "diagram-evidence-architecture": (
        "Evidence-only core and optional intervention path. Applications supply captured "
        "records and independently read observations; explicit verifiers produce state "
        "and origin receipts. A domain matcher qualifies custom assessment targets. "
        "Explanation does not execute tools or replay. Separately invoked research "
        "adapters may supply estimates with refusal records; evaluator-only truth is "
        "reserved for audit. Adapter declarations are trusted inputs, not authentication "
        "or guarantees of read-only behavior."
    ),
    "diagram-timeout-retry": (
        "Illustrative timeout-after-commit sequence for an exactly-one contract. The "
        "first effect commits before its timeout acknowledgement and the agent reports "
        "failure. A retry without idempotency creates a second effect; a retry with the "
        "same provider-scoped operation key and payload reuses the first effect. Final "
        "independent, complete readback covers the stability horizon before a definite "
        "conclusion is drawn. Times are illustrative, arrows show event order rather "
        "than causal necessity, and the provider behavior is a declared example rather "
        "than a real-service guarantee."
    ),
}


def digest(path: Path):
    return {"path": path.relative_to(REPO).as_posix(), "sha256": sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def check_text_bounds(figure) -> dict:
    """Reject clipped or sub-8-point labels before writing any figure asset."""
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    canvas_bounds = figure.bbox
    labels = [label for axis in figure.axes for label in axis.texts]
    for label in labels:
        bounds = label.get_window_extent(renderer=renderer)
        if (label.get_fontsize() < 8 or bounds.x0 < canvas_bounds.x0 - 0.5
                or bounds.y0 < canvas_bounds.y0 - 0.5
                or bounds.x1 > canvas_bounds.x1 + 0.5
                or bounds.y1 > canvas_bounds.y1 + 0.5):
            raise ValueError(f"Clipped or undersized diagram label: {label.get_text()!r}")
    return {"labels": len(labels), "all_labels_within_canvas": True,
            "minimum_font_size_points": min(label.get_fontsize() for label in labels)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPO / "paper" / "figures")
    args = parser.parse_args()
    directory = args.output_dir.resolve()
    if not directory.is_relative_to(REPO):
        raise SystemExit("Output directory must be within this repository for portable manifests")
    expected = [directory / f"{name}.{suffix}"
                for name in CAPTIONS for suffix in ("pdf", "svg", "png")]
    expected.append(directory / "diagram-figures.json")
    existing = [str(path) for path in expected if path.exists()]
    if existing:
        raise SystemExit("Refusing to overwrite existing diagrams: " + ", ".join(existing))
    directory.mkdir(parents=True, exist_ok=True)
    configuration()
    generated = []
    layout_checks = {}
    for name, factory in (("diagram-evidence-architecture", architecture),
                          ("diagram-timeout-retry", timing)):
        figure = factory()
        layout_checks[name] = check_text_bounds(figure)
        # Preserve exactly 6.9-inch width; tight cropping can silently change printed font size.
        for suffix in ("pdf", "svg", "png"):
            path = directory / f"{name}.{suffix}"
            metadata = {"Creator": "Consequa-X conceptual figure script"}
            if suffix == "pdf":
                metadata.update({"CreationDate": None, "ModDate": None})
            elif suffix == "svg":
                metadata = {"Creator": metadata["Creator"], "Date": None}
            figure.savefig(path, dpi=220, metadata=metadata)
            generated.append(digest(path))
        plt.close(figure)
    manifest = {
        "schema_version": "consequa-x-conceptual-paper-figures-v1",
        "purpose": "Illustrative software architecture and event order; no empirical data plotted",
        "source_script": digest(Path(__file__).resolve()),
        "reviewed_runtime_sources": [digest(REPO / item) for item in SOURCES],
        "physical_width_inches": 6.9,
        "minimum_font_size_points": 8,
        "font_family": plt.rcParams["font.serif"],
        "resolved_font_family": font_manager.FontProperties(
            fname=font_manager.findfont(font_manager.FontProperties(family="serif"))).get_name(),
        "svg_text_editable": True,
        "layout_checks": layout_checks,
        "captions": CAPTIONS,
        "illustrative_times_ms": {
            "registered": 0, "first_dispatch": 5, "first_commit": 15,
            "timeout_response": 20, "reported_failure": 22, "retry_dispatch": 30,
            "retry_execution": 35, "deadline": 50, "horizon": 70,
            "observed_at": 80, "readback_watermark": 70,
        },
        "trust_limits": [
            "Verifier and TargetMatcher domain semantics remain application responsibilities",
            "Source assertions, schema validation and hashes do not authenticate sources",
            "Origin support does not establish counterfactual necessity",
            "PaymentWorld idempotency is an illustrative declared provider behavior",
        ],
        "artifacts": generated,
    }
    expected[-1].write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Created {len(generated)} diagram artifacts and diagram-figures.json in {directory}")


if __name__ == "__main__":
    main()
