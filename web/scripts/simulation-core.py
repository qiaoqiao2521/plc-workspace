"""Typed, composable plant models around isolated, actual compiled ST execution.

This module supplies the same operations to HTTP, CLI and human UI. It owns no
model roles and cannot grant generation, Siemens or machine acceptance.
"""
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / 'web/data/simulation'
SCHEMA = 'plc-scene.v1'
SCOPE = ('Actual captured ST via matiec/GCC, one persistent FB call per step; '
         'synthetic scan-count plant, not physical dynamics, real-time TON, '
         'LAD execution, TIA/PLCSIM, retention, safety or machine acceptance')
MAX_COMPONENTS = 64
MAX_TRACE = 2000
CATALOG = json.loads((DATA / 'catalog.json').read_text())
COMPONENTS = {item['type']: item for item in CATALOG['components']}
PROFILES = {item['id']: item for item in CATALOG['profiles']}
CONTRACT_HASH = hashlib.sha256((DATA / 'contract.md').read_bytes()).hexdigest()


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def _module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_program(program):
    """Validate a fixed interface without treating compilation as correctness."""
    if not isinstance(program, dict) or set(program) - {
            'profile', 'source', 'filename', 'request_fingerprint', 'request_id'}:
        raise ValueError('program requires profile/source and optional filename/request identity')
    profile = PROFILES.get(program.get('profile'))
    if profile is None:
        raise ValueError('Unsupported simulation profile; select an explicit catalog profile')
    source = program.get('source')
    if not isinstance(source, str) or not source.strip() or len(source.encode()) > 200000:
        raise ValueError('Expected nonempty SCL/ST source, at most 200000 bytes')
    for name in ('filename', 'request_fingerprint', 'request_id'):
        if name in program and (not isinstance(program[name], str) or len(program[name]) > 300):
            raise ValueError('Invalid program ' + name)
    normalized = _module('candidate-validation').normalize(source)
    tokens = re.sub(r'\(\*.*?\*\)|//[^\n]*', '', normalized, flags=re.S)
    if re.search(r'\b(?:PROGRAM|CONFIGURATION|RESOURCE|TASK|FUNCTION|VAR_EXTERNAL|VAR_IN_OUT|EXTERNAL|'
                 r'TON|TOF|TP|TIME|LTIME|DATE|DT|TOD|POINTER|REF_TO|ARRAY|STRUCT)\b', tokens, re.I):
        raise ValueError('Only a single scan-count FB is supported; time blocks/vendor code are unsupported')
    if re.findall(r'\bFUNCTION_BLOCK\s+(\w+)', tokens, re.I) != [profile['block']]:
        raise ValueError('Profile requires exactly one FB named ' + profile['block'])
    if len(re.findall(r'\bEND_FUNCTION_BLOCK\b', tokens, re.I)) != 1:
        raise ValueError('Expected one complete FUNCTION_BLOCK')
    for section, fields in (('VAR_INPUT', profile['inputs']), ('VAR_OUTPUT', profile['outputs'])):
        sections = re.findall(r'\b' + section + r'\b(.*?)\bEND_VAR\b', tokens, re.I | re.S)
        if len(sections) != 1:
            raise ValueError('Expected exactly one ' + section)
        declarations = {}
        for declaration in sections[0].split(';'):
            if not declaration.strip():
                continue
            match = re.fullmatch(r'\s*([A-Za-z_][\w]*(?:\s*,\s*[A-Za-z_][\w]*)*)\s*:\s*'
                                 r'(BOOL|INT|UINT)(?:\s*:=\s*(?:TRUE|FALSE|\d+))?\s*',
                                 declaration, re.I)
            if not match:
                raise ValueError('Unsupported declaration in ' + section)
            for name in match[1].split(','):
                key = name.strip().lower()
                if key in declarations:
                    raise ValueError('Duplicate interface symbol')
                declarations[key] = match[2].upper()
        if declarations != {name.lower(): kind for name, kind in fields.items()}:
            raise ValueError(section + ' does not match the selected profile interface')
    return copy.deepcopy(profile), normalized


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_scene(value, profile_id):
    """Return canonical defaults, typed connections and a deterministic DAG order."""
    if not isinstance(value, dict) or set(value) - {
            'schema_version', 'id', 'label', 'components', 'connections', 'bindings'}:
        raise ValueError('Invalid scene object')
    if value.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported scene schema')
    scene = copy.deepcopy(value)
    for name in ('id', 'label'):
        if not isinstance(scene.get(name), str) or not 1 <= len(scene[name]) <= 120:
            raise ValueError('Scene requires a short ' + name)
    rows = scene.get('components')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_COMPONENTS:
        raise ValueError('Scene needs 1..64 components')
    by_id = {}
    for item in rows:
        if not isinstance(item, dict) or set(item) - {'id', 'type', 'position', 'parameters'}:
            raise ValueError('Invalid component')
        key = item.get('id')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,47}', key) or key in by_id:
            raise ValueError('Component IDs must be unique, short ASCII identifiers')
        kind = COMPONENTS.get(item.get('type'))
        if kind is None:
            raise ValueError('Unsupported component type')
        position = item.setdefault('position', [0, 0, 0])
        if (not isinstance(position, list) or len(position) != 3
                or any(not _number(x) or abs(x) > 100 for x in position)):
            raise ValueError('Position must contain three finite coordinates within 100 units')
        parameters = item.setdefault('parameters', {})
        if not isinstance(parameters, dict) or set(parameters) - set(kind['parameters']):
            raise ValueError('Unsupported parameter for ' + key)
        for name, rule in kind['parameters'].items():
            actual = parameters.setdefault(name, rule['default'])
            if rule.get('type') == 'BOOL':
                valid = type(actual) is bool
            else:
                valid = _number(actual) and rule['min'] <= actual <= rule['max']
            if not valid:
                raise ValueError('Invalid parameter ' + key + '.' + name)
        by_id[key] = item

    def port(reference, direction):
        if not isinstance(reference, str) or reference.count('.') != 1:
            raise ValueError('Ports use component.port references')
        component, name = reference.split('.')
        item = by_id.get(component)
        kind = COMPONENTS[item['type']]['ports'][direction].get(name) if item else None
        if not kind:
            raise ValueError('Unknown ' + direction + ' port: ' + reference)
        return component, kind

    connections = scene.get('connections')
    bindings = scene.get('bindings')
    if not isinstance(connections, list) or len(connections) > 128:
        raise ValueError('Expected at most 128 connections')
    if not isinstance(bindings, dict) or set(bindings) != {'inputs', 'outputs'}:
        raise ValueError('Expected typed PLC input and output bindings')
    profile = PROFILES[profile_id]
    if not isinstance(bindings['inputs'], dict) or set(bindings['inputs']) != set(profile['inputs']):
        raise ValueError('Every PLC profile input needs exactly one scene binding')
    if (not isinstance(bindings['outputs'], dict)
            or set(bindings['outputs']) - set(profile['outputs'])
            or not set(profile['actuators']).issubset(bindings['outputs'])):
        raise ValueError('Every actuator output needs a typed scene binding')
    writers = set()
    dependents = {key: set() for key in by_id}
    incoming = {key: set() for key in by_id}
    for edge in connections:
        if not isinstance(edge, dict) or set(edge) != {'from', 'to'}:
            raise ValueError('Connection needs from/to')
        a, kind_a = port(edge['from'], 'outputs')
        b, kind_b = port(edge['to'], 'inputs')
        if kind_a != kind_b:
            raise ValueError('Port type mismatch')
        if edge['to'] in writers:
            raise ValueError('Multiple writers for ' + edge['to'])
        writers.add(edge['to'])
        dependents[a].add(b)
        incoming[b].add(a)
    for name, reference in bindings['inputs'].items():
        _, kind = port(reference, 'outputs')
        if kind != profile['inputs'][name]:
            raise ValueError('PLC input type mismatch: ' + name)
        if name in ('Enable', 'Start', 'Stop', 'Reset') and by_id[reference.split('.')[0]]['type'] != 'switch':
            raise ValueError('Control inputs must bind explicit switch components')
    for name, references in bindings['outputs'].items():
        if not isinstance(references, list) or not references or len(references) > 64:
            raise ValueError('PLC output binding must be a nonempty port list')
        for reference in references:
            _, kind = port(reference, 'inputs')
            if kind != profile['outputs'][name]:
                raise ValueError('PLC output type mismatch: ' + name)
            if reference in writers:
                raise ValueError('Multiple writers for ' + reference)
            writers.add(reference)
    for key, item in by_id.items():
        for name in COMPONENTS[item['type']]['ports']['inputs']:
            if key + '.' + name not in writers:
                raise ValueError('Unconnected device input: ' + key + '.' + name)
    queue = sorted(key for key, deps in incoming.items() if not deps)
    order = []
    while queue:
        key = queue.pop(0)
        order.append(key)
        for target in sorted(dependents[key]):
            incoming[target].remove(key)
            if not incoming[target]:
                queue.append(target)
        queue.sort()
    if len(order) != len(by_id):
        raise ValueError('Device connections must form an acyclic graph')
    return scene, order


class NativeWorker:
    """A watchdog protects the HTTP process from a blocking/crashing native FB."""
    def __init__(self, program, compiler, library, directory, scan_timeout=2.0):
        self.scan_timeout = scan_timeout
        self.buffer = b''
        self.process = subprocess.Popen(
            [sys.executable, str(HERE / 'simulation-worker.py')], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, start_new_session=True)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            self.metadata = self.request({'command': 'init', 'program': program,
                                         'compiler': compiler, 'library': library,
                                         'directory': str(directory)}, timeout=125)
        except BaseException:
            self.close()
            raise

    def request(self, body, timeout=None):
        if self.process.poll() is not None:
            raise RuntimeError('Native worker exited; completed trace retained')
        try:
            pending = (json.dumps(body, allow_nan=False) + '\n').encode()
            while pending:
                written = self.process.stdin.write(pending)
                if not written:
                    raise BrokenPipeError('Zero-length worker pipe write')
                pending = pending[written:]
        except (BrokenPipeError, OSError) as error:
            self.close()
            raise RuntimeError('Native worker pipe closed') from error
        deadline = time.monotonic() + (timeout if timeout is not None else self.scan_timeout)
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b'\n' not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.close()
                    raise TimeoutError('Native scan watchdog expired; worker stopped and completed trace retained')
                if not selector.select(remaining):
                    continue
                block = os.read(self.process.stdout.fileno(), 65536)
                if not block:
                    self.close()
                    raise RuntimeError('Native worker exited without a result')
                self.buffer += block
                if len(self.buffer) > 262144:
                    self.close()
                    raise RuntimeError('Native worker response exceeded its budget')
        line, self.buffer = self.buffer.split(b'\n', 1)
        result = json.loads(line)
        if not result.get('ok'):
            raise RuntimeError(result.get('error', 'Native execution failed'))
        return result['result']

    def scan(self, inputs, *, timeout=None):
        return self.request({'command': 'scan', 'inputs': inputs}, timeout=timeout)

    def close(self):
        process = getattr(self, 'process', None)
        if process is None:
            return
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()


class Plant:
    def __init__(self, scene, order):
        self.scene, self.order = scene, order
        self.components = {item['id']: item for item in scene['components']}
        self.state = {}
        self.faults = {}
        self.outputs = {}
        self.signals = {}
        self.events = []
        for key, item in self.components.items():
            params = item['parameters']
            self.state[key] = ({'value': params['initial']} if item['type'] == 'switch'
                               else {'position': params.get('initial_position', 0.0)})
        self.evaluate(False)

    def set_inputs(self, values):
        if not isinstance(values, dict):
            raise ValueError('inputs must be an object of Boolean control levels')
        targets = {}
        for name, value in values.items():
            reference = self.scene['bindings']['inputs'].get(name)
            if not reference or type(value) is not bool:
                raise ValueError('Only declared Boolean control inputs may be set')
            key = reference.split('.')[0]
            if self.components[key]['type'] != 'switch':
                raise ValueError('Sensor inputs come from the plant; use inject_fault')
            if key in targets and targets[key] != value:
                raise ValueError('Contradictory writes to the same switch')
            targets[key] = value
        for key, value in targets.items():
            self.state[key]['value'] = value
        self.evaluate(False)

    def sample(self):
        return {name: bool(self.signals[reference])
                for name, reference in self.scene['bindings']['inputs'].items()}

    def evaluate(self, advance):
        signals = {}
        targets = {target: self.outputs.get(name, 0)
                   for name, references in self.scene['bindings']['outputs'].items() for target in references}
        connections = {edge['to']: edge['from'] for edge in self.scene['connections']}
        for key in self.order:
            item = self.components[key]
            kind, parameters, state = item['type'], item['parameters'], self.state[key]
            ports = COMPONENTS[kind]['ports']
            values = {name: (signals[connections[key + '.' + name]] if key + '.' + name in connections
                             else targets[key + '.' + name]) for name in ports['inputs']}
            active = self.faults.get(key, set())
            old = dict(state)
            if kind == 'switch':
                state = {'value': state['value']}
            elif kind == 'lamp':
                state = {'value': bool(values['value'])}
            elif kind == 'motor':
                state = {'command': bool(values['command']),
                         'running': bool(values['command']) and 'stuck_off' not in active}
            elif kind == 'conveyor':
                position = state['position']
                if advance and values['run'] and 'jam' not in active:
                    position = min(1.0, round(position + parameters['step'], 8))
                state = {'position': position, 'running': bool(values['run']), 'jammed': 'jam' in active}
            elif kind == 'photoeye':
                detected = values['position'] >= parameters['threshold']
                if 'stuck_low' in active:
                    detected = False
                elif 'stuck_high' in active:
                    detected = True
                state = {'detected': bool(detected), 'position': float(values['position'])}
            elif kind == 'cylinder':
                extend, retract = bool(values['extend']), bool(values['retract'])
                position = state['position']
                if advance and extend != retract and 'jam' not in active:
                    position = round(max(0.0, min(1.0, position + parameters['step'] * (1 if extend else -1))), 8)
                state = {'position': position, 'extended': position >= 1, 'retracted': position <= 0,
                         'extend': extend, 'retract': retract, 'conflict': extend and retract, 'jammed': 'jam' in active}
            else:
                state = {'position': float(values['position'])}
            self.state[key] = state
            signals.update({key + '.' + name: state[name] for name in ports['outputs']})
            if advance:
                for name in ('detected', 'extended', 'retracted', 'running', 'conflict'):
                    if name in state and state.get(name) != old.get(name):
                        self.events.append({'type': 'state_change', 'component': key,
                                            'signal': name, 'value': state[name]})
        self.signals = signals

    def advance(self, outputs):
        self.outputs = outputs
        self.events = []
        self.evaluate(True)


class SimulationService:
    def __init__(self, compiler=None, library=None, runtime_root=None, *, scan_timeout=2.0,
                 batch_timeout=30.0):
        self.compiler = str(compiler or os.environ.get('SIM_IEC2C', ''))
        self.library = str(library or os.environ.get('SIM_MATIEC_LIB', ''))
        if not _number(scan_timeout) or scan_timeout <= 0 or not _number(batch_timeout) or batch_timeout <= 0:
            raise ValueError('Native scan and batch timeouts must be positive finite seconds')
        self.scan_timeout = scan_timeout
        self.batch_timeout = batch_timeout
        if runtime_root is None:
            self.root = Path(tempfile.mkdtemp(prefix='plc-composable-sim-'))
        else:
            self.root = Path(runtime_root).resolve() / 'simulation'
        if self.root.is_relative_to(ROOT):
            raise ValueError('Simulation runtime artifacts must stay outside the repository')
        self.root.mkdir(parents=True, exist_ok=True)
        self.sessions = {}
        self.lock = threading.RLock()

    def capabilities(self):
        available = bool(self.compiler and Path(self.compiler).is_file() and self.library
                         and Path(self.library).is_dir() and shutil.which('gcc'))
        return {'available': available, 'engine': 'isolated matiec/GCC native FB',
                'profiles': list(PROFILES), 'scope': SCOPE,
                'reason': None if available else 'Set SIM_IEC2C and SIM_MATIEC_LIB; GCC must be available',
                'step_unit': 'FB invocation', 'physical_time': False,
                'limits': {'scan_timeout_seconds': self.scan_timeout,
                           'batch_timeout_seconds': self.batch_timeout, 'max_step_count': 500}}

    def catalog(self):
        return {**copy.deepcopy(CATALOG), 'capabilities': self.capabilities()}

    def templates(self):
        mappings = [('conveyor-pusher-v1', 'conveyor-pusher.scene.json', DATA / 'transfer-pusher.scl'),
                    ('conveyor-12-v1', 'conveyor.scene.json', DATA / 'conveyor-12.scl'),
                    ('conveyor-8-demo-v1', 'conveyor.scene.json', ROOT / 'plans/plc-generation-ui/user-eval/candidates/FB_ConveyorPack.scl'),
                    ('latch-start-stop-v1', 'latch.scene.json', DATA / 'start-stop.scl')]
        return {'templates': [{'id': key, 'label': PROFILES[key]['label'],
                               'scene': json.loads((DATA / scene).read_text()),
                               'program': {'profile': key, 'source': source.read_text(), 'filename': source.name},
                               'cases': PROFILES[key]['cases']} for key, scene, source in mappings]}

    def _configuration(self, body):
        default = body.get('template', 'conveyor-pusher-v1')
        templates = {item['id']: item for item in self.templates()['templates']}
        if default not in templates:
            raise ValueError('Unknown simulation template')
        base = templates[default]
        program = copy.deepcopy(body.get('program', base['program']))
        profile, normalized = prepare_program(program)
        if 'scene' not in body and profile['id'] != base['id']:
            base = templates[profile['id']]
        scene, order = validate_scene(body.get('scene', base['scene']), profile['id'])
        return program, profile, normalized, scene, order

    def create(self, body):
        if set(body) - {'template', 'scene', 'program'}:
            raise ValueError('create accepts template/scene/program')
        program, profile, normalized, scene, order = self._configuration(body)
        capabilities = self.capabilities()
        if not capabilities['available']:
            raise RuntimeError(capabilities['reason'])
        if len(self.sessions) >= 8:
            raise RuntimeError('At most eight sessions; close an existing session first')
        key = str(uuid.uuid4())
        folder = self.root / key
        folder.mkdir()
        worker = NativeWorker(program, self.compiler, self.library, folder, self.scan_timeout)
        plant = Plant(scene, order)
        session = {'session': key, 'program': program, 'profile': profile['id'], 'scene': scene,
                   'source_sha256': digest(program['source'].encode()), 'scene_sha256': digest(scene),
                   'adapted_source_sha256': digest(normalized.encode()), 'worker': worker,
                   'plant': plant, 'scan': 0, 'trace': [], 'inputs': plant.sample(),
                   'outputs': {name: 0 for name in profile['outputs']}, 'halted': None,
                   'last': time.monotonic()}
        self.sessions[key] = session
        return {'session': key, 'snapshot': self._snapshot(session), 'profile': profile['id'],
                'source_sha256': session['source_sha256'], 'scene_sha256': session['scene_sha256'],
                'capabilities': capabilities, 'scope': SCOPE}

    def _session(self, body):
        key = body.get('session')
        if not isinstance(key, str) or key not in self.sessions:
            raise ValueError('Unknown simulation session')
        return self.sessions[key]

    def _snapshot(self, session):
        plant = session['plant']
        outputs = session['outputs']
        conveyor = next((state for key, state in plant.state.items()
                         if plant.components[key]['type'] == 'conveyor'), {})
        return {'session': session['session'], 'scan': session['scan'], 'profile': session['profile'],
                'step_unit': 'FB invocation', 'physical_time': False,
                'inputs': dict(session['inputs']), 'outputs': dict(outputs),
                'plant_inputs': plant.sample(), 'position': conveyor.get('position', 0),
                'state': outputs.get('State'),
                'components': [{**copy.deepcopy(item), 'state': copy.deepcopy(plant.state[item['id']])}
                               for item in session['scene']['components']],
                'faults': {key: sorted(value) for key, value in plant.faults.items() if value},
                'events': copy.deepcopy(plant.events), 'halted': session['halted'],
                'source_sha256': session['source_sha256'], 'scene_sha256': session['scene_sha256'],
                'request_fingerprint': session['program'].get('request_fingerprint'), 'scope': SCOPE}

    def inspect(self, body):
        session = self._session(body)
        return {'session': session['session'], 'snapshot': self._snapshot(session),
                'scene': copy.deepcopy(session['scene']), 'program': copy.deepcopy(session['program']),
                'cases': PROFILES[session['profile']]['cases'], 'trace_length': len(session['trace'])}

    def step(self, body):
        if set(body) - {'session', 'inputs', 'steps', 'count'} or ('steps' in body and 'count' in body):
            raise ValueError('step accepts session, inputs and count')
        session = self._session(body)
        count = body.get('count', body.get('steps', 1))
        if type(count) is not int or not 1 <= count <= 500:
            raise ValueError('count must be an integer from 1 to 500')
        if session['scan'] + count > MAX_TRACE:
            raise ValueError('Trace budget is 2000 scans; export and create a fresh session')
        if session['halted']:
            raise RuntimeError('Session halted: ' + session['halted'])
        deadline = time.monotonic() + self.batch_timeout
        session['plant'].set_inputs(body.get('inputs', {}))
        rows = []
        for _ in range(count):
            sampled = session['plant'].sample()
            remaining = deadline - time.monotonic()
            call_timeout = min(session['worker'].scan_timeout, remaining)
            try:
                if remaining <= 0:
                    raise TimeoutError('Simulation batch watchdog expired')
                outputs = session['worker'].scan(sampled, timeout=call_timeout)
            except (TimeoutError, RuntimeError, OSError) as error:
                if isinstance(error, TimeoutError) and call_timeout < session['worker'].scan_timeout:
                    error = TimeoutError('Simulation batch watchdog expired after '
                                         + str(self.batch_timeout)
                                         + ' seconds; worker stopped and completed trace retained')
                session['halted'] = str(error)
                session['worker'].close()
                raise error
            session['inputs'], session['outputs'] = sampled, outputs
            session['plant'].advance(outputs)
            session['scan'] += 1
            session['last'] = time.monotonic()
            row = self._snapshot(session)
            session['trace'].append(row)
            rows.append(row)
        return {'session': session['session'], 'snapshot': rows[-1], 'trace': rows,
                'source_sha256': session['source_sha256'], 'scene_sha256': session['scene_sha256']}

    def inject_fault(self, body):
        if set(body) != {'session', 'device', 'fault', 'active'} or type(body['active']) is not bool:
            raise ValueError('inject_fault accepts session/device/fault/active:boolean')
        session = self._session(body)
        plant = session['plant']
        item = plant.components.get(body['device'])
        if not item or body['fault'] not in COMPONENTS[item['type']]['faults']:
            raise ValueError('Fault not supported by this component')
        active = set(plant.faults.get(body['device'], set()))
        if body['active']:
            active.add(body['fault'])
        else:
            active.discard(body['fault'])
        if {'stuck_low', 'stuck_high'}.issubset(active):
            raise ValueError('A sensor cannot be stuck high and stuck low simultaneously')
        plant.faults[body['device']] = active
        plant.evaluate(False)
        plant.events = [{'type': 'fault_changed', 'component': body['device'],
                         'fault': body['fault'], 'active': body['active']}]
        return {'session': session['session'], 'snapshot': self._snapshot(session)}

    def export_trace(self, body):
        session = self._session(body)
        return {'schema_version': 'plc-simulation-evidence.v1', 'session': session['session'],
                'profile': session['profile'], 'source_sha256': session['source_sha256'],
                'scene_sha256': session['scene_sha256'], 'contract_sha256': CONTRACT_HASH,
                'request_fingerprint': session['program'].get('request_fingerprint'),
                'request_id': session['program'].get('request_id'),
                'program': copy.deepcopy(session['program']), 'scene': copy.deepcopy(session['scene']),
                'trace': copy.deepcopy(session['trace']), 'halted': session['halted'],
                'scope': SCOPE, 'status': 'unknown' if session['halted'] else 'not_run',
                'acceptance': {'simulation_case': False, 'generation': False,
                               'tia': False, 'machine': False},
                'note': 'Interactive observations alone do not constitute an independent case verdict'}

    def run_case(self, body):
        if set(body) - {'session', 'template', 'scene', 'program', 'case'}:
            raise ValueError('run_case accepts an existing session or a new configuration plus case')
        case = body.get('case', 'normal')
        if 'session' in body:
            if set(body) - {'session', 'case'}:
                raise ValueError('A session case cannot replace its program or scene')
            original = self._session(body)
            configuration = {'program': original['program'], 'scene': original['scene']}
        else:
            configuration = {key: value for key, value in body.items() if key != 'case'}
        program, profile, _, _, _ = self._configuration(configuration)
        if case not in profile['cases']:
            raise ValueError('Case not supported by selected profile')
        created = self.create(configuration)
        key = created['session']
        session = self.sessions[key]
        checks, first_failure = [], None

        def expect(snapshot, name, expected, actual):
            nonlocal first_failure
            passed = expected == actual
            row = {'name': name, 'status': 'pass' if passed else 'fail',
                   'scan': snapshot['scan'], 'expected': expected, 'actual': actual}
            checks.append(row)
            if not passed and first_failure is None:
                first_failure = {**row, 'snapshot': snapshot}

        def step(**inputs):
            snap = self.step({'session': key, 'inputs': inputs})['snapshot']
            if profile['id'] == 'conveyor-pusher-v1':
                count = sum(bool(snap['outputs'].get(x)) for x in ('Motor', 'Extend', 'Retract'))
                expect(snap, 'actuator_interlock', True, count <= 1)
            for component in snap['components']:
                if component['type'] == 'cylinder':
                    expect(snap, 'cylinder_command_interlock:' + component['id'],
                           False, bool(component['state'].get('conflict')))
            return snap

        def all_off(snapshot):
            logical_off = not any(snapshot['outputs'].get(name, 0) for name in profile['actuators'])
            plant_off = all(
                not (component['state'].get('command') or component['state'].get('running'))
                if component['type'] == 'motor' else
                not (component['state'].get('extend') or component['state'].get('retract'))
                if component['type'] == 'cylinder' else True
                for component in snapshot['components'])
            return logical_off and plant_off

        def fault(kind, name, active=True):
            candidates = [item['id'] for item in session['scene']['components'] if item['type'] == kind]
            if not candidates:
                raise ValueError('Case requires component type ' + kind)
            self.inject_fault({'session': key, 'device': candidates[0], 'fault': name, 'active': active})

        try:
            if case == 'normal':
                snap = step(Enable=True, Start=True, Stop=False)
                expect(snap, 'fresh_start_energizes_motor', 1, snap['outputs']['Motor'])
                if profile['id'] == 'latch-start-stop-v1':
                    snap = step(Start=False)
                    expect(snap, 'start_release_keeps_latch', 1, snap['outputs']['Motor'])
                    snap = step(Stop=True)
                    expect(snap, 'stop_revokes_motor', 0, snap['outputs']['Motor'])
                else:
                    observed = ['Motor'] if snap['outputs']['Motor'] else []
                    done = False
                    for _ in range(40):
                        snap = step(Start=False)
                        expect(snap, 'normal_run_no_fault', 0, snap['outputs']['Error'])
                        if snap['inputs']['AtEnd']:
                            expect(snap, 'arrival_revokes_motor', 0, snap['outputs']['Motor'])
                        for output in profile['actuators']:
                            if snap['outputs'][output] and (not observed or observed[-1] != output):
                                observed.append(output)
                                if output == 'Extend':
                                    expect(snap, 'extend_starts_with_arrival_feedback', True, snap['inputs']['AtEnd'])
                                elif output == 'Retract':
                                    expect(snap, 'retract_starts_with_extended_feedback', True, snap['inputs']['Extended'])
                        if profile['id'] == 'conveyor-pusher-v1' and snap['outputs']['Retract']:
                            expect(snap, 'retract_only_after_extension', True, 'Extend' in observed)
                        if snap['outputs']['Done']:
                            done = True
                            expect(snap, 'completion_revokes_actions', True, all_off(snap))
                            if profile['id'] == 'conveyor-pusher-v1':
                                expect(snap, 'complete_actuator_sequence', ['Motor', 'Extend', 'Retract'], observed)
                                expect(snap, 'completion_has_retracted_feedback', True, snap['inputs']['Retracted'])
                            break
                    expect(snap, 'completion_within_case_horizon', True, done)
                    following = step(Start=False)
                    expect(following, 'done_is_one_scan', 0, following['outputs']['Done'])
            elif case == 'stop-restart':
                snap = step(Enable=True, Start=True, Stop=False)
                expect(snap, 'initial_start', 1, snap['outputs']['Motor'])
                snap = step(Start=True, Stop=True)
                expect(snap, 'simultaneous_stop_revokes_actions', True, all_off(snap))
                snap = step(Start=True, Stop=False)
                expect(snap, 'held_start_after_stop_does_not_restart', True, all_off(snap))
                step(Start=False)
                snap = step(Start=True)
                expect(snap, 'fresh_edge_restarts', 1, snap['outputs']['Motor'])
            else:
                sensor = case == 'sensor-failed'
                fault('photoeye' if sensor else 'conveyor', 'stuck_low' if sensor else 'jam')
                snap = step(Enable=True, Start=True, Stop=False)
                expect(snap, 'start_is_not_waiting_call', 0, snap['outputs']['Error'])
                for wait in range(1, profile['waiting_calls'] + 1):
                    snap = step(Start=False)
                    expected_error = int(wait == profile['waiting_calls'])
                    expect(snap, 'timeout_wait_' + str(wait), expected_error, snap['outputs']['Error'])
                expect(snap, 'timeout_reason', 1, snap['outputs']['TimeoutFault'])
                expect(snap, 'fault_revokes_actions', True, all_off(snap))
                if case == 'fault-reset':
                    snap = step(Stop=True, Reset=True)
                    expect(snap, 'stop_does_not_acknowledge_fault', 1, snap['outputs']['Error'])
                    snap = step(Stop=False, Reset=True)
                    expect(snap, 'held_reset_is_not_new_edge', 1, snap['outputs']['Error'])
                    step(Reset=False)
                    snap = step(Reset=True)
                    expect(snap, 'fresh_reset_clears_fault', 0, snap['outputs']['Error'])
                    expect(snap, 'reset_does_not_restart', True, all_off(snap))
            result = self.export_trace({'session': key})
            result.update(case=case, checks=checks, first_failure=first_failure,
                          status='fail' if first_failure else 'pass')
            result['acceptance']['simulation_case'] = first_failure is None and bool(checks)
            result['note'] = 'Independent finite case assertions only; no generation/platform acceptance'
            return result
        except (RuntimeError, TimeoutError, OSError) as error:
            result = self.export_trace({'session': key})
            result.update(case=case, checks=checks, first_failure=first_failure,
                          status='unknown', reason=str(error))
            return result
        finally:
            self.close({'session': key})

    def close(self, body):
        session = self._session(body)
        session['worker'].close()
        del self.sessions[session['session']]
        return {'closed': True, 'session': session['session']}

    def close_all(self):
        with self.lock:
            for session in list(self.sessions.values()):
                session['worker'].close()
            self.sessions.clear()

    shutdown = close_all

    def dispatch(self, action, body=None):
        body = {} if body is None else body
        if not isinstance(body, dict):
            raise ValueError('Simulation request must be a JSON object')
        with self.lock:
            if action in ('catalog', 'templates', 'capabilities'):
                if body:
                    raise ValueError(action + ' does not accept request fields')
                return getattr(self, action)()
            if action not in {'create', 'inspect', 'step', 'inject_fault', 'run_case', 'export_trace', 'close'}:
                raise ValueError('Unknown simulation action')
            return getattr(self, action)(body)
