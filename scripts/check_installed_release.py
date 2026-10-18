"""Dependency-free, offline release smoke checks against an installed wheel.

Copy this file and the reviewed wheel outside the source checkout, install that
wheel into a fresh virtual environment, then run with that environment's Python:

    python -I check_installed_release.py --wheel FILE.whl \
        --expected-wheel-sha256 HASH --expected-version 1.1.0 --output receipt.json

This is an application integration and installation check, not the full test
suite. It does not execute an agent, contact a provider, or import the benchmark.
The recorded platform identifies where the check actually ran; a Windows result
never constitutes a Linux result. The API checks do not import benchmark code.
CLI subprocesses import packaged research modules but do not execute scenarios
or replay. Existing receipts and source traces are kept.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from email.parser import Parser
from hashlib import sha256
from importlib import metadata, resources
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile


PRIVATE_MARKER = "cq-private-smoke-7da2"
UNSAFE_TEXT = PRIVATE_MARKER + " </pre><script>alert('captured data')</script>"


def require(condition: bool, message: str) -> None:
    """Keep release gates active when the interpreter uses optimization."""
    if not condition:
        raise ValueError(message)


def checked_wheel(path: Path, expected_sha256: str, expected_version: str) -> dict:
    """Bind checks to one reviewed artifact before importing the distribution."""
    require(bool(re.fullmatch(r"[a-f0-9]{64}", expected_sha256)),
            "Expected wheel SHA-256 must be 64 lowercase hexadecimal characters")
    require(path.name.endswith(".whl"), "A built wheel is required")
    content = path.read_bytes()
    require(sha256(content).hexdigest() == expected_sha256, "Reviewed wheel hash differs")
    with ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "Wheel contains duplicate entries")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        require(len(metadata_names) == 1, "Wheel must contain exactly one METADATA record")
        record = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
        require(record["Name"] == "consequa-x" and record["Version"] == expected_version,
                "Reviewed wheel distribution/version differs")
        payloads = {name: sha256(archive.read(name)).hexdigest() for name in names
                    if name.startswith("consequa_x/") and not name.endswith("/")}
    require(bool(payloads), "Wheel contains no package payload")
    return {"filename": path.name, "bytes": len(content), "sha256": expected_sha256,
            "payload_sha256": payloads}


def checked_install(wheel: dict, expected_version: str) -> dict:
    """Reject editable/source imports and compare every installed wheel payload."""
    import consequa_x
    from consequa_x.schema import generate_trace_schema, get_trace_schema

    package_file = Path(consequa_x.__file__).resolve()
    require(any(part in {"site-packages", "dist-packages"} for part in package_file.parts),
            "Import must come from installed site-packages, outside the checkout")
    distribution = metadata.distribution("consequa-x")
    require(consequa_x.__version__ == distribution.version == expected_version,
            "Installed import/metadata versions differ from reviewed version")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    require(not direct_url.get("dir_info", {}).get("editable"),
            "Editable installs do not validate a built wheel")
    dependencies = distribution.metadata.get_all("Requires-Dist", [])
    require(all(";" in item and "extra ==" in item.split(";", 1)[1]
                for item in dependencies), "Required runtime dependencies must remain empty")
    require(distribution.metadata["License-Expression"] == "MIT", "License metadata changed")
    for relative, digest in wheel["payload_sha256"].items():
        installed = package_file.parent.parent / relative
        require(installed.is_file() and sha256(installed.read_bytes()).hexdigest() == digest,
                f"Installed payload differs from reviewed wheel: {relative}")
    schema = resources.files("consequa_x").joinpath("schemas/trace-v0.1.json")
    require(get_trace_schema() == generate_trace_schema() == json.loads(
        schema.read_text(encoding="utf-8")), "Installed portable trace schema differs")
    require(resources.files("consequa_x").joinpath("py.typed").is_file(),
            "Installed typing marker is missing")
    return {"module_file": str(package_file), "version": distribution.version,
            "runtime_dependencies": 0, "matching_wheel_payloads": len(wheel["payload_sha256"])}


def artifact_trace(*, content: bytes = b"approved artifact", available: bool = True,
                   origin: bool = True):
    """Build a self-contained captured fixture using only the installed public API.

    The application owns the exactly-one delivery predicate and its independent
    readback. No benchmark helper or repository example is loaded by this file.
    The small verifier interprets only this declared, bounded fixture format.
    """
    from consequa_x import (
        Action, AgentAssessment, AssessmentStatus, Evidence, Event, EventType, Observation,
        OriginStatus, OutcomeContract, ResponseStatus, ToolResponse, Trace,
        VerificationResult, VerificationStatus, verify,
    )

    expected = {"path": PRIVATE_MARKER + "/report.txt",
                "sha256": sha256(b"approved artifact").hexdigest()}
    action = Action(PRIVATE_MARKER + "-action", PRIVATE_MARKER + "-trace",
                    PRIVATE_MARKER + "-agent", PRIVATE_MARKER + "-deliver", expected, 0,
                    OutcomeContract(PRIVATE_MARKER + "-contract", "artifact_delivered",
                                    expected, 50, stability_ms=20),
                    idempotency_key=PRIVATE_MARKER + "-key")
    record = {"effect_id": PRIVATE_MARKER + "-effect", "path": expected["path"],
              "sha256": sha256(content).hexdigest(), "committed_at_ms": 25,
              "present_through_ms": 100}
    if origin:
        record.update(action_id=action.action_id, actor=action.actor)
    observation = Observation(PRIVATE_MARKER + "-observation", PRIVATE_MARKER + "-readback",
                              100, 100, {"path": expected["path"]}, (record,),
                              available=available)

    class CapturedArtifactVerifier:
        def verify(self, action, observation):
            evidence = (Evidence(observation.observation_id, observation.source,
                                 observation.as_of_ms, {"records": list(observation.records),
                                                       "scope": observation.scope}),)
            matching = [item for item in observation.records
                        if item["path"] == action.contract.expected["path"]
                        and item["sha256"] == action.contract.expected["sha256"]
                        and action.registered_at_ms <= item["committed_at_ms"]
                        <= action.contract.deadline_ms
                        and item["present_through_ms"] >= action.contract.horizon_ms]
            if not observation.available or not observation.complete:
                status = VerificationStatus.UNKNOWN
            elif (observation.scope != {"path": action.contract.expected["path"]}
                  or observation.as_of_ms < action.contract.horizon_ms):
                status = VerificationStatus.UNKNOWN
            else:
                status = (VerificationStatus.SATISFIED if len(matching) == 1
                          else VerificationStatus.VIOLATED)
            identifiers = tuple(item["effect_id"] for item in observation.records)
            linked = tuple(item["effect_id"] for item in observation.records
                           if item.get("action_id") == action.action_id
                           and item.get("actor") == action.actor)
            return VerificationResult(action.contract.contract_id, status,
                                      observation.observed_at_ms, evidence,
                                      OriginStatus.CONFIRMED if linked else OriginStatus.UNKNOWN,
                                      identifiers, linked, UNSAFE_TEXT)

    decision = Event(PRIVATE_MARKER + "-decision", action.trace_id, EventType.AGENT_DECISION,
                     1, action.actor, data={"captured_payload": UNSAFE_TEXT})
    dispatch = Event(PRIVATE_MARKER + "-dispatch", action.trace_id, EventType.ACTION_DISPATCH,
                     5, action.actor, (decision.id,), {"action_id": action.action_id})
    timeout = Event(PRIVATE_MARKER + "-timeout", action.trace_id, EventType.TOOL_RESPONSE,
                    10, action.actor, (dispatch.id,), {"attempt_id": PRIVATE_MARKER + "-attempt"})
    response = ToolResponse(PRIVATE_MARKER + "-attempt", ResponseStatus.TIMEOUT, 10,
                            PRIVATE_MARKER + "-request", {"payload": UNSAFE_TEXT})
    assessment = AgentAssessment(AssessmentStatus.FAILURE, 11, (timeout.id,), UNSAFE_TEXT)
    receipt = verify(action, observation, verifier=CapturedArtifactVerifier())
    return Trace(action.trace_id, action, (decision, dispatch, timeout), (response,), assessment,
                 (observation,), (receipt,))


class ArtifactTargetMatcher:
    """Check captured content and time separately from the fixture's origin link."""

    def matching_effect_ids(self, action, verification):
        from consequa_x import VerificationStatus

        if verification.status is VerificationStatus.UNKNOWN:
            return ()
        return tuple(item["effect_id"] for item in verification.evidence[-1].details["records"]
                     if item["effect_id"] in verification.attributable_effect_ids
                     and item["path"] == action.contract.expected["path"]
                     and item["sha256"] == action.contract.expected["sha256"]
                     and action.registered_at_ms <= item["committed_at_ms"]
                     <= action.contract.deadline_ms
                     and item["present_through_ms"] >= action.contract.horizon_ms)


def check_trace_workflow() -> dict:
    from consequa_x import OriginStatus, Trace, explain
    from consequa_x.schema import validate_trace

    matcher = ArtifactTargetMatcher()
    statuses = set()
    traces = (artifact_trace(), artifact_trace(content=b"different captured bytes"),
              artifact_trace(available=False), artifact_trace(origin=False))
    for trace in traces:
        require(Trace.from_json(trace.to_json()) == validate_trace(trace.to_json())
                == validate_trace(trace.to_dict()) == trace, "Trace round-trip changed evidence")
        explanation = explain(trace, target_matcher=matcher)
        statuses.add(explanation.consequence.status.value)
        require(bool(explanation.graph.nodes), "Evidence graph is empty")
    require(statuses == {"satisfied", "violated", "unknown"}, "Outcome coverage differs")
    require(explain(traces[0]).assessment_alignment == "unassessable",
            "Generic predicate must be neutral without a target matcher")
    require(explain(traces[0], target_matcher=matcher).assessment_alignment == "contradicted",
            "Independent matching delivery must contradict a reported failure")
    require(explain(traces[2], target_matcher=matcher).assessment_alignment == "unassessable",
            "Unavailable readback must preserve unknown assessment alignment")
    unknown_origin = explain(traces[3], target_matcher=matcher)
    require(unknown_origin.consequence.origin is OriginStatus.UNKNOWN
            and unknown_origin.assessment_alignment == "unassessable",
            "Satisfied state alone cannot establish action origin")
    incomplete = replace(traces[0], verifications=())
    try:
        explain(incomplete)
    except ValueError:
        pass
    else:
        raise ValueError("Missing independent verification was accepted")
    return {"trace_roundtrips": len(traces), "observed_statuses": sorted(statuses),
            "custom_verifier": True, "custom_target_matcher": True,
            "missing_verification_refused": True, "unknown_origin_preserved": True}


def captured_record_trace(mode: str):
    """Capture one synthetic tool call with the 1.2 recorder; a list is the record store.

    ``timeout_after_commit`` writes the record, then times out (``attempt()``);
    ``other_actor`` times out before writing while a different actor writes the
    record (``capture_tool``); ``stale`` succeeds (``call()``) but is read back
    from a snapshot whose watermark precedes the contract horizon.
    """
    from consequa_x import Observation, OutcomeContract, RecordVerifier, TraceRecorder, capture_tool

    now = [0]
    rec = TraceRecorder(PRIVATE_MARKER + "-capture", actor=PRIVATE_MARKER + "-agent",
                        clock=lambda: now[0])
    expected = {"order_id": PRIVATE_MARKER + "-order", "amount_minor": 5000}
    contract = OutcomeContract(PRIVATE_MARKER + "-record-contract", "record_present", expected,
                               deadline_ms=200, exact_count=1, stability_ms=50)
    verifier = RecordVerifier(scope_fields=("order_id",))
    store = []
    message = rec.context("user_input", {"message": UNSAFE_TEXT})
    now[0] = 2
    rec.decision({"tool": "issue_refund"}, inputs=(message,))
    now[0] = 3
    action = rec.register(PRIVATE_MARKER + "-refund", "issue_refund", expected, contract=contract)
    now[0] = 5

    def write(effect_id, **origin):
        store.append({"effect_id": effect_id, **expected, "committed_at_ms": 40, **origin})

    if mode == "timeout_after_commit":
        try:
            with rec.attempt(data={"tool": "issue_refund"}) as attempt:
                write(PRIVATE_MARKER + "-effect", action_id=action.action_id,
                      actor=action.actor, attempt_id=attempt.attempt_id)
                now[0] = 60
                raise TimeoutError(UNSAFE_TEXT)
        except TimeoutError:
            pass
    elif mode == "other_actor":
        @capture_tool(rec)
        def issue_refund(arguments):
            now[0] = 60
            raise TimeoutError(UNSAFE_TEXT)

        try:
            issue_refund(expected)
        except TimeoutError:
            pass
        write(PRIVATE_MARKER + "-staff-effect", actor=PRIVATE_MARKER + "-staff")
    else:
        def issue_refund(arguments):
            write(PRIVATE_MARKER + "-effect", action_id=action.action_id, actor=action.actor)
            now[0] = 60
            return {"accepted": True}

        require(rec.call(issue_refund, expected) == {"accepted": True},
                "Recorded tool call changed the tool's result")
    now[0] = 61
    rec.assessment("success" if mode == "stale" else "failure")
    now[0] = 300
    observation = Observation(PRIVATE_MARKER + "-readback", PRIVATE_MARKER + "-replica",
                              rec.now(), 100 if mode == "stale" else 300,
                              {"order_id": expected["order_id"]}, tuple(store))
    rec.verify(observation, verifier=verifier)
    return rec.trace(), verifier


def check_capture_workflow() -> dict:
    """Exercise the 1.2 recorder, tool capture and record verifier from the install."""
    import asyncio
    from types import SimpleNamespace

    from consequa_x import (OutcomeContract, ResponseStatus, Trace, TraceRecorder, explain,
                            render_report)
    from consequa_x.mcp_capture import call_mcp_tool
    from consequa_x.schema import validate_trace

    expected = {"timeout_after_commit": ("timeout", "satisfied", "confirmed", "contradicted"),
                "other_actor": ("timeout", "satisfied", "other_actor", "unassessable"),
                "stale": ("success", "unknown", "unknown", "unassessable")}
    for mode, outcome in expected.items():
        trace, verifier = captured_record_trace(mode)
        require(Trace.from_json(trace.to_json()) == validate_trace(trace.to_json()) == trace,
                "Recorded trace round-trip changed evidence")
        (response,) = trace.responses
        if response.status is ResponseStatus.TIMEOUT:
            require(response.result == {"exception": "TimeoutError"},
                    "Recorded exception kept more than its type name")
        explanation = explain(trace, target_matcher=verifier.target_matcher())
        observed = (response.status.value, explanation.consequence.status.value,
                    explanation.consequence.origin.value, explanation.assessment_alignment)
        require(observed == outcome, f"Recorded {mode} outcome differs: {observed}")
        require(PRIVATE_MARKER not in render_report(trace),
                "Default report of a recorded trace leaked captured identity")

    class StandInSession:
        """Has the MCP ClientSession.call_tool shape; no MCP SDK is installed or used."""

        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=True, content=[UNSAFE_TEXT])

    rec = TraceRecorder(PRIVATE_MARKER + "-mcp", actor=PRIVATE_MARKER + "-agent")
    rec.register(PRIVATE_MARKER + "-mcp-action", "issue_refund", {}, contract=OutcomeContract(
        PRIVATE_MARKER + "-mcp-contract", "record_present", {"order_id": "o-1"}, 200))
    asyncio.run(call_mcp_tool(rec, StandInSession(), "issue_refund", {}))
    rec.assessment("unknown")
    (response,) = rec.trace().responses
    require(response.status is ResponseStatus.ERROR and response.result == {"is_error": True}
            and UNSAFE_TEXT not in rec.trace().to_json(),
            "MCP tool error was not recorded as an error without its content")
    return {"recorded_modes": sorted(expected), "record_verifier": True,
            "attempt_context": True, "capture_tool": True, "recorder_call": True,
            "mcp_error_recorded": True, "exception_messages_dropped": True}


def invalid_trace_inputs() -> dict[str, str]:
    """Exercise structural, numeric and cross-record strict decoding gates."""
    good = artifact_trace().to_dict()
    mutations = {
        "unknown_top_level": lambda item: item.update(unexpected=True),
        "unknown_nested_field": lambda item: item["action"].update(unexpected=True),
        "boolean_time": lambda item: item["action"].update(registered_at_ms=True),
        "wrong_trace_identity": lambda item: item["action"].update(trace_id="different"),
        "missing_evidence_event": lambda item: item["assessment"].update(
            evidence_event_ids=["missing"]),
        "unsupported_version": lambda item: item.update(schema_version="999"),
    }
    invalid = {}
    for name, mutate in mutations.items():
        value = json.loads(json.dumps(good))
        mutate(value)
        invalid[name] = json.dumps(value)
    invalid["duplicate_json_field"] = '{"trace_id":"first","trace_id":"second"}'
    invalid["non_finite_number"] = '{"trace_id":NaN}'
    return invalid


def check_schema_refusals() -> int:
    from consequa_x import Trace
    from consequa_x.schema import validate_trace

    invalid = invalid_trace_inputs()
    for name, text in invalid.items():
        for decoder in (Trace.from_json, validate_trace):
            try:
                decoder(text)
            except (ValueError, TypeError):
                pass
            else:
                raise ValueError(f"Strict decoder accepted invalid trace: {name}")
    return len(invalid) * 2


def check_reports(directory: Path) -> dict:
    from consequa_x import render_report

    trace = artifact_trace()
    before = trace.to_json()
    safe = render_report(trace)
    detailed = render_report(trace, include_details=True)
    require(PRIVATE_MARKER not in safe, "Default report leaked captured payload/identity")
    require(PRIVATE_MARKER in detailed and "&lt;script&gt;" in detailed,
            "Details report must explicitly include escaped captured text")
    for report in (safe, detailed):
        require("<script" not in report.lower() and "<iframe" not in report.lower(),
                "Report must not contain active captured markup or embedded remote content")
        require("<!doctype html>" in report.lower() and "<svg" in report.lower(),
                "Report lacks an HTML document/evidence graph")
    require(trace.to_json() == before, "Rendering altered source evidence")
    source = directory / "captured-trace.json"
    source.write_text(before, encoding="utf-8")
    source_bytes = source.read_bytes()
    destination = directory / "report.html"
    command = [sys.executable, "-I", "-m", "consequa_x", "report"]

    def run(arguments, success):
        result = subprocess.run(command + arguments, cwd=directory, capture_output=True,
                                text=True, timeout=60, check=False)
        require((result.returncode == 0) is success,
                f"Unexpected report CLI result ({result.returncode}): {result.stderr[:1000]}")
        return result.returncode

    run([str(source), "--output", str(destination)], True)
    require(destination.read_text(encoding="utf-8") == safe,
            "Report CLI and API default output differ")
    saved = destination.read_bytes()
    run([str(source), "--output", str(destination)], False)
    require(destination.read_bytes() == saved, "CLI overwrote an existing report")
    run([str(source), "--output", str(source)], False)
    require(source.read_bytes() == source_bytes, "CLI overwrote the source trace")
    detailed_path = directory / "report-details.html"
    run([str(source), "--output", str(detailed_path), "--include-details"], True)
    require(detailed_path.read_text(encoding="utf-8") == detailed,
            "Report CLI and API explicit-detail output differ")
    for name, text in invalid_trace_inputs().items():
        invalid = directory / (name + ".json")
        invalid.write_text(text, encoding="utf-8")
        invalid_bytes = invalid.read_bytes()
        output = directory / (name + ".html")
        run([str(invalid), "--output", str(output)], False)
        require(not output.exists() and invalid.read_bytes() == invalid_bytes,
                f"Refused invalid input changed source or created a report: {name}")
    return {"default_omits_captured_details": True, "explicit_details_escaped": True,
            "source_unchanged": True, "existing_output_preserved": True,
            "invalid_inputs_refused_without_output": len(invalid_trace_inputs()),
            "cli_checks": 4 + len(invalid_trace_inputs())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--expected-wheel-sha256", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "Keep prior installation receipts; choose a new output")
    require(sys.flags.isolated == 1, "Run the checker with python -I to isolate imports")
    require(not any((parent / "pyproject.toml").exists()
                    for parent in (Path.cwd(), *Path.cwd().parents)),
            "Run the installed checker from outside a source/project checkout")
    wheel = checked_wheel(args.wheel, args.expected_wheel_sha256, args.expected_version)
    install = checked_install(wheel, args.expected_version)
    workflow = check_trace_workflow()
    capture = check_capture_workflow()
    refusals = check_schema_refusals()
    with tempfile.TemporaryDirectory(prefix="consequa-installed-") as temporary:
        reports = check_reports(Path(temporary))
    require(not any(name.startswith("consequa_x.benchmark") for name in sys.modules),
            "Installed application integration unexpectedly imported benchmark code")
    receipt = {"passed": True, "python": platform.python_version(),
               "platform": platform.platform(), "system": platform.system(),
               "machine": platform.machine(), "kernel_release": platform.release(),
               "executable": sys.executable, "isolated_imports": True,
               "wheel": {key: value for key, value in wheel.items() if key != "payload_sha256"},
               "install": install, "workflow": workflow, "capture": capture,
               "strict_schema_refusals": refusals,
               "reports": reports, "provider_calls": 0, "api_process_benchmark_imports": 0,
               "cli_import_scope": ("CLI imports packaged research modules but does not "
                                    "execute scenarios/replay"),
               "checker_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}
    if sys.platform == "linux":
        receipt["linux_distribution"] = platform.freedesktop_os_release()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
