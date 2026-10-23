"""Draw the actual native study boundary; contains no benchmark outcome data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 8.1,
                         'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none'})
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    ax.set(xlim=(0, 10), ylim=(0, 6.2))
    ax.axis('off')

    def box(x, y, w, h, title, detail, *, color='#e7f0f1', edge='#51727b'):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
            boxstyle='round,pad=0.04,rounding_size=0.08', linewidth=.9,
            facecolor=color, edgecolor=edge))
        ax.text(x + w/2, y + h*.72, title, ha='center', va='center',
                fontweight='bold', color='#163f52', fontsize=8.5)
        ax.text(x + w/2, y + h*.30, detail, ha='center', va='center',
                linespacing=1.3, fontsize=7.6, color='#243d46')

    def arrow(a, b, *, color='#51727b', style='-'):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=9,
            linewidth=.95, color=color, linestyle=style, connectionstyle='arc3'))

    box(.3, 5.15, 9.4, .82, 'One local Qwen3 4B model; full native history and schemas',
        'Same limits and public capabilities; fresh matched world for each arm')
    centers = [1.35, 3.78, 6.21, 8.64]
    titles = ['Vanilla', 'SDK retry3', 'Native guard', 'ConseqaX guard']
    details = ['Direct tool dispatch', 'Native retries and backoff',
               'Native recovery control law', 'Same guard; actual SDK receipts']
    for x, title, detail in zip(centers, titles, details):
        box(x-1.03, 3.82, 2.06, .87, title, detail,
            color='#d5e9e8' if title == 'ConseqaX guard' else '#eef3f4')
        arrow((x, 5.15), (x, 4.72))
        arrow((x, 3.78), (x, 3.3))
    box(.3, 2.35, 9.4, .91, 'Unchanged LIMBO runtime, services and fault semantics',
        'Actual execute / public verify / explicit waits; late effects settle before native grading')
    box(.3, .92, 5.65, .94, 'Saved execution and native evaluator',
        'Calls, final world, effect ledger, native TS / EOS and separate harm metrics', color='#f1f0e9')
    box(6.35, .92, 3.35, .94, 'Independent offline audit',
        'Native guard + effect replay\nReceipt mapping recomputation', color='#f1f0e9')
    arrow((3.1, 2.32), (3.1, 1.89))
    arrow((5.99, 1.39), (6.31, 1.39))
    ax.plot([.15, 9.85], [2.08, 2.08], color='#967d46', linestyle=(0, (4, 3)), linewidth=.9)
    ax.text(9.7, 2.12, 'Evaluator-only state stays below this boundary',
            ha='right', va='bottom', color='#756139', fontsize=7.4)
    ax.text(5, .43, '12 base instances  |  24 clean/fault conditions  |  96 planned slots',
            ha='center', fontweight='bold', color='#163f52', fontsize=8.4)
    ax.text(5, .13, 'Methods diagram only. No oracle, human participation or benchmark results are depicted.',
            ha='center', color='#4a5d64', fontsize=7.5)
    fig.subplots_adjust(left=.01, right=.99, top=.99, bottom=.01)
    for extension in ('pdf', 'svg', 'png'):
        fig.savefig(out / ('limbo-native-methods.' + extension), dpi=240, bbox_inches='tight')
    plt.close(fig)
    (out / 'make_limbo_methods_figure.source.py').write_bytes(Path(__file__).read_bytes())
    files = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
             for p in sorted(out.iterdir()) if p.is_file()}
    (out / 'manifest.json').write_text(json.dumps(files, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'data_free_methods_diagram': True}))


if __name__ == '__main__':
    main()
