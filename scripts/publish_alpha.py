"""Upload only the reviewed alpha files after verifying their receipt hashes."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import urlopen


SERVICE = "https://upload.pypi.org/legacy/"
REQUIRED_CHECKS = frozenset({
    "source_tests", "lint", "strict_metadata", "artifact_inventory",
    "wheel_install_smoke", "sdist_install_smoke", "release_helper_tests",
})


def checked_files(receipt_path):
    receipt_path = Path(receipt_path).resolve()
    record = json.loads(receipt_path.read_text(encoding="utf-8"))
    if record["distribution"] != "consequa-x" or record["version"] != "0.1.0a2":
        raise ValueError("Receipt must identify the reviewed Consequa-X alpha 2")
    checks = record["local_checks"]
    if not REQUIRED_CHECKS.issubset(checks) or any(value is not True for value in checks.values()):
        raise ValueError("All local release checks must pass before upload")
    expected = {"consequa_x-0.1.0a2-py3-none-any.whl", "consequa_x-0.1.0a2.tar.gz"}
    files = []
    for item in record["artifacts"]:
        if item["path"] not in expected:
            raise ValueError("Receipt must use the reviewed artifact filenames directly")
        path = (receipt_path.parent/item["path"]).resolve()
        if not path.is_relative_to(receipt_path.parent) or path.name not in expected:
            raise ValueError("Release file path is outside the reviewed artifact directory")
        if sha256(path.read_bytes()).hexdigest() != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError("Release artifact bytes differ from the reviewed receipt")
        files.append(path)
    if len(files) != 2 or {path.name for path in files} != expected:
        raise ValueError("Receipt must contain exactly the reviewed wheel and source distribution")
    return record, files


def published_files():
    try:
        with urlopen("https://pypi.org/pypi/consequa-x/0.1.0a2/json", timeout=30) as response:
            return json.load(response)["urls"]
    except HTTPError as error:
        if error.code == 404:
            return []
        raise


def reviewed_registry_files(record, existing):
    expected = {item["path"]: item["sha256"] for item in record["artifacts"]}
    for item in existing:
        if item["filename"] not in expected or item["digests"]["sha256"] != expected[item["filename"]]:
            raise ValueError("Published version differs from the reviewed artifacts; refusing upload")
    names = [item["filename"] for item in existing]
    if len(names) != len(set(names)):
        raise ValueError("Published version contains duplicate artifact filenames")
    return set(names)


def upload(receipt_path, *, account="devraj0502"):
    record, files = checked_files(receipt_path)
    names = reviewed_registry_files(record, published_files())
    missing = [path for path in files if path.name not in names]
    if not missing:
        print("The reviewed alpha files are already published on PyPI.")
        return 0
    import keyring
    token = keyring.get_password(SERVICE, account)
    if not token or not token.startswith("pypi-"):
        raise RuntimeError(f"Local PyPI upload authentication is not configured for {account}")
    environment = os.environ.copy()
    environment.update(TWINE_USERNAME="__token__", TWINE_PASSWORD=token)
    result = subprocess.run([sys.executable, "-m", "twine", "upload", "--non-interactive",
        "--disable-progress-bar", "--repository-url", SERVICE, *(str(path) for path in missing)],
        env=environment, check=False).returncode
    if result:
        return result
    for attempt in range(6):
        names = reviewed_registry_files(record, published_files())
        if names == {path.name for path in files}:
            print("Production PyPI publishes both reviewed artifact hashes.")
            return 0
        if attempt < 5:
            time.sleep(2)
    raise RuntimeError("Upload accepted, but public hash verification is pending; rerun to verify")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--account", default="devraj0502")
    args = parser.parse_args()
    raise SystemExit(upload(args.receipt, account=args.account))
