"""Validated in-memory geometry changes and new ImageJ ROI ZIP copies."""
import math
from dataclasses import replace
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from roifile import ROI_TYPE, ImagejRoi


def geometry(record, paths, metadata):
    paths = tuple(tuple((float(x), float(y)) for x, y in p) for p in paths)
    minimum = 1 if record.kind == 'point' else 2 if record.kind == 'line' else 3
    if len(paths) != 1 or len(paths[0]) < minimum:
        raise ValueError('단일 경로 ROI와 최소 좌표 수를 유지하세요')
    coords = np.asarray(paths[0])
    if not np.isfinite(coords).all() or (coords < 0).any():
        raise ValueError('좌표는 이미지 안의 유한한 양수 또는 0이어야 합니다')
    limits = np.array([metadata.width, metadata.height])
    outside = (coords >= limits).any() if record.kind == 'point' else (coords > limits).any()
    if outside:
        raise ValueError('좌표가 원본 이미지 범위를 벗어납니다')
    left, top = (math.floor(v) for v in coords.min(axis=0))
    right, bottom = (math.ceil(v) + (1 if record.kind == 'point' else 0) for v in coords.max(axis=0))
    right, bottom = min(metadata.width, max(left + 1, right)), min(metadata.height, max(top + 1, bottom))
    if right <= left or bottom <= top:
        raise ValueError('ROI의 외접 사각형이 비어 있습니다')
    return replace(record, paths=paths, bbox=(left, top, right - left, bottom - top))


def export_copy(path, records):
    """Exclusive creation means even an existing export cannot be overwritten."""
    path = Path(path)
    if path.suffix.lower() != '.zip' or not records:
        raise ValueError('ROI가 있는 상태에서 새 .zip 파일명을 지정하세요')
    payloads = []
    for i, record in enumerate(records):
        if len(record.paths) != 1:
            raise ValueError('복합 경로 ROI 내보내기는 아직 지원하지 않습니다')
        roi = ImagejRoi.frompoints(np.asarray(record.paths[0], dtype=np.float32))
        roi.roitype = {'point': ROI_TYPE.POINT, 'line': ROI_TYPE.POLYLINE, 'polygon': ROI_TYPE.POLYGON}[record.kind]
        roi.name = record.name
        roi.position = record.page_index + 1 if record.page_index is not None else 0
        roi.stroke_color = bytes.fromhex('ff' + record.color.lstrip('#'))
        payloads.append((f'{i + 1:04d}.roi', roi.tobytes()))
    # Validate all geometry before creating the destination; archive member names
    # are generated, independent of user ROI names or original archive paths.
    with path.open('xb') as output, ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in payloads:
            archive.writestr(name, data)
