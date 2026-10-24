"""One bounded local draft build after the exact poststudy process seals.

Presentation only: retains every already frozen cohort/statistic. Never starts a
model, retries a study, pushes Git, changes main, invokes Actions, or declares
the paper finished. The local PDF remains VISUAL_REVIEW_PENDING.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import finish_limbo_poststudy as post  # noqa: E402
from scripts import run_limbo_completion_pipeline as common  # noqa: E402

BRANCH = 'codex/native-external-2026-10-21'
EDITOR = 'scripts/finalize_limbo_editorial_sources.py'
SELF = 'scripts/finish_limbo_paper_build.py'
BUILDER = 'scripts/build_final_limbo_paper.py'
BASE_PYTHON = Path('C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
NODE = Path('C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
MARKER = Path('C:/Users/DELL/.codex/plugins/cache/openai-primary-runtime/pdf/26.1022.11436/skills/pdf/container_tools/mark_artifact_operation_started.mjs')
COMPILER = Path('C:/Users/DELL/OneDrive/Desktop/ConseqaX/tmp/tectonic/tectonic.exe')
POPPLER = Path('C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')
EDITOR_DOCS = {'paper/limbo-evidence-ledger-addendum-2026-10-24.md',
               'paper/limbo-review-disposition-2026-10-24.md', 'paper/evidence-ledger.md'}
POLL_SECONDS = 30
require, binding, load, write_new = common.require, common.binding, common.load, common.write_new


@dataclass(frozen=True)
class Config:
    root: Path
    poststudy: Path
    poststudy_launch: Path
    output: Path
    edited_stage: Path
    pdf_output: Path
    pdf_work: Path
    python: Path = BASE_PYTHON
    node: Path = NODE
    marker: Path = MARKER
    compiler: Path = COMPILER
    poppler: Path = POPPLER

    def resolved(self):
        root = self.root.resolve()
        return replace(self, root=root, **{key: ((root / Path(getattr(self, key))).resolve()
            if not Path(getattr(self, key)).is_absolute() else Path(getattr(self, key)).resolve())
            for key in self.__dataclass_fields__ if key != 'root'})


def git(root, *args, check=True):
    """Only the explicit local commands in this file reach this adapter."""
    return subprocess.run(['git', '-C', str(root), *args], check=check, capture_output=True)


def normalized(path):
    return os.path.normcase(os.path.abspath(path))


def paper_inventory(root):
    directory = root / 'paper'
    result = {}
    for path in sorted(directory.rglob('*')):
        require(not path.is_symlink(), 'Working paper symlinks are refused')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = binding(path)
    require(result, 'Working paper sources are missing')
    return result


def check_repo(config, *, clean=False, ancestor=None, git_call=git):
    branch = git_call(config.root, 'branch', '--show-current').stdout.decode().strip()
    require(branch == BRANCH, 'Local draft work is allowed only on the named research branch')
    lock_name = Path(git_call(config.root, 'rev-parse', '--git-path', 'index.lock').stdout.decode().strip())
    lock_path = lock_name if lock_name.is_absolute() else config.root / lock_name
    require(not lock_path.exists(), 'Concurrent Git index operation detected')
    require(not git_call(config.root, 'diff', '--cached', '--name-only', '-z').stdout,
            'Refuse a dirty Git index; never incorporate someone else\'s staged work')
    if clean:
        require(not git_call(config.root, 'status', '--porcelain', '--untracked-files=no').stdout,
                'Concurrent tracked edits detected before local paper application')
    head = git_call(config.root, 'rev-parse', 'HEAD').stdout.decode().strip()
    require(re.fullmatch(r'[0-9a-f]{40}', head) is not None, 'Need an exact local HEAD')
    if ancestor:
        require(git_call(config.root, 'merge-base', '--is-ancestor', ancestor, head, check=False).returncode == 0,
                'Research history changed; only descendant independent commits are allowed')
    return head


def post_config(config, original):
    values = {key: Path(value) for key, value in original['original_paths'].items()}
    values.update(root=config.root, protocol=Path(original['protocol']['path']),
        protocol_commit=original['protocol_commit'], python=Path(original['python']['path']),
        interrupted_analysis=Path(original['interrupted_cohort']['analysis_path']),
        interrupted_protocol=Path(original['interrupted_cohort']['protocol']['path']),
        interrupted_protocol_commit=original['interrupted_cohort']['protocol_commit'],
        portable_audit_output=Path(original['new_outputs']['portable_audit_output']),
        manuscript_output=Path(original['new_outputs']['manuscript_output']))
    return SimpleNamespace(**values)


def validate_paths(config):
    require(config.root == ROOT.resolve(), 'Use this helper\'s research checkout only')
    outputs = (config.output, config.edited_stage, config.pdf_output, config.pdf_work)
    for path in outputs:
        require(not path.exists() and not path.is_symlink(), 'Every draft output/work directory must be NEW')
        expected_parent = config.root / ('tmp/pdfs' if path == config.pdf_work else 'output')
        require(expected_parent in path.parents, 'Draft outputs must stay inside research output/tmp paths')
        require(path != config.poststudy and path not in config.poststudy.parents
                and config.poststudy not in path.parents, 'Draft outputs cannot overlap the original poststudy')
    for position, first in enumerate(outputs):
        for second in outputs[position + 1:]:
            require(first != second and first not in second.parents and second not in first.parents,
                    'Draft outputs/work directories must be disjoint')
    original = load(config.poststudy / 'claim.json')
    inputs = [Path(value) for value in original['original_paths'].values()]
    inputs += [Path(value) for value in original['new_outputs'].values()]
    inputs += [Path(original['protocol']['path']).parent,
               Path(original['interrupted_cohort']['analysis_path']),
               Path(original['interrupted_cohort']['protocol']['path']).parent]
    for output in outputs:
        for source in inputs:
            require(output != source and output not in source.parents and source not in output.parents,
                    'A draft output overlaps an original or future scientific/poststudy input')


def prepare_claim(config, *, git_call=git):
    head = check_repo(config, clean=True, git_call=git_call)
    original = load(config.poststudy / 'claim.json')
    require(original.get('schema') == 'conseqax-limbo-poststudy-claim-v1', 'Need the original poststudy claim')
    launch = load(config.poststudy_launch)
    launch_config = config.poststudy_launch.parent / 'launch-config.json'
    require(launch.get('schema') == 'conseqax-durable-research-launch-v1'
            and launch.get('status') == 'launched_not_complete'
            and launch.get('config_binding') == binding(launch_config), 'Exact poststudy launch/config binding differs')
    planned = load(launch_config)
    identity = launch['target']
    require(type(identity.get('pid')) is int and identity['pid'] > 0
            and type(identity.get('create_time')) in (float, int)
            and math.isfinite(identity['create_time']) and identity['create_time'] > 0,
            'Need the exact recorded process PID and full creation epoch')
    require(planned['command'] == identity['command_line'], 'Poststudy target command differs from launch plan')
    command = identity['command_line']
    require(normalized(command[0]) == normalized(original['python']['path'])
            and normalized(config.root / 'scripts/finish_limbo_poststudy.py') in
                {normalized(value) for value in command[1:] if not value.startswith('--')},
            'Poststudy launch targets a different executable or helper')
    for flag, value in (('--output', config.poststudy), ('--protocol', original['protocol']['path'])):
        require(command.count(flag) == 1 and command.index(flag) + 1 < len(command)
                and normalized(command[command.index(flag) + 1]) == normalized(value), 'Poststudy command identity differs: ' + flag)
    require(command.count('--protocol-commit') == 1
            and command[command.index('--protocol-commit') + 1] == original['protocol_commit'],
            'Poststudy launch protocol commit differs')
    cfg = post_config(config, original)
    sources = dict(original['source_files'])
    for name in (SELF, EDITOR):
        sources[name] = binding(common.confined(config.root, name))
    for name, expected in sources.items():
        source = common.confined(config.root, name)
        require(binding(source) == expected, 'A held source changed before draft queueing: ' + name)
        require(git_call(config.root, 'show', f'{head}:{name}').stdout == source.read_bytes(),
                'Draft helpers and held sources must already belong to the launch commit')
        common.copy_new(source, config.output / 'inputs/source' / name)
    inputs = {str(path): binding(path) for path in (config.poststudy / 'claim.json', config.poststudy_launch,
        launch_config, cfg.protocol, cfg.interrupted_protocol)}
    for path, expected in inputs.items():
        require(binding(path) == expected, 'Draft input changed during claim preparation')
    post.verify_sources(cfg, original)
    tools = {str(path): binding(path) for path in (config.python, config.node, config.marker, config.compiler,
        config.poppler / 'pdfinfo.exe', config.poppler / 'pdftoppm.exe')}
    base = paper_inventory(config.root)
    for name in base:
        common.copy_new(config.root / name, config.output / 'inputs/paper-base' / name)
    claim = {'schema': 'conseqax-limbo-local-draft-claim-v1', 'utc': common.utc(), 'launch_head': head,
        'branch': BRANCH, 'poststudy_identity': identity, 'poststudy_launch': str(config.poststudy_launch),
        'poststudy': str(config.poststudy), 'inputs': inputs, 'sources': sources, 'tools': tools,
        'paper_base': base, 'original_poststudy_claim': original,
        'protocol_commit': original['protocol_commit'], 'new_model_calls': 0,
        'pushes_main_actions_or_external_publication': False, 'visual_review_pending': True,
        'scope': 'Presentation of all already frozen statistics after partial follow-up exposure; no endpoint, filter, sample, or analysis changes. One local review-pending draft commit/build only.'}
    write_new(config.output / 'claim.json', claim)
    return claim


def verify_held(config, claim, *, paper_expected=None, git_call=git):
    check_repo(config, ancestor=claim['launch_head'], git_call=git_call)
    for group in ('sources', 'inputs', 'tools'):
        for name, expected in claim[group].items():
            path = config.root / name if group == 'sources' else Path(name)
            require(binding(path) == expected, 'A held draft source/input/tool changed: ' + str(path))
    require(paper_inventory(config.root) == (claim['paper_base'] if paper_expected is None else paper_expected),
            'Working paper changed concurrently after draft launch')


def observe_poststudy(config, identity):
    import psutil
    try:
        process = psutil.Process(identity['pid'])
        if process.create_time() != identity['create_time']:
            return {'status': 'pid_reused'}
        if (not process.is_running() or process.status() in (psutil.STATUS_DEAD, psutil.STATUS_ZOMBIE)
                or normalized(process.exe()) != normalized(identity['executable'])
                or process.cmdline() != identity['command_line']):
            return {'status': 'identity_changed_or_gone'}
        if process.create_time() != identity['create_time']:
            return {'status': 'identity_changed_during_read'}
        return {'status': 'matching'}
    except psutil.NoSuchProcess:
        return {'status': 'pid_gone'}
    except psutil.AccessDenied:
        return {'status': 'identity_unreadable'}


def is_sealed(config):
    return (config.poststudy / 'terminal-result.json').is_file() and (config.poststudy / 'manifest.json').is_file()


def wait_for_poststudy(config, claim, journal, *, observer=observe_poststudy, sleeper=time.sleep, git_call=git):
    while True:
        verify_held(config, claim, git_call=git_call)
        if is_sealed(config):
            return
        observation = observer(config, claim['poststudy_identity'])
        journal.append(event='poststudy_wait', observation=observation)
        if observation.get('status') != 'matching':
            require(is_sealed(config), 'Exact poststudy process disappeared before its full seal: ' + str(observation))
            return
        sleeper(POLL_SECONDS)


def verify_completed_poststudy(config, claim):
    original = claim['original_poststudy_claim']
    cfg = post_config(config, original)
    post_manifest = common.verify_manifest(config.poststudy)
    terminal = load(config.poststudy / 'terminal-result.json')
    require(terminal.get('schema') == 'conseqax-limbo-poststudy-terminal-v1'
            and terminal.get('status') == terminal.get('paper_stage') == 'REVIEW_PENDING'
            and terminal.get('exit_code') == 0 and terminal.get('error') is None
            and terminal.get('new_model_calls') == 0 and terminal.get('new_pdf_created') is False,
            'The exact poststudy did not seal a successful REVIEW_PENDING stage')
    stages = terminal.get('stages', [])
    require([value.get('stage') for value in stages] == ['portable_audit', 'prepare_manuscript']
            and all(value.get('returncode') == 0 and value.get('known_subprocess_closed') is True for value in stages),
            'Poststudy dependent stages are incomplete, open or failed')
    post.verify_sources(cfg, original)
    chain, official = post.verify_original_chain(cfg)
    require(terminal.get('original_chain') == chain, 'Sealed pipeline/analysis chain differs from poststudy')
    portable_manifest = common.verify_manifest(cfg.portable_audit_output)
    stage_manifest = common.verify_manifest(cfg.manuscript_output)
    require(terminal.get('portable_audit_manifest') == portable_manifest
            and terminal.get('manuscript_manifest') == stage_manifest, 'Poststudy child manifests differ')
    portable = load(cfg.portable_audit_output / 'audit-result.json')
    for key in ('schema', 'passed', 'protocol_commit', 'protocol', 'collection_manifest', 'rows', 'summary', 'scope'):
        require(portable.get(key) == official.get(key), 'Portable replay differs from first-authority audit: ' + key)
    comparison = portable.get('portable_audit', {}).get('comparison_to_original_official', {})
    require(comparison.get('semantic_agreement') is True
            and comparison.get('original_official_audit_remains_first_authority') is True
            and {key: comparison.get(key) for key in ('sha256', 'bytes')}
                == binding(cfg.official_audit / 'audit-result.json'), 'Portable comparison binding differs')
    prepared = load(cfg.manuscript_output / 'preparation-receipt.json')
    require(prepared.get('status') == 'REVIEW_PENDING' and prepared.get('visual_review_pending') is True
            and prepared.get('protocol_commit') == cfg.protocol_commit
            and prepared.get('protocol') == binding(cfg.protocol)
            and prepared.get('analysis_manifest') == chain['analysis_manifest']
            and prepared.get('both_cohorts_retained_separately') is True and prepared.get('cohorts_pooled') is False
            and prepared.get('interrupted_cohort', {}).get('protocol_commit') == cfg.interrupted_protocol_commit
            and prepared['interrupted_cohort'].get('analysis_manifest') == original['interrupted_cohort']['analysis_manifest'],
            'Prepared manuscript lost exact separate cohort provenance')
    directories = (cfg.pipeline, cfg.collection, cfg.official_audit, cfg.analysis,
                   cfg.portable_audit_output, config.poststudy, cfg.manuscript_output, cfg.interrupted_analysis)
    sealed = {str(path): common.verify_manifest(path) for path in directories}
    require(sealed[str(config.poststudy)] == post_manifest, 'Poststudy changed during validation')
    return cfg, sealed


def validate_editorial(config, claim, cfg):
    seal = common.verify_manifest(config.edited_stage)
    receipt = load(config.edited_stage / 'editorial-receipt.json')
    require(receipt.get('schema') == 'conseqax-limbo-final-editorial-v1'
            and receipt.get('status') == 'EDITORIAL_REVIEW_PENDING'
            and receipt.get('visual_review_pending') is True and receipt.get('proposed_sources_require_review') is True
            and receipt.get('new_pdf_created') is False and receipt.get('new_model_calls') == 0
            and receipt.get('git_mutations') == 0 and receipt.get('cohorts_pooled') is False,
            'Editorial stage must remain static and review pending')
    require(receipt.get('protocol_commit') == cfg.protocol_commit and receipt.get('protocol') == binding(cfg.protocol)
            and receipt.get('analysis_manifest') == binding(cfg.analysis / 'manifest.json')
            and receipt.get('original_stage_manifest') == binding(cfg.manuscript_output / 'manifest.json'),
            'Editorial stage analysis/original-stage/protocol binding differs')
    earlier = receipt.get('interrupted_cohort', {})
    require(earlier.get('protocol_commit') == cfg.interrupted_protocol_commit
            and earlier.get('protocol') == binding(cfg.interrupted_protocol)
            and earlier.get('analysis_manifest') == binding(cfg.interrupted_analysis / 'manifest.json'),
            'Editorial stage lost the separately retained interrupted cohort')
    require(common.verify_manifest(config.edited_stage / 'inputs/original-staging')
            == binding(cfg.manuscript_output / 'manifest.json'), 'Copied original manuscript stage differs')
    inventory = load(config.edited_stage / 'manifest.json')
    actual = {name: expected for name, expected in inventory.items() if name.startswith('paper/')}
    proposed = receipt.get('proposed_paper_files')
    original = {path.relative_to(cfg.manuscript_output).as_posix()
                for path in (cfg.manuscript_output / 'paper').rglob('*') if path.is_file()}
    require(type(proposed) is dict and proposed == actual and set(proposed) == original | EDITOR_DOCS,
            'Only the complete original paper inventory and declared editorial ledger/addenda may be proposed')
    require(receipt.get('base_paper_bindings') == {name: claim['paper_base'].get(name) for name in proposed},
            'Editorial base paper differs from the pre-wait launch bindings')
    for name in proposed:
        member = PurePosixPath(name)
        require(not member.is_absolute() and '..' not in member.parts and member.parts[0] == 'paper',
                'Editorial proposal escapes the explicit paper directory')
        require(binding(common.confined(config.edited_stage, name)) == proposed[name], 'Proposed bytes changed')
    for name, expected in receipt.get('source_bindings', {}).items():
        require(name in claim['sources'] and expected == claim['sources'][name], 'Editorial source differs from launch')
    require({EDITOR, BUILDER, 'scripts/prepare_final_limbo_manuscript.py',
             'scripts/analyze_limbo_external_benchmark.py'} <= set(receipt.get('source_bindings', {})),
            'Editorial stage omitted required source identities')
    return proposed, seal


def apply_proposals(config, claim, proposed):
    require(paper_inventory(config.root) == claim['paper_base'], 'Paper changed before proposal application')
    for name, expected in proposed.items():
        source, target = common.confined(config.edited_stage, name), common.confined(config.root, name)
        require(binding(source) == expected, 'Proposed source changed before application')
        require((binding(target) if target.exists() else None) == claim['paper_base'].get(name),
                'Concurrent paper edit detected during application')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + '.limbo-draft-tmp')
        require(not temporary.exists(), 'Concurrent draft temporary file exists')
        common.copy_new(source, temporary)
        require(binding(temporary) == expected, 'Draft copy differs before replacement')
        require((binding(target) if target.exists() else None) == claim['paper_base'].get(name),
                'Concurrent paper edit detected immediately before replacement')
        os.replace(temporary, target)
    expected = {**claim['paper_base'], **proposed}
    require(paper_inventory(config.root) == expected, 'Applied paper inventory differs')
    return expected


def stage_and_commit(config, claim, proposed, sealed, *, git_call=git):
    # Refuse unrelated tracked work; the only permitted tracked changes are the
    # exact proposed paper paths that this helper just applied.
    check_repo(config, ancestor=claim['launch_head'], git_call=git_call)
    changed = set(git_call(config.root, 'diff', '--name-only', '-z').stdout.decode().split('\0')) - {''}
    require(changed <= set(proposed), 'Concurrent unrelated tracked edits detected; no commit')
    files = set(proposed)
    for value, expected in sealed.items():
        directory = Path(value)
        require(config.root / 'output' in directory.parents and common.verify_manifest(directory) == expected,
                'Only exact fully sealed study data directories may be staged')
        files.update(path.relative_to(config.root).as_posix() for path in directory.rglob('*') if path.is_file())
    require(all(not name.endswith('.lock') and '..' not in PurePosixPath(name).parts for name in files),
            'Unsafe explicit stage inventory')
    expected_files = {name: binding(common.confined(config.root, name)) for name in sorted(files)}
    pathspec = config.output / 'commit-pathspec.nul'
    with pathspec.open('xb') as stream:
        stream.write(b''.join(name.encode('utf-8') + b'\0' for name in sorted(files)))
        stream.flush()
        os.fsync(stream.fileno())
    parent = git_call(config.root, 'rev-parse', 'HEAD').stdout.decode().strip()
    git_call(config.root, '--literal-pathspecs', 'add', '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul')
    staged = set(git_call(config.root, 'diff', '--cached', '--name-only', '-z').stdout.decode().split('\0')) - {''}
    require(staged and staged <= files, 'Unexpected staged file; refuse local commit')
    require(all(git_call(config.root, 'show', ':' + name).stdout == (config.root / name).read_bytes() for name in staged),
            'Staged bytes differ from the applied/validated files')
    require(all(binding(config.root / name) == expected for name, expected in expected_files.items()),
            'A paper or sealed study file changed during staging')
    require(git_call(config.root, 'rev-parse', 'HEAD').stdout.decode().strip() == parent,
            'Concurrent local commit detected; no draft commit')
    hooks = config.output / 'empty-hooks'
    hooks.mkdir()
    git_call(config.root, '-c', 'core.hooksPath=' + str(hooks), '-c', 'commit.gpgsign=false',
        '--literal-pathspecs', 'commit', '--only', '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul',
        '--no-verify', '--no-gpg-sign', '-m', 'Stage audited two-cohort ConseqaX local draft for visual review')
    source_commit = git_call(config.root, 'rev-parse', 'HEAD').stdout.decode().strip()
    require(re.fullmatch(r'[0-9a-f]{40}', source_commit) is not None and source_commit != parent,
            'No new exact local draft commit was produced')
    require(git_call(config.root, 'rev-parse', source_commit + '^').stdout.decode().strip() == parent,
            'Local draft commit parent differs')
    committed = set(git_call(config.root, 'diff-tree', '--no-commit-id', '--name-only', '-r', '-z', source_commit)
                    .stdout.decode().split('\0')) - {''}
    require(committed == staged, 'Draft commit includes unexpected files; preserve local state for review')
    check_repo(config, clean=True, ancestor=claim['launch_head'], git_call=git_call)
    return {'source_commit': source_commit, 'parent_commit': parent, 'files': expected_files,
            'changed_files': sorted(committed), 'local_only': True, 'push_performed': False}


def environment(config):
    allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT', 'USERPROFILE',
               'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'}
    result = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    result.update(PYTHONPATH=str(config.root), PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONUTF8='1')
    return result


def execute(config, name, command, records, journal, *, runner):
    record = {'stage': name, 'command': command, 'started_utc': common.utc(),
              'known_subprocess_closed': False, 'returncode': None}
    records.append(record)
    journal.append(event='stage_enter', stage=name, command=command)
    stdout_path, stderr_path = [config.output / (name + suffix) for suffix in ('.stdout.log', '.stderr.log')]
    try:
        with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
            try:
                completed = runner(command, cwd=str(config.root), env=environment(config), stdout=stdout, stderr=stderr)
                require(type(completed.returncode) is int, 'Need an actual process return code')
                record.update(known_subprocess_closed=True, returncode=completed.returncode)
            except OSError:
                record['known_subprocess_closed'] = True
                raise
            finally:
                for stream in (stdout, stderr):
                    stream.flush()
                    os.fsync(stream.fileno())
    finally:
        record.update(ended_utc=common.utc(), stdout=binding(stdout_path), stderr=binding(stderr_path))
        journal.append(event='stage_return' if record['known_subprocess_closed'] else 'stage_liveness_unknown', **record)
    require(record['returncode'] == 0, 'One-shot stage failed; no retry or repair: ' + name)


def run(config, *, runner=common.default_runner, observer=observe_poststudy, sleeper=time.sleep, git_call=git):
    config = config.resolved()
    validate_paths(config)
    config.output.mkdir(parents=True, exist_ok=False)
    journal, stages = common.Journal(config.output / 'events.jsonl'), []
    result = {'schema': 'conseqax-limbo-local-draft-terminal-v1', 'started_utc': common.utc(),
        'status': 'LOCAL_DRAFT_NOT_BUILT', 'error': None, 'exit_code': 1, 'stages': stages,
        'visual_review_pending': True, 'new_model_calls': 0, 'new_native_evaluations': 0,
        'push_performed': False, 'finished_or_publishable_or_acceptance_claim': False}
    try:
        claim = prepare_claim(config, git_call=git_call)
        wait_for_poststudy(config, claim, journal, observer=observer, sleeper=sleeper, git_call=git_call)
        verify_held(config, claim, git_call=git_call)
        cfg, sealed = verify_completed_poststudy(config, claim)
        editor_command = [str(config.python), '-B', str(config.root / EDITOR), '--root', str(config.root),
            '--stage', str(cfg.manuscript_output), '--analysis', str(cfg.analysis), '--protocol', str(cfg.protocol),
            '--protocol-commit', cfg.protocol_commit, '--interrupted-analysis', str(cfg.interrupted_analysis),
            '--interrupted-protocol', str(cfg.interrupted_protocol),
            '--interrupted-protocol-commit', cfg.interrupted_protocol_commit, '--output', str(config.edited_stage)]
        execute(config, 'editorial_stage', editor_command, stages, journal, runner=runner)
        verify_held(config, claim, git_call=git_call)
        proposed, editor_seal = validate_editorial(config, claim, cfg)
        sealed[str(config.edited_stage)] = editor_seal
        check_repo(config, clean=True, ancestor=claim['launch_head'], git_call=git_call)
        expected_paper = apply_proposals(config, claim, proposed)
        result['paper_sources_applied'] = True
        committed = stage_and_commit(config, claim, proposed, sealed, git_call=git_call)
        result['local_commit'] = committed
        verify_held(config, claim, paper_expected=expected_paper, git_call=git_call)
        require(all(common.verify_manifest(Path(path)) == expected for path, expected in sealed.items()),
                'A sealed study/editorial directory changed before the PDF build')
        marker_command = [str(config.node), str(config.marker), '--operation-kind', 'create',
                          '--expected-output-count', '1', '--output-format', 'pdf']
        build_command = [str(config.python), '-B', str(config.root / BUILDER), '--root', str(config.root),
            '--source-commit', committed['source_commit'], '--analysis', str(cfg.analysis),
            '--protocol', str(cfg.protocol), '--protocol-commit', cfg.protocol_commit,
            '--interrupted-analysis', str(cfg.interrupted_analysis), '--interrupted-protocol', str(cfg.interrupted_protocol),
            '--interrupted-protocol-commit', cfg.interrupted_protocol_commit, '--output', str(config.pdf_output),
            '--work', str(config.pdf_work), '--compiler', str(config.compiler), '--poppler', str(config.poppler)]
        # Authoring marker exactly once, immediately before this one PDF build.
        execute(config, 'pdf_marker', marker_command, stages, journal, runner=runner)
        execute(config, 'pdf_build', build_command, stages, journal, runner=runner)
        pdf_seal = common.verify_manifest(config.pdf_output)
        built = load(config.pdf_output / 'build-receipt.json')
        require(built.get('schema') == 'conseqax-final-limbo-paper-build-v1'
                and built.get('source_commit') == committed['source_commit']
                and built.get('protocol_commit') == cfg.protocol_commit
                and built.get('visual_review_pending') is True and built.get('all_pages_rendered') is True
                and built.get('new_model_calls') == 0 and built.get('both_cohorts_retained_separately') is True
                and built.get('cohorts_pooled') is False, 'PDF bundle is not the exact local review-pending build')
        verify_held(config, claim, paper_expected=expected_paper, git_call=git_call)
        result.update(status='LOCAL_DRAFT_VISUAL_REVIEW_PENDING', exit_code=0,
            protocol_commit=cfg.protocol_commit, pdf_output=str(config.pdf_output), pdf_manifest=pdf_seal,
            sealed_inputs=sealed, editorial_manifest=editor_seal)
    except BaseException as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
        journal.append(event='local_draft_stopped', error=result['error'])
    finally:
        result['ended_utc'] = common.utc()
        closed = all(stage['known_subprocess_closed'] for stage in stages)
        journal.append(event='local_draft_exit' if closed else 'local_draft_interrupted_unsealed',
                       status=result['status'], exit_code=result['exit_code'], all_children_known_closed=closed)
        journal.close()
        if closed:
            write_new(config.output / 'terminal-result.json', result)
            write_new(config.output / 'manifest.json', {path.relative_to(config.output).as_posix(): binding(path)
                for path in sorted(config.output.rglob('*')) if path.is_file()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('poststudy', 'poststudy-launch', 'output', 'edited-stage', 'pdf-output', 'pdf-work'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name, default in (('root', ROOT), ('python', BASE_PYTHON), ('node', NODE), ('marker', MARKER),
                          ('compiler', COMPILER), ('poppler', POPPLER)):
        parser.add_argument('--' + name, type=Path, default=default)
    config = Config(**vars(parser.parse_args()))
    result = run(config)
    print(common.json.dumps({'status': result['status'], 'exit_code': result['exit_code'],
                             'visual_review_pending': True, 'error': result['error']}, sort_keys=True))
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
