"""Versioned local JSON saves. Never unpickle or import types named by a save."""
import collections
import dataclasses
import json
import math
import os
from pathlib import Path
import random
import sys


def registry():
    # Only already-loaded project dataclasses are eligible for reconstruction.
    root = Path(__file__).resolve().parent.parent
    result = {}
    for module in list(sys.modules.values()):
        location = getattr(module, '__file__', None)
        if not location or not Path(location).resolve().is_relative_to(root):
            continue
        for cls in vars(module).values():
            if isinstance(cls, type) and dataclasses.is_dataclass(cls):
                result[cls.__module__ + ':' + cls.__name__] = cls
    return result


def encode(value):
    if isinstance(value, random.Random):
        return {'t': 'rng', 'v': encode(value.getstate())}
    if dataclasses.is_dataclass(value):
        return {'t': 'data', 'c': type(value).__module__ + ':' + type(value).__name__,
                'v': encode(vars(value))}
    if isinstance(value, dict):
        return {'t': 'dict', 'v': [[encode(k), encode(v)] for k, v in value.items()],
                'counter': isinstance(value, collections.Counter)}
    for cls, tag in ((tuple, 'tuple'), (set, 'set'), (frozenset, 'frozenset'), (collections.deque, 'deque'), (list, 'list')):
        if isinstance(value, cls):
            return {'t': tag, 'v': [encode(v) for v in value]}
    if isinstance(value, float) and not math.isfinite(value):
        return {'t': 'float', 'v': repr(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError('Unsupported save type: ' + type(value).__name__)


def decode(value, classes):
    if not isinstance(value, dict):
        return value
    tag, payload = value['t'], value.get('v')
    if tag == 'dict':
        result = {decode(k, classes): decode(v, classes) for k, v in payload}
        return collections.Counter(result) if value.get('counter') else result
    if tag in ('tuple', 'set', 'frozenset', 'deque', 'list'):
        return {'tuple': tuple, 'set': set, 'frozenset': frozenset, 'deque': collections.deque, 'list': list}[tag](decode(v, classes) for v in payload)
    if tag == 'rng':
        result = random.Random(0)
        result.setstate(decode(payload, classes))
        return result
    if tag == 'float':
        return float(payload)
    if tag == 'data':
        cls = classes[value['c']]
        result = cls.__new__(cls)
        for key, item in decode(payload, classes).items():
            object.__setattr__(result, key, item)
        return result
    raise ValueError('Unknown save type')


def save(session, path):
    path = Path(path)
    payload = {'version': 1, 'profile': 'new_w5000_candidate', 'state': encode(vars(session))}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def load(path):
    import sim_server  # establishes the adapter's scripts import path
    from equipment_session import EquipmentSession
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('version') != 1 or payload.get('profile') != 'new_w5000_candidate':
        raise ValueError('Unsupported save version/profile')
    result = EquipmentSession.__new__(EquipmentSession)
    result.__dict__.update(decode(payload['state'], registry()))
    result.permanent._new_dp_state = result.dp_state
    result.inventory.validate()
    result._store_waiting_weapons()
    result.state()
    return result
