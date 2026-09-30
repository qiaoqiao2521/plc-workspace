#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

import plcrex
import plcrex.tools.stp.st_parser as st_parser_module
from plcrex.tools.stp.st_parser import STParser


def _portable_get_file(rel_path: str) -> str:
    normalized = rel_path.replace("\\", os.sep).replace("/", os.sep)
    prefix = f"plcrex{os.sep}"
    if normalized.startswith(prefix):
        normalized = normalized[len(prefix):]
    package_root = Path(plcrex.__file__).resolve().parent
    candidate = package_root / normalized
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    fallback = Path(normalized)
    if fallback.is_file():
        return fallback.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Unable to locate PLCreX resource: {rel_path}")


st_parser_module.get_file = _portable_get_file


def run_st_parser(source: Path, export: Path, txt: bool = True, dot: bool = True, beckhoff: bool = False) -> int:
    out_dir = export.parent / "PLCreX_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    STParser(source, out_dir, export.stem, txt, dot, beckhoff).translate()
    print(f"Wrote parser outputs to {out_dir}")
    return 0


def run_iec_check(source: Path, exe: Path, export: Path, verbose: bool = False, help_flag: bool = False) -> int:
    out_dir = export.parent / "PLCreX_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"{export.stem}.log"
    option = "--help" if help_flag else "--verbose" if verbose else "--quiet"
    with open(log_path, "w", encoding="utf-8") as stream:
        completed = subprocess.run([str(exe), str(source), option], stdout=stream, stderr=subprocess.STDOUT, check=False)
    output = log_path.read_text(encoding="utf-8", errors="replace")
    if completed.returncode != 0 and not output.strip():
        output = (
            f"iec-checker exited with code {completed.returncode} and produced no output.\n"
            f"command: {exe} {source} {option}\n"
            "This preserves the real tool result; it is not treated as a pass."
        )
        log_path.write_text(output, encoding="utf-8")
    print(output)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["st-parser", "iec-check"])
    parser.add_argument("args", nargs="+")
    ns = parser.parse_args()

    if ns.command == "st-parser":
        if len(ns.args) != 2:
            raise SystemExit("st-parser requires: <source> <export>")
        return run_st_parser(Path(ns.args[0]), Path(ns.args[1]))

    if len(ns.args) != 3:
        raise SystemExit("iec-check requires: <source> <exe> <export>")
    return run_iec_check(Path(ns.args[0]), Path(ns.args[1]), Path(ns.args[2]))


if __name__ == "__main__":
    sys.exit(main())
