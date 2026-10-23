"""Prepare/freeze and serially collect the separately registered LIMBO study."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.limbo_agent.protocol import (  # noqa: E402
    environment_binding, extract_metadata, file_binding, freeze, native_binding, source_binding, utc, write_new,
)
from research.limbo_agent.harness import (  # noqa: E402
    collect, execute_slot, installed_wheel_binding, manifest, run_episode_worker,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="phase", required=True)
    for name in ("prepare", "readiness", "freeze", "collect", "development", "_episode"):
        p = sub.add_parser(name)
        p.add_argument("--native-root", required=True)
        p.add_argument("--output", required=True)
        if name in ("readiness", "freeze", "development"):
            p.add_argument("--wheel", required=True)
            p.add_argument("--runtime-binding", required=True)
        if name == "readiness":
            p.add_argument("--baseline-audit", required=True)
            p.add_argument("--guard-audit", required=True)
            p.add_argument("--transport-proof", required=True)
        if name in ("freeze", "development"):
            p.add_argument("--max-tool-calls", type=int, default=16)
            p.add_argument("--max-requests", type=int, default=16)
            p.add_argument("--max-output-tokens", type=int, default=512)
            p.add_argument("--request-timeout", type=float, default=1200)
            p.add_argument("--episode-timeout", type=float, default=7200)
            p.add_argument("--seed", type=int, default=1701)
        if name == "freeze":
            p.add_argument("--world-count", type=int, default=24)
            p.add_argument("--index-salt", type=int, default=1022)
            p.add_argument("--readiness", required=True)
        if name == "collect":
            p.add_argument("--protocol", required=True)
            p.add_argument("--protocol-commit", required=True)
        if name == "development":
            p.add_argument("--template", required=True)
            p.add_argument("--index", type=int, choices=(0, 1), default=0)
            p.add_argument("--mode", default="timeout_post")
            p.add_argument("--arm", choices=("vanilla", "sdk_retry3", "guard", "conseqax_guard"),
                           default="conseqax_guard")
            p.add_argument("--ledger", required=True)
        if name == "_episode":
            p.add_argument("--config", required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if args.phase == "_episode":
        run_episode_worker(ROOT, args.native_root, args.config, out)
    elif args.phase == "collect":
        collect(ROOT, args.native_root, args.protocol, args.protocol_commit, out)
    elif args.phase == "prepare":
        out.mkdir(parents=True, exist_ok=False)
        metadata = extract_metadata(args.native_root, 1022)
        write_new(out / "metadata.json", metadata)
        write_new(out / "identity.json", {"native": native_binding(args.native_root),
                                           "sources": source_binding(ROOT), "utc": utc()})
        write_new(out / "manifest.json", manifest(out))
        print(json.dumps({"templates": len(metadata), "domains": sorted({d for m in metadata for d in m["domains"]}),
                          "task_targets_or_instructions_exported": False}))
    elif args.phase == "readiness":
        audits = {"baseline": json.loads(Path(args.baseline_audit).read_text(encoding="utf-8")),
                  "guard": json.loads(Path(args.guard_audit).read_text(encoding="utf-8"))}
        proof = json.loads(Path(args.transport_proof).read_text(encoding="utf-8"))
        binding = json.loads(Path(args.runtime_binding).read_text(encoding="utf-8"))
        if (not proof.get("passed") or proof["runtime"] != binding or proof["native_episodes"] != 0):
            raise ValueError("Current runtime needs a passed task-independent transport proof")
        for kind, audit in audits.items():
            if (not audit["passed"] or audit["sources"] != source_binding(ROOT)
                    or not audit["row"]["audit_complete"] or not audit["row"]["execution_success"]):
                raise ValueError("Readiness requires complete current-source excluded development audits")
            from research.limbo_agent.audit import verify_manifest
            verify_manifest(Path(audit["episode"]))
            if file_binding(Path(audit["episode"]) / "manifest.json") != audit["episode_manifest"]:
                raise ValueError("Development episode manifest changed")
            if audit["spec"]["index"] not in (0, 1):
                raise ValueError("Readiness development index is not excluded")
        if (audits["baseline"]["spec"]["policy"] != "vanilla"
                or audits["baseline"]["spec"]["mode"] != "none"
                or audits["guard"]["spec"]["policy"] != "conseqax_guard"
                or audits["guard"]["spec"]["mode"] == "none"
                or not audits["guard"]["row"]["fault_triggered"]
                or audits["guard"]["row"]["receipt_count"] < 1):
            raise ValueError("Need native clean baseline and actual fault-triggered SDK receipt run")
        out.mkdir(parents=True, exist_ok=False)
        value = {"passed": True, "utc": utc(), "native": native_binding(args.native_root),
                 "sources": source_binding(ROOT), "wheel": installed_wheel_binding(args.wheel),
                 "wheel_file": file_binding(args.wheel),
                 "runtime_binding": json.loads(Path(args.runtime_binding).read_text(encoding="utf-8")),
                 "development_audits": {"baseline": {"path": str(Path(args.baseline_audit).resolve()),
                                                        **file_binding(args.baseline_audit)},
                                        "guard": {"path": str(Path(args.guard_audit).resolve()),
                                                     **file_binding(args.guard_audit)}},
                 "transport_proof": {"path": str(Path(args.transport_proof).resolve()),
                                      **file_binding(args.transport_proof)},
                 "scope": "File/payload, live full transport and independently replayed excluded native development gates"}
        write_new(out / "readiness.json", value)
        write_new(out / "manifest.json", manifest(out))
    elif args.phase == "freeze":
        readiness = json.loads(Path(args.readiness).read_text(encoding="utf-8"))
        if not readiness.get("passed") or readiness["sources"] != source_binding(ROOT):
            raise ValueError("Readiness is failed or source bytes changed")
        freeze(ROOT, args.native_root, args.wheel, args.runtime_binding, out,
               world_count=args.world_count, index=args.index_salt,
               max_tool_calls=args.max_tool_calls, max_requests=args.max_requests,
               max_output_tokens=args.max_output_tokens, request_timeout_s=args.request_timeout,
               episode_timeout_s=args.episode_timeout, seed=args.seed, readiness_path=args.readiness)
    elif args.phase == "development":
        # Persistent reservation is made before any model client is constructed.
        ledger = Path(args.ledger).resolve()
        ledger.mkdir(parents=True, exist_ok=True)
        lock = ledger / "exclusive-lock"
        lock.mkdir(exist_ok=False)
        try:
            reservations = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ledger.glob("reservation-*.json"))]
            consumed = 0
            for i, reservation in enumerate(reservations):
                settlement = ledger / f"settlement-{i:03d}.json"
                if settlement.exists():
                    settled = json.loads(settlement.read_text(encoding="utf-8"))
                    if settled["reservation"] != file_binding(ledger / f"reservation-{i:03d}.json"):
                        raise ValueError("Development settlement binding differs")
                    consumed += settled["consumed"]
                else:
                    consumed += reservation["reserved"]
            if args.max_requests < 1 or consumed + args.max_requests > 24:
                raise ValueError("Separate LIMBO development allowance of 24 invocations would be exceeded")
            reservation_number = len(reservations)
            reservation_path = ledger / f"reservation-{reservation_number:03d}.json"
            write_new(reservation_path,
                      {"utc": utc(), "reserved": args.max_requests, "output": str(out),
                       "release_unused_only_with_complete_terminal_accounting": True, "index": args.index})
        finally:
            lock.rmdir()
        sys.path.insert(0, str(Path(args.native_root).resolve()))
        # Trusted development extractor selects only focal labels/affordances.
        from limbo.tasks import make_task
        task = make_task(args.template, args.index)
        compatible = [f for f in task.focals if args.mode != "partial_timeout" or f.batch]
        if not compatible:
            raise ValueError("Development fault incompatible with selected template")
        binding = json.loads(Path(args.runtime_binding).read_text(encoding="utf-8"))
        spec = dict(template=args.template, index=args.index, focal=compatible[0].label, mode=args.mode,
                    model=binding["model"], policy=args.arm, human_available=False, contract="native",
                    max_tool_calls=args.max_tool_calls, experiment="conseqax-limbo-excluded-development",
                    doc_variant="neutral", paraphrase=0, reasoning_effort=None, replicate=0,
                    harness="minimal", instruction_variant="default")
        protocol = {"sources": source_binding(ROOT), "native": native_binding(args.native_root),
                    "environment": environment_binding(),
                    "wheel": {"path": str(Path(args.wheel).resolve()), **file_binding(args.wheel)},
                    "runtime_binding": binding, "seed": args.seed,
                    "limits": {"max_requests": args.max_requests,
                               "max_output_tokens": args.max_output_tokens,
                               "request_timeout_s": args.request_timeout,
                               "episode_timeout_s": args.episode_timeout,
                               "work": {"execute": 96, "verify": 64, "wait": 64, "total_wait_seconds": 172800}}}
        returned = execute_slot(ROOT, args.native_root, protocol,
                     {"slot": 0, "world_rank": 0, "arm": args.arm, "spec": spec}, out)
        summary = out / "model/client-summary.json"
        if returned["status"] == "child_returned" and summary.exists():
            counts = json.loads(summary.read_text(encoding="utf-8"))
            from research.limbo_agent.audit import jsonl
            journal = jsonl(out / "model/model-calls.jsonl")
            starts = [r for r in journal if r["event"] == "request_start"]
            terminals = list((out / "model").glob("*-terminal.json"))
            dispatched = [r for r in journal if r["event"] == "before_dispatch"]
            if (len(starts) == len(terminals) == counts["invocations"]
                    and len(dispatched) == counts["generation_dispatch_attempts"] <= args.max_requests):
                write_new(ledger / f"settlement-{reservation_number:03d}.json",
                          {"utc": utc(), "reservation": file_binding(reservation_path),
                           "consumed": len(dispatched), "complete_terminal_accounting": True,
                           "invocations_including_predispatch_refusals": len(starts),
                           "output_manifest": file_binding(out / "manifest.json")})


if __name__ == "__main__":
    main()
