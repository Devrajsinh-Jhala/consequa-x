# Policy evaluation

Provider: **ollama**. Planned 2 samples; completed 2, failed 0, not started 0. Policy calls: 4 / 6.

This evaluation calls a selected local Ollama model against simulated payments. It is a template-level smoke evaluation, not a held-out research study.

Reported assessments: success 0, failure 0, partial 0, unknown 2.

Definite claim coverage: 0.0% (0/2); assessable claim coverage: 0.0% (0/2); contradictions among assessable claims: not available (0/0). Unknown assessments are abstentions; partial assessments remain separate. These are hindsight comparisons with supported action-linked state, not a grade of what an ambiguous public response lets the policy know. Failed and unstarted runs have no final assessment and remain outside these denominators.

| Sample | Case | Seed | Status | Calls | Reported assessment | Verified outcome | Origin | Alignment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | clean | 0 | completed | 2 | unknown | satisfied | confirmed | unassessable |
| 1 | timeout_after_commit | 1 | completed | 2 | unknown | satisfied | confirmed | unassessable |

Provider/protocol failures and unstarted samples are separate from consequence violations. Unknown readback remains unknown. Model seed settings are a reproducibility control, not a guarantee across models, servers, or hardware. Virtual payment deadlines exclude inference latency.

The model receives declared task/context and public tool responses. Independent readback is revealed only after its final assessment. Evaluator labels and truth are in separate files and must not be passed to a policy or explainer. Manifest hashes check file integrity, not evidence authenticity.
