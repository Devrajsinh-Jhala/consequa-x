"""Independently inventory final stable archives and bind them to Git and study bytes."""
import argparse
import base64
import csv
from email.parser import BytesParser
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tomllib
import zipfile
from packaging.requirements import Requirement


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists() and (parent / "pyproject.toml").is_file())
    output = args.release / "inventory.json"
    assert not output.exists(), "Preserve existing inventory"
    frozen = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    payloads = frozen["payload_sha256"]
    git_files = subprocess.run(["git", "ls-tree", "-r", "--name-only", args.source_revision],
        cwd=root, capture_output=True, check=True).stdout.decode().splitlines()
    expected_source = {name for name in git_files if name.startswith(("src/", "tests/", "examples/"))
        and (name.endswith(".py") or name.startswith("src/"))}
    expected_source |= {name for name in git_files if name.startswith("scripts/")
                        and name.endswith(".py")}
    expected_source |= {name for name in git_files if name.startswith("docs/")
                        and (name.endswith(".md") or name.startswith("docs/studies/")
                             and name.endswith(".json"))}
    expected_source |= {"README.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE", "requirements-dev.lock",
                        "pyproject.toml", "MANIFEST.in"}
    sdist = args.release / "consequa_x-1.0.0.tar.gz"
    wheel = args.release / "consequa_x-1.0.0-py3-none-any.whl"
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        assert len({m.name for m in members}) == len(members)
        assert all(not m.issym() and not m.islnk() and ".." not in Path(m.name).parts
                   and not Path(m.name).is_absolute() for m in members)
        source = {}
        for member in members:
            if not member.isfile():
                continue
            name = member.name.removeprefix("consequa_x-1.0.0/")
            assert name != member.name, member.name
            assert not any(part in {"tmp", "output", ".venv", ".git", "__pycache__"}
                           for part in Path(name).parts), name
            assert "token" not in name.lower() and not name.endswith((".pem", ".pypirc", ".env")), name
            source[name] = archive.extractfile(member).read()
        generated = {"PKG-INFO", "setup.cfg"} | {f"src/consequa_x.egg-info/{name}"
            for name in ("PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt",
                         "requires.txt", "top_level.txt")}
        assert set(source) == expected_source | generated, (
            sorted(expected_source - source.keys()), sorted(source.keys() - expected_source - generated))
        for name in expected_source:
            git_bytes = subprocess.run(["git", "show", f"{args.source_revision}:{name}"],
                cwd=root, capture_output=True, check=True).stdout
            assert source[name] == git_bytes, name
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        metadata_files = {f"consequa_x-1.0.0.dist-info/{name}" for name in (
            "licenses/LICENSE", "METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD")}
        assert set(names) == set(payloads) | metadata_files
        assert {name for name in names if name.startswith("consequa_x/")} == set(payloads)
        for name, digest in payloads.items():
            content = archive.read(name)
            assert sha256(content).hexdigest() == digest, name
            assert content == source[f"src/{name}"], name
        meta = BytesParser().parsebytes(archive.read("consequa_x-1.0.0.dist-info/METADATA"))
        assert meta["Name"] == "consequa-x" and meta["Version"] == "1.0.0"
        assert meta["License-Expression"] == "MIT" and meta["Requires-Python"] == ">=3.11"
        assert meta.get_all("License-File") == ["LICENSE"]
        assert archive.read("consequa_x-1.0.0.dist-info/licenses/LICENSE") == source["LICENSE"]
        wheel_meta = BytesParser().parsebytes(archive.read("consequa_x-1.0.0.dist-info/WHEEL"))
        assert wheel_meta["Root-Is-Purelib"] == "true"
        assert wheel_meta.get_all("Tag") == ["py3-none-any"]
        project = tomllib.loads(source["pyproject.toml"].decode())["project"]
        assert project["dependencies"] == []
        expected_requirements = {str(Requirement(f'{item}; extra == "{extra}"'))
            for extra, items in project["optional-dependencies"].items() for item in items}
        assert {str(Requirement(item)) for item in meta.get_all("Requires-Dist", [])} \
            == expected_requirements
        assert source["README.md"].decode().replace("\r\n", "\n") \
            == meta.get_payload().replace("\r\n", "\n")
        assert "consequa-x = consequa_x.cli:main" in archive.read(
            "consequa_x-1.0.0.dist-info/entry_points.txt").decode()
        record_name = "consequa_x-1.0.0.dist-info/RECORD"
        records = list(csv.reader(io.StringIO(archive.read(record_name).decode())))
        assert len(records) == len(names) and {row[0] for row in records} == set(names)
        for name, digest, size in records:
            if name == record_name:
                assert digest == size == ""
                continue
            content = archive.read(name)
            expected = "sha256=" + base64.urlsafe_b64encode(sha256(content).digest()).decode().rstrip("=")
            assert digest == expected and int(size) == len(content), name
    report = {"passed": True, "source_revision": args.source_revision,
        "study_source_revision": frozen["source_revision"], "version": "1.0.0",
        "runtime_files_identical_to_study_checkpoint": len(payloads),
        "git_source_files_checked": len(expected_source), "wheel_record_entries": len(records),
        "sdist_file_count": len(source), "sdist_includes_docs_examples_tests_auditors": True,
        "private_research_outputs_credentials_and_environments_excluded": True,
        "bundled_schema_pytyped_mit_console_entrypoint": True, "runtime_dependencies": 0,
        "artifacts": [{"path": p.name, "bytes": p.stat().st_size,
                       "sha256": sha256(p.read_bytes()).hexdigest()} for p in (wheel, sdist)]}
    output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
