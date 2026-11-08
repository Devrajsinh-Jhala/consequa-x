"""Read-only qualification audit of saved Kaggle outputs; zero model execution.

The uploaded archive is data. Nothing is extracted, imported or executed from it.
Hashes validate retained byte consistency, not independent hardware authenticity.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.kaggle_limbo.audit import (  # noqa: E402
    validate_condition, verify_gpu_load_proof, verify_gpu_residency,
)

MAX_BYTES = 256 * 1024**2
MAX_ENTRIES = 20_000
TERMINALS = {"completed", "native_error_return", "failed", "interrupted", "refused"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode() + b"\n"


def json_data(data, label):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + label)
            result[key] = value
        return result

    try:
        return json.loads(data, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON: " + label) from exc


def safe_name(name):
    require(type(name) is str and name and "\\" not in name and ":" not in name
            and not any(ord(c) < 32 for c in name), "Unsafe archive path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and path.as_posix() == name
            and all(part not in {".", "..", ""} for part in path.parts), "Unsafe archive path")
    return name


def zip_files(data, label):
    require(len(data) <= MAX_BYTES, "Compressed archive exceeds audit limit: " + label)
    result, folded = {}, set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        require(len(entries) <= MAX_ENTRIES
                and sum(x.file_size for x in entries) <= MAX_BYTES, "Archive exceeds audit limits: " + label)
        for entry in entries:
            require(entry.orig_filename == entry.filename, "Normalized/ambiguous archive member")
            name = safe_name(entry.filename.rstrip("/") if entry.is_dir() else entry.filename)
            require(not entry.is_dir() or entry.filename == name + "/", "Noncanonical archive directory")
            require(name.casefold() not in folded, "Duplicate/case-colliding archive member")
            folded.add(name.casefold())
            mode = entry.external_attr >> 16
            require(not entry.flag_bits & 1 and not stat.S_ISLNK(mode)
                    and (not stat.S_IFMT(mode) or stat.S_ISREG(mode) or stat.S_ISDIR(mode)),
                    "Linked, encrypted or special archive member")
            if not entry.is_dir():
                result[name] = archive.read(entry)
    return result


def check_binding(data, expected, label):
    require(type(expected) is dict and set(expected) == {"sha256", "bytes"}
            and type(expected["bytes"]) is int and expected["bytes"] >= 0
            and type(expected["sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]) is not None,
            "Invalid byte binding: " + label)
    require(digest(data) == expected, "Byte binding differs: " + label)


def checkpoint_state(files, identity):
    schedule = json_data(files["schedule.json"], "schedule")
    require(type(schedule) is list and len(schedule) == identity["planned_slots"]
            and [s.get("slot") for s in schedule] == list(range(len(schedule))), "Schedule identities differ")
    check_binding(files["schedule.json"], identity["schedule"], "schedule")
    names = sorted(n for n in files if n.startswith("events/") and n.endswith(".json"))
    previous, reservations, terminals = None, {}, {}
    for sequence, name in enumerate(names):
        require(name == f"events/{sequence:06d}.json", "Reordered/missing checkpoint event")
        event = json_data(files[name], name)
        content = {key: value for key, value in event.items() if key != "content_sha256"}
        require(event.get("content_sha256") == digest(canonical(content))["sha256"], "Event content checksum differs")
        require(event.get("sequence") == sequence and event.get("previous_sha256") == previous
                and event.get("identity") == digest(files["identity.json"]), "Checkpoint event ancestry differs")
        kind, slot = event.get("kind"), event.get("slot")
        if kind in {"reserve", "terminal"}:
            require(type(slot) is int and 0 <= slot < len(schedule)
                    and event.get("slot_sha256") == digest(canonical(schedule[slot]))["sha256"], "Event slot differs")
        if kind == "reserve":
            require(slot not in reservations, "Repeated checkpoint reservation")
            reservations[slot] = digest(files[name])["sha256"]
        elif kind == "terminal":
            require(slot in reservations and slot not in terminals
                    and event.get("reservation_sha256") == reservations[slot]
                    and event.get("status") in TERMINALS, "Terminal reservation/status differs")
            prefix = f"slots/slot-{slot:05d}/episode/"
            retained = {key: digest(value) for key, value in files.items() if key.startswith(prefix)}
            require(retained == event.get("episode_files"), "Sealed episode inventory differs")
            terminals[slot] = event["status"]
        else:
            require(kind == "session", "Unknown checkpoint event kind")
        previous = digest(files[name])["sha256"]
    return {"planned": len(schedule), "started": len(reservations), "terminal": len(terminals),
            "pending": sorted(set(reservations) - set(terminals)), "unstarted": len(schedule) - len(reservations),
            "statuses": {status: sum(value == status for value in terminals.values()) for status in sorted(TERMINALS)},
            "last_event_sha256": previous}


def parse_response(response):
    """Compare native chat parsing semantics using data only, without importing it."""
    choices = response.get("choices")
    require(type(choices) is list and bool(choices), "Response has no choices")
    text, calls, finish = [], [], None
    for choice in choices:
        message = choice.get("message") or {}
        if message.get("content"):
            require(type(message["content"]) is str, "Non-text response content")
            text.append(message["content"])
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            calls.append({"id": call.get("id") or f"call_{len(calls)}", "name": function.get("name", ""),
                          "arguments": function.get("arguments") or "{}"})
        finish = choice.get("finish_reason") or finish
    return "\n".join(text), calls, finish


def model_row(files, prefix, condition):
    def read(relative):
        return json_data(files[prefix + relative], relative)

    parsed, response, request = read("parsed-turn.json"), read("client/0001-response.bin"), read("client/0001-request.bin")
    text, calls, finish = parse_response(response)
    require((parsed.get("text"), parsed.get("tool_calls"), parsed.get("finish_reason")) == (text, calls, finish),
            "Saved raw API response and parsed turn disagree")
    metadata, context = read("client/0001-response-meta.json"), read("client/0001-context.json")
    require(metadata.get("status") == 200
            and metadata.get("body_sha256") == digest(files[prefix + "client/0001-response.bin"])["sha256"],
            "Response metadata differs")
    cfg, lease = read("client/kaggle-gpu-config.json"), read("lease/runtime-binding.json")
    require(cfg.get("condition") == condition and cfg.get("runtime") == lease
            and request.get("model") == response.get("model") == lease.get("model"), "Model/runtime condition differs")
    load = read("lease/gpu-load-proof.json")
    require(cfg.get("gpu_load_proof") == load and cfg.get("cpu_fallback_allowed") is False, "GPU config/load proof differs")
    verify_gpu_load_proof(load, lease)
    verify_gpu_residency(context, lease)
    require(context.get("passed") is True and context.get("request") == request, "Context proof/request differs")
    request_hash = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False, ensure_ascii=False).encode()).hexdigest()
    require(context.get("request_sha256") == request_hash, "Context request hash differs")
    prompt, gate, tokens = context.get("provider_rendered_prompt"), context.get("context"), context.get("runtime_tokenizer", {}).get("tokens")
    require(type(prompt) is str and type(gate) is dict and type(tokens) is list
            and gate.get("rendered_prompt_sha256") == digest(prompt.encode())["sha256"]
            and gate.get("prompt_tokens") == len(tokens)
            and gate.get("required_tokens") == len(tokens) + request["max_tokens"] + gate["reserve_tokens"]
            and gate.get("fits") is True and gate["required_tokens"] <= gate["context_tokens"], "Context accounting differs")
    expected_call = False
    if len(calls) == 1 and calls[0]["name"] == "lookup_echo":
        try:
            expected_call = json_data(calls[0]["arguments"], "tool arguments") == {"name": "test-item"}
        except (ValueError, TypeError):
            pass
    pass_name = prefix + "preflight.json"
    if pass_name in files:
        receipt = read("preflight.json")
        require(receipt.get("passed") is True and expected_call
                and receipt.get("model_id") == lease["model"] and receipt.get("condition") == condition,
                "Preflight pass receipt contradicts saved response")
    terminal = read("client/0001-terminal.json")
    require(terminal.get("dispatches") == 1 and terminal.get("returned") is True, "Generation terminal differs")
    return {"session_path": prefix.rstrip("/"), "family": PurePosixPath(prefix).name,
        "model_id": lease["model"], "http_status": metadata["status"],
        "exact_required_tool_call": expected_call, "pass_receipt_present": pass_name in files,
        "raw_api_content_empty": text == "", "raw_api_content_characters": len(text),
        "raw_api_tool_calls": len(calls), "parsed_tool_calls": len(parsed["tool_calls"]),
        "finish_reason": finish, "reported_output_tokens": response.get("usage", {}).get("completion_tokens"),
        "context_fits": gate["fits"], "prompt_tokens": gate["prompt_tokens"],
        "required_context_tokens": gate["required_tokens"], "context_tokens": gate["context_tokens"],
        "offloaded_layers": load["offloaded_layers"], "total_layers": load["total_layers"],
        "response_binding": digest(files[prefix + "client/0001-response.bin"]),
        "failure_class": None if expected_call else ("empty_api_response_without_tool_call" if not calls and not text
            else "required_tool_call_not_returned")}


def audit_archive(archive_path):
    path = Path(archive_path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES, "Expected bounded regular results ZIP")
    data = path.read_bytes()
    outer = zip_files(data, "results")
    receipt = json_data(outer["checkpoint-export.json"], "checkpoint export")
    check_binding(outer["checkpoint.zip"], receipt["archive"], "nested checkpoint ZIP")
    nested = zip_files(outer["checkpoint.zip"], "checkpoint")
    manifest = json_data(nested["checkpoint.json"], "checkpoint manifest")
    inventory = manifest.get("files")
    require(type(inventory) is dict and set(nested) == set(inventory) | {"checkpoint.json"}, "Checkpoint inventory differs")
    raw = {name.removeprefix("conseqax-benchmark/"): value for name, value in outer.items()
           if name.startswith("conseqax-benchmark/") and name != "conseqax-benchmark/.writer.lock"}
    require(set(raw) == set(inventory), "Raw output and exported checkpoint inventories differ")
    for name, expected in inventory.items():
        safe_name(name)
        check_binding(nested[name], expected, name)
        require(raw[name] == nested[name], "Raw output differs from exported checkpoint: " + name)
    identity = json_data(raw["identity.json"], "identity")
    require(identity.get("schema") == "conseqax-kaggle-checkpoint-v1", "Unexpected checkpoint schema")
    condition = identity["lineage"]["condition"]
    validate_condition(condition)
    state = checkpoint_state(raw, identity)
    require(state == receipt.get("state"), "Exported checkpoint state differs from retained event history")
    progress = json_data(outer["progress.json"], "progress")
    require(progress.get("state") == state, "Progress state differs from checkpoint history")
    prefixes = sorted(name.removesuffix("parsed-turn.json") for name in raw
                      if name.startswith("sessions/") and name.endswith("/parsed-turn.json"))
    require(bool(prefixes), "No retained qualification turns")
    rows = [model_row(raw, prefix, condition) for prefix in prefixes]
    return {"schema": "conseqax-kaggle-qualification-audit-v1", "archive": digest(data),
        "byte_consistency_passed": True, "checkpoint_files_verified": len(inventory),
        "raw_output_matches_exported_snapshot": True, "event_chain_and_schedule_verified": True,
        "condition": condition, "study_source_commit": identity["lineage"]["source_commit"],
        "checkpoint_state": state, "models": rows,
        "all_retained_qualification_turns_passed": all(row["exact_required_tool_call"] for row in rows),
        "scope": {"archive_code_executed": False, "fresh_inference_calls": 0,
            "independent_hardware_authentication": False, "native_episode_audit_performed": False,
            "underlying_generated_text_before_provider_parser_available": False,
            "raw_API_empty_does_not_establish_the_model_generated_no_tokens": True,
            "scientific_task_outcomes_claimed": False}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit_archive(args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"report": str(args.output), "models_checked": len(report["models"]),
        "qualification_passed": report["all_retained_qualification_turns_passed"],
        "measured_slots_started": report["checkpoint_state"]["started"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
