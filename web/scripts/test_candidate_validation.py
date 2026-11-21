"""Newly captured source, compiler feedback and fixed native conveyor obligations."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
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
    return {'request_fingerprint': 'fixture-request', 'scl_files': [{'name': 'FB_ConveyorPack.scl', 'content': content}]}


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


class VerdictTests(unittest.TestCase):
    def test_worker_with_successful_compiler_does_not_claim_behavior(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            source = b'FUNCTION_BLOCK FB_Test\nEND_FUNCTION_BLOCK'
            (folder / 'sources').mkdir()
            (folder / 'sources/FB_Test.st').write_bytes(source)
            validation.write_json(folder / 'job.json', {'files': [
                {'name': 'FB_Test.st', 'sha256': validation.sha(source)}],
                'compiler': 'synthetic-fixture', 'library': 'synthetic-fixture', 'profile': None})
            with patch.object(validation.subprocess, 'run') as compiler:
                compiler.return_value = validation.subprocess.CompletedProcess([], 0, 'compiler fixture', '')
                validation._worker(folder)
            report = json.loads((folder / 'worker-result.json').read_text())
            self.assertEqual(report['status'], 'unknown')
            self.assertEqual({c['name']:c['status'] for c in report['checks']},
                             {'linux_compile':'pass','scan_contract':'not_run'})
            self.assertEqual(report['diagnostics'], 'compiler fixture')
            self.assertNotIn('scenarios', report)

    @unittest.skipUnless(os.name == 'posix', 'Uses local process groups and SIGUSR1')
    def test_cancellation_reaps_local_worker_and_keeps_only_compile_observation(self):
        # The child is a controlled stand-in for a compiler/scan worker. This
        # exercises actual process-group cleanup, not native SCL semantics.
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'check'
            lib = Path(temp) / 'lib'
            lib.mkdir()
            (lib / 'ieclib.txt').touch()
            workers = []
            original_popen = validation.subprocess.Popen
            checkpoint = json.dumps({'checks': [validation.check('linux_compile', 'pass', 'fixture')]})
            child = ('import pathlib,time; p=pathlib.Path("worker-progress.tmp"); '
                     f'p.write_text({checkpoint!r}); p.replace("worker-progress.json"); time.sleep(30)')

            def start_fixture(*args, **kwargs):
                proc = original_popen([sys.executable, '-c', child], cwd=folder, **kwargs)
                workers.append(proc)
                return proc

            done = threading.Event()
            def interrupt():
                until = time.monotonic() + 4
                while not (folder / 'worker-progress.json').exists() and time.monotonic() < until:
                    if done.wait(.02):
                        return
                if not done.is_set():
                    os.kill(os.getpid(), signal.SIGUSR1)

            def raise_cancel(*_):
                raise KeyboardInterrupt('fixture cancellation')

            handler = signal.signal(signal.SIGUSR1, raise_cancel)
            thread = threading.Thread(target=interrupt)
            thread.start()
            try:
                with patch.object(validation.subprocess, 'Popen', side_effect=start_fixture):
                    with self.assertRaises(KeyboardInterrupt):
                        validation.validate_candidate(candidate(), folder, profile=validation.PROFILE,
                                                      compiler=sys.executable, library=lib)
                self.assertIsNotNone(workers[0].poll())
                report = json.loads((folder / 'report.json').read_text())
                self.assertEqual(report['reason'], 'cancelled')
                self.assertEqual({c['name']: c['status'] for c in report['checks']},
                    {'source_capture':'pass', 'linux_compile':'pass', 'scan_contract':'unknown'})
                self.assertIsNone(validation.validation_level(report, validation.PROFILE, 'fixture-request'))
            finally:
                done.set()
                thread.join()
                signal.signal(signal.SIGUSR1, handler)

    def test_required_checks_are_not_inferred_from_headline(self):
        fp = 'fixture-request'
        report = {'schema_version': 2, 'request_fingerprint': fp,
                  'verification_goal': validation.verification_goal(None),
                  'status': 'unknown', 'checks': [
                      validation.check('source_capture', 'pass', 'captured'),
                      validation.check('linux_compile', 'pass', 'fixture compiler'),
                      validation.check('scan_contract', 'not_run', 'no profile')]}
        level = lambda r, profile=None, current=fp: validation.validation_level(r, profile, current)
        self.assertEqual(level(report), 'compile_only')
        self.assertIsNone(level({**report, 'status': 'pass'}))
        self.assertIsNone(level(report, current='older'))
        self.assertIsNone(level({**report, 'reason': 'cancelled'}))
        self.assertIsNone(level({**report, 'verification_goal': {}}))
        self.assertIsNone(level({**report, 'checks': report['checks'][1:]}))
        self.assertIsNone(level({**report, 'checks': report['checks'] + report['checks'][:1]}))
        behavior = {**report, 'status': 'pass', 'profile': validation.PROFILE,
            'verification_goal': validation.verification_goal(validation.PROFILE),
            'contract': validation.CONTRACT, 'contract_sha256': validation.sha(json.dumps(
                validation.CONTRACT, sort_keys=True, separators=(',', ':')).encode())}
        for status in ('fail', 'unknown', 'not_run', 'pass'):
            behavior['checks'] = [*report['checks'][:2], validation.check('scan_contract', status, 'fixture scans')]
            self.assertEqual(level(behavior, validation.PROFILE), 'behavior_pass' if status == 'pass' else None)
        self.assertIsNone(level({**behavior, 'contract_sha256': 'stale'}, validation.PROFILE))
        self.assertIsNone(level(behavior))


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
        self.assertEqual(validation.validation_level(report, validation.PROFILE, 'fixture-request'), 'behavior_pass')
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
        self.assertEqual({c['name']:c['status'] for c in report['checks']}['linux_compile'], 'fail')
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
        self.assertEqual(report['status'], 'unknown', report['diagnostics'])
        checks = {item['name']: item['status'] for item in report['checks']}
        self.assertEqual(checks['linux_compile'], 'pass')
        self.assertEqual(checks['scan_contract'], 'not_run')
        self.assertNotIn('scenarios', report)
        self.assertEqual(validation.validation_level(report, None, 'fixture-request'), 'compile_only')

    @unittest.skipUnless(os.name == 'posix', 'Native execution watchdog uses POSIX SIGALRM')
    def test_native_infinite_scan_is_bounded_and_never_accepted(self):
        result = candidate()
        result['scl_files'][0]['content'] = result['scl_files'][0]['content'].replace(
            '#Motor := (#statState = 2);', 'WHILE TRUE DO #Motor := FALSE; END_WHILE;\n#Motor := (#statState = 2);')
        report = self.validate(result)
        self.assertEqual(report['status'], 'unknown')
        self.assertIn('5 second', report['diagnostics'])
        self.assertEqual(report['reason'], 'tool_timeout')
        self.assertIsNone(validation.validation_level(report, validation.PROFILE, 'fixture-request'))
        self.assertEqual({c['name']:c['status'] for c in report['checks']}['linux_compile'], 'pass')


if __name__ == '__main__':
    unittest.main()
