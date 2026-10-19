"""The Python examples shown in the README run as written."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def python_blocks(path, heading):
    text = (ROOT / path).read_text(encoding="utf-8")
    section = text[text.index(heading):]
    section = section[:section.index("\n## ", 1)]
    return re.findall(r"```python\n(.*?)```", section, re.S)


def test_readme_python_example_runs(capsys):
    (block,) = python_blocks("README.md", "## Use it in Python")
    exec(compile(block, "README.md", "exec"), {})
    assert "ASSESSMENT_DIVERGENCE" in capsys.readouterr().out
