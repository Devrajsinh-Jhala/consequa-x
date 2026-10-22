"""Check all public native tool schemas against a live render/tokenizer, no generation."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.limbo_agent.transport import AuditedLIMBOClient, RuntimeBinding, write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', required=True)
    parser.add_argument('--binding', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.native_root).resolve()))
    from limbo.services import build_tools
    from limbo.prompts import GENERAL_TOOL_SCHEMAS
    tools = [tool.schema('neutral') for _, tool in sorted(build_tools('native').items())]
    tools += GENERAL_TOOL_SCHEMAS
    binding = RuntimeBinding.from_dict(json.loads(Path(args.binding).read_text(encoding='utf-8')))
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    payload = {'model': binding.model,
        'messages': [{'role': 'system', 'content': 'Task-independent complete public tool-schema render check.'},
                     {'role': 'user', 'content': 'Do not execute any operation.'}],
        'tools': [{'type': 'function', 'function': tool} for tool in tools],
        'max_tokens': 512, 'temperature': 0, 'seed': 1701}
    write_json(output / 'native-public-request.json', payload)
    with AuditedLIMBOClient(binding, output / 'client', max_requests=1,
            max_output_tokens=512, request_timeout_s=1200, seed=1701) as client:
        client._current = {'prefix': output / 'schema-preview', 'number': 0, 'dispatched': 0}
        try:
            receipt = client._context_check(payload)
        finally:
            client._current = None
    write_json(output / 'result.json', {'passed': receipt['passed'], 'runtime': asdict(binding),
        'public_tool_schema_count': len(tools), 'actual_generation_dispatches': 0,
        'native_tasks': 0, 'scope': 'All public implementation schemas; invented messages, render/tokenize only',
        'context': receipt['offline_context']})
    print(json.dumps({'passed': receipt['passed'], 'schemas': len(tools),
        'prompt_tokens': receipt['offline_context']['prompt_tokens'], 'generation_dispatches': 0}))


if __name__ == '__main__':
    main()
