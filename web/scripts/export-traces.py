#!/usr/bin/env python3
"""Generate presentation data from the actual canonical ST, not a second model."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'validation/tests'))
from scan_runtime import compile_runtime, INPUTS

UNITS = ['BusyPhase', 'InvalidPhase', 'StepDone', 'SuccessPhase', 'TimeoutReached', 'NextPhase', 'NextTimer', 'NextTimeoutFault']

def step(note, timeout=8, **kwargs):
    return {'note': note, 'timeout': timeout, 'inputs': {k: kwargs.get(k, k == 'enable') for k in INPUTS}}

def start(timeout=8):
    return step('新的 Start 上升沿进入输送；进入步的这一拍，计时器为 0。', timeout, start=True, init_done=True)

SCENARIOS = [
 ('cycle', '完整工作循环', '从启动到输送、翻转、出料，观察一次调用最多迁移一步。', [
 step('初始化后，保持使能并等待新的启动沿。', init_done=True), start(),
 step('输送尚未完成，等待计数增加到 1。'),
 step('输送完成，进入翻转；切换相位时计时清零。', transport_done=True),
 step('翻转尚未完成，Q1 保持动作。'),
 step('翻转完成，进入出料。', flip_done=True),
 step('出料等待中，输送带和 Q2 保持动作。'),
 step('出料完成，返回输送；Done 只在这一拍为真。', output_done=True),
 step('下一拍继续输送，Done 脉冲消失。')]),
 ('timeout', '超时与故障恢复', '第 N 个等待调用到期。停止和 Reset 不确认故障；禁用清除当前错误。', [
 start(3), step('第 1 个等待调用。',3),step('第 2 个等待调用。',3),
 step('第 3 个等待调用到期：故障、超时原因与输出撤销同拍提交。',3),
 step('Stop 不清除已有故障。',3,stop=True),step('Reset 不能确认已锁存的块错误。',3,reset=True),
 step('实际执行一个禁用调用，清除当前故障；历史诊断仍保留。',3,enable=False),
 step('重新使能开启新诊断会话；没有新的 Start，不启动。',3),start(3)]),
 ('zero', '阈值切零再恢复', '运行中修改阈值：零会清空计时，恢复正值后从零开始。', [
 start(),step('累计等待 1 拍。'),step('累计等待 2 拍。'),step('累计等待 3 拍。'),
 step('阈值切换为 0，计时器立即清零，不冻结旧计数。',0),
 step('阈值保持 0，计时器保持 0。',0),step('恢复阈值 2：首个等待调用计数为 1。',2),
 step('恢复后第 2 个等待调用到期。',2)]),
 ('reset', '被拒绝的 Reset 沿', '停止期间的 Reset 沿被消费，停止解除后保持电平不算新的命令。', [
 start(),step('Stop 取消执行，CommandAborted 置位。',stop=True),
 step('停止期间 Reset 上升沿被拒绝，但边沿记忆仍更新。',stop=True,reset=True),
 step('Stop 解除、Reset 保持：没有新沿，CommandAborted 不能提前清除。',reset=True),
 step('释放 Reset 后，仍保持已取消状态。'),start()]),
 ('deadline', '完成与到期同拍', '相位完成优先于超时，边界扫描仍按正常工艺迁移。', [
 start(2),step('输送已等待 1 拍，下一拍即将到期。',2),
 step('到期拍同时收到输送完成，进入翻转而非故障。',2,transport_done=True),
 step('翻转进入后计时重新开始。',2)]),
 ('held', '保持 Start 不重启', '停止解除不恢复运动。启动请求必须先释放，再形成新的上升沿。', [
 start(),step('Start 持续为真，输送继续。',start=True),
 step('Stop 撤销动作，同时仍消费 Start 电平。',start=True,stop=True),
 step('停止解除，Start 仍为真，没有新上升沿，因此不启动。',start=True,init_done=True),
 step('先释放 Start。',init_done=True),start()])
]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iec2c', type=Path, required=True)
    parser.add_argument('--matiec-lib', type=Path, required=True)
    args=parser.parse_args()
    project=ROOT/'projects/FB_MainSequence'
    files=[project/'02_src/st'/f'FC_MainSequence_{u}.st' for u in UNITS]+[project/'02_src/st/FB_MainSequence.st']
    source='\n'.join(p.read_text() for p in files)
    scenarios=[]
    with tempfile.TemporaryDirectory(prefix='plc-web-traces-') as td:
        runtime=compile_runtime(source, Path(td), args.iec2c.resolve(), args.matiec_lib.resolve(), 'gcc')
        for id,title,description,steps in SCENARIOS:
            runtime.reset()
            frames=[]
            for index,s in enumerate(steps):
                frames.append({'scan':index+1, **s, 'outputs':runtime.scan(s['timeout'], **s['inputs'])})
            scenarios.append({'id':id,'title':title,'description':description,'frames':frames})
    evidence=json.loads((ROOT/'docs/verification/plc-semantics-v0.3/summary.json').read_text())
    formal=json.loads((ROOT/'docs/verification/plc-semantics-v0.3/formal-result.json').read_text())
    for key,p in [('source_sha256', project/'03_checks/plcverif/FB_MainSequence_PLCverif.scl'), ('projection_manifest_sha256',project/'00_meta/projection-manifest.json'), ('required_assertions_sha256',project/'03_checks/plcverif/required-assertions.txt')]:
        if formal[key]!=hashlib.sha256(p.read_bytes()).hexdigest():
            raise SystemExit(f'Stale verification evidence: {key}')
    data={'schema':1,'contract':'v0.3','interface':'0.2.0','kind':'compiled-ST trace replay',
          'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
          'formal_source_sha256':formal['source_sha256'],
          'evidence':{k:evidence[k] for k in ('scan_tests','tooling_tests','formal_assertions','control_combinations','differential_calls','formal_result')},
          'scenarios':scenarios}
    path=ROOT/'web/data/traces.json'
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(f'Exported {len(scenarios)} scenarios / {sum(len(s["frames"]) for s in scenarios)} scans')

if __name__=='__main__':main()
