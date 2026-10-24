"""Prospective, metadata-only LIMBO schedule and immutable file bindings.

Task generation stays inside the trusted extractor. Only template/family/domain,
focal public affordances and fault compatibility leave it, never instructions,
target matches, setup contents, expected outputs or task-specific values.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

PIN = "2db09fba22a0572a70639162a808906409f612a8"
ARMS = ("vanilla", "sdk_retry3", "guard", "conseqax_guard")
MODES = ("timeout_pre", "timeout_post", "timeout_late", "timeout_late_tail",
         "partial_timeout", "duplicate_delivery")
SCHEMA = "conseqax-limbo-protocol-v1"


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_binding(path):
    path = Path(path)
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


def native_binding(root):
    root = Path(root).resolve()
    if git(root, "rev-parse", "HEAD") != PIN:
        raise ValueError("Native source is not the declared upstream pin")
    # Check the complete tracked implementation, not only currently imported files.
    names = git(root, "ls-files", "limbo").splitlines()
    result = {}
    for name in names:
        if not name.endswith(".py"):
            continue
        actual = (root / name).read_bytes()
        blob = subprocess.run(["git", "-C", str(root), "show", f"{PIN}:{name}"],
                              check=True, capture_output=True).stdout
        if actual.replace(b"\r\n", b"\n") != blob.replace(b"\r\n", b"\n"):
            raise ValueError("Native source differs from committed bytes: " + name)
        result[name] = file_binding(root / name)
    if not result:
        raise ValueError("Native implementation binding is empty")
    return {"commit": PIN, "files": result}


def source_binding(root):
    root = Path(root)
    names = sorted(str(p.relative_to(root)).replace("\\", "/")
                   for p in (root / "research/limbo_agent").glob("*.py"))
    names += ["scripts/run_limbo_external_benchmark.py",
              "scripts/audit_limbo_external_benchmark.py", "research/native_agent/transport.py",
              "research/native_agent/__init__.py"]
    if (root / "research/__init__.py").exists():
        names.append("research/__init__.py")
    return {name: file_binding(root / name) for name in names}


def verify_files(root, bindings):
    for name, expected in bindings.items():
        candidate = (Path(root) / name).resolve()
        if not candidate.is_relative_to(Path(root).resolve()):
            raise ValueError("Binding escapes its declared root")
        if file_binding(candidate) != expected:
            raise ValueError("File identity changed: " + name)


def environment_binding():
    names = ("Jinja2", "tokenizers", "psutil", "consequa-x")
    return {"python_version": sys.version, "implementation": sys.implementation.name,
            "executable": {"path": sys.executable, **file_binding(sys.executable)},
            "base_executable": {"path": sys._base_executable, **file_binding(sys._base_executable)},
            "distributions": {name: importlib.metadata.version(name) for name in names},
            "coverage": "Interpreter executable bytes and dependency distribution versions; not all dependency payload bytes"}


def extract_metadata(native_root, index, seed=1701):
    """Trusted extractor; result intentionally excludes all task instance values."""
    sys.path.insert(0, str(Path(native_root).resolve()))
    from limbo.tasks import TEMPLATES, make_task
    from limbo.services import build_tools
    tools = build_tools("native")
    records = []
    for template in sorted(TEMPLATES):
        instance_index = 10000 + int(digest([seed, template, index])[:8], 16) % 1000000
        task = make_task(template, instance_index)
        focals = []
        for focal in task.focals:
            spec = tools[focal.tool]
            focals.append({"label": focal.label, "tool": focal.tool,
                           "domain": spec.domain, "batch": bool(focal.batch),
                           "verification": focal.verification,
                           "idempotency": focal.idempotency,
                           "reversible": bool(focal.reversible)})
        records.append({"template": template, "index": instance_index, "family": task.family,
                        "domains": sorted(task.domains), "focals": focals})
    return records


def make_schedule(metadata, *, world_count, model, max_tool_calls, seed=1701):
    if not metadata:
        raise ValueError("Empty metadata")
    if world_count != 2 * len(metadata):
        raise ValueError("Exactly one clean and one fault condition per template is required")
    # Metadata-only hash ranks are outcome independent. Every external template
    # has one clean condition and one compatible fault. Balance fault families
    # before applying the hash tie-break; no reward/target enters selection.
    templates = sorted(metadata, key=lambda m: digest([seed, m["template"], m["index"]]))
    candidates = []
    for m in templates:
        for f in m["focals"]:
            for mode in MODES:
                if mode == "partial_timeout" and not f["batch"]:
                    continue
                candidates.append({"template": m["template"], "index": m["index"],
                                   "focal": f["label"], "mode": mode,
                                   "family": m["family"], "domain": f["domain"],
                                   "affordances": {k: f[k] for k in
                                       ("batch", "verification", "idempotency", "reversible")}})
    batch_templates = [m for m in templates if any(f["batch"] for f in m["focals"])]
    reserved_partial = min(batch_templates, key=lambda m: digest([seed, "partial-slot", m["template"]]))["template"] if batch_templates else None
    selected, counts = [], {}
    for template in templates:
        available = [c for c in candidates if c["template"] == template["template"]]
        if template["template"] == reserved_partial:
            # Preserve coverage of the rare batch-only fault even when this
            # template's hash rank comes before the other fault families.
            available = [c for c in available if c["mode"] == "partial_timeout"]
        if not available:
            raise ValueError("Not enough compatible metadata worlds")
        chosen = min(available, key=lambda c: (counts.get(c["mode"], 0),
                     sum(x["domain"] == c["domain"] for x in selected), digest([seed, c])))
        clean = {**chosen, "mode": "none"}
        selected.extend((clean, chosen))
        counts[chosen["mode"]] = counts.get(chosen["mode"], 0) + 1
    slots = []
    for rank, world in enumerate(selected):
        order = ARMS[rank % len(ARMS):] + ARMS[:rank % len(ARMS)]
        for arm in order:
            spec = {k: world[k] for k in ("template", "index", "focal", "mode")}
            spec.update(model=model, policy=arm, human_available=False, contract="native",
                        max_tool_calls=max_tool_calls, experiment="conseqax-limbo-frozen-v1",
                        paraphrase=0, replicate=0, doc_variant="neutral", harness="minimal",
                        instruction_variant="default", reasoning_effort=None)
            slots.append({"slot": len(slots), "world_rank": rank, "arm": arm,
                          "metadata": world, "spec": spec})
    return slots


def freeze(root, native_root, wheel, runtime_path, output, *, world_count=24,
           index=1022, max_tool_calls=16, max_requests=16, max_output_tokens=512,
           request_timeout_s=1200, episode_timeout_s=7200, seed=1701, readiness_path=None):
    if max_requests < 1 or max_tool_calls < 1 or max_output_tokens < 1:
        raise ValueError("Positive budgets are required")
    if request_timeout_s <= 0 or episode_timeout_s <= request_timeout_s:
        raise ValueError("Episode deadline must exceed request timeout")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    binding = json.loads(Path(runtime_path).read_text(encoding="utf-8"))
    metadata = extract_metadata(native_root, index, seed)
    protocol = {"schema": SCHEMA, "created_utc": utc(), "seed": seed,
                "native": native_binding(native_root), "sources": source_binding(root),
                "environment": environment_binding(),
                "wheel": {"path": str(Path(wheel).resolve()), **file_binding(wheel)},
                "runtime_binding": binding,
                "runtime_binding_file": {"path": str(Path(runtime_path).resolve()),
                                         **file_binding(runtime_path)},
                "metadata": metadata, "arms": list(ARMS),
                "readiness": {"path": str(Path(readiness_path).resolve()), **file_binding(readiness_path)}
                             if readiness_path is not None else None,
                "limits": {"max_requests": max_requests, "max_output_tokens": max_output_tokens,
                           "request_timeout_s": request_timeout_s,
                           "episode_timeout_s": episode_timeout_s,
                           "work": {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}},
                "schedule": make_schedule(metadata, world_count=world_count, model=binding["model"],
                                           max_tool_calls=max_tool_calls, seed=seed),
                "claims": {"human_available": False, "paid_inference": False,
                           "retry_resume_replacement": False, "model_calls_serial": True,
                           "selection_uses_targets_or_outcomes": False,
                           "base_task_parameters_matched_clean_fault": True,
                           "native_world_rng_seed_depends_on_fault_mode": True,
                           "receipt_arm_same_native_guard_decisions": True,
                           "native_EOS_is_universal_exactly_once": False}}
    protocol["endpoints"] = {
        "primary": "Unchanged native TS and EOS true among independently replayed grades over all planned slots",
        "operational": "Complete independent native replay and available native grade, including saved LLM-error returns after native flush",
        "execution_success_secondary": "Operational plus no native error and no llm_error/harness_error stop",
        "unavailable_native_grade": "No invented semantic zero; contributes zero to planned primary success numerator",
        "receipt": "Native guard behavioral conformance and current public report mapping; no algorithmic superiority requirement"}
    write_new(output / "protocol.json", protocol)
    write_new(output / "protocol-receipt.json", {"protocol": file_binding(output / "protocol.json"),
                                               "created_utc": utc()})
    return protocol


def verify_protocol(root, native_root, path, commit):
    path = Path(path).resolve()
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("An exact 40-character protocol commit is required")
    relative = str(path.relative_to(Path(root).resolve())).replace("\\", "/")
    blob = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{relative}"],
                          check=True, capture_output=True).stdout
    if blob != path.read_bytes():
        raise ValueError("Protocol bytes differ from explicitly committed artifact")
    value = json.loads(blob)
    if value["schema"] != SCHEMA or value["native"]["commit"] != PIN:
        raise ValueError("Unsupported protocol or upstream source")
    verify_files(root, value["sources"])
    if canonical(value["sources"]) != canonical(source_binding(root)):
        raise ValueError("Scientific source inventory or namespace initializer changed")
    verify_files(native_root, value["native"]["files"])
    if canonical(value["environment"]) != canonical(environment_binding()):
        raise ValueError("Interpreter/dependency environment changed")
    if file_binding(value["wheel"]["path"]) != {k: value["wheel"][k] for k in ("sha256", "bytes")}:
        raise ValueError("Wheel changed")
    for name, binding in value["sources"].items():
        committed = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{name}"],
                                   check=True, capture_output=True).stdout
        if hashlib.sha256(committed).hexdigest() != binding["sha256"]:
            raise ValueError("Frozen source is not in protocol commit: " + name)
    expected = make_schedule(value["metadata"], world_count=len(value["schedule"]) // len(ARMS),
                             model=value["runtime_binding"]["model"],
                             max_tool_calls=value["schedule"][0]["spec"]["max_tool_calls"],
                             seed=value["seed"])
    if canonical(expected) != canonical(value["schedule"]):
        raise ValueError("Schedule is not the registered metadata selection")
    return value
