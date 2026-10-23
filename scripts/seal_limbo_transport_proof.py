"""Seal an already closed task-independent transport proof, without inference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.limbo_agent.protocol import source_binding, utc, write_new  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    directory = args.proof.resolve()
    if (directory / 'manifest.json').exists():
        raise ValueError('Refuse resealing an existing proof')
    result = json.loads((directory / 'probe-result.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'client/client-summary.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (directory / 'client/model-calls.jsonl').read_text(encoding='utf-8').splitlines()]
    starts = [r for r in rows if r['event'] == 'request_start']
    dispatches = [r for r in rows if r['event'] == 'before_dispatch']
    returns = [r for r in rows if r['event'] == 'request_return']
    if (not result['passed'] or result['native_episodes'] != 0
            or len(starts) != len(dispatches) or len(returns) != len(starts)
            or summary['invocations'] != len(starts)
            or summary['generation_dispatch_attempts'] != len(dispatches)
            or len(starts) != 2):
        raise ValueError('Need a closed, passed two-call proof with complete accounting')
    sources = source_binding(ROOT)
    for name in sources:
        target = directory / 'execution-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    shutil.copyfile(__file__, directory / 'sealing-helper.source.py')
    write_new(directory / 'seal-receipt.json', {
        'utc': utc(), 'sources': sources, 'passed': True,
        'scope': 'Postcompletion packaging of original raw proof; not prospective source registration',
        'model_generation_requests_by_sealer': 0, 'native_episodes': 0,
        'actual_dispatch_attempts': len(dispatches), 'returned_completions': len(returns),
        'source_copies_observed_after_collection': True,
    })
    inventory = {}
    for path in sorted(directory.rglob('*')):
        if path.is_file():
            data = path.read_bytes()
            inventory[path.relative_to(directory).as_posix()] = {
                'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    write_new(directory / 'manifest.json', inventory)
    print(json.dumps({'sealed': str(directory), 'files': len(inventory), 'dispatches': len(dispatches)}))


if __name__ == '__main__':
    main()
