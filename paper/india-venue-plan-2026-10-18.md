# India conference strategy and scientific readiness

Checked on **18 October 2026, Asia/Kolkata**. This is a research and submission
planning note, not a claim of acceptance, a conference ranking, or a submitted
paper. The supplied review is advice to assess; its business section and
acceptance probabilities are excluded. No organizer was contacted, submission
made, fee paid, model called, or GitHub Actions run for this note.

## Recommended direction

For the full paper, the strongest topical fit found in this focused India-hosted
search is **Innovations in Software Engineering Conference (ISEC)**: the work is
about engineering and evaluating agent software, debugging ambiguous execution,
and making verification boundaries explicit. Its 2027 main research deadlines
have already passed. Preserve the full research objective and develop the
comparative evidence rather than presenting an available demo/workshop slot as
equivalent to main-track research acceptance. No future ISEC research deadline is
assumed announced.

There are two distinct current possibilities if an earlier India presentation is
useful: an ISEC tool demonstration by 23 October, or an ISEC GenAI&SE workshop
paper by 8 November. These require separate, much shorter submissions and a
decision about archival overlap with the eventual full paper. They are options
to evaluate, not selected or submitted venues. Venue fit below is our inference
from official scope, not an organizer's endorsement.

## Official calls and deadline status

| Route | India location and status as checked | Fit and decision |
| --- | --- | --- |
| **ISEC 2027 research track** | Mumbai. Both rounds closed: 26 June and 25 September 2026, AoE. | Best full-paper scope match in this search; prepare research for a subsequent verified call. Regular papers use ACM `sigconf,review,anonymous`, at most 10 main-text pages including appendices/figures, excluding references. This is not the current IEEE manuscript format. [Official research CFP](https://conf.researchr.org/track/isec-2027/isec-2027-research-papers). |
| **ISEC 2027 Demos and Tools** | Mumbai. Deadline **23 October 2026, AoE**; decision 25 November; camera ready 18 December. | Credible option for the released framework and reproducible evidence inspection, distinct from a full research result. Maximum four pages including references, ACM single-column, plus a 5–10 minute video. [Official demo CFP](https://conf.researchr.org/track/isec-2027/isec-2027-industry-innovation-track). |
| **GenAI&SE: Co-Pilots to Actors, at ISEC 2027** | SPIT, Mumbai; workshop 18 February 2027. Submission **8 November 2026**; ISEC's workshop calendar specifies AoE. | Strong workshop fit for trusted agent operation and AgentOps. Research/case/evaluation papers up to four ACM-format pages; shorter demo/extended abstracts up to 500 words. Decision 8 December; camera ready 14 December. [Workshop CFP](https://genai4se.github.io/ISEC27-Workshop/), [official host and dates](https://conf.researchr.org/track/isec-2027/isec-2027-tutorials-and-workshops). |
| **COMSNETS 2027 SysAI workshop** | Bengaluru, conference 5–9 January 2027. Published workshop deadline **16 October 2026, AoE: passed**. | Relevant agent/tool-use and reliable-AI systems topics, but no current submission window was verified. Four–six pages including references, IEEE format, double-blind; do not label this main-track COMSNETS. [Official SysAI CFP](https://www.comsnets.org/SysAI). |

AoE means UTC−12. The ISEC demo cutoff corresponds to 24 October, 17:29:59 IST;
the host's 8 November AoE workshop cutoff corresponds to 9 November, 17:29:59 IST.
Recheck the selected submission portal before relying on a cutoff or extension.

The GenAI&SE page is a JavaScript application. The official host's link and the
workshop's own published static application text were inspected without
executing that code. Its linked submission destination is
[Microsoft CMT / GenAISE2027](https://cmt3.research.microsoft.com/GenAISE2027).
Anonymity, what counts within the four pages, and the exact archival status of
each submission category are not fully explicit in the inspected workshop text;
resolve these from the current portal/author instructions before formatting or
submitting. Do not silently import main-track rules as confirmed workshop rules.

The host also lists **RELIABLE-SE 2027**, with four-page papers, two-page posters,
and a nominal 8 November deadline. However, its linked
[official HotCRP page](https://reliablese2026.hotcrp.com/) currently states that
submissions are closed, despite describing the 2027 workshop. This inconsistency
prevents treating it as a verified available route. Its coding-agent focus also
requires a more direct software-development application than a refund example.

## Alternatives checked and why they are not the recommendation

- **CODS** is the current name of the ACM India data-centric series formerly
  called CODS-COMAD. Its official 2026 event is 13–16 December in Gandhinagar;
  the main/YRS deadline was 20 August 2026 and has passed. This search did not
  verify an official 2027 CFP or deadline. A hypothetical 2027 entry from a
  deadline aggregator is insufficient. A stronger data-management or benchmark
  contribution would improve fit. [Official CODS 2026 site](https://ikdd.acm.org/cods-2026/).
- **IEEE PerCom 2027** is in Goa, 8–12 March; the main full-paper deadline was
  extended to 18 September 2026 and has passed. Pervasive computing is not the
  present refund protocol's central setting. [Official PerCom site](https://percom.org/).
  Its **PeRConAI** workshop has a 17 November 2026 deadline, double-blind IEEE
  submissions with six technical pages and an optional seventh page. It would
  require a substantive resource-constrained/pervasive application, not merely
  running a small model on a laptop. It requires full registration and in-person
  presentation. [Official PeRConAI CFP](https://perconai.iit.cnr.it/call-for-papers/).
- **ICSE 2027**, a relevant international software-engineering ambition, is in
  Dublin, Ireland, 25 April–1 May. It does not meet an India-hosted requirement.
  An ICSE workshop is also a separate publication category from its research
  track. [Official ICSE 2027 site](https://conf.researchr.org/home/icse-2027).
- ACM India **COMPUTE** is a computing-education conference; this paper has no
  education study. **ARCS** presents PhD students' already accepted research and
  is not a replacement original-paper publication route. Neither should be
  selected simply because it has ACM India branding.
  [COMPUTE CFP](https://isigcse.acm.org/compute/2026/compute-2026-call-for-papers/),
  [ARCS scope](https://event.india.acm.org/arcs/).

No claim that a venue is universally “top” follows from an IEEE/ACM logo,
indexing, a national location, or a promotional description. Fit, contribution,
review standards and the actual publication category matter. This focused
search found no verified still-open **full main-research** India-hosted call
that is both an obvious fit and a reason to rush the current experiments.

## Scientific gates for the full research paper

These are our readiness criteria derived from the actual manuscript and
[T1–T20 review response](review-response-2026-10-18.md), not extra requirements
attributed to a particular conference. Larger local inference alone cannot
resolve every item.

| Gate | Work required | Evidence to retain and permissible claim |
| --- | --- | --- |
| **1. Matched diagnostic baselines (T1)** | Score response-only, latest-step/recency, an evidence-aware rules baseline, and an equally informed trace judge on the same captured episodes. Keep diagnosis separate from changing the action policy. | A per-method input, compute and availability table; per-episode predictions; independent evaluator labels. A verifier-plus-rules baseline can tie Consequa-X: report the tie and locate the actual protocol benefit rather than weakening the comparator. |
| **2. Matched intervention comparisons (T1, T5, T13)** | Compare faithful CAR-style decision interventions and any joint-fault method within a common declared player/target space. Pin upstream definitions and label independent adaptations. | Same continuation policy, eligible evidence, candidate units, reset access and attempted-call budget. Distinguish differences in refusal/game semantics from estimator accuracy. A context-deletion ablation is not a faithful decision-step CAR reproduction. |
| **3. Larger, frozen local-model study (T3, T12)** | Freeze protocol, prompts, manifests, models/digests, inference settings, seeds/order, budgets, missingness rules and analysis before new calls. Sample independently constructed task/template families, then repeated episodes within them. Add genuinely distinct model families if resources permit. | All planned episodes, failed/unstarted slots, raw requests/responses and costs. Report per-model and per-family outcomes. Repetition on one refund wording/model remains a bounded local study, not broad agent generalization. |
| **4. External validity and recovery boundaries (T2, T7, T8)** | Add at least one independently implemented application or established stateful benchmark with admissible readback/provenance. Evaluate bounded polling separately if implemented. | Transfer results and source trust assumptions; read count, latency and unknown rate versus wait. Do not claim real-service effectiveness from a simulator, or exactly-once execution from polling under unbounded late commits. Replay remains isolated from real consequential writes. |
| **5. Inferential and annotation integrity (T4, T10–T15)** | Choose estimands and precision targets in advance. Use family-aware paired uncertainty; retain unknowns. Validate any new interval method independently. Obtain genuinely independent, blinded rationale annotation if making language-claim accuracy conclusions. | Exact numerator/denominator, coverage and refusal; predeclared primary contrasts; all interval variants and multiplicity rules. Separate an AI-assisted development label audit from independent human annotation. No invented reviewer, annotator or agreement coefficient. |
| **6. Reviewer access and claim audit (T9, T20)** | Freeze an evidence inventory tying each manuscript number to immutable source/protocol/raw data/analysis. Decide an anonymized reviewer-access route while respecting the private repository. Supply actual author details and AI-use disclosures. | A reproducible minimal archive and clear access statement. Public PyPI software and a public landing page do not establish public access to research data. Never claim an artifact badge or independent replication before it exists. |

For precision planning, the familiar worst-case independent Bernoulli
approximation gives about 385 **assessable independent units** for a 95% interval
with ±5 percentage-point half-width. This is only a planning calculation
(`1.96² × 0.25 / 0.05²`); it is not a justified sample size for clustered
templates, paired differences, low claim coverage, several models, or multiple
comparisons. Predeclare the actual target and account for those design features.
An exhausted run budget is a reported study limit, not a reason to replace
failed episodes or relabel incomplete evidence.

Use the existing scripted studies to establish mechanism properties and
calibration under their explicit assumptions. Use the local model collection to
measure model behavior and evidence assessment. Neither supplies independent
task diversity for the other. A full paper can report negative comparisons and
protocol tradeoffs honestly; formatting, graphs and additional calls cannot
manufacture a novel empirical advantage.

## Concrete submission checklist

1. **Select the publication category explicitly.** Keep the complete IEEE source
   as a working manuscript. Make a separate ACM derivative only after choosing
   a current ISEC category; do not squeeze the full paper by shrinking type.
2. **Finish the study record before changing headline claims.** Update abstract,
   tables and conclusion only from audited outputs. Reconcile T1–T20 against
   completed evidence; do not mark every feedback item done because code exists.
3. **For an ISEC demo option:** demonstrate timeout-before/after-commit,
   other-actor state satisfaction, unknown evidence and offline reports; prepare
   the required video and usable artifact. The current demo CFP calls for AI-use
   disclosure, original work, in-person presentation and a non-student author
   registration for publication. Anonymity is not explicitly specified in the
   inspected demo text. Confirm portal requirements. [Demo author instructions](https://conf.researchr.org/track/isec-2027/isec-2027-industry-innovation-track).
4. **For a main ISEC research derivative:** use double-blind ACM format, neutral
   self-citations and an artifact-availability statement. Optional artifact
   evaluation follows acceptance; its result does not determine paper acceptance.
   Check ACM authorship/AI policy, originality and simultaneous-submission rules.
   Check actual affiliation-dependent APC coverage and registration terms rather
   than assuming the author's costs. [Research author instructions](https://conf.researchr.org/track/isec-2027/isec-2027-research-papers).
5. **Separate science from promotion.** The website may show the released package
   and accurate examples. Do not advertise accepted research, a selected venue,
   or superiority until supported. Avoid posting a branded review archive into
   an anonymous submission without considering author identification.
6. **Before any submission:** verify current CFP/portal status, settle author and
   contributor credit, funding/conflicts, AI disclosures, artifact access and
   archival overlap. Obtain the author's final approval of the exact manuscript
   and venue. No deadline, portal state or future call is guaranteed by this
   dated note.

GitHub Actions remains disabled. Local experiments and local verification do not
require enabling it.
