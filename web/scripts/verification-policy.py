"""Deterministic verdicts for the currently supported checks, independent of AI."""
import copy

PROFILE = 'conveyor-12-v1'
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


def complete_report(report, profile=None):
    """Checker-side assembly. A total pass applies only to the selected goal."""
    report = copy.deepcopy(report)
    policy = goal(profile)
    supplied = {item['name']: item for item in report.get('checks', [])}
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
    valid = valid and profile in (None, '', PROFILE) and report.get('profile') == (profile or None)
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
    if not valid:
        retained = report if isinstance(report, dict) else {}
        report = {**retained, 'reason': 'invalid_report',
                  'diagnostics': 'Missing or mismatched current verification goal/checks; no acceptance granted. '
                                 + str(retained.get('diagnostics', '')),
                  'checks': [{'name': name, 'status': 'unknown',
                              'detail': 'Invalid checker delivery'} for name in CHECK_TARGETS]}
        for row in report['checks']:
            if row['name'] in ('lad_scl_compare', 'tia_compile'):
                row.update(status='not_run', detail='No executor integrated for this check')
    return complete_report(report, profile)
