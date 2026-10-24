"""Editorial checks use historical audited values only as non-published fixtures."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tested_editorial", ROOT / "scripts/finalize_limbo_editorial_sources.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
ANALYSIS = ROOT / "output/limbo-interrupted-analysis-2026-10-24"


@pytest.fixture(scope="module")
def original_paper_sources():
    """Keep the old preparer input stable after its output becomes the paper."""
    b = M.module(ROOT, M.BUILDER, "fixture_source_builder")
    commit = "8b25d4c7769c5c593333c9d3eeeceb8ae001dba4"
    preserved = ROOT / "output/limbo-followup-manuscript-stage-2026-10-24-v2/inputs/source/paper"
    sources = {}
    for name in ("conseqax-research.tex", "conseqax-research.md", "limbo-native-methods.tex"):
        committed = b.git(ROOT, "show", f"{commit}:paper/{name}")
        path = preserved / name
        data = path.read_bytes() if path.is_file() else committed
        assert data == committed, "Preserved preparer fixture differs from the immutable source: " + name
        sources[name] = data.decode("utf-8")
    return sources


@pytest.fixture()
def fixture(original_paper_sources):
    # No new benchmark outcome is generated, graded or written by these tests.
    b, p = M.module(ROOT, M.BUILDER, "fixture_builder"), M.module(ROOT, M.PREPARER, "fixture_preparer")
    result = b.load(ANALYSIS / "results.json")
    earlier = {"result": result}
    protocol = b.load(ROOT / "output/limbo-followup-protocol-2026-10-24/protocol.json")
    methods = p.final_methods(original_paper_sources["limbo-native-methods.tex"],
        protocol, "8b25d4c7769c5c593333c9d3eeeceb8ae001dba4",
        b.binding(ROOT / "output/limbo-followup-protocol-2026-10-24/protocol.json"), earlier)
    tex, md = p.assemble(original_paper_sources["conseqax-research.tex"],
        original_paper_sources["conseqax-research.md"], methods, result, ANALYSIS, earlier)
    return p, result, earlier, (tex, md, methods, p.native_results(result, ANALYSIS, True, earlier))


def test_actual_preparer_shape_and_frozen_counts_survive(fixture):
    p, result, earlier, original = fixture
    edited = M.edit_texts(p, result, earlier, ANALYSIS, *original)
    tex, md, methods, native = edited
    assert native.count(r"\caption{Follow-up runtime condition.") == 5
    assert md.count("![Follow-up runtime condition.") == 3
    assert "Assigned-condition results were " in native and "Assigned-condition results were " in md
    assert "Native guard minus Vanilla" in native and "Native guard minus SDK retry" in md
    assert "90 unavailable grades are not native failures" in native
    assert "separately scripted repeated-proposal fixture" in methods
    assert "No measured receipt activated" in tex
    assert "both native runtime conditions retain the 2.1.1" in md
    assert "detection does not repair all harmful effects" in tex
    for arm, label in zip(M.ARMS, M.LABELS):
        values = result["arms"][arm]["endpoints"]
        assert f"{label}: TS {values['TS']['true_audited']}/24, EOS {values['EOS']['true_audited']}/24" in md
    for name in ("limbo-results-table.tex", "limbo-outcomes.pdf", "limbo-stratification.pdf", "limbo-costs.pdf"):
        assert original[3].count(name) == native.count(name)


def test_positive_receipts_are_not_replaced_with_zero(fixture):
    _p, result, earlier, _original = fixture
    changed = deepcopy(result)
    package = changed["arms"]["conseqax_guard"]
    package["costs"]["receipt_count"]["observed_total"] = 9
    package["receipt_episodes_with_at_least_one"] = 3
    assert "9 audited receipts in 3/24 episodes" in M.abstract(changed, earlier)
    assert "No measured receipt" not in M.abstract(changed, earlier)
    assert "9 audited receipts in 3/24 planned SDK episodes" in M.readiness_text(changed)


@pytest.mark.parametrize("old,text", [("x", "x x"), ("x", "missing"), ("", "anything")])
def test_unexpected_or_duplicate_anchor_rejected(old, text):
    with pytest.raises(ValueError, match="exactly one"):
        M.once(text, old, "new")


@pytest.mark.parametrize("change", ["orientation", "difference", "availability"])
def test_resealed_inconsistent_contrast_rejected(fixture, change):
    _p, result, _earlier, _original = fixture
    pair = deepcopy(result)
    cell = pair["matched_contrasts"]["vanilla__vs__guard"]
    if change == "orientation":
        cell["left"] = "guard"
    elif change == "difference":
        cell["endpoints"]["TS"]["all_planned_numerator_difference_left_minus_right"] += 1
    else:
        cell["endpoints"]["TS"]["both_grades_available"] += 1
    with pytest.raises(ValueError):
        M.baseline_contrasts(pair)


def test_changed_staging_shape_rejected(fixture):
    p, result, earlier, original = fixture
    with pytest.raises(ValueError, match="editorial anchor"):
        M.edit_texts(p, result, earlier, ANALYSIS, original[0].replace(p.escape(p.abstract(result, earlier)), "changed"),
            *original[1:])


def test_wrong_sealed_stage_schema_refused_before_git_or_output(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    receipt = stage / "preparation-receipt.json"
    receipt.write_text(json.dumps({"schema": "untrusted", "status": "REVIEW_PENDING"}), encoding="utf-8")
    b = M.module(ROOT, M.BUILDER, "negative_editorial_builder")
    (stage / "manifest.json").write_text(json.dumps({receipt.name: b.binding(receipt)}), encoding="utf-8")
    output = ROOT / "output" / ("never-created-editorial-test-" + uuid.uuid4().hex)
    args = SimpleNamespace(root=ROOT, stage=stage, output=output, analysis=ANALYSIS,
        interrupted_analysis=ANALYSIS, protocol=Path("unused"), protocol_commit="a" * 40,
        interrupted_protocol=Path("unused"), interrupted_protocol_commit="b" * 40)
    with pytest.raises(ValueError, match="sealed review-pending"):
        M.prepare(args)
    assert not output.exists()
