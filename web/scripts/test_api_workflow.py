"""Real HTTP/controller/native integration with scripted API completions only.

No hosted model or paid API is used. The fixture supplies candidate answers;
matiec/GCC, the serialized LAD executor, gates, and subprocess cleanup are real.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from test_agent_control import NATIVE_AVAILABLE, answer_for, bridge_module, request
from test_model_api import FIXTURE_KEY, HttpFixture, completion


@unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for real API workflow/native checks')
class APIWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plc-api-workflow-fixture-')
        self.root = Path(self.temp.name) / 'runs'
        self.fixture = HttpFixture()
        self.bad_ir = True
        self.block_reviews = False
        self.release_reviews = threading.Event()
        self.both_reviews = threading.Event()
        self.fixture_lock = threading.Lock()
        self.deliveries, self.fixture_errors = [], []
        self.review_instructions = set()
        self.repairs = self.review_count = 0
        self.fixture.respond = self.respond
        self.bridge = bridge_module.GenerationBridge(
            config=self.fixture.config(timeout_seconds=60), runtime_root=self.root)
        self.server = bridge_module.ThreadingHTTPServer(('127.0.0.1', 0), bridge_module.Handler)
        self.server.bridge = self.bridge
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.release_reviews.set()
        if self.bridge.active:
            self.bridge.cancel(self.bridge.active)
            deadline = time.monotonic() + 10
            while self.bridge.active and time.monotonic() < deadline:
                time.sleep(.02)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.fixture.close()
        self.temp.cleanup()

    def respond(self, incoming):
        """Recognize each complete output schema; never invent tool reports."""
        try:
            payload = json.loads(incoming['body'])
            system, user = payload['messages']
            schema = json.loads(system['content'].rsplit('JSON Schema:\n', 1)[1])
            data = json.loads(user['content'])
            fields = set(schema['properties'])
            if 'specification' in fields:
                kind, stage = 'analysis', 'analysis'
            elif 'logic_ir' in fields and 'request_id' in fields:
                kind, stage = 'generation', 'generation'
            elif fields == {'logic_ir', 'summary'}:
                with self.fixture_lock:
                    self.repairs += 1
                    number = self.repairs
                kind, stage = 'repair', 'repair-' + str(number)
            elif schema['properties']['verdict']['enum'] == ['pass', 'fail', 'unknown']:
                # Both reviewer roles have the same answer schema. Their actual
                # stage/role identities remain inside the real controller.
                kind, stage = 'review', 'semantic-review'
            elif schema['properties']['verdict']['enum'] == ['approve', 'reject', 'unknown']:
                kind = 'final-review' if 'reviews' in data else 'spec-review'
                stage = kind
            else:
                raise ValueError('Unexpected fixture schema')
            with self.fixture_lock:
                self.deliveries.append(kind)
                if kind == 'review':
                    self.review_count += 1
                    self.review_instructions.add(system['content'])
                    if self.review_count == 2:
                        self.both_reviews.set()
            if kind == 'review':
                # Neither review responds until both HTTP calls are in flight.
                if not self.both_reviews.wait(timeout=8):
                    raise RuntimeError('Parallel review requests did not arrive')
                if self.block_reviews and not self.release_reviews.wait(timeout=30):
                    raise RuntimeError('Fixture reviewers were not released')
            answer = answer_for({'stage': stage, 'packet': {'data': data}}, bad_ir=self.bad_ir)
            return 200, {}, json.dumps(completion(json.dumps(answer))).encode()
        except Exception as error:
            with self.fixture_lock:
                self.fixture_errors.append(type(error).__name__)
            return 500, {}, b'{"error":"Explicit API workflow fixture failed"}'

    def http(self, path, body):
        req = Request(self.url + path, data=json.dumps(body).encode(), method='POST',
                      headers={'Content-Type': 'application/json', 'X-PLC-Workspace': '1'})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def begin(self):
        code, response = self.http('/api/generate', {'request': request()})
        self.assertEqual(code, 202, response)
        return response['job_id']

    def wait_finished(self, job_id, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.bridge.snapshot(job_id)
            if current.get('finished'):
                return current
            time.sleep(.02)
        self.fail('API workflow did not finish and release its process')

    def assert_no_credentials(self, snapshot, logs):
        self.assertNotIn(FIXTURE_KEY, json.dumps(snapshot))
        self.assertNotIn(FIXTURE_KEY, logs)
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertNotIn(FIXTURE_KEY.encode(), path.read_bytes(), str(path))
        with self.fixture.lock:
            captured = list(self.fixture.requests)
        self.assertTrue(captured)
        for incoming in captured:
            self.assertEqual(incoming['path'], '/v1/chat/completions')
            self.assertEqual(incoming['headers'].get('Authorization'), 'Bearer ' + FIXTURE_KEY)
            self.assertNotIn(FIXTURE_KEY.encode(), incoming['body'])
        self.assertEqual(self.fixture_errors, [])

    def test_api_fixture_repairs_ir_through_real_native_and_parallel_review(self):
        logs = io.StringIO()
        with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            job_id = self.begin()
            final = self.wait_finished(job_id)
        self.assertEqual(final['status'], 'complete', final.get('error'))
        self.assertIsNone(self.bridge.active)
        self.assertEqual(self.deliveries,
                         ['analysis', 'spec-review', 'generation', 'repair', 'review', 'review', 'final-review'])
        self.assertEqual(len(self.review_instructions), 2)
        outcome = final['workflow']
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['industrial_acceptance'], 'not_run')
        self.assertEqual(final['acceptance'], {'scl_compile': True, 'scl_behavior': True,
                                              'lad_scl_compare': True, 'tia_compile': False})
        self.assertEqual(len(outcome['attempts']), 2)
        self.assertEqual(outcome['attempts'][0]['validation']['status'], 'fail')
        self.assertEqual(outcome['attempts'][1]['validation']['status'], 'pass')
        self.assertTrue(outcome['attempts'][0]['validation']['comparison']['counterexamples'])
        self.assertEqual(set(outcome['reviews']), {'semantics', 'interface'})
        report = final['verification']
        statuses = {row['name']: row['status'] for row in report['checks']}
        for required in report['required_checks']:
            self.assertEqual(statuses[required], 'pass')
        self.assertEqual(statuses['tia_compile'], 'not_run')
        self.assertEqual(report['comparison']['bounded_calls'], 16384)
        for number in range(2):
            self.assertTrue((self.root / job_id / f'attempt-{number}/validation/native/runtime.so').is_file())
        self.assert_no_credentials(final, logs.getvalue())

    def test_cancelling_two_hung_api_reviewers_forces_exit_without_acceptance(self):
        self.bad_ir = False
        self.block_reviews = True
        logs = io.StringIO()
        with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
            job_id = self.begin()
            self.assertTrue(self.both_reviews.wait(timeout=20), 'Both API reviewers must be in flight')
            with self.bridge.lock:
                process = self.bridge.jobs[job_id]['process']
            self.assertIsNotNone(process)
            self.assertIsNone(process.poll())
            code, _ = self.http('/api/jobs/' + job_id + '/cancel', {})
            self.assertEqual(code, 200)
            final = self.wait_finished(job_id, timeout=10)
        self.assertFalse(self.release_reviews.is_set(), 'Fixture did not unblock the pending HTTP calls')
        self.assertIsNone(self.bridge.active)
        self.assertIsNotNone(process.poll())
        if os.name == 'posix':
            self.assertEqual(process.returncode, -signal.SIGKILL, 'The bridge force-kill fallback must run')
        self.assertEqual(final['status'], 'cancelled')
        self.assertFalse(any(final['acceptance'].values()))
        self.assertNotIn('result', final)
        self.assertEqual(final['workflow']['verdict'], 'cancelled')
        self.assertFalse(any(final['workflow']['acceptance'].values()))
        self.assertIsNone(final['workflow']['result'])
        self.assertEqual(self.deliveries, ['analysis', 'spec-review', 'generation', 'review', 'review'])
        self.assertEqual(len(self.review_instructions), 2)
        self.assert_no_credentials(final, logs.getvalue())


if __name__ == '__main__':
    unittest.main()
