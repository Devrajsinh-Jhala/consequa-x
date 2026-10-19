"""Export the reviewed public site only; never copy a repository or deploy it.

The ZIP contains exactly ALLOWLIST. Its separate manifest records the committed
input revision and helper hash. No directory scan selects publication inputs.
"""

import argparse
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_NAME = "consequa-x-render-site.zip"
ZIP_DATE = (2026, 10, 18, 0, 0, 0)
ALLOWLIST = (
    "render.yaml",
    "website/dist/index.html",
    "website/dist/docs.html",
    "website/dist/support.html",
    "website/dist/security.html",
    "website/dist/changelog.html",
    "website/dist/styles.css",
    "website/dist/docs.css",
    "website/dist/app.js",
    "website/dist/favicon.svg",
    "website/dist/robots.txt",
    "website/dist/sitemap.xml",
    "website/dist/quickstart.zip",
    "website/dist/assets/demo-data.js",
    "website/dist/assets/sample-report.html",
    "website/dist/assets/sample-report.zip",
    "website/dist/examples/agent_loop_sqlite.py",
    "website/dist/examples/artifact_delivery.py",
    "website/dist/examples/report_quickstart.py",
    "website/dist/fonts/README.md",
    "website/dist/fonts/SpaceGrotesk-Variable.ttf",
    "website/dist/fonts/SpaceGrotesk-OFL.txt",
    "website/dist/fonts/Manrope-Variable.ttf",
    "website/dist/fonts/Manrope-OFL.txt",
    "website/dist/fonts/JetBrainsMono-Variable.ttf",
    "website/dist/fonts/JetBrainsMono-OFL.txt",
)
TEXT_SUFFIXES = {".html", ".css", ".js", ".svg", ".txt", ".xml", ".py", ".md", ".yaml"}
ZIP_METADATA = {"timestamp": list(ZIP_DATE), "mode": "100644", "create_system": "unix",
                "compression": "deflate-9", "member_order": "lexicographic"}
REPORT_HTML_SHA256 = "5ca06033bdaad60615c28bb23eed6c83a61099cf96b9e05c5f018e9bedcf0ed4"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return sha256(data).hexdigest()


def checked_file(root, name):
    """Read one named regular file, rejecting symbolic links and junctions."""
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.parts
            and all(part not in {".", "..", ""} for part in relative.parts)
            and "\\" not in name and ":" not in name, "Unsafe input path")
    path = root.joinpath(*relative.parts)
    for component in (root, *[root.joinpath(*relative.parts[:i])
                             for i in range(1, len(relative.parts) + 1)]):
        require(not component.is_symlink()
                and not getattr(component, "is_junction", lambda: False)(),
                "Input links are refused: " + name)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "Input is not a regular file: " + name)
    require(path.resolve(strict=True).is_relative_to(root), "Input escapes source root")
    data = path.read_bytes()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "Input changed while being read: " + name)
    require(data, "Empty input: " + name)
    return data


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def committed_data(root, revision):
    require(re.fullmatch(r"[0-9a-f]{40,64}", revision), "Expected a full source commit")
    result = {}
    for name in ALLOWLIST:
        entry = git(root, "ls-tree", revision, "--", name).decode("utf-8").strip()
        require(entry.startswith("100644 blob ") and entry.endswith("\t" + name),
                "Source commit lacks an ordinary approved file: " + name)
        result[name] = git(root, "show", revision + ":" + name)
    return result


def allowlist_document(root, revision):
    document = git(root, "show", revision + ":website/README.md")
    match = re.search(r"The current public asset allowlist is:\s*```text\n(.*?)```",
                      document.decode("utf-8"), re.DOTALL)
    require(match and tuple(match[1].strip().splitlines()) == ALLOWLIST,
            "Explicit helper allowlist differs from the source README allowlist")
    return document


def validate_types(data):
    for name, content in data.items():
        suffix = PurePosixPath(name).suffix
        if suffix in TEXT_SUFFIXES:
            text = content.decode("utf-8")
            require("\x00" not in text, "NUL in public text: " + name)
            if suffix == ".html":
                require(text.lstrip().lower().startswith("<!doctype html>"),
                        "HTML declaration missing: " + name)
            elif suffix in {".svg", ".xml"}:
                require("<!DOCTYPE" not in text.upper() and "<!ENTITY" not in text.upper(),
                        "XML document types/entities are refused")
                ElementTree.fromstring(text)
        elif suffix == ".png":
            require(content.startswith(b"\x89PNG\r\n\x1a\n")
                    and content[12:16] == b"IHDR" and len(content) > 33,
                    "PNG header differs: " + name)
        elif suffix == ".gif":
            require(content[:6] in {b"GIF87a", b"GIF89a"}
                    and len(content) > 13 and content[-1:] == b";",
                    "GIF header/trailer differs: " + name)
        elif suffix == ".ttf":
            require(content.startswith(b"\x00\x01\x00\x00") and len(content) > 12,
                    "TrueType header differs: " + name)
        elif suffix != ".zip":
            raise ValueError("Unapproved file type: " + name)
    with zipfile.ZipFile(BytesIO(data["website/dist/quickstart.zip"])) as archive:
        expected = {"LICENSE", "README.md", "agent_loop_sqlite.py", "artifact_delivery.py",
                    "report_quickstart.py"}
        require(len(archive.infolist()) == len(expected)
                and set(archive.namelist()) == expected, "Unexpected quickstart ZIP member")
        for item in archive.infolist():
            require(not item.is_dir() and not item.flag_bits & 1
                    and stat.S_IFMT(item.external_attr >> 16) in {0, stat.S_IFREG}
                    and item.file_size <= 1_000_000, "Unsafe quickstart ZIP member")
            content = archive.read(item)
            content.decode("utf-8")
            if item.filename.endswith(".py"):
                require(content == data["website/dist/examples/" + item.filename],
                        "Quickstart example differs from public example")
        require(archive.testzip() is None, "Quickstart ZIP CRC failed")
    with zipfile.ZipFile(BytesIO(data["website/dist/assets/sample-report.zip"])) as archive:
        require(archive.namelist() == ["my-report.html"], "Unexpected report ZIP member")
        item = archive.infolist()[0]
        require(item.date_time == ZIP_DATE and item.create_system == 3
                and item.external_attr == 0o100644 << 16
                and item.compress_type == zipfile.ZIP_DEFLATED
                and not item.extra and not item.comment and not archive.comment
                and not item.flag_bits & 1 and item.file_size <= 1_000_000,
                "Unsafe report ZIP member or non-deterministic metadata")
        report = archive.read(item)
        require(report == data["website/dist/assets/sample-report.html"]
                and digest(report) == REPORT_HTML_SHA256,
                "Report ZIP changed original package HTML bytes")
        require(archive.testzip() is None, "Report ZIP CRC failed")
    config = data["render.yaml"].decode("utf-8")
    expected_config = ["services:", "  - type: web", "    name: consequa-x",
                       "    runtime: static", "    rootDir: website", '    buildCommand: "true"',
                       "    staticPublishPath: dist", '    autoDeployTrigger: "commit"']
    require([line for line in config.splitlines() if line.strip() and not line.startswith("#")]
            == expected_config, "Render configuration differs from reviewed static-only settings")


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
        self.styles = []
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        require(tag != "base" and "srcset" not in values,
                "Review reference handling before adding base/srcset")
        if "id" in values:
            require(values["id"] not in self.ids, "Duplicate public HTML ID")
            self.ids.add(values["id"])
        for key in ("href", "src", "data-animation", "data-poster", "xlink:href"):
            if key in values:
                self.links.append((values[key], tag == "a" and key == "href"))
        if "style" in values:
            self.styles.append(values["style"])
        if tag == "style":
            self.in_style = True

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False

    def handle_data(self, value):
        if self.in_style:
            self.styles.append(value)


def css_references(text):
    require(not re.search(r"@import\b", text, re.IGNORECASE), "CSS imports need explicit review")
    return [(match[1].strip().strip("\"'"), False)
            for match in re.finditer(r"url\(\s*(.*?)\s*\)", text, re.IGNORECASE)]


def validate_references(data):
    pages = {}
    links = []
    for name, content in data.items():
        if name.endswith(".html"):
            page = References()
            page.feed(content.decode("utf-8"))
            pages[name] = page
            links.extend((name, ref, navigation) for ref, navigation in page.links)
            for style in page.styles:
                links.extend((name, ref, False) for ref, _ in css_references(style))
        elif name.endswith(".css"):
            links.extend((name, ref, False)
                         for ref, _ in css_references(content.decode("utf-8")))
    checked = 0
    external_navigation = 0
    for source, ref, navigation in links:
        parsed = urlsplit(ref)
        if parsed.scheme or parsed.netloc:
            require(navigation and parsed.scheme in {"https", "http", "mailto"},
                    "External resource or unsupported URL: " + source)
            external_navigation += 1
            continue
        path = unquote(parsed.path)
        require("\\" not in path and "\x00" not in path and ":" not in path,
                "Unsafe resource path: " + source)
        parts = PurePosixPath(path).parts
        require(".." not in parts, "Parent resource paths need explicit review: " + source)
        if path.startswith("/"):
            target = "website/dist/" + path.lstrip("/")
        elif path:
            target = str(PurePosixPath(source).parent / path)
        else:
            target = source
        if target.endswith("/"):
            target += "index.html"
        require(target in data, "Resource is outside public allowlist: " + target)
        if parsed.fragment:
            require(target in pages and unquote(parsed.fragment) in pages[target].ids,
                    "Missing public fragment: " + ref + " in " + source)
        checked += 1
    return {"local_references_checked": checked,
            "external_navigation_links": external_navigation,
            "external_resource_references": 0}


def archive_bytes(data):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name in sorted(ALLOWLIST):
            item = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, data[name], compresslevel=9)
    return buffer.getvalue()


def verify_export(root, output):
    manifest = json.loads(checked_file(output, "manifest.json").decode("utf-8"))
    require(manifest["format"] == "render-site-export-v1"
            and manifest["status"] == "prepared-not-deployed", "Unexpected export manifest")
    require(manifest["deployment"] == {"performed": False, "render_url": None,
                                       "github_actions_used": False}
            and manifest["zip_metadata"] == ZIP_METADATA, "Export status/metadata differs")
    blob = checked_file(output, ARCHIVE_NAME)
    require(manifest["archive"] == {"path": ARCHIVE_NAME, "bytes": len(blob),
                                    "sha256": digest(blob), "member_count": len(ALLOWLIST)},
            "Archive digest or inventory count differs")
    expected = committed_data(root, manifest["source_revision"])
    require(manifest["allowlist_document"] == {"path": "website/README.md", "sha256": digest(
            allowlist_document(root, manifest["source_revision"]))},
            "Allowlist document digest differs")
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        items = archive.infolist()
        require(len(items) == len(ALLOWLIST) and archive.namelist() == sorted(ALLOWLIST),
                "Archive differs from exact public allowlist")
        data = {}
        for item in items:
            require(item.create_system == 3 and item.date_time == ZIP_DATE
                    and item.external_attr == 0o100644 << 16
                    and item.compress_type == zipfile.ZIP_DEFLATED
                    and not item.extra and not item.comment and not item.flag_bits & 1,
                    "Archive metadata differs from fixed regular-file format")
            data[item.filename] = archive.read(item)
        require(not archive.comment and archive.testzip() is None, "Archive integrity failed")
    require(data == expected, "Archive differs from committed approved source files")
    validate_types(data)
    references = validate_references(data)
    require(references == manifest["reference_checks"], "Reference-check receipt differs")
    require(manifest["files"] == [{"path": name, "bytes": len(data[name]),
                                   "sha256": digest(data[name])} for name in sorted(ALLOWLIST)],
            "Per-file manifest differs")
    require(blob == archive_bytes(data), "Archive is not the deterministic approved export")
    require(manifest["helper"] == {"path": "scripts/export_render_site.py",
                                   "sha256": digest(checked_file(root, "scripts/export_render_site.py"))},
            "Helper changed since export; retain the recorded helper version")
    return manifest


def export_site(root, output, expected_source):
    require(not output.exists() and not output.is_symlink(), "Existing output is refused")
    output_parent = output.parent.resolve(strict=True)
    require(output_parent.is_relative_to(root / "output"), "Output must stay under repository output/")
    for parent in (output.parent, *output.parent.parents):
        if parent == root.parent:
            break
        require(not parent.is_symlink() and not getattr(parent, "is_junction", lambda: False)(),
                "Output directory links are refused")
    revision = git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    require(revision == expected_source, "HEAD differs from the explicitly selected source revision")
    document = allowlist_document(root, revision)
    require(checked_file(root, "website/README.md") == document,
            "Allowlist documentation has uncommitted changes")
    data = {name: checked_file(root, name) for name in ALLOWLIST}
    require(data == committed_data(root, revision), "Approved website/config has uncommitted changes")
    validate_types(data)
    references = validate_references(data)
    blob = archive_bytes(data)
    manifest = {
        "format": "render-site-export-v1", "status": "prepared-not-deployed",
        "source_revision": revision,
        "helper": {"path": "scripts/export_render_site.py",
                   "sha256": digest(checked_file(root, "scripts/export_render_site.py"))},
        "archive": {"path": ARCHIVE_NAME, "bytes": len(blob), "sha256": digest(blob),
                    "member_count": len(ALLOWLIST)},
        "zip_metadata": ZIP_METADATA,
        "allowlist_document": {"path": "website/README.md", "sha256": digest(document)},
        "files": [{"path": name, "bytes": len(data[name]), "sha256": digest(data[name])}
                  for name in sorted(ALLOWLIST)],
        "reference_checks": references,
        "deployment": {"performed": False, "render_url": None, "github_actions_used": False},
        "scope": f"Only the {len(ALLOWLIST)} explicit public source files; no Git history or private study inputs.",
    }
    output.mkdir()
    with (output / ARCHIVE_NAME).open("xb") as destination:
        destination.write(blob)
        destination.flush()
        os.fsync(destination.fileno())
    with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as destination:
        destination.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        destination.flush()
        os.fsync(destination.fileno())
    verify_export(root, output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-source", help="Full current HEAD, required for export")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if args.command == "export":
        require(args.expected_source is not None, "Export requires --expected-source")
        manifest = export_site(ROOT, output, args.expected_source)
    else:
        require(args.expected_source is None, "Verification uses the manifest's source revision")
        manifest = verify_export(ROOT, output)
    print(json.dumps({"status": manifest["status"], "archive": manifest["archive"],
                      "source_revision": manifest["source_revision"],
                      "reference_checks": manifest["reference_checks"]}, indent=2))


if __name__ == "__main__":
    main()
