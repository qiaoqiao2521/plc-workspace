import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).with_name('local-server.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

def request():
    brief = {k: '' for k in ['name','block_name','requirement','flow','io_text','constraints']}
    brief.update(name='test',block_name='FB_Test',requirement='启动输送，到位停止，故障撤销动作。')
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

    def run_stub(self, stdout, code=0, delay=0, cancel=False, provider="agy", timeout=2):
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/'fake-agy'
            script.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep('+str(delay)+')\nprint('+repr(stdout)+')\nraise SystemExit('+str(code)+')\n')
            script.chmod(0o755)
            server=bridge.GenerationBridge(str(script),timeout=timeout,provider=provider,node=str(script))
            job=server.begin(request(),'prompt')
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
