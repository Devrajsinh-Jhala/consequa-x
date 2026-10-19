# Independent final trace-judge audit

All 84 planned judge inputs received exactly one completed response, with no failed, interrupted, unavailable or unstarted selected slots. The 338-event journal, all 168 raw request/response files, started records and final receipts agree. Every output was independently reparsed against the strict three-field schema. No audit model calls were made.

The analysis and every generator/model/profile and case stratum were independently recomputed from saved evaluation context and raw outputs; all match. Frozen source hashes were checked against the retained D-drive snapshot, not the subsequently changed main checkout.

| Auditor | Target | Definite claims / gold-assessable | Wrong / claims | Correct / selected84 | Evidence-supported claims | Unsupported correct guesses |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| local_trace_judge | state | 60/84 | 9/60 | 51/84 | 43 | 8 |
| local_trace_judge | action_linked | 0/84 | 0/0 | 0/84 | 0 | 0 |
| local_trace_judge | origin | 52/52 | 12/52 | 40/84 | 24 | 16 |
| independent_public_reference | state | 72/84 | 0/72 | 72/84 | 72 | 0 |
| independent_public_reference | action_linked | 64/84 | 0/64 | 64/84 | 64 | 0 |
| independent_public_reference | origin | 36/52 | 0/36 | 36/84 | 36 | 0 |
| consequa_state_origin | state | 72/84 | 0/72 | 72/84 | 72 | 0 |
| consequa_state_origin | action_linked | 64/84 | 0/64 | 64/84 | 64 | 0 |
| consequa_state_origin | origin | 36/52 | 0/36 | 36/84 | 36 | 0 |

The judge state outputs comprise 9 false positives, no false negatives, and 24 unknowns. All 84 action-linked outputs are unknown, so its claim error is undefined (0/0), not zero error. Origin has 60 definite outputs overall: 52 on assessable gold (40 correct, 12 wrong) and eight additional claims on unassessable gold. The latter are retained without invented truth labels.

Public-reference evidence qualification supports 43 of 60 state claims and 24 of 60 definite origin outputs. Eight correct state guesses and 16 correct origin guesses lack that source qualification; hindsight correctness does not make them supported explanations. Consequa-X and the equally informed independent reference remain exactly equal on all selected targets, limiting any advantage claim.

| Target | Reference unknown, judge definite | Reference definite, judge unknown | Both definite, disagree | Both definite, agree | Both unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| state | 8 | 20 | 9 | 43 | 4 |
| action_linked | 0 | 64 | 0 | 0 | 20 |
| origin | 24 | 0 | 12 | 24 | 24 |

These are 84 selected traces but 17 distinct public-evidence patterns within 14 fixed wording/mechanism cells. The subset was selected after factual collection and before judge outputs. Pool503+1 is context, not a 504-slot judge denominator. This one small local judge shares a family with some generators; its result does not establish general LLM-judge inferiority. Human annotation remains pending.

Analysis SHA-256: `117ea516eadd2e171fef5f8ffbe7337f5d70dd32add6647a3ee6496f2a51528f`. Protocol SHA-256: `4439983d1f861eaffaffbc4140750a8a1740653baa8eb7037ae5df600ca074ae`.
