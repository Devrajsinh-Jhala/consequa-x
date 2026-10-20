"""Seal the visually checked paper; never execute a measured world."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import shutil
import subprocess

ROOT = Path('D:/ConsequaX-Research/paper-writing')
TEMP = ROOT / 'tmp/pdfs/recovery-study-2026-10-20'
OUT = ROOT / 'output/pdf/recovery-study-2026-10-20'

def binding(path):
    data = path.read_bytes()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')

def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    shutil.copyfile(source, destination)

parser = argparse.ArgumentParser()
parser.add_argument('--source-commit', required=True)
args = parser.parse_args()
assert not OUT.exists()
head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip()
assert head == args.source_commit
sources = ['paper/conseqax-research.tex', 'paper/recovery-study-results.tex',
           'paper/recovery-availability-results.tex']
sources += ['paper/figures/' + stem + '.pdf' for stem in
            ('recovery-method-overview', 'recovery-family-primary-contrasts', 'recovery-availability-grid')]
for name in sources:
    assert (ROOT / name).read_bytes() == subprocess.check_output(
        ['git', '-C', str(ROOT), 'show', f'{head}:{name}']), name
qa = json.loads((TEMP / 'automated-pdf-qa.json').read_text(encoding='utf-8'))
assert qa['pages'] == 10 and qa['all_fonts_embedded']
assert qa['automated_text_and_font_checks_passed']
assert qa['pdf_sha256'] == binding(TEMP / 'conseqax-research.pdf')['sha256']
pages = sorted(TEMP.glob('verified-page-*.png'))
assert len(pages) == 10
evidence = [
    'output/recovery-controller-protocol-2026-10-20/protocol.json',
    'output/recovery-controller-protocol-2026-10-20/run-claim.json',
    'output/recovery-controller-study-2026-10-20/manifest.json',
    'output/recovery-controller-study-2026-10-20/completion-receipt.json',
    'output/recovery-artifact-finalization-2026-10-20/finalization-record.json',
    'output/recovery-artifact-finalization-2026-10-20/manifest.json',
    'output/recovery-controller-audit-2026-10-20/audit-receipt.json',
    'output/recovery-portable-audit-2026-10-20/portable-audit-receipt.json',
    'output/recovery-portable-audit-2026-10-20/manifest.json',
    'output/recovery-paired-analysis-2026-10-20-v2/manifest.json',
    'output/recovery-publication-figures-2026-10-20-v3/manifest.json',
    'output/recovery-availability-protocol-2026-10-20/protocol.json',
    'output/recovery-availability-protocol-2026-10-20/run-claim.json',
    'output/recovery-availability-study-2026-10-20/manifest.json',
    'output/recovery-availability-study-2026-10-20/completion-receipt.json',
    'output/recovery-availability-audit-2026-10-20/audit-receipt.json',
    'output/recovery-availability-audit-2026-10-20/manifest.json',
    'output/recovery-availability-figures-2026-10-20-v2/manifest.json',
]
OUT.mkdir(parents=True, exist_ok=False)
copy(TEMP / 'conseqax-research.pdf', OUT / 'ConseqaX_Research_Paper.pdf')
for name in sources:
    copy(ROOT / name, OUT / 'source' / name)
for name in evidence:
    copy(ROOT / name, OUT / 'evidence' / name)
for name in ('automated-pdf-qa.json', 'extracted-text.txt', 'compile-console.log', 'conseqax-research.log'):
    copy(TEMP / name, OUT / 'quality' / name)
for page in pages:
    copy(page, OUT / 'quality/pages' / page.name)
copy(Path(__file__), OUT / 'quality/package-paper.source.py')
write(OUT / 'source-bindings.json', {'source_commit': head,
      'sources_match_immutable_git_blobs': True,
      'files': {name: binding(ROOT / name) for name in sources}})
write(OUT / 'evidence-bindings.json', {'source_commit': head,
      'files': {name: binding(ROOT / name) for name in evidence},
      'scope': 'Manifest/receipt references; complete raw data remains at the recorded repository paths.'})
write(OUT / 'quality/visual-review.json', {
    'all_ten_pages_inspected': True, 'review_kind': 'AI-assisted rendered-page inspection',
    'pages_1_to_5': 'lead integrator', 'pages_6_to_10': 'separate AI visual reviewer',
    'passed': True, 'clipping_or_overlaps_found': False,
    'all_figures_precede_references': True,
    'scope': 'Visual quality check, not independent human validation or external scientific replication.',
    'page_bindings': {page.name: binding(page) for page in pages}})
compiler = Path('C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tectonic/tectonic.exe')
write(OUT / 'build-receipt.json', {
    'schema': 'conseqa-focused-paper-build-v1', 'complete': True,
    'packaged_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': head,
    'command': ['tectonic', 'paper/conseqax-research.tex', '--outdir', 'tmp/pdfs/recovery-study-2026-10-20', '--keep-logs'],
    'compiler': {'path': str(compiler), **binding(compiler)},
    'compile_exit_code': 0, 'pages': 10, 'fonts': 12, 'all_fonts_embedded': True,
    'automated_and_all_page_visual_checks_passed': True,
    'measured_worlds_or_model_calls_added_by_packaging': 0,
    'venue_specific_submission_compliance_not_asserted': True})
(OUT / 'README.md').write_text(
    '# Focused IEEE research draft\n\n'
    'This checked 10-page draft reports the objective recovery and controlled availability studies. '
    'Study A retains its packaging deviation, invariant timing seeds, strong-reference parity and negative polling result. '
    'Study B retains all 64 factor profiles, uniform physical success, classical-reference parity and actual reporting/read costs. '
    'Neither is an autonomous benchmark score or external service validation. No participant or annotation study is claimed.\n\n'
    'The PDF, exact TeX/figure inputs, all-page previews, font/text checks, compilation diagnostics and evidence references '
    'are bound by manifest.json. Source inputs match the recorded immutable Git commit. The source/ folder preserves '
    'the paper/ structure; compile source/paper/conseqax-research.tex using a compatible TeX environment with IEEEtran, '
    'newtx, placeins and the other declared packages. A compatible compiler need not reproduce PDF metadata bytes.\n\n'
    'Complete raw traces and SQLite snapshots are retained at the repository paths in evidence-bindings.json; '
    'this PDF bundle does not duplicate those raw worlds. It is a generic IEEE draft, with no chosen venue, '
    'acceptance claim, DOI-backed archive, or venue-specific page/anonymity certification. '
    'The author is Devrajsinh Jhala, Independent Researcher. Current software is 2.1.2; measured research is pinned to 2.1.1.\n',
    encoding='utf-8', newline='\n')
write(OUT / 'manifest.json', {
    'schema': 'conseqa-focused-paper-snapshot-v1', 'complete': True, 'source_commit': head,
    'files': {p.relative_to(OUT).as_posix(): binding(p) for p in sorted(OUT.rglob('*')) if p.is_file()}})
print(json.dumps({'complete': True, 'source_commit': head, 'pdf': binding(OUT / 'ConseqaX_Research_Paper.pdf'),
                  'snapshot_manifest': binding(OUT / 'manifest.json')}))
