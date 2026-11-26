#!/usr/bin/env python3
"""Persistent JSON-lines control of the local PLC workflow; no model CLI or scheduler.

The Agent keeps stdin open, reads packets, and submits one answer per JSON line.
EOF, Ctrl-C, and recoverable process errors cancel the owned job before exiting.
Session credentials are accepted through stdin and kept only in process memory.
"""

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


INPUT_LIMIT = 1_000_000
FILE_LIMIT = 8_000_000
RESPONSE_LIMIT = 16_000_000
HTTP_TIMEOUT = 2
CLEANUP_SECONDS = 8
LOOPBACK = ('127.0.0.1', 'localhost', '::1')


class CliError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def contains_secret(value, secret):
    if not secret:
        return False
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str) and secret in item:
            return True
        if isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return False


def emit(value, secret=''):
    if contains_secret(value, secret):
        raise CliError('A local response contained the session credential and was discarded.')
    print(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False), flush=True)


def parse_json(raw):
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate field')
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=object_pairs)
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CliError('Input must be valid finite JSON without duplicate fields.') from None


def read_json_file(path):
    try:
        with Path(path).open('rb') as source:
            raw = source.read(FILE_LIMIT + 1)
    except OSError:
        raise CliError('Cannot read the requested JSON file.') from None
    if len(raw) > FILE_LIMIT:
        raise CliError('The JSON file exceeds the size limit.')
    return parse_json(raw)


def validate_request(value):
    spec = importlib.util.spec_from_file_location('plc_agent_bridge', Path(__file__).with_name('local-server.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.validate_request(value)
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise CliError('Invalid PLC request; check the brief, source names, profile, and fingerprint.') from None
    return value


def prepare_request(path):
    data = read_json_file(path)
    if not isinstance(data, dict):
        raise CliError('The brief must be a JSON object.')
    supplied, states = (data.get('brief'), data.get('states', [])) if 'brief' in data else (data, [])
    if not isinstance(supplied, dict):
        raise CliError('The brief must be a JSON object.')
    brief = {key: '' for key in ('name', 'block_name', 'requirement', 'flow', 'io_text', 'constraints')}
    brief.update(supplied)
    content = json.dumps({'brief': brief, 'states': states}, ensure_ascii=False, separators=(',', ':'))
    return validate_request({'schema_version': 1, 'request_id': str(uuid.uuid4()),
        'request_fingerprint': hashlib.sha256(content.encode()).hexdigest(), 'brief': brief, 'states': states})


def server_url(value):
    if (not isinstance(value, str) or len(value) > 2048
            or any(ord(char) < 33 or ord(char) > 126 for char in value)
            or any(char in value for char in ('?', '#', '\\'))):
        raise CliError('Use an HTTP loopback root URL without credentials, query, or fragment.')
    try:
        parsed = urllib.parse.urlsplit(value)
        if (parsed.scheme != 'http' or parsed.hostname not in LOOPBACK
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ('', '/') or parsed.port == 0):
            raise ValueError('invalid local URL')
    except ValueError:
        raise CliError('Use an HTTP loopback root URL without credentials, query, or fragment.') from None
    return value.rstrip('/')


def job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise CliError('Invalid local job identifier.')
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalApi:
    def __init__(self, url):
        self.url = server_url(url)
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))

    def call(self, path, data=None, token=None, timeout=HTTP_TIMEOUT, details=False):
        body = None if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        if body is not None and len(body) > INPUT_LIMIT:
            raise CliError('The local API request exceeds the size limit.', 400)
        headers = {'Content-Type': 'application/json', 'X-PLC-Workspace': '1'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(self.url + path, data=body, headers=headers)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(RESPONSE_LIMIT + 1)
        except urllib.error.HTTPError as error:
            status = error.code
            detail = ''
            if details:
                try:
                    payload = parse_json(error.read(16000))
                    if isinstance(payload, dict) and isinstance(payload.get('error'), str):
                        detail = ' ' + payload['error'][:3000]
                except (CliError, OSError):
                    pass
            error.close()
            if 300 <= status < 400:
                raise CliError('Local API redirects are not followed.', status) from None
            raise CliError('Local API rejected the request (HTTP ' + str(status) + ').' + detail, status) from None
        except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError):
            raise CliError('Cannot reach the local PLC workspace; check its address and process.') from None
        if len(raw) > RESPONSE_LIMIT:
            raise CliError('The local API response exceeds the size limit.')
        value = parse_json(raw)
        if not isinstance(value, dict):
            raise CliError('The local API response must be a JSON object.')
        if token and contains_secret(value, token):
            raise CliError('A local response contained the session credential and was discarded.')
        return value


@contextmanager
def quiet_stdin():
    """Protect attach credentials from a PTY's automatic input echo."""
    previous = None
    if sys.stdin.isatty():
        try:
            import termios
            previous = termios.tcgetattr(sys.stdin.fileno())
            hidden = previous.copy()
            hidden[3] &= ~(termios.ECHO | termios.ECHONL)
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, hidden)
        except (ImportError, OSError):
            raise CliError('Cannot disable terminal echo; use a writable stdin pipe.') from None
    try:
        yield
    finally:
        if previous is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, previous)
            except OSError:
                pass


def stdin_queue():
    messages = queue.Queue(maxsize=16)

    def deliver(raw):
        try:
            messages.put(('value', parse_json(raw)))
        except CliError:
            messages.put(('invalid', None))

    def read():
        buffered, oversized = b'', False
        try:
            while True:
                # Raw fd reads avoid leaving a daemon thread holding Python's
                # buffered-stdin lock when a finished workflow exits.
                chunk = os.read(sys.stdin.fileno(), 16384)
                if not chunk:
                    if oversized:
                        messages.put(('invalid', None))
                    elif buffered:
                        deliver(buffered)
                    messages.put(('eof', None))
                    return
                pieces = chunk.split(b'\n')
                for index, piece in enumerate(pieces):
                    if not oversized:
                        if len(buffered) + len(piece) > INPUT_LIMIT:
                            buffered, oversized = b'', True
                        else:
                            buffered += piece
                    if index < len(pieces) - 1:
                        if oversized:
                            messages.put(('invalid', None))
                        else:
                            deliver(buffered)
                        buffered, oversized = b'', False
        except (OSError, ValueError):
            messages.put(('eof', None))

    threading.Thread(target=read, daemon=True).start()
    return messages


def cancel_and_wait(api, identifier):
    deadline = time.monotonic() + CLEANUP_SECONDS
    api.call('/api/jobs/' + identifier + '/cancel', {}, timeout=min(HTTP_TIMEOUT, CLEANUP_SECONDS))
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        snapshot = api.call('/api/jobs/' + identifier, timeout=min(HTTP_TIMEOUT, remaining))
        if snapshot.get('finished') is True:
            return snapshot
        time.sleep(min(.1, max(0, deadline - time.monotonic())))
    raise CliError('Cancellation was requested, but local cleanup did not finish within 8 seconds.')


def run_workflow(args, api):
    identifier, token, owned, finished = None, '', False, False
    final_code, failure = 2, None

    def finish(snapshot):
        nonlocal finished, final_code
        emit({'type': 'finished', 'job_id': identifier, 'job': snapshot}, token)
        finished = True
        final_code = 0 if snapshot.get('status') == 'complete' else 2

    def interrupt(_signal, _frame):
        raise KeyboardInterrupt

    previous_signals = {name: signal.signal(name, interrupt) for name in (signal.SIGINT, signal.SIGTERM)}
    try:
        with quiet_stdin():
            incoming = stdin_queue()
            if args.attach:
                kind, session = incoming.get()
                if (kind != 'value' or not isinstance(session, dict)
                        or set(session) != {'job_id', 'agent_token'}):
                    raise CliError('Attach requires one stdin JSON line with job_id and agent_token.')
                identifier = job_id(session['job_id'])
                token = session['agent_token']
                if (not isinstance(token, str) or not 1 <= len(token) <= 512
                        or any(ord(char) < 33 or ord(char) > 126 for char in token)):
                    token = ''
                    raise CliError('Invalid Agent credential format.')
                api.call('/api/agent/jobs/' + identifier + '/packets', token=token)
                owned = True  # A bad attach token must never cancel somebody else's job.
            else:
                value = read_json_file(args.request)
                value = value.get('request', value) if isinstance(value, dict) else value
                session = api.call('/api/agent/jobs', {'request': validate_request(value)})
                identifier = job_id(session.get('job_id'))
                owned = True
                token = session.get('agent_token')
                if (not isinstance(token, str) or not 1 <= len(token) <= 512
                        or any(ord(char) < 33 or ord(char) > 126 for char in token)):
                    token = ''
                    raise CliError('The workspace returned an invalid Agent credential.')
            emit({'type': 'started', 'job_id': identifier}, token)
            seen, next_poll = set(), 0
            while True:
                if time.monotonic() >= next_poll:
                    pending = api.call('/api/agent/jobs/' + identifier + '/packets', token=token)
                    if pending.get('finished') is True:
                        finish(api.call('/api/jobs/' + identifier))
                        break
                    packets = pending.get('packets')
                    if not isinstance(packets, list) or any(not isinstance(item, dict)
                            or not isinstance(item.get('packet_id'), str)
                            or not re.fullmatch(r'[0-9a-f]{32}', item['packet_id']) for item in packets):
                        raise CliError('The workspace returned invalid stage packets.')
                    fresh = [item for item in packets if item['packet_id'] not in seen]
                    if fresh:
                        emit({'type': 'packets', 'job_id': identifier, 'packets': fresh}, token)
                        seen.update(item['packet_id'] for item in fresh)
                    next_poll = time.monotonic() + args.poll_interval
                try:
                    kind, value = incoming.get(timeout=max(0, next_poll - time.monotonic()))
                except queue.Empty:
                    continue
                if kind == 'eof' or (kind == 'value' and value == {'command': 'cancel'}):
                    break
                event = {'type': 'answer_rejected', 'job_id': identifier}
                if isinstance(value, dict) and isinstance(value.get('packet_id'), str) and re.fullmatch(
                        r'[0-9a-f]{32}', value['packet_id']):
                    event['packet_id'] = value['packet_id']
                if (kind != 'value' or not isinstance(value, dict)
                        or set(value) != {'packet_id', 'input_sha256', 'answer'}):
                    emit({**event, 'error': 'Submit packet_id, input_sha256, and answer as one JSON object.'}, token)
                    continue
                if contains_secret(value, token):
                    emit({**event, 'error': 'A stage answer must not contain the session credential.'}, token)
                    continue
                try:
                    accepted = api.call('/api/agent/jobs/' + identifier + '/answers', value, token)
                except CliError as error:
                    if error.status not in (400, 409):
                        raise
                    emit({**event, 'error': str(error)}, token)
                    continue
                if accepted.get('accepted') is not True:
                    raise CliError('The workspace did not acknowledge the stage answer.')
                emit({'type': 'answer_accepted', 'job_id': identifier, 'packet_id': value['packet_id']}, token)
    except KeyboardInterrupt:
        pass
    except (CliError, BrokenPipeError) as error:
        failure = str(error) if isinstance(error, CliError) else 'The output stream closed; cancelling the local job.'
    except Exception:
        failure = 'The CLI could not continue; the local job will be cancelled.'
    finally:
        # A second terminal signal must not interrupt the short cleanup window.
        for name in previous_signals:
            signal.signal(name, signal.SIG_IGN)
        if failure:
            try:
                emit({'type': 'error', 'error': failure}, token)
            except (CliError, BrokenPipeError):
                pass
        if owned and not finished:
            try:
                finish(cancel_and_wait(api, identifier))
            except (CliError, OSError, ValueError, TypeError):
                failure = 'Could not confirm local job cleanup; inspect the job with status.'
                try:
                    emit({'type': 'error', 'job_id': identifier, 'error': failure}, token)
                except (CliError, BrokenPipeError):
                    pass
        for name, previous in previous_signals.items():
            signal.signal(name, previous)
    return 1 if failure else final_code


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal error can echo arbitrary argv, including a pasted token.
        raise CliError('Invalid CLI arguments; use --help for the command syntax.')


def run_simulation(args, api):
    """Use the same typed operations as the visual editor, with no model key."""
    body = {}
    if args.input:
        if args.input == '-':
            raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
            if len(raw) > INPUT_LIMIT:
                raise CliError('The simulation request exceeds the size limit.')
            body = parse_json(raw)
        else:
            body = read_json_file(args.input)
    if not isinstance(body, dict):
        raise CliError('The simulation request must be a JSON object.')
    if args.session:
        identifier = job_id(args.session)
        if body.get('session', identifier) != identifier:
            raise CliError('The file and --session refer to different sessions.')
        body['session'] = identifier
    action = {'fault': 'inject_fault', 'run-case': 'run_case',
              'trace': 'export_trace'}.get(args.action, args.action)
    result = api.call('/api/sim/' + action, body, timeout=180, details=True)
    if args.output:
        try:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        except OSError:
            raise CliError('Cannot write the simulation result file.') from None
        emit({'type': 'simulation', 'action': action, 'output': str(destination),
              'status': result.get('status'), 'session': result.get('session'),
              'source_sha256': result.get('source_sha256'),
              'first_failure': result.get('first_failure') or result.get('first_counterexample')})
    else:
        emit({'type': 'simulation', 'action': action, 'result': result})
    if action == 'export_trace':
        return 0  # Export delivery succeeds even when observations confer no verdict.
    return 1 if result.get('status') == 'fail' else 2 if result.get('status') in ('unknown', 'not_run') else 0


def main():
    parser = JsonParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8766', help='HTTP loopback root URL')
    parser.add_argument('--poll-interval', type=float, default=.25, help='Polling seconds, 0.1 to 5')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='Read local capabilities')
    simulation = commands.add_parser('simulate', help='Assemble, execute and diagnose a source-bound simulated cell')
    simulation.add_argument('action', choices=('catalog', 'templates', 'create', 'inspect', 'step',
        'inject_fault', 'fault', 'run_case', 'run-case', 'export_trace', 'trace', 'close',
        'integrations', 'oip_catalog', 'oip_assemble', 'oip_test', 'oip_self_test'))
    simulation.add_argument('--input', help='Operation JSON file, or - to read one JSON object from stdin')
    simulation.add_argument('--session', help='Existing simulation session ID')
    simulation.add_argument('--output', help='Write the complete result JSON and print a compact receipt')
    prepare = commands.add_parser('prepare', help='Build a bound request from an explicit brief')
    prepare.add_argument('--brief', required=True)
    for command in ('status', 'cancel'):
        child = commands.add_parser(command)
        child.add_argument('job_id')
    workflow = commands.add_parser('workflow', help='Keep stdin open and answer JSON stage packets')
    source = workflow.add_mutually_exclusive_group(required=True)
    source.add_argument('--request')
    source.add_argument('--attach', action='store_true')
    try:
        args = parser.parse_args()
        if not math.isfinite(args.poll_interval) or not .1 <= args.poll_interval <= 5:
            raise CliError('Polling interval must be between 0.1 and 5 seconds.')
        api = LocalApi(args.url)
        if args.command == 'prepare':
            emit(prepare_request(args.brief))
        elif args.command == 'doctor':
            emit({'type': 'doctor', 'capabilities': api.call('/api/capabilities')})
        elif args.command == 'status':
            identifier = job_id(args.job_id)
            emit({'type': 'status', 'job_id': identifier, 'job': api.call('/api/jobs/' + identifier)})
        elif args.command == 'cancel':
            identifier = job_id(args.job_id)
            emit({'type': 'cancel', 'job_id': identifier, 'job': cancel_and_wait(api, identifier)})
        elif args.command == 'simulate':
            return run_simulation(args, api)
        else:
            return run_workflow(args, api)
        return 0
    except (CliError, KeyboardInterrupt) as error:
        emit({'type': 'error', 'error': str(error) if isinstance(error, CliError) else 'Command interrupted.'})
        return 1
    except Exception:
        emit({'type': 'error', 'error': 'The local CLI command failed.'})
        return 1


if __name__ == '__main__':
    sys.exit(main())
