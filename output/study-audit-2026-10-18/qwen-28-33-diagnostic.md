# Dispatched Qwen control diagnostic

Audited 18 October 2026. This bounded check covers exactly completed slots
episode_00028 through episode_00033 in protocol
`e8859ef64006780298922ef24215f4e080fa84575032a65944268317a6ee55ab`,
source `bcd733d8f8c5712e4413afe030b6a20bf7080de1`. It checks dispatched
controls after the earlier no-action diagnostic. It is not an interim estimate
of effectiveness or a reason to change sampling, models, prompts or stopping.

The six committed receipts and their trace/explanation/evaluator-ledger artifacts
were copied to a separate temporary snapshot before interpretation. All artifact
hashes matched their receipts. A closed hash-chained journal prefix independently
bound the receipts and all twelve request/response byte pairs. Every provider
response was complete HTTP 200 from the declared Qwen model name. The frozen
installed model digest is retained in the machine-readable diagnostic; provider
name and local digest checks are not hardware attestation.

Raw requests matched their captured trace requests, requested phase seeds,
temperature, token cap and frozen system-prompt hashes. Raw response JSON
decisions matched the retained trace decisions and request-payload hashes.
All six slots selected refund, made one actual dispatch and one provider attempt,
then stopped after their second model call. No slot in this bounded check retried.
The action arguments match the frozen payment, INR currency and 125,000 minor
units, with registration at 5 ms, deadline at 100 ms and horizon at 120 ms.

| Slot | Condition | Provider response | Hidden state / linked gold | Public reference and Consequa-X state / linked / origin |
| --- | --- | --- | --- | --- |
| 00028 | Missing provenance | Success | True / True | True / Unknown / Unknown |
| 00029 | Delayed readback | Success | True / True | Unknown / Unknown / Unknown |
| 00030 | Delayed readback | Success | True / True | Unknown / Unknown / Unknown |
| 00031 | Clean boundary | Success | True / True | True / True / Confirmed |
| 00032 | Clean boundary | Success | True / True | True / True / Confirmed |
| 00033 | Other actor | Timeout | True / False | True / False / Other actor |

The independently implemented public reference and Consequa-X match on every
state, linkage and origin output in these six slots. Their definite outputs
agree with the independent ledger gold. Their unknown outputs are retained as
abstentions, even when the complete hidden ledger determines a true outcome.

The execution diagnostic correctly distinguishes the actual mechanisms:

- Slot 00028 contains one visible refund record with suppressed origin fields,
  so provenance loss has an actual record opportunity. State remains known while
  public linkage and origin remain unknown.
- Slots 00029 and 00030 contain real committed refunds but their public
  watermark is 0 ms, before the 120 ms horizon. The measured gap is 120 ms;
  it is not confused with the configured 200 ms source lag or interpreted as
  absence of an effect.
- Slots 00031 and 00032 contain one correctly scoped agent refund each, with
  public origin witnesses and a horizon-covering readback.
- Slot 00033 actually enters the timeout-before-commit fault path. Its agent
  attempt dispatches and times out without committing; an external actor then
  commits the sole refund. The diagnostic records one external effect, zero
  agent effects, global satisfaction and false action-linked satisfaction.

The model reports structured `unknown` in all six final raw responses, including
the five successful acknowledgements. This is retained model behavior, rather
than an adapter substitution or an invented success/failure label. The separate
response-only proxy can make a definite acknowledgement-based claim; its input
budget and uncertainty differ from the model self-report and readback auditors.

No collection defect was found in this bounded dispatched-control check. It
validates the separate per-episode execution helper on real retained dispatched
traces, but it establishes no aggregate model ranking or retry-performance claim.
No model call or full-study analysis/finalization was performed, and the live
collection and all frozen scripts, tests, protocol files and runtime files were
left unchanged.

Machine-readable details: `qwen-28-33-completed.json` and
`qwen-28-33-provider-binding.json`. Local snapshots are under
`tmp/study-audit-2026-10-18-qwen-28-33/`.
