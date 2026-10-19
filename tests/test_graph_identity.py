"""Imported traces must not turn ambiguous identities into provider-origin claims."""

from dataclasses import replace

import pytest

from consequa_x.benchmark.runner import run_scenario
from consequa_x.graph import build_graph
from consequa_x.models import EventType
from consequa_x.verification import verify


def test_duplicate_dispatch_attempt_identity_refuses_origin_and_response_joins():
    trace = run_scenario().trace
    dispatch = next(event for event in trace.events if event.type is EventType.ACTION_DISPATCH)
    duplicate = replace(dispatch, id="ambiguous_dispatch")
    graph = build_graph(replace(trace, events=(*trace.events, duplicate)))
    assert not {edge.kind for edge in graph.edges} & {"RESPONSE", "EFFECT"}


def test_conflicting_dispatch_actor_does_not_assert_provider_effect_origin():
    trace = run_scenario().trace
    events = tuple(replace(event, actor="another_actor")
                   if event.type is EventType.ACTION_DISPATCH else event for event in trace.events)
    graph = build_graph(replace(trace, events=events))
    assert any(edge.kind == "RESPONSE" for edge in graph.edges)
    assert not any(edge.kind == "EFFECT" for edge in graph.edges)


def test_event_identity_cannot_overwrite_an_evidence_node():
    trace = run_scenario().trace
    effect_id = trace.verifications[-1].effect_ids[0]
    additional = replace(trace.events[0], id=f"effect:{effect_id}")
    with pytest.raises(ValueError, match="identity conflicts"):
        build_graph(replace(trace, events=(*trace.events, additional)))


def test_duplicate_readback_records_are_preserved_without_overwriting_each_other():
    trace = run_scenario().trace
    view = trace.observations[0]
    original = view.records[0]
    changed = dict(original, amount_minor=250_000, actor="another_actor")
    view = replace(view, records=(original, changed))
    receipt = verify(trace.single_action, view)
    assert receipt.status.value == "unknown"
    graph = build_graph(replace(trace, observations=(view,), verifications=(receipt,)))
    witnesses = [node for node in graph.nodes if node.kind == "observed_external_effect"]
    assert len(witnesses) == 2 and len({node.id for node in witnesses}) == 2
    assert {node.data["amount_minor"] for node in witnesses} == {500_000, 250_000}
    assert {node.data["actor"] for node in witnesses} == {trace.single_action.actor, "another_actor"}


def test_witness_identifiers_do_not_collide_when_source_identities_contain_delimiters():
    trace = run_scenario().trace
    view = trace.observations[0]
    records = tuple(dict(view.records[0], effect_id=value) for value in ("c", "b:c"))
    observations = tuple(replace(view, observation_id=value, records=records)
                         for value in ("a:b", "a"))
    graph = build_graph(replace(trace, observations=observations,
                               verifications=tuple(verify(trace.single_action, item)
                                                   for item in observations)))
    witnesses = [node for node in graph.nodes if node.kind == "observed_external_effect"]
    assert len(witnesses) == len({node.id for node in witnesses}) == 4
    assert {(node.data["witness_observation_id"], node.data["effect_id"])
            for node in witnesses} == {(view_id, effect_id)
                                      for view_id in ("a:b", "a") for effect_id in ("c", "b:c")}


def test_event_identity_cannot_overwrite_a_generated_repeated_effect_witness():
    trace = run_scenario().trace
    view = trace.observations[0]
    later = replace(view, observation_id="later")
    trace = replace(trace, observations=(view, later),
                    verifications=tuple(verify(trace.single_action, item) for item in (view, later)))
    witness = next(node for node in build_graph(trace).nodes
                   if node.kind == "observed_external_effect")
    additional = replace(trace.events[0], id=witness.id)
    with pytest.raises(ValueError, match="identity conflicts"):
        build_graph(replace(trace, events=(*trace.events, additional)))


@pytest.mark.parametrize("committed_at", [0, 4, 101])
def test_origin_edge_requires_a_temporally_possible_witness(committed_at):
    trace = run_scenario().trace
    view = trace.observations[0]
    view = replace(view, records=(dict(view.records[0], committed_at_ms=committed_at),))
    graph = build_graph(replace(trace, observations=(view,),
                               verifications=(verify(trace.single_action, view),)))
    assert not any(edge.kind == "EFFECT" for edge in graph.edges)


@pytest.mark.parametrize("reserved", [
    {"witness_observation_id": "source-specific-value"},
    {"witness_observation_id": {"provider": [17, None]}},
    {"source_record": "source-owned-value"},
    {"witness_observation_id": "source-specific-value", "source_record": {"original": True}},
])
@pytest.mark.parametrize("repeated", [False, True])
def test_reserved_graph_metadata_preserves_the_complete_verbatim_source_record(reserved, repeated):
    trace = run_scenario().trace
    view = trace.observations[0]
    view = replace(view, records=(dict(view.records[0], **reserved),))
    observations = (view, replace(view, observation_id="later")) if repeated else (view,)
    trace = replace(trace, observations=observations,
                    verifications=tuple(verify(trace.single_action, item) for item in observations))
    graph = build_graph(trace)
    witnesses = [node for node in graph.nodes if node.kind == "observed_external_effect"]
    assert len(witnesses) == len(observations)
    for witness in witnesses:
        captured = next(item for item in observations
                        if item.observation_id == witness.data["witness_observation_id"])
        assert witness.data["source_record"] == captured.records[0]
        assert {key: witness.data["source_record"][key] for key in reserved} == reserved
        # Serialization and graph metadata must not mutate the adapter's record.
        assert {key: captured.records[0][key] for key in reserved} == reserved
