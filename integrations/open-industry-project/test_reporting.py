"""Result-policy regression checks: empty or malformed evidence cannot be green."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from run import normalize_tests


class ReportPolicyTests(unittest.TestCase):
    def evaluate(self, content, exit_code=0):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.CompletedProcess([], exit_code,
                json.dumps(content) if not isinstance(content, str) else content, "")
            return normalize_tests(result, {}, Path(tmp))

    def test_empty_success_is_not_run(self):
        self.assertEqual(self.evaluate({"ok": True, "tests": []})["status"], "not_run")
        self.assertEqual(self.evaluate("no tests found in example") ["status"], "not_run")

    def test_zero_assertions_is_not_run(self):
        report = self.evaluate({"ok": True, "tests": [{"ok": True, "checks": []}]})
        self.assertEqual((report["status"], report["reason"]), ("not_run", "no_assertions"))

    def test_missing_or_bad_checks_are_error(self):
        for tests in ([None], [{"ok": True}], [{"ok": True, "checks": [None]}], [{"error": "compile failed"}]):
            with self.subTest(tests=tests):
                self.assertEqual(self.evaluate({"ok": True, "tests": tests})["status"], "error")

    def test_failed_assertion_cannot_hide_in_success_envelope(self):
        report = self.evaluate({"ok": True, "tests": [{"ok": True, "checks": [{"ok": False}]}]})
        self.assertEqual(report["status"], "failed")

    def test_process_error_cannot_hide_in_success_envelope(self):
        report = self.evaluate({"ok": True, "tests": [{"ok": True, "checks": [{"ok": True}]}]}, 3)
        self.assertEqual(report["status"], "error")

    def test_actual_success_is_passed(self):
        report = self.evaluate({"ok": True, "tests": [{"ok": True, "checks": [{"ok": True}]}]})
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["counts"], {"tests": 1, "checks": 1, "failed_checks": 0})


if __name__ == "__main__":
    unittest.main()
