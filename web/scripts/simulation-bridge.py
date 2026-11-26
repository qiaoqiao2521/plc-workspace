"""Engineering handoff and one serialized API for UI and Agent simulation calls.

This bridge never imports an engineering file's verification or acceptance. A
captured, supported source is executed again by the native simulation service.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import uuid


PROFILES = ('conveyor-12-v1', 'conveyor-8-demo-v1',
            'latch-start-stop-v1', 'conveyor-pusher-v1')
ACTIONS = ('catalog', 'templates', 'create', 'inspect', 'step',
           'inject_fault', 'run_case', 'export_trace', 'close',
           'integrations', 'oip_catalog', 'oip_assemble', 'oip_test', 'oip_self_test')
ALIASES = {'fault': 'inject_fault', 'run-case': 'run_case', 'trace': 'export_trace'}
OIP_ROOT = Path(__file__).resolve().parents[2] / 'integrations/open-industry-project'


def engineering_program(engineering, validate_request, validate_artifact):
    """Validate the existing envelope, then retain source and provenance only."""
    if not isinstance(engineering, dict):
        raise ValueError('工程须包含原始 request 与 result。')
    request, result = engineering.get('request'), engineering.get('result')
    validate_request(request)
    validate_artifact(result, request)
    if result.get('questions'):
        raise ValueError('工程还有未决工艺；先完成规格再运行。')
    files = result.get('scl_files')
    if not isinstance(files, list) or len(files) != 1:
        raise ValueError('本版支持单个有明确合同的 FB；多文件工程尚未接入仿真。')
    source = files[0]
    profile = request['brief'].get('validation_profile')
    if profile not in PROFILES:
        raise ValueError('当前工程未选择受支持的仿真合同；请使用启停或输送带合同。')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*\.(?:scl|st)', source['name']):
        raise ValueError('仿真源文件名不合法。')
    return {'profile': profile, 'source': source['content'], 'filename': source['name'],
            'request_id': request['request_id'],
            'request_fingerprint': request['request_fingerprint']}


class SimulationBridge:
    def __init__(self, runtime_root, validate_request, validate_artifact):
        self.runtime_root = Path(runtime_root)
        self.validate_request, self.validate_artifact = validate_request, validate_artifact
        self.lock = threading.RLock()
        self._service = None
        self._oip_projects = {}

    def service(self):
        if self._service is None:
            path = Path(__file__).with_name('simulation-core.py')
            spec = importlib.util.spec_from_file_location('plc_simulation_core', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._service = module.SimulationService(
                compiler=os.environ.get('SIM_IEC2C'), library=os.environ.get('SIM_MATIEC_LIB'),
                runtime_root=self.runtime_root)
        return self._service

    def capabilities(self):
        with self.lock:
            return {**self.service().capabilities(), 'api': '/api/sim/',
                    'actions': list(ACTIONS), 'engineering_import': True,
                    'industrial_acceptance': 'not_run'}

    def dispatch(self, action, data):
        action = ALIASES.get(action, action)
        if action not in ACTIONS or not isinstance(data, dict):
            raise ValueError('不支持的仿真操作或请求格式。')
        body = copy.deepcopy(data)
        if 'engineering' in body:
            if action not in ('create', 'run_case', 'oip_test') or 'program' in body:
                raise ValueError('工程只可用于创建或测试，不能与另一份程序混合。')
            body['program'] = engineering_program(
                body.pop('engineering'), self.validate_request, self.validate_artifact)
        with self.lock:
            if action == 'integrations':
                if body:
                    raise ValueError('integrations does not accept request fields')
                return self.integrations()
            if action.startswith('oip_'):
                return self.oip(action, body)
            return self.service().dispatch(action, body)

    def oip_checkout(self):
        index = json.loads((OIP_ROOT / 'source-index.json').read_text())
        selected = os.environ.get('PLC_OIP_CHECKOUT') or os.environ.get('PLC_OIP_DIR')
        return (Path(selected).expanduser().resolve() if selected else
                Path.home() / '.cache/plc-workspace/oip' / index['commit'])

    def integrations(self):
        index = json.loads((OIP_ROOT / 'source-index.json').read_text())
        checkout = self.oip_checkout()
        installed = (checkout / '.git').exists()
        report = self._run_oip('doctor', timeout=20) if installed else {
            'status': 'unknown', 'reason': 'Run integrations/open-industry-project/setup.py first'}
        return {'open_industry_project': {
            'installed': installed, 'ready': report['status'] == 'pass',
            'commit': index['commit'], 'repository': index['repository'], 'license': index['license'],
            'supported_profiles': ['conveyor-8-demo-v1', 'conveyor-12-v1'],
            'native_ready': self.service().capabilities()['available'],
            'status': report['status'], 'reason': report.get('reason'),
            'scope': 'Pinned headless plant; native PLC source is executed separately from OIP self-tests'}}

    def _run_oip(self, action, arguments=(), *, timeout=90):
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        command = [sys.executable, str(OIP_ROOT / 'run.py'), '--checkout', str(self.oip_checkout()),
                   action, *map(str, arguments)]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=os.name == 'posix')
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.communicate()
            return {'status': 'unknown', 'reason': 'oip_timeout',
                    'industrial_acceptance': 'not_run'}
        try:
            if len(stdout.encode()) > 16_000_000:
                raise ValueError('OIP response exceeds the result limit')
            report = json.loads(stdout)
            if not isinstance(report, dict):
                raise ValueError('Expected an OIP report object')
        except (ValueError, TypeError):
            return {'status': 'unknown', 'reason': 'invalid_oip_report',
                    'detail': stderr[-2000:], 'industrial_acceptance': 'not_run'}
        raw = report.get('status')
        status = {'passed': 'pass', 'failed': 'fail', 'error': 'unknown',
                  'unavailable': 'unknown', 'not_run': 'not_run'}.get(raw, 'unknown')
        if process.returncode not in (0, 1, 2) or (status == 'pass' and process.returncode != 0):
            status = 'unknown'
        return {**report, 'upstream_status': raw, 'status': status,
                'industrial_acceptance': 'not_run'}

    def oip(self, action, body):
        allowed = {'oip_catalog': {'parts'}, 'oip_assemble': set(),
                   'oip_test': {'program', 'project_id'}, 'oip_self_test': set()}[action]
        if set(body) - allowed:
            raise ValueError('Unexpected fields for ' + action)
        if action == 'oip_catalog':
            parts = body.get('parts', [])
            if (not isinstance(parts, list) or len(parts) > 20
                    or any(not isinstance(part, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', part)
                           or part.startswith('-') for part in parts)):
                raise ValueError('Provide a short list of OIP catalog part IDs')
            return self._run_oip('catalog', parts)
        if action == 'oip_self_test':
            return self._run_oip('upstream-tests')
        if action == 'oip_assemble':
            identifier = str(uuid.uuid4())
            output = self.runtime_root / 'oip-projects' / identifier
            output.parent.mkdir(parents=True, exist_ok=True)
            report = self._run_oip('assemble', ['--output', output])
            if report['status'] == 'pass':
                self._oip_projects[identifier] = output
                report['project_id'] = identifier
            return report
        arguments = ['--iec2c', os.environ.get('SIM_IEC2C', ''),
                     '--matiec-lib', os.environ.get('SIM_MATIEC_LIB', '')]
        if not self.service().capabilities()['available']:
            return {'status': 'unknown', 'reason': 'native_toolchain_missing',
                    'industrial_acceptance': 'not_run'}
        if 'project_id' in body:
            project = self._oip_projects.get(body['project_id'])
            if project is None:
                raise ValueError('Unknown OIP project; assemble it through this service first')
            arguments += ['--project', project]
        if 'program' in body:
            program = body['program']
            if not isinstance(program, dict) or program.get('profile') not in ('conveyor-8-demo-v1', 'conveyor-12-v1'):
                raise ValueError('The OIP native plant bridge currently supports the two conveyor profiles')
            folder = self.runtime_root / 'oip-runs' / str(uuid.uuid4())
            folder.mkdir(parents=True)
            source = folder / 'program.json'
            source.write_text(json.dumps(program, ensure_ascii=False, allow_nan=False))
            arguments += ['--program-json', source]
        return self._run_oip('native-test', arguments)

    def shutdown(self):
        with self.lock:
            if self._service is not None:
                self._service.shutdown()
