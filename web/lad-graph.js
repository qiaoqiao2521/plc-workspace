// Display validation and layout only. Verdicts come from the native/graph checks.
// Every drawn node and wire comes from the serialized LAD product, never its IR.
const identifier = value => typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(value);
const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).sort().join(',') === [...expected].sort().join(',');

export function validateLadGraph(graph) {
  const reject = detail => { throw new Error(`LAD 图格式错误：${detail}`); };
  if (!keys(graph,['schema_version','format','contract_id','block','symbols','networks']) || graph.schema_version !== 1 ||
      graph.format !== 'plc-lad-bool-v1' || graph.contract_id !== 'latch-start-stop-v1' || graph.block !== 'FB_StartStop' ||
      JSON.stringify(graph).length > 524288) reject('不支持的版本或合同。');
  if (!Array.isArray(graph.symbols) || graph.symbols.length < 4 || graph.symbols.length > 32 ||
      !Array.isArray(graph.networks) || !graph.networks.length || graph.networks.length > 28) reject('符号或网络数量越界。');
  const symbols = new Map();
  for (const s of graph.symbols) {
    if (!keys(s,['name','type','storage','initial']) || !identifier(s.name) || s.type !== 'BOOL' ||
        !['input','output','static','temp'].includes(s.storage) || typeof s.initial !== 'boolean' ||
        (s.storage !== 'static' && s.initial) || symbols.has(s.name.toLowerCase())) reject('符号声明无效。');
    symbols.set(s.name.toLowerCase(),s);
  }
  const inputNames = graph.symbols.filter(s=>s.storage==='input').map(s=>s.name).sort();
  const outputNames = graph.symbols.filter(s=>s.storage==='output').map(s=>s.name);
  if (inputNames.join(',') !== 'Enable,Start,Stop' || outputNames.join(',') !== 'Motor') reject('启停基准接口不匹配。');
  const networks = new Set(), writers = new Set(), temps = new Set();
  for (const network of graph.networks) {
    if (!keys(network,['id','nodes','edges','entry','exit']) || !identifier(network.id) || networks.has(network.id) ||
        !Array.isArray(network.nodes) || network.nodes.length < 4 || network.nodes.length > 384 ||
        !Array.isArray(network.edges) || network.edges.length < 3 || network.edges.length > 768) reject('网络定义无效。');
    networks.add(network.id);
    const nodes = new Map(), forward = new Map(), reverse = new Map();
    for (const n of network.nodes) {
      const fields = n?.kind === 'contact' ? ['id','kind','symbol','negated'] : n?.kind === 'coil' ? ['id','kind','symbol'] : ['id','kind'];
      if (!keys(n,fields) || !identifier(n.id) || nodes.has(n.id) || !['rail','junction','contact','coil'].includes(n.kind)) reject('节点无效或重复。');
      if (['contact','coil'].includes(n.kind)) {
        const symbol = symbols.get(typeof n.symbol === 'string' ? n.symbol.toLowerCase() : undefined);
        if (!symbol || symbol.name !== n.symbol) reject('未声明的符号。');
        if (n.kind === 'contact' && (typeof n.negated !== 'boolean' || symbol.storage === 'output' || (symbol.storage === 'temp' && !temps.has(symbol.name)))) reject('触点极性或读取对象无效。');
        if (n.kind === 'coil' && symbol.storage === 'input') reject('输入不能作为线圈。');
      }
      nodes.set(n.id,n); forward.set(n.id,[]); reverse.set(n.id,[]);
    }
    if (!nodes.has(network.entry) || !nodes.has(network.exit) || network.entry === network.exit ||
        nodes.get(network.entry).kind !== 'rail' || nodes.get(network.exit).kind !== 'rail' ||
        network.nodes.filter(n=>n.kind==='rail').length !== 2) reject('左右电源轨无效。');
    const edges = new Set();
    for (const e of network.edges) {
      if (!keys(e,['from','to']) || !nodes.has(e.from) || !nodes.has(e.to) || e.from === e.to || edges.has(`${e.from}:${e.to}`)) reject('连线无效或重复。');
      edges.add(`${e.from}:${e.to}`); forward.get(e.from).push(e.to); reverse.get(e.to).push(e.from);
    }
    const coils = network.nodes.filter(n=>n.kind==='coil');
    if (coils.length !== 1 || writers.has(coils[0].symbol)) reject('必须单线圈、单写入。');
    for (const n of network.nodes) {
      const before = reverse.get(n.id).length, after = forward.get(n.id).length;
      if (n.id === network.entry ? before !== 0 || after !== 1 :
          n.id === network.exit ? before !== 1 || after !== 0 :
          n.kind === 'junction' ? !((before === 1 && after >= 2) || (before >= 2 && after === 1)) : before !== 1 || after !== 1) reject('节点连接数量错误。');
    }
    if (forward.get(coils[0].id)[0] !== network.exit) reject('线圈必须位于出口前。');
    const pending = new Map(network.nodes.map(n=>[n.id,reverse.get(n.id).length]));
    const queue = [network.entry], seen = new Set();
    for (let i=0;i<queue.length;i++) {
      const id=queue[i]; seen.add(id);
      for (const next of forward.get(id)) { pending.set(next,pending.get(next)-1); if (pending.get(next) === 0) queue.push(next); }
    }
    if (seen.size !== nodes.size || queue.at(-1) !== network.exit) reject('存在环或不连通的节点。');
    writers.add(coils[0].symbol);
    if (symbols.get(coils[0].symbol.toLowerCase()).storage === 'temp') temps.add(coils[0].symbol);
  }
  if (graph.symbols.some(s=>s.storage !== 'input' && !writers.has(s.name))) reject('非输入符号缺少唯一写入。');
  return graph;
}

// Reconstruct a series/parallel drawing from product edges. An imported DAG that
// cannot be drawn without ambiguity is rejected explicitly, never redrawn as IR.
export function layoutLadNetwork(network) {
  const byId = new Map(network.nodes.map(n=>[n.id,n]));
  const outgoing = new Map(network.nodes.map(n=>[n.id,[]]));
  const incoming = new Map(network.nodes.map(n=>[n.id,[]]));
  for (const edge of network.edges) { outgoing.get(edge.from).push(edge.to); incoming.get(edge.to).push(edge.from); }
  const order=[], seen=new Set();
  function visit(id) { if (seen.has(id)) return; seen.add(id); for (const next of outgoing.get(id)) visit(next); order.unshift(id); }
  visit(network.entry);
  const post = new Map();
  for (const id of [...order].reverse()) {
    const children = outgoing.get(id);
    const shared = children.length ? [...post.get(children[0])].filter(n=>children.every(c=>post.get(c).has(n))) : [];
    post.set(id,new Set([id,...shared]));
  }
  const used = new Set();
  function take(id) { if (used.has(id)) throw new Error('LAD 预览不支持此交叉汇合拓扑；请审阅导出的图数据。'); used.add(id); }
  function sequence(start, stop) {
    const parts=[]; let current=start;
    while (current !== stop) {
      if (!byId.has(current)) throw new Error('LAD 预览路径缺失。');
      take(current);
      const next=outgoing.get(current);
      if (next.length > 1) {
        const join=order.find(id=>id !== current && next.every(child=>post.get(child).has(id)));
        if (!join || join === stop || byId.get(join).kind !== 'junction') throw new Error('LAD 预览无法确定分支汇合点。');
        const branches=next.map(child=>sequence(child,join)); take(join);
        const height=branches.reduce((n,b)=>n+b.height,0)+24*(branches.length-1);
        parts.push({kind:'parallel',split:current,join,branches,width:Math.max(...branches.map(b=>b.width))+80,height});
        current=outgoing.get(join)[0];
      } else {
        const n=byId.get(current);
        parts.push({kind:'node',id:current,width:n.symbol ? Math.max(100,n.symbol.length*7+24) : 24,height:72});
        current=next[0];
      }
    }
    return {parts,width:parts.reduce((n,p)=>n+p.width,0)+Math.max(0,parts.length-1)*28,height:Math.max(72,...parts.map(p=>p.height))};
  }
  const tree=sequence(network.entry,undefined);
  if (used.size !== byId.size) throw new Error('LAD 预览存在未绘制节点。');
  const positions = new Map();
  function place(seq,x,y) {
    let cursor=x;
    for (const part of seq.parts) {
      if (part.kind === 'node') positions.set(part.id,{x:cursor+part.width/2,y});
      else {
        positions.set(part.split,{x:cursor,y}); positions.set(part.join,{x:cursor+part.width,y});
        let top=y-part.height/2;
        for (const branch of part.branches) { place(branch,cursor+40,top+branch.height/2); top+=branch.height+24; }
      }
      cursor+=part.width+28;
    }
  }
  place(tree,24,tree.height/2+32);
  const nodes=network.nodes.map(n=>({...n,...positions.get(n.id)}));
  const extent = node => ['contact','coil'].includes(node.kind) ? 24 : 0;
  const edges=network.edges.map(e=>{
    const from={...byId.get(e.from),...positions.get(e.from)},to={...byId.get(e.to),...positions.get(e.to)};
    const x1=from.x+extent(from),x2=to.x-extent(to);
    const bend=outgoing.get(e.from).length>1 ? from.x : incoming.get(e.to).length>1 ? to.x : (x1+x2)/2;
    return {...e,path:from.y === to.y ? `M ${x1} ${from.y} H ${x2}` : `M ${x1} ${from.y} H ${bend} V ${to.y} H ${x2}`};
  });
  return {width:tree.width+48,height:tree.height+64,nodes,edges};
}
