"""Typed native controls for commands verified against the pinned ImageJ 1.54p.

These are adapters to ImageJ, not replacement implementations of its algorithms.
The catalog deliberately excludes unverified arbitrary macro options.
"""
import copy
import math
import re


def number(key, label, default, minimum=0, maximum=1000):
    return {'key': key, 'label': label, 'kind': 'number', 'default': default,
                'minimum': minimum, 'maximum': maximum}


def flag(key, label, default=False):
    return {'key': key, 'label': label, 'kind': 'boolean', 'default': default}


COMMANDS = {
    'Gaussian Blur...': {'title': '가우시안 흐림', 'fields': [number('sigma', '표준편차 (픽셀)', 2)]},
    **{name + '...': {'title': label, 'fields': [number('radius', '반경 (픽셀)', 2, maximum=100 if name == 'Median' else 1000)]}
       for name, label in [('Median', '중앙값 필터'), ('Mean', '평균 필터'),
                           ('Minimum', '최솟값 필터'), ('Maximum', '최댓값 필터'),
                           ('Variance', '분산 필터')]},
    'Unsharp Mask...': {'title': '선명하게', 'fields': [
        number('radius', '흐림 표준편차 (픽셀)', 2),
        number('mask', '강도', 0.6, 0, 0.99)]},
    'Remove Outliers...': {'title': '이상 픽셀 제거', 'fields': [
        number('radius', '주변 반경 (픽셀)', 2, maximum=100),
        number('threshold', '주변 중앙값과의 밝기 차이', 50, 0, 1e12),
        {'key': 'which', 'label': '제거할 픽셀', 'kind': 'choice', 'default': 'Bright',
             'choices': ['Bright', 'Dark'], 'labels': ['주변보다 밝은 픽셀', '주변보다 어두운 픽셀']}]},
    'Subtract Background...': {'title': '배경 제거', 'wholeImage': True, 'fields': [
        number('rolling', '배경 반경 (픽셀)', 50, 0.001),
        flag('light', '밝은 배경'), flag('sliding', '포물면으로 배경 추정'),
        flag('disable', '배경 추정 전 평활화 끄기'), flag('separate', 'RGB 채널별 처리')]},
}


def command_form(command, options=''):
    """Use native controls only if every existing option is represented faithfully."""
    if command not in COMMANDS:
        return {}
    spec = copy.deepcopy(COMMANDS[command])
    fields = {f['key']: f for f in spec['fields']}
    values = {k: f['default'] for k, f in fields.items()}
    seen = set()
    for token in options.split():
        if token == 'slice' and token not in seen:
            seen.add(token)
            continue
        key, equals, raw = token.partition('=')
        if key not in fields or key in seen:
            return {}
        seen.add(key)
        field = fields[key]
        if field['kind'] == 'boolean':
            if equals:
                return {}
            values[key] = True
        elif not equals:
            return {}
        else:
            values[key] = raw
    try:
        values = validate_values(command, values)
    except ValueError:
        return {}
    return dict(spec, command=command, values=values)


def validate_values(command, values):
    if command not in COMMANDS or not isinstance(values, dict):
        raise ValueError('지원하는 영상 처리 명령을 선택하세요')
    fields = COMMANDS[command]['fields']
    if set(values) != {f['key'] for f in fields}:
        raise ValueError('처리 설정이 변경되었습니다. 명령을 다시 선택하세요')
    normalized = {}
    for field in fields:
        key, value = field['key'], values[field['key']]
        label = field['label']
        if field['kind'] == 'number':
            # Strings come from editable QML fields; disallow bool, NaN and macro text.
            if type(value) not in (int, float, str) or (isinstance(value, str) and
                    not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value.strip())):
                raise ValueError(label + ': 숫자를 입력하세요')
            value = float(value)
            if not math.isfinite(value) or not field['minimum'] <= value <= field['maximum']:
                raise ValueError(f"{label}: {field['minimum']:g}–{field['maximum']:g} 범위로 입력하세요")
        elif field['kind'] == 'boolean':
            if type(value) is not bool:
                raise ValueError(label + ': 선택 여부를 확인하세요')
        elif value not in field['choices']:
            raise ValueError(label + ': 목록에서 선택하세요')
        normalized[key] = value
    return normalized


def command_options(command, values):
    values = validate_values(command, values)
    tokens = []
    for field in COMMANDS[command]['fields']:
        key, value = field['key'], values[field['key']]
        if field['kind'] == 'boolean':
            if value:
                tokens.append(key)
        elif field['kind'] == 'number':
            tokens.append(f'{key}={value:.15g}')
        else:
            tokens.append(f'{key}={value}')
    # IJ.setupDialog otherwise promotes composite images to PROCESS_STACK.
    # Do not pass `stack`: writes to an ImageJ VirtualStack are not retained.
    return ' '.join(tokens + ['slice'])


def validate_selection(command, record):
    if record is None:
        return
    if COMMANDS[command].get('wholeImage'):
        raise ValueError('배경 제거는 전체 페이지를 처리합니다. 선택 ROI를 해제한 뒤 실행하세요')
    if record.kind != 'polygon' or record.tool in ('Text', 'Arrow', 'Angle') or len(record.paths) != 1:
        raise ValueError('영상 처리에는 사각형·타원·다각형 등 면적 ROI를 선택하세요')
