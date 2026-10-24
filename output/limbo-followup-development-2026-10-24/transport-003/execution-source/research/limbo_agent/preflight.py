"""Read-only pinned public-API inventory; never import or execute LIMBO.

Only the explicit API/document allowlist and three public schema declarations
are inspected. Tasks, fixtures, cases, archives and scenario values stay out.
Git lazy fetching is disabled so this check cannot request new remote blobs.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys


PIN = "2db09fba22a0572a70639162a808906409f612a8"
FILES = (
    "README.md", "LICENSE", "DATA_LICENSE", "requirements.txt", "limbo/__init__.py",
    "limbo/llm.py", "limbo/agent.py", "limbo/runtime.py", "limbo/grader.py",
    "limbo/policies.py", "limbo/runner.py",
)
SCHEMA_CLASSES = {"VerifyResult", "Contract", "ToolSpec"}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git(repo, *arguments, allow_failure=False):
    env = os.environ.copy()
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *arguments],
        capture_output=True, env=env, check=False)
    if result.returncode and not allow_failure:
        raise RuntimeError("Read-only Git identity/source check failed: " + arguments[0])
    return result


def api_inventory(source):
    """Return names/signatures/import dependencies, never function bodies."""
    tree = ast.parse(source)
    imports, functions, classes = [], {}, {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append("." * node.level + (node.module or ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[node.name] = {"line": node.lineno, "arguments": ast.unparse(node.args)}
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = class_inventory(node)
    return {"imports": sorted(imports), "functions": functions, "classes": classes}


def class_inventory(node):
    return {"line": node.lineno, "fields": {
        item.target.id: ast.unparse(item.annotation) for item in node.body
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)}, "methods": {
        item.name: {"line": item.lineno, "arguments": ast.unparse(item.args)} for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))}}


def inspect(repo):
    repo = Path(repo).resolve()
    head = git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    if head != PIN or git(repo, "symbolic-ref", "-q", "HEAD", allow_failure=True).returncode != 1:
        raise RuntimeError("LIMBO must be detached at the exact declared source commit")
    if git(repo, "status", "--porcelain").stdout.strip():
        raise RuntimeError("Pinned upstream checkout must remain unchanged")
    bindings, inventories = {}, {}
    for name in FILES:
        committed = git(repo, "show", PIN + ":" + name).stdout
        actual = (repo / name).read_bytes()
        if actual != committed and not (b"\r\n" not in committed and actual == committed.replace(b"\n", b"\r\n")):
            raise RuntimeError("Public API bytes differ from the pin: " + name)
        bindings[name] = {"git_sha256": digest(committed), "runtime_sha256": digest(actual),
                          "runtime_bytes": len(actual), "git_bytes": len(committed)}
        if name.endswith(".py"):
            inventories[name] = api_inventory(actual.decode("utf-8"))
    # Public dataclass declarations only; no service handler/verifier bodies
    # or per-domain values are emitted or used to instantiate an environment.
    schema_source = git(repo, "show", PIN + ":limbo/services.py").stdout
    schemas = {node.name: class_inventory(node) for node in ast.parse(schema_source).body
               if isinstance(node, ast.ClassDef) and node.name in SCHEMA_CLASSES}
    if set(schemas) != SCHEMA_CLASSES:
        raise RuntimeError("Expected public verification/tool schema declarations changed")
    versions = {}
    for name in ("consequa-x", "numpy", "pandas", "scipy", "statsmodels", "matplotlib"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    if any(name == "limbo" or name.startswith("limbo.") for name in sys.modules):
        raise RuntimeError("Preflight must not import any upstream runtime or task module")
    return {"schema": "conseqax-limbo-public-api-preflight-v1", "passed": True,
        "recorded_utc": datetime.now(timezone.utc).isoformat(), "upstream_repository": "https://github.com/jaxblack/limbo-bench",
        "upstream_commit": PIN, "upstream_root": str(repo), "detached": True,
        "public_file_bindings": bindings, "public_api_inventory": inventories,
        "public_schema_source": {"path": "limbo/services.py", "git_sha256": digest(schema_source),
            "git_bytes": len(schema_source), "inspection_scope": "VerifyResult, Contract and ToolSpec declaration metadata only"},
        "public_schemas": schemas, "available_distribution_versions": versions,
        "dependency_check_scope": "Installed metadata only; upstream modules were not imported or executed",
        "preflight_source_sha256": digest(Path(__file__).read_bytes()),
        "task_definition_files_read": 0, "fixtures_or_archives_opened": 0,
        "upstream_modules_imported": 0, "model_generations": 0, "episodes_executed": 0,
        "production_service_requests": 0, "git_lazy_fetch_disabled": True,
        "limits": ["Not an execution protocol, dependency import proof or performance result",
            "Public verification detail is an unconstrained dictionary; per-domain shape/cost remains unvalidated",
            "Source inventory excludes hidden task data and uninspected runtime dependencies"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="D:/ConsequaX-Research/limbo-pinned-2db09fba")
    parser.add_argument("--output", help="Optional new JSON file; existing files are never overwritten")
    args = parser.parse_args()
    result = inspect(args.repo)
    if args.output:
        with Path(args.output).open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"passed": True, "upstream_commit": PIN, "output": str(Path(args.output).resolve()),
                          "model_generations": 0, "episodes_executed": 0}))
    else:
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
