# Matched local trace judge

All frozen factual schedule slots with repetition == 0, in original order; fixed after factual collection and before judge outputs; not held out.

Collection state: completed; final: true; stop reason: all_never_started_slots_processed.

Pool context: 504 factual slots, 503 completed and one failed. These are not judge denominators.
Selected judge slots: 84; available factual inputs: 84.
Judge dispositions: {"completed": 84}.

| Method | Target | Claims / assessable outputs | Wrong / claims | Correct / selected planned |
| --- | --- | ---: | ---: | ---: |
| local_trace_judge | state | 60 / 84 | 9 / 60 | 51 / 84 |
| local_trace_judge | action_linked | 0 / 84 | 0 / 0 | 0 / 84 |
| local_trace_judge | origin | 52 / 52 | 12 / 52 | 40 / 84 |
| independent_public_reference | state | 72 / 84 | 0 / 72 | 72 / 84 |
| independent_public_reference | action_linked | 64 / 84 | 0 / 64 | 64 / 84 |
| independent_public_reference | origin | 36 / 52 | 0 / 36 | 36 / 84 |
| consequa_state_origin | state | 72 / 84 | 0 / 72 | 72 / 84 |
| consequa_state_origin | action_linked | 64 / 84 | 0 / 64 | 64 / 84 |
| consequa_state_origin | origin | 36 / 52 | 0 / 36 | 36 / 84 |

Zero denominators are undefined. Abstentions, failures and unavailable inputs do not count as correct claims.

Evidence-supported means the independent public reference derives the same definite label from the allowed readback; correct unsupported guesses remain separately counted. This is rule-based evidence qualification, not a rationale annotation.

Post-collection descriptive comparator on 14 fixed wording/mechanism cells; requested seeds do not establish independence. One Qwen judge overlaps a factual generator family. No human validation, causal identification, benchmark score, or method superiority is established.
