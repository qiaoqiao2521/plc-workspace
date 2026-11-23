"""Loopback HTTP fixtures only: no paid API, model-quality, or PLC acceptance claim."""

import concurrent.futures
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('model_api', Path(__file__).with_name('model-api.py'))
model_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_api)

FIXTURE_KEY = 'sk-local-fixture-not-a-real-api-key'


def packet(stage='analysis', label='fixture'):
    return {'stage': stage, 'instructions': 'Review the PLC requirement. Keep unknowns explicit.',
            'data': {'requirement': label},
            'schema': {'type': 'object', 'properties': {'verdict': {'type': 'string'}},
                       'required': ['verdict'], 'additionalProperties': False}}


def completion(content=None, **choice_changes):
    choice = {'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant',
              'content': json.dumps({'verdict': 'unknown'}) if content is None else content,
              'refusal': None}}
    choice.update(choice_changes)
    return {'id': 'fixture-completion', 'choices': [choice]}


class HttpFixture:
    """A real local HTTP server with controllable synthetic completion responses."""

    def __init__(self):
        self.requests = []
        self.respond = lambda request: (200, {}, json.dumps(completion()).encode())
        self.lock = threading.Lock()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *args):
                pass

            def do_POST(self):
                request = {'path': self.path, 'headers': dict(self.headers),
                           'body': self.rfile.read(int(self.headers.get('Content-Length', '0')))}
                with fixture.lock:
                    fixture.requests.append(request)
                status, headers, body = fixture.respond(request)
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.base_url = 'http://127.0.0.1:' + str(self.server.server_address[1]) + '/v1'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def set_response(self, response, *, status=200, headers=None):
        raw = response if isinstance(response, bytes) else json.dumps(response).encode()
        self.respond = lambda _request: (status, headers or {}, raw)

    def config(self, **changes):
        return {'base_url': self.base_url, 'model': 'fixture-model',
                'api_key': FIXTURE_KEY, **changes}


class ConfigTests(unittest.TestCase):
    def test_config_defaults_copy_and_public_redaction(self):
        source = {'base_url': 'https://provider.invalid/v1/', 'model': ' model ',
                  'api_key': FIXTURE_KEY}
        config = model_api.normalize_config(source)
        self.assertEqual(config['base_url'], 'https://provider.invalid/v1')
        self.assertEqual(config['model'], 'model')
        self.assertEqual(config['timeout_seconds'], 120)
        self.assertEqual(config['response_format'], 'json_object')
        self.assertEqual(source['model'], ' model ')
        safe = model_api.public_config(config)
        self.assertTrue(safe['api_key_set'])
        self.assertNotIn('api_key', safe)
        self.assertNotIn(FIXTURE_KEY, json.dumps(safe))

    def test_anonymous_local_endpoints_and_remote_https(self):
        for url in ('http://127.0.0.1:9000/v1', 'http://localhost/v1', 'http://[::1]:8080/v1',
                    'https://localhost/v1'):
            with self.subTest(url=url):
                config = model_api.normalize_config({'base_url': url, 'model': 'local'})
                self.assertEqual(config['api_key'], '')
        with self.assertRaisesRegex(model_api.ApiError, 'requires an API key'):
            model_api.normalize_config({'base_url': 'https://provider.invalid/v1', 'model': 'm'})

    def test_invalid_config_never_echoes_values(self):
        valid = {'base_url': 'https://provider.invalid/v1', 'model': 'fixture', 'api_key': FIXTURE_KEY}
        cases = [{'base_url': url} for url in (
            'http://provider.invalid/v1', 'http://192.168.0.1/v1', 'http://127.0.0.1.evil/v1',
            'file:///v1', 'https://user:secret@provider.invalid/v1',
            'https://provider.invalid/v1?key=' + FIXTURE_KEY,
            'https://provider.invalid/v1#' + FIXTURE_KEY,
            'https://provider.invalid:70000/v1', 'https://provider.invalid:0/v1',
            'https://provider.invalid/\npath', 'https://provider.invalid\\@localhost/v1',
            'https://%6cocalhost/v1', '',
        )]
        cases += [{'timeout_seconds': value} for value in
                  (0, 601, 10 ** 1000, float('nan'), float('inf'), True, '120')]
        cases += [{'api_key': '\n' + FIXTURE_KEY}, {'api_key': 'key with spaces'},
                  {'model': ''}, {'model': FIXTURE_KEY}, {'response_format': 'automatic'}, {'tools': []}]
        for changes in cases:
            with self.subTest(fields=list(changes)):
                with self.assertRaises(model_api.ApiError) as caught:
                    model_api.normalize_config({**valid, **changes})
                self.assertNotIn(FIXTURE_KEY, str(caught.exception))
        for invalid in (None, [], 'config'):
            with self.assertRaises(model_api.ApiError):
                model_api.normalize_config(invalid)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = HttpFixture()
        self.addCleanup(self.fixture.close)

    def dispatch(self, value=None, **config):
        value = value or packet()
        return model_api.ApiDispatch(self.fixture.config(**config))(value['stage'], 'reviewer', value)

    def test_real_loopback_http_packet_binding_schema_and_secret_header(self):
        value = packet(label='停止优先；未知条件不得放行')
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            response = self.dispatch(value)
        request = self.fixture.requests[0]
        self.assertEqual(request['path'], '/v1/chat/completions')
        self.assertEqual(request['headers']['Authorization'], 'Bearer ' + FIXTURE_KEY)
        payload = json.loads(request['body'])
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual(payload['n'], 1)
        self.assertFalse(payload['stream'])
        self.assertNotIn('tools', payload)
        self.assertEqual([m['role'] for m in payload['messages']], ['system', 'user'])
        self.assertEqual(json.loads(payload['messages'][1]['content']), value['data'])
        schema_text = payload['messages'][0]['content'].split('JSON Schema:\n', 1)[1]
        self.assertEqual(json.loads(schema_text), value['schema'])
        self.assertIn(value['instructions'], payload['messages'][0]['content'])
        expected_hash = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                                 separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(response, {'input_sha256': expected_hash, 'answer': {'verdict': 'unknown'}})
        self.assertNotIn(FIXTURE_KEY, request['body'].decode())
        self.assertNotIn(FIXTURE_KEY, json.dumps(response))
        self.assertEqual(output.getvalue(), '')

    def test_anonymous_model_and_explicit_no_json_mode(self):
        self.dispatch(api_key='', response_format='none')
        request = self.fixture.requests[0]
        self.assertNotIn('Authorization', request['headers'])
        self.assertNotIn('response_format', json.loads(request['body']))

    def test_concurrent_stages_have_no_shared_conversation(self):
        dispatch = model_api.ApiDispatch(self.fixture.config())
        values = [packet(stage='semantic-review', label='first-stage-only'),
                  packet(stage='interface-review', label='second-stage-only')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(dispatch, item['stage'], 'reviewer', item) for item in values]
            responses = [future.result(timeout=5) for future in futures]
        self.assertNotEqual(responses[0]['input_sha256'], responses[1]['input_sha256'])
        sent = [json.loads(item['body']) for item in self.fixture.requests]
        self.assertEqual(len(sent), 2)
        for item in sent:
            self.assertEqual(len(item['messages']), 2)
        self.assertEqual({json.loads(item['messages'][1]['content'])['requirement'] for item in sent},
                         {'first-stage-only', 'second-stage-only'})

    def test_http_error_is_sanitized_and_not_retried(self):
        self.fixture.set_response({'error': {'message': FIXTURE_KEY + ' provider-private-detail'}}, status=401)
        with self.assertRaisesRegex(model_api.ApiError, 'HTTP 401') as caught:
            self.dispatch()
        self.assertNotIn(FIXTURE_KEY, str(caught.exception))
        self.assertNotIn('provider-private-detail', str(caught.exception))
        self.assertEqual(len(self.fixture.requests), 1)

    def test_redirect_never_sends_credentials_to_target(self):
        destination = HttpFixture()
        self.addCleanup(destination.close)
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.fixture.set_response(b'', status=status,
                    headers={'Location': destination.base_url + '/chat/completions'})
                with self.assertRaisesRegex(model_api.ApiError, 'redirects'):
                    self.dispatch()
        self.assertEqual(destination.requests, [])

    def test_refusal_truncation_tools_and_invalid_envelopes_fail_closed(self):
        cases = [completion(finish_reason=reason) for reason in
                 ('length', 'content_filter', 'tool_calls', 'function_call', None)]
        for changes in ({'refusal': 'No'}, {'tool_calls': [{'id': 'unexpected-tool'}]},
                        {'function_call': {}}, {'role': 'tool'}, {'content': None},
                        {'content': [{'type': 'refusal', 'refusal': 'No'}]}):
            item = completion()
            item['choices'][0]['message'].update(changes)
            cases.append(item)
        cases += [{'choices': []}, {'choices': completion()['choices'] * 2},
                  {'choices': [None]}, [], {'error': 'provider error'},
                  completion(index=1)]
        for response in cases:
            with self.subTest(response_type=type(response).__name__):
                self.fixture.set_response(response)
                with self.assertRaises(model_api.ApiError):
                    self.dispatch()

    def test_invalid_json_and_ambiguous_values_are_not_repaired(self):
        for content in ('```json\n{}\n```', '{} trailing', '[]', 'null',
                        '{"verdict":"pass","verdict":"fail"}', '{"v":NaN}',
                        '{"v":1e999}', '{"v":"\\ud800"}'):
            with self.subTest(content=content):
                self.fixture.set_response(completion(content))
                with self.assertRaises(model_api.ApiError):
                    self.dispatch()
        for raw in (b'not JSON ' + FIXTURE_KEY.encode(), b'{"choices":[],"choices":[]}', b'\xff'):
            self.fixture.set_response(raw)
            with self.assertRaises(model_api.ApiError) as caught:
                self.dispatch()
            self.assertNotIn(FIXTURE_KEY, str(caught.exception))

    def test_schema_validation_is_left_to_workflow(self):
        self.fixture.set_response(completion('{"unexpected_field":"untrusted"}'))
        self.assertEqual(self.dispatch()['answer'], {'unexpected_field': 'untrusted'})

    def test_echoed_credentials_are_discarded_including_json_escapes(self):
        for content in (json.dumps({'verdict': FIXTURE_KEY}),
                        '{"verdict":"' + ''.join('\\u%04x' % ord(c) for c in FIXTURE_KEY) + '"}'):
            self.fixture.set_response(completion(content))
            with self.assertRaisesRegex(model_api.ApiError, 'credential') as caught:
                self.dispatch()
            self.assertNotIn(FIXTURE_KEY, str(caught.exception))
        escaped_key = 'local-fixture-quoted"key\\value'
        self.fixture.set_response(completion(json.dumps({'verdict': escaped_key})))
        with self.assertRaisesRegex(model_api.ApiError, 'credential'):
            self.dispatch(api_key=escaped_key)

    def test_invalid_or_oversized_inputs_stop_before_network(self):
        invalid = [None, {}, {**packet(), 'stage': 'different'},
                   {**packet(), 'schema': []}, {**packet(), 'data': float('nan')}]
        dispatch = model_api.ApiDispatch(self.fixture.config())
        for value in invalid:
            with self.assertRaises(model_api.ApiError):
                dispatch('analysis', 'reviewer', value)
        with patch.object(model_api, 'MAX_PACKET_BYTES', 128):
            with self.assertRaisesRegex(model_api.ApiError, 'size limit'):
                self.dispatch()
        with self.assertRaisesRegex(model_api.ApiError, 'credential'):
            self.dispatch(packet(label=FIXTURE_KEY))
        escaped_key = 'local-fixture-quoted"key\\value'
        with self.assertRaisesRegex(model_api.ApiError, 'credential'):
            self.dispatch(packet(label=escaped_key), api_key=escaped_key)
        self.assertEqual(self.fixture.requests, [])

    def test_response_size_and_timeout_are_bounded(self):
        self.fixture.set_response(b' ' * 257)
        with patch.object(model_api, 'MAX_RESPONSE_BYTES', 256):
            with self.assertRaisesRegex(model_api.ApiError, 'size limit'):
                self.dispatch()
        def slow(_request):
            time.sleep(1.2)
            return 200, {}, json.dumps(completion()).encode()
        self.fixture.respond = slow
        started = time.monotonic()
        with self.assertRaisesRegex(model_api.ApiError, 'timed out'):
            self.dispatch(timeout_seconds=1)
        self.assertLess(time.monotonic() - started, 2)

    def test_network_error_never_echoes_exception_credentials(self):
        with patch.object(model_api.urllib.request.OpenerDirector, 'open',
                          side_effect=OSError(FIXTURE_KEY + ' private connection text')):
            with self.assertRaisesRegex(model_api.ApiError, 'connection failed') as caught:
                self.dispatch()
        self.assertNotIn(FIXTURE_KEY, str(caught.exception))
        self.assertNotIn('private connection text', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
