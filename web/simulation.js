const $ = id => document.getElementById(id);
let session, busy = false, playing = false, timer, view, latest;
const names = ['Motor','Busy','Done','Error','TimeoutFault'];
for (const name of names) {
  const span = document.createElement('span'); span.id = `out-${name}`;
  span.append(document.createTextNode(name), document.createElement('b'));
  span.lastChild.textContent = '0'; $('outputs').append(span);
}
async function request(action, body) {
  const response = await fetch(`/api/simulation/${action}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || '请求失败'); return result;
}
function pause() { playing = false; view?.setPlayback(false); clearTimeout(timer); $('play').textContent = '连续运行'; }
function controls() { for (const id of ['start','step','play','reset','new']) $(id).disabled = busy || (id !== 'new' && !session); }
function render(result) {
  const o = result.outputs;
  latest=result; view?.update(result);
  $('scan').textContent = result.scan; $('wait').textContent = o.statWaitCount;
  $('position').textContent = `${Math.round(result.position * 100)}%`;
  $('phase').textContent = o.Error ? '故障锁存' : {1:'待机',2:'输送',3:'完成脉冲'}[o.statState];
  for (const name of names) { const span = $(`out-${name}`); span.lastChild.textContent = o[name]; span.className = o[name] ? (name.includes('Error') || name.includes('Fault') ? 'fault' : 'on') : ''; }
  const row = document.createElement('tr'); row.className = o.Error ? 'fault' : o.Done ? 'done' : '';
  for (const value of [result.scan, Object.keys(result.inputs).filter(k=>result.inputs[k]).join(', ') || '—', o.statState, o.statWaitCount, ...names.map(k=>o[k])]) { const td = document.createElement('td'); td.textContent = value; row.append(td); }
  $('trace').prepend(row); if ($('trace').children.length > 40) $('trace').lastChild.remove();
  $('message').textContent = o.Error ? '故障仍锁存。解除 Stop 后，释放 Reset 再给一个新边沿。' : o.Done ? '本拍 Done=1；继续单步可看到脉冲清除。' : '每个记录行对应一次真实 FB 调用。';
}
async function scan(pulse = '') {
  if (busy || !session) return;
  busy = true; controls();
  try { render(await request('step', {session,inputs:{Enable:$('enable').checked, Start:pulse==='Start', Stop:$('stop').checked, Reset:pulse==='Reset'},jam:$('jam').checked,sensor_failed:$('sensor-failed').checked})); }
  catch (error) { pause(); $('message').textContent = error.message; }
  finally { busy = false; controls(); }
}
async function loop() { if (!playing) return; await scan(); if (playing) timer = setTimeout(loop,500); }
async function fresh() {
  if (busy) return; pause(); busy = true; controls();
  try {
    if (session) await request('close',{session}); session = undefined;
    const result = await request('new',{}); session = result.session;
    $('trace').replaceChildren(); latest=undefined; view?.reset();
    $('scan').textContent = '0'; $('wait').textContent = '0'; $('position').textContent = '0%'; $('phase').textContent = '待机（初始化）';
    for (const name of names) { $(`out-${name}`).className=''; $(`out-${name}`).lastChild.textContent='0'; }
    $('source-hash').textContent = `执行源 SHA256：${result.source_sha256}；适配后 ST：${result.normalized_sha256}`;
    $('message').textContent = 'PLC 与工件已初始化。点击启动，或先选择卡住工件。连续两次 Start／Reset 之间需单步释放边沿。';
  } catch (error) { session = undefined; $('message').textContent = `无法连接仿真服务：${error.message}。请按仓库 web/README.md 启动 simulation-server.py（8767 端口）。`; }
  finally { busy = false; controls(); }
}
$('new').onclick=fresh;
$('step').onclick=()=>{pause(); return scan();};
$('start').onclick=()=>{pause(); return scan('Start');};
$('reset').onclick=()=>{pause(); return scan('Reset');};
$('play').onclick=()=>{if(playing) pause(); else {playing=true;view?.setPlayback(true);$('play').textContent='暂停';loop();}};
window.addEventListener('pagehide',()=>{pause();if(session) fetch('/api/simulation/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session}),keepalive:true}).catch(()=>{});});
fetch('./simulation-source.scl').then(r=>{if(!r.ok)throw new Error('源码未构建');return r.text();}).then(text=>$('source').textContent=text).catch(e=>$('source').textContent=e.message);
if (location.hostname === '127.0.0.1' && location.port !== '8767') $('service-link').hidden = false;
fresh();

function sceneUnavailable() { view?.dispose();view=undefined;$('scene-status').textContent='3D 不可用';$('scene-fallback').hidden=false;$('camera-home').disabled=$('camera-top').disabled=true; }
$('scene').addEventListener('scene-lost',sceneUnavailable);
$('camera-home').onclick=()=>view?.cameraView(false);
$('camera-top').onclick=()=>view?.cameraView(true);
import('./simulation-3d.js').then(({createConveyorView})=>{
  view=createConveyorView($('scene'));view.reset();view.setPlayback(playing);if(latest)view.update(latest);
  $('scene-status').textContent='3D 已就绪';
}).catch(sceneUnavailable);
