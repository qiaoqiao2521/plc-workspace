import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const root = new URL('../',import.meta.url);
const project = new URL('../projects/FB_MainSequence/',root);
const traces = JSON.parse(await readFile(new URL('data/traces.json',root),'utf8'));
const brief = {
  name:'翻转输送线（仓库抽象示例）', block_name:'FB_MainSequence',
  requirement:'完成初始化后，新 Start 上升沿进入输送。输送完成进入翻转，翻转完成进入出料，出料完成返回输送并输出单拍 Done，持续循环。Enable 连续使能；Stop/EStop 撤销动作并取消健康命令，已有故障保留。Reset 只重置健康命令；块错误需实际执行禁用调用才能清除。重新使能开启新诊断会话。没有新的 Start 沿不重新启动。',
  flow:'输送 → 翻转 → 出料 → 输送',
  io_text:'xInitDone、xTransportDone、xFlipDone、xOutputDone 为语义反馈；xBeltForward、xQ1、xQ2 为动作命令。Main 映射物理 I/O，FB 无硬件地址。',
  constraints:'内部状态与输出分离。每调用最多迁移一步；Start/Reset 沿在禁用或停止期间仍消费。超时单位为扫描调用数，默认阈值 8；阈值 0 清空计数并禁用超时。到期同拍完成优先。EStop 是外部抑制反馈。非断电保持证明，TIA/CPU/固件未定。',
  target:{cpu:'unknown',tia_version:'unknown',architecture:'Main LAD / FB SCL'}
};
const states = [
  {id:0,name:'初始',actions:'无动作输出',completion:'使能且无抑制，InitDone 与新的 Start 沿',next_state:'1 输送'},
  {id:1,name:'输送',actions:'BeltForward',completion:'TransportDone',next_state:'2 翻转'},
  {id:2,name:'翻转',actions:'StartLamp、Q1',completion:'FlipDone',next_state:'3 出料'},
  {id:3,name:'出料',actions:'BeltForward、StartLamp、Q2',completion:'OutputDone；本拍 Done',next_state:'1 输送'},
  {id:900,name:'故障',actions:'撤销动作输出',completion:'执行 xEnable=FALSE 调用清除当前错误',next_state:'0 初始'}
];
const request = {schema_version:1,request_id:'repository-example-v0.3',request_fingerprint:createHash('sha256').update(JSON.stringify({brief,states})).digest('hex'),brief,states};
const paths = Object.keys(traces.source_hashes);
const scl_files = await Promise.all(paths.map(async p => ({name:p.split('/').at(-1).replace(/\.st$/,'.scl'),content:await readFile(new URL('../'+p,root),'utf8')})));
const fb = scl_files.at(-1).content;
const io = [];
for (const [marker,direction] of [['VAR_INPUT','input'],['VAR_OUTPUT','output']]) {
  const declarations = fb.split(marker)[1].split('END_VAR')[0];
  for (const line of declarations.split('\n')) { const match = line.match(/^\s*(\w+)\s*:\s*(\w+)/); if (match) io.push({direction,name:match[1],type:match[2],description:'仓库接口 0.2.0 的语义信号；未分配物理地址'}); }
}
const base = {contacts:[],coil:'',block:'',instance:'',bindings:[]};
const call = {...base,title:'周期调用顺控 FB',kind:'call',block:'FB_MainSequence',instance:'dbMainSequence',bindings:io.filter(s=>s.direction==='input').map(s=>({parameter:s.name,symbol:'#'+s.name})),note:'EN=TRUE，必须每拍调用；xEnable 作为参数，以执行禁用清除与边沿消费。实例和接线是 Main 的候选规格，实机 Main 尚未提供。'};
const lad_networks = [call,...['xBeltForward','xQ1','xQ2'].map(symbol=>({...base,title:`映射 ${symbol} 命令`,kind:'rung',contacts:[{symbol:`dbMainSequence.${symbol}`,negated:false}],coil:`${symbol}_Command`,note:'只映射语义命令。物理输出、独立安全回路及子单元联锁需按真实机器工程落实。'}))];
const result = {...request}; delete result.brief; delete result.states;
Object.assign(result,{summary:'仓库已有 FB_MainSequence v0.3 抽象核心。以下 SCL 直接取自规范 ST 源码；LAD 为与接口衔接的 Main 网络审阅草稿。',questions:['实际 TIA Portal、CPU、固件、Main 和子单元 FB 尚未提供。','需要独立落实物理 I/O、安全反馈与保持配置。'],states,io,scl_files,lad_networks,checks:[{name:'编译 ST 扫描测试',status:'pass',detail:'仓库已发布 27 项扫描测试记录，只对应已有抽象核心。'},{name:'形式验证',status:'pass',detail:'32 条断言的已发布记录，绑定规范源码投影。'},{name:'TIA 编译 / LAD / 现场验收',status:'not_run',detail:'LAD Main 是候选网络，不继承核心 ST 的验证结果。'}]});
const example = {request,result,provenance:{kind:'repository_example',source_hashes:traces.source_hashes,formal_source_sha256:traces.formal_source_sha256}};
await writeFile(new URL('dist/data/example.json',root),JSON.stringify(example,null,2)+'\n');
