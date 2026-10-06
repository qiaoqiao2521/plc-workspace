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

class NativeRuntime:
    """Compile a trusted, fixed FB interface; no user-supplied paths or identifiers."""
    def __init__(self, folder, compiler, library, *, source_bytes, block_name, inputs, outputs):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", block_name) or any(
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (*inputs, *outputs)):
            raise ValueError("Invalid fixed native interface")
        self.inputs, self.outputs = tuple(inputs), tuple(outputs)
        original = source_bytes
        if not isinstance(original, bytes):
            raise TypeError("Captured source must be immutable bytes")
        self.source_bytes = original
        self.source_hash = hashlib.sha256(original).hexdigest()
        source = original.decode()
        source = re.sub(r'FUNCTION_BLOCK "([A-Za-z_][A-Za-z0-9_]*)"', r'FUNCTION_BLOCK \1', source)
        source = re.sub(r'(?m)^\{[^\n]*\}\s*$', '', source)
        source = re.sub(r'(?m)^VERSION\s*:[^\n]*$', '', source)
        source = re.sub(r'(?m)^BEGIN\s*$', '', source)
        source = re.sub(r'#(?=[A-Za-z_])', '', source)
        source = re.sub(r'//[^\n]*', '', source)
        source += f'\nPROGRAM SimProgram\nVAR\nb : {block_name};\nEND_VAR\nb();\nEND_PROGRAM\nCONFIGURATION SimConfig\nRESOURCE R ON PLC\nTASK Main(INTERVAL := T#50ms, PRIORITY := 0);\nPROGRAM P WITH Main : SimProgram;\nEND_RESOURCE\nEND_CONFIGURATION\n'
        folder = Path(folder).resolve()
        if folder.is_relative_to(ROOT):
            raise ValueError('Build directory must be outside repository')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'input.st').write_text(source)
        self.normalized_hash = hashlib.sha256(source.encode()).hexdigest()
        assigns = '\n'.join(f'b->{n.upper()}.value = (flags >> {i}) & 1;' for i, n in enumerate(self.inputs))
        reads = '\n'.join(f'out[{i}] = b->{n.upper()}.value;' for i, n in enumerate(self.outputs))
        (folder / 'driver.c').write_text(f'''#include <stdint.h>
#include <stdlib.h>
#include "POUS.h"
TIME __CURRENT_TIME;
#include "POUS.c"
void *create_instance(void) {{
 {block_name.upper()} *b = calloc(1, sizeof(*b));
 if(b) {block_name.upper()}_init__(b, 0);
 return b;
}}
void destroy_instance(void *p) {{ free(p); }}
void scan(void *p, unsigned flags, int32_t *out) {{
 {block_name.upper()} *b = p;
 {assigns}
 {block_name.upper()}_body__(b);
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
        flags = sum(inputs.get(n, False) << i for i, n in enumerate(self.inputs))
        result = (ctypes.c_int32 * len(self.outputs))()
        self.lib.scan(handle, flags, result)
        return dict(zip(self.outputs, result))


class ConveyorRuntime(NativeRuntime):
    def __init__(self, folder, compiler, library, *, source_bytes=None):
        super().__init__(folder, compiler, library,
            source_bytes=SOURCE.read_bytes() if source_bytes is None else source_bytes,
            block_name='FB_ConveyorPack', inputs=INPUTS, outputs=OUTPUTS)
