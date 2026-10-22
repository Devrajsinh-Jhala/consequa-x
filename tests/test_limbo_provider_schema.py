"""Provider schema compatibility; no native task or model generation."""
from copy import deepcopy

import pytest

from research.limbo_agent import transport


def tools(value=True):
    return [{"type": "function", "function": {"name": "invented", "parameters": {
        "type": "object", "additionalProperties": value,
        "properties": {"row": {"type": "object", "additionalProperties": True},
                       "rows": {"type": "array", "items": {
                           "type": "object", "additionalProperties": False}}},
        "$defs": {"opaque": {"additionalProperties": False}}, "required": ["row"]}}}]


def test_default_true_elision_is_offline_only_and_opaque_nodes_are_preserved(monkeypatch):
    original = tools()
    before = deepcopy(original)
    received = []
    monkeypatch.setattr(transport, "render_gguf_template", lambda m, h, t: received.append(t) or "rendered")
    assert transport.render_limbo_template({}, [], original) == "rendered"
    assert original == before
    p = received[0][0]["function"]["parameters"]
    assert "additionalProperties" not in p
    assert "additionalProperties" not in p["properties"]["row"]
    assert p["properties"]["rows"]["items"]["additionalProperties"] is False
    assert p["$defs"]["opaque"]["additionalProperties"] is False


@pytest.mark.parametrize("value", [False, 1, 0, None, {}, {"type": "string"}, "true"])
def test_nondefault_constraint_refused_before_render_or_network(value, monkeypatch):
    def forbidden(*args):
        pytest.fail("A lossy schema reached rendering")
    monkeypatch.setattr(transport, "render_gguf_template", forbidden)
    with pytest.raises(ValueError, match="non-default additionalProperties"):
        transport.render_limbo_template({}, [], tools(value))
