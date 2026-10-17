# Focused related-work update, 18 October 2026

This check addresses the supplied review's research suggestions. It excludes its
business assessment. A reference resolving establishes neither correctness nor an
independent reproduction. No numerical result from the review was adopted.

## Suggested manuscript positioning

The following is proposed prose, not a claim that these comparisons were run.

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
prior work and provide future transfer targets. Our three-decision scripted
refund simulator is a controlled mechanism audit, not an evaluation on any of
those benchmarks, a production payment API or their task distributions.

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
