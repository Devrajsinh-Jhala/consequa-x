# Paper figures

The IEEE manuscript embeds the vector PDFs at their full 6.9-inch width.
SVG files preserve editable text; 220-dpi PNGs support Markdown and preview.
Labels are at least 8 points at the embedded size. The four original result
tables remain in the paper.

| Figure | Asset stem | Purpose and scope |
| --- | --- | --- |
| 1 | `diagram-evidence-architecture` | Captured evidence, explicit verifier/target matcher and optional research replay. Evaluator truth stays audit-only; application source trust is an assumption. |
| 2 | `diagram-timeout-retry` | Illustrative timeout-after-commit sequence, comparing duplicate creation with provider-scoped idempotency. Times are illustrative and arrows show event order. |
| 3 | `data-branch-disposition` | All 16 mechanism/game groups and all 655,360 planned slots, with inactive holds shown as a subset of completed branches. Completion does not imply verified success or an available estimate. |
| 4 | `data-interval-tradeoffs` | All eight on-reach global-consequence retry cases, contrasting saved normal/Hoeffding coverage, width and sign detection or false flags. Unavailable/undefined rows have no numerical markers. |

[Diagram provenance](diagram-figures.json) binds the generator, reviewed runtime
sources and all six diagram assets. [Plot provenance](data-figures.json) retains
the 16 plotted coefficient rows, 16 branch groups, original input hashes and all
six plot assets. The original collection remains separate and unchanged.

The data plots use the [sealed repeated-sampling collection](../../output/interaction-sampling-2026-10-15/README.md)
and its [independent saved-evidence audit](../../output/interaction-sampling-audits-2026-10-15/independent.json).
The generator verifies the complete 52-file collection before selecting rows.
It makes no model/policy calls, executes no simulator, recomputes no confidence
intervals and imports no framework implementation. Coverage and flag whiskers
are the saved nominal 95% Wilson uncertainty for repeated-trial rates, not
coefficient intervals or simultaneous bounds. Methods share draws; they are not
independent replications. A/R labels are two counts, available estimates and
population-reference-eligible trials, each out of 128; A/R is not a fraction.

## Reproduce in a new directory

From the repository root, in a separate authoring environment with Matplotlib
installed (retained artifacts used 3.11.2):

```console
python scripts/draw_paper_diagrams.py --output-dir tmp/paper-figures-fresh
python scripts/plot_paper_results.py --output tmp/paper-figures-fresh
```

Each script refuses to overwrite its existing named outputs. Use a fresh
directory for another run. Both can share that directory because their filenames
differ. The conceptual generator requires its destination to stay inside the
repository; the empirical generator refuses output inside the sealed study.
The conceptual script uses an installed serif font and records its selected
font; the retained diagrams use Times New Roman. Font versions and rendering
libraries can affect bytes, so new manifests record actual output hashes.

These tools are optional paper-authoring dependencies. They do not add a runtime
dependency or a visual report feature to `consequa-x==1.0.0`.
