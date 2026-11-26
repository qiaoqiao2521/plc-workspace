"""Actual matiec FB calls drive the pinned OIP physical plant through JSON lines."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time

from assemble import RECIPE_PATH, assemble
from common import HERE, ROOT, base_report, project_identity, sha256, verify_checkout


class OipPlant:
    """One cloud process/one physics world. No network sockets or hardware I/O."""
    def __init__(self, checkout: Path, project: Path):
        self.identity = verify_checkout(checkout)
        self.project_identity = project_identity(project)
        self.errors = tempfile.TemporaryFile(mode="w+t")
        self.process = subprocess.Popen(
            ["node", str(HERE / "bridge.mjs"), str(checkout), str(project)],
            cwd=checkout, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors,
            text=True, bufsize=1,
        )
        self.lines = queue.Queue()
        def read_output():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)
        self.reader = threading.Thread(target=read_output, daemon=True)
        self.reader.start()
        try:
            hello = self._read()
            if not hello.get("ready") or hello.get("native_plc_attached") is not False:
                raise RuntimeError("Unexpected OIP bridge greeting")
            self.state = hello["state"]
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            line = self.lines.get(timeout=60)
        except queue.Empty as exc:
            raise RuntimeError("OIP bridge timed out; no PLC verdict is available") from exc
        if line is None:
            self.errors.seek(0)
            raise RuntimeError("OIP bridge exited: " + self.errors.read()[-3000:])
        result = json.loads(line)
        if result.get("ok") is not True:
            raise RuntimeError(result.get("error", "OIP bridge refused the operation"))
        return result

    def request(self, body):
        self.process.stdin.write(json.dumps(body) + "\n")
        self.process.stdin.flush()
        result = self._read()
        if "state" in result:
            self.state = result["state"]
        return result

    def reset(self):
        return self.request({"op": "reset"})["state"]

    def step(self, motor: bool, *, jam: bool = False, steps: int = 15):
        return self.request({"op": "step", "motor": motor, "jam": jam, "steps": steps})["state"]

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdout.close()
        self.errors.close()


def _load_core():
    spec = importlib.util.spec_from_file_location("plc_oip_simulation_core", ROOT / "web/scripts/simulation-core.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _negative_program(program, normalized):
    """A separate, explicitly wrong controller, using the exact same normal-run oracle."""
    replacements = 0
    def mutate(match):
        nonlocal replacements
        token = match.group()
        if token.upper() == "END_FUNCTION_BLOCK":
            replacements += 1
            return "Done := FALSE; (* synthetic negative control only *)\nEND_FUNCTION_BLOCK"
        return token
    mutated = re.sub(r"'(?:(?:'')|[^'])*'|\(\*.*?\*\)|\bEND_FUNCTION_BLOCK\b", mutate,
                     normalized, flags=re.I | re.S)
    if replacements != 1:
        raise ValueError("Negative-control anchor changed; expected one executable END_FUNCTION_BLOCK")
    return {**program, "source": mutated, "filename": "synthetic-suppress-done.st"}


def run_native(checkout: Path, compiler: Path, library: Path, *, project: Path | None = None,
               program: dict | None = None) -> dict:
    """Frozen original source in a watchdog worker drives the real OIP/Jolt plant.

    The profile chooses an independent 8- or 12-call oracle. It never changes the
    controller's waiting threshold. A synthetic mutation is compiled separately.
    """
    started = time.monotonic()
    report = base_report("native-oip-loop", "Frozen FB_ConveyorPack source compiled by matiec/GCC driving OIP/Jolt plant")
    identity = verify_checkout(checkout)
    recipe = json.loads(RECIPE_PATH.read_text())
    if recipe["physics_hz"] != 60 or recipe["scan_ms"] != 250:
        raise ValueError("Recipe clock changed; review this fixed adapter before running")
    source_path = None
    if program is None:
        source_path = ROOT / recipe["native_source"]
        program = {"profile": "conveyor-8-demo-v1", "source": source_path.read_text(),
                   "filename": source_path.name}
    # Copy the caller's object, so later edits cannot alter the evidence being run.
    program = json.loads(json.dumps(program, allow_nan=False))
    core = _load_core()
    profile, normalized = core.prepare_program(program)
    if profile["id"] not in {"conveyor-8-demo-v1", "conveyor-12-v1"}:
        raise ValueError("OIP conveyor plant supports only conveyor-8-demo-v1 and conveyor-12-v1")
    captured = program["source"].encode()
    waiting_calls = {"conveyor-8-demo-v1": 8, "conveyor-12-v1": 12}[profile["id"]]
    if profile["waiting_calls"] != waiting_calls:
        raise ValueError("Profile waiting contract changed; review OIP adapter before running")
    expected_timeout_scan = waiting_calls + 1
    mutant_program = _negative_program(program, normalized)
    core.prepare_program(mutant_program)
    with tempfile.TemporaryDirectory(prefix="plc-oip-native-") as tmp:
        work = Path(tmp)
        if project is None:
            project = work / "plant"
            assemble(checkout, project)
        original_project = project_identity(project)
        plant = OipPlant(checkout, project)
        def run_case(name, captured_program, *, jam=False, sensor_failed=False):
            state = plant.reset()
            trace = []
            plc = None
            result = {"name": name, "status": "error", "source_sha256": sha256(captured_program["source"].encode()),
                      "checks": [], "trace": trace}
            try:
                plc = core.NativeWorker(captured_program, str(compiler), str(library), work / name,
                                        scan_timeout=2.0)
                result["runtime_source_sha256"] = plc.metadata["runtime_source_sha256"]
                for scan in range(1, waiting_calls + 5):
                    raw = state["tags"].get("AtEnd")
                    if type(raw) is not bool:
                        raise RuntimeError("OIP sensor did not publish a BOOL AtEnd")
                    sampled = {"Enable": True, "Start": scan == 1, "Stop": False,
                               "Reset": False, "AtEnd": False if sensor_failed else raw}
                    outputs = plc.scan(sampled)
                    after = plant.step(bool(outputs["Motor"]), jam=jam, steps=15)
                    trace.append({"scan": scan, "time_ms": (scan - 1) * 250,
                                  "sampled_inputs": sampled, "native_outputs": outputs,
                                  "plant_before": state, "plant_after": after,
                                  "faults": {"jam": jam, "sensor_stuck_off": sensor_failed}})
                    state = after
            except (RuntimeError, OSError, ValueError) as exc:
                result["error"] = str(exc)
                result["compiler_logs"] = {p.name: p.read_text()[-4000:]
                                           for p in (work / name).glob("*.log")}
                return result
            finally:
                if plc is not None:
                    plc.close()
            checks = []
            def check(label, ok, observed):
                checks.append({"name": label, "ok": bool(ok), "observed": observed})
            check("start drives the real belt", trace[0]["native_outputs"]["Motor"] == 1
                  and trace[0]["plant_after"]["conveyor_speeds"].get("belt", 0) > 0,
                  trace[0]["plant_after"]["conveyor_speeds"])
            if jam or sensor_failed:
                first_error = next((row["scan"] for row in trace if row["native_outputs"]["Error"]), None)
                check(f"{waiting_calls} waiting calls expire on scan {expected_timeout_scan}",
                      first_error == expected_timeout_scan, first_error)
                check("timeout revokes Motor and stays latched", all(
                    row["native_outputs"]["Motor"] == 0 and row["native_outputs"]["Busy"] == 0
                    and row["native_outputs"]["Error"] == 1 and row["native_outputs"]["TimeoutFault"] == 1
                    for row in trace[waiting_calls:]), [row["native_outputs"] for row in trace[waiting_calls:]])
                if jam:
                    first_x = trace[0]["plant_before"]["cargo"][0]["position"][0]
                    last_x = trace[-1]["plant_after"]["cargo"][0]["position"][0]
                    check("physical jam acted on cargo", abs(last_x - first_x) < 0.001, {"first_x": first_x, "last_x": last_x})
                else:
                    check("raw sensor saw cargo but PLC input was stuck off", any(
                        row["plant_before"]["tags"]["AtEnd"] for row in trace)
                        and not any(row["sampled_inputs"]["AtEnd"] for row in trace),
                        [row["plant_before"]["tags"]["AtEnd"] for row in trace])
            else:
                done = [row["scan"] for row in trace if row["native_outputs"]["Done"]]
                check("arrival produces exactly one Done before timeout", len(done) == 1
                      and done[0] <= expected_timeout_scan, done)
                check("completion uses actual sampled sensor", any(
                    row["sampled_inputs"]["AtEnd"] and row["native_outputs"]["Done"] for row in trace),
                    [row["scan"] for row in trace if row["sampled_inputs"]["AtEnd"]])
                check("arrival revokes Motor and Busy on the completion call", len(done) == 1 and all(
                    not row["native_outputs"]["Motor"] and not row["native_outputs"]["Busy"]
                    and row["plant_after"]["conveyor_speeds"].get("belt") == 0
                    for row in trace if row["native_outputs"]["Done"]),
                    [row["native_outputs"] for row in trace if row["native_outputs"]["Done"]])
                check("normal run never latches an error", not any(row["native_outputs"]["Error"] for row in trace),
                      [row["native_outputs"]["Error"] for row in trace])
                check("cargo moved in physical world", trace[-1]["plant_after"]["cargo"][0]["position"][0]
                      > trace[0]["plant_before"]["cargo"][0]["position"][0] + 0.3,
                      trace[-1]["plant_after"]["cargo"][0]["position"])
            result.update({"status": "passed" if all(c["ok"] for c in checks) else "failed", "checks": checks})
            return result
        try:
            cases = [run_case("normal-arrival", program), run_case("physical-jam", program, jam=True),
                     run_case("sensor-stuck-off", program, sensor_failed=True)]
            negative = run_case("negative-control-suppress-done", mutant_program)
        finally:
            plant.close()
        if project_identity(project) != original_project or (source_path and source_path.read_bytes() != captured):
            raise RuntimeError("Source/project changed during execution; results cannot establish current identity")
        mutation_caught = negative["status"] == "failed" and any(
            not c["ok"] and c["name"] == "arrival produces exactly one Done before timeout" for c in negative["checks"])
        report.update({
            "status": "error" if any(c["status"] == "error" for c in [*cases, negative]) else
                      "passed" if all(c["status"] == "passed" for c in cases) and mutation_caught else "failed",
            "identity": identity, "native_source": recipe["native_source"] if source_path else "captured program.source",
            "profile": profile["id"], "program_identity": {k: v for k, v in program.items() if k != "source"},
            "source_sha256": sha256(captured), "adapted_source_sha256": sha256(normalized.encode()),
            "runtime_source_sha256": cases[0].get("runtime_source_sha256"),
            "recipe_sha256": sha256(RECIPE_PATH.read_bytes()), "project_identity": original_project,
            "scene_sha256": sha256((project / "scene.json").read_bytes()),
            "clock": {"physics_hz": 60, "scan_ms": 250, "physics_steps_per_scan": 15,
                      "startup_settle_steps_without_plc": 30, "timeout_unit": "FB calls, not milliseconds",
                      "waiting_calls": waiting_calls, "expected_timeout_scan": expected_timeout_scan},
            "tests": cases, "negative_control": {"kind": "synthetic source mutation: suppress Done after original FB body",
                                                  "detected": mutation_caught, "run": negative},
            "counts": {"tests": len(cases), "checks": sum(len(t["checks"]) for t in cases),
                       "failed_checks": sum(not c["ok"] for t in cases for c in t["checks"]),
                       "negative_controls": 1, "negative_controls_detected": int(mutation_caught)},
            "visual_render": "not_run", "oip_plc_execution": "not_used", "elapsed_seconds": round(time.monotonic() - started, 3),
        })
    return report
