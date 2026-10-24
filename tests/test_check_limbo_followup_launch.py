"""Invented file/process-free prelaunch gates; no native task or model calls."""
from __future__ import annotations

import copy
import json

import pytest

from scripts import check_limbo_followup_launch as subject


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')


def bound(path):
    return {'path': str(path), **subject.binding(path)}


def test_only_declared_historical_move_is_resolved(tmp_path):
    root = tmp_path / 'current'
    root.mkdir()
    assert subject.current_path('D:/ConsequaX-Research/paper-writing/output/proof.json', root) == root / 'output/proof.json'
    assert subject.current_path(root / 'output/proof.json', root) == root / 'output/proof.json'
    for name in ('D:/unrelated/proof.json', 'D:/ConsequaX-Research/paper-writing/../secret.json',
                 'output/proof.json', 'Z:/old/proof.json'):
        with pytest.raises(ValueError):
            subject.current_path(name, root)


def test_evidence_full_manifest_rejects_tamper_and_unlisted_files(tmp_path):
    root = tmp_path / 'source'
    proof = root / 'proof'
    write(proof / 'result.json', {'passed': True})
    write(proof / 'manifest.json', {'result.json': subject.binding(proof / 'result.json')})
    evidence = subject.Evidence(root)
    evidence.item(bound(proof / 'result.json'), sealed=True)
    assert set(evidence.files) == {'proof/result.json', 'proof/manifest.json'}
    assert set(evidence.manifests) == {'proof'}
    write(proof / 'unexpected.json', {})
    with pytest.raises(ValueError, match='inventory differs'):
        evidence.sealed(proof)
    (proof / 'unexpected.json').unlink()
    write(proof / 'result.json', {'passed': False})
    with pytest.raises(ValueError, match='Sealed file changed'):
        evidence.sealed(proof)


def test_all_nested_bound_proofs_are_checked(tmp_path):
    path = tmp_path / 'proof.json'
    write(path, {'synthetic': True})
    evidence = subject.Evidence(tmp_path)
    evidence.tree({'historical': [{'recorded': bound(path)}],
        'other': {'path': str(path), 'binding': subject.binding(path)}})
    assert evidence.files == {'proof.json': subject.binding(path)}
    wrong = bound(path)
    wrong['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='Bound evidence changed'):
        evidence.tree({'historical': [{'recorded': wrong}]})


def test_publication_requires_exact_committed_bytes(tmp_path, monkeypatch):
    path = tmp_path / 'checker.py'
    path.write_bytes(b'# synthetic immutable checker\n')
    evidence = subject.Evidence(tmp_path)
    evidence.file(path)
    monkeypatch.setattr(subject.portable, 'git', lambda *args: path.read_bytes())
    evidence.published('a' * 40)
    with pytest.raises(ValueError, match='40-character'):
        evidence.published('main')
    monkeypatch.setattr(subject.portable, 'git', lambda *args: b'different committed bytes')
    with pytest.raises(ValueError, match='Published artifact differs'):
        evidence.published('a' * 40)


@pytest.fixture
def private_runtime(tmp_path):
    runtime_root = tmp_path / 'private'
    runtime_root.mkdir()
    for name in ('ollama.exe', 'lib/ollama/llama-server.exe', 'lib/ollama/example.dll'):
        path = runtime_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('invented ' + name).encode())
    files = {path.relative_to(runtime_root).as_posix(): subject.binding(path)
             for path in runtime_root.rglob('*') if path.is_file()}
    manifest = runtime_root / 'private-runtime-manifest.json'
    write(manifest, {'schema': 'conseqax-private-cpu-runtime-v1', 'declared_version': '0.40.10',
        'source_before_equals_source_after_equals_private_copy': True, 'destination': str(runtime_root),
        'files': files})
    copied = tmp_path / 'repo/private-runtime-manifest.json'
    copied.parent.mkdir()
    copied.write_bytes(manifest.read_bytes())
    runtime = {'server_executable': str(runtime_root / 'ollama.exe'),
        'server_executable_sha256': files['ollama.exe']['sha256'],
        'runner_executable': str(runtime_root / 'lib/ollama/llama-server.exe'),
        'runner_executable_sha256': files['lib/ollama/llama-server.exe']['sha256']}
    return runtime_root, copied, runtime


def test_private_runtime_checks_whole_copy_and_executable_locations(private_runtime):
    runtime_root, copied, runtime = private_runtime
    assert subject.validate_private_runtime(bound(copied), runtime, '0.40.10')['files']
    wrong = copy.deepcopy(runtime)
    wrong['runner_executable'] = str(runtime_root.parent / 'installed-updater/llama-server.exe')
    with pytest.raises(ValueError, match='outside the declared private runtime'):
        subject.validate_private_runtime(bound(copied), wrong, '0.40.10')
    (runtime_root / 'extra.dll').write_bytes(b'unbound')
    with pytest.raises(ValueError, match='extra or missing'):
        subject.validate_private_runtime(bound(copied), runtime, '0.40.10')


def test_private_runtime_tamper_and_inventory_mismatch_fail(private_runtime):
    runtime_root, copied, runtime = private_runtime
    (runtime_root / 'lib/ollama/example.dll').write_bytes(b'changed')
    with pytest.raises(ValueError, match='binary/library changed'):
        subject.validate_private_runtime(bound(copied), runtime, '0.40.10')
    copied.write_bytes(copied.read_bytes() + b' ')
    with pytest.raises(ValueError, match='manifest bytes differ'):
        subject.validate_private_runtime(bound(copied), runtime, '0.40.10')


@pytest.mark.parametrize('change', ('missing_exposure', 'pooled', 'wrong_original'))
def test_original_partial_exposure_and_unpooled_condition_are_mandatory(tmp_path, change):
    prior = {'protocol_commit': subject.ORIGINAL,
             'partial_data_exposed_before_followup_freeze': True, 'cohorts_pooled': False}
    if change == 'missing_exposure':
        prior.pop('partial_data_exposed_before_followup_freeze')
    elif change == 'pooled':
        prior['cohorts_pooled'] = True
    else:
        prior['protocol_commit'] = 'f' * 40
    with pytest.raises(ValueError):
        subject.validate_prior({'prior_condition': prior}, subject.Evidence(tmp_path))


def test_model_alias_is_the_only_schedule_normalization():
    original = {'schedule': [{'slot': 0, 'spec': {'model': 'historical', 'index': 123,
                                               'mode': 'timeout_post'}}]}
    followup = copy.deepcopy(original)
    followup['schedule'][0]['spec']['model'] = 'new alias same weights'
    assert subject.scientific_schedule(original) == subject.scientific_schedule(followup)
    followup['schedule'][0]['spec']['index'] += 1
    assert subject.scientific_schedule(original) != subject.scientific_schedule(followup)
    assert original['schedule'][0]['spec']['model'] == 'historical'
