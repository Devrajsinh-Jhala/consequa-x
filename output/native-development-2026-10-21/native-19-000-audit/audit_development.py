"""Independent offline integration audit; no collection or policy modules imported."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path('D:/ConsequaX-Research/paper-writing')
RAW = ROOT / 'output/native-development-2026-10-21/native-19-000'
EP = RAW / 'episode'
OUT = Path(__file__).resolve().parent
NATIVE = Path('C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit')
COMMIT = '4a150b5a0fc2fbadcec93b1cb254330b374a9395'
WHEEL = ROOT / 'output/release-2.1.1-2026-10-19/consequa_x-2.1.1-py3-none-any.whl'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def inventory(directory):
    return {p.relative_to(directory).as_posix(): {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
            for p in sorted(directory.rglob('*')) if p.is_file()}


def module_from_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def journal(name):
    rows = []
    for index, line in enumerate((EP / (name + '.jsonl')).read_text(encoding='utf-8').splitlines()):
        row = json.loads(line)
        require(type(row) is dict and row.get('event_index') == index, name + ' journal index differs')
        rows.append(row)
    return rows


def no_forbidden_modules():
    prohibited = ('consequa_x', 'research.native_agent.controller', 'research.native_agent.transport',
                  'research.native_agent.harness', 'scripts.run_native_external_benchmark')
    found = [name for name in sys.modules for prefix in prohibited
             if name == prefix or name.startswith(prefix + '.')]
    require(not found, 'Forbidden scientific policy/collector imports: ' + repr(found))


result = {'schema': 'conseqax-native-development-independent-offline-audit-v1',
          'started_utc': datetime.now(timezone.utc).isoformat(), 'passed': False,
          'scope': 'Excluded development task 19; native unwrapped integration only; not a benchmark score',
          'new_model_calls': 0, 'human_labels': 0, 'source_commit': COMMIT}
before = inventory(RAW)
try:
    write('raw-artifacts-before.json', {'root': str(RAW), 'files': before,
        'coverage': 'Post-collection inventory generated before audit; no prospective original manifest existed'})
    identity = load(EP / 'worker-identity.json')
    records = identity['source_files']
    require(len(records) == 8, 'Expected eight recorded execution source files')
    source_checks = {}
    for name, record in records.items():
        pure = Path(name)
        require(not pure.is_absolute() and '..' not in pure.parts, 'Unsafe source path')
        blob = subprocess.check_output(['git', '-C', str(ROOT), 'show', COMMIT + ':' + name])
        candidates = [('exact_git_bytes', blob)]
        if b'\r\n' not in blob:
            candidates.append(('git_lf_to_windows_crlf', blob.replace(b'\n', b'\r\n')))
        matches = [(mode, data) for mode, data in candidates
                   if sha(data) == record['sha256'] and len(data) == record['bytes']]
        require(len(matches) == 1, 'Worker source record does not match pinned Git bytes: ' + name)
        mode, data = matches[0]
        target = OUT / 'verified-worker-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        source_checks[name] = {**record, 'git_blob_sha256': sha(blob), 'git_bytes': len(blob), 'checkout_mode': mode}
    write('source-bindings.json', {'commit': COMMIT, 'files': source_checks,
        'current_collector_not_imported': True, 'stored_source_copies_exactly_match_worker_records': True})
    protocol = module_from_file('verified_development_protocol',
        OUT / 'verified-worker-source/research/native_agent/protocol.py')
    native_audit = module_from_file('verified_development_native_audit',
        OUT / 'verified-worker-source/research/native_agent/audit.py')
    runtime = protocol.runtime_binding(WHEEL)
    write('runtime-binding.json', runtime)
    result['framework_wheel_sha256'] = runtime['framework_wheel_sha256']
    result['framework_payload_files_verified'] = len(runtime['framework_payload'])
    result['scientific_framework_imported'] = False
    native_sources = native_audit.verify_native_source(NATIVE)
    write('native-source-bindings.json', native_sources)
    result['native_bound_source_and_data_files'] = len(native_sources['files'])
    # No native imports, official scenarios, or reference actions occur above.
    for name in tuple(os.environ):
        upper = name.upper()
        if upper.endswith(('_API_KEY', '_API_TOKEN', '_ACCESS_TOKEN')) or upper in {
            'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'OPENAI_BASE_URL',
            'OPENAI_API_BASE', 'LITELLM_PROXY_API_BASE', 'GOOGLE_APPLICATION_CREDENTIALS',
            'AWS_SHARED_CREDENTIALS_FILE'}:
            os.environ.pop(name, None)
    os.environ.update(PYTHON_DOTENV_DISABLED='1', TAU2_DATA_DIR=str(NATIVE / 'data'),
        LITELLM_LOCAL_MODEL_COST_MAP='True', LITELLM_TELEMETRY='False', DO_NOT_TRACK='1',
        HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(NATIVE / 'src'))
    no_forbidden_modules()
    with native_audit.no_network() as network_attempts:
        from tau2.data_model.tasks import Task
        from tau2.domains.airline.environment import get_environment
        import tau2
        require(Path(tau2.__file__).resolve() == NATIVE.resolve() / 'src/tau2/__init__.py', 'Native origin differs')
        official = [task for task in load(NATIVE / 'data/tau2/domains/airline/tasks.json') if task['id'] == '19']
        require(len(official) == 1, 'Excluded development task identity differs')
        task = Task.model_validate(official[0])
        model = journal('model-calls')
        starts = [r for r in model if r['kind'] == 'request_start']
        returns = [r for r in model if r['kind'] == 'request_return']
        errors = [r for r in model if r['kind'] == 'request_error']
        require([r['call_index'] for r in starts] == list(range(len(starts))), 'Model start indices differ')
        require([r['call_index'] for r in returns] == list(range(len(starts))) and not errors,
                'Completed smoke model terminal accounting differs')
        require([r['kind'] for r in model] == ['request_start', 'request_return'] * len(starts),
                'Model start/return chronological structure differs')
        execution = load(EP / 'execution-receipt.json')
        state = execution['model_requests']
        require(state['attempted'] == state['completed'] == state['provider_invoked']
                == state['provider_returned'] == len(starts) == 14, 'Execution/model request counts differ')
        require(state['failed'] == state['refused_before_provider'] == state['usage_unavailable'] == 0,
                'Unexpected model errors/unavailability')
        for field in ('prompt_tokens', 'completion_tokens'):
            values = [r['response']['usage'][field] for r in returns]
            require(all(type(v) is int and v >= 0 for v in values), 'Invalid observed token count')
            require(sum(values) == state[field], 'Token journal/receipt differs')
        contexts = load(EP / 'context-checks.json')['checks']
        events = journal('context-events')
        network = load(EP / 'network-guard.json')['events']
        generations = [r for r in network if r.get('generation_request') is True]
        require(len(contexts) == len(events) == len(generations) == len(starts),
                'Context/model/HTTP dispatch counts differ')
        require(all(row.get('allowed') is True for row in network if row.get('kind') == 'http'),
                'Unexpected refused HTTP request')
        for index, (context, event, start) in enumerate(zip(contexts, events, starts)):
            require(event['kind'] == 'context_gate_result' and event['receipt'] == context,
                    'Flushed context event/final context differs')
            require(context['passed'] is True and context['same_rendered_bytes'] is True
                    and context['same_token_ids'] is True and context['verified_live_runner'] is True,
                    'Context parity check did not pass')
            wire, request = context['request'], start['request']
            require(sha(json.dumps(wire, sort_keys=True).encode()) == context['request_sha256'],
                    'Parsed context request digest differs')
            def normalize(messages):
                value = deepcopy(messages)
                for message in value:
                    if message.get('tool_calls') is None:
                        message.pop('tool_calls', None)
                    if message.get('role') == 'assistant' and message.get('tool_calls') and message.get('content') is None:
                        message.pop('content', None)
                return value
            require(normalize(request['messages']) == normalize(wire['messages']),
                    'Native model-input history differs from context request')
            require(request['model'] == 'openai/' + wire['model'], 'Native/OpenAI model route differs')
            for key in ('max_tokens', 'seed', 'temperature', 'tool_choice', 'tools'):
                require(request.get(key) == wire.get(key), 'Native/context request option differs: ' + key)
            require(request['api_base'] == 'http://127.0.0.1:11436/v1'
                    and request['num_retries'] == 0, 'Local no-retry invocation differs')
            profile = context['resident_profile']
            require(profile['context_length'] == 16384 and profile['digest'] == identity['resident']['digest'],
                    'Resident context/model identity differs')
            offline = context['offline_context']
            prompt = context['offline_rendered_prompt']
            require(prompt == context['server_preview']['_debug_info']['rendered_template'],
                    'Saved actual server render and offline render differ')
            require(sha(prompt.encode()) == offline['rendered_prompt_sha256'], 'Rendered prompt digest differs')
            require(offline['fits'] is True and offline['truncation_requested'] is False
                    and offline['required_tokens'] == offline['prompt_tokens'] + offline['output_tokens'] + offline['reserve_tokens']
                    and offline['required_tokens'] <= offline['context_tokens'] == 16384,
                    'Context arithmetic/budget differs')
            require(len(context['runtime_tokenizer']['tokens']) == offline['prompt_tokens'], 'Runtime token count differs')
        terminal, tool_starts = journal('tool-dispatch'), journal('tool-dispatch-starts')
        require(len(terminal) == len(tool_starts) == execution['actual_tool_dispatches']
                == execution['completed_tool_dispatches'] == 5 and execution['inflight_tool_dispatches'] == [],
                'Tool invocation accounting differs')
        for index, (start, end) in enumerate(zip(tool_starts, terminal)):
            require(start['call_index'] == end['call_index'] == index
                    and all(start[k] == end[k] for k in ('phase', 'request', 'before')),
                    'Tool in-flight start/terminal record differs')
        require(journal('controller-events') == [], 'Unwrapped native smoke emitted controller events')
        saved = load(EP / 'native-simulation.json')
        require(saved['id'] == 'development-19-native' and saved['task_id'] == '19', 'Saved episode identity differs')
        audit = native_audit.audit_native_episode(saved, task, terminal,
            load(EP / 'episode-start.json')['hashes'], load(EP / 'final-state.json')['hashes'], NATIVE)
        write('native-replay-and-regrade.json', audit)
        # Independently compare saved evaluator-only DB snapshots with re-created state.
        environment = get_environment(solo_mode=False)
        initial = task.initial_state
        environment.set_state(initialization_data=initial.initialization_data if initial else None,
            initialization_actions=initial.initialization_actions if initial else None,
            message_history=deepcopy(initial.message_history) if initial and initial.message_history else [], strict=True)
        def snapshot():
            result = {}
            for key, toolkit in (('agent', environment.tools), ('user', environment.user_tools)):
                db = getattr(toolkit, 'db', None) if toolkit is not None else None
                result[key] = db.model_dump(mode='json') if db is not None else None
            return result
        require(snapshot() == load(EP / 'initial-db.evaluator-only.json'), 'Saved initial DB snapshot differs')
        for row in terminal:
            if row['phase'] != 'episode':
                continue
            request = row['request']
            environment.make_tool_call(request['tool_name'], requestor=request['requestor'], **request['arguments'])
            environment.sync_tools()
        require(snapshot() == load(EP / 'final-db.evaluator-only.json'), 'Saved final DB snapshot differs')
        no_forbidden_modules()
        result['network_attempts'] = len(network_attempts)
    parent = load(RAW / 'parent-receipt.json')
    config = load(EP / 'configuration.json')
    require(parent['child_return_code'] == parent['exit_code'] == 0 and parent['hard_timeout'] is False
            and parent['supervisor_error'] is None and parent['cleanup_errors'] == [], 'Parent did not complete cleanly')
    require(execution['capture_errors'] == [] and execution['error_type'] is None
            and execution['status'] == 'native_returned' and execution['corrective_reruns'] == 0,
            'Execution did not complete cleanly')
    require(config['maximum_attempted_requests'] == 18 and len(starts) <= 18
            and config['config']['timeout'] == 3600.0 and execution['wall_seconds'] < 3600,
            'Development budget differs')
    result.update(passed=True, native_reward=audit['reward'], termination_reason=saved['termination_reason'],
        required_basis_nonempty_communication=bool(task.evaluation_criteria.communicate_info),
        initialization_dispatches=sum(r['phase'] == 'initialization' for r in terminal),
        episode_tool_names=[r['request']['tool_name'] for r in terminal if r['phase'] == 'episode'],
        actual_tool_dispatches=len(terminal), model_completion_invocations=len(starts),
        actual_http_generation_dispatch_records=len(generations), context_parity_receipts=len(contexts),
        observed_prompt_tokens=state['prompt_tokens'], observed_completion_tokens=state['completion_tokens'],
        execution_wall_seconds=execution['wall_seconds'], parent_wall_seconds=parent['wall_seconds'],
        native_message_costs=audit['message_costs'], initial_and_final_saved_db_snapshots_verified=True,
        maximum_context_prompt_tokens=max(c['offline_context']['prompt_tokens'] for c in contexts),
        maximum_context_required_tokens=max(c['offline_context']['required_tokens'] for c in contexts),
        source_files_verified=len(source_checks), source_import_forbidden_modules_absent=True)
    result['limitations'] = [
        'Excluded development task, unwrapped native arm only; not a comparative benchmark result.',
        'Post-collection raw inventory binds current bytes; no prospective complete raw manifest existed.',
        'Native COMMUNICATE component is vacuously satisfied because this task has no communication criterion.',
        'Saved context parsed requests match native inputs and all dispatch counts. Raw HTTP byte digests cannot be reconstructed independently after JSON key ordering was discarded; no claim of raw-byte request reauthentication.',
        'Runtime token IDs and renderer parity are saved collector observations; this offline audit checks their consistency, not a fresh server rendering or tokenizer execution.',
        'Native message monetary cost is zero for local inference; hardware/electricity costs are not estimated.',
        'Framework wheel and all installed package payload files were checked without importing the framework; native arm does not invoke it.',
        'Automated same-project audit, no human labels.']
except BaseException as exc:
    result['error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
finally:
    after = inventory(RAW)
    result['raw_originals_unchanged'] = before == after
    if before != after:
        result['passed'] = False
        result['raw_change_error'] = 'Raw original artifact inventory changed during audit'
    write('raw-artifacts-after.json', {'root': str(RAW), 'files': after})
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write('audit-result.json', result)
    files = {p.relative_to(OUT).as_posix(): sha(p.read_bytes()) for p in sorted(OUT.rglob('*'))
             if p.is_file() and p.name != 'manifest.json'}
    write('manifest.json', {'schema': 'conseqax-native-development-offline-audit-artifacts-v1', 'files': files})
print(json.dumps({key: result.get(key) for key in ('passed', 'error', 'raw_originals_unchanged',
      'native_bound_source_and_data_files', 'model_completion_invocations', 'actual_tool_dispatches', 'termination_reason')},
      indent=2))
raise SystemExit(0 if result['passed'] else 1)
