"""Read-only, bounded ImageJ ROI/ROI ZIP import in encoded original coordinates."""
import math
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from roifile import ROI_TYPE, ImagejRoi

MAX_FILE_BYTES = 4 * 1024**2
MAX_TOTAL_BYTES = 32 * 1024**2
MAX_ROIS = 1024
MAX_POINTS = 200_000


@dataclass(frozen=True)
class ImportedRoi:
    id: str
    name: str
    kind: str
    paths: tuple
    color: str
    bbox: tuple
    page_index: int | None


def decode_roi(data, filename, metadata, *, frames=0, slices=0):
    if len(data) < 64 or data[:4] != b'Iout':
        raise ValueError('빈 파일 또는 올바르지 않은 ImageJ ROI 헤더')
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('ROI 파일 크기 한도 초과')
    roi = ImagejRoi.frombytes(data)
    if roi.subtype.value != 0 or getattr(roi, 'rounded_rect_arc_size', 0):
        raise ValueError('텍스트/화살표/회전 도형 등 이 ROI 하위 형식은 아직 지원하지 않습니다')
    closed = {ROI_TYPE.POLYGON, ROI_TYPE.RECT, ROI_TYPE.OVAL, ROI_TYPE.FREEHAND, ROI_TYPE.TRACED}
    opened = {ROI_TYPE.LINE, ROI_TYPE.POLYLINE, ROI_TYPE.FREELINE, ROI_TYPE.ANGLE}
    if roi.multi_coordinates is not None:
        kind = 'polygon'
    elif roi.roitype == ROI_TYPE.POINT:
        kind = 'point'
    elif roi.roitype in closed:
        kind = 'polygon'
    elif roi.roitype in opened:
        kind = 'line'
    else:
        raise ValueError('지원하지 않는 ROI 도형')
    paths = [np.asarray(p, dtype=np.float64) for p in roi.coordinates(multi=True)]
    if not paths or any(p.ndim != 2 or p.shape[1] != 2 or not len(p) for p in paths):
        raise ValueError('ROI 좌표가 없습니다')
    count = sum(len(p) for p in paths)
    if count > MAX_POINTS or any(not np.isfinite(p).all() for p in paths):
        raise ValueError('ROI 좌표 수 한도 초과 또는 유효하지 않은 좌표')
    if kind != 'point' and any(len(p) < (3 if kind == 'polygon' else 2) for p in paths):
        raise ValueError('ROI 도형 좌표가 부족합니다')
    if any((p < 0).any() or (p[:, 0] > metadata.width).any() or (p[:, 1] > metadata.height).any() for p in paths):
        raise ValueError('ROI 좌표가 현재 이미지 범위를 벗어납니다. 대응하는 원본 이미지를 여세요')
    if kind == 'point' and any((p[:, 0] >= metadata.width).any() or (p[:, 1] >= metadata.height).any() for p in paths):
        raise ValueError('점 ROI가 현재 이미지 픽셀 범위를 벗어납니다')
    # One-based flattened position is unambiguous. T/Z are acquisition indices only.
    position = roi.position
    if roi.c_position > 1 or (roi.t_position > 0 and roi.z_position > 0):
        raise ValueError('다차원 C/Z/T ROI 위치는 현재 2D 페이지에 매핑할 수 없습니다')
    if roi.t_position > 0:
        if metadata.page_count != frames:
            raise ValueError('ROI frame 위치와 현재 이미지 페이지 구성이 다릅니다')
        position = roi.t_position
    if roi.z_position > 0:
        if metadata.page_count != slices:
            raise ValueError('ROI slice 위치와 현재 이미지 페이지 구성이 다릅니다')
        position = roi.z_position
    if position < 0 or position > metadata.page_count:
        raise ValueError('ROI 페이지 위치가 현재 스택 범위를 벗어납니다')
    coords = np.concatenate(paths)
    left, top = (math.floor(v) for v in coords.min(axis=0))
    right, bottom = (math.ceil(v) + (1 if kind == 'point' else 0) for v in coords.max(axis=0))
    right, bottom = min(metadata.width, max(left + 1, right)), min(metadata.height, max(top + 1, bottom))
    stroke = roi.stroke_color
    color = '#' + bytes(stroke[1:4]).hex() if stroke and len(stroke) == 4 and stroke[0] else '#45c3cf'
    return ImportedRoi(sha256(filename.encode('utf-8') + data).hexdigest(),
                       (roi.name or Path(filename).stem)[:160], kind,
                       tuple(tuple((float(x), float(y)) for x, y in p) for p in paths),
                       color, (left, top, right - left, bottom - top), position - 1 if position else None)


def load_rois(paths, metadata, *, frames=0, slices=0):
    records, errors = [], []
    total = count = point_count = 0

    def add(data, name):
        nonlocal total, count, point_count
        count += 1
        total += len(data)
        if count > MAX_ROIS or total > MAX_TOTAL_BYTES:
            raise ValueError('ROI 가져오기 전체 크기/개수 한도 초과')
        try:
            record = decode_roi(data, name, metadata, frames=frames, slices=slices)
            point_count += sum(len(p) for p in record.paths)
            if point_count > MAX_POINTS:
                raise ValueError('ROI 전체 좌표 수 한도 초과')
            records.append(record)
        except (ValueError, TypeError, IndexError, OverflowError) as exc:
            errors.append(Path(name).name + ': ' + str(exc))

    for name in paths:
        path = Path(name).resolve(strict=True)
        before = path.stat()
        if path.suffix.lower() == '.roi':
            if before.st_size > MAX_FILE_BYTES:
                errors.append(path.name + ': ROI 파일 크기 한도 초과')
                continue
            add(path.read_bytes(), str(path))
        elif path.suffix.lower() == '.zip':
            with ZipFile(path) as archive:
                entries = [e for e in archive.infolist() if not e.is_dir() and e.filename.lower().endswith('.roi')]
                if len(entries) > MAX_ROIS or sum(e.file_size for e in entries) > MAX_TOTAL_BYTES:
                    raise ValueError('ROI ZIP 크기/개수 한도 초과')
                if not entries:
                    errors.append(path.name + ': ZIP 안에 ROI 파일이 없습니다')
                for entry in entries:
                    if entry.file_size > MAX_FILE_BYTES:
                        errors.append(Path(entry.filename).name + ': ROI 파일 크기 한도 초과')
                        continue
                    # Read members directly; archive paths never write to the filesystem.
                    with archive.open(entry) as stream:
                        add(stream.read(MAX_FILE_BYTES + 1), str(path) + '/' + entry.filename)
        else:
            errors.append(path.name + ': .roi 또는 RoiSet.zip 파일을 선택하세요')
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('읽는 동안 ROI 파일이 변경되었습니다')
    return records, errors
