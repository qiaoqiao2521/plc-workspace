#!/usr/bin/env python3
"""JSON CLI for pinned OIP catalog, assembly, self-tests and actual native-PLC/plant tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys

from assemble import assemble
from common import HERE, base_report, checkout_path, execute, project_identity, verify_checkout


class IntegrationTerminated(BaseException):
    """Unwind every native/plant finally block before reporting interrupted work."""


def _terminate(signum, _frame):
    raise IntegrationTerminated(f"Integration interrupted by signal {signum}; no new verdict is available")


def normalize_tests(result, identity, project):
    report = base_report("oip-upstream-tests", "OIP's own example and embedded PLC; not plc-workspace native-source acceptance")
    report.update({"identity": identity, "project": str(project), "project_identity": project_identity(project),
                   "exit_code": result.returncode, "stderr": result.stderr.strip()[-4000:]})
    try:
        upstream = json.loads(result.stdout)
    except json.JSONDecodeError:
        no_tests = result.returncode == 0 and result.stdout.strip().startswith("no tests found in ")
        report.update({"status": "not_run" if no_tests else "error", "reason": "no_tests" if no_tests else "invalid_json",
                       "stdout": result.stdout.strip()[-4000:], "counts": {"tests": 0, "checks": 0}})
        return report
    tests = upstream.get("tests") if isinstance(upstream, dict) else None
    if not isinstance(tests, list):
        report.update({"status": "error", "reason": "invalid_test_report", "upstream": upstream,
                       "counts": {"tests": 0, "checks": 0}})
        return report
    if not tests:
        absent = result.returncode == 0 and upstream.get("ok") is True
        report.update({"status": "not_run" if absent else "error", "reason": "no_tests" if absent else "upstream_error",
                       "upstream": upstream, "counts": {"tests": 0, "checks": 0}})
        return report
    runnable = all(isinstance(t, dict) and "error" not in t
                   and isinstance(t.get("checks"), list)
                   and all(isinstance(c, dict) for c in t["checks"]) for t in tests)
    checks = [c for t in tests for c in t.get("checks", [])] if runnable else []
    counts = {"tests": len(tests), "checks": len(checks),
              "failed_checks": sum(c.get("ok") is not True for c in checks)}
    # Neither zero tests nor a zero-assertion test can become verification success.
    if not runnable or result.returncode not in (0, 1):
        status = "error"
    elif not checks or any(not t.get("checks") for t in tests):
        status = "not_run"
    else:
        status = "passed" if result.returncode == 0 and upstream.get("ok") is True and all(
            t.get("ok") is True for t in tests) and counts["failed_checks"] == 0 else "failed"
    report.update({"status": status, "counts": counts, "upstream": upstream})
    if status == "not_run":
        report["reason"] = "no_assertions"
    return report


def upstream_tests(checkout: Path, project: Path | None = None):
    identity = verify_checkout(checkout)
    project = project or checkout / "examples/projects/start-stop-motor"
    before = project_identity(project)
    result = execute(["node", "scripts/test-project.mjs", str(project), "--jobs", "1", "--json"], cwd=checkout)
    report = normalize_tests(result, identity, project)
    if project_identity(project) != before:
        report.update({"status": "error", "reason": "project_changed_during_test"})
    return report


def catalog(checkout: Path, parts: list[str]):
    identity = verify_checkout(checkout)
    if any(not p or p.startswith("-") or "/" in p for p in parts):
        raise ValueError("Catalog takes part identifiers, not options or paths")
    result = execute(["node", "scripts/catalog.mjs", "--json", *parts], cwd=checkout)
    data = json.loads(result.stdout)
    report = base_report("oip-catalog", "Queryable original OIP part catalog and typed parameter/signal declarations")
    report.update({"status": "passed" if result.returncode == 0 and data.get("parts") and not data.get("failures") else "failed",
                   "identity": identity, "exit_code": result.returncode, "catalog": data,
                   "counts": {"parts": len(data.get("parts", []))}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path)
    parser.add_argument("--save", type=Path, help="Save the exact JSON result to this explicit output file")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("doctor")
    cat = actions.add_parser("catalog")
    cat.add_argument("parts", nargs="*")
    tests = actions.add_parser("upstream-tests")
    tests.add_argument("--project", type=Path)
    build = actions.add_parser("assemble")
    build.add_argument("--output", type=Path, required=True)
    bundle = actions.add_parser("export")
    bundle.add_argument("--output", type=Path, required=True)
    bundle.add_argument("--project", type=Path)
    bundle.add_argument("--program-json", type=Path)
    bundle.add_argument("--report", type=Path, help="Optional native report; all source/scene identities must match")
    native = actions.add_parser("native-test")
    native.add_argument("--iec2c", type=Path, required=True)
    native.add_argument("--matiec-lib", type=Path, required=True)
    native.add_argument("--project", type=Path)
    native.add_argument("--program-json", type=Path, help="Frozen program object from the current engineering request")
    native.add_argument("--source", type=Path, help="Explicit local SCL/ST to freeze; requires --profile")
    native.add_argument("--profile", choices=["conveyor-8-demo-v1", "conveyor-12-v1"])
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _terminate)
    checkout = checkout_path(args.checkout)
    try:
        if args.action == "doctor":
            report = {**base_report("oip-installation", "Pinned OIP installation identity, not program verification"),
                      "status": "passed", "identity": verify_checkout(checkout)}
        elif args.action == "catalog":
            report = catalog(checkout, args.parts)
        elif args.action == "upstream-tests":
            report = upstream_tests(checkout, args.project)
        elif args.action == "assemble":
            report = {**base_report("oip-assembly", "Atomic scene assembly"), **assemble(checkout, args.output)}
        elif args.action == "export":
            from export import export_bundle
            program = json.loads(args.program_json.read_text()) if args.program_json else None
            evidence = json.loads(args.report.read_text()) if args.report else None
            report = export_bundle(checkout, args.output, project=args.project, program=program, report=evidence)
        else:
            from native_bridge import run_native
            if args.program_json and (args.source or args.profile):
                raise ValueError("Use --program-json or --source with --profile, not both")
            if bool(args.source) != bool(args.profile):
                raise ValueError("--source and --profile must be provided together")
            program = json.loads(args.program_json.read_text()) if args.program_json else (
                {"profile": args.profile, "source": args.source.read_text(), "filename": args.source.name}
                if args.source else None)
            report = run_native(checkout, args.iec2c.resolve(), args.matiec_lib.resolve(), project=args.project,
                                program=program)
    except (IntegrationTerminated, FileNotFoundError, ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        report = {**base_report(args.action, "Requested OIP integration check"),
                  "status": "unavailable" if isinstance(exc, FileNotFoundError) else "error", "reason": str(exc)}
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(rendered)
    sys.stdout.write(rendered)
    return 0 if report["status"] == "passed" else 1 if report["status"] == "failed" else 2


if __name__ == "__main__":
    sys.exit(main())
