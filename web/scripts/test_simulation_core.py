"""Independent composition/scan contracts and real native worker regressions."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('simulation_core', Path(__file__).with_name('simulation-core.py'))
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='plc-composition-test-')
        self.service = core.SimulationService(runtime_root=self.folder.name)
        self.templates = {item['id']: item for item in self.service.templates()['templates']}

    def tearDown(self):
        self.service.shutdown()
        self.folder.cleanup()

    def test_templates_are_valid_without_claiming_runtime_availability(self):
        for key, template in self.templates.items():
            profile, _ = core.prepare_program(template['program'])
            scene, order = core.validate_scene(template['scene'], key)
            plant = core.Plant(scene, order)
            self.assertEqual(set(plant.sample()), set(profile['inputs']))
            self.assertFalse(plant.sample()['Start'])
        missing = core.SimulationService(compiler='/missing/compiler', library='/missing/lib',
                                         runtime_root=self.folder.name)
        try:
            self.assertFalse(missing.capabilities()['available'])
            with self.assertRaisesRegex(RuntimeError, 'SIM_IEC2C'):
                missing.dispatch('create', {'template': 'conveyor-pusher-v1'})
        finally:
            missing.shutdown()

    def test_port_types_and_single_writer_reject_wrong_assembly(self):
        scene = copy.deepcopy(self.templates['conveyor-pusher-v1']['scene'])
        scene['connections'][0]['from'] = 'belt.position'
        with self.assertRaisesRegex(ValueError, 'type mismatch'):
            core.validate_scene(scene, 'conveyor-pusher-v1')
        scene = copy.deepcopy(self.templates['conveyor-pusher-v1']['scene'])
        scene['bindings']['outputs']['Extend'].append('drive.command')
        with self.assertRaisesRegex(ValueError, 'Multiple writers'):
            core.validate_scene(scene, 'conveyor-pusher-v1')

    def test_cyclic_wiring_rejected_before_native_execution(self):
        scene = copy.deepcopy(self.templates['conveyor-pusher-v1']['scene'])
        scene['bindings']['outputs']['Motor'] = ['runlamp.value']
        scene['connections'].append({'from': 'eye.detected', 'to': 'drive.command'})
        with self.assertRaisesRegex(ValueError, 'acyclic'):
            core.validate_scene(scene, 'conveyor-pusher-v1')

    def test_unknown_component_nonfinite_parameter_and_unconnected_input_rejected(self):
        base = self.templates['conveyor-pusher-v1']['scene']
        scene = copy.deepcopy(base)
        scene['components'][0]['type'] = 'invented-actuator'
        with self.assertRaisesRegex(ValueError, 'Unsupported component'):
            core.validate_scene(scene, 'conveyor-pusher-v1')
        scene = copy.deepcopy(base)
        next(c for c in scene['components'] if c['id'] == 'belt')['parameters']['step'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'Invalid parameter'):
            core.validate_scene(scene, 'conveyor-pusher-v1')
        scene = copy.deepcopy(base)
        scene['connections'].pop()
        with self.assertRaisesRegex(ValueError, 'Unconnected'):
            core.validate_scene(scene, 'conveyor-pusher-v1')

    def test_program_interface_profile_and_timers_are_not_silently_adapted(self):
        program = copy.deepcopy(self.templates['latch-start-stop-v1']['program'])
        program['profile'] = 'some-other-plc'
        with self.assertRaisesRegex(ValueError, 'Unsupported simulation profile'):
            core.prepare_program(program)
        program = copy.deepcopy(self.templates['latch-start-stop-v1']['program'])
        program['source'] = program['source'].replace('Motor : BOOL;', 'Motor : INT;')
        with self.assertRaisesRegex(ValueError, 'interface'):
            core.prepare_program(program)
        program = copy.deepcopy(self.templates['latch-start-stop-v1']['program'])
        program['source'] = program['source'].replace('running : BOOL', 'clock : TON;\n    running : BOOL')
        with self.assertRaisesRegex(ValueError, 'time blocks'):
            core.prepare_program(program)

    def test_native_pragmas_are_rejected(self):
        program = copy.deepcopy(self.templates['latch-start-stop-v1']['program'])
        program['source'] += '\n{#include <unistd.h>}\n'
        with self.assertRaises(NotImplementedError):
            core.prepare_program(program)

    def test_sensor_values_cannot_be_written_as_operator_inputs(self):
        scene, order = core.validate_scene(self.templates['conveyor-pusher-v1']['scene'], 'conveyor-pusher-v1')
        plant = core.Plant(scene, order)
        with self.assertRaisesRegex(ValueError, 'Sensor inputs'):
            plant.set_inputs({'Start': True, 'AtEnd': True})
        self.assertFalse(plant.sample()['Start'])
        with self.assertRaises(ValueError):
            plant.set_inputs({'Start': 'false'})


class NativeSimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = os.environ.get('SIM_IEC2C')
        cls.library = os.environ.get('SIM_MATIEC_LIB')
        if not cls.compiler or not cls.library:
            raise unittest.SkipTest('Real compiled-ST tests require SIM_IEC2C and SIM_MATIEC_LIB')

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='plc-native-composition-test-')
        self.service = core.SimulationService(self.compiler, self.library, self.folder.name)
        self.templates = {item['id']: item for item in self.service.templates()['templates']}

    def tearDown(self):
        self.service.shutdown()
        self.folder.cleanup()

    def create(self, template='conveyor-pusher-v1', **extra):
        return self.service.dispatch('create', {'template': template, **extra})['session']

    def step(self, key, **inputs):
        return self.service.dispatch('step', {'session': key, 'inputs': inputs})['snapshot']

    def test_normal_cases_execute_all_four_actual_programs(self):
        for profile in self.templates:
            with self.subTest(profile=profile):
                report = self.service.dispatch('run_case', {'template': profile, 'case': 'normal'})
                self.assertEqual(report['status'], 'pass', report.get('first_failure'))
                self.assertTrue(report['trace'])
                self.assertTrue(report['acceptance']['simulation_case'])
                self.assertFalse(report['acceptance']['generation'])
                self.assertFalse(report['acceptance']['tia'])
                self.assertEqual(report['source_sha256'], hashlib.sha256(
                    self.templates[profile]['program']['source'].encode()).hexdigest())

    def test_default_pusher_feedback_is_sampled_before_motion(self):
        key = self.create()
        rows = [self.step(key, Start=True)]
        rows += [self.step(key, Start=False) for _ in range(14)]
        # Literal independent scan observations for .2/.25 travel-per-scan fixture.
        self.assertEqual([r['outputs']['Motor'] for r in rows[:6]], [1, 1, 1, 1, 1, 0])
        self.assertFalse(rows[4]['inputs']['AtEnd'])
        self.assertEqual(rows[4]['position'], 1)
        self.assertTrue(rows[5]['inputs']['AtEnd'])
        self.assertEqual([rows[i]['outputs']['State'] for i in (0, 5, 9, 13)], [1, 2, 3, 0])
        self.assertEqual([rows[i]['outputs']['Done'] for i in (12, 13, 14)], [0, 1, 0])

    def test_wrong_eight_call_program_does_not_inherit_twelve_call_acceptance(self):
        program = copy.deepcopy(self.templates['conveyor-8-demo-v1']['program'])
        program['profile'] = 'conveyor-12-v1'
        report = self.service.dispatch('run_case', {'program': program, 'case': 'jam'})
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['first_failure']['scan'], 9)
        self.assertEqual(report['first_failure']['expected'], 0)
        self.assertEqual(report['first_failure']['actual'], 1)
        self.assertFalse(report['acceptance']['simulation_case'])
        legacy = self.service.dispatch('run_case', {'template': 'conveyor-8-demo-v1', 'case': 'jam'})
        self.assertEqual(legacy['status'], 'pass')
        self.assertEqual(legacy['trace'][-1]['scan'], 9)

    def test_faults_timeout_recovery_and_held_start_are_independently_checked(self):
        for case in ('jam', 'sensor-failed', 'stop-restart', 'fault-reset'):
            with self.subTest(case=case):
                report = self.service.dispatch('run_case', {'template': 'conveyor-pusher-v1', 'case': case})
                self.assertEqual(report['status'], 'pass', report.get('first_failure'))
        report = self.service.dispatch('run_case', {'template': 'conveyor-12-v1', 'case': 'fault-reset'})
        self.assertEqual(report['status'], 'pass', report.get('first_failure'))

    def test_wrong_motor_output_is_a_counterexample_not_a_tool_error(self):
        program = copy.deepcopy(self.templates['latch-start-stop-v1']['program'])
        program['source'] = program['source'].replace('Motor := running;', 'Motor := TRUE;')
        report = self.service.dispatch('run_case', {'program': program, 'case': 'stop-restart'})
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(report['first_failure']['scan'], 2)
        self.assertEqual(report['first_failure']['name'], 'simultaneous_stop_revokes_actions')

    def test_typed_but_wrong_wiring_cannot_hide_an_energized_motor_on_stop(self):
        scene = copy.deepcopy(self.templates['latch-start-stop-v1']['scene'])
        scene['bindings']['outputs']['Motor'] = ['runlamp.value']
        scene['connections'].append({'from': 'enable.value', 'to': 'drive.command'})
        report = self.service.dispatch('run_case', {'template': 'latch-start-stop-v1',
                                                  'scene': scene, 'case': 'stop-restart'})
        self.assertEqual(report['status'], 'fail')
        failure = report['first_failure']
        self.assertEqual(failure['scan'], 2)
        self.assertEqual(failure['snapshot']['outputs']['Motor'], 0)
        drive = next(item for item in failure['snapshot']['components'] if item['id'] == 'drive')
        self.assertTrue(drive['state']['running'])

    def test_composed_extra_lamp_receives_same_output_and_changes_scene_identity(self):
        scene = copy.deepcopy(self.templates['latch-start-stop-v1']['scene'])
        scene['components'].append({'id': 'additional', 'type': 'lamp', 'position': [3, 0, 0], 'parameters': {}})
        scene['bindings']['outputs']['Motor'].append('additional.value')
        key = self.create('latch-start-stop-v1', scene=scene)
        snapshot = self.step(key, Start=True)
        self.assertTrue(next(c for c in snapshot['components'] if c['id'] == 'additional')['state']['value'])
        fresh = self.create('latch-start-stop-v1')
        other = self.service.dispatch('inspect', {'session': fresh})['snapshot']
        self.assertNotEqual(snapshot['scene_sha256'], other['scene_sha256'])
        self.assertEqual(snapshot['source_sha256'], other['source_sha256'])

    def test_session_and_case_state_are_independent(self):
        a, b = self.create('latch-start-stop-v1'), self.create('latch-start-stop-v1')
        self.step(a, Start=True)
        self.assertEqual(self.step(b)['outputs']['Motor'], 0)
        before = self.service.dispatch('inspect', {'session': a})['snapshot']
        report = self.service.dispatch('run_case', {'session': a, 'case': 'stop-restart'})
        self.assertEqual(report['status'], 'pass')
        after = self.service.dispatch('inspect', {'session': a})['snapshot']
        self.assertEqual(before, after)
        evidence = self.service.dispatch('export_trace', {'session': a})
        self.assertEqual(evidence['status'], 'not_run')
        self.assertFalse(evidence['acceptance']['simulation_case'])

    def test_bad_input_does_not_advance_or_partially_mutate_session(self):
        key = self.create()
        with self.assertRaisesRegex(ValueError, 'Sensor inputs'):
            self.step(key, Start=True, AtEnd=True)
        inspected = self.service.dispatch('inspect', {'session': key})['snapshot']
        self.assertEqual(inspected['scan'], 0)
        self.assertFalse(inspected['plant_inputs']['Start'])
        with self.assertRaises(ValueError):
            self.service.dispatch('step', {'session': key, 'count': 0})

    def test_infinite_native_loop_is_killed_without_wedging_other_sessions(self):
        self.service.scan_timeout = .3
        program = copy.deepcopy(self.templates['latch-start-stop-v1']['program'])
        program['source'] = program['source'].replace('Motor := running;', 'WHILE TRUE DO\n    running := running;\nEND_WHILE;\nMotor := running;')
        key = self.create('latch-start-stop-v1', program=program)
        with self.assertRaisesRegex(TimeoutError, 'watchdog'):
            self.step(key, Start=True)
        evidence = self.service.dispatch('export_trace', {'session': key})
        self.assertEqual(evidence['status'], 'unknown')
        self.assertEqual(evidence['trace'], [])
        self.assertTrue(evidence['halted'])
        other = self.create('latch-start-stop-v1')
        self.assertEqual(self.step(other, Start=True)['outputs']['Motor'], 1)

    def test_finite_native_calls_cannot_outlive_the_batch_wall_clock_budget(self):
        program = copy.deepcopy(self.templates['latch-start-stop-v1']['program'])
        program['source'] = program['source'].replace(
            'running : BOOL', 'counter : DINT := 0;\n    accumulator : DINT := 0;\n    running : BOOL')
        program['source'] = program['source'].replace('Motor := running;', '''
FOR counter := 1 TO 1000000 DO
    accumulator := accumulator + 1;
    IF accumulator >= 1000000 THEN
        accumulator := 0;
    END_IF;
END_FOR;
Motor := running;''')
        key = self.create('latch-start-stop-v1', program=program)
        first = self.step(key, Start=True)
        self.assertEqual(first['outputs']['Motor'], 1)  # Actual finite loop completes.
        self.service.batch_timeout = .05
        with self.assertRaisesRegex(TimeoutError, 'batch watchdog'):
            self.service.dispatch('step', {'session': key, 'count': 500, 'inputs': {'Start': False}})
        evidence = self.service.dispatch('export_trace', {'session': key})
        self.assertEqual(evidence['status'], 'unknown')
        self.assertGreaterEqual(len(evidence['trace']), 1)
        self.assertLess(len(evidence['trace']), 501)
        self.assertEqual(evidence['trace'][0], first)
        self.assertIn('batch watchdog', evidence['halted'])
        self.assertIsNotNone(self.service.sessions[key]['worker'].process.poll())
        other = self.create('latch-start-stop-v1')
        self.assertEqual(self.step(other, Start=True)['outputs']['Motor'], 1)


if __name__ == '__main__':
    unittest.main()
