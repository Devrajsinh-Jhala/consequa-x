"""Prospective, pure repair of one pinned Granite provider template.

This module does not install a template, modify a model, relax qualification,
dispatch a generation, or change any frozen study. A caller must declare and
qualify the returned bytes as a new provider-template condition before use.
"""
from __future__ import annotations

import hashlib
import json
import re


ORIGINAL_TEMPLATE_SHA256 = "3da071a01bbe5a1aa1e9766149ff67ed2b232f63d55e6ed50e3777b74536a67f"
ORIGINAL_TEMPLATE_BYTES = 6560
DEFAULT_SYSTEM_ANCHOR = (
    "{{- /*\nIf no user message provided, build the default system message\n*/ -}}\n"
    '{{- if eq $system "" }}'
)


def _binding(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def repair_template(template: str | bytes) -> dict:
    """Append existing native format guidance only to a custom system message.

    Require exact original UTF-8 bytes, including their line endings. The patch
    inserts one branch before the existing default-system decision. Consequently
    the default-system branch and every message/tool/history rendering branch
    remain byte-for-byte intact; no model output is converted into a tool call.
    """
    if not isinstance(template, (str, bytes)):
        raise TypeError("Expected pinned Granite template text or UTF-8 bytes")
    raw = template.encode("utf-8") if isinstance(template, str) else template
    original = _binding(raw)
    if original != {"sha256": ORIGINAL_TEMPLATE_SHA256, "bytes": ORIGINAL_TEMPLATE_BYTES}:
        raise ValueError("Unsupported Granite template: original SHA256/length differs")
    text = raw.decode("utf-8")
    if text.count(DEFAULT_SYSTEM_ANCHOR) != 1:
        raise ValueError("Pinned Granite template lacks one exact default-system anchor")
    # Reuse the official guidance from the frozen template itself. Do not
    # paraphrase its format, invent a tool choice, or add examples with answers.
    guidance_match = re.search(
        r'\{\{- \$system = print \$system (" You are a helpful assistant with access to the following tools\.[^\n]+") \}\}',
        text,
    )
    if guidance_match is None:
        raise ValueError("Pinned Granite template lacks its native tool-format guidance")
    guidance = json.loads(guidance_match.group(1)).lstrip()
    insertion = (
        "{{- /* Retain native tool format with a user-provided system prompt. */}}\n"
        '{{- if and .Tools (ne $system "") }}\n'
        '    {{- $system = print $system "\\n\\n" '
        + json.dumps(guidance, ensure_ascii=False)
        + " }}\n{{- end}}\n\n"
    )
    repaired = text.replace(DEFAULT_SYSTEM_ANCHOR, insertion + DEFAULT_SYSTEM_ANCHOR, 1)
    return {
        "schema": "conseqax-granite-custom-system-format-repair-v1",
        "template": repaired,
        "original": original,
        "patched": _binding(repaired.encode("utf-8")),
        "official_guidance": guidance,
        "prospective_template_condition": True,
        "native_messages_and_tools_rewritten": False,
        "model_output_reinterpreted_as_tool_call": False,
        "gpu_qualification_completed": False,
        "scope": "One insertion before default-system selection; custom system plus tools only",
    }
