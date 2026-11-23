#!/usr/bin/env python3
"""Build and check the explicit synthetic latch benchmark outside the repository.

--example is a deterministic fixture, not an AI run. --proposal accepts a bound
IR proposal from the existing task handoff. Neither mode grants model-review,
Siemens, machine, or fresh browser-session acceptance.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('latch_workflow', HERE / 'plc-workflow.py')
workflow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(workflow)


def build_and_check(request, proposal, output, *, origin):
    workflow.bridge.validate_request(request)
    if request['brief'].get('validation_profile') != workflow.bridge.verification_policy.LATCH_PROFILE:
        raise ValueError('Only the explicit latch-start-stop-v1 benchmark is supported')
    workflow.bridge.validate_schema(proposal, workflow.IR_GENERATION)
    if any(proposal[key] != request[key] for key in ('schema_version', 'request_id', 'request_fingerprint')):
        raise ValueError('IR proposal belongs to another request')
    if proposal['questions']:
        raise ValueError('Unresolved questions prevent executable generation')
    folder = Path(output).resolve()
    if folder.is_relative_to(HERE.parents[1]) or folder.exists():
        raise ValueError('Use a fresh output directory outside the repository')
    folder.mkdir(parents=True)
    workflow.save(folder / 'request.json', request)
    workflow.save(folder / 'proposal.json', proposal)
    candidate = workflow.ir_candidate(proposal)
    workflow.save(folder / 'candidate.json', candidate)
    report = workflow.validate_current(candidate, folder / 'validation', request['brief']['validation_profile'])
    candidate['checks'] = [{key: row[key] for key in ('name', 'status', 'detail')} for row in report['checks']]
    workflow.save(folder / 'candidate.json', candidate)
    # This is a portable historical evidence package, not a forged reviewed_draft.
    engineering = {'kind': 'agent_candidate', 'origin': origin, 'request': request, 'result': candidate,
                   'verification': report, 'workflow': {'verdict': 'offline_tools_only',
                       'industrial_acceptance': 'not_run', 'validation_level': 'not_accepted',
                       'acceptance': {name: False for name in ('scl_compile', 'scl_behavior', 'lad_scl_compare', 'tia_compile')},
                       'reason': 'Independent local tool checks only; online specification/review/repair not executed'}}
    workflow.save(folder / 'engineering.json', engineering)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--example', action='store_true', help='Check the explicit deterministic fixture; no AI invocation')
    choice.add_argument('--proposal', type=Path, help='JSON IR proposal bound to the supplied task request')
    parser.add_argument('--request', type=Path, help='Request JSON or an exported task with a request field')
    parser.add_argument('--output', type=Path, required=True, help='Fresh output directory outside repository')
    args = parser.parse_args()
    if args.example:
        if args.request:
            parser.error('--example constructs its own explicit benchmark request')
        brief = json.loads((HERE.parent / 'data/latch-start-stop-brief.json').read_text())
        content = json.dumps({'brief': brief, 'states': []}, ensure_ascii=False, separators=(',', ':'))
        request = {'schema_version': 1, 'request_id': str(uuid.uuid4()),
                   'request_fingerprint': hashlib.sha256(content.encode()).hexdigest(), 'brief': brief, 'states': []}
        proposal = {key: request[key] for key in ('schema_version', 'request_id', 'request_fingerprint')}
        proposal.update(summary='Deterministic synthetic benchmark fixture; no online model run.', questions=[],
                        logic_ir=workflow.validation_module().logic_module().example_ir())
        origin = 'deterministic_benchmark_fixture'
    else:
        if not args.request:
            parser.error('--proposal requires --request from the same generation task')
        request = json.loads(args.request.read_text())
        request = request.get('request', request)
        proposal = json.loads(args.proposal.read_text())
        origin = 'external_ir_proposal_local_checks'
    try:
        report = build_and_check(request, proposal, args.output, origin=origin)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, str(error) + '\n')
    print(json.dumps({'status': report['status'], 'scope': report['scope'],
                      'checks': report['checks'], 'engineering': str(args.output.resolve() / 'engineering.json'),
                      'online_model': 'not_run', 'tia_compile': 'not_run'}, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'pass' else 2


if __name__ == '__main__':
    sys.exit(main())
