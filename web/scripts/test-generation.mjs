import test from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {flowDraft, makeRequest, validateBrief, validateResult, agentPrompt, openEngineering, ladTitle, conveyorAcceptanceBrief, latchAcceptanceBrief, LATCH_PROFILE, canonicalJson, bindVerification, sourceHash, verificationSummary} from '../generation-model.js';
import {validateLadGraph,layoutLadNetwork} from '../lad-graph.js';
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

function currentReport(profile) {
  const targets={source_structure:'candidate',linux_compile:'scl_compile',scan_contract:'scl_behavior',lad_scl_compare:'lad_scl_compare',tia_compile:'tia_compile'};
  const required=['source_structure','linux_compile',...(profile?['scan_contract']:[]),...(profile===LATCH_PROFILE?['lad_scl_compare']:[])];
  return {schema_version:2,profile:profile || null,target:profile===LATCH_PROFILE?'lad_scl_compare':profile?'scl_behavior':'scl_compile',status:'pass',required_checks:required,
    acceptance:{scl_behavior:true,tia_compile:true},
    checks:Object.entries(targets).map(([name,target])=>({name,target,required:required.includes(name),status:required.includes(name)?'pass':'not_run',detail:'Synthetic evidence'}))};
}

test('compile-only result is explicitly separate from behavior acceptance',()=>{
  const summary=verificationSummary(currentReport(),{current:true,approved:true});
  assert.equal(summary.title,'编译通过，行为未验收');
  assert.equal(summary.acceptance.scl_compile,true);
  assert.equal(summary.acceptance.scl_behavior,false);
  assert.equal(summary.acceptance.tia_compile,false);
});

test('required failure unknown and not-run cannot be hidden behind a forged total pass',()=>{
  const profile='conveyor-12-v1';
  for(const name of ['source_structure','linux_compile','scan_contract']) for(const status of ['fail','unknown','not_run']){
    const report=currentReport(profile);report.checks.find(c=>c.name===name).status=status;
    const summary=verificationSummary(report,{profile,current:true,approved:true});
    assert.equal(summary.status,status);assert.equal(Object.values(summary.acceptance).some(Boolean),false);
  }
  const passed=verificationSummary(currentReport(profile),{profile,current:true,approved:true});
  assert.equal(passed.title,'受限 SCL 行为检查通过');assert.equal(passed.acceptance.scl_behavior,true);
});

test('legacy imported cancelled unapproved and incomplete results cannot regain current acceptance',async()=>{
  const profile='conveyor-12-v1',report=currentReport(profile);
  for(const options of [{},{profile},{profile,current:false,approved:true},{profile,current:true,approved:false}]){
    assert.equal(Object.values(verificationSummary(report,options).acceptance).some(Boolean),false);
  }
  const incomplete=structuredClone(report);incomplete.checks=incomplete.checks.filter(c=>c.name!=='scan_contract');
  assert.equal(verificationSummary(incomplete,{profile,current:true,approved:true}).status,'unknown');
  const waived=structuredClone(report);waived.checks.find(c=>c.name==='scan_contract').required=false;
  assert.equal(verificationSummary(waived,{profile,current:true,approved:true}).status,'unknown');
  const legacy=structuredClone(report);delete legacy.schema_version;
  assert.equal(verificationSummary(legacy,{profile,current:true,approved:true}).status,'unknown');
  for(const reason of ['cancelled','worker_failed','tool_timeout']) {
    assert.equal(verificationSummary({...report,reason},{profile,current:true,approved:true}).status,'unknown');
  }
  const req=await makeRequest({...brief,validation_profile:profile},[]),res=candidate(req);
  report.request_fingerprint=req.request_fingerprint;
  report.files=[{name:res.scl_files[0].name,sha256:await sourceHash(res.scl_files[0].content)}];
  const restored=await openEngineering({kind:'agent_candidate',request:req,result:res,verification:report,workflow:{verdict:'reviewed_draft',acceptance:{scl_behavior:true}}});
  assert.equal(Object.values(verificationSummary(restored.verification,{profile}).acceptance).some(Boolean),false);
});

test('same source with changed requirements cannot reuse a v2 report',async()=>{
  const req=await makeRequest(brief,[]),res=candidate(req),report=currentReport();
  report.request_fingerprint=req.request_fingerprint;
  report.files=[{name:res.scl_files[0].name,sha256:await sourceHash(res.scl_files[0].content)}];
  assert.equal((await bindVerification(report,res)).request_fingerprint,req.request_fingerprint);
  const changed=await makeRequest({...brief,requirement:brief.requirement+' 修改等待规则。'},[]);
  await assert.rejects(bindVerification(report,candidate(changed)),/需求不匹配/);
});

test('display rejects duplicate, relabeled, unsupported and unselected checks',()=>{
  const profile='conveyor-12-v1';
  const mutations=[
    report=>{report.checks[2]=structuredClone(report.checks[1]);},
    report=>{report.checks[2].target='scl_compile';},
    report=>{report.checks[2].required=false;},
    report=>{report.checks[2].detail=null;},
    report=>{report.required_checks=['source_structure','linux_compile'];},
    report=>{report.checks.find(c=>c.name==='tia_compile').status='pass';},
    report=>{report.checks.find(c=>c.name==='lad_scl_compare').status='pass';},
  ];
  for(const mutate of mutations){
    const report=currentReport(profile); mutate(report);
    const summary=verificationSummary(report,{profile,current:true,approved:true});
    assert.equal(summary.status,'unknown');
    assert.equal(Object.values(summary.acceptance).some(Boolean),false);
  }
  const unselected=currentReport();
  unselected.checks.find(c=>c.name==='scan_contract').status='pass';
  assert.equal(verificationSummary(unselected,{current:true,approved:true}).status,'unknown');
  assert.equal(verificationSummary(currentReport('unsupported'),{profile:'unsupported',current:true,approved:true}).status,'unknown');
});

// Use the real deterministic product serializer for frontend format compatibility.
// The behavior of this example is tested separately by the native/graph checks.
const products=JSON.parse(execFileSync('python3',['-c',`
import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('logic',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ir=m.example_ir()
print(json.dumps({'logic_ir':ir,'lad_graph':m.emit_lad(ir),'scl':m.emit_scl(ir)}))
`,fileURLToPath(new URL('./logic-ir.py',import.meta.url))],{encoding:'utf8'}));
const dualCandidate = req => ({...candidate(req),scl_files:[{name:'FB_StartStop.scl',content:products.scl}],
  logic_ir:structuredClone(products.logic_ir),lad_graph:structuredClone(products.lad_graph)});

test('synthetic latch contract is explicit and cannot silently accept edited process or source',async()=>{
  const input=latchAcceptanceBrief();
  const req=await makeRequest(input,[]);
  assert.equal(req.brief.validation_profile,LATCH_PROFILE);
  assert.match(req.brief.requirement,/不是现场设备默认工艺/);
  for(const key of ['block_name','requirement','flow','io_text','constraints']) {
    assert.notEqual(validateBrief({...input,[key]:input[key]+'changed'}).length,0);
  }
  assert.notEqual(validateBrief({...input,source_files:[{name:'Old.scl',content:'old'}]}).length,0);
  await assert.rejects(makeRequest(input,[{id:1,name:'extra'}]),/附加状态/);
  assert.equal(validateBrief({...input,name:'My demo',target:{cpu:'S7-1500',tia_version:'V21'}}).length,0);
  assert.match(agentPrompt(req),/只提出/);
  assert.equal(input.requirement,latchAcceptanceBrief().requirement);
});

test('S2 result requires both serialized products with matching symbols and no legacy shell',async()=>{
  const req=await makeRequest(latchAcceptanceBrief(),[]),res=dualCandidate(req);
  assert.equal(validateResult(res,req),res);
  const noGraph=structuredClone(res);delete noGraph.lad_graph;
  assert.throws(()=>validateResult(noGraph,req),/IR\/LAD/);
  const symbols=structuredClone(res);symbols.logic_ir.symbols[0].initial=true;
  assert.throws(()=>validateResult(symbols,req),/符号声明不一致/);
  const oldRequest=await makeRequest(brief,[]);
  assert.throws(()=>validateResult({...res,request_id:oldRequest.request_id,request_fingerprint:oldRequest.request_fingerprint},oldRequest),/IR\/LAD/);
});

test('S2 scoped pass needs independent behavior and graph comparison; failures never inherit aggregate pass',()=>{
  const profile=LATCH_PROFILE,report=currentReport(profile);
  const passed=verificationSummary(report,{profile,current:true,approved:true});
  assert.equal(passed.acceptance.scl_behavior,true);
  assert.equal(passed.acceptance.lad_scl_compare,true);
  assert.equal(passed.acceptance.tia_compile,false);
  for(const name of report.required_checks) for(const status of ['fail','unknown','not_run']) {
    const broken=structuredClone(report);broken.checks.find(c=>c.name===name).status=status;
    const summary=verificationSummary(broken,{profile,current:true,approved:true});
    assert.equal(summary.status,status);assert.equal(Object.values(summary.acceptance).some(Boolean),false);
  }
  for(const reason of ['cancelled','worker_failed','invalid_report']) {
    assert.equal(verificationSummary({...report,reason},{profile,current:true,approved:true}).status,'unknown');
  }
  const forged=structuredClone(report);forged.checks.find(c=>c.name==='tia_compile').status='pass';
  assert.equal(verificationSummary(forged,{profile,current:true,approved:true}).status,'unknown');
});

test('IR and LAD hashes bind current products and imported passes remain history',async()=>{
  const req=await makeRequest(latchAcceptanceBrief(),[]),res=dualCandidate(req),verification=currentReport(LATCH_PROFILE);
  verification.request_fingerprint=req.request_fingerprint;
  verification.files=[{name:res.scl_files[0].name,sha256:await sourceHash(res.scl_files[0].content)}];
  verification.logic_ir_sha256=await sourceHash(canonicalJson(res.logic_ir));
  verification.lad_graph_sha256=await sourceHash(canonicalJson(res.lad_graph));
  const value={kind:'agent_candidate',request:req,result:res,verification,workflow:{verdict:'reviewed_draft'}};
  const restored=await openEngineering(value);
  assert.deepEqual(restored.result.lad_graph,res.lad_graph);
  assert.equal(verificationSummary(restored.verification,{profile:LATCH_PROFILE}).acceptance.lad_scl_compare,false);
  const changedIr=structuredClone(res);changedIr.logic_ir.networks[0].expression.children[0].negated=true;
  await assert.rejects(bindVerification(verification,changedIr),/IR\/LAD/);
  const changedGraph=structuredClone(res);changedGraph.lad_graph.networks[0].nodes.find(n=>n.kind==='contact').negated=true;
  await assert.rejects(bindVerification(verification,changedGraph),/IR\/LAD/);
  const missingHash={...verification};delete missingHash.lad_graph_sha256;
  await assert.rejects(bindVerification(missingHash,res),/IR\/LAD/);
  assert.equal(canonicalJson({z:[{b:2,a:1}],a:false}),'{"a":false,"z":[{"a":1,"b":2}]}');
});

test('structurally rejected IR stays reviewable without fabricating missing products',async()=>{
  const req=await makeRequest(latchAcceptanceBrief(),[]),res=dualCandidate(req),verification=currentReport(LATCH_PROFILE);
  res.logic_ir.networks.push(structuredClone(res.logic_ir.networks.at(-1)));
  res.scl_files=[];delete res.lad_graph;
  assert.equal(validateResult(res,req),res);
  Object.assign(verification,{status:'fail',reason:'source_invalid',files:[],request_fingerprint:req.request_fingerprint,
    logic_ir_sha256:await sourceHash(canonicalJson(res.logic_ir)),lad_graph_sha256:null});
  verification.checks.forEach(c=>{c.status=c.name==='source_structure'?'fail':'not_run';});
  const restored=await openEngineering({kind:'agent_candidate',request:req,result:res,verification});
  assert.deepEqual(restored.result.logic_ir,res.logic_ir);
  assert.equal(restored.result.lad_graph,undefined);
  assert.equal(verificationSummary(verification,{profile:LATCH_PROFILE,current:true,approved:true}).acceptance.lad_scl_compare,false);
  for (const forged of [{...verification,status:'pass'},{...verification,reason:null},{...verification,checks:[]}]) {
    await assert.rejects(bindVerification(forged,res),/IR\/LAD/);
  }
});

test('graph preview keeps every generated wire, branch, symbol and contact polarity',()=>{
  validateLadGraph(products.lad_graph);
  for(const network of products.lad_graph.networks) {
    const layout=layoutLadNetwork(network);
    assert.deepEqual(layout.nodes.map(({x,y,...n})=>n),network.nodes);
    assert.deepEqual(layout.edges.map(({path,...edge})=>edge),network.edges);
    assert.ok(layout.nodes.every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)));
    assert.deepEqual(layoutLadNetwork(network),layout);
    if(network.nodes.some(n=>n.kind==='junction')) {
      assert.ok(new Set(layout.nodes.filter(n=>n.kind==='contact').map(n=>n.y)).size>1,'Parallel contacts need distinct branches');
      assert.ok(layout.edges.some(e=>/ V /.test(e.path)),'Parallel wires must connect different branch heights');
    }
  }
});

test('graph display refuses broken connections, duplicate writers and changed polarity types',()=>{
  const mutate=[
    graph=>{graph.networks[0].edges[0].to='missing';},
    graph=>{graph.networks[0].nodes.find(n=>n.kind==='contact').negated='false';},
    graph=>{graph.networks[1].nodes.find(n=>n.kind==='coil').symbol='StartRise';},
    graph=>{graph.networks[0].nodes.push({id:'orphan',kind:'junction'});},
    graph=>{graph.networks[0].edges.push({...graph.networks[0].edges[0]});},
  ];
  for(const change of mutate) { const graph=structuredClone(products.lad_graph);change(graph);assert.throws(()=>validateLadGraph(graph),/LAD 图格式错误/); }
});
