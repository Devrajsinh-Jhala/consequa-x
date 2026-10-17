"""Release archives must contain reviewed public bytes and no extra payloads."""

import base64
from hashlib import sha256
import io
import json
from pathlib import Path
import runpy
import stat
import tarfile
from zipfile import ZipFile, ZipInfo

import pytest


VERSION = "1.1.0"
DIST = f"consequa_x-{VERSION}.dist-info/"
EGG = "src/consequa_x.egg-info/"
PREFIX = f"consequa_x-{VERSION}/"


def write_wheel(path, payloads, *, corrupt_record=False):
    data = dict(payloads)
    records = []
    for name, content in sorted(data.items()):
        digest = base64.urlsafe_b64encode(sha256(content).digest()).decode().rstrip("=")
        records.append(f"{name},sha256={digest},{len(content)}")
    records.append(f"{DIST}RECORD,,")
    record = ("\n".join(records) + "\n").encode()
    if corrupt_record:
        record = record.replace(b"sha256=", b"sha256=wrong", 1)
    data[DIST + "RECORD"] = record
    with ZipFile(path, "w") as archive:
        for name, content in data.items():
            member = ZipInfo(name)
            # Preserve adversarial raw separators on Windows, whose ZipInfo
            # constructor otherwise silently normalizes them before writing.
            member.filename = member.orig_filename = name
            archive.writestr(member, content)


def write_sdist(path, payloads, *, extra_members=()):
    with tarfile.open(path, "w:gz") as archive:
        for name, content in payloads.items():
            member = tarfile.TarInfo(PREFIX + name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        for member in extra_members:
            archive.addfile(member, io.BytesIO(b""))


@pytest.fixture
def release(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/audit_release_artifacts.py"
    module = runpy.run_path(str(script))
    root = tmp_path / "source"
    root.mkdir()
    project = '''[project]
name = "consequa-x"
version = "1.1.0"
requires-python = ">=3.11"
license = "MIT"
dependencies = []
[project.optional-dependencies]
dev = ["pytest>=8"]
[project.urls]
Homepage = "https://example.test"
Documentation = "https://example.test/docs"
Issues = "https://example.test/issues"
Security = "https://example.test/security"
[project.scripts]
consequa-x = "consequa_x.cli:main"
'''
    sources = {
        "pyproject.toml": project.encode(),
        "MANIFEST.in": b"include README.md CONTRIBUTING.md CHANGELOG.md LICENSE SECURITY.md requirements-dev.lock\n"
                       b"recursive-include docs *.md\nrecursive-include docs/studies *.json\n"
                       b"recursive-include tests *.py\nrecursive-include examples *.py\n"
                       b"recursive-include scripts *.py\n",
        "README.md": b"# Public quickstart\n",
        "CONTRIBUTING.md": b"Public contribution instructions\n",
        "CHANGELOG.md": b"Version 1.1.0\n",
        "LICENSE": b"MIT License\nPermission is hereby granted, free of charge.\n",
        "SECURITY.md": b"Private disclosure route\n",
        "requirements-dev.lock": b"pytest==8.0\n",
        "docs/guide.md": b"Public guide\n",
        "docs/studies/plan.json": b'{"public_plan": true}\n',
        "tests/test_example.py": b"def test_example():\n    assert True\n",
        "examples/quickstart.py": b"print('synthetic fixture')\n",
        "scripts/check.py": b"print('reviewed check')\n",
        "src/consequa_x/__init__.py": b'__version__ = "1.1.0"\n',
        "src/consequa_x/cli.py": b"def main():\n    return 0\n",
        "src/consequa_x/report.py": b"def render_report(trace):\n    return '<html></html>'\n",
        "src/consequa_x/py.typed": b"",
        "src/consequa_x/schemas/trace-v0.1.json": b'{"version": "0.1"}\n',
    }
    for name, data in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Out-of-scope source material must never enter a distribution inventory.
    for name in ("Pypi token.txt", "output/private.json", "website/index.html",
                 "community/README.md", "docs/research/brief.pdf", "tmp/disk.qcow2"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic private sentinel", encoding="utf-8")
    metadata = b"""Metadata-Version: 2.4
Name: consequa-x
Version: 1.1.0
Requires-Python: >=3.11
License-Expression: MIT
License-File: LICENSE
Description-Content-Type: text/markdown
Project-URL: Homepage, https://example.test
Project-URL: Documentation, https://example.test/docs
Project-URL: Issues, https://example.test/issues
Project-URL: Security, https://example.test/security
Provides-Extra: dev
Requires-Dist: pytest>=8; extra == "dev"

# Public quickstart
"""
    entry = b"[console_scripts]\nconsequa-x = consequa_x.cli:main\n"
    wheel_data = {name.removeprefix("src/"): value for name, value in sources.items()
                  if name.startswith("src/consequa_x/")}
    wheel_data.update({DIST + "METADATA": metadata,
                       DIST + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                       DIST + "entry_points.txt": entry, DIST + "top_level.txt": b"consequa_x\n",
                       DIST + "licenses/LICENSE": sources["LICENSE"]})
    sdist_data = dict(sources)
    sdist_data.update({"PKG-INFO": metadata, "setup.cfg": b"[egg_info]\ntag_build =\ntag_date = 0\n",
                       EGG + "PKG-INFO": metadata, EGG + "dependency_links.txt": b"\n",
                       EGG + "entry_points.txt": entry, EGG + "top_level.txt": b"consequa_x\n",
                       EGG + "requires.txt": b"[dev]\npytest>=8\n"})
    sdist_data[EGG + "SOURCES.txt"] = (
        "\n".join(sorted((set(sdist_data) | {EGG + "SOURCES.txt"}) - {"PKG-INFO", "setup.cfg"}))
        + "\n").encode()
    wheel = tmp_path / f"consequa_x-{VERSION}-py3-none-any.whl"
    sdist = tmp_path / f"consequa_x-{VERSION}.tar.gz"
    write_wheel(wheel, wheel_data)
    write_sdist(sdist, sdist_data)
    return {"module": module, "root": root, "sources": sources, "wheel": wheel, "sdist": sdist,
            "wheel_data": wheel_data, "sdist_data": sdist_data, "tmp": tmp_path}


def checked(release):
    return release["module"]["audit"](release["wheel"], release["sdist"], release["root"],
                                       VERSION, "a" * 40)


def test_exact_public_archives_bind_all_source_and_artifact_bytes(release):
    result = checked(release)
    assert result["passed"] is True
    assert result["runtime_files"] == 5
    assert result["metadata"]["runtime_dependencies"] == 0
    assert {item["path"] for item in result["source_files"]} == set(release["sources"])
    for item in result["source_files"]:
        assert item["sha256"] == sha256(release["sources"][item["path"]]).hexdigest()
    assert [item["sha256"] for item in result["artifacts"]] == [
        sha256(release[key].read_bytes()).hexdigest() for key in ("wheel", "sdist")]
    assert len(result["source_inventory_sha256"]) == len(result["auditor_sha256"]) == 64


@pytest.mark.parametrize("name", ["Pypi token.txt", "output/private.json", "website/index.html",
                                   "community/README.md", "docs/research/brief.pdf", "tmp/disk.qcow2",
                                   ".env", ".git/config", "consequa_x/__pycache__/cli.pyc"])
def test_private_and_generated_material_is_refused_in_source_archive(release, name):
    release["sdist_data"][name] = b"must never ship"
    write_sdist(release["sdist"], release["sdist_data"])
    with pytest.raises(ValueError, match="Forbidden"):
        checked(release)


@pytest.mark.parametrize("name", ["../escape.py", "/absolute.py", "consequa_x\\cli.py",
                                   "consequa_x/a:b.py", "consequa_x/./cli.py"])
def test_unsafe_wheel_member_paths_are_refused(release, name):
    release["wheel_data"][name] = b"unsafe"
    write_wheel(release["wheel"], release["wheel_data"])
    with pytest.raises(ValueError, match="Unsafe"):
        checked(release)


@pytest.mark.parametrize("target", ["wheel", "sdist"])
def test_missing_typing_schema_or_public_docs_cannot_pass_an_inventory_audit(release, target):
    if target == "wheel":
        del release["wheel_data"]["consequa_x/py.typed"]
        write_wheel(release["wheel"], release["wheel_data"])
    else:
        del release["sdist_data"]["SECURITY.md"]
        write_sdist(release["sdist"], release["sdist_data"])
    with pytest.raises(ValueError, match="inventory differs"):
        checked(release)


@pytest.mark.parametrize("target,name", [("wheel", "consequa_x/report.py"),
                                        ("sdist", "docs/guide.md")])
def test_hash_consistent_archives_still_require_exact_reviewed_source_bytes(release, target, name):
    release[target + "_data"][name] += b"\nchanged after review\n"
    {"wheel": write_wheel, "sdist": write_sdist}[target](release[target], release[target + "_data"])
    with pytest.raises(ValueError, match="payload differs"):
        checked(release)


def test_arbitrary_generated_metadata_filename_is_not_an_escape_from_allowlist(release):
    release["sdist_data"][EGG + "unreviewed.txt"] = b"hidden payload"
    write_sdist(release["sdist"], release["sdist_data"])
    with pytest.raises(ValueError, match="inventory differs"):
        checked(release)


def test_duplicate_wheel_members_are_refused(release):
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(release["wheel"], "a") as archive:
            archive.writestr("consequa_x/cli.py", b"replacement")
    with pytest.raises(ValueError, match="Duplicate"):
        checked(release)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_tar_links_and_special_members_are_never_followed_or_extracted(release, kind):
    member = tarfile.TarInfo(PREFIX + "link")
    member.type = kind
    member.linkname = "../../outside"
    write_sdist(release["sdist"], release["sdist_data"], extra_members=[member])
    with pytest.raises(ValueError, match="links or special"):
        checked(release)
    assert not (release["tmp"] / "outside").exists()


def test_zip_symlinks_are_refused(release):
    member = ZipInfo("consequa_x/link")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(release["wheel"], "a") as archive:
        archive.writestr(member, "../../outside")
    with pytest.raises(ValueError, match="links"):
        checked(release)


@pytest.mark.parametrize("old,new", [(b"Version: 1.1.0", b"Version: 1.0.0"),
                                     (b"License-Expression: MIT", b"License-Expression: Other"),
                                     (b"Requires-Python: >=3.11", b"Requires-Python: >=3.12"),
                                     (b"https://example.test/docs", b"https://unreviewed.test/docs"),
                                     (b'Requires-Dist: pytest>=8; extra == "dev"',
                                      b"Requires-Dist: requests>=2")])
def test_metadata_cannot_change_version_license_compatibility_dependencies_or_urls(release, old, new):
    release["wheel_data"][DIST + "METADATA"] = release["wheel_data"][DIST + "METADATA"].replace(old, new)
    write_wheel(release["wheel"], release["wheel_data"])
    with pytest.raises(ValueError, match="metadata differs|URLs differ|dependencies differ"):
        checked(release)


def test_reviewed_entrypoint_and_record_integrity_are_independent_requirements(release):
    release["wheel_data"][DIST + "entry_points.txt"] = b"[console_scripts]\nconsequa-x = other:run\n"
    write_wheel(release["wheel"], release["wheel_data"])
    with pytest.raises(ValueError, match="entrypoint differs"):
        checked(release)


def test_wheel_record_with_incorrect_hash_is_refused(release):
    write_wheel(release["wheel"], release["wheel_data"], corrupt_record=True)
    with pytest.raises(ValueError, match="RECORD hash"):
        checked(release)


def test_broad_manifest_directives_cannot_expand_the_reviewed_public_scope(release):
    with (release["root"] / "MANIFEST.in").open("a", encoding="utf-8") as stream:
        stream.write("graft output\n")
    with pytest.raises(ValueError, match="MANIFEST directive"):
        checked(release)


def arguments(release, output):
    return ["--wheel", str(release["wheel"]), "--sdist", str(release["sdist"]),
            "--source-root", str(release["root"]), "--expected-version", VERSION,
            "--source-revision", "a" * 40, "--output", str(output)]


def test_cli_writes_a_new_bound_receipt_and_preserves_it_on_repeat(release):
    output = release["tmp"] / "receipt.json"
    assert release["module"]["main"](arguments(release, output)) == 0
    original = output.read_bytes()
    assert json.loads(original)["passed"] is True
    with pytest.raises(ValueError, match="Keep previous audit receipts"):
        release["module"]["main"](arguments(release, output))
    assert output.read_bytes() == original


def test_failed_audit_creates_no_output_tree(release):
    release["wheel_data"]["unreviewed.txt"] = b"extra payload"
    write_wheel(release["wheel"], release["wheel_data"])
    output = release["tmp"] / "not-created" / "receipt.json"
    with pytest.raises(ValueError, match="inventory differs"):
        release["module"]["main"](arguments(release, output))
    assert not output.parent.exists()
