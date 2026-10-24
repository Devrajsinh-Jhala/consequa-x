"""Read-only publication/evidence gate for the declared second LIMBO condition.

No inference, task construction, native grading, process launch or process
control occurs. Historical proof paths are resolved only through the explicitly
declared D-to-C move; historical runtime executions are not relabeled as new.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import audit_limbo_portable as portable  # noqa: E402

ORIGINAL = '267cd1a3e846c46c009f20accbf302746e064875'
HISTORICAL_ROOT = PureWindowsPath('D:/ConsequaX-Research/paper-writing')
SUPPORT = (
    'scripts/analyze_limbo_external_benchmark.py', 'scripts/run_limbo_completion_pipeline.py',
    'scripts/check_limbo_readiness.py', 'scripts/check_limbo_saved_proposal_receipt.py',
    'scripts/check_limbo_launch.py', 'scripts/seal_limbo_transport_proof.py',
    'scripts/audit_limbo_portable.py', 'scripts/audit_limbo_interrupted_collection.py',
    'scripts/check_limbo_relocated_readiness.py', 'scripts/check_limbo_followup_launch.py',
    'scripts/declare_limbo_followup.py', 'scripts/launch_durable_research.py',
    'scripts/start_durable_limbo_runtime.py', 'scripts/copy_private_ollama_runtime.py',
    'scripts/seal_durable_lifetime_probe.py', 'scripts/probe_durable_research_lifetime.py',
    'scripts/build_final_limbo_paper.py', 'scripts/prepare_final_limbo_manuscript.py',
    'scripts/finish_limbo_poststudy.py', 'docs/limbo-analysis-plan-2026-10-24.md',
    'docs/limbo-readiness-amendment-2026-10-24.md', 'docs/limbo-followup-condition-2026-10-24.md',
    'docs/durable-local-runtime-2026-10-24.md', 'docs/third-party-attribution.md',
    'docs/third-party/limbo-MIT-LICENSE.txt',
)
require, same, load, binding = portable.require, portable.same, portable.load, portable.binding


def stream_binding(path):
    path = Path(path)
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return {'sha256': result.hexdigest(), 'bytes': path.stat().st_size}


def current_path(recorded, root):
    """Only historical research evidence is relocated; arbitrary paths fail."""
    root = Path(root).resolve()
    path = Path(recorded)
    if path.is_absolute() and path.resolve().is_relative_to(root):
        return path.resolve()
    old = PureWindowsPath(recorded)
    try:
        relative = old.relative_to(HISTORICAL_ROOT)
    except ValueError as exc:
        raise ValueError('Bound research evidence is outside the current or declared historical root') from exc
    require('..' not in relative.parts, 'Historical evidence path escapes research root')
    return root.joinpath(*relative.parts)


def exact_item(item):
    require(type(item) is dict and type(item.get('path')) is str
            and type(item.get('bytes')) is int and item['bytes'] >= 0
            and type(item.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', item['sha256']),
            'Missing exact file path/byte/hash binding')
    return {key: item[key] for key in ('sha256', 'bytes')}


class Evidence:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.files = {}
        self.manifests = {}

    def file(self, path, expected=None):
        path = Path(path).resolve()
        require(path.is_relative_to(self.root) and not path.is_symlink(), 'Publication evidence is outside repository')
        actual = stream_binding(path)
        if expected is not None:
            same(actual, expected, 'Bound evidence changed: ' + str(path))
        name = path.relative_to(self.root).as_posix()
        if name in self.files:
            same(self.files[name], actual, 'Evidence changed within launch check')
        self.files[name] = actual
        return path

    def item(self, item, *, sealed=False):
        path = self.file(current_path(item['path'], self.root), exact_item(item))
        if sealed:
            self.sealed(path.parent)
        return path

    def sealed(self, directory):
        directory = Path(directory).resolve()
        expected = portable.sealed_manifest(directory)
        self.file(directory / 'manifest.json')
        self.manifests[directory.relative_to(self.root).as_posix()] = binding(directory / 'manifest.json')
        for name, identity in expected.items():
            self.file(portable.safe_file(directory, name), identity)

    def tree(self, value):
        """Check every explicit bound research proof in the chosen subtree."""
        if isinstance(value, dict):
            if {'path', 'sha256', 'bytes'} <= set(value):
                self.item(value)
            elif type(value.get('path')) is str and type(value.get('binding')) is dict:
                self.item({'path': value['path'], **value['binding']})
            for item in value.values():
                self.tree(item)
        elif isinstance(value, list):
            for item in value:
                self.tree(item)

    def published(self, commit):
        require(bool(re.fullmatch('[0-9a-f]{40}', commit)), 'Exact 40-character publication commit required')
        for name, identity in sorted(self.files.items()):
            data = portable.git(self.root, 'show', f'{commit}:{name}')
            same({'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}, identity,
                 'Published artifact differs: ' + name)
            same(stream_binding(self.root / name), identity, 'Artifact changed while checking publication')


def load_helper(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Cannot load published auxiliary checker')
    module = importlib.util.module_from_spec(spec)
    # Compile the verified source bytes, bypassing any stale cached bytecode.
    exec(compile(Path(path).read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def scientific_schedule(protocol):
    result = json.loads(json.dumps(protocol['schedule']))
    for row in result:
        row['spec']['model'] = '<same-weights-different-declared-alias>'
    return result


def validate_prior(protocol, evidence):
    prior = protocol.get('prior_condition')
    require(type(prior) is dict and prior.get('protocol_commit') == ORIGINAL,
            'Exact original interrupted condition must be declared')
    require(prior.get('partial_data_exposed_before_followup_freeze') is True
            and prior.get('cohorts_pooled') is False,
            'Partial-data exposure and separate unpooled cohorts must be explicit')
    path = evidence.item(prior['protocol'])
    relative = path.relative_to(evidence.root).as_posix()
    require(portable.git(evidence.root, 'show', f'{ORIGINAL}:{relative}') == path.read_bytes(),
            'Original protocol differs from published original commit')
    original = load(path)
    for key in ('metadata', 'seed', 'limits', 'arms', 'sources', 'native'):
        same(protocol[key], original[key], 'Follow-up changed registered scientific condition: ' + key)
    same(scientific_schedule(protocol), scientific_schedule(original), 'Follow-up changed cases, faults or arm rotation')
    require(protocol['runtime_binding']['model_blob_sha256'] == original['runtime_binding']['model_blob_sha256'],
            'Follow-up changed model weights')
    analysis_path = evidence.item(prior['interrupted_analysis'], sealed=True)
    if 'interrupted_analysis_manifest' in prior:
        same(exact_item(prior['interrupted_analysis_manifest']), binding(analysis_path.parent / 'manifest.json'),
             'Interrupted analysis manifest binding differs')
        evidence.item(prior['interrupted_analysis_manifest'])
    analysis = load(analysis_path)
    require(analysis.get('schema') == 'conseqax-limbo-analysis-v1'
            and analysis.get('planned_slots') == 96 and analysis.get('base_instances') == 12
            and analysis.get('planned_worlds') == 24, 'Original analysis omitted registered denominators')
    require(analysis.get('inputs', {}).get('protocol_commit') == ORIGINAL
            and {key: analysis['inputs']['protocol'][key] for key in ('sha256', 'bytes')} == binding(path),
            'Interrupted analysis is not bound to exact original protocol')
    evidence.tree(analysis['inputs'])
    audit_path = current_path(analysis['inputs']['audit']['path'], evidence.root)
    evidence.sealed(audit_path.parent)
    audit = load(audit_path)
    require(audit.get('schema') == 'conseqax-limbo-audit-v1' and audit.get('passed') is True
            and bool(audit.get('interrupted_collection')) and len(audit.get('rows', [])) == 96,
            'Original audit is not an explicit all-planned interrupted cohort')
    archive = Path(audit['interrupted_collection']['archive']).resolve()
    evidence.sealed(archive)
    same(binding(archive / 'manifest.json'), audit['collection_manifest'], 'Interrupted archive manifest differs')
    same(analysis['analysis_source'], binding(evidence.root / 'scripts/analyze_limbo_external_benchmark.py'),
         'Original and follow-up analysis implementations differ')
    analyzer = load_helper(evidence.root / 'scripts/analyze_limbo_external_benchmark.py', '_followup_frozen_analyzer')
    checked_original, checked_audit, inputs = analyzer.validate_inputs(audit_path, path, ORIGINAL)
    recomputed = analyzer.analyze(checked_original, checked_audit, inputs)
    for key, expected in recomputed.items():
        if key != 'created_utc':
            same(analysis[key], expected, 'Interrupted analysis recomputation differs: ' + key)
    return {'protocol': binding(path), 'analysis': binding(analysis_path),
            'audit': binding(audit_path), 'archive_manifest': binding(archive / 'manifest.json'),
            'partial_data_exposed_before_followup_freeze': True, 'cohorts_pooled': False}


def validate_private_runtime(item, runtime, version):
    path = Path(item['path']).resolve()
    same(stream_binding(path), exact_item(item), 'Private-runtime inventory copy changed')
    private = load(path)
    require(private.get('schema') == 'conseqax-private-cpu-runtime-v1'
            and private.get('declared_version') == version
            and private.get('source_before_equals_source_after_equals_private_copy') is True,
            'Invalid private-runtime copy evidence')
    destination = Path(private['destination']).resolve()
    original_manifest = destination / 'private-runtime-manifest.json'
    same(stream_binding(original_manifest), stream_binding(path), 'Private and published manifest bytes differ')
    expected = private['files']
    require(type(expected) is dict and {'ollama.exe', 'lib/ollama/llama-server.exe'} <= set(expected),
            'Private runtime entrypoints are not bound')
    actual_names = {file.relative_to(destination).as_posix() for file in destination.rglob('*')
                    if file.is_file() and file != original_manifest}
    require(actual_names == set(expected), 'Private runtime inventory has extra or missing files')
    for name, identity in expected.items():
        file = portable.safe_file(destination, name)
        same(stream_binding(file), identity, 'Private runtime binary/library changed: ' + name)
    for role, name in (('server', 'ollama.exe'), ('runner', 'lib/ollama/llama-server.exe')):
        require(Path(runtime[role + '_executable']).resolve() == destination / Path(*PurePosixPath(name).parts)
                and runtime[role + '_executable_sha256'] == expected[name]['sha256'],
                'Live binding is outside the declared private runtime: ' + role)
    return private


def validate_processes(runtime):
    import psutil
    checked = {}
    for role in ('server', 'runner'):
        process = psutil.Process(runtime[role + '_pid'])
        require(abs(process.create_time() - runtime[role + '_create_time']) < .001,
                'Bound live process birth identity changed: ' + role)
        require(Path(process.exe()).resolve() == Path(runtime[role + '_executable']).resolve(),
                'Bound live executable changed: ' + role)
        require(stream_binding(process.exe())['sha256'] == runtime[role + '_executable_sha256'],
                'Bound live executable bytes changed: ' + role)
        require(process.is_running() and process.status() != psutil.STATUS_ZOMBIE,
                'Bound runtime process is not live: ' + role)
        checked[role] = {'pid': process.pid, 'create_time': process.create_time(),
            'executable_sha256': runtime[role + '_executable_sha256']}
        if role == 'runner':
            require(process.ppid() == runtime['server_pid'], 'Runner parent is not bound server')
    return checked


def validate_readiness(protocol, evidence):
    path = evidence.item(protocol['readiness'], sealed=True)
    ready = load(path)
    require(ready.get('passed') is True and ready.get('schema') == 'conseqax-limbo-relocated-readiness-v1',
            'Passed relocated readiness is required')
    for key in ('sources', 'native', 'runtime_binding', 'environment'):
        same(ready[key], protocol[key], 'Protocol/readiness identity differs: ' + key)
    same(ready['wheel_file'], {key: protocol['wheel'][key] for key in ('sha256', 'bytes')},
         'Protocol/readiness wheel differs')
    from research.limbo_agent.harness import installed_wheel_binding
    same(installed_wheel_binding(protocol['wheel']['path']), ready['wheel'], 'Installed SDK wheel payload changed')
    require(ready.get('historical_protocol_commit') == ORIGINAL
            and ready.get('native_model_development_calls_added') == 0
            and ready.get('task_independent_budget_used') == ready.get('task_independent_budget_ceiling') == 8,
            'Historical/current readiness or fixed development budget changed')
    old_path = evidence.item(ready['historical_published_readiness'], sealed=True)
    relative = old_path.relative_to(evidence.root).as_posix()
    require(portable.git(evidence.root, 'show', f'{ORIGINAL}:{relative}') == old_path.read_bytes(),
            'Historical readiness differs from original published artifact')
    old = load(old_path)
    for name in ('transport_proof', 'scripted_receipt_path_proof'):
        evidence.item(old[name], sealed=True)
    for name in ('prospective_amendment', 'readiness_checker'):
        evidence.item(old[name])
    for item in old['development_audits'].values():
        audit_path = evidence.item(item, sealed=True)
        audit = load(audit_path)
        episode = current_path(audit['episode'], evidence.root)
        evidence.sealed(episode)
        same(binding(episode / 'manifest.json'), audit['episode_manifest'], 'Historical native episode changed')
        require(audit['passed'] is True and audit['row']['audit_complete'] is True
                and audit['row']['execution_success'] is True, 'Historical native validation is incomplete')
    for name in ('historical_native_execution_audits', 'historical_actual_sdk_path'):
        evidence.tree(ready[name])
    for name in ('current_transport_proof', 'current_schema_proof', 'durability_proof'):
        evidence.item(ready[name], sealed=True)
    transport = load(current_path(ready['current_transport_proof']['path'], evidence.root))
    require(transport.get('passed') is True and transport.get('runtime') == protocol['runtime_binding']
            and transport.get('native_episodes') == transport.get('service_dispatches') == 0
            and transport.get('model_invocation_cap') == 2,
            'Current two-call task-independent transport proof differs')
    schema = load(current_path(ready['current_schema_proof']['path'], evidence.root))
    require(schema.get('passed') is True and schema.get('runtime') == protocol['runtime_binding']
            and schema.get('public_tool_schema_count') == 26
            and schema.get('native_tasks') == schema.get('actual_generation_dispatches') == 0,
            'Current full public-schema zero-generation proof differs')
    for name in ('prospective_amendment', 'readiness_checker', 'current_runtime_launch'):
        evidence.item(ready[name])
    helper = load_helper(evidence.item(ready['readiness_checker']), '_followup_published_readiness')
    durability = helper.validate_durability(Path(ready['durability_proof']['path']))
    same(durability, ready['durability_validation'], 'Recomputed delayed-lifetime proof differs')
    launch = helper.validate_runtime_launch(Path(protocol['runtime_binding_file']['path']),
                                           protocol['runtime_binding'], durability)
    for name in ('current_runtime_launch', 'private_runtime_manifest', 'current_runtime_launch_evidence'):
        same(launch[name], ready[name], 'Recomputed static runtime launch evidence differs: ' + name)
    for name, identity in ready['current_runtime_launch_evidence'].items():
        evidence.file(portable.safe_file(evidence.root, name), identity)
    return ready


def run(native_root, protocol_path, commit, output, *, root=ROOT):
    root, native_root, protocol_path = Path(root).resolve(), Path(native_root).resolve(), Path(protocol_path).resolve()
    # The original frozen verifier enforces interpreter/dependency, scientific
    # source, registered schedule, exact published protocol and SDK-wheel bytes.
    from research.limbo_agent.protocol import native_binding, verify_protocol, utc
    protocol = verify_protocol(root, native_root, protocol_path, commit)
    same(native_binding(native_root), protocol['native'], 'Current native checkout/pin differs')
    evidence = Evidence(root)
    for name in set(SUPPORT) | set(protocol['sources']):
        evidence.file(portable.safe_file(root, name))
    evidence.file(protocol_path)
    evidence.item(protocol['runtime_binding_file'])
    same(load(protocol['runtime_binding_file']['path']), protocol['runtime_binding'], 'Runtime-binding file changed')
    condition = protocol.get('execution_condition')
    require(type(condition) is dict and condition.get('id') == 'relocated-isolated-runtime-2026-10-24'
            and condition.get('ollama_version') == '0.40.10', 'Explicit follow-up execution condition is missing')
    for key in ('private_runtime_manifest', 'runtime_launch_receipt', 'launcher', 'durability_proof',
                'amendment', 'declaration_source'):
        evidence.item(condition[key], sealed=key == 'durability_proof')
    # Verify auxiliary sources before executing their read-only proof validators.
    evidence.published(commit)
    prior = validate_prior(protocol, evidence)
    ready = validate_readiness(protocol, evidence)
    for key, ready_key in (('runtime_launch_receipt', 'current_runtime_launch'),
                           ('durability_proof', 'durability_proof'), ('amendment', 'prospective_amendment')):
        same({name: condition[key][name] for name in ('sha256', 'bytes')},
             {name: ready[ready_key][name] for name in ('sha256', 'bytes')},
             'Execution-condition/readiness proof differs: ' + key)
    same(stream_binding(ready['private_runtime_manifest']['path']),
         exact_item(condition['private_runtime_manifest']), 'Readiness private manifest differs from published copy')
    validate_private_runtime(condition['private_runtime_manifest'], protocol['runtime_binding'], condition['ollama_version'])
    require(stream_binding(protocol['runtime_binding']['model_blob'])['sha256']
            == protocol['runtime_binding']['model_blob_sha256'], 'Current model-weight bytes changed')
    processes = validate_processes(protocol['runtime_binding'])
    evidence.published(commit)
    remote = subprocess.run(['git', '-C', str(root), 'ls-remote', 'origin', 'refs/heads/main'],
        check=True, capture_output=True, text=True).stdout.split()
    require(len(remote) == 2 and remote == [commit, 'refs/heads/main'],
            'Exact protocol commit is not the verified published remote main head')
    out = Path(output).resolve()
    require(not any(out.is_relative_to(root / name) for name in evidence.manifests),
            'Launch-check output cannot alter sealed evidence')
    out.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'conseqax-limbo-followup-prelaunch-v1', 'passed': True, 'utc': utc(),
        'protocol_commit': commit, 'observed_remote_main': remote[0],
        'protocol': binding(protocol_path), 'readiness': exact_item(protocol['readiness']),
        'published_files_verified': evidence.files, 'sealed_manifests_verified': evidence.manifests,
        'prior_condition': prior, 'live_runtime_processes': processes,
        'private_runtime_full_inventory_verified': True, 'model_generations': 0,
        'processes_started_or_controlled': False, 'native_tasks_constructed_or_graded': False,
        'scope': 'Read-only publication/evidence gate; original and follow-up cohorts remain separate'}
    portable.write_json(out / 'prelaunch.json', result)
    (out / 'check_limbo_followup_launch.source.py').write_bytes(Path(__file__).read_bytes())
    portable.write_json(out / 'manifest.json', {path.relative_to(out).as_posix(): binding(path)
        for path in out.rglob('*') if path.is_file()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native-root', 'protocol', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--protocol-commit', required=True)
    args = parser.parse_args()
    result = run(args.native_root, args.protocol, args.protocol_commit, args.output)
    print(json.dumps({'passed': True, 'files': len(result['published_files_verified']),
                      'protocol_commit': args.protocol_commit, 'model_generations': 0}))


if __name__ == '__main__':
    main()
