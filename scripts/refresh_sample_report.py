"""Regenerate the website's sample report from the package in this checkout.

The website embeds the exact HTML that ``consequa-x report`` writes for the
demo's ``episode_01`` trace, plus a deterministic ZIP of the same bytes. Run
this after any change to the report renderer, then run
``scripts/build_site_demo.py`` to refresh the recorded demo data. It updates
``website/dist/assets/sample-report.html``, ``sample-report.zip`` and the pinned
SHA-256 in ``scripts/export_render_site.py`` and ``website/README.md``.
"""

from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "website" / "dist" / "assets"
ZIP_DATE = (2026, 10, 18, 0, 0, 0)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="consequa-sample-report-") as workdir:
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        for arguments in (("demo", "--output", "my-demo"),
                          ("report", "my-demo/traces/episode_01.json", "--output", "my-report.html")):
            subprocess.run([sys.executable, "-B", "-m", "consequa_x", *arguments], cwd=workdir,
                           env=environment, capture_output=True, check=True)
        report = (Path(workdir) / "my-report.html").read_bytes()
    (ASSETS / "sample-report.html").write_bytes(report)
    info = zipfile.ZipInfo("my-report.html", date_time=ZIP_DATE)
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(ASSETS / "sample-report.zip", "w") as archive:
        archive.writestr(info, report, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = sha256(report).hexdigest()
    for path in (ROOT / "scripts" / "export_render_site.py", ROOT / "website" / "README.md"):
        text = path.read_text(encoding="utf-8")
        updated = re.sub(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])",
                         lambda match: digest if match.group(0) == _pinned(text) else match.group(0),
                         text)
        path.write_text(updated, encoding="utf-8", newline="\n")
    print(f"sample-report.html sha256 {digest}")
    return 0


def _pinned(text: str) -> str:
    match = re.search(r'REPORT_HTML_SHA256 = "([0-9a-f]{64})"', text) or re.search(
        r"SHA-256\s*`([0-9a-f]{64})`", text)
    if match is None:
        raise SystemExit("Cannot find the pinned sample report SHA-256")
    return match.group(1)


if __name__ == "__main__":
    raise SystemExit(main())
