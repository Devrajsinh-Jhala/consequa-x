"""Read-only auxiliary observations using the already tested resource sampler."""
import argparse
import json
from pathlib import Path

import psutil

import observe_native_resources as sampler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path, required=True)
    args = parser.parse_args()
    path = args.runtime_binding.resolve()
    runtime = json.loads(path.read_text(encoding='utf-8'))
    processes = {}
    for role in ('server', 'runner'):
        born = runtime[role + '_create_time']
        processes[role] = sampler.bind_process(psutil, runtime[role + '_pid'],
            runtime[role + '_executable'], runtime[role + '_executable_sha256'],
            (born - .001, born + .001), runtime['server_pid'] if role == 'runner' else None)
    source = Path(__file__).resolve()
    binding = {'schema': 'limbo-resource-observer-binding-v1', 'created_utc': sampler.utc(),
        'scope': 'Auxiliary read-only bound-process CPU/RSS and system available RAM; no inference or process control',
        'script': {'path': str(Path(sampler.__file__).resolve()), 'sha256': sampler.sha_file(sampler.__file__)},
        'adapter_source': {'path': str(source), 'sha256': sampler.sha_file(source),
                           'source': source.read_text(encoding='utf-8')},
        'inputs': {'runtime_binding': {'path': str(path), 'sha256': sampler.sha_file(path)}},
        'processes': processes, 'model_blob_sha256': runtime['model_blob_sha256'],
        'cpu_percent_definition': '100*processCPUdelta/monotonicwalltime; may exceed100 across cores; firstsample null',
        'limitations': ['Thirty-second sampling does not establish true peaks',
            'RSS can count shared pages', 'Unobserved programs affect available RAM',
            'Caches and host load prevent causal SDK-overhead inference'],
        'actual_generation_requests': 0, 'network_requests': 0}
    code, summary = sampler.observe(binding, args.output, args.stop_file, 30, psutil)
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
