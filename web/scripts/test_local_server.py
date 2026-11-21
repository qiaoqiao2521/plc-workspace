import importlib.util
import copy
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
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

def request(profile=None):
    brief = {k: '' for k in ['name','block_name','requirement','flow','io_text','constraints']}
    brief.update(name='test',block_name='FB_Test',requirement='启动输送，到位停止，故障撤销动作。')
    if profile is not None:
        brief['validation_profile'] = profile
    content = json.dumps({'brief':brief,'states':[]},ensure_ascii=False,separators=(',',':'))
    return {'schema_version':1,'request_id':'test-run','request_fingerprint':hashlib.sha256(content.encode()).hexdigest(),'brief':brief,'states':[]}

def result(req):
    return {**{k:req[k] for k in ['schema_version','request_id','request_fingerprint']},'summary':'candidate','questions':[],'states':[],'io':[],'scl_files':[],'lad_networks':[],'checks':[]}

class BridgeTests(unittest.TestCase):
    def test_rejects_wrong_fingerprint_before_launch(self):
        req=request();req['request_fingerprint']='old'
        with self.assertRaises(ValueError):bridge.GenerationBridge('/not/used').begin(req,'prompt')

    def test_rejects_all_wrong_response_shapes(self):
        for value in [None,{}, {'schema_version':1}]:
            with self.assertRaises(ValueError):bridge.validate_schema(value,bridge.SCHEMA)

    def run_stub(self, stdout, code=0, delay=0, cancel=False, provider="agy", timeout=2, profile=None):
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/'fake-agy'
            script.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep('+str(delay)+')\nprint('+repr(stdout)+')\nraise SystemExit('+str(code)+')\n')
            script.chmod(0o755)
            workflow={'root':td,'company':'fixture','api_url':'http://127.0.0.1:3100'}
            server=bridge.GenerationBridge(str(script),timeout=timeout,provider=provider,node=str(script),workflow=workflow)
            original_popen=bridge.subprocess.Popen
            def run_fake(command, **kwargs):
                self.assertIn('mcode-workflow.py', ' '.join(command))
                return original_popen([str(script)], **kwargs)
            context=patch.object(bridge.subprocess,'Popen',side_effect=run_fake) if provider=='mcode-cm' else nullcontext()
            with context:
                job=server.begin(request(profile),'prompt')
                if cancel:server.cancel(job)
                deadline=time.monotonic()+5
                while server.active and time.monotonic()<deadline:time.sleep(.01)
                self.assertIsNone(server.active)
                return server.snapshot(job)

    def test_accepts_structured_success_and_rejects_stale_result(self):
        envelope={'status':'SUCCESS','structured_output':result(request())}
        self.assertEqual(self.run_stub(json.dumps(envelope))['status'],'complete')
        envelope['structured_output']['request_fingerprint']='old'
        self.assertEqual(self.run_stub(json.dumps(envelope))['status'],'failed')

    def test_exit_zero_without_structured_result_is_not_success(self):
        self.assertEqual(self.run_stub('{"status":"SUCCESS","response":"looks good"}')['status'],'failed')
        self.assertEqual(self.run_stub('[]')['status'],'failed')
        self.assertEqual(self.run_stub('{}',code=2)['status'],'failed')

    def test_cancel_before_or_during_launch_never_returns_complete(self):
        envelope={'status':'SUCCESS','structured_output':result(request())}
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
            server = bridge.GenerationBridge(None, workflow={'root': temp})
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

    def test_zcode_response_is_validated_and_prose_is_rejected(self):
        good=json.dumps({'response':json.dumps(result(request()))})
        self.assertEqual(self.run_stub(good,provider='zcode')['status'],'complete')
        for bad in [json.dumps({'response':'looks good'}),json.dumps({'response':'{}'}),json.dumps({'response':json.dumps(result(request())), 'error':'failed'})]:
            self.assertEqual(self.run_stub(bad,provider='zcode')['status'],'failed')

    def test_zcode_budget_does_not_inherit_agy_transport_grace(self):
        good=json.dumps({'response':json.dumps(result(request()))})
        outcome=self.run_stub(good,delay=4,provider='zcode')
        self.assertEqual(outcome['status'],'failed')
        self.assertIn('预算',outcome['error'])

    def test_explicit_unlimited_budget_accepts_late_result(self):
        good=json.dumps({'response':json.dumps(result(request()))})
        self.assertEqual(self.run_stub(good,delay=2.5,provider='zcode',timeout=0)['status'],'complete')

    def test_mcode_workflow_accepts_only_reviewed_draft(self):
        candidate=result(request())
        candidate['scl_files']=[{'name':'Test.scl','content':'fixture'}]
        validation=bridge.verification_policy.complete_report({
            'request_fingerprint':request()['request_fingerprint'],
            'files':[{'name':'Test.scl','sha256':hashlib.sha256(b'fixture').hexdigest()}],
            'checks':[{'name':name,'status':'pass','detail':'Synthetic tool fixture'}
                      for name in ('source_structure','linux_compile')]})
        good={'verdict':'reviewed_draft','result':candidate,'validation':validation}
        self.assertEqual(self.run_stub(json.dumps(good),provider='mcode-cm',timeout=0)['status'],'complete')
        for change in [{'checks': validation['checks'][:1]},
                       {'required_checks': ['linux_compile']}, {'schema_version': 1}]:
            forged = {**good, 'validation': {**validation, **change}}
            blocked = self.run_stub(json.dumps(forged), provider='mcode-cm', timeout=0)
            self.assertEqual(blocked['status'], 'failed')
            self.assertNotIn('result', blocked)
            self.assertEqual(blocked['candidate_result'], candidate)
            self.assertFalse(any(blocked['workflow']['acceptance'].values()))
        self.assertEqual(self.run_stub(json.dumps({**good, 'validation_level': 'behavior_pass'}),
            provider='mcode-cm', timeout=0)['status'], 'failed')
        stale = {**good, 'validation': {**validation, 'request_fingerprint': 'older'}}
        rejected = self.run_stub(json.dumps(stale), provider='mcode-cm')
        self.assertEqual(rejected['status'], 'failed')
        self.assertNotIn('candidate_result', rejected)
        for verdict in ['blocked','rejected','unknown','audit_complete']:
            outcome=self.run_stub(json.dumps({'verdict':verdict,'result':result(request()),
                'analysis':{'questions':['Confirm valve']}}),provider='mcode-cm',timeout=0)
            self.assertEqual(outcome['status'],'failed')
            self.assertIn('Confirm valve',outcome['error'])
        failure=self.run_stub('{}',code=1,provider='mcode-cm',timeout=0)
        self.assertEqual(failure['status'],'failed')
        self.assertIn('工程未放行',failure['error'])

    def test_empty_source_cannot_gain_compilation_acceptance(self):
        candidate = result(request())
        report = bridge.verification_policy.complete_report({
            'request_fingerprint': candidate['request_fingerprint'], 'files': [],
            'checks': [{'name': name, 'status': 'pass', 'detail': 'Synthetic fixture'}
                       for name in ('source_structure', 'linux_compile')]})
        outcome = self.run_stub(json.dumps({'verdict': 'reviewed_draft', 'result': candidate,
            'validation': report}), provider='mcode-cm')
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
                    'validation': report}), provider='mcode-cm', profile=policy.PROFILE)
                self.assertEqual(outcome['status'], 'complete' if variant == 'valid' else 'failed')
                self.assertEqual(outcome['acceptance']['scl_behavior'], variant == 'valid')

    def test_mcode_failure_preserves_source_and_bound_diagnostics(self):
        candidate=result(request())
        candidate['scl_files']=[{'name':'Broken.scl','content':'broken source'}]
        validation={'status':'fail','request_fingerprint':candidate['request_fingerprint'],
                    'files':[{'name':'Broken.scl','sha256':hashlib.sha256(b'broken source').hexdigest()}],
                    'checks':[{'name':'Linux compile','status':'fail','detail':'type mismatch'}]}
        envelope={'verdict':'rejected','result':None,'candidate':candidate,
                  'validation':validation,'attempts':[{'attempt':0}]}
        outcome=self.run_stub(json.dumps(envelope),provider='mcode-cm',timeout=0)
        self.assertEqual(outcome['status'],'failed')
        self.assertEqual(outcome['candidate_result'],candidate)
        self.assertEqual(outcome['verification'],validation)
        self.assertEqual(outcome['workflow']['attempts'],[{'attempt':0}])
        self.assertIn('type mismatch',outcome['error'])
        envelope['validation']['files'][0]['sha256']='stale'
        outcome=self.run_stub(json.dumps(envelope),provider='mcode-cm',timeout=0)
        self.assertEqual(outcome['status'],'failed')
        self.assertNotIn('candidate_result',outcome)

    def test_review_approval_without_current_tool_evidence_is_rejected(self):
        outcome=self.run_stub(json.dumps({'verdict':'reviewed_draft','result':result(request())}),
                              provider='mcode-cm',timeout=0)
        self.assertEqual(outcome['status'],'failed')
        self.assertIn('没有返回',outcome['error'])

    def test_legacy_total_pass_does_not_satisfy_new_workflow_gate(self):
        candidate=result(request())
        candidate['scl_files']=[{'name':'Test.scl','content':'fixture'}]
        report={'status':'pass','request_fingerprint':candidate['request_fingerprint'],
                'files':[{'name':'Test.scl','sha256':hashlib.sha256(b'fixture').hexdigest()}],
                'checks':[],'acceptance':{'scl_behavior':True}}
        outcome=self.run_stub(json.dumps({'verdict':'reviewed_draft','result':candidate,'validation':report}),
                              provider='mcode-cm',timeout=0)
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
                                      provider='mcode-cm',timeout=0)
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

    def test_http_rejects_foreign_origin_and_exposes_missing_provider(self):
        server=bridge.ThreadingHTTPServer(('127.0.0.1',0),bridge.Handler)
        server.bridge=bridge.GenerationBridge(None)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        try:
            self.assertFalse(json.load(urlopen(url+'/api/capabilities'))['ready'])
            req=Request(url+'/api/generate',data=b'{}',headers={'Content-Type':'application/json','X-PLC-Workspace':'1','Origin':'https://foreign.example'})
            with self.assertRaises(HTTPError) as error:urlopen(req)
            self.assertEqual(error.exception.code,403)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
