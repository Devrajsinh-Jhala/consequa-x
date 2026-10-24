"""Offline adversarial checks; Git, processes and PDF authoring are all fakes."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('finish_limbo_paper_build_tested',
    ROOT / 'scripts/finish_limbo_paper_build.py')
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def seal(directory):
    write(directory / 'manifest.json', {path.relative_to(directory).as_posix(): M.binding(path)
        for path in sorted(directory.rglob('*')) if path.is_file() and path != directory / 'manifest.json'})
    return M.binding(directory / 'manifest.json')


class Journal:
    def __init__(self):
        self.events = []

    def append(self, **value):
        self.events.append(value)


class FakeGit:
    """Only an in-memory Git command model; never invokes a real repository."""
    def __init__(self, root):
        self.root, self.head, self.parent = root, 'a' * 40, 'a' * 40
        self.branch, self.dirty, self.staged = M.BRANCH, set(), set()
        self.commands, self.extra_staged = [], set()
        self.ancestor = True

    def __call__(self, root, *args, check=True):
        assert root == self.root
        assert not any(value in args for value in ('push', 'fetch', 'pull', 'merge', 'reset', 'checkout', 'switch'))
        self.commands.append(args)
        output, code = b'', 0
        if args == ('branch', '--show-current'):
            output = self.branch.encode()
        elif args == ('rev-parse', '--git-path', 'index.lock'):
            output = b'.git/index.lock'
        elif args == ('rev-parse', 'HEAD'):
            output = self.head.encode()
        elif args[:1] == ('rev-parse',) and args[1].endswith('^'):
            output = self.parent.encode()
        elif args[:2] == ('merge-base', '--is-ancestor'):
            code = 0 if self.ancestor else 1
        elif args[:2] == ('diff', '--cached'):
            output = b''.join(value.encode() + b'\0' for value in sorted(self.staged))
        elif args[:1] == ('diff',):
            output = b''.join(value.encode() + b'\0' for value in sorted(self.dirty))
        elif args[:1] == ('status',):
            output = b' M other.md' if self.dirty or self.staged else b''
        elif args[:1] == ('show',):
            name = args[1].split(':', 1)[1]
            output = (root / name).read_bytes()
        elif 'add' in args:
            path = Path(next(value.split('=', 1)[1] for value in args if value.startswith('--pathspec-from-file=')))
            selected = set(path.read_bytes().decode().split('\0')) - {''}
            self.staged = selected | self.extra_staged
        elif 'commit' in args:
            self.committed, self.parent, self.head = set(self.staged), self.head, 'b' * 40
            self.dirty.clear()
            self.staged.clear()
        elif args[:1] == ('diff-tree',):
            output = b''.join(value.encode() + b'\0' for value in sorted(self.committed))
        else:
            raise AssertionError('Unexpected Git command: ' + str(args))
        if code and check:
            raise subprocess.CalledProcessError(code, args)
        return subprocess.CompletedProcess(args, code, stdout=output, stderr=b'')


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'research'
    (root / 'paper').mkdir(parents=True)
    (root / 'paper/main.tex').write_bytes(b'original paper')
    (root / '.git').mkdir()
    for name in (M.SELF, M.EDITOR):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('offline source ' + name).encode())
    tools = root / 'tools'
    tools.mkdir()
    for name in ('python.exe', 'node.exe', 'marker.mjs', 'tectonic.exe', 'pdfinfo.exe', 'pdftoppm.exe'):
        (tools / name).write_bytes(name.encode())
    poststudy = root / 'output/poststudy'
    poststudy.mkdir(parents=True)
    protocol, earlier_protocol = root / 'output/protocol/protocol.json', root / 'output/earlier-protocol/protocol.json'
    write(protocol, {'scope': 'no actual study in test'})
    write(earlier_protocol, {'scope': 'distinct earlier protocol'})
    original = {'schema': 'conseqax-limbo-poststudy-claim-v1', 'source_files': {},
        'original_paths': {name: str(root / ('output/' + name)) for name in
                           ('pipeline', 'collection', 'official_audit', 'analysis', 'native_root')},
        'protocol': {'path': str(protocol), **M.binding(protocol)}, 'protocol_commit': 'c' * 40,
        'python': {'path': str(tools / 'python.exe'), **M.binding(tools / 'python.exe')},
        'interrupted_cohort': {'analysis_path': str(root / 'output/earlier-analysis'),
            'protocol': {'path': str(earlier_protocol), **M.binding(earlier_protocol)},
            'protocol_commit': 'd' * 40},
        'new_outputs': {'portable_audit_output': str(root / 'output/portable'),
                        'manuscript_output': str(root / 'output/manuscript')}}
    write(poststudy / 'claim.json', original)
    launch_dir = root / 'output/poststudy-launch'
    command = [str(tools / 'python.exe'), '-B', str(root / 'scripts/finish_limbo_poststudy.py'),
        '--output', str(poststudy), '--protocol', str(protocol), '--protocol-commit', 'c' * 40]
    write(launch_dir / 'launch-config.json', {'command': command})
    identity = {'pid': 18052, 'create_time': 1792817626.0065167, 'command_line': command,
                'executable': str(tools / 'python.exe')}
    write(launch_dir / 'launch-receipt.json', {'schema': 'conseqax-durable-research-launch-v1',
        'status': 'launched_not_complete', 'config_binding': M.binding(launch_dir / 'launch-config.json'),
        'target': identity})
    config = M.Config(root, poststudy, launch_dir / 'launch-receipt.json', root / 'output/build-waiter',
        root / 'output/editorial', root / 'output/pdf/draft', root / 'tmp/pdfs/draft',
        python=tools / 'python.exe', node=tools / 'node.exe', marker=tools / 'marker.mjs',
        compiler=tools / 'tectonic.exe', poppler=tools)
    monkeypatch.setattr(M, 'ROOT', root)
    monkeypatch.setattr(M.post, 'verify_sources', lambda *args: None)
    return config, FakeGit(root), original


def make_claim(config, git):
    config.output.mkdir(parents=True)
    return M.prepare_claim(config, git_call=git)


def test_claim_derives_full_precision_process_birth_from_bound_receipt(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    assert claim['poststudy_identity']['create_time'] == 1792817626.0065167
    assert claim['poststudy_identity']['pid'] == 18052
    assert claim['paper_base'] == M.paper_inventory(config.root)
    assert claim['new_model_calls'] == 0 and claim['visual_review_pending'] is True
    assert all('commit' not in args and 'add' not in args for args in git.commands)


@pytest.mark.parametrize('change,reason', [
    (lambda git: setattr(git, 'branch', 'main'), 'named research branch'),
    (lambda git: git.staged.add('someone-else.md'), 'dirty Git index'),
    (lambda git: git.dirty.add('someone-else.md'), 'Concurrent tracked edits'),
])
def test_queue_refuses_wrong_branch_or_existing_git_work(setup, change, reason):
    config, git, _ = setup
    config.output.mkdir(parents=True)
    change(git)
    with pytest.raises(ValueError, match=reason):
        M.prepare_claim(config, git_call=git)
    assert not any('commit' in args for args in git.commands)


def test_index_lock_in_actual_git_path_is_refused(setup):
    config, git, _ = setup
    (config.root / '.git/index.lock').write_text('other operation')
    with pytest.raises(ValueError, match='Concurrent Git index'):
        M.check_repo(config, git_call=git)


def test_claim_refuses_altered_launch_config_even_when_epoch_looks_plausible(setup):
    config, git, _ = setup
    config.output.mkdir(parents=True)
    write(config.poststudy_launch.parent / 'launch-config.json', {'command': ['wrong']})
    with pytest.raises(ValueError, match='launch/config binding'):
        M.prepare_claim(config, git_call=git)


def test_held_verification_allows_descendant_docs_commit_but_not_paper_edit(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    git.head = 'e' * 40
    M.verify_held(config, claim, git_call=git)
    (config.root / 'paper/main.tex').write_bytes(b'concurrent edit')
    with pytest.raises(ValueError, match='paper changed concurrently'):
        M.verify_held(config, claim, git_call=git)


def test_held_source_change_is_rejected_before_any_wait_work(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    (config.root / M.EDITOR).write_bytes(b'changed after queue')
    with pytest.raises(ValueError, match='held draft source'):
        M.verify_held(config, claim, git_call=git)


def test_wait_stops_on_pid_reuse_without_polling_or_starting_replacement(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    slept = []
    with pytest.raises(ValueError, match='disappeared before its full seal'):
        M.wait_for_poststudy(config, claim, Journal(), observer=lambda *args: {'status': 'pid_reused'},
                            sleeper=slept.append, git_call=git)
    assert slept == [] and not any('commit' in args for args in git.commands)


def test_wait_rechecks_terminal_race_before_treating_process_exit_as_failure(setup, monkeypatch):
    config, git, _ = setup
    claim = make_claim(config, git)
    values = iter([False, True])
    monkeypatch.setattr(M, 'is_sealed', lambda value: next(values))
    M.wait_for_poststudy(config, claim, Journal(), observer=lambda *args: {'status': 'pid_gone'},
                        sleeper=lambda seconds: pytest.fail('No wait after final seal'), git_call=git)


def test_output_cannot_substitute_for_future_analysis(setup):
    config, _, original = setup
    bad = replace(config, edited_stage=Path(original['original_paths']['analysis']))
    with pytest.raises(ValueError, match='overlaps an original or future'):
        M.validate_paths(bad)


def editorial_fixture(config, claim):
    cfg = M.post_config(config, claim['original_poststudy_claim'])
    cfg.manuscript_output.mkdir(parents=True)
    (cfg.manuscript_output / 'paper').mkdir()
    (cfg.manuscript_output / 'paper/main.tex').write_bytes(b'prepared factual paper')
    seal(cfg.manuscript_output)
    for path in (cfg.analysis / 'results.json', cfg.interrupted_analysis / 'results.json'):
        write(path, {'offline_fixture': True})
        seal(path.parent)
    shutil.copytree(cfg.manuscript_output, config.edited_stage / 'inputs/original-staging')
    (config.edited_stage / 'paper').mkdir(parents=True)
    (config.edited_stage / 'paper/main.tex').write_bytes(b'edited factual paper')
    for name in M.EDITOR_DOCS:
        path = config.edited_stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'editorial addendum')
    proposed = {path.relative_to(config.edited_stage).as_posix(): M.binding(path)
                for path in (config.edited_stage / 'paper').rglob('*') if path.is_file()}
    for name in (M.BUILDER, 'scripts/prepare_final_limbo_manuscript.py', 'scripts/analyze_limbo_external_benchmark.py'):
        claim['sources'][name] = {'sha256': '0' * 64, 'bytes': 0}
    receipt = {'schema': 'conseqax-limbo-final-editorial-v1', 'status': 'EDITORIAL_REVIEW_PENDING',
        'visual_review_pending': True, 'proposed_sources_require_review': True, 'new_pdf_created': False,
        'new_model_calls': 0, 'git_mutations': 0, 'cohorts_pooled': False,
        'protocol_commit': cfg.protocol_commit, 'protocol': M.binding(cfg.protocol),
        'analysis_manifest': M.binding(cfg.analysis / 'manifest.json'),
        'original_stage_manifest': M.binding(cfg.manuscript_output / 'manifest.json'),
        'interrupted_cohort': {'protocol_commit': cfg.interrupted_protocol_commit,
            'protocol': M.binding(cfg.interrupted_protocol),
            'analysis_manifest': M.binding(cfg.interrupted_analysis / 'manifest.json')},
        'proposed_paper_files': proposed,
        'base_paper_bindings': {name: claim['paper_base'].get(name) for name in proposed},
        'source_bindings': {name: claim['sources'][name] for name in (M.EDITOR, M.BUILDER,
            'scripts/prepare_final_limbo_manuscript.py', 'scripts/analyze_limbo_external_benchmark.py')}}
    write(config.edited_stage / 'editorial-receipt.json', receipt)
    seal(config.edited_stage)
    return cfg, receipt


def reseal_editor(config, receipt):
    write(config.edited_stage / 'editorial-receipt.json', receipt)
    seal(config.edited_stage)


def test_editorial_validation_and_apply_only_declared_proposals(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    cfg, receipt = editorial_fixture(config, claim)
    proposed, _ = M.validate_editorial(config, claim, cfg)
    expected = M.apply_proposals(config, claim, proposed)
    assert expected == {**claim['paper_base'], **receipt['proposed_paper_files']}
    assert (config.root / 'paper/main.tex').read_bytes() == b'edited factual paper'
    assert not (config.root / 'inputs').exists()


@pytest.mark.parametrize('change,reason', [
    (lambda value: value.update(status='FINAL_PUBLISHABLE'), 'review pending'),
    (lambda value: value.update(cohorts_pooled=True), 'review pending'),
    (lambda value: value['interrupted_cohort'].update(protocol_commit='f' * 40), 'interrupted cohort'),
    (lambda value: value['base_paper_bindings'].update({'paper/main.tex': None}), 'pre-wait launch'),
])
def test_resealed_editorial_semantic_changes_are_rejected(setup, change, reason):
    config, git, _ = setup
    claim = make_claim(config, git)
    cfg, receipt = editorial_fixture(config, claim)
    change(receipt)
    reseal_editor(config, receipt)
    with pytest.raises(ValueError, match=reason):
        M.validate_editorial(config, claim, cfg)


def test_extra_editorial_file_cannot_escape_allowlist_even_if_fully_resealed(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    cfg, receipt = editorial_fixture(config, claim)
    path = config.edited_stage / 'paper/unrequested.tex'
    path.write_bytes(b'unsolicited source')
    receipt['proposed_paper_files']['paper/unrequested.tex'] = M.binding(path)
    receipt['base_paper_bindings']['paper/unrequested.tex'] = None
    reseal_editor(config, receipt)
    with pytest.raises(ValueError, match='complete original paper inventory'):
        M.validate_editorial(config, claim, cfg)


def test_concurrent_paper_edit_is_never_overwritten(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    _, receipt = editorial_fixture(config, claim)
    path = config.root / 'paper/main.tex'
    path.write_bytes(b'another authors work')
    with pytest.raises(ValueError, match='Paper changed before'):
        M.apply_proposals(config, claim, receipt['proposed_paper_files'])
    assert path.read_bytes() == b'another authors work'


def test_edit_arriving_during_copy_is_detected_before_atomic_replacement(setup, monkeypatch):
    config, git, _ = setup
    claim = make_claim(config, git)
    _, receipt = editorial_fixture(config, claim)
    original_copy = M.common.copy_new
    target = config.root / 'paper/main.tex'
    def racing_copy(source, temporary):
        original_copy(source, temporary)
        target.write_bytes(b'edit arriving while proposal was copied')
    monkeypatch.setattr(M.common, 'copy_new', racing_copy)
    with pytest.raises(ValueError, match='immediately before replacement'):
        M.apply_proposals(config, claim, {'paper/main.tex': receipt['proposed_paper_files']['paper/main.tex']})
    assert target.read_bytes() == b'edit arriving while proposal was copied'


@pytest.mark.parametrize('change,reason', [
    (lambda value: value.update(status='MANUSCRIPT_PREPARATION_FAILED'), 'successful REVIEW_PENDING'),
    (lambda value: value['stages'][0].update(known_subprocess_closed=False), 'incomplete, open or failed'),
    (lambda value: value['stages'][1].update(returncode=1), 'incomplete, open or failed'),
])
def test_sealed_failed_or_open_poststudy_never_reaches_editor(setup, monkeypatch, change, reason):
    config, git, _ = setup
    claim = make_claim(config, git)
    terminal = {'schema': 'conseqax-limbo-poststudy-terminal-v1', 'status': 'REVIEW_PENDING',
        'paper_stage': 'REVIEW_PENDING', 'exit_code': 0, 'error': None, 'new_model_calls': 0,
        'new_pdf_created': False, 'stages': [
            {'stage': 'portable_audit', 'returncode': 0, 'known_subprocess_closed': True},
            {'stage': 'prepare_manuscript', 'returncode': 0, 'known_subprocess_closed': True}]}
    change(terminal)
    write(config.poststudy / 'terminal-result.json', terminal)
    seal(config.poststudy)
    monkeypatch.setattr(M.post, 'verify_original_chain', lambda value: pytest.fail('Must not enter downstream chain'))
    with pytest.raises(ValueError, match=reason):
        M.verify_completed_poststudy(config, claim)


def test_local_commit_pathspec_is_explicit_and_never_pushes(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    path = config.root / 'paper/main.tex'
    path.write_bytes(b'new draft')
    git.dirty = {'paper/main.tex'}
    committed = M.stage_and_commit(config, claim, {'paper/main.tex': M.binding(path)}, {}, git_call=git)
    assert committed['local_only'] is True and committed['push_performed'] is False
    assert committed['changed_files'] == ['paper/main.tex']
    assert (config.output / 'commit-pathspec.nul').read_bytes() == b'paper/main.tex\0'
    assert sum('commit' in command for command in git.commands) == 1


def test_injected_staged_work_blocks_commit(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    path = config.root / 'paper/main.tex'
    path.write_bytes(b'new draft')
    git.dirty, git.extra_staged = {'paper/main.tex'}, {'README.md'}
    with pytest.raises(ValueError, match='Unexpected staged file'):
        M.stage_and_commit(config, claim, {'paper/main.tex': M.binding(path)}, {}, git_call=git)
    assert not any('commit' in command for command in git.commands)


def test_unsealed_scientific_directory_is_never_staged(setup):
    config, git, _ = setup
    claim = make_claim(config, git)
    unsealed = config.root / 'output/live-server'
    unsealed.mkdir()
    (unsealed / 'server.stderr.log').write_bytes(b'live')
    with pytest.raises(FileNotFoundError):
        M.stage_and_commit(config, claim, {}, {str(unsealed): {'sha256': '0' * 64, 'bytes': 0}}, git_call=git)
    assert not any('add' in command or 'commit' in command for command in git.commands)


def test_failed_stage_is_one_shot_and_records_known_exit(setup):
    config, _, _ = setup
    config.output.mkdir(parents=True)
    calls, records = [], []
    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1)
    with pytest.raises(ValueError, match='no retry or repair'):
        M.execute(config, 'editorial_stage', ['fake-editor'], records, Journal(), runner=runner)
    assert len(calls) == 1 and records[0]['known_subprocess_closed'] is True and records[0]['returncode'] == 1


def test_interrupted_wait_never_invents_child_terminal_exit(setup):
    config, _, _ = setup
    config.output.mkdir(parents=True)
    records = []
    def runner(command, **kwargs):
        raise KeyboardInterrupt('actual child liveness unknown')
    with pytest.raises(KeyboardInterrupt):
        M.execute(config, 'pdf_build', ['fake-builder'], records, Journal(), runner=runner)
    assert records[0]['known_subprocess_closed'] is False and records[0]['returncode'] is None


def test_run_keeps_marker_immediately_before_one_build_and_review_pending(setup, monkeypatch):
    config, git, original = setup
    cfg = M.post_config(config, original)
    claim = {'launch_head': git.head, 'paper_base': M.paper_inventory(config.root), 'sources': {}, 'inputs': {},
             'tools': {}, 'original_poststudy_claim': original}
    monkeypatch.setattr(M, 'prepare_claim', lambda *args, **kwargs: claim)
    monkeypatch.setattr(M, 'wait_for_poststudy', lambda *args, **kwargs: None)
    monkeypatch.setattr(M, 'verify_held', lambda *args, **kwargs: None)
    monkeypatch.setattr(M, 'verify_completed_poststudy', lambda *args: (cfg, {}))
    monkeypatch.setattr(M, 'validate_editorial', lambda *args: ({}, {'sha256': '0' * 64, 'bytes': 0}))
    monkeypatch.setattr(M, 'apply_proposals', lambda *args: claim['paper_base'])
    monkeypatch.setattr(M, 'stage_and_commit', lambda *args, **kwargs: {'source_commit': 'b' * 40})
    monkeypatch.setattr(M.common, 'verify_manifest', lambda path: {'sha256': '0' * 64, 'bytes': 0})
    seen = []
    def runner(command, **kwargs):
        seen.append(command)
        if str(config.root / M.BUILDER) in command:
            write(config.pdf_output / 'build-receipt.json', {
                'schema': 'conseqax-final-limbo-paper-build-v1', 'source_commit': 'b' * 40,
                'protocol_commit': cfg.protocol_commit, 'visual_review_pending': True,
                'all_pages_rendered': True, 'new_model_calls': 0,
                'both_cohorts_retained_separately': True, 'cohorts_pooled': False})
        return subprocess.CompletedProcess(command, 0)
    result = M.run(config, runner=runner, git_call=git)
    assert result['status'] == 'LOCAL_DRAFT_VISUAL_REVIEW_PENDING' and result['visual_review_pending'] is True
    assert len(seen) == 3 and seen[1][0] == str(config.node)
    assert seen[1][-4:] == ['--expected-output-count', '1', '--output-format', 'pdf']
    assert seen[2][2] == str(config.root / M.BUILDER)
    for flag in ('--interrupted-analysis', '--interrupted-protocol', '--interrupted-protocol-commit'):
        assert seen[2].count(flag) == 1
    assert seen[2][seen[2].index('--source-commit') + 1] == 'b' * 40
    assert result['push_performed'] is False and result['finished_or_publishable_or_acceptance_claim'] is False
