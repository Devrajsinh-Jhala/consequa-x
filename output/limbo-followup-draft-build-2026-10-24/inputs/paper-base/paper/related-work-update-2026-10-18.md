# Focused related-work update, 18 October 2026

This check addresses the supplied review's research suggestions. It excludes its
business assessment. A reference resolving establishes neither correctness nor an
independent reproduction. No numerical result from the review was adopted.

## Suggested manuscript positioning

The initial literature-positioning pass did not run the referenced methods.
The subsequently completed local-judge and maintained task/tool experiments
are identified explicitly below. The subsequently completed native CAR
comparison now has a final independent artifact audit; it supports the bounded
scripted compatibility claim below, not reproduction of CAR-paper results.

**Attribution and evidence.** Who&When studies attribution of a failed multi-agent
run to an agent and decisive step from annotated logs (`whoandwhen`). That task
differs from checking a particular external effect using an independent witness.
W3C PROV-DM already represents entities, activities, agents and responsibility
(`prov`); Consequa-X is not a new general provenance model or a PROV conformance
implementation. Its narrower contribution is an executable contract separating
state satisfaction, origin evidence and report alignment, with explicit refusal
when the required evidence is unavailable.

**Effects and recovery.** Trofimov and Novikov already separate external events
from runtime observations, including exogenous effects (`agenttool`). LIMBO grades
committed-effect histories and analyzes late commits (`limbo`). Consequently,
response/effect separation, external-actor effects and effect ledgers should not
be claimed as new concepts here. Our study tests a particular evidence and replay
protocol; it does not establish a safer recovery controller. LIMBO's late-commit
argument also means that polling to a declared visibility watermark cannot
guarantee exactly-once execution of a keyless, non-idempotent write with unbounded
in-flight time. Idempotence and stale-read semantics are established systems
concerns (`helland`, `vogels`).

**Evaluation scope.** AppWorld uses state-based task tests that also inspect
unintended changes; ToolSandbox evaluates stateful trajectories and intermediate
milestones; tau-bench compares final database state with an annotated goal
(`appworld`, `toolsandbox`, `taubench`). These establish world-state evaluation as
prior work. Our three-decision scripted refund simulator remains a controlled
mechanism audit. A separate model-free transfer study now executes maintained
tau3 retail/airline tools and the native DB-evaluator component under a pinned
source revision. It replays reference actions and fixed controls, rather than
running an autonomous agent and simulated user. It therefore supplies neither
the full native reward nor a pass@k, published-agent comparison or production
payment result. AppWorld and ToolSandbox remain unexecuted transfer candidates.

**Intervals.** Clopper--Pearson's binomial inversion supplies a primary citation
for exact binomial limits (`clopperpearson`). Brown, Cai and DasGupta document
erratic Wald coverage for binomial proportions (`brown`); their result does not
by itself prove undercoverage for paired Shapley marginals. Waudby-Smith and
Ramdas develop variance-adaptive bounded-mean intervals and time-uniform
confidence sequences (`betting`). Such intervals are a relevant planned
comparator, not an implemented result in this revision. Any implementation must
declare the independent sampling unit, predictable betting strategy and stopping
rule; rescaling bounded paired marginals alone does not validate a selective
complete-case sample or simultaneous position selection. The review's claimed
widths, detection rates and replay-budget savings remain unverified.

## New comparative evidence and its boundary

The [same-evidence judge](../output/matched-trace-judge-analysis-2026-10-18/analysis.md)
and [standalone audit](../output/matched-trace-judge-audit-2026-10-18/final-raw-and-fractions-audit.md)
address interpretation of an identical public contract/readback/provenance
view. All 84 selected inputs received one completed Qwen3 4B output. The judge
made nine wrong state claims among sixty definite state outputs, abstained on
every linked target, and made twelve wrong origin claims among fifty-two with
assessable gold. Eight further definite origin outputs have unassessable gold.
Hindsight correctness and public-source qualification remain separate: eight
correct state and sixteen correct origin guesses lack that qualification.
The equally informed independent reference and Consequa-X remain exactly equal.
This does not reproduce Who&When's agent/step attribution task or establish
general LLM-judge inferiority. The 84 selected traces contain seventeen public
evidence patterns in fourteen fixed cells, with one judge family overlapping
some generators. Saved-data analysis is not independent human annotation.

The [maintained source README](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/README.md)
identifies tau3 branding, updated tasks and the canonical `base` split. Our
[frozen transfer protocol](../output/tau3-state-transfer-2026-10-18/protocol.json)
pins that exact commit rather than silently substituting the original 2024
corpus. The [final audit](../output/tau3-state-transfer-audit-2026-10-18/final-audit.md)
retains 656 completed task/control cells across all 114 retail and 50 airline
tasks, with zero model calls. Reference DB self-replay matching is 164/164;
immediate requested-field satisfaction is 223/225. Rejected native calls and
already matching initial fields explain why those targets differ, as retained
in the [task-context review](../output/tau3-state-transfer-audit-2026-10-18/final-findings-context.md).
All 900 withheld-readback checks remain unknown. The adapter-author audit
checks artifacts and interpretations; it is not independently labeled predicate
accuracy. Communication and qualitative reward components, task-policy behavior
and autonomous user-agent interaction remain outside the experiment.

For CAR, executed same-policy interventions and allocation already belong to
the authors' method. The new
[prospective native comparison](../output/upstream-car-protocol-2026-10-18/protocol.json)
uses unmodified upstream source
[`db90fa28b97164c35e7c524e4597b8cbdb3035af`](https://github.com/jaineet17/causal-agent-replay/tree/db90fa28b97164c35e7c524e4597b8cbdb3035af),
version 0.2.0, through a documented scripted-refund bridge. The
[final independent artifact audit](../output/upstream-car-audit-2026-10-18/final-audit.md) checks all 1,024 paired groups, 2,048 engine files
and 393,216 planned engine-receipt slots, with zero redraws. Factual traces and
fresh-call totals match in every pair. The primary gate admits 640 pairs with
exact point parity and withholds 384 for both engines. No non-budget semantic
discrepancy was found. Native interval endpoints remain upstream outputs; the
audit independently recomputes point, coverage, error and width summaries.
The [results/cost context](../output/upstream-car-audit-2026-10-18/final-findings-context.md) and [Figure 9 exports](../output/upstream-car-figures-2026-10-19-v2/README.md) preserve all 144 coefficient
rows; selecting retry position 1 for the figure was a disclosed postcollection
presentation choice.

Both engines used 209,666 fresh scripted policy calls and zero live models.
The bridge, supplemental endpoint work, native rollout budget and deterministic
reconstruction counters have separate accounting scopes; concurrent per-trial
elapsed sums do not establish intrinsic speed. The
[collector deviation](../output/upstream-car-audit-2026-10-18/protocol-deviation.md) affects 64 native cap-4 contrastive groups: 2,008
zero-spend refusals were coalesced under canonical failed slots, and individual
refused-coroutine identities were not retained. All affected method vectors
are already unavailable, preserving fresh-call caps and every eligible result.
This is a recorded collector limitation, not a prospective protocol amendment.
The comparison establishes scripted same-policy/same-game compatibility and
conditional interval behavior, not full upstream reproduction, new attribution
methodology, independent task generalization or superiority.

Current software availability is also separate from experimental evidence.
The historical [2.0.0 release](https://pypi.org/project/consequa-x/2.0.0/) broke the earlier API:
wire schema 1.0, several actions per trace, a declared time base, deeply
read-only keyword wire records and verifier-owned target matching/findings.
The [API/source review](../output/claude-2.0-paper-review-2026-10-19/README.md)
documents removed matcher interfaces, structured per-action explanation and
the moved research namespace. The frozen 1.1.0 experiments do not establish
end-to-end equivalence of the breaking release. A separate
[sealed offline 2.0 conformance run](../output/v2-migration-conformance-2026-10-19/summary.json)
uses source `f64bf49f1a99c22f67d8f393a01dea4e6e22fe04` under
[protocol](../output/v2-migration-protocol-2026-10-19/protocol.json) SHA-256
`ec736f462be44c1c442bb4a7b9c071006a1ec7e9dd9915f6e0c4c53d7e196e1e`.
All 503 retained traces migrate structurally and agree in fresh canonical state,
origin, action linkage, receipt identity and assessment alignment, including 72
unknown states. The original 504 slots retain the failed slot; zero new model
calls or processing errors occurred. Exact diagnosis-code lists change on 275
traces. The [completion receipt](../output/v2-migration-conformance-2026-10-19/completion-receipt.json)
records unchanged inputs; an [independent artifact audit](../output/v2-migration-audit-2026-10-19/README.md)
completed 71,383 checks with zero errors, using saved artifacts and public-evidence
arithmetic without framework/runner execution. This computational check is not
independent human validation. Exposed single-action refund compatibility is not
accuracy, held-out
generalization or general 2.0-feature validation.

Current software is [2.1.1](https://pypi.org/project/consequa-x/2.1.1/). The 2.1
line adds composite verifiers, several readback sources, OpenTelemetry and optional
SDK integrations, retaining schema 1.0/the 2.0 API. Its
[release record](../output/release-2.1.1-2026-10-19/README.md) and
[current source/publication review](../output/claude-2.1.1-paper-review-2026-10-19/README.md)
are engineering evidence. Scientific validation of those additions is unmeasured;
the completed compatibility arm remains frozen 2.0. Retained actual-model smoke
loops cover OpenAI Agents/LangChain through local Ollama and Claude Agent SDK
through remote Haiku; the latter uses an in-process MCP server. These integration
checks establish no scientific accuracy result, external/deployed MCP-service
validation or live OpenTelemetry collector/backend validation. Public multi-readback
verification wrappers changed after the measured 2.0 source, so schema/API
continuity alone supplies no blanket 2.1.1 conformance result.

The earlier [1.1.1 metadata release](https://pypi.org/project/consequa-x/1.1.1/)
and [its review](../output/claude-change-review-2026-10-18/README.md), plus the
[1.2.0 additive release](https://pypi.org/project/consequa-x/1.2.0/) and
[its review](../output/claude-1.2-paper-review-2026-10-19/README.md), remain
dated checkpoints. Historical study pins and versions stay unchanged.
Release checks cover Windows and one emulated Alpine guest; macOS is untested.
The historical 2.0 MCP check used a stand-in session; later SDK integration
checks belong to the current-release review. The scripted SQLite example and
polling/retry/async/collection APIs are
implemented software, not comparative scientific evaluations. The repository
is public and Actions disabled; immutable archival release and evidence
inventory remain separate. New features do not authenticate readback inputs.

## Ready-to-paste inline IEEE bibliography additions

The keys match the additions in `references.bib`. Retain only items actually
cited in the manuscript. The existing manuscript uses an inline bibliography.

```tex
\bibitem{whoandwhen}
S. Zhang \emph{et al.}, ``Which Agent Causes Task Failures and When? On Automated Failure Attribution of LLM Multi-Agent Systems,'' in \emph{Proc. 42nd Int. Conf. Machine Learning}, PMLR, vol. 267, 2025, pp. 76583--76599. [Online]. Available: \url{https://proceedings.mlr.press/v267/zhang25cq.html}

\bibitem{limbo}
J. Li, ``Where Does Exactly-Once Live? Model, Harness, and Tool-Contract Effects on Duplicate Side Effects in LLM Agents,'' arXiv:2609.29095v1, 2026. [Online]. Available: \url{https://arxiv.org/html/2609.29095v1}

\bibitem{agenttool}
A. Trofimov and B. Novikov, ``When Tool Calls Succeed but Workflows Fail: Anomalies at the Agent-Tool Boundary,'' arXiv:2609.15397v1, 2026. [Online]. Available: \url{https://arxiv.org/html/2609.15397v1}

\bibitem{appworld}
H. Trivedi \emph{et al.}, ``AppWorld: A Controllable World of Apps and People for Benchmarking Interactive Coding Agents,'' in \emph{Proc. 62nd Annu. Meeting Association for Computational Linguistics}, vol. 1, 2024, pp. 16022--16076, doi: 10.18653/v1/2024.acl-long.850.

\bibitem{toolsandbox}
J. Lu \emph{et al.}, ``ToolSandbox: A Stateful, Conversational, Interactive Evaluation Benchmark for LLM Tool Use Capabilities,'' in \emph{Findings of the Association for Computational Linguistics: NAACL 2025}, 2025, pp. 1160--1183, doi: 10.18653/v1/2025.findings-naacl.65.

\bibitem{taubench}
S. Yao, N. Shinn, P. Razavi, and K. Narasimhan, ``$\tau$-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains,'' arXiv:2406.12045v1, 2024. [Online]. Available: \url{https://arxiv.org/html/2406.12045v1}

\bibitem{prov}
L. Moreau and P. Missier, Eds., ``PROV-DM: The PROV Data Model,'' W3C Recommendation, Apr. 30, 2013. [Online]. Available: \url{https://www.w3.org/TR/2013/REC-prov-dm-20130430/}

\bibitem{helland}
P. Helland, ``Idempotence Is Not a Medical Condition,'' \emph{Communications of the ACM}, vol. 55, no. 5, pp. 56--65, 2012, doi: 10.1145/2160718.2160734.

\bibitem{vogels}
W. Vogels, ``Eventually Consistent,'' \emph{Communications of the ACM}, vol. 52, no. 1, pp. 40--44, 2009, doi: 10.1145/1435417.1435432.

\bibitem{clopperpearson}
C. J. Clopper and E. S. Pearson, ``The Use of Confidence or Fiducial Limits Illustrated in the Case of the Binomial,'' \emph{Biometrika}, vol. 26, no. 4, pp. 404--413, 1934, doi: 10.1093/biomet/26.4.404.

\bibitem{brown}
L. D. Brown, T. T. Cai, and A. DasGupta, ``Interval Estimation for a Binomial Proportion,'' \emph{Statistical Science}, vol. 16, no. 2, pp. 101--133, 2001, doi: 10.1214/ss/1009213286.

\bibitem{betting}
I. Waudby-Smith and A. Ramdas, ``Estimating Means of Bounded Random Variables by Betting,'' \emph{Journal of the Royal Statistical Society Series B: Statistical Methodology}, vol. 86, no. 1, pp. 1--27, 2024, doi: 10.1093/jrsssb/qkad009.
```

## Additional suggested papers checked but not added mechanically

- [UndoBench v1](https://arxiv.org/html/2610.05622v1), Dolly Sah, Tanmay Sah,
  Harshul Jain and Tanya Sah, submitted 4 October 2026. The checked abstract and
  limitations distinguish nominal task competence from fault recovery using
  paired trials and state/wire effect oracles. Its principal frozen study is a
  lost-acknowledgment setting; the authors explicitly limit independent task
  cluster count and mutation-boundary coverage. No results were reproduced.
- [FinalityBench v1](https://arxiv.org/html/2609.04706v1), Abhishek Sharma,
  submitted 4 September 2026. Checked sections describe a canonical event log,
  separately faulted views and effect-level financial grading. Its finality
  probes and delayed determination are relevant to future transfer, but this
  revision has not run that benchmark. Its abstract's episode counts must not
  be presented as comparable Consequa-X model evidence.

Other names and identifiers listed in the supplied review were not exhaustively
checked in this focused pass. They are not endorsed by omission or included as
citations solely because the review calls them verified. No venue-fit percentage,
business recommendation or numerical simulation from that document was adopted.
