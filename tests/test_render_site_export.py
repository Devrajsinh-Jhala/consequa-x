"""Publication boundaries for the site-only Render export, with no network."""

import importlib.util
from io import BytesIO
from pathlib import Path
import zipfile

import pytest


SPEC = importlib.util.spec_from_file_location(
    "render_export", Path(__file__).resolve().parents[1] / "scripts/export_render_site.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
REVISION = "f9a02ccd31050bbe4053f357fcf8c083bae1e589"


@pytest.fixture(scope="module")
def public_data():
    return {name: exporter.checked_file(exporter.ROOT, name) for name in exporter.ALLOWLIST}


@pytest.fixture
def source(tmp_path, monkeypatch, public_data):
    for name, content in public_data.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    helper = tmp_path / "scripts/export_render_site.py"
    helper.parent.mkdir()
    helper.write_bytes(Path(exporter.__file__).read_bytes())
    readme = exporter.checked_file(exporter.ROOT, "website/README.md")
    (tmp_path / "website/README.md").write_bytes(readme)
    (tmp_path / "output").mkdir()
    monkeypatch.setattr(exporter, "git", lambda *args: REVISION.encode("ascii"))
    monkeypatch.setattr(exporter, "committed_data", lambda *args: public_data)
    monkeypatch.setattr(exporter, "allowlist_document", lambda *args: readme)
    return tmp_path


def test_export_ignores_unapproved_files_and_refuses_overwrite(source):
    secret = b"test-only private canary 48019"
    (source / "private-research.pdf").write_bytes(secret)
    (source / "website/dist/unreviewed.txt").write_bytes(secret)
    (source / ".git").mkdir()
    (source / ".git/history").write_bytes(secret)
    output = source / "output/site-only"
    receipt = exporter.export_site(source, output, REVISION)
    blob = (output / exporter.ARCHIVE_NAME).read_bytes()
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        assert archive.namelist() == sorted(exporter.ALLOWLIST)
        assert len(archive.infolist()) == 26
        assert not any(secret in archive.read(name) for name in archive.namelist())
    assert receipt["deployment"] == {
        "performed": False, "render_url": None, "github_actions_used": False}
    assert exporter.verify_export(source, output) == receipt
    with pytest.raises(ValueError, match="Existing output"):
        exporter.export_site(source, output, REVISION)
    assert (output / exporter.ARCHIVE_NAME).read_bytes() == blob


def test_uncommitted_replacement_stops_before_output_creation(source):
    (source / "website/dist/index.html").write_text("private replacement", encoding="utf-8")
    output = source / "output/blocked"
    with pytest.raises(ValueError, match="uncommitted changes"):
        exporter.export_site(source, output, REVISION)
    assert not output.exists()


def test_missing_or_external_resource_is_refused(public_data):
    for injection, reason in (
        ('<img src="unreviewed.txt">', "outside public allowlist"),
        ('<script src="https://example.invalid/remote.js"></script>', "External resource"),
        ('<a href="../private-research.pdf">source</a>', "Parent resource paths"),
    ):
        changed = dict(public_data)
        changed["website/dist/index.html"] += injection.encode("utf-8")
        with pytest.raises(ValueError, match=reason):
            exporter.validate_references(changed)


@pytest.mark.parametrize("path,reason", [
    ("website/dist/quickstart.zip", "Unexpected quickstart ZIP member"),
    ("website/dist/assets/sample-report.zip", "Unexpected report ZIP member"),
])
def test_unexpected_nested_download_member_is_refused(public_data, path, reason):
    changed = dict(public_data)
    buffer = BytesIO(public_data[path])
    with zipfile.ZipFile(buffer, "a") as archive:
        archive.writestr("private-research.pdf", "test-only canary")
    changed[path] = buffer.getvalue()
    with pytest.raises(ValueError, match=reason):
        exporter.validate_types(changed)


def test_report_download_refuses_changed_html(public_data):
    changed = dict(public_data)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        item = zipfile.ZipInfo("my-report.html", date_time=exporter.ZIP_DATE)
        item.create_system = 3
        item.external_attr = 0o100644 << 16
        item.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(item, public_data["website/dist/assets/sample-report.html"]
                         + b"<script>testOnlyInjectedScript()</script>", compresslevel=9)
    changed["website/dist/assets/sample-report.zip"] = buffer.getvalue()
    with pytest.raises(ValueError, match="changed original package HTML bytes"):
        exporter.validate_types(changed)


def test_directory_input_is_refused(tmp_path):
    (tmp_path / "approved.txt").mkdir()
    with pytest.raises(ValueError, match="not a regular file"):
        exporter.checked_file(tmp_path, "approved.txt")


def test_link_input_is_refused(tmp_path):
    (tmp_path / "private.txt").write_text("test-only canary", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        link.symlink_to(tmp_path / "private.txt")
    except OSError:
        pytest.skip("Host does not permit creating a symbolic link")
    with pytest.raises(ValueError, match="links are refused"):
        exporter.checked_file(tmp_path, "linked.txt")
