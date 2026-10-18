"""Frozen, resumable factual-trace research study; never touches live payments.

This is research tooling, not a package API. Freeze once, inspect protocol.json,
then run. A started slot is never regenerated, including after interruption.
Only declared validation cases are admitted; the original held-out reserve is
refused. No model weights are downloaded.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from http.client import HTTPException
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request

import consequa_x
from consequa_x.adapters.ollama import (
    MAX_RESPONSE_BYTES, OllamaPolicy, PROMPT_PROFILES,
    _normalized_model, _reject_remote_routing,
)
from consequa_x.benchmark.policy_runner import MAX_TRIAL_SEED, run_policy_scenario
from consequa_x.benchmark.study import study_plan_from_json, template_wording_sha256
from consequa_x.models import to_dict
from consequa_x.policies import PolicyError, strict_json_loads


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "consequa-matched-local-study-v1"
PROTOCOL_DOCUMENT = ROOT / "paper/protocol-matched-local-2026-10-18.md"
RESEARCH_TESTS = (
    ROOT / "tests/test_matched_local_study.py",
    ROOT / "tests/test_matched_baseline_audit.py",
)


class InfrastructurePolicyError(PolicyError):
    """A provider/identity/budget failure that must stop this invocation."""


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def digest(data):
    return sha256(data).hexdigest()


def read_json(path):
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, value):
    """Exclusive creation plus fsync: artifacts cannot silently replace history."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def write_bytes_new(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def code_hashes():
    package = Path(consequa_x.__file__).resolve().parent
    paths = [Path(__file__), ROOT / "scripts/analyze_matched_local_study.py"]
    hashes = {f"research/{path.name}": digest(path.read_bytes()) for path in paths}
    hashes.update({f"tests/{path.name}": digest(path.read_bytes()) for path in RESEARCH_TESTS})
    hashes.update({
        f"runtime/{path.relative_to(package).as_posix()}": digest(path.read_bytes())
        for path in sorted(package.rglob("*"))
        if path.is_file() and (path.suffix in {".py", ".json"} or path.name == "py.typed")
    })
    return hashes


def make_schedule(cases, models, profiles, samples, seed, order_seed):
    """Randomized repetition blocks; paired worlds across model/profile cells.

    Models are grouped inside a repetition to limit CPU-only weight swapping.
    Model, profile and case order are all frozen before generation.
    """
    if type(samples) is not int or samples < 1:
        raise ValueError("samples must be positive")
    if type(seed) is not int or seed < 0 or seed + len(cases) * samples - 1 > MAX_TRIAL_SEED:
        raise ValueError("world/model phase seed reservation is outside the supported range")
    if len(set(models)) != len(models) or not models:
        raise ValueError("models must be nonempty and unique")
    if set(profiles) != set(PROMPT_PROFILES) or len(profiles) != len(PROMPT_PROFILES):
        raise ValueError("use exactly both existing prompt profiles")
    rng = random.Random(order_seed)
    schedule = []
    for repetition in range(samples):
        model_order = list(models)
        rng.shuffle(model_order)
        for model in model_order:
            profile_order, case_order = list(profiles), list(enumerate(cases))
            rng.shuffle(profile_order)
            rng.shuffle(case_order)
            for profile in profile_order:
                for case_index, case in case_order:
                    trial = seed + case_index * samples + repetition
                    schedule.append({
                        "slot": len(schedule), "slot_id": f"episode_{len(schedule):05d}",
                        "model": model, "prompt_version": profile, "case_id": case.case_id,
                        "repetition": repetition, "world_seed": trial, "trial_seed": trial,
                        "reserved_phase_seeds": list(range(trial * 6, trial * 6 + 6)),
                        "template_id": case.template.template_id,
                        "family_id": case.template.family_id,
                        "wording_sha256": template_wording_sha256(case.template),
                    })
    return schedule


def inspect_models(models, settings, policy_factory=OllamaPolicy):
    result = {"inspected_utc": now(), "models": {}}
    policy = policy_factory(models[0], **settings)
    result["server_version"] = policy._request("/api/version")
    tags = policy._request("/api/tags")
    for model in models:
        matches = [item for item in tags.get("models", []) if item.get("name") == model]
        if len(matches) != 1 or not isinstance(matches[0].get("digest"), str):
            raise PolicyError(f"Exact installed model/digest missing: {model}")
        instance = policy_factory(model, **settings)
        inspection = instance.validate_local_model(force=True)
        result["models"][model] = {"tag": matches[0], "inspection": inspection}
    return result


def freeze(args):
    out = Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("freeze requires a new empty output directory")
    if not math.isfinite(args.max_wall_seconds) or args.max_wall_seconds <= 0:
        raise ValueError("max_wall_seconds must be finite and positive")
    manifest_bytes = Path(args.study).read_bytes()
    protocol_document = Path(getattr(args, "protocol", PROTOCOL_DOCUMENT)).resolve()
    snapshots = {
        "written-protocol.source.md": protocol_document,
        "study-plan.source.json": Path(args.study).resolve(),
        **{f"research-tests/{path.name}": path for path in RESEARCH_TESTS},
    }
    # Read every declared source before any output or generation is possible.
    snapshot_bytes = {name: path.read_bytes() for name, path in snapshots.items()}
    plan = study_plan_from_json(manifest_bytes.decode("utf-8"))
    cases = plan.select("validation")
    if any(case.template.family_id == "refund-operations-ticket" for case in cases):
        raise ValueError("The original held-out family reserve must remain unused")
    models = tuple(args.models)
    schedule = make_schedule(cases, models, tuple(PROMPT_PROFILES), args.samples,
                             args.seed, args.order_seed)
    settings = {"base_url": args.base_url, "temperature": args.temperature,
                "timeout": args.timeout, "num_predict": args.num_predict}
    inspection = inspect_models(models, settings)
    source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    protocol = {
        "schema_version": SCHEMA, "frozen_utc": now(), "source_revision": source,
        "package_version": importlib.metadata.version("consequa-x"),
        "python": sys.version, "platform": platform.platform(),
        "manifest_sha256": digest(manifest_bytes), "code_sha256": code_hashes(),
        "source_inventory": {name: {"source_path": (
                                        snapshots[name].relative_to(ROOT).as_posix()
                                        if snapshots[name].is_relative_to(ROOT)
                                        else str(snapshots[name])),
                                    "sha256": digest(content)}
                             for name, content in snapshot_bytes.items()},
        "prompt_sha256": {key: digest(value.encode("utf-8"))
                          for key, value in PROMPT_PROFILES.items()},
        "settings": settings, "max_attempts": 2, "max_wall_seconds": args.max_wall_seconds,
        "models": inspection["models"], "server_version": inspection["server_version"],
        "samples_per_case_cell": args.samples, "seed": args.seed,
        "order_seed": args.order_seed, "schedule": schedule,
        "planned_episodes": len(schedule), "max_chat_calls": 3 * len(schedule),
        "selected_cases": [case.to_dict() for case in cases],
        "exposure": {"split": "validation",
                     "families": sorted({case.template.family_id for case in cases}),
                     "wording_exposure": "As declared by the research protocol; previously exposed "
                                         "refund-case-note family is identified explicitly if selected.",
                     "previously_exposed_family_selected": any(
                         case.template.family_id == "refund-case-note" for case in cases),
                     "held_out_generated": False, "mechanisms_previously_exposed": True,
                     "reserve_family": "refund-operations-ticket"},
        "failure_policy": "Never regenerate a started slot. Failures and interrupted partials "
                          "remain in the denominator. Resume only unstarted slots. No provider retries. "
                          "Stop this invocation after transport/HTTP/identity/pre-call failure, preserving "
                          "later slots as unstarted; malformed model decisions remain failed samples.",
        "sampling_unit": "Fixed declared simulator cases; repetitions are model/world seed controls, "
                         "not independent task families. Wording controls do not hold out fault "
                         "mechanisms. Model size/family are confounded.",
        "order": "Randomized repetition/model/profile/case blocks, frozen before generation; "
                 "same world and requested model phase seeds across all model/profile cells.",
        "baseline_scope": "Offline factual-trace audit ablations, not causal attribution or "
                          "faithful CAR/VerifiedToolCalls reproductions. No baseline generation calls.",
        "gold": "Evaluator-only direct simulator ledger predicate, independent of verification "
                "results; retained separately and never supplied to policies or auditors.",
        "analysis": {"primary": "Coverage, wrong claims / definite claims, and correct definite "
                      "claims / completed episodes, stratified by model/profile/case and target.",
                     "hypothesis_tests": False, "rationale_annotation": False,
                     "generalization_claim": False, "confidence_intervals": "None: no pooled "
                     "independent-task interval; retain per-repetition paired counts."},
        "methods": {
            "response_only": "Last public response: success=true, error=false, timeout/missing=unknown. "
                             "Same naive acknowledgment proxy for state and action-linked target.",
            "agent_self_report": "Final structured assessment: success=true, failure=false, "
                                 "partial/unknown=unknown; same reported effect proxy for both targets.",
            "readback_state_only": "Same captured independent readback and contract, provenance "
                                   "removed; state verifier only, action-linkage abstains.",
            "consequa_state_origin": "Same readback plus captured provenance; package state verifier "
                                     "and action_linked_consequence mapping. No evaluator truth.",
            "independent_public_reference": "Independent transparent contract+provenance join over "
                                            "the same public readback and action as Consequa-X; "
                                            "no package verifier/target helper or evaluator truth.",
        },
    }
    for name, content in snapshot_bytes.items():
        write_bytes_new(out / name, content)
    write_new(out / "preflight.json", inspection)
    write_new(out / "protocol.json", protocol)
    write_new(out / "protocol.sha256.json", {"sha256": digest((out / "protocol.json").read_bytes())})
    return {"output": str(out), "planned_episodes": len(schedule),
            "max_chat_calls": protocol["max_chat_calls"], "protocol_sha256":
            digest((out / "protocol.json").read_bytes())}


class Journal:
    """Append-only hash chain; a torn final line is a hard stop, never repaired."""

    def __init__(self, path):
        self.path = Path(path)
        self.records = []
        self.last = None
        if self.path.exists():
            for line in self.path.read_bytes().splitlines(keepends=True):
                if not line.endswith(b"\n"):
                    raise ValueError("Torn journal line: preserve evidence and stop")
                row = strict_json_loads(line.decode("utf-8"))
                claimed = row.pop("sha256")
                if row.get("previous_sha256") != self.last or digest(encoded(row)) != claimed:
                    raise ValueError("Journal chain changed")
                row["sha256"] = claimed
                self.records.append(row)
                self.last = claimed

    def append(self, event, **data):
        row = {"index": len(self.records), "utc": now(), "event": event,
               "previous_sha256": self.last, **data}
        row["sha256"] = digest(encoded(row))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.write(encoded(row))
            stream.flush()
            os.fsync(stream.fileno())
        self.records.append(row)
        self.last = row["sha256"]


class RecordingPolicy(OllamaPolicy):
    """Retain exact chat request/response bytes, including malformed responses."""

    def __init__(self, model, *, directory, slot, journal, max_calls, deadline_utc=None,
                 expected_digest=None, **kwargs):
        super().__init__(model, **kwargs)
        self.directory, self.slot, self.journal = Path(directory), slot, journal
        self.max_calls = max_calls
        self.deadline_utc = deadline_utc
        self.expected_digest = expected_digest
        self.calls = 0

    def _request(self, path, payload=None):
        if path != "/api/chat":
            return super()._request(path, payload)
        attempts = sum(row["event"] == "chat_started" for row in self.journal.records)
        if attempts >= self.max_calls:
            self.journal.append("call_budget_exhausted", slot_id=self.slot)
            raise InfrastructurePolicyError("Frozen study chat-call cap reached")
        if self.deadline_utc is not None and time.time() >= self.deadline_utc:
            self.journal.append("wall_time_exhausted", slot_id=self.slot)
            raise InfrastructurePolicyError("Frozen study wall-time budget exhausted; no generation call made")
        if self.expected_digest is not None:
            try:
                identities = [item for item in self.list_models() if item["name"] == self.model]
                if len(identities) != 1 or identities[0].get("digest") != self.expected_digest:
                    raise PolicyError("Model tag/digest changed before generation; no call made")
            except PolicyError as error:
                self.journal.append("model_identity_failed", slot_id=self.slot, model=self.model,
                                    error=str(error))
                raise InfrastructurePolicyError(str(error)) from None
        # The identity request may itself consume the remaining wall budget.
        # Recheck after all pre-call I/O, and bound the actual HTTP wait below.
        if self.deadline_utc is not None and time.time() >= self.deadline_utc:
            self.journal.append("wall_time_exhausted", slot_id=self.slot)
            raise InfrastructurePolicyError("Frozen study wall-time budget exhausted; no generation call made")
        call_id = f"{self.slot}-call-{self.calls:02d}"
        self.calls += 1
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
        request_path = self.directory / "calls" / f"{call_id}.request.json"
        write_bytes_new(request_path, body)
        self.journal.append("chat_started", slot_id=self.slot, call_id=call_id,
                            request_file=request_path.relative_to(self.directory).as_posix(),
                            request_sha256=digest(body))
        request = Request(self.base_url + path, data=body,
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
        timeout = self.timeout
        if self.deadline_utc is not None:
            remaining = self.deadline_utc - time.time()
            if remaining <= 0:
                # The attempted-call receipt remains visible even if durable
                # file/journal writes consumed the last remaining instant.
                self.journal.append("wall_time_exhausted", slot_id=self.slot, call_id=call_id,
                                    dispatched=False)
                raise InfrastructurePolicyError("Frozen study wall-time budget exhausted; no generation call made")
            timeout = min(timeout, remaining)
        start = time.monotonic()
        response_bytes = None
        try:
            with self._opener.open(request, timeout=timeout) as response:
                response_bytes = response.read(MAX_RESPONSE_BYTES + 1)
                status = response.status
        except HTTPError as error:
            response_bytes = error.read(MAX_RESPONSE_BYTES + 1)
            status = error.code
        except (URLError, TimeoutError, socket.timeout, OSError, HTTPException) as error:
            self.journal.append("chat_transport_failed", slot_id=self.slot, call_id=call_id,
                                error_type=type(error).__name__, elapsed_seconds=time.monotonic()-start)
            raise InfrastructurePolicyError("Could not reach local Ollama; no sample retry permitted") from None
        path = self.directory / "calls" / f"{call_id}.response.raw"
        write_bytes_new(path, response_bytes)
        self.journal.append("chat_received", slot_id=self.slot, call_id=call_id,
                            response_file=path.relative_to(self.directory).as_posix(),
                            response_sha256=digest(response_bytes), status=status,
                            elapsed_seconds=time.monotonic()-start,
                            truncated=len(response_bytes) > MAX_RESPONSE_BYTES)
        if status != 200:
            raise InfrastructurePolicyError(f"Local Ollama returned HTTP {status}")
        if len(response_bytes) > MAX_RESPONSE_BYTES:
            raise PolicyError("Local Ollama response exceeds the 1 MiB limit")
        try:
            value = strict_json_loads(response_bytes.decode("utf-8"))
        except UnicodeDecodeError:
            raise PolicyError("Local Ollama response is not UTF-8 JSON") from None
        if type(value) is not dict:
            raise PolicyError("Local Ollama response must be a JSON object")
        try:
            _reject_remote_routing(value)
            returned_model = value.get("model")
            if (type(returned_model) is not str or not returned_model.strip()
                    or returned_model.strip() != returned_model
                    or _normalized_model(returned_model) != _normalized_model(self.model)):
                raise PolicyError("Local Ollama response is missing or changed its model identity")
        except PolicyError as error:
            self.journal.append("chat_identity_failed", slot_id=self.slot, call_id=call_id,
                                model=self.model, error=str(error))
            raise InfrastructurePolicyError(str(error)) from None
        return value


def validate_freeze(out):
    protocol = read_json(out / "protocol.json")
    if protocol.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported frozen study schema")
    if digest((out / "protocol.json").read_bytes()) != read_json(out / "protocol.sha256.json")["sha256"]:
        raise ValueError("Frozen protocol changed")
    if digest((out / "study-plan.source.json").read_bytes()) != protocol["manifest_sha256"]:
        raise ValueError("Frozen manifest changed")
    for name, source in protocol["source_inventory"].items():
        if digest((out / name).read_bytes()) != source["sha256"]:
            raise ValueError(f"Frozen source snapshot changed: {name}")
        source_path = Path(source["source_path"])
        if not source_path.is_absolute():
            source_path = ROOT / source_path
        if digest(source_path.read_bytes()) != source["sha256"]:
            raise ValueError(f"Declared study source changed: {name}")
    if code_hashes() != protocol["code_sha256"]:
        raise ValueError("Frozen research/runtime source changed; do not resume under new code")
    if protocol["package_version"] != importlib.metadata.version("consequa-x") or protocol["python"] != sys.version:
        raise ValueError("Frozen Python/package version changed")
    return protocol


def run(out, *, limit=None, policy_factory=RecordingPolicy, inspector=inspect_models):
    """Run only never-started slots; limit is an interruption boundary, not redraw."""
    out = Path(out).resolve()
    protocol = validate_freeze(out)
    lock = out / "runner.lock"
    # A crashed process leaves its lock. Root must preserve/rename it after checking
    # that the recorded PID no longer exists; the runner never guesses or deletes it.
    write_new(lock, {"pid": os.getpid(), "started_utc": now()})
    try:
        journal = Journal(out / "request-journal.jsonl")
        try:
            current = inspector(tuple(protocol["models"]), protocol["settings"])
            for model, frozen in protocol["models"].items():
                if current["models"][model]["tag"]["digest"] != frozen["tag"]["digest"]:
                    raise PolicyError("Installed model digest changed since protocol freeze")
            if current["server_version"] != protocol["server_version"]:
                raise PolicyError("Local Ollama server version changed since protocol freeze")
        except (PolicyError, OSError, ValueError) as error:
            journal.append("run_preflight_failed", error_type=type(error).__name__, error=str(error))
            raise
        journal.append("run_preflight", models=current["models"],
                       server_version=current["server_version"])
        original_starts = [event for event in journal.records if event["event"] == "run_started"]
        start_stamp = original_starts[0]["utc"] if original_starts else now()
        deadline = datetime.fromisoformat(start_stamp).timestamp() + protocol["max_wall_seconds"]
        journal.append("run_started", frozen_deadline_utc=datetime.fromtimestamp(
            deadline, timezone.utc).isoformat())
        plan = study_plan_from_json((out / "study-plan.source.json").read_text(encoding="utf-8"))
        cases = {case.case_id: case for case in plan.select("validation")}
        started = 0
        for slot in protocol["schedule"]:
            folder = out / "episodes" / slot["slot_id"]
            if (folder / "started.json").exists():
                continue
            if time.time() >= deadline:
                journal.append("wall_time_exhausted", next_slot_id=slot["slot_id"])
                break
            if limit is not None and started >= limit:
                break
            write_new(folder / "started.json", {"utc": now(), "slot": slot,
                      "protocol_sha256": read_json(out / "protocol.sha256.json")["sha256"]})
            journal.append("episode_started", slot_id=slot["slot_id"])
            started += 1
            policy = policy_factory(slot["model"], directory=out, slot=slot["slot_id"],
                                    journal=journal, max_calls=protocol["max_chat_calls"],
                                    deadline_utc=deadline,
                                    expected_digest=protocol["models"][slot["model"]]["tag"]["digest"],
                                    prompt_version=slot["prompt_version"], **protocol["settings"])
            case = cases[slot["case_id"]]
            before = time.monotonic()
            journal_before = len(journal.records)
            try:
                # Recheck the tag before every episode without making generation calls.
                tags = policy.list_models()
                identities = [item for item in tags if item["name"] == slot["model"]]
                if len(identities) != 1 or identities[0].get("digest") != protocol["models"][slot["model"]]["tag"]["digest"]:
                    raise PolicyError("Model tag/digest changed during the study")
                episode = run_policy_scenario(case.config, policy, seed=slot["world_seed"],
                                              max_attempts=protocol["max_attempts"], template=case.template)
                write_new(folder / "trace.json", episode.trace.to_dict())
                write_new(folder / "explanation.json", episode.explanation.to_dict())
                write_new(folder / "evaluator-truth.json", {"records": to_dict(episode.ground_truth),
                          "scenario": to_dict(case.config), "action_selected": episode.action_selected})
                receipt = {"status": "completed", "slot": slot, "policy_calls": policy.calls,
                           "elapsed_seconds": time.monotonic()-before, "finished_utc": now(),
                           "artifact_sha256": {name: digest((folder / name).read_bytes()) for name in
                              ("trace.json", "explanation.json", "evaluator-truth.json")}}
            except PolicyError as error:
                receipt = {"status": "failed", "slot": slot, "policy_calls": policy.calls,
                           "error_type": type(error).__name__, "error": str(error),
                           "infrastructure_failure": isinstance(error, InfrastructurePolicyError),
                           "elapsed_seconds": time.monotonic()-before, "finished_utc": now()}
            write_new(folder / "receipt.json", receipt)
            journal.append("episode_finished", slot_id=slot["slot_id"], status=receipt["status"],
                           receipt_sha256=digest((folder / "receipt.json").read_bytes()))
            print(json.dumps({"slot": slot["slot_id"], "status": receipt["status"],
                              "calls": policy.calls}), flush=True)
            recent = journal.records[journal_before:]
            infrastructure_failure = receipt["status"] == "failed" and (
                receipt.get("infrastructure_failure", False) or policy.calls == 0 or any(event["event"] in {
                    "chat_transport_failed", "model_identity_failed", "chat_identity_failed",
                    "wall_time_exhausted", "call_budget_exhausted"
                } or (event["event"] == "chat_received" and event["status"] != 200)
                    for event in recent))
            if infrastructure_failure:
                journal.append("run_infrastructure_stop", failed_slot_id=slot["slot_id"])
                break
        journal.append("run_stopped", newly_started_episodes=started)
        return {"newly_started_episodes": started, "planned_episodes": protocol["planned_episodes"]}
    finally:
        # Remove only our own nonrecursive exact lock; evidence remains in journal.
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("freeze")
    preparation.add_argument("--study", default=str(ROOT / "docs/studies/refund-family-candidates-v1.json"))
    preparation.add_argument("--protocol", default=str(PROTOCOL_DOCUMENT),
                             help="Exact written precollection protocol to snapshot and bind")
    preparation.add_argument("--models", nargs="+", required=True)
    preparation.add_argument("--samples", type=int, default=7)
    preparation.add_argument("--seed", type=int, default=18000000)
    preparation.add_argument("--order-seed", type=int, default=18000099)
    preparation.add_argument("--base-url", default="http://127.0.0.1:11434")
    preparation.add_argument("--temperature", type=float, default=0.2)
    preparation.add_argument("--num-predict", type=int, default=384)
    preparation.add_argument("--timeout", type=float, default=180)
    preparation.add_argument("--max-wall-seconds", type=float, default=21600)
    preparation.add_argument("--output", required=True)
    execution = commands.add_parser("run")
    execution.add_argument("--output", required=True)
    execution.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.command == "run" and args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    result = freeze(args) if args.command == "freeze" else run(args.output, limit=args.limit)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
