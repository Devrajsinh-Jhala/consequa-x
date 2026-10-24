"""Bind preserved native validation to a separately checked relocated runtime."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.limbo_agent.audit import jsonl, require, verify_manifest  # noqa: E402
from research.limbo_agent.harness import installed_wheel_binding, manifest  # noqa: E402
from research.limbo_agent.protocol import (  # noqa: E402
    environment_binding, file_binding, native_binding, source_binding, utc, write_new,
)

ORIGINAL_COMMIT = '267cd1a3e846c46c009f20accbf302746e064875'
HISTORICAL_ROOT = PureWindowsPath('D:/ConsequaX-Research/paper-writing')


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON: ' + value)))


def current_path(recorded):
    """Resolve only the declared move; never rewrite the historical bytes."""
    path = PureWindowsPath(recorded)
    try:
        relative = path.relative_to(HISTORICAL_ROOT)
    except ValueError as exc:
        raise ValueError('Historical evidence is outside the declared research root') from exc
    require('..' not in relative.parts, 'Historical path escapes the research root')
    return ROOT.joinpath(*relative.parts)


def check_preserved(item):
    path = current_path(item['path'])
    require(file_binding(path) == {key: item[key] for key in ('sha256', 'bytes')},
            'Preserved historical evidence changed: ' + str(path))
    return path


def bound(path):
    return {'path': str(Path(path).resolve()), **file_binding(path)}


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def timestamp(value):
    result = datetime.fromisoformat(value)
    require(result.tzinfo is not None, 'Evidence timestamps must include their UTC offset')
    return result.timestamp()


def ambient_job(value):
    require(value.get('query_current_job_succeeded') is True
            and type(value.get('limit_flags')) is int and value['limit_flags'] == 6144
            and value.get('kill_on_job_close') is False
            and value.get('breakaway_ok') is True and value.get('silent_breakaway_ok') is True,
            'Need actual non-killing ambient job limits, not a summary assertion')


def same_identity(left, right):
    fields = ('pid', 'create_time', 'executable', 'command_line', 'username')
    require(all(left.get(key) == right.get(key) for key in fields), 'Process identity chain differs')
    require(type(left.get('pid')) is int and left['pid'] > 0
            and number(left.get('create_time')) and left['create_time'] > 0
            and isinstance(left.get('username'), str) and left['username'], 'Invalid process identity')


def validate_durability(proof_path):
    """Recompute the closed sentinel proof; no process, network or model calls."""
    proof_path = Path(proof_path).resolve()
    directory = proof_path.parent
    require(proof_path.name == 'lifetime-proof.json', 'Need the sealed lifetime proof artifact')
    require(all(not path.is_symlink() for path in directory.rglob('*')), 'Proof symlinks are refused')
    inventory = load(directory / 'manifest.json')
    require(isinstance(inventory, dict), 'Need a sealed proof file inventory')
    verify_manifest(directory)
    proof = load(proof_path)
    require(proof.get('schema') == 'conseqax-durable-lifetime-proof-v1' and proof.get('passed') is True,
            'Creator-independent delayed sentinel proof did not pass')
    refs = proof.get('raw_binding_references')
    require(isinstance(refs, dict) and set(refs) == set(inventory) - {proof_path.name}
            and all(value == inventory[name] for name, value in refs.items()),
            'Lifetime raw bindings must cover the complete sealed inventory')
    required = {'launch-config.json', 'launch-receipt.json', 'terminal-receipt.json',
        'sentinel/started.json', 'sentinel/delayed-sentinel.json', 'supervisor-identity.json',
        'wmi-handoff-identity.json', 'wmi-handoff-receipt.json', 'wmi-create-result.json',
        'tool-return-observation.json', 'launcher-source.py', 'sentinel-source.py'}
    require(required <= set(refs), 'Lifetime proof is missing raw chain evidence')
    config, launched, terminal, started, ended, supervisor, handoff, handed, created, tool = [
        load(directory / name) for name in ('launch-config.json', 'launch-receipt.json',
        'terminal-receipt.json', 'sentinel/started.json', 'sentinel/delayed-sentinel.json',
        'supervisor-identity.json', 'wmi-handoff-identity.json', 'wmi-handoff-receipt.json',
        'wmi-create-result.json', 'tool-return-observation.json')]
    require(config.get('job_policy') == proof.get('job_policy') == launched.get('job_policy')
            == 'ambient_non_killing' and config.get('mechanism') == proof.get('launch_mechanism')
            == 'wmi_two_stage', 'Lifetime proof uses a different explicit launch criterion')
    require(config.get('creationflags') == 0x01000208
            and config['parent_current_job_limits'].get('kill_on_job_close') is True,
            'Need the actual parent kill-on-close job and all declared creation flags')
    require(launched.get('status') == 'launched_not_complete'
            and launched.get('no_job_breakaway_fallback') is True
            and launched.get('config_binding') == file_binding(directory / 'launch-config.json'),
            'Launch receipt/config bytes differ')
    require(terminal.get('status') == 'target_exited' and type(terminal.get('return_code')) is int
            and terminal['return_code'] == 0 and type(proof.get('target_exit_code')) is int
            and proof['target_exit_code'] == 0, 'Lifetime target did not exit successfully')
    target = started['identity']
    for other in (ended['identity'], launched['target'], terminal['target']):
        same_identity(target, other)
    same_identity(supervisor, launched['supervisor'])
    same_identity(supervisor, handed['supervisor'])
    require(created.get('ReturnValue') == 0 and created.get('ProcessId') == handoff.get('pid'),
            'WMI handoff identity differs from actual creation result')
    user = config['parent'].get('username')
    require(user and all(item.get('username') == user for item in (target, supervisor, handoff)),
            'Lifetime chain changed Windows user')
    for value in (started, ended, supervisor, handoff):
        limits = value['current_job_limits']
        ambient_job(limits)
        identity = value.get('identity', value)
        require(identity.get('in_any_windows_job') is True
                and limits.get('process_id_list_complete') is True
                and identity['pid'] in limits.get('process_ids', []),
                'Observed process is absent from its actual ambient job inventory')
    ambient_job(launched['supervisor_current_job_limits'])
    require(launched['target'].get('listed_in_supervisor_non_killing_ambient_job') is True,
            'Actual target ambient membership was not verified')
    require(config['launcher_source_binding'] == refs['launcher-source.py']
            and {key: started['source'][key] for key in ('sha256', 'bytes')} == refs['sentinel-source.py'],
            'Lifetime executable source snapshots differ')
    for label, relative in (('stdout', 'target.stdout.log'), ('stderr', 'target.stderr.log')):
        require(terminal.get(label) == refs.get(relative), 'Closed target log binding differs')
    elapsed = ended.get('elapsed_monotonic_s')
    require(number(elapsed) and elapsed >= 15 and started.get('planned_delay_s') == 15
            and proof.get('sentinel_elapsed_s') == elapsed, 'Sentinel delay is missing, short or inconsistent')
    require(all(type(row.get(name)) is int and row[name] == 0 for row in (started, ended, proof)
                for name in ('model_calls', 'network_calls')), 'Lifetime probe performed unexpected work')
    duration = tool.get('wall_time_seconds')
    require(tool.get('source_kind') == 'Codex exec_command tool result'
            and isinstance(tool.get('chunk_id'), str) and tool['chunk_id']
            and type(tool.get('exit_code')) is int and tool['exit_code'] == 0
            and number(duration) and 0 < duration < 15, 'Missing actual successful launching tool observation')
    parent_birth = config['parent'].get('create_time')
    require(number(parent_birth), 'Missing actual parent process birth')
    upper_bound = parent_birth + duration
    finished, beginning = timestamp(ended['finished_utc']), timestamp(started['started_utc'])
    require(beginning < finished and abs((finished - beginning) - elapsed) < 1
            and upper_bound < finished, 'Raw timing does not prove delayed completion after tool return')
    require(abs(timestamp(proof['tool_return_upper_bound_utc']) - upper_bound) < .00001
            and timestamp(proof['delayed_completion_utc']) == finished,
            'Stored timing summary differs from its conservative raw upper bound')
    require(proof.get('tool_returned_before_delayed_completion') is True
            and proof.get('same_user_throughout') is True
            and proof.get('self_observed_job_flags') == [6144, 6144]
            and proof.get('self_observed_kill_on_job_close') == [False, False],
            'Lifetime summary differs from recomputed observations')
    return {'passed': True, 'manifest_binding': file_binding(directory / 'manifest.json'),
        'target_exit_code': 0, 'sentinel_elapsed_s': elapsed, 'job_flags': [6144, 6144],
        'kill_on_job_close': False, 'same_user': True, 'user': user,
        'tool_return_upper_bound_utc': datetime.fromtimestamp(upper_bound, timezone.utc).isoformat(),
        'delayed_completion_utc': ended['finished_utc'],
        'launcher_source_binding': refs['launcher-source.py'],
        'scope': 'Observed escape from tool kill-on-close job and delayed completion; ambient job retained. No reboot/logoff or arbitrary termination survival claim.'}


def streamed_binding(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return {'sha256': value.hexdigest(), 'bytes': Path(path).stat().st_size}


def validate_runtime_launch(runtime_path, runtime, durability):
    """Bind immutable launch metadata; never seal/read the running server logs."""
    runtime_path = Path(runtime_path).resolve()
    directory = runtime_path.parent
    receipt = load(directory / 'launch-receipt.json')
    require(receipt.get('schema') == 'conseqax-durable-limbo-runtime-v1'
            and receipt.get('runtime_binding') == runtime and receipt.get('job_policy') == 'ambient_non_killing',
            'Current runtime launch receipt/binding differs')
    require(receipt.get('model_generation_attempts') == receipt.get('model_downloads') == 0
            and receipt.get('model_load_requests') == 1 and receipt.get('normal_service_modified') is False
            and receipt['base_manifest_before'] == receipt['base_manifest_after'],
            'Runtime load/download/generation/original-model accounting differs')
    loaded = load(directory / 'load-only.json')
    require(loaded.get('done_reason') == 'load' and loaded.get('response') == ''
            and loaded.get('model') == runtime['model']
            and loaded.get('eval_count', 0) == loaded.get('prompt_eval_count', 0) == 0,
            'Expected an actual zero-completion empty-prompt model load')
    require(receipt.get('version_response', {}).get('version') == receipt.get('declared_runtime_version') == '0.40.10',
            'New execution condition runtime version differs')
    required_env = {'OLLAMA_HOST': '127.0.0.1:11436', 'OLLAMA_NO_CLOUD': '1',
        'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1', 'OLLAMA_KV_CACHE_TYPE': 'q8_0',
        'OLLAMA_FLASH_ATTENTION': '1', 'OLLAMA_CONTEXT_LENGTH': '8192', 'OLLAMA_KEEP_ALIVE': '-1'}
    require(all(receipt['process_only_environment'].get(key) == value for key, value in required_env.items()),
            'Private runtime context/cache/offline/process environment differs')
    resident = load(directory / 'resident-model.json')
    require(resident.get('name') == runtime['model'] and resident.get('digest') == runtime['model_digest']
            and resident.get('context_length') == 8192 and runtime['parallel_slots'] == 1,
            'Loaded model/context differs from runtime binding')
    launch_dir = directory / 'durable-server-launch'
    config, launched, supervisor, handoff = [load(launch_dir / name) for name in (
        'launch-config.json', 'launch-receipt.json', 'supervisor-identity.json', 'wmi-handoff-identity.json')]
    require(config.get('mechanism') == 'wmi_two_stage' and config.get('job_policy') == 'ambient_non_killing'
            and config['parent_current_job_limits'].get('kill_on_job_close') is True
            and config['launcher_source_binding'] == durability['launcher_source_binding']
            == file_binding(launch_dir / 'launcher-source.py'), 'Runtime did not use the validated durability chain')
    require(launched.get('config_binding') == file_binding(launch_dir / 'launch-config.json')
            and launched.get('status') == 'launched_not_complete'
            and launched['target'].get('listed_in_supervisor_non_killing_ambient_job') is True,
            'Private server actual durable launch evidence differs')
    for item in (supervisor, handoff):
        ambient_job(item['current_job_limits'])
        require(item.get('username') == config['parent'].get('username') == durability['user'],
                'Runtime launch user differs from the verified lifetime chain')
    same_identity(supervisor, launched['supervisor'])
    target = launched['target']
    require(target['pid'] == runtime['server_pid'] and target['create_time'] == runtime['server_create_time']
            and PureWindowsPath(target['executable']) == PureWindowsPath(runtime['server_executable'])
            and target['username'] == durability['user'], 'Private server identity/birth/executable differs')
    private_ref = receipt['private_runtime_manifest']
    private_path = Path(private_ref['path']).resolve()
    require(streamed_binding(private_path) == {key: private_ref[key] for key in ('sha256', 'bytes')},
            'Private CPU runtime inventory changed')
    private = load(private_path)
    require(private.get('schema') == 'conseqax-private-cpu-runtime-v1'
            and private.get('source_before_equals_source_after_equals_private_copy') is True
            and private.get('declared_version') == receipt['declared_runtime_version'], 'Private CPU copy proof differs')
    private_root = private_path.parent
    require(Path(private['destination']).resolve() == private_root, 'Private CPU runtime location differs')
    paths = list(private_root.rglob('*'))
    require(all(not path.is_symlink() for path in paths), 'Private runtime symlinks are refused')
    actual = {path.relative_to(private_root).as_posix() for path in paths if path.is_file() and path != private_path}
    require(actual == set(private['files']), 'Private CPU file inventory differs')
    for name, expected in private['files'].items():
        require(streamed_binding(private_root / name) == expected, 'Private CPU runtime file changed: ' + name)
    for role, relative in (('server', 'ollama.exe'), ('runner', 'lib/ollama/llama-server.exe')):
        require(Path(runtime[role + '_executable']).resolve() == (private_root / relative).resolve()
                and runtime[role + '_executable_sha256'] == private['files'][relative]['sha256'],
                'Bound runtime executable differs from private CPU inventory: ' + role)
    names = ('start.json', 'alias-create.json', 'load-only.json', 'model-show.json',
        'resident-model.json', 'runtime-binding.json', 'launch-receipt.json',
        'durable-server-launch/launch-config.json', 'durable-server-launch/launch-receipt.json',
        'durable-server-launch/launcher-source.py', 'durable-server-launch/supervisor-identity.json',
        'durable-server-launch/wmi-handoff-identity.json', 'durable-server-launch/wmi-handoff-receipt.json',
        'durable-server-launch/wmi-request.json', 'durable-server-launch/wmi-create-result.json',
        'durable-server-launch/create-wmi-supervisor.ps1')
    return {'current_runtime_launch': bound(directory / 'launch-receipt.json'),
        'private_runtime_manifest': bound(private_path),
        'current_runtime_launch_evidence': {(directory / name).relative_to(ROOT).as_posix():
                                          file_binding(directory / name) for name in names}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native-root', 'wheel', 'runtime-binding', 'prior-readiness',
                 'transport-proof', 'schema-proof', 'amendment', 'durability-proof', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    ready_path = args.prior_readiness.resolve()
    relative = ready_path.relative_to(ROOT).as_posix()
    committed = subprocess.run(['git', '-C', str(ROOT), 'show', f'{ORIGINAL_COMMIT}:{relative}'],
                               check=True, capture_output=True).stdout
    require(committed == ready_path.read_bytes(), 'Preserved readiness differs from original published bytes')
    verify_manifest(ready_path.parent)
    prior = load(ready_path)
    require(prior.get('passed') is True and prior.get('schema') == 'conseqax-limbo-separated-readiness-v1',
            'Need original passed separated readiness')
    sources, native = source_binding(ROOT), native_binding(args.native_root)
    require(prior['sources'] == sources and prior['native'] == native,
            'The new condition must retain the same scientific/native source')
    require(prior['wheel_file'] == file_binding(args.wheel), 'Selected SDK wheel changed')
    installed = installed_wheel_binding(args.wheel)
    for key in ('framework_payload', 'framework_payload_count', 'framework_version', 'framework_wheel_sha256'):
        require(installed[key] == prior['wheel'][key], 'Installed SDK payload changed: ' + key)
    historical = {}
    for kind, item in prior['development_audits'].items():
        path = check_preserved(item)
        verify_manifest(path.parent)
        audit = load(path)
        require(audit['passed'] is True and audit['row']['audit_complete'] is True
                and audit['row']['execution_success'] is True and audit['sources'] == sources,
                'Preserved native audit failed or source changed')
        episode = current_path(audit['episode'])
        verify_manifest(episode)
        require(file_binding(episode / 'manifest.json') == audit['episode_manifest'],
                'Preserved native episode inventory changed')
        historical[kind] = {'recorded_binding': item, 'relocated_evidence': bound(path),
                            'runtime_binding': prior['runtime_binding']}
    receipt_path = check_preserved(prior['scripted_receipt_path_proof'])
    verify_manifest(receipt_path.parent)
    receipt = load(receipt_path)
    require(receipt['passed'] is True and receipt['receipt_count'] > 0
            and receipt['model_generations'] == 0 and receipt['native_task_grade_computed'] is False
            and all(receipt['parity'].values()) and receipt['sources'] == sources,
            'Preserved actual SDK path proof failed')
    for name in ('transport_proof', 'prospective_amendment', 'readiness_checker'):
        check_preserved(prior[name])
    runtime = load(args.runtime_binding)
    require(runtime['model_blob_sha256'] == prior['runtime_binding']['model_blob_sha256']
            and runtime['context_tokens'] == prior['runtime_binding']['context_tokens'] == 8192
            and runtime['parallel_slots'] == 1, 'Model weights/context/parallelism changed')
    verify_manifest(args.transport_proof.parent)
    transport = load(args.transport_proof)
    require(transport.get('passed') is True and transport['runtime'] == runtime
            and transport['native_episodes'] == transport['service_dispatches'] == 0
            and transport['model_invocation_cap'] == 2, 'New runtime two-call proof failed')
    seal = load(args.transport_proof.parent / 'seal-receipt.json')
    require(seal['sources'] == sources and seal['actual_dispatch_attempts'] == seal['returned_completions'] == 2,
            'New transport source or completion counts changed')
    summary = load(args.transport_proof.parent / 'client/client-summary.json')
    require(summary['invocations'] == summary['generation_dispatch_attempts'] == 2
            and summary['automatic_http_retries'] == summary['budget_refusals'] == 0,
            'New transport is not exactly two one-send calls')
    calls = jsonl(args.transport_proof.parent / 'client/model-calls.jsonl')
    require(all(sum(row['event'] == name for row in calls) == 2 for name in
                ('request_start', 'before_dispatch', 'request_return')), 'New transport journal differs')
    for name, expected in sources.items():
        require(file_binding(args.transport_proof.parent / 'execution-source' / name) == expected,
                'New transport source copy changed')
    verify_manifest(args.schema_proof.parent)
    schema = load(args.schema_proof)
    require(schema['passed'] is True and schema['runtime'] == runtime
            and schema['public_tool_schema_count'] == 26 and schema['native_tasks'] == 0
            and schema['actual_generation_dispatches'] == 0, 'Current full public-schema proof failed')
    durability = validate_durability(args.durability_proof)
    runtime_launch = validate_runtime_launch(args.runtime_binding, runtime, durability)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    value = {'schema': 'conseqax-limbo-relocated-readiness-v1', 'passed': True, 'utc': utc(),
        'sources': sources, 'native': native, 'wheel': installed, 'wheel_file': file_binding(args.wheel),
        'environment': environment_binding(), 'runtime_binding': runtime,
        'historical_published_readiness': bound(ready_path), 'historical_protocol_commit': ORIGINAL_COMMIT,
        'historical_native_execution_audits': historical, 'historical_actual_sdk_path': bound(receipt_path),
        'current_transport_proof': bound(args.transport_proof), 'current_schema_proof': bound(args.schema_proof),
        'durability_proof': bound(args.durability_proof), 'prospective_amendment': bound(args.amendment),
        'durability_validation': durability, **runtime_launch,
        'readiness_checker': bound(__file__), 'native_model_development_calls_added': 0,
        'task_independent_budget_used': 8, 'task_independent_budget_ceiling': 8,
        'scope': 'Preserved actual source/SDK/native validation plus newly tested runtime; historical native runs are not relabeled as current-runtime executions'}
    write_new(out / 'readiness.json', value)
    write_new(out / 'manifest.json', manifest(out))
    print(json.dumps({'passed': True, 'output': str(out)}))


if __name__ == '__main__':
    main()
