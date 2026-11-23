"""Structural and artifact-level tests; independent behavior tests are separate."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('logic_ir', Path(__file__).with_name('logic-ir.py'))
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


class LogicIRTests(unittest.TestCase):
    def test_deterministic_outputs_and_owned_validation(self):
        source = logic.example_ir()
        first = logic.generate(source)
        self.assertEqual(first, logic.generate(copy.deepcopy(source)))
        owned = logic.validate_ir(source)
        owned['symbols'][0]['name'] = 'Changed'
        self.assertEqual(source['symbols'][0]['name'], 'Enable')
        self.assertIn(' OR ', first['scl_files'][0]['content'])
        self.assertIn('NOT #Stop', first['scl_files'][0]['content'])
        graph = first['lad_graph']
        self.assertEqual(sum(n['kind'] == 'coil' for net in graph['networks'] for n in net['nodes']), 5)
        self.assertEqual(sum(n['kind'] == 'junction' for net in graph['networks'] for n in net['nodes']), 2)

    def test_ir_rejects_undeclared_type_extra_and_unresolved(self):
        mutations = [
            lambda ir: ir['networks'][0]['expression']['children'][0].update(symbol='Missing'),
            lambda ir: ir['symbols'][0].update(type='UINT'),
            lambda ir: ir.update(raw_scl='Motor := TRUE;'),
            lambda ir: ir['unresolved'].append('Which stop policy?'),
            lambda ir: ir['symbols'][0].update(initial=0),
            lambda ir: ir['networks'][0]['expression']['children'][0].update(negated=0),
            lambda ir: ir.update(schema_version=True),
            lambda ir: ir['networks'][0].update(target='Enable'),
            lambda ir: ir['symbols'][4].update(name='motor'),
            lambda ir: ir['symbols'][4].update(name='IF'),
            lambda ir: ir['symbols'][4].update(name='Bad;END_VAR'),
            lambda ir: ir['symbols'][4].update(name='FB_StartStop'),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                ir = logic.example_ir()
                mutate(ir)
                with self.assertRaises(ValueError):
                    logic.validate_ir(ir)

    def test_ir_rejects_missing_multiwriter_output_reads_and_temp_use(self):
        ir = logic.example_ir()
        ir['networks'].append({**ir['networks'][-1], 'id': 'second_output'})
        with self.assertRaisesRegex(ValueError, 'multiple writers'):
            logic.validate_ir(ir)
        ir = logic.example_ir()
        ir['networks'].pop()
        with self.assertRaisesRegex(ValueError, 'without one writer'):
            logic.validate_ir(ir)
        ir = logic.example_ir()
        ir['networks'][0]['expression']['children'][0]['symbol'] = 'Motor'
        with self.assertRaisesRegex(ValueError, 'outputs cannot be read'):
            logic.validate_ir(ir)
        ir = logic.example_ir()
        ir['networks'][0], ir['networks'][1] = ir['networks'][1], ir['networks'][0]
        with self.assertRaisesRegex(ValueError, 'before its network assignment'):
            logic.validate_ir(ir)

    def test_expression_limits_and_unsupported_nodes(self):
        ir = logic.example_ir()
        ir['networks'][0]['expression'] = {'kind': 'call', 'block': 'TON'}
        with self.assertRaisesRegex(ValueError, 'unsupported expression'):
            logic.validate_ir(ir)
        ir = logic.example_ir()
        leaf = {'kind': 'contact', 'symbol': 'Start', 'negated': False}
        node = copy.deepcopy(leaf)
        for _ in range(logic.MAX_EXPR_DEPTH):
            node = {'kind': 'series', 'children': [node, copy.deepcopy(leaf)]}
        ir['networks'][0]['expression'] = node
        with self.assertRaisesRegex(ValueError, 'budget'):
            logic.validate_ir(ir)
        ir = logic.example_ir()
        ir['networks'][0]['expression']['children'] *= 5
        with self.assertRaises(ValueError):
            logic.validate_ir(ir)

    def test_lad_reads_serialized_graph_not_ir(self):
        graph = logic.emit_lad(logic.example_ir())
        with self.assertRaises(TypeError):
            logic.LadRuntime(graph)
        # A graph-only polarity mutation is meaningful without touching the IR.
        next_network = graph['networks'][1]
        stop = next(n for n in next_network['nodes'] if n.get('symbol') == 'Stop')
        stop['negated'] = False
        with patch.object(logic, 'validate_ir', side_effect=AssertionError('must not inspect IR')):
            runtime = logic.LadRuntime(json.dumps(graph))
            handle = runtime.create()
            self.assertEqual(runtime.scan(handle, {'Enable': True, 'Start': True}), {'Motor': 0})
            runtime.destroy(handle)

    def test_lad_parallel_series_negation_and_instance_persistence(self):
        runtime = logic.LadRuntime(json.dumps(logic.emit_lad(logic.example_ir())))
        first, second = runtime.create(), runtime.create()
        self.assertEqual(runtime.scan(first, {'Enable': True, 'Start': True}), {'Motor': 1})
        self.assertEqual(runtime.scan(first, {'Enable': True}), {'Motor': 1})
        self.assertEqual(runtime.scan(second, {'Enable': True}), {'Motor': 0})
        self.assertEqual(runtime.scan(first, {'Enable': True, 'Stop': True}), {'Motor': 0})
        self.assertEqual(runtime.scan(first, {'Enable': True}), {'Motor': 0})
        runtime.destroy(first)
        with self.assertRaises(ValueError):
            runtime.scan(first, {})
        runtime.destroy(second)

    def test_lad_rejects_topology_and_transport_corruption(self):
        original = logic.emit_lad(logic.example_ir())
        mutations = [
            lambda graph: graph['networks'][0]['edges'].append(copy.deepcopy(graph['networks'][0]['edges'][0])),
            lambda graph: graph['networks'][0]['edges'][0].update(to='unknown'),
            lambda graph: graph['networks'][0]['edges'][0].update(to='n0'),
            lambda graph: graph['networks'][0]['nodes'].append({'id': 'orphan', 'kind': 'junction'}),
            lambda graph: graph['networks'][0]['nodes'][1].update(negated='false'),
            lambda graph: graph['networks'][0]['nodes'][1].update(symbol='Motor'),
            lambda graph: graph['networks'][0]['nodes'][1].update(kind='call'),
            lambda graph: graph.update(ir=logic.example_ir()),
            lambda graph: graph['networks'][0].update(exit='n0'),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                graph = copy.deepcopy(original)
                mutate(graph)
                with self.assertRaises(ValueError):
                    logic.validate_lad(graph)
        encoded = json.dumps(original).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON field'):
            logic.LadRuntime(encoded)
        with self.assertRaisesRegex(ValueError, 'size budget'):
            logic.LadRuntime(' ' * (logic.MAX_SERIALIZED_BYTES + 1))

    def test_lad_rejects_coil_bypass_and_multiple_writers(self):
        graph = logic.emit_lad(logic.example_ir())
        network = graph['networks'][0]
        network['edges'].append({'from': network['entry'], 'to': network['exit']})
        with self.assertRaises(ValueError):
            logic.validate_lad(graph)
        graph = logic.emit_lad(logic.example_ir())
        graph['networks'].append({**copy.deepcopy(graph['networks'][-1]), 'id': 'second_output'})
        with self.assertRaisesRegex(ValueError, 'multiple writers'):
            logic.validate_lad(graph)

    def test_nested_series_parallel_circuit_executes(self):
        ir = logic.example_ir()
        # (Enable OR Stop) AND (Start OR !Stop) exercises nested joins/splits.
        def contact(symbol, negated=False):
            return {'kind': 'contact', 'symbol': symbol, 'negated': negated}
        ir['networks'][0]['expression'] = {'kind': 'series', 'children': [
            {'kind': 'parallel', 'children': [contact('Enable'), contact('Stop')]},
            {'kind': 'parallel', 'children': [contact('Start'), contact('Stop', True)]}]}
        graph = logic.emit_lad(ir)
        self.assertEqual(sum(node['kind'] == 'junction' for node in graph['networks'][0]['nodes']), 4)
        runtime = logic.LadRuntime(json.dumps(graph))
        handle = runtime.create()
        self.assertEqual(runtime.scan(handle, {'Enable': True}), {'Motor': 1})
        runtime.destroy(handle)

    def test_readback_order_is_sequential_not_simultaneous(self):
        ir = logic.example_ir()
        consume = ir['networks'].pop(3)
        ir['networks'].insert(0, consume)
        # Structurally legal but wrong: committing StartPrev first eats the edge.
        graph = logic.emit_lad(ir)
        runtime = logic.LadRuntime(json.dumps(graph))
        handle = runtime.create()
        self.assertEqual(runtime.scan(handle, {'Enable': True, 'Start': True}), {'Motor': 0})
        runtime.destroy(handle)


if __name__ == '__main__':
    unittest.main()
