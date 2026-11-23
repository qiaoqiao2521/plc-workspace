"""Independent S2 acceptance probes: real compiler/graph, no model responses.

These tests exercise a worked IR and deliberately wrong variants. They do not
stand in for a real model API/Agent generation or repair run. Native tests need
SIM_IEC2C and SIM_MATIEC_LIB; absence is an explicit unittest skip, not a pass.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logic = _load('acceptance_logic_ir', 'logic-ir.py')
contract = _load('acceptance_latch_contract', 'latch-contract.py')
validation = _load('acceptance_candidate_validation', 'candidate-validation.py')
native = _load('acceptance_native_runtime', 'conveyor-runtime.py')
policy = validation.policy


def candidate(ir=None):
    ir = logic.example_ir() if ir is None else copy.deepcopy(ir)
    return {'request_fingerprint': 'independent-synthetic-latch-test',
            'logic_ir': ir, 'lad_networks': [], **logic.generate(ir)}


def semantic_mutants():
    """Each mutation still generates well-formed, compilable but wrong logic."""
    value = logic.example_ir()
    value['networks'][1]['expression']['children'][2]['kind'] = 'series'
    yield 'parallel_becomes_series', value

    value = logic.example_ir()
    value['networks'][1]['expression']['children'][1]['negated'] = False
    yield 'stop_contact_polarity_reversed', value

    value = logic.example_ir()
    value['networks'][1]['expression']['children'].pop(1)
    yield 'stop_condition_omitted', value

    value = logic.example_ir()
    value['networks'][1]['expression']['children'][2]['children'][1]['symbol'] = 'Start'
    yield 'held_start_causes_restart', value

    value = logic.example_ir()
    value['networks'].insert(0, value['networks'].pop(3))
    yield 'start_memory_updated_before_edge_test', value


def first_counterexample(runtime, scenarios):
    for case in scenarios:
        handle = runtime.create()
        try:
            for number, (inputs, expected) in enumerate(case['steps'], 1):
                actual = runtime.scan(handle, inputs)
                if actual != expected:
                    return {'name': case['name'], 'call': number, 'inputs': inputs,
                            'expected': expected, 'actual': actual}
        finally:
            runtime.destroy(handle)
    return None


def assert_instance_isolation(test, runtime):
    """Interleave two live instances; sequential reset alone would miss leakage."""
    running, idle = runtime.create(), runtime.create()
    try:
        test.assertEqual(runtime.scan(running, {'Enable': True, 'Start': True}), {'Motor': 1})
        test.assertEqual(runtime.scan(idle, {'Enable': True}), {'Motor': 0})
        test.assertEqual(runtime.scan(running, {'Enable': True}), {'Motor': 1})
        test.assertEqual(runtime.scan(idle, {'Enable': True, 'Stop': True}), {'Motor': 0})
        test.assertEqual(runtime.scan(running, {'Enable': True}), {'Motor': 1})
    finally:
        runtime.destroy(running)
        runtime.destroy(idle)
    fresh = runtime.create()
    try:
        test.assertEqual(runtime.scan(fresh, {'Enable': True}), {'Motor': 0})
        test.assertEqual(runtime.scan(fresh, {'Enable': True, 'Start': True}), {'Motor': 1})
    finally:
        runtime.destroy(fresh)


class IndependentLadAcceptanceTests(unittest.TestCase):
    def test_actual_serialized_graph_matches_fixed_and_bounded_contract(self):
        serialized = json.dumps(logic.emit_lad(logic.example_ir()))
        runtime = logic.LadRuntime(serialized)
        self.assertIsNone(first_counterexample(runtime, contract.fixed_scenarios()))
        self.assertIsNone(first_counterexample(runtime, contract.bounded_scenarios()))

    def test_wrong_graph_products_have_semantic_counterexamples(self):
        for name, ir in semantic_mutants():
            with self.subTest(mutation=name):
                runtime = logic.LadRuntime(json.dumps(logic.emit_lad(ir)))
                counterexample = first_counterexample(runtime, contract.fixed_scenarios())
                self.assertIsNotNone(counterexample, name)
                self.assertNotEqual(counterexample['expected'], counterexample['actual'])

    def test_graph_execution_does_not_recompute_the_original_ir(self):
        ir = logic.example_ir()
        graph = logic.emit_lad(ir)
        for network in graph['networks']:
            for node in network['nodes']:
                if node.get('kind') == 'contact' and node.get('symbol') == 'Stop':
                    node['negated'] = False
        serialized = json.dumps(graph)
        # A product executor must not consult either emitter at all.
        with patch.object(logic, 'emit_scl', side_effect=AssertionError('read SCL emitter')), \
                patch.object(logic, 'emit_lad', side_effect=AssertionError('read IR emitter')):
            runtime = logic.LadRuntime(serialized)
            self.assertIsNotNone(first_counterexample(runtime, contract.fixed_scenarios()))
        self.assertEqual(ir, logic.example_ir())

    def test_lad_instances_are_persistent_and_independent(self):
        assert_instance_isolation(self, logic.LadRuntime(json.dumps(logic.emit_lad(logic.example_ir()))))

    def test_duplicate_output_writer_is_structural_failure_not_unknown(self):
        result = candidate()
        duplicate = copy.deepcopy(result['logic_ir']['networks'][-1])
        duplicate['id'] = 'duplicate_motor_writer'
        result['logic_ir']['networks'].append(duplicate)
        with tempfile.TemporaryDirectory() as temp:
            report = validation.validate_candidate(result, Path(temp) / 'validation', profile=contract.PROFILE)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['reason'], 'source_invalid')
        self.assertEqual({row['name']: row['status'] for row in report['checks']}['source_structure'], 'fail')
        self.assertIn('multiple writers', report['diagnostics'])
        self.assertFalse(any(report['acceptance'].values()))

    def test_missing_tools_never_grant_dual_output_acceptance(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            report = validation.validate_candidate(candidate(), Path(temp) / 'validation', profile=contract.PROFILE)
        self.assertEqual(report['status'], 'unknown')
        self.assertEqual(report['reason'], 'tool_missing')
        self.assertFalse(any(report['acceptance'].values()))

    def test_missing_or_changed_artifacts_cannot_bind_to_a_dual_output_report(self):
        result = candidate()
        bound = policy.artifact_bindings(result)
        self.assertTrue(policy.artifacts_match(bound, result, contract.PROFILE))
        self.assertFalse(policy.artifacts_match({}, {'scl_files': result['scl_files']}, contract.PROFILE))
        self.assertFalse(policy.artifacts_match(bound, {**result, 'lad_graph': None}, contract.PROFILE))
        changed = copy.deepcopy(result)
        changed['logic_ir']['networks'][1]['expression']['children'][1]['negated'] = False
        self.assertFalse(policy.artifacts_match(bound, changed, contract.PROFILE))
        changed = copy.deepcopy(result)
        changed['lad_graph']['networks'].reverse()
        self.assertFalse(policy.artifacts_match(bound, changed, contract.PROFILE))


@unittest.skipUnless(os.getenv('SIM_IEC2C') and os.getenv('SIM_MATIEC_LIB'),
                     'Real matiec required; online models are not part of these tests')
class IndependentNativeAcceptanceTests(unittest.TestCase):
    def test_real_checker_requires_independent_behavior_and_both_products(self):
        result = candidate()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'validation'
            report = validation.validate_candidate(result, folder, profile=contract.PROFILE)
            self.assertEqual(report['status'], 'pass', report.get('diagnostics'))
            comparison = report['comparison']
            self.assertEqual((comparison['named_scenarios'], comparison['named_calls']), (14, 64))
            self.assertEqual((comparison['bounded_scenarios'], comparison['bounded_calls']), (4096, 16384))
            self.assertTrue(comparison['scl_passed'])
            self.assertTrue(comparison['lad_passed'])
            self.assertTrue(comparison['agreement_passed'])
            self.assertEqual(comparison['counterexamples'], {})
            self.assertTrue((folder / comparison['trace_file']).is_file())
            self.assertEqual(json.loads((folder / 'report.json').read_text()), report)
            self.assertTrue(policy.artifacts_match(report, result, contract.PROFILE))
        self.assertEqual(report['acceptance'], {'scl_compile': True, 'scl_behavior': True,
                                              'lad_scl_compare': True, 'tia_compile': False})
        self.assertEqual({row['name']: row['status'] for row in report['checks']}['tia_compile'], 'not_run')

    def test_equally_wrong_scl_and_lad_are_rejected_despite_matching_each_other(self):
        for name, ir in semantic_mutants():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as temp:
                report = validation.validate_candidate(candidate(ir), Path(temp) / 'validation', profile=contract.PROFILE)
                self.assertEqual(report['status'], 'fail', report.get('diagnostics'))
                statuses = {row['name']: row['status'] for row in report['checks']}
                self.assertEqual(statuses['linux_compile'], 'pass', report.get('diagnostics'))
                self.assertEqual(statuses['scan_contract'], 'fail')
                self.assertEqual(statuses['lad_scl_compare'], 'fail')
                comparison = report['comparison']
                self.assertTrue(comparison['agreement_passed'])
                self.assertFalse(comparison['scl_passed'])
                self.assertFalse(comparison['lad_passed'])
                self.assertIn('scl', comparison['counterexamples'])
                self.assertIn('lad', comparison['counterexamples'])
                self.assertFalse(any(report['acceptance'].values()))

    def test_real_native_instances_are_persistent_and_independent(self):
        source = validation.normalize(logic.emit_scl(logic.example_ir())).encode()
        with tempfile.TemporaryDirectory() as temp:
            runtime = native.NativeRuntime(Path(temp) / 'native', os.environ['SIM_IEC2C'], os.environ['SIM_MATIEC_LIB'],
                source_bytes=source, block_name=contract.BLOCK, inputs=contract.INPUTS,
                outputs=contract.OUTPUTS, normalized=True)
            assert_instance_isolation(self, runtime)


if __name__ == '__main__':
    unittest.main()
