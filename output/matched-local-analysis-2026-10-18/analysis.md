# Matched local-model factual audit

Fixed simulator cases and exposed mechanisms; wording robustness only. Offline auditors share factual traces but declared information sets differ. Independent public reference shares Consequa-X's information set. No causal attribution, human rationale audit, named-system reproduction, statistical superiority or population generalization is established.

Planned episodes: 504; statuses: `{"completed": 503, "failed": 1, "interrupted_partial": 0, "unstarted": 0}`.
Attempted chat calls: 896 / 1512.

| Auditor | Target | Claims / assessable | Wrong / claims | Correct / assessable | Correct / planned |
| --- | --- | ---: | ---: | ---: | ---: |
| response_only | state | 201 / 503 | 53 / 201 | 148 / 503 | 148 / 504 |
| response_only | action_linked | 201 / 503 | 53 / 201 | 148 / 503 | 148 / 504 |
| response_only | origin | 0 / 310 | 0 / 0 | 0 / 310 | 0 / 504 |
| agent_self_report | state | 252 / 503 | 148 / 252 | 104 / 503 | 104 / 504 |
| agent_self_report | action_linked | 252 / 503 | 136 / 252 | 116 / 503 | 116 / 504 |
| agent_self_report | origin | 0 / 310 | 0 / 0 | 0 / 310 | 0 / 504 |
| readback_state_only | state | 431 / 503 | 0 / 431 | 431 / 503 | 431 / 504 |
| readback_state_only | action_linked | 0 / 503 | 0 / 0 | 0 / 503 | 0 / 504 |
| readback_state_only | origin | 0 / 310 | 0 / 0 | 0 / 310 | 0 / 504 |
| independent_public_reference | state | 431 / 503 | 0 / 431 | 431 / 503 | 431 / 504 |
| independent_public_reference | action_linked | 385 / 503 | 0 / 385 | 385 / 503 | 385 / 504 |
| independent_public_reference | origin | 216 / 310 | 0 / 216 | 216 / 310 | 216 / 504 |
| consequa_state_origin | state | 431 / 503 | 0 / 431 | 431 / 503 | 431 / 504 |
| consequa_state_origin | action_linked | 385 / 503 | 0 / 385 | 385 / 503 | 385 / 504 |
| consequa_state_origin | origin | 216 / 310 | 0 / 216 | 216 / 310 | 216 / 504 |

Zero denominators produce JSON null. Abstention is not counted as a correct claim.
Failed, partial and unstarted episodes remain explicit outside completed semantic targets.
Correct definite outputs divided by all frozen slots in the group, including failed, partial, unstarted and gold-unassessable slots. This is a descriptive operational yield, not semantic accuracy with invented negative labels for missing executions. Completed-episode rates remain separate.
Each JSON stratum retains its full planned, started, disposition and call counts, including strata with no completed episodes.
