# Policy evaluation

Provider: **scripted**. Planned 6 samples; completed 6, failed 0, not started 0. Policy calls: 12 / 30.

This is an offline scripted-policy smoke evaluation. No language model was run.

Reported assessments: success 4, failure 2, partial 0, unknown 0.

Definite claim coverage: 100.0% (6/6); assessable claim coverage: 83.3% (5/6); contradictions among assessable claims: 60.0% (3/5). Unknown assessments are abstentions; partial assessments remain separate. These counts score the structured status only; an unknown status can coexist with definite claims in the rationale, which requires separate review. These are hindsight comparisons with supported action-linked state, not a grade of what an ambiguous public response lets the policy know. Failed and unstarted runs have no final assessment and remain outside these denominators.

Study: **refund-family-candidates-v1**; declared split: **tuning**; case-order seed: 7. Template families are confined to one split. This assignment does not certify unseen model inputs or held-out fault compositions; final study scope still requires an exposure audit.

| Sample | Case | Seed | Status | Calls | Reported assessment | Verified outcome | Origin | Alignment | Linked contract satisfied |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | tuning.partial-refund | 100 | completed | 2 | success | violated | confirmed | contradicted | False |
| 1 | tuning.ordinary | 101 | completed | 2 | success | satisfied | confirmed | consistent | True |
| 2 | tuning.missing-provenance | 102 | completed | 2 | success | satisfied | unknown | unassessable | None |
| 3 | tuning.false-acknowledgement | 103 | completed | 2 | success | violated | unknown | contradicted | False |
| 4 | tuning.timeout-before | 104 | completed | 2 | failure | violated | unknown | consistent | False |
| 5 | tuning.timeout-after | 105 | completed | 2 | failure | satisfied | confirmed | contradicted | True |

Provider/protocol failures and unstarted samples are separate from consequence violations. Unknown readback remains unknown. Model seed settings are a reproducibility control, not a guarantee across models, servers, or hardware. Virtual payment deadlines exclude inference latency.

The linked-contract target requires qualifying action-linked refund witnesses as well as satisfied state; another actor's refund is not agent success. Missing provenance leaves this target unknown.

The model receives declared task/context and public tool responses. Independent readback is revealed only after its final assessment. Evaluator labels and truth are in separate files and must not be passed to a policy or explainer. Manifest hashes check file integrity, not evidence authenticity.
