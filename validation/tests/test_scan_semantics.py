#!/usr/bin/env python3
"""Executable requirements for scan boundaries, using compiled canonical ST."""
from __future__ import annotations

import argparse
import json
import itertools
import re
from pathlib import Path
import random
import sys
import unittest

from scan_runtime import compile_runtime

UNITS = ["BusyPhase", "InvalidPhase", "StepDone", "SuccessPhase", "TimeoutReached",
         "NextPhase", "NextTimer", "NextTimeoutFault"]
RUNTIME = None
PROJECTIONS = []
CANONICAL_SOURCE = ""


class ScanContractTests(unittest.TestCase):
    def setUp(self):
        self.r = RUNTIME
        self.r.reset()

    def scan(self, timeout=8, **inputs):
        inputs.setdefault("enable", True)
        return self.r.scan(timeout, **inputs)

    def start(self, timeout=8):
        result = self.scan(timeout, enable=True, init_done=True, start=True)
        self.assertEqual(result["phase"], 1)
        self.assertEqual(result["timer"], 0)
        return result

    def test_no_start_no_init_exit(self):
        for _ in range(10):
            result = self.scan(enable=True, init_done=True)
            self.assertEqual(result["phase"], 0)
            self.assertFalse(result["error"])

    def test_timeout_exact_boundary(self):
        # Sampled thresholds only; the universally quantified deadline is P30.
        for timeout in (1, 2, 3, 8, 31, 65535):
            with self.subTest(timeout=timeout):
                self.r.reset()
                self.start(timeout)
                # For the large UINT boundary, inject the prior timer, then execute real ST.
                if timeout == 65535:
                    self.r.inject(1, timer=65533)
                    scans = (65534, 65535)
                else:
                    scans = range(1, timeout + 1)
                for count in scans:
                    result = self.scan(timeout)
                    if count < timeout:
                        self.assertEqual(result["phase"], 1)
                        self.assertEqual(result["timer"], count)
                        self.assertFalse(result["error"], f"early fault at {count}/{timeout}")
                        self.assertTrue(result["belt_forward"])
                    else:
                        self.assertEqual(result["phase"], 900)
                        self.assertEqual(result["timer"], 0)
                        self.assertTrue(result["error"])
                        self.assertTrue(result["timeout_fault"])
                        self.assertFalse(result["belt_forward"])

    def test_completion_on_deadline_wins(self):
        self.start()
        for _ in range(7):
            self.scan()
        result = self.scan(transport_done=True)
        self.assertEqual(result["phase"], 2)
        self.assertFalse(result["error"])
        self.assertTrue(result["q1"])
        self.assertEqual(result["timer"], 0)

    def test_live_timeout_reduction_preserves_reason(self):
        self.start()
        for _ in range(3):
            self.scan()
        result = self.scan(timeout=2)
        self.assertEqual(result["phase"], 900)
        self.assertTrue(result["timeout_fault"])

    def test_zero_disables_timeout(self):
        self.start(timeout=0)
        for _ in range(100):
            result = self.scan(timeout=0)
            self.assertEqual(result["phase"], 1)
            self.assertEqual(result["timer"], 0)
            self.assertFalse(result["error"])

    def test_full_cycle_and_done_pulse(self):
        self.start()
        self.assertEqual(self.scan(transport_done=True)["phase"], 2)
        self.assertEqual(self.scan(flip_done=True)["phase"], 3)
        result = self.scan(output_done=True)
        self.assertEqual(result["phase"], 1)
        self.assertTrue(result["done"])
        self.assertFalse(self.scan()["done"])

    def test_multiple_done_levels_do_not_cascade_within_scan(self):
        self.start()
        for phase in (2, 3, 1):
            result = self.scan(transport_done=True, flip_done=True, output_done=True)
            self.assertEqual(result["phase"], phase)

    def test_busy_start_ignored(self):
        self.start()
        for phase in (1, 2, 3):
            self.r.inject(phase)
            result = self.scan(start=True)
            self.assertEqual(result["phase"], phase)

    def test_reset_prevents_same_scan_start(self):
        self.start()
        result = self.scan(reset=True, enable=True, init_done=True, start=True)
        self.assertEqual(result["phase"], 0)
        self.assertEqual(result["timer"], 0)
        self.assertFalse(any(result[k] for k in ("belt_forward", "q1", "q2", "done", "error")))

    def test_error_holds_without_acknowledgement(self):
        self.start(timeout=1)
        self.scan(timeout=1)
        for _ in range(5):
            result = self.scan(enable=True, init_done=True, start=True,
                                 transport_done=True, flip_done=True, output_done=True)
            self.assertEqual(result["phase"], 900)
            self.assertTrue(result["error"])
            self.assertTrue(result["timeout_fault"])
            self.assertFalse(any(result[k] for k in ("belt_forward", "q1", "q2", "done")))

    def test_illegal_phase_fails_closed(self):
        for phase in (-32768, -1, 4, 899, 901, 32767):
            self.r.reset()
            self.r.inject(phase)
            result = self.scan()
            self.assertEqual(result["phase"], 900)
            self.assertTrue(result["error"])
            self.assertFalse(any(result[k] for k in ("belt_forward", "q1", "q2", "done")))

    def test_illegal_phase_reports_no_timeout(self):
        # Contract: "Invalid phase raises Error without falsely reporting a timeout."
        for phase in (-32768, -1, 4, 899, 901, 32767):
            self.r.reset()
            self.r.inject(phase)
            result = self.scan()
            self.assertEqual(result["phase"], 900)
            self.assertTrue(result["error"])
            self.assertFalse(result["timeout_fault"])
            self.assertFalse(result["timeout_diagnostic"])

    def test_enable_loss_cancels_motion(self):
        self.start()
        result = self.scan(enable=False, transport_done=True)
        self.assertEqual(result["phase"], 0)
        self.assertFalse(result["belt_forward"] or result["q1"])

    def test_stop_does_not_acknowledge_fault(self):
        self.start(timeout=1)
        self.scan(timeout=1)
        result = self.scan(stop=True, reset=True)
        self.assertEqual(result["phase"], 900)
        self.assertTrue(result["timeout_fault"])

    def test_held_start_does_not_restart_after_stop(self):
        self.start()
        self.scan(start=True, stop=True)
        result = self.scan(start=True, init_done=True)
        self.assertEqual(result["phase"], 0)

    def test_enable_error_and_diagnostic_lifetimes(self):
        self.start(timeout=1)
        result = self.scan(timeout=1)
        self.assertTrue(result["error"] and result["timeout_diagnostic"])
        for _ in range(3):
            result = self.scan(enable=False)
            self.assertFalse(result["error"] or result["timeout_fault"] or result["valid"] or result["busy"])
            self.assertTrue(result["timeout_diagnostic"])
        result = self.scan(init_done=True)
        self.assertEqual(result["phase"], 0)
        self.assertFalse(result["timeout_diagnostic"])
        self.assertTrue(result["valid"] and result["busy"])
        self.assertFalse(result["command_busy"])

    def test_reset_cannot_acknowledge_block_error(self):
        self.start(timeout=1)
        self.scan(timeout=1)
        for inputs in ({"estop": True, "reset": True}, {"reset": True},
                       {"reset": False}, {"reset": True}):
            result = self.scan(**inputs)
            self.assertEqual(result["phase"], 900)
            self.assertTrue(result["error"] and result["timeout_diagnostic"])
        result = self.scan(enable=False)
        self.assertFalse(result["error"])
        self.assertTrue(result["timeout_diagnostic"])
        result = self.scan(init_done=True)
        self.assertEqual(result["phase"], 0)
        self.assertFalse(result["timeout_diagnostic"])

    def test_reset_consumes_start_without_replay(self):
        self.start()
        result = self.scan(reset=True, start=True, init_done=True)
        self.assertEqual(result["phase"], 0)
        self.assertEqual(self.scan(start=True, init_done=True)["phase"], 0)
        self.scan(start=False)
        self.assertEqual(self.scan(start=True, init_done=True)["phase"], 1)

    def test_start_edge_consumed_while_disabled(self):
        self.scan(enable=False, start=True)
        result = self.scan(start=True, init_done=True)
        self.assertEqual(result["phase"], 0)
        self.scan(start=False)
        self.assertEqual(self.scan(start=True, init_done=True)["phase"], 1)

    def test_stop_at_deadline_aborts_without_new_timeout(self):
        self.start(timeout=1)
        result = self.scan(timeout=1, stop=True)
        self.assertEqual(result["phase"], 0)
        self.assertFalse(result["error"] or result["timeout_diagnostic"])
        self.assertTrue(result["command_aborted"])
        self.assertFalse(result["command_busy"])
        self.assertTrue(self.scan()["command_aborted"])
        self.assertFalse(self.scan(start=True, init_done=True)["command_aborted"])

    def test_disable_abort_is_observable_for_one_call(self):
        self.start()
        result = self.scan(enable=False)
        self.assertTrue(result["command_aborted"])
        self.assertFalse(self.scan(enable=False)["command_aborted"])

    def test_output_tampering_cannot_change_internal_state(self):
        self.start()
        self.r.lib.poison_outputs()
        result = self.scan()
        self.assertEqual(result["phase"], 1)
        self.assertFalse(result["error"] or result["timeout_fault"])
        self.assertTrue(result["belt_forward"])

    def test_control_priority_matrix(self):
        for phase in (0, 1, 2, 3, 900):
            for enable, stop, estop, reset, start in itertools.product((False, True), repeat=5):
                with self.subTest(phase=phase, enable=enable, stop=stop, estop=estop, reset=reset, start=start):
                    self.r.reset()
                    self.r.inject(phase, timeout_fault=(phase == 900))
                    result = self.scan(enable=enable, stop=stop, estop=estop, reset=reset,
                                       start=start, init_done=True, transport_done=True,
                                       flip_done=True, output_done=True)
                    if not enable:
                        expected = 0
                    elif phase == 900:
                        expected = 900
                    elif stop or estop or reset:
                        expected = 0
                    else:
                        expected = {0: int(start), 1: 2, 2: 3, 3: 1}[phase]
                    self.assertEqual(result["phase"], expected)
                    self.assertEqual(bool(result["error"]), expected == 900)
                    if not enable or stop or estop or reset or expected == 900:
                        self.assertFalse(any(result[k] for k in ("belt_forward", "belt_reverse", "q1", "q2", "done", "command_busy")))

    def test_zero_threshold_midwait_keeps_timer_zero(self):
        # Contract: "Zero disables counting and keeps timer zero" — switching N to
        # zero mid-wait zeroes the timer, and a restored positive threshold counts
        # from that zero instead of inheriting the frozen count.
        self.start(timeout=8)
        for _ in range(3):
            self.scan(timeout=8)
        result = self.scan(timeout=0)
        self.assertEqual(result["phase"], 1)
        self.assertEqual(result["timer"], 0)
        self.assertFalse(result["error"])
        self.assertEqual(self.scan(timeout=0)["timer"], 0)
        result = self.scan(timeout=2)
        self.assertEqual(result["phase"], 1)
        self.assertEqual(result["timer"], 1)
        self.assertFalse(result["error"])
        result = self.scan(timeout=2)
        self.assertEqual(result["phase"], 900)
        self.assertTrue(result["error"] and result["timeout_fault"])

    def test_reset_held_across_stop_release_not_accepted(self):
        # Contract: "Healthy Reset is accepted only on a rising edge after
        # Stop/EStop release" — a reset held across the release is not a new
        # acceptance and must not clear CommandAborted.
        self.start()
        self.assertTrue(self.scan(stop=True)["command_aborted"])
        self.scan(stop=True, reset=True)
        result = self.scan(reset=True)
        self.assertEqual(result["phase"], 0)
        self.assertTrue(result["command_aborted"])
        self.assertTrue(self.scan()["command_aborted"])
        result = self.scan(start=True, init_done=True)
        self.assertEqual(result["phase"], 1)
        self.assertFalse(result["command_aborted"])

    def test_outputs_written_once_and_not_read_in_canonical_fb(self):
        fb = CANONICAL_SOURCE[CANONICAL_SOURCE.index("FUNCTION_BLOCK"):]
        declarations = re.search(r"VAR_OUTPUT(.*?)END_VAR", fb, re.S).group(1)
        names = re.findall(r"^\s*(\w+)\s*:", declarations, re.M)
        body = fb[fb.rindex("END_VAR") + len("END_VAR"):]
        body = re.sub(r"\(\*.*?\*\)", "", body, flags=re.S)
        for name in names:
            self.assertEqual(len(re.findall(r"(?m)^" + name + r"\s*:=", body)), 1, name)
            # Named FC argument labels are not reads of the same-named FB output.
            without_lhs = re.sub(r"\b" + name + r"\s*:=", "", body)
            self.assertIsNone(re.search(r"\b" + name + r"\b", without_lhs), name)

    def test_generated_projections_match_scan_by_scan(self):
        all_runtimes = [self.r, *PROJECTIONS]
        for r in all_runtimes:
            r.reset()
        rng = random.Random(20260922)
        for index in range(5000):
            # Include startup, corrupt state and UINT boundary snapshots as well as sequences.
            if index % 31 == 0:
                phase = rng.choice([-1, 0, 1, 2, 3, 4, 900])
                timer = rng.choice([0, 1, 6, 7, 65533, 65534])
                for r in all_runtimes:
                    r.inject(phase, timer)
            inputs = {name: rng.random() < probability for name, probability in (
                ("enable", .8), ("start", .2), ("estop", .03), ("stop", .03),
                ("reset", .03), ("init_done", .8), ("transport_done", .1),
                ("flip_done", .1), ("output_done", .1))}
            timeout = rng.choice([0, 1, 2, 3, 8, 31, 65535])
            expected = self.scan(timeout, **inputs)
            for r in PROJECTIONS:
                self.assertEqual(expected, r.scan(timeout, **inputs), f"scan {index}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--iec2c", type=Path, required=True)
    parser.add_argument("--matiec-lib", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    src = args.project / "02_src/st"
    source = "\n".join((src / f"FC_MainSequence_{n}.st").read_text() for n in UNITS)
    source += "\n" + (src / "FB_MainSequence.st").read_text()
    global RUNTIME, PROJECTIONS, CANONICAL_SOURCE
    CANONICAL_SOURCE = source
    try:
        RUNTIME = compile_runtime(source, args.work_dir.resolve(), args.iec2c.resolve(),
                                  args.matiec_lib.resolve(), args.cc)
        for name, relative in (
            ("formal", "03_checks/plcverif/FB_MainSequence_PLCverif.scl"),
            ("openplc", "03_checks/openplc/FB_MainSequence_OpenPLC.st"),
        ):
            projection = (args.project / relative).read_text()
            projection = projection[:projection.index("END_FUNCTION_BLOCK") + len("END_FUNCTION_BLOCK")]
            PROJECTIONS.append(compile_runtime(
                projection, args.work_dir.resolve() / name, args.iec2c.resolve(),
                args.matiec_lib.resolve(), args.cc))
    except (OSError, RuntimeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ScanContractTests))
    (args.work_dir / "result.json").write_text(json.dumps({
        "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "pass": result.wasSuccessful(), "scope": "matiec compiled ST; no Siemens acceptance",
    }, indent=2) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
