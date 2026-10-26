"""The multi-family gate must refuse truncation and malformed token evidence."""
import pytest

from research.expanded_limbo.transport import checked_context


def test_exact_context_boundary_includes_generation_and_reserve():
    record = checked_context("full prompt", [1, 2, 3], output_tokens=8,
                             context_tokens=15, reserve_tokens=4)
    assert record["required_tokens"] == 15 and record["fits"]
    assert record["truncation_requested"] is False
    with pytest.raises(ValueError, match="exceeds"):
        checked_context("full prompt", [1, 2, 3, 4], output_tokens=8,
                        context_tokens=15, reserve_tokens=4)


@pytest.mark.parametrize("tokens", [None, [], [True], [-1], [1.5], "1,2"])
def test_context_requires_actual_runner_token_ids(tokens):
    with pytest.raises(ValueError, match="token IDs"):
        checked_context("full prompt", tokens, output_tokens=8, context_tokens=20)


def test_empty_preview_cannot_authorize_generation():
    with pytest.raises(ValueError, match="provider-rendered"):
        checked_context("", [1], output_tokens=8, context_tokens=100)
