"""The homepage demo shows recorded package output, never hand-written outcomes."""

from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("site_demo_builder", "scripts/build_site_demo.py")
exporter = load("render_export_for_demo", "scripts/export_render_site.py")


def committed_data():
    text = builder.OUTPUT.read_text(encoding="utf-8")
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


class ResultsTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.rows = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table" and "data-results-table" in dict(attrs):
            self.inside = True
        elif self.inside and tag == "tr":
            self.rows.append([])
        elif self.inside and tag == "td":
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.inside = False
        elif self.inside and tag == "td":
            self.rows[-1].append(" ".join("".join(self.cell).split()))
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data + " ")


def test_committed_demo_data_matches_a_fresh_package_run():
    assert builder.OUTPUT.read_text(encoding="utf-8") == builder.build()


def test_homepage_results_table_matches_explain_output():
    parser = ResultsTable()
    parser.feed((ROOT / "website/dist/index.html").read_text(encoding="utf-8"))
    rows = [row for row in parser.rows if row]
    expected = [[item["scenario"], ", ".join(item["response"]), item["assessment"],
                 item["explanation"]["state"], item["explanation"]["origin"],
                 item["explanation"]["alignment"], " ".join(item["explanation"]["diagnoses"])]
                for item in committed_data()["scenarios"]]
    assert rows == expected


def test_demo_terminal_records_the_report_that_the_site_serves():
    data = committed_data()
    assert data["report"]["sha256"] == exporter.REPORT_HTML_SHA256
    assert data["terminal"][-1]["output"] == ["Saved offline report to my-report.html"]
    printed = [line for step in data["terminal"] for line in step["output"]]
    assert not any(re.search(r"[A-Za-z]:[\\/]|/tmp/|consequa-site-demo-", line) for line in printed)


def test_homepage_fallback_text_matches_the_recorded_run():
    # Script replaces these on load; crawlers, slow loads and no-JS visitors see the markup.
    data = committed_data()
    page = (ROOT / "website/dist/index.html").read_text(encoding="utf-8")
    versions = re.findall(r"<span data-version>([^<]*)</span>", page)
    hashes = re.findall(r"<code data-report-hash>([^<]*)</code>", page)
    assert versions and set(versions) == {data["package_version"]}
    assert hashes == [data["report"]["sha256"][:12] + "…"]


def test_public_pages_reference_only_allowlisted_assets():
    public = {name: exporter.checked_file(ROOT, name) for name in exporter.ALLOWLIST}
    exporter.validate_types(public)
    checks = exporter.validate_references(public)
    assert checks["external_resource_references"] == 0
    index = public["website/dist/index.html"].decode("utf-8")
    assert "assets/demo-data.js" in index and "package-demo" not in index
