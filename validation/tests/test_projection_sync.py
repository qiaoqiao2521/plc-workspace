"""Projection drift must block rather than silently validate a different program."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "validation/scripts/sync-semantics.py"
PROJECT = ROOT / "projects/FB_MainSequence"
spec = importlib.util.spec_from_file_location("sync", SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        inputs = [PROJECT / "02_src/st" / f"{n}.st" for n in sync.UNITS]
        inputs += [PROJECT / "01_specs/scan-contract.md",
                   PROJECT / "03_checks/plcverif/assertions.scl",
                   PROJECT / "03_checks/openplc/driver.st"]
        for p in inputs:
            dest = self.project / p.relative_to(PROJECT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        for p, text in sync.expected_files(self.project).items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

    def check(self):
        return subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.project), "--check"],
                              capture_output=True, text=True, timeout=10).returncode

    def test_generated_output_edit_is_rejected(self):
        self.assertEqual(self.check(), 0)
        p = self.project / "03_checks/plcverif/FB_MainSequence_PLCverif.scl"
        p.write_text(p.read_text().replace("xBeltReverse := FALSE", "xBeltReverse := TRUE"))
        self.assertEqual(self.check(), 1)

    def test_source_change_requires_regeneration(self):
        p = self.project / "02_src/st/FB_MainSequence.st"
        p.write_text(p.read_text() + "\n(* new source revision *)\n")
        self.assertEqual(self.check(), 1)

    def test_assertion_file_cannot_patch_runtime(self):
        p = self.project / "03_checks/plcverif/assertions.scl"
        p.write_text(p.read_text() + "\nxError := FALSE;\n")
        self.assertEqual(self.check(), 2)

    def test_extra_source_unit_requires_explicit_dependency_order(self):
        (self.project / "02_src/st/FC_Extra.st").write_text("FUNCTION FC_Extra : BOOL\nEND_FUNCTION\n")
        self.assertEqual(self.check(), 2)


if __name__ == "__main__":
    unittest.main()
