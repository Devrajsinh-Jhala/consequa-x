# Final tau3 state-transfer artifact audit

The656 fixed cells completed (656 completed,0 failed,0 unstarted), covering114 retail and50 airline canonical tasks. All episode hashes and start records match the frozen schedule. This is implementation-author review, separate from the root executor; it is not independent human validation.

| Domain | Control | Native DB match | Requested fields satisfied |
|---|---|---:|---:|
| retail | reference | 114/114 | 174/176 |
| retail | omit_writes | 11/114 | 2/176 |
| retail | false_acknowledgement | 11/114 | 2/176 |
| retail | altered_first_write | 13/114 | 72/176 |
| airline | reference | 50/50 | 49/49 |
| airline | omit_writes | 24/50 | 0/49 |
| airline | false_acknowledgement | 24/50 | 0/49 |
| airline | altered_first_write | 24/50 | 23/49 |

All900 consequential-action captures exercised the record-level audit. All900 withheld-readback checks stayed unknown; origin stayed unknown and assessment alignment unassessable throughout. No unavailable or invalid captures were retained. These counts do not establish independent predicate accuracy.

Native reference DB matching is164/164, while requested fields match223/225. Retail task64 attempts to exchange a pending order; task105 lacks sufficient gift-card balance. The native tool returns errors, and the gold replay repeats those failed calls, so task-level DB equality can still pass. No-write/false-ack controls each retain two satisfied retail address predicates because those initial addresses already match the request (tasks22 and110). These are examples of target separation, not facts to remove from results.

The summary finalized at19:15:07 IST on18 October2026, before the20:36:46 IST version-preparation commit. Every frozen local source blob matches commit7f6ef0c. Current runtime differs only in the later1.1.0→1.1.1 version label; the study is not resealed or relabeled. See `final-audit.json` for exact hashes, fractions, error cases and chronology.

No extra native benchmark cases, models, package publication or GitHub Actions were run by this audit.
