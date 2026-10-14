"""Check an installed alpha outside the source checkout, with no provider calls."""

import argparse
from hashlib import sha256
from importlib import metadata
import json
from pathlib import Path
import platform
import sys

import consequa_x
from consequa_x import Trace, explain
from consequa_x.benchmark.runner import demo_scenarios, run_scenario
from consequa_x.schema import get_trace_schema, validate_trace


parser = argparse.ArgumentParser()
parser.add_argument("report", type=Path)
args = parser.parse_args()
installed_path = Path(consequa_x.__file__).resolve()
assert installed_path.is_relative_to(Path(sys.prefix).resolve())
assert metadata.version("consequa-x") == consequa_x.__version__ == "0.1.0a2"
assert get_trace_schema()["$schema"].endswith("/2020-12/schema")
assert all("extra ==" in requirement
           for requirement in metadata.metadata("consequa-x").get_all("Requires-Dist", []))
scenarios = demo_scenarios()
assert len(scenarios) == 12
for config in scenarios:
    trace = run_scenario(config, seed=0).trace
    encoded = trace.to_json()
    assert Trace.from_json(encoded) == trace
    assert validate_trace(encoded) == trace
    assert explain(trace).to_dict()
module_hashes = {path.relative_to(installed_path.parent).as_posix(): sha256(path.read_bytes()).hexdigest()
                 for path in sorted(installed_path.parent.rglob("*"))
                 if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
report = {"passed": True, "version": consequa_x.__version__, "python": platform.python_version(),
          "platform": platform.platform(), "isolated_interpreter": sys.flags.isolated == 1,
          "imported_installed_package": True, "demo_trace_roundtrips": len(scenarios),
          "schema_validation": True, "explanation_smoke": True, "runtime_dependencies": 0,
          "provider_calls": 0, "installed_payload_sha256": module_hashes}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8", newline="\n")
print(json.dumps({key: value for key, value in report.items() if key != "installed_payload_sha256"}))
