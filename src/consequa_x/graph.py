"""An evidence graph: declared dependencies and origin links are not causal effects."""

from dataclasses import dataclass, field
from typing import Any, Iterable

from .attribution import EffectEstimate
from .models import EventType, Trace, to_dict


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
            raise ValueError(f"Trace event identity conflicts with evidence node: {identifier!r}")
        node(identifier, kind, time_ms, data)

    def edge(source, target, kind, basis, data=None):
        if source not in nodes or target not in nodes:
            raise ValueError(f"Graph link has an absent endpoint: {source!r} -> {target!r}")
        key = (source, target, kind)
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

    contract_node = f"contract:{trace.action.contract.contract_id}"
    evidence_node(contract_node, "postcondition", trace.action.registered_at_ms,
                  trace.action.contract.to_dict())
    for observation in trace.observations:
        observation_node = f"observation:{observation.observation_id}"
        evidence_node(observation_node, "external_observation", observation.observed_at_ms,
                      observation.to_dict())
        for record in observation.records:
            effect_id = record.get("effect_id")
            committed_at = record.get("committed_at_ms")
            if (not isinstance(effect_id, str) or not effect_id
                    or type(committed_at) is not int or committed_at < 0):
                continue
            effect_node = f"effect:{effect_id}"
            evidence_node(effect_node, "observed_external_effect", committed_at,
                          {**record, "witness_observation_id": observation.observation_id})
            edge(effect_node, observation_node, "OBSERVATION", "readback_record")
            attempt_id = record.get("attempt_id")
            dispatch = dispatches.get(attempt_id) if isinstance(attempt_id, str) else None
            if (dispatch and record.get("action_id") == trace.action.action_id
                    and dispatch.data.get("action_id") == trace.action.action_id
                    and dispatch.actor == trace.action.actor
                    and record.get("actor", trace.action.actor) == trace.action.actor):
                edge(dispatch.id, effect_node, "EFFECT", "provider_origin_metadata")

    for index, verification in enumerate(trace.verifications):
        verification_node = f"verification:{verification.contract_id}:{index}"
        evidence_node(verification_node, "verification", verification.observed_at_ms,
                      verification.to_dict())
        edge(contract_node, verification_node, "CONTRACT", "declared_predicate")
        for evidence in verification.evidence:
            edge(f"observation:{evidence.observation_id}", verification_node,
                 "VERIFICATION", "read_only_verifier")
        for effect_id in verification.effect_ids:
            identifier = f"effect:{effect_id}"
            if identifier in nodes:
                edge(identifier, verification_node, "VERIFICATION", "predicate_evidence")

    for estimate in estimates:
        if estimate.event_id not in nodes:
            raise ValueError("Attribution candidate is not present in this trace")
        decisions = [event.id for event in trace.events if event.type is EventType.AGENT_DECISION]
        intent = next((event for event in trace.events
                       if event.type is EventType.ACTION_INTENT
                       and event.data.get("action_id") == trace.action.action_id), None)
        decision = next((parent for parent in intent.parent_ids if parent in decisions), None) if intent else None
        initial_decision = decision or (decisions[0] if decisions else None)
        target = initial_decision if estimate.target == "action" else contract_node
        if target:
            edge(estimate.event_id, target, "ESTIMATED_INFLUENCE",
                 "isolated_simulated_intervention", estimate.to_dict())
    return ConsequenceGraph(tuple(nodes.values()), tuple(edges))
