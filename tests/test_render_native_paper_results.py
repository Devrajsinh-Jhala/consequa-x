"""Synthetic temporary audit fixtures only; never official scientific outputs.

No model, Git, network, native task/evaluator or PDF is used by these tests.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_paper_renderer",
    ROOT / "scripts/render_native_paper_results.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)
PROTOCOL_COMMIT = "a" * 40


def diagnostics(available=True):
    attempts = 2 if available else 0
    return {"model": {"attempted": attempts, "returned": attempts, "failed": 0, "pending": 0,
        "journal_call_accounting_valid": True, "http_generation_dispatch_records": attempts if available else None,
        "tokens": {name: {"sum_observed": attempts * tokens, "observed_responses": attempts,
                           "unavailable_attempts": 0}
                   for name, tokens in (("prompt_tokens", 10), ("completion_tokens", 3))}},
        "journal_availability": {name: {"available": available, "errors": []} for name in renderer.JOURNALS}}


def money():
    return {"assistant": {"messages": 2, "native_cost": 0.1, "sum_observed_cost": 0.1,
                           "unavailable_cost_messages": 0},
            "user": {"messages": 1, "native_cost": 0.2, "sum_observed_cost": 0.2,
                     "unavailable_cost_messages": 0}}


def unavailable(row, files, disposition="unstarted"):
    row.update(collection_disposition=disposition, operational_success=0, native_reward=None,
               native_component_outcomes=None, episode_audit_passed=None, normal_termination=None,
               diagnostics=diagnostics(False))
    files.pop(f"episode-audit-{row['slot']:03d}.json")


def manifest(directory):
    data = {"schema": "conseqax-native-offline-audit-artifacts-v1", "files": {
        path.relative_to(directory).as_posix(): renderer.sha256(path.read_bytes())
        for path in sorted(directory.rglob("*")) if path.is_file() and path.name != "manifest.json"}}
    (directory / "manifest.json").write_text(json.dumps(data), encoding="utf-8")


def fixture(tmp_path, mutate=None, mutate_result=None):
    directory = tmp_path / "synthetic-audit-fixture"
    directory.mkdir()
    rows, files = [], {}
    for task in range(12):
        for arm in renderer.ARMS[task % 4:] + renderer.ARMS[:task % 4]:
            slot = len(rows)
            reward = float(task % 2 == 0)
            outcomes = {"reward": reward, "reward_breakdown": {"DB": reward, "COMMUNICATE": 1.0}}
            row = {"slot": slot, "task_id": f"synthetic-only-{task}", "arm": arm,
                "nonempty_communication": task < 6, "collection_disposition": "worker_returned",
                "operational_success": int(reward), "required_task_basis": ["DB", "COMMUNICATE"],
                "native_reward": reward, "native_component_outcomes": outcomes,
                "episode_audit_passed": True, "normal_termination": True, "diagnostics": diagnostics()}
            rows.append(row)
            files[f"episode-audit-{slot:03d}.json"] = {"passed": True, "reward": deepcopy(outcomes),
                "normal_termination": True, "new_model_calls": 0, "network_attempts": 0, "message_costs": money()}
    if mutate:
        mutate(rows, files)
    for row in rows:
        files[f"slot-audit-{row['slot']:03d}.json"] = deepcopy(row)
    result = {"schema": "conseqax-native-offline-audit-v1", "passed": True,
        "fixture_notice": "SYNTHETIC TEMPORARY UNIT FIXTURE; NOT RESEARCH EVIDENCE",
        "new_model_calls": 0, "human_labels": 0, "network_attempts": 0,
        "protocol_anchor": {"protocol_commit": PROTOCOL_COMMIT,
                            "protocol_file_sha256": "b" * 64, "protocol_sha256": "c" * 64},
        "source_commit": "d" * 40, "collection_manifest_sha256": "e" * 64, "collection_bound_files": 1,
        "native_simulations_audited": sum(row["episode_audit_passed"] is True for row in rows),
        "all_slots_attempted": all(row["collection_disposition"] != "unstarted" for row in rows),
        "rows": rows, "summary": {"planned_slots": 999999, "groups": {"intentionally": "not trusted"}}}
    if mutate_result:
        mutate_result(result)
    files["audit-result.json"] = result
    for name, value in files.items():
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    manifest(directory)
    return directory / "audit-result.json"


def validate(path):
    contents, inputs = renderer.verify_inventory(path)
    result, rows, costs = renderer.validate_audit(contents, PROTOCOL_COMMIT)
    return renderer.summarize(rows, costs), rows, inputs


def test_counts_recomputed_from_rows_ignore_the_untrusted_summary_and_bind_full_inventory(tmp_path):
    path = fixture(tmp_path)
    summary, rows, inputs = validate(path)
    assert summary["distinct_task_ids"] == 12 and summary["planned_slots"] == 48
    assert len(rows) == 48 and len(inputs["files"]) == 97
    assert [group["operational_successes"] for group in summary["groups"] if group["stratum"] == "all"] == [6] * 4
    assert all(group["planned"] == 6 for group in summary["groups"] if group["stratum"] != "all")
    assert all(row["monetary"]["sum_observed_native_message_amounts"] == "3.6" for row in summary["resources"])


def test_unstarted_failure_and_premature_native_results_keep_distinct_denominators(tmp_path):
    def mutate(rows, files):
        unavailable(rows[0], files)
        unavailable(rows[1], files, "execution_failed")
        premature = rows[3]
        premature.update(native_reward=0.0, operational_success=0, normal_termination=False,
                         native_component_outcomes={"reward": 0.0, "reward_breakdown": None})
        files["episode-audit-003.json"].update(normal_termination=False, reward=deepcopy(premature["native_component_outcomes"]))
    path = fixture(tmp_path, mutate)
    summary, rows, _ = validate(path)
    groups = {group["arm"]: group for group in summary["groups"] if group["stratum"] == "all"}
    assert groups["B"]["native_reward_observed"] == 11
    assert groups["B"]["native_reward_unavailable"] == 1 and groups["B"]["dispositions"]["unstarted"] == 1
    assert groups["C"]["collection_failures"] == 1
    assert groups["G"]["premature_terminations"] == 1 and groups["G"]["native_reward_observed"] == 12
    assert rows[0]["native_reward"] is None and rows[3]["native_reward"] == 0.0


def test_missing_and_malformed_prefix_journals_are_not_zero_total_cost(tmp_path):
    def mutate(rows, files):
        unavailable(rows[0], files, "execution_failed")
        unavailable(rows[1], files, "execution_failed")
        prefix = rows[1]["diagnostics"] = diagnostics()
        prefix["journal_availability"]["model-calls"]["errors"] = [{"line": 4, "error": "synthetic truncated line"}]
        prefix["model"].update(returned=1, failed=0, pending=1)
        for token in prefix["model"]["tokens"].values():
            token.update(observed_responses=1, unavailable_attempts=1, sum_observed=7)
    summary, _, _ = validate(fixture(tmp_path, mutate))
    resources = {row["arm"]: row for row in summary["resources"]}
    assert resources["B"]["model_journals_missing"] == 1
    assert resources["B"]["model_journals_partial_or_missing"] == 1
    assert resources["B"]["http_record_slots_unavailable"] == 1
    assert resources["C"]["model_journals_malformed"] == 1
    assert resources["C"]["model_journals_with_pending_requests"] == 1
    assert resources["C"]["request_counts_observed"]["pending"] == 1
    assert resources["C"]["tokens"]["prompt_tokens"]["unavailable_attempts"] == 1


def test_native_null_costs_remain_unavailable_and_known_amounts_are_partial(tmp_path):
    def mutate(rows, files):
        files["episode-audit-000.json"]["message_costs"]["assistant"].update(
            native_cost=None, unavailable_cost_messages=1, sum_observed_cost=0.04)
    summary, _, _ = validate(fixture(tmp_path, mutate))
    cost = summary["resources"][0]["monetary"]
    assert cost["slots_with_complete_native_cost"] == 11
    assert cost["messages_unavailable_in_audited_episodes"] == 1
    assert cost["sum_observed_native_message_amounts"] == "3.54"


def test_audited_episode_cannot_retain_a_pending_model_request(tmp_path):
    def mutate(rows, files):
        model = rows[0]["diagnostics"]["model"]
        model.update(returned=1, pending=1)
        for token in model["tokens"].values():
            token.update(observed_responses=1, unavailable_attempts=1)
    with pytest.raises(ValueError, match="Audited episode has pending model requests"):
        validate(fixture(tmp_path, mutate))


@pytest.mark.parametrize("http_records", [None, 0, 1, 3])
def test_audited_episode_requires_known_http_dispatch_count_equal_to_attempts(tmp_path, http_records):
    def mutate(rows, files):
        rows[0]["diagnostics"]["model"]["http_generation_dispatch_records"] = http_records
    with pytest.raises(ValueError, match="HTTP dispatch count differs"):
        validate(fixture(tmp_path, mutate))


def test_normal_empty_criteria_requires_vacuous_communication_component(tmp_path):
    def mutate(rows, files):
        row = rows[24]
        assert row["nonempty_communication"] is False
        row.update(native_reward=0.0, operational_success=0,
                   native_component_outcomes={"reward": 0.0, "reward_breakdown": {"DB": 1.0, "COMMUNICATE": 0.0}})
        files["episode-audit-024.json"]["reward"] = deepcopy(row["native_component_outcomes"])
    with pytest.raises(ValueError, match="Empty communication criteria"):
        validate(fixture(tmp_path, mutate))


def test_all_unstarted_is_48_operational_zeros_and_48_unavailable_native_rewards(tmp_path):
    def mutate(rows, files):
        for row in rows:
            unavailable(row, files)
    summary, rows, _ = validate(fixture(tmp_path, mutate))
    assert all(row["native_reward"] is None for row in rows)
    for group in summary["groups"]:
        assert group["operational_successes"] == group["native_reward_observed"] == 0
        assert group["native_reward_unavailable"] == group["planned"]
    assert all(row["model_journals_missing"] == 12 for row in summary["resources"])


@pytest.mark.parametrize("field,value", [("schema", "other"), ("passed", False), ("passed", 1),
    ("new_model_calls", 1), ("human_labels", 1), ("network_attempts", 1)])
def test_refuses_failed_or_wrong_scope_audit(tmp_path, field, value):
    path = fixture(tmp_path, mutate_result=lambda result: result.update({field: value}))
    with pytest.raises(ValueError):
        validate(path)


@pytest.mark.parametrize("commit", ["main", "f" * 40])
def test_requires_caller_pinned_protocol_commit(tmp_path, commit):
    contents, _ = renderer.verify_inventory(fixture(tmp_path))
    with pytest.raises(ValueError, match="protocol commit"):
        renderer.validate_audit(contents, commit)


@pytest.mark.parametrize("change", ["tampered", "unbound", "deleted"])
def test_full_manifest_refuses_changed_unbound_or_absent_artifacts(tmp_path, change):
    path = fixture(tmp_path)
    target = path.parent / "slot-audit-000.json"
    if change == "tampered":
        target.write_text("{}", encoding="utf-8")
    elif change == "unbound":
        (path.parent / "unbound.json").write_text("{}", encoding="utf-8")
    else:
        target.unlink()
    with pytest.raises(ValueError, match="inventory|hash mismatch"):
        renderer.verify_inventory(path)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "stratum", "bool_stratum", "excluded", "bool_slot"])
def test_rejects_malformed_paired_matrix_even_with_rehashed_manifest(tmp_path, mutation):
    def mutate(rows, files):
        if mutation == "missing":
            rows.pop()
        elif mutation == "duplicate":
            rows[1]["arm"] = rows[0]["arm"]
        elif mutation == "stratum":
            for row in rows:
                if row["task_id"] == "synthetic-only-0":
                    row["nonempty_communication"] = False
        elif mutation == "bool_stratum":
            rows[0]["nonempty_communication"] = 1
        elif mutation == "excluded":
            rows[0]["task_id"] = "19"
        else:
            rows[0]["slot"] = False
    with pytest.raises(ValueError):
        validate(fixture(tmp_path, mutate))


def test_slot_artifact_must_match_result_row_even_when_both_hashes_are_valid(tmp_path):
    path = fixture(tmp_path)
    slot = path.parent / "slot-audit-000.json"
    data = json.loads(slot.read_text())
    data["collection_disposition"] = "execution_failed"
    slot.write_text(json.dumps(data), encoding="utf-8")
    manifest(path.parent)
    with pytest.raises(ValueError, match="bound slot-audit"):
        validate(path)


@pytest.mark.parametrize("mutation", ["tokens", "requests", "op", "reward", "cost", "required", "missing_field"])
def test_refuses_inconsistent_semantic_or_resource_counts(tmp_path, mutation):
    def mutate(rows, files):
        if mutation == "tokens":
            rows[0]["diagnostics"]["model"]["tokens"]["prompt_tokens"]["unavailable_attempts"] = 1
        elif mutation == "requests":
            rows[0]["diagnostics"]["model"]["attempted"] = 3
        elif mutation == "op":
            rows[0]["operational_success"] = 0
        elif mutation == "reward":
            rows[0]["native_reward"] = True
        elif mutation == "cost":
            files["episode-audit-000.json"]["message_costs"]["assistant"]["unavailable_cost_messages"] = 1
        elif mutation == "required":
            rows[0]["required_task_basis"] = ["DB", "NL_ASSERTION"]
        else:
            rows[0].pop("native_reward")
    with pytest.raises(ValueError):
        validate(fixture(tmp_path, mutate))


def test_strict_json_rejects_duplicate_keys_nonfinite_and_overflow_numbers():
    for value in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'):
        with pytest.raises(ValueError):
            renderer.strict_json(value)


def test_temporary_render_preserves_48_rows_limits_source_bytes_and_output_manifest(tmp_path):
    path = fixture(tmp_path)
    output = tmp_path / "synthetic-render-only"
    result = renderer.execute(path, output, PROTOCOL_COMMIT)
    assert result["planned_slots"] == 48
    receipt = json.loads((output / "source-receipt.json").read_text())
    assert len(receipt["all_planned_rows"]) == 48 and receipt["audit_summary_not_used"] is True
    assert receipt["input_audit"]["files"]["audit-result.json"]["sha256"] == renderer.sha256(path.read_bytes())
    assert (output / "renderer.source.py").read_bytes() == (ROOT / "scripts/render_native_paper_results.py").read_bytes()
    generated_manifest = json.loads((output / "manifest.json").read_text())
    assert set(generated_manifest["files"]) == {"results.md", "results.tex", "source-receipt.json", "renderer.source.py"}
    for name, digest in generated_manifest["files"].items():
        assert renderer.sha256((output / name).read_bytes()) == digest
    markdown = (output / "results.md").read_text()
    assert "not a semantic reward of zero" in markdown and "vacuously" in markdown
    assert "only when communication-component evaluation is reached" in markdown
    assert "Premature native stops retain the evaluator's returned reward zero" in markdown
    assert "same field predicate" in markdown and "full package receipt" in markdown
    assert "12 distinct, previously exposed" in markdown
    assert markdown.count("| synthetic-only-") == 48
    assert sum(f"| {index} | synthetic-only-" in markdown for index in range(48)) == 48
    tex = (output / "results.tex").read_text()
    assert r"\begin{table*}" in tex and "six nonempty and six empty" in tex
    assert "single protocol-declared fixed-seed run" in tex
    assert "Premature native stops retain reward zero and unavailable component grades" in tex
    with pytest.raises(ValueError, match="must be new"):
        renderer.execute(path, output, PROTOCOL_COMMIT)


def test_invalid_input_never_creates_output_directory(tmp_path):
    path = fixture(tmp_path, mutate_result=lambda result: result.update(passed=False))
    output = tmp_path / "not-created"
    with pytest.raises(ValueError):
        renderer.execute(path, output, PROTOCOL_COMMIT)
    assert not output.exists()


def test_output_cannot_be_nested_in_sealed_audit_input(tmp_path):
    path = fixture(tmp_path)
    with pytest.raises(ValueError, match="inside sealed audit"):
        renderer.execute(path, path.parent / "new-subdirectory", PROTOCOL_COMMIT)
    assert not (path.parent / "new-subdirectory").exists()
