"""Paper-helper checks use invented counts in memory and temporary prose only."""
from __future__ import annotations

import copy

import pytest

from scripts import build_final_limbo_paper as build
from scripts import prepare_final_limbo_manuscript as prepare


@pytest.fixture(scope="module")
def original_paper_sources():
    """The preparer consumes the pre-integration template, not today's paper."""
    commit = "8b25d4c7769c5c593333c9d3eeeceb8ae001dba4"
    preserved = prepare.ROOT / "output/limbo-followup-manuscript-stage-2026-10-24-v2/inputs/source/paper"
    sources = {}
    for name in ("conseqax-research.tex", "conseqax-research.md", "limbo-native-methods.tex"):
        committed = build.git(prepare.ROOT, "show", f"{commit}:paper/{name}")
        path = preserved / name
        data = path.read_bytes() if path.is_file() else committed
        assert data == committed, "Preserved preparer fixture differs from the immutable source: " + name
        sources[name] = data.decode("utf-8")
    return sources


@pytest.fixture
def cohorts(tmp_path, monkeypatch):
    def checked(alias, original):
        n = 6 if original else 96
        arms = {}
        audit_rows = []
        for index in range(96):
            arm = prepare.ARMS[index % 4]
            started = not original or index < 7
            available = index < n
            status = ("audited_native_return" if available else
                "interrupted_terminal_unavailable" if started else "unstarted_interruption")
            audit_rows.append({"arm": arm, "started": started, "operational": available,
                               "status": status})
        for arm in prepare.ARMS:
            selected = [row for row in audit_rows if row["arm"] == arm]
            available = sum(row["operational"] for row in selected)
            arms[arm] = {"started": sum(row["started"] for row in selected),
                "audited_grade_available": available, "audited_native_error_returns": 0,
                "execution_success": available, "grade_unavailable": 24 - available,
                "receipt_episodes_with_at_least_one": 0,
                "costs": {"receipt_count": {"observed_total": 0}},
                "native_effects": {key: {"observed_total": 0} for key in
                    ("dup_executed", "dup_live", "dup_compensated", "collateral_records", "extraneous_writes", "n_effects")},
                "usage": {key: {"observed_token_total": 0, "unknown_invocations_among_audited_rows": 0}
                          for key in ("input_tokens", "output_tokens")},
                "dispositions": dict(prepare.Counter(row["status"] for row in selected)),
                "endpoints": {key: {"true_audited": 0} for key in
                              ("TS", "EOS", "clean_success", "exact_state")}}
        protocol = {"metadata": [{"template": "invented"}], "seed": 1701,
            "limits": {"max_requests": 16, "max_output_tokens": 512, "request_timeout_s": 1200,
                "episode_timeout_s": 7200, "work": {"execute": 96, "verify": 64,
                    "wait": 64, "total_wait_seconds": 172800}},
            "sources": {"invented.py": {"sha256": "b" * 64, "bytes": 1}},
            "arms": list(prepare.ARMS), "native": {"commit": "c" * 40, "files": {"invented.py": "bound"}},
            "runtime_binding": {"model": alias, "model_blob_sha256": "d" * 64,
                                "context_tokens": 8192, "parallel_slots": 1},
            "environment": {"distributions": {"consequa-x": "2.1.1"}},
            "schedule": [{"slot": index, "spec": {"model": alias, "index": 20000, "max_tool_calls": 16}}
                         for index in range(96)]}
        if not original:
            protocol.update(execution_condition={"ollama_version": "0.40.10"}, prior_condition={
                "protocol_commit": "a" * 40, "protocol": {"sha256": "0" * 64, "bytes": 1},
                "partial_data_exposed_before_followup_freeze": True, "cohorts_pooled": False,
                "interrupted_analysis": {"sha256": "2" * 64, "bytes": 2}})
        audit = {"rows": audit_rows, "protocol": {"sha256": "0" * 64, "bytes": 1}}
        if original:
            audit["interrupted_collection"] = {"original_final_seal_unavailable": True}
        return {"protocol": protocol, "audit": audit, "result": {"arms": arms,
            "inputs": {"protocol_commit": "a" * 40 if original else "e" * 40}},
            "sealed": {"files": {"results.json": {"sha256": "2" * 64, "bytes": 2}}},
            "analyzer_binding": {"sha256": "f" * 64, "bytes": 1}}

    current, earlier = checked("invented-new-alias", False), checked("invented-old-alias", True)
    calls = []

    def validate(_root, directory, _protocol, commit, source_commit, *, require_figures=True):
        calls.append((directory.name, commit, source_commit, require_figures))
        return earlier if directory.name == "earlier" else current

    monkeypatch.setattr(build, "validate_analysis", validate)
    return current, earlier, calls, tmp_path


def validate(cohorts):
    _current, _earlier, _calls, root = cohorts
    return build.validate_cohorts(root, root / "current", root / "current.json", "e" * 40,
        root / "earlier", root / "earlier.json", "a" * 40, "1" * 40)


def test_both_cohorts_validated_and_only_alias_is_normalized(cohorts):
    current, earlier, calls, _root = cohorts
    before = copy.deepcopy(current["protocol"])
    assert validate(cohorts) == (current, earlier)
    assert calls == [("current", "e" * 40, "1" * 40, True),
                     ("earlier", "a" * 40, "1" * 40, False)]
    assert current["protocol"] == before


@pytest.mark.parametrize("change,match", [
    (lambda value: value["metadata"].append({"extra": True}), "metadata"),
    (lambda value: value.update(seed=1702), "seed"),
    (lambda value: value["limits"].update(max_requests=17), "limits"),
    (lambda value: value["sources"].clear(), "sources"),
    (lambda value: value["native"].update(commit="0" * 40), "native"),
    (lambda value: value["schedule"][0]["spec"].update(index=20001), "task indices"),
    (lambda value: value["runtime_binding"].update(model_blob_sha256="0" * 64), "weights"),
    (lambda value: value.pop("prior_condition"), "prospectively declare"),
    (lambda value: value["prior_condition"].update(partial_data_exposed_before_followup_freeze=False), "exact original cohort"),
    (lambda value: value["prior_condition"].update(protocol_commit="0" * 40), "exact original cohort"),
    (lambda value: value["execution_condition"].update(ollama_version="unknown"), "Ollama version"),
])
def test_scientific_or_undeclared_runtime_changes_fail(cohorts, change, match):
    change(cohorts[0]["protocol"])
    with pytest.raises(ValueError, match=match):
        validate(cohorts)


def test_original_interrupted_provenance_is_mandatory(cohorts):
    cohorts[1]["audit"].pop("interrupted_collection")
    with pytest.raises(ValueError, match="interrupted-collection"):
        validate(cohorts)


def test_both_denominators_and_unknowns_are_kept_in_table_and_prose(cohorts):
    current, earlier, *_ = cohorts
    rows = build.cohort_accounting_rows(current, earlier)
    assert len(rows) == 8 and sum(row[2] for row in rows[:4]) == 96
    assert sum(row[2] for row in rows[4:]) == 96
    assert sum(row[3] for row in rows[:4]) == 7
    assert sum(row[4] for row in rows[:4]) == 6
    assert sum(row[6] for row in rows[:4]) == 90
    table = build.cohort_accounting_tex(current, earlier)
    assert "no pooling" in table and "Original interrupted" in table
    prose = prepare.cohort_disclosures(current["result"], earlier)
    assert "6 independently replayed grades" in prose and "90 unavailable grades" in prose
    assert "interrupted_terminal_unavailable 1" in prose and "unstarted_interruption 89" in prose
    assert "not pooled" in prose


def test_methods_use_actual_runtime_and_retain_partial_data_exposure(cohorts, original_paper_sources):
    current, earlier, *_ = cohorts
    source = original_paper_sources["limbo-native-methods.tex"]
    text = prepare.final_methods(source, current["protocol"], "e" * 40,
                                 {"sha256": "2" * 64}, earlier)
    assert "version 0.40.10" in text and "Ollama 0.40.8 to 0.40.10" in text
    assert "after access to the partial original data" in text
    assert "original final collector seal and process terminal are unavailable" in text
    assert "12 unique base instances" in text
    prepare.reject_stale(text)


def test_full_manuscript_mirrors_both_cohorts_without_new_document(cohorts, tmp_path, original_paper_sources):
    current, earlier, *_ = cohorts
    (tmp_path / "narrative.md").write_text("\n\n".join("Invented test paragraph " + str(index) for index in range(7)),
                                           encoding="utf-8")
    methods = prepare.final_methods(original_paper_sources["limbo-native-methods.tex"],
        current["protocol"], "e" * 40, {"sha256": "2" * 64}, earlier)
    tex, md = prepare.assemble(original_paper_sources["conseqax-research.tex"],
        original_paper_sources["conseqax-research.md"], methods,
        current["result"], tmp_path, earlier)
    results_tex = prepare.native_results(current["result"], tmp_path, True, earlier)
    assert r"\input{limbo-cohort-accounting.tex}" in results_tex
    assert "Original interrupted" in md and "Follow-up" in md
    assert "6/96" in tex and "6/96" in md
    assert "Independent Researcher" in tex and "Independent Researcher" in md
    assert "does not introduce a new recovery" in tex
    for body in (tex, md, results_tex):
        prepare.reject_stale(body)
