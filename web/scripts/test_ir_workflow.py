"""S2 workflow integration with explicit model fixtures, never online acceptance.

Native-labelled tests invoke the actual configured matiec/GCC checker and the
serialized LAD executor. Schema/gate-only tests explicitly inject observations.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


workflow = load('ir_workflow', HERE / 'plc-workflow.py')
logic = load('workflow_logic_ir', HERE / 'logic-ir.py')
checker = load('workflow_candidate_checker', HERE / 'candidate-validation.py')
COMPILER = os.environ.get('SIM_IEC2C')
LIBRARY = os.environ.get('SIM_MATIEC_LIB')
NATIVE_AVAILABLE = bool(COMPILER and shutil.which(COMPILER) and LIBRARY
                        and (Path(LIBRARY) / 'ieclib.txt').is_file() and shutil.which('gcc'))


def fingerprint(request):
    content = json.dumps({'brief': request['brief'], 'states': request['states']},
                         ensure_ascii=False, separators=(',', ':'))
    request['request_fingerprint'] = hashlib.sha256(content.encode()).hexdigest()
    return request


def request():
    brief = json.loads((HERE.parent / 'data/latch-start-stop-brief.json').read_text())
    return fingerprint({'schema_version': 1, 'request_id': 's2-explicit-model-fixture',
                        'brief': brief, 'states': []})


def proposal(req, ir=None):
    return {**{key: req[key] for key in ('schema_version', 'request_id', 'request_fingerprint')},
            'summary': 'Explicit model fixture, not an online model response',
            'questions': [], 'logic_ir': copy.deepcopy(ir if ir is not None else logic.example_ir())}


def wrong_parallel_ir():
    ir = logic.example_ir()
    ir['networks'][1]['expression']['children'][2]['kind'] = 'series'
    return ir


class IRWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.req = request()
        self.calls, self.packets = [], {}
        self.folder = tempfile.TemporaryDirectory(prefix='plc-ir-workflow-fixture-')
        self.addCleanup(self.folder.cleanup)
        self.generated_ir = logic.example_ir()
        self.repaired_ir = logic.example_ir()

    def dispatch(self, stage, role, packet):
        self.calls.append((stage, role))
        self.packets[stage] = copy.deepcopy(packet)
        if stage == 'analysis':
            answer = {'verdict': 'ready', 'questions': [], 'unresolved': [],
                      'specification': 'Explicitly selected synthetic latch-start-stop-v1 contract',
                      'obligations': ['Every call consumes Start; stop/disable clears Motor in the same call']}
        elif stage == 'spec-review' or stage.startswith('final-review'):
            answer = {'verdict': 'approve', 'findings': [], 'evidence': ['Explicit model fixture review']}
        elif stage.startswith(('semantic-review', 'interface-review')):
            answer = {'verdict': 'pass', 'findings': [], 'evidence': ['Explicit model fixture review']}
        elif stage == 'generation':
            answer = proposal(self.req, self.generated_ir)
        elif stage.startswith('repair-'):
            answer = {'logic_ir': copy.deepcopy(self.repaired_ir),
                      'summary': 'Explicit model fixture repairs parallel branch; no test or contract edits'}
        else:
            raise AssertionError('Unexpected stage: ' + stage)
        return {'input_sha256': workflow.digest(packet), 'answer': answer}

    def run_flow(self, **kwargs):
        runtime = Path(self.folder.name) / str(len(list(Path(self.folder.name).iterdir())))
        return workflow.run_workflow(self.req, kwargs.pop('dispatch', self.dispatch), runtime=runtime,
                                     max_repairs=kwargs.pop('max_repairs', 1), **kwargs)

    def native_validator(self, candidate, directory, *, profile=None):
        return checker.validate_candidate(candidate, directory, profile=profile,
                                          compiler=COMPILER, library=LIBRARY)

    def fixture_failure(self, candidate, directory, *, profile=None):
        """Explicit gate-only observations, used solely to exercise repair schemas."""
        policy = workflow.bridge.verification_policy
        report = {
            'files': workflow.source_manifest(candidate),
            'request_fingerprint': candidate['request_fingerprint'],
            **policy.artifact_bindings(candidate),
            'contract': policy.contract_for(profile),
            'contract_sha256': policy.contract_digest(profile),
            'generator': {'version': logic.GENERATOR_VERSION,
                          'sha256': hashlib.sha256((HERE / 'logic-ir.py').read_bytes()).hexdigest()},
            'checks': [{'name': name, 'status': status,
                        'detail': 'Explicit gate-only tool fixture; no native claim'}
                       for name, status in [('source_structure', 'pass'), ('linux_compile', 'pass'),
                                            ('scan_contract', 'fail'), ('lad_scl_compare', 'fail')]],
            'diagnostics': 'Explicit fixture contract counterexample',
            'scope': 'Schema/gate test only',
        }
        return policy.complete_report(report, profile)

    @unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for real native workflow tests')
    def test_model_fixture_bad_ir_repairs_once_with_real_native_and_lad_checks(self):
        self.generated_ir = wrong_parallel_ir()
        req_before = copy.deepcopy(self.req)
        outcome = self.run_flow(validator=self.native_validator)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['validation_level'], 'lad_scl_pass')
        self.assertEqual(outcome['acceptance'], {'scl_compile': True, 'scl_behavior': True,
                                               'lad_scl_compare': True, 'tia_compile': False})
        self.assertEqual(outcome['industrial_acceptance'], 'not_run')
        self.assertEqual(len(outcome['attempts']), 2)
        first, second = outcome['attempts']
        self.assertEqual(first['validation']['status'], 'fail')
        self.assertEqual(second['validation']['status'], 'pass')
        self.assertTrue(first['validation']['comparison']['counterexamples'])
        for key in ('logic_ir_sha256', 'lad_graph_sha256'):
            self.assertNotEqual(first[key], second[key])
        self.assertNotEqual(first['files'], second['files'])
        self.assertNotIn('semantic-review', [stage for stage, _ in self.calls])
        self.assertIn('semantic-review-1', [stage for stage, _ in self.calls])
        self.assertEqual(self.req, req_before)
        repair = self.packets['repair-1']
        self.assertEqual(set(repair['schema']['properties']), {'logic_ir', 'summary'})
        self.assertEqual(repair['data']['frozen'], self.packets['generation']['data'])
        self.assertEqual(repair['data']['frozen']['validation_contract'], checker.policy.contract_for(logic.PROFILE))
        products = logic.generate(self.repaired_ir)
        self.assertEqual(outcome['result']['scl_files'], products['scl_files'])
        self.assertEqual(outcome['result']['lad_graph'], products['lad_graph'])
        self.assertEqual(outcome['result']['logic_ir'], self.repaired_ir)
        self.assertEqual(outcome['result']['lad_networks'], [])
        compare = outcome['validation']['comparison']
        self.assertEqual(compare['named_calls'] + compare['bounded_calls'], 16448)
        root = next(Path(self.folder.name).iterdir())
        for number in range(2):
            attempt = root / f'attempt-{number}'
            self.assertTrue((attempt / 'validation/native/runtime.so').is_file())
            captured = json.loads((attempt / 'validation/lad_graph.json').read_text())
            saved = json.loads((attempt / 'candidate.json').read_text())
            self.assertEqual(captured, saved['lad_graph'])
        self.assertEqual(json.loads((root / 'outcome.json').read_text()), outcome)

    @unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for real native workflow tests')
    def test_model_fixture_bad_repair_exhausts_budget_with_real_tools(self):
        self.generated_ir = self.repaired_ir = wrong_parallel_ir()
        outcome = self.run_flow(validator=self.native_validator, max_repairs=1)
        self.assertEqual(outcome['verdict'], 'rejected')
        self.assertIn('budget exhausted', outcome['reason'])
        self.assertEqual(len(outcome['attempts']), 2)
        self.assertEqual([attempt['validation']['status'] for attempt in outcome['attempts']], ['fail', 'fail'])
        self.assertEqual([stage for stage, _ in self.calls if stage.startswith('repair')], ['repair-1'])
        self.assertFalse(any(stage.startswith(('semantic-review', 'final-review')) for stage, _ in self.calls))
        self.assertIsNone(outcome['result'])
        self.assertIsNotNone(outcome['candidate'])
        self.assertFalse(any(outcome['acceptance'].values()))

    def test_missing_actual_tool_blocks_without_spending_ir_repair_budget(self):
        def unavailable(candidate, directory, *, profile=None):
            return checker.validate_candidate(candidate, directory, profile=profile,
                compiler='/missing-plc-workflow-compiler', library='/missing-plc-workflow-library')
        outcome = self.run_flow(validator=unavailable, max_repairs=2)
        self.assertEqual(outcome['verdict'], 'blocked')
        self.assertEqual(outcome['validation']['reason'], 'tool_missing')
        self.assertEqual(outcome['validation']['status'], 'unknown')
        self.assertFalse(any(stage.startswith(('repair', 'semantic-review')) for stage, _ in self.calls))
        self.assertFalse(any(outcome['acceptance'].values()))
        self.assertEqual(outcome['candidate']['logic_ir'], self.generated_ir)

    @unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for real native workflow tests')
    def test_model_fixture_structural_ir_failure_is_retained_and_repairable(self):
        self.generated_ir['networks'][0]['expression']['children'][0]['symbol'] = 'Undeclared'
        outcome = self.run_flow(validator=self.native_validator)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        first = outcome['attempts'][0]['validation']
        self.assertEqual(first['reason'], 'source_invalid')
        self.assertEqual(first['status'], 'fail')
        self.assertEqual(first['files'], [])
        self.assertIn('undeclared symbol', first['diagnostics'])
        failed_candidate = self.packets['repair-1']['data']['candidate']
        self.assertEqual(failed_candidate['logic_ir'], self.generated_ir)
        self.assertNotIn('lad_graph', failed_candidate)
        self.assertEqual(outcome['validation_level'], 'lad_scl_pass')

    def test_mixed_lad_tool_unknown_and_scl_failure_does_not_trigger_ir_repair(self):
        def mixed(candidate, directory, *, profile=None):
            report = self.fixture_failure(candidate, directory, profile=profile)
            next(row for row in report['checks'] if row['name'] == 'lad_scl_compare').update(
                status='unknown', detail='Explicit unavailable LAD executor fixture')
            return report
        outcome = self.run_flow(validator=mixed, max_repairs=2)
        self.assertEqual(outcome['verdict'], 'blocked')
        self.assertFalse(any(stage.startswith(('repair', 'semantic-review')) for stage, _ in self.calls))
        self.assertFalse(any(outcome['acceptance'].values()))

    def test_fixture_repair_schema_rejects_test_contract_source_and_verdict_edits(self):
        for forbidden, value in [('validation_contract', {}), ('expected', [{'Motor': 1}]),
                                 ('scl_files', []), ('lad_graph', {}), ('checks', [])]:
            with self.subTest(forbidden=forbidden):
                self.calls.clear()
                def illegal(stage, role, packet):
                    response = self.dispatch(stage, role, packet)
                    if stage == 'repair-1':
                        response['answer'][forbidden] = value
                    return response
                with self.assertRaises(ValueError):
                    self.run_flow(dispatch=illegal, validator=self.fixture_failure)
                self.assertIn('repair-1', [stage for stage, _ in self.calls])
                self.assertNotIn('semantic-review-1', [stage for stage, _ in self.calls])

    def test_fixture_repair_cannot_change_ir_contract_id(self):
        self.repaired_ir['contract_id'] = 'self-approved-contract'
        with self.assertRaises(ValueError):
            self.run_flow(validator=self.fixture_failure)
        self.assertIn('repair-1', [stage for stage, _ in self.calls])

    def test_fixture_generation_cannot_supply_its_own_pass(self):
        def illegal(stage, role, packet):
            response = self.dispatch(stage, role, packet)
            if stage == 'generation':
                response['answer']['checks'] = [{'name': 'scan_contract', 'status': 'pass', 'detail': 'model claim'}]
            return response
        with self.assertRaises(ValueError):
            self.run_flow(dispatch=illegal, validator=self.fixture_failure)
        self.assertNotIn('repair-1', [stage for stage, _ in self.calls])

    @unittest.skipUnless(NATIVE_AVAILABLE, 'Set SIM_IEC2C/SIM_MATIEC_LIB for real native workflow tests')
    def test_real_report_changed_ir_lad_source_or_request_binding_cannot_be_reused(self):
        captured = None
        for changed in ('logic_ir_sha256', 'lad_graph_sha256', 'files', 'request_fingerprint'):
            with self.subTest(changed=changed):
                self.calls.clear()
                def stale(candidate, directory, *, profile=None):
                    nonlocal captured
                    if captured is None:
                        captured = self.native_validator(candidate, directory, profile=profile)
                        self.assertEqual(captured['status'], 'pass')
                    report = copy.deepcopy(captured)
                    if changed == 'files':
                        report['files'][0]['sha256'] = '0' * 64
                    else:
                        report[changed] = '0' * 64
                    return report
                outcome = self.run_flow(validator=stale, max_repairs=2)
                self.assertEqual(outcome['verdict'], 'blocked')
                self.assertEqual(outcome['validation']['status'], 'unknown')
                self.assertEqual(outcome['validation']['reason'], 'invalid_report')
                self.assertFalse(any(outcome['acceptance'].values()))
                self.assertFalse(any(stage.startswith(('repair', 'semantic-review')) for stage, _ in self.calls))

    def test_ir_artifacts_without_explicit_profile_do_not_acquire_acceptance(self):
        self.req['brief']['validation_profile'] = ''
        fingerprint(self.req)
        def legacy_with_ir(stage, role, packet):
            response = self.dispatch(stage, role, packet)
            if stage == 'generation':
                response['answer'] = workflow.ir_candidate(proposal(self.req))
            return response
        outcome = self.run_flow(dispatch=legacy_with_ir,
            validator=lambda candidate, directory, profile=None: checker.validate_candidate(
                candidate, directory, profile=profile, compiler='/unused-compiler', library='/unused-library'))
        self.assertEqual(outcome['verdict'], 'blocked')
        self.assertFalse(any(outcome['acceptance'].values()))
        self.assertNotIn('repair-1', [stage for stage, _ in self.calls])

    def test_fixed_synthetic_brief_cannot_be_reused_for_changed_process(self):
        for changed in ('requirement', 'constraints', 'block_name', 'source_files', 'states'):
            with self.subTest(changed=changed):
                self.req = request()
                if changed == 'source_files':
                    self.req['brief'][changed] = [{'name': 'Other.scl', 'content': 'anything'}]
                elif changed == 'states':
                    self.req['states'] = [{'id': 1}]
                else:
                    self.req['brief'][changed] += 'changed'
                fingerprint(self.req)
                with self.assertRaises(ValueError):
                    self.run_flow(validator=self.fixture_failure)
                self.assertEqual(self.calls, [])

    def test_transport_schema_accepts_legacy_and_optional_ir_without_granting_acceptance(self):
        legacy = {**{key: self.req[key] for key in ('schema_version', 'request_id', 'request_fingerprint')},
                  'summary': 'legacy fixture', 'questions': [], 'states': [], 'io': [],
                  'scl_files': [], 'lad_networks': [], 'checks': []}
        workflow.bridge.validate_schema(legacy, workflow.bridge.SCHEMA)
        current = workflow.ir_candidate(proposal(self.req))
        workflow.bridge.validate_schema(current, workflow.bridge.SCHEMA)
        self.assertNotIn('logic_ir', workflow.bridge.SCHEMA['required'])
        self.assertNotIn('lad_graph', workflow.bridge.SCHEMA['required'])
        for key in ('logic_ir', 'lad_graph'):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    workflow.bridge.validate_schema({**legacy, key: []}, workflow.bridge.SCHEMA)
        self.assertNotIn('acceptance', current)

    def test_ir_packet_schema_resolves_recursive_expression_refs(self):
        response = proposal(self.req)
        workflow.bridge.validate_schema(response, workflow.IR_GENERATION)
        workflow.bridge.validate_schema({'logic_ir': self.generated_ir, 'summary': 'fixture'}, workflow.IR_REPAIR)
        response['logic_ir']['networks'][0]['expression']['children'][0]['negated'] = 'false'
        with self.assertRaises(ValueError):
            workflow.bridge.validate_schema(response, workflow.IR_GENERATION)


if __name__ == '__main__':
    unittest.main()
