"""Offline partial failure-integrity audit, never a native-reward audit.

No collector/controller/transport/framework import, model call, or Git write.
The exact source-bound audit helper only replays the saved completed prefix.
"""
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
RAW = ROOT / 'output/native-development-2026-10-21/guarded-20-001'
EP = RAW / 'episode'
PIPELINE = ROOT / 'output/native-finish-pipeline-2026-10-21'
OFFICIAL = ROOT / 'output/native-official-pipeline-2026-10-21'
RESERVATION = ROOT / 'output/native-development-2026-10-21/reservation-9ed7112beaa34b4497a076831d6e8066.json'
SETTLEMENT = RESERVATION.with_suffix('.settlement.json')
NATIVE = Path('C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tau2-bench-audit')
COMMIT = '8bd1cd88ab3644a9c6417e29308ab4b502b40484'
WHEEL = ROOT / 'output/release-2.1.1-2026-10-19/consequa_x-2.1.1-py3-none-any.whl'
OUT = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


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
    rows = [json.loads(line) for line in (EP / (name + '.jsonl')).read_text(encoding='utf-8').splitlines()]
    for index, row in enumerate(rows):
        require(type(row) is dict and row.get('event_index') == index, name + ' index differs')
    return rows


def no_forbidden_modules():
    prefixes = ('consequa_x', 'research.native_agent.controller', 'research.native_agent.transport',
                'research.native_agent.harness', 'scripts.run_native_external_benchmark')
    require(not [name for name in sys.modules for prefix in prefixes
                 if name == prefix or name.startswith(prefix + '.')], 'Forbidden measured imports')


def normalized_messages(messages):
    value = deepcopy(messages)
    for item in value:
        if item.get('role') == 'assistant' and item.get('tool_calls', 'absent') is None:
            item.pop('tool_calls', None)
        if item.get('role') == 'assistant' and item.get('tool_calls') and item.get('content') is None:
            item.pop('content', None)
    return value


require(not (OUT / 'audit-result.json').exists(), 'One-shot output already exists; do not overwrite')
require((RAW / 'parent-receipt.json').is_file(), 'Development collection is not terminal')
before = {'raw': inventory(RAW), 'pipeline': inventory(PIPELINE),
          'reservation': sha(RESERVATION.read_bytes()), 'settlement': sha(SETTLEMENT.read_bytes())}
result = {'schema': 'conseqax-native-partial-failure-integrity-audit-v1',
          'started_utc': datetime.now(timezone.utc).isoformat(),
          'failure_integrity_checks_passed': False, 'native_reward_audit_passed': False,
          'native_reward': None, 'native_reward_available': False,
          'scope': 'Excluded development task 20/G, partial execution failure; not an official benchmark score',
          'source_commit': COMMIT, 'new_model_calls': 0, 'human_labels': 0}
try:
    write('input-inventory-before.json', before)
    for label, directory in [('raw', RAW), ('pipeline', PIPELINE)]:
        for relative in inventory(directory):
            target = OUT / 'input-snapshot' / label / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write((directory / relative).read_bytes())
    for source in (RESERVATION, SETTLEMENT):
        with (OUT / 'input-snapshot' / source.name).open('xb') as stream:
            stream.write(source.read_bytes())
    identity = load(EP / 'worker-identity.json')
    require(len(identity['source_files']) == 8, 'Expected eight measured sources')
    source_checks = {}
    for name, record in identity['source_files'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'Unsafe source path')
        blob = subprocess.check_output(['git', '-C', str(ROOT), 'show', COMMIT + ':' + name])
        require(sha(blob) == record['sha256'] and len(blob) == record['bytes'],
                'Source identity is not exact pinned Git bytes: ' + name)
        target = OUT / 'verified-worker-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(blob)
        source_checks[name] = {**record, 'checkout_mode': 'exact_git_bytes'}
    write('source-bindings.json', {'commit': COMMIT, 'files': source_checks})
    harness_text = (OUT / 'verified-worker-source/research/native_agent/harness.py').read_text()
    transport_text = (OUT / 'verified-worker-source/research/native_agent/transport.py').read_text()
    require('guard.require_native_invocation = True' in harness_text
            and 'invoke_scope=guard.native_invocation' in harness_text
            and 'if scope["dispatched"]:' in transport_text and 'scope["dispatched"] = True' in transport_text,
            'Pinned single-dispatch native scope is absent')
    protocol = module_from_file('verified_failure_protocol', OUT / 'verified-worker-source/research/native_agent/protocol.py')
    audit = module_from_file('verified_failure_native_audit', OUT / 'verified-worker-source/research/native_agent/audit.py')
    runtime = protocol.runtime_binding(WHEEL)
    write('runtime-binding.json', runtime)
    native_sources = audit.verify_native_source(NATIVE)
    write('native-source-bindings.json', native_sources)

    parent = load(RAW / 'parent-receipt.json')
    parent_start = load(RAW / 'parent-start.json')
    execution = load(EP / 'execution-receipt.json')
    config = load(EP / 'configuration.json')
    error = load(EP / 'execution-error.json')
    require(parent['child_return_code'] == parent['exit_code'] == 1
            and parent['hard_timeout'] is False and parent['saved_simulation_available'] is False
            and parent['supervisor_error'] is None and parent['cleanup_errors'] == [], 'Terminal parent differs')
    require(execution['status'] == 'failed' and execution['error_type'] == error['type'] == 'Timeout'
            and execution['capture_errors'] == [] and execution['corrective_reruns'] == 0
            and execution['native_reward_not_fabricated'] is True
            and not (EP / 'native-simulation.json').exists(), 'Failure/no-grade capture differs')
    require(execution['arm'] == config['arm'] == 'G' and execution['task_id'] == config['task_id'] == '20'
            and config['framework_identity']['version'] == '2.1.1', 'Selected identity differs')
    require(Path(config['framework_identity']['module_origin']).resolve()
            == (Path(runtime['framework_root']) / '__init__.py').resolve(), 'Framework installed origin differs')
    require(config['maximum_attempted_requests'] == 29 and config['config']['timeout'] == 7200
            and parent_start['hard_deadline_seconds'] == 7200 and parent['wall_seconds'] < 7200
            and config['config']['llm_args_agent']['timeout'] == config['config']['llm_args_user']['timeout'] == 1200
            and parent_start['corrective_reruns'] == 0, 'Declared request/deadline caps differ')
    for role in ('agent', 'user'):
        args = config['config']['llm_args_' + role]
        require(args['max_tokens'] == 512 and args['seed'] == 1701 and args['temperature'] == 0
                and args['num_retries'] == 0 and args['api_base'] == 'http://127.0.0.1:11436/v1',
                'Shared local one-attempt fixed seed/cap differs')
    model = journal('model-calls')
    starts = [r for r in model if r['kind'] == 'request_start']
    returned = [r for r in model if r['kind'] == 'request_return']
    errors = [r for r in model if r['kind'] == 'request_error']
    require([r['kind'] for r in model] == ['request_start', 'request_return'] * 8 + ['request_start', 'request_error']
            and [r['call_index'] for r in starts] == list(range(9))
            and [r['call_index'] for r in returned] == list(range(8))
            and len(errors) == 1 and errors[0]['call_index'] == 8 and errors[0]['error_type'] == 'Timeout',
            'Partial journal is not eight complete invocations plus one terminal timeout')
    state = execution['model_requests']
    require(state['attempted'] == state['provider_invoked'] == 9
            and state['completed'] == state['provider_returned'] == 8
            and state['failed'] == 1 and state['refused_before_provider'] == state['usage_unavailable'] == 0,
            'Execution/model counts differ')
    for field in ('prompt_tokens', 'completion_tokens'):
        values = [row['response']['usage'][field] for row in returned]
        require(all(type(v) is int and v >= 0 for v in values) and sum(values) == state[field],
                'Observed returned token sum differs')
    contexts = load(EP / 'context-checks.json')['checks']
    events = journal('context-events')
    network = load(EP / 'network-guard.json')['events']
    generations = [r for r in network if r.get('generation_request') is True]
    previews = [r for r in network if r.get('kind') == 'http' and r.get('path') == '/v1/chat/completions'
                and r.get('generation_request') is False]
    require(len(contexts) == len(events) == len(generations) == len(previews) == len(starts) == 9
            and not any(r.get('allowed') is False for r in network), 'Dispatch/context accounting differs')
    linked = []
    for index, (context, event, start, generation, preview) in enumerate(zip(contexts, events, starts, generations, previews)):
        require(event['kind'] == 'context_gate_result' and event['receipt'] == context, 'Flushed context differs')
        require(all(context[k] is True for k in ('passed', 'same_rendered_bytes', 'same_token_ids', 'verified_live_runner')),
                'Saved full context parity flags did not pass')
        wire, request = context['request'], start['request']
        parsed_sha = sha(canonical(wire).encode())
        require(parsed_sha == context['request_sha256'] == generation['parsed_body_sha256']
                and generation['kind'] == 'http' and generation['method'] == 'POST'
                and generation['path'] == '/v1/chat/completions' and generation['allowed'] is True
                and len(generation['body_sha256']) == 64, 'Actual generation/context binding differs')
        expected_preview = {**deepcopy(wire), '_debug_render_only': True}
        require(preview['parsed_body_sha256'] == sha(canonical(expected_preview).encode())
                and preview['method'] == 'POST' and preview['allowed'] is True, 'Preview binding differs')
        terminal = returned[index] if index < 8 else errors[0]
        require(datetime.fromisoformat(start['recorded_utc']) <= datetime.fromisoformat(event['recorded_utc'])
                <= datetime.fromisoformat(terminal['recorded_utc']), 'Context interval differs')
        require(canonical(normalized_messages(request['messages'])) == canonical(normalized_messages(wire['messages']))
                and request['model'] == 'openai/' + wire['model'], 'Strict native history binding differs')
        require(not (set(wire) - {'model', 'messages', 'max_tokens', 'seed', 'temperature', 'tool_choice', 'tools'}),
                'Actual generation added an unbound option')
        for key in ('max_tokens', 'seed', 'temperature', 'tool_choice', 'tools'):
            require(type(request.get(key)) is type(wire.get(key)) and canonical(request.get(key)) == canonical(wire.get(key)),
                    'Native/wire option differs: ' + key)
        require(request['api_base'] == 'http://127.0.0.1:11436/v1' and request['num_retries'] == 0,
                'Local zero-retry invocation differs')
        offline = context['offline_context']
        prompt = context['offline_rendered_prompt']
        require(context['resident_profile']['context_length'] == 16384
                and context['resident_profile']['digest'] == identity['resident']['digest'], 'Resident identity differs')
        require(prompt == context['server_preview']['_debug_info']['rendered_template']
                and sha(prompt.encode()) == offline['rendered_prompt_sha256'], 'Saved render bytes differ')
        require(offline['fits'] is True and offline['truncation_requested'] is False
                and offline['required_tokens'] == offline['prompt_tokens'] + offline['output_tokens'] + offline['reserve_tokens']
                and offline['required_tokens'] <= offline['context_tokens'] == 16384
                and len(context['runtime_tokenizer']['tokens']) == offline['prompt_tokens'], 'Saved context arithmetic differs')
        linked.append({'call_index': index, 'terminal': terminal['kind'], 'generation_dispatches': 1,
                       'actual_http_parsed_body_sha256': parsed_sha,
                       'actual_http_raw_body_sha256': generation['body_sha256'],
                       'strict_native_input_match': True, 'prompt_tokens': offline['prompt_tokens'],
                       'required_tokens': offline['required_tokens']})
    write('strict-invocation-dispatch-linkage.json', {'passed': True, 'rows': linked,
          'scope': 'All nine native invocations, including timed-out final request; one captured HTTP generation each',
          'allowed_equivalences': ['assistant tool_calls:null may be absent',
                                  'assistant content:null may be absent only with nonempty tool_calls']})

    tool_starts, tools = journal('tool-dispatch-starts'), journal('tool-dispatch')
    require(len(tool_starts) == len(tools) == execution['actual_tool_dispatches'] == execution['completed_tool_dispatches'] == 5
            and execution['inflight_tool_dispatches'] == [], 'Actual native tool accounting differs')
    for index, (start, end) in enumerate(zip(tool_starts, tools)):
        require(start['call_index'] == end['call_index'] == index
                and all(start[k] == end[k] for k in ('phase', 'request', 'before')), 'Tool start/terminal binding differs')
    controller = journal('controller-events')
    counts = Counter(r.get('event') for r in controller)
    require(all(r.get('arm') == 'G' and r.get('episode_id') == 'development-20-G'
                and r.get('index') == r['event_index'] for r in controller), 'Controller identities differ')
    require(counts['receipt'] == counts['guard_block'] == counts['read_dispatch'] == 0,
            'Expected pre-mutation failure actually exercised receipt/guard/read')
    declarations = {'scope': 'Saved controller declarations, not semantic receipt validation',
                    'event_counts': dict(counts), 'sdk_receipts': 0, 'guard_blocks': 0,
                    'scheduled_verification_reads': 0, 'sdk_receipt_path_exercised': False}
    write('controller-declarations.json', declarations)

    # Process-local Python network blocking is active before importing native
    # environment classes. This is a saved-prefix replay only, never ALL grading.
    for name in tuple(os.environ):
        upper = name.upper()
        if upper.endswith(('_API_KEY', '_API_TOKEN', '_ACCESS_TOKEN')) or upper in {
                'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'OPENAI_BASE_URL', 'OPENAI_API_BASE',
                'LITELLM_PROXY_API_BASE', 'GOOGLE_APPLICATION_CREDENTIALS', 'AWS_SHARED_CREDENTIALS_FILE'}:
            os.environ.pop(name, None)
    os.environ.update(PYTHON_DOTENV_DISABLED='1', TAU2_DATA_DIR=str(NATIVE / 'data'),
                      LITELLM_LOCAL_MODEL_COST_MAP='True', LITELLM_TELEMETRY='False', DO_NOT_TRACK='1',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(NATIVE / 'src'))
    no_forbidden_modules()
    with audit.no_network() as attempts:
        from tau2.data_model.tasks import Task
        from tau2.domains.airline.environment import get_environment
        task_rows = [r for r in load(NATIVE / 'data/tau2/domains/airline/tasks.json') if r['id'] == '20']
        require(len(task_rows) == 1, 'Excluded task identity differs')
        task = Task.model_validate(task_rows[0])
        initial = task.initial_state
        environment = get_environment(solo_mode=False)
        environment.set_state(initialization_data=initial.initialization_data if initial else None,
                              initialization_actions=initial.initialization_actions if initial else None,
                              message_history=deepcopy(initial.message_history) if initial and initial.message_history else [], strict=True)
        def snapshot():
            value = {}
            for label, toolkit in (('agent', environment.tools), ('user', environment.user_tools)):
                db = getattr(toolkit, 'db', None) if toolkit is not None else None
                value[label] = db.model_dump(mode='json') if db is not None else None
            return value
        require(snapshot() == load(EP / 'initial-db.evaluator-only.json'), 'Initial DB snapshot differs')
        require(audit.hashes(environment) == load(EP / 'episode-start.json')['hashes'], 'Initial DB hash differs')
        messages = load(EP / 'partial-native-messages.json')['messages']
        audit.validate_journal(tools)
        extracted = audit.extract_tool_pairs(messages, allow_pending=True)
        require(extracted['pending'] == [] and len(extracted['pairs']) == 5
                and all(r['phase'] == 'episode' for r in tools), 'Partial transcript dispatches differ')
        replay = audit.replay_episode_calls(environment, tools, extracted['pairs'])
        require(replay['final_hashes'] == load(EP / 'final-state.json')['hashes'], 'Final DB hash differs')
        require(snapshot() == load(EP / 'final-db.evaluator-only.json'), 'Final DB snapshot differs')
        no_forbidden_modules()
        write('partial-prefix-native-replay.json', {'scope': 'Completed saved native tool prefix only; no native reward evaluation',
              'replay': replay, 'initial_and_final_db_snapshots_verified': True,
              'native_reward': None, 'required_communication_criterion_nonempty': bool(task.evaluation_criteria.communicate_info),
              'partial_message_cost_metadata': audit.message_costs(messages), 'offline_network_attempts': len(attempts)})

    reservation, settlement = load(RESERVATION), load(SETTLEMENT)
    require(sha(RESERVATION.read_bytes()) == parent_start['command'][-1]
            == settlement['reservation_sha256'] == 'd5c2bba0b6b11f6787fc90ae481a51d85d70bd088bae3dccd8ec1655aa567a88',
            'Reservation binding differs')
    require(reservation['source_files'] == identity['source_files'] and reservation['category'] == 'excluded_native'
            and reservation['consumed_before'] == 35 and reservation['reserved_maximum_requests'] == 29
            and reservation['shared_category_ceiling'] == 64
            and settlement['accounted_attempts'] == 9 and settlement['released_unused_requests'] == 20,
            'Budget/settlement differs')
    for record in settlement['verified_artifacts']:
        require(sha(Path(record['path']).read_bytes()) == record['sha256'], 'Settlement retained artifact differs')
    write('budget-settlement-check.json', {'verified': True, 'consumed_before': 35, 'actual_attempts': 9,
          'total_excluded_native_consumed_after': 44, 'shared_category_ceiling': 64,
          'released_unused_requests': 20, 'reservation_sha256': sha(RESERVATION.read_bytes())})
    pipeline_receipt, claim = load(PIPELINE / 'pipeline-receipt.json'), load(PIPELINE / 'pipeline-claim.json')
    pipeline_manifest = load(PIPELINE / 'manifest.json')
    for name, record in pipeline_manifest['files'].items():
        payload = (PIPELINE / name).read_bytes()
        require(sha(payload) == record['sha256'] and len(payload) == record['bytes'],
                'Pipeline sealed manifest differs: ' + name)
    stage_names = [p.name for p in PIPELINE.iterdir() if p.is_dir()]
    require(len(stage_names) == 10 and all(name.split('-')[1].isdigit() for name in stage_names)
            and pipeline_receipt['status'] == 'failed' and pipeline_receipt['error_type'] == 'PipelineRefusal'
            and pipeline_receipt['message'] == 'guarded_smoke terminal parent receipt failed; no automatic development retry'
            and pipeline_receipt['corrective_reruns'] == 0 and claim['execute_explicit'] is True
            and claim['plan']['source_commit'] == COMMIT and not OFFICIAL.exists(),
            'Pipeline did not fail closed before readiness/freeze/official collection')
    write('pipeline-refusal-check.json', {'verified': True, 'receipt': pipeline_receipt,
          'official_output_absent': True, 'source_identity_stages_only': sorted(stage_names),
          'protocol_not_frozen': True, 'official_collection_not_started': True,
          'pipeline_manifest_sha256': sha((PIPELINE / 'manifest.json').read_bytes())})
    result.update(failure_integrity_checks_passed=True, source_files_verified=8,
        native_bound_source_and_data_files=len(native_sources['files']),
        framework_wheel_sha256=runtime['framework_wheel_sha256'], framework_payload_files_verified=len(runtime['framework_payload']),
        actual_http_generation_dispatches=9, complete_model_invocations=8, failed_model_invocations=1,
        pending_model_invocations=0, failed_model_error='Timeout', actual_tool_dispatches=5,
        tool_names=[r['request']['tool_name'] for r in tools], completed_tool_prefix_replayed=True,
        db_changed_calls=replay['counts'].get('db_changed_calls', 0),
        observed_prompt_tokens_completed_requests=state['prompt_tokens'], observed_completion_tokens_completed_requests=state['completion_tokens'],
        timed_out_request_usage_available=False, timed_out_request_usage_not_zero_imputed=True,
        maximum_context_prompt_tokens=max(c['offline_context']['prompt_tokens'] for c in contexts),
        maximum_context_required_tokens=max(c['offline_context']['required_tokens'] for c in contexts),
        execution_wall_seconds=execution['wall_seconds'], parent_wall_seconds=parent['wall_seconds'],
        controller_declarations=declarations, native_reward_not_fabricated=True,
        sdk_receipt_path_exercised=False, official_collection_not_started=True,
        pipeline_refused_as_declared=True, offline_network_attempts=0,
        limitations=['This is a partial failure-integrity audit, not a passed native-reward audit or official benchmark score.',
          'No native simulation was returned; reward and termination semantics are unavailable, not zero.',
          'The timed-out ninth invocation has no returned token/cost usage; completed-response sums exclude it.',
          'All five native tools were read-only and the DB stayed unchanged. No SDK receipt or guard block occurred.',
          'Saved runtime render/token parity is checked for consistency; no server/tokenizer is rerun.',
          'Actual canonical request digests are linked; raw body serialization is retained as a digest, not reconstructed.',
          'Original inventories are post-collection; no prospective complete raw manifest existed.',
          'Audit is automated and same-project; no independent human or external replication.'])
except BaseException as exc:
    result['error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
finally:
    after = {'raw': inventory(RAW), 'pipeline': inventory(PIPELINE),
             'reservation': sha(RESERVATION.read_bytes()), 'settlement': sha(SETTLEMENT.read_bytes())}
    result['original_inputs_unchanged'] = before == after
    if before != after:
        result['failure_integrity_checks_passed'] = False
    write('input-inventory-after.json', after)
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write('audit-result.json', result)
    files = {p.relative_to(OUT).as_posix(): sha(p.read_bytes()) for p in sorted(OUT.rglob('*'))
             if p.is_file() and p != OUT / 'manifest.json'}
    write('manifest.json', {'schema': 'conseqax-native-partial-failure-audit-artifacts-v1', 'files': files})
print(json.dumps(result, indent=2))
raise SystemExit(0 if result['failure_integrity_checks_passed'] else 1)
