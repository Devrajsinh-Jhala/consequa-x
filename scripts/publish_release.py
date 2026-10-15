"""Publish only the reviewed stable Consequa-X wheel and source distribution."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import urlopen

SERVICE = "https://upload.pypi.org/legacy/"
REQUIRED_CHECKS = frozenset({"source_tests", "lint", "strict_metadata", "artifact_inventory",
    "wheel_install_smoke", "sdist_install_smoke", "python311_conformance", "release_helper_tests"})


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON field in release receipt")
        result[key] = value
    return result


def checked_files(receipt_path):
    receipt_path = Path(receipt_path).resolve()
    record = json.loads(receipt_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    version = record["version"]
    if (record["distribution"] != "consequa-x" or type(version) is not str
            or re.fullmatch(r"\d+\.\d+\.\d+", version) is None):
        raise ValueError("Receipt must identify a stable Consequa-X release")
    if re.fullmatch(r"[a-f0-9]{40}", record["source_revision"]) is None:
        raise ValueError("Receipt requires a full frozen Git source revision")
    checks = record["local_checks"]
    if not REQUIRED_CHECKS.issubset(checks) or any(value is not True for value in checks.values()):
        raise ValueError("All named release checks must pass")
    expected = {f"consequa_x-{version}-py3-none-any.whl", f"consequa_x-{version}.tar.gz"}
    files = []
    for item in record["artifacts"]:
        if item["path"] not in expected:
            raise ValueError("Release artifact must use its reviewed basename")
        path = (receipt_path.parent/item["path"]).resolve()
        if not path.is_relative_to(receipt_path.parent):
            raise ValueError("Release artifact escapes its reviewed directory")
        if (type(item["bytes"]) is not int or item["bytes"] <= 0
                or path.stat().st_size != item["bytes"]
                or sha256(path.read_bytes()).hexdigest() != item["sha256"]):
            raise ValueError("Release artifact differs from the reviewed bytes")
        files.append(path)
    if len(files) != 2 or {path.name for path in files} != expected:
        raise ValueError("Receipt requires exactly the reviewed wheel and source distribution")
    return record, files


def published_files(version):
    url = f"https://pypi.org/pypi/consequa-x/{version}/json?verification={time.time_ns()}"
    try:
        with urlopen(url, timeout=30) as response:
            record = json.load(response)
        if record["info"]["name"] != "consequa-x" or record["info"]["version"] != version:
            raise ValueError("Registry metadata identifies another project or version")
        return record["urls"]
    except HTTPError as error:
        if error.code == 404:
            return []
        raise


def reviewed_names(record, existing):
    expected = {item["path"]: item for item in record["artifacts"]}
    names = set()
    for item in existing:
        name = item["filename"]
        if (name in names or name not in expected
                or item["digests"]["sha256"] != expected[name]["sha256"]
                or item["size"] != expected[name]["bytes"]):
            raise ValueError("Published release differs from the reviewed files")
        names.add(name)
    return names


def upload(receipt_path, *, account="devraj0502"):
    record, files = checked_files(receipt_path)
    names = reviewed_names(record, published_files(record["version"]))
    missing = [path for path in files if path.name not in names]
    if not missing:
        print("Both reviewed stable files are already published on PyPI.")
        return 0
    import keyring
    token = keyring.get_password(SERVICE, account)
    if not token or not token.startswith("pypi-"):
        raise RuntimeError("Local upload authentication is not configured")
    environment = os.environ.copy()
    environment.update(TWINE_USERNAME="__token__", TWINE_PASSWORD=token)
    result = subprocess.run([sys.executable, "-m", "twine", "upload", "--non-interactive",
        "--disable-progress-bar", "--repository-url", SERVICE, *(str(path) for path in missing)],
        env=environment, check=False).returncode
    if result:
        return result
    for attempt in range(10):
        if reviewed_names(record, published_files(record["version"])) == {path.name for path in files}:
            print("Production PyPI publishes both reviewed stable artifact hashes and sizes.")
            return 0
        if attempt < 9:
            time.sleep(2)
    raise RuntimeError("Upload accepted; public verification pending. Rerun to verify without replacing files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--account", default="devraj0502")
    args = parser.parse_args()
    raise SystemExit(upload(args.receipt, account=args.account))
