"""Independent expectations for the synthetic BOOL start/stop latch benchmark.

This is a benchmark contract, not a default process policy for real equipment.
Neither the fixed cases nor the bounded oracle import a generator, an IR
interpreter, a LAD executor, or a candidate program. Each scenario starts with
a fresh persistent instance. Four-call enumeration is finite test evidence,
not a proof for arbitrary programs or unbounded execution.
"""
from itertools import product


PROFILE = 'latch-start-stop-v1'
BLOCK = 'FB_StartStop'
INPUTS = ('Enable', 'Start', 'Stop')
OUTPUTS = ('Motor',)
BOUNDED_CALLS = 4
CONTRACT = {
    'id': PROFILE,
    'block': BLOCK,
    'inputs': {name: 'BOOL' for name in INPUTS},
    'outputs': {name: 'BOOL' for name in OUTPUTS},
    'call_model': 'one persistent instance, once per scan, including disabled scans',
    'initially_running': False,
    'initial_previous_start': False,
    'initial_motor': False,
    'first_call_start_high_is_rising_edge': True,
    'start_requires_enable_and_no_stop': True,
    'released_start_keeps_running': True,
    'stop_revokes_motor_in_same_call': True,
    'disable_revokes_motor_in_same_call': True,
    'stop_wins_over_start': True,
    'start_edges_consumed_while_stopped_or_disabled': True,
    'held_start_after_stop_or_disable_restarts': False,
    'new_start_edge_on_release_or_reenable_can_start': True,
    'outputs_reflect_committed_state_in_same_call': True,
    'power_loss_retention': 'outside_scope',
    'safety_function': False,
    'bounded_input_calls': BOUNDED_CALLS,
    'bounded_input_sequences': 8 ** BOUNDED_CALLS,
}


def _steps(rows):
    """Expand explicitly written Enable/Start/Stop/Motor truth-table rows."""
    return [({name: bool(value) for name, value in zip(INPUTS, row[:3])},
             {'Motor': row[3]}) for row in rows]


def fixed_scenarios():
    """Hand-written expected outputs; no oracle or candidate evaluation here."""
    cases = [
        ('initial_idle_and_enable_alone', [
            (0, 0, 0, 0),
            (1, 0, 0, 0),
            (1, 0, 0, 0),
        ]),
        ('first_enabled_call_start_high_then_latch', [
            (1, 1, 0, 1),
            (1, 0, 0, 1),
            (1, 0, 0, 1),
            (1, 0, 1, 0),
            (1, 0, 0, 0),
        ]),
        ('normal_start_and_stop_publish_without_delay', [
            (1, 0, 0, 0),
            (1, 1, 0, 1),
            (1, 0, 0, 1),
            (1, 0, 1, 0),
            (1, 0, 0, 0),
        ]),
        ('simultaneous_start_stop_consumes_start', [
            (1, 1, 1, 0),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('held_start_through_stop_needs_new_edge', [
            (1, 1, 0, 1),
            (1, 1, 1, 0),
            (1, 1, 0, 0),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('new_start_edge_during_stop_is_not_queued', [
            (1, 0, 0, 0),
            (1, 0, 1, 0),
            (1, 1, 1, 0),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('disable_clears_running_latch', [
            (1, 1, 0, 1),
            (1, 0, 0, 1),
            (0, 0, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('held_start_through_disable_needs_new_edge', [
            (1, 1, 0, 1),
            (0, 1, 0, 0),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('new_start_edge_while_disabled_is_not_queued', [
            (0, 0, 0, 0),
            (0, 1, 0, 0),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('first_disabled_call_also_consumes_high_start', [
            (0, 1, 0, 0),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('simultaneous_disable_stop_and_start', [
            (1, 1, 0, 1),
            (1, 0, 0, 1),
            (0, 1, 1, 0),
            (1, 1, 0, 0),
            (1, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('fresh_start_on_stop_release_is_allowed', [
            (1, 1, 0, 1),
            (1, 0, 1, 0),
            (1, 1, 0, 1),
        ]),
        ('fresh_start_on_reenable_is_allowed', [
            (1, 1, 0, 1),
            (0, 0, 0, 0),
            (1, 1, 0, 1),
        ]),
        ('repeated_start_edges_do_not_toggle_running', [
            (1, 1, 0, 1),
            (1, 0, 0, 1),
            (1, 1, 0, 1),
            (1, 0, 0, 1),
        ]),
    ]
    return [{'name': name, 'steps': _steps(rows)} for name, rows in cases]


def bounded_scenarios():
    """Yield all 4096 four-call BOOL input sequences from fresh initial state.

    The oracle is the independently written contract transition, not the
    behavior of either generated artifact. Named cases above intentionally
    retain literal expectations so an oracle error cannot silently rewrite
    those primary obligations. Each yielded dictionary is independent.
    """
    combinations = tuple(product((False, True), repeat=len(INPUTS)))
    for number, sequence in enumerate(product(combinations, repeat=BOUNDED_CALLS)):
        running = False
        previous_start = False
        steps = []
        for enable, start, stop in sequence:
            rising_start = start and not previous_start
            if not enable or stop:
                running = False
            elif rising_start:
                running = True
            # Otherwise keep the previous running state, including when Start
            # is released. Every invocation consumes Start, even when inhibited.
            previous_start = start
            steps.append(({'Enable': enable, 'Start': start, 'Stop': stop},
                          {'Motor': int(running)}))
        yield {'name': f'all_four_calls_{number:04d}', 'steps': steps}
