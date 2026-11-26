"""Public HTTP/CLI and engineering identity checks, independent of model answers."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sim_http_bridge_test', HERE / 'local-server.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def engineering():
    brief = {key: '' for key in ('name', 'block_name', 'requirement', 'flow', 'io_text', 'constraints')}
    brief.update(name='current source test', block_name='FB_ConveyorPack',
                 requirement='输送到位停止，等待十二次调用后超时。', validation_profile='conveyor-12-v1')
    fingerprint = hashlib.sha256(json.dumps({'brief': brief, 'states': []},
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    request = {'schema_version': 1, 'request_id': 'current-source',
               'request_fingerprint': fingerprint, 'brief': brief, 'states': []}
    source = (HERE.parents[1] / 'plans/plc-generation-ui/user-eval/candidates/FB_ConveyorPack.scl').read_text()
    result = {'schema_version': 1, 'request_id': request['request_id'],
        'request_fingerprint': fingerprint, 'summary': 'Source identity fixture',
        'questions': [], 'states': [], 'io': [], 'lad_networks': [], 'checks': [],
        'scl_files': [{'name': 'FB_ConveyorPack.scl', 'content': source}]}
    return {'kind': 'agent_candidate', 'request': request, 'result': result,
            'verification': {'status': 'pass'}, 'acceptance': {'industrial': True}}


class EngineeringHandoffTests(unittest.TestCase):
    def convert(self, value):
        return bridge.simulation_bridge.engineering_program(
            value, bridge.validate_request, bridge.validate_workflow_artifact)

    def test_captures_exact_current_source_but_never_saved_verdicts(self):
        original = engineering()
        program = self.convert(original)
        self.assertEqual(program['source'], original['result']['scl_files'][0]['content'])
        self.assertEqual(program['request_fingerprint'], original['request']['request_fingerprint'])
        self.assertEqual(set(program), {'profile', 'source', 'filename', 'request_id', 'request_fingerprint'})
        original['result']['scl_files'][0]['content'] = 'changed after import'
        self.assertNotEqual(program['source'], original['result']['scl_files'][0]['content'])

    def test_rejects_stale_request_and_result(self):
        for part in ('request', 'result'):
            value = engineering()
            value[part]['request_fingerprint'] = '0' * 64
            with self.assertRaises(ValueError):
                self.convert(value)

    def test_unresolved_or_multi_file_sources_are_not_silently_substituted(self):
        value = engineering()
        value['result']['questions'] = ['尚未确定停止规则']
        with self.assertRaises(ValueError):
            self.convert(value)
        value = engineering()
        value['result']['scl_files'].append({'name': 'Other.scl', 'content': 'other'})
        with self.assertRaises(ValueError):
            self.convert(value)


class PublicSimulationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='plc-sim-http-')
        self.server = bridge.ThreadingHTTPServer(('127.0.0.1', 0), bridge.Handler)
        self.server.bridge = bridge.GenerationBridge(runtime_root=self.directory.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.bridge.simulation.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()

    def cli(self, action, body=None, extra=()):
        command = [sys.executable, str(HERE / 'plc-agent.py'), '--url', self.url,
                   'simulate', action, *extra]
        if body is not None:
            command += ['--input', '-']
        completed = subprocess.run(command, input=None if body is None else json.dumps(body),
            text=True, capture_output=True, timeout=180)
        return completed.returncode, json.loads(completed.stdout)

    def test_catalog_and_templates_are_accessible_without_model_credentials(self):
        code, envelope = self.cli('catalog')
        self.assertEqual(code, 0, envelope)
        self.assertTrue(envelope['result']['components'])
        with urlopen(self.url + '/api/capabilities') as response:
            capabilities = json.load(response)
        self.assertFalse(capabilities['ready'])
        self.assertTrue(capabilities['simulation']['engineering_import'])
        code, templates = self.cli('templates')
        self.assertEqual(code, 0, templates)
        self.assertTrue(templates['result']['templates'])

    def test_cross_origin_mutation_is_rejected(self):
        request = Request(self.url + '/api/sim/create', data=b'{}', headers={
            'Content-Type': 'application/json', 'X-PLC-Workspace': '1',
            'Origin': 'https://unrelated.example'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 403)

    def test_cli_keeps_invalid_engineering_diagnostic(self):
        code, envelope = self.cli('create', {'engineering': {}})
        self.assertNotEqual(code, 0)
        self.assertIn('请求版本错误', envelope['error'])

    @unittest.skipUnless(os.environ.get('SIM_IEC2C') and os.environ.get('SIM_MATIEC_LIB'),
                         'native matiec toolchain is required')
    def test_current_wrong_candidate_is_executed_and_rejected_by_twelve_scan_case(self):
        # This historical eight-call candidate must never inherit its imported
        # fake pass when checked against the explicitly selected twelve-call case.
        value = engineering()
        code, envelope = self.cli('run-case', {'template': 'conveyor-12-v1',
            'engineering': value, 'case': 'jam'})
        self.assertEqual(code, 1, envelope)
        result = envelope['result']
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['source_sha256'], hashlib.sha256(
            value['result']['scl_files'][0]['content'].encode()).hexdigest())
        failure = result['first_failure']
        self.assertEqual(failure['scan'], 9)
        self.assertEqual(failure['expected'], 0)
        self.assertEqual(failure['actual'], 1)


if __name__ == '__main__':
    unittest.main()
