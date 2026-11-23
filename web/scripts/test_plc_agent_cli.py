"""The thin Agent CLI against a real local controller, using explicit answers.

No model is invoked. The native-labelled test executes actual matiec/GCC and
serialized LAD checks; all other tests stop before code generation.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen

from test_agent_control import NATIVE_AVAILABLE, answer_for, bridge_module, request

CLI = Path(__file__).with_name('plc-agent.py')


class StdioClient:
    def __init__(self, command, cwd):
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, bufsize=1, start_new_session=(os.name == 'posix'))
        self.lines, self.errors, self.events = [], [], []
        self.pending = queue.Queue()
        self.readers = [threading.Thread(target=self.read_output, daemon=True),
                        threading.Thread(target=self.read_errors, daemon=True)]
        for thread in self.readers:
            thread.start()

    def read_output(self):
        for line in self.process.stdout:
            self.lines.append(line)
            try:
                event = json.loads(line)
            except ValueError:
                event = {'type': 'invalid_json'}
            self.events.append(event)
            self.pending.put(event)
        self.pending.put(None)

    def read_errors(self):
        self.errors.append(self.process.stderr.read())

    def send(self, value):
        self.process.stdin.write(json.dumps(value, ensure_ascii=False) + '\n')
        self.process.stdin.flush()

    def next(self, timeout):
        try:
            event = self.pending.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError('CLI did not emit its next protocol event') from None
        if event is None:
            raise AssertionError('CLI ended before the expected protocol event')
        return event

    def wait(self, timeout=10):
        code = self.process.wait(timeout=timeout)
        for thread in self.readers:
            thread.join(timeout=2)
        return code

    def close(self):
        if not self.process.stdin.closed:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.wait(timeout=3)
        self.process.stdout.close()
        self.process.stderr.close()


class PLCAgentCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plc-agent-cli-fixture-')
        self.folder = Path(self.temp.name)
        self.bridge = bridge_module.GenerationBridge(runtime_root=self.folder / 'runs')
        self.clients, self.servers = [], []
        self.url = self.serve(bridge_module.Handler)
        self.addCleanup(self.cleanup)

    def serve(self, handler):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        server.daemon_threads = True
        server.bridge = self.bridge
        thread = threading.Thread(target=server.serve_forever,
                                  kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return 'http://127.0.0.1:' + str(server.server_port)

    def cleanup(self):
        for client in self.clients:
            client.close()
        if self.bridge.active:
            self.bridge.cancel(self.bridge.active)
            deadline = time.monotonic() + 10
            while self.bridge.active and time.monotonic() < deadline:
                time.sleep(.02)
        for server, thread in reversed(self.servers):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.temp.cleanup()

    def command(self, *args, url=None):
        return [sys.executable, str(CLI), '--url', self.url if url is None else url,
                '--poll-interval', '.1', *args]

    def once(self, *args, url=None):
        return subprocess.run(self.command(*args, url=url), cwd=self.folder, input='',
                              text=True, capture_output=True, timeout=15)

    def start(self, *, attach=None, exported=False, url=None):
        if attach is None:
            path = self.folder / ('request-' + str(len(self.clients)) + '.json')
            value = {'kind': 'plc-agent-task', 'request': request()} if exported else request()
            path.write_text(json.dumps(value, ensure_ascii=False))
            args = ['workflow', '--request', str(path)]
        else:
            args = ['workflow', '--attach']
        client = StdioClient(self.command(*args, url=url), self.folder)
        self.clients.append(client)
        if attach is not None:
            client.send(attach)
        return client

    def wait_event(self, client, event_type, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event = client.next(max(.01, deadline - time.monotonic()))
            self.assertIsInstance(event, dict)
            self.assertNotEqual(event.get('type'), 'invalid_json')
            if event.get('type') == event_type:
                return event
            if event.get('type') in ('error', 'finished'):
                self.fail('CLI emitted ' + event['type'] + ' before ' + event_type)
        self.fail('CLI did not emit ' + event_type)

    def wait_packet(self, client, stage):
        while True:
            event = self.wait_event(client, 'packets')
            for packet in event['packets']:
                if packet['stage'] == stage:
                    return packet

    def answer(self, client, packet, value=None):
        client.send({'packet_id': packet['packet_id'], 'input_sha256': packet['input_sha256'],
                     'answer': answer_for(packet) if value is None else value})

    def create_agent_job(self):
        req = Request(self.url + '/api/agent/jobs',
                      data=json.dumps({'request': request()}).encode(), method='POST',
                      headers={'Content-Type': 'application/json', 'X-PLC-Workspace': '1'})
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 202)
            return json.loads(response.read())

    def assert_token_private(self, client, job_id):
        with self.bridge.lock:
            token = self.bridge._tokens[job_id]
            controller = self.bridge.jobs[job_id].get('process')
        self.assertFalse(token in ''.join(client.lines), 'Token appeared on CLI stdout')
        self.assertFalse(token in ''.join(client.errors), 'Token appeared on CLI stderr')
        self.assertFalse(token in ' '.join(client.process.args), 'Token appeared in argv')
        for process in (client.process, controller):
            if process is None or process.poll() is not None:
                continue
            for name in ('cmdline', 'environ'):
                path = Path('/proc') / str(process.pid) / name
                if path.is_file():
                    self.assertFalse(token.encode() in path.read_bytes(), 'Token appeared in process ' + name)
        for path in self.folder.rglob('*'):
            if path.is_file():
                self.assertFalse(token.encode() in path.read_bytes(), 'Token appeared in a test/runtime file')
        self.assertFalse(token in json.dumps(self.bridge.snapshot(job_id)), 'Token appeared in job snapshot')

    def assert_cancelled(self, client, finished):
        self.assertEqual(client.wait(), 2)
        job = finished['job']
        self.assertTrue(job['finished'])
        self.assertEqual(job['status'], 'cancelled')
        self.assertFalse(any(job['acceptance'].values()))
        self.assertNotIn('result', job)
        self.assertIsNone(self.bridge.active)
        self.assert_token_private(client, finished['job_id'])

    def test_doctor_status_and_rejected_answer_then_blocked_workflow(self):
        doctor = self.once('doctor')
        self.assertEqual(doctor.returncode, 0)
        diagnostic = json.loads(doctor.stdout)
        self.assertEqual(diagnostic['type'], 'doctor')
        self.assertTrue(diagnostic['capabilities']['agent_control'])
        self.assertFalse(diagnostic['capabilities']['ready'])
        client = self.start(exported=True)
        job_id = self.wait_event(client, 'started')['job_id']
        packet = self.wait_packet(client, 'analysis')
        status = self.once('status', job_id)
        self.assertEqual(status.returncode, 0)
        self.assertEqual(json.loads(status.stdout)['job']['status'], 'running')
        self.assert_token_private(client, job_id)
        self.answer(client, packet, {'verdict': 'ready'})
        rejected = self.wait_event(client, 'answer_rejected')
        self.assertEqual(rejected['packet_id'], packet['packet_id'])
        self.answer(client, packet, answer_for(packet, analysis_blocked=True))
        self.assertEqual(self.wait_event(client, 'answer_accepted')['packet_id'], packet['packet_id'])
        review = self.wait_packet(client, 'spec-review')
        self.answer(client, review)
        finished = self.wait_event(client, 'finished')
        self.assertEqual(client.wait(), 2)
        self.assertEqual(finished['job']['status'], 'failed')
        self.assertEqual(finished['job']['workflow']['verdict'], 'blocked')
        self.assertFalse(any(finished['job']['acceptance'].values()))
        self.assertNotIn('result', finished['job'])
        stages = [p['stage'] for e in client.events if e.get('type') == 'packets' for p in e['packets']]
        self.assertNotIn('generation', stages)
        self.assertIsNone(self.bridge.active)
        self.assert_token_private(client, job_id)

    def test_attach_keeps_token_in_memory_and_eof_cancels_until_finished(self):
        created = self.create_agent_job()
        unauthorized = self.start(attach={**created, 'agent_token': created['agent_token'] + 'invalid'})
        self.assertEqual(unauthorized.wait(), 1)
        self.assertEqual(self.bridge.snapshot(created['job_id'])['status'], 'running')
        self.assertFalse(self.bridge.snapshot(created['job_id'])['finished'])
        self.assert_token_private(unauthorized, created['job_id'])
        client = self.start(attach=created)
        self.assertEqual(self.wait_event(client, 'started')['job_id'], created['job_id'])
        self.wait_packet(client, 'analysis')
        self.assert_token_private(client, created['job_id'])
        client.process.stdin.close()
        self.assert_cancelled(client, self.wait_event(client, 'finished'))
        cancelled = self.once('cancel', created['job_id'])
        self.assertEqual(cancelled.returncode, 0)
        state = json.loads(cancelled.stdout)
        self.assertEqual(state['type'], 'cancel')
        self.assertTrue(state['job']['finished'])
        self.assertEqual(state['job']['status'], 'cancelled')

    @unittest.skipUnless(os.name == 'posix', 'POSIX SIGINT cleanup check')
    def test_sigint_cancels_created_workflow_until_finished(self):
        client = self.start()
        job_id = self.wait_event(client, 'started')['job_id']
        self.wait_packet(client, 'analysis')
        client.process.send_signal(signal.SIGINT)
        self.assert_cancelled(client, self.wait_event(client, 'finished'))
        self.assertEqual(self.bridge.snapshot(job_id)['status'], 'cancelled')

    def test_nonloopback_or_nonroot_endpoint_is_rejected(self):
        for url in ('http://example.invalid', 'https://127.0.0.1',
                    'http://127.0.0.1@outside.invalid', self.url + '/prefix', self.url + '?token=forbidden'):
            with self.subTest(url=url):
                result = self.once('doctor', url=url)
                self.assertEqual(result.returncode, 1)
        self.assertIsNone(self.bridge.active)

    def test_authenticated_packet_redirect_never_reaches_another_server(self):
        received, authenticated = [], []
        created = self.create_agent_job()

        class Sink(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                received.append(True)
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'{}')

        destination = self.serve(Sink)

        class RedirectPackets(bridge_module.Handler):
            def do_GET(self):
                if self.path.endswith('/packets'):
                    authenticated.append(self.headers.get('Authorization') == 'Bearer ' + created['agent_token'])
                    if len(authenticated) == 1:
                        # Prove ownership with the real server before testing an
                        # authenticated polling failure and cleanup.
                        return super().do_GET()
                    self.send_response(302)
                    self.send_header('Location', destination + '/leak')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                else:
                    super().do_GET()

        redirector = self.serve(RedirectPackets)
        client = self.start(attach=created, url=redirector)
        self.assertEqual(client.wait(timeout=15), 1)
        self.assertEqual(received, [])
        self.assertEqual(authenticated, [True, True])
        self.assertTrue(self.bridge.snapshot(created['job_id'])['finished'])
        self.assertEqual(self.bridge.snapshot(created['job_id'])['status'], 'cancelled')
        self.assertIsNone(self.bridge.active)
        self.assert_token_private(client, created['job_id'])

    def test_prepare_preserves_chinese_brief_sources_and_rejects_invalid_source(self):
        source = {'name': 'FB_Original.scl', 'content': 'FUNCTION_BLOCK FB_Original\n// 原程序保持\nEND_FUNCTION_BLOCK'}
        brief = {**request()['brief'], 'validation_profile': '', 'source_files': [source]}
        path = self.folder / 'brief.json'
        path.write_text(json.dumps({'brief': brief, 'states': []}, ensure_ascii=False))
        prepared = self.once('prepare', '--brief', str(path))
        self.assertEqual(prepared.returncode, 0)
        frozen = json.loads(prepared.stdout)
        self.assertNotIn('type', frozen)
        self.assertEqual(frozen['schema_version'], 1)
        self.assertEqual(frozen['brief'], brief)
        self.assertEqual(frozen['states'], [])
        self.assertTrue(frozen['request_id'])
        encoded = json.dumps({'brief': brief, 'states': []}, ensure_ascii=False, separators=(',', ':'))
        self.assertEqual(frozen['request_fingerprint'], hashlib.sha256(encoded.encode()).hexdigest())
        bridge_module.validate_request(frozen)
        path.write_text(json.dumps({'requirement': '尚未确认工艺反馈和停止条件，必须先向用户明确。'}, ensure_ascii=False))
        minimal = self.once('prepare', '--brief', str(path))
        self.assertEqual(minimal.returncode, 0)
        minimum = json.loads(minimal.stdout)
        for key in ('name', 'block_name', 'flow', 'io_text', 'constraints'):
            self.assertEqual(minimum['brief'][key], '')
        path.write_text(json.dumps({**brief, 'source_files': [{**source, 'name': '../escape.scl'}]}))
        invalid = self.once('prepare', '--brief', str(path))
        self.assertEqual(invalid.returncode, 1)
        self.assertIsNone(self.bridge.active)

    @unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for CLI/controller/native checks')
    def test_stdio_answers_drive_real_native_lad_and_scl_to_reviewed_draft(self):
        client = self.start()
        job_id = self.wait_event(client, 'started')['job_id']
        seen, stages = set(), []
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            event = client.next(max(.01, deadline - time.monotonic()))
            kind = event.get('type')
            self.assertNotIn(kind, ('error', 'answer_rejected', 'invalid_json'))
            if kind == 'finished':
                final = event['job']
                break
            if kind == 'packets':
                self.assertEqual(event['job_id'], job_id)
                for packet in event['packets']:
                    if packet['packet_id'] not in seen:
                        seen.add(packet['packet_id'])
                        stages.append(packet['stage'])
                        self.answer(client, packet)
        else:
            self.fail('CLI/controller did not finish the bounded native workflow')
        self.assertEqual(client.wait(), 0)
        self.assertEqual(stages[:3], ['analysis', 'spec-review', 'generation'])
        self.assertEqual(set(stages[3:5]), {'semantic-review', 'interface-review'})
        self.assertEqual(stages[-1], 'final-review')
        self.assertEqual(final['status'], 'complete')
        self.assertEqual(final['workflow']['verdict'], 'reviewed_draft')
        self.assertEqual(final['workflow']['industrial_acceptance'], 'not_run')
        self.assertEqual(final['acceptance'], {'scl_compile': True, 'scl_behavior': True,
                                              'lad_scl_compare': True, 'tia_compile': False})
        self.assertEqual(final['verification']['comparison']['bounded_calls'], 16384)
        self.assertIsNone(self.bridge.active)
        self.assert_token_private(client, job_id)


if __name__ == '__main__':
    unittest.main()
