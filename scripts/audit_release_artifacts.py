"""Audit reviewed wheel/sdist contents without importing them or accessing a network.

Only source files selected by the repository's bounded MANIFEST.in directives
and narrowly named setuptools metadata are permitted. The caller supplies a
frozen Git revision; file hashes bind the actual source bytes independently.
An existing receipt is never replaced. This checks contents, not authenticity.
"""

from __future__ import annotations

import argparse
import ast
import base64
import configparser
import csv
from email.parser import BytesParser
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tomllib
from urllib.parse import urlsplit
from zipfile import ZipFile


TOP_LEVEL = frozenset({"README.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE",
                       "SECURITY.md", "requirements-dev.lock"})
RECURSIVE = frozenset({("docs", "*.md"), ("docs/studies", "*.json"),
                       ("tests", "*.py"), ("tests/fixtures", "*.json"), ("tests/fixtures", "*.md"),
                       ("examples", "*.py"), ("scripts", "*.py")})
EGG_NAMES = frozenset({"PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt",
                       "requires.txt", "top_level.txt"})
DIST_NAMES = frozenset({"METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD",
                        "licenses/LICENSE"})
FORBIDDEN_PARTS = frozenset({"output", "tmp", "website", "community", "research", "paper",
                            "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache",
                            ".venv", "pypi token.txt"})
FORBIDDEN_SUFFIXES = frozenset({".pdf", ".pyc", ".pyo", ".qcow2", ".vhd", ".vhdx", ".vdi",
                               ".iso", ".img", ".ova", ".ovf", ".vmdk", ".vmx"})


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def safe_name(name: str, *, directory: bool = False) -> str:
    """Validate archive paths before joining, reading or displaying their contents."""
    require(isinstance(name, str) and bool(name), "Empty archive member path")
    if directory and name.endswith("/"):
        name = name[:-1]
    parts = name.split("/")
    require(not any(part in {"", ".", ".."} for part in parts)
            and "\\" not in name and ":" not in name
            and not any(ord(character) < 32 or ord(character) == 127 for character in name),
            "Unsafe archive member path")
    for part in parts:
        lowered = part.lower()
        require(lowered not in FORBIDDEN_PARTS and not lowered.startswith((".git", ".env"))
                and PurePosixPath(lowered).suffix not in FORBIDDEN_SUFFIXES,
                "Forbidden private, generated or unsupported archive content")
    return name


def source_file(root: Path, relative: str) -> bytes:
    safe_name(relative)
    path = root / relative
    require(path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to(root), "Source file is absent or escapes source root")
    require(not any(parent.is_symlink() for parent in path.parents if parent != root.parent),
            "Source file traverses a symbolic link")
    return path.read_bytes()


def source_files(root: Path, version: str) -> tuple[dict[str, bytes], dict]:
    root = root.resolve()
    project = tomllib.loads(source_file(root, "pyproject.toml").decode("utf-8"))["project"]
    require(project.get("name") == "consequa-x" and project.get("version") == version,
            "Source project distribution/version differs")
    require(project.get("requires-python") == ">=3.11" and project.get("license") == "MIT"
            and project.get("dependencies") == [], "Source Python/license/runtime requirements differ")
    require(project.get("scripts") == {"consequa-x": "consequa_x.cli:main"},
            "Source console entrypoint differs")
    urls = project.get("urls", {})
    require({"Homepage", "Documentation", "Issues", "Security"}.issubset(urls),
            "Source must declare public documentation/support/security URLs")
    for url in urls.values():
        parsed = urlsplit(url)
        require(parsed.scheme == "https" and bool(parsed.hostname)
                and not parsed.username and not parsed.password and not parsed.fragment,
                "Project URLs must be absolute HTTPS URLs without credentials or fragments")
    selected = {"pyproject.toml", "MANIFEST.in"}
    manifest = source_file(root, "MANIFEST.in").decode("utf-8")
    for line in manifest.splitlines():
        words = line.partition("#")[0].split()
        if not words:
            continue
        if words[0] == "include":
            require(len(words) > 1 and set(words[1:]).issubset(TOP_LEVEL),
                    "Unreviewed MANIFEST include directive")
            selected.update(words[1:])
        elif words[0] == "recursive-include":
            require(len(words) == 3 and tuple(words[1:]) in RECURSIVE,
                    "Unreviewed MANIFEST recursive directive")
            base, pattern = words[1:]
            selected.update(path.relative_to(root).as_posix()
                            for path in (root / base).rglob(pattern) if path.is_file())
        else:
            raise ValueError("Unreviewed MANIFEST directive")
    require(TOP_LEVEL.issubset(selected), "MANIFEST omits required public release documents")
    package = root / "src/consequa_x"
    require(package.is_dir(), "Source package is absent")
    for path in package.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        require(path.suffix == ".py" or relative == "src/consequa_x/py.typed"
                or (path.parent == package / "schemas" and path.suffix == ".json"),
                "Unreviewed runtime package data")
        selected.add(relative)
    require({"src/consequa_x/__init__.py", "src/consequa_x/cli.py",
             "src/consequa_x/py.typed", "src/consequa_x/schemas/trace-v1.0.json"}.issubset(selected),
            "Required runtime/typing/schema source files are absent")
    files = {name: source_file(root, name) for name in sorted(selected)}
    tree = ast.parse(files["src/consequa_x/__init__.py"].decode("utf-8"))
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__"
                        for target in node.targets)]
    require(versions == [version], "Source runtime version differs")
    require(b"MIT License" in files["LICENSE"]
            and b"Permission is hereby granted" in files["LICENSE"], "Source MIT license is absent")
    return files, project


def expected_parents(files: set[str]) -> set[str]:
    return {parent.as_posix() for name in files for parent in PurePosixPath(name).parents
            if parent.as_posix() != "."}


def wheel_files(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as archive:
        members = archive.infolist()
        # ZipInfo.filename normalizes backslashes on Windows and truncates NULs.
        # Validate the original member spelling, before that normalization.
        names = [safe_name(item.orig_filename, directory=item.is_dir()) for item in members]
        require(len(names) == len(set(name.casefold() for name in names)),
                "Duplicate archive member path")
        files = {}
        directories = set()
        for item, name in zip(members, names):
            mode = stat.S_IFMT(item.external_attr >> 16)
            require(mode in {0, stat.S_IFREG, stat.S_IFDIR} and not item.flag_bits & 1,
                    "Wheel contains links, special or encrypted members")
            if item.is_dir():
                directories.add(name)
            else:
                require(mode != stat.S_IFDIR, "Wheel member type conflicts with its path")
                files[name] = archive.read(item)
        require(directories.issubset(expected_parents(set(files))), "Unreviewed archive directory")
    return files


def sdist_files(path: Path, version: str) -> dict[str, bytes]:
    prefix = f"consequa_x-{version}"
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [safe_name(item.name, directory=item.isdir()) for item in members]
        require(len(names) == len(set(name.casefold() for name in names)),
                "Duplicate archive member path")
        files = {}
        directories = set()
        for item, name in zip(members, names):
            require(item.isfile() or item.isdir(), "Source archive contains links or special members")
            require(name == prefix or name.startswith(prefix + "/"), "Unexpected source archive root")
            if item.isdir():
                directories.add(name)
            else:
                require(name != prefix, "Source archive root must be a directory")
                stream = archive.extractfile(item)
                require(stream is not None, "Source archive file is unreadable")
                files[name.removeprefix(prefix + "/")] = stream.read()
        full_files = {prefix + "/" + name for name in files}
        require(directories.issubset(expected_parents(full_files)), "Unreviewed archive directory")
    return files


def config(data: bytes) -> configparser.ConfigParser:
    result = configparser.ConfigParser(interpolation=None)
    result.read_string(data.decode("utf-8"))
    return result


def entrypoint(data: bytes) -> None:
    record = config(data)
    require(record.defaults() == {} and record.sections() == ["console_scripts"]
            and dict(record["console_scripts"]) == {"consequa-x": "consequa_x.cli:main"},
            "Generated console entrypoint differs")


def metadata_record(data: bytes, project: dict, readme: bytes) -> dict:
    record = BytesParser().parsebytes(data)
    for name, expected in {"Name": "consequa-x", "Version": project["version"],
                           "Requires-Python": ">=3.11", "License-Expression": "MIT",
                           "Description-Content-Type": "text/markdown"}.items():
        require(record.get_all(name) == [expected], "Generated distribution metadata differs")
    require(record.get_all("License-File") == ["LICENSE"], "Generated license metadata differs")
    description = data.replace(b"\r\n", b"\n").partition(b"\n\n")[2]
    require(description.rstrip(b"\n") == readme.replace(b"\r\n", b"\n").rstrip(b"\n"),
            "Generated package description differs from reviewed README")
    urls = {}
    for item in record.get_all("Project-URL", []):
        label, separator, value = item.partition(",")
        require(bool(separator) and label.strip() not in urls, "Duplicate/malformed metadata URL")
        urls[label.strip()] = value.strip()
    require(urls == project["urls"], "Generated project URLs differ from reviewed source")
    expected = {f'{dependency};extra=="{extra}"'
                for extra, dependencies in project.get("optional-dependencies", {}).items()
                for dependency in dependencies}
    actual = record.get_all("Requires-Dist", [])
    def normalize(value):
        return re.sub(r"\s+", "", value)

    require(len(actual) == len(expected) and len(actual) == len(set(actual))
            and {normalize(item) for item in actual}
            == {normalize(item) for item in expected},
            "Generated dependencies differ or add required runtime dependencies")
    require(set(record.get_all("Provides-Extra", []))
            == set(project.get("optional-dependencies", {})), "Generated extras differ")
    return {"name": record["Name"], "version": record["Version"],
            "requires_python": record["Requires-Python"], "license": record["License-Expression"],
            "runtime_dependencies": 0, "project_urls": urls}


def audit(wheel: Path, sdist: Path, source_root: Path, version: str, revision: str) -> dict:
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+", version)), "Expected version must be stable")
    require(bool(re.fullmatch(r"[a-f0-9]{40}", revision)), "A full frozen source revision is required")
    require(wheel.name == f"consequa_x-{version}-py3-none-any.whl"
            and sdist.name == f"consequa_x-{version}.tar.gz", "Release artifact basenames differ")
    sources, project = source_files(source_root, version)
    git_verified = False
    if (source_root / ".git").exists():
        def git(*arguments):
            result = subprocess.run(["git", "-C", str(source_root), *arguments],
                                    capture_output=True, text=True, check=False, timeout=60)
            require(result.returncode == 0, "Source Git revision/tracked-byte verification failed")
            return result.stdout.strip()

        require(git("rev-parse", "HEAD") == revision, "Source revision differs from actual Git HEAD")
        git("ls-files", "--error-unmatch", "--", *sorted(sources))
        git("diff", "--quiet", revision, "--", *sorted(sources))
        git_verified = True
    wheel_data, sdist_data = wheel_files(wheel), sdist_files(sdist, version)
    dist = f"consequa_x-{version}.dist-info/"
    egg = "src/consequa_x.egg-info/"
    runtime = {name.removeprefix("src/"): value for name, value in sources.items()
               if name.startswith("src/consequa_x/")}
    expected_wheel = set(runtime) | {dist + name for name in DIST_NAMES}
    expected_sdist = set(sources) | {"PKG-INFO", "setup.cfg"} | {egg + name for name in EGG_NAMES}
    require(set(wheel_data) == expected_wheel, "Wheel inventory differs from exact allowlist")
    require(set(sdist_data) == expected_sdist, "Source archive inventory differs from exact allowlist")
    require(all(wheel_data[name] == data for name, data in runtime.items()),
            "Wheel runtime payload differs from reviewed source")
    require(all(sdist_data[name] == data for name, data in sources.items()),
            "Source archive payload differs from reviewed source")
    require(wheel_data[dist + "licenses/LICENSE"] == sources["LICENSE"],
            "Wheel license differs from reviewed MIT source")
    metadata = metadata_record(wheel_data[dist + "METADATA"], project, sources["README.md"])
    metadata_record(sdist_data["PKG-INFO"], project, sources["README.md"])
    metadata_record(sdist_data[egg + "PKG-INFO"], project, sources["README.md"])
    for payload in (wheel_data[dist + "entry_points.txt"], sdist_data[egg + "entry_points.txt"]):
        entrypoint(payload)
    for payload in (wheel_data[dist + "top_level.txt"], sdist_data[egg + "top_level.txt"]):
        require(payload.decode("utf-8").strip() == "consequa_x", "Generated top-level package differs")
    require(not sdist_data[egg + "dependency_links.txt"].strip(), "Unexpected dependency links")
    requirements = sdist_data[egg + "requires.txt"].decode("utf-8").strip().splitlines()
    expected_requirements = []
    for extra, dependencies in project.get("optional-dependencies", {}).items():
        expected_requirements.extend([f"[{extra}]", *dependencies])
    require([line.strip() for line in requirements if line.strip()] == expected_requirements,
            "Generated source dependencies differ")
    source_list = sdist_data[egg + "SOURCES.txt"].decode("utf-8").splitlines()
    require(len(source_list) == len(set(source_list)) and set(source_list)
            == expected_sdist - {"PKG-INFO", "setup.cfg"}, "Generated source listing differs")
    setup = config(sdist_data["setup.cfg"])
    require(setup.defaults() == {} and setup.sections() == ["egg_info"]
            and dict(setup["egg_info"]) == {"tag_build": "", "tag_date": "0"},
            "Unreviewed generated setup configuration")
    wheel_metadata = BytesParser().parsebytes(wheel_data[dist + "WHEEL"])
    require(wheel_metadata.get_all("Wheel-Version") == ["1.0"]
            and wheel_metadata.get_all("Root-Is-Purelib") == ["true"]
            and wheel_metadata.get_all("Tag") == ["py3-none-any"], "Wheel format/platform differs")
    rows = list(csv.reader(io.StringIO(wheel_data[dist + "RECORD"].decode("utf-8"))))
    require(all(len(row) == 3 for row in rows), "Malformed wheel RECORD")
    require(len(rows) == len({row[0] for row in rows})
            and {row[0] for row in rows} == expected_wheel, "Wheel RECORD inventory differs")
    for name, digest, size in rows:
        if name == dist + "RECORD":
            require(digest == size == "", "Wheel RECORD must not hash itself")
        else:
            data = wheel_data[name]
            expected_digest = base64.urlsafe_b64encode(sha256(data).digest()).decode().rstrip("=")
            require(digest == "sha256=" + expected_digest and size == str(len(data)),
                    "Wheel RECORD hash or size differs")
    source_records = [{"path": name, "bytes": len(data), "sha256": sha256(data).hexdigest()}
                      for name, data in sorted(sources.items())]
    source_digest = sha256(json.dumps(source_records, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
    return {"passed": True, "distribution": "consequa-x", "version": version,
            "source_revision": revision, "source_root": str(source_root.resolve()),
            "source_revision_git_verified": git_verified,
            "source_revision_scope": ("Actual Git HEAD; all reviewed source paths tracked and unchanged"
                                      if git_verified else
                                      "Caller-declared revision outside Git; hashes bind actual files"),
            "source_inventory_sha256": source_digest, "source_files": source_records,
            "runtime_files": len(runtime), "wheel_files": len(wheel_data),
            "sdist_files": len(sdist_data), "metadata": metadata,
            "checks": {"exact_inventory": True, "source_bytes_match": True,
                       "unsafe_paths_and_links_refused": True, "wheel_record_integrity": True,
                       "metadata_and_entrypoint": True, "network_access": False},
            "artifacts": [{"filename": path.name, "bytes": path.stat().st_size,
                           "sha256": sha256(path.read_bytes()).hexdigest()}
                          for path in (wheel, sdist)],
            "auditor_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(not args.output.exists() and not args.output.is_symlink(),
            "Keep previous audit receipts; choose a new output")
    receipt = audit(args.wheel, args.sdist, args.source_root,
                    args.expected_version, args.source_revision)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: receipt[key] for key in ("passed", "version", "runtime_files",
                                                  "wheel_files", "sdist_files")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
