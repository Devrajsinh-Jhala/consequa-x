# Final state-transfer findings and task context

The sealed experiment completed all 656 fixed cells across 164 canonical tasks. Its native DB figures measure self-replay consistency and controlled end-state differences. The requested-field figures describe application contracts captured immediately after each scripted operation. Neither is autonomous agent performance or independently validated predicate accuracy.

| Domain | Control | Native DB component match | Requested-field predicates satisfied |
|---|---|---:|---:|
| retail | reference | 114/114 | 174/176 |
| retail | omit_writes | 11/114 | 2/176 |
| retail | false_acknowledgement | 11/114 | 2/176 |
| retail | altered_first_write | 13/114 | 72/176 |
| airline | reference | 50/50 | 49/49 |
| airline | omit_writes | 24/50 | 0/49 |
| airline | false_acknowledgement | 24/50 | 0/49 |
| airline | altered_first_write | 24/50 | 23/49 |

All 900 operation captures were structurally valid. All 900 withheld-readback checks remained unknown; action origin remained unknown and assessment alignment unassessable in every capture. There were 2,318 tracked reference/control trajectory tool calls, excluding preflight/readback lookups and evaluator replays; there were no model calls.

Retail task 64 contains a rejected exchange followed by a successful pending-order modification. The policy distinguishes pending-order modification from delivered-order exchange. The unsuccessful first-operation contract and successful final task DB match therefore describe different targets; this can be an error/fallback trajectory. No dataset-bug conclusion follows from this audit.

Retail task 105 contains a rejected exchange due to gift-card balance and a separate NL assertion requiring both kettle exchanges. The experiment does not evaluate that assertion or full task success. DB equality with the repeated failed call is not evidence that the exchanges occurred.

In tasks 22 and 110, two requested user-address field predicates already match the initial address when all writes are omitted. Task 22 explicitly includes changing the address and then restoring the original. A final state can satisfy a restoration predicate without establishing the preceding changes or any action origin. These cases remain in every denominator.

All 656 episode hashes and start records matched the frozen schedule. Historical runner, tests, protocol and application sources match commit `7f6ef0c`. The study completed at 19:15:07 IST on 18 October 2026, before the later version-preparation commit at 20:36:46 IST. The current runtime differs only in the subsequent 1.1.0 to 1.1.1 version label. Frozen study files were not resealed or regenerated.

See `final-audit.json` for exact manifests and `task-context-audit.json` for the four complete source-task descriptions and reference-call context. This is implementation-author review, separate from execution, and does not replace independent human validation.
