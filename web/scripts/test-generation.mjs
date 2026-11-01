import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {flowDraft, makeRequest, validateBrief, validateResult, agentPrompt, openEngineering, ladTitle, conveyorAcceptanceBrief, bindVerification, sourceHash} from '../generation-model.js';
if (!globalThis.crypto) globalThis.crypto = webcrypto;
const brief = {name:'测试输送线',block_name:'FB_Test',requirement:'启动后输送，到位停止。停止撤销动作。',flow:'输送 → 到位 → 输送',io_text:'',constraints:'',target:{cpu:'unknown',tia_version:'unknown'}};
const candidate = req => ({schema_version:1,request_id:req.request_id,request_fingerprint:req.request_fingerprint,summary:'未验证草稿',questions:[],states:[],io:[],scl_files:[{name:'FB_Test.scl',content:'FUNCTION_BLOCK FB_Test\nEND_FUNCTION_BLOCK'}],lad_networks:[],checks:[]});
test('flow draft preserves cycle link and leaves process conditions unguessed',()=>{const states=flowDraft(brief.flow);assert.equal(states.length,2);assert.equal(states[1].next_state,'输送');assert.equal(states[0].completion,'');});
test('request freezes input values; changed process has a different fingerprint',async()=>{const states=flowDraft(brief.flow),req=await makeRequest(brief,states);states[0].actions='changed';assert.equal(req.states[0].actions,'');assert.notEqual((await makeRequest(brief,states)).request_fingerprint,req.request_fingerprint);});
test('old result or other request cannot bind to current requirements',async()=>{const first=await makeRequest(brief,[]),second=await makeRequest({...brief,requirement:brief.requirement+'附加夹紧联锁'},[]);assert.throws(()=>validateResult(candidate(first),second),/不匹配/);assert.throws(()=>validateResult(candidate(first),undefined),/先准备/);});
test('result validator rejects path traversal, duplicate code files and malformed networks',async()=>{const req=await makeRequest(brief,[]),result=candidate(req);result.scl_files[0].name='../outside.scl';assert.throws(()=>validateResult(result,req),/文件名/);result.scl_files=[{name:'FB_Test.scl',content:''},{name:'FB_Test.scl',content:''}];assert.throws(()=>validateResult(result,req),/重复/);result.scl_files=[];result.lad_networks=[{title:'network',kind:'rung',contacts:null,bindings:[],coil:'q',block:'',instance:'',note:''}];assert.throws(()=>validateResult(result,req),/LAD/);});
test('model claims are transported as reports, not a proof flag',async()=>{const req=await makeRequest(brief,[]),result=candidate(req);result.checks=[{name:'scan',status:'pass',detail:'model claim'}];const accepted=validateResult(result,req);assert.equal(accepted.verified,undefined);assert.match(agentPrompt(req),/not_run\/unknown/);assert.equal(validateBrief({...brief,block_name:'../invalid'}).length,1);});

test('engineering reopen restores original binding without weakening result import',async()=>{
  const req=await makeRequest(brief,flowDraft(brief.flow)),res=candidate(req);
  const value={kind:'repository_example',request:req,result:res,verification_status:'pass'};
  const restored=await openEngineering(value);
  assert.equal(restored.request.request_id,req.request_id); assert.equal(restored.verified,undefined);
  restored.request.brief.name='edited'; assert.equal(req.brief.name,brief.name);
  assert.throws(()=>validateResult(res,{...req,request_id:'new-task'}),/不匹配/);
});
test('engineering reopen rejects tampering and malformed states before restoration',async()=>{
  const req=await makeRequest(brief,[]),value={kind:'agent_candidate',request:req,result:candidate(req)};
  await assert.rejects(openEngineering({...value,request:{...req,brief:{...brief,name:'tampered'}}}),/指纹/);
  await assert.rejects(openEngineering({...value,request:{...req,states:[null]}}),/状态/);
  await assert.rejects(openEngineering({...value,result:{...value.result,request_id:'other'}}),/不匹配/);
});
test('LAD display and export share prefix normalization without modifying candidates',()=>{
  assert.equal(ladTitle('网络 1: 周期调用'),'周期调用');
  assert.equal(ladTitle('Network 2 · Motor'),'Motor');
  assert.equal(ladTitle('第1缸到位'),'第1缸到位');
});

test('original source and selected scan contract are frozen into the request identity',async()=>{
  const original='FUNCTION_BLOCK "FB_ConveyorPack"\n// 原程序\nEND_FUNCTION_BLOCK';
  const input=conveyorAcceptanceBrief(original),req=await makeRequest(input,[]);
  assert.equal(req.brief.source_files[0].content,original);
  assert.equal(req.brief.validation_profile,'conveyor-12-v1');
  assert.match(req.brief.requirement,/第 1～11 次/);
  input.source_files[0].content+='\n';
  assert.notEqual((await makeRequest(input,[])).request_fingerprint,req.request_fingerprint);
  assert.notEqual((await makeRequest({...req.brief,validation_profile:''},[])).request_fingerprint,req.request_fingerprint);
  assert.equal(req.brief.source_files[0].content,original);
  assert.match(agentPrompt(req),/原程序/);
});

test('saved source-bound diagnostics and repair diffs survive reopening a failed candidate',async()=>{
  const req=await makeRequest(brief,[]),res=candidate(req);
  res.scl_files[0].content+='\n// 中文输入\r\n';
  const verification={status:'fail',scope:'Linux only',files:[{name:res.scl_files[0].name,sha256:await sourceHash(res.scl_files[0].content)}],checks:[{name:'matiec',status:'fail',detail:'type mismatch'}]};
  const workflow={verdict:'rejected',attempts:[{attempt:1,validation:verification,diff:'- old\n+ repaired'}]};
  const value={kind:'agent_candidate',request:req,result:res,verification,workflow};
  const restored=await openEngineering(value);
  assert.equal(restored.verification.status,'fail');
  assert.equal(restored.workflow.attempts[0].diff,workflow.attempts[0].diff);
  assert.equal(restored.verified,undefined);
  restored.verification.files[0].name='changed';
  assert.equal(verification.files[0].name,'FB_Test.scl');
  const changed=structuredClone(value); changed.result.scl_files[0].content+='\n';
  await assert.rejects(openEngineering(changed),/源码不匹配/);
});

test('verification binding rejects partial, duplicate and wrong-name evidence',async()=>{
  const req=await makeRequest(brief,[]),res=candidate(req);
  res.scl_files.push({name:'FC_Helper.scl',content:'FUNCTION FC_Helper : BOOL\nEND_FUNCTION'});
  const report={status:'pass',checks:[],files:await Promise.all(res.scl_files.map(async f=>({name:f.name,sha256:await sourceHash(f.content)})))};
  assert.equal((await bindVerification(report,res)).status,'pass');
  await assert.rejects(bindVerification({...report,files:report.files.slice(0,1)},res),/格式错误/);
  await assert.rejects(bindVerification({...report,files:[report.files[0],report.files[0]]},res),/指纹错误/);
  await assert.rejects(bindVerification({...report,files:[report.files[0],{...report.files[1],name:'Another.scl'}]},res),/源码不匹配/);
});
