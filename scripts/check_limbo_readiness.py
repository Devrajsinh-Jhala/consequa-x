"""Check the prospectively separated native-execution and SDK-path gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.limbo_agent.audit import jsonl, verify_manifest  # noqa: E402
from research.limbo_agent.harness import installed_wheel_binding, manifest  # noqa: E402
from research.limbo_agent.protocol import (  # noqa: E402
    file_binding, native_binding, source_binding, utc, write_new,
)

PARITY = {'observations', 'interventions', 'runtime_events', 'initial_world',
          'after_each_step_world', 'final_world', 'final_rng', 'final_ledger',
          'public_receipt_mapping'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def proof_binding(path):
    return {'path': str(Path(path).resolve()), **file_binding(path)}


def check_fixture(value, sources, native, wheel, guard_path, guard, amendment):
    require(value.get('schema') == 'conseqax-limbo-saved-proposal-receipt-v1'
            and value.get('passed') is True, 'Need a passed scripted receipt-path proof')
    require(value.get('sources') == sources and value.get('native') == native,
            'Fixture scientific/native source identities differ')
    require(value.get('model_generations') == 0
            and value.get('model_client_instantiated') is False
            and value.get('scripted_second_identical_proposal') is True
            and value.get('native_task_grade_computed') is False,
            'Scripted path fixture must remain distinct from autonomous model performance')
    require(type(value.get('receipt_count')) is int and value['receipt_count'] > 0
            and value.get('fault_triggered') is True, 'Actual SDK receipt and native fault are required')
    require(type(value.get('parity')) is dict and PARITY <= set(value['parity'])
            and all(value['parity'][name] is True for name in PARITY), 'Native/SDK path parity failed')
    require(value.get('development_spec') == guard['spec'], 'Fixture development world differs')
    require({name: value.get('wheel', {}).get(name) for name in ('sha256', 'bytes')}
            == file_binding(wheel), 'Fixture selected wheel differs')
    require({name: value.get('source_audit', {}).get(name) for name in ('sha256', 'bytes')}
            == file_binding(guard_path), 'Fixture guarded audit differs')
    require(value.get('amendment') == proof_binding(amendment), 'Prospective amendment binding differs')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native-root', 'wheel', 'runtime-binding', 'baseline-audit',
                 'guard-audit', 'transport-proof', 'receipt-proof', 'amendment', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    sources, native = source_binding(ROOT), native_binding(args.native_root)
    runtime = load(args.runtime_binding)
    transport = load(args.transport_proof)
    verify_manifest(args.transport_proof.parent)
    require(transport.get('passed') is True and transport.get('native_episodes') == 0
            and transport.get('service_dispatches') == 0 and transport.get('model_invocation_cap') == 2
            and transport.get('runtime') == runtime, 'Current-runtime two-call transport proof failed')
    proof_root = args.transport_proof.parent
    seal = load(proof_root / 'seal-receipt.json')
    require(seal.get('passed') is True and seal.get('sources') == sources
            and seal.get('actual_dispatch_attempts') == 2 and seal.get('returned_completions') == 2
            and seal.get('model_generation_requests_by_sealer') == 0,
            'Transport source or postcompletion packaging proof differs')
    for name, expected in sources.items():
        require(file_binding(proof_root / 'execution-source' / name) == expected,
                'Transport scientific source copy differs: ' + name)
    summary = load(proof_root / 'client/client-summary.json')
    require(summary.get('automatic_http_retries') == 0 and summary.get('budget_refusals') == 0
            and summary.get('invocations') == summary.get('generation_dispatch_attempts') == 2,
            'Transport two-call accounting differs')
    calls = jsonl(proof_root / 'client/model-calls.jsonl')
    require(all(sum(row['event'] == event for row in calls) == 2
                for event in ('request_start', 'before_dispatch', 'request_return'))
            and len(list((proof_root / 'client').glob('*-terminal.json'))) == 2,
            'Transport journal/terminal inventory differs')
    audits = {}
    for kind, path in (('baseline', args.baseline_audit), ('guard', args.guard_audit)):
        verify_manifest(path.parent)
        audit = load(path)
        require(audit.get('schema') == 'conseqax-limbo-development-audit-v1'
                and audit.get('passed') is True and audit.get('sources') == sources,
                'Need a complete current-source excluded native audit')
        row = audit['row']
        require(row.get('audit_complete') is True and row.get('execution_success') is True,
                'Native execution did not return normally with a complete replay audit')
        require(audit['spec']['index'] in (0, 1), 'Development index is not excluded')
        episode = Path(audit['episode'])
        verify_manifest(episode)
        require(file_binding(episode / 'manifest.json') == audit['episode_manifest'],
                'Audited episode inventory changed')
        config = load(episode / 'worker-config.json')['protocol']
        require(config['native'] == native and config['runtime_binding'] == runtime,
                'Native development source/runtime differs')
        require({key: config['wheel'][key] for key in ('sha256', 'bytes')} == file_binding(args.wheel),
                'Native development wheel differs')
        audits[kind] = audit
    require(audits['baseline']['spec']['policy'] == 'vanilla'
            and audits['baseline']['spec']['mode'] == 'none', 'Need a clean native baseline')
    require(audits['guard']['spec']['policy'] == 'conseqax_guard'
            and audits['guard']['spec']['mode'] != 'none'
            and audits['guard']['row']['fault_triggered'] is True, 'Need a native fault-triggered guard execution')
    verify_manifest(args.receipt_proof.parent)
    receipt = load(args.receipt_proof)
    check_fixture(receipt, sources, native, args.wheel, args.guard_audit, audits['guard'], args.amendment)
    require(receipt.get('fixture_sources') == {
        'scripts/check_limbo_saved_proposal_receipt.py':
            file_binding(ROOT / 'scripts/check_limbo_saved_proposal_receipt.py')},
        'Receipt-path fixture source changed')
    require(file_binding(args.receipt_proof.parent / 'sources/check_limbo_saved_proposal_receipt.py')
            == file_binding(ROOT / 'scripts/check_limbo_saved_proposal_receipt.py'),
            'Receipt-path fixture source copy differs')
    episode = Path(audits['guard']['episode']).resolve()
    origin = receipt.get('source_episode', {})
    require(Path(origin.get('path', '')).resolve() == episode
            and origin.get('manifest') == file_binding(episode / 'manifest.json')
            and origin.get('worker_config') == file_binding(episode / 'worker-config.json')
            and origin.get('runtime_journal') == file_binding(episode / 'runtime.jsonl'),
            'Receipt-path source episode bindings differ')
    installed = installed_wheel_binding(args.wheel)
    require(receipt.get('installed_wheel') == installed, 'Receipt-path installed payload differs')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    value = {'schema': 'conseqax-limbo-separated-readiness-v1', 'passed': True, 'utc': utc(),
        'sources': sources, 'native': native,
        'wheel': installed, 'wheel_file': file_binding(args.wheel),
        'runtime_binding': runtime,
        'development_audits': {kind: proof_binding(path) for kind, path in
            (('baseline', args.baseline_audit), ('guard', args.guard_audit))},
        'transport_proof': proof_binding(args.transport_proof),
        'scripted_receipt_path_proof': proof_binding(args.receipt_proof),
        'prospective_amendment': proof_binding(args.amendment),
        'readiness_checker': proof_binding(__file__),
        'scope': 'Passed autonomous native executions plus separately scripted SDK path; no autonomous receipt-activation requirement',
        'native_grades_used_to_select_readiness': False,
        'official_model_policy_or_proposals_changed': False}
    write_new(out / 'readiness.json', value)
    write_new(out / 'manifest.json', manifest(out))
    print(json.dumps({'passed': True, 'output': str(out)}))


if __name__ == '__main__':
    main()
