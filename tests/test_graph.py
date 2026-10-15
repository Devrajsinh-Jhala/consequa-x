"""Graph links show observed evidence; replay overlays are explicitly experimental."""

from dataclasses import replace

import pytest

from consequa_x.attribution import EffectEstimate, Intervention, leave_one_out
from consequa_x.benchmark.runner import (
    RefundReplayRunner,
    demo_scenarios,
    run_scenario,
)
from consequa_x.explanation import explain
from consequa_x.graph import build_graph
from consequa_x.models import EventType, OriginStatus
from consequa_x.verification import verify


def configs():
    return {config.name: config for config in demo_scenarios()}


def links(graph, kind):
    return {(edge.source, edge.target) for edge in graph.edges if edge.kind == kind}


def test_timeout_response_and_committed_effect_have_separate_graph_branches():
    episode = run_scenario(seed=5)
    graph = episode.explanation.graph
    effect_id = episode.trace.verifications[-1].effect_ids[0]
    assert links(graph, "RESPONSE") == {("dispatch_1", "response_1")}
    assert links(graph, "EFFECT") == {("dispatch_1", f"effect:{effect_id}")}
    assert all(edge.source != "response_1" for edge in graph.edges if edge.kind == "EFFECT")
    by_id = {node.id: node for node in graph.nodes}
    assert by_id["response_1"].data["status"] == "timeout"
    assert by_id[f"effect:{effect_id}"].kind == "observed_external_effect"
    assert by_id[f"effect:{effect_id}"].data["status"] == "processed"


@pytest.mark.parametrize("config", demo_scenarios(), ids=lambda config: config.name)
def test_default_graph_contains_only_evidence_links_with_valid_endpoints(config):
    graph = run_scenario(config).explanation.graph
    ids = {node.id for node in graph.nodes}
    assert len(ids) == len(graph.nodes)
    assert all(edge.source in ids and edge.target in ids for edge in graph.edges)
    assert {edge.kind for edge in graph.edges} <= {
        "DEPENDENCY", "TEMPORAL", "RESPONSE", "EFFECT", "OBSERVATION",
        "CONTRACT", "VERIFICATION", "IDENTITY",
    }
    assert not links(graph, "ESTIMATED_INFLUENCE")
    assert all(edge.basis != "isolated_simulated_intervention" for edge in graph.edges)


def test_origin_links_require_observed_provenance_not_matching_state_or_timing():
    for name in ("external_actor", "missing_provenance"):
        episode = run_scenario(configs()[name])
        assert episode.trace.verifications[-1].effect_ids
        assert not links(episode.explanation.graph, "EFFECT")
        assert links(episode.explanation.graph, "OBSERVATION")


def test_idempotent_retry_links_effect_to_original_attempt_only():
    safe = run_scenario(configs()["safe_retry"])
    unsafe = run_scenario(configs()["unsafe_retry"])
    assert links(safe.explanation.graph, "RESPONSE") == {
        ("dispatch_1", "response_1"), ("dispatch_2", "response_2"),
    }
    assert {source for source, _ in links(safe.explanation.graph, "EFFECT")} == {"dispatch_1"}
    assert {source for source, _ in links(unsafe.explanation.graph, "EFFECT")} == {
        "dispatch_1", "dispatch_2",
    }


def test_reconciled_graph_retains_both_observation_and_verification_records():
    episode = run_scenario(configs()["delayed_reconciled"])
    graph = episode.explanation.graph
    by_id = {node.id: node for node in graph.nodes}
    contract_id = episode.trace.action.contract.contract_id
    first_id, second_id = (f"verification:{contract_id}:{index}" for index in range(2))
    assert by_id[first_id].data["status"] == "unknown"
    assert by_id[second_id].data["status"] == "satisfied"
    for index, observation in enumerate(episode.trace.observations):
        assert (f"observation:{observation.observation_id}",
                f"verification:{contract_id}:{index}") in links(graph, "VERIFICATION")


def test_experimental_overlays_are_explicit_and_target_the_registered_estimand():
    config = configs()["unsafe_retry"]
    episode = run_scenario(config)
    runner = RefundReplayRunner(config)
    candidates = (Intervention("retry_instruction"),)
    action_estimates = leave_one_out(runner, candidates, samples=4, target="action")
    consequence_estimates = leave_one_out(runner, candidates, samples=4, target="consequence")
    graph = build_graph(episode.trace, action_estimates + consequence_estimates)
    assert links(graph, "ESTIMATED_INFLUENCE") == {
        ("retry_instruction", "refund_decision"),
        ("retry_instruction", f"contract:{episode.trace.action.contract.contract_id}"),
    }
    experimental = [edge for edge in graph.edges if edge.kind == "ESTIMATED_INFLUENCE"]
    assert {edge.basis for edge in experimental} == {"isolated_simulated_intervention"}
    assert {edge.data["effect"] for edge in experimental} == {0, -1}
    assert explain(episode.trace, consequence_estimates).attribution == consequence_estimates
    assert not episode.explanation.attribution


def test_overlay_candidate_must_be_captured_in_the_explained_trace():
    episode = run_scenario()
    (estimate,) = leave_one_out(RefundReplayRunner(), (Intervention("vip_policy"),),
                               samples=4, target="action")
    with pytest.raises(ValueError, match="candidate"):
        build_graph(episode.trace, (replace(estimate, event_id="not_in_trace"),))


def test_conflicting_actor_metadata_does_not_assert_dispatch_effect_origin():
    episode = run_scenario(configs()["clean"])
    observation = episode.trace.observations[0]
    record = dict(observation.records[0], actor="some_other_actor")
    observation = replace(observation, records=(record,))
    verification = verify(episode.trace.action, observation)
    assert verification.origin is OriginStatus.UNKNOWN
    trace = replace(episode.trace, observations=(observation,), verifications=(verification,))
    assert not links(build_graph(trace), "EFFECT")


def test_origin_join_checks_action_identity_on_both_dispatch_and_readback():
    trace = run_scenario(configs()["clean"]).trace
    events = tuple(replace(event, data={**event.data, "action_id": "another_action"})
                   if event.type is EventType.ACTION_DISPATCH else event for event in trace.events)
    conflicting = replace(trace, events=events)
    assert conflicting.verifications[-1].origin is OriginStatus.CONFIRMED
    assert links(build_graph(conflicting), "RESPONSE") == {("dispatch_1", "response_1")}
    assert not links(build_graph(conflicting), "EFFECT")


@pytest.mark.parametrize("value", [None, [], {}, 7, False])
def test_arbitrary_json_attempt_payloads_are_not_used_as_identity_joins(value):
    trace = run_scenario(configs()["clean"]).trace
    events = tuple(replace(event, data={**event.data, "attempt_id": value})
                   if event.type in {EventType.ACTION_DISPATCH, EventType.TOOL_RESPONSE}
                   else event for event in trace.events)
    graph = build_graph(replace(trace, events=events))
    assert not links(graph, "RESPONSE")
    assert not links(graph, "EFFECT")


def successive_readbacks(*changes):
    """Capture independent observations; do not rewrite an earlier receipt."""
    trace = run_scenario(configs()["clean"]).trace
    original = trace.observations[0]
    observations = (original,) + tuple(
        replace(original, observation_id=f"readback_{index}",
                observed_at_ms=200 + index, as_of_ms=200 + index,
                records=(dict(original.records[0], **change),))
        for index, change in enumerate(changes, start=1)
    )
    return replace(trace, observations=observations,
                   verifications=tuple(verify(trace.action, view) for view in observations))


def effect_witnesses(graph):
    return {node.data["witness_observation_id"]: node
            for node in graph.nodes if node.kind == "observed_external_effect"}


def test_conflicting_later_origin_cannot_overwrite_an_earlier_witness_and_inherit_its_edge():
    trace = successive_readbacks({"actor": "another_actor"})
    graph = build_graph(trace)
    witnesses = effect_witnesses(graph)
    original_id = trace.observations[0].observation_id
    earlier, later = witnesses[original_id], witnesses["readback_1"]
    assert trace.verifications[-1].origin is OriginStatus.UNKNOWN
    assert earlier.data["actor"] == trace.action.actor
    assert later.data["actor"] == "another_actor"
    assert links(graph, "EFFECT") == {("dispatch_1", earlier.id)}
    identity = next(node for node in graph.nodes if node.kind == "external_effect_identity")
    assert set(identity.data) == {"effect_id", "witness_node_ids"}
    assert identity.data["witness_node_ids"] == sorted((earlier.id, later.id))
    assert links(graph, "IDENTITY") == {(earlier.id, identity.id), (later.id, identity.id)}
    assert links(graph, "OBSERVATION") == {
        (earlier.id, f"observation:{original_id}"), (later.id, "observation:readback_1"),
    }


def test_corrected_payload_and_verification_retain_their_own_evidence():
    trace = successive_readbacks({"amount_minor": 250_000})
    graph = build_graph(trace)
    witnesses = effect_witnesses(graph)
    assert witnesses[trace.observations[0].observation_id].data["amount_minor"] == 500_000
    assert witnesses["readback_1"].data["amount_minor"] == 250_000
    assert [receipt.status.value for receipt in trace.verifications] == ["satisfied", "violated"]
    for index, view in enumerate(trace.observations):
        receipt_id = f"verification:{trace.action.contract.contract_id}:{index}"
        observed = {edge.source for edge in graph.edges
                    if edge.kind == "VERIFICATION" and edge.target == receipt_id
                    and edge.basis == "predicate_evidence"}
        assert observed == {witnesses[view.observation_id].id}


def test_later_compensation_preserves_processed_and_reversed_snapshot_states():
    trace = successive_readbacks({"status": "reversed", "reversed_at_ms": 150})
    graph = build_graph(trace)
    witnesses = effect_witnesses(graph)
    earlier = witnesses[trace.observations[0].observation_id]
    later = witnesses["readback_1"]
    assert earlier.data["status"] == "processed"
    assert "reversed_at_ms" not in earlier.data
    assert later.data["status"] == "reversed" and later.data["reversed_at_ms"] == 150
    # Both receipts concern the original deadline, before the later reversal.
    assert all(receipt.status.value == "satisfied" for receipt in trace.verifications)
    assert links(graph, "EFFECT") == {("dispatch_1", earlier.id), ("dispatch_1", later.id)}


def test_observation_order_does_not_change_witness_payloads_or_semantic_links():
    trace = successive_readbacks({"actor": "another_actor"},
                                {"status": "reversed", "reversed_at_ms": 150})
    forward = build_graph(trace)
    reverse = build_graph(replace(trace, observations=tuple(reversed(trace.observations))))
    assert {node.id: (node.kind, node.time_ms, node.data) for node in forward.nodes} == {
        node.id: (node.kind, node.time_ms, node.data) for node in reverse.nodes}
    assert {(edge.source, edge.target, edge.kind, edge.basis) for edge in forward.edges} == {
        (edge.source, edge.target, edge.kind, edge.basis) for edge in reverse.edges}


def test_repeated_identical_records_still_preserve_each_observation_witness():
    trace = successive_readbacks({})
    graph = build_graph(trace)
    witnesses = effect_witnesses(graph)
    assert set(witnesses) == {view.observation_id for view in trace.observations}
    assert len({node.id for node in witnesses.values()}) == 2
    for view in trace.observations:
        assert witnesses[view.observation_id].data == {
            **view.records[0], "witness_observation_id": view.observation_id,
        }


def test_later_missing_provenance_does_not_inherit_the_earlier_origin():
    trace = successive_readbacks({})
    later = trace.observations[-1]
    record = {key: value for key, value in later.records[0].items()
              if key not in {"action_id", "attempt_id", "actor"}}
    later = replace(later, records=(record,))
    trace = replace(trace, observations=(trace.observations[0], later),
                    verifications=(trace.verifications[0], verify(trace.action, later)))
    graph = build_graph(trace)
    witnesses = effect_witnesses(graph)
    earlier_id = trace.observations[0].observation_id
    assert trace.verifications[-1].origin is OriginStatus.UNKNOWN
    assert links(graph, "EFFECT") == {("dispatch_1", witnesses[earlier_id].id)}
    assert not {"action_id", "attempt_id", "actor"} & witnesses[later.observation_id].data.keys()


def test_verification_never_borrows_an_effect_record_from_another_observation():
    trace = successive_readbacks({})
    missing_view = replace(trace.observations[-1], records=())
    # A structurally valid imported receipt can claim an effect absent from its
    # source snapshot. Structural decoding does not authenticate that claim.
    trace = replace(trace, observations=(trace.observations[0], missing_view))
    graph = build_graph(trace)
    later_id = f"verification:{trace.action.contract.contract_id}:1"
    assert not {edge.source for edge in graph.edges
                if edge.kind == "VERIFICATION" and edge.target == later_id
                and edge.basis == "predicate_evidence"}


@pytest.mark.parametrize("candidate_kind", ["contract", "observation", "effect", "witness", "verification"])
def test_generated_evidence_nodes_cannot_be_replay_attribution_candidates(candidate_kind):
    trace = successive_readbacks({})
    kinds = {"contract": "postcondition", "observation": "external_observation",
             "effect": "external_effect_identity", "witness": "observed_external_effect",
             "verification": "verification"}
    generated = next(node for node in build_graph(trace).nodes
                     if node.kind == kinds[candidate_kind])
    estimate = EffectEstimate(generated.id, "action", 0.5, 0.5, 0.0, (-0.5, 0.5), 2, (1, 2))
    with pytest.raises(ValueError, match="captured trace event"):
        build_graph(trace, (estimate,))
