"""Replay known failures in recorded ZCode delivery. Exit 0 reproduces the
negative fixtures; it does not accept either candidate. No Siemens acceptance.
"""
import argparse,ctypes,hashlib,json,re,subprocess
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-dir',type=Path,default=Path(__file__).parent/'unlimited/zcode')
parser.add_argument('--work-dir',type=Path,required=True)
parser.add_argument('--iec2c',type=Path,required=True)
parser.add_argument('--matiec-lib',type=Path,required=True)
args=parser.parse_args()
TASK=args.source_dir.resolve(); OUT=args.work_dir.resolve()
COMPILER=args.iec2c.resolve(); LIBRARY=args.matiec_lib.resolve()
if OUT.is_relative_to(Path(__file__).resolve().parents[3]):
    parser.error('--work-dir must be outside the repository')
OUT.mkdir(parents=True,exist_ok=True)
def compile_candidate(name, inputs, outputs):
    original = (TASK / (name + '.scl')).read_text()
    source = re.sub(r'FUNCTION_BLOCK "([A-Za-z_][A-Za-z0-9_]*)"', r'FUNCTION_BLOCK \1', original)
    source = re.sub(r'(?m)^\{[^\n]*\}\s*$', '', source)
    source = re.sub(r'(?m)^VERSION\s*:[^\n]*$', '', source)
    source = re.sub(r'(?m)^TITLE\s*=[^\n]*$', '', source)
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
        result = subprocess.run(args, capture_output=True, text=True, timeout=None)
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

reset,scan,source_hash=compile_candidate('FB_ConveyorPack',['Enable','Start','Stop','Reset','AtEnd'],['Motor','Busy','Done','Error','TimeoutFault'])
checks=[]
def check(name,actual,expected):
 checks.append({'case':name,'observed':actual,'expected':expected,'matches':all(actual[k]==v for k,v in expected.items())})
reset();check('startup scan',scan(Enable=True,Start=True),{'Motor':1,'Busy':1,'Done':0,'Error':0})
for i in range(1,8):check(f'wait {i}, Enable withdrawn',scan(),{'Motor':1,'Busy':1,'Done':0,'Error':0})
check('wait 8 timeout',scan(),{'Motor':0,'Busy':0,'Done':0,'Error':1,'TimeoutFault':1})
check('fault Stop plus Reset',scan(Enable=True,Stop=True,Reset=True),{'Motor':0,'Error':1,'TimeoutFault':1})
check('held Reset after Stop release',scan(Enable=True,Reset=True),{'Error':1,'TimeoutFault':1})
scan(Enable=True)
check('fresh Reset plus Start clears without restart',scan(Enable=True,Reset=True,Start=True),{'Motor':0,'Busy':0,'Error':0,'TimeoutFault':0})
reset();scan(Enable=True,Start=True)
for _ in range(7):scan()
check('AtEnd at deadline',scan(AtEnd=True),{'Motor':0,'Busy':0,'Done':1,'Error':0,'TimeoutFault':0})
check('next scan Done cleared',scan(),{'Done':0,'Motor':0,'Busy':0})
reset();check('Idle Reset plus Start',scan(Enable=True,Reset=True,Start=True),{'Motor':0,'Busy':0})
reset();scan(Enable=True,Stop=True,Start=True)
check('held Start after Stop release',scan(Enable=True,Start=True),{'Motor':0,'Busy':0})
a_report={'source_sha256':source_hash,'scope':'normalized generated SCL compiled by matiec/GCC and persistent FB calls; no Boolean/control-flow modifications; not TIA/PLCSIM','checks':checks,'verdict':'fail' if any(not c['matches'] for c in checks) else 'selected checks matched'}

reset,scan,sha=compile_candidate('FB_ClampPair',['xEnable','xStart','xReset','xClampHome','xClampClamped','xAdvHome','xAdvAdvanced'],['eState','xQClampClose','xQClampOpen','xQAdvFwd','xQAdvBack','xFault','xCycleDone'])
reset();initial=scan(xEnable=True,xStart=True,xClampHome=True,xAdvHome=True)
stopped=scan(xEnable=False,xClampClamped=True)
reset();trace=[scan(xEnable=True,xStart=True,xClampHome=True,xAdvHome=True),scan(xEnable=True,xClampClamped=True),scan(xEnable=True,xAdvAdvanced=True),scan(xEnable=True)]
b_report={'source_sha256':sha,'scope':'normalized ST -> matiec/GCC persistent FB; constant time, no timer acceptance; not TIA/PLCSIM','stop_as_chosen_by_model':{'input':'xEnable=FALSE, xClampClamped=TRUE after accepted start','model_claim':'xEnable FALSE freezes step advancement','before':initial,'after':stopped,'matches_model_claim':stopped['eState']==initial['eState']},'return_without_home_trace':trace,'no_Done_without_home_matches':trace[-1]['xCycleDone']==0,'verdict':'fail: B04 invented mechanical/stop assumptions; also advances during its own chosen stop'}

report={'scope':'recorded unaccepted ZCode artifacts; normalized ST/matiec/GCC, not TIA/PLCSIM',
        'A':a_report,'B':b_report,
        'instrumentation_accepted':{c['case'] for c in a_report['checks'] if not c['matches']}=={'startup scan','AtEnd at deadline','next scan Done cleared'} and
            not b_report['stop_as_chosen_by_model']['matches_model_claim'] and b_report['no_Done_without_home_matches']}
(OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'A_verdict':a_report['verdict'],'B_verdict':b_report['verdict'],'known_failures_reproduced':report['instrumentation_accepted']}))
raise SystemExit(0 if report['instrumentation_accepted'] else 1)
