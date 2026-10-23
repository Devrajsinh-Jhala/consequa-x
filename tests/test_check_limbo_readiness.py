"""Separated readiness must preserve actual activation and source identities."""
import copy
from pathlib import Path

import pytest

from scripts import check_limbo_readiness as check


@pytest.fixture
def inputs(tmp_path):
    wheel, audit, amendment = [tmp_path / name for name in ('wheel.whl', 'audit.json', 'amendment.md')]
    for path in (wheel, audit, amendment):
        path.write_text('synthetic test fixture', encoding='utf-8')
    sources, native, spec = {'source': {'sha256': 'synthetic'}}, {'commit': 'synthetic'}, {'index': 0}
    value = {'schema': 'conseqax-limbo-saved-proposal-receipt-v1', 'passed': True,
        'sources': sources, 'native': native, 'model_generations': 0,
        'model_client_instantiated': False, 'scripted_second_identical_proposal': True,
        'native_task_grade_computed': False, 'receipt_count': 1, 'fault_triggered': True,
        'parity': {name: True for name in check.PARITY}, 'development_spec': spec,
        'wheel': check.file_binding(wheel), 'source_audit': check.proof_binding(audit),
        'amendment': check.proof_binding(amendment)}
    return value, sources, native, wheel, audit, {'spec': spec}, amendment


def test_accepts_actual_separate_path_without_positive_task_reward(inputs):
    check.check_fixture(*inputs)


@pytest.mark.parametrize('field,value', [
    ('passed', False), ('receipt_count', 0), ('receipt_count', True),
    ('fault_triggered', False), ('model_generations', 1),
    ('model_client_instantiated', True), ('scripted_second_identical_proposal', False),
    ('native_task_grade_computed', True), ('sources', {}), ('native', {}),
    ('development_spec', {'index': 10000}), ('wheel', {}), ('source_audit', {}),
    ('amendment', {}), ('parity', {}),
])
def test_refuses_incomplete_or_changed_path_evidence(inputs, field, value):
    changed = list(copy.deepcopy(inputs))
    changed[0][field] = value
    with pytest.raises(ValueError):
        check.check_fixture(*changed)


def test_rejects_a_single_parity_failure(inputs):
    inputs[0]['parity']['final_ledger'] = False
    with pytest.raises(ValueError, match='parity'):
        check.check_fixture(*inputs)


def test_original_bound_document_change_invalidates_proof(inputs):
    Path(inputs[-1]).write_text('changed after proof', encoding='utf-8')
    with pytest.raises(ValueError, match='amendment'):
        check.check_fixture(*inputs)
