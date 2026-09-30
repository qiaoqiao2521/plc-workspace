"""Programmatic stage barriers; model agreement never substitutes for tool evidence."""
import copy
import importlib.util
from pathlib import Path
import threading
import unittest
from test_local_server import request, result

spec = importlib.util.spec_from_file_location('workflow', Path(__file__).with_name('mcode-workflow.py'))
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class Gates(unittest.TestCase):
    def setUp(self):
        self.calls = []
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
        return {'input_sha256': workflow.digest(packet), 'answer': copy.deepcopy(self.answers[stage])}

    def test_unresolved_blocks_before_generation_even_if_supervisor_approves(self):
        self.answers['analysis']['unresolved'] = ['Stop requirements contradict']
        outcome = workflow.run_workflow(request(), self.dispatch)
        self.assertEqual(outcome['verdict'], 'blocked')
        self.assertEqual([s for s, _ in self.calls], ['analysis', 'spec-review'])
        self.assertIsNone(outcome['result'])

    def test_supervisor_rejection_blocks_approved_analyst(self):
        self.answers['spec-review']['verdict'] = 'reject'
        self.assertEqual(workflow.run_workflow(request(), self.dispatch)['verdict'], 'blocked')
        self.assertNotIn('generation', [s for s, _ in self.calls])

    def test_stale_review_binding_is_rejected(self):
        def stale(stage, role, packet):
            response = self.dispatch(stage, role, packet)
            response['input_sha256'] = 'old-source'
            return response
        with self.assertRaisesRegex(ValueError, 'binding mismatch'):
            workflow.run_workflow(request(), stale)

    def test_failed_worker_becomes_unknown_and_still_reaches_supervisor(self):
        def failed(stage, role, packet):
            if stage == 'interface-review':
                raise RuntimeError('invalid JSON from worker')
            return self.dispatch(stage, role, packet)
        outcome = workflow.run_workflow(request(), failed)
        self.assertEqual(outcome['reviews']['interface']['verdict'], 'unknown')
        self.assertEqual(outcome['verdict'], 'rejected')
        self.assertIn(('final-review', 'supervisor'), self.calls)

    def test_supervisor_cannot_override_failed_or_unknown_review(self):
        for verdict in ['fail', 'unknown']:
            self.answers['semantic-review']['verdict'] = verdict
            outcome = workflow.run_workflow(request(), self.dispatch)
            self.assertEqual(outcome['verdict'], 'rejected')
            self.assertIsNone(outcome['result'])

    def test_new_questions_and_unsupported_proof_stop_review(self):
        self.answers['generation']['questions'] = ['Choose valve']
        self.assertEqual(workflow.run_workflow(request(), self.dispatch)['verdict'], 'blocked')
        self.assertNotIn('semantic-review', [s for s, _ in self.calls])
        self.answers['generation']['questions'] = []
        self.answers['generation']['checks'] = [{'name': 'Compile', 'status': 'pass', 'detail': 'Model says so'}]
        self.assertEqual(workflow.run_workflow(request(), self.dispatch)['verdict'], 'blocked')

    def test_parallel_reviews_single_supervisor_and_no_industrial_pass(self):
        barrier = threading.Barrier(2)
        def parallel(stage, role, packet):
            if stage in ['semantic-review', 'interface-review']:
                barrier.wait(timeout=2)
            return self.dispatch(stage, role, packet)
        outcome = workflow.run_workflow(request(), parallel)
        self.assertEqual(outcome['verdict'], 'reviewed_draft')
        self.assertEqual(outcome['industrial_acceptance'], 'not_run')
        self.assertEqual([role for stage, role in self.calls if stage.endswith('review') and
                          stage in ['spec-review', 'final-review']], ['supervisor', 'supervisor'])
        self.assertEqual(outcome['candidate_sha256'], workflow.digest({
            'frozen': {'request': request(), 'analysis': self.answers['analysis']},
            'result': self.answers['generation']}))


if __name__ == '__main__':
    unittest.main()
