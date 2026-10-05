"""Fixed recorded conveyor candidate -> matiec -> persistent native FB instances.

No arbitrary code upload. Adapt Siemens syntax only; never rewrite FB control flow.
"""
import ctypes
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'plans/plc-generation-ui/user-eval/candidates/FB_ConveyorPack.scl'
INPUTS = ('Enable', 'Start', 'Stop', 'Reset', 'AtEnd')
OUTPUTS = ('statState', 'statWaitCount', 'Motor', 'Busy', 'Done', 'Error', 'TimeoutFault')

class ConveyorRuntime:
    def __init__(self, folder, compiler, library):
        original = SOURCE.read_bytes()
        self.source_hash = hashlib.sha256(original).hexdigest()
        source = original.decode()
        source = re.sub(r'FUNCTION_BLOCK "([A-Za-z_][A-Za-z0-9_]*)"', r'FUNCTION_BLOCK \1', source)
        source = re.sub(r'(?m)^\{[^\n]*\}\s*$', '', source)
        source = re.sub(r'(?m)^VERSION\s*:[^\n]*$', '', source)
        source = re.sub(r'(?m)^BEGIN\s*$', '', source)
        source = re.sub(r'#(?=[A-Za-z_])', '', source)
        source = re.sub(r'//[^\n]*', '', source)
        source += '\nPROGRAM SimProgram\nVAR\nb : FB_ConveyorPack;\nEND_VAR\nb();\nEND_PROGRAM\nCONFIGURATION SimConfig\nRESOURCE R ON PLC\nTASK Main(INTERVAL := T#50ms, PRIORITY := 0);\nPROGRAM P WITH Main : SimProgram;\nEND_RESOURCE\nEND_CONFIGURATION\n'
        folder = Path(folder).resolve()
        if folder.is_relative_to(ROOT):
            raise ValueError('Build directory must be outside repository')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'input.st').write_text(source)
        self.normalized_hash = hashlib.sha256(source.encode()).hexdigest()
        assigns = '\n'.join(f'b->{n.upper()}.value = (flags >> {i}) & 1;' for i, n in enumerate(INPUTS))
        reads = '\n'.join(f'out[{i}] = b->{n.upper()}.value;' for i, n in enumerate(OUTPUTS))
        (folder / 'driver.c').write_text(f'''#include <stdint.h>
#include <stdlib.h>
#include "POUS.h"
TIME __CURRENT_TIME;
#include "POUS.c"
void *create_instance(void) {{
 FB_CONVEYORPACK *b = calloc(1, sizeof(*b));
 if(b) FB_CONVEYORPACK_init__(b, 0);
 return b;
}}
void destroy_instance(void *p) {{ free(p); }}
void scan(void *p, unsigned flags, int32_t *out) {{
 FB_CONVEYORPACK *b = p;
 {assigns}
 FB_CONVEYORPACK_body__(b);
 {reads}
}}
''')
        for label, command in [
            ('iec2c', [str(compiler), '-I', str(library), '-T', str(folder), str(folder / 'input.st')]),
            ('gcc', ['gcc', '-shared', '-fPIC', '-std=gnu11', '-I', str(Path(library) / 'C'), '-I', str(folder), str(folder / 'driver.c'), '-lm', '-o', str(folder / 'runtime.so')])]:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
            (folder / f'{label}.log').write_text(result.stdout + result.stderr)
            if result.returncode:
                raise RuntimeError(f'{label} failed; see {folder / (label + ".log")}')
        self.lib = ctypes.CDLL(str(folder / 'runtime.so'))
        self.lib.create_instance.argtypes = []
        self.lib.create_instance.restype = ctypes.c_void_p
        self.lib.destroy_instance.argtypes = [ctypes.c_void_p]
        self.lib.destroy_instance.restype = None
        self.lib.scan.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int32)]
        self.lib.scan.restype = None

    def create(self):
        handle = self.lib.create_instance()
        if not handle:
            raise MemoryError('Native instance allocation failed')
        return handle

    def destroy(self, handle):
        self.lib.destroy_instance(handle)

    def scan(self, handle, inputs):
        flags = sum(inputs.get(n, False) << i for i, n in enumerate(INPUTS))
        result = (ctypes.c_int32 * len(OUTPUTS))()
        self.lib.scan(handle, flags, result)
        return dict(zip(OUTPUTS, result))
