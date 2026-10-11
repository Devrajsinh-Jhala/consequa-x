# Paired policy replay

Provider: **scripted**; case: **clean**. 2 paired seeds per condition. Completed 4 of 4 branches; failed 0, not started 0. Policy calls: 6 / 12.

This is a scripted integration fixture. No language model was run.

Reported assessments: success 2, failure 0, partial 0, unknown 2.

Definite claim coverage: 50.0% (2/4); assessable claim coverage: 50.0% (2/4); contradictions among assessable claims: 0.0% (0/2). Unknown assessments are abstentions; partial assessments remain separate. These counts score the structured status only; an unknown status can coexist with definite claims in the rationale, which requires separate review. These are hindsight comparisons with supported action-linked state, not a grade of what an ambiguous public response lets the policy know. Failed and unstarted runs have no final assessment and remain outside these denominators.

Each factual seed runs once and is reused across candidates and all selected targets. Each changed branch starts a fresh simulated world under the same fixed contract. Estimates read the collected episodes and make no additional policy calls.

| Context | Target | Status | Original rate | Changed rate | Signed effect | Approx. 95% interval | Known pairs | Unknown | Failed | Unstarted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vip_policy | action | estimated | 1.000 | 0.000 | +1.000 | [-0.431, +1.000] | 2 | 0 | 0 | 0 |
| vip_policy | consequence | estimated | 1.000 | 0.000 | +1.000 | [-0.431, +1.000] | 2 | 0 | 0 | 0 |
| vip_policy | action_linked_consequence | estimated | 1.000 | 0.000 | +1.000 | [-0.431, +1.000] | 2 | 0 | 0 | 0 |

Effects are original minus changed target probability, not responsibility shares. The consequence target is verified state satisfaction; another actor can satisfy that state. Each approximate conservative Wilson-difference interval applies to one estimate, without simultaneous coverage across candidates.

The optional action_linked_consequence target additionally requires qualifying action-linked witnesses; satisfied state with exclusively external origin is false, and insufficient provenance is unknown. This is a supported-evidence target, not causal responsibility.

A target estimate requires every planned pair to be usable. Unknown consequence pairs, provider/protocol failures, and unstarted pairs are recorded separately; none are dropped, redrawn, or assigned a fabricated outcome. Known action selection can still be estimated when consequence readback is unknown.

Model phase seeds are a pairing control, not a guarantee of deterministic generation. Simulation deadlines exclude inference latency. The optional attribution explanation attaches only available estimates to a representative factual trace; its influence edges describe the replay distribution.

Keep evaluator truth and run-level labels out of policy and explainer inputs. The manifest covers branch artifacts, estimates, schema, report, and any attribution explanation. Hashes detect changed files, not evidence authenticity. Actual model measurements, held-out tasks, and matched strong baselines remain necessary for the research paper.
