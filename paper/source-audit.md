# Primary-source check for the working manuscript

Initial check: 13 October 2026; dated follow-ups below include 20 October 2026.
This is a focused review of the closest overlaps, not a
systematic literature search or independent reproduction. Links identify exact
paper versions. Reported findings remain the authors' claims unless reproduced.

The 18–19 October execution/release rows below are historical checkpoints.
Their “current 2.1.1” and unmeasured-feature descriptions are superseded by the
dated 20 October update at the end of this file, without changing their retained
source pins, exact counts, or original study artifacts.

| Source | Checked material | Consequence for our paper |
| --- | --- | --- |
| [CAR v1](https://arxiv.org/html/2606.08275v1), Jaineet Shah, submitted 6 June 2026 | ArXiv title/author/history and full-text sections 2–4 and limitations | Arbitrary outcome scoring and same-policy contrastive/Shapley replay already exist. Describe our code as an independent adaptation, with a distinct world/evidence boundary and deviations. |
| [CausalLoss-Fin v1](https://arxiv.org/html/2609.25960v1), Abhishek Sharma, submitted 22 September 2026 | ArXiv record, abstract, introduction and related-work discussion | Joint decision/infrastructure interventions and signed financial-effect attribution overlap directly. Its evaluated policies are deterministic procedures. Do not infer stochastic-model results or compare candidate sets unequally. |
| [PCCC v1](https://arxiv.org/html/2606.05263v1), Renwei Meng, submitted 3 June 2026 | ArXiv record and full-text sections 3.2 and discussion | Final verified-success credit under specified interventions and frozen continuation policy is established prior scope. Training credit differs from diagnosis but does not remove the overlap. |
| [Verified Tool Calls v1](https://arxiv.org/html/2608.02645v1), Isham Kalappurackal Mansoor, Abhishek Phadke and Pratip Rana, submitted 31 July 2026 | ArXiv record and full-text sections 4.3–4.5 | Response/effect separation, postconditions, unknown verification and retry controls are foundations. Avoid presenting three-valued verification as unique. |
| [Callability v2](https://arxiv.org/html/2608.23628v2), Zihao Wang, revised 30 August 2026 | ArXiv record, contributions, experiment/analysis and limitations | Operationally indistinguishable states and verification/terminal-claim comparisons overlap. Its model-specific effects warn against assuming uniform gains. |
| [A Value for N-Person Games](https://www.rand.org/pubs/papers/P295.html), Lloyd S. Shapley | RAND publication/citation metadata | The linked RAND report is P-295, 1952. It is not the separate 1953 chapter. Allocation is standard, not introduced here. |
| [Hoeffding, bounded-sum inequalities](https://www.tandfonline.com/doi/abs/10.1080/01621459.1963.10500830) | Publisher-indexed title, author, volume 58(301), pages 13–30 and abstract | Independent bounded-sum concentration is standard. The paper year is 1963; the publisher's online date is 2012. |
| [NIST binomial intervals](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm) | Official handbook definitions | Exact binomial tail inversion and score intervals are existing statistical methods. State their sampling assumptions and precision tradeoffs. |

## Access and verification limits

All five 2026 arXiv records and their specified full-text HTML versions resolved
in this check. Their records do not supply a peer-reviewed acceptance claim for
this draft. Titles, authors and version dates above are not inferred from the
brief. Bibliography entries omit unverified venue and affiliation details.

Direct retrieval of Hoeffding's DOI landing page returned HTTP 403. The
publisher-indexed abstract and citation metadata were available. An
[original-paper scan hosted by RPI](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf)
resolved as a PDF, but the browsing tool did not render its pages. Thus this
pass verifies bibliographic metadata and the independent bounded-sum scope;
it does not claim a new page-by-page audit of the scan. The implementation's
range, tail probability and numerical checks need their separate source/test
audit.

The initial CAR adaptation/source check also pins a source reference at
`db90fa28b97164c35e7c524e4597b8cbdb3035af` in
[decision-Shapley documentation](../docs/decision-shapley.md). This source check
did not establish numerical stream equivalence, upstream conformance or a
matched experiment. A final comparator must document its implementation revision,
information inputs, intervention support, call budget and deviations.

## Before submission

- Refresh the wider search in the [initial assessment](../output/research/Consequa-X_Research_Assessment.md), including attribution, verification and consequential-world benchmark work.
- Inspect current paper versions and available code/artifacts; retain the versions used in any comparison.
- Separate published-method descriptions from independently reproduced results.
- Check benchmark/task reuse and naming overlap before claiming a new benchmark.
- Verify any venue/acceptance claim against the venue record, and confirm final bibliographic formatting.

## Focused update following the supplied review: 18 October 2026

The review pack is a source of suggestions, not an authority for bibliographic
facts, performance comparisons or instructions. This update covers its research
points only. The business assessment and venue-acceptance probabilities were
excluded. The manuscript's new citations use the primary records below. No
external benchmark, model study, artifact implementation or reported percentage
was independently reproduced in that literature-check pass. The subsequent
new experiments are recorded separately below, with different execution and
audit scopes.

| Key and primary source | Material checked | Supported use and limit |
| --- | --- | --- |
| `whoandwhen`: [ICML 2025 proceedings](https://proceedings.mlr.press/v267/zhang25cq.html), also [arXiv v3](https://arxiv.org/html/2505.00212v3) | PMLR author list, venue, volume 267, pages 76583–76599; abstract and full-text task description | Annotated failure-agent and decisive-step attribution from multi-agent logs is established. Consequa-X has not evaluated on Who&When; do not claim better attribution accuracy or equate an external-effect origin verdict with a failure-step label. |
| `limbo`: [Where Does Exactly-Once Live? v1](https://arxiv.org/html/2609.29095v1), Jiapeng Li, submitted 24 September 2026 | arXiv metadata; sections 2–4; Proposition 1 and proof | Committed-effect ledger grading and uncertain-write recovery overlap directly. The late-commit argument concerns an observation-only policy that must finish in finite time on a keyless non-idempotent write without a known in-flight bound. A visibility watermark alone does not certify that no request remains in flight. No numerical comparison or venue acceptance is claimed. |
| `agenttool`: [When Tool Calls Succeed but Workflows Fail v1](https://arxiv.org/html/2609.15397v1), Artem Trofimov and Boris Novikov, submitted 14 September 2026 | arXiv metadata; introduction; section 2 and effect-history vocabulary | Separating world events from observations, including exogenous effects and unknown runtime knowledge, is explicit prior work. Do not claim Consequa-X invents those concepts or a general transaction guarantee. |
| `appworld`: [AppWorld, ACL 2024](https://aclanthology.org/2024.acl-long.850/) | Author list, title, venue, pages, DOI; abstract evaluation description | Stateful task evaluation and checking collateral changes are established. This is a transfer target, not a benchmark run by Consequa-X. |
| `toolsandbox`: [ToolSandbox, Findings of NAACL 2025](https://aclanthology.org/2025.findings-naacl.65/) and [Apple research page](https://machinelearning.apple.com/research/toolsandbox-stateful-conversational-llm-benchmark) | Published citation metadata and abstract | Stateful conversational trajectories and intermediate/final milestone evaluation are established. The final proceedings author list names **Haoping Bai**, whereas the initial arXiv record used Felix Bai; the added bibliography follows the published proceedings. |
| `taubench`: [tau-bench v1](https://arxiv.org/html/2406.12045v1), Shunyu Yao, Noah Shinn, Pedram Razavi and Karthik Narasimhan, submitted 17 June 2024 | arXiv record, abstract, sections 1 and 3 | Final database state is compared with an annotated goal. This checked 2024 paper is historical context; the new maintained-code study below pins a separate implementation and measures only model-free state transfer. |
| Maintained tau3 code: [pinned README](https://github.com/sierra-research/tau2-bench/blob/96a3ef92329baf908ffe9dfe188cea34e8701d2a/README.md), revision `96a3ef92329baf908ffe9dfe188cea34e8701d2a` | Official source README checked for tau3 branding, task updates and canonical `base` split; exact native-source/data/dependency bindings are in the separately frozen transfer protocol | This maintained implementation, not an assumed unchanged 2024 corpus, supplies the new model-free native task/tool study. README metadata alone does not validate its predicates or establish a full reward/leaderboard run. |
| `prov`: [PROV-DM Recommendation, 30 April 2013](https://www.w3.org/TR/2013/REC-prov-dm-20130430/) | W3C status, editors, overview and core relations | Provenance entities, activities, agents and responsibility predate this work. The evidence graph neither establishes causal intervention effects by itself nor claims PROV conformance. |
| `helland`: [Idempotence Is Not a Medical Condition](https://cacm.acm.org/practice/idempotence-is-not-a-medical-condition/), Pat Helland, CACM 55(5):56–65, 2012, DOI 10.1145/2160718.2160734 | ACM-deposited Crossref title/author/volume/pages/year | Foundational context for retry/idempotence semantics. Publisher and Queue full-text routes returned HTTP 403; no page-by-page audit is claimed. This entry identifies the **CACM** version, not the distinct Queue DOI/pagination. |
| `vogels`: [Eventually Consistent](https://cacm.acm.org/practice/eventually-consistent/), Werner Vogels, CACM 52(1):40–44, 2009, DOI 10.1145/1435417.1435432; [author-hosted text](https://www.allthingsdistributed.com/2008/12/eventually_consistent.html) | ACM-deposited Crossref metadata; author-hosted December 2008 discussion of client-visible stale reads | Convergence and immediate read-your-writes guarantees differ. This does not supply an adapter-specific visibility bound. CACM direct full text returned 403; the inspected author-hosted text precedes the cited January 2009 issue. |
| `clopperpearson`: [Clopper and Pearson, Biometrika 26(4):404–413, 1934](https://academic.oup.com/biomet/article-abstract/26/4/404/291538), DOI 10.1093/biomet/26.4.404 | Oxford publisher title, author, date, volume and pagination | Primary bibliographic citation for binomial confidence-limit inversion. Full PDF is access-restricted. Numerical implementation checks remain separate from this metadata audit. |
| `brown`: [Brown, Cai and DasGupta, Statistical Science 16(2):101–133, 2001](https://projecteuclid.org/journals/statistical-science/volume-16/issue-2/Interval-Estimation-for-a-Binomial-Proportion/10.1214/ss/1009213286.pdf), DOI 10.1214/ss/1009213286 | Publisher-indexed abstract and publisher-deposited Crossref citation | Wald binomial coverage problems and alternative proportion intervals are established. These findings do not by themselves prove the behavior of a normal interval on paired replay/Shapley marginals. Direct publisher PDF retrieval did not render through the browsing tool. |
| `betting`: [Waudby-Smith and Ramdas, JRSS-B 86(1):1–27, 2024](https://academic.oup.com/jrsssb/article/86/1/1/7043257), DOI 10.1093/jrsssb/qkad009; [author preprint v7](https://arxiv.org/abs/2010.09686v7) | Publisher-indexed abstract, introduction and summary; issue record; preprint metadata and abstract; deposited citation | Variance-adaptive bounded-mean CIs and time-uniform CSs are relevant alternatives. Issue year is 2024, first online publication 16 February 2023. The review's claimed widths, coverage and detection rates were not reproduced. This citation does not certify a Consequa-X betting implementation, missingness handling, adaptive position selection or simultaneous coverage. |

Crossref metadata was retrieved directly from the DOI records via
`https://api.crossref.org/works/<DOI>` for the CACM, Brown and betting entries.
These are publisher-deposited bibliographic records, not substitutes for full-text
method validation. Search results from third-party aggregators were not used to
support manuscript method or performance claims.

Two additional suggested preprints resolved and were checked narrowly:
[UndoBench v1](https://arxiv.org/html/2610.05622v1) (Dolly Sah, Tanmay Sah, Harshul
Jain and Tanya Sah; submitted 4 October 2026), abstract and limitations; and
[FinalityBench v1](https://arxiv.org/html/2609.04706v1) (Abhishek Sharma; submitted
4 September 2026), abstract and canonical-log/finality-probe sections. They concern
recovery capability and delayed financial finality, respectively. Neither was
run, and their reported episode totals are not interchangeable with independent
task clusters or Consequa-X live-model evidence. They are documented as future
comparison candidates rather than added to inflate the bibliography.

The remaining attribution and transactional-runtime suggestions in the review
were not exhaustively checked. No assertion that all of them exist, match the
listed identifier or have the review's reported performance is carried forward.
The new [positioning notes](related-work-update-2026-10-18.md) supply bounded
manuscript wording and inline bibliography entries for the twelve checked
additions. The earlier nine records remain historical checks, not a fresh audit
of all their current versions.

## New execution and artifact checks, 18–19 October 2026

These are checks of our retained experiments, separate from the literature
metadata/full-text review above. They do not reproduce other papers' empirical
claims or supply independent human validation.

| Record | Checked material and result | Interpretation boundary |
| --- | --- | --- |
| [Same-evidence local judge protocol](../output/matched-trace-judge-2026-10-18/protocol.json), source `be842879dcc0aea09ecf603ed38ecf11e6d55fb0` | [Final raw/fraction audit](../output/matched-trace-judge-audit-2026-10-18/final-raw-and-fractions-audit.md) checks 84 completed one-call inputs, 168 raw request/response files, strict output parsing, the 338-event journal and all method/stratum fractions. Protocol SHA `4439983d1f861eaffaffbc4140750a8a1740653baa8eb7037ae5df600ca074ae`; analysis SHA `117ea516eadd2e171fef5f8ffbe7337f5d70dd32add6647a3ee6496f2a51528f`. | Standalone AI-assisted analysis, not human annotation. One small Qwen3 4B judge, seventeen public-evidence patterns in fourteen cells, post-factual/pre-judge selection. State 9/60 wrong; linked error 0/0 undefined; origin 12/52 wrong assessable claims plus eight definite outputs without assessable gold. Correct unsupported guesses remain separate. |
| [Maintained native state-transfer protocol](../output/tau3-state-transfer-2026-10-18/protocol.json), local source `7f6ef0cea960495d9d07e97c5e02dc31d010f176` | [Final artifact audit](../output/tau3-state-transfer-audit-2026-10-18/final-audit.md) and [task-context check](../output/tau3-state-transfer-audit-2026-10-18/final-findings-context.md) retain all 656 cells from 114 retail/50 airline source tasks and four fixed controls. All 900 action captures are valid and all 900 withheld-readback checks unknown, with zero model calls. Native reference DB match 164/164 and requested fields 223/225 have different targets. | Audit is by the adapter implementation author, separate from execution; it is not independent predicate labeling. Reference-action replay omits autonomous user-agent behavior and non-DB grading. Rejected calls and initial/restored state matches remain in the denominators. Trajectory call logs exclude extra preflight/readback/evaluator work and cannot be called total execution cost. |
| [Pinned native CAR protocol](../output/upstream-car-protocol-2026-10-18/protocol.json), local source `940ebfcc0059c992977dd8e9f112361ff5b31edd`, upstream `db90fa28b97164c35e7c524e4597b8cbdb3035af` | [final independent artifact audit](../output/upstream-car-audit-2026-10-18/final-audit.md) checks all 2,053 manifest-bound files, including 2,048 engine trials, 1,024 semantic group bindings, 393,216 receipt slots, 38 local source blobs and 36 pinned upstream files. All factual traces/call totals agree; 640 eligible pairs have exact point parity, while 384 remain unavailable for both engines. All original summary rows match independently recomputed point, coverage, bias, RMSE and width values. Final audit SHA `fa4e6c08d26db580d001a4b8d7b8fae9ffbd1ac99f072418e66c1e424bc537e8`. | The separate stdlib artifact audit imports no collection/summarizer code and runs no policy/model, but is AI-assisted computational checking, not independent human replication. Engine interval endpoints are read unchanged. No non-budget discrepancy; [collector deviation](../output/upstream-car-audit-2026-10-18/protocol-deviation.md) discloses 64 budget contrastive groups with 2,008 coalesced zero-spend refusals and no per-refused-coroutine IDs. Fresh-call accounting (209,666 per engine) and primary refusal remain intact; no eligible result changes. [results/cost context](../output/upstream-car-audit-2026-10-18/final-findings-context.md) separates native bridge work and concurrent timing from CX world counts; [Figure 9 exports](../output/upstream-car-figures-2026-10-19-v2/README.md) is postcollection presentation. No full CAR reproduction, speed or superiority claim. |
| [Historical 1.1.1 release](https://pypi.org/project/consequa-x/1.1.1/), [retained source/wheel comparison](../output/claude-change-review-2026-10-18/README.md) | Public metadata/documentation release; 37 runtime payloads match 1.1.0 after only the version string is normalized. Core verifier, schema, public API and replay behavior are unchanged. New installed checks are Windows Python 3.11.9/3.12.10 only. | Existing studies remain bound to their frozen 1.1.0 sources. Linux was not rerun for 1.1.1 and macOS has never been tested. Public Git history is not an immutable archival DOI. The later 1.2.0 additions have separate release evidence and were not exercised by frozen 1.1.0 studies. |
| [Historical 1.2.0 release](https://pypi.org/project/consequa-x/1.2.0/), [retained release checks](../output/release-1.2.0-2026-10-19/README.md), [source/wheel comparison](../output/claude-1.2-paper-review-2026-10-19/README.md) | Official PyPI file sizes/hashes match the retained publication record from build source `2afea71f2b8facf90562564aa8cdfee7168bb945`. Recorder, tool capture, generic record verifier/target matcher, MCP wrapper and scripted SQLite example are shipped. Source and wheels retain 36 pre-existing non-initializer runtime payloads byte for byte; three modules are added and the initializer changes version/exports. Local installed checks cover Windows 3.11/3.12 and one emulated Alpine Linux/Python 3.14 guest. | New features were not exercised by the frozen 1.1.0 comparisons. Release conformance is not new accuracy evidence. MCP uses a stand-in, not a live server/SDK; framework-guide snippets are sketches. SQLite uses a scripted policy and simulated times. No general Linux/macOS, autonomous-agent or live-service claim follows. Readback authority/completeness/provenance remain application inputs; no archival DOI or independent human validation is established. |
| [Historical 2.0.0 release](https://pypi.org/project/consequa-x/2.0.0/), [release checks](../output/release-2.0.0-2026-10-19/README.md), [API/source review](../output/claude-2.0-paper-review-2026-10-19/README.md) | Official PyPI artifact sizes/hashes match the retained publication record from build source `87463bf290ff1a1da9b270a7b11f48c512549172`. Breaking schema 1.0 and APIs introduce multi-action traces, explicit time bases, immutable keyword wire records and verifier-owned target matches/findings. Explanations summarize latest recorded evidence/assessment per action. Windows and one emulated Alpine guest have release checks; macOS untested, MCP stand-in only. | These software checks do not relabel the frozen 1.1.0/schema 0.1 studies or establish end-to-end 2.0 equivalence. Static source review is not empirical replication. Multi-action, polling, retry, async and collection features need their own evidence. Framework integrations/composition/OpenTelemetry were deferred from 2.0 to 2.1; source trust remains an application input. |
| Sealed offline 2.0 migration/re-verification of 503 retained factual traces | [Prospective protocol](../output/v2-migration-protocol-2026-10-19/protocol.json), [summary](../output/v2-migration-conformance-2026-10-19/summary.json), [completion receipt](../output/v2-migration-conformance-2026-10-19/completion-receipt.json); source `f64bf49f1a99c22f67d8f393a01dea4e6e22fe04`, protocol SHA-256 `ec736f462be44c1c442bb4a7b9c071006a1ec7e9dd9915f6e0c4c53d7e196e1e` | All 503 migrations preserve the legacy structural projection and round-trip. Fresh old/new canonical state, origin, action linkage, receipt identities and assessment alignment agree on 503/503, including 72 unknown states; full legacy receipts also agree. Exact diagnosis lists change on 275 traces and match on 228; independent arithmetic finds 275 UNASSESSABLE_ASSESSMENT additions and 24 CONSISTENT_OUTCOME removals within those traces. Zero processing errors/new model calls; the original failed slot remains in the 504-slot denominator and historical inputs are unchanged. [Independent saved-artifact audit](../output/v2-migration-audit-2026-10-19/README.md) completed 71,383 checks with zero errors without runner/framework execution; it is computational checking, not human validation. Post-hoc exposed single-action refund conformance is not accuracy, general 2.0-feature validation or validation of 2.1.1; clock origin remains unrecoverable. |
| [Current 2.1.1 release](https://pypi.org/project/consequa-x/2.1.1/), [retained release record](../output/release-2.1.1-2026-10-19/README.md) | [Source/publication review](../output/claude-2.1.1-paper-review-2026-10-19/README.md); current reviewed source `3ff37d57e8f8f09cad8c1e3b15a8377f451a2500`, build source `b73ecd00fc9b4b8b3f9b8182aa8ed652419d7e54`. All 54 wheel payloads match the build. Retained wheel SHA-256 `c86c02aacac53d51bd4335238c4f44b96098db9af354662b23722fab60ed3b98`, source archive `9841f34842c89bbbdffa6776bbc5baf32e2288f25a35cfc1ad1e3f665021fa69`. Retained publication receipts state 19 October 2026, 15:15 UTC; review rechecked local bytes without a current registry query. The 2.1 additions include composite verifiers, several readback sources, OpenTelemetry and optional SDK integrations; schema 1.0 and the 2.0 API remain. | Release engineering and integration checks are separate from scientific evaluation. The measured conformance source is frozen 2.0 and the historical comparison sources remain 1.1.0. No scientific validation of the new 2.1.1 feature set or new accuracy result is supplied. Current retained engineering evidence includes local-Ollama OpenAI Agents/LangChain loops and an authenticated remote-Haiku Claude SDK loop using an in-process MCP server. This does not validate an external/deployed MCP service or a live OTel collector/backend. Default refund verifier class body/records/explain/target/numerical modules match frozen 2.0, but public multi-readback verify/averify wrappers changed; no blanket 2.1.1 conformance follows. Retained core-wheel checks cover Windows Python 3.11.9/3.12.10/3.13.16/3.14.8/3.15.0 and one emulated Alpine 3.24.2/Python 3.14.8 guest; SDK extras/live checks cover Windows 3.12 only and macOS remains untested. The newer-Python full-suite logs have initial demo-data failures and passing reruns at an earlier revision, not uniformly clean full suites at the final release source. |

The old private-repository descriptions are historical visibility statements.
The maintainer made the repository public on 18 October 2026. Current paper
availability text must distinguish accessible committed records from ongoing
uncommitted output and any future immutable archive. No source/test/protocol
hash is silently updated to accommodate a later package version or style edit.
GitHub Actions remains disabled.

## Current controlled evaluation and version boundary — 20 October 2026

This update concerns the [focused paper](conseqax-research.md), not a new
literature search or reproduction of another paper. Its objective endpoints
use SQLite/effect-ledger truth, separately implemented reference rules, and
automated artifact audits. Interpretability, preference, and rationale quality
are outside scope. Historical unblinded rationale annotations, including T15,
are excluded from the current paper and are not empirically validated here.
There is no participant-study or annotation requirement; the [review addendum](recovery-review-response-2026-10-20.md)
records withdrawal of the unused optional follow-up before any annotations.

| Record | Checked material and result | Interpretation boundary |
| --- | --- | --- |
| [Study A prospective protocol](../output/recovery-controller-protocol-2026-10-20/protocol.json), source `22e88498cff0e2afd1549803fb4d9645902e74b9`, package 2.1.1 | Protocol SHA-256 `b5c6a06bf1d758678e4d9890aa66872d4036634e2a4a4fd89626bd710bbc5aaa`; [summary](../output/recovery-controller-study-2026-10-20/summary.json) and [findings](recovery-study-findings-2026-10-20.md) retain all 15,360 complete worlds, zero failed, 3,072 per policy. All recorded endpoint/resource metrics are constant across the 128 seeds in each of 120 case-policy groups. | Effective diversity remains 24 authored cases in 12 purposive families. Deterministic policies and a common local substrate do not establish autonomous-agent, task-population, or independently operated service performance. Readback is an application method on the same SQLite ledger/connection after world advancement, separate from the acknowledgement signal rather than an independent source/connection/trust domain. |
| [Study A paired comparisons](../output/recovery-publication-figures-2026-10-20-v3/paired-contrasts.csv) and [all 12 family contrasts](../output/recovery-publication-figures-2026-10-20-v3/family-safe-recovery-contrasts.csv) | Readback safe recovery is 1,792/3,072 for every policy versus response retry's 1,024/3,072; equal-family difference +0.25 consists of three +1 and nine zero families. Reference-polling reports, actions, endpoints, and retained truth agree in all 3,072 pairs. Polling and one-final-read have identical final reports and physical outcomes, but consume 7,680 versus 3,840 reads with 220 versus 200 ms mean logical decision time. | Strong-reference parity is observed conformance under shared controller logic, not superiority. Study A contains no case where evidence becomes newly admissible only at a later scheduled poll, so its incremental polling result is negative. Logical time is not production latency. Same-connection readback, admitted source semantics, original D/H truth, later R/S recovery, harms, and report correctness retain separate interpretations. |
| [Original-host semantic audit](../output/recovery-controller-audit-2026-10-20/audit-receipt.json), [portable artifact audit](../output/recovery-portable-audit-2026-10-20/portable-audit-receipt.json), and [packaging deviation](../output/recovery-artifact-finalization-2026-10-20/finalization-record.json) | Both audits passed, queried all 15,360 retained SQLite snapshots read-only, and recomputed the summary. Finalization-record SHA-256 `26fabbec4c16af115ad367086efd247e0660af801f0290fe57fa4265a84440a0` records preservation of every existing artifact byte and creation only of the absent terminal manifest/receipt, without rerunning worlds or regenerating the summary. | The original runner's exit status and termination cause remain unknown; completion time denotes packaging. Separate auditor code was authored within the same AI-assisted workflow, not external replication. Portable rechecking omits original live-host checks and does not prove authenticity, first-run exclusivity, or absence of earlier tampering/off-record activity. |
| [Study B registered availability protocol](../output/recovery-availability-protocol-2026-10-20/protocol.json), source `d805b3e3560c05ee0a7efd02a80fc18503c6ee05`, package 2.1.1 | SHA-256 `e874c6781aa0dbc8ef682ea0a8d37c25d73cc861dada05fd0379116d4a7f6584`; registered at commit `b937920469285cdd971783fa6cb33216a7e4da13` before execution. All 960 worlds completed normally with zero failed, 192 per policy; the [terminal receipt](../output/recovery-availability-study-2026-10-20/completion-receipt.json) is retained. The [audit](../output/recovery-availability-audit-2026-10-20/audit-receipt.json) passed with all 1,925 artifacts and 960 SQLite snapshots checked, including recorded-host byte verification. | The 64 controlled availability/lag/completeness profiles repeat across three domains; these are not independently sampled tasks. This follow-up was motivated after Study A's negative result. The audit verifies retained consistency, not original-runtime attestation, source authentication, or independent external replication. |
| [Study B full-grid coverage analysis](../output/recovery-availability-audit-2026-10-20/coverage-analysis.json) and [raw summary](../output/recovery-availability-study-2026-10-20/summary.json) | Every policy has 192/192 safe recoveries, one effect per world, no duplicate/unwanted events; physical effect histories agree in all 192 five-arm cells. One-final-read state/linkage correct yield is 3/192 with 189 unknown, 192 reads, mean logical time 150 ms. Polling/reference yield is 81/192 with 111 unknown, 741 reads, mean 224.375 ms. State-only has the same state yield/resources/actions but all 192 linkage claims unknown. Response reports 192/192 correct state/linkage from ACK, zero reads, mean 2 ms, without horizon-qualified evidence. | The polling state-yield gain over one final read is 78/192 = 26/64 profiles = 0.40625, shared by the reference and state-only rule. No physical recovery gain or strong-reference superiority follows. Reference-polling reports, dispatches, and metrics agree. Counts agree with the prospective 1/64 versus 27/64 diagnostic, whose agreement was not an audit pass condition. The uniformly safe design cannot estimate response false-success risk; logical time is not production latency. No confidence interval, p-value, or autonomous-task generalization is inferred from this finite grid. |
| [Published 2.1.2 release](../output/release-2.1.2-2026-10-20/README.md) and [publication receipt](../output/release-2.1.2-2026-10-20/publication.json) | Retained release records bind publication on 20 October 2026 to build `064127ff120abae543abfe69f77e44b03f3b928e`. The current paper's controlled experiments retain their exact 2.1.1 runtime pin; historical 1.1.0 and 2.0 experiments are unchanged. | Engineering installation/integration checks do not expand the scientific evaluation to every release feature, the public blocking polling helper, live provider semantics, or deployed SDK/telemetry services. No blanket cross-version performance equivalence is asserted. |

Broader objective validation remains an extension: actual autonomous-agent
decisions with native benchmark reward and matched classical controls,
independently established adapter predicates, provider finality/idempotency and
service ground truth, and a defensible population-sampling design. More local
seeds cannot supply those claims. Methodological novelty, immutable archival
access, author/contact metadata, and the selected venue's requirements remain
open questions or submission preparation, not a requirement to run a participant
study. GitHub Actions remains disabled.

### Primary-source recheck — 21 October 2026

The official arXiv version histories and versioned full texts were rechecked
for [Verified Tool Calls v1](https://arxiv.org/abs/2608.02645v1),
[Callability Is Not Operability v2](https://arxiv.org/abs/2608.23628v2),
[agent-tool anomalies v1](https://arxiv.org/abs/2609.15397v1), and
[LIMBO v1](https://arxiv.org/abs/2609.29095v1). Current titles/authors are correct.
Submission/version dates are 31 July, 30 August, 14 September and 24 September
2026 respectively. The July date for the first paper follows its submission
history despite the August identifier. These are preprints, not asserted
peer-reviewed results. The manuscript's narrow response/state, observation,
interface-ambiguity and late-commit boundary summaries follow their full texts;
this is source inspection rather than independent reproduction.

The pinned maintained benchmark's README uses tau3 branding; its pyproject
identifies Python package tau2 1.0.1. Native reward implementation confirms
required DB/communication multiplication and vacuous empty communication
criteria. The prospective metadata erratum and shared native C/G predicate
arithmetic are disclosed in the current methods documents. No new native
pilot score is added by this bibliographic check.
