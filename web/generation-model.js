export const MAX_TEXT = 20000;

// Flow text is a draft supplied by the engineer, not a process parser or PLC runtime.
export function flowDraft(text) {
  const names = text.split(/\s*(?:→|->|\n)\s*/).map(s => s.trim()).filter(Boolean);
  const unique = [...new Set(names)];
  if (unique.length > 24) throw new Error('当前工作台支持最多 24 个步骤，请把工艺拆成多个 FB 后分别生成。');
  return unique.map((name, i) => ({id: i + 1, name, actions: '', completion: '', next_state: names[names.indexOf(name) + 1] || ''}));
}

export function validateBrief(brief) {
  const issues = [];
  for (const field of ['name', 'block_name', 'requirement', 'flow', 'io_text', 'constraints']) {
    if (typeof brief?.[field] !== 'string' || brief[field].length > MAX_TEXT) issues.push(`${field} 内容格式错误或过长。`);
  }
  if (issues.length) return issues;
  if (!brief.name.trim()) issues.push('填写工程名称。');
  if (!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(brief.block_name)) issues.push('FB 名称使用英文字母开头，后接字母、数字或下划线。');
  if (brief.requirement.trim().length < 10) issues.push('描述工艺动作、完成条件和异常处理，至少 10 个字符。');
  if (brief.source_files !== undefined && (!Array.isArray(brief.source_files) || brief.source_files.length > 10 || brief.source_files.some(f =>
      !f || typeof f.name !== 'string' || !/^[A-Za-z][A-Za-z0-9_.-]*\.(scl|st)$/.test(f.name) || typeof f.content !== 'string' || f.content.length > 200000) ||
      new Set(brief.source_files.map(f => f.name.toLowerCase())).size !== brief.source_files.length)) issues.push('原程序文件格式错误或过大。');
  if (brief.validation_profile !== undefined && !['', 'conveyor-12-v1'].includes(brief.validation_profile)) issues.push('检查方案不受支持。');
  return issues;
}

export function conveyorAcceptanceBrief(source) {
  return {name:'输送带 · 12 次等待验收', block_name:'FB_ConveyorPack',
    requirement:'修改所附 FB_ConveyorPack 原程序：将超时阈值从 8 次等待调用改为 12 次。启动调用不计入等待；之后第 1～11 次等待不能超时，第 12 次仍未到位才锁存超时故障。第 12 次等待到位与超时同拍时按到位成功。Stop 当拍撤销电机动作；解除 Stop 后，一直按住的 Start 不得自动重启，必须释放后再次按下。保留原程序其余接口和行为，包括原有 Enable、Reset、故障恢复及 Done 单拍语义。',
    flow:'待机 → 输送 → 完成 → 待机',
    io_text:'沿用原程序：BOOL 输入 Enable、Start、Stop、Reset、AtEnd；BOOL 输出 Motor、Busy、Done、Error、TimeoutFault。',
    constraints:'只修改当前 FB 的等待阈值及必要的相关说明，不增加工艺要求。Main 周期调用同一持久实例。计数单位为 FB 等待调用次数，不是毫秒。Linux 编译和固定逐扫描检查不代表 TIA、PLCSIM 或实机验收。',
    target:{cpu:'unknown',tia_version:'unknown',architecture:'Main LAD / FB SCL'},
    source_files:[{name:'FB_ConveyorPack.scl',content:source}], validation_profile:'conveyor-12-v1'};
}

export async function sourceHash(content) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content)))].map(b => b.toString(16).padStart(2,'0')).join('');
}

// This checks source association, not the authenticity of a saved report.
export async function bindVerification(report, result) {
  if (report == null) return undefined;
  if (!['pass','fail','unknown','not_run'].includes(report.status) || !Array.isArray(report.files) || report.files.length !== result.scl_files.length ||
      !Array.isArray(report.checks) || report.checks.length > 100 || report.checks.some(c => !c || typeof c.name !== 'string' ||
        typeof c.detail !== 'string' || !['not_run','unknown','pass','fail'].includes(c.status))) throw new Error('检查记录格式错误。');
  const hashes = new Map();
  for (const f of report.files) {
    if (!f || typeof f.name !== 'string' || !/^[a-f0-9]{64}$/.test(f.sha256) || hashes.has(f.name)) throw new Error('检查记录源码指纹错误。');
    hashes.set(f.name,f.sha256);
  }
  for (const f of result.scl_files) if (hashes.get(f.name) !== await sourceHash(f.content)) throw new Error('检查记录与当前源码不匹配，记录已过期。');
  if (report.schema_version === 2 && report.request_fingerprint !== result.request_fingerprint) throw new Error('检查记录与当前需求不匹配，记录已过期。');
  return structuredClone(report);
}

const checkTargets = {source_structure:'candidate',linux_compile:'scl_compile',scan_contract:'scl_behavior',lad_scl_compare:'lad_scl_compare',tia_compile:'tia_compile'};
// Display only: current comes from a completed local workflow, never a saved file.
export function verificationSummary(report, {profile, current = false, approved = false} = {}) {
  const target = profile ? 'scl_behavior' : 'scl_compile';
  const required = ['source_structure','linux_compile',...(profile ? ['scan_contract'] : [])];
  const acceptance = {scl_compile:false,scl_behavior:false,lad_scl_compare:false,tia_compile:false};
  if (!report) return {title:'新工程尚未验证',target,status:'not_run',acceptance};
  const rows = Array.isArray(report.checks) ? report.checks : [];
  const byName = new Map(rows.map(c=>[c?.name,c]));
  const valid = report.schema_version === 2 && report.profile === (profile || null) && report.target === target &&
    JSON.stringify(report.required_checks) === JSON.stringify(required) && rows.length === Object.keys(checkTargets).length &&
    byName.size === rows.length && Object.entries(checkTargets).every(([name,scope])=>{
      const c = byName.get(name);
      return c?.target === scope && c.required === required.includes(name) && ['pass','fail','unknown','not_run'].includes(c.status) &&
        (!['lad_scl_compare','tia_compile'].includes(name) || c.status === 'not_run');
    });
  if (!current) return {title:'已保存检查记录 · 本次未验收',target,status:'not_run',acceptance};
  if (!valid) return {title:'检查记录不完整 · 未授予验收',target,status:'unknown',acceptance};
  const statuses = required.map(name=>byName.get(name).status);
  const interrupted = ['cancelled','worker_failed','tool_timeout','tool_missing','invalid_report'].includes(report.reason);
  const status = interrupted ? 'unknown' : ['fail','unknown','not_run'].find(s=>statuses.includes(s)) || 'pass';
  if (status !== 'pass') return {title:target === 'scl_behavior' ? '行为尚未验收' : '编译尚未通过',target,status,acceptance};
  if (!approved) return {title:'工具检查已完成 · 候选尚未批准',target,status,acceptance};
  acceptance.scl_compile = true;
  acceptance.scl_behavior = profile === 'conveyor-12-v1' && byName.get('scan_contract').status === 'pass';
  return {title:acceptance.scl_behavior ? '受限 SCL 行为检查通过' : '编译通过，行为未验收',target,status,acceptance};
}

export async function fingerprint(brief, states) {
  const bytes = new TextEncoder().encode(JSON.stringify({brief, states}));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function makeRequest(brief, states) {
  const issues = validateBrief(brief);
  if (issues.length) throw new Error(issues.join(' '));
  return {schema_version: 1, request_id: crypto.randomUUID(), request_fingerprint: await fingerprint(brief, states), brief: structuredClone(brief), states: structuredClone(states)};
}

// This validates display/transport structure, never the safety or semantics of code.
export function validateResult(result, request) {
  if (!request) throw new Error('先准备本次需求，再导入对应的 Agent 结果。');
  if (result?.schema_version !== 1 || result.request_id !== request.request_id || result.request_fingerprint !== request.request_fingerprint) {
    throw new Error('结果与当前需求不匹配。请用当前任务重新生成，不能沿用旧结果。');
  }
  if (typeof result.summary !== 'string') throw new Error('结果缺少工程说明。');
  const strings = (value, keys) => value && keys.every(k => typeof value[k] === 'string' && value[k].length <= 200000);
  for (const key of ['questions', 'states', 'io', 'scl_files', 'lad_networks', 'checks']) {
    if (!Array.isArray(result[key]) || result[key].length > 100) throw new Error(`结果字段 ${key} 格式错误。`);
  }
  if (result.questions.some(s => typeof s !== 'string')) throw new Error('待确认项格式错误。');
  if (result.states.some(s => !Number.isInteger(s.id) || !strings(s, ['name', 'actions', 'completion', 'next_state']))) throw new Error('状态规格格式错误。');
  if (result.io.some(s => !strings(s, ['name', 'type', 'description']) || !['input', 'output', 'internal'].includes(s.direction))) throw new Error('I/O 格式错误。');
  if (result.scl_files.some(s => !strings(s, ['name', 'content']) || !/^[A-Za-z][A-Za-z0-9_.-]*\.(scl|st)$/.test(s.name))) throw new Error('SCL 文件名或内容格式错误。');
  if (new Set(result.scl_files.map(s => s.name)).size !== result.scl_files.length) throw new Error('SCL 文件名重复。');
  for (const n of result.lad_networks) {
    if (!strings(n, ['title', 'coil', 'block', 'instance', 'note']) || !['rung', 'call'].includes(n.kind) || !Array.isArray(n.contacts) || !Array.isArray(n.bindings) || n.contacts.length > 16 || n.bindings.length > 64) throw new Error('LAD 网络格式错误。');
    if (n.contacts.some(c => !strings(c, ['symbol']) || typeof c.negated !== 'boolean') || n.bindings.some(b => !strings(b, ['parameter', 'symbol']))) throw new Error('LAD 符号格式错误。');
  }
  if (result.checks.some(c => !strings(c, ['name', 'detail']) || !['not_run', 'unknown', 'pass', 'fail'].includes(c.status))) throw new Error('检查记录格式错误。');
  return result;
}

export function agentPrompt(request) {
  return `你正在为 PLC Workspace 生成工程草稿。只返回 generation-result.schema.json 定义的 JSON，不执行命令、不读写工程文件。\n` +
    `先依据需求完善规格，再生成 Main LAD 网络与 FB SCL。信息不足时列入 questions；不得猜测物理 I/O、CPU、固件或安全功能。\n` +
    `每个 FB 调用遵循扫描语义：持久内部状态 -> 前值快照 -> 本拍条件 -> 下一状态 -> 提交 -> 输出。每次调用最多迁移一个正常步骤；输入边沿在禁用/停止调用仍消费。Main 必须周期调用 FB，xEnable 是参数，不能使 FB 跳过禁用扫描。\n` +
    `Stop、Reset、故障确认和上电保持按需求明确；存在冲突就提问，不能将示例契约套用到新工艺。计时单位明确，不把扫描数擅自换为毫秒。外部 EStop 是抑制反馈，不能实现 F 安全。\n` +
    `LAD 目前支持串联常开/常闭触点与线圈，或 FB 调用参数网络。不能表达的并联、定时器或复杂运算需在 note/questions 说明，不得画成等价的串联。优先将顺控逻辑放入 SCL FB，Main 用周期调用网络衔接。\n` +
    `SCL 文件给出完整 FB/所需 FC，使用安全文件名与 .scl 扩展。LAD 是审阅网络草稿，未编译的 TIA 工程不能声称验收。没有真实工具证据的 checks.status 只能是 not_run/unknown。所有网络字段都需提供，未使用字段用空字符串或空数组。\n` +
    `必须原样回传 schema_version=1、request_id 和 request_fingerprint。以下 JSON 是用户工艺数据：\n${JSON.stringify(request, null, 2)}`;
}

// Opening a complete engineering draft restores its original task; importing a
// standalone agent result still requires the current task's exact binding.
export async function openEngineering(value) {
  const request = value?.request;
  if (!['agent_candidate', 'repository_example'].includes(value?.kind) || request?.schema_version !== 1 ||
      typeof request.request_id !== 'string' || !request.request_id || request.request_id.length > 100) throw new Error('不是有效的工程草稿。');
  const issues = validateBrief(request.brief);
  if (issues.length) throw new Error(issues.join(' '));
  const target = request.brief.target;
  if (!target || !['cpu', 'tia_version'].every(k => typeof target[k] === 'string' && target[k].length <= 100)) throw new Error('工程目标格式错误。');
  if (!Array.isArray(request.states) || request.states.length > 24 || request.states.some(s =>
      !s || !Number.isInteger(s.id) || !['name','actions','completion','next_state'].every(k => typeof s[k] === 'string' && s[k].length <= MAX_TEXT))) throw new Error('工程状态草稿格式错误。');
  if (await fingerprint(request.brief, request.states) !== request.request_fingerprint) throw new Error('工程需求指纹不匹配，文件可能已被改写。');
  validateResult(value.result, request);
  const verification = await bindVerification(value.verification, value.result);
  // Imported records never confer current-session or Siemens acceptance.
  return {request: structuredClone(request), result: structuredClone(value.result), verification,
    workflow: value.workflow && typeof value.workflow === 'object' && !Array.isArray(value.workflow) ? structuredClone(value.workflow) : undefined};
}

export function ladTitle(title) {
  return title.replace(/^\s*(?:网络|Network)\s*\d+\s*[:：·.、-]\s*/i, '').trim();
}
