# Consequa-X protocol and software paper

[consequa-x-ieee.tex](consequa-x-ieee.tex) is the complete generic IEEE conference
source. [manuscript.md](manuscript.md) presents the same paper as readable
Markdown, with links to evidence. The format uses `IEEEtran` in conference mode,
two columns, numbered references, equations and compact result tables. The
maintainer requested IEEE formatting; a specific conference or journal has not
been selected. No affiliation is inferred.

The paper's contribution is the implemented evidence/intervention protocol and
its audited behavior. It describes existing contrastive and Shapley methods as
adaptations, states their assumptions, and reports conservative uncertainty's
precision costs. It makes no claim of a new estimator or demonstrated superiority
over an equally informed baseline. Broader held-out comparison is future work,
not an unfinished section that the current paper treats as a result.

Completed evidence includes the original 1,280-trial calibration, the separately
frozen 384-trial shared-draw comparison, the physical refund interaction
enumeration and the 24-episode local-model validation. The latter used 59 calls;
zero definite statuses for the revised profile leaves its conditional
contradiction rate undefined. A separate rationale reading remains explicitly
single-reader and exploratory. Reusable application verification and graph
witness semantics are described separately from historical experimental code.

Stable Python version 1.0.0 is public on
[PyPI](https://pypi.org/project/consequa-x/1.0.0/); both distribution downloads
and an isolated registry installation were verified on 15 October 2026. The
source distribution includes documentation, examples, tests and audit scripts.
The research repository is now private. Git history, raw evidence and retained
research records are available to authorized collaborators; the paper does not
promise public access to the complete research archive. An immutable archive,
reviewer-access arrangement and final venue-specific requirements remain to be
settled before submission.

- [Evidence ledger](evidence-ledger.md): claim-to-artifact mapping, frozen source
  revisions and limits.
- [Source audit](source-audit.md): focused primary-source checks and access limits.
- [Bibliography](references.bib): inspected versions and standard statistical
  sources, kept alongside the self-contained IEEE reference list.
- [Release readiness](../docs/release-readiness.md): package engineering and
  publication evidence, separate from scientific claims.
- [Stable publication receipt](../output/release-1.0.0-2026-10-15/publication.json)
  and [registry installation](../output/release-1.0.0-2026-10-15/registry-install.json):
  the actual public version, artifact hashes and installed-payload checks.
- [Physical refund enumeration](../output/refund-interactions-2026-10-13/README.md):
  512 retained branches across eight cases and two declared games.
- [Frozen local-model proposal](protocol-next-validation.md) and
  [completed findings](../output/local-validation-2026-10-14/FINDINGS.md):
  unchanged source/model/prompt identities and all outcome denominators.

The source uses an inline `thebibliography` so a standalone compiler does not
depend on a separate bibliography build. The companion BibTeX file preserves
full metadata for a future venue template. A successful PDF compilation and
visual review are required before delivering or attaching a generated PDF.
No page count, submission compliance or acceptance is claimed by the source
alone. GitHub Actions is not used for this work.
