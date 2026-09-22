#!/usr/bin/env python3
"""Run the complete generated OpenPLC test program natively, not its service."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


DRIVER = r'''
#include <stdio.h>
#include "POUS.h"
#define __LOCATED_VAR(type, name, ...) IEC_##type storage_##name; IEC_##type *name = &storage_##name;
#include "LOCATED_VARIABLES.h"
#undef __LOCATED_VAR
TIME __CURRENT_TIME;
#include "POUS.c"
int main(void) {
    PLC_PRG instance = {0};
    PLC_PRG_init__(&instance, 0);
    for (int n = 1; n <= 801; n++) {
        PLC_PRG_body__(&instance);
        if (*__QX0_7) { printf("FAIL at call %d\n", n); return 1; }
        if (*__QX0_6) {
            printf("PASS at call %d; phase=%d; scenario=%d; cycles=%d\n",
                   n, *__MW0, *__MW4, *__MW1);
            return 0;
        }
    }
    puts("UNKNOWN: no driver verdict within 801 calls");
    return 2;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--iec2c", type=Path, required=True)
    parser.add_argument("--matiec-lib", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = (args.project / "03_checks/openplc/FB_MainSequence_OpenPLC.st").resolve()
    (work / "run.c").write_text(DRIVER)
    commands = [
        ("iec2c", [str(args.iec2c.resolve()), "-I", str(args.matiec_lib.resolve()),
                   "-T", str(work), str(source)]),
        ("cc", [args.cc, "-std=gnu11", "-I", str(args.matiec_lib.resolve() / "C"),
                "-I", str(work), str(work / "run.c"), "-lm", "-o", str(work / "run")]),
        ("run", [str(work / "run")]),
    ]
    for name, command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"UNKNOWN: {name}: {exc}")
            return 2
        log = result.stdout + result.stderr
        (work / f"{name}.log").write_text(log)
        if name != "run" and result.returncode:
            print(f"UNKNOWN: {name} failed; see {work / (name + '.log')}")
            return 2
    passed = result.returncode == 0 and log.startswith("PASS at call ")
    verdict = "pass" if passed else ("fail" if result.returncode == 1 else "unknown")
    report = {"result": verdict, "detail": log.strip(),
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "scope": "native complete test program; no OpenPLC service or Siemens acceptance"}
    (work / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return {"pass": 0, "fail": 1, "unknown": 2}[verdict]


if __name__ == "__main__":
    raise SystemExit(main())
