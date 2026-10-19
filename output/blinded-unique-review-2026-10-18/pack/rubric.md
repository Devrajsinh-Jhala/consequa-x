# Evidence annotation rubric

Read the registered contract and the captured independent readback. Public tool
responses are acknowledgements about requests; they do not establish effects.
Identifiers are opaque and local to each card. Equal identifiers within one card
refer to the same entity; equal spellings on different cards need not.

Use only evidence on the card. Do not infer missing facts from a case number,
another card, a successful response, or the study's purpose. A blank annotation
means not yet reviewed; use the explicit `unknown` label for a reviewed but
unassessable target. The optional support field should cite a visible field,
record identifier or timestamp, not invent an unseen event.

## State: satisfied / violated / unknown

Match the contract's payment, amount and currency. Registration is the earliest
in-scope commit time. The horizon is `deadline_ms + stability_ms`, with both
deadline and horizon inclusive. A qualifying effect commits no later than the
deadline and remains unreversed through the horizon. A reversal exactly at the
horizon does not satisfy persistence. An effect after the horizon is outside
scope. With `exact_count`, the number of matching effects must equal that count
throughout the inclusive stability window; an extra matching effect during the
window violates that requirement, even if it is later reversed.

`satisfied`: adequate independent readback establishes the contract.
`violated`: adequate independent readback establishes a contract failure.
`unknown`: the evidence cannot establish either, including unavailable,
incomplete, malformed, wrong-scope or horizon-stale readback. Do not treat a
missing or stale record as evidence of absence. An exhaustive empty snapshot
can establish absence only when scope and the required horizon are covered.

## Origin: confirmed / other_actor / unknown

Consider relevant observed refunds from registration through the horizon,
including wrong-amount and reversed effects; these can establish origin even
when the requested target fails. `confirmed` requires a trustworthy observed
link to this action and its actor. `other_actor` requires observed effects
explicitly belonging only to other actors, with none linked to this action.
`unknown` applies to missing or insufficient provenance, no relevant effect, or
insufficient independent readback. A request identifier alone is not an origin
proof. Origin is provenance evidence, not counterfactual causal responsibility.

## Action-linked target: satisfied / not_satisfied / unknown

`satisfied`: the state target is satisfied and sufficient qualifying effects are
linked to this action and actor. Check payload, deadline and persistence as well
as the provenance link.
`not_satisfied`: a known state violation, or a satisfied state supported only by
other actors' effects.
`unknown`: insufficient target/provenance evidence. State satisfaction alone
does not establish this action's target. An exact-count-zero target has unknown
action linkage because absence is not a qualifying action-produced effect.

## Independent review procedure

1. Two reviewers each make a separate copy of `blank_annotations.csv`, assign
   their own reviewer identifier, and label every case independently using this
   rubric. Keep each reviewer's original completed file. Do not share labels
   before both initial annotation files are locked.
2. Record uncertain evidence as `unknown`, with an optional short support/note.
   Do not force agreement or guess an outcome. The packet contains no expected
   labels, machine predictions, model identity or evaluator truth.
3. After both independent files are complete, compare labels and retain all
   original disagreements. If adjudication is needed, have a third reviewer
   inspect the evidence/rubric and record a separate adjudication file and reason.
   Do not overwrite the two independent records.
4. Report actual reviewed counts, missing cases, reviewer qualifications,
   disagreement/adjudication counts and agreement methodology before making a
   human-validation claim. A single author's self-review is not independent
   double annotation. Agreement is not a substitute for an independent source
   of simulator or real-service truth.

These are 17 unique public-evidence byte patterns observed in 84 selected
traces from fixed simulator conditions. Human agreement uses 17 unique evidence patterns as its primary denominator. These were observed in 84 selected traces. Any frequency-weighted expansion to 84 is descriptive; repeated evidence and annotations are not independent tasks.
These patterns do not establish independent tasks, held-out mechanisms or
real-service transfer.
Preparing this packet does not mean any human has reviewed it.
