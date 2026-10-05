"""Loopback-only visible native PLC simulation, independent of AI generation."""
import argparse
import importlib.util
import json
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit
import uuid

spec = importlib.util.spec_from_file_location('conveyor_runtime', Path(__file__).with_name('conveyor-runtime.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Simulation:
    def __init__(self, runtime):
        self.runtime = runtime
        self.sessions = {}

    def new(self):
        now = time.monotonic()
        for key, session in list(self.sessions.items()):
            if now - session['last'] > 1800:
                self.runtime.destroy(session['handle'])
                del self.sessions[key]
        if len(self.sessions) >= 16:
            raise ValueError('最多 16 个会话；请关闭会话或等待闲置会话释放')
        key = str(uuid.uuid4())
        self.sessions[key] = {'handle': self.runtime.create(), 'scan': 0, 'position': 0, 'last': now}
        return {'session': key, 'source_sha256': self.runtime.source_hash,
                'normalized_sha256': self.runtime.normalized_hash,
                'candidate': '已记录 agy 输送草稿；仅部分扫描检查通过，未作工业验收',
                'engine': 'matiec → C → GCC → persistent FB', 'scan': 0, 'position': 0}

    def step(self, body):
        if not isinstance(body, dict) or set(body) != {'session', 'inputs', 'jam', 'sensor_failed'}:
            raise ValueError('Expected session, inputs, jam, sensor_failed')
        inputs = body['inputs']
        if not isinstance(inputs, dict) or set(inputs) != set(module.INPUTS[:-1]):
            raise ValueError('Expected Enable, Start, Stop, Reset')
        if any(type(x) is not bool for x in [*inputs.values(), body['jam'], body['sensor_failed']]):
            raise ValueError('All signals must be JSON booleans')
        s = self.sessions.get(body['session'])
        if s is None:
            raise ValueError('会话不存在；请重新载入工件')
        at_end = s['position'] >= 1 and not body['sensor_failed']
        # Sample sensors, execute exactly one FB call, then advance toy plant.
        sampled = {**inputs, 'AtEnd': at_end}
        outputs = self.runtime.scan(s['handle'], sampled)
        if outputs['Motor'] and not body['jam']:
            s['position'] = min(1, round(s['position'] + .2, 6))
        s['scan'] += 1
        s['last'] = time.monotonic()
        return {'scan': s['scan'], 'inputs': sampled, 'outputs': outputs, 'position': s['position']}

    def close(self, key):
        s = self.sessions.pop(key, None)
        if s:
            self.runtime.destroy(s['handle'])

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(module.ROOT / 'web/dist'), **kwargs)

    def reply(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/':
            self.path = '/simulation.html'
        # Do not expose source directories or directory listings.
        if urlsplit(self.path).path.endswith('/'):
            return self.reply(404, {'error': 'Not found'})
        return super().do_GET()

    def do_POST(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected or self.headers.get('Origin') not in (None, 'http://' + expected):
            return self.reply(403, {'error': 'Only same-origin loopback requests allowed'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048 or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Expected small JSON request')
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/simulation/new' and body == {}:
                return self.reply(200, self.server.simulation.new())
            if self.path == '/api/simulation/step':
                return self.reply(200, self.server.simulation.step(body))
            if self.path == '/api/simulation/close' and isinstance(body, dict) and set(body) == {'session'} and isinstance(body['session'], str):
                self.server.simulation.close(body['session'])
                return self.reply(200, {'closed': True})
            return self.reply(404, {'error': 'Not found'})
        except (ValueError, TypeError, KeyError) as e:
            return self.reply(400, {'error': str(e)})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--iec2c', type=Path, required=True)
    parser.add_argument('--matiec-lib', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='plc-visible-sim-') as folder:
        runtime = module.ConveyorRuntime(folder, args.iec2c.resolve(), args.matiec_lib.resolve())
        exported = module.ROOT / 'web/dist/simulation-source.scl'
        if not exported.exists() or module.hashlib.sha256(exported.read_bytes()).hexdigest() != runtime.source_hash:
            raise RuntimeError('Displayed source differs from execution source; rebuild web/dist')
        server = HTTPServer(('127.0.0.1', args.port), Handler)
        server.simulation = Simulation(runtime)
        print(f'Native PLC simulation: http://127.0.0.1:{args.port}/simulation.html', flush=True)
        try:
            server.serve_forever()
        finally:
            for key in list(server.simulation.sessions):
                server.simulation.close(key)
            server.server_close()
