"""Validate real-project MCP contracts in disposable copies; never index originals.

Usage: python tools/validate_static_context_projects.py --doctor-mesh PATH
       --requests PATH --output PATH
Only eligible Python source bytes are copied. No analyzed code is imported/run.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from pie.indexing.indexer import index_project
from pie.scanning.discovery import iter_files


def snapshot(root):
    unreadable, directories, oversized = set(), set(), set()
    records = list(iter_files(root, unreadable_paths=unreadable,
                              unreadable_directories=directories, oversized_paths=oversized))
    if unreadable or directories or oversized:
        raise RuntimeError('Incomplete source discovery; refusing partial validation')
    return {r.path.as_posix(): r.content for r in records}


def validate(original, symbols, expected):
    before = snapshot(original)
    with TemporaryDirectory(prefix='pie-real-project-') as directory:
        root = Path(directory)
        for relative, content in before.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        indexed = index_project(root)
        if indexed['index_state'] != 'CURRENT':
            raise RuntimeError(f'Copy index is not CURRENT: {indexed}')
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
             'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                        'clientInfo': {'name': 'pie-real-project-validation', 'version': '1'}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        ]
        messages.extend({'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
                         'params': {'name': 'pie_build_context_pack',
                                    'arguments': {'symbol': symbol, 'max_chars': 32000, 'max_calls': 100}}}
                        for i, symbol in enumerate(symbols, 3))
        env = os.environ.copy()
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
        proc = subprocess.run([sys.executable, '-u', '-m', 'pie.interfaces.mcp_server',
                               '--root', str(root)],
                              input=''.join(json.dumps(m) + '\n' for m in messages),
                              text=True, encoding='utf-8', capture_output=True, env=env,
                              timeout=60, check=True)
        replies = {r['id']: r for r in map(json.loads, proc.stdout.splitlines())}
        if len(replies) != len(symbols) + 2:
            raise AssertionError('Unexpected MCP response count')
        if not any(t['name'] == 'pie_build_context_pack' for t in replies[2]['result']['tools']):
            raise AssertionError('Context Pack tool not discovered')
        packs = {}
        for i, symbol in enumerate(symbols, 3):
            reply = replies[i]['result']
            if reply.get('isError'):
                raise AssertionError(reply)
            pack = json.loads(reply['content'][0]['text'])
            if pack['coverage']['exhaustive'] or pack['coverage']['static_analysis_coverage'] != 'PARTIAL':
                raise AssertionError('Misleading exhaustive claim')
            if not pack['coverage']['returned_verified_call_list_complete']:
                raise AssertionError('Known results were truncated')
            for caller in pack['callers']:
                if sha256(before[caller['path']]).hexdigest() != caller['source_sha256']:
                    raise AssertionError('Caller hash mismatch')
            packs[symbol] = pack
        for symbol, locations in expected.items():
            actual = {(c['path'], c['line']) for c in packs[symbol]['callers']}
            if actual != set(locations):
                raise AssertionError(f'{symbol}: expected {locations!r}, got {actual!r}')
    if snapshot(original) != before:
        raise AssertionError('Original source snapshot changed during validation')
    return {'source_file_count': len(before), 'sources_unchanged': True,
            'source_sha256': {p: sha256(content).hexdigest() for p, content in before.items()},
            'index': indexed, 'packs': packs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--doctor-mesh', type=Path, required=True)
    parser.add_argument('--requests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {
        'doctor_mesh': validate(args.doctor_mesh, ['audit_component', 'MeasurementCache.get'], {
            'audit_component': [('ai_mesh_doctor/batch.py', 62), ('ai_mesh_doctor/capture.py', 115),
                                ('ai_mesh_doctor/ui.py', 627), ('tests/test_efficiency.py', 118),
                                ('tests/test_efficiency.py', 119), ('tests/test_efficiency.py', 122)],
        }),
        'requests': validate(args.requests, ['extract_cookies_to_jar'], {
            'extract_cookies_to_jar': [('src/requests/adapters.py', 365), ('src/requests/auth.py', 270),
                                     ('src/requests/sessions.py', 240), ('src/requests/sessions.py', 276),
                                     ('src/requests/sessions.py', 716), ('src/requests/sessions.py', 718)],
        }),
    }
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({name: {'source_file_count': value['source_file_count'],
                             'sources_unchanged': value['sources_unchanged'],
                             'verified_calls': {s: p['coverage']['verified_direct_call_count']
                                                for s, p in value['packs'].items()}}
                      for name, value in result.items()}, indent=2))


if __name__ == '__main__':
    main()
