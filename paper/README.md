# Consequa-X protocol and software paper

[consequa-x-ieee.tex](consequa-x-ieee.tex) is the complete generic IEEE conference
source. [manuscript.md](manuscript.md) presents the same paper as readable
Markdown, with links to evidence. The format uses `IEEEtran` in conference mode,
two columns, numbered references, equations and compact result tables. The
maintainer requested IEEE formatting; a specific conference or journal has not
been selected. No affiliation is inferred.

The compiled [six-page paper](../output/pdf/Consequa-X_IEEE_Paper.pdf) is ready
for maintainer review. Its [PDF quality receipt](../output/pdf/qa.json) records
successful compilation, AI-assisted visual inspection of all six pages,
embedded fonts and checks for clipping, missing characters and unresolved
references. The PDF was built from frozen source revision
`01d0709ad98acf27c4e12c0899208c28417d46a9`; its recorded SHA-256 is
`6b22124d81b17d0d0e2608183cfd8fc015449d912fc87340e82a3f1a67899a98`.
This artifact check does not replace final independent human checking or
establish venue-specific submission compliance.

The paper's contribution is the implemented evidence/intervention protocol and
its audited behavior. It describes existing contrastive and Shapley methods as
adaptations, states their assumptions, and reports conservative uncertainty's
precision costs. It makes no claim of a new estimator or demonstrated superiority
over an equally informed baseline. Broader held-out comparison is future work,
not an unfinished section that the current paper treats as a result.

Completed evidence includes the original 1,280-trial calibration, the separately
frozen 384-trial shared-draw comparison, the physical refund interaction
enumeration, 2,048 repeated physical-sampling trials and the 24-episode
local-model validation. The repeated sampler retained 655,360 branches and
628,535 scripted calls, with zero model or additional comparison calls. Its
all-eight-case result table reports availability and reference eligibility
alongside interval coverage, width and detection or false-flag counts. The
standalone saved-evidence audit passed 44,698,925 assertions and checked
4,210 full traces without importing the framework implementation or making
generation calls. The
local-model validation used 59 calls;
zero definite statuses for the revised profile leaves its conditional
contradiction rate undefined. Separate rationale labels came from an unblinded
annotation pass in the AI-assisted development workflow; independent human
verification and inter-rater reliability are not established. Reusable
application verification and graph
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
- [Repeated physical sampling](../output/interaction-sampling-2026-10-15/README.md),
  [precollection protocol](../output/interaction-sampling-2026-10-15/protocol.json),
  [all summary rows](../output/interaction-sampling-2026-10-15/summary.json) and
  [installed checkpoint](../output/interaction-sampling-checkpoint-2026-10-15/checkpoint.json):
  all trials/slots, separate strict/on-reach games and refusal denominators.
- [Repeated-sampling audit](../output/interaction-sampling-audits-2026-10-15/independent.json)
  and [derived findings](../output/interaction-sampling-findings-2026-10-15/FINDINGS.md):
  the audit binds the frozen revision and sealed manifest; complete CSV/JSON
  analysis remains outside that original collection.
- [Frozen local-model proposal](protocol-next-validation.md) and
  [completed findings](../output/local-validation-2026-10-14/FINDINGS.md):
  unchanged source/model/prompt identities and all outcome denominators.

The source uses an inline `thebibliography` so a standalone compiler does not
depend on a separate bibliography build. The companion BibTeX file preserves
full metadata for a future venue template. The linked PDF has completed
compilation and artifact checks; any later source edits require a new build
and visual review. Venue selection, independent human checking, reviewer-access
arrangements and actual submission remain maintainer steps. No acceptance is
claimed. GitHub Actions is not used for this work.
