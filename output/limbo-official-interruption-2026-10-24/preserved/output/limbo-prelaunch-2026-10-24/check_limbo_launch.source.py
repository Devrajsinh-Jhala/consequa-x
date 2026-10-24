"""Read-only publication and readiness cross-check before one-shot collection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.limbo_agent.audit import require, verify_manifest  # noqa: E402
from research.limbo_agent.harness import manifest  # noqa: E402
from research.limbo_agent.protocol import file_binding, utc, verify_protocol, write_new  # noqa: E402

SUPPORT = (
    'scripts/analyze_limbo_external_benchmark.py', 'scripts/run_limbo_completion_pipeline.py',
    'scripts/check_limbo_readiness.py', 'scripts/check_limbo_saved_proposal_receipt.py',
    'scripts/check_limbo_launch.py', 'scripts/seal_limbo_transport_proof.py',
    'docs/limbo-analysis-plan-2026-10-24.md', 'docs/limbo-readiness-amendment-2026-10-24.md',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', required=True, type=Path)
    parser.add_argument('--protocol', required=True, type=Path)
    parser.add_argument('--protocol-commit', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    protocol = verify_protocol(ROOT, args.native_root, args.protocol, args.protocol_commit)
    ready_path = Path(protocol['readiness']['path'])
    ready = json.loads(ready_path.read_text(encoding='utf-8'))
    verify_manifest(ready_path.parent)
    require(ready.get('passed') is True and ready.get('schema') == 'conseqax-limbo-separated-readiness-v1',
            'Passed separated readiness is required')
    require(file_binding(ready_path) == {key: protocol['readiness'][key] for key in ('sha256', 'bytes')},
            'Frozen readiness bytes changed')
    for key in ('sources', 'native', 'runtime_binding'):
        require(ready[key] == protocol[key], 'Protocol/readiness identity differs: ' + key)
    require(ready['wheel_file'] == {key: protocol['wheel'][key] for key in ('sha256', 'bytes')},
            'Protocol/readiness wheel differs')
    names = set(SUPPORT) | set(protocol['sources'])
    for path in (args.protocol, ready_path, Path(protocol['runtime_binding_file']['path'])):
        names.add(path.resolve().relative_to(ROOT).as_posix())
    evidence = list(ready['development_audits'].values()) + [ready[name] for name in
        ('transport_proof', 'scripted_receipt_path_proof', 'prospective_amendment', 'readiness_checker')]
    for item in evidence:
        path = Path(item['path'])
        require(file_binding(path) == {key: item[key] for key in ('sha256', 'bytes')},
                'Readiness evidence changed: ' + str(path))
        names.add(path.resolve().relative_to(ROOT).as_posix())
    verified = {}
    for name in sorted(names):
        blob = subprocess.run(['git', '-C', str(ROOT), 'show', f'{args.protocol_commit}:{name}'],
                              check=True, capture_output=True).stdout
        require(blob == (ROOT / name).read_bytes(), 'Published artifact differs: ' + name)
        verified[name] = file_binding(ROOT / name)
    remote = subprocess.run(['git', '-C', str(ROOT), 'ls-remote', 'origin', 'refs/heads/main'],
                            check=True, capture_output=True, text=True).stdout.split()
    require(len(remote) == 2 and remote[0] == args.protocol_commit,
            'The exact protocol commit must be the verified published main head before launch')
    for role in ('server', 'runner'):
        binding = protocol['runtime_binding']
        process = psutil.Process(binding[role + '_pid'])
        require(abs(process.create_time() - binding[role + '_create_time']) < .001,
                'Bound runtime process identity changed')
        require(Path(process.exe()).resolve() == Path(binding[role + '_executable']).resolve(),
                'Bound runtime executable changed')
        require(file_binding(Path(process.exe()))['sha256'] == binding[role + '_executable_sha256'],
                'Bound runtime executable bytes changed')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / 'prelaunch.json', {'passed': True, 'utc': utc(),
        'protocol_commit': args.protocol_commit, 'observed_remote_main': remote[0],
        'protocol': file_binding(args.protocol), 'readiness': file_binding(ready_path),
        'published_files_verified': verified, 'runtime_process_identities_checked': True,
        'model_generations': 0, 'scope': 'Read-only publication and readiness check; no benchmark score'})
    (out / 'check_limbo_launch.source.py').write_bytes(Path(__file__).read_bytes())
    write_new(out / 'manifest.json', manifest(out))
    print(json.dumps({'passed': True, 'files': len(verified), 'protocol_commit': args.protocol_commit}))


if __name__ == '__main__':
    main()
