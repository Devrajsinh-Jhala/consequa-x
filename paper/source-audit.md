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
