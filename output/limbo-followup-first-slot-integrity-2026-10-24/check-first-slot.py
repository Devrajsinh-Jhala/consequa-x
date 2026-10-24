"""Offline interim replay of the already sealed first follow-up slot only."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
NATIVE = ROOT.parent / 'limbo-pinned-2db09fba'
PROTOCOL = ROOT / 'output/limbo-followup-protocol-2026-10-24/protocol.json'
COLLECTION = ROOT / 'output/limbo-followup-collection-2026-10-24'
EPISODE = COLLECTION / 'slot-000'
COMMIT = '8b25d4c7769c5c593333c9d3eeeceb8ae001dba4'
sys.path.insert(0, str(ROOT))
from scripts import audit_limbo_portable as portable  # noqa: E402


def main():
    portable.require(not (OUT / 'manifest.json').exists(), 'Refuse existing sealed interim proof')
    value = portable.verify_protocol_bytes(ROOT, NATIVE, PROTOCOL, COMMIT)
    planned = value['schedule'][0]
    portable.require(planned['slot'] == 0, 'Only the already sealed first planned slot is authorized')
    before = portable.sealed_manifest(EPISODE)
    manifest_before = portable.binding(EPISODE / 'manifest.json')
    portable.same(portable.load(EPISODE / 'worker-config.json'), {'protocol': value, 'slot': planned},
                  'First-slot configuration differs from exact published protocol')
    disposition = portable.load(COLLECTION / 'disposition-000.json')
    portable.same(disposition, portable.load(EPISODE / 'parent-terminal.json'),
                  'First-slot parent disposition differs')
    portable.require(disposition['status'] == 'child_returned' and disposition['exit_code'] == 0
                     and disposition['slot'] == 0 and disposition['directory'] == 'slot-000',
                     'Only a sealed completed first return can be audited')
    claim = portable.load(COLLECTION / 'claim.json')
    portable.require(claim['protocol_commit'] == COMMIT and claim['retry_resume_replacement'] is False
                     and claim['protocol_sha256'] == portable.binding(PROTOCOL)['sha256'],
                     'Published one-shot collection claim differs')
    with portable.frozen_auditor(ROOT) as (frozen_protocol, auditor):
        portable.validate_schedule(value, frozen_protocol, ROOT)
        sys.path.insert(0, str(NATIVE))
        try:
            portable.check_native_imports(NATIVE, value['native']['files'])
            with auditor.no_network(), portable.bound_native_imports(NATIVE, value['native']['files']):
                row = auditor.audit_episode(EPISODE, planned, value)
            portable.check_native_imports(NATIVE, value['native']['files'])
        finally:
            sys.path.remove(str(NATIVE))
    portable.require(row['audit_complete'] is True and row['grade_available'] is True,
                     'First native saved trajectory did not pass full independent replay')
    portable.same(portable.sealed_manifest(EPISODE), before, 'Original first slot changed during replay')
    portable.same(portable.binding(EPISODE / 'manifest.json'), manifest_before,
                  'Original first-slot manifest changed during replay')
    portable.verify_files(ROOT, value['sources'])
    portable.verify_files(NATIVE, value['native']['files'])
    shutil.copytree(EPISODE, OUT / 'saved-first-slot')
    portable.same(portable.sealed_manifest(OUT / 'saved-first-slot'), before,
                  'Copied first-slot inventory differs from original sealed bytes')
    (OUT / 'protocol.json').write_bytes(PROTOCOL.read_bytes())
    for name in value['sources']:
        target = OUT / 'frozen-scientific-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    for name in value['native']['files']:
        target = OUT / 'frozen-native-source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(NATIVE / name, target)
    (OUT / 'audit_limbo_portable.source.py').write_bytes(Path(portable.__file__).read_bytes())
    result = {'schema': 'conseqax-limbo-followup-first-slot-interim-integrity-v1',
        'passed': True, 'utc': datetime.now(timezone.utc).isoformat(), 'protocol_commit': COMMIT,
        'protocol': portable.binding(PROTOCOL), 'planned_slot': planned,
        'audited_episode': str(EPISODE), 'episode_manifest': manifest_before,
        'episode_inventory_files': len(before), 'row': row,
        'helper': portable.binding(__file__), 'portable_bootstrap': portable.binding(portable.__file__),
        'current_offline_environment': portable.current_environment(),
        'scope': {**portable.SCOPE, 'only_first_already_sealed_slot_replayed': True,
            'final_collection_audit': False, 'comparative_score': False,
            'other_slots_inspected_or_replayed': False, 'original_episode_modified': False,
            'fresh_model_calls': 0, 'live_tokenizer_or_render_calls': 0,
            'live_service_or_network_calls': 0, 'SDK_reexecution': False,
            'native_simulator_replay_of_saved_trajectory': True,
            'treatment_or_collection_changed_based_on_outcome': False,
            'passed_means_first_native_task_succeeded': False}}
    portable.write_json(OUT / 'interim-integrity.json', result)
    portable.write_json(OUT / 'manifest.json', {path.relative_to(OUT).as_posix(): portable.binding(path)
        for path in OUT.rglob('*') if path.is_file() and path != OUT / 'manifest.json'})
    portable.sealed_manifest(OUT)
    print('Passed independent first-slot interim replay; no final collection score or new inference.')


if __name__ == '__main__':
    main()
