#!/usr/bin/env python3
"""Source-bound checks for a generated SCL candidate in the supported Linux subset.

The model cannot supply tests or change the named conveyor contract. Compiling and
executing generated code always happens in a disposable, time-bounded subprocess.
This is a local engineering tool, not a hostile-code sandbox or Siemens compiler.
"""
import argparse
import hashlib
import importlib.util
from itertools import chain
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
PROFILE = policy.PROFILE
INPUTS = ('Enable', 'Start', 'Stop', 'Reset', 'AtEnd')
OUTPUTS = ('Motor', 'Busy', 'Done', 'Error', 'TimeoutFault')
SCOPE = ('Linux matiec IEC ST subset after syntax-only Siemens adaptation; '
         'not TIA compilation, PLCSIM, formal verification or machine acceptance')
CONTRACT = policy.CONTRACT
LATCH_PROFILE = policy.LATCH_PROFILE


def logic_module():
    spec = importlib.util.spec_from_file_location('logic_ir', HERE / 'logic-ir.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


def check(name, status, detail):
    return {'name': name, 'status': status, 'detail': detail}


# Compatibility helpers delegate to the one report policy.
verification_goal = policy.goal
report_matches_profile = policy.report_matches_profile


def check_statuses(report):
    """Validate raw worker observations before using a partial checkpoint."""
    rows = report.get('checks') if isinstance(report, dict) else None
    if not isinstance(rows, list) or len(rows) >= 100:
        return None
    statuses = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'name', 'status', 'detail'}
                or not isinstance(row['name'], str) or not isinstance(row['detail'], str)
                or row['name'] in statuses or row['status'] not in policy.STATUSES):
            return None
        statuses[row['name']] = row['status']
    return statuses


def validation_level(report, profile, request_fingerprint):
    if (not isinstance(report, dict) or not isinstance(request_fingerprint, str)
            or report.get('request_fingerprint') != request_fingerprint):
        return None
    assessed = policy.assess_report(report, profile)
    level = policy.validation_level(assessed['acceptance'])
    return level if level != 'not_accepted' else None


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


def run_latch_scans(runtime, folder, serialized_graph):
    """Execute both delivered artifacts against a separate fixed contract oracle.

    Persist every observed sequence, but include only named traces and the first
    counterexamples in model packets. No test expectations come from either
    generator or executor. Four-call enumeration is bounded test evidence.
    """
    ladder = logic_module().LadRuntime(serialized_graph)
    contract = policy.latch
    named = contract.fixed_scenarios()
    summary = {'named_scenarios': 0, 'named_calls': 0, 'bounded_scenarios': 0, 'bounded_calls': 0,
               'scl_passed': True, 'lad_passed': True, 'agreement_passed': True,
               'counterexamples': {}}
    retained = []
    trace_path = folder / 'latch-traces.jsonl'
    with trace_path.open('w') as traces:
        for index, case in enumerate(chain(named, contract.bounded_scenarios())):
            native_handle, lad_handle = runtime.create(), ladder.create()
            rows = []
            try:
                for number, (inputs, expected) in enumerate(case['steps'], 1):
                    scl = runtime.scan(native_handle, inputs)
                    lad = ladder.scan(lad_handle, inputs)
                    row = {'call': number, 'inputs': inputs, 'expected': expected, 'scl': scl, 'lad': lad}
                    for key, passed in (('scl', scl == expected), ('lad', lad == expected), ('agreement', scl == lad)):
                        summary[key + '_passed'] &= passed
                        if not passed and key not in summary['counterexamples']:
                            summary['counterexamples'][key] = {'scenario': case['name'], **row,
                                'prefix': rows + [row]}
                    rows.append(row)
            finally:
                runtime.destroy(native_handle)
                ladder.destroy(lad_handle)
            observed = {'name': case['name'], 'calls': rows,
                        'passed': bool(rows) and all(row['scl'] == row['expected'] == row['lad'] for row in rows)}
            traces.write(json.dumps(observed, ensure_ascii=False, separators=(',', ':')) + '\n')
            bucket = 'named' if index < len(named) else 'bounded'
            summary[bucket + '_scenarios'] += 1
            summary[bucket + '_calls'] += len(rows)
            if bucket == 'named':
                retained.append(observed)
        traces.flush()
    # Empty or incomplete enumeration is a failed check, never an all([]) pass.
    complete = (summary['named_scenarios'] == 14 and summary['named_calls'] == 64
                and summary['bounded_scenarios'] == 8 ** contract.BOUNDED_CALLS
                and summary['bounded_calls'] == contract.BOUNDED_CALLS * 8 ** contract.BOUNDED_CALLS)
    if not complete:
        summary.update(scl_passed=False, lad_passed=False, agreement_passed=False,
                       incomplete_evidence=True)
    summary.update(trace_file=trace_path.name, trace_sha256=sha(trace_path.read_bytes()),
                   scope='14 named scenarios and all 4096 four-call BOOL input sequences from fresh instances; finite tests only')
    write_json(folder / 'latch-summary.json', summary)
    return retained, summary


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
    outcome = {**normalized, 'status': 'unknown', 'diagnostics': diagnostics[-40000:], 'checks': checks}
    # Preserve completed compilation even if a later native scan is cancelled or
    # terminated by its watchdog. These are observations, not final acceptance.
    write_json(folder / 'worker-progress.json', outcome)
    if not job['profile']:
        checks.append(check('scan_contract', 'not_run', 'No independently fixed behavior profile selected'))
    elif job['profile'] == LATCH_PROFILE:
        graph_bytes = (folder / 'lad_graph.json').read_bytes()
        if sha(graph_bytes) != job['lad_graph_file_sha256']:
            raise ValueError('Captured LAD graph changed before execution')
        native_spec = importlib.util.spec_from_file_location('candidate_native', HERE / 'conveyor-runtime.py')
        native = importlib.util.module_from_spec(native_spec)
        native_spec.loader.exec_module(native)
        try:
            runtime = native.NativeRuntime(folder / 'native', job['compiler'], job['library'],
                source_bytes=adapted.encode(), block_name=policy.latch.BLOCK,
                inputs=policy.latch.INPUTS, outputs=policy.latch.OUTPUTS, normalized=True)
            if os.name == 'posix':
                signal.alarm(15)
            try:
                cases, comparison = run_latch_scans(runtime, folder, graph_bytes)
            finally:
                if os.name == 'posix':
                    signal.alarm(0)
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
            outcome.update(status='unknown', diagnostics=str(error))
            checks.extend([check(name, 'unknown', 'Native or LAD adapter failed: ' + str(error))
                           for name in ('scan_contract', 'lad_scl_compare')])
        else:
            scl_pass = comparison['scl_passed']
            both_pass = scl_pass and comparison['lad_passed'] and comparison['agreement_passed']
            detail = (f"{LATCH_PROFILE}: {comparison['named_scenarios']} named scenarios / "
                      f"{comparison['named_calls']} calls; {comparison['bounded_scenarios']} four-call "
                      f"sequences / {comparison['bounded_calls']} calls; finite tests, not equivalence proof")
            failures = json.dumps(comparison['counterexamples'], ensure_ascii=False)
            if comparison.get('incomplete_evidence'):
                failures = 'Incomplete/empty fixed contract observations'
            outcome.update(status='pass' if both_pass else 'fail', scenarios=cases,
                           comparison=comparison, diagnostics='' if both_pass else failures)
            checks.append(check('scan_contract', 'pass' if scl_pass else 'fail',
                                detail + ('; native SCL matches independent expectations' if scl_pass else '; ' + failures)))
            checks.append(check('lad_scl_compare', 'pass' if both_pass else 'fail',
                                detail + ('; serialized LAD and native SCL each match expectations and each other'
                                          if both_pass else '; ' + failures)))
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
                passed = bool(cases) and all(case['calls'] and case['passed'] for case in cases)
                outcome.update(status='pass' if passed else 'fail', scenarios=cases)
                failures = [f"{case['name']} call {row['call']}: expected {row['expected']}, actual {row['actual']}"
                            for case in cases for row in case['calls'] if not row['passed']]
                if not cases or any(not case['calls'] for case in cases):
                    failures.append('Fixed behavior checks returned no native scan evidence')
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
              'profile': profile or None, 'industrial_acceptance': 'not_run', 'tia_compile': 'not_run',
              'adapter_sha256': sha(Path(__file__).read_bytes()),
              'request_fingerprint': result.get('request_fingerprint')}
    def finish_report():
        # Tool checks describe distinct scopes; never upgrade compile-only work.
        complete = policy.complete_report(report, profile)
        write_json(folder / 'report.json', complete)
        return complete
    contract = policy.contract_for(profile)
    if contract:
        report['contract'] = contract
        report['contract_sha256'] = policy.contract_digest(profile)
        write_json(folder / 'contract.json', contract)
    if profile == LATCH_PROFILE:
        report.update(policy.artifact_bindings(result))
        for name in ('logic_ir', 'lad_graph'):
            if name in result:
                write_json(folder / (name + '.json'), result[name])
    try:
        supplied = result['scl_files']
        if not isinstance(supplied, list) or len(supplied) > 100:
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
        if profile == LATCH_PROFILE:
            logic = logic_module()
            generated = logic.generate(result.get('logic_ir'))
            logic.validate_lad(result.get('lad_graph'))
            if (result.get('scl_files') != generated['scl_files']
                    or result.get('lad_graph') != generated['lad_graph'] or result.get('lad_networks') != []):
                raise ValueError('SCL and serialized LAD must be the deterministic products of this exact IR')
            report['generator'] = {'version': logic.GENERATOR_VERSION,
                                   'sha256': sha((HERE / 'logic-ir.py').read_bytes())}
        elif 'logic_ir' in result or 'lad_graph' in result:
            raise ValueError('IR/LAD artifacts require the explicit latch-start-stop-v1 contract')
        if not files:
            raise ValueError('Candidate requires 1..100 source files')
    except (KeyError, TypeError, ValueError) as error:
        report.update(reason='source_invalid', diagnostics=str(error),
                      checks=[check('source_structure', 'fail', str(error))])
        return finish_report()
    captured_check = check('source_structure', 'pass',
                           ('Bounded BOOL IR, symbols, single writers, graph topology and deterministic product association checked; not PLC behavior'
                            if profile == LATCH_PROFILE else
                            'Source file names, UTF-8 content, uniqueness and size checked; not PLC behavior'))
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
    job = {'files': files, 'compiler': compiler, 'library': library, 'profile': profile}
    if profile == LATCH_PROFILE:
        job['lad_graph_file_sha256'] = sha((folder / 'lad_graph.json').read_bytes())
    write_json(folder / 'job.json', job)
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
        compiled = check('linux_compile', 'unknown', detail)
        try:
            observed = json.loads((folder / 'worker-progress.json').read_text())
            if check_statuses(observed) == {'linux_compile': 'pass'}:
                compiled = observed['checks'][0]
        except (OSError, ValueError):
            pass
        return [captured_check, compiled,
                check('scan_contract', 'unknown' if profile else 'not_run', detail)] + (
                    [check('lad_scl_compare', 'unknown', detail)] if profile == LATCH_PROFILE else [])

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
            try:
                outcome = json.loads(outcome_file.read_text())
                if (check_statuses(outcome) is None or outcome.get('status') not in policy.STATUSES
                        or not isinstance(outcome.get('diagnostics'), str)):
                    raise ValueError('Invalid validation worker delivery')
                report.update(status=outcome['status'], diagnostics=outcome['diagnostics'],
                              checks=[captured_check, *outcome['checks']])
                # Workers supply observations, never source/request/contract identity.
                for key in ('normalized_sha256', 'scenarios', 'comparison'):
                    if key in outcome:
                        report[key] = outcome[key]
            except (OSError, ValueError):
                report.update(reason='invalid_report', diagnostics='Invalid validation worker delivery',
                              checks=interrupted_checks('Worker result could not be validated'))
        else:
            explanation = (('Native/LAD scan exceeded the 15 second execution budget' if profile == LATCH_PROFILE
                            else 'Native scan exceeded the 5 second execution budget')
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
