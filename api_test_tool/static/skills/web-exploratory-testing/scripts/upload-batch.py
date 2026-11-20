#!/usr/bin/env python3
"""Upload local UI evidence in validated batches without exposing Base64 to model context."""
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
    parser.add_argument('--manifest', required=True, type=Path,
                        help='JSON list: file,case_id,step and optional kind,captured_at,filename,content_type')
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('workspace_client', args.client)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.Client(args.url)
    totals = client.upload_assets_from_files(args.project, args.execution, entries)
    print(json.dumps(totals, ensure_ascii=False))


if __name__ == '__main__':
    main()
