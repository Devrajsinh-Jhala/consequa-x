"""Read frozen public protocol metadata only; no model or native task runs."""
from __future__ import annotations

import copy

import pytest

from scripts import declare_limbo_followup as declaration


@pytest.fixture(scope="module")
def original():
    path = declaration.ROOT / "output/limbo-protocol-2026-10-24/protocol.json"
    assert declaration.file_binding(path) == {
        "sha256": "8896a371b2c5f854293f8c4f1ee049bf8aeaab9b254c36f2e25de1b2b79881c6",
        "bytes": 118781,
    }
    return declaration.load(path)


@pytest.fixture
def followup(original):
    value = copy.deepcopy(original)
    value["runtime_binding"]["model"] = "invented-relocated-alias:ctx8k"
    for row in value["schedule"]:
        row["spec"]["model"] = value["runtime_binding"]["model"]
    return value


def set_value(value, path, new):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = new


def test_declared_alias_and_relocated_runtime_paths_preserve_scientific_design(original, followup):
    before = copy.deepcopy(original)
    followup["created_utc"] = "invented-later-date"
    followup["wheel"]["path"] = "C:/invented-relocation/package.whl"
    for key in ("executable", "base_executable"):
        followup["environment"][key]["path"] = "C:/invented-relocation/python.exe"
    for key in ("model_blob", "runner_executable", "server_executable"):
        followup["runtime_binding"][key] = "C:/invented-relocation/" + key
    # Runtime executable identities can change only as a separately declared
    # execution condition; model weights and all scientific settings stay held.
    followup["runtime_binding"]["server_executable_sha256"] = "0" * 64
    followup["runtime_binding"]["runner_executable_sha256"] = "1" * 64
    declaration.compare_design(original, followup)
    assert original == before
    assert followup["schedule"][0]["spec"]["model"] == "invented-relocated-alias:ctx8k"


@pytest.mark.parametrize("path,new", [
    (("schema",), "invented-schema-v2"),
    (("seed",), 1702),
    (("metadata", 0, "index"), 987654321),
    (("metadata", 0, "template"), "invented-replacement-template"),
    (("arms", 0), "invented-arm"),
    (("limits", "max_requests"), 17),
    (("limits", "max_output_tokens"), 513),
    (("limits", "request_timeout_s"), 1201),
    (("limits", "episode_timeout_s"), 7201),
    (("limits", "work", "execute"), 97),
    (("limits", "work", "verify"), 65),
    (("limits", "work", "wait"), 65),
    (("limits", "work", "total_wait_seconds"), 172801),
    (("claims", "human_available"), True),
    (("claims", "paid_inference"), True),
    (("claims", "retry_resume_replacement"), True),
    (("endpoints", "primary"), "Invented replacement endpoint"),
    (("native", "commit"), "0" * 40),
    (("native", "files", "limbo/__init__.py", "sha256"), "0" * 64),
    (("sources", "research/limbo_agent/transport.py", "sha256"), "0" * 64),
])
def test_changed_registered_selection_control_limits_sources_or_endpoints_fail(original, followup, path, new):
    set_value(followup, path, new)
    with pytest.raises(ValueError, match="Original design changed"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("field,new", [
    ("template", "invented-template"), ("index", 987654321),
    ("focal", "invented-focal"), ("mode", "invented-fault"),
    ("policy", "invented-policy"), ("human_available", True),
    ("contract", "invented-contract"), ("max_tool_calls", 17),
    ("experiment", "invented-experiment"), ("paraphrase", 1),
    ("replicate", 1), ("doc_variant", "invented-documentation"),
    ("harness", "invented-harness"), ("instruction_variant", "invented-instructions"),
    ("reasoning_effort", "high"),
])
def test_every_slot_scientific_specification_remains_frozen(original, followup, field, new):
    followup["schedule"][0]["spec"][field] = new
    with pytest.raises(ValueError, match="cases, arms or limits"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("field,new", [
    ("slot", 99), ("world_rank", 99), ("arm", "invented-arm"),
])
def test_slot_identity_and_order_remain_frozen(original, followup, field, new):
    followup["schedule"][0][field] = new
    with pytest.raises(ValueError, match="cases, arms or limits"):
        declaration.compare_design(original, followup)


def test_selected_fault_metadata_cannot_change(original, followup):
    followup["schedule"][0]["metadata"]["mode"] = "invented-fault"
    with pytest.raises(ValueError, match="cases, arms or limits"):
        declaration.compare_design(original, followup)


def test_reordered_slot_list_cannot_pass(original, followup):
    followup["schedule"][0], followup["schedule"][1] = followup["schedule"][1], followup["schedule"][0]
    with pytest.raises(ValueError, match="cases, arms or limits"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("delta", [-1, 1])
def test_omitted_or_extra_slots_cannot_change_denominator(original, followup, delta):
    if delta < 0:
        followup["schedule"].pop()
    else:
        followup["schedule"].append(copy.deepcopy(followup["schedule"][-1]))
    with pytest.raises(ValueError, match="96 planned slots"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("namespace", ["sources", "native"])
def test_source_inventory_cannot_gain_or_lose_files(original, followup, namespace):
    inventory = followup[namespace] if namespace == "sources" else followup["native"]["files"]
    inventory["invented.py"] = {"sha256": "0" * 64, "bytes": 1}
    with pytest.raises(ValueError, match="Original design changed"):
        declaration.compare_design(original, followup)
    inventory.pop("invented.py")
    inventory.pop(next(iter(inventory)))
    with pytest.raises(ValueError, match="Original design changed"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("field,new", [
    ("model_blob_sha256", "0" * 64), ("model_digest", "0" * 64),
    ("context_tokens", 8193), ("parallel_slots", 2),
    ("parallel_slots", True), ("context_tokens", 8192.0),
])
def test_weight_cache_and_runtime_configuration_cannot_change(original, followup, field, new):
    followup["runtime_binding"][field] = new
    with pytest.raises(ValueError, match="weights/configuration"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("which", ["original", "followup"])
def test_individual_slot_cannot_escape_its_declared_alias(original, followup, which):
    original = copy.deepcopy(original)
    (original if which == "original" else followup)["schedule"][0]["spec"]["model"] = "invented-other-model"
    with pytest.raises(ValueError, match="declared runtime alias"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("field", ["sha256", "bytes"])
def test_same_named_sdk_version_cannot_use_different_wheel_bytes(original, followup, field):
    followup["wheel"][field] = "0" * 64 if field == "sha256" else followup["wheel"]["bytes"] + 1
    with pytest.raises(ValueError, match="SDK wheel"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("field", ["python_version", "implementation", "distributions"])
def test_interpreter_and_dependency_versions_cannot_change(original, followup, field):
    if field == "distributions":
        followup["environment"][field]["consequa-x"] = "2.1.2"
    else:
        followup["environment"][field] = "invented-other-version"
    with pytest.raises(ValueError, match="interpreter/dependency versions"):
        declaration.compare_design(original, followup)


@pytest.mark.parametrize("binary", ["executable", "base_executable"])
@pytest.mark.parametrize("field", ["sha256", "bytes"])
def test_interpreter_payload_identity_remains_frozen(original, followup, binary, field):
    value = followup["environment"][binary]
    value[field] = "0" * 64 if field == "sha256" else value["bytes"] + 1
    with pytest.raises(ValueError, match="interpreter bytes"):
        declaration.compare_design(original, followup)


def test_identity_byte_count_cannot_use_numerically_equal_float(original, followup):
    followup["wheel"]["bytes"] = float(followup["wheel"]["bytes"])
    with pytest.raises(ValueError, match="SDK wheel"):
        declaration.compare_design(original, followup)
