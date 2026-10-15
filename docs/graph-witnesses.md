# Effect witnesses in evidence graphs

One provider effect can appear in several independent readbacks. Its status,
payload or provenance can differ between snapshots. The graph preserves each
captured record rather than replacing an earlier record with a later one.

For an effect captured once, its `effect:<effect_id>` node retains the original
`observed_external_effect` representation. For an effect captured more than once,
including duplicate records in one observation, the graph contains:

- An `effect:<effect_id>` node of kind `external_effect_identity`. Its data contains
  only the declared `effect_id` and a sorted list of `witness_node_ids`. Its time
  is the earliest observation time; it does not assert a common commit time,
  payload, state or actor.
- An `observed_external_effect` node for each captured record. The identifier is
  `effect-witness:<quoted observation_id>:<quoted effect_id>:<record index>`.
  Each component is URL-quoted independently and the index is zero-based within
  the observation. The node retains that record and its `witness_observation_id`.
- An `IDENTITY` edge from each witness to the effect identity, with basis
  `readback_effect_identifier`. This records the source's shared identifier; it
  does not authenticate the source or reconcile conflicting records.

`witness_observation_id` is authoritative graph metadata. If a source record
already contains that name or the reserved `source_record` name, the node also
stores the complete original record under `source_record`. This preserves the
source's values verbatim without using them to identify the graph witness.
Ordinary records without either reserved name retain their original flat payload.

`OBSERVATION` edges join witnesses to their own snapshots. Provider-origin
`EFFECT` edges join dispatches to the specific witnesses that support their
action, attempt and actor metadata. An effect must commit no earlier than the
dispatch or action registration and no later than its source watermark for that
origin edge. A later conflicting actor record cannot inherit an earlier record's
origin edge. Historical origin evidence remains visible on its original witness.

Effect-to-verification edges use witnesses in that receipt's declared evidence
observations. An effect found only in another snapshot does not support the
receipt. The verifier result remains responsible for deciding whether a record
satisfies the domain predicate; the graph records its evidence relationships.

Replay attribution candidates must identify captured trace events. Generated
contract, observation, effect, witness and verification node identifiers cannot
be used as intervention candidates; they are evidence graph artifacts rather
than captured policy history.

The trace schema remains `0.1`. Consumers that previously assumed every
`effect:<id>` node contains a status, amount and actor should also handle the
identity-only kind and follow `IDENTITY` edges to its witnesses. Graphs containing
repeated effects gain witness identifiers and `IDENTITY` edges. Existing recorded
research exports retain their original graphs and source revisions; they are not
rewritten to the new representation.
