"""Imported traces must not turn ambiguous identities into provider-origin claims."""

from dataclasses import replace

import pytest

from consequa_x.benchmark.runner import run_scenario
from consequa_x.graph import build_graph
from consequa_x.models import EventType


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
