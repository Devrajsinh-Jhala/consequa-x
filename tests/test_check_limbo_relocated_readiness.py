"""Adversarial offline checks against copies of the actual closed lifetime proof.

Semantic mutations are deliberately resealed: a valid file hash alone must not
turn a short delay, killing job, different user, or invented timing into readiness.
No process, model, or network operation is performed by these tests.
"""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('relocated_readiness_checker',
    ROOT / 'scripts/check_limbo_relocated_readiness.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
PROBE = ROOT / 'output/durable-launch-lifetime-probe-2026-10-24'
RUNTIME = ROOT / 'output/limbo-runtime-isolated-2026-10-24'


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8')


@pytest.fixture
def probe(tmp_path):
    target = tmp_path / 'probe'
    shutil.copytree(PROBE, target)
    return target


def mutate(directory, relative, edit):
    path = directory / relative
    value = CHECK.load(path)
    edit(value)
    write(path, value)


def reseal(directory):
    proof_path = directory / 'lifetime-proof.json'
    proof = CHECK.load(proof_path)
    proof['raw_binding_references'] = {
        path.relative_to(directory).as_posix(): CHECK.file_binding(path)
        for path in directory.rglob('*') if path.is_file()
        and path.name not in ('manifest.json', 'lifetime-proof.json')}
    write(proof_path, proof)
    write(directory / 'manifest.json', {
        path.relative_to(directory).as_posix(): CHECK.file_binding(path)
        for path in directory.rglob('*') if path.is_file() and path.name != 'manifest.json'})


def check(directory):
    return CHECK.validate_durability(directory / 'lifetime-proof.json')


def test_actual_closed_probe_passes_with_upper_bound_not_exact_return(probe):
    result = check(probe)
    assert result['passed'] is True and result['sentinel_elapsed_s'] >= 15
    assert result['job_flags'] == [6144, 6144] and result['kill_on_job_close'] is False
    assert result['tool_return_upper_bound_utc'] < result['delayed_completion_utc']
    assert 'exact_tool_return_utc' not in result


def test_unsealed_mutation_is_rejected(probe):
    (probe / 'target.stdout.log').write_text('tamper', encoding='utf-8')
    with pytest.raises(ValueError, match='differ|changed'):
        check(probe)


@pytest.mark.parametrize('edit,reason', [
    (lambda value: value.update(elapsed_monotonic_s=14.5), 'Sentinel delay'),
    (lambda value: value['current_job_limits'].update(kill_on_job_close=True), 'non-killing ambient'),
    (lambda value: value['current_job_limits'].update(limit_flags=10240), 'non-killing ambient'),
    (lambda value: value['identity'].update(username='different-user'), 'identity chain'),
    (lambda value: value.update(model_calls=1), 'unexpected work'),
    (lambda value: value['current_job_limits'].update(process_ids=[]), 'actual ambient job inventory'),
])
def test_resealed_semantically_invalid_sentinel_is_rejected(probe, edit, reason):
    mutate(probe, 'sentinel/delayed-sentinel.json', edit)
    reseal(probe)
    with pytest.raises(ValueError, match=reason):
        check(probe)


def test_resealed_nonzero_target_exit_is_rejected(probe):
    mutate(probe, 'terminal-receipt.json', lambda value: value.update(return_code=1))
    reseal(probe)
    with pytest.raises(ValueError, match='exit successfully'):
        check(probe)


def test_resealed_fabricated_return_bound_is_rejected(probe):
    mutate(probe, 'lifetime-proof.json', lambda value:
           value.update(tool_return_upper_bound_utc='2026-10-24T04:36:12+00:00'))
    reseal(probe)
    with pytest.raises(ValueError, match='conservative raw upper bound'):
        check(probe)


def test_resealed_unobserved_tool_timing_is_rejected(probe):
    mutate(probe, 'tool-return-observation.json', lambda value:
           value.update(source_kind='estimated by a model', wall_time_seconds=1))
    reseal(probe)
    with pytest.raises(ValueError, match='actual successful launching tool observation'):
        check(probe)


def test_resealed_closed_log_disagrees_with_terminal_receipt(probe):
    (probe / 'target.stdout.log').write_bytes(b'changed after target exited')
    reseal(probe)
    with pytest.raises(ValueError, match='Closed target log binding'):
        check(probe)


def test_incomplete_raw_binding_map_is_rejected(probe):
    mutate(probe, 'lifetime-proof.json', lambda value:
           value['raw_binding_references'].pop('supervisor-identity.json'))
    manifest = CHECK.load(probe / 'manifest.json')
    manifest['lifetime-proof.json'] = CHECK.file_binding(probe / 'lifetime-proof.json')
    write(probe / 'manifest.json', manifest)
    with pytest.raises(ValueError, match='complete sealed inventory'):
        check(probe)


def test_summary_passed_alone_is_insufficient(tmp_path):
    proof = tmp_path / 'lifetime-proof.json'
    write(proof, {'schema': 'conseqax-durable-lifetime-proof-v1', 'passed': True})
    write(tmp_path / 'manifest.json', {'lifetime-proof.json': CHECK.file_binding(proof)})
    with pytest.raises(ValueError, match='complete sealed inventory'):
        CHECK.validate_durability(proof)


@pytest.mark.parametrize('text', ['{"passed":true,"passed":false}', '{"delay":NaN}'])
def test_ambiguous_or_nonfinite_json_is_rejected(tmp_path, text):
    path = tmp_path / 'bad.json'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate JSON|Nonfinite JSON'):
        CHECK.load(path)


@pytest.fixture
def runtime_copy(tmp_path, monkeypatch):
    # Only immutable metadata is copied; do not read or copy live server logs.
    destination = tmp_path / 'runtime'
    for path in RUNTIME.rglob('*'):
        if path.is_file() and path.suffix != '.log':
            target = destination / path.relative_to(RUNTIME)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    monkeypatch.setattr(CHECK, 'ROOT', tmp_path)
    return destination


def runtime_check(directory):
    runtime_path = directory / 'runtime-binding.json'
    return CHECK.validate_runtime_launch(runtime_path, CHECK.load(runtime_path),
                                        CHECK.validate_durability(PROBE / 'lifetime-proof.json'))


def test_actual_private_runtime_metadata_passes_without_sealing_live_logs(runtime_copy):
    result = runtime_check(runtime_copy)
    assert len(result['current_runtime_launch_evidence']) == 16
    assert all(not name.endswith('.log') for name in result['current_runtime_launch_evidence'])


@pytest.mark.parametrize('relative,edit,reason', [
    ('load-only.json', lambda value: value.update(eval_count=1), 'zero-completion'),
    ('launch-receipt.json', lambda value: value.update(model_downloads=1), 'accounting'),
    ('launch-receipt.json', lambda value: value['version_response'].update(version='0.40.8'), 'runtime version'),
    ('launch-receipt.json', lambda value:
     value['process_only_environment'].update(OLLAMA_NO_CLOUD='0'), 'offline/process environment'),
    ('durable-server-launch/supervisor-identity.json', lambda value:
     value['current_job_limits'].update(kill_on_job_close=True), 'non-killing ambient'),
])
def test_invalid_current_runtime_metadata_is_rejected(runtime_copy, relative, edit, reason):
    mutate(runtime_copy, relative, edit)
    with pytest.raises(ValueError, match=reason):
        runtime_check(runtime_copy)


def test_private_runtime_library_tampering_is_detected_without_modifying_real_copy(runtime_copy, tmp_path):
    # A tiny temporary private inventory exercises the same hash check. Never
    # mutate the real private binaries used by the running study.
    receipt = CHECK.load(runtime_copy / 'launch-receipt.json')
    private = tmp_path / 'fake-private'
    private.mkdir()
    (private / 'one.dll').write_bytes(b'original bytes')
    private_manifest = private / 'private-runtime-manifest.json'
    write(private_manifest, {'schema': 'conseqax-private-cpu-runtime-v1',
        'source_before_equals_source_after_equals_private_copy': True,
        'declared_version': '0.40.10', 'destination': str(private),
        'files': {'one.dll': CHECK.streamed_binding(private / 'one.dll')}})
    receipt['private_runtime_manifest'] = {'path': str(private_manifest), **CHECK.file_binding(private_manifest)}
    write(runtime_copy / 'launch-receipt.json', receipt)
    (private / 'one.dll').write_bytes(b'changed bytes')
    with pytest.raises(ValueError, match='Private CPU runtime file changed'):
        runtime_check(runtime_copy)


def test_declared_move_rejects_outside_and_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(CHECK, 'ROOT', tmp_path)
    assert CHECK.current_path('D:/ConsequaX-Research/paper-writing/output/a.json') == tmp_path / 'output/a.json'
    for path in ('D:/other/a.json', 'D:/ConsequaX-Research/paper-writing/../secret.json'):
        with pytest.raises(ValueError, match='outside|escapes'):
            CHECK.current_path(path)
