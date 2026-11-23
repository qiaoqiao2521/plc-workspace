"""Bounded BOOL IR, deterministic SCL/LAD emitters, and a product-graph executor.

This is the explicitly selected synthetic start/stop benchmark, not a general
PLC compiler or a Siemens LAD exchange format. Validation proves only structural
well-formedness. The independent contract checks live outside this module.
"""
import copy
import json
import re

PROFILE = 'latch-start-stop-v1'
BLOCK = 'FB_StartStop'
INPUTS = ('Enable', 'Start', 'Stop')
OUTPUTS = ('Motor',)
GENERATOR_VERSION = 'bool-ir-v1'
MAX_SYMBOLS = 32
MAX_NETWORKS = 28
MAX_EXPR_DEPTH = 12
MAX_EXPR_NODES = 128
MAX_GRAPH_NODES = 384
MAX_GRAPH_EDGES = 768
MAX_SERIALIZED_BYTES = 512 * 1024
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,47}\Z')
# Keep IEC keywords and standard elementary type names out of declarations.
RESERVED = set(('AND OR XOR NOT TRUE FALSE BOOL BYTE WORD DWORD LWORD SINT INT '
                'DINT LINT USINT UINT UDINT ULINT REAL LREAL TIME DATE TOD DT '
                'STRING WSTRING CHAR WCHAR ARRAY OF STRUCT END_STRUCT TYPE '
                'END_TYPE VAR VAR_INPUT VAR_OUTPUT VAR_IN_OUT VAR_TEMP '
                'VAR_GLOBAL VAR_EXTERNAL END_VAR RETAIN NON_RETAIN CONSTANT '
                'FUNCTION FUNCTION_BLOCK END_FUNCTION END_FUNCTION_BLOCK '
                'PROGRAM END_PROGRAM CONFIGURATION END_CONFIGURATION RESOURCE '
                'END_RESOURCE TASK WITH ON AT EN ENO IF THEN ELSE ELSIF END_IF '
                'CASE END_CASE FOR TO BY DO END_FOR WHILE END_WHILE REPEAT UNTIL '
                'END_REPEAT EXIT RETURN MOD R_EDGE F_EDGE INITIAL_STEP STEP '
                'END_STEP TRANSITION END_TRANSITION ACTION END_ACTION').split())


def _fail(path, message):
    raise ValueError(f'{path}: {message}')


def _object(value, keys, path):
    if type(value) is not dict or set(value) != set(keys):
        _fail(path, 'expected exactly ' + ', '.join(sorted(keys)))


def _identifier(value, path):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or value.upper() in RESERVED:
        _fail(path, 'expected a non-reserved ASCII identifier, 1..48 characters')


def _array(value, minimum, maximum, path):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail(path, f'expected an array with {minimum}..{maximum} items')


def _symbols(value):
    _array(value, 4, MAX_SYMBOLS, 'symbols')
    result = {}
    folded = set()
    for index, item in enumerate(value):
        path = f'symbols[{index}]'
        _object(item, ('name', 'type', 'storage', 'initial'), path)
        _identifier(item['name'], path + '.name')
        key = item['name'].upper()
        if key in folded or key == BLOCK.upper():
            _fail(path, 'case-insensitive duplicate or block-name collision')
        folded.add(key)
        if item['type'] != 'BOOL' or item['storage'] not in ('input', 'output', 'static', 'temp'):
            _fail(path, 'only BOOL input/output/static/temp symbols are supported')
        if type(item['initial']) is not bool:
            _fail(path, 'initial must be a JSON boolean')
        if item['storage'] in ('input', 'output', 'temp') and item['initial']:
            _fail(path, 'input/output/temp initial must be false in this subset')
        result[item['name']] = item
    if {name for name, item in result.items() if item['storage'] == 'input'} != set(INPUTS):
        _fail('symbols', 'this contract requires exactly Enable, Start and Stop inputs')
    if {name for name, item in result.items() if item['storage'] == 'output'} != set(OUTPUTS):
        _fail('symbols', 'this contract requires exactly the Motor output')
    return result


def _header(value):
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        _fail('schema_version', 'only version 1 is supported')
    if value['contract_id'] != PROFILE or value['block'] != BLOCK:
        _fail('contract_id/block', 'unsupported contract or block')
    return _symbols(value['symbols'])


def _read_symbol(name, symbols, written, path):
    if not isinstance(name, str) or name not in symbols:
        _fail(path, 'undeclared symbol (references are case-sensitive)')
    storage = symbols[name]['storage']
    if storage == 'output':
        _fail(path, 'outputs cannot be read as control memory')
    if storage == 'temp' and name not in written:
        _fail(path, 'temporary symbol read before its network assignment')


def _write_symbol(name, symbols, written, path):
    if not isinstance(name, str) or name not in symbols:
        _fail(path, 'undeclared coil/assignment target')
    if symbols[name]['storage'] == 'input':
        _fail(path, 'input symbols cannot be written')
    if name in written:
        _fail(path, 'multiple writers are outside this subset')


def _all_written(symbols, written):
    missing = {name for name, item in symbols.items() if item['storage'] != 'input'} - written
    if missing:
        _fail('networks', 'non-input symbols without one writer: ' + ', '.join(sorted(missing)))


def validate_ir(ir):
    """Return an owned validated IR; do not claim that its behavior is correct."""
    _object(ir, ('schema_version', 'contract_id', 'block', 'symbols', 'networks', 'unresolved'), 'IR')
    symbols = _header(ir)
    if type(ir['unresolved']) is not list or ir['unresolved']:
        _fail('unresolved', 'unresolved requirements prevent executable generation')
    _array(ir['networks'], 1, MAX_NETWORKS, 'networks')
    written, ids = set(), set()
    for index, network in enumerate(ir['networks']):
        path = f'networks[{index}]'
        _object(network, ('id', 'target', 'expression'), path)
        _identifier(network['id'], path + '.id')
        if network['id'].upper() in ids:
            _fail(path, 'duplicate network id')
        ids.add(network['id'].upper())
        _write_symbol(network['target'], symbols, written, path + '.target')
        count = 0

        def expression(node, depth, here):
            nonlocal count
            count += 1
            if depth > MAX_EXPR_DEPTH or count > MAX_EXPR_NODES:
                _fail(here, 'expression exceeds the bounded depth/node budget')
            if type(node) is not dict:
                _fail(here, 'expected expression object')
            kind = node.get('kind')
            if kind == 'contact':
                _object(node, ('kind', 'symbol', 'negated'), here)
                _read_symbol(node['symbol'], symbols, written, here + '.symbol')
                if type(node['negated']) is not bool:
                    _fail(here, 'contact negated must be a JSON boolean')
            elif kind in ('series', 'parallel'):
                _object(node, ('kind', 'children'), here)
                _array(node['children'], 2, 8, here + '.children')
                for child_index, child in enumerate(node['children']):
                    expression(child, depth + 1, f'{here}.children[{child_index}]')
            else:
                _fail(here, 'unsupported expression; only contact/series/parallel are supported')

        expression(network['expression'], 1, path + '.expression')
        written.add(network['target'])
    _all_written(symbols, written)
    return copy.deepcopy(ir)


def _scl_expression(node):
    if node['kind'] == 'contact':
        value = '#' + node['symbol']
        return f'(NOT {value})' if node['negated'] else value
    operator = ' AND ' if node['kind'] == 'series' else ' OR '
    return '(' + operator.join(_scl_expression(child) for child in node['children']) + ')'


def emit_scl(ir):
    ir = validate_ir(ir)
    lines = [f'FUNCTION_BLOCK "{ir["block"]}"', "{ S7_Optimized_Access := 'TRUE' }", 'VERSION : 0.1',
             '// Synthetic latch-start-stop-v1; one persistent instance, one call per scan.',
             '// Call even when Enable is FALSE. Not a safety or retention function.']
    for storage, section in (('input', 'VAR_INPUT'), ('output', 'VAR_OUTPUT'),
                             ('static', 'VAR'), ('temp', 'VAR_TEMP')):
        items = [item for item in ir['symbols'] if item['storage'] == storage]
        if not items:
            continue
        lines.append(section)
        for item in items:
            initial = '' if storage == 'temp' else ' := ' + ('TRUE' if item['initial'] else 'FALSE')
            lines.append(f'    {item["name"]} : BOOL{initial};')
        lines.append('END_VAR')
    lines.append('BEGIN')
    for network in ir['networks']:
        lines.extend([f'    // Network {network["id"]}',
                      f'    #{network["target"]} := {_scl_expression(network["expression"])};'])
    lines.extend(['END_FUNCTION_BLOCK', ''])
    return '\n'.join(lines)


def emit_lad(ir):
    ir = validate_ir(ir)
    graph = {key: copy.deepcopy(ir[key]) for key in ('schema_version', 'contract_id', 'block', 'symbols')}
    graph.update(format='plc-lad-bool-v1', networks=[])
    for network in ir['networks']:
        nodes, edges = [], []

        def node(kind, **fields):
            item = {'id': 'n' + str(len(nodes)), 'kind': kind, **fields}
            nodes.append(item)
            return item['id']

        def edge(start, end):
            edges.append({'from': start, 'to': end})

        def circuit(expr, start):
            if expr['kind'] == 'contact':
                end = node('contact', symbol=expr['symbol'], negated=expr['negated'])
                edge(start, end)
                return end
            if expr['kind'] == 'series':
                for child in expr['children']:
                    start = circuit(child, start)
                return start
            split = node('junction')
            edge(start, split)
            ends = [circuit(child, split) for child in expr['children']]
            join = node('junction')
            for end in ends:
                edge(end, join)
            return join

        entry = node('rail')
        end = circuit(network['expression'], entry)
        coil = node('coil', symbol=network['target'])
        edge(end, coil)
        exit_node = node('rail')
        edge(coil, exit_node)
        graph['networks'].append({'id': network['id'], 'nodes': nodes, 'edges': edges,
                                  'entry': entry, 'exit': exit_node})
    validate_lad(graph)
    return graph


def generate(ir):
    return {'scl_files': [{'name': BLOCK + '.scl', 'content': emit_scl(ir)}], 'lad_graph': emit_lad(ir)}


def _graph_plan(graph):
    """Validate serialized-product topology, without consulting or reconstructing IR."""
    _object(graph, ('schema_version', 'format', 'contract_id', 'block', 'symbols', 'networks'), 'LAD')
    symbols = _header(graph)
    if graph['format'] != 'plc-lad-bool-v1':
        _fail('format', 'unsupported LAD graph format')
    _array(graph['networks'], 1, MAX_NETWORKS, 'networks')
    written, ids, plans = set(), set(), []
    for index, network in enumerate(graph['networks']):
        path = f'networks[{index}]'
        _object(network, ('id', 'nodes', 'edges', 'entry', 'exit'), path)
        _identifier(network['id'], path + '.id')
        if network['id'].upper() in ids:
            _fail(path, 'duplicate network id')
        ids.add(network['id'].upper())
        _array(network['nodes'], 4, MAX_GRAPH_NODES, path + '.nodes')
        _array(network['edges'], 3, MAX_GRAPH_EDGES, path + '.edges')
        nodes, coils, rails = {}, [], []
        for item in network['nodes']:
            if type(item) is not dict:
                _fail(path, 'expected node object')
            kind = item.get('kind')
            if kind in ('rail', 'junction'):
                _object(item, ('id', 'kind'), path + '.node')
            elif kind == 'contact':
                _object(item, ('id', 'kind', 'symbol', 'negated'), path + '.contact')
                _read_symbol(item['symbol'], symbols, written, path + '.contact.symbol')
                if type(item['negated']) is not bool:
                    _fail(path, 'contact negated must be a JSON boolean')
            elif kind == 'coil':
                _object(item, ('id', 'kind', 'symbol'), path + '.coil')
                _write_symbol(item['symbol'], symbols, written, path + '.coil.symbol')
                coils.append(item['id'])
            else:
                _fail(path, 'unsupported node kind')
            _identifier(item['id'], path + '.node.id')
            if item['id'] in nodes:
                _fail(path, 'duplicate node id')
            nodes[item['id']] = item
            if kind == 'rail':
                rails.append(item['id'])
        entry, exit_node = network['entry'], network['exit']
        if (not isinstance(entry, str) or not isinstance(exit_node, str) or entry == exit_node
                or set(rails) != {entry, exit_node} or len(rails) != 2 or len(coils) != 1):
            _fail(path, 'requires distinct entry/exit rails and exactly one normal coil')
        incoming = {key: [] for key in nodes}
        outgoing = {key: [] for key in nodes}
        seen_edges = set()
        for item in network['edges']:
            _object(item, ('from', 'to'), path + '.edge')
            start, end = item['from'], item['to']
            if not isinstance(start, str) or not isinstance(end, str) or start not in nodes or end not in nodes:
                _fail(path, 'edge refers to an unknown node')
            if start == end or (start, end) in seen_edges:
                _fail(path, 'self-link or duplicate edge')
            seen_edges.add((start, end))
            outgoing[start].append(end)
            incoming[end].append(start)
        if incoming[entry] or len(outgoing[entry]) != 1 or outgoing[exit_node] or incoming[exit_node] != coils:
            _fail(path, 'invalid rail wiring or coil bypass')
        coil = coils[0]
        if len(incoming[coil]) != 1 or outgoing[coil] != [exit_node]:
            _fail(path, 'coil must be the only writer at the network end')
        for key, item in nodes.items():
            if item['kind'] == 'contact' and (len(incoming[key]) != 1 or len(outgoing[key]) != 1):
                _fail(path, 'contacts require exactly one input and one output connection')
            if item['kind'] == 'junction' and not (
                    len(incoming[key]) == 1 and len(outgoing[key]) >= 2
                    or len(incoming[key]) >= 2 and len(outgoing[key]) == 1):
                _fail(path, 'junction must explicitly split or join branches')
        # Kahn's algorithm also checks every node participates in the bounded DAG.
        indegree = {key: len(value) for key, value in incoming.items()}
        queue = [key for key in nodes if indegree[key] == 0]
        if queue != [entry]:
            _fail(path, 'every node must be reachable from the entry rail')
        order = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            for target in outgoing[current]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if len(order) != len(nodes):
            _fail(path, 'cycle or unreachable cyclic branch')
        reachable_exit, pending = {exit_node}, [exit_node]
        while pending:
            for predecessor in incoming[pending.pop()]:
                if predecessor not in reachable_exit:
                    reachable_exit.add(predecessor)
                    pending.append(predecessor)
        if len(reachable_exit) != len(nodes):
            _fail(path, 'every node must reach the exit through the coil')
        written.add(nodes[coil]['symbol'])
        plans.append((nodes, incoming, order, entry))
    _all_written(symbols, written)
    return symbols, plans


def validate_lad(graph):
    _graph_plan(graph)
    if len(json.dumps(graph, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > MAX_SERIALIZED_BYTES:
        raise ValueError('Serialized LAD graph exceeds size budget')
    return copy.deepcopy(graph)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


class LadRuntime:
    """Execute only the captured serialized LAD product, one persistent instance/call.

    This small BOOL graph interpreter is an independent execution path, not a
    Siemens runtime. It cannot read the original IR or SCL emitter's expressions.
    """
    def __init__(self, serialized_graph):
        if not isinstance(serialized_graph, (str, bytes)):
            raise TypeError('LAD runtime requires serialized graph bytes/text, not an IR/dict')
        if len(serialized_graph.encode('utf-8') if isinstance(serialized_graph, str) else serialized_graph) > MAX_SERIALIZED_BYTES:
            raise ValueError('Serialized LAD graph exceeds size budget')
        try:
            graph = json.loads(serialized_graph, object_pairs_hook=_json_object,
                               parse_constant=lambda value: _fail('JSON', 'non-finite value ' + value))
        except RecursionError as error:
            raise ValueError('Serialized LAD graph exceeds JSON nesting budget') from error
        self._symbols, self._plans = _graph_plan(graph)
        self._instances = {}
        self._serial = 0

    def create(self):
        self._serial += 1
        self._instances[self._serial] = {name: item['initial'] for name, item in self._symbols.items()}
        return self._serial

    def destroy(self, handle):
        if handle not in self._instances:
            raise ValueError('Unknown LAD instance')
        del self._instances[handle]

    def scan(self, handle, inputs):
        if handle not in self._instances:
            raise ValueError('Unknown LAD instance')
        if type(inputs) is not dict or any(name not in INPUTS or type(value) is not bool for name, value in inputs.items()):
            raise ValueError('Only Boolean Enable/Start/Stop inputs are supported')
        values = self._instances[handle]
        for name, item in self._symbols.items():
            if item['storage'] == 'input':
                values[name] = inputs.get(name, False)
            elif item['storage'] == 'temp':
                values[name] = False
        for nodes, incoming, order, entry in self._plans:
            energized = {}
            for key in order:
                item = nodes[key]
                power = key == entry or any(energized[source] for source in incoming[key])
                if item['kind'] == 'contact':
                    conductive = values[item['symbol']] != item['negated']
                    power = power and conductive
                elif item['kind'] == 'coil':
                    values[item['symbol']] = bool(power)
                energized[key] = bool(power)
        return {name: int(values[name]) for name in OUTPUTS}


def example_ir():
    """An explicit worked example, never a substitute for the selected AI run."""
    def contact(symbol, negated=False):
        return {'kind': 'contact', 'symbol': symbol, 'negated': negated}
    return {
        'schema_version': 1, 'contract_id': PROFILE, 'block': BLOCK,
        'symbols': [{'name': name, 'type': 'BOOL', 'storage': storage, 'initial': False}
                    for name, storage in [('Enable', 'input'), ('Start', 'input'), ('Stop', 'input'),
                                          ('Motor', 'output'), ('Running', 'static'), ('StartPrev', 'static'),
                                          ('StartRise', 'temp'), ('NextRunning', 'temp')]],
        'networks': [
            {'id': 'start_edge', 'target': 'StartRise', 'expression': {
                'kind': 'series', 'children': [contact('Start'), contact('StartPrev', True)]}},
            {'id': 'next_running', 'target': 'NextRunning', 'expression': {
                'kind': 'series', 'children': [contact('Enable'), contact('Stop', True), {
                    'kind': 'parallel', 'children': [contact('Running'), contact('StartRise')]}]}},
            {'id': 'commit_running', 'target': 'Running', 'expression': contact('NextRunning')},
            {'id': 'consume_start', 'target': 'StartPrev', 'expression': contact('Start')},
            {'id': 'publish_motor', 'target': 'Motor', 'expression': contact('NextRunning')},
        ],
        'unresolved': [],
    }
