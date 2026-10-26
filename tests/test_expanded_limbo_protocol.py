"""New prospective design checks; synthetic metadata is never study evidence."""
from collections import Counter, defaultdict
from copy import deepcopy

import pytest

from research.expanded_limbo.protocol import (
    ARMS, FAULTS, build_protocol, candidate_indices, canonical, make_schedule,
    validate_metadata, validate_models, verify_protocol_structure,
)


def binding(character="a"):
    return {"sha256": character * 64, "bytes": 123}


@pytest.fixture
def proposal_inputs():
    templates = [f"template_{i:02d}" for i in range(12)]
    exposure = {"complete_known_exposure_attested": True,
        "sources": {"historical-protocol.json": binding()},
        "by_template": {t: [0, 1, 1022, 987654] for t in templates}}
    indices = candidate_indices(templates, exposure, selection_seed="synthetic-fixed-seed")
    metadata = []
    for position, template in enumerate(templates):
        for index in indices[template]:
            metadata.append({"template": template, "index": index, "family": "synthetic",
                "domains": ["data"], "horizon": "long" if position == 0 else "short",
                "focals": [{"label": "write", "tool": "db_insert_many", "domain": "data",
                    "batch": position == 0, "verification": "strong", "idempotency": "non_idempotent",
                    "reversible": True, "supports_schema_drift": position == 1}]})
    models = [{"id": family + "-fixture", "family": family, "checkpoint": "synthetic-test-only",
        "quantization": "fixture", "weights": binding(c), "tokenizer": binding(c),
        "chat_template": binding(c), "license": binding(c), "context_tokens": 8192,
        "transport_preflight": binding(c)} for family, c in zip(("qwen", "llama", "granite"), "bcd")]
    return {"metadata": metadata, "models": models, "exposure": exposure,
        "selection_seed": "synthetic-fixed-seed", "source_files": {"new/protocol.py": binding()},
        "native_files": {"limbo/agent.py": binding()}, "wheel_binding": binding()}


def test_fixed_full_matrix_counts_and_rare_fault_coverage(proposal_inputs):
    protocol = build_protocol(**proposal_inputs)
    assert protocol["counts"] == {"base_instances": 48, "templates": 12,
        "assigned_worlds": 144, "models": 3, "generation_replicates": 2,
        "arms": 4, "planned_slots": 3456, "blocks": 72}
    modes = Counter(w["metadata"]["mode"] for w in protocol["worlds"])
    assert modes["none"] == 48
    assert sum(v for k, v in modes.items() if k != "none") == 96
    assert set(modes) == {"none", *FAULTS}
    by_base = defaultdict(list)
    for world in protocol["worlds"]:
        by_base[world["base_rank"]].append(world["metadata"])
    assert len(by_base) == 48
    for rows in by_base.values():
        assert len(rows) == 3 and rows[0]["mode"] == "none"
        assert rows[1]["mode"] != rows[2]["mode"]
    for world in protocol["worlds"]:
        mode, affordance = world["metadata"]["mode"], world["metadata"]["affordances"]
        if mode == "partial_timeout":
            assert affordance["batch"]
        if mode == "schema_drift":
            assert affordance["supports_schema_drift"]


def test_every_model_seed_world_has_all_paired_arms(proposal_inputs):
    protocol = build_protocol(**proposal_inputs)
    pairs = defaultdict(list)
    for row in protocol["schedule"]:
        pairs[row["model_id"], row["generation_seed"], row["world_rank"]].append(row)
        assert row["spec"]["human_available"] is False
        assert row["spec"]["model"] == row["model_id"]
        assert row["spec"]["policy"] == row["arm"]
        assert row["temperature"] == 0.2
    assert len(pairs) == 3 * 2 * 144
    for rows in pairs.values():
        assert {r["arm"] for r in rows} == set(ARMS)
        assert len({canonical(r["metadata"]) for r in rows}) == 1
    assert [r["slot"] for r in protocol["schedule"]] == list(range(3456))
    assert len({canonical(r["spec"]) for r in protocol["schedule"]}) == 3456


def test_static_blocks_cover_every_slot_once_and_one_model(proposal_inputs):
    protocol = build_protocol(**proposal_inputs)
    covered = []
    for block in protocol["blocks"]:
        first, count = block["first_slot"], block["slot_count"]
        rows = protocol["schedule"][first:first + count]
        assert count == 48
        assert {r["block_id"] for r in rows} == {block["block_id"]}
        assert {r["model_id"] for r in rows} == {block["model_id"]}
        assert {r["generation_seed"] for r in rows} == {block["generation_seed"]}
        assert len({r["world_rank"] for r in rows}) == 12
        covered.extend(r["slot"] for r in rows)
    assert covered == list(range(3456))
    # Model order rotates between fixed world blocks, independent of results.
    assert [b["model_id"] for b in protocol["blocks"][:3]] != [
        b["model_id"] for b in protocol["blocks"][3:6]]


def test_reconstruction_is_exact_and_input_order_independent(proposal_inputs):
    protocol = build_protocol(**proposal_inputs)
    assert verify_protocol_structure(protocol) is protocol
    other = deepcopy(proposal_inputs)
    other["metadata"].reverse()
    rebuilt = build_protocol(**other)
    assert protocol["worlds"] == rebuilt["worlds"]
    assert protocol["schedule"] == rebuilt["schedule"]


@pytest.mark.parametrize("mutation", ["slot_arm", "seed", "temperature", "block", "claim", "count"])
def test_reconstruction_rejects_changed_plan(proposal_inputs, mutation):
    protocol = build_protocol(**proposal_inputs)
    if mutation == "slot_arm":
        protocol["schedule"][0]["arm"] = "other"
    elif mutation == "seed":
        protocol["schedule"][0]["generation_seed"] += 1
    elif mutation == "temperature":
        protocol["schedule"][0]["temperature"] = 0.9
    elif mutation == "block":
        protocol["blocks"][0]["slot_count"] -= 1
    elif mutation == "claim":
        protocol["claims"]["task_population_inference"] = True
    else:
        protocol["counts"]["base_instances"] = 3456
    with pytest.raises(ValueError, match="reconstruction"):
        verify_protocol_structure(protocol)


def test_fresh_indices_exclude_all_bound_prior_exposure(proposal_inputs):
    exposure = proposal_inputs["exposure"]
    templates = sorted(exposure["by_template"])
    first = candidate_indices(templates, exposure, selection_seed="synthetic-fixed-seed")
    for template in templates:
        assert not set(first[template]) & set(exposure["by_template"][template])
        exposure["by_template"][template].append(first[template][0])
    next_plan = candidate_indices(templates, exposure, selection_seed="synthetic-fixed-seed")
    for template in templates:
        assert first[template][0] not in next_plan[template]
        assert len(next_plan[template]) == 4


@pytest.mark.parametrize("mutation", ["unattested", "missing_source", "missing_development", "bad_binding"])
def test_exposure_ledger_is_required(proposal_inputs, mutation):
    exposure = proposal_inputs["exposure"]
    if mutation == "unattested":
        exposure["complete_known_exposure_attested"] = False
    elif mutation == "missing_source":
        exposure["sources"] = {}
    elif mutation == "missing_development":
        exposure["by_template"]["template_00"].remove(1)
    else:
        exposure["sources"]["historical-protocol.json"]["sha256"] = "latest"
    with pytest.raises(ValueError):
        build_protocol(**proposal_inputs)


@pytest.mark.parametrize("field", ["instruction", "targets", "match", "setup", "grade"])
def test_privileged_task_fields_cannot_enter_metadata(proposal_inputs, field):
    proposal_inputs["metadata"][0][field] = "forbidden fixture"
    with pytest.raises(ValueError, match="privileged"):
        build_protocol(**proposal_inputs)


@pytest.mark.parametrize("field", ["match", "expected", "target", "outcome"])
def test_privileged_focal_fields_cannot_enter_metadata(proposal_inputs, field):
    proposal_inputs["metadata"][0]["focals"][0][field] = "forbidden fixture"
    with pytest.raises(ValueError, match="privileged"):
        build_protocol(**proposal_inputs)


def test_metadata_must_exactly_match_index_plan(proposal_inputs):
    indices = candidate_indices(sorted(proposal_inputs["exposure"]["by_template"]),
        proposal_inputs["exposure"], selection_seed="synthetic-fixed-seed")
    proposal_inputs["metadata"][0]["index"] = 0
    with pytest.raises(ValueError, match="fresh index plan"):
        validate_metadata(proposal_inputs["metadata"], indices)


@pytest.mark.parametrize("mutation", ["family", "weights", "context", "preflight", "extra"])
def test_exact_three_family_model_bindings_required(proposal_inputs, mutation):
    models = proposal_inputs["models"]
    if mutation == "family":
        models[2]["family"] = "qwen"
    elif mutation == "weights":
        models[2]["weights"]["sha256"] = "mutable-latest-alias"
    elif mutation == "context":
        models[2]["context_tokens"] = 16384
    elif mutation == "preflight":
        del models[2]["transport_preflight"]
    else:
        models[2]["api_key"] = "forbidden fixture"
    with pytest.raises(ValueError):
        validate_models(models)


def test_zero_temperature_repeats_are_not_claimed_as_stochastic(proposal_inputs):
    protocol = build_protocol(**proposal_inputs, temperature=0)
    assert protocol["claims"]["stochastic_generation_intended"] is False
    assert protocol["claims"]["seed_support_and_variation_require_measured_validation"] is True


@pytest.mark.parametrize("seeds", [[1701], [1701, 1701], [True, 2], [-1, 2]])
def test_invalid_generation_seed_matrix_refused(proposal_inputs, seeds):
    with pytest.raises(ValueError, match="generation seeds"):
        build_protocol(**proposal_inputs, generation_seeds=seeds)


@pytest.mark.parametrize("temperature", [True, -0.1, 2.1, float("nan"), float("inf")])
def test_invalid_temperature_refused(proposal_inputs, temperature):
    with pytest.raises(ValueError, match="temperature"):
        build_protocol(**proposal_inputs, temperature=temperature)


def test_missing_rare_fault_affordance_is_explicit_failure(proposal_inputs):
    for row in proposal_inputs["metadata"]:
        for focal in row["focals"]:
            focal["batch"] = False
    with pytest.raises(ValueError, match="no compatible"):
        build_protocol(**proposal_inputs)


def test_short_last_blocks_preserve_all_planned_slots(proposal_inputs):
    protocol = build_protocol(**proposal_inputs, worlds_per_block=17)
    assert sum(b["slot_count"] for b in protocol["blocks"]) == 3456
    assert protocol["blocks"][-1]["slot_count"] == 32


def test_no_inference_or_old_protocol_required_to_plan(proposal_inputs, monkeypatch):
    import socket
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("Planning must not start processes or connect")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    protocol = build_protocol(**proposal_inputs)
    assert protocol["counts"]["planned_slots"] == 3456


def test_schedule_rejects_noncontiguous_world_ranks(proposal_inputs):
    protocol = build_protocol(**proposal_inputs)
    worlds = deepcopy(protocol["worlds"])
    worlds[1]["world_rank"] = 0
    with pytest.raises(ValueError, match="contiguous"):
        make_schedule(worlds, protocol["models"], generation_seeds=[1701, 2718], temperature=0.2)
