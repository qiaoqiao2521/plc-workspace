import importlib.util
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).with_name('local-server.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

# This key and provider are fixtures. Every launch in these tests is redirected
# to a local subprocess; no model API or paid service is contacted.
API_CONFIG = {'base_url': 'https://provider.example/v1', 'model': 'fixture-model',
              'api_key': 'fixture-key'}

def request(profile=None):
    brief = {k: '' for k in ['name','block_name','requirement','flow','io_text','constraints']}
    brief.update(name='test',block_name='FB_Test',requirement='启动输送，到位停止，故障撤销动作。')
    if profile is not None:
        brief['validation_profile'] = profile
    content = json.dumps({'brief':brief,'states':[]},ensure_ascii=False,separators=(',',':'))
    return {'schema_version':1,'request_id':'test-run','request_fingerprint':hashlib.sha256(content.encode()).hexdigest(),'brief':brief,'states':[]}

def result(req):
    return {**{k:req[k] for k in ['schema_version','request_id','request_fingerprint']},'summary':'candidate','questions':[],'states':[],'io':[],'scl_files':[],'lad_networks':[],'checks':[]}

def reviewed_fixture(req=None):
    req = req or request()
    candidate = result(req)
    candidate['scl_files'] = [{'name': 'Test.scl', 'content': 'fixture'}]
    validation = bridge.verification_policy.complete_report({
        'request_fingerprint': req['request_fingerprint'],
        'files': [{'name': 'Test.scl', 'sha256': hashlib.sha256(b'fixture').hexdigest()}],
        'checks': [{'name': name, 'status': 'pass', 'detail': 'Synthetic subprocess fixture'}
                   for name in ('source_structure', 'linux_compile')]})
    return {'verdict': 'reviewed_draft', 'result': candidate, 'validation': validation}

class BridgeTests(unittest.TestCase):
    def test_rejects_wrong_fingerprint_before_launch(self):
        req=request();req['request_fingerprint']='old'
        with self.assertRaises(ValueError):bridge.GenerationBridge(API_CONFIG).begin(req)

    def test_rejects_all_wrong_response_shapes(self):
        for value in [None,{}, {'schema_version':1}]:
            with self.assertRaises(ValueError):bridge.validate_schema(value,bridge.SCHEMA)

    def test_api_configuration_is_memory_only_and_preserves_key_for_same_endpoint(self):
        with tempfile.TemporaryDirectory() as td:
            server=bridge.GenerationBridge(API_CONFIG, runtime_root=td)
            self.assertTrue(server.ready)
            public=server.configure({'model': 'different-fixture-model'})
            self.assertTrue(public['api_key_set'])
            self.assertEqual(server._config['api_key'], API_CONFIG['api_key'])
            self.assertNotIn('api_key', public)
            self.assertNotIn(API_CONFIG['api_key'], json.dumps(public))
            self.assertEqual(list(Path(td).iterdir()), [])
            before=server.public_config()
            with self.assertRaises(ValueError):
                server.configure({'base_url': 'https://different-provider.example/v1'})
            self.assertEqual(server.public_config(), before)
            self.assertEqual(server._config['api_key'], API_CONFIG['api_key'])
            changed=server.configure({'base_url': 'https://different-provider.example/v1',
                                      'api_key': 'replacement-fixture-key'})
            self.assertEqual(changed['base_url'], 'https://different-provider.example/v1')
            self.assertEqual(server._config['api_key'], 'replacement-fixture-key')
            self.assertNotIn('replacement-fixture-key', json.dumps(changed))
            local=server.configure({'base_url': 'http://127.0.0.1:9000/v1'})
            self.assertFalse(local['api_key_set'])
            self.assertTrue(server.ready)
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_clear_key_disables_remote_api_and_running_jobs_freeze_configuration(self):
        with tempfile.TemporaryDirectory() as td:
            server=bridge.GenerationBridge(API_CONFIG, runtime_root=td)
            server.active='fixture-running-job'
            with self.assertRaises(RuntimeError):
                server.configure({'model': 'changed'})
            self.assertEqual(server.public_config()['model'], API_CONFIG['model'])
            server.active=None
            public=server.configure({'clear_key': True})
            self.assertFalse(public['api_key_set'])
            self.assertFalse(server.ready)
            self.assertEqual(server._config['api_key'], '')
            with patch.object(bridge.subprocess, 'Popen') as launch:
                with self.assertRaises(ValueError):
                    server.begin(request())
                launch.assert_not_called()
            with self.assertRaises(ValueError):
                server.configure({'clear_key': True, 'api_key': 'conflicting-fixture-key'})
            self.assertFalse(server.ready)
            self.assertEqual(server.jobs, {})

    def run_stub(self, stdout, code=0, delay=0, cancel=False, timeout=2, profile=None):
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/'fixture-workflow.py'
            script.write_text('import json, sys, time\n'
                'assert isinstance(json.loads(sys.stdin.read()), dict)\n'
                'time.sleep('+str(delay)+')\nprint('+repr(stdout)+')\nraise SystemExit('+str(code)+')\n')
            runtime=Path(td)/'runtime'
            server=bridge.GenerationBridge(API_CONFIG, runtime_root=runtime, timeout=timeout)
            original_popen=bridge.subprocess.Popen
            launches=[]
            inputs=[]
            scratch_contains_key=[]
            def run_fake(command, **kwargs):
                launches.append((command, kwargs))
                scratch_contains_key.append(any(API_CONFIG['api_key'].encode() in path.read_bytes()
                    for path in Path(kwargs['cwd']).rglob('*') if path.is_file()))
                proc=original_popen([sys.executable, str(script)], **kwargs)
                original_communicate=proc.communicate
                def communicate(*args, **options):
                    received=options.get('input', args[0] if args else None)
                    if received is not None:
                        inputs.append(received)
                    return original_communicate(*args, **options)
                proc.communicate=communicate
                return proc
            with patch.object(bridge.subprocess,'Popen',side_effect=run_fake):
                job=server.begin(request(profile))
                if cancel:server.cancel(job)
                deadline=time.monotonic()+5
                while server.active and time.monotonic()<deadline:time.sleep(.01)
                self.assertIsNone(server.active)
                self.assertEqual(server.provider, 'api')
                self.assertFalse(any(scratch_contains_key))
                if not cancel:
                    self.assertEqual(len(launches), 1)
                    self.assertEqual(len(inputs), 1)
                for command, options in launches:
                    self.assertIn('plc-workflow.py', ' '.join(command))
                    self.assertNotIn(API_CONFIG['api_key'], ' '.join(command))
                    self.assertEqual(options.get('stdin'), bridge.subprocess.PIPE)
                    self.assertNotIn(API_CONFIG['api_key'], json.dumps(options.get('env', {})))
                for raw in inputs:
                    self.assertIsInstance(json.loads(raw), dict)
                    self.assertIn(API_CONFIG['api_key'], raw)
                for artifact in runtime.rglob('*'):
                    if artifact.is_file():
                        self.assertNotIn(API_CONFIG['api_key'].encode(), artifact.read_bytes())
                snapshot=server.snapshot(job)
                self.assertNotIn(API_CONFIG['api_key'], json.dumps(snapshot))
                return snapshot

    def test_accepts_structured_success_and_rejects_stale_result(self):
        envelope=reviewed_fixture()
        self.assertEqual(self.run_stub(json.dumps(envelope))['status'],'complete')
        envelope['result']['request_fingerprint']='old'
        self.assertEqual(self.run_stub(json.dumps(envelope))['status'],'failed')

    def test_exit_zero_without_structured_result_is_not_success(self):
        self.assertEqual(self.run_stub('{"status":"SUCCESS","response":"looks good"}')['status'],'failed')
        self.assertEqual(self.run_stub('[]')['status'],'failed')
        self.assertEqual(self.run_stub('{}',code=2)['status'],'failed')

    def test_cancel_before_or_during_launch_never_returns_complete(self):
        envelope=reviewed_fixture()
        self.assertEqual(self.run_stub(json.dumps(envelope),delay=1,cancel=True)['status'],'cancelled')

    def test_cancel_request_is_distinct_from_finished_cleanup(self):
        server=bridge.GenerationBridge(None)
        server.jobs['cancel-test']={'status':'cancelled','process':None,'started':time.monotonic(),
                                    'acceptance':{'scl_behavior':True}}
        pending=server.snapshot('cancel-test')
        self.assertFalse(pending['finished'])
        self.assertFalse(any(pending['acceptance'].values()))
        server.jobs['cancel-test'].update(duration_seconds=1,candidate_result=result(request()))
        finished=server.snapshot('cancel-test')
        self.assertTrue(finished['finished'])
        self.assertEqual(finished['candidate_result'],result(request()))
        self.assertFalse(any(finished['acceptance'].values()))

    def test_cancel_before_cleanup_recovers_only_a_draft(self):
        req = request()
        candidate = result(req)
        with tempfile.TemporaryDirectory() as temp:
            server = bridge.GenerationBridge(runtime_root=temp)
            server.jobs['job'] = {'status': 'cancelled'}
            self.assertFalse(server.snapshot('job')['finished'])
            saved = Path(temp) / 'job'
            saved.mkdir()
            (saved / 'outcome.json').write_text(json.dumps({
                'result': candidate, 'verdict': 'reviewed_draft',
                'validation_level': 'behavior_pass', 'acceptance': {'scl_behavior': True}}))
            server.recover_workflow('job', req, cancelled=True)
            server.jobs['job']['duration_seconds'] = 1
            snapshot = server.snapshot('job')
            self.assertTrue(snapshot['finished'])
            self.assertEqual(snapshot['candidate_result'], candidate)
            self.assertNotIn('result', snapshot)
            self.assertEqual(snapshot['workflow']['verdict'], 'cancelled')
            self.assertEqual(snapshot['workflow']['validation_level'], 'not_accepted')
            self.assertIsNone(snapshot['workflow']['result'])
            self.assertFalse(any(snapshot['workflow']['acceptance'].values()))

    def test_failed_or_cancelled_snapshot_revokes_nested_workflow_acceptance(self):
        for status in ('failed', 'cancelled'):
            with self.subTest(status=status):
                candidate = result(request())
                server = bridge.GenerationBridge(None)
                server.jobs['job'] = {'status': status, 'result': candidate,
                    'workflow': {'verdict': 'reviewed_draft', 'result': candidate,
                        'validation_level': 'behavior_pass', 'acceptance': {'scl_behavior': True}}}
                snapshot = server.snapshot('job')
                self.assertNotIn('result', snapshot)
                self.assertIsNone(snapshot['workflow']['result'])
                self.assertEqual(snapshot['workflow']['candidate'], candidate)
                self.assertNotEqual(snapshot['workflow']['verdict'], 'reviewed_draft')
                self.assertEqual(snapshot['workflow']['validation_level'], 'not_accepted')
                self.assertFalse(any(snapshot['workflow']['acceptance'].values()))

    def test_legacy_cli_envelopes_and_prose_cannot_bypass_workflow(self):
        for bad in [{'status': 'SUCCESS', 'structured_output': result(request())},
                    {'response': json.dumps(result(request()))},
                    {'response': 'looks good'}, {'response': '{}'},
                    {'response': json.dumps(result(request())), 'error': 'failed'}]:
            outcome=self.run_stub(json.dumps(bad))
            self.assertEqual(outcome['status'],'failed')
            self.assertNotIn('result', outcome)
            self.assertFalse(any(outcome['acceptance'].values()))

    def test_workflow_budget_is_enforced_without_transport_grace(self):
        good=json.dumps(reviewed_fixture())
        outcome=self.run_stub(good,delay=2,timeout=1)
        self.assertEqual(outcome['status'],'failed')
        self.assertIn('预算',outcome['error'])

    def test_explicit_unlimited_budget_accepts_late_result(self):
        good=json.dumps(reviewed_fixture())
        self.assertEqual(self.run_stub(good,delay=1.2,timeout=0)['status'],'complete')

    def test_api_workflow_accepts_only_reviewed_draft(self):
        candidate=result(request())
        candidate['scl_files']=[{'name':'Test.scl','content':'fixture'}]
        validation=bridge.verification_policy.complete_report({
            'request_fingerprint':request()['request_fingerprint'],
            'files':[{'name':'Test.scl','sha256':hashlib.sha256(b'fixture').hexdigest()}],
            'checks':[{'name':name,'status':'pass','detail':'Synthetic tool fixture'}
                      for name in ('source_structure','linux_compile')]})
        good={'verdict':'reviewed_draft','result':candidate,'validation':validation}
        self.assertEqual(self.run_stub(json.dumps(good),timeout=0)['status'],'complete')
        for change in [{'checks': validation['checks'][:1]},
                       {'required_checks': ['linux_compile']}, {'schema_version': 1}]:
            forged = {**good, 'validation': {**validation, **change}}
            blocked = self.run_stub(json.dumps(forged), timeout=0)
            self.assertEqual(blocked['status'], 'failed')
            self.assertNotIn('result', blocked)
            self.assertEqual(blocked['candidate_result'], candidate)
            self.assertFalse(any(blocked['workflow']['acceptance'].values()))
        self.assertEqual(self.run_stub(json.dumps({**good, 'validation_level': 'behavior_pass'}),
            timeout=0)['status'], 'failed')
        stale = {**good, 'validation': {**validation, 'request_fingerprint': 'older'}}
        rejected = self.run_stub(json.dumps(stale))
        self.assertEqual(rejected['status'], 'failed')
        self.assertNotIn('candidate_result', rejected)
        for verdict in ['blocked','rejected','unknown','audit_complete']:
            outcome=self.run_stub(json.dumps({'verdict':verdict,'result':result(request()),
                'analysis':{'questions':['Confirm valve']}}),timeout=0)
            self.assertEqual(outcome['status'],'failed')
            self.assertIn('Confirm valve',outcome['error'])
        failure=self.run_stub('{}',code=1,timeout=0)
        self.assertEqual(failure['status'],'failed')
        self.assertIn('工程未放行',failure['error'])

    def test_empty_source_cannot_gain_compilation_acceptance(self):
        candidate = result(request())
        report = bridge.verification_policy.complete_report({
            'request_fingerprint': candidate['request_fingerprint'], 'files': [],
            'checks': [{'name': name, 'status': 'pass', 'detail': 'Synthetic fixture'}
                       for name in ('source_structure', 'linux_compile')]})
        outcome = self.run_stub(json.dumps({'verdict': 'reviewed_draft', 'result': candidate,
            'validation': report}))
        self.assertEqual(outcome['status'], 'failed')
        self.assertFalse(any(outcome['acceptance'].values()))

    def test_profile_cannot_skip_scan_or_frozen_contract(self):
        policy = bridge.verification_policy
        candidate = result(request(policy.PROFILE))
        candidate['scl_files'] = [{'name': 'Test.scl', 'content': 'fixture'}]
        valid = policy.complete_report({
            'request_fingerprint': candidate['request_fingerprint'],
            'contract': policy.CONTRACT, 'contract_sha256': policy.CONTRACT_SHA256,
            'files': [{'name': 'Test.scl', 'sha256': hashlib.sha256(b'fixture').hexdigest()}],
            'checks': [{'name': name, 'status': 'pass', 'detail': 'Synthetic fixture'}
                for name in ('source_structure', 'linux_compile', 'scan_contract')]}, policy.PROFILE)
        for variant in ('valid', 'missing_contract', 'wrong_contract', 'wrong_hash', 'not_run', 'unknown', 'fail'):
            with self.subTest(variant=variant):
                report = copy.deepcopy(valid)
                if variant == 'missing_contract':
                    report.pop('contract')
                    report.pop('contract_sha256')
                elif variant == 'wrong_contract':
                    report['contract']['waiting_calls'] = 8
                    report['contract_sha256'] = hashlib.sha256(json.dumps(
                        report['contract'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                elif variant == 'wrong_hash':
                    report['contract_sha256'] = 'wrong'
                elif variant != 'valid':
                    next(c for c in report['checks'] if c['name'] == 'scan_contract')['status'] = variant
                report.update(status='pass', acceptance={'scl_behavior': True})
                outcome = self.run_stub(json.dumps({'verdict': 'reviewed_draft', 'result': candidate,
                    'validation': report}), profile=policy.PROFILE)
                self.assertEqual(outcome['status'], 'complete' if variant == 'valid' else 'failed')
                self.assertEqual(outcome['acceptance']['scl_behavior'], variant == 'valid')

    def test_api_failure_preserves_source_and_bound_diagnostics(self):
        candidate=result(request())
        candidate['scl_files']=[{'name':'Broken.scl','content':'broken source'}]
        validation={'status':'fail','request_fingerprint':candidate['request_fingerprint'],
                    'files':[{'name':'Broken.scl','sha256':hashlib.sha256(b'broken source').hexdigest()}],
                    'checks':[{'name':'Linux compile','status':'fail','detail':'type mismatch'}]}
        envelope={'verdict':'rejected','result':None,'candidate':candidate,
                  'validation':validation,'attempts':[{'attempt':0}]}
        outcome=self.run_stub(json.dumps(envelope),timeout=0)
        self.assertEqual(outcome['status'],'failed')
        self.assertEqual(outcome['candidate_result'],candidate)
        self.assertEqual(outcome['verification'],validation)
        self.assertEqual(outcome['workflow']['attempts'],[{'attempt':0}])
        self.assertIn('type mismatch',outcome['error'])
        envelope['validation']['files'][0]['sha256']='stale'
        outcome=self.run_stub(json.dumps(envelope),timeout=0)
        self.assertEqual(outcome['status'],'failed')
        self.assertNotIn('candidate_result',outcome)

    def test_review_approval_without_current_tool_evidence_is_rejected(self):
        outcome=self.run_stub(json.dumps({'verdict':'reviewed_draft','result':result(request())}),
                              timeout=0)
        self.assertEqual(outcome['status'],'failed')
        self.assertIn('没有返回',outcome['error'])

    def test_legacy_total_pass_does_not_satisfy_new_workflow_gate(self):
        candidate=result(request())
        candidate['scl_files']=[{'name':'Test.scl','content':'fixture'}]
        report={'status':'pass','request_fingerprint':candidate['request_fingerprint'],
                'files':[{'name':'Test.scl','sha256':hashlib.sha256(b'fixture').hexdigest()}],
                'checks':[],'acceptance':{'scl_behavior':True}}
        outcome=self.run_stub(json.dumps({'verdict':'reviewed_draft','result':candidate,'validation':report}),
                              timeout=0)
        self.assertEqual(outcome['status'],'failed')
        self.assertEqual(outcome['candidate_result'],candidate)
        self.assertFalse(any(outcome['acceptance'].values()))

    def test_bridge_recomputes_required_checks_before_complete(self):
        candidate=result(request())
        candidate['scl_files']=[{'name':'Test.scl','content':'fixture'}]
        for status in ('fail','unknown','not_run'):
            with self.subTest(status=status):
                report=bridge.verification_policy.complete_report({
                    'request_fingerprint':request()['request_fingerprint'],
                    'files':[{'name':'Test.scl','sha256':hashlib.sha256(b'fixture').hexdigest()}],
                    'checks':[{'name':'source_structure','status':'pass','detail':'structure fixture'},
                              {'name':'linux_compile','status':status,'detail':'Mandatory compiler check'}]})
                report['status']='pass'
                outcome=self.run_stub(json.dumps({'verdict':'reviewed_draft','result':candidate,'validation':report}),
                                      timeout=0)
                self.assertEqual(outcome['status'],'failed')
                self.assertFalse(any(outcome['acceptance'].values()))

    def test_original_program_and_behavior_contract_are_in_request_binding(self):
        req=request()
        req['brief']['source_files']=[{'name':'FB_Test.scl','content':'source'}]
        with self.assertRaisesRegex(ValueError,'指纹'):
            bridge.validate_request(req)
        def rebind():
            content=json.dumps({'brief':req['brief'],'states':req['states']},ensure_ascii=False,separators=(',',':'))
            req['request_fingerprint']=hashlib.sha256(content.encode()).hexdigest()
        req['brief']['validation_profile']='conveyor-12-v1'
        rebind()
        bridge.validate_request(req)
        req['brief']['source_files'][0]['name']='../outside.scl'
        rebind()
        with self.assertRaisesRegex(ValueError,'文件名'):
            bridge.validate_request(req)

    def test_http_rejects_foreign_origin_and_exposes_unconfigured_api(self):
        server=bridge.ThreadingHTTPServer(('127.0.0.1',0),bridge.Handler)
        server.bridge=bridge.GenerationBridge(None)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            capabilities=json.load(urlopen(url+'/api/capabilities'))
            self.assertFalse(capabilities['ready'])
            self.assertEqual(capabilities['provider'], 'api')
            self.assertTrue(capabilities['agent_control'])
            for path in ('/api/generate', '/api/config', '/api/agent/jobs'):
                req=Request(url+path,data=b'{}',headers={'Content-Type':'application/json',
                    'X-PLC-Workspace':'1','Origin':'https://foreign.example'})
                with self.assertRaises(HTTPError) as error:urlopen(req)
                self.assertEqual(error.exception.code,403)
        finally:server.shutdown();server.server_close()

    def test_http_api_configuration_never_returns_or_writes_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            server=bridge.ThreadingHTTPServer(('127.0.0.1',0),bridge.Handler)
            server.bridge=bridge.GenerationBridge(runtime_root=td)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_port)
            try:
                configured=Request(url+'/api/config',data=json.dumps(API_CONFIG).encode(),
                    headers={'Content-Type':'application/json','X-PLC-Workspace':'1'})
                with urlopen(configured) as response:
                    posted=json.load(response)
                self.assertTrue(posted['api_key_set'])
                self.assertNotIn('api_key', posted)
                with urlopen(url+'/api/config') as response:
                    public=json.load(response)
                self.assertEqual(public, posted)
                self.assertNotIn(API_CONFIG['api_key'], json.dumps(public))
                self.assertEqual(list(Path(td).iterdir()), [])
            finally:
                server.shutdown();server.server_close();thread.join(timeout=2)

    def test_real_agent_http_stage_binding_schema_replay_and_cancellation(self):
        # Runs the actual local controller and mailbox, but submits synthetic
        # analysis only. It does not call a model, compile a PLC, or claim acceptance.
        with tempfile.TemporaryDirectory() as td:
            server=bridge.ThreadingHTTPServer(('127.0.0.1',0),bridge.Handler)
            controller=server.bridge=bridge.GenerationBridge(runtime_root=td)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url='http://127.0.0.1:'+str(server.server_port)
            job_id=None

            def call(path, data=None, token=None):
                headers={'Content-Type':'application/json','X-PLC-Workspace':'1'}
                if token is not None:
                    headers['Authorization']='Bearer '+token
                req=Request(url+path, data=None if data is None else json.dumps(data).encode(), headers=headers)
                with urlopen(req, timeout=5) as response:
                    return json.load(response)

            def rejected(status, path, data=None, token=None):
                with self.assertRaises(HTTPError) as caught:
                    call(path, data, token)
                self.assertEqual(caught.exception.code, status)
                caught.exception.close()

            try:
                self.assertFalse(controller.ready)
                created=call('/api/agent/jobs', {'request': request()})
                job_id, token=created['job_id'], created['agent_token']
                self.assertGreaterEqual(len(token), 32)
                packets_path='/api/agent/jobs/'+job_id+'/packets'
                answers_path='/api/agent/jobs/'+job_id+'/answers'
                rejected(401, packets_path)
                rejected(401, packets_path, token='wrong-fixture-token')
                rejected(400, packets_path+'?token='+token, token=token)
                deadline=time.monotonic()+5
                available=call(packets_path, token=token)
                while not available['packets'] and time.monotonic()<deadline:
                    time.sleep(.02)
                    available=call(packets_path, token=token)
                self.assertEqual(len(available['packets']), 1)
                frozen=available['packets'][0]
                self.assertEqual(frozen['stage'], 'analysis')
                self.assertEqual(frozen['packet']['stage'], 'analysis')
                self.assertEqual(frozen['input_sha256'], hashlib.sha256(json.dumps(
                    frozen['packet'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
                self.assertNotIn(token, json.dumps(available))
                snapshot=call('/api/jobs/'+job_id)
                self.assertEqual(snapshot['mode'], 'agent')
                self.assertNotIn(token, json.dumps(snapshot))
                answer={'packet_id': frozen['packet_id'], 'input_sha256': frozen['input_sha256'],
                    'answer': {'verdict': 'ready', 'questions': [], 'unresolved': [],
                               'specification': 'Synthetic test requirement',
                               'obligations': ['Stop cancels action']}}
                rejected(401, answers_path, answer, token='wrong-fixture-token')
                rejected(400, answers_path, {**answer, 'input_sha256': 'stale'}, token)
                rejected(400, answers_path, {**answer, 'packet_id': 'f'*32}, token)
                rejected(400, answers_path, {**answer, 'answer': {'verdict': 'approve'}}, token)
                rejected(400, answers_path, {**answer, 'acceptance': {'scl_behavior': True}}, token)
                self.assertFalse((Path(td)/job_id/'answers'/(frozen['packet_id']+'.json')).exists())
                self.assertEqual(call(answers_path, answer, token), {'accepted': True})
                rejected(409, answers_path, answer, token)
                call('/api/jobs/'+job_id+'/cancel', {})
                deadline=time.monotonic()+5
                snapshot=call('/api/jobs/'+job_id)
                while not snapshot['finished'] and time.monotonic()<deadline:
                    time.sleep(.02)
                    snapshot=call('/api/jobs/'+job_id)
                self.assertTrue(snapshot['finished'])
                self.assertEqual(snapshot['status'], 'cancelled')
                self.assertFalse(any(snapshot['acceptance'].values()))
                self.assertNotIn('result', snapshot)
                self.assertNotIn(token, json.dumps(snapshot))
                rejected(409, answers_path, answer, token)
                self.assertEqual(call(packets_path, token=token)['packets'], [])
                for artifact in Path(td).rglob('*'):
                    if artifact.is_file():
                        self.assertNotIn(token.encode(), artifact.read_bytes())
            finally:
                if job_id is not None:
                    controller.cancel(job_id)
                    deadline=time.monotonic()+5
                    while controller.active and time.monotonic()<deadline:
                        time.sleep(.02)
                server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
