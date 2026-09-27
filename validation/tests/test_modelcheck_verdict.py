"""Guard against tool exit 0 being confused with a proof."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/run-semantic-modelcheck.py"
spec = importlib.util.spec_from_file_location("modelcheck", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VerdictTests(unittest.TestCase):
    def test_success_requires_unambiguous_proof(self):
        self.assertEqual(module.verdict("**Result: the requirement is SATISFIED**", 0), "pass")

    def test_exit_zero_alone_is_unknown(self):
        self.assertEqual(module.verdict("Program directory: /example", 0), "unknown")
        self.assertEqual(module.verdict("**Result: the requirement is UNKNOWN**", 0), "unknown")

    def test_failure_wins_over_success_text(self):
        text = "**Result: the requirement is SATISFIED**\n**Result: the requirement is VIOLATED**"
        self.assertEqual(module.verdict(text, 0), "fail")

    def test_nonzero_exit_cannot_pass(self):
        self.assertEqual(module.verdict("**Result: the requirement is SATISFIED**", 1), "unknown")


class RequiredAssertionTests(unittest.TestCase):
    # Required lines pin full expressions; IDs alone once let a keep-the-ID,
    # rewrite-the-expression-to-TRUE variant pass the solver (2026-09-27 review).
    L1 = "//#ASSERT NOT (xBeltForward AND xBeltReverse) : P1_BeltMutualExclusion"
    L2 = ("//#ASSERT NOT ((NOT xClearReq) AND (NOT xAbortReq) AND xBusyPhase "
          "AND (NOT xStepDone) AND (uiStepTimeoutScans = 0) AND (uiStepTimerStat <> 0)) "
          ": P32_ZeroThresholdKeepsTimerZero")
    REQUIRED = "# pinned baseline; comments allowed\n" + L1 + "\n" + L2 + "\n"
    SOURCE = "// header\n" + L1 + "\n" + L2 + "\n"

    def test_empty_or_malformed_baseline_is_refused(self):
        for baseline in ("", "# comments only\n", "P1_BeltMutualExclusion"):
            with self.subTest(baseline=baseline), self.assertRaises(ValueError):
                module.missing_required_assertions(self.SOURCE, baseline)

    def test_complete_set_passes(self):
        self.assertEqual(module.missing_required_assertions(self.SOURCE, self.REQUIRED), [])

    def test_id_kept_expression_rewritten_to_true_is_refused(self):
        weakened = self.SOURCE.replace(
            "NOT (xBeltForward AND xBeltReverse)", "TRUE")
        self.assertEqual(module.missing_required_assertions(weakened, self.REQUIRED), [self.L1])

    def test_deletion_is_refused(self):
        self.assertEqual(
            module.missing_required_assertions(self.SOURCE.replace(self.L1 + "\n", ""), self.REQUIRED),
            [self.L1])

    def test_extra_lines_tolerated_for_negative_control(self):
        source = self.SOURCE + "//#ASSERT FALSE : NEGATIVE_CONTROL\n"
        self.assertEqual(module.missing_required_assertions(source, self.REQUIRED), [])

    def test_garbled_expression_does_not_count(self):
        self.assertEqual(module.missing_required_assertions(
            self.SOURCE.replace("uiStepTimerStat <> 0", "uiStepTimerStat >= 0"), self.REQUIRED), [self.L2])


if __name__ == "__main__":
    unittest.main()
