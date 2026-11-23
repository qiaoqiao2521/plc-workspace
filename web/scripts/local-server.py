#!/usr/bin/env python3
"""Loopback workspace with direct model API and constrained external Agent control."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'data/generation-result.schema.json').read_text())
LIMIT = 1_000_000
_policy_spec = importlib.util.spec_from_file_location('verification_policy', Path(__file__).with_name('verification-policy.py'))
verification_policy = importlib.util.module_from_spec(_policy_spec)
_policy_spec.loader.exec_module(verification_policy)
_api_spec = importlib.util.spec_from_file_location('model_api', Path(__file__).with_name('model-api.py'))
model_api = importlib.util.module_from_spec(_api_spec)
_api_spec.loader.exec_module(model_api)


def validate_schema(value, schema, root=None, depth=0):
    """The bounded JSON Schema features used by this project's model packets."""
    root = schema if root is None else root
    if depth > 64:
        raise ValueError('模型结果嵌套过深。')
    if '$ref' in schema:
        if not schema['$ref'].startswith('#/'):
            raise ValueError('不支持外部 Schema 引用。')
        target = root
        for part in schema['$ref'][2:].split('/'):
            target = target[part.replace('~1', '/').replace('~0', '~')]
        return validate_schema(value, target, root, depth + 1)
    if 'oneOf' in schema:
        accepted = 0
        for option in schema['oneOf']:
            try:
                validate_schema(value, option, root, depth + 1)
                accepted += 1
            except ValueError:
                pass
        if accepted != 1:
            raise ValueError('模型结果不符合唯一受支持的节点格式。')
        return
    kind = schema.get('type')
    valid = {'object': lambda: isinstance(value, dict), 'array': lambda: isinstance(value, list),
             'string': lambda: isinstance(value, str), 'integer': lambda: type(value) is int,
             'boolean': lambda: type(value) is bool}[kind]()
    if (not valid or ('enum' in schema and value not in schema['enum'])
            or ('const' in schema and value != schema['const'])):
        raise ValueError('模型结果不符合结构化格式。')
    if kind == 'object':
        properties = schema.get('properties', {})
        if (not set(schema.get('required', [])).issubset(value)
                or (schema.get('additionalProperties') is False and not set(value).issubset(properties))):
            raise ValueError('模型结果字段不完整。')
        for key, child in properties.items():
            if key in value:
                validate_schema(value[key], child, root, depth + 1)
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', 100):
            raise ValueError('模型结果条目过多。')
        for item in value:
            validate_schema(item, schema['items'], root, depth + 1)
    elif kind == 'string':
        if (not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', 200000)
                or ('pattern' in schema and not re.search(schema['pattern'], value))):
            raise ValueError('模型结果字符串不符合限制。')
    elif kind == 'integer':
        if not schema.get('minimum', value) <= value <= schema.get('maximum', value):
            raise ValueError('模型结果整数超出范围。')


def validate_request(request):
    if not isinstance(request, dict) or request.get('schema_version') != 1:
        raise ValueError('请求版本错误。')
    if not isinstance(request.get('request_id'), str) or len(request['request_id']) > 100:
        raise ValueError('请求标识错误。')
    brief, states = request.get('brief'), request.get('states')
    if not isinstance(brief, dict) or not isinstance(states, list) or len(states) > 24:
        raise ValueError('缺少需求或状态草稿。')
    for key in ['name', 'block_name', 'requirement', 'flow', 'io_text', 'constraints']:
        if not isinstance(brief.get(key), str) or len(brief[key]) > 20000:
            raise ValueError('需求字段错误或过长。')
    if len(brief['requirement'].strip()) < 10:
        raise ValueError('需求描述过短。')
    sources = brief.get('source_files', [])
    if not isinstance(sources, list) or len(sources) > 10:
        raise ValueError('原程序文件格式错误或过多。')
    names = []
    for source in sources:
        if (not isinstance(source, dict) or set(source) != {'name', 'content'}
                or not isinstance(source['name'], str)
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*\.(?:scl|st)', source['name'])
                or not isinstance(source['content'], str) or len(source['content']) > 200000):
            raise ValueError('原程序文件名或内容错误。')
        names.append(source['name'].casefold())
    if len(set(names)) != len(names):
        raise ValueError('原程序文件名重复。')
    profile = brief.get('validation_profile')
    if profile not in (None, '', verification_policy.PROFILE, verification_policy.LATCH_PROFILE):
        raise ValueError('不支持的行为验收合同。')
    if profile == verification_policy.LATCH_PROFILE:
        baseline = json.loads((ROOT / 'data/latch-start-stop-brief.json').read_text())
        if (any(brief[key] != baseline[key] for key in
                ('block_name', 'requirement', 'flow', 'io_text', 'constraints')) or sources or states):
            raise ValueError('启停双输出目前只支持明确选择的固定合成基准；请重新载入基准，勿将其套用到其他工艺。')
    content = json.dumps({'brief': brief, 'states': states}, ensure_ascii=False, separators=(',', ':'))
    expected = hashlib.sha256(content.encode()).hexdigest()
    if request.get('request_fingerprint') != expected:
        raise ValueError('需求指纹不匹配。')


def validate_workflow_artifact(result, request, validation=None):
    """Keep a failed candidate reviewable without accepting stale tool reports."""
    validate_schema(result, SCHEMA)
    if (result['schema_version'] != 1 or result['request_id'] != request['request_id']
            or result['request_fingerprint'] != request['request_fingerprint']):
        raise ValueError('流程成果与当前需求不匹配。')
    if validation is not None:
        expected = [{'name': file['name'], 'sha256': hashlib.sha256(
            file['content'].encode('utf-8')).hexdigest()} for file in result['scl_files']]
        if validation.get('files') != expected:
            raise ValueError('检查记录与当前程序文件不匹配。')
        if validation.get('request_fingerprint') != request['request_fingerprint']:
            raise ValueError('检查记录与当前需求不匹配。')
        if not verification_policy.artifacts_match(validation, result, request['brief'].get('validation_profile')):
            raise ValueError('检查记录与当前逻辑 IR / LAD 图不匹配。')


def stop_process(proc):
    """Allow native checker cleanup, then bound a blocked HTTP/model wait."""
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == 'posix':
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except ProcessLookupError:
        return

    def reap():
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                if os.name == 'posix':
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except ProcessLookupError:
                pass
    threading.Thread(target=reap, daemon=True).start()


class GenerationBridge:
    def __init__(self, config=None, runtime_root=None, timeout=0):
        self.timeout, self.provider = timeout, 'api'
        self.runtime_root = Path(runtime_root or Path(tempfile.gettempdir()) / 'plc-workspace-runs').resolve()
        if self.runtime_root.is_relative_to(ROOT.parent):
            raise ValueError('运行记录必须保存在仓库以外。')
        self.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._config = model_api.normalize_config(config) if config is not None else {
            'base_url': 'https://api.openai.com/v1', 'model': '', 'api_key': '',
            'timeout_seconds': 120, 'response_format': 'json_object'}
        self.jobs, self._tokens, self.lock, self.active = {}, {}, threading.Lock(), None

    @property
    def ready(self):
        try:
            model_api.normalize_config(self._config)
            return True
        except model_api.ApiError:
            return False

    def public_config(self):
        with self.lock:
            return {**{key: self._config[key] for key in
                       ('base_url', 'model', 'timeout_seconds', 'response_format')},
                    'api_key_set': bool(self._config.get('api_key'))}

    def configure(self, data):
        if (not isinstance(data, dict) or set(data) - (model_api.CONFIG_FIELDS | {'clear_key'})
                or not isinstance(data.get('clear_key', False), bool)):
            raise ValueError('API 配置字段无效。')
        with self.lock:
            if self.active:
                raise RuntimeError('任务运行中不能更换 API 配置，请完成或取消后再改。')
            proposed = {**self._config, **{key: value for key, value in data.items()
                                         if key in model_api.CONFIG_FIELDS}}
            if not isinstance(proposed.get('base_url'), str):
                raise ValueError('API 地址无效。')
            changed_endpoint = proposed['base_url'].rstrip('/') != self._config['base_url'].rstrip('/')
            if changed_endpoint and 'api_key' not in data:
                proposed['api_key'] = ''
            clearing = data.get('clear_key', False)
            if clearing:
                if data.get('api_key'):
                    raise ValueError('清除密钥不能同时设置新密钥。')
                proposed['api_key'] = ''
            try:
                if clearing:
                    # Validate non-secret fields even while intentionally disabling a remote API.
                    proposed = model_api.normalize_config({**proposed, 'api_key': secrets.token_urlsafe(32)})
                    proposed['api_key'] = ''
                else:
                    proposed = model_api.normalize_config(proposed)
            except model_api.ApiError as error:
                raise ValueError(str(error)) from None
            self._config = proposed
        return self.public_config()

    def keep_workflow(self, job_id, request, envelope):
        validation = envelope.get('validation')
        candidate = envelope.get('candidate') or envelope.get('result')
        if candidate is not None:
            validate_workflow_artifact(candidate, request, validation)
        with self.lock:
            self.jobs[job_id].update(workflow=envelope, verification=validation,
                                     candidate_result=candidate)

    def recover_workflow(self, job_id, request, *, cancelled=False):
        retained = self.runtime_root / job_id / 'outcome.json'
        try:
            if not retained.is_file() or retained.stat().st_size > LIMIT * 8:
                return
            envelope = json.loads(retained.read_text())
            if cancelled:
                envelope = {**envelope, 'verdict': 'cancelled',
                            'candidate': envelope.get('candidate') or envelope.get('result'),
                            'result': None, 'validation_level': 'not_accepted',
                            'acceptance': {name: False for name in
                                ('scl_compile', 'scl_behavior', 'lad_scl_compare', 'tia_compile')}}
            self.keep_workflow(job_id, request, envelope)
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            pass  # Never expose an invalid or stale artifact.

    def begin(self, request, prompt=None, mode='api'):
        validate_request(request)
        if mode not in ('api', 'agent'):
            raise ValueError('不支持的生成方式。')
        if prompt is not None and (not isinstance(prompt, str) or len(prompt) > 100000):
            raise ValueError('生成任务内容错误或过长。')
        # The controller constructs all prompts from the validated request. Client
        # prompt text is never an instruction or an alternative execution path.
        with self.lock:
            if self.active:
                raise RuntimeError('已有生成任务运行中，请等待完成或取消。')
            if mode == 'api' and not self.ready:
                raise ValueError('请先配置模型 API，或选择外部 Agent 接管。')
            config = copy.deepcopy(self._config) if mode == 'api' else None
            if config and config['api_key'] and model_api._contains_secret(request, config['api_key']):
                raise ValueError('需求中不能包含模型 API 密钥。')
            job_id = str(uuid.uuid4())
            self.jobs[job_id] = {'status': 'running', 'mode': mode,
                                'started': time.monotonic(), 'process': None}
            if mode == 'agent':
                self._tokens[job_id] = secrets.token_urlsafe(32)
            self.active = job_id
            while len(self.jobs) > 8:
                old_id = next(iter(self.jobs))
                del self.jobs[old_id]
                self._tokens.pop(old_id, None)
        threading.Thread(target=self.run, args=(job_id, copy.deepcopy(request), mode, config), daemon=True).start()
        return job_id

    def begin_agent(self, request):
        job_id = self.begin(request, mode='agent')
        with self.lock:
            return {'job_id': job_id, 'agent_token': self._tokens[job_id]}

    def _authorize_agent(self, job_id, token):
        # Called only while holding self.lock. Tokens never enter a job snapshot,
        # child command/environment, stage packet, or runtime file.
        expected = self._tokens.get(job_id)
        if (not expected or not isinstance(token, str) or not token.isascii()
                or not secrets.compare_digest(expected, token)):
            raise PermissionError('Agent 令牌无效。')
        job = self.jobs.get(job_id)
        if not job or job.get('mode') != 'agent':
            raise PermissionError('Agent 任务不存在。')
        return job

    def pending_packets(self, job_id, token):
        with self.lock:
            job = self._authorize_agent(job_id, token)
            packets = []
            folder = self.runtime_root / job_id
            if job['status'] == 'running':
                for path in sorted((folder / 'packets').glob('*.json')):
                    if (folder / 'answers' / path.name).exists():
                        continue
                    if path.stat().st_size > LIMIT * 8:
                        raise ValueError('阶段任务超过大小限制。')
                    packet = json.loads(path.read_text())
                    if packet.get('packet_id') != path.stem:
                        raise ValueError('阶段任务标识不匹配。')
                    packets.append(packet)
            return {'status': job['status'], 'finished': 'duration_seconds' in job, 'packets': packets}

    def submit_answer(self, job_id, token, data):
        with self.lock:
            job = self._authorize_agent(job_id, token)
            if job['status'] != 'running':
                raise RuntimeError('任务已结束，不能提交阶段回答。')
            if (not isinstance(data, dict) or set(data) != {'packet_id', 'input_sha256', 'answer'}
                    or not isinstance(data['packet_id'], str)
                    or not re.fullmatch(r'[0-9a-f]{32}', data['packet_id'])):
                raise ValueError('阶段回答字段无效。')
            folder = self.runtime_root / job_id
            source = folder / 'packets' / (data['packet_id'] + '.json')
            target = folder / 'answers' / source.name
            if target.exists():
                raise RuntimeError('该阶段回答已经提交。')
            if not source.is_file() or source.stat().st_size > LIMIT * 8:
                raise ValueError('该阶段尚未由控制器开放。')
            frozen = json.loads(source.read_text())
            actual = hashlib.sha256(json.dumps(frozen['packet'], ensure_ascii=False, sort_keys=True,
                                                separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            if (frozen.get('packet_id') != data['packet_id'] or frozen.get('input_sha256') != actual
                    or data['input_sha256'] != actual):
                raise ValueError('回答与当前阶段输入不匹配。')
            validate_schema(data['answer'], frozen['packet']['schema'])
            body = json.dumps({'input_sha256': actual, 'answer': data['answer']}, ensure_ascii=False, allow_nan=False)
            if model_api._contains_secret(data['answer'], token):
                raise ValueError('阶段回答中不能包含 Agent 令牌。')
            if len(body.encode()) > LIMIT:
                raise ValueError('阶段回答超过大小限制。')
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = target.with_suffix('.tmp')
            temporary.write_text(body)
            temporary.replace(target)
            return {'accepted': True}

    def run(self, job_id, request, mode, config):
        proc = None
        try:
            with tempfile.TemporaryDirectory(prefix='plc-generation-') as td:
                request_path = Path(td) / 'request.json'
                request_path.write_text(json.dumps(request, ensure_ascii=False))
                command = [sys.executable, str(Path(__file__).with_name('plc-workflow.py')), 'run',
                           '--provider', mode, '--request', str(request_path),
                           '--runtime', str(self.runtime_root / job_id)]
                child_env = os.environ.copy()
                child_env.pop('PLC_API_KEY', None)
                proc = subprocess.Popen(command, cwd=td, env=child_env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, start_new_session=(os.name == 'posix'))
                with self.lock:
                    self.jobs[job_id]['process'] = proc
                    cancelled = self.jobs[job_id]['status'] == 'cancelled'
                if cancelled:
                    stop_process(proc)
                try:
                    stdout, _stderr = proc.communicate(input=json.dumps(config) if mode == 'api' else '',
                                                      timeout=self.timeout or None)
                except subprocess.TimeoutExpired:
                    stop_process(proc)
                    proc.communicate()
                    self.recover_workflow(job_id, request, cancelled=True)
                    raise ValueError(f'生成超过 {self.timeout} 秒预算，结果未接受。')
                with self.lock:
                    cancelled = self.jobs[job_id]['status'] == 'cancelled'
                if cancelled:
                    self.recover_workflow(job_id, request, cancelled=True)
                    return
                if proc.returncode != 0:
                    with self.lock:
                        self.jobs[job_id]['provider_exit_code'] = proc.returncode
                    self.recover_workflow(job_id, request)
                    raise ValueError('模型接入或阶段执行失败，工程未放行。需求与已有候选已保留，请查看流程记录后重试。')
                if len(stdout.encode()) > LIMIT * 8:
                    raise ValueError('流程返回内容过大，请缩小工程范围。')
                envelope = json.loads(stdout)
                validation = envelope.get('validation')
                self.keep_workflow(job_id, request, envelope)
                if envelope.get('verdict') != 'reviewed_draft':
                    questions = list(envelope.get('analysis', {}).get('questions', []))
                    questions += envelope.get('generation_questions', [])
                    findings = envelope.get('final_review', {}).get('findings', [])
                    if validation:
                        findings = findings + [c['detail'] for c in validation.get('checks', [])
                                               if c.get('status') in ['fail', 'unknown']]
                    raise ValueError('严格流程已阻断工程交付（' + str(envelope.get('verdict')) + '）：' +
                                     '；'.join(questions + findings + [envelope.get('reason', '')])[:3000])
                result = envelope['result']
                validate_workflow_artifact(result, request, validation)
                assessed = verification_policy.assess_report(validation, request['brief'].get('validation_profile'))
                level = verification_policy.validation_level(assessed['acceptance'])
                if (not result['scl_files'] or assessed['status'] != 'pass'
                        or envelope.get('validation_level', level) != level):
                    raise ValueError('流程没有返回当前目标必选检查通过的证据，工程未放行。')
                envelope = {**envelope, 'validation': assessed,
                            'validation_level': level, 'acceptance': assessed['acceptance']}
                with self.lock:
                    if self.jobs[job_id]['status'] != 'cancelled':
                        self.jobs[job_id].update(status='complete', result=result, workflow=envelope,
                                                verification=assessed, acceptance=assessed['acceptance'])
        except (ValueError, OSError, TypeError, AttributeError, KeyError) as error:
            with self.lock:
                if self.jobs[job_id]['status'] != 'cancelled':
                    self.jobs[job_id].update(status='failed', error=str(error) if isinstance(error, ValueError)
                                             else '本机模型进程或结果格式错误，结果未接受。')
        finally:
            with self.lock:
                self.jobs[job_id]['process'] = None
                self.jobs[job_id]['duration_seconds'] = round(time.monotonic() - self.jobs[job_id]['started'], 1)
                if self.active == job_id:
                    self.active = None

    def snapshot(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            snapshot = copy.deepcopy({k: v for k, v in job.items() if k not in ['process', 'started']})
            snapshot['finished'] = 'duration_seconds' in job
            if snapshot['status'] != 'complete':
                snapshot['acceptance'] = {name: False for name in
                    ('scl_compile', 'scl_behavior', 'lad_scl_compare', 'tia_compile')}
                envelope = snapshot.get('workflow')
                if envelope is not None:
                    snapshot['workflow'] = {**envelope,
                        'verdict': 'cancelled' if snapshot['status'] == 'cancelled' else
                            ('unknown' if envelope.get('verdict') == 'reviewed_draft' else envelope.get('verdict')),
                        'candidate': envelope.get('candidate') or envelope.get('result'),
                        'result': None, 'validation_level': 'not_accepted',
                        'acceptance': snapshot['acceptance'].copy()}
                snapshot.pop('result', None)
            return snapshot

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job['status'] != 'running':
                return
            job['status'] = 'cancelled'
            proc = job['process']
        stop_process(proc)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'dist'), **kwargs)

    def log_message(self, *_):
        pass  # Do not persist user requirements, model content or session identifiers.

    def allowed(self, mutation=False):
        host = self.headers.get('Host', '')
        valid_host = urlparse('http://' + host).hostname in ['127.0.0.1', 'localhost']
        if not valid_host:
            return False
        if mutation:
            origin = self.headers.get('Origin')
            return (origin is None or origin == 'http://' + host) and self.headers.get('X-PLC-Workspace') == '1'
        return True

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def agent_token(self):
        value = self.headers.get('Authorization', '')
        return value.removeprefix('Bearer ') if value.startswith('Bearer ') else None

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error': '只允许本机访问。'})
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == '/api/capabilities':
                return self.reply(200, {'provider': 'api', 'ready': self.server.bridge.ready,
                                       'agent_control': True, 'timeout_seconds': self.server.bridge.timeout})
            if path == '/api/config':
                return self.reply(200, self.server.bridge.public_config())
            match = re.fullmatch(r'/api/agent/jobs/([^/]+)/packets', path)
            if match:
                if parsed.query:
                    raise ValueError('Agent 令牌只能通过 Authorization 头发送。')
                return self.reply(200, self.server.bridge.pending_packets(match[1], self.agent_token()))
            if path.startswith('/api/jobs/'):
                result = self.server.bridge.snapshot(path.removeprefix('/api/jobs/'))
                return self.reply(200 if result else 404, result or {'error': '任务不存在，请重新生成。'})
        except PermissionError as error:
            return self.reply(401, {'error': str(error)})
        except (ValueError, OSError, KeyError, TypeError):
            return self.reply(400, {'error': '阶段任务读取失败。'})
        super().do_GET()

    def do_POST(self):
        if not self.allowed(mutation=True):
            return self.reply(403, {'error': '请求必须来自本机工作台。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > LIMIT or self.headers.get('Content-Type') != 'application/json':
                raise ValueError('请求格式或大小错误。')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('请求必须是对象。')
            path = urlparse(self.path).path
            if path == '/api/config':
                return self.reply(200, self.server.bridge.configure(data))
            if path == '/api/generate':
                job_id = self.server.bridge.begin(data['request'], data.get('prompt'))
                return self.reply(202, {'job_id': job_id})
            if path == '/api/agent/jobs':
                return self.reply(202, self.server.bridge.begin_agent(data['request']))
            match = re.fullmatch(r'/api/agent/jobs/([^/]+)/answers', path)
            if match:
                return self.reply(200, self.server.bridge.submit_answer(match[1], self.agent_token(), data))
            match = re.fullmatch(r'/api/jobs/([^/]+)/cancel', path)
            if match:
                self.server.bridge.cancel(match[1])
                current = self.server.bridge.snapshot(match[1])
                return self.reply(200 if current else 404, {'status': current['status']} if current
                                  else {'error': '任务不存在。'})
            return self.reply(404, {'error': '接口不存在。'})
        except PermissionError as error:
            self.reply(401, {'error': str(error)})
        except RuntimeError as error:
            self.reply(409, {'error': str(error)})
        except (ValueError, KeyError, TypeError, OSError):
            self.reply(400, {'error': '请求内容无效，请检查需求、配置或阶段回答。'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--timeout', type=int, default=0, help='整条任务秒数预算；0 不限时，API 请求另有超时')
    parser.add_argument('--runtime-root', type=Path, help='仓库外运行记录目录，默认系统临时目录/plc-workspace-runs')
    args = parser.parse_args()
    if not (ROOT / 'dist/index.html').is_file():
        parser.error('先运行 npm --prefix web run build。')
    if args.timeout < 0:
        parser.error('--timeout 不能为负数。')
    config = None
    if any(os.environ.get(key) for key in ('PLC_API_BASE_URL', 'PLC_API_MODEL', 'PLC_API_KEY')):
        try:
            config = model_api.normalize_config({
                'base_url': os.environ.get('PLC_API_BASE_URL', 'https://api.openai.com/v1'),
                'model': os.environ.get('PLC_API_MODEL', ''), 'api_key': os.environ.get('PLC_API_KEY', ''),
                'timeout_seconds': float(os.environ.get('PLC_API_TIMEOUT', '120')),
                'response_format': os.environ.get('PLC_API_RESPONSE_FORMAT', 'json_object')})
        except (model_api.ApiError, ValueError):
            parser.error('PLC_API_* 配置无效，请检查地址、模型、密钥及请求超时；也可以在页面配置。')
    try:
        bridge = GenerationBridge(config=config, runtime_root=args.runtime_root, timeout=args.timeout)
    except ValueError as error:
        parser.error(str(error))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.bridge = bridge
    print(f'PLC Workspace: http://127.0.0.1:{args.port} (API {"configured" if bridge.ready else "unconfigured"}; Agent ready)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if bridge.active:
            bridge.cancel(bridge.active)
            deadline = time.monotonic() + 6
            while bridge.active and time.monotonic() < deadline:
                time.sleep(0.05)
        server.server_close()


if __name__ == '__main__':
    main()
