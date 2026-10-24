"""Build an audited, Git-bound final paper with visual review still pending.

The caller must run the PDF authoring marker immediately before invoking this
builder. This script never runs the marker, models, native collectors, network
clients or Git mutations. A passed 96-slot audit can retain failed/unstarted
slots; it does not imply 96 successful executions or tasks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile


DEFAULT_COMPILER = Path("C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tectonic/tectonic.exe")
DEFAULT_POPPLER = Path("C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin")
MAIN = "paper/conseqax-research.tex"
READABLE = "paper/conseqax-research.md"
METHODS = "paper/limbo-native-methods.tex"
ANALYZER = "scripts/analyze_limbo_external_benchmark.py"
OLD_FIGURES = ("recovery-method-overview.pdf", "recovery-family-primary-contrasts.pdf",
               "recovery-availability-grid.pdf")
NEW_FIGURES = ("limbo-outcomes.pdf", "limbo-stratification.pdf", "limbo-costs.pdf")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def byte_binding(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def binding(path):
    digest, count = hashlib.sha256(), 0
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            count += len(chunk)
    return {"sha256": digest.hexdigest(), "bytes": count}


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON: " + value)))


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def command(args, cwd, timeout=120):
    return subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True,
                          check=False, timeout=timeout)


def git(root, *args):
    result = command(["git", "-C", root, *args], root)
    require(result.returncode == 0, "Git read failed: " + result.stderr.decode(errors="replace"))
    return result.stdout


def exact_commit(value, label):
    require(bool(re.fullmatch(r"[0-9a-f]{40}", value)), label + " requires an exact 40-character SHA")
    return value


def safe_member(name):
    require(type(name) is str and name and "\\" not in name and ":" not in name,
            "Unsafe relative artifact path: " + repr(name))
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == name,
            "Unsafe relative artifact path: " + name)
    return path


def check_manifest(directory):
    directory = Path(directory).resolve()
    manifest_path = directory / "manifest.json"
    manifest = load(manifest_path)
    require(type(manifest) is dict and bool(manifest), "Empty artifact manifest")
    actual = set()
    for path in directory.rglob("*"):
        require(not path.is_symlink(), "Symbolic links are not allowed in the sealed analysis")
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(directory).as_posix())
    require(set(manifest) == actual, "Sealed analysis inventory differs")
    for name, expected in manifest.items():
        safe_member(name)
        require(expected == binding(directory / name), "Sealed artifact changed: " + name)
    return {"manifest": binding(manifest_path), "files": manifest}


def committed_file(root, relative, commit):
    safe_member(relative)
    path = root / relative
    require(path.is_file() and not path.is_symlink(), "Missing/nonregular source: " + relative)
    require(path.resolve().is_relative_to(root), "Source leaves repository: " + relative)
    data = path.read_bytes()
    require(git(root, "show", f"{commit}:{relative}") == data,
            "Source bytes differ from explicit Git commit: " + relative)
    return byte_binding(data)


def validate_analysis(root, directory, protocol_path, protocol_commit, source_commit, *, require_figures=True):
    """Recompute all analysis values and generated text from the passed native audit."""
    sealed = check_manifest(directory)
    result = load(directory / "results.json")
    require(result.get("schema") == "conseqax-limbo-analysis-v1", "Unsupported analysis schema")
    for key, expected in (("planned_slots", 96), ("planned_worlds", 24),
                          ("base_instances", 12), ("templates", 12), ("focal_domains", 6)):
        require(type(result.get(key)) is int and result[key] == expected, "Analysis scope differs: " + key)
    expected_figures = [f"{Path(name).stem}.{extension}" for name in NEW_FIGURES
                        for extension in ("pdf", "svg", "png")]
    require(type(result.get("figures_generated")) is bool, "Figure availability must be explicit")
    require(not require_figures or result["figures_generated"], "The final paper requires actual result figures")
    if not result["figures_generated"]:
        expected_figures = []
    require(result.get("figures") == expected_figures, "Actual result figure inventory differs")
    require(all(name in sealed["files"] and sealed["files"][name]["bytes"] > 0
                for name in expected_figures), "Sealed analysis omits actual result figures")
    analyzer_binding = committed_file(root, ANALYZER, source_commit)
    require(result.get("analysis_source") == analyzer_binding
            and binding(directory / "inputs/analyze_limbo_external_benchmark.py") == analyzer_binding,
            "Analysis implementation does not match the explicit source commit")
    specification = importlib.util.spec_from_file_location("conseqax_final_paper_analysis", root / ANALYZER)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    require(result.get("inputs", {}).get("protocol_commit") == protocol_commit,
            "Analysis protocol commit differs from the requested protocol")
    inputs = result["inputs"]
    for key, copy_name in (("audit", "audit-result.json"), ("audit_manifest", "audit-manifest.json"),
                           ("protocol", "protocol.json")):
        expected = {field: inputs[key][field] for field in ("sha256", "bytes")}
        require(binding(directory / "inputs" / copy_name) == expected,
                "Analysis copied input differs: " + key)
    # Recorded absolute paths are provenance labels, not portable input locators.
    # Rebuild only the sealed two-file audit layout in an owned temporary folder.
    with tempfile.TemporaryDirectory(prefix="conseqax-paper-audit-check-") as temporary:
        audit_directory = Path(temporary)
        shutil.copyfile(directory / "inputs/audit-result.json", audit_directory / "audit-result.json")
        shutil.copyfile(directory / "inputs/audit-manifest.json", audit_directory / "manifest.json")
        protocol, audit, checked_inputs = module.validate_inputs(audit_directory / "audit-result.json",
                                                                protocol_path, protocol_commit)
    require(set(inputs) == set(checked_inputs), "Analysis input inventory differs")
    for key in checked_inputs:
        if key in ("audit", "audit_manifest", "protocol"):
            require(set(inputs[key]) == {"path", "sha256", "bytes"}
                    and type(inputs[key]["path"]) is str and inputs[key]["path"]
                    and {field: inputs[key][field] for field in ("sha256", "bytes")}
                    == {field: checked_inputs[key][field] for field in ("sha256", "bytes")},
                    "Analysis byte binding differs: " + key)
        else:
            require(inputs[key] == checked_inputs[key], "Analysis input binding differs: " + key)
    recomputed = module.analyze(protocol, audit, inputs)
    actual = {key: value for key, value in result.items()
              if key not in ("created_utc", "analysis_source", "figures", "figures_generated")}
    expected = {key: value for key, value in recomputed.items() if key != "created_utc"}
    require(module.canonical(actual) == module.canonical(expected),
            "Analysis values differ from recomputed audited rows")
    # JSON is sealed with sorted keys, while the frozen exporter iterates the
    # analysis's deliberately registered arm/contrast order. Recreate that order
    # from the validated rows; do not regenerate display text from JSON key order.
    paragraphs = module.narrative(recomputed)
    generated = {"results.md": module.markdown(recomputed), "results.tex": module.latex(recomputed),
        "narrative.md": "\n\n".join(paragraphs) + "\n",
        "narrative.tex": "% Generated factual paragraphs; native grades and accounting only.\n"
            + "\n\n".join(module.tex_escape(paragraph) for paragraph in paragraphs) + "\n"}
    for name, text in generated.items():
        require((directory / name).read_bytes() == text.encode("utf-8"),
                "Generated result text differs from audited analysis: " + name)
    require(check_manifest(directory) == sealed, "Analysis changed during validation")
    return {"passed": True, "sealed": sealed, "result": result, "protocol": protocol,
            "audit": audit, "analyzer_binding": analyzer_binding}


def scientific_schedule(protocol):
    """Normalize only the runtime alias, never task selection or control settings."""
    schedule = json.loads(json.dumps(protocol["schedule"]))
    for row in schedule:
        row["spec"]["model"] = "<same-pinned-model-weights>"
    return schedule


def validate_cohorts(root, analysis, protocol, commit, interrupted_analysis,
                     interrupted_protocol, interrupted_commit, source_commit):
    """Require both complete denominators and an explicit non-pooled follow-up."""
    exact_commit(interrupted_commit, "--interrupted-protocol-commit")
    require(commit != interrupted_commit, "A follow-up must have a separately published protocol identity")
    require(analysis.resolve() != interrupted_analysis.resolve(), "The two cohort analyses cannot substitute for each other")
    current = validate_analysis(root, analysis, protocol, commit, source_commit)
    earlier = validate_analysis(root, interrupted_analysis, interrupted_protocol,
                                interrupted_commit, source_commit, require_figures=False)
    first, second = earlier["protocol"], current["protocol"]
    for key in ("metadata", "seed", "limits", "arms", "sources"):
        require(first[key] == second[key], "The follow-up changed a frozen scientific condition: " + key)
    for key in ("commit", "files"):
        require(first["native"][key] == second["native"][key], "The pinned native implementation changed: " + key)
    require(scientific_schedule(first) == scientific_schedule(second),
            "Follow-up task indices, faults, ordering or policy limits differ from the original schedule")
    require(first["runtime_binding"]["model_blob_sha256"] == second["runtime_binding"]["model_blob_sha256"],
            "Follow-up model weights differ from the original condition")
    require(bool(earlier["audit"].get("interrupted_collection")),
            "The original cohort must retain its explicit interrupted-collection provenance")
    require(type(second.get("execution_condition")) is dict and bool(second["execution_condition"])
            and type(second.get("prior_condition")) is dict and bool(second["prior_condition"]),
            "The follow-up must prospectively declare its runtime condition and prior-data exposure")
    prior = second["prior_condition"]
    require(prior.get("protocol_commit") == interrupted_commit
            and type(prior.get("protocol")) is dict
            and {key: prior["protocol"].get(key) for key in ("sha256", "bytes")}
                == earlier["audit"]["protocol"]
            and prior.get("partial_data_exposed_before_followup_freeze") is True
            and prior.get("cohorts_pooled") is False,
            "The prospective follow-up must bind this exact original cohort and partial-data exposure")
    require(type(prior.get("interrupted_analysis")) is dict
            and {key: prior["interrupted_analysis"].get(key) for key in ("sha256", "bytes")}
                == earlier["sealed"]["files"]["results.json"],
            "The prospective follow-up must retain its exact declared interrupted analysis")
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+", second["execution_condition"].get("ollama_version", ""))),
            "The follow-up must explicitly bind its Ollama version")
    require(earlier["analyzer_binding"] == current["analyzer_binding"],
            "The cohorts must use the same frozen analysis implementation")
    return current, earlier


def cohort_accounting_rows(current, earlier):
    rows = []
    for label, checked in (("Original interrupted", earlier), ("Follow-up", current)):
        for arm, name in zip(("vanilla", "sdk_retry3", "guard", "conseqax_guard"),
                             ("Vanilla", "SDK retry", "Native guard", "ConseqaX guard")):
            value = checked["result"]["arms"][arm]
            audited = [row for row in checked["audit"]["rows"] if row["arm"] == arm]
            rows.append([label, name, 24, sum(row["started"] for row in audited),
                value["audited_grade_available"], value["audited_native_error_returns"],
                value["grade_unavailable"], value["endpoints"]["TS"]["true_audited"],
                value["endpoints"]["EOS"]["true_audited"]])
    return rows


def cohort_accounting_tex(current, earlier):
    return ("% Derived separately from both complete 96-slot audited cohorts; no pooling.\n"
        + r"\begin{table*}[t]" + "\n"
        + r"\caption{Both registered cohorts retain their full planned denominators. Started includes an interrupted child; graded includes independently replayed native error returns after settlement. Unknown grades remain unavailable. The follow-up uses the same 12 base instances and is not an independent task sample.}" + "\n"
        + r"\label{tab:limbo-cohorts}\centering\small\setlength{\tabcolsep}{4pt}" + "\n"
        + r"\begin{tabular}{llrrrrrrr}\toprule" + "\n"
        + r"Cohort & Arm & Planned & Started & Graded & Error returns & Unavailable & TS & EOS \\" + "\n"
        + r"\midrule" + "\n"
        + "\n".join(" & ".join(map(str, row)) + r" \\" for row in cohort_accounting_rows(current, earlier))
        + "\n" + r"\bottomrule\end{tabular}\end{table*}" + "\n")


def uncomment(text):
    """Remove TeX comments and literal environments before dependency discovery."""
    text = re.sub(r"\\begin\{(verbatim\*?|lstlisting|minted|comment)\}.*?\\end\{\1\}",
                  "", text, flags=re.S)
    lines = []
    for line in text.splitlines():
        stop = len(line)
        for index, character in enumerate(line):
            if character != "%":
                continue
            backslashes = len(line[:index]) - len(line[:index].rstrip("\\"))
            if backslashes % 2 == 0:
                stop = index
                break
        lines.append(line[:stop])
    return "\n".join(lines)


def literal(name):
    require(not any(character in name for character in "\\{}#$~\n\r"),
            "Dynamic/unsupported TeX dependency must be made literal: " + name)
    safe_member(name)
    return name


def discover_sources(root):
    """Discover literal recursive inputs and graphics; reject ambiguous resolutions."""
    main = root / MAIN
    discovered, texts, edges = set(), {}, []

    def resolve(name, owner, extensions, graphic_paths=()):
        name = literal(name)
        names = (name,) if Path(name).suffix else tuple(name + extension for extension in extensions)
        directories = [owner.parent, root, main.parent]
        for entry in graphic_paths:
            directories.extend((root / entry, owner.parent / entry, main.parent / entry))
        candidates = set()
        for directory in directories:
            for value in names:
                path = (directory / value).resolve()
                require(path.is_relative_to(root), "TeX dependency leaves repository")
                if path.is_file():
                    require(not (directory / value).is_symlink(), "Linked source dependency")
                    candidates.add(path)
        require(len(candidates) == 1,
                f"Missing/ambiguous literal dependency {name!r} in {owner.relative_to(root)}")
        return candidates.pop()

    def visit(path):
        if path in discovered:
            return
        discovered.add(path)
        text = uncomment(path.read_text(encoding="utf-8"))
        texts[path] = text
        pattern = r"\\(?:input|include)(?![A-Za-z@])\s*(?:\{([^{}\r\n]+)\}|([^\s{}\r\n%]+))"
        for match in re.finditer(pattern, text):
            target = resolve(match.group(1) or match.group(2), path, (".tex",))
            require(target.suffix == ".tex", "Only TeX input sources are supported")
            edges.append({"from": path.relative_to(root).as_posix(),
                          "to": target.relative_to(root).as_posix(), "kind": "input"})
            visit(target)
        for match in re.finditer(r"\\(?:bibliography|addbibresource)(?:\[[^\]]*\])?\s*\{([^{}]+)\}", text):
            for name in match.group(1).split(","):
                target = resolve(name.strip(), path, (".bib",))
                discovered.add(target)
                edges.append({"from": path.relative_to(root).as_posix(),
                              "to": target.relative_to(root).as_posix(), "kind": "bibliography"})

    require(main.is_file(), "Main manuscript is missing")
    visit(main.resolve())
    graphic_paths = []
    for text in texts.values():
        for match in re.finditer(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}", text):
            for item in re.findall(r"\{([^{}]*)\}", match.group(1)):
                if item:
                    graphic_paths.append(literal(item.rstrip("/")))
    for owner, text in texts.items():
        for match in re.finditer(r"\\includegraphics\*?(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}", text):
            target = resolve(match.group(1), owner, (".pdf", ".png", ".jpg", ".jpeg", ".eps"), graphic_paths)
            discovered.add(target)
            edges.append({"from": owner.relative_to(root).as_posix(),
                          "to": target.relative_to(root).as_posix(), "kind": "graphic"})
    require(root / METHODS in discovered, "Actual LIMBO methods must be included")
    require(not any(path.name == "native-four-arm-methods.pdf" for path in discovered),
            "Stale prospective Tau comparison figure remains in the final paper")
    for path, text in texts.items():
        require(not re.search(r"\b(?:TODO|TBD|REPLACE_ME|INSERT_RESULTS)\b|pending precollection publication", text, re.I),
                "Unresolved manuscript placeholder: " + path.relative_to(root).as_posix())
        require("Native Integration and Prospective External Pilot" not in text,
                "The old prospective external pilot section remains")
    discovered.add(root / READABLE)
    return sorted(path.relative_to(root).as_posix() for path in discovered), edges


def validate_paper_assets(root, names, analysis):
    included = {name: binding(root / name) for name in names}
    graphics = {Path(name).name: name for name in names if Path(name).suffix.lower() == ".pdf"}
    require(len(graphics) == sum(Path(name).suffix.lower() == ".pdf" for name in names),
            "Duplicate figure basenames must be disambiguated")
    for name in OLD_FIGURES + NEW_FIGURES:
        require(name in graphics, "Required final result/methods figure is absent: " + name)
    for name in NEW_FIGURES:
        require(included[graphics[name]] == binding(analysis / name),
                "Manuscript native figure differs from audited analysis: " + name)
    table = binding(analysis / "results.tex")
    require(any(Path(name).suffix == ".tex" and expected == table for name, expected in included.items()),
            "The exact audit-generated native results table must be included")
    return included


def check_tex_log(log):
    pattern = (r"Overfull\s+\\[hv]box|undefined references|undefined citations|"
               r"(?:Reference|Citation)[^\n]*undefined|Missing character:|"
               r"(?:Font|font)[^\n]*(?:not found|not loadable|cannot be found|undefined|not available|substitut)|"
               r"LaTeX Error|Emergency stop|Fatal error")
    return [line for line in log.splitlines() if re.search(pattern, line, re.I)]


def pdf_fonts(reader):
    """Inspect page and nested Form/Pattern resources, including figure fonts."""
    fonts, seen_resources, seen_fonts = {}, set(), set()

    def object_value(value):
        return value.get_object() if hasattr(value, "get_object") else value

    def inspect_font(reference):
        font = object_value(reference)
        identity = id(font)
        if identity in seen_fonts:
            return
        seen_fonts.add(identity)
        if font.get("/DescendantFonts"):
            for descendant in font["/DescendantFonts"]:
                inspect_font(descendant)
            return
        name, subtype = str(font.get("/BaseFont", "Type3")), str(font.get("/Subtype"))
        streams = []
        if subtype == "/Type3":
            procedures = object_value(font.get("/CharProcs", {}))
            require(bool(procedures) and all(hasattr(object_value(value), "get_data")
                    for value in procedures.values()), "Type3 glyph programs are not embedded")
            streams = [byte_binding(object_value(value).get_data()) for value in procedures.values()]
            resources(font.get("/Resources"))
        else:
            descriptor = object_value(font.get("/FontDescriptor"))
            require(descriptor is not None, "Font descriptor missing: " + name)
            for key in ("/FontFile", "/FontFile2", "/FontFile3"):
                if descriptor.get(key) is not None:
                    data = object_value(descriptor[key]).get_data()
                    require(bool(data), "Empty embedded font program: " + name)
                    streams.append(byte_binding(data))
            require(bool(streams), "Unembedded font: " + name)
        fonts[f"{name}|{subtype}|{identity}"] = {"name": name, "subtype": subtype,
                                                  "embedded": True, "programs": streams}

    def resources(reference):
        value = object_value(reference)
        if value is None or id(value) in seen_resources:
            return
        seen_resources.add(id(value))
        for reference in object_value(value.get("/Font", {})).values():
            inspect_font(reference)
        for kind in ("/XObject", "/Pattern"):
            for reference in object_value(value.get(kind, {})).values():
                resources(object_value(reference).get("/Resources"))
        for reference in object_value(value.get("/ExtGState", {})).values():
            entry = object_value(reference)
            if entry.get("/Font"):
                inspect_font(entry["/Font"][0])

    for page in reader.pages:
        resources(page.get("/Resources"))
    require(bool(fonts), "No embedded fonts were found")
    return list(fonts.values())


def render_and_check(pdf, quality, poppler, dpi):
    from PIL import Image, ImageDraw
    from pypdf import PdfReader
    reader = PdfReader(pdf, strict=True)
    require(not reader.is_encrypted and len(reader.pages) > 0, "Missing/encrypted paper pages")
    fonts = pdf_fonts(reader)
    page_text = [page.extract_text() or "" for page in reader.pages]
    require(all(text.strip() for text in page_text), "A manuscript page has no extractable text")
    text = "\n\n".join(page_text)
    require("\ufffd" not in text and "\x00" not in text and "??" not in text,
            "Extracted text contains replacement characters or unresolved references")
    (quality / "extracted-text.txt").write_text(text, encoding="utf-8", newline="\n")
    info = command([poppler / "pdfinfo.exe", pdf], quality)
    (quality / "pdfinfo.stderr.log").write_bytes(info.stderr)
    require(info.returncode == 0, "PDF information check failed")
    (quality / "pdfinfo.txt").write_bytes(info.stdout)
    rendered = command([poppler / "pdftoppm.exe", "-r", dpi, "-png", pdf, quality / "page"],
                       quality, timeout=600)
    (quality / "render.stderr.log").write_bytes(rendered.stderr)
    require(rendered.returncode == 0, "All-page PDF rendering failed")
    pages = sorted(quality.glob("page-*.png"), key=lambda path: int(path.stem.split("-")[-1]))
    require(len(pages) == len(reader.pages), "Rendered page inventory differs from PDF")
    for start in range(0, len(pages), 4):
        sheet = Image.new("RGB", (1300, 1740), "#e2e5e8")
        draw = ImageDraw.Draw(sheet)
        for offset, page in enumerate(pages[start:start + 4]):
            with Image.open(page) as original:
                image = original.convert("RGB")
            require(image.width > 0 and image.height > 0, "Invalid rendered page")
            image.thumbnail((620, 820))
            x, y = (offset % 2) * 650 + 15, (offset // 2) * 870 + 30
            draw.text((x, y - 20), f"Page {start + offset + 1}", fill="#111111")
            sheet.paste(image, (x, y))
        sheet.save(quality / f"contact-sheet-{start // 4 + 1}.png")
    return {"pages": len(reader.pages), "fonts": fonts, "all_fonts_embedded": True,
            "all_pages_rendered": True, "render_dpi": dpi, "visual_review_pending": True}


def build(args):
    root = args.root.resolve()
    source_commit = exact_commit(args.source_commit, "--source-commit")
    protocol_commit = exact_commit(args.protocol_commit, "--protocol-commit")
    analysis, protocol = args.analysis.resolve(), args.protocol.resolve()
    output, work = args.output.resolve(), args.work.resolve()
    require(not output.exists() and not work.exists(), "Refuse existing output/work directory")
    require(not output.is_relative_to(work) and not work.is_relative_to(output),
            "Output and work directories must not overlap")
    require(not root.is_relative_to(output) and not root.is_relative_to(work),
            "Output/work cannot contain the repository")
    require(protocol.is_relative_to(root), "The protocol must belong to this source repository")
    require(git(root, "cat-file", "-t", source_commit).strip() == b"commit"
            and git(root, "cat-file", "-t", protocol_commit).strip() == b"commit",
            "Both identities must name exact commits")
    script_relative = Path(__file__).resolve().relative_to(root).as_posix()
    script_binding = committed_file(root, script_relative, source_commit)
    interrupted_analysis, interrupted_protocol = args.interrupted_analysis.resolve(), args.interrupted_protocol.resolve()
    interrupted_commit = exact_commit(args.interrupted_protocol_commit, "--interrupted-protocol-commit")
    require(interrupted_protocol.is_relative_to(root), "The original protocol must belong to this repository")
    checked, earlier = validate_cohorts(root, analysis, protocol, protocol_commit,
        interrupted_analysis, interrupted_protocol, interrupted_commit, source_commit)
    names, edges = discover_sources(root)
    sources = {name: committed_file(root, name, source_commit) for name in names}
    cohort_table = root / "paper/limbo-cohort-accounting.tex"
    require("paper/limbo-cohort-accounting.tex" in names
            and cohort_table.read_text(encoding="utf-8") == cohort_accounting_tex(checked, earlier),
            "Both-cohort denominator table must exactly match the two audited analyses")
    require(sources == validate_paper_assets(root, names, analysis), "Paper source changed during validation")
    compiler, poppler = args.compiler.resolve(), args.poppler.resolve()
    require(compiler.is_file() and all((poppler / name).is_file() for name in ("pdfinfo.exe", "pdftoppm.exe")),
            "Cached compiler or PDF tools are unavailable")
    tool_bindings = {"tectonic": {"path": str(compiler), **binding(compiler)},
        **{name: {"path": str(poppler / name), **binding(poppler / name)}
           for name in ("pdfinfo.exe", "pdftoppm.exe")}}
    source, build_dir, quality = work / "source", work / "build", work / "quality"
    work.mkdir(parents=True, exist_ok=False)
    for directory in (source, build_dir, quality):
        directory.mkdir()
    for name, expected in sources.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
        require(binding(target) == expected, "Source changed while copying: " + name)
    arguments = [compiler, MAIN, "--only-cached", "--untrusted", "--outdir", build_dir,
        "--keep-logs", "--keep-intermediates", "--makefile-rules", quality / "compile-dependencies.d"]
    compiled = command(arguments, source, timeout=1200)
    (quality / "compile.stdout.log").write_bytes(compiled.stdout)
    (quality / "compile.stderr.log").write_bytes(compiled.stderr)
    require(compiled.returncode == 0, "Cached TeX compilation failed; inspect work/quality logs")
    log_path = build_dir / "conseqax-research.log"
    log = log_path.read_text(encoding="utf-8", errors="replace")
    bad = check_tex_log(log + "\n" + compiled.stdout.decode(errors="replace")
                        + "\n" + compiled.stderr.decode(errors="replace"))
    write_json(quality / "tex-warning-check.json", {"blocking": bad,
        "underfull_warnings": log.count("Underfull"), "visual_review_pending": True})
    require(not bad, "Blocking TeX warnings: " + repr(bad))
    pdf = build_dir / "conseqax-research.pdf"
    quality_receipt = render_and_check(pdf, quality, poppler, args.dpi)
    require(check_manifest(analysis) == checked["sealed"], "Sealed analysis changed during build")
    require(check_manifest(interrupted_analysis) == earlier["sealed"], "Original interrupted analysis changed during build")
    require(all(committed_file(root, name, source_commit) == expected for name, expected in sources.items()),
            "Manuscript sources changed during build")
    require(committed_file(root, script_relative, source_commit) == script_binding,
            "Builder changed during build")
    require(committed_file(root, ANALYZER, source_commit) == checked["analyzer_binding"],
            "Analyzer changed during build")
    require(all(binding(source / name) == expected for name, expected in sources.items()),
            "Copied compilation source changed during build")
    require(all(binding(Path(value["path"])) == {key: value[key] for key in ("sha256", "bytes")}
                for value in tool_bindings.values()), "Compiler/PDF tools changed during build")
    audit = checked["audit"]
    availability = sum(row["operational"] for row in audit["rows"])
    execution_success = sum(row["execution_success"] for row in audit["rows"])
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, output / "source")
    shutil.copytree(quality, output / "quality")
    shutil.copytree(analysis, output / "inputs/analysis")
    shutil.copytree(interrupted_analysis, output / "inputs/interrupted-analysis")
    shutil.copyfile(protocol, output / "inputs/protocol.json")
    shutil.copyfile(interrupted_protocol, output / "inputs/interrupted-protocol.json")
    shutil.copyfile(pdf, output / "ConseqaX_Research_Paper.pdf")
    shutil.copyfile(log_path, output / "quality/compile.tex.log")
    shutil.copyfile(__file__, output / "quality/build_final_limbo_paper.source.py")
    require(check_manifest(output / "inputs/analysis") == checked["sealed"],
            "Copied sealed analysis differs")
    require(check_manifest(output / "inputs/interrupted-analysis") == earlier["sealed"],
            "Copied interrupted analysis differs")
    require(binding(output / "inputs/interrupted-protocol.json") == earlier["audit"]["protocol"],
            "Copied interrupted protocol differs from the retained audit")
    require(binding(output / "inputs/protocol.json") == audit["protocol"],
            "Copied protocol differs from the passed audit")
    require(all(binding(output / "source" / name) == expected for name, expected in sources.items()),
            "Copied manuscript source differs")
    write_json(output / "source-bindings.json", {"source_commit": source_commit,
        "protocol_commit": protocol_commit, "protocol": binding(protocol),
        "sources_match_explicit_git_blobs": True, "sources": sources, "dependency_edges": edges,
        "analysis_manifest": checked["sealed"]["manifest"], "analysis_values_recomputed": True,
        "interrupted_cohort": {"protocol_commit": interrupted_commit,
            "protocol": binding(interrupted_protocol), "analysis_manifest": earlier["sealed"]["manifest"],
            "planned_slots": 96, "grade_available": sum(row["operational"] for row in earlier["audit"]["rows"])},
        "cohorts_pooled": False, "unique_base_instances_across_cohorts": 12,
        "analyzer": checked["analyzer_binding"], "builder": script_binding,
        "tools": tool_bindings, "compile_command": list(map(str, arguments)),
        "offline_cached_resources_only": True, "untrusted_tex_mode": True})
    write_json(output / "build-receipt.json", {"schema": "conseqax-final-limbo-paper-build-v1",
        "built_utc": utc(), "source_commit": source_commit, "protocol_commit": protocol_commit,
        "pdf": binding(output / "ConseqaX_Research_Paper.pdf"), **quality_receipt,
        "compile_exit_code": compiled.returncode, "blocking_tex_warnings": bad,
        "underfull_warnings": log.count("Underfull"), "official_native_results": True,
        "official_results_mean_passed_analysis_of_all_planned_dispositions": True,
        "all_planned_trajectories_succeeded_is_not_asserted": True,
        "planned_slots": 96, "planned_worlds": 24, "base_instances": 12,
        "audited_native_grade_available": availability, "execution_success": execution_success,
        "native_grade_unavailable": 96 - availability, "human_labels": 0,
        "interrupted_cohort_planned_slots": 96,
        "interrupted_cohort_audited_grades": sum(row["operational"] for row in earlier["audit"]["rows"]),
        "both_cohorts_retained_separately": True, "cohorts_pooled": False,
        "new_model_calls": 0, "new_native_evaluations": 0,
        "source_authentication_or_external_replication": False})
    (output / "README.md").write_text(
        "# Audited LIMBO paper build\n\n"
        "This bundle binds the manuscript to an explicit Git commit and a validated "
        "follow-up 96-slot native analysis and the original interrupted 96-slot cohort. "
        "Both full denominators are retained separately on the same 12 base instances. "
        "The cohorts are not pooled. A passed audit can retain failed or unstarted slots; "
        "it does not establish that all tasks succeeded.\n\n"
        "Automatic compilation, embedded-font, text and all-page rendering checks passed. "
        "**Visual review is pending.** Inspect every page and the contact sheets before "
        "recording a separate dated review receipt; do not edit this sealed bundle to "
        "claim a review that has not occurred.\n\n"
        "The copied analysis inputs retain the audit scope, metric limitations and exact "
        "protocol identities. Raw collection artifacts remain linked by their original "
        "manifest digest. No model call, native evaluation or human label is created by "
        "this document build.\n", encoding="utf-8", newline="\n")
    write_json(output / "manifest.json", {path.relative_to(output).as_posix(): binding(path)
        for path in sorted(output.rglob("*")) if path.is_file()})
    check_manifest(output)
    return {"output": str(output), "source_commit": source_commit,
        "protocol_commit": protocol_commit, "pages": quality_receipt["pages"],
        "visual_review_pending": True, "pdf": binding(output / "ConseqaX_Research_Paper.pdf")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--interrupted-analysis", required=True, type=Path)
    parser.add_argument("--interrupted-protocol", required=True, type=Path)
    parser.add_argument("--interrupted-protocol-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--compiler", type=Path, default=DEFAULT_COMPILER)
    parser.add_argument("--poppler", type=Path, default=DEFAULT_POPPLER)
    parser.add_argument("--dpi", type=int, default=110)
    args = parser.parse_args()
    require(72 <= args.dpi <= 300, "Render DPI must be between 72 and 300")
    work_preexisted = args.work.exists()
    try:
        result = build(args)
    except Exception as exc:
        if not work_preexisted and args.work.is_dir() and not (args.work / "build-failure.json").exists():
            write_json(args.work / "build-failure.json", {"schema": "conseqax-paper-build-failure-v1",
                "utc": utc(), "error": type(exc).__name__ + ": " + str(exc),
                "visual_review_pending": True, "passed": False})
        raise
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
