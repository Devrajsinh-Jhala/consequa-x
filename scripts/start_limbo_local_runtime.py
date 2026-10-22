"""Start a separate local research listener and load existing weights only."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/limbo-runtime-2026-10-22'
EXE = Path('C:/Users/DELL/AppData/Local/Programs/Ollama/ollama.exe')
MODELS = Path('C:/Users/DELL/.ollama/models')
BASE_TAG = 'qwen3:4b-instruct-2507-q4_K_M'
TAG = 'conseqax-limbo-qwen4b-20261022:ctx8k'
BLOB_SHA = '85e4a5b7b8ef0e48af0e8658f5aaab9c2324c76c1641493f4d1e25fce54b18b9'
BLOB = MODELS / ('blobs/sha256-' + BLOB_SHA)
BASE_MANIFEST = MODELS / 'manifests-v2/ollama.com/library/qwen3/4b-instruct-2507-q4_K_M'
SERVER = 'http://127.0.0.1:11436'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write(name, value):
    with (OUT / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    if OUT.exists():
        raise SystemExit('Refuse existing one-shot runtime output')
    with socket.socket() as test:
        test.bind(('127.0.0.1', 11436))
    required = BLOB.stat().st_size + 612 * 1024**2 + 1024**3
    available = psutil.virtual_memory().available
    if available < required:
        raise SystemExit(f'Cold memory gate: {available} available, {required} required')
    assert digest(BLOB) == BLOB_SHA
    config = {'OLLAMA_HOST': '127.0.0.1:11436', 'OLLAMA_MODELS': str(MODELS),
        'OLLAMA_NO_CLOUD': '1', 'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1',
        'OLLAMA_KV_CACHE_TYPE': 'q8_0', 'OLLAMA_FLASH_ATTENTION': '1',
        'OLLAMA_CONTEXT_LENGTH': '8192', 'OLLAMA_KEEP_ALIVE': '-1',
        'OLLAMA_NOPRUNE': '1', 'OLLAMA_DEBUG': '1'}
    env, removed = dict(os.environ), []
    for name in tuple(env):
        upper = name.upper()
        if (upper.endswith(('_API_KEY', '_API_TOKEN', '_ACCESS_TOKEN')) or upper in
            {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
             'GOOGLE_APPLICATION_CREDENTIALS', 'AWS_SHARED_CREDENTIALS_FILE'}):
            env.pop(name, None)
            removed.append(name)
    env.update(config)
    OUT.mkdir(parents=True, exist_ok=False)
    before = digest(BASE_MANIFEST)
    record = {'started_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'New separate LIMBO candidate; existing weights, no download or completion',
        'model_generation_attempts': 0, 'model_load_requests': 0, 'model_downloads': 0,
        'server_executable': str(EXE), 'server_executable_sha256': digest(EXE),
        'process_only_environment': config, 'removed_environment_names': sorted(removed),
        'base_manifest_sha256_before': before, 'normal_service_modified': False,
        'cold_memory_gate': {'available_bytes': available, 'required_bytes': required,
          'scope': 'Weights + expected single8k q8 KV +1GiB reserve, not maximum later memory'}}
    write('start.json', record)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    with (OUT / 'server.stdout.log').open('xb') as stdout, (OUT / 'server.stderr.log').open('xb') as stderr:
        process = subprocess.Popen([str(EXE), 'serve'], env=env, stdout=stdout, stderr=stderr,
            startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(path, payload=None, timeout=120):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(SERVER + path, data=data,
            headers={'Content-Type': 'application/json'})
        with opener.open(request, timeout=timeout) as response:
            return json.load(response)

    for attempt in range(40):
        try:
            version = api('/api/version', timeout=2)
            break
        except Exception:
            if process.poll() is not None:
                raise RuntimeError('Research listener exited; no unrelated process is touched')
            time.sleep(.5)
    else:
        raise RuntimeError('Research listener readiness failed')
    tags = api('/api/tags')['models']
    if any(item['name'] == TAG for item in tags):
        raise RuntimeError('Refuse replacing existing research model alias')
    created = api('/api/create', {'model': TAG, 'from': BASE_TAG,
        'parameters': {'num_ctx': 8192, 'num_predict': 512, 'temperature': 0, 'seed': 1701},
        'stream': False})
    write('alias-create.json', created)
    show = api('/api/show', {'model': TAG})
    write('model-show.json', show)
    # An empty prompt requests loading only; no completion tokens are requested.
    loaded = api('/api/generate', {'model': TAG, 'prompt': '', 'stream': False,
        'keep_alive': -1, 'options': {'num_ctx': 8192, 'num_predict': 0}})
    write('load-only.json', loaded)
    assert loaded.get('done_reason') == 'load' and not loaded.get('response')
    resident = [item for item in api('/api/ps')['models'] if item['name'] == TAG]
    assert len(resident) == 1 and resident[0]['context_length'] == 8192
    write('resident-model.json', resident[0])
    server = psutil.Process(process.pid)
    candidates = [p for p in server.children(recursive=True) if p.name().lower() == 'llama-server.exe']
    assert len(candidates) == 1
    runner = candidates[0]
    args = runner.cmdline()
    port = int(args[args.index('--port') + 1])
    assert str(BLOB).lower() in ' '.join(args).lower()
    binding = {'api_base': SERVER + '/v1', 'model': TAG, 'model_digest': resident[0]['digest'],
        'model_blob': str(BLOB), 'model_blob_sha256': BLOB_SHA,
        'server_pid': server.pid, 'server_executable': server.exe(),
        'server_executable_sha256': digest(Path(server.exe())), 'server_create_time': server.create_time(),
        'runner_pid': runner.pid, 'runner_executable': runner.exe(),
        'runner_executable_sha256': digest(Path(runner.exe())), 'runner_create_time': runner.create_time(),
        'runner_port': port, 'context_tokens': 8192, 'parallel_slots': 1}
    write('runtime-binding.json', binding)
    record.update({'finished_utc': datetime.now(timezone.utc).isoformat(), 'server_pid': server.pid,
        'runner_pid': runner.pid, 'version_response': version, 'model_load_requests': 1,
        'base_manifest_sha256_after': digest(BASE_MANIFEST), 'runtime_binding': binding})
    assert record['base_manifest_sha256_after'] == before
    write('launch-receipt.json', record)
    print(json.dumps({'status': 'resident_candidate', 'binding': str(OUT / 'runtime-binding.json'),
        'server_pid': server.pid, 'runner_pid': runner.pid, 'context': 8192,
        'generation_attempts': 0, 'load_requests': 1}))


if __name__ == '__main__':
    main()
