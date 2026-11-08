"""Offline checks of prospective template bytes; no model/runtime installation."""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.kaggle_limbo import granite_format as repair  # noqa: E402


@pytest.fixture
def original():
    archive = ROOT / "output/kaggle-benchmark-2026-11-08/conseqax-kaggle-benchmark.zip"
    member = "conseqax-kaggle-study/assets/models/granite/sha256-" + repair.ORIGINAL_TEMPLATE_SHA256
    with zipfile.ZipFile(archive) as source:
        return source.read(member)


@pytest.mark.parametrize("as_text", [False, True])
def test_pinned_template_repair_binds_exact_before_and_after_bytes(original, as_text):
    result = repair.repair_template(original.decode() if as_text else original)
    assert result["original"] == {
        "sha256": repair.ORIGINAL_TEMPLATE_SHA256, "bytes": len(original)}
    after = result["template"].encode()
    assert result["patched"] == {"sha256": hashlib.sha256(after).hexdigest(), "bytes": len(after)}
    assert result["patched"]["sha256"] != repair.ORIGINAL_TEMPLATE_SHA256
    assert result["prospective_template_condition"]
    assert result["gpu_qualification_completed"] is False
    assert result["native_messages_and_tools_rewritten"] is False
    assert result["model_output_reinterpreted_as_tool_call"] is False


def test_single_custom_system_insertion_preserves_all_original_rendering(original):
    before = original.decode()
    result = repair.repair_template(original)
    after = result["template"]
    edits = [edit for edit in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes()
             if edit[0] != "equal"]
    assert len(edits) == 1
    operation, begin, end, inserted_begin, inserted_end = edits[0]
    assert operation == "insert" and begin == end
    insertion = after[inserted_begin:inserted_end]
    # The added condition is evaluated before the default branch fills $system:
    # no-tools and empty-custom-system requests do not receive extra guidance.
    assert '{{- if and .Tools (ne $system "") }}' in insertion
    assert result["official_guidance"] in insertion
    assert begin <= before.index(repair.DEFAULT_SYSTEM_ANCHOR)
    assert after[:inserted_begin] + after[inserted_end:] == before
    # The source of the guidance and the native message/tool replay stay intact.
    default_start = before.index(repair.DEFAULT_SYSTEM_ANCHOR)
    assert after.endswith(before[default_start:])
    assert before.count(result["official_guidance"]) == 1
    assert after.count(result["official_guidance"]) == 2
    assert '.Messages' not in insertion and '.ToolCalls' not in insertion
    assert '"<|tool_call|>"' not in insertion  # Guidance never fabricates an output token.


@pytest.mark.parametrize("change", ["one_byte", "newlines", "other_family", "already_patched"])
def test_changed_or_unsupported_template_is_rejected(original, change):
    candidate = {
        "one_byte": original + b"\n",
        "newlines": original.replace(b"\n", b"\r\n"),
        "other_family": b"{{ .Messages }}",
        "already_patched": repair.repair_template(original)["template"],
    }[change]
    with pytest.raises(ValueError, match="original SHA256/length differs"):
        repair.repair_template(candidate)


@pytest.mark.parametrize("value", [None, 123, {}, bytearray(b"template")])
def test_non_text_template_input_is_rejected(value):
    with pytest.raises(TypeError):
        repair.repair_template(value)
