"""Newly captured source, compiler feedback and fixed native conveyor obligations."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('candidate_validation', Path(__file__).with_name('candidate-validation.py'))
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
SOURCE = validation.ROOT / 'plans/plc-generation-ui/user-eval/candidates/FB_ConveyorPack.scl'


def candidate(threshold=12):
    # A test fixture derived from an existing draft, not an edit to that draft.
    content = SOURCE.read_text().replace('>= 8', f'>= {threshold}')
    return {'scl_files': [{'name': 'FB_ConveyorPack.scl', 'content': content}]}


class CaptureTests(unittest.TestCase):
    def test_unavailable_compiler_preserves_source_and_unknown_report(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            result = candidate()
            report = validation.validate_candidate(result, Path(temp) / 'check', profile=validation.PROFILE)
            captured = Path(temp) / 'check/sources/FB_ConveyorPack.scl'
            self.assertEqual(captured.read_bytes(), result['scl_files'][0]['content'].encode())
            self.assertEqual(report['files'], [{'name': 'FB_ConveyorPack.scl', 'sha256': validation.sha(captured.read_bytes())}])
            self.assertEqual(report['status'], 'unknown')
            self.assertEqual(report['tia_compile'], 'not_run')
            self.assertEqual(json.loads((Path(temp) / 'check/report.json').read_text()), report)
            self.assertEqual(report['contract']['waiting_calls'], 12)

    def test_reusing_check_directory_cannot_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            target = Path(temp) / 'check'
            validation.validate_candidate(candidate(), target)
            with self.assertRaises(FileExistsError):
                validation.validate_candidate(candidate(8), target)

    def test_source_paths_and_case_duplicate_names_are_rejected(self):
        for files in [[{'name': '../outside.scl', 'content': 'x'}],
                      [{'name': 'A.scl', 'content': 'x'}, {'name': 'a.scl', 'content': 'y'}]]:
            with self.subTest(files=files), tempfile.TemporaryDirectory() as temp:
                report = validation.validate_candidate({'scl_files': files}, Path(temp) / 'check')
                self.assertEqual(report['status'], 'fail')

    def test_adaptation_preserves_literals_and_rejects_native_pragmas(self):
        adapted = validation.normalize("FUNCTION_BLOCK \"B\"\nBEGIN\n#v := '//not a comment'; // comment\nEND_FUNCTION_BLOCK")
        self.assertIn("v := '//not a comment';", adapted)
        self.assertNotIn('#v', adapted)
        self.assertEqual(validation.normalize('#v := BOOL#TRUE;'), 'v := BOOL#TRUE;')
        with self.assertRaises(NotImplementedError):
            validation.normalize('{#include <stdio.h>}')


class NativeCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = os.getenv('SIM_IEC2C')
        cls.library = os.getenv('SIM_MATIEC_LIB')
        if not cls.compiler or not cls.library:
            raise unittest.SkipTest('Native candidate checks need SIM_IEC2C and SIM_MATIEC_LIB')

    def validate(self, result, profile=validation.PROFILE):
        with tempfile.TemporaryDirectory(prefix='plc-candidate-test-') as temp:
            return validation.validate_candidate(result, Path(temp) / 'check', profile=profile,
                compiler=self.compiler, library=self.library)

    def test_twelve_waiting_calls_and_simultaneous_inputs_pass(self):
        report = self.validate(candidate())
        self.assertEqual(report['status'], 'pass', report['diagnostics'])
        self.assertEqual(len(report['scenarios']), 5)
        self.assertTrue(all(case['passed'] for case in report['scenarios']))
        self.assertEqual(report['scenarios'][0]['calls'][-1]['call'], 13)
        self.assertEqual(report['tia_compile'], 'not_run')

    def test_old_eight_call_source_fails_new_frozen_contract(self):
        report = self.validate(candidate(8))
        self.assertEqual(report['status'], 'fail', report['diagnostics'])
        checks = {item['name']: item['status'] for item in report['checks']}
        self.assertEqual(checks['linux_compile'], 'pass')
        self.assertEqual(checks['scan_contract'], 'fail')
        self.assertIn('timeout_on_waiting_call_12', report['diagnostics'])

    def test_real_type_error_returns_compiler_diagnostic(self):
        result = candidate()
        result['scl_files'][0]['content'] = result['scl_files'][0]['content'].replace(
            '#Motor := (#statState = 2);', '#Motor := 1.5;')
        report = self.validate(result)
        self.assertEqual(report['status'], 'fail', report['diagnostics'])
        self.assertEqual(report['checks'][0]['name'], 'linux_compile')
        self.assertEqual(report['checks'][0]['status'], 'fail')
        self.assertTrue(report['diagnostics'].strip())

    def test_start_edge_during_stop_must_be_consumed(self):
        result = candidate()
        result['scl_files'][0]['content'] = result['scl_files'][0]['content'].replace(
            '#statLastStart := #Start;', 'IF NOT #Stop THEN #statLastStart := #Start; END_IF;')
        report = self.validate(result)
        self.assertEqual(report['status'], 'fail', report['diagnostics'])
        failure = next(case for case in report['scenarios'] if case['name'] == 'start_edge_during_stop_is_consumed')
        self.assertFalse(failure['passed'])

    def test_generic_candidate_compiles_without_inheriting_behavior_tests(self):
        report = self.validate(candidate(8), profile=None)
        self.assertEqual(report['status'], 'pass', report['diagnostics'])
        checks = {item['name']: item['status'] for item in report['checks']}
        self.assertEqual(checks['linux_compile'], 'pass')
        self.assertEqual(checks['scan_contract'], 'not_run')
        self.assertNotIn('scenarios', report)

    @unittest.skipUnless(os.name == 'posix', 'Native execution watchdog uses POSIX SIGALRM')
    def test_native_infinite_scan_is_bounded_and_never_accepted(self):
        result = candidate()
        result['scl_files'][0]['content'] = result['scl_files'][0]['content'].replace(
            '#Motor := (#statState = 2);', 'WHILE TRUE DO #Motor := FALSE; END_WHILE;\n#Motor := (#statState = 2);')
        report = self.validate(result)
        self.assertEqual(report['status'], 'unknown')
        self.assertIn('5 second', report['diagnostics'])


if __name__ == '__main__':
    unittest.main()
