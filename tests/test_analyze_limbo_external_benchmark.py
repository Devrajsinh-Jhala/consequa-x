"""Synthetic analysis fixtures live only in pytest temporary directories."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from research.limbo_agent.protocol import make_schedule
from scripts import analyze_limbo_external_benchmark as analysis


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture(scope="module")
def base_fixture(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("limbo-analysis-synthetic-base")
    repo = tmp_path / "synthetic-analysis-fixture"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Synthetic Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "core.autocrlf", "false")
    (repo / "frozen.py").write_text("# Synthetic frozen source, never a measured result.\n", encoding="utf-8")
    metadata = []
    domains = ("billing", "data", "deploy", "mail", "social", "tickets")
    for index in range(12):
        domain = domains[index % 6]
        metadata.append({"template": f"synthetic_template_{index:02d}", "index": 20000 + index,
            "family": "synthetic-family-" + domain, "domains": [domain], "focals": [{
                "label": "synthetic_write", "tool": "invented.write", "domain": domain,
                "batch": index == 1, "verification": "public", "idempotency": "native",
                "reversible": True}]})
    protocol = {"schema": "conseqax-limbo-protocol-v1", "native": {"commit": analysis.PIN},
        "sources": {"frozen.py": analysis.binding(repo / "frozen.py")}, "metadata": metadata,
        "seed": 1701, "arms": list(analysis.ARMS), "runtime_binding": {"model": "synthetic-no-model"},
        "schedule": make_schedule(metadata, world_count=24, model="synthetic-no-model", max_tool_calls=16)}
    protocol_path = repo / "protocol.json"
    write_json(protocol_path, protocol)
    git(repo, "add", "frozen.py", "protocol.json")
    git(repo, "commit", "-qm", "Synthetic fixture only")
    commit = git(repo, "rev-parse", "HEAD")
    rows = []
    for planned in protocol["schedule"]:
        rank, arm = planned["world_rank"], planned["arm"]
        success = rank % 2 == 0 if arm == "vanilla" else True
        rows.append({"slot": planned["slot"], "world_rank": rank, "arm": arm,
            "started": True, "operational": True, "audit_complete": True,
            "grade_available": True, "execution_success": True,
            "status": "audited_native_return", "native_error": None, "native_stop_reason": "done",
            "native_grade": {"TS": success, "EOS": success, "clean_success": success,
                "exact_state": success, "dup_executed": 0, "dup_live": 0, "dup_compensated": 0,
                "extraneous_writes": 0, "n_effects": 1, "collateral": []},
            "fault_triggered": planned["metadata"]["mode"] != "none",
            "work": {"execute": 3, "verify": 2, "advance": 7, "flush": 1},
            "work_charges": {"native_tool_events": 3, "public_verify_attempts": 2,
                "outer_wait_attempts": 2, "outer_virtual_wait_seconds": 10.0,
                "flush_attempts": 1, "boundary_enter_counts_are_not_physical_effect_counts": True},
            "model_invocations": 2, "model_completions": 2, "model_dispatches": 2,
            "model_cap_refusals": 0, "receipt_count": 2 if arm == "conseqax_guard" else 0,
            "package_same_native_guard_replay": arm == "conseqax_guard", "wall_s": 12.5,
            "virtual_seconds": 15.0,
            "usage": {key: {"observed_prefix_total": 20 if key == "input_tokens" else 4,
                "unknown_invocations": 0, "complete_for_all_invocations": True} for key in analysis.USAGE}})
    audit = {"schema": "conseqax-limbo-audit-v1", "passed": True,
        "protocol_commit": commit, "protocol": analysis.binding(protocol_path),
        "collection_manifest": {"sha256": "a" * 64, "bytes": 1234}, "rows": rows,
        "summary": {"deliberately_untrusted_convenience_summary": "must not be used"},
        "scope": {"independent_native_policy_and_effect_replay": True,
            "conseqax_guard_replayed_as_declared_native_guard": True,
            "SDK_receipt_current_public_report_mapping_recomputation": True,
            "saved_context_render_token_proof_consistency": True,
            "SDK_execution_or_independent_service_verifier_replay": False,
            "independent_tokenizer_reconstruction": False,
            "passed_means_all_slots_operational_or_successful": False,
            "human_or_network_used": False}}
    audit_dir = repo / "audit"
    audit_dir.mkdir()
    audit_path = audit_dir / "audit-result.json"
    def seal():
        write_json(audit_path, audit)
        write_json(audit_dir / "manifest.json", {"audit-result.json": analysis.binding(audit_path)})
    seal()
    return {"repo": repo, "protocol": protocol, "protocol_path": protocol_path, "commit": commit,
            "audit": audit, "audit_path": audit_path, "seal": seal}


@pytest.fixture
def fixture(base_fixture, tmp_path):
    repo = tmp_path / "synthetic-analysis-fixture"
    shutil.copytree(base_fixture["repo"], repo)
    protocol_path = repo / "protocol.json"
    audit_path = repo / "audit/audit-result.json"
    protocol, audit = analysis.load(protocol_path), analysis.load(audit_path)
    def seal():
        write_json(audit_path, audit)
        write_json(audit_path.parent / "manifest.json", {"audit-result.json": analysis.binding(audit_path)})
    return {"repo": repo, "protocol": protocol, "protocol_path": protocol_path,
            "commit": base_fixture["commit"], "audit": audit, "audit_path": audit_path, "seal": seal}


def validate(fixture):
    return analysis.validate_inputs(fixture["audit_path"], fixture["protocol_path"], fixture["commit"])


def test_independent_schedule_matches_registered_selection(fixture):
    protocol, audit, inputs = validate(fixture)
    assert analysis.registered_schedule(protocol) == protocol["schedule"]
    result = analysis.analyze(protocol, audit, inputs)
    assert (result["planned_slots"], result["planned_worlds"], result["base_instances"]) == (96, 24, 12)
    assert result["arms"]["vanilla"]["endpoints"]["EOS"]["true_audited"] == 12
    assert result["arms"]["guard"]["endpoints"]["EOS"]["true_audited"] == 24
    assert len(result["matched_contrasts"]) == 6
    assert len(result["strata"]["template"]) == 12
    assert len(result["strata"]["domain"]) == 6
    assert len(result["strata"]["mode"]) == 7
    assert all(row["arms"]["guard"]["planned"] == 2 for row in result["strata"]["template"].values())
    pair = result["matched_contrasts"]["vanilla__vs__guard"]["endpoints"]["EOS"]
    assert pair["all_planned_numerator_difference_left_minus_right"] == -12
    assert pair["right_only_true_among_both_available"] == 12
    assert pair["both_grades_available"] == 24
    costs = result["matched_contrasts"]["vanilla__vs__guard"]["paired_cost_differences"]
    assert costs["outer_wait_attempts"]["observed_sum_left_minus_right"] == 0
    assert costs["model_dispatches"]["both_accounting_available"] == 24


def unavailable(row, *, started):
    row.clear()
    row.update(started=started, operational=False, audit_complete=False, grade_available=False,
               execution_success=False, native_grade=None,
               status="child_failed" if started else "unstarted_integrity_stop")


def test_unavailable_and_error_return_remain_distinct_with_fixed_denominator(fixture):
    rows = fixture["audit"]["rows"]
    guard = [row for row in rows if row["arm"] == "guard"]
    first, second = guard[:2]
    identities = [{key: row[key] for key in ("slot", "world_rank", "arm")} for row in (first, second)]
    unavailable(first, started=False)
    first.update(identities[0])
    unavailable(second, started=True)
    second.update(identities[1])
    second["observed_journal_prefix"] = {"unquantified_work": 999999}
    guard[2].update(execution_success=False, status="audited_native_error_return",
                    native_error="LLMError: synthetic terminal error", native_stop_reason="llm_error")
    fixture["seal"]()
    protocol, audit, inputs = validate(fixture)
    result = analysis.analyze(protocol, audit, inputs)
    summary = result["arms"]["guard"]
    assert summary["planned"] == 24 and summary["grade_unavailable"] == 2
    assert summary["audited_native_error_returns"] == 1
    assert summary["execution_success"] == 21
    assert summary["endpoints"]["EOS"]["true_audited"] == 22
    assert summary["endpoints"]["EOS"]["false_audited"] == 0
    assert summary["endpoints"]["EOS"]["all_planned_success_fraction"] == 22 / 24
    assert summary["costs"]["model_dispatches"]["observed_total"] == 44
    assert summary["costs"]["model_dispatches"]["rows_unavailable"] == 2
    assert summary["costs"]["model_dispatches"]["complete_for_all_planned_slots"] is False
    pair = result["matched_contrasts"]["guard__vs__conseqax_guard"]["endpoints"]["EOS"]
    assert pair["all_planned_numerator_difference_left_minus_right"] == -2
    assert pair["at_least_one_grade_unavailable"] == 2
    assert pair["same_boolean_among_both_available"] == 22
    assert result["worlds"][0]["arms"]["guard"]["EOS"] is None


def test_cost_waits_usage_availability_and_cached_input_are_not_conflated(fixture):
    row = next(row for row in fixture["audit"]["rows"] if row["arm"] == "vanilla")
    row["usage"]["output_tokens"].update(observed_prefix_total=3, unknown_invocations=1,
                                          complete_for_all_invocations=False)
    fixture["seal"]()
    protocol, audit, inputs = validate(fixture)
    summary = analysis.analyze(protocol, audit, inputs)["arms"]["vanilla"]
    assert summary["costs"]["boundary_advance_attempts"]["observed_total"] == 168
    assert summary["costs"]["outer_wait_attempts"]["observed_total"] == 48
    assert summary["costs"]["outer_virtual_wait_seconds"]["observed_total"] == 240
    assert summary["costs"]["boundary_execute_attempts"]["observed_total"] == 72
    assert summary["native_effects"]["n_effects"]["observed_total"] == 24
    assert summary["usage"]["input_tokens"]["observed_token_total"] == 480
    assert summary["usage"]["cached_tokens"]["observed_token_total"] == 96
    usage = summary["usage"]["output_tokens"]
    assert usage["observed_token_total"] == 95
    assert usage["unknown_invocations_among_audited_rows"] == 1
    assert usage["known_invocations_among_audited_rows"] == 47
    assert usage["complete_for_all_planned_slots"] is False


@pytest.mark.parametrize("mutation,match", [
    (lambda audit: audit.update(passed=False), "passed official"),
    (lambda audit: audit.update(schema="conseqax-limbo-development-audit-v1"), "passed official"),
    (lambda audit: audit.update(protocol_commit="b" * 40), "binding differs"),
    (lambda audit: audit["rows"].pop(), "omits planned"),
    (lambda audit: audit["rows"].__setitem__(1, copy.deepcopy(audit["rows"][0])), "identity/order"),
    (lambda audit: audit["rows"][0].update(slot=True), "identity/order"),
    (lambda audit: audit["rows"][0]["native_grade"].update(TS=1), "not boolean"),
    (lambda audit: audit["rows"][0]["native_grade"].update(EOS=False), "EOS definition"),
    (lambda audit: audit["rows"][0].update(grade_available=False), "flags disagree"),
    (lambda audit: audit["rows"][0].update(native_error="LLMError: fixture"), "Execution success disagrees"),
    (lambda audit: audit["rows"][0].update(native_stop_reason="llm_error"), "Execution success disagrees"),
    (lambda audit: audit["rows"][0].update(model_dispatches=3), "counts disagree"),
    (lambda audit: audit["rows"][0]["usage"]["input_tokens"].update(unknown_invocations=1), "availability flag"),
    (lambda audit: audit["rows"][0]["usage"]["input_tokens"].update(observed_prefix_total=-1), "negative"),
    (lambda audit: audit["scope"].update(human_or_network_used=True), "non-claim differs"),
    (lambda audit: audit.update(collection_manifest={"sha256": "x", "bytes": 2}), "manifest binding"),
])
def test_rejects_corrupt_semantics_even_if_resealed(fixture, mutation, match):
    mutation(fixture["audit"])
    fixture["seal"]()
    with pytest.raises(ValueError, match=match):
        validate(fixture)


def test_missing_grade_cannot_be_replaced_by_false(fixture):
    row = fixture["audit"]["rows"][0]
    row.update(operational=False, grade_available=False, audit_complete=False, execution_success=False)
    fixture["seal"]()
    with pytest.raises(ValueError, match="replaced by a value"):
        validate(fixture)


def test_unsealed_or_extra_audit_file_is_rejected(fixture):
    fixture["audit_path"].write_bytes(fixture["audit_path"].read_bytes() + b" ")
    with pytest.raises(ValueError, match="sealed manifest"):
        validate(fixture)
    fixture["seal"]()
    (fixture["audit_path"].parent / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        validate(fixture)


def test_protocol_requires_exact_commit_bytes_and_source_binding(fixture):
    with pytest.raises(ValueError, match="40-character"):
        analysis.validate_inputs(fixture["audit_path"], fixture["protocol_path"], "main")
    original = fixture["protocol_path"].read_bytes()
    fixture["protocol_path"].write_bytes(original + b" ")
    with pytest.raises(ValueError, match="explicit Git commit"):
        validate(fixture)
    fixture["protocol_path"].write_bytes(original)
    fixture["protocol"]["sources"]["frozen.py"]["sha256"] = "0" * 64
    write_json(fixture["protocol_path"], fixture["protocol"])
    git(fixture["repo"], "add", "protocol.json")
    git(fixture["repo"], "commit", "-qm", "Synthetic invalid source binding")
    fixture["commit"] = git(fixture["repo"], "rev-parse", "HEAD")
    fixture["audit"].update(protocol_commit=fixture["commit"], protocol=analysis.binding(fixture["protocol_path"]))
    fixture["seal"]()
    with pytest.raises(ValueError, match="Scientific source differs"):
        validate(fixture)


def test_rejects_recommitted_schedule_change(fixture):
    fixture["protocol"]["schedule"][0]["spec"]["index"] += 1
    write_json(fixture["protocol_path"], fixture["protocol"])
    git(fixture["repo"], "add", "protocol.json")
    git(fixture["repo"], "commit", "-qm", "Synthetic changed task")
    fixture["commit"] = git(fixture["repo"], "rev-parse", "HEAD")
    fixture["audit"].update(protocol_commit=fixture["commit"], protocol=analysis.binding(fixture["protocol_path"]))
    fixture["seal"]()
    with pytest.raises(ValueError, match="registered selection"):
        validate(fixture)


def test_output_provenance_and_counts_are_sealed_without_overwrite(fixture, tmp_path):
    output = tmp_path / "synthetic-output"
    result = analysis.run(fixture["audit_path"], fixture["protocol_path"], fixture["commit"], output,
                          make_figures=False)
    assert result["figures_generated"] is False
    assert result["figures"] == []
    manifest = analysis.load(output / "manifest.json")
    assert all(analysis.binding(output / name) == value for name, value in manifest.items())
    assert (output / "inputs/audit-result.json").read_bytes() == fixture["audit_path"].read_bytes()
    assert "12/24" in (output / "results.md").read_text(encoding="utf-8")
    assert "Vanilla & 24 & 24 & 12 & 12 & 0" in (output / "results.tex").read_text(encoding="utf-8")
    narrative = (output / "narrative.md").read_text(encoding="utf-8")
    assert "native grades for 96/96 slots" in narrative
    assert "Vanilla: TS 12/24, EOS 12/24" in narrative
    assert "48 audited SDK receipts across 24/24 planned episodes" in narrative
    assert "24/24 matched worlds had both native grades available" in narrative
    assert "clean TS/EOS 12/12 and 12/12, assigned-fault TS/EOS 0/12 and 0/12" in narrative
    assert "does not independently re-execute the SDK" in narrative
    assert (output / "narrative.tex").exists()
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        analysis.run(fixture["audit_path"], fixture["protocol_path"], fixture["commit"], output,
                     make_figures=False)
    assert (output / "manifest.json").read_bytes() == before


def test_no_figures_or_outputs_before_validation(fixture, tmp_path, monkeypatch):
    fixture["audit"]["passed"] = False
    fixture["seal"]()
    calls = []
    monkeypatch.setattr(analysis, "plots", lambda *_args: calls.append("forbidden"))
    with pytest.raises(ValueError, match="passed official"):
        analysis.run(fixture["audit_path"], fixture["protocol_path"], fixture["commit"], tmp_path / "no-output")
    assert not calls and not (tmp_path / "no-output").exists()


def test_no_post_treatment_fault_trigger_selection(fixture):
    for row in fixture["audit"]["rows"]:
        row["fault_triggered"] = False
    fixture["seal"]()
    protocol, audit, inputs = validate(fixture)
    result = analysis.analyze(protocol, audit, inputs)
    assert len(result["strata"]["mode"]) == 7
    assert sum(group["arms"]["vanilla"]["planned"] for name, group in result["strata"]["mode"].items() if name != "none") == 12
    assert result["arms"]["vanilla"]["fault_triggered"] == {"true": 0, "false": 24, "unavailable": 0}


def test_duplicate_json_keys_are_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"passed":false,"passed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON"):
        analysis.load(path)


def test_narrative_retains_error_return_and_missing_accounting(fixture):
    row = next(row for row in fixture["audit"]["rows"] if row["arm"] == "guard")
    identity = {key: row[key] for key in ("slot", "world_rank", "arm")}
    unavailable(row, started=False)
    row.update(identity)
    error = next(row for row in fixture["audit"]["rows"] if row["arm"] == "conseqax_guard")
    error.update(execution_success=False, status="audited_native_error_return",
                 native_error="LLMError: fixture", native_stop_reason="llm_error")
    fixture["seal"]()
    protocol, audit, inputs = validate(fixture)
    paragraphs = analysis.narrative(analysis.analyze(protocol, audit, inputs))
    text = "\n".join(paragraphs)
    assert "native grades for 95/96 slots, including 1 native error returns" in text
    assert "Native guard: TS 23/24, EOS 23/24" in text
    assert "1/24 worlds had at least one unavailable grade" in text
    assert "Native guard: 69 execute attempts" in text
    assert "from 23/24 slots with complete accounting" in text
    assert "Incomplete slots may have additional unquantified work" in text


def test_tex_escape_uses_literal_character_mapping():
    assert analysis.tex_escape("A&B_50%") == r"A\&B\_50\%"


def test_plot_layout_and_sources_on_synthetic_data_without_writing_artifacts(fixture, tmp_path, monkeypatch):
    pytest.importorskip("matplotlib")
    pytest.importorskip("numpy")
    from matplotlib.figure import Figure
    rendered = []
    def render_only(figure, path, **_kwargs):
        figure.canvas.draw()
        rendered.append((Path(path).name, len(figure.axes)))
    monkeypatch.setattr(Figure, "savefig", render_only)
    protocol, audit, inputs = validate(fixture)
    result = analysis.analyze(protocol, audit, inputs)
    filenames = analysis.plots(result, tmp_path)
    assert len(filenames) == 9
    assert set(filenames) == {f"limbo-{name}.{extension}" for name in
                              ("outcomes", "stratification", "costs") for extension in ("pdf", "svg", "png")}
    assert [axes for name, axes in rendered if name.endswith(".pdf")] == [2, 2, 3]
    assert not any((tmp_path / name).exists() for name in filenames)
