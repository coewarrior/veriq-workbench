#!/usr/bin/env python3
"""Upload a local, already-redacted artifact without putting Base64 in model context."""
import argparse
import importlib.util
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, type=Path, help='Verified platform api-test-client.py')
    parser.add_argument('--url', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--execution', required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--step', required=True)
    parser.add_argument('--kind', choices=['screenshot', 'video', 'fixture', 'observation'], default='screenshot')
    parser.add_argument('--captured-at', default='')
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('workspace_client', args.client)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.Client(args.url)
    asset = client.asset_from_file(args.file, case_id=args.case, step=args.step,
                                   kind=args.kind, captured_at=args.captured_at)
    result = client.call('upload_ui_test_asset', {
        'project_id': args.project, 'execution_id': args.execution, **asset})
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
