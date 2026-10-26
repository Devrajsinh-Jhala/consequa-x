"""Metadata-only prospective design for a new multi-model LIMBO condition.

This module does not execute an episode, contact a provider, load weights, or
modify the previously frozen research. Generating metadata may construct a
native task in a trusted extractor; only explicitly permitted metadata exits.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys


SCHEMA = "conseqax-expanded-limbo-protocol-v1"
NATIVE_PIN = "2db09fba22a0572a70639162a808906409f612a8"
ARMS = ("vanilla", "guard", "no_unkeyed_repeat", "obligation_shield")
FAMILIES = ("qwen", "llama", "granite")
FAULTS = (
    "timeout_pre", "timeout_post", "timeout_late", "timeout_late_tail",
    "http500_pre", "http500_post", "http503_transient", "outage", "rate_limit",
    "schema_drift", "partial_timeout", "duplicate_delivery",
)
META_KEYS = {"template", "index", "family", "domains", "horizon", "focals"}
FOCAL_KEYS = {"label", "tool", "domain", "batch", "verification", "idempotency",
              "reversible", "supports_schema_drift"}
DEFAULT_LIMITS = {"max_requests": 16, "max_output_tokens": 512,
    "request_timeout_s": 1200, "episode_timeout_s": 7200,
    "work": {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_binding(path):
    path = Path(path)
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return {"sha256": value.hexdigest(), "bytes": path.stat().st_size}


def _binding(value, label):
    require(type(value) is dict and set(value) == {"sha256", "bytes"},
            label + " must bind exact bytes and SHA-256")
    sha = value["sha256"]
    require(isinstance(sha, str) and len(sha) == 64
            and all(c in "0123456789abcdef" for c in sha), label + " has an invalid SHA-256")
    require(type(value["bytes"]) is int and value["bytes"] > 0, label + " has invalid bytes")


def validate_exposure(exposure, templates):
    """Caller supplies the complete historical metadata ledger, not only 0/1.

    The ledger records all known prior task construction/development/collection
    indices, even failed or unstarted scheduled indices. Completeness is an
    explicit caller attestation; this function cannot infer undocumented access.
    """
    require(type(exposure) is dict and set(exposure) == {
        "complete_known_exposure_attested", "sources", "by_template"}, "Invalid exposure ledger")
    require(exposure["complete_known_exposure_attested"] is True,
            "A complete known-exposure attestation is required")
    require(type(exposure["sources"]) is dict and bool(exposure["sources"]),
            "Exposure records need source bindings")
    for name, binding in exposure["sources"].items():
        require(isinstance(name, str) and bool(name), "Invalid exposure source name")
        _binding(binding, "Exposure source " + name)
    require(type(exposure["by_template"]) is dict
            and set(exposure["by_template"]) == set(templates), "Exposure template inventory differs")
    for name, indices in exposure["by_template"].items():
        require(type(indices) is list and len(indices) == len(set(indices))
                and all(type(i) is int and i >= 0 for i in indices),
                "Exposure indices must be unique nonnegative integers: " + name)
        require({0, 1}.issubset(indices), "Exclude initial development indices 0 and 1: " + name)


def candidate_indices(templates, exposure, *, instances_per_template=4,
                      selection_seed="conseqax-expanded-limbo-2026-10-25-v1"):
    """Deterministically choose fresh parameter indices, never using outcomes."""
    require(type(templates) in (list, tuple) and len(templates) == len(set(templates))
            and all(isinstance(t, str) and t for t in templates), "Invalid template names")
    require(len(templates) == 12, "This design covers all twelve native templates")
    require(type(instances_per_template) is int and instances_per_template > 0,
            "Positive instances-per-template required")
    require(isinstance(selection_seed, str) and bool(selection_seed), "Explicit selection seed required")
    validate_exposure(exposure, templates)
    result = {}
    for template in sorted(templates):
        excluded = set(exposure["by_template"][template])
        chosen, attempt = [], 0
        while len(chosen) < instances_per_template:
            index = 10_000_000 + int(digest([selection_seed, template, attempt])[:12], 16) % 2_000_000_000
            attempt += 1
            if index not in excluded and index not in chosen:
                chosen.append(index)
        result[template] = chosen
    return result


def extract_metadata(native_root, index_plan):
    """Trusted native construction; no instruction, target, setup or match escapes.

    The caller must separately verify the pinned source inventory before use.
    This is not an OS sandbox or a claim that the template itself is unseen.
    """
    sys.path.insert(0, str(Path(native_root).resolve()))
    from limbo.tasks import TEMPLATES, make_task
    from limbo.services import build_tools
    require(set(index_plan) == set(TEMPLATES), "Native template inventory differs")
    tools, rows = build_tools("native"), []
    for template in sorted(index_plan):
        for index in index_plan[template]:
            task = make_task(template, index)
            focals = []
            for focal in task.focals:
                tool = tools[focal.tool]
                focals.append({"label": focal.label, "tool": focal.tool, "domain": tool.domain,
                    "batch": bool(focal.batch), "verification": focal.verification,
                    "idempotency": focal.idempotency, "reversible": bool(focal.reversible),
                    "supports_schema_drift": tool.contract.drift is not None})
            rows.append({"template": template, "index": index, "family": task.family,
                "domains": sorted(task.domains), "horizon": task.horizon, "focals": focals})
    return rows


def validate_metadata(metadata, index_plan):
    require(type(metadata) is list and bool(metadata), "Metadata cannot be empty")
    expected = {(t, i) for t, indices in index_plan.items() for i in indices}
    actual = []
    for row in metadata:
        require(type(row) is dict and set(row) == META_KEYS, "Unexpected or privileged task metadata field")
        require(isinstance(row["template"], str) and type(row["index"]) is int,
                "Invalid base-instance identity")
        actual.append((row["template"], row["index"]))
        require(isinstance(row["family"], str) and bool(row["family"]), "Missing task family")
        require(type(row["domains"]) is list and bool(row["domains"])
                and all(isinstance(d, str) and d for d in row["domains"])
                and len(row["domains"]) == len(set(row["domains"])), "Invalid domains")
        require(row["horizon"] in {"short", "long"}, "Invalid task horizon")
        require(type(row["focals"]) is list and bool(row["focals"]), "Missing focal affordances")
        labels = []
        for focal in row["focals"]:
            require(type(focal) is dict and set(focal) == FOCAL_KEYS,
                    "Unexpected or privileged focal metadata field")
            require(all(isinstance(focal[k], str) and focal[k]
                        for k in ("label", "tool", "domain", "verification", "idempotency")),
                    "Invalid focal affordance")
            require(focal["domain"] in row["domains"], "Focal domain is outside task domains")
            require(all(type(focal[k]) is bool for k in ("batch", "reversible", "supports_schema_drift")),
                    "Focal boolean affordance is not boolean")
            labels.append(focal["label"])
        require(len(labels) == len(set(labels)), "Duplicate focal label")
    require(len(actual) == len(set(actual)) and set(actual) == expected,
            "Metadata differs from the fresh index plan")


def compatible(mode, focal):
    require(mode in FAULTS, "Unsupported fault mode")
    return ((mode != "partial_timeout" or focal["batch"])
            and (mode != "schema_drift" or focal["supports_schema_drift"]))


def make_worlds(metadata, *, selection_seed, faults=FAULTS):
    """One clean and two distinct assigned faults per fresh base instance.

    Reserve coverage of every supported declared fault before greedily balancing
    mode/domain/focal counts. Selection uses affordances and fixed hashes only.
    All focal options remain public; no outcome/target value is an input.
    """
    require(type(faults) in (list, tuple) and bool(faults)
            and len(faults) == len(set(faults)) and set(faults).issubset(FAULTS),
            "Fault inventory must be unique supported modes")
    require(len(faults) >= 2, "Two distinct assigned faults require at least two modes")
    bases = sorted(metadata, key=lambda row: digest([selection_seed, row["template"], row["index"]]))
    candidates = {}
    for rank, row in enumerate(bases):
        candidates[rank] = [{"template": row["template"], "index": row["index"],
            "family": row["family"], "horizon": row["horizon"], "focal": focal["label"],
            "domain": focal["domain"], "mode": mode,
            "affordances": {k: focal[k] for k in FOCAL_KEYS - {"label", "tool", "domain"}}}
            for focal in row["focals"] for mode in faults if compatible(mode, focal)]
    eligibility = {mode: [r for r, rows in candidates.items() if any(c["mode"] == mode for c in rows)]
                   for mode in faults}
    require(all(eligibility.values()), "A declared fault has no compatible base instance")
    reserved = {rank: [] for rank in candidates}
    for mode in sorted(faults, key=lambda m: (len(eligibility[m]), digest([selection_seed, m]))):
        options = [r for r in eligibility[mode] if len(reserved[r]) < 2]
        require(bool(options), "Cannot reserve all fault modes in two slots per base")
        rank = min(options, key=lambda r: (len(reserved[r]), digest([selection_seed, mode, r])))
        reserved[rank].append(mode)
    counts, domains, focals, worlds = Counter(), Counter(), Counter(), []
    for rank, row in enumerate(bases):
        selected = []
        for required_mode in [*reserved[rank], *([None] * (2 - len(reserved[rank])))]:
            options = [c for c in candidates[rank]
                       if c["mode"] not in {x["mode"] for x in selected}
                       and (required_mode is None or c["mode"] == required_mode)]
            require(bool(options), "Base instance lacks two compatible distinct faults")
            chosen = min(options, key=lambda c: (counts[c["mode"]], domains[c["domain"]],
                focals[(c["template"], c["focal"])], digest([selection_seed, c])))
            selected.append(chosen)
            counts[chosen["mode"]] += 1
            domains[chosen["domain"]] += 1
            focals[(chosen["template"], chosen["focal"])] += 1
        for world in [{**selected[0], "mode": "none"}, *selected]:
            worlds.append({"world_rank": len(worlds), "base_rank": rank, "metadata": world})
    require(set(counts) == set(faults), "Declared fault coverage was lost")
    return worlds


def validate_models(models):
    require(type(models) is list and len(models) == 3, "Exactly three frozen model candidates required")
    require({m.get("family") for m in models} == set(FAMILIES),
            "Required model families are Qwen, Llama and Granite")
    require(len({m.get("id") for m in models}) == 3, "Model IDs must be unique")
    keys = {"id", "family", "checkpoint", "quantization", "weights", "tokenizer",
            "chat_template", "license", "context_tokens", "transport_preflight"}
    for model in models:
        require(type(model) is dict and set(model) == keys, "Model binding inventory differs")
        require(all(isinstance(model[k], str) and model[k]
                    for k in ("id", "family", "checkpoint", "quantization")), "Missing model identity")
        require(type(model["context_tokens"]) is int and model["context_tokens"] >= 8192,
                "Model needs a validated context of at least 8192 tokens")
        for key in ("weights", "tokenizer", "chat_template", "license", "transport_preflight"):
            _binding(model[key], model["id"] + " " + key)
    require(len({m["context_tokens"] for m in models}) == 1,
            "All model candidates require the same prospectively fixed context budget")


def make_schedule(worlds, models, *, generation_seeds, temperature,
                  worlds_per_block=12, max_tool_calls=16):
    validate_models(models)
    require(type(generation_seeds) in (list, tuple) and len(generation_seeds) >= 2
            and len(generation_seeds) == len(set(generation_seeds))
            and all(type(seed) is int and 0 <= seed <= 2_147_483_647 for seed in generation_seeds),
            "At least two unique explicit generation seeds required")
    require(type(temperature) in (int, float) and math.isfinite(temperature)
            and 0 <= temperature <= 2, "Invalid fixed generation temperature")
    require(type(worlds_per_block) is int and worlds_per_block > 0, "Positive block width required")
    require(type(max_tool_calls) is int and max_tool_calls > 0, "Positive tool budget required")
    require(bool(worlds) and [w["world_rank"] for w in worlds] == list(range(len(worlds))),
            "World ranks must be complete and contiguous")
    schedule, blocks = [], []
    for replicate, seed in enumerate(generation_seeds):
        for first in range(0, len(worlds), worlds_per_block):
            block_worlds = worlds[first:first + worlds_per_block]
            rotation = (first // worlds_per_block + replicate) % len(models)
            ordered_models = models[rotation:] + models[:rotation]
            for model in ordered_models:
                model_rank = models.index(model)
                block_id = f"block-{len(blocks):04d}"
                first_slot = len(schedule)
                for world in block_worlds:
                    rank, metadata = world["world_rank"], world["metadata"]
                    arm_rotation = (rank + model_rank + replicate) % len(ARMS)
                    for arm in ARMS[arm_rotation:] + ARMS[:arm_rotation]:
                        spec = {key: metadata[key] for key in ("template", "index", "focal", "mode")}
                        spec.update(model=model["id"], policy=arm, human_available=False,
                            contract="native", max_tool_calls=max_tool_calls,
                            experiment="conseqax-expanded-limbo-v1", paraphrase=0,
                            replicate=replicate, doc_variant="neutral", harness="minimal",
                            instruction_variant="default", reasoning_effort=None)
                        schedule.append({"slot": len(schedule), "block_id": block_id,
                            "world_rank": rank, "base_rank": world["base_rank"], "arm": arm,
                            "model_id": model["id"], "model_family": model["family"],
                            "generation_seed": seed, "temperature": temperature,
                            "metadata": metadata, "spec": spec})
                blocks.append({"block_id": block_id, "model_id": model["id"],
                    "replicate": replicate, "generation_seed": seed,
                    "first_slot": first_slot, "slot_count": len(schedule) - first_slot,
                    "world_ranks": [w["world_rank"] for w in block_worlds]})
    return {"schedule": schedule, "blocks": blocks}


def build_protocol(metadata, models, exposure, *, selection_seed,
                   instances_per_template=4, generation_seeds=(1701, 2718), temperature=0.2,
                   worlds_per_block=12, max_tool_calls=16, source_files, native_files,
                   wheel_binding, faults=FAULTS, limits=None, readiness_binding=None):
    """Return an unfrozen proposed protocol. Publication/freeze is a separate step.

    Every preflight must be genuinely completed and its supplied bytes reviewed
    before the caller publishes this object as a measured protocol. No boolean
    supplied here is a substitute for independent execution readiness checks.
    """
    templates = sorted(exposure["by_template"])
    indices = candidate_indices(templates, exposure, instances_per_template=instances_per_template,
                                selection_seed=selection_seed)
    validate_metadata(metadata, indices)
    for name, inventory in (("research source", source_files), ("native source", native_files)):
        require(type(inventory) is dict and bool(inventory), "Missing " + name + " inventory")
        for path, binding in inventory.items():
            require(isinstance(path, str) and path and not Path(path).is_absolute()
                    and ".." not in Path(path).parts, "Unsafe source inventory path")
            _binding(binding, name + " " + path)
    _binding(wheel_binding, "Scientific wheel")
    if readiness_binding is not None:
        _binding(readiness_binding, "Readiness receipt")
    limits = json.loads(canonical(DEFAULT_LIMITS if limits is None else limits))
    require(type(limits) is dict and set(limits) == set(DEFAULT_LIMITS), "Limit inventory differs")
    require(all(type(limits[k]) is int and limits[k] > 0
                for k in ("max_requests", "max_output_tokens")), "Positive model limits required")
    require(limits["max_output_tokens"] <= 512, "Transport supports at most 512 output tokens")
    require(all(type(limits[k]) in (int, float) and math.isfinite(limits[k]) and limits[k] > 0
                for k in ("request_timeout_s", "episode_timeout_s"))
            and limits["episode_timeout_s"] > limits["request_timeout_s"], "Invalid deadlines")
    require(type(limits["work"]) is dict and set(limits["work"]) == set(DEFAULT_LIMITS["work"])
            and all(type(v) is int and v > 0 for v in limits["work"].values()), "Invalid work limits")
    worlds = make_worlds(metadata, selection_seed=selection_seed, faults=faults)
    schedule = make_schedule(worlds, models, generation_seeds=generation_seeds,
        temperature=temperature, worlds_per_block=worlds_per_block, max_tool_calls=max_tool_calls)
    return {"schema": SCHEMA, "native_pin": NATIVE_PIN, "selection_seed": selection_seed,
        "instances_per_template": instances_per_template, "index_plan": indices,
        "exposure": exposure, "metadata": metadata, "models": models, "arms": list(ARMS),
        "faults": list(faults), "worlds": worlds, **schedule,
        "generation_seeds": list(generation_seeds), "temperature": temperature,
        "worlds_per_block": worlds_per_block, "max_tool_calls": max_tool_calls,
        "sources": source_files, "native_sources": native_files, "wheel": wheel_binding,
        "limits": limits,
        "readiness": readiness_binding,
        "counts": {"base_instances": len(metadata), "templates": len(templates),
            "assigned_worlds": len(worlds), "models": len(models),
            "generation_replicates": len(generation_seeds), "arms": len(ARMS),
            "planned_slots": len(schedule["schedule"]), "blocks": len(schedule["blocks"])},
        "claims": {"human_available": False, "paid_inference": False,
            "model_requests_serial": True, "outcome_based_selection": False,
            "new_parameter_instances_not_unseen_templates": True,
            "stochastic_generation_intended": temperature > 0,
            "seed_support_and_variation_require_measured_validation": True,
            "all_planned_dispositions_retained": True, "replace_started_slots": False,
            "resume_started_slots": False, "native_world_seed_includes_mode_and_focal": True,
            "blocks_are_execution_partitions_not_outcome_gates": True,
            "task_population_inference": False, "native_EOS_is_universal_exactly_once": False},
        "analysis": {"unit": "Matched assigned world within model and generation replicate; cluster by base instance",
            "primary_comparisons": [["obligation_shield", "guard"],
                                    ["obligation_shield", "no_unkeyed_repeat"]],
            "primary_endpoints": ["native_TS", "native_EOS"],
            "secondary": ["audited_grade_availability", "normal_execution_return", "dup_executed",
                "dup_live", "collateral", "extraneous_writes", "false_completion_claim",
                "receipt_claim_soundness", "definite_claim_coverage", "model_dispatches",
                "execute_attempts", "public_verify_attempts", "explicit_waits", "tokens_known_unknown"],
            "report": "Exact finite paired discordance and numerator/denominator differences per model/seed; no pooled independent-task p-values",
            "missing": "Unavailable native grades stay unknown; never replace or impute semantic failures; retain all-planned success yield and conditional available-grade endpoints separately",
            "strata": ["model", "generation_seed", "template", "family", "focal_domain",
                       "assigned_fault", "verification", "idempotency", "horizon"]}}


def verify_protocol_structure(protocol):
    """Independently reconstruct the proposal and reject changed schedules/claims."""
    require(type(protocol) is dict and protocol.get("schema") == SCHEMA, "Unsupported expanded protocol")
    expected = build_protocol(protocol["metadata"], protocol["models"], protocol["exposure"],
        selection_seed=protocol["selection_seed"], instances_per_template=protocol["instances_per_template"],
        generation_seeds=protocol["generation_seeds"], temperature=protocol["temperature"],
        worlds_per_block=protocol["worlds_per_block"], max_tool_calls=protocol["max_tool_calls"],
        source_files=protocol["sources"], native_files=protocol["native_sources"],
        wheel_binding=protocol["wheel"], faults=protocol["faults"], limits=protocol["limits"],
        readiness_binding=protocol["readiness"])
    require(canonical(expected) == canonical(protocol), "Expanded protocol differs from deterministic reconstruction")
    return protocol
