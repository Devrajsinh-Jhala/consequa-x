# Paper-impact review of the 1.1.1 changes

Read-only comparison of `940ebfcc0059c992977dd8e9f112361ff5b31edd` through
`27b95a1d84d98b66a047d8891056f90b1c54946d`, performed 18 October 2026.
The machine-readable [review](review.json) records source, wheel and metadata
checks. No package, paper, release, website or workflow settings were changed
by this review.

## Core behavior is unchanged

Both source revisions contain the same 37 runtime payload paths. The only
changed runtime file is `src/consequa_x/__init__.py`, whose sole difference is
the version string `1.1.0` to `1.1.1`. The public export list, verifier, schema,
policy, replay, graph and report implementations are unchanged. Dependencies,
Python minimum and CLI entry points are unchanged.

The retained 1.1.0 and 1.1.1 wheels independently confirm the same result:
37 package payload members each; only `consequa_x/__init__.py` differs; replacing
only that version string removes every runtime-payload difference. This is a
byte/source comparison, not new empirical accuracy or human validation.

[PyPI's official 1.1.1 page](https://pypi.org/project/consequa-x/1.1.1/)
confirms the published release and artifact hashes. Its
[local release record](../release-1.1.1-2026-10-18/README.md) reports installed
Windows checks on Python 3.11.9 and 3.12.10. Linux was not rerun for 1.1.1;
macOS has never been tested; formal report browser QA was not rerun. Do not
turn unchanged code into a claim of new platform validation.

## Paper updates needed

The current software/availability paragraphs in the IEEE source, Markdown
manuscript and paper README still cite only 1.1.0 and call the main repository
private. A read-only GitHub API check confirmed it is now public and GitHub
Actions remains disabled. The artifact citation and review-response rows T9
and T20 need corresponding current-status updates. Historical source pins,
protocol wording and study-specific use of 1.1.0 must remain unchanged.

A public mutable repository makes its committed content available; it does
not establish an immutable archive DOI or publish still-uncommitted study
outputs. The paper should describe the actual committed evidence inventory
and any separately prepared archival release precisely.

The CAR runner is unchanged, but its frozen inputs include the version file
and a test file whose lambda was replaced by an equivalent named helper.
Their byte changes invalidate the old protocol on current main despite no
algorithm change. Run that protocol in the separate frozen `940ebfc` worktree;
do not reseal it or silently update its hashes. No frozen worktree was edited
by this review.

The new product roadmap keeps `TraceRecorder`, `RecordVerifier`,
`RecordTargetMatcher`, `capture_tool`, the SQLite agent-loop example, MCP and
framework wrappers **planned** for 1.2. They are not current paper features or
completed validation. The new website inspector uses recorded package output
on synthetic scenarios; it adds no local-model or real-service study evidence.

## Research artifact workflow note

The main snapshot-integrity helper recognized the historical `artifacts`,
`cases` and Render export manifest formats. The new CAR completed manifest uses
a `schema` plus `files` mapping. A separately authorized, main-only companion
patch adds that format, completion/inventory checks and fixtures rejecting
changed gzip payloads, omitted trials, incomplete status and escaping paths.
All 57 snapshot tests and lint passed. This changes no running frozen CAR
source or tests. CI configuration also adds a macOS matrix entry, but its sole
trigger remains manual and repository Actions is disabled.
