"""Programmatic stage barriers; model agreement never substitutes for tool evidence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from test_local_server import request, result

spec = importlib.util.spec_from_file_location('workflow', Path(__file__).with_name('mcode-workflow.py'))
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class Gates(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.packets = {}
        self.folder = tempfile.TemporaryDirectory(prefix='plc-workflow-test-')
        self.addCleanup(self.folder.cleanup)
        self.answers = {
            'analysis': {'verdict': 'ready', 'questions': [], 'unresolved': [],
                         'specification': 'Confirmed process', 'obligations': ['Stop cancels action']},
            'spec-review': {'verdict': 'approve', 'findings': [], 'evidence': ['request']},
            'generation': result(request()),
            'semantic-review': {'verdict': 'pass', 'findings': [], 'evidence': ['source']},
            'interface-review': {'verdict': 'pass', 'findings': [], 'evidence': ['source']},
            'final-review': {'verdict': 'approve', 'findings': [], 'evidence': ['reviews']},
        }
        self.answers['generation']['questions'] = []
        self.answers['generation']['scl_files'] = [{'name': 'Fixture.scl', 'content': 'Synthetic fixture'}]

    def dispatch(self, stage, role, packet):
        self.calls.append((stage, role))
        self.packets[stage] = packet
        name = stage.rsplit('-', 1)[0] if stage.rsplit('-', 1)[-1].isdigit() else stage
        return {'input_sha256': workflow.digest(packet), 'answer': copy.deepcopy(self.answers[name])}

    def validate(self, candidate, directory, *, profile=None):
        report = {'files': workflow.source_manifest(candidate), 'request_fingerprint': candidate['request_fingerprint'],
                'checks': [{'name': name, 'status': 'pass',
                            'detail': 'Synthetic unit-test evidence, not native compilation'}
                            for name in ('source_structure', 'linux_compile')],
                'diagnostics': '', 'scope': 'Unit-test injection only'}
        if profile == 'conveyor-12-v1':
            report['contract'] = copy.deepcopy(workflow.validation_module().CONTRACT)
            report['contract_sha256'] = workflow.digest(report['contract'])
            report['checks'].append({'name': 'scan_contract', 'status': 'pass', 'detail': 'Synthetic scan fixture'})
        return workflow.bridge.verification_policy.complete_report(report, profile)

    def run_workflow(self, request_value=None, dispatch=None, **kwargs):
        return workflow.run_workflow(request_value or request(), dispatch or self.dispatch,
            runtime=Path(self.folder.name), validator=kwargs.pop('validator', self.validate),
            max_repairs=kwargs.pop('max_repairs', 0), **kwargs)

    def test_unresolved_blocks_before_generation_even_if_supervisor_approves(self):
        self.answers['analysis']['unresolved'] = ['Stop requirements contradict']
        outcome = self.run_workflow()
        self.assertEqual(outcome['verdict'], 'blocked')
        self.assertEqual([s for s, _ in self.calls], ['analysis', 'spec-review'])
        self.assertIsNone(outcome['result'])

    def test_supervisor_rejection_blocks_approved_analyst(self):
        self.answers['spec-review']['verdict'] = 'reject'
        self.assertEqual(self.run_workflow()['verdict'], 'blocked')
        self.assertNotIn('generation', [s for s, _ in self.calls])

    def test_stale_review_binding_is_rejected(self):
        def stale(stage, role, packet):
            response = self.dispatch(stage, role, packet)
            response['input_sha256'] = 'old-source'
            return response
        with self.assertRaisesRegex(ValueError, 'binding mismatch'):
            self.run_workflow(dispatch=stale)

    def test_failed_worker_becomes_unknown_and_still_reaches_supervisor(self):
        def failed(stage, role, packet):
            if stage == 'interface-review':
                raise RuntimeError('invalid JSON from worker')
            return self.dispatch(stage, role, packet)
        outcome = self.run_workflow(dispatch=failed)
        self.assertEqual(outcome['reviews']['interface']['verdict'], 'unknown')
        self.assertEqual(outcome['verdict'], 'rejected')
        self.assertIn(('final-review', 'supervisor'), self.calls)

    def test_supervisor_cannot_override_failed_or_unknown_review(self):
        for verdict in ['fail', 'unknown']:
            self.answers['semantic-review']['verdict'] = verdict
            outcome = self.run_workflow()
            self.assertEqual(outcome['verdict'], 'rejected')
            self.assertIsNone(outcome['result'])

    def test_new_questions_and_unsupported_proof_stop_review(self):
        self.answers['generation']['questions'] = ['Choose valve']
        self.assertEqual(self.run_workflow()['verdict'], 'blocked')
        self.assertNotIn('semantic-review', [s for s, _ in self.calls])
        self.answers['generation']['questions'] = []
        self.answers['generation']['checks'] = [{'name': 'Compile', 'status': 'pass', 'detail': 'Model says so'}]
        self.assertEqual(self.run_workflow()['verdict'], 'blocked')

    def test_parallel_reviews_single_supervisor_and_no_industrial_pass(self):
        barrier = threading.Barrier(2)
        def parallel(stage, role, packet):
            if stage in ['semantic-review', 'interface-review']:
                barrier.wait(timeout=2)
            return self.dispatch(stage, role, packet)
        outcome = self.run_workflow(dispatch=parallel)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['industrial_acceptance'], 'not_run')
        self.assertEqual([role for stage, role in self.calls if stage.endswith('review') and
                          stage in ['spec-review', 'final-review']], ['supervisor', 'supervisor'])
        self.assertEqual(outcome['candidate_sha256'], workflow.digest({
            'frozen': self.packets['generation']['data'], 'result': outcome['result']}))

    def test_skills_and_original_source_are_actually_in_generation_packet(self):
        req = request()
        req['brief']['source_files'] = [{'name': 'Original.scl', 'content': 'original code'}]
        req['brief']['validation_profile'] = 'conveyor-12-v1'
        content = json.dumps({'brief': req['brief'], 'states': req['states']},
                             ensure_ascii=False, separators=(',', ':'))
        req['request_fingerprint'] = workflow.hashlib.sha256(content.encode()).hexdigest()
        self.answers['generation']['request_fingerprint'] = req['request_fingerprint']
        self.run_workflow(req)
        data = self.packets['generation']['data']
        self.assertEqual(data['request']['brief']['source_files'][0]['content'], 'original code')
        self.assertEqual(data['validation_profile'], 'conveyor-12-v1')
        self.assertEqual(data['validation_contract']['waiting_calls'], 12)
        self.assertEqual(data['validation_contract_sha256'], workflow.digest(data['validation_contract']))
        self.assertTrue(any(item['path'].endswith('SKILL.md') and item['content'] for item in data['knowledge']))
        for item in data['knowledge']:
            self.assertEqual(item['sha256'], workflow.hashlib.sha256(
                (workflow.HERE.parents[1] / item['path']).read_bytes()).hexdigest())

    def test_compiler_error_is_given_to_source_only_repair_and_rechecked(self):
        self.answers['repair'] = {'scl_files': [{'name': 'Fixture.scl', 'content': 'fixed fixture'}],
                                  'summary': 'Fixed reported type error'}
        checked = []
        def compiler(candidate, directory, *, profile=None):
            checked.append(candidate['scl_files'][0]['content'])
            report = self.validate(candidate, directory, profile=profile)
            if len(checked) == 1:
                report.update(status='fail', diagnostics='Type mismatch at input.st:12')
                report['checks'][0].update(status='fail', detail=report['diagnostics'])
            return report
        outcome = self.run_workflow(validator=compiler, max_repairs=1)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(checked, ['Synthetic fixture', 'fixed fixture'])
        repair = self.packets['repair-1']
        self.assertIn('Type mismatch', repair['data']['validation']['diagnostics'])
        self.assertEqual(set(repair['schema']['properties']), {'scl_files', 'summary'})
        self.assertEqual(outcome['candidate']['io'], self.answers['generation']['io'])
        self.assertEqual(outcome['candidate']['lad_networks'], self.answers['generation']['lad_networks'])
        final = self.packets['final-review-1']['data']
        self.assertEqual(final['tool_evidence']['files'], workflow.source_manifest(outcome['result']))
        self.assertEqual(len(outcome['attempts']), 2)
        self.assertIn('-Synthetic fixture', outcome['attempts'][1]['diff'])
        for attempt in range(2):
            folder = Path(self.folder.name) / f'attempt-{attempt}'
            self.assertTrue((folder / 'candidate.json').exists())
            self.assertTrue((folder / 'validation.json').exists())
            self.assertTrue((folder / 'changes.diff').exists())

    def test_unknown_checker_retains_candidate_without_spending_repair_budget(self):
        def unavailable(candidate, directory, *, profile=None):
            report = self.validate(candidate, directory, profile=profile)
            report.update(status='unknown', diagnostics='Compiler unavailable')
            report['checks'][0].update(status='unknown', detail='Compiler unavailable')
            return report
        outcome = self.run_workflow(validator=unavailable, max_repairs=2)
        self.assertEqual(outcome['verdict'], 'blocked')
        self.assertIsNone(outcome['result'])
        self.assertEqual(outcome['candidate']['scl_files'], self.answers['generation']['scl_files'])
        self.assertFalse(any(stage.startswith('repair') for stage, _ in self.calls))
        self.assertEqual(json.loads((Path(self.folder.name) / 'outcome.json').read_text()), outcome)

    def test_stale_compiler_source_binding_is_unknown(self):
        def stale(candidate, directory, *, profile=None):
            report = self.validate(candidate, directory, profile=profile)
            report['files'][0]['sha256'] = 'old source hash'
            return report
        outcome = self.run_workflow(validator=stale)
        self.assertEqual(outcome['validation']['status'], 'unknown')
        self.assertNotIn(('semantic-review', 'semantics'), self.calls)

    def test_compile_only_draft_does_not_acquire_behavior_acceptance(self):
        outcome = self.run_workflow()
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['verification_goal']['target'], 'scl_compile')
        self.assertTrue(outcome['acceptance']['scl_compile'])
        self.assertFalse(outcome['acceptance']['scl_behavior'])
        self.assertEqual(next(c['status'] for c in outcome['validation']['checks']
                              if c['name'] == 'scan_contract'), 'not_run')

    def test_required_behavior_cannot_be_waived_by_checker_total_or_supervisor(self):
        req = request()
        req['brief']['validation_profile'] = 'conveyor-12-v1'
        req['request_fingerprint'] = workflow.hashlib.sha256(json.dumps(
            {'brief': req['brief'], 'states': req['states']}, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        self.answers['generation']['request_fingerprint'] = req['request_fingerprint']
        for status in ('not_run', 'unknown', 'fail'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                def invalid(candidate, directory, *, profile=None):
                    report = self.validate(candidate, directory, profile=profile)
                    next(c for c in report['checks'] if c['name'] == 'scan_contract')['status'] = status
                    report.update(status='pass', acceptance={'scl_behavior': True})
                    return report
                before = len(self.calls)
                outcome = workflow.run_workflow(req, self.dispatch, validator=invalid, runtime=folder, max_repairs=0)
                self.assertIsNone(outcome['result'])
                self.assertIsNotNone(outcome['candidate'])
                self.assertFalse(any(outcome['acceptance'].values()))
                self.assertNotIn('semantic-review', [stage for stage, _ in self.calls[before:]])

    def test_same_source_with_changed_requirement_cannot_reuse_old_report(self):
        def stale(candidate, directory, *, profile=None):
            report = self.validate(candidate, directory, profile=profile)
            report['request_fingerprint'] = 'previous requirement'
            return report
        outcome = self.run_workflow(validator=stale)
        self.assertEqual(outcome['validation']['status'], 'unknown')
        self.assertFalse(any(outcome['acceptance'].values()))
        self.assertIsNotNone(outcome['candidate'])

    def test_legacy_or_incomplete_checker_report_cannot_authorize_a_new_run(self):
        for variant in ('legacy', 'missing', 'waived'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as folder:
                def incomplete(candidate, directory, *, profile=None):
                    report = self.validate(candidate, directory, profile=profile)
                    if variant == 'legacy':
                        del report['schema_version']
                    elif variant == 'missing':
                        report['checks'].pop(1)
                    else:
                        report['checks'][1]['required'] = False
                    return report
                outcome = workflow.run_workflow(request(), self.dispatch, validator=incomplete, runtime=folder, max_repairs=0)
                self.assertEqual(outcome['verdict'], 'blocked')
                self.assertFalse(any(outcome['acceptance'].values()))

    def test_cancelled_check_retains_candidate_and_reason_without_acceptance(self):
        def cancelled(candidate, directory, *, profile=None):
            raise InterruptedError('User cancelled')
        with self.assertRaises(InterruptedError):
            self.run_workflow(validator=cancelled)
        retained = json.loads((Path(self.folder.name) / 'outcome.json').read_text())
        self.assertEqual(retained['verdict'], 'cancelled')
        self.assertEqual(retained['validation']['reason'], 'cancelled')
        self.assertEqual(retained['candidate']['scl_files'], self.answers['generation']['scl_files'])
        self.assertFalse(any(retained['acceptance'].values()))
        self.assertNotIn(('semantic-review', 'semantics'), self.calls)

    def test_cancelled_workflow_retains_checker_completed_observations(self):
        def cancelled(candidate, directory, *, profile=None):
            report = self.validate(candidate, directory, profile=profile)
            report['reason'] = 'cancelled'
            directory.mkdir()
            workflow.save(directory / 'report.json', report)
            raise KeyboardInterrupt('Cancelled after compiler observation')
        with self.assertRaises(KeyboardInterrupt):
            self.run_workflow(validator=cancelled)
        retained = json.loads((Path(self.folder.name) / 'outcome.json').read_text())
        self.assertEqual(retained['verdict'], 'cancelled')
        self.assertEqual(next(c['status'] for c in retained['validation']['checks']
                              if c['name'] == 'linux_compile'), 'pass')
        self.assertFalse(any(retained['acceptance'].values()))

    def test_checker_crash_is_unknown_with_its_actual_reason(self):
        def crashed(candidate, directory, *, profile=None):
            raise RuntimeError('Compiler worker unexpectedly exited')
        outcome = self.run_workflow(validator=crashed)
        self.assertEqual(outcome['verdict'], 'blocked')
        self.assertEqual(outcome['validation']['reason'], 'worker_failed')
        self.assertIn('unexpectedly exited', outcome['validation']['diagnostics'])
        self.assertFalse(any(outcome['acceptance'].values()))

    def test_review_failure_can_be_repaired_without_overriding_earlier_rejection(self):
        self.answers['repair'] = {'scl_files': [{'name': 'Fixture.scl', 'content': 'fixed edge handling'}],
                                  'summary': 'Fixed source violation from reviewer'}
        def dispatch(stage, role, packet):
            response = self.dispatch(stage, role, packet)
            if stage == 'semantic-review':
                response['answer'] = {'verdict': 'fail', 'findings': ['Source violates confirmed Stop'],
                                      'evidence': ['counterexample']}
            return response
        outcome = self.run_workflow(dispatch=dispatch, max_repairs=1)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['attempts'][0]['reviews']['semantics']['verdict'], 'fail')
        self.assertEqual(outcome['attempts'][1]['reviews']['semantics']['verdict'], 'pass')
        self.assertIn('semantic-review-1', self.packets)
        self.assertEqual(outcome['industrial_acceptance'], 'not_run')

    def test_disputed_added_requirement_reaches_fresh_review_without_source_change(self):
        self.answers['repair'] = {'scl_files': copy.deepcopy(self.answers['generation']['scl_files']),
            'summary': 'The frozen request only requires Stop cancellation; extra Busy lifecycle was not requested.'}
        def disputed(stage, role, packet):
            response = self.dispatch(stage, role, packet)
            if stage == 'semantic-review':
                response['answer'] = {'verdict': 'fail', 'findings': ['Busy must also cover the completion call'],
                                      'evidence': ['Reviewer preference; absent from confirmed request']}
            if stage == 'semantic-review-1':
                context = packet['data']['repair_context']
                self.assertIn('was not requested', context['summary'])
                self.assertEqual(context['previous_reviews']['semantics']['verdict'], 'fail')
                self.assertEqual(context['previous_validation']['status'], 'pass')
                self.assertEqual(packet['data']['result']['scl_files'], self.answers['generation']['scl_files'])
            return response
        outcome = self.run_workflow(dispatch=disputed, max_repairs=1)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['attempts'][0]['files'], outcome['attempts'][1]['files'])
        self.assertEqual(outcome['attempts'][1]['diff'], '')
        self.assertIn('repair_context', outcome['attempts'][1])
        self.assertEqual(outcome['attempts'][0]['reviews']['semantics']['verdict'], 'fail')
        self.assertEqual(outcome['attempts'][1]['reviews']['semantics']['verdict'], 'pass')

    @unittest.skipUnless(os.getenv('SIM_IEC2C') and os.getenv('SIM_MATIEC_LIB'),
                         'Real compiler repair loop needs SIM_IEC2C and SIM_MATIEC_LIB')
    def test_real_type_error_then_fixture_repair_recompiles_current_source(self):
        # The AI response is an explicit fixture here; compilation/scan evidence
        # is real. This does not claim an online mcode/Paperclip acceptance run.
        original = (workflow.HERE.parents[1] /
            'plans/plc-generation-ui/user-eval/candidates/FB_ConveyorPack.scl').read_text()
        corrected = original.replace('>= 8 THEN', '>= 12 THEN')
        broken = corrected.replace('#Motor := (#statState = 2);', "#Motor := 'not a bool';")
        self.assertNotEqual(broken, corrected)
        req = request()
        req['brief']['validation_profile'] = 'conveyor-12-v1'
        req['brief']['source_files'] = [{'name': 'FB_ConveyorPack.scl', 'content': original}]
        req['brief']['requirement'] = '将原输送带等待阈值8改为12次调用，启动不计，到位优先，Stop后Start保持不重启，其余保持原行为。'
        content = json.dumps({'brief': req['brief'], 'states': req['states']},
                             ensure_ascii=False, separators=(',', ':'))
        req['request_fingerprint'] = workflow.hashlib.sha256(content.encode()).hexdigest()
        self.answers['generation']['request_fingerprint'] = req['request_fingerprint']
        self.answers['generation']['scl_files'] = [{'name': 'FB_ConveyorPack.scl', 'content': broken}]
        self.answers['repair'] = {'scl_files': [{'name': 'FB_ConveyorPack.scl', 'content': corrected}],
                                  'summary': 'Repair fixture replaces the invalid BOOL assignment'}
        outcome = self.run_workflow(req, validator=workflow.validate_current, max_repairs=1)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['attempts'][0]['validation']['status'], 'fail')
        self.assertIn('error', outcome['attempts'][0]['validation']['diagnostics'].lower())
        self.assertEqual(outcome['attempts'][1]['validation']['status'], 'pass')
        self.assertNotEqual(outcome['attempts'][0]['files'], outcome['attempts'][1]['files'])
        self.assertEqual(outcome['validation']['files'], workflow.source_manifest(outcome['result']))
        self.assertEqual(outcome['validation']['contract']['waiting_calls'], 12)


if __name__ == '__main__':
    unittest.main()
