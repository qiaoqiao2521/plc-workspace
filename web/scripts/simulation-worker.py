#!/usr/bin/env python3
"""Disposable JSON-lines worker; native compilation/FB calls never run in HTTP."""
import importlib.util
import json
from pathlib import Path
import sys


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    core = load('simulation-core')
    native = load('conveyor-runtime')
    runtime = handle = None
    try:
        for line in sys.stdin.buffer:
            body = None
            try:
                if len(line) > 262144:
                    raise ValueError('Worker input too large')
                body = json.loads(line)
                if body.get('command') == 'init' and runtime is None:
                    profile, normalized = core.prepare_program(body['program'])
                    runtime = native.NativeRuntime(
                        body['directory'], Path(body['compiler']), Path(body['library']),
                        source_bytes=normalized.encode(), block_name=profile['block'],
                        inputs=tuple(profile['inputs']), outputs=tuple(profile['outputs']), normalized=True)
                    handle = runtime.create()
                    result = {'engine': 'matiec/GCC persistent FB',
                              'runtime_source_sha256': runtime.normalized_hash}
                elif body.get('command') == 'scan' and runtime is not None:
                    values = body['inputs']
                    if set(values) != set(runtime.inputs) or any(type(x) is not bool for x in values.values()):
                        raise ValueError('Worker scan input mismatch')
                    result = runtime.scan(handle, values)
                else:
                    raise ValueError('Expected init followed by scan commands')
                response = {'ok': True, 'result': result}
            except Exception as error:
                message = type(error).__name__ + ': ' + str(error)
                if isinstance(body, dict) and body.get('command') == 'init':
                    folder = Path(body.get('directory', '/nonexistent'))
                    for name in ('iec2c.log', 'gcc.log'):
                        path = folder / name
                        if path.is_file():
                            details = path.read_text(errors='replace').strip()
                            if details:
                                message += '\n' + name + ':\n' + details[-4000:]
                response = {'ok': False, 'error': message}
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
            sys.stdout.flush()
    finally:
        if runtime is not None and handle is not None:
            runtime.destroy(handle)


if __name__ == '__main__':
    main()
