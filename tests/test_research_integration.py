"""Regression coverage for additive replay targets and independent seed keys."""

from unittest.mock import patch

import pytest

from consequa_x import cli
from consequa_x.adapters.ollama import OllamaPolicy
from consequa_x.attribution import Intervention, leave_one_out
from consequa_x.benchmark.payments import Fault
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from consequa_x.benchmark.runner import RefundReplayRunner, ScenarioConfig, run_scenario
from consequa_x.graph import build_graph
from consequa_x.policies import ScriptedRefundPolicy


def test_state_and_linked_influence_edges_for_same_candidate_are_both_retained():
    config = ScenarioConfig(fault=Fault.CLEAN)
    runner = RefundReplayRunner(config)
    candidate = Intervention("vip_policy")
    estimates = tuple(leave_one_out(runner, (candidate,), samples=2, target=target)[0]
                      for target in ("consequence", "action_linked_consequence"))
    graph = build_graph(run_scenario(config).trace, estimates)
    edges = [edge for edge in graph.edges if edge.kind == "ESTIMATED_INFLUENCE"]
    assert len(edges) == 2
    assert {edge.data["target"] for edge in edges} == {"consequence", "action_linked_consequence"}


def test_policy_seed_changes_recorded_model_keys_without_changing_world_or_public_inputs():
    config = ScenarioConfig(fault=Fault.CLEAN)
    first = run_policy_scenario(config, ScriptedRefundPolicy(), seed=4)
    second = run_policy_scenario(config, ScriptedRefundPolicy(), seed=4, policy_seed=99)
    assert first.trace.action == second.trace.action
    assert first.trace.responses == second.trace.responses
    assert first.trace.observations == second.trace.observations
    first_events = [event for event in first.trace.events if "policy_request" in event.data]
    second_events = [event for event in second.trace.events if "policy_request" in event.data]
    assert [event.data["model_seed"] for event in first_events] == [24, 25]
    assert [event.data["model_seed"] for event in second_events] == [594, 595]
    assert [event.data["policy_request"] for event in first_events] == [
        event.data["policy_request"] for event in second_events
    ]


@pytest.mark.parametrize("seed", [True, -1, MAX_TRIAL_SEED + 1, "3"])
def test_invalid_independent_policy_seed_rejected_before_provider(seed):
    with patch.object(ScriptedRefundPolicy, "decide") as decide:
        with pytest.raises(ValueError):
            run_policy_scenario(ScenarioConfig(), ScriptedRefundPolicy(), policy_seed=seed)
    decide.assert_not_called()


@pytest.mark.parametrize("targets", ["bad", "action,action", "action,", ""])
def test_invalid_cli_target_selection_rejected_before_provider_or_artifacts(tmp_path, targets):
    output = tmp_path / "invalid"
    with patch.object(OllamaPolicy, "list_models") as listing:
        assert cli.main(["model-experiment", "--provider", "ollama", "--model", "fake",
                         "--targets", targets, "--output", str(output)]) == 2
    listing.assert_not_called()
    assert not output.exists()


def test_cli_three_targets_survive_graph_export_without_extra_model_calls(tmp_path):
    import json

    output = tmp_path / "three-targets"
    assert cli.main(["model-experiment", "--case", "clean", "--candidates", "vip_policy",
                     "--targets", "action,consequence,action_linked_consequence", "--samples", "2",
                     "--template", "refund-support-note-v1", "--output", str(output)]) == 0
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert result["summary"]["policy_calls"] == 6
    assert result["template"]["template_id"] == "refund-support-note-v1"
    assert len(result["estimates"]) == 3
    explanation = json.loads((output / result["attribution_explanation"]).read_text(encoding="utf-8"))
    edges = [edge for edge in explanation["graph"]["edges"] if edge["kind"] == "ESTIMATED_INFLUENCE"]
    assert {edge["data"]["target"] for edge in edges} == {
        "action", "consequence", "action_linked_consequence",
    }
