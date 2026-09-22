#!/usr/bin/env python3
"""Verify the generated semantic core; fail/unknown never return success."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


def verdict(output: str, exit_code: int) -> str:
    results = re.findall(r"\*\*Result: the requirement is (SATISFIED|VIOLATED|UNKNOWN)\*\*", output)
    if "VIOLATED" in results:
        return "fail"
    if exit_code != 0 or results != ["SATISFIED"]:
        return "unknown"
    return "pass"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--plcverif-cli", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--java", default="java")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    root = Path(__file__).resolve().parent
    check = subprocess.run([sys.executable, str(root / "sync-semantics.py"),
                            "--project", str(args.project), "--check"],
                           capture_output=True, text=True, timeout=30)
    if check.returncode:
        print(check.stdout + check.stderr, file=sys.stderr)
        return 2
    launchers = list((args.plcverif_cli / "plugins").glob("org.eclipse.equinox.launcher_*.jar"))
    if len(launchers) != 1 or not args.backend.is_file():
        print("BLOCKED: a unique PLCverif launcher and native backend are required", file=sys.stderr)
        return 2
    run = args.work_dir.resolve() / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run.mkdir(parents=True, exist_ok=False)
    checkdir = args.project / "03_checks/plcverif"
    source = checkdir / "FB_MainSequence_PLCverif.scl"
    case = checkdir / "FB_MainSequence-assert-nusmv.vc3"
    for path in (source, case):
        shutil.copy2(path, run / path.name)
    command = [args.java, "-jar", str(launchers[0].resolve()), "-nosplash", "-consoleLog",
               "-data", str(run / "workspace"), "-application", "cern.plcverif.cli.cmdline.app.application",
               case.name, "-job.backend.binary_path", str(args.backend.resolve()),
               "-job.backend.algorithm", "Classic", "-job.backend.dynamic", "true",
               "-job.backend.df", "true", "-job.backend.req_as_invar", "false",
               "-job.backend.timeout", str(args.timeout)]
    try:
        completed = subprocess.run(command, cwd=run, capture_output=True, text=True,
                                   timeout=args.timeout + 20)
        output = completed.stdout + completed.stderr
        code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"") + (exc.stderr or b"")
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        output += "\nOUTER PROCESS TIMEOUT\n"
        code = -1
    (run / "run.log").write_text(output)
    result = verdict(output, code)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = {
        "result": result,
        "tool_exit": code,
        "parameter_domain": "all UINT timeout values, independently sampled on each scan",
        "algorithm": "Classic; dynamic reordering; CTL assertion requirement",
        "source_sha256": sha(run / source.name),
        "case_sha256": sha(run / case.name),
        "projection_manifest_sha256": sha(args.project / "00_meta/projection-manifest.json"),
        "assertion_count": len(re.findall(r"(?m)^\s*//#ASSERT ", source.read_text())),
        "run_dir": str(run),
        "siemens_final": "unverified",
    }
    (run / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return {"pass": 0, "fail": 1, "unknown": 2}[result]


if __name__ == "__main__":
    raise SystemExit(main())
