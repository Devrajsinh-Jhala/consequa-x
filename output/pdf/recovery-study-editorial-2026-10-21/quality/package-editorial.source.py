from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, shutil, subprocess
from pypdf import PdfReader
ROOT = Path('D:/ConsequaX-Research/paper-writing')
TEMP = ROOT/'tmp/pdfs/recovery-study-editorial-2026-10-21'
OUT = ROOT/'output/pdf/recovery-study-editorial-2026-10-21'
def binding(path):
    data = path.read_bytes()
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def write(path, value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False)
        stream.write('\n')
source = json.loads((TEMP/'source-bindings.json').read_text())
for name, expected in source['files'].items():
    assert binding(TEMP/'source'/name) == expected
    assert binding(ROOT/name) == expected
assert binding(ROOT/'output/pdf/recovery-study-2026-10-20/ConseqaX_Research_Paper.pdf')['sha256'] == source['old_pdf_sha256_before']
assert (TEMP/'quality/compile-exit-code.txt').read_text().strip() == '0'
pdf = TEMP/'build/conseqax-research.pdf'
reader = PdfReader(pdf)
texts = [page.extract_text() or '' for page in reader.pages]
text = '\n\n'.join(texts)
(TEMP/'quality/extracted-text.txt').write_text(text,encoding='utf-8')
fonts = {}
for page in reader.pages:
    resources = page.get('/Resources',{}).get_object()
    for ref in resources.get('/Font',{}).get_object().values():
        font = ref.get_object()
        base = str(font.get('/BaseFont'))
        descendants = font.get('/DescendantFonts')
        objects = [item.get_object() for item in descendants] if descendants else [font]
        embedded = True
        for obj in objects:
            descriptor = obj.get('/FontDescriptor')
            desc = descriptor.get_object() if descriptor else {}
            embedded = embedded and any(key in desc for key in ('/FontFile','/FontFile2','/FontFile3'))
        fonts[base] = {'subtype':str(font.get('/Subtype')),'embedded':bool(embedded)}
log = (TEMP/'build/conseqax-research.log').read_text(encoding='utf-8',errors='replace')
serious = [line for line in log.splitlines() if re.search(r'Overfull|undefined|Missing character|^!|LaTeX Error',line,re.I)]
underfull = [line.strip() for line in log.splitlines() if 'Underfull' in line]
links = sorted({str(annotation.get_object().get('/A',{}).get_object().get('/URI')) for page in reader.pages for annotation in page.get('/Annots',[]) if annotation.get_object().get('/A') and annotation.get_object()['/A'].get('/URI')})
expected_links = ['https://arxiv.org/html/2608.02645v1','https://arxiv.org/html/2608.23628v2']
assert len(reader.pages) == 10
assert len(fonts) == 12 and all(row['embedded'] for row in fonts.values())
assert not serious, serious
assert all(link in links for link in expected_links)
assert '??' not in text and '[?]' not in text and '\ufffd' not in text
qa = {'schema':'conseqa-editorial-pdf-qa-v1','pages':len(reader.pages),'pdf':binding(pdf),'page_text_characters':[len(value) for value in texts],'fonts':fonts,'all_fonts_embedded':True,'compiler_errors_overfull_undefined_missing_glyphs':serious,'underfull_spacing_diagnostics':underfull,'metadata':{str(key):str(value) for key,value in (reader.metadata or {}).items()},'page_boxes':[{'mediabox':[float(x) for x in page.mediabox],'cropbox':[float(x) for x in page.cropbox]} for page in reader.pages],'annotation_links':links,'explicit_verified_and_callability_version_urls_present':True,'automated_checks_passed':True,'pdffonts_cli_available':False,'font_inspection_method':'pypdf font/DescendantFonts/FontDescriptor traversal requiring embedded FontFile, FontFile2 or FontFile3','visual_review_recorded_separately':True}
write(TEMP/'quality/automated-pdf-qa.json',qa)
pages = sorted((TEMP/'quality/pages').glob('verified-page-*.png'))
assert len(pages) == 10
visual = {'schema':'conseqa-editorial-pdf-visual-review-v1','reviewed_utc':datetime.now(timezone.utc).isoformat(),'review_kind':'AI-assisted inspection of all ten Poppler page renders at 120 dpi','passed':True,'all_pages_inspected':True,'clipping_overlap_missing_glyphs_or_unreadable_figures_found':False,'all_figures_precede_references':True,'pages':{'1-3':'Title, author, two-column prose, related work, equations and section transitions are legible and clear.','4-5':'Policy table, source identities, equation and dense results fit within columns without clipping.','6-9':'All three scientific figures and the numeric tables are sharp, labeled and within page boundaries.','10':'Versioned reference URLs fit the columns, references remain legible, and disclosure/conclusion are clear.'},'underfull_warning_assessment':'Retained TeX underfull warnings concern justified spacing; all affected pages inspected with no overflow or overlap.','scope':'Document layout QA only; not independent human validation, external replication or venue-specific compliance.','page_bindings':{page.name:binding(page) for page in pages}}
write(TEMP/'quality/visual-review.json',visual)
assert not OUT.exists()
OUT.mkdir(parents=True)
shutil.copyfile(pdf,OUT/'ConseqaX_Research_Paper.pdf')
shutil.copytree(TEMP/'source',OUT/'source')
shutil.copytree(TEMP/'quality',OUT/'quality')
shutil.copyfile(TEMP/'build/conseqax-research.log',OUT/'quality/conseqax-research.log')
shutil.copyfile(TEMP/'source-bindings.json',OUT/'source-bindings.json')
shutil.copyfile(Path(__file__),OUT/'quality/package-editorial.source.py')
receipt = {'schema':'conseqa-editorial-paper-build-v1','complete':True,'packaged_utc':datetime.now(timezone.utc).isoformat(),'source_commit':source['source_commit'],'operation':'Editorial wording and explicit versioned-reference URL update; no new experimental results','compiler':source['compiler'],'command':['tectonic','paper/conseqax-research.tex','--only-cached','--outdir','../build','--keep-logs','--keep-intermediates','--makefile-rules','../quality/compile-dependencies.d'],'working_directory':str(TEMP/'source'),'compile_exit_code':0,'offline_cached_resources_only':True,'pages':len(reader.pages),'fonts':len(fonts),'all_fonts_embedded':True,'automated_and_all_page_visual_checks_passed':True,'pdf':binding(OUT/'ConseqaX_Research_Paper.pdf'),'old_sealed_pdf_preserved':True,'old_pdf_sha256':source['old_pdf_sha256_before'],'measured_worlds_or_model_calls_added':0,'no_new_native_pilot_results':True,'venue_specific_submission_compliance_not_asserted':True}
write(OUT/'build-receipt.json',receipt)
(OUT/'README.md').write_text('# Editorial IEEE research draft - 21 October 2026\n\nThis 10-page draft contains editorial corrections to the scope of separately captured observations and separately implemented reference arithmetic, plus explicit versioned prior-work URLs and verified bibliographic months. It reports the existing controlled recovery and availability experiments; it contains no official autonomous-pilot results.\n\nExact TeX/figure inputs match commit 8bd1cd88ab3644a9c6417e29308ab4b502b40484. The compiler used only cached resources. The bundle retains build logs, dependencies, input hashes, metadata, extracted text, all-page renders, embedded-font checks, and AI-assisted visual QA. The original 20 October sealed PDF is unchanged.\n\nNo model calls, benchmark worlds, human participation or GitHub Actions were added. Layout QA does not establish scientific validity, top-conference readiness or compliance with a specific venue. Complete evidence remains at the repository paths referenced in the manuscript and original study bundles.\n',encoding='utf-8')
write(OUT/'manifest.json',{'schema':'conseqa-editorial-paper-snapshot-v1','complete':True,'source_commit':source['source_commit'],'files':{p.relative_to(OUT).as_posix():binding(p) for p in sorted(OUT.rglob('*')) if p.is_file()}})
print(json.dumps({'pdf':str(OUT/'ConseqaX_Research_Paper.pdf'),'pdf_binding':binding(OUT/'ConseqaX_Research_Paper.pdf'),'pages':len(reader.pages),'fonts':len(fonts),'all_fonts_embedded':True,'serious_diagnostics':len(serious),'underfull_diagnostics':len(underfull),'manifest':binding(OUT/'manifest.json')}))
