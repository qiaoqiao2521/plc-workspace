"""Real native FB and deterministic plant checks; configure existing compiler paths."""
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import urllib.request
import urllib.error
import json
import shutil
from unittest.mock import patch
import unittest

spec = importlib.util.spec_from_file_location('simulation_server', Path(__file__).with_name('simulation-server.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

class NativeSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler, library = os.getenv('SIM_IEC2C'), os.getenv('SIM_MATIEC_LIB')
        if not compiler or not library:
            raise unittest.SkipTest('Native simulation needs SIM_IEC2C and SIM_MATIEC_LIB')
        cls.compiler, cls.library = compiler, library
        cls.folder = tempfile.TemporaryDirectory(prefix='plc-sim-test-')
        cls.runtime = server.module.ConveyorRuntime(cls.folder.name, compiler, library)
        cls.assets = server.FrozenAssets(cls.write_assets(Path(cls.folder.name) / 'assets'), cls.runtime.source_bytes)

    @classmethod
    def write_assets(cls, directory):
        directory.mkdir(parents=True)
        for name in ('simulation.html', 'simulation.css', 'simulation.js'):
            (directory / name).write_bytes((server.module.ROOT / 'web' / name).read_bytes())
        (directory / 'simulation-source.scl').write_bytes(cls.runtime.source_bytes)
        (directory / 'data').mkdir()
        (directory / 'data/example.json').write_bytes(b'{"version":1}')
        return directory

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.sim = server.Simulation(self.runtime)
        self.key = self.sim.new()['session']

    def tearDown(self):
        for key in list(self.sim.sessions):
            self.sim.close(key)

    def step(self, key=None, jam=False, sensor_failed=False, **inputs):
        return self.sim.step({'session': key or self.key, 'inputs': {name: inputs.get(name, False) for name in server.module.INPUTS[:-1]}, 'jam': jam, 'sensor_failed': sensor_failed})

    def test_arrival_feedback_next_scan_done_one_scan(self):
        self.assertEqual(self.step(Enable=True, Start=True)['outputs']['Motor'], 1)
        for _ in range(4):
            self.assertEqual(self.step()['outputs']['Motor'], 1)
        arrival = self.step()
        self.assertTrue(arrival['inputs']['AtEnd'])
        self.assertEqual(arrival['outputs']['Done'], 1)
        self.assertEqual(arrival['outputs']['Motor'], 0)
        self.assertEqual(self.step()['outputs']['Done'], 0)

    def test_stop_cancels_same_scan(self):
        self.step(Enable=True, Start=True)
        stopped = self.step(Stop=True)
        self.assertEqual(stopped['position'], .2)
        self.assertEqual(stopped['outputs']['Motor'], 0)

    def test_timeout_eighth_wait_and_reset_edge_consumption(self):
        self.step(Enable=True, Start=True, jam=True)
        for i in range(1, 8):
            result = self.step(jam=True)
            self.assertEqual(result['outputs']['statWaitCount'], i)
            self.assertEqual(result['outputs']['Error'], 0)
        self.assertEqual(self.step(jam=True)['outputs']['TimeoutFault'], 1)
        self.assertEqual(self.step(Stop=True, Reset=True)['outputs']['Error'], 1)
        self.assertEqual(self.step(Reset=True)['outputs']['Error'], 1)
        self.step()
        cleared = self.step(Enable=True, Start=True, Reset=True)['outputs']
        self.assertEqual((cleared['Error'], cleared['Motor']), (0, 0))

    def test_failed_sensor_timeout_despite_arrived_plant(self):
        self.step(Enable=True, Start=True, sensor_failed=True)
        for _ in range(8):
            result = self.step(sensor_failed=True)
        self.assertEqual(result['position'], 1)
        self.assertFalse(result['inputs']['AtEnd'])
        self.assertEqual(result['outputs']['TimeoutFault'], 1)

    def test_sessions_have_separate_persistent_memory(self):
        other = self.sim.new()['session']
        self.step(Enable=True, Start=True, jam=True)
        self.assertEqual(self.step(key=other)['outputs']['Motor'], 0)
        self.assertEqual(self.step(jam=True)['outputs']['statWaitCount'], 1)
        self.sim.close(other)
        with self.assertRaises(ValueError):
            self.step(key=other)

    def test_bad_signals_do_not_advance_instance(self):
        with self.assertRaises(ValueError):
            self.step(Start='false')
        self.assertEqual(self.sim.sessions[self.key]['scan'], 0)
        self.assertEqual(self.step(Enable=True, Start=True)['outputs']['statWaitCount'], 0)

    def test_http_origin_invalid_signals_and_native_step(self):
        httpd = server.create_server(self.runtime, self.assets, port=0)
        httpd.simulation = self.sim
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{httpd.server_port}'
        body = {'session': self.key, 'inputs': {'Enable': True, 'Start': True, 'Stop': False, 'Reset': False}, 'jam': False, 'sensor_failed': False}
        def post(payload, origin):
            req = urllib.request.Request(base + '/api/simulation/step', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'Origin': origin})
            return urllib.request.urlopen(req, timeout=3)
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                post(body, 'http://foreign.example')
            self.assertEqual(error.exception.code, 403)
            self.assertEqual(self.sim.sessions[self.key]['scan'], 0)
            with post(body, base) as response:
                result = json.load(response)
            self.assertEqual((result['scan'], result['outputs']['Motor']), (1, 1))
            body['inputs']['Start'] = 'false'
            with self.assertRaises(urllib.error.HTTPError) as error:
                post(body, base)
            self.assertEqual(error.exception.code, 400)
            self.assertEqual(self.sim.sessions[self.key]['scan'], 1)
        finally:
            httpd.shutdown()
            thread.join()
            httpd.server_close()

    def test_post_start_source_and_asset_changes_keep_existing_and_new_sessions_frozen(self):
        with tempfile.TemporaryDirectory(prefix='plc-sim-rebuild-') as folder:
            directory = self.write_assets(Path(folder) / 'dist')
            assets = server.FrozenAssets(directory, self.runtime.source_bytes)
            httpd = server.create_server(self.runtime, assets, port=0)
            httpd.simulation = self.sim
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{httpd.server_port}'
            def post(action, body):
                req = urllib.request.Request(base + '/api/simulation/' + action, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': base})
                with urllib.request.urlopen(req, timeout=3) as response:
                    self.assertEqual(response.headers['X-PLC-Snapshot'], assets.sha256)
                    return json.load(response)
            def step(key, start):
                return post('step', {'session': key, 'inputs': {'Enable': True, 'Start': start, 'Stop': False, 'Reset': False}, 'jam': True, 'sensor_failed': False})
            try:
                self.assertEqual(step(self.key, True)['outputs']['Motor'], 1)
                changed = self.runtime.source_bytes.replace(b'#Motor := (#statState = 2);', b'#Motor := FALSE;')
                self.assertNotEqual(changed, self.runtime.source_bytes)
                # Rebuild changes every served asset, including SCL and nested data.
                for name in assets.files:
                    (directory / name).write_bytes(changed if name == 'simulation-source.scl' else b'new build')
                with self.assertRaisesRegex(ValueError, 'Displayed source differs'):
                    server.FrozenAssets(directory, self.runtime.source_bytes)
                shutil.rmtree(directory)
                for name, expected in assets.files.items():
                    with urllib.request.urlopen(base + '/' + name, timeout=3) as response:
                        self.assertEqual(response.read(), expected)
                        self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        self.assertEqual(response.headers['X-PLC-Snapshot'], assets.sha256)
                self.assertEqual(step(self.key, False)['outputs']['Motor'], 1)
                fresh = post('new', {})
                self.assertEqual(fresh['source_sha256'], self.runtime.source_hash)
                self.assertEqual(fresh['asset_snapshot_sha256'], assets.sha256)
                self.assertEqual(step(fresh['session'], True)['outputs']['Motor'], 1)
            finally:
                httpd.shutdown()
                thread.join()
                httpd.server_close()

    def test_compilation_uses_captured_source_even_if_file_changes_before_compile(self):
        with tempfile.TemporaryDirectory(prefix='plc-sim-captured-source-') as folder:
            root = Path(folder)
            changed = self.runtime.source_bytes.replace(b'#Motor := (#statState = 2);', b'#Motor := FALSE;')
            disk = root / 'changed.scl'
            disk.write_bytes(changed)
            with patch.object(server.module, 'SOURCE', disk):
                frozen = server.module.ConveyorRuntime(root / 'frozen', self.compiler, self.library,
                                                       source_bytes=self.runtime.source_bytes)
                updated = server.module.ConveyorRuntime(root / 'updated', self.compiler, self.library)
            for runtime, expected in ((frozen, 1), (updated, 0)):
                handle = runtime.create()
                try:
                    self.assertEqual(runtime.scan(handle, {'Enable': True, 'Start': True})['Motor'], expected)
                finally:
                    runtime.destroy(handle)
            self.assertEqual(frozen.source_hash, self.runtime.source_hash)
            self.assertNotEqual(updated.source_hash, self.runtime.source_hash)


class MultiSourceSnapshotTests(unittest.TestCase):
    def test_all_scene_sources_are_checked_and_frozen(self):
        with tempfile.TemporaryDirectory(prefix='plc-multi-snapshot-') as folder:
            root = Path(folder)
            for name in ('simulation.html', 'simulation.css', 'simulation.js'):
                (root / name).write_bytes(b'ui')
            sources = {'simulation-source.scl': b'conveyor', 'clamp-source.scl': b'clamp'}
            for name, content in sources.items():
                (root / name).write_bytes(content)
            assets = server.FrozenAssets(root, sources)
            (root / 'clamp-source.scl').write_bytes(b'changed')
            self.assertEqual(assets.files['clamp-source.scl'], b'clamp')
            with self.assertRaisesRegex(ValueError, 'Displayed source differs'):
                server.FrozenAssets(root, sources)
            (root / 'clamp-source.scl').unlink()
            with self.assertRaisesRegex(ValueError, 'Displayed source differs'):
                server.FrozenAssets(root, sources)
