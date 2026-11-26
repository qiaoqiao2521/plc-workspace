#!/usr/bin/env python3
"""Linux process-lifecycle test; interrupt a genuinely loaded, looping native FB."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

from common import HERE, ROOT, base_report, checkout_path


def process_row(pid):
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rpartition(")")[2].split()
        return {"pid": int(pid), "ppid": int(fields[1]), "pgid": int(fields[2]),
                "ticks": int(fields[11]) + int(fields[12]), "started": fields[19]}
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def direct_children(parent):
    rows = [process_row(path.name) for path in Path("/proc").iterdir() if path.name.isdigit()]
    return [row for row in rows if row and row["ppid"] == parent]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--iec2c", type=Path, required=True)
    parser.add_argument("--matiec-lib", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--save", type=Path)
    args = parser.parse_args()
    source_path = ROOT / "web/data/simulation/conveyor-12.scl"
    original = source_path.read_text()
    source, count = re.subn(r"(?im)^\s*END_FUNCTION_BLOCK\s*$",
                           "WHILE TRUE DO Motor := Motor; END_WHILE;\nEND_FUNCTION_BLOCK", original)
    if count != 1:
        raise RuntimeError("Expected one fixture FB terminator")
    report = base_report("termination-cleanup", "Process lifecycle only, with an explicitly synthetic looping controller")
    with tempfile.TemporaryDirectory(prefix="plc-oip-terminate-") as tmp:
        program = Path(tmp) / "program.json"
        program.write_text(json.dumps({"profile": "conveyor-12-v1", "source": source,
                                       "filename": "synthetic-looping-controller.scl"}))
        process = subprocess.Popen([
            sys.executable, str(HERE / "run.py"), "--checkout", str(checkout_path(args.checkout)),
            "native-test", "--iec2c", str(args.iec2c.resolve()), "--matiec-lib", str(args.matiec_lib.resolve()),
            "--project", str(args.project.resolve()), "--program-json", str(program),
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        tracked = []
        worker = None
        try:
            deadline = time.monotonic() + 20
            while process.poll() is None and time.monotonic() < deadline:
                for row in direct_children(process.pid):
                    try:
                        maps = (Path("/proc") / str(row["pid"]) / "maps").read_text()
                    except (FileNotFoundError, ProcessLookupError):
                        continue
                    if "/normal-arrival/runtime.so" in maps:
                        time.sleep(0.1)
                        later = process_row(row["pid"])
                        if later and later["ticks"] > row["ticks"]:
                            worker = later
                            break
                if worker:
                    break
                time.sleep(0.05)
            if not worker:
                detail = ""
                if process.poll() is not None:
                    stdout, stderr = process.communicate()
                    detail = (stdout + stderr)[-6000:]
                raise RuntimeError("Did not observe a loaded, active native runtime before termination: " + detail)
            tracked = direct_children(process.pid)
            if worker["pgid"] == process.pid:
                raise RuntimeError("Native worker was not isolated in its own process group")
            started = time.monotonic()
            os.killpg(process.pid, signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=3)
            elapsed = time.monotonic() - started
            remaining = [row["pid"] for row in tracked if (
                (actual := process_row(row["pid"])) and actual["started"] == row["started"])]
            result = json.loads(stdout)
            passed = process.returncode == 2 and result["status"] == "error" and not remaining
            if source_path.read_text() != original:
                raise RuntimeError("Original fixture source changed")
            report.update({"status": "passed" if passed else "failed", "signal": "SIGTERM",
                           "loaded_native_worker_observed": True, "native_worker_separate_process_group": True,
                           "children_before_signal": tracked, "remaining_children": remaining,
                           "adapter_exit_code": process.returncode, "adapter_result": result,
                           "cleanup_seconds": round(elapsed, 3), "stderr": stderr[-2000:]})
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
            for row in tracked:
                actual = process_row(row["pid"])
                if actual and actual["started"] == row["started"]:
                    os.kill(row["pid"], signal.SIGKILL)
    text = json.dumps(report, indent=2) + "\n"
    if args.save:
        args.save.write_text(text)
    print(text, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
