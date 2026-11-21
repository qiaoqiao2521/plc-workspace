"""Deterministic verdicts for the currently supported checks, independent of AI."""
import copy
import hashlib
import json

PROFILE = 'conveyor-12-v1'
CONTRACT = {
    'id': PROFILE, 'block': 'FB_ConveyorPack', 'waiting_calls': 12,
    'start_call_counts_as_waiting': False, 'arrival_wins_at_deadline': True,
    'stop_revokes_motor': True, 'start_held_through_stop_restarts': False,
    'new_start_edge_after_release_restarts': True, 'done_is_one_call': True,
}
CONTRACT_SHA256 = hashlib.sha256(json.dumps(
    CONTRACT, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
STATUSES = ('pass', 'fail', 'unknown', 'not_run')
CHECK_TARGETS = {
    'source_structure': 'candidate',
    'linux_compile': 'scl_compile',
    'scan_contract': 'scl_behavior',
    'lad_scl_compare': 'lad_scl_compare',
    'tia_compile': 'tia_compile',
}


def goal(profile=None):
    required = ['source_structure', 'linux_compile']
    if profile:
        required.append('scan_contract')
    return {'target': 'scl_behavior' if profile else 'scl_compile',
            'required_checks': required}


def report_matches_profile(report, profile=None):
    if (not isinstance(report, dict) or profile not in (None, '', PROFILE)
            or report.get('profile') != (profile or None)):
        return False
    if not profile:
        return report.get('contract') is None and report.get('contract_sha256') is None
    return report.get('contract') == CONTRACT and report.get('contract_sha256') == CONTRACT_SHA256


def invalid_report(report):
    retained = report if isinstance(report, dict) else {}
    return {**retained, 'reason': 'invalid_report',
            'diagnostics': 'Missing or mismatched current verification goal/checks/contract; no acceptance granted. '
                           + str(retained.get('diagnostics', '')),
            'checks': [{'name': name,
                        'status': 'not_run' if name in ('lad_scl_compare', 'tia_compile') else 'unknown',
                        'detail': 'Invalid checker delivery'} for name in CHECK_TARGETS]}


def complete_report(report, profile=None):
    """Checker-side assembly. A total pass applies only to the selected goal."""
    report = copy.deepcopy(report)
    policy = goal(profile)
    checks = report.get('checks') if isinstance(report, dict) else None
    valid = isinstance(checks, list) and len(checks) <= len(CHECK_TARGETS)
    supplied = {}
    if valid:
        for item in checks:
            if (not isinstance(item, dict) or not isinstance(item.get('name'), str)
                    or item['name'] not in CHECK_TARGETS or item['name'] in supplied
                    or item.get('status') not in STATUSES or not isinstance(item.get('detail'), str)):
                valid = False
                break
            supplied[item['name']] = item
    # Never turn duplicate, unknown (including linux_validation), or malformed
    # observations into a passing canonical report by dropping them.
    if not valid:
        report = invalid_report(report)
        supplied = {item['name']: item for item in report['checks']}
    if ('profile' in report and report['profile'] != (profile or None)) or not report_matches_profile(
            {**report, 'profile': profile or None}, profile):
        report['reason'] = 'invalid_report'
    rows = []
    for name, target in CHECK_TARGETS.items():
        item = supplied.get(name, {'status': 'not_run', 'detail': 'Check not executed'})
        rows.append({'name': name, 'target': target, 'required': name in policy['required_checks'],
                     'status': item['status'], 'detail': item['detail']})
    statuses = [item['status'] for item in rows if item['required']]
    # Non-run/unknown mandatory checks never count as passing evidence.
    status = next((s for s in ('fail', 'unknown', 'not_run') if s in statuses), 'pass')
    if report.get('reason') in ('cancelled', 'worker_failed', 'tool_timeout', 'tool_missing', 'invalid_report'):
        status = 'unknown'
    by_name = {item['name']: item['status'] for item in rows}
    if (any(by_name[name] != 'not_run' for name in ('lad_scl_compare', 'tia_compile'))
            or (not profile and by_name['scan_contract'] != 'not_run')):
        report['reason'] = 'invalid_report'
        status = 'unknown'
    compiled = status == 'pass' and all(by_name[name] == 'pass' for name in ('source_structure', 'linux_compile'))
    report.update(schema_version=2, profile=profile or None, **policy, checks=rows, status=status,
                  acceptance={'scl_compile': compiled,
                              'scl_behavior': compiled and profile == PROFILE and by_name['scan_contract'] == 'pass',
                              'lad_scl_compare': False, 'tia_compile': False})
    return report


def assess_report(report, profile=None):
    """Consumer-side gate. Ignore claimed totals and reject incomplete/old reports.

    Historical reports may still be displayed/exported, but they cannot satisfy
    a new controller run. The goal and mandatory checks come from the request.
    """
    policy = goal(profile)
    valid = isinstance(report, dict) and report.get('schema_version') == 2
    rows = report.get('checks') if isinstance(report, dict) else None
    valid = valid and report_matches_profile(report, profile)
    valid = valid and all(report.get(key) == value for key, value in policy.items())
    valid = valid and isinstance(rows, list) and len(rows) == len(CHECK_TARGETS)
    if valid:
        names = [row.get('name') for row in rows if isinstance(row, dict)]
        valid = len(names) == len(rows) and all(isinstance(name, str) for name in names) and set(names) == set(CHECK_TARGETS)
    if valid:
        valid = all(row.get('target') == CHECK_TARGETS[row['name']]
                    and type(row.get('required')) is bool
                    and row['required'] == (row['name'] in policy['required_checks'])
                    and row.get('status') in STATUSES and isinstance(row.get('detail'), str)
                    for row in rows)
        # S1 has no LAD comparison or TIA executor. A forged row cannot add one.
        valid = valid and all(row['status'] == 'not_run' for row in rows
                              if row['name'] in ('lad_scl_compare', 'tia_compile'))
        valid = valid and (bool(profile) or all(row['status'] == 'not_run' for row in rows
                                               if row['name'] == 'scan_contract'))
    if not valid:
        report = invalid_report(report)
    return complete_report(report, profile)
