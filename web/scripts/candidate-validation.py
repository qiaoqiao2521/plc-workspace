#!/usr/bin/env python3
"""Source-bound checks for a generated SCL candidate in the supported Linux subset.

The model cannot supply tests or change the named conveyor contract. Compiling and
executing generated code always happens in a disposable, time-bounded subprocess.
This is a local engineering tool, not a hostile-code sandbox or Siemens compiler.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
_policy_spec = importlib.util.spec_from_file_location('verification_policy', HERE / 'verification-policy.py')
policy = importlib.util.module_from_spec(_policy_spec)
_policy_spec.loader.exec_module(policy)
PROFILE = 'conveyor-12-v1'
INPUTS = ('Enable', 'Start', 'Stop', 'Reset', 'AtEnd')
OUTPUTS = ('Motor', 'Busy', 'Done', 'Error', 'TimeoutFault')
SCOPE = ('Linux matiec IEC ST subset after syntax-only Siemens adaptation; '
         'not TIA compilation, PLCSIM, formal verification or machine acceptance')
CONTRACT = {
    'id': PROFILE, 'block': 'FB_ConveyorPack', 'waiting_calls': 12,
    'start_call_counts_as_waiting': False, 'arrival_wins_at_deadline': True,
    'stop_revokes_motor': True, 'start_held_through_stop_restarts': False,
    'new_start_edge_after_release_restarts': True, 'done_is_one_call': True,
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


def check(name, status, detail):
    return {'name': name, 'status': status, 'detail': detail}


def normalize(source):
    """Only remove Siemens declaration decoration and local-variable prefixes.

    Keep line count for compiler diagnostics. Do not remove arbitrary pragmas:
    matiec can interpret some as native code, which is outside this adapter.
    """
    source = re.sub(r'(?im)^(\s*FUNCTION_BLOCK\s+)"([A-Za-z_][A-Za-z0-9_]*)"', r'\1\2', source)
    source = re.sub(r"(?im)^\s*\{\s*S7_Optimized_Access\s*:=\s*'(?i:TRUE|FALSE)'\s*\}[^\S\n]*$", '', source)
    source = re.sub(r'(?im)^[^\S\n]*VERSION\s*:[^\n]*', '', source)
    source = re.sub(r'(?im)^[^\S\n]*BEGIN[^\S\n]*$', '', source)
    # Transform tokens, preserving literals and comments rather than interpreting
    # // inside a string as a source comment.
    tokens = re.compile(r"'(?:(?:'')|[^'])*'|\(\*.*?\*\)|//[^\n]*|(?<![A-Za-z0-9_])#[A-Za-z_][A-Za-z0-9_]*|[{}]", re.S)
    def replace(match):
        value = match.group()
        if value.startswith('#'):
            return value[1:]
        if value.startswith('//'):
            return ' ' * len(value)
        if value in '{}':
            raise NotImplementedError('Native/vendor pragmas are outside the Linux adapter')
        return value
    source = tokens.sub(replace, source)
    if re.search(r'\b(?:REGION|END_REGION|VARIANT|WSTRING|WCHAR|AT|PEEK|POKE)\b|%[IQM]',
                 re.sub(r"'(?:(?:'')|[^'])*'|\(\*.*?\*\)", '', source, flags=re.S), re.I):
        raise NotImplementedError('Vendor addressing or instructions are outside the Linux adapter')
    return source


def wrapper(block):
    return (f'\nPROGRAM CandidateCheckProgram\nVAR\ninstance : {block};\nEND_VAR\n'
            'instance();\nEND_PROGRAM\nCONFIGURATION CandidateCheckConfig\n'
            'RESOURCE R ON PLC\nTASK Main(INTERVAL := T#50ms, PRIORITY := 0);\n'
            'PROGRAM P WITH Main : CandidateCheckProgram;\nEND_RESOURCE\nEND_CONFIGURATION\n')


def interface_error(source):
    blocks = re.findall(r'\bFUNCTION_BLOCK\s+([A-Za-z_][A-Za-z0-9_]*)', source, re.I)
    if blocks != ['FB_ConveyorPack']:
        return 'The frozen profile requires exactly one FB named FB_ConveyorPack'
    for section, names in (('VAR_INPUT', INPUTS), ('VAR_OUTPUT', OUTPUTS)):
        match = re.search(r'\b' + section + r'\b(.*?)\bEND_VAR\b', source, re.S | re.I)
        if not match:
            return f'The frozen profile requires {section}'
        declarations = match.group(1)
        for name in names:
            if not re.search(r'\b' + name + r'\s*:\s*BOOL\b', declarations, re.I):
                return f'The frozen profile requires {section} {name} : BOOL'
    return None


def run_scans(runtime, folder):
    """Fixed independently defined observations; no model-generated oracle."""
    cases = []
    def scenario(name, steps):
        handle = runtime.create()
        rows = []
        try:
            for number, (inputs, expected) in enumerate(steps, 1):
                actual = runtime.scan(handle, inputs)
                row = {'call': number, 'inputs': {n: bool(inputs.get(n, False)) for n in INPUTS},
                       'expected': expected, 'actual': actual,
                       'passed': all(actual[n] == value for n, value in expected.items())}
                rows.append(row)
                # Retain the last completed call if a later native call hangs.
                write_json(folder / 'scans.json', cases + [{'name': name, 'calls': rows}])
        finally:
            runtime.destroy(handle)
        cases.append({'name': name, 'calls': rows,
                      'passed': all(row['passed'] for row in rows)})

    start = ({'Enable': True, 'Start': True}, {'Motor': 1, 'Done': 0, 'Error': 0, 'TimeoutFault': 0})
    waiting = ({'Enable': True}, {'Motor': 1, 'Done': 0, 'Error': 0, 'TimeoutFault': 0})
    scenario('timeout_on_waiting_call_12', [start] + [waiting] * 11 + [
        ({'Enable': True}, {'Motor': 0, 'Done': 0, 'Error': 1, 'TimeoutFault': 1})])
    scenario('arrival_wins_on_waiting_call_12', [start] + [waiting] * 11 + [
        ({'Enable': True, 'AtEnd': True}, {'Motor': 0, 'Done': 1, 'Error': 0, 'TimeoutFault': 0}),
        ({'Enable': True, 'AtEnd': True}, {'Motor': 0, 'Done': 0, 'Error': 0, 'TimeoutFault': 0})])
    scenario('early_arrival_done_one_call', [start,
        ({'Enable': True, 'AtEnd': True}, {'Motor': 0, 'Done': 1, 'Error': 0, 'TimeoutFault': 0}),
        ({'Enable': True, 'AtEnd': True}, {'Motor': 0, 'Done': 0, 'Error': 0, 'TimeoutFault': 0})])
    scenario('held_start_through_stop_needs_new_edge', [start,
        ({'Enable': True, 'Start': True, 'Stop': True}, {'Motor': 0, 'Done': 0}),
        ({'Enable': True, 'Start': True}, {'Motor': 0, 'Done': 0}),
        ({'Enable': True, 'Start': True}, {'Motor': 0, 'Done': 0}),
        ({'Enable': True}, {'Motor': 0}),
        ({'Enable': True, 'Start': True}, {'Motor': 1, 'Done': 0})])
    scenario('start_edge_during_stop_is_consumed', [start, waiting,
        ({'Enable': True, 'Start': True, 'Stop': True}, {'Motor': 0, 'Done': 0}),
        ({'Enable': True, 'Start': True}, {'Motor': 0, 'Done': 0}),
        ({'Enable': True}, {'Motor': 0}),
        ({'Enable': True, 'Start': True}, {'Motor': 1, 'Done': 0})])
    write_json(folder / 'scans.json', cases)
    return cases


def _worker(folder):
    job = json.loads((folder / 'job.json').read_text())
    def captured_source(item):
        content = (folder / 'sources' / item['name']).read_bytes()
        if sha(content) != item['sha256']:
            raise ValueError('Captured source changed before compilation: ' + item['name'])
        return content.decode('utf-8')
    source = '\n'.join(captured_source(item) for item in job['files'])
    try:
        adapted = normalize(source)
    except NotImplementedError as error:
        write_json(folder / 'worker-result.json', {'status': 'unknown', 'diagnostics': str(error),
            'checks': [check('linux_compile', 'unknown', str(error))]})
        return
    blocks = re.findall(r'\bFUNCTION_BLOCK\s+([A-Za-z_][A-Za-z0-9_]*)', adapted, re.I)
    if not blocks:
        write_json(folder / 'worker-result.json', {'status': 'unknown', 'diagnostics': 'No supported FUNCTION_BLOCK declaration',
            'checks': [check('linux_compile', 'unknown', 'Adapter requires at least one FUNCTION_BLOCK')]})
        return
    build = folder / 'build'
    build.mkdir()
    translated = adapted + wrapper(blocks[0])
    (build / 'input.st').write_text(translated)
    result = subprocess.run([job['compiler'], '-I', job['library'], '-T', str(build), str(build / 'input.st')],
                            capture_output=True, text=True, timeout=60)
    diagnostics = result.stdout + result.stderr
    (build / 'iec2c.log').write_text(diagnostics)
    normalized = {'normalized_sha256': sha(translated.encode())}
    if result.returncode:
        write_json(folder / 'worker-result.json', {**normalized, 'status': 'fail', 'diagnostics': diagnostics[-40000:],
            'checks': [check('linux_compile', 'fail', 'matiec rejected the captured candidate; see build/iec2c.log')]})
        return
    checks = [check('linux_compile', 'pass', 'Captured candidate compiled by matiec (syntax-adapted IEC ST subset)')]
    outcome = {**normalized, 'status': 'pass', 'diagnostics': diagnostics[-40000:], 'checks': checks}
    # Preserve completed compilation even if a later native scan is cancelled or
    # terminated by its watchdog. These are observations, not final acceptance.
    write_json(folder / 'worker-progress.json', outcome)
    if not job['profile']:
        checks.append(check('scan_contract', 'not_run', 'No independently fixed behavior profile selected'))
    elif job['profile'] != PROFILE:
        outcome.update(status='unknown', diagnostics='Unsupported behavior profile: ' + job['profile'])
        checks.append(check('scan_contract', 'unknown', outcome['diagnostics']))
    else:
        problem = interface_error(adapted)
        if problem:
            outcome.update(status='fail', diagnostics=problem)
            checks.append(check('scan_contract', 'fail', problem))
        else:
            spec = importlib.util.spec_from_file_location('candidate_native', HERE / 'conveyor-runtime.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            try:
                # Already normalized text has no Siemens decoration. The fixed
                # native interface reads public outputs, never private stat names.
                runtime = module.NativeRuntime(folder / 'native', job['compiler'], job['library'],
                    source_bytes=adapted.encode(), block_name='FB_ConveyorPack', inputs=INPUTS, outputs=OUTPUTS,
                    normalized=True)
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
                logs = '\n'.join(path.read_text() for path in sorted((folder / 'native').glob('*.log')))
                outcome.update(status='unknown', diagnostics=str(error) + '\n' + logs[-40000:])
                checks.append(check('scan_contract', 'unknown', 'Native adapter failed; inspect native tool diagnostics'))
            else:
                # A native call cannot be interrupted by Python signal handlers.
                # SIGALRM terminates this disposable worker if a scan loops.
                if os.name == 'posix':
                    signal.alarm(5)
                try:
                    cases = run_scans(runtime, folder)
                finally:
                    if os.name == 'posix':
                        signal.alarm(0)
                passed = all(case['passed'] for case in cases)
                outcome.update(status='pass' if passed else 'fail', scenarios=cases)
                failures = [f"{case['name']} call {row['call']}: expected {row['expected']}, actual {row['actual']}"
                            for case in cases for row in case['calls'] if not row['passed']]
                if failures:
                    outcome['diagnostics'] = '\n'.join(failures)
                checks.append(check('scan_contract', 'pass' if passed else 'fail',
                    f'{PROFILE}: {sum(len(c["calls"]) for c in cases)} native calls, '
                    + (f'{len(cases)} scenarios passed' if passed else '\n'.join(failures)[:6000])))
    write_json(folder / 'worker-result.json', outcome)


def validate_candidate(result, runtime_path, *, profile=None, compiler=None, library=None):
    """Capture candidate, run checks, and save an immutable source-bound report.

    Every call needs its own fresh directory outside the repository. Missing
    compiler/native adapter support is unknown, never a pass or a code error.
    """
    folder = Path(runtime_path).resolve()
    if folder.is_relative_to(ROOT):
        raise ValueError('Candidate validation directory must be outside repository')
    folder.mkdir(parents=True, exist_ok=False)
    source_folder = folder / 'sources'
    source_folder.mkdir()
    files = []
    report = {'status': 'unknown', 'files': files, 'checks': [], 'diagnostics': '', 'scope': SCOPE,
              'profile': profile, 'industrial_acceptance': 'not_run', 'tia_compile': 'not_run',
              'adapter_sha256': sha(Path(__file__).read_bytes()),
              'request_fingerprint': result.get('request_fingerprint')}
    def finish_report():
        # Tool checks describe distinct scopes; never upgrade compile-only work.
        complete = policy.complete_report(report, profile)
        write_json(folder / 'report.json', complete)
        return complete
    if profile == PROFILE:
        report['contract'] = dict(CONTRACT)
        report['contract_sha256'] = sha(json.dumps(CONTRACT, sort_keys=True, separators=(',', ':')).encode())
        write_json(folder / 'contract.json', CONTRACT)
    try:
        supplied = result['scl_files']
        if not isinstance(supplied, list) or not supplied or len(supplied) > 100:
            raise ValueError('Candidate requires 1..100 source files')
        names = set()
        for item in supplied:
            name, content = item['name'], item['content']
            if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*\.(?:scl|st)', name)
                    or name.casefold() in names or not isinstance(content, str) or len(content.encode()) > 200000):
                raise ValueError('Invalid, duplicate or oversized SCL file')
            names.add(name.casefold())
            captured = content.encode('utf-8')
            (source_folder / name).write_bytes(captured)
            files.append({'name': name, 'sha256': sha(captured)})
    except (KeyError, TypeError, ValueError) as error:
        report.update(reason='source_invalid', diagnostics=str(error),
                      checks=[check('source_structure', 'fail', str(error))])
        return finish_report()
    captured_check = check('source_structure', 'pass',
                           'Source file names, UTF-8 content, uniqueness and size checked; not PLC behavior')
    report['checks'] = [captured_check]
    report['source_sha256'] = sha(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
    compiler = compiler or os.getenv('SIM_IEC2C')
    library = library or os.getenv('SIM_MATIEC_LIB')
    executable = shutil.which(str(compiler)) if compiler else None
    if not executable or not library or not (Path(library) / 'ieclib.txt').is_file():
        report.update(reason='tool_missing', diagnostics='Configure SIM_IEC2C and SIM_MATIEC_LIB for an installed matiec compiler',
                      checks=[captured_check, check('linux_compile', 'unknown', 'matiec compiler/library unavailable'),
                              check('scan_contract', 'not_run', 'Compilation unavailable')])
        return finish_report()
    compiler = str(Path(executable).resolve())
    library = str(Path(library).resolve())
    report['tools'] = {'iec2c': {'path': compiler, 'binary_sha256': sha(Path(compiler).read_bytes())},
                       'matiec_library': library}
    write_json(folder / 'job.json', {'files': files, 'compiler': compiler, 'library': library, 'profile': profile})
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', str(folder)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=(os.name == 'posix'))
    def terminate_worker():
        try:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        return process.communicate()
    def interrupted_checks(detail):
        progress = folder / 'worker-progress.json'
        completed = json.loads(progress.read_text()) if progress.is_file() else {}
        compiled = next((c for c in completed.get('checks', []) if c['name'] == 'linux_compile'),
                        check('linux_compile', 'unknown', detail))
        return [captured_check, compiled, check('scan_contract', 'unknown' if profile else 'not_run', detail)]
    try:
        stdout, stderr = process.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        stdout, stderr = terminate_worker()
        report.update(reason='tool_timeout', diagnostics='Candidate check exceeded the 90 second tool budget; no pass accepted',
                      checks=interrupted_checks('Tool/native execution timed out'))
    except BaseException as error:
        # Cancellation must also reap the independent native process group.
        terminate_worker()
        report.update(reason='cancelled' if isinstance(error, (InterruptedError, KeyboardInterrupt)) else 'worker_failed',
                      diagnostics='Candidate validation interrupted; no current acceptance',
                      checks=interrupted_checks('Validation interrupted'))
        finish_report()
        raise
    else:
        outcome_file = folder / 'worker-result.json'
        if process.returncode == 0 and outcome_file.is_file():
            report.update(json.loads(outcome_file.read_text()))
            report['checks'].insert(0, captured_check)
        else:
            explanation = ('Native scan exceeded the 5 second execution budget'
                           if process.returncode == -signal.SIGALRM else f'Validation worker exited {process.returncode}')
            report.update(reason='tool_timeout' if process.returncode == -signal.SIGALRM else 'worker_failed',
                          diagnostics=stderr[-40000:] or explanation,
                          checks=interrupted_checks('Tool/native execution failed'))
    (folder / 'worker.log').write_text(stdout + stderr)
    report['checks'].append(check('tia_compile', 'not_run', 'Requires target Windows TIA/Openness environment'))
    return finish_report()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    args = parser.parse_args()
    _worker(args.worker.resolve())
