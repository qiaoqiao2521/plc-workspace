"""A bounded file handoff for the existing PLC controller, not an Agent scheduler."""
import hashlib
import json
from pathlib import Path
import threading
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.tmp')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    pending.replace(path)


class AgentDispatch:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()

    def __call__(self, stage, role, packet):
        if self.cancelled.is_set():
            raise InterruptedError('Agent handoff cancelled')
        packet_id = uuid.uuid4().hex
        bound = digest(packet)
        save(self.runtime / 'packets' / (packet_id + '.json'),
             {'packet_id': packet_id, 'input_sha256': bound, 'stage': stage, 'role': role, 'packet': packet})
        answer_path = self.runtime / 'answers' / (packet_id + '.json')
        while not self.cancelled.wait(.1):
            if not answer_path.is_file():
                continue
            answer = json.loads(answer_path.read_text())
            if answer.get('input_sha256') != bound:
                raise ValueError('Agent answer input binding mismatch')
            return answer
        raise InterruptedError('Agent handoff cancelled')
