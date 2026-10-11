from unittest.mock import patch

import pytest

from consequa_x import cli
from consequa_x.adapters.ollama import OllamaPolicy
from consequa_x.models import AssessmentStatus
from consequa_x.policies import PolicyDecision, PolicyReply


@pytest.mark.parametrize("command", ["model-eval", "model-experiment"])
def test_scripted_prompt_selection_is_rejected_before_outputs_or_provider(tmp_path, capsys, command):
    output = tmp_path / "rejected"
    with patch.object(OllamaPolicy, "list_models") as listing:
        assert cli.main([command, "--prompt-version", "refund-policy-v2",
                         "--output", str(output)]) == 2
    listing.assert_not_called()
    assert not output.exists()
    assert "requires --provider ollama" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["model-eval", "model-experiment"])
def test_cli_passes_prompt_profile_through_to_captured_policy(tmp_path, command):
    output = tmp_path / command
    prompts = []

    def decide(self, request, *, seed):
        prompts.append(self.prompt_version)
        return PolicyReply(PolicyDecision("stop", AssessmentStatus.UNKNOWN, "No evidence yet."))

    extra = ["--cases", "clean", "--samples", "1"] if command == "model-eval" else [
        "--case", "clean", "--candidates", "distractor", "--samples", "2"]
    with patch.object(OllamaPolicy, "list_models", return_value=(
        {"name": "fixture:latest", "model": "fixture:latest", "digest": "test"},
    )), patch.object(OllamaPolicy, "validate_local_model", return_value={}), patch.object(
        OllamaPolicy, "decide", decide
    ):
        assert cli.main([command, "--provider", "ollama", "--model", "fixture:latest",
                         "--prompt-version", "refund-policy-v2", "--output", str(output),
                         *extra]) == 0
    assert prompts and set(prompts) == {"refund-policy-v2"}
    import json
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert result["policy"]["prompt_version"] == "refund-policy-v2"
