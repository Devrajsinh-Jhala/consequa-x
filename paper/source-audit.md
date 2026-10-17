# Primary-source check for the working manuscript

Checked 13 October 2026. This is a focused review of the closest overlaps, not a
systematic literature search or independent reproduction. Links identify exact
paper versions. Reported findings remain the authors' claims unless reproduced.

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

The CAR adaptation also pins a source reference at
`db90fa28b97164c35e7c524e4597b8cbdb3035af` in
[decision-Shapley documentation](../docs/decision-shapley.md). This source check
does not establish numerical stream equivalence, upstream conformance or a
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
was independently reproduced in this pass.

| Key and primary source | Material checked | Supported use and limit |
| --- | --- | --- |
| `whoandwhen`: [ICML 2025 proceedings](https://proceedings.mlr.press/v267/zhang25cq.html), also [arXiv v3](https://arxiv.org/html/2505.00212v3) | PMLR author list, venue, volume 267, pages 76583–76599; abstract and full-text task description | Annotated failure-agent and decisive-step attribution from multi-agent logs is established. Consequa-X has not evaluated on Who&When; do not claim better attribution accuracy or equate an external-effect origin verdict with a failure-step label. |
| `limbo`: [Where Does Exactly-Once Live? v1](https://arxiv.org/html/2609.29095v1), Jiapeng Li, submitted 24 September 2026 | arXiv metadata; sections 2–4; Proposition 1 and proof | Committed-effect ledger grading and uncertain-write recovery overlap directly. The late-commit argument concerns an observation-only policy that must finish in finite time on a keyless non-idempotent write without a known in-flight bound. A visibility watermark alone does not certify that no request remains in flight. No numerical comparison or venue acceptance is claimed. |
| `agenttool`: [When Tool Calls Succeed but Workflows Fail v1](https://arxiv.org/html/2609.15397v1), Artem Trofimov and Boris Novikov, submitted 14 September 2026 | arXiv metadata; introduction; section 2 and effect-history vocabulary | Separating world events from observations, including exogenous effects and unknown runtime knowledge, is explicit prior work. Do not claim Consequa-X invents those concepts or a general transaction guarantee. |
| `appworld`: [AppWorld, ACL 2024](https://aclanthology.org/2024.acl-long.850/) | Author list, title, venue, pages, DOI; abstract evaluation description | Stateful task evaluation and checking collateral changes are established. This is a transfer target, not a benchmark run by Consequa-X. |
| `toolsandbox`: [ToolSandbox, Findings of NAACL 2025](https://aclanthology.org/2025.findings-naacl.65/) and [Apple research page](https://machinelearning.apple.com/research/toolsandbox-stateful-conversational-llm-benchmark) | Published citation metadata and abstract | Stateful conversational trajectories and intermediate/final milestone evaluation are established. The final proceedings author list names **Haoping Bai**, whereas the initial arXiv record used Felix Bai; the added bibliography follows the published proceedings. |
| `taubench`: [tau-bench v1](https://arxiv.org/html/2406.12045v1), Shunyu Yao, Noah Shinn, Pedram Razavi and Karthik Narasimhan, submitted 17 June 2024 | arXiv record, abstract, sections 1 and 3 | Final database state is compared with an annotated goal. Cite this inspected 2024 preprint without inferring later venue metadata or claiming a tau2-bench run. |
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
