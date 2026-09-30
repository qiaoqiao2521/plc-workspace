import {flowDraft, makeRequest, validateResult, agentPrompt} from './generation-model.js';
const $ = id => document.getElementById(id);
const fieldIds = {name:'project-name', block_name:'block-name', requirement:'requirement', flow:'flow', io_text:'io-text', constraints:'constraints'};
let states = [], request, result, example, ready = false, busy = false, stale = false, jobId, generationOrigin = 'agent', exportFile, generationBudget = 180;
const text = (id, value) => { $(id).textContent = value; };
const node = (tag, value, className) => { const el = document.createElement(tag); if (value !== undefined) el.textContent = value; if (className) el.className = className; return el; };
function message(value, error = false) { $('message').hidden = !value; text('message', value || ''); $('message').classList.toggle('error', error); }
function readBrief() { return {...Object.fromEntries(Object.entries(fieldIds).map(([k,id]) => [k,$(id).value])), target:{cpu:$('cpu').value,tia_version:$('tia-version').value || 'unknown',architecture:'Main LAD / FB SCL'}}; }
function writeBrief(brief) { for (const [k,id] of Object.entries(fieldIds)) $(id).value = brief[k] || ''; $('cpu').value = brief.target?.cpu || 'unknown'; $('tia-version').value = brief.target?.tia_version === 'unknown' ? '' : brief.target?.tia_version || ''; }
function updateActions() {
  $('generate').disabled = !ready || !request || busy;
  $('export-task').disabled = !request || busy;
  $('import-result').disabled = !request || busy;
  $('export-project').disabled = !result || stale || busy;
  $('download-scl').disabled = stale || busy;
  $('download-lad').disabled = stale || busy;
}
function dirty() {
  request = undefined;
  stale = !!result;
  text('artifact-status', stale ? '需求已修改 · 结果过期' : '需求编辑中');
  $('artifact-status').classList.toggle('stale', stale);
  text('request-label', '重新整理步骤后，建立新的生成任务');
  text('verification-title', stale ? '旧结果已过期' : '新工程尚未验证');
  text('verification-note', '当前需求需要自己的编译与扫描测试，不能继承已有示例的检查记录。');
  updateActions();
}
function showTab(name, focus = false) {
  document.querySelectorAll('[data-tab]').forEach(b => { const selected = b.dataset.tab === name; b.setAttribute('aria-selected', String(selected)); b.tabIndex = selected ? 0 : -1; $(`panel-${b.dataset.tab}`).hidden = !selected; if (selected && focus) b.focus(); });
}
function renderStates() {
  $('spec-empty').hidden = false; $('spec-content').hidden = true;
  if (!states.length && !result) return;
  $('spec-empty').hidden = true; $('spec-content').hidden = false;
  $('state-flow').replaceChildren(); $('state-editor').replaceChildren();
  states.forEach(s => {
    $('state-flow').append(node('span', `${s.id} ${s.name}${s.next_state ? ' → ' + s.next_state : ''}`));
    const row = node('div',undefined,'state-editor-row'), name = node('div',s.name,'state-name'); name.append(node('small',`状态 ${s.id}`));
    const fields = node('div',undefined,'state-fields');
    for (const [key,label] of [['actions','动作输出'],['completion','完成条件'],['next_state','下一状态']]) {
      const l = node('label',label), input = node('input'); input.value = s[key]; input.placeholder = '待明确'; input.maxLength = 1000; input.setAttribute('aria-label', `${s.name} · ${label}`);
      input.addEventListener('input', () => { s[key] = input.value; dirty(); }); l.append(input); fields.append(l);
    }
    row.append(name, fields); $('state-editor').append(row);
  });
}
function renderQuestions(questions) { $('questions-box').hidden = !questions.length; $('questions').replaceChildren(...questions.map(q => node('li',q))); }
function renderResult() {
  stale = false; $('artifact-status').classList.remove('stale');
  text('artifact-status', generationOrigin === 'example' ? '仓库工程示例' : 'AI 工程草稿 · 待验证');
  text('spec-summary', result.summary); states = structuredClone(result.states); renderStates(); renderQuestions(result.questions);
  $('io-empty').hidden = !!result.io.length; $('io-table').hidden = !result.io.length;
  $('io-rows').replaceChildren();
  const directions = {input:'输入',output:'输出',internal:'内部'};
  for (const signal of result.io) { const tr = node('tr'); for (const v of [directions[signal.direction],signal.name,signal.type,signal.description]) tr.append(node('td',v)); $('io-rows').append(tr); }
  $('scl-empty').hidden = !!result.scl_files.length; $('scl-content').hidden = !result.scl_files.length;
  $('scl-files').replaceChildren(...result.scl_files.map((f,i) => { const o = node('option',f.name); o.value = String(i); return o; })); showCode();
  $('lad-empty').hidden = !!result.lad_networks.length; $('download-lad').hidden = !result.lad_networks.length;
  $('lad-networks').replaceChildren();
  for (const [i,n] of result.lad_networks.entries()) {
    const article = node('article',undefined,'lad-network'); article.append(node('h3', `网络 ${i+1} · ${n.title}`));
    if (n.kind === 'call') {
      const call = node('div',undefined,'lad-call'); call.append(node('strong', `${n.block} / ${n.instance}`), node('small','周期调用 · EN = TRUE'));
      const bindings = node('div',undefined,'lad-bindings'); n.bindings.forEach(b => bindings.append(node('span', `${b.parameter} := ${b.symbol}`))); call.append(bindings); article.append(call);
    } else {
      const rung = node('div',undefined,'lad-rung'); rung.append(node('span',undefined,'lad-wire'));
      n.contacts.forEach(c => { const contact = node('span',c.negated ? '─|/|─' : '─| |─','lad-contact'); contact.append(node('small',c.symbol)); rung.append(contact,node('span',undefined,'lad-wire')); });
      const coil = node('span','─( )─','lad-coil'); coil.append(node('small',n.coil)); rung.append(coil,node('span',undefined,'lad-wire')); article.append(rung);
    }
    article.append(node('p',n.note)); $('lad-networks').append(article);
  }
  const isExample = generationOrigin === 'example';
  text('verification-title', isExample ? '仓库示例已有离线验证记录' : '新工程尚未验证');
  text('verification-note', isExample ? '这些记录只绑定 FB_MainSequence 的已有源码。LAD 接线网络仍是审阅草稿，TIA 编译与现场验收尚未完成。' : '以下为 Agent 自报检查；本站尚未对这些新代码执行编译、扫描或形式验证。');
  const statuses = {not_run:'未执行',unknown:'未知',pass:'自报通过',fail:'自报失败'};
  $('checks-list').replaceChildren();
  result.checks.forEach(c => { const row = node('article',undefined,'check-record'); row.append(node('strong',c.name),node('span',isExample && c.status === 'pass' ? '已有记录' : statuses[c.status]),node('p',c.detail)); $('checks-list').append(row); });
  text('request-label', `需求 ${request.request_fingerprint.slice(0,12)} · ${isExample ? '已有示例' : '工程草稿'}`);
  $('step-code').classList.add('current'); updateActions();
}
function showCode() { text('scl-code',result?.scl_files[Number($('scl-files').value)]?.content || ''); }
async function prepare() {
  if (!states.length) states = flowDraft($('flow').value);
  request = await makeRequest(readBrief(), states);
  stale = !!result; $('artifact-status').classList.toggle('stale',stale);
  text('artifact-status', '规格待审阅'); text('request-label', `需求 ${request.request_fingerprint.slice(0,12)} · 任务已准备`);
  text('spec-summary', '步骤来自你填写的流程顺序。补充动作与完成条件后，AI 会整理完整规格和工程草稿。');
  if (!result) {
    $('io-empty').hidden = false; $('io-table').hidden = true; $('io-rows').replaceChildren();
    $('scl-empty').hidden = false; $('scl-content').hidden = true; $('scl-files').replaceChildren(); text('scl-code','');
    $('lad-empty').hidden = false; $('lad-networks').replaceChildren(); $('download-lad').hidden = true;
    $('checks-list').replaceChildren(); text('verification-title','新工程尚未验证');
    text('verification-note','工程草稿需要自己的编译与扫描测试，不能继承已有示例的检查记录。');
  }
  renderStates(); renderQuestions(states.filter(s => !s.actions || !s.completion).map(s => `“${s.name}”的动作或完成条件尚未明确，请补充或让 AI 提问。`));
  $('step-spec').classList.add('current'); showTab('spec'); updateActions(); return request;
}
function setBusy(value) {
  busy = value;
  document.querySelectorAll('#brief-form input,#brief-form textarea,#brief-form select,#brief-form button,#state-editor input').forEach(el => { el.disabled = value; });
  $('load-brief').disabled = value; $('view-example').disabled = value; $('cancel').hidden = !value; $('generate').hidden = value;
  updateActions();
}
async function api(path, body) {
  const response = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json','X-PLC-Workspace':'1'},body:JSON.stringify(body)} : {});
  const value = await response.json(); if (!response.ok) throw new Error(value.error || `本机接口返回 HTTP ${response.status}`); return value;
}
async function generate() {
  if (!request || !ready || busy) return;
  setBusy(true); message(`agy 正在整理规格与工程草稿。最多等待 ${generationBudget} 秒；可以取消。`);
  try {
    const accepted = await api('/api/generate', {request,prompt:agentPrompt(request)}); jobId = accepted.job_id;
    let response;
    do { await new Promise(resolve => setTimeout(resolve,1200)); response = await api(`/api/jobs/${jobId}`); } while (response.status === 'running');
    if (response.status === 'cancelled') { message('生成已取消，需求草稿仍保留。'); return; }
    if (response.status !== 'complete') throw new Error(response.error || '生成未完成，请检查本机 agy 后重试。');
    result = validateResult(response.result,request); generationOrigin = 'agent'; renderResult(); showTab('spec');
    message(`agy 已返回工程草稿（${response.duration_seconds ?? '—'} 秒）。请审阅规格、待确认项和代码，再运行工程检查。`);
  } catch (error) { message(error.message,true); }
  finally { jobId = undefined; setBusy(false); }
}
function download(name, value, type = 'application/json') {
  const content = typeof value === 'string' ? value : JSON.stringify(value,null,2);
  exportFile = {name,content,type}; text('export-title',name); $('export-text').value = content; text('export-feedback',''); $('export-dialog').showModal();
}
function saveExport() {
  if (!exportFile) return;
  const url = URL.createObjectURL(new Blob([exportFile.content],{type:exportFile.type})); const a = node('a'); a.href = url; a.download = exportFile.name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),10000);
  text('export-feedback','已向浏览器发起下载；也可以复制上方文本。');
}
function ladMarkdown() { return '# Main LAD 网络规格（待 TIA 实现与编译）\n\n' + result.lad_networks.map((n,i) => `## 网络 ${i+1}：${n.title}\n\n${n.kind === 'call' ? `周期调用 ${n.block}，实例 ${n.instance}，EN=TRUE。\n\n${n.bindings.map(b => `- ${b.parameter} := ${b.symbol}`).join('\n')}` : n.contacts.map(c => `${c.negated ? '常闭' : '常开'} ${c.symbol}`).join(' 串联 ') + ` → 线圈 ${n.coil}`}\n\n${n.note}`).join('\n\n'); }
async function loadExample(artifact) {
  try {
    if (!example) { const response = await fetch('./data/example.json'); if (!response.ok) throw new Error('已有工程示例加载失败，请重新构建网站。'); example = await response.json(); }
    writeBrief(example.request.brief); states = structuredClone(example.request.states); result = undefined; request = undefined; stale = false;
    if (artifact) { request = structuredClone(example.request); result = validateResult(structuredClone(example.result),request); generationOrigin = 'example'; renderResult(); message('显示仓库已有工程示例。该示例没有调用模型；修改需求后可交给 agy 生成新草稿。'); }
    else { await prepare(); message('已载入示例工艺需求。可修改后交给 agy，或查看仓库已有工程。'); }
    showTab('spec'); updateActions();
  } catch (error) { message(error.message,true); }
}
document.querySelectorAll('[data-tab]').forEach((b,i,buttons) => {
  b.addEventListener('click', () => showTab(b.dataset.tab));
  b.addEventListener('keydown',event => { let target; if (event.key === 'ArrowRight') target = (i+1)%buttons.length; if (event.key === 'ArrowLeft') target = (i+buttons.length-1)%buttons.length; if (event.key === 'Home') target = 0; if (event.key === 'End') target = buttons.length-1; if (target !== undefined) { event.preventDefault(); showTab(buttons[target].dataset.tab,true); } });
});
$('brief-form').addEventListener('submit', async event => { event.preventDefault(); try { await prepare(); message('生成任务已准备。审阅步骤后，可以交给 agy。'); } catch (error) { message(error.message,true); } });
$('brief-form').addEventListener('input', event => { if (event.target.id === 'flow') states = []; dirty(); });
$('generate').addEventListener('click',generate);
$('cancel').addEventListener('click', async () => { if (jobId) { try { await api(`/api/jobs/${jobId}/cancel`,{}); message('正在取消 agy，需求草稿会保留。'); } catch (error) { message(error.message,true); } } });
$('load-brief').addEventListener('click', () => loadExample(false)); $('view-example').addEventListener('click', () => loadExample(true)); $('scl-files').addEventListener('change',showCode);
$('save-draft').addEventListener('click', () => { try { localStorage.setItem('plc-workspace-brief-v1',JSON.stringify({brief:readBrief(),states})); message('需求与状态草稿已保存在此浏览器。不会保存模型凭据或生成进程。'); } catch { message('浏览器未允许本地保存，可导出 Agent 任务保留需求。',true); } });
$('export-task').addEventListener('click', async () => { try { const response = await fetch('./data/generation-result.schema.json'); if (!response.ok) throw new Error('结果格式加载失败。'); download('plc-agent-task.json',{request,prompt:agentPrompt(request),result_schema:await response.json()}); } catch (error) { message(error.message,true); } });
$('import-result').addEventListener('click', () => { $('result-file').value = ''; $('result-file').click(); });
$('result-file').addEventListener('change', async event => { try { const file = event.target.files[0]; if (!file) return; if (file.size > 1000000) throw new Error('结果文件超过 1 MB，请拆分工程。'); const value = JSON.parse(await file.text()); const imported = validateResult(value.result || value,request); result = imported; generationOrigin = 'import'; renderResult(); message('Agent 结果已导入。本机尚未执行工程检查。'); } catch (error) { message(error instanceof SyntaxError ? '结果文件不是有效 JSON。' : error.message,true); } });
$('download-scl').addEventListener('click', () => { if (stale || !result) return; const file = result.scl_files[Number($('scl-files').value)]; download(file.name,file.content,'text/plain;charset=utf-8'); });
$('download-lad').addEventListener('click', () => { if (!stale && result) download('Main-LAD-networks.md',ladMarkdown(),'text/markdown;charset=utf-8'); });
$('close-export').addEventListener('click',()=> $('export-dialog').close());
$('save-export').addEventListener('click',saveExport);
$('copy-export').addEventListener('click',async()=> { try { await navigator.clipboard.writeText(exportFile.content); text('export-feedback','文本已复制。'); } catch { text('export-feedback','浏览器不允许自动复制，请选中上方文本复制。'); } });
$('export-project').addEventListener('click', () => { if (!stale && result) download('plc-engineering-draft.json',{kind:generationOrigin === 'example' ? 'repository_example' : 'agent_candidate',request,result,verification_status:'not_run_for_import',lad_format:'review_networks_not_tia_project'}); });
async function init() {
  try { const saved = JSON.parse(localStorage.getItem('plc-workspace-brief-v1')); if (saved?.brief && Array.isArray(saved.states)) { writeBrief(saved.brief); states = saved.states; message('已恢复此浏览器保存的需求草稿。请整理任务后重新生成。'); } } catch { /* Invalid/blocked local storage leaves a clean editable form. */ }
  try { const capability = await api('/api/capabilities'); ready = capability.ready === true && capability.provider === 'agy'; generationBudget = capability.timeout_seconds || 180; } catch { ready = false; }
  text('connection',ready ? '本机 agy 已连接' : '本机生成未连接'); $('connection').classList.toggle('ready',ready);
  if (!ready) { text('generate-title','本机生成未连接'); text('generate-help','使用 npm --prefix web run dev 启动本机桥接；也可导出任务、导入 Agent 结果。'); }
  updateActions();
}
init();
