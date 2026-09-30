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
  return issues;
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
