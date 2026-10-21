"""Vector methods diagram only; no observations, tasks or quantitative results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


PIN = "8bd1cd88ab3644a9c6417e29308ab4b502b40484"
ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")


def finalize(output):
    required = ("native-four-arm-methods.pdf", "native-four-arm-methods.svg", "native-four-arm-methods.png",
                "rendered-page.png", "fontcheck.txt", "pdfinfo.txt", "source-bindings.json",
                "plot_native_methods.source.py", "visual-qa.json")
    if any(not (output / name).is_file() for name in required):
        raise RuntimeError("Render/font/source/visual QA artifacts must exist before sealing")
    if json.loads((output / "visual-qa.json").read_text())["passed"] is not True:
        raise RuntimeError("Visual inspection must pass before sealing")
    target = output / "manifest.json"
    if target.exists():
        raise FileExistsError("Sealed figure artifacts must not be overwritten")
    files = {path.relative_to(output).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size}
             for path in sorted(output.rglob("*")) if path.is_file()}
    write_json(target, {"schema": "conseqax-native-methods-figure-v1", "complete": True,
        "figure_scope": "Methods only; no quantitative observations or results", "files": files})


def draw(output, frozen):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, PathPatch
    from matplotlib.path import Path as MplPath

    if (output / "manifest.json").exists():
        raise FileExistsError("Figure directory is already sealed")
    head = subprocess.check_output(["git", "-C", str(frozen), "rev-parse", "HEAD"]).decode().strip()
    if head != PIN:
        raise RuntimeError("Methods figure requires the declared frozen source")
    bindings = {}
    for name in ("research/native_agent/controller.py", "research/native_agent/harness.py"):
        actual = (frozen / name).read_bytes()
        git_blob = subprocess.check_output(["git", "-C", str(frozen), "show", PIN + ":" + name])
        if actual != git_blob and not (b"\r\n" not in git_blob and actual == git_blob.replace(b"\n", b"\r\n")):
            raise RuntimeError("Frozen source bytes changed")
        bindings[name] = {"runtime_sha256": sha(frozen / name), "git_sha256": hashlib.sha256(git_blob).hexdigest(),
                          "runtime_bytes": len(actual), "git_bytes": len(git_blob)}
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none"})
    fig = plt.figure(figsize=(7.2, 3.6), facecolor="white")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set(xlim=(0, 100), ylim=(0, 50))
    ax.axis("off")
    ink, muted = "#182A3A", "#4E6170"
    blue, green, amber = "#1D5D8B", "#246A57", "#80502D"

    def text(x, y, value, *, size=8, color=ink, weight="normal", ha="center", va="center"):
        return ax.text(x, y, value, fontsize=size, color=color, weight=weight,
                       ha=ha, va=va, linespacing=1.22, zorder=4)

    def box(x, y, w, h, *, fill="#F4F7FA", edge="#B4C4CF", dash=False):
        patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.18,rounding_size=0.65",
            linewidth=0.8, facecolor=fill, edgecolor=edge, linestyle="--" if dash else "-", zorder=2)
        ax.add_patch(patch)
        return patch

    def arrow(start, end, *, both=False, color=muted, width=0.85):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="<->" if both else "-|>",
            mutation_scale=8, linewidth=width, color=color, shrinkA=0, shrinkB=0, zorder=3))

    def elbow(points, *, color=muted):
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(points) - 1)
        ax.add_patch(PathPatch(MplPath(points, codes), fill=False, linewidth=0.85, edgecolor=color, zorder=3))
        arrow(points[-2], points[-1], color=color)

    text(50, 48.0, "Native four-arm method and evaluation boundary", size=9, weight="bold")

    box(1.1, 33.0, 19.0, 11.4)
    text(10.6, 40.9, "Native simulated\nuser", weight="bold")
    text(10.6, 36.5, "Private user scenario\nSimulated dialogue", size=7.5, color=muted)

    box(24.0, 33.0, 22.0, 11.4)
    text(35.0, 41.3, "Native assistant", weight="bold")
    text(35.0, 36.8, "Full policy + tool schemas\nComplete message history", size=7.5, color=muted)

    box(50.0, 33.0, 26.0, 11.4, fill="#EDF5FC", edge=blue)
    text(63.0, 41.3, "Matched wrapper", color=blue, weight="bold")
    text(63.0, 37.8, "Pre-read   /   write   /   post-read", size=7.5)
    text(63.0, 35.0, "Actual calls in native history", size=7.5, color=muted)

    box(80.0, 33.0, 18.9, 11.4)
    text(89.45, 41.3, "Native environment", weight="bold")
    text(89.45, 36.8, "Actual tools + state\nNative task initialization", size=7.5, color=muted)
    for start, end in (((20.6, 38.7), (23.5, 38.7)), ((46.5, 38.7), (49.5, 38.7)),
                       ((76.5, 38.7), (79.5, 38.7))):
        arrow(start, end, both=True)

    # Lower-left: matched report/guard interventions, with common predicate
    # explicitly named rather than implied to be independent algorithms.
    box(1.1, 4.4, 52.9, 23.0, fill="#FCFDFE", edge="#B4C4CF")
    text(3.0, 25.2, "Wrapper condition", size=8.5, weight="bold", ha="left")
    text(14.0, 21.9, "Evidence shown to assistant", size=7.5, color=muted, ha="left")
    text(47.3, 21.9, "Guard", size=7.5, color=muted)
    ax.plot([3, 52], [20.4, 20.4], color="#D2DCE4", lw=0.7, zorder=3)
    rows = (("B", "Raw readback", "Off"), ("C", "Direct public-field report", "On"),
            ("R", "ConseqaX 2.1.1 receipt", "Off"), ("G", "ConseqaX 2.1.1 receipt", "On"))
    for y, (arm, report, guard) in zip((18.3, 15.1, 11.9, 8.7), rows):
        text(6.0, y, arm, color=blue if arm in "RG" else ink, weight="bold", size=8.5)
        text(14.0, y, report, size=8, ha="left")
        text(47.3, y, guard, size=8, color=green if guard == "On" else muted)
    text(27.6, 2.8, "C / R / G share field_status; C / G share the same guard.", size=7.5, color=muted)

    # Evaluator-only capture: no return path to the assistant or wrapper.
    elbow([(89.45, 32.5), (89.45, 29.7), (69.4, 29.7), (69.4, 27.4)], color=muted)
    text(78.8, 31.0, "Evaluator capture", size=7.5, color=muted)
    box(59.8, 18.6, 19.2, 8.4, fill="#F1F5F8")
    text(69.4, 24.3, "Sealed execution", size=7.5, weight="bold")
    text(69.4, 21.3, "Tool calls + DB hashes\nSaved native run", size=7.5, color=muted)

    box(82.0, 13.8, 16.9, 13.2, fill="#EFF8F4", edge=green)
    text(90.45, 23.6, "Independent audit", size=8, color=green, weight="bold")
    text(90.45, 18.8, "Full-call replay\nNative ALL grader\nDB + COMM", size=7.5)
    arrow((79.5, 22.8), (81.5, 22.8), color=green)

    box(59.8, 5.0, 19.2, 9.8, fill="#FCF5ED", edge=amber, dash=True)
    text(69.4, 12.6, "Evaluator-only gold", size=7.5, color=amber, weight="bold")
    text(69.4, 8.6, "Reference actions\nExpected DB + criteria", size=7.5, color=muted)
    elbow([(79.4, 9.5), (90.45, 9.5), (90.45, 13.3)], color=amber)
    text(79.4, 2.8, "Gold never enters the wrapper or assistant.", size=7.5, color=muted)

    fig.savefig(output / "native-four-arm-methods.pdf", facecolor="white",
        metadata={"Title": "Native four-arm method and evaluation boundary",
                  "Subject": "Methods only. Current visible fields; origin unknown. No deadline or durability claim."})
    fig.savefig(output / "native-four-arm-methods.svg", facecolor="white")
    fig.savefig(output / "native-four-arm-methods.png", facecolor="white", dpi=300)
    plt.close(fig)
    shutil.copyfile(__file__, output / "plot_native_methods.source.py")
    write_json(output / "source-bindings.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
        "figure_scope": "Methods only; no observations, quantitative results or benchmark outcome claims",
        "frozen_source_commit": PIN, "frozen_source_root": str(frozen), "source_bindings": bindings,
        "plot_source_sha256": sha(__file__), "dimensions_inches": [7.2, 3.6],
        "font_size_range_pt": [7.5, 9], "pdf_fonttype": 42,
        "limitations": ["Current public-field predicates only", "C/R/G use the same field_status helper",
            "C/G use the same guard", "Origin unknown; no temporal durability or deadline claim",
            "Private user scenario is confined to the native user; evaluator gold is not a policy input"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "output/native-method-figure-2026-10-21"))
    parser.add_argument("--frozen-root", default="D:/ConsequaX-Research/paper-frozen-native-2026-10-21")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if args.finalize:
        finalize(output)
    else:
        draw(output, Path(args.frozen_root).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
