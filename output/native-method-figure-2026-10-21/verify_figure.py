"""PDF structure/font check; does not create or modify the figure."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
PDF = ROOT / "native-four-arm-methods.pdf"
reader = PdfReader(PDF)
assert len(reader.pages) == 1
page = reader.pages[0]
assert abs(float(page.mediabox.width) - 518.4) < 0.01
assert abs(float(page.mediabox.height) - 259.2) < 0.01
fonts = []
for name, reference in page["/Resources"]["/Font"].items():
    font = reference.get_object()
    descendants = font.get("/DescendantFonts") or [font]
    for descendant in descendants:
        actual = descendant.get_object()
        descriptor = actual["/FontDescriptor"].get_object()
        streams = [descriptor[key].get_object() for key in ("/FontFile", "/FontFile2", "/FontFile3")
                   if key in descriptor]
        assert streams and all(len(stream.get_data()) > 0 for stream in streams)
        fonts.append({"resource": str(name), "font": str(actual["/BaseFont"]),
            "subtype": str(actual["/Subtype"]), "embedded": True,
            "embedded_bytes": sum(len(stream.get_data()) for stream in streams),
            "to_unicode": "/ToUnicode" in font})
assert fonts and all(font["embedded"] and font["to_unicode"] for font in fonts)
images = [str(name) for name, reference in (page["/Resources"].get("/XObject") or {}).items()
          if reference.get_object().get("/Subtype") == "/Image"]
assert not images
svg = (ROOT / "native-four-arm-methods.svg").read_text(encoding="utf-8")
assert "<image" not in svg
text = page.extract_text()
for phrase in ("Native four-arm method", "field_status", "Raw readback", "Direct public-field report",
               "ConseqaX 2.1.1 receipt", "Evaluator-only gold", "Reference actions", "DB + COMM"):
    assert phrase in text, phrase
result = {"passed": True, "pages": 1, "dimensions_points": [float(page.mediabox.width), float(page.mediabox.height)],
    "fonts": fonts, "raster_image_xobjects": images, "svg_embedded_images": False,
    "pdf_sha256": hashlib.sha256(PDF.read_bytes()).hexdigest(),
    "verification_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "font_check_method": "pypdf FontDescriptor embedded FontFile streams and ToUnicode; pdffonts binary unavailable"}
(ROOT / "structural-qa.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
(ROOT / "fontcheck.txt").write_text("Direct PDF object font inspection using pypdf\n" +
    "\n".join(f"{font['font']}: embedded={font['embedded']} bytes={font['embedded_bytes']} ToUnicode={font['to_unicode']}"
              for font in fonts) + "\nNo raster image XObjects.\n", encoding="utf-8")
print(json.dumps(result, sort_keys=True))
