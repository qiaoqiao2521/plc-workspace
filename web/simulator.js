import {openEngineering} from './generation-model.js';

const $ = id => document.getElementById(id);
const HANDOFF_KEY = 'plc-workspace-simulation-engineering-v1';
const labels = {switch: '按钮与开关', lamp: '指示灯', motor: '电机', conveyor: '输送段', photoeye: '光电传感器', cylinder: '气缸', workpiece: '工件'};
const faultLabels = {jam: '卡住 / 无法运动', stuck_off: '电机不响应', stuck_low: '信号常断', stuck_high: '信号常通'};
const caseLabels = {normal: '正常完成', jam: '输送卡料', 'sensor-failed': '光电没有反馈', 'stop-restart': '停止与重新启动', 'fault-reset': '故障确认与复位沿'};
const parameterLabels = {initial: '初始开关值', step: '每拍位移比例', threshold: '检测位置', initial_position: '初始行程比例', length: '长度'};
const state = {catalog: [], profiles: [], templates: [], template: '', scene: null, engineering: null, session: null, snapshot: null, selected: null, history: [], shownTrace: [], lastCase: null, busy: false, connected: false, playing: false, timer: null, epoch: 0, view: null, integration: null, integrationError: '', oipReport: null};
const clone = value => structuredClone(value);
const text = (id, value) => { $(id).textContent = String(value ?? ''); };
const node = (tag, value, className) => { const element = document.createElement(tag); if (value !== undefined) element.textContent = value; if (className) element.className = className; return element; };
const controlInputNames = () => ['Enable', 'Start', 'Stop', 'Reset'].filter(name => state.scene?.components.some(component => component.type === 'switch' && state.scene.bindings?.inputs?.[name] === `${component.id}.value`));
const manualInputs = () => Object.fromEntries(controlInputNames().map(name => [name, $(`input-${name.toLowerCase()}`).checked]));
const profileId = () => state.engineering ? state.engineering.request.brief.validation_profile || 'unsupported' : state.templates.find(template => template.id === state.template)?.program?.profile;
const currentProfile = () => state.profiles.find(profile => profile.id === profileId());

function message(value, error = false) {
  $('message').hidden = !value;
  text('message', value);
  $('message').classList.toggle('error', error);
}
async function api(action, body) {
  const response = await fetch(`/api/sim/${action}`, body === undefined ? {headers: {'Accept': 'application/json'}} : {method: 'POST', headers: {'Content-Type': 'application/json', 'X-PLC-Workspace': '1'}, body: JSON.stringify(body)});
  const contentType = response.headers?.get('Content-Type') || '';
  if (contentType && !contentType.includes('json')) throw new Error('此页面没有连接仿真服务。请运行同一工程工作台的服务后重试。');
  let value;
  try { value = await response.json(); } catch { throw new Error('仿真服务没有返回有效记录。请检查服务状态。'); }
  if (!response.ok) throw new Error(typeof value.error === 'string' ? value.error : value.detail || value.reason || `仿真请求失败（${response.status}）`);
  return value;
}
function pause() {
  state.playing = false;
  clearTimeout(state.timer); state.timer = null;
  text('play', '连续运行'); $('play').setAttribute('aria-pressed', 'false');
}
function updateControls() {
  const sessionReady = !!state.session && !state.busy;
  for (const id of ['step', 'play']) $(id).disabled = !sessionReady;
  for (const name of ['Start', 'Stop', 'Reset']) $(name.toLowerCase()).disabled = !sessionReady || !controlInputNames().includes(name);
  for (const id of ['inject-fault', 'clear-fault']) $(id).disabled = !sessionReady || !$('fault-device').value || !$('fault-type').value;
  $('export-trace').disabled = state.busy || (!state.session && !state.lastCase);
  $('create-session').disabled = !state.connected || state.capabilities?.available === false || !state.scene || state.busy;
  $('run-case').disabled = !state.connected || state.capabilities?.available === false || !state.scene || !$('test-case').value || state.busy;
  $('test-case').disabled = state.busy || !$('test-case').options.length;
  $('template-select').disabled = !state.templates.length || state.busy;
  $('component-type').disabled = !state.catalog.length || state.busy;
  $('add-component').disabled = !state.scene || state.busy;
  $('add-connection').disabled = !state.scene || state.busy;
  $('fault-device').disabled = !state.scene || state.busy;
  $('fault-type').disabled = !state.scene || state.busy;
  $('import-engineering').disabled = state.busy;
  $('import-scene').disabled = state.busy;
  $('export-scene').disabled = !state.scene || state.busy;
  $('use-example').disabled = state.busy;
  document.querySelectorAll('#inspector input,#inspector select,#inspector button,#bindings-list input,#bindings-list select,#bindings-list button,#connections-list input,#connections-list select,#connections-list button').forEach(input => { input.disabled = state.busy; });
  for (const name of ['Enable', 'Start', 'Stop', 'Reset']) { const input = $(`input-${name.toLowerCase()}`); input.disabled = state.busy || !controlInputNames().includes(name); input.closest('label').hidden = !controlInputNames().includes(name); }
  $('run-oip').disabled = state.busy || !state.integration?.ready || !oipSupported();
  text('create-session', state.busy ? '正在处理…' : state.session ? '重建运行' : '创建运行');
}
async function task(work) {
  if (state.busy) return;
  state.busy = true; updateControls();
  try { await work(); }
  catch (error) { pause(); message(error.message || '操作未完成。', true); }
  finally { state.busy = false; updateControls(); }
}
function abandonSession() {
  pause();
  const previous = state.session;
  state.epoch += 1; state.session = null; state.snapshot = null; state.displayedSnapshot = null; state.history = []; state.shownTrace = []; state.lastCase = null;
  if (previous) api('close', {session: previous}).catch(() => {});
  text('scan-count', 0); text('scene-state', '配置预览 · 尚未执行 PLC');
  text('snapshot-label', '尚未执行'); text('view-tag', '配置预览'); $('view-tag').className = 'view-tag';
  text('case-result', '尚未运行用例。用例将创建独立实例，不改变手动运行状态。'); $('case-result').className = 'case-result';
  $('show-failure').hidden = true; $('show-live').hidden = true;
  $('plc-inputs').replaceChildren(); $('plc-outputs').replaceChildren();
  $('component-state').replaceChildren(node('p', '创建运行后显示实际状态', 'muted small'));
  text('active-faults', '未施加故障'); $('active-faults').classList.remove('has-fault');
  text('source-hash', '');
  state.oipReport = null; text('oip-summary', 'not_run · 尚未执行'); $('oip-summary').className = 'integration-summary'; $('oip-details').hidden = true;
  renderTrace([]); updateControls();
}
function mutateScene(change) {
  if (!state.scene || state.busy) return;
  abandonSession(); change(state.scene);
  resetControlInputs();
  renderAssembly(); renderInspector(); renderBindings(); renderConnections(); renderFaultChoices();
  state.view?.setScene(state.scene);
  state.view?.select(state.selected);
  message('场景配置已修改。创建新的运行后，程序和设备将从初始状态开始。');
}
function componentType(type) { return state.catalog.find(item => item.type === type) || {type, label: labels[type] || type, ports: {inputs: {}, outputs: {}}, parameters: {}, faults: []}; }
function resetControlInputs(snapshot) {
  for (const name of controlInputNames()) {
    const endpoint = state.scene.bindings.inputs[name], component = state.scene.components.find(item => endpoint === `${item.id}.value`);
    $(`input-${name.toLowerCase()}`).checked = snapshot?.inputs?.[name] ?? component?.parameters?.initial ?? componentType('switch').parameters?.initial?.default ?? false;
  }
}
function endpoints(direction, type) {
  const choices = [];
  for (const component of state.scene?.components || []) {
    const ports = componentType(component.type).ports?.[direction] || {};
    for (const [port, portType] of Object.entries(ports)) if (!type || portType === type) choices.push({value: `${component.id}.${port}`, type: portType});
  }
  return choices;
}
function fillOptions(select, values, current, emptyLabel) {
  const options = [];
  if (emptyLabel !== undefined) { const option = node('option', emptyLabel); option.value = ''; options.push(option); }
  for (const item of values) { const option = node('option', item.label || item.value); option.value = item.value; options.push(option); }
  if (current && !values.some(item => item.value === current)) { const missing = node('option', `${current} · 待检查`); missing.value = current; options.push(missing); }
  select.replaceChildren(...options); select.value = current || '';
}
const icons = {
  conveyor: '<path d="M3 8h18v8H3zM6 8v8m4-8v8m4-8v8m4-8v8M5 16v4m14-4v4"/>',
  motor: '<path d="M5 7h12v11H5zM17 10h4v5h-4M3 9h2m-2 6h2M8 7V4h6v3M8 10v5m3-5v5m3-5v5"/>',
  photoeye: '<path d="M5 5h7v9H5zM8 14v6H4m4 0h4M12 8h8m-8 3h8"/><circle cx="8.5" cy="9.5" r="1.5"/>',
  cylinder: '<path d="M3 7h11v10H3zM14 10h7v4h-7M6 7v10m5-10v10M21 6v12"/>',
  switch: '<path d="M5 11h14v10H5zM9 11V7h6v4M8 7V4h8v3"/>',
  lamp: '<path d="M8 6h8v9H8zM12 15v5m-4 0h8M7 3l-2-2m12 2 2-2M3 9H1m22 0h-2"/>',
  workpiece: '<path d="m12 3 9 5v9l-9 5-9-5V8l9-5Zm0 10 9-5M3 8l9 5v9M7 6l9 5v4"/>',
};
function renderAssembly() {
  const components = state.scene?.components || [];
  text('component-count', `${components.length} 件`);
  $('component-list').replaceChildren(...components.map(component => {
    const row = node('button', undefined, `component-row${state.selected === component.id ? ' selected' : ''}`);
    row.type = 'button'; row.dataset.component = component.id; row.setAttribute('aria-pressed', String(state.selected === component.id));
    const icon = node('span', undefined, 'component-symbol');
    // All SVG strings are fixed application icons, never imported project text.
    icon.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[component.type] || icons.workpiece}</svg>`;
    const label = node('span', undefined, 'component-label'); label.append(node('strong', component.id), node('small', componentType(component.type).label));
    row.append(icon, label, node('span', undefined, 'component-status'));
    row.addEventListener('click', () => select(component.id));
    return row;
  }));
}
function select(id) {
  state.selected = state.scene?.components.some(c => c.id === id) ? id : null;
  state.view?.select(state.selected);
  renderAssembly(); renderInspector();
}
function renderInspector() {
  const component = state.scene?.components.find(c => c.id === state.selected);
  $('inspector').hidden = !component; $('inspector-empty').hidden = !!component;
  text('selected-type', component ? componentType(component.type).label : '未选择');
  if (!component) return;
  text('selected-name', component.id);
  ['x', 'y', 'z'].forEach((axis, index) => { $(`position-${axis}`).value = component.position?.[index] ?? 0; });
  const catalog = componentType(component.type);
  $('parameter-fields').replaceChildren(...Object.entries(catalog.parameters || {}).map(([name, spec]) => {
    const label = node('label', parameterLabels[name] || name), input = node('input');
    const current = component.parameters?.[name] ?? spec.default;
    if (typeof spec.default === 'boolean') { input.type = 'checkbox'; input.checked = !!current; }
    else { input.type = 'number'; input.value = current ?? 0; if (spec.min !== undefined) input.min = spec.min; if (spec.max !== undefined) input.max = spec.max; input.step = 'any'; }
    input.setAttribute('aria-label', `${component.id} ${name}`);
    input.addEventListener('change', () => {
      const value = input.type === 'checkbox' ? input.checked : Number(input.value);
      if (typeof value === 'number' && !Number.isFinite(value)) return message('参数必须是有限数值。', true);
      if (typeof value === 'number' && (value < (spec.min ?? -Infinity) || value > (spec.max ?? Infinity))) return message(`参数 ${name} 超出允许范围。`, true);
      mutateScene(scene => { const found = scene.components.find(c => c.id === component.id); found.parameters ||= {}; found.parameters[name] = value; });
    });
    label.append(input); return label;
  }));
  const ports = [];
  for (const direction of ['inputs', 'outputs']) for (const [name, type] of Object.entries(catalog.ports?.[direction] || {})) {
    const row = node('div', undefined, 'port-row'); row.append(node('span', direction === 'inputs' ? '接收' : '提供'), node('strong', `${name} · ${type}`)); ports.push(row);
  }
  $('component-ports').replaceChildren(...ports);
  renderSelectedState(state.displayedSnapshot);
  updateControls();
}
function renderSelectedState(snapshot) {
  const component = snapshot?.components?.find(c => c.id === state.selected);
  if (!component) { $('component-state').replaceChildren(node('p', '创建运行后显示实际状态', 'muted small')); return; }
  $('component-state').replaceChildren(...Object.entries(component.state || {}).map(([name, value]) => {
    const row = node('div', undefined, `state-row${value === true ? ' on' : ''}`);
    row.append(node('span', name), node('strong', typeof value === 'object' ? JSON.stringify(value) : String(value)));
    return row;
  }));
}
function renderBindings() {
  const elements = [], bindings = state.scene?.bindings || {inputs: {}, outputs: {}};
  for (const [signal, destination] of Object.entries(bindings.inputs || {})) {
    const row = node('div', undefined, 'binding-row'), label = node('label', signal), select = node('select');
    label.append(node('span', 'PLC 输入'));
    const type = currentProfile()?.inputs?.[signal] || 'BOOL';
    fillOptions(select, endpoints('outputs', type).map(endpoint => ({...endpoint, label: `${endpoint.value} · ${endpoint.type}`})), destination, '未绑定');
    select.setAttribute('aria-label', `PLC 输入 ${signal} 的设备来源`);
    select.addEventListener('change', () => mutateScene(scene => { scene.bindings.inputs[signal] = select.value; }));
    row.append(label, select); elements.push(row);
  }
  for (const [signal, destinations] of Object.entries(bindings.outputs || {})) {
    const row = node('div', undefined, 'binding-row'), label = node('label', signal);
    label.append(node('span', 'PLC 输出'));
    const type = currentProfile()?.outputs?.[signal] || 'BOOL';
    const targets = Array.isArray(destinations) ? destinations : [destinations];
    row.append(label);
    targets.forEach((target, index) => {
      const targetRow = node('div', undefined, 'binding-target'), select = node('select'), remove = node('button', '移除', 'danger-text');
      fillOptions(select, endpoints('inputs', type).map(endpoint => ({...endpoint, label: `${endpoint.value} · ${endpoint.type}`})), target, '未绑定');
      select.setAttribute('aria-label', `PLC 输出 ${signal} 的第 ${index + 1} 个设备目标`);
      select.addEventListener('change', () => mutateScene(scene => { scene.bindings.outputs[signal][index] = select.value; }));
      remove.addEventListener('click', () => mutateScene(scene => { scene.bindings.outputs[signal].splice(index, 1); }));
      targetRow.append(select, remove); row.append(targetRow);
    });
    const add = node('button', '添加设备目标', 'quiet'); add.addEventListener('click', () => mutateScene(scene => { scene.bindings.outputs[signal].push(''); })); row.append(add); elements.push(row);
  }
  $('bindings-list').replaceChildren(...elements);
}
function renderConnections() {
  const connections = state.scene?.connections || [];
  text('connection-count', connections.length);
  $('connections-list').replaceChildren(...connections.map((connection, index) => {
    const row = node('div', undefined, 'connection-row'), from = node('select'), to = node('select');
    const availableOutputs = endpoints('outputs'), sourceType = availableOutputs.find(endpoint => endpoint.value === connection.from)?.type;
    fillOptions(from, availableOutputs.map(endpoint => ({...endpoint, label: `${endpoint.value} · ${endpoint.type}`})), connection.from, '选择设备输出');
    fillOptions(to, endpoints('inputs', sourceType).map(endpoint => ({...endpoint, label: `${endpoint.value} · ${endpoint.type}`})), connection.to, '选择设备输入');
    from.setAttribute('aria-label', `连接 ${index + 1} 来源`); to.setAttribute('aria-label', `连接 ${index + 1} 目标`);
    for (const [input, key] of [[from, 'from'], [to, 'to']]) input.addEventListener('change', () => mutateScene(scene => { scene.connections[index][key] = input.value; }));
    const footer = node('div', undefined, 'connection-row-footer'), remove = node('button', '移除', 'danger-text');
    remove.addEventListener('click', () => mutateScene(scene => { scene.connections.splice(index, 1); }));
    footer.append(node('span', '输出连接到输入'), remove); row.append(from, to, footer); return row;
  }));
}
function renderFaultChoices() {
  const choices = (state.scene?.components || []).filter(c => componentType(c.type).faults?.length).map(c => ({value: c.id, label: `${c.id} · ${componentType(c.type).label}`}));
  const previous = $('fault-device').value;
  fillOptions($('fault-device'), choices, choices.some(c => c.value === previous) ? previous : choices[0]?.value);
  renderFaultTypes();
}
function renderFaultTypes() {
  const component = state.scene?.components.find(c => c.id === $('fault-device').value);
  const faults = component ? componentType(component.type).faults || [] : [];
  fillOptions($('fault-type'), faults.map(fault => ({value: fault, label: faultLabels[fault] || fault})), faults[0]);
}
function showProgram() {
  const example = state.templates.find(t => t.id === state.template);
  const files = state.engineering?.result?.scl_files;
  text('program-name', files ? files.map(file => file.name).join(' · ') : example?.program?.filename || example?.label || '尚未载入');
  text('program-detail', files ? `当前工程 · ${state.engineering.request.request_fingerprint.slice(0, 12)} · 将重新执行` : '明确的合成示例 · 运行结果不外推其他工程');
  text('program-source', files ? files.map(file => `// ${file.name}\n${file.content}`).join('\n\n') : example?.program?.source || '尚未载入程序。');
  $('use-example').hidden = !state.engineering;
  const cases = currentProfile()?.cases || [];
  fillOptions($('test-case'), cases.map(value => ({value, label: caseLabels[value] || value})), cases.includes($('test-case').value) ? $('test-case').value : cases[0]);
  renderIntegration();
}
function loadTemplate(id, keepEngineering = true) {
  const template = state.templates.find(item => item.id === id);
  if (!template) return;
  abandonSession();
  state.template = id; state.scene = clone(template.scene);
  if (!keepEngineering) state.engineering = null;
  state.selected = state.scene.components[0]?.id || null;
  resetControlInputs();
  $('template-select').value = id;
  text('scene-title', state.scene.label || template.label);
  renderAssembly(); renderInspector(); renderBindings(); renderConnections(); renderFaultChoices();
  state.view?.setScene(state.scene); state.view?.select(state.selected);
  showProgram(); updateControls();
}
function payload() {
  const data = {template: state.template, scene: clone(state.scene)};
  if (state.engineering) data.engineering = clone(state.engineering);
  return data;
}
function renderSignals(id, signals = {}) {
  $(id).replaceChildren(...Object.entries(signals).map(([name, value]) => {
    const on = value === true || value === 1;
    const row = node('div', undefined, `signal-row${on ? ' on' : ''}`);
    row.append(node('span', name), node('strong', typeof value === 'boolean' ? (value ? '1' : '0') : String(value)));
    return row;
  }));
}
function displaySnapshot(snapshot, replay = false) {
  if (!snapshot || !Number.isInteger(snapshot.scan)) return;
  state.displayedSnapshot = snapshot;
  text('scan-count', snapshot.scan);
  text('snapshot-label', `${replay ? '回看' : '当前'} · 第 ${snapshot.scan} 拍`);
  text('scene-state', `${replay ? '记录回看' : '实际执行'} · ${snapshot.profile || ''}${snapshot.state != null ? ` · 状态 ${snapshot.state}` : ''}`);
  text('view-tag', replay ? `回看 · ${snapshot.scan}` : `实际执行 · ${snapshot.scan}`);
  $('view-tag').className = `view-tag ${replay ? 'replay' : 'running'}`;
  renderSignals('plc-inputs', snapshot.inputs); renderSignals('plc-outputs', snapshot.outputs);
  renderSelectedState(snapshot); state.view?.update(snapshot);
  const faults = snapshot.faults;
  const names = Array.isArray(faults) ? faults.map(f => typeof f === 'string' ? f : `${f.device || f.id || ''}: ${faultLabels[f.fault] || f.fault || JSON.stringify(f)}`) : Object.entries(faults || {}).flatMap(([key, value]) => value ? [`${key}: ${Array.isArray(value) ? value.join(', ') : typeof value === 'object' ? JSON.stringify(value) : value}`] : []);
  text('active-faults', names.length ? names.join('；') : '未施加故障'); $('active-faults').classList.toggle('has-fault', !!names.length);
  if (snapshot.source_sha256) text('source-hash', `本次执行源码 SHA-256 ${snapshot.source_sha256}`);
  for (const component of snapshot.components || []) {
    const element = [...document.querySelectorAll('.component-row')].find(row => row.dataset.component === component.id);
    const active = Object.values(component.state || {}).some(value => value === true);
    element?.querySelector('.component-status')?.classList.toggle('active', active);
  }
  $('show-live').hidden = !replay || !state.snapshot;
}
function snapshotFrom(data) { return data?.snapshot || data?.snapshots?.at(-1) || (Number.isInteger(data?.scan) ? data : null); }
function consume(data) {
  const snapshot = snapshotFrom(data);
  if (!snapshot) throw new Error('仿真服务未返回扫描快照。');
  state.snapshot = snapshot;
  const rows = data.snapshots || (Array.isArray(data.trace) ? data.trace : [snapshot]);
  for (const row of rows) if (Number.isInteger(row.scan) && row.scan > (state.history.at(-1)?.scan ?? -1)) state.history.push(row);
  displaySnapshot(snapshot); renderTrace(state.history);
  return snapshot;
}
function trueSignals(values = {}) { return Object.entries(values).filter(([, value]) => value === true || value === 1).map(([key]) => key).join(', ') || '—'; }
function eventSummary(event) {
  if (typeof event === 'string') return event;
  if (event.type === 'state_change') return `${event.component} · ${event.signal} → ${typeof event.value === 'boolean' ? Number(event.value) : event.value}`;
  if (event.type === 'fault_changed') return `${event.component} · ${faultLabels[event.fault] || event.fault} ${event.active ? '已施加' : '已解除'}`;
  return event.message || event.kind || JSON.stringify(event);
}
function renderTrace(rows, failure) {
  state.shownTrace = rows;
  if (!rows.length) { const row = node('tr'), cell = node('td', '创建运行并单步后，记录出现在这里。', 'empty-copy'); cell.colSpan = 6; row.append(cell); $('trace-rows').replaceChildren(row); text('trace-note', '选择记录可回看对应快照；回看不会再次执行 PLC。'); return; }
  const visible = rows.slice(-400);
  $('trace-rows').replaceChildren(...visible.map(snapshot => {
    const failed = Number(failure?.scan) === snapshot.scan;
    const row = node('tr', undefined, `trace-row${failed ? ' failed' : ''}`);
    row.dataset.scan = String(snapshot.scan); row.tabIndex = 0; row.setAttribute('aria-label', `回看第 ${snapshot.scan} 拍${failed ? '，首次失败' : ''}`);
    const events = (snapshot.events || []).map(eventSummary).join('；') || '—';
    for (const value of [snapshot.scan, snapshot.state ?? snapshot.outputs?.State ?? '—', trueSignals(snapshot.inputs), trueSignals(snapshot.outputs), Number.isFinite(snapshot.position) ? `${(snapshot.position * 100).toFixed(0)}%` : '—', events]) row.append(node('td', String(value)));
    row.lastElementChild.title = JSON.stringify(snapshot.events || [], null, 2);
    const activate = () => { document.querySelectorAll('.trace-row').forEach(other => other.classList.remove('selected')); row.classList.add('selected'); displaySnapshot(snapshot, true); };
    row.addEventListener('click', activate); row.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } });
    return row;
  }));
  text('trace-note', `${rows.length} 条记录${rows.length > 400 ? ' · 表格显示最近 400 条，导出保留完整记录' : ''} · 选择一拍回看，不推进 PLC`);
}
async function createSession() {
  pause();
  const previous = state.session;
  if (previous) await api('close', {session: previous});
  state.session = null; abandonSession(); state.view?.setScene(state.scene);
  const data = await api('create', payload());
  if (!data.session) throw new Error(data.detail || data.error || data.reason || '执行器未就绪，本次运行未创建。');
  state.session = data.session;
  resetControlInputs(consume(data));
  if (data.source_sha256) text('source-hash', `本次执行源码 SHA-256 ${data.source_sha256}`);
  text('execution-scope', data.scope || '持久 PLC 实例驱动固定步长设备模型。每拍先采样输入，再运行程序，再更新设备；计数表示调用次数。当前结果不授予 TIA、PLCSIM 或实机验收。');
  message('已创建新的 PLC 实例与设备状态。点击“启动一拍”，再单步或连续运行观察。');
}
async function stepOnce(overrides = {}) {
  if (!state.session) throw new Error('请先创建运行。');
  const data = await api('step', {session: state.session, inputs: {...manualInputs(), ...overrides}, count: 1});
  consume(data);
  return data;
}
async function playbackTick() {
  if (!state.playing || !state.session) return;
  if (state.busy) { state.timer = setTimeout(playbackTick, 100); return; }
  await task(async () => { await stepOnce(); });
  if (state.playing) state.timer = setTimeout(playbackTick, 220);
}
function download(filename, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'}));
  const link = node('a'); link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
async function loadEngineering(value) {
  const restored = await openEngineering(value);
  if (!restored.result.scl_files?.length) throw new Error('工程没有可执行 SCL 文件，请先完成生成。');
  abandonSession();
  // Deliberately retain only the reviewed request and candidate. Imported
  // acceptance claims, workflow records and credentials do not cross this door.
  state.engineering = {kind: value.kind, request: restored.request, result: restored.result};
  const profile = restored.request.brief.validation_profile;
  const template = state.templates.find(item => item.program?.profile === profile);
  if (template) loadTemplate(template.id);
  else { showProgram(); updateControls(); }
  message(`已载入 ${restored.request.brief.name || '当前工程'}。创建运行将重新编译这份源码；导入的历史通过记录不会作为本次验收。`);
}
async function runCase() {
  pause();
  const report = await api('run_case', {...payload(), case: $('test-case').value});
  state.lastCase = report;
  const verdict = ['pass', 'fail', 'unknown', 'not_run'].includes(report.status) ? report.status : 'unknown';
  const failure = report.first_failure || report.first_counterexample;
  const lines = {pass: '该用例的已执行断言符合预期。', fail: '该用例发现不符合预期的行为。', unknown: '本次未得到可判定结果。', not_run: '此用例尚未执行。'};
  let detail = lines[verdict];
  if (Array.isArray(report.checks)) { const failed = report.checks.filter(check => check.status === 'fail'); detail += `\n${report.checks.length} 项断言 · ${report.checks.filter(check => check.status === 'pass').length} 项通过 · ${failed.length} 项失败`; }
  if (failure) detail += `\n首次失败：第 ${failure.scan ?? '未知'} 拍 · ${failure.name || failure.id || ''}\n预期 ${JSON.stringify(failure.expected)}；实际 ${JSON.stringify(failure.actual)}`;
  if (report.reason || report.error) detail += `\n${report.reason || report.error}`;
  text('case-result', detail); $('case-result').className = `case-result ${verdict}`;
  $('show-failure').hidden = !failure;
  const trace = report.trace || [];
  if (trace.length) { renderTrace(trace, failure); displaySnapshot(trace.at(-1), true); }
  if (report.source_sha256) text('source-hash', `本次用例源码 SHA-256 ${report.source_sha256}`);
  message(verdict === 'pass' ? '用例已完成。结果仅覆盖本次程序、场景和已执行断言。' : '用例结束，详细原因和逐拍记录已保留。', verdict === 'fail' || verdict === 'unknown');
}

function oipSupported() {
  return (state.integration?.supported_profiles || ['conveyor-12-v1', 'conveyor-8-demo-v1']).includes(profileId());
}
function renderIntegration() {
  let status;
  if (!oipSupported()) status = '当前程序接口暂不支持物理复核；目前支持 12 次等待输送合同与历史 8 次示例。';
  else if (state.integration?.ready) status = `物理执行器已就绪${state.integration.commit ? ` · 上游 ${state.integration.commit.slice(0, 12)}` : ''} · ${state.engineering ? '复核当前工程' : '复核所选示例'}`;
  else if (state.integration) status = `not_run · ${state.integration.reason || state.integration.detail || '物理执行器尚未安装或依赖未就绪'}`;
  else status = state.integrationError ? `not_run · ${state.integrationError}` : '正在检查物理执行器…';
  text('oip-status', status);
  updateControls();
}
async function runOip() {
  pause();
  const program = state.templates.find(template => template.id === state.template)?.program;
  text('oip-summary', '正在执行物理复核，请等待实际测试结果…'); $('oip-summary').className = 'integration-summary'; $('oip-details').hidden = true;
  try {
    const report = await api('oip_test', state.engineering ? {engineering: clone(state.engineering)} : {program: clone(program)});
    state.oipReport = report;
    const normalized = {passed: 'pass', failed: 'fail', error: 'unknown'}[report.status] || report.status;
    const status = ['pass', 'fail', 'unknown', 'not_run'].includes(normalized) ? normalized : 'unknown';
    const tests = Array.isArray(report.tests) ? report.tests : [];
    const summary = {pass: '物理复核的已执行检查通过', fail: '物理复核发现不符合预期的结果', unknown: '物理复核未得到可判定结果', not_run: '物理复核未执行'};
    text('oip-summary', `${status} · ${summary[status]}${tests.length ? ` · ${tests.length} 项检查` : ''}${report.reason || report.error ? `\n${report.reason || report.error}` : ''}`);
    $('oip-summary').className = `integration-summary ${status}`;
    text('oip-report', JSON.stringify(report, null, 2)); $('oip-details').hidden = false;
    message('物理复核报告已保留；本次报告不改写工程生成或平台验收状态。', status === 'fail');
  } catch (error) { text('oip-summary', `not_run · ${error.message}`); throw error; }
}

$('template-select').addEventListener('change', () => { loadTemplate($('template-select').value); message(state.engineering ? '已切换设备场景，保留当前工程。接口是否匹配将在创建时检查。' : '已载入合成示例，可调整组件后创建运行。'); });
$('add-component').addEventListener('click', () => mutateScene(scene => {
  const type = $('component-type').value, catalog = componentType(type);
  let number = 1; while (scene.components.some(component => component.id === `${type}${number}`)) number++;
  const id = `${type}${number}`;
  scene.components.push({id, type, position: [0, 0, 2 + number * .4], parameters: Object.fromEntries(Object.entries(catalog.parameters || {}).map(([key, value]) => [key, value.default]))}); state.selected = id;
}));
$('remove-component').addEventListener('click', () => mutateScene(scene => {
  const id = state.selected; scene.components = scene.components.filter(component => component.id !== id);
  scene.connections = (scene.connections || []).filter(connection => !connection.from.startsWith(`${id}.`) && !connection.to.startsWith(`${id}.`));
  for (const [signal, endpoint] of Object.entries(scene.bindings.inputs || {})) if (endpoint.startsWith(`${id}.`)) scene.bindings.inputs[signal] = '';
  for (const [signal, endpoints] of Object.entries(scene.bindings.outputs || {})) scene.bindings.outputs[signal] = endpoints.filter(endpoint => !endpoint.startsWith(`${id}.`));
  state.selected = scene.components[0]?.id || null;
}));
for (const [index, axis] of ['x', 'y', 'z'].entries()) $(`position-${axis}`).addEventListener('change', event => {
  const value = Number(event.target.value);
  if (!Number.isFinite(value) || Math.abs(value) > 50) { message('位置坐标应在 -50 到 50 之间。', true); return; }
  mutateScene(scene => { scene.components.find(c => c.id === state.selected).position[index] = value; });
});
$('add-connection').addEventListener('click', () => mutateScene(scene => { scene.connections ||= []; scene.connections.push({from: '', to: ''}); }));
$('fault-device').addEventListener('change', renderFaultTypes);
for (const [id, active] of [['inject-fault', true], ['clear-fault', false]]) $(id).addEventListener('click', () => task(async () => {
  pause();
  const data = await api('inject_fault', {session: state.session, device: $('fault-device').value, fault: $('fault-type').value, active});
  const snapshot = snapshotFrom(data); if (snapshot) { state.snapshot = snapshot; displaySnapshot(snapshot); }
  message(active ? '故障已施加，下一次扫描将观察它对设备与反馈的影响。' : '故障已解除。是否恢复动作由当前 PLC 程序决定。');
}));
$('create-session').addEventListener('click', () => task(createSession));
$('step').addEventListener('click', () => task(async () => { pause(); await stepOnce(); }));
for (const [id, signal] of [['start', 'Start'], ['stop', 'Stop'], ['reset', 'Reset']]) $(id).addEventListener('click', () => task(async () => {
  pause(); await stepOnce({[signal]: true}); $(`input-${signal.toLowerCase()}`).checked = false;
  message(`${signal} 已提交一拍。下次单步或连续运行将采样当前复选框值。`);
}));
$('play').addEventListener('click', () => {
  if (state.playing) { pause(); return; }
  state.playing = true; text('play', '暂停观察'); $('play').setAttribute('aria-pressed', 'true'); playbackTick();
});
$('run-case').addEventListener('click', () => task(runCase));
$('run-oip').addEventListener('click', () => task(runOip));
$('show-failure').addEventListener('click', () => {
  const failure = state.lastCase?.first_failure || state.lastCase?.first_counterexample;
  const row = state.lastCase?.trace?.find(item => item.scan === Number(failure?.scan));
  if (row) { displaySnapshot(row, true); renderTrace(state.lastCase.trace, failure); $('scene-title').scrollIntoView({behavior: 'smooth', block: 'start'}); }
  else message('此错误发生在运行建立或检查阶段，没有可回看的执行扫描。', true);
});
$('show-live').addEventListener('click', () => { if (state.snapshot) { displaySnapshot(state.snapshot); renderTrace(state.history); } });
$('export-trace').addEventListener('click', () => task(async () => {
  const record = state.session ? await api('export_trace', {session: state.session}) : state.lastCase;
  download('plc-simulation-trace.json', {...record, ...(state.lastCase && state.session ? {independent_case: state.lastCase} : {}), ...(state.oipReport ? {physical_review: state.oipReport} : {})});
}));
$('camera-home').addEventListener('click', () => state.view?.cameraView('home'));
$('camera-top').addEventListener('click', () => state.view?.cameraView('top'));
$('show-signals').addEventListener('change', () => state.view?.showSignals($('show-signals').checked));
$('import-engineering').addEventListener('click', () => { $('engineering-file').value = ''; $('engineering-file').click(); });
$('engineering-file').addEventListener('change', event => task(async () => {
  const file = event.target.files[0]; if (!file) return;
  if (file.size > 5_000_000) throw new Error('工程文件超过 5 MB，请拆分后载入。');
  await loadEngineering(JSON.parse(await file.text()));
}));
$('use-example').addEventListener('click', () => { state.engineering = null; try { sessionStorage.removeItem(HANDOFF_KEY); } catch {} loadTemplate(state.template, false); message('已切回当前设备单元的合成示例程序。'); });
$('export-scene').addEventListener('click', () => { if (state.scene) download('plc-device-scene.json', state.scene); });
$('import-scene').addEventListener('click', () => { $('scene-file').value = ''; $('scene-file').click(); });
$('scene-file').addEventListener('change', event => task(async () => {
  const file = event.target.files[0]; if (!file) return;
  if (file.size > 1_000_000) throw new Error('场景文件超过 1 MB。');
  const scene = JSON.parse(await file.text());
  if (scene?.schema_version !== 'plc-scene.v1' || !Array.isArray(scene.components) || !scene.bindings || !Array.isArray(scene.connections) || scene.components.length > 100) throw new Error('不是受支持的 PLC 设备场景。');
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  if (!object(scene.bindings.inputs) || !object(scene.bindings.outputs) || Object.values(scene.bindings.inputs).some(value => typeof value !== 'string') || Object.values(scene.bindings.outputs).some(value => !Array.isArray(value) || value.some(endpoint => typeof endpoint !== 'string')) || scene.connections.some(edge => !object(edge) || typeof edge.from !== 'string' || typeof edge.to !== 'string')) throw new Error('场景的连接和 PLC 绑定结构无效。');
  const ids = new Set();
  for (const component of scene.components) {
    if (!component || typeof component.id !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(component.id) || ids.has(component.id) || !state.catalog.some(c => c.type === component.type) || !Array.isArray(component.position) || component.position.length !== 3 || component.position.some(v => !Number.isFinite(v) || Math.abs(v) > 50)) throw new Error('场景中存在无效或重复组件。');
    ids.add(component.id);
  }
  abandonSession(); state.scene = clone(scene); state.selected = scene.components[0]?.id || null;
  resetControlInputs();
  text('scene-title', scene.label || scene.id || '已导入场景');
  renderAssembly(); renderInspector(); renderBindings(); renderConnections(); renderFaultChoices(); state.view?.setScene(state.scene);
  message('场景已导入。创建运行时将进一步检查端口类型、绑定和程序接口。');
}));
$('scene').addEventListener('scene-lost', () => { $('scene-fallback').hidden = false; message('三维画面已暂停，扫描记录和运行控制仍可使用。'); });
document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
window.addEventListener('pagehide', () => { pause(); state.view?.dispose(); });

async function init() {
  try {
    const [{components, profiles, capabilities}, {templates}] = await Promise.all([api('catalog'), api('templates')]);
    if (!Array.isArray(components) || !Array.isArray(templates) || !templates.length) throw new Error('仿真组件或模板未就绪。');
    state.catalog = components; state.templates = templates; state.profiles = profiles || []; state.capabilities = capabilities; state.connected = true;
    fillOptions($('component-type'), components.map(component => ({value: component.type, label: component.label || labels[component.type]})), components[0]?.type);
    fillOptions($('template-select'), templates.map(template => ({value: template.id, label: template.label})), templates[0].id);
    text('connection-status', '仿真服务已连接'); $('connection-status').className = 'connection ready';
    loadTemplate(templates[0].id);
    if (capabilities?.available === false) { text('connection-status', '执行器未就绪'); $('connection-status').className = 'connection error'; message('not_run · PLC 执行工具尚未就绪。现在可以组装场景，安装运行工具并重启工作台服务后再执行验证。'); }
    if (new URLSearchParams(location.search).has('engineering')) {
      try {
        const value = sessionStorage.getItem(HANDOFF_KEY);
        if (!value) message('当前标签页没有可交接的工程，请从需求生成页进入，或打开工程文件。', true);
        else await loadEngineering(JSON.parse(value));
      } catch (error) { message(error.message || '工程交接未完成，请重新打开工程文件。', true); }
    }
  } catch (error) {
    text('connection-status', '服务未就绪'); $('connection-status').className = 'connection error';
    message(error.message || '未连接仿真服务。请启动工作台服务后刷新。', true);
  }
  try {
    const {createAssemblyView} = await import('./simulator-3d.js');
    state.view = createAssemblyView($('scene'), {onSelect: select});
    if (state.scene) { state.view.setScene(state.scene); state.view.select(state.selected); }
  } catch {
    $('scene-fallback').hidden = false;
  }
  try { const integrations = await api('integrations'); state.integration = integrations.open_industry_project || null; }
  catch (error) { state.integrationError = error.message || '物理执行器不可用'; }
  renderIntegration();
  updateControls();
}
init();
