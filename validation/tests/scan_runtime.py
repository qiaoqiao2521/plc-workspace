"""Compile actual ST with matiec and call one persistent FB instance per scan."""
from __future__ import annotations

import ctypes
from pathlib import Path
import re
import subprocess

INPUTS = ("enable", "start", "estop", "stop", "reset", "init_done",
          "transport_done", "flip_done", "output_done")
OUTPUTS = ("phase", "timer", "error", "timeout_fault", "belt_forward",
           "belt_reverse", "start_lamp", "reset_lamp", "q1", "q2", "done", "valid", "busy", "command_busy",
           "command_aborted", "timeout_diagnostic")
C_INPUTS = ("XENABLE", "XEVTSTART", "XESTOP", "XSTOP", "XRESET", "XINITDONE",
            "XTRANSPORTDONE", "XFLIPDONE", "XOUTPUTDONE")
C_OUTPUTS = ("IPHASE", "UISTEPTIMERSTAT", "XERROR", "XTIMEOUTFAULT", "XBELTFORWARD",
             "XBELTREVERSE", "XSTARTLAMP", "XRESETLAMP", "XQ1", "XQ2", "XDONE",
             "XVALID", "XBUSY", "XCOMMANDBUSY", "XCOMMANDABORTED", "XTIMEOUTDIAGNOSTIC")


def compile_runtime(source: str, folder: Path, iec2c: Path, library: Path, cc: str):
    folder.mkdir(parents=True, exist_ok=True)
    # Formal checker syntax adapter only; assertions are ST comments.
    source = re.sub(r"(?m)^BEGIN\s*$", "", source)
    source = re.sub(r"(?m)^\s*//[^\n]*$", "", source)
    source += """
PROGRAM AuditProgram
VAR
    instance : FB_MainSequence;
END_VAR
instance();
END_PROGRAM
CONFIGURATION AuditConfig
RESOURCE R ON PLC
TASK Main(INTERVAL := T#50ms, PRIORITY := 0);
PROGRAM P WITH Main : AuditProgram;
END_RESOURCE
END_CONFIGURATION
"""
    (folder / "input.st").write_text(source)
    assigns = "\n".join(f"b.{name}.value = (flags >> {i}) & 1;"
                        for i, name in enumerate(C_INPUTS))
    outputs = "\n".join(f"out[{i}] = b.{name}.value;" for i, name in enumerate(C_OUTPUTS))
    (folder / "driver.c").write_text(f"""
#include <stdint.h>
#include "POUS.h"
TIME __CURRENT_TIME;
#include "POUS.c"
static FB_MAINSEQUENCE b;
void reset_instance(void) {{ b = (FB_MAINSEQUENCE){{0}}; FB_MAINSEQUENCE_init__(&b, 0); }}
void inject_state(int phase, unsigned timer, int timeout_fault) {{
    b.IPHASESTAT.value = phase; b.UISTEPTIMERSTAT.value = timer;
    b.XTIMEOUTFAULTSTAT.value = timeout_fault;
    b.XTIMEOUTDIAGNOSTICSTAT.value = timeout_fault;
}}
void poison_outputs(void) {{
    b.XTIMEOUTFAULT.value = 1; b.XERROR.value = 1; b.IPHASE.value = 900;
}}
void scan(unsigned flags, unsigned timeout, int32_t *out) {{
    {assigns}
    b.UISTEPTIMEOUTSCANS.value = timeout;
    FB_MAINSEQUENCE_body__(&b);
    {outputs}
}}
""")
    for name, command in [
        ("iec2c", [str(iec2c), "-I", str(library), "-T", str(folder), str(folder / "input.st")]),
        ("cc", [cc, "-shared", "-fPIC", "-std=gnu11", "-I", str(library / "C"),
                "-I", str(folder), str(folder / "driver.c"), "-lm", "-o", str(folder / "runtime.so")]),
    ]:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (folder / f"{name}.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"{name} failed ({result.returncode}); see {folder / (name + '.log')}")
    return Runtime(folder / "runtime.so")


class Runtime:
    def __init__(self, binary: Path):
        self.lib = ctypes.CDLL(str(binary))
        self.lib.reset_instance.argtypes = []
        self.lib.reset_instance.restype = None
        self.lib.inject_state.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_int]
        self.lib.inject_state.restype = None
        self.lib.poison_outputs.argtypes = []
        self.lib.poison_outputs.restype = None
        self.lib.scan.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_int32)]
        self.lib.scan.restype = None
        self.reset()

    def reset(self):
        self.lib.reset_instance()

    def inject(self, phase: int, timer: int = 0, timeout_fault: bool = False):
        """Test-only fault/state injection; not an application interface."""
        self.lib.inject_state(phase, timer, timeout_fault)

    def scan(self, timeout: int = 8, **inputs) -> dict[str, int]:
        if not 0 <= timeout <= 65535:
            raise ValueError("timeout must fit UINT")
        unknown = set(inputs) - set(INPUTS)
        if unknown:
            raise ValueError(f"unknown inputs: {unknown}")
        flags = sum(bool(inputs.get(name, False)) << i for i, name in enumerate(INPUTS))
        result = (ctypes.c_int32 * len(OUTPUTS))()
        self.lib.scan(flags, timeout, result)
        return dict(zip(OUTPUTS, result))
