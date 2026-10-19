"""Corruption boundaries for the offline auditor; no research collectors are imported."""

import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_external_validation_artifacts as audit


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audit.encoded(value))
    return audit.digest(path.read_bytes())


def seal(directory, protocol):
    hashed = write(directory / "protocol.json", protocol)
    write(directory / "protocol.sha256.json", {"sha256": hashed})
    return hashed


def journal(directory, events):
    previous = None
    lines = []
    for index, event in enumerate(events):
        row = {**event, "index": index, "previous_sha256": previous}
        previous = audit.digest(audit.encoded(row))
        lines.append(audit.encoded({**row, "sha256": previous}))
    (directory / "request-journal.jsonl").write_bytes(b"".join(lines))


def judge_fixture(root):
    directory = root / "judge"
    slot = "episode_00000"
    public = {"contract": {"expected": True}, "observations": []}
    entry = {"slot": {"slot_id": slot, "model": "generator"}, "input_status": "available",
             "input_file": "inputs/input.json", "input_sha256": write(directory / "inputs/input.json", public),
             "judge_seed": 11}
    gold = {"state": True, "action_linked": True, "origin": "unknown"}
    context = {slot: {"gold": gold, "baselines": {
        "independent_public_reference": gold, "consequa_state_origin": gold}}}
    protocol = {"schedule": [entry], "selected_planned": 1, "available_inputs": 1,
                "code_sha256": {}, "external_source_sha256": {}, "source_revision": "a" * 40,
                "evaluation_context_sha256": write(directory / "evaluation-context.json", context),
                "model": "fixed-judge", "output_schema": {"type": "object"}, "prompt": "Read public evidence",
                "settings": {"temperature": 0.2, "num_predict": 192}}
    hashed = seal(directory, protocol)
    started_hash = write(directory / f"judgments/{slot}/started.json", {
        "entry": entry, "protocol_sha256": hashed})
    request_name, response_name = "calls/request.json", "calls/response.json"
    request = {"model": protocol["model"], "stream": False, "think": False, "format": protocol["output_schema"],
               "messages": [{"role": "system", "content": protocol["prompt"]},
                            {"role": "user", "content": audit.encoded(public).decode().rstrip("\n")}],
               "options": {"seed": 11, "temperature": 0.2, "num_predict": 192}}
    raw = {"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": json.dumps({
        "state": "satisfied", "action_linked": "unknown", "origin": "confirmed"})}}
    receipt = {"status": "completed", "attempted_calls": 1, "slot_id": slot,
               "prediction": {"state": True, "action_linked": None, "origin": "confirmed"}}
    events = [{"event": "run_started"},
              {"event": "judge_started", "slot_id": slot, "started_sha256": started_hash},
              {"event": "chat_started", "slot_id": slot, "call_id": slot + "-call-00",
               "request_file": request_name, "request_sha256": write(directory / request_name, request)},
              {"event": "chat_received", "slot_id": slot, "call_id": slot + "-call-00",
               "status": 200, "truncated": False, "response_file": response_name,
               "response_sha256": write(directory / response_name, raw)},
              {"event": "judge_finished", "slot_id": slot,
               "receipt_sha256": write(directory / f"judgments/{slot}/receipt.json", receipt)},
              {"event": "run_stopped", "stopped_reason": "all_never_started_slots_processed"}]
    journal(directory, events)
    return directory, hashed, events, protocol


def check_judge(root, fixture):
    directory, hashed, *_ = fixture
    return audit.audit_judge(audit.Audit(root), directory, expected_slots=1, expected_protocol_hash=hashed)


def tau_fixture(root):
    directory = root / "tau"
    upstream = root / "upstream"
    upstream.mkdir()
    (upstream / "source.py").write_bytes(b"upstream source bytes\n")
    slot = {"slot": 0, "domain": "retail", "task_id": "a", "variant": "reference",
            "task_sha256": "b" * 64, "source_index": 0}
    protocol = {"schedule": [slot], "local_hashes": {}, "source_revision": "a" * 40,
                "source": "C:/historical/upstream", "upstream_commit": "c" * 40,
                "upstream_hashes": {"source.py": audit.digest((upstream / "source.py").read_bytes())},
                "loaded_dependency_hashes": {}}
    hashed = seal(directory, protocol)
    write(directory / "started/episode_0000.json", {**slot, "started_utc": "2026-10-18T00:00:00Z"})
    capture = {"audit_disposition": "captured", "inputs_unchanged": True, "withheld_status": "unknown",
               "trace": {"verifications": [{"origin": "unknown", "status": "satisfied"}]},
               "explanation": {"assessment_alignment": "unassessable"}}
    episode = {"slot": 0, "domain": "retail", "task_id": "a", "variant": "reference",
               "source_task_sha256": slot["task_sha256"], "model_calls": 0, "disposition": "completed",
               "native_db_component": {"db_check": {"db_match": True}}, "action_audits": [capture],
               "native_calls": [{"executed": True}, {"executed": False}]}
    summary = {"planned": 1, "model_calls": 0, "upstream_commit": protocol["upstream_commit"],
               "files": {"episodes/episode_0000.json": write(directory / "episodes/episode_0000.json", episode)},
               "dispositions": {"completed": 1, "failed": 0, "unstarted": 0},
               "native_db_component_counts": [{"domain": "retail", "variant": "reference", "db_match": True, "count": 1}],
               "action_field_counts": [{"domain": "retail", "variant": "reference", "status": "satisfied", "count": 1}]}
    write(directory / "summary.json", summary)
    return directory, hashed, protocol, summary


def check_tau(root, fixture):
    directory, hashed, *_ = fixture
    return audit.audit_tau(audit.Audit(root, [f"C:/historical/upstream={root / 'upstream'}"]), directory,
                           expected_cells=1, expected_captures=1, expected_protocol_hash=hashed)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../b", "a//b", "a/./b", "a\\b", "C:/secret", "", "."])
def test_rejects_artifact_path_escape(name):
    with pytest.raises(ValueError):
        audit.relative_name(name)


@pytest.mark.parametrize("blob", [b'{"same":1,"same":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_rejects_ambiguous_json(blob):
    with pytest.raises(ValueError):
        audit.decode(blob)


def test_relocation_requires_explicit_prefix_and_uses_most_specific(tmp_path):
    runner = audit.Audit(tmp_path, [f"C:/old={tmp_path / 'all'}", f"C:/old/deps={tmp_path / 'dependencies'}"])
    assert runner.relocate("c:\\OLD\\deps\\module.py") == tmp_path / "dependencies/module.py"
    with pytest.raises(ValueError, match="Missing explicit"):
        runner.relocate("C:/older/module.py")
    with pytest.raises(ValueError):
        runner.relocate("C:/old/../escape")


@pytest.mark.parametrize("mappings", [["missing-separator"], ["=missing"], ["C:/x="], ["C:/x=.", "c:/X=."]])
def test_relocation_rejects_ambiguous_mapping(tmp_path, mappings):
    with pytest.raises(ValueError):
        audit.Audit(tmp_path, mappings)


def test_pinned_git_fallback_checks_historical_bytes(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = tmp_path / "source.py"
    source.write_bytes(b"original source\n")
    expected = audit.digest(source.read_bytes())
    subprocess.run(["git", "-C", str(tmp_path), "add", "source.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Audit Test", "-c", "user.email=audit@example.invalid",
                    "commit", "-qm", "fixture"], check=True)
    revision = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    source.write_bytes(b"later working source\n")
    runner = audit.Audit(tmp_path)
    runner.historical_code("source.py", expected, revision)
    assert runner.git_blobs == 1
    assert source.read_bytes() == b"later working source\n"
    with pytest.raises(ValueError, match="Pinned Git source"):
        runner.historical_code("source.py", "0" * 64, revision)


def test_bound_dependency_change_is_fatal(tmp_path):
    dependency = tmp_path / "module.py"
    dependency.write_bytes(b"original\n")
    bindings = {"C:/dependency/module.py": audit.digest(dependency.read_bytes())}
    dependency.write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="Bound file bytes"):
        audit.Audit(tmp_path, [f"C:/dependency={tmp_path}"]).absolute_bindings(bindings)


def test_judge_recounts_unassessable_origin_separately(tmp_path):
    result = check_judge(tmp_path, judge_fixture(tmp_path))
    assert result["completed"] == result["attempted_calls"] == 1
    origin = result["summary"]["methods"]["local_trace_judge"]["origin"]
    assert origin["all_definite_outputs"] == origin["claims_with_unassessable_gold"] == 1
    assert origin["claims"] == 0 and origin["claim_error"]["value"] is None


@pytest.mark.parametrize("mutation", ["active", "torn", "chain", "omitted", "extra", "nested_extra", "input", "response", "protocol"])
def test_judge_detects_inventory_and_byte_corruption(tmp_path, mutation):
    fixture = judge_fixture(tmp_path)
    directory, _, _, _ = fixture
    if mutation == "active":
        (directory / "runner.lock").write_text("active")
    elif mutation in ("torn", "chain"):
        path = directory / "request-journal.jsonl"
        blob = path.read_bytes()
        path.write_bytes(blob[:-1] if mutation == "torn" else blob.replace(b'"run_started"', b'"run_changed"'))
    elif mutation == "omitted":
        (directory / "calls/response.json").unlink()
    elif mutation == "extra":
        write(directory / "calls/extra.json", {})
    elif mutation == "nested_extra":
        write(directory / "calls/nested/extra.json", {})
    else:
        path = directory / {"input": "inputs/input.json", "response": "calls/response.json", "protocol": "protocol.json"}[mutation]
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((ValueError, OSError)):
        check_judge(tmp_path, fixture)


@pytest.mark.parametrize("mutation", ["wrong_order", "wrong_seed", "raw_disagrees", "truncated", "duplicate_slot"])
def test_judge_checks_accounting_after_valid_rehash(tmp_path, mutation):
    fixture = judge_fixture(tmp_path)
    directory, _, events, _ = fixture
    if mutation == "wrong_order":
        events[2]["event"] = "chat_received"
    elif mutation == "truncated":
        events[3]["truncated"] = True
    elif mutation == "duplicate_slot":
        events[4]["slot_id"] = "another_slot"
    elif mutation == "wrong_seed":
        path = directory / events[2]["request_file"]
        request = audit.decode(path.read_bytes())
        request["options"]["seed"] = 12
        events[2]["request_sha256"] = write(path, request)
    else:
        path = directory / "judgments/episode_00000/receipt.json"
        receipt = audit.decode(path.read_bytes())
        receipt["prediction"]["state"] = False
        events[4]["receipt_sha256"] = write(path, receipt)
    journal(directory, events)
    with pytest.raises(ValueError):
        check_judge(tmp_path, fixture)


@pytest.mark.parametrize("mutation", [None, "wrong_summary", "wrong_receipt", "wrong_stratum", "not_final"])
def test_judge_analysis_is_recounted_despite_matching_manifest_hash(tmp_path, mutation):
    fixture = judge_fixture(tmp_path)
    directory, hashed, _, protocol = fixture
    result = check_judge(tmp_path, fixture)
    analysis = tmp_path / "analysis"
    receipt = audit.decode((directory / "judgments/episode_00000/receipt.json").read_bytes())
    saved = {"final": True, "collection_state": "completed", "protocol_sha256": hashed,
             "attempted_calls_including_partial": 1,
             "journal_sha256": audit.digest((directory / "request-journal.jsonl").read_bytes()),
             "summary": result["summary"], "receipts": [receipt],
             "strata": {"model": {json.dumps({"model": protocol["schedule"][0]["slot"]["model"]}, sort_keys=True):
                                  json.loads(json.dumps(result["summary"]))}}}
    if mutation == "wrong_summary":
        saved["summary"]["methods"]["local_trace_judge"]["state"]["wrong_claims"] = 1
    elif mutation == "wrong_receipt":
        saved["receipts"][0]["prediction"]["state"] = False
    elif mutation == "wrong_stratum":
        saved["strata"]["model"].clear()
    elif mutation == "not_final":
        saved["final"] = False
    file_hash = write(analysis / "analysis.json", saved)
    write(analysis / "manifest.json", {"files": {"analysis.json": file_hash}})
    arguments = {"expected_slots": 1, "expected_protocol_hash": hashed}
    if mutation is None:
        assert audit.audit_judge(audit.Audit(tmp_path), directory, analysis, **arguments)["completed"] == 1
    else:
        with pytest.raises(ValueError):
            audit.audit_judge(audit.Audit(tmp_path), directory, analysis, **arguments)


@pytest.mark.parametrize("mutation", ["done", "length", "tool", "extra_key", "bad_label"])
def test_raw_judge_prediction_requires_complete_schema(mutation):
    envelope = {"done": True, "message": {"role": "assistant", "content": json.dumps({
        "state": "satisfied", "action_linked": "unknown", "origin": "unknown"})}}
    if mutation == "done":
        envelope["done"] = False
    elif mutation == "length":
        envelope["done_reason"] = "length"
    elif mutation == "tool":
        envelope["message"]["tool_calls"] = [{}]
    else:
        content = json.loads(envelope["message"]["content"])
        content["extra" if mutation == "extra_key" else "state"] = "unsupported"
        envelope["message"]["content"] = json.dumps(content)
    with pytest.raises(ValueError):
        audit.parse_prediction(envelope)


def test_tau_recounts_captures_and_distinguishes_executed_calls(tmp_path):
    result = check_tau(tmp_path, tau_fixture(tmp_path))
    assert result["completed_cells"] == result["captures"] == result["withheld_unknown"] == 1
    assert result["native_call_records"] == 2 and result["native_calls_executed"] == 1


@pytest.mark.parametrize("mutation", ["active", "missing", "extra", "raw_bytes", "upstream_bytes", "start_slot"])
def test_tau_detects_file_and_start_corruption(tmp_path, mutation):
    fixture = tau_fixture(tmp_path)
    directory = fixture[0]
    if mutation == "active":
        (directory / "runner.lock").write_text("active")
    elif mutation == "missing":
        (directory / "episodes/episode_0000.json").unlink()
    elif mutation == "extra":
        write(directory / "episodes/episode_0001.json", {})
    elif mutation == "raw_bytes":
        path = directory / "episodes/episode_0000.json"
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "upstream_bytes":
        (tmp_path / "upstream/source.py").write_bytes(b"changed\n")
    else:
        path = directory / "started/episode_0000.json"
        start = audit.decode(path.read_bytes())
        start["source_index"] = 1
        write(path, start)
    with pytest.raises((ValueError, OSError)):
        check_tau(tmp_path, fixture)


@pytest.mark.parametrize("mutation", ["disposition", "count", "upstream", "withheld", "origin", "status", "model_calls", "task_hash"])
def test_tau_checks_accounting_after_valid_rehash(tmp_path, mutation):
    fixture = tau_fixture(tmp_path)
    directory, _, _, summary = fixture
    path = directory / "episodes/episode_0000.json"
    episode = audit.decode(path.read_bytes())
    if mutation == "disposition":
        summary["dispositions"]["unstarted"] = 1
    elif mutation == "count":
        summary["action_field_counts"][0]["count"] = 2
    elif mutation == "upstream":
        summary["upstream_commit"] = "d" * 40
    elif mutation == "model_calls":
        episode["model_calls"] = 1
    elif mutation == "task_hash":
        episode["source_task_sha256"] = "f" * 64
    elif mutation == "withheld":
        episode["action_audits"][0]["withheld_status"] = "satisfied"
    else:
        verification = episode["action_audits"][0]["trace"]["verifications"][0]
        verification[mutation] = "confirmed" if mutation == "origin" else "unsupported"
    summary["files"]["episodes/episode_0000.json"] = write(path, episode)
    write(directory / "summary.json", summary)
    with pytest.raises(ValueError):
        check_tau(tmp_path, fixture)


def test_manifest_fraction_arithmetic_is_checked_after_valid_hash(tmp_path):
    fractions = [{"numerator": 1, "denominator": 2, "value": 1.0}]
    hashed = write(tmp_path / "fractions.json", fractions)
    write(tmp_path / "manifest.json", {"files": {"fractions.json": hashed}})
    with pytest.raises(ValueError, match="fraction arithmetic"):
        audit.verify_manifest(audit.Audit(tmp_path), tmp_path / "manifest.json")


@pytest.mark.parametrize("name", ["private/mapping.json", "../escape.json"])
def test_review_pack_rejects_private_mapping_or_escape_even_with_matching_archive_hash(tmp_path, name):
    archive = tmp_path / "review.zip"
    data = b"{}"
    with zipfile.ZipFile(archive, "w") as members:
        members.writestr(name, data)
        members.writestr("manifest.json", audit.encoded({"files": {name: {"bytes": len(data), "sha256": audit.digest(data)}}}))
    receipt = {"archive": "review.zip", "archive_sha256": audit.digest(archive.read_bytes()),
               "archive_bytes": archive.stat().st_size, "archive_members": 2}
    write(tmp_path / "receipt.json", receipt)
    with pytest.raises(ValueError):
        audit.audit_review_pack(audit.Audit(tmp_path), tmp_path / "receipt.json")


def test_cli_refuses_overwrite_before_study_reads(tmp_path):
    output = tmp_path / "audit"
    output.mkdir()
    (output / "keep.txt").write_text("preserved")
    with pytest.raises(ValueError, match="fresh"):
        audit.main(["--root", str(tmp_path), "--output", str(output)])
    assert (output / "keep.txt").read_text() == "preserved"
