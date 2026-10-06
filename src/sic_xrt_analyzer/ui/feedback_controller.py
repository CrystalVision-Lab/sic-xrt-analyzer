"""Durable per-image review session; user feedback never mutates predictions."""
import copy
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import numpy as np
from PySide6.QtCore import (
    Property,
    QLockFile,
    QObject,
    QSettings,
    QStandardPaths,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage

from sic_xrt_analyzer.analysis.feedback import (
    SCHEMA,
    apply_event,
    atomic_json,
    file_hash,
    latest_events,
    new_session,
    status,
    target_for,
    validate_session,
)
from sic_xrt_analyzer.imaging.original_source import SourceError

from .latest_reader import LatestReader
from .research_controller import local_path


class FeedbackController(QObject):
    changed = Signal()
    focusRequested = Signal(float,float)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        settings = bridge._settings
        self.root = (Path(settings.fileName()).parent/'reviews' if settings.format() == QSettings.IniFormat else
                     Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))/'reviews')
        self.loader, self.preview_loader = LatestReader(self), LatestReader(self)
        self.loader.ready.connect(self._ready)
        self.preview_loader.ready.connect(self._preview_ready)
        self.identity = self.source = self.data = None
        self.session_path = None
        self.loading = False
        self.error = self.export_path = self.mode = self.selected_id = self.preview = ''
        self.reviewer = str(settings.value('feedbackReviewer','양희승'))
        self.pending = {}
        self.filter = 'ALL'
        self.type_filter = 'ALL'
        self.revision = 0
        bridge.pipeline.changed.connect(self._source_changed)

    def _source_changed(self):
        source = self.bridge.pipeline.source
        identity = source.identity if source else None
        if identity == self.identity:
            self.changed.emit()
            return
        self.loader.invalidate()
        self.preview_loader.invalidate()
        self.identity, self.source = identity, source
        self.data = self.session_path = None
        self.pending = {}
        self.error = self.export_path = self.mode = self.selected_id = self.preview = ''
        self.loading = bool(source)
        self.changed.emit()
        if source:
            if source.metadata.dtype != 'uint8' or source.metadata.channels != 3:
                self.loading = False
                self.error = '검수 학습 자료는 현재 8비트 RGB TIFF/JPG만 지원합니다.'
                self.changed.emit()
                return
            def read():
                source.validate_identity()
                digest = file_hash(source.path)
                path = self.root/f'{digest}_page{source.page_index}.json'
                metadata = {'file_path':str(Path(source.path).resolve()),'sha256':digest,'page_index':source.page_index,
                    'width':source.metadata.width,'height':source.metadata.height,'coordinate_space':'raw_pixel_xy',
                    'orientation':'encoded_no_exif_rotation'}
                data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else new_session(metadata)
                if data.get('schema') != SCHEMA or any(data['source'][k] != metadata[k] for k in ('sha256','page_index','width','height','coordinate_space')):
                    raise ValueError('검수 기록의 원본 정보가 일치하지 않습니다.')
                validate_session(data)
                data['source']['file_path'] = metadata['file_path']
                source.validate_identity()
                return identity,path,data
            self.loader.submit(read)

    def _ready(self, payload, error):
        self.loading = False
        if error:
            self.error = '검수 기록을 열지 못했습니다: '+error
        elif payload and payload[0] == self.identity:
            self.session_path, self.data = payload[1:]
            selected = self.bridge.research.state['selected']
            if selected:
                self.select_candidate(selected)
        self.changed.emit()

    def _save(self, updated):
        """Serialize cooperating windows and refuse to overwrite a newer history."""
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(self.session_path)+'.lock')
        lock.setStaleLockTime(30000)
        if not lock.tryLock(0):
            raise ValueError('다른 창에서 이 영상의 검수 기록을 저장하고 있습니다.')
        try:
            if self.session_path.exists():
                on_disk = json.loads(self.session_path.read_text(encoding='utf-8'))
                if any(on_disk[k] != self.data[k] for k in ('session_id', 'wafer_id', 'events')):
                    raise ValueError('다른 창에서 검수 기록을 수정했습니다. 영상을 다시 열어 최신 기록을 불러오세요.')
            atomic_json(self.session_path, updated)
        finally:
            lock.unlock()

    def _candidates(self):
        result = self.bridge.pipeline.result
        if not result or not self.data or result.source_identity != self.identity:
            return {}
        rows = {}
        for p in self.bridge.research.rows:
            # Exact encoded coordinates are stable across repeated analyses.
            # Nearby points are NOT merged heuristically.
            ident = str(uuid5(NAMESPACE_URL,self.data['session_id']+':xy:'+repr(float(p['x']))+':'+repr(float(p['y']))))
            rows[ident] = {'candidate_id':p['id'],'x':p['x'],'y':p['y'],'predicted_type':p['type'],
                'analysis_id':result.analysis_id,'model_sha256':result.model_version,'model_id':result.model_id}
        return rows

    def _originals(self):
        rows = self._candidates()
        if self.data:
            rows.update(self.data.get('candidate_snapshot', {}))
            rows.update({k:r['original'] for k,r in latest_events(self.data).items()})
        rows.update(self.pending)
        return rows

    def selected(self):
        original = self._originals().get(self.selected_id)
        if not original:
            return {}
        event = latest_events(self.data).get(self.selected_id) if self.data else None
        target = event['target'] if event else target_for(original)
        return {'id':self.selected_id,'original':original,'target':target,'x':target['x'],'y':target['y'],
                'status':status(event),'note':event['note'] if event else '',
                'reviewer':event['reviewer'] if event else '', 'revision':event['revision'] if event else 0}

    @Slot(str)
    def selectRecord(self, ident):
        if ident not in self._originals():
            return
        self.selected_id, self.preview, self.mode = ident, '', ''
        selected = self.selected()
        source, token = self.source, ident
        def read():
            source.validate_identity()
            w,h = min(128,source.metadata.width),min(128,source.metadata.height)
            x=max(0,min(round(selected['x'])-64,source.metadata.width-w))
            y=max(0,min(round(selected['y'])-64,source.metadata.height-h))
            pixels=np.ascontiguousarray(source.read_region(x,y,w,h))
            if pixels.dtype != np.uint8 or pixels.shape != (h,w,3):
                raise ValueError('검수 미리보기는 RGB 8비트 영상만 지원합니다.')
            image=QImage(pixels.data,w,h,pixels.strides[0],QImage.Format_RGB888).copy()
            source.validate_identity()
            return token,image,[(selected['x']-x+.5)/w,(selected['y']-y+.5)/h]
        self.preview_loader.submit(read)
        self.changed.emit()
        self.focusRequested.emit(selected['x'],selected['y'])

    def select_candidate(self, row):
        candidate = next((k for k,v in self._candidates().items() if v['candidate_id']==row['id']),None)
        if candidate:
            # Selection alone is never a review and never claims human correctness.
            self.selected_id, self.mode = candidate, ''
            self.changed.emit()

    def _preview_ready(self, payload, error):
        if error:
            self.error = error
        elif payload and payload[0] == self.selected_id:
            self.bridge.provider.feedback_image = payload[1]
            self.preview_center=payload[2]
            self.revision+=1
            self.preview=f'image://tiff/feedback?revision={self.revision}'
        self.changed.emit()

    @Slot(str,str)
    def configure(self, reviewer, wafer):
        if not self.data:
            return
        if self.data['events'] and wafer != self.data['wafer_id']:
            self.error='기존 기록의 웨이퍼 번호는 변경할 수 없습니다.'
        elif wafer not in tuple(str(i) for i in range(1,10)) or not reviewer.strip():
            self.error='검수자명과 웨이퍼 번호를 입력하세요.'
        else:
            try:
                updated=copy.deepcopy(self.data)
                updated['wafer_id']=wafer
                self._save(updated)
                self.data,self.reviewer,self.error=updated,reviewer.strip(),''
                self.bridge._settings.setValue('feedbackReviewer',self.reviewer)
            except (OSError,ValueError) as exc:
                self.error=str(exc)
        self.changed.emit()

    @Slot(str,str,str,str,result=bool)
    def record(self, action, label='', note='', duplicate_of=''):
        try:
            if not self.data or not self.selected():
                raise ValueError('검수할 후보를 선택하세요.')
            self.source.validate_identity()
            originals=self._originals()
            if action=='duplicate' and duplicate_of not in originals:
                raise ValueError('같은 영상 안의 중복 대상을 선택하세요.')
            updated=apply_event(self.data,self.selected_id,originals[self.selected_id],action,self.reviewer,note,
                                label=label,duplicate_of=duplicate_of)
            if action == 'duplicate':
                updated.setdefault('candidate_snapshot', {})[duplicate_of] = originals[duplicate_of]
            self._save(updated)
            self.data,self.error=updated,''
            self.changed.emit()
            return True
        except (OSError,ValueError,SourceError) as exc:
            self.error=str(exc)
            self.changed.emit()
            return False

    @Slot(str)
    def setMode(self, mode):
        self.mode = mode if mode in ('location','add') and self.data and self.data['wafer_id'] and (mode=='add' or self.selected()) else ''
        self.changed.emit()

    @Slot(float,float,result=bool)
    def place(self,x,y,note=''):
        try:
            if self.mode not in ('add','location') or not self.data:
                return False
            self.source.validate_identity()
            if self.mode=='add':
                ident=str(uuid4())
                original={'candidate_id':None,'x':x,'y':y,'predicted_type':None,'analysis_id':None,'model_sha256':None,'model_id':None}
            else:
                ident,original=self.selected_id,self._originals()[self.selected_id]
            updated=apply_event(self.data,ident,original,self.mode,self.reviewer,note,x=x,y=y)
            self._save(updated)
            self.data,self.selected_id,self.mode,self.error=updated,ident,'',''
            self.selectRecord(ident)
            return True
        except (OSError,ValueError,SourceError) as exc:
            self.error=str(exc)
            self.changed.emit()
            return False

    @Slot(str)
    def setReviewFilter(self,value):
        self.filter=value
        self.changed.emit()

    @Slot(str)
    def setTypeFilter(self, value):
        self.type_filter = value if value in ('ALL', 'BPD', 'TED', 'TSD', 'UNKNOWN') else 'ALL'
        self.changed.emit()

    @Slot(int)
    def stepRecord(self, delta):
        rows = self.state['rows']
        if not rows:
            return
        index = next((i for i,r in enumerate(rows) if r['id'] == self.selected_id), -1 if delta > 0 else len(rows))
        self.selectRecord(rows[max(0, min(len(rows)-1, index+delta))]['id'])

    @Slot(str, result=bool)
    def confirmLocation(self, note=''):
        selected = self.selected()
        if not selected:
            return False
        self.setMode('location')
        return self.place(selected['x'], selected['y'], note)

    @Slot(str, result=bool)
    def importFeedback(self, path):
        try:
            if not self.data:
                raise ValueError('원본 영상을 먼저 여세요.')
            self.source.validate_identity()
            incoming = validate_session(json.loads(local_path(path).read_text(encoding='utf-8')))
            if any(incoming['source'][k] != self.data['source'][k] for k in ('sha256','page_index','width','height','coordinate_space','orientation')):
                raise ValueError('같은 원본·페이지의 검수 기록만 불러올 수 있습니다.')
            if self.data['events']:
                if incoming['session_id'] != self.data['session_id'] or incoming['wafer_id'] != self.data['wafer_id']:
                    raise ValueError('기존 기록과 세션 또는 웨이퍼가 다릅니다.')
                # Only an identical prefix can be extended, preventing silent overwrite.
                length = len(self.data['events'])
                if incoming['events'][:length] != self.data['events']:
                    raise ValueError('충돌하는 수정 이력이 있습니다. 기존 기록을 유지했습니다.')
            incoming['source']['file_path'] = str(Path(self.source.path).resolve())
            self._save(incoming)
            self.data, self.error, self.selected_id, self.preview = incoming, '', '', ''
            self.changed.emit()
            return True
        except (OSError, ValueError, KeyError, TypeError, SourceError) as exc:
            self.error = str(exc)
            self.changed.emit()
            return False

    @Slot(str,result=bool)
    def exportFeedback(self,folder):
        try:
            if not self.data or not self.data['events']:
                raise ValueError('저장할 검수 기록이 없습니다.')
            self.source.validate_identity()
            if file_hash(self.source.path) != self.data['source']['sha256']:
                raise ValueError('원본 해시가 변경됐습니다.')
            from sic_xrt_analyzer.analysis.research import new_run
            path=new_run(local_path(folder),'feedback')/'feedback.json'
            exported = copy.deepcopy(self.data)
            exported['candidate_snapshot'] = self._originals()
            validate_session(exported)
            atomic_json(path,exported)
            self.export_path,self.error=str(path),''
            self.changed.emit()
            return True
        except (OSError,ValueError,SourceError) as exc:
            self.error=str(exc)
            self.changed.emit()
            return False

    @Property('QVariantMap',notify=changed)
    def state(self):
        originals=self._originals()
        events=latest_events(self.data) if self.data else {}
        rows=[]
        for ident,original in originals.items():
            event=events.get(ident)
            target=event['target'] if event else target_for(original)
            kind = target['label'] or original['predicted_type'] or '미확정'
            if self.type_filter == 'UNKNOWN' and target['label'] is not None:
                continue
            if self.type_filter not in ('ALL', 'UNKNOWN') and kind != self.type_filter:
                continue
            if self.filter=='unreviewed' and event or self.filter=='reviewed' and not event:
                continue
            if self.filter=='deferred' and (not event or target['objectness'] is not None or target['duplicate_of']):
                continue
            rows.append({'id':ident,'x':target['x'],'y':target['y'],'type':kind,
                         'status':status(event),'reviewed':bool(event),'labelConfirmed':bool(target['label'])})
        return {'ready':bool(self.data),'loading':self.loading,'error':self.error,'reviewer':self.reviewer,
                'wafer':self.data['wafer_id'] if self.data else '', 'selected':self.selected(),'rows':rows,
                'reviewedCount':len(events),'total':len(originals),'mode':self.mode,'filter':self.filter,'typeFilter':self.type_filter,
                'preview':self.preview,'previewCenter':getattr(self,'preview_center',[.5,.5]),
                'exportPath':self.export_path,'sessionPath':str(self.session_path or ''),
                'eventsCount':len(self.data['events']) if self.data else 0,
                'overlay':[{'id':i,'x':e['target']['x'],'y':e['target']['y'],'status':status(e),
                            'objectness':e['target']['objectness'],'duplicate':bool(e['target']['duplicate_of'])} for i,e in events.items()]}
