"""External Agent protocol: real HTTP/controller, explicit answer fixtures.

These tests never call a hosted model. Native-labelled tests do run matiec/GCC
and the serialized LAD executor; scripted answers are only transport fixtures.
"""
import hashlib
import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge_module = load('external_agent_bridge', 'local-server.py')
logic = load('external_agent_logic', 'logic-ir.py')
NATIVE_AVAILABLE = bool(os.environ.get('SIM_IEC2C') and shutil.which(os.environ['SIM_IEC2C'])
                        and os.environ.get('SIM_MATIEC_LIB')
                        and (Path(os.environ['SIM_MATIEC_LIB']) / 'ieclib.txt').is_file()
                        and shutil.which('gcc'))


def request():
    brief = json.loads((HERE.parent / 'data/latch-start-stop-brief.json').read_text())
    encoded = json.dumps({'brief': brief, 'states': []}, ensure_ascii=False, separators=(',', ':'))
    return {'schema_version': 1, 'request_id': 'external-agent-protocol-fixture',
            'request_fingerprint': hashlib.sha256(encoded.encode()).hexdigest(),
            'brief': brief, 'states': []}


def answer_for(item, *, bad_ir=False, analysis_blocked=False):
    """Explicit scripted Agent answers, not a claim about model capability."""
    stage, packet = item['stage'], item['packet']
    if stage == 'analysis':
        return {'verdict': 'blocked' if analysis_blocked else 'ready',
                'questions': ['Fixture unresolved process decision'] if analysis_blocked else [],
                'unresolved': [], 'specification': 'Explicit synthetic latch contract',
                'obligations': ['Every invocation consumes Start; stop/disable revokes Motor immediately']}
    if stage == 'spec-review' or stage.startswith('final-review'):
        return {'verdict': 'approve', 'findings': [], 'evidence': ['Explicit Agent answer fixture']}
    if stage.startswith(('semantic-review', 'interface-review')):
        return {'verdict': 'pass', 'findings': [], 'evidence': ['Explicit Agent answer fixture']}
    if stage == 'generation':
        req = packet['data']['request']
        ir = logic.example_ir()
        if bad_ir:
            ir['networks'][1]['expression']['children'][2]['kind'] = 'series'
        return {**{key: req[key] for key in ('schema_version', 'request_id', 'request_fingerprint')},
                'summary': 'Explicit external Agent fixture', 'questions': [], 'logic_ir': ir}
    if stage.startswith('repair-'):
        return {'logic_ir': logic.example_ir(), 'summary': 'Explicit fixture repairs IR only'}
    raise AssertionError('Unexpected controller stage: ' + stage)


class AgentControlHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plc-agent-control-test-')
        self.root = Path(self.temp.name) / 'runs'
        self.bridge = bridge_module.GenerationBridge(runtime_root=self.root)
        self.server = bridge_module.ThreadingHTTPServer(('127.0.0.1', 0), bridge_module.Handler)
        self.server.bridge = self.bridge
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.bridge.active:
            job = self.bridge.active
            self.bridge.cancel(job)
            deadline = time.monotonic() + 8
            while self.bridge.active and time.monotonic() < deadline:
                time.sleep(.02)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        self.temp.cleanup()

    def http(self, method, path, data=None, *, token=None, headers=None):
        values = {'Content-Type': 'application/json'}
        if method == 'POST':
            values['X-PLC-Workspace'] = '1'
        if token is not None:
            values['Authorization'] = 'Bearer ' + token
        values.update(headers or {})
        req = Request(self.url + path, data=None if data is None else json.dumps(data).encode(),
                      method=method, headers=values)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def create_job(self):
        code, data = self.http('POST', '/api/agent/jobs', {'request': request()})
        self.assertEqual(code, 202, data)
        self.assertIsInstance(data.get('job_id'), str)
        self.assertIsInstance(data.get('agent_token'), str)
        self.assertGreaterEqual(len(data['agent_token']), 24)
        return data['job_id'], data['agent_token']

    def poll(self, job, token):
        code, data = self.http('GET', f'/api/agent/jobs/{job}/packets', token=token)
        self.assertEqual(code, 200, data)
        return data

    def wait_packets(self, job, token, *, expected=None, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self.poll(job, token)
            if data['packets'] and (expected is None or any(p['stage'] == expected for p in data['packets'])):
                return data['packets']
            if data.get('finished'):
                self.fail('Controller finished before expected packet: ' + json.dumps(self.bridge.snapshot(job)))
            time.sleep(.02)
        self.fail('No pending packet delivered: ' + str(expected))

    def submit(self, job, token, packet, answer=None):
        body = {'packet_id': packet['packet_id'], 'input_sha256': packet['input_sha256'],
                'answer': answer_for(packet) if answer is None else answer}
        return self.http('POST', f'/api/agent/jobs/{job}/answers', body, token=token)

    def wait_finished(self, job, *, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.bridge.snapshot(job)
            if result and result.get('finished'):
                return result
            time.sleep(.02)
        self.fail('Controller did not finish/clean up')

    def drive(self, job, token, *, bad_ir=False, stop_at_reviews=False):
        seen = []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            data = self.poll(job, token)
            for item in data['packets']:
                if stop_at_reviews and item['stage'].startswith(('semantic-review', 'interface-review')):
                    return seen
                if item['packet_id'] in [entry['packet_id'] for entry in seen]:
                    continue
                answer = answer_for(item, bad_ir=bad_ir)
                code, response = self.submit(job, token, item, answer)
                self.assertEqual(code, 200, response)
                self.assertTrue(response.get('accepted'))
                seen.append(item)
            current = self.bridge.snapshot(job)
            if current.get('finished'):
                return seen
            time.sleep(.02)
        self.fail('Controller did not progress through Agent fixtures')

    def test_agent_entry_starts_without_api_credentials_or_cli(self):
        code, capabilities = self.http('GET', '/api/capabilities')
        self.assertEqual(code, 200)
        self.assertEqual(capabilities['provider'], 'api')
        self.assertFalse(capabilities['ready'])
        self.assertTrue(capabilities['agent_control'])
        job, token = self.create_job()
        packet = self.wait_packets(job, token, expected='analysis')[0]
        self.assertEqual(packet['stage'], 'analysis')
        self.assertEqual(set(packet['packet']), {'stage', 'data', 'schema', 'instructions'})
        actual = hashlib.sha256(json.dumps(packet['packet'], ensure_ascii=False,
                                          sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(packet['input_sha256'], actual)
        self.assertNotIn(token, json.dumps(self.bridge.snapshot(job)))
        self.assertNotIn(token, json.dumps(self.poll(job, token)))
        for path in self.root.rglob('*.json'):
            self.assertNotIn(token, path.read_text())

    def test_agent_token_is_required_and_scoped_to_job(self):
        job, token = self.create_job()
        packet = self.wait_packets(job, token)[0]
        for wrong in (None, token + 'wrong'):
            code, _ = self.http('GET', f'/api/agent/jobs/{job}/packets', token=wrong)
            self.assertEqual(code, 401)
            code, _ = self.submit(job, wrong, packet)
            self.assertEqual(code, 401)
        self.bridge.cancel(job)
        self.wait_finished(job)
        second, second_token = self.create_job()
        self.assertNotEqual(token, second_token)
        code, _ = self.http('GET', f'/api/agent/jobs/{second}/packets', token=token)
        self.assertEqual(code, 401)

    def test_agent_token_cannot_be_reflected_into_answers_or_evidence(self):
        job, token = self.create_job()
        packet = self.wait_packets(job, token, expected='analysis')[0]
        answer = answer_for(packet)
        answer['specification'] += ' ' + token
        code, _ = self.submit(job, token, packet, answer)
        self.assertEqual(code, 400)
        pending = self.poll(job, token)['packets']
        self.assertEqual([p['packet_id'] for p in pending], [packet['packet_id']])
        for path in self.root.rglob('*.json'):
            self.assertNotIn(token, path.read_text())

    def test_bad_binding_or_schema_never_consumes_the_pending_stage(self):
        job, token = self.create_job()
        packet = self.wait_packets(job, token)[0]
        base = {'packet_id': packet['packet_id'], 'input_sha256': packet['input_sha256'],
                'answer': answer_for(packet)}
        variants = [
            {**base, 'input_sha256': '0' * 64},
            {**base, 'answer': {**base['answer'], 'acceptance': {'scl_behavior': True}}},
            {**base, 'answer': 'arbitrary answer'},
            {**base, 'packet_id': '../outcome'},
            {**base, 'stage': 'final-review'},
        ]
        for body in variants:
            code, _ = self.http('POST', f'/api/agent/jobs/{job}/answers', body, token=token)
            self.assertIn(code, (400, 409))
            pending = self.poll(job, token)['packets']
            self.assertEqual([p['packet_id'] for p in pending], [packet['packet_id']])
        simultaneous = threading.Barrier(2)

        def send_once():
            simultaneous.wait(timeout=5)
            return self.submit(job, token, packet)[0]

        with ThreadPoolExecutor(max_workers=2) as pool:
            deliveries = [pool.submit(send_once) for _ in range(2)]
            self.assertEqual(sorted(future.result(timeout=10) for future in deliveries), [200, 409])
        self.wait_packets(job, token, expected='spec-review')
        code, _ = self.submit(job, token, packet)
        self.assertEqual(code, 409)

    def test_cross_origin_or_missing_workspace_header_cannot_mutate(self):
        for headers in ({'Origin': 'https://other.example'}, {'X-PLC-Workspace': '0'}):
            code, _ = self.http('POST', '/api/agent/jobs', {'request': request()}, headers=headers)
            self.assertEqual(code, 403)
        self.assertIsNone(self.bridge.active)

    def test_one_job_and_pending_cancellation_leave_no_acceptance(self):
        job, token = self.create_job()
        packet = self.wait_packets(job, token)[0]
        code, _ = self.http('POST', '/api/agent/jobs', {'request': request()})
        self.assertEqual(code, 409)
        code, _ = self.http('POST', f'/api/jobs/{job}/cancel', {})
        self.assertEqual(code, 200)
        finished = self.wait_finished(job)
        self.assertEqual(finished['status'], 'cancelled')
        self.assertFalse(any(finished['acceptance'].values()))
        self.assertNotIn('result', finished)
        self.assertIsNone(self.bridge.active)
        code, _ = self.submit(job, token, packet)
        self.assertEqual(code, 409)

    def test_unresolved_analysis_cannot_be_approved_into_generation(self):
        job, token = self.create_job()
        first = self.wait_packets(job, token, expected='analysis')[0]
        code, _ = self.submit(job, token, first, answer_for(first, analysis_blocked=True))
        self.assertEqual(code, 200)
        review = self.wait_packets(job, token, expected='spec-review')[0]
        code, _ = self.submit(job, token, review)
        self.assertEqual(code, 200)
        finished = self.wait_finished(job)
        self.assertEqual(finished['status'], 'failed')
        self.assertEqual(finished['workflow']['verdict'], 'blocked')
        self.assertFalse(any(finished['acceptance'].values()))
        self.assertFalse(self.poll(job, token)['packets'])

    @unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for real Agent transport/native checks')
    def test_agent_fixture_repairs_ir_through_real_controller_native_and_graph(self):
        job, token = self.create_job()
        delivered = self.drive(job, token, bad_ir=True)
        stages = [item['stage'] for item in delivered]
        self.assertEqual(stages[:3], ['analysis', 'spec-review', 'generation'])
        self.assertIn('repair-1', stages)
        self.assertIn('semantic-review-1', stages)
        self.assertIn('interface-review-1', stages)
        self.assertEqual(stages[-1], 'final-review-1')
        final = self.wait_finished(job)
        self.assertEqual(final['status'], 'complete', final.get('error'))
        self.assertEqual(final['workflow']['verdict'], 'reviewed_draft')
        self.assertTrue(final['acceptance']['scl_compile'])
        self.assertTrue(final['acceptance']['scl_behavior'])
        self.assertTrue(final['acceptance']['lad_scl_compare'])
        self.assertFalse(final['acceptance']['tia_compile'])
        self.assertEqual(len(final['workflow']['attempts']), 2)
        self.assertEqual(final['workflow']['attempts'][0]['validation']['status'], 'fail')
        self.assertEqual(final['verification']['comparison']['bounded_calls'], 16384)
        self.assertNotIn(token, json.dumps(final))

    @unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for cancellation after native checks')
    def test_cancelling_two_waiting_reviewers_does_not_hang_controller(self):
        job, token = self.create_job()
        self.drive(job, token, stop_at_reviews=True)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            pending = self.poll(job, token)['packets']
            if len(pending) == 2:
                break
            time.sleep(.02)
        self.assertEqual({p['stage'] for p in pending}, {'semantic-review', 'interface-review'})
        self.bridge.cancel(job)
        result = self.wait_finished(job, timeout=8)
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse(any(result['acceptance'].values()))
        self.assertFalse(any(result['workflow']['acceptance'].values()))
        self.assertIsNone(result['workflow']['result'])
        self.assertIsNone(self.bridge.active)


if __name__ == '__main__':
    unittest.main()
