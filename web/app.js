const $ = (id) => document.getElementById(id);
const phaseNames = {0:'初始',1:'输送',2:'翻转',3:'出料',900:'故障'};
const inputNames = {enable:'Enable',start:'Start',estop:'EStop',stop:'Stop',reset:'Reset',init_done:'InitDone',transport_done:'TransportDone',flip_done:'FlipDone',output_done:'OutputDone'};
const outputNames = {belt_forward:'BeltForward',q1:'Q1',q2:'Q2',done:'Done',command_busy:'CommandBusy',command_aborted:'CommandAborted',error:'Error',timeout_fault:'TimeoutFault',timeout_diagnostic:'TimeoutDiagnostic'};
let data, scenario, index = 0, interval;
const text = (id,value) => { $(id).textContent = value; };
function stop(){ clearInterval(interval); interval = undefined; text('play','播放回放'); $('play').setAttribute('aria-pressed','false'); }
function selectScenario(id){
  stop(); scenario = data.scenarios.find(s=>s.id === id) || data.scenarios[0]; index=0;
  text('scene-title',scenario.title);text('scene-description',scenario.description);
  document.querySelectorAll('.scenario-button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===scenario.id)));
  $('scan-range').max=scenario.frames.length-1; $('timeline').replaceChildren();
  for(const [i,frame] of scenario.frames.entries()){
    const tr=document.createElement('tr'); const o=frame.outputs;
    const td=document.createElement('td'), b=document.createElement('button'); b.className='row-select'; b.textContent=String(frame.scan).padStart(2,'0'); b.setAttribute('aria-label',`跳到第 ${frame.scan} 拍`); td.append(b);tr.append(td);
    const active=Object.entries(frame.inputs).filter(([,v])=>v).map(([k])=>inputNames[k]);
    for(const value of [active.join(' · ') || '全部关闭',`${o.phase} ${phaseNames[o.phase]}`,`${o.timer} / ${frame.timeout || '禁用'}`]){const cell=document.createElement('td');cell.textContent=value;tr.append(cell);}
    const status=document.createElement('td'),tag=document.createElement('span');tag.className=`table-tag${o.error?' error':''}`;tag.textContent=o.error?'故障锁存':o.done?'周期完成':o.command_busy?'执行中':o.command_aborted?'已取消':'待命';status.append(tag);tr.append(status);
    tr.addEventListener('click',()=>{stop();index=i;render();});$('timeline').append(tr);
  }
  render();
}
function signals(id,names,values){
  $(id).replaceChildren();
  for(const [key,label] of Object.entries(names)){
    const row=document.createElement('div');row.className=`signal-row${values[key]?' on':''}${key.includes('fault')||key==='error'?' danger':''}`;
    const name=document.createElement('span');name.textContent=label;
    const value=document.createElement('span');value.className='signal-value';value.textContent=values[key]?'1':'0';
    const led=document.createElement('span');led.className='signal-led';led.setAttribute('aria-hidden','true');value.append(led);row.append(name,value);$(id).append(row);
  }
}
function render(){
  const f=scenario.frames[index],o=f.outputs;
  text('phase-chip',`相位 ${o.phase} · ${phaseNames[o.phase]}`);$('phase-chip').classList.toggle('error',!!o.error);
  text('machine-state',o.error?'故障 / 动作已撤销':o.command_busy?'工艺执行中':'待命 / 无动作');
  document.querySelectorAll('[data-phase]').forEach(el=>el.classList.toggle('on',Number(el.dataset.phase)===o.phase));
  document.querySelectorAll('[data-machine]').forEach(el=>el.classList.toggle('on',Number(el.dataset.machine)===o.phase&&!!o.command_busy));
  text('scan-number',String(f.scan).padStart(2,'0'));text('timer-number',`${o.timer} / ${f.timeout||'禁用'}`);
  text('command-state',o.error?'故障锁存':o.command_busy?'执行中':o.command_aborted?'已取消':'待命');
  text('scan-note',f.note);text('scan-position',`${index+1} / ${scenario.frames.length}`);$('scan-range').value=index;
  $('prev').disabled=index===0;$('next').disabled=index===scenario.frames.length-1;
  signals('inputs',inputNames,f.inputs);signals('outputs',outputNames,o);
  [...$('timeline').children].forEach((row,i)=>{row.classList.toggle('selected',i===index);row.querySelector('button').setAttribute('aria-current',String(i===index));});
}
function next(){if(index<scenario.frames.length-1){index++;render();}if(index===scenario.frames.length-1)stop();}
function play(){if(interval){stop();return;}if(index===scenario.frames.length-1){index=0;render();}text('play','暂停回放');$('play').setAttribute('aria-pressed','true');interval=setInterval(next,Number($('speed').value));}
$('play').addEventListener('click',play);
$('next').addEventListener('click',()=>{stop();next();});$('prev').addEventListener('click',()=>{stop();index=Math.max(0,index-1);render();});
$('rewind').addEventListener('click',()=>{if(!scenario)return;stop();index=0;render();});
$('scan-range').addEventListener('input',e=>{stop();index=Number(e.target.value);render();});
$('speed').addEventListener('change',()=>{if(interval){stop();play();}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
$('download').addEventListener('click',()=>{const blob=new Blob([JSON.stringify({kind:data.kind,contract:data.contract,source_hashes:data.source_hashes,scenario},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`plc-trace-${scenario.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
async function load(){
 try{
  $('load-error').hidden=true;
  const res=await fetch('./data/traces.json');if(!res.ok)throw Error(`HTTP ${res.status}`);data=await res.json();
  if(data.schema!==1||!data.scenarios?.length)throw Error('Invalid trace data');
  $('scenarios').replaceChildren();
  data.scenarios.forEach((s,i)=>{const b=document.createElement('button');b.className='scenario-button';b.dataset.id=s.id;const n=document.createElement('span');n.textContent=String(i+1).padStart(2,'0');b.append(n,document.createTextNode(s.title));b.addEventListener('click',()=>selectScenario(s.id));$('scenarios').append(b);});
  $('metrics').replaceChildren();
  for(const [key,label,unit] of [['scan_tests','编译 ST 扫描测试','项'],['formal_assertions','形式验证断言','条'],['control_combinations','同时控制输入组合','组'],['differential_calls','同源投影差分调用','次']]){const div=document.createElement('div');div.className='metric';const num=document.createElement('strong');num.textContent=data.evidence[key].toLocaleString('zh-CN');const u=document.createElement('span');u.className='metric-unit';u.textContent=unit;num.append(u);const caption=document.createElement('span');caption.textContent=label;div.append(num,caption);$('metrics').append(div);}
  text('source-hash',`source ${data.formal_source_sha256.slice(0,12)}`);
  for(const id of ['play','download','scan-range'])$(id).disabled=false;
  selectScenario('cycle');
 }catch(error){stop();$('load-error').hidden=false;text('scene-title','暂时无法加载场景');for(const id of ['play','download','scan-range','prev','next'])$(id).disabled=true;console.error('Trace load failed',error);}
}
$('retry').addEventListener('click',load);load();
