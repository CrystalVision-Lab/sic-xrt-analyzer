"""Local point-review UI consumer of versioned data-tools artifacts."""
import hashlib
import json
import math
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtQuick import QQuickImageProvider

from sic_xrt_analyzer.imaging.image_stack import JpegImageSource
from sic_xrt_analyzer.imaging.original_source import OriginalImageSource

LABELS = ['BPD', 'TED', 'TSD'] + ['TED_'+c for c in 'abcdef'] + ['TSD_'+c for c in 'abc'] + ['normal', 'dust', 'scratch']


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(4*1024**2):
            digest.update(block)
    return digest.hexdigest()


def event_hash(row):
    values = {k: v for k, v in row.items() if k != 'event_sha256'}
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validated_folder(folder):
    folder = Path(folder).resolve(strict=True)
    hashes = json.loads((folder/'output_hashes.json').read_text(encoding='utf-8'))
    for name, expected in hashes.items():
        path = (folder/name).resolve(strict=True)
        if not path.is_relative_to(folder) or sha(path) != expected:
            raise ValueError('데이터 작업 파일의 해시가 일치하지 않습니다: '+name)
    return folder


def json_lines(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8').splitlines()]


@contextmanager
def exclusive_writer(session):
    lock_path = session/'.write.lock'
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError('다른 창에서 저장 중입니다. 잠시 후 다시 시도하세요') from exc
    try:
        yield
    finally:
        os.close(descriptor)
        lock_path.unlink()


class ReviewStore:
    def __init__(self, workspace, candidates, session, review_plan=None):
        self.workspace, self.candidates = validated_folder(workspace), validated_folder(candidates)
        contract = json.loads((self.workspace/'workspace.json').read_text(encoding='utf-8'))
        proposal = json.loads((self.candidates/'candidate_summary.json').read_text(encoding='utf-8'))
        if (contract['schema'], contract['schema_version'], proposal['schema'], proposal['schema_version']) != ('annotation_workspace', 2, 'candidate_workbench', 1):
            raise ValueError('지원되지 않는 데이터 작업 버전입니다')
        if proposal['workspace_manifest_sha256'] != sha(self.workspace/'output_hashes.json'):
            raise ValueError('후보와 제공자 주석이 서로 다른 작업입니다')
        registry = validated_folder(contract['registry_root'])
        if sha(registry/'output_hashes.json') != contract['registry_manifest_sha256']:
            raise ValueError('원본 등록이 주석 복원 이후 바뀌었습니다')
        self.source_root = Path(contract['source_root']).resolve(strict=True)
        self.images = {p['asset_id']: p for p in json_lines(self.workspace/'images.jsonl')}
        assets = json_lines(registry/'assets.jsonl')
        self.loose = {a['sha256']: a for a in assets if a['source_kind'] == 'file' and a['kind'] == 'image'}
        self.items = {}
        for root, filename, key, kind in [(self.workspace, 'provider_points.jsonl', 'point_id', 'provider'),
                                          (self.candidates, 'candidates_2d.jsonl', 'candidate_id', 'contrast'),
                                          (self.candidates, 'candidates_3d.jsonl', 'candidate_id', 'contrast')]:
            for p in json_lines(root/filename):
                if p[key] in self.items:
                    raise ValueError('중복된 항목 ID입니다')
                self.items[p[key]] = p | {'item_id': p[key], 'source_kind': kind, 'frame_index': p.get('frame_index'),
                                         'fine_label': p.get('fine_label') or '종류 미지정', 'phase': p.get('phase') or 'unknown'}
        self.priority_ids = None
        if review_plan is not None:
            plan_root = validated_folder(review_plan)
            plan = json.loads((plan_root/'review_plan.json').read_text(encoding='utf-8'))
            ids = [p['item_id'] for p in plan['items']]
            if (plan.get('schema'), plan.get('schema_version')) != ('review_priority_plan', 1) or \
                    plan.get('workspace_manifest_sha256') != sha(self.workspace/'output_hashes.json') or \
                    plan.get('candidate_manifest_sha256') != sha(self.candidates/'output_hashes.json') or \
                    len(ids) != len(set(ids)) or len(ids) != plan.get('selected_count') or \
                    plan.get('total_items') != len(self.items) or not set(ids).issubset(self.items):
                raise ValueError('첫 검수 계획의 입력 또는 항목 목록이 잘못되었습니다')
            self.priority_ids = ids
        self.session = Path(session).resolve()
        if any(self.session.is_relative_to(p) or p.is_relative_to(self.session)
               for p in (self.source_root, self.workspace, self.candidates, registry)):
            raise ValueError('검수 기록은 원본과 작업 폴더 밖에 저장해야 합니다')
        self.header = {'schema': 'review_decisions_session', 'schema_version': 1,
                       'workspace_manifest_sha256': sha(self.workspace/'output_hashes.json'),
                       'candidate_manifest_sha256': sha(self.candidates/'output_hashes.json'),
                       'reviewer_display_name': contract['summary']['requested_reviewer_name']}
        if not self.session.exists():
            self.session.mkdir(parents=True)
            (self.session/'review_session.json').write_text(json.dumps(self.header, ensure_ascii=False, indent=2), encoding='utf-8')
            (self.session/'decisions.jsonl').write_bytes(b'')
        else:
            if json.loads((self.session/'review_session.json').read_text(encoding='utf-8')) != self.header:
                raise ValueError('기존 검수 기록의 입력 작업이 다릅니다')
        self.events = json_lines(self.session/'decisions.jsonl')
        self.latest = {}
        previous = None
        for seq, event in enumerate(self.events, 1):
            if event.get('sequence') != seq or event.get('previous_event_sha256') != previous or event.get('event_sha256') != event_hash(event):
                raise ValueError('검수 이력의 해시 또는 순서가 잘못되었습니다')
            if event.get('item_id') not in self.items:
                raise ValueError('검수 이력에 없는 항목이 포함되었습니다')
            previous = event['event_sha256']
            self.latest[event['item_id']] = event
        self.checked = {}
        self.lock = threading.RLock()

    def rows(self, area='', phase='', origin='', state='unreviewed', offset=0, limit=100, priority_only=True):
        result = []
        active = self.priority_ids if priority_only and self.priority_ids is not None else list(self.items)
        for ident in active:
            item = self.items[ident]
            actual_area = item['area_id'] or '3D'
            decision = self.latest.get(item['item_id'], {}).get('decision', 'unreviewed')
            if area and actual_area != area or phase and item['phase'] != phase or origin and item['source_kind'] != origin:
                continue
            if state and decision != state:
                continue
            result.append({k: item[k] for k in ('item_id', 'source_kind', 'image_asset_id', 'x', 'y', 'phase', 'frame_index', 'fine_label')} |
                          {'area_id': actual_area, 'status': decision})
        return {'total': len(result), 'rows': result[offset:offset+limit],
                'reviewed':sum(ident in self.latest for ident in active), 'all':len(active),
                'priority_count':len(self.priority_ids or []), 'full_count':len(self.items)}

    def save(self, item_id, decision, label, actor, checked, notes=''):
        if item_id not in self.items or decision not in {'confirm', 'correct', 'exclude', 'hold'}:
            raise ValueError('항목 또는 결정이 잘못되었습니다')
        actor = actor.strip()
        if not actor or len(actor) > 120 or any(s in actor.casefold() for s in ('codex', 'chatgpt', 'gpt', 'ai')):
            raise ValueError('실제로 확인한 사람의 이름을 입력하세요')
        if decision in {'confirm', 'correct'} and (label not in LABELS or not checked):
            raise ValueError('종류를 선택하고 직접 확인 체크를 해주세요')
        item = self.items[item_id]
        if decision == 'confirm' and (item['source_kind'] != 'provider' or label != item['fine_label']):
            raise ValueError('다른 종류는 수정으로 저장하세요')
        if len(notes) > 2000:
            raise ValueError('메모는 2000자 이하로 입력하세요')
        with self.lock, exclusive_writer(self.session):
            # A second window or external edit must not silently overwrite history.
            disk = json_lines(self.session/'decisions.jsonl')
            if disk != self.events:
                raise ValueError('다른 창에서 기록이 바뀌었습니다. 검수 창을 다시 열어주세요')
            row = {k: item[k] for k in ('item_id', 'image_asset_id', 'frame_index', 'source_kind', 'x', 'y')}
            row.update(event_id=str(uuid.uuid4()), sequence=len(self.events)+1,
                       previous_event_sha256=self.events[-1]['event_sha256'] if self.events else None,
                       decision=decision, reviewed_label=label if label in LABELS else None,
                       actual_actor=actor, actor_type='human', directly_checked=bool(checked), notes=notes,
                       reviewer_display_name=self.header['reviewer_display_name'], reviewed_at=datetime.now(UTC).isoformat())
            row['event_sha256'] = event_hash(row)
            with (self.session/'decisions.jsonl').open('ab') as stream:
                stream.write((json.dumps(row, ensure_ascii=False, allow_nan=False)+'\n').encode())
                stream.flush()
                os.fsync(stream.fileno())
            self.events.append(row)
            self.latest[item_id] = row
            return row

    def source(self, item):
        image = self.images[item['image_asset_id']]
        alias = self.loose.get(image['sha256'])
        if alias is None:
            raise ValueError('같은 원본의 풀어 둔 영상 파일이 필요합니다')
        path = (self.source_root/alias['locator']).resolve(strict=True)
        if not path.is_relative_to(self.source_root):
            raise ValueError('원본 폴더 밖의 영상입니다')
        signature = (path.stat().st_size, path.stat().st_mtime_ns)
        with self.lock:
            if path not in self.checked:
                if sha(path) != image['sha256']:
                    raise ValueError('원본 영상 해시가 바뀌었습니다')
                self.checked[path] = signature
            if self.checked[path] != signature:
                raise ValueError('원본 영상이 검수 중 바뀌었습니다')
        source = OriginalImageSource(path, item['frame_index'] or 0) if image['suffix'] in {'.tif', '.tiff'} else JpegImageSource(path)
        if (path.stat().st_size, path.stat().st_mtime_ns) != signature:
            raise ValueError('원본 영상이 검수 중 바뀌었습니다')
        return source

    def crop(self, item_id, marked=False, edge=512):
        item = self.items[item_id]
        source = self.source(item)
        x, y = item['x'], item['y']
        if not all(math.isfinite(p) for p in (x, y)) or not (0 <= x < source.metadata.width and 0 <= y < source.metadata.height):
            raise ValueError('좌표가 원본 영상 밖에 있습니다')
        left, top = max(0, round(x)-edge//2), max(0, round(y)-edge//2)
        width, height = min(edge, source.metadata.width-left), min(edge, source.metadata.height-top)
        pixels = source.read_region(left, top, width, height)
        if pixels.dtype != np.uint8:
            low, high = np.percentile(pixels, [1, 99])
            pixels = np.clip((pixels.astype(np.float32)-low)*255/max(high-low, 1), 0, 255).astype(np.uint8)
        if pixels.ndim == 2:
            pixels = np.repeat(pixels[..., None], 3, axis=-1)
        rgb = np.ascontiguousarray(pixels[..., :3])
        image = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
        if marked:
            painter = QPainter(image)
            xx, yy = round(x-left), round(y-top)
            # Outlined arms remain visible on bright/dark texture after scaling.
            # Leave the center open so the annotated defect is still visible.
            arms = [(xx-24, yy, xx-8, yy), (xx+8, yy, xx+24, yy),
                    (xx, yy-24, xx, yy-8), (xx, yy+8, xx, yy+24)]
            for color, thickness in [('#111827', 7), ('#ffeb3b', 3)]:
                painter.setPen(QPen(QColor(color), thickness))
                for arm in arms:
                    painter.drawLine(*arm)
            painter.end()
        source.validate_identity()
        return image


class ReviewBridge(QObject):
    error = Signal(str)

    def __init__(self, store):
        super().__init__()
        self.store = store

    @Slot(str, str, str, str, int, bool, result='QVariantMap')
    def query(self, area, phase, origin, state, offset, priority_only):
        return self.store.rows(area, phase, origin, state, max(0, offset), priority_only=priority_only)

    @Slot(str, str, str, str, bool, str, result='QVariantMap')
    def save(self, item_id, decision, label, actor, checked, notes):
        try:
            self.store.save(item_id, decision, label, actor, checked, notes)
            return {'ok': True}
        except (ValueError, OSError) as exc:
            return {'ok': False, 'error': str(exc)}


class ReviewImageProvider(QQuickImageProvider):
    def __init__(self, store, bridge):
        super().__init__(QQuickImageProvider.Image)
        self.store, self.bridge = store, bridge

    def requestImage(self, image_id, size, requested_size):
        try:
            parts = image_id.split('/')
            image = self.store.crop(parts[0], marked=len(parts)>1 and parts[1]=='marked')
        except Exception as exc:  # noqa: BLE001 - contain third-party decoder faults at the Qt provider boundary
            self.bridge.error.emit(str(exc))
            image = QImage(512, 512, QImage.Format_RGB888)
            image.fill('#1e293b')
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image
