"""Postcollection figure checks use explicitly synthetic layout data only."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_matched_study_figures as figures


def write(path, data):
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def rate(n, d):
    return {"numerator": n, "denominator": d, "value": n/d if d else None}


def summary(rows, planned):
    result = {}
    for method in figures.METHODS:
        result[method] = {}
        selected = [row for row in rows if row["method"] == method]
        for target in figures.TARGETS:
            eligible = [row for row in selected if row["gold"][target] is not None]
            claims = [row for row in eligible if row["prediction"][target] is not None]
            correct = sum(row["prediction"][target] == row["gold"][target] for row in claims)
            result[method][target] = {
                "completed": len(selected), "gold_assessable": len(eligible), "claims": len(claims),
                "correct_claims": correct, "wrong_claims": len(claims)-correct,
                "abstentions": len(eligible)-len(claims), "planned_episodes": planned,
                "coverage": rate(len(claims), len(eligible)), "claim_error": rate(len(claims)-correct, len(claims)),
                "correct_yield": rate(correct, len(eligible)), "full_planned_correct_yield": rate(correct, planned)}
    return result


def fixture_inputs(path, *, stopped=False):
    path.mkdir(parents=True, exist_ok=True)
    schedule, episodes, rows = [], [], []
    for model in ("fixture-qwen:4b", "fixture-llama:3b", "fixture-gemma:1b"):
        for profile in ("refund-policy-v1", "refund-policy-v2"):
            for case in range(2):
                slot = {"slot_id": f"fixture_{len(schedule):04d}", "model": model,
                        "prompt_version": profile, "case_id": f"fixture-case-{case}", "repetition": 0}
                schedule.append(slot)
                status = "interrupted_partial" if stopped and len(schedule) == 1 else "completed"
                episodes.append({"slot": slot, "status": status})
                if status != "completed":
                    continue
                gold = {"state": bool(case), "action_linked": bool(case)}
                for method in figures.METHODS:
                    prediction = ({target: None for target in figures.TARGETS} if method == "agent_self_report"
                                  else {"state": gold["state"], "action_linked": None}
                                  if method == "readback_state_only" else dict(gold))
                    rows.append({"slot": slot, "method": method, "gold": gold,
                                 "prediction": prediction, "action_selected": bool(case)})
    protocol = {"schema_version": "consequa-matched-local-study-v1", "planned_episodes": len(schedule),
                "schedule": schedule}
    protocol_path = path / "protocol.json"
    write(protocol_path, protocol)
    journal_path = path / "request-journal.jsonl"
    write(journal_path, {"event": "chat_started" if stopped else "run_stopped", "synthetic_fixture": True})
    status = {name: sum(receipt["status"] == name for receipt in episodes) for name in figures.STATUSES}
    strata, diagnostic_strata = {}, {}
    for key in sorted({figures.key_for(slot) for slot in schedule}):
        group = [receipt for receipt in episodes if figures.key_for(receipt["slot"]) == key]
        group_rows = [row for row in rows if figures.key_for(row["slot"]) == key]
        counts = Counter(receipt["status"] for receipt in group)
        strata[key] = {"planned_episodes": len(group), "episode_status": {name: counts[name] for name in figures.STATUSES},
                       "summary": summary(group_rows, len(group))}
        picked = sum(row["action_selected"] for row in group_rows if row["method"] == figures.METHODS[0])
        diagnostic_strata[key] = {"planned_episodes": len(group), "completed_episodes": counts["completed"],
                                  "action_selected_episodes": picked, "dispatched_episodes": picked,
                                  "rates": {f"{name}_per_{basis}": rate(picked, denominator)
                                            for name in ("action_selected", "dispatched")
                                            for basis, denominator in (("completed", counts["completed"]), ("planned", len(group)))}}
    analysis = {"schema_version": "consequa-matched-audit-analysis-v1", "synthetic_fixture": True,
                "protocol_sha256": figures.file_hash(protocol_path), "journal_sha256": figures.file_hash(journal_path),
                "planned_episodes": len(schedule), "episode_status": status, "episodes": episodes, "rows": rows,
                "summary": summary(rows, len(schedule)), "strata": {"model/prompt_version": strata}}
    analysis_path = path / "analysis.json"
    write(analysis_path, analysis)
    disposition = {"schema_version": "consequa-matched-study-disposition-v1", "final": True,
                   "no_active_runner": True, "collection_state": "stopped" if stopped else "completed",
                   "stopped_reason": "Synthetic interrupted-layout fixture" if stopped else "",
                   "analysis_sha256": figures.file_hash(analysis_path), "episode_status": status,
                   "protocol_sha256": analysis["protocol_sha256"], "journal_sha256": analysis["journal_sha256"]}
    disposition_path = path / "disposition.json"
    write(disposition_path, disposition)
    diagnostic = {"schema_version": "consequa-matched-execution-summary-v1",
                  "protocol_sha256": analysis["protocol_sha256"], "journal_sha256": analysis["journal_sha256"],
                  "analysis_sha256": figures.file_hash(analysis_path),
                  "episode_status": status, "strata": {"model/prompt_version": diagnostic_strata}}
    diagnostic_inventory = path / "input-inventory.json"
    write(diagnostic_inventory, {"synthetic_fixture": True})
    diagnostic["input_inventory_sha256"] = figures.file_hash(diagnostic_inventory)
    diagnostic_path = path / "execution-summary.json"
    write(diagnostic_path, diagnostic)
    return analysis_path, protocol_path, disposition_path, diagnostic_path


def rewrite_analysis(paths, mutate):
    value = figures.read_json(paths[0])
    mutate(value)
    write(paths[0], value)
    disposition = figures.read_json(paths[2])
    disposition["analysis_sha256"] = figures.file_hash(paths[0])
    write(paths[2], disposition)


def test_final_fixture_and_zero_claim_denominators(tmp_path):
    paths = fixture_inputs(tmp_path)
    inputs, _, _ = figures.validate_inputs(*paths)
    table = figures.plotted_rows(inputs)
    nulls = [row for row in table if row["method"] == "agent_self_report" and row["metric"] == "claim_error"]
    assert nulls and all(row["value"] is None and row["denominator"] == 0 for row in nulls)
    assert any(row["target"] == "episode_disposition" for row in table)


def test_ongoing_or_locked_data_are_refused(tmp_path):
    paths = fixture_inputs(tmp_path)
    disposition = figures.read_json(paths[2])
    disposition["final"] = False
    write(paths[2], disposition)
    with pytest.raises(ValueError, match="Final collection disposition"):
        figures.validate_inputs(*paths)
    disposition["final"] = True
    write(paths[2], disposition)
    (tmp_path / "runner.lock").write_text("fixture-active", encoding="utf-8")
    with pytest.raises(ValueError, match="runner lock"):
        figures.validate_inputs(*paths)


def test_interrupted_data_need_stopped_disclosure(tmp_path):
    paths = fixture_inputs(tmp_path, stopped=True)
    figures.validate_inputs(*paths)
    disposition = figures.read_json(paths[2])
    disposition["collection_state"] = "completed"
    write(paths[2], disposition)
    with pytest.raises(ValueError, match="unfinished slots"):
        figures.validate_inputs(*paths)
    disposition["collection_state"] = "stopped"
    disposition["stopped_reason"] = ""
    write(paths[2], disposition)
    with pytest.raises(ValueError, match="explicit reason"):
        figures.validate_inputs(*paths)


def test_changed_analysis_bytes_are_refused(tmp_path):
    paths = fixture_inputs(tmp_path)
    paths[0].write_bytes(paths[0].read_bytes() + b" ")
    with pytest.raises(ValueError, match="Analysis differs"):
        figures.validate_inputs(*paths)


def test_inconsistent_rate_denominators_are_refused(tmp_path):
    paths = fixture_inputs(tmp_path)
    rewrite_analysis(paths, lambda value: value["summary"]["consequa_state_origin"]["state"]["coverage"].update(denominator=999))
    with pytest.raises(ValueError, match="Fraction counts"):
        figures.validate_inputs(*paths)


def test_duplicate_auditor_row_cannot_inflate_coverage(tmp_path):
    paths = fixture_inputs(tmp_path)
    rewrite_analysis(paths, lambda value: value["rows"].append(value["rows"][0]))
    with pytest.raises(ValueError, match="exactly one row"):
        figures.validate_inputs(*paths)


def test_diagnostic_selection_must_match_retained_analysis(tmp_path):
    paths = fixture_inputs(tmp_path)
    diagnostic = figures.read_json(paths[3])
    group = next(iter(diagnostic["strata"]["model/prompt_version"].values()))
    group["action_selected_episodes"] = 2
    write(paths[3], diagnostic)
    with pytest.raises(ValueError, match="selection/dispatch"):
        figures.validate_inputs(*paths)


def test_vector_fixture_exports_and_exact_fraction_tables(tmp_path):
    pytest.importorskip("matplotlib")
    paths = fixture_inputs(tmp_path / "synthetic-input")
    out = tmp_path / "synthetic-output"
    result = figures.build(*paths[:3], out, paths[3])
    assert result["planned_episodes"] == 12
    inventory = figures.read_json(out / "figure-inventory.json")
    assert inventory["synthetic_fixture"] is True
    for stem in result["figures"]:
        assert (out / f"{stem}.pdf").read_bytes().startswith(b"%PDF")
        assert "SYNTHETIC LAYOUT FIXTURE" in (out / f"{stem}.svg").read_text(encoding="utf-8")
    assert "N/A (0 denom.)" in (out / "matched-baseline-metrics.svg").read_text(encoding="utf-8")
    assert "numerator,denominator,value" in (out / "figure-fractions.csv").read_text(encoding="utf-8")
    assert all(sha256((out / name).read_bytes()).hexdigest() == digest for name, digest in inventory["files"].items())
    with pytest.raises(FileExistsError):
        figures.build(*paths[:3], out, paths[3])
