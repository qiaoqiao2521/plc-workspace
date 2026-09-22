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


if __name__ == "__main__":
    unittest.main()
