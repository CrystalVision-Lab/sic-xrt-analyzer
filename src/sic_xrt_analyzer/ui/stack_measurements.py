"""Explicit XY calibration and non-destructive geometry measurements on TIFF stacks."""
import math
from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot


class StackMeasurements(QObject):
    changed = Signal()

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.pixel_width = self.pixel_height = 1.0
        self.distance = self.known = 1.0
        self.unit = 'pixel'
        self.error = ''
        self.reference = 0.0
        self.rows = []

    @Property('QVariantMap', notify=changed)
    def state(self):
        return {'unit': self.unit, 'pixelWidth': self.pixel_width, 'pixelHeight': self.pixel_height,
                'pixelsPerUnit': 1/self.pixel_width, 'reference': self.reference,
                'distance': self.distance, 'known': self.known,
                'rows': self.rows, 'error': self.error}

    def require_frame(self):
        frame = self.bridge.stack_viewer.frame
        working_stack = frame is not None and self.bridge._stack_context and frame.source.path == self.bridge._working_path
        if (frame is None or frame.source.metadata.format != 'TIFF' or (frame.source.metadata.page_count < 2 and not working_stack)
                or self.bridge.stack_viewer.initial_loading):
            raise ValueError('여러 페이지가 있는 XRT TIFF 스택을 준비한 뒤 사용하세요')
        return frame

    @Slot()
    def reset(self):
        self.pixel_width = self.pixel_height = 1.0
        self.distance = self.known = 1.0
        self.unit = 'pixel'
        self.reference = 0.0
        self.error = ''
        self.bridge.workbench.runtime.calibration = {'pixelWidth':1.,'pixelHeight':1.,'unit':'pixel'}
        self.changed.emit()

    @Slot()
    def useReferenceLine(self):
        try:
            frame = self.require_frame()
            record = self.bridge.roi_manager.selected_record(frame)
            if record.kind != 'line' or record.tool == 'Angle':
                raise ValueError('실제 길이를 알고 있는 눈금에 직선 또는 분할선을 그려 선택하세요')
            points = record.paths[0]
            self.reference = sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in pairwise(points))
            if self.reference <= 0:
                raise ValueError('기준선의 길이는 0보다 커야 합니다')
            self.error = ''
        except ValueError as exc:
            self.error = str(exc)
        self.changed.emit()

    @Slot(float, float, str, float)
    def setScale(self, pixels, known, unit, aspect):
        try:
            self.require_frame()
            if not all(math.isfinite(v) and v > 0 for v in (pixels, known, aspect)):
                raise ValueError('픽셀 거리·실제 거리·가로세로 비율은 0보다 큰 유한한 값이어야 합니다')
            unit = unit.strip()
            if not unit or len(unit) > 32 or any(c in unit for c in '\t\r\n'):
                raise ValueError('길이 단위를 입력하세요 (예: mm, µm)')
            width, height = known/pixels, known/pixels*aspect
            if not all(math.isfinite(v) and v > 0 for v in (width,height)):
                raise ValueError('눈금 계산 범위를 초과했습니다')
            self.pixel_width, self.pixel_height, self.unit = width, height, unit
            self.distance, self.known = pixels, known
            self.bridge.workbench.runtime.calibration = {'pixelWidth':self.pixel_width,'pixelHeight':self.pixel_height,'unit':unit}
            self.error = ''
        except ValueError as exc:
            self.error = str(exc)
        self.changed.emit()

    @Slot()
    def measure(self):
        try:
            frame = self.require_frame()
            record = self.bridge.roi_manager.selected_record(frame)
            if len(record.paths) != 1:
                raise ValueError('복합 ROI의 면적은 ImageJ Measure로 측정하세요')
            points = record.paths[0]
            if record.kind == 'point':
                metric, value, raw, unit = 'Count', len(points), len(points), 'points'
            elif record.tool == 'Angle':
                a,b,c = points[:3]
                u,v = ((a[0]-b[0])*self.pixel_width,(a[1]-b[1])*self.pixel_height), ((c[0]-b[0])*self.pixel_width,(c[1]-b[1])*self.pixel_height)
                if math.hypot(*u)*math.hypot(*v) == 0:
                    raise ValueError('각도 측정의 두 선은 길이가 0보다 커야 합니다')
                value = math.degrees(math.acos(max(-1,min(1,(u[0]*v[0]+u[1]*v[1])/(math.hypot(*u)*math.hypot(*v))))))
                metric,raw,unit = 'Angle',value,'°'
            elif record.kind == 'line':
                raw = sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in pairwise(points))
                value = sum(math.hypot((b[0]-a[0])*self.pixel_width,(b[1]-a[1])*self.pixel_height) for a,b in pairwise(points))
                metric,unit = 'Length',self.unit
            else:
                if record.tool == 'Oval':
                    raw = math.pi*(max(p[0] for p in points)-min(p[0] for p in points))*(max(p[1] for p in points)-min(p[1] for p in points))/4
                else:
                    raw = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))/2
                value,metric,unit = raw*self.pixel_width*self.pixel_height,'Area',self.unit+'²'
            if not math.isfinite(value):
                raise ValueError('측정값이 계산 범위를 초과했습니다')
            frame.source.validate_identity()
            self.rows.append({'file':Path(frame.source.path).name,'page':frame.source.page_index+1,
                              'roi':record.name,'metric':metric,'value':value,'unit':unit,'pixels':raw})
            self.error = ''
        except ValueError as exc:
            self.error = str(exc)
        self.changed.emit()

    @Slot()
    def clearResults(self):
        self.rows = []; self.changed.emit()

    @Slot(result=str)
    def resultsText(self):
        def clean(value):
            return str(value).replace('\t',' ').replace('\r',' ').replace('\n',' ')
        return 'File\tPage\tROI\tMeasurement\tValue\tUnit\tRaw pixels\n' + '\n'.join(
            '\t'.join(clean(r[k]) for k in ('file','page','roi','metric','value','unit','pixels')) for r in self.rows)

    @Slot(str)
    def saveResults(self, url):
        try:
            path = Path(self.bridge.localPath(url))
            if path.suffix.lower() != '.tsv' or not self.rows:
                raise ValueError('측정 결과가 있는 상태에서 새 .tsv 파일을 지정하세요')
            with path.open('x',encoding='utf-8-sig',newline='') as out:
                out.write(self.resultsText()+'\n')
            self.error = ''
        except (OSError,ValueError) as exc:
            self.error = str(exc)
        self.changed.emit()
