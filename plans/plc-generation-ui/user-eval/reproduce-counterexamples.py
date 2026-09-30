"""Bounded scan probes of recorded candidates, using the existing matiec toolchain.

Syntax normalization is explicit. This is not Siemens compilation or deployment.
"""
import argparse
import ctypes
import hashlib
import json
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-dir', type=Path, default=Path(__file__).resolve().parent / 'candidates')
parser.add_argument('--work-dir', type=Path, required=True, help='Temporary output outside the repository')
parser.add_argument('--iec2c', type=Path, required=True)
parser.add_argument('--matiec-lib', type=Path, required=True)
args = parser.parse_args()
TASK = args.source_dir.resolve()
OUT = args.work_dir.resolve()
COMPILER = args.iec2c.resolve()
LIBRARY = args.matiec_lib.resolve()
if OUT.is_relative_to(Path(__file__).resolve().parents[3]):
    parser.error('--work-dir must be outside the repository')

def compile_candidate(name, inputs, outputs):
    original = (TASK / (name + '.scl')).read_text()
    source = re.sub(r'FUNCTION_BLOCK "([A-Za-z_][A-Za-z0-9_]*)"', r'FUNCTION_BLOCK \1', original)
    source = re.sub(r'(?m)^\{[^\n]*\}\s*$', '', source)
    source = re.sub(r'(?m)^VERSION\s*:[^\n]*$', '', source)
    source = re.sub(r'(?m)^BEGIN\s*$', '', source)
    source = re.sub(r'#(?=[A-Za-z_])', '', source)
    source = re.sub(r'//[^\n]*', '', source)
    constant_block = re.search(r'(?ms)^CONST\s*\n(.*?)^END_CONST\s*$', source)
    if constant_block:
        constants = re.findall(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*INT\s*:=\s*([0-9]+)\s*;\s*$', constant_block[1], re.M)
        if len(constants) != constant_block[1].count(';'):
            raise ValueError('Only literal INT constants are supported by this probe')
        source = source[:constant_block.start()] + source[constant_block.end():]
        for symbol, value in constants:
            source = re.sub(r'\b' + re.escape(symbol) + r'\b', value, source)
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    program = f'\nPROGRAM ProbeProgram\nVAR\n b : {name};\nEND_VAR\nb();\nEND_PROGRAM\nCONFIGURATION ProbeConfig\nRESOURCE R ON PLC\nTASK Main(INTERVAL := T#50ms, PRIORITY := 0);\nPROGRAM P WITH Main : ProbeProgram;\nEND_RESOURCE\nEND_CONFIGURATION\n'
    (folder / 'input.st').write_text(source + program)
    fb_type = name.upper()
    setters = '\n'.join(f'b.{n.upper()}.value = (flags >> {i}) & 1;' for i, n in enumerate(inputs))
    getters = '\n'.join(f'out[{i}] = b.{n.upper()}.value;' for i, n in enumerate(outputs))
    driver = f'''#include <stdint.h>
#include "POUS.h"
TIME __CURRENT_TIME;
#include "POUS.c"
static {fb_type} b;
void reset_instance(void) {{ b=({fb_type}){{0}}; {fb_type}_init__(&b,0); }}
void scan(unsigned flags,int32_t *out) {{ {setters} {fb_type}_body__(&b); {getters} }}
'''
    (folder / 'driver.c').write_text(driver)
    commands = [('iec2c', [str(COMPILER), '-I', str(LIBRARY), '-T', str(folder), str(folder / 'input.st')]),
                ('gcc', ['gcc', '-shared', '-fPIC', '-std=gnu11', '-I', str(LIBRARY / 'C'), '-I', str(folder), str(folder / 'driver.c'), '-lm', '-o', str(folder / 'runtime.so')])]
    for label, args in commands:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        (folder / (label + '.log')).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f'{name} {label}: exit {result.returncode}; see {folder}')
    lib = ctypes.CDLL(str(folder / 'runtime.so'))
    lib.reset_instance.argtypes = []
    lib.reset_instance.restype = None
    lib.scan.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_int32)]
    lib.scan.restype = None
    def scan(**values):
        flags = sum(bool(values.get(n, False)) << i for i, n in enumerate(inputs))
        result = (ctypes.c_int32 * len(outputs))()
        lib.scan(flags, result)
        return dict(zip(outputs, result))
    return lib.reset_instance, scan, hashlib.sha256(original.encode()).hexdigest()

def main():
    reset_a, a, a_hash = compile_candidate('FB_ConveyorPack',
        ['Enable', 'Start', 'Stop', 'Reset', 'AtEnd'],
        ['statState', 'statWaitCount', 'Motor', 'Busy', 'Done', 'Error', 'TimeoutFault'])
    checks = []
    def check(label, observed, expected):
        checks.append({'case': label, 'observed': observed, 'expected': expected,
                       'matches': all(observed[k] == v for k, v in expected.items())})
    reset_a()
    check('A startup', a(Enable=True, Start=True), {'statState': 2, 'statWaitCount': 0, 'Motor': 1})
    for i in range(1, 8):
        check(f'A wait {i}, Enable withdrawn', a(), {'statWaitCount': i, 'Motor': 1, 'Error': 0})
    check('A wait 8 timeout', a(), {'statState': 1, 'Motor': 0, 'Error': 1, 'TimeoutFault': 1})
    check('A Stop plus Reset retains fault', a(Enable=True, Stop=True, Reset=True), {'Error': 1, 'TimeoutFault': 1})
    check('A held Reset after Stop release', a(Enable=True, Reset=True), {'Error': 1, 'TimeoutFault': 1})
    a(Enable=True)
    check('A fresh Reset plus Start clears without restart', a(Enable=True, Reset=True, Start=True), {'Motor': 0, 'Error': 0})
    reset_a()
    a(Enable=True, Start=True)
    for _ in range(7): a()
    check('A arrival at deadline', a(AtEnd=True), {'Done': 1, 'Error': 0, 'Motor': 0})
    check('A next scan pulse cleared', a(), {'Done': 0})
    reset_a()
    check('A idle Reset plus Start', a(Enable=True, Reset=True, Start=True), {'Motor': 0})
    reset_a()
    a(Enable=True, Stop=True, Start=True)
    check('A held Start after Stop', a(Enable=True, Start=True), {'Motor': 0})

    reset_b, b, b_hash = compile_candidate('FB_ClampPair',
        ['i_xEnable', 'i_xStart', 'i_xStop', 'i_xReset', 'i_xClampDone', 'i_xClampHome', 'i_xPushDone', 'i_xPushHome'],
        ['stat_nState', 'q_xClampValve', 'q_xPushValve', 'q_xBusy', 'q_xDone'])
    reset_b()
    stop_counterexample = {'input': {'i_xEnable': 1, 'i_xStart': 1, 'i_xStop': 1, 'i_xReset': 1},
                          'observed': b(i_xEnable=True, i_xStart=True, i_xStop=True, i_xReset=True),
                          'obligation': 'Stop must revoke actuation; no Start acceptance while Stop remains true'}
    reset_b()
    return_trace = [b(i_xEnable=True, i_xStart=True),
                    b(i_xEnable=True, i_xClampDone=True),
                    b(i_xEnable=True, i_xClampDone=True, i_xPushDone=True),
                    b(i_xEnable=True)]
    report = {'scope': 'normalized generated SCL -> matiec C -> native persistent FB calls; not TIA/PLCSIM',
              'normalization': ['remove quoted FB declaration, Siemens attributes/version and BEGIN',
                                'fold declared literal INT constants for matiec CASE label support',
                                'remove local # prefix and // comments; no Boolean/control-flow edits'],
              'source_sha256': {'A': a_hash, 'B': b_hash}, 'A': checks,
              'B_stop_counterexample': stop_counterexample,
              'B_return_without_home_trace': return_trace,
              'B_return_obligation': 'Both Home inputs remain false at the final call; leaving Done sensors does not establish Home',
              'candidate_verdict': {
                  'A': 'selected checks matched; not full acceptance' if all(x['matches'] for x in checks) else 'fail: selected check mismatch',
                  'B': 'fail: captured scan violation' if stop_counterexample['observed']['q_xClampValve'] or return_trace[-1]['q_xDone'] else 'no captured violation; not full acceptance'},
              'instrumentation_accepted': all(x['matches'] for x in checks) and
                  stop_counterexample['observed']['q_xClampValve'] == 1 and return_trace[-1]['q_xDone'] == 1}
    (OUT / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['instrumentation_accepted'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
