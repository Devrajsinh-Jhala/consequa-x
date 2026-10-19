# Claude 1.2 changes: implications for the paper

Reviewed on **19 October 2026, Asia/Calcutta**. This is a read-only source and publication review; no package, website, workflow, or experimental source was changed, and no tests, model calls or new experiments were run. `review.json` retains full commit identities, source blob comparisons, wheel comparison, publication evidence, and the checks made for this review.

## Findings

- Reviewed `origin/main` at `53c09ae`, from the paper worktree at `eeda887`. Current **1.2.0 is publicly published**, not merely planned. The official [version-specific PyPI JSON](https://pypi.org/pypi/consequa-x/1.2.0/json) independently matches both artifact sizes and SHA-256 hashes in the retained publication record. The public release was uploaded on 18 October 2026 at 19:02 UTC, which is **19 October 2026 at 00:32 IST**.
- Compared with frozen experimental source `940ebfc`, **36 of 37 existing runtime payload files are byte-identical** in both source and distributed wheels. The sole changed existing file is `__init__.py`: version and additive exports. Three runtime files were added. No existing public export was removed. Models and bundled schema, refund verifier, graph, explanation, report, policies, replay, attribution and research algorithms remain byte-identical at their existing paths. This is a byte/source statement, not a claim that every behavior of the new import surface was independently retested here.
- Newly shipped: `TraceRecorder`; `Attempt` and the `attempt()` context manager; synchronous `call()`/`capture_tool`; `RecordVerifier`/`RecordTargetMatcher`; `consequa_x.mcp_capture.call_mcp_tool`; and `examples/agent_loop_sqlite.py`. MCP capture is imported from its submodule, not exported at the package root.
- The recorder captures application-supplied context, decisions, dispatches, responses, assessments and readback; it does not automatically observe arbitrary agents. The generic record predicate checks exact JSON field values, scope, timing, persistence and count, with origin reported separately. Readback trust/completeness/provenance still belong to the application.
- The SQLite example uses real local database writes and a separate read-only connection, but a scripted policy and simulated times. Its three modes are timeout after commit, other actor, and stale readback. This is a runnable integration example, not an autonomous-agent or real-payment experiment.
- The MCP wrapper is SDK-free and async, using the `session.call_tool` shape. Release tests use a stand-in session. Framework guide snippets are sketches, not implemented, live-validated framework adapters.
- Retained 1.2.0 release checks report 1,839 passed, 21 skipped and 240 subtests, without GitHub Actions. Installed checks cover Windows Python 3.11.9/3.12.10 and **one emulated QEMU Alpine Linux 3.24.2/Python 3.14.8 guest**, plus a Windows sdist and registry install. macOS remains untested. These are release conformance receipts, not research accuracy results. This review did not rerun them.
- GitHub's read-only API reports the repository **public** and Actions **disabled** (`enabled:false`). The current docs URL returned HTTP 200 and contains 1.2.0, `TraceRecorder` and `RecordVerifier`. The retained deployment record says Render currently deploys from the `consequa-x-site` mirror of this repository's website bytes; do not claim it is directly connected to the main repository. The pre-upload docs/support gate was pending then and completed after publication; keep both timestamped receipts intact.

## Wording for both manuscripts

Replace the current availability/version paragraphs, including the statement that 1.2 is planned, with the following. Convert Markdown links to the existing LaTeX citation/URL style in the IEEE source.

> Consequa-X 1.2.0 is publicly available under MIT on [PyPI](https://pypi.org/project/consequa-x/1.2.0/), with source, issues and the retained research records in the [public repository](https://github.com/Devrajsinh-Jhala/consequa-x). The release record binds the wheel and source-distribution hashes to build source `2afea71f2b8facf90562564aa8cdfee7168bb945`. Version 1.2 adds application-side trace recording, tool-call capture, a generic record verifier and target matcher, an MCP call wrapper, and a scripted local SQLite integration example. These additions were not exercised by the paper's frozen experiments.
>
> The matched-judge, native benchmark-transfer and native CAR comparisons retain their original version 1.1.0 source and protocol pins. Earlier studies retain their own original version and source receipts. Relative to frozen source `940ebfc`, all 36 existing runtime payload files outside `__init__.py` remain byte-identical in version 1.2.0; the changed initializer adds exports and a version label, and three modules are new. This comparison preserves the distinction between the evaluated artifact and later product features; it does not relabel or rerun the studies.
>
> Version 1.2.0 has retained installed-artifact checks on Windows Python 3.11/3.12 and one emulated Alpine Linux/Python 3.14 guest. macOS is untested; the MCP check uses a stand-in session. Readback authenticity, completeness and provenance remain application responsibilities. The source repository is public, while an immutable archival DOI and independent human review remain separate unfinished steps. GitHub Actions remains disabled.

If the manuscript needs a shorter version, keep the first paragraph and the first sentence of the second, with platform details only in the paper README. Avoid turning the release test count into a new research evaluation subsection.

For the artifact bibliography entry use **version 1.2.0, 19 October 2026** with the version-specific PyPI URL. Keep separate experimental pins and historical version-specific artifact links unchanged.

## Wording for paper README

> The current public release is [1.2.0](https://pypi.org/project/consequa-x/1.2.0/). Its [release record](../release-1.2.0-2026-10-19/README.md) retains the publication hashes and local installed-artifact checks. The new recorder, tool-call capture, generic record verifier/target matcher, MCP wrapper and SQLite example are shipped integration features; the new frozen comparisons still use their original 1.1.0 source/protocol pins and do not evaluate these additions. Earlier studies retain their original versions and sources. The [source and issue tracker](https://github.com/Devrajsinh-Jhala/consequa-x) are public. Actions remains disabled.

The release-record link above is relative to this review directory; **from `paper/README.md` use `../output/release-1.2.0-2026-10-19/README.md`**. State platform coverage as Windows 3.11/3.12 plus one emulated Alpine/Python 3.14 guest, not general Linux validation. Replace the stale 'planned 1.2' sentence; preserve the historical 1.1.0/1.1.1 receipts and their narrower checks.

## Row for evidence ledger

| Claim | Evidence | Boundary |
| --- | --- | --- |
| Current 1.2.0 release, public source and integration additions | Version-specific PyPI metadata; `output/release-1.2.0-2026-10-19/{README.md,publication.json,checks.json,site-publication.json}`; this review | Source `2afea71f2b8facf90562564aa8cdfee7168bb945`. Recorder, tool capture, generic record verification, MCP wrapper and scripted SQLite example are implemented. All 36 old runtime payloads except the version/export initializer are byte-identical to frozen `940ebfc`; three modules are new. Frozen 1.1.0 experiments did not exercise additions. Release checks cover Windows and one emulated Alpine guest; MCP uses a stand-in, macOS untested. Public source is not an archival DOI. Actions disabled. |

Rename the existing 'Current stable 1.1.1' row to **'Historical 1.1.1 metadata release'**, keep its evidence as dated history, and remove 'planned 1.2' from that row. Do not alter historical visibility/release receipts.

## Row for source audit

| Source | Supports | Does not support |
| --- | --- | --- |
| PyPI Consequa-X 1.2.0; retained 19 October release receipts; this source/wheel comparison | Current MIT publication and additive capture/generic-verification APIs; byte identity of the 36 pre-existing non-initializer runtime files; local installed checks on Windows and one emulated Alpine guest; public repository and disabled Actions | New empirical validation of recorder/generic record/MCP integrations; live MCP or framework compatibility; autonomous SQLite agent performance; all-Linux/macOS support; independent human validation; broad accuracy/speed/superiority claims or an immutable archival DOI |

Keep the earlier 1.1.1 comparison as historical evidence, rather than silently overwriting it with 1.2 results. All study manifests, model digests, dependency pins and frozen sources remain unchanged.
