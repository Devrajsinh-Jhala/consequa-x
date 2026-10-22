"""One dated paper snapshot; no model, evaluator, network, or Git mutation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageDraw
from pypdf import PdfReader

ROOT = Path('D:/ConsequaX-Research/paper-writing')
WORK = ROOT / 'tmp/pdfs/native-integration-2026-10-22-r2'
OUT = ROOT / 'output/pdf/native-integration-2026-10-22'
COMPILER = Path('C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tectonic/tectonic.exe')
POPPLER = Path('C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
INPUTS = ('paper/conseqax-research.tex', 'paper/native-external-validation.tex',
          'paper/recovery-study-results.tex', 'paper/recovery-availability-results.tex',
          'paper/figures/recovery-method-overview.pdf',
          'paper/figures/recovery-family-primary-contrasts.pdf',
          'paper/figures/recovery-availability-grid.pdf',
          'paper/figures/native-four-arm-methods.pdf')
EXTRA = ('paper/conseqax-research.md', 'paper/native-development-claims-2026-10-21.json')


def binding(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def command(args, cwd=ROOT):
    return subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, check=False)


def main():
    if WORK.exists() or OUT.exists():
        raise SystemExit('Refuse existing dated work/output directory')
    head = command(['git', 'rev-parse', 'HEAD'])
    assert head.returncode == 0
    commit = head.stdout.decode().strip()
    sources = {}
    for name in INPUTS + EXTRA:
        actual = (ROOT / name).read_bytes()
        blob = command(['git', 'show', f'{commit}:{name}'])
        assert blob.returncode == 0 and blob.stdout == actual, name
        sources[name] = binding(actual)
    source, build, quality = WORK / 'source', WORK / 'build', WORK / 'quality'
    for directory in (source, build, quality):
        directory.mkdir(parents=True, exist_ok=False)
    for name in INPUTS + EXTRA:
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    args = [COMPILER, 'paper/conseqax-research.tex', '--only-cached', '--outdir', '../build',
            '--keep-logs', '--keep-intermediates', '--makefile-rules', '../quality/compile-dependencies.d']
    result = command(args, source)
    (quality / 'compile.stdout.log').write_bytes(result.stdout)
    (quality / 'compile.stderr.log').write_bytes(result.stderr)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    log = (build / 'conseqax-research.log').read_text(errors='replace')
    bad = [line for line in log.splitlines() if re.search(
        r'Overfull|undefined references|Reference .* undefined|Citation .* undefined|Missing character', line)]
    assert not bad, bad
    pdf = build / 'conseqax-research.pdf'
    reader = PdfReader(pdf)
    fonts = {}
    for page in reader.pages:
        resources = page['/Resources'].get_object()
        font_map = resources.get('/Font', {})
        if hasattr(font_map, 'get_object'):
            font_map = font_map.get_object()
        for ref in font_map.values():
            font = ref.get_object()
            for item in font.get('/DescendantFonts', [font]):
                current = item.get_object()
                descriptor = current.get('/FontDescriptor')
                assert descriptor is not None
                descriptor = descriptor.get_object()
                embedded = any(descriptor.get(key) for key in ('/FontFile', '/FontFile2', '/FontFile3'))
                assert embedded, str(current.get('/BaseFont'))
                fonts[str(current.get('/BaseFont'))] = {'embedded': True}
    text = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
    assert '\ufffd' not in text
    (quality / 'extracted-text.txt').write_text(text, encoding='utf-8')
    info = command([POPPLER / 'pdfinfo.exe', pdf])
    assert info.returncode == 0
    (quality / 'pdfinfo.txt').write_bytes(info.stdout)
    rendered = command([POPPLER / 'pdftoppm.exe', '-r', '110', '-png', pdf, quality / 'page'])
    assert rendered.returncode == 0
    pages = sorted(quality.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
    assert len(pages) == len(reader.pages)
    for start in range(0, len(pages), 4):
        sheet = Image.new('RGB', (1300, 1740), '#e2e5e8')
        draw = ImageDraw.Draw(sheet)
        for offset, page in enumerate(pages[start:start+4]):
            image = Image.open(page).convert('RGB')
            image.thumbnail((620, 820))
            x, y = (offset % 2) * 650 + 15, (offset // 2) * 870 + 30
            draw.text((x, y - 20), f'Page {start+offset+1}', fill='#111111')
            sheet.paste(image, (x, y))
        sheet.save(quality / f'contact-sheet-{start//4+1}.png')
    OUT.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, OUT / 'source')
    shutil.copytree(quality, OUT / 'quality')
    shutil.copyfile(pdf, OUT / 'ConseqaX_Research_Paper.pdf')
    shutil.copyfile(build / 'conseqax-research.log', OUT / 'quality/compile.tex.log')
    shutil.copyfile(__file__, OUT / 'quality/build_snapshot.source.py')
    write(OUT / 'source-bindings.json', {'source_commit': commit, 'sources_match_immutable_git_blobs': True,
        'files': sources, 'compiler': {'path': str(COMPILER), **binding(COMPILER.read_bytes())},
        'compile_command': list(map(str, args)), 'offline_cached_resources_only': True})
    write(OUT / 'build-receipt.json', {'schema': 'conseqax-native-integration-paper-build-v1',
        'built_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': commit,
        'compile_exit_code': result.returncode, 'pages': len(reader.pages),
        'pdf': binding(pdf.read_bytes()), 'fonts': fonts, 'all_fonts_embedded': True,
        'blocking_tex_warnings': bad, 'underfull_warnings': log.count('Underfull'),
        'visual_review_pending': True, 'official_pilot_results': False,
        'new_model_calls': 0, 'new_native_evaluations': 0, 'human_labels': 0})
    print(json.dumps({'output': str(OUT), 'pages': len(reader.pages), 'fonts': len(fonts),
                      'source_commit': commit, 'pdf': binding(pdf.read_bytes())}))


if __name__ == '__main__':
    main()
