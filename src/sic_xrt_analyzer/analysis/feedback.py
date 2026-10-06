"""Append-only human review history in encoded original-pixel coordinates."""
import copy
import hashlib
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

SCHEMA = 'xrt_feedback_v1'
TYPES = ('BPD', 'TED', 'TSD')
ACTIONS = ('confirm', 'background', 'type', 'type_unknown', 'location', 'add', 'duplicate', 'defer', 'undo')


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+str(uuid4())+'.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def latest_events(data):
    return {row['record_id']: row for row in data['events']}


def new_session(source):
    return {'schema': SCHEMA, 'session_id': str(uuid4()), 'source': source, 'wafer_id': '',
            'events': [], 'exhaustive_annotations': False, 'expert_ground_truth': False}


def target_for(original):
    return {'x': original['x'], 'y': original['y'], 'objectness': None, 'label': None,
            'location_confirmed': False, 'duplicate_of': None}


def changed_target(data, record_id, original, action, x=None, y=None, label=None, duplicate_of=None):
    if action not in ACTIONS:
        raise ValueError('알 수 없는 검수 동작입니다.')
    history = [r for r in data['events'] if r['record_id'] == record_id]
    current = copy.deepcopy(history[-1]['target'] if history else target_for(original))
    current['duplicate_of'] = None
    if action == 'undo':
        if not history:
            raise ValueError('되돌릴 기록이 없습니다.')
        return copy.deepcopy(history[-1]['previous_target'])
    if action == 'confirm':
        current['objectness'] = True
    elif action == 'background':
        current.update(objectness=False, label=None, location_confirmed=False)
    elif action == 'type':
        if label not in TYPES:
            raise ValueError('확인한 종류를 선택하세요.')
        current.update(objectness=True, label=label)
    elif action == 'type_unknown':
        current.update(objectness=True, label=None)
    elif action in ('location', 'add'):
        source = data['source']
        if (type(x) not in (int,float) or type(y) not in (int,float) or not math.isfinite(x) or not math.isfinite(y)
                or not 0 <= x < source['width'] or not 0 <= y < source['height']):
            raise ValueError('원본 영상 안의 위치를 선택하세요.')
        current.update(x=float(x), y=float(y), objectness=True, location_confirmed=True)
        if action == 'add' and label in TYPES:
            current['label'] = label
    elif action == 'duplicate':
        if not duplicate_of or duplicate_of == record_id:
            raise ValueError('서로 다른 중복 대상이 필요합니다.')
        current.update(objectness=None, label=None, location_confirmed=False, duplicate_of=duplicate_of)
    elif action == 'defer':
        current.update(objectness=None, label=None, location_confirmed=False)
    return current


def apply_event(data, record_id, original, action, reviewer, note='', **kwargs):
    if not reviewer.strip() or data['wafer_id'] not in tuple(str(i) for i in range(1,10)):
        raise ValueError('검수자명과 웨이퍼 번호를 먼저 입력하세요.')
    if len(reviewer)>100 or len(note)>2000:
        raise ValueError('검수자명 또는 메모가 너무 깁니다.')
    old = latest_events(data).get(record_id)
    if old and old['original'] != original:
        raise ValueError('원본 후보의 기록은 변경할 수 없습니다.')
    result = copy.deepcopy(data)
    result['events'].append({'id': str(uuid4()), 'record_id': record_id, 'revision': old['revision']+1 if old else 1,
        'action': action, 'reviewer': reviewer.strip(), 'actor': 'human', 'created_at': datetime.now(UTC).isoformat(),
        'note': note, 'original': copy.deepcopy(original),
        'previous_target': copy.deepcopy(old['target'] if old else target_for(original)),
        'target': changed_target(data,record_id,original,action,**kwargs)})
    return result


def status(event):
    if not event:
        return '미검수'
    target = event['target']
    if target['duplicate_of']:
        return '중복'
    if target['objectness'] is False:
        return '배경'
    if target['objectness'] is True:
        return '결함'+(' · '+target['label'] if target['label'] else ' · 종류 미확정')
    return '보류'


def validate_session(data):
    """Replay the history; imported labels cannot bypass the review contract."""
    if data.get('schema') != SCHEMA or not data.get('session_id') or data.get('expert_ground_truth') is not False or data.get('exhaustive_annotations') is not False:
        raise ValueError('지원하지 않는 검수 기록입니다.')
    source = data['source']
    if (source.get('coordinate_space') != 'raw_pixel_xy' or source.get('orientation') != 'encoded_no_exif_rotation'
            or len(source.get('sha256', '')) != 64 or any(c not in '0123456789abcdef' for c in source['sha256'])
            or type(source.get('page_index')) is not int or source['page_index'] < 0
            or any(type(source.get(k)) is not int or source[k] < 1 for k in ('width', 'height'))):
        raise ValueError('원본 영상 정보가 올바르지 않습니다.')
    replay = new_session(source)
    replay['wafer_id'] = data['wafer_id']
    ids = set()
    for event in data['events']:
        if event['id'] in ids or event['actor'] != 'human':
            raise ValueError('중복되거나 지원하지 않는 검수 기록입니다.')
        ids.add(event['id'])
        datetime.fromisoformat(event['created_at'])
        original = event['original']
        for k, bound in (('x', source['width']), ('y', source['height'])):
            if type(original[k]) not in (int, float) or not math.isfinite(original[k]) or not 0 <= original[k] < bound:
                raise ValueError('원본 후보 좌표가 올바르지 않습니다.')
        target = event['target']
        expected = apply_event(replay, event['record_id'], original, event['action'], event['reviewer'], event['note'],
                               x=target['x'], y=target['y'], label=target['label'], duplicate_of=target['duplicate_of'])['events'][-1]
        if any(event[k] != expected[k] for k in ('revision', 'original', 'previous_target', 'target')):
            raise ValueError('검수 이력이 서로 맞지 않습니다.')
        replay['events'].append(event)
    return data
