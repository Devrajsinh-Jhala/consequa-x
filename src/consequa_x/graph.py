"""An evidence graph: declared dependencies and origin links are not causal effects."""

from dataclasses import dataclass, field
from typing import Any, Iterable
from urllib.parse import quote

from .errors import ValidationError
from .attribution import EffectEstimate
from .models import EventType, Observation, Trace, to_dict


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: str
    time_ms: int
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    basis: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsequenceGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def to_dict(self) -> dict:
        return to_dict(self)


def build_graph(trace: Trace, estimates: Iterable[EffectEstimate] = ()) -> ConsequenceGraph:
    """Link captured history to readback evidence, without consulting simulator truth.

    An EFFECT edge is supported by readback's propagated action/attempt metadata.
    Repeated readbacks retain separate effect witnesses: their payload, state and
    provenance are never overwritten by another observation of the same effect.
    Only ESTIMATED_INFLUENCE edges carry intervention-based attribution. Their
    estimates apply to the replay distribution, not to necessity in this one run.
    """
    nodes = {}
    edges = []
    edge_keys = set()
    event_ids = {event.id for event in trace.events}

    def node(identifier, kind, time_ms, data):
        nodes[identifier] = GraphNode(identifier, kind, time_ms, to_dict(data))

    def evidence_node(identifier, kind, time_ms, data):
        if identifier in event_ids:
            raise ValidationError(f"Trace event identity conflicts with evidence node: {identifier!r}")
        if identifier in nodes:
            raise ValidationError(f"Duplicate evidence node identity: {identifier!r}")
        node(identifier, kind, time_ms, data)

    def edge(source, target, kind, basis, data=None):
        if source not in nodes or target not in nodes:
            raise ValidationError(f"Graph link has an absent endpoint: {source!r} -> {target!r}")
        # State and action-linked estimates can point to the same contract.
        # Their distinct estimands must survive edge deduplication.
        estimate_target = data.get("target") if kind == "ESTIMATED_INFLUENCE" and data else None
        key = (source, target, kind, estimate_target)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(GraphEdge(source, target, kind, basis, to_dict(data or {})))

    for event in trace.events:
        node(event.id, event.type.value, event.time_ms, event.data)
    for event in trace.events:
        for parent in event.parent_ids:
            edge(parent, event.id, "DEPENDENCY", "declared_trace_dependency")
    ordered = sorted(enumerate(trace.events), key=lambda item: (item[1].time_ms, item[0]))
    for (_, earlier), (_, later) in zip(ordered, ordered[1:]):
        edge(earlier.id, later.id, "TEMPORAL", "captured_order")

    attempts = {}
    for event in trace.events:
        attempt_id = event.data.get("attempt_id")
        if (event.type is EventType.ACTION_DISPATCH and isinstance(attempt_id, str)
                and attempt_id.strip()):
            attempts.setdefault(attempt_id, []).append(event)
    dispatches = {attempt_id: events[0] for attempt_id, events in attempts.items()
                  if len(events) == 1}
    for event in trace.events:
        if event.type is EventType.TOOL_RESPONSE:
            attempt_id = event.data.get("attempt_id")
            dispatch = dispatches.get(attempt_id) if isinstance(attempt_id, str) else None
            if dispatch:
                edge(dispatch.id, event.id, "RESPONSE", "captured_attempt_identity")

    actions = {action.action_id: action for action in trace.actions}
    contract_nodes = {}
    for action in trace.actions:
        contract_nodes[action.action_id] = f"contract:{action.contract.contract_id}"
        evidence_node(contract_nodes[action.action_id], "postcondition", action.registered_at_ms,
                      action.contract.to_dict())
    # A single observation keeps the original effect:<id> representation. For
    # repeated identities, that node identifies only the declared effect; each
    # snapshot gets its own witness. In particular, a later actor/payload change
    # cannot inherit an earlier dispatch's origin edge.
    effect_records: dict[str, list[tuple[Observation, int, dict]]] = {}
    for observation in trace.observations:
        for index, record in enumerate(observation.records):
            effect_id = record.get("effect_id")
            committed_at = record.get("committed_at_ms")
            if (isinstance(effect_id, str) and effect_id
                    and type(committed_at) is int and committed_at >= 0):
                effect_records.setdefault(effect_id, []).append((observation, index, record))

    def witness_id(observation_id, effect_id, index):
        # Quote each identity separately to avoid collisions such as a:b/c and
        # a/b:c. The index also preserves duplicate records in malformed readback.
        return f"effect-witness:{quote(observation_id, safe='')}:{quote(effect_id, safe='')}:{index}"

    for effect_id, witnesses in effect_records.items():
        if len(witnesses) > 1:
            evidence_node(
                f"effect:{effect_id}", "external_effect_identity",
                min(observation.observed_at_ms for observation, _, _ in witnesses),
                {"effect_id": effect_id, "witness_node_ids": sorted(
                    witness_id(observation.observation_id, effect_id, index)
                    for observation, index, _ in witnesses
                )},
            )
    witnesses_by_observation: dict[tuple[str, str], list[str]] = {}
    for observation in trace.observations:
        observation_node = f"observation:{observation.observation_id}"
        evidence_node(observation_node, "external_observation", observation.observed_at_ms,
                      observation.to_dict())
        for index, record in enumerate(observation.records):
            effect_id = record.get("effect_id")
            committed_at = record.get("committed_at_ms")
            if (not isinstance(effect_id, str) or not effect_id
                    or type(committed_at) is not int or committed_at < 0):
                continue
            repeated = len(effect_records[effect_id]) > 1
            effect_node = (witness_id(observation.observation_id, effect_id, index)
                           if repeated else f"effect:{effect_id}")
            witness_data = dict(record)
            if {"witness_observation_id", "source_record"} & record.keys():
                # These names belong to graph metadata. Retain the complete
                # original payload when a source also supplies either name.
                witness_data["source_record"] = record
            witness_data["witness_observation_id"] = observation.observation_id
            evidence_node(effect_node, "observed_external_effect", committed_at,
                          witness_data)
            witnesses_by_observation.setdefault(
                (observation.observation_id, effect_id), []
            ).append(effect_node)
            if repeated:
                edge(effect_node, f"effect:{effect_id}", "IDENTITY", "readback_effect_identifier")
            edge(effect_node, observation_node, "OBSERVATION", "readback_record")
            attempt_id = record.get("attempt_id")
            dispatch = dispatches.get(attempt_id) if isinstance(attempt_id, str) else None
            action_id = record.get("action_id")
            action = actions.get(action_id) if isinstance(action_id, str) else None
            if (dispatch and action
                    and dispatch.data.get("action_id") == action.action_id
                    and dispatch.actor == action.actor
                    and record.get("actor", action.actor) == action.actor
                    and dispatch.time_ms <= committed_at
                    and action.registered_at_ms <= committed_at <= observation.as_of_ms):
                edge(dispatch.id, effect_node, "EFFECT", "provider_origin_metadata")

    for index, verification in enumerate(trace.verifications):
        verification_node = f"verification:{verification.contract_id}:{index}"
        evidence_node(verification_node, "verification", verification.observed_at_ms,
                      verification.to_dict())
        edge(contract_nodes[verification.action_id], verification_node, "CONTRACT",
             "declared_predicate")
        for evidence in verification.evidence:
            edge(f"observation:{evidence.observation_id}", verification_node,
                 "VERIFICATION", "read_only_verifier")
            for effect_id in verification.effect_ids:
                for identifier in witnesses_by_observation.get(
                    (evidence.observation_id, effect_id), ()
                ):
                    edge(identifier, verification_node, "VERIFICATION", "predicate_evidence")

    estimates = tuple(estimates)
    if estimates and len(trace.actions) != 1:
        raise ValidationError("Intervention estimates apply to single-action traces only")
    for estimate in estimates:
        action = trace.actions[0]
        if estimate.event_id not in event_ids:
            raise ValidationError("Attribution candidate must identify a captured trace event")
        decisions = [event.id for event in trace.events if event.type is EventType.AGENT_DECISION]
        intent = next((event for event in trace.events
                       if event.type is EventType.ACTION_INTENT
                       and event.data.get("action_id") == action.action_id), None)
        decision = next((parent for parent in intent.parent_ids if parent in decisions), None) if intent else None
        initial_decision = decision or (decisions[0] if decisions else None)
        target = initial_decision if estimate.target == "action" else contract_nodes[action.action_id]
        if target:
            edge(estimate.event_id, target, "ESTIMATED_INFLUENCE",
                 "isolated_simulated_intervention", estimate.to_dict())
    return ConsequenceGraph(tuple(nodes.values()), tuple(edges))
