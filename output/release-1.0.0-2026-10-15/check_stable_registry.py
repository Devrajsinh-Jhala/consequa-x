"""Verify published metadata and download both exact reviewed files."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

root = next(parent for parent in Path(__file__).resolve().parents
            if (parent / ".git").exists() and (parent / "pyproject.toml").is_file())
release = root / "output/release-1.0.0-2026-10-15"
checks = json.loads((release / "checks.json").read_text())
records = []
for url in ("https://pypi.org/pypi/consequa-x/1.0.0/json",
            "https://pypi.org/pypi/Consequa-X/1.0.0/json",
            "https://pypi.org/pypi/consequa-x/json"):
    try:
        request = Request(url, headers={"Cache-Control": "no-cache", "Accept": "application/json"})
        with urlopen(request, timeout=30) as response:
            record = json.load(response)
        assert record["info"]["name"] == "consequa-x" and record["info"]["version"] == "1.0.0"
        records.append((url, record))
    except HTTPError as error:
        if error.code != 404:
            raise
        print(f"Metadata endpoint still returns 404: {url}")
assert records, "Wait for public JSON metadata; do not upload again"
url, record = records[0]
expected = {item["path"]: item for item in checks["artifacts"]}
assert len(record["urls"]) == len(expected) == 2
files = []
downloads = root / "tmp/stable-registry-downloads"
downloads.mkdir(exist_ok=True)
for item in record["urls"]:
    reviewed = expected[item["filename"]]
    assert item["digests"]["sha256"] == reviewed["sha256"] and item["size"] == reviewed["bytes"]
    parsed = urlparse(item["url"])
    assert parsed.scheme == "https" and parsed.hostname == "files.pythonhosted.org"
    with urlopen(item["url"], timeout=45) as response:
        content = response.read()
    assert len(content) == reviewed["bytes"] and sha256(content).hexdigest() == reviewed["sha256"]
    path = downloads / item["filename"]
    if path.exists():
        assert path.read_bytes() == content
    else:
        path.write_bytes(content)
    files.append({**reviewed, "url": item["url"], "independent_download_verified": True})
receipt = {"status": "published_and_download_verified", "distribution": "consequa-x",
    "version": "1.0.0", "source_revision": checks["source_revision"],
    "verified_at_utc": datetime.now(timezone.utc).isoformat(), "metadata_url": url,
    "files": files, "checks_sha256": sha256((release / "checks.json").read_bytes()).hexdigest(),
    "note": "Initial upload accepted; early version JSON endpoint was cached404. No duplicate upload used."}
path = release / "publication.json"
assert not path.exists()
path.write_text(json.dumps(receipt, indent=2, sort_keys=True)+"\n", encoding="utf-8")
print(json.dumps(receipt))
