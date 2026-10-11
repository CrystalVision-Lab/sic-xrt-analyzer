"""Opt-in TD-03 source-anchor, fidelity and Qt-submission validation.

QTest is automated dispatch, not physical-mouse acceptance. Keep captures,
actual paths, models and reports in an ignored artifacts directory.
"""
import argparse
import json
import math
import os
import platform
import subprocess
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import imagecodecs
import numpy as np
from benchmark_viewer import digest, spin
from benchmark_viewer_interaction import Session, stats
from PySide6.QtCore import Q_ARG, QMetaObject, QPoint, QPointF, Qt, qVersion
from PySide6.QtGui import QWheelEvent
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sic_xrt_analyzer.imaging.display_pyramid import DisplayPyramid
from sic_xrt_analyzer.ui import prepared_view
from sic_xrt_analyzer.ui.prepared_view import PreparedView


def invoke(obj, method, *args):
    assert QMetaObject.invokeMethod(obj, method, *(Q_ARG('QVariant', a) for a in args))


def source_anchor(s, local):
    frame = s.item('imageFrame')
    scale = s.viewer.property('displayScale')
    return [(local.x()-frame.x())/scale, (local.y()-frame.y())/scale]


def pointer(s, fx, fy):
    scene = s.viewport.mapToScene(QPointF(fx*s.viewport.width(), fy*s.viewport.height()))
    scene = QPoint(round(scene.x()), round(scene.y()))
    return scene, s.viewport.mapFromScene(QPointF(scene))


def wheel(s, point, delta):
    # Explicit Qt logical coordinates avoid the measured Qt 6.11 QTest wheel
    # position mismatch at fractional DPI. Product MouseArea sees a real event.
    event=QWheelEvent(QPointF(point),s.window.mapToGlobal(QPointF(point)),
                      QPoint(),QPoint(0,delta),Qt.NoButton,Qt.ControlModifier,
                      Qt.NoScrollPhase,False)
    s.app.sendEvent(s.window,event)


def anchor_cases(s):
    rows = []
    # Capture both the transform and original pixel; do not use clamped ROI coordinates.
    for name, fx, fy, tool in [('center',.5,.5,'wheel'), ('top-left',.1,.1,'wheel'),
                              ('bottom-right',.9,.9,'wheel'), ('after-pan',.35,.65,'wheel'),
                              ('zoom-click',.4,.6,'click'), ('round-trip',.3,.7,'wheel')]:
        invoke(s.viewer,'setActualZoom',1.)
        s.viewer.setProperty('panX',73. if name=='after-pan' else 0.)
        s.viewer.setProperty('panY',-61. if name=='after-pan' else 0.)
        s.ui.setProperty('activeTool','Zoom' if tool=='click' else 'Pan')
        s.settle()
        scene, local = pointer(s,fx,fy)
        before = source_anchor(s,local)
        for i in range(4):
            if tool=='click':
                QTest.mouseClick(s.window,Qt.LeftButton,Qt.NoModifier,scene)
            else:
                wheel(s,scene,120)
            s.settle()
            after = source_anchor(s,local)
            rows.append({'case':name,'step':i+1,'zoom':s.ui.property('effectiveZoom'),
                         'before':before,'after':after,'error':math.dist(before,after),
                         'pass':math.dist(before,after)<=1e-7,
                         'local':[local.x(),local.y()], 'pan':[s.viewer.property('panX'),s.viewer.property('panY')]})
        for i in range(4):
            if tool=='click':
                QTest.mouseClick(s.window,Qt.LeftButton,Qt.AltModifier,scene)
            else:
                wheel(s,scene,-120)
            s.settle()
        after = source_anchor(s,local)
        rows.append({'case':name+'-return','before':before,'after':after,
                     'error':math.dist(before,after),'pass':math.dist(before,after)<=1e-7})
    # Fit has no previous pan and is centered independently on each axis.
    invoke(s.viewer,'fitView')
    s.settle()
    f=s.item('imageFrame')
    fit={'center_error':[f.x()-(s.viewport.width()-f.width())/2,
                         f.y()-(s.viewport.height()-f.height())/2],
         'contains':f.width()<=s.viewport.width() and f.height()<=s.viewport.height()}
    scene,local=pointer(s,.35,.65)
    before=source_anchor(s,local)
    wheel(s,scene,120)
    s.settle()
    after=source_anchor(s,local)
    rows.append({'case':'fit-zoom','before':before,'after':after,
                 'error':math.dist(before,after),'pass':math.dist(before,after)<=1e-7})
    # Viewport and PreparedView must describe precisely the same source region.
    f=s.item('imageFrame')
    np.testing.assert_allclose(s.view.viewTransform,[f.x(),f.y(),s.viewer.property('displayScale')],atol=1e-9,rtol=0)
    return {'rows':rows,'fit':fit,'prepared_transform_matches':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths',nargs='+',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--baseline-ref')
    parser.add_argument('--model',type=Path)
    parser.add_argument('--reference-result',type=Path)
    parser.add_argument('--benchmark',action='store_true')
    parser.add_argument('--repeats',type=int,default=30)
    parser.add_argument('--no-quality',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QSG_RENDER_LOOP','basic')
    app=QApplication([])
    QQuickStyle.setStyle('Basic')
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'baseline_ref':args.baseline_ref,'environment':{'os':platform.platform(),
            'qt':qVersion(),'qpa':app.platformName(),'scale_factor':os.getenv('QT_SCALE_FACTOR')},
            'physical_mouse':'PENDING','frame_timing':'Qt submission, not physical present', 'files':[]}
    s=Session.__new__(Session)
    original_paint=PreparedView.paint
    try:
        with patch.object(PreparedView,'paint',lambda item,painter:s.paint(original_paint,item,painter)), \
             patch.object(DisplayPyramid,'region',s.timed('region',DisplayPyramid.region)), \
             patch.object(prepared_view,'render_samples',s.timed('conversion',prepared_view.render_samples)), \
             patch.object(imagecodecs,'jpeg8_decode',s.timed('jpeg_decode',imagecodecs.jpeg8_decode)):
            s.__init__(app,args.output,args.baseline_ref or False)
            s.window.setTitle('XRT-PERF-TD-03 automated benchmark')
            previous=None
            for path in args.paths:
                row={'file':path.name,'sha_before':digest(path)}
                report['files'].append(row)
                row['open_seconds']=s.open(path)
                if previous is not None:
                    assert previous.closed
                    assert s.view._display_cache is None or s.view._display_cache[0][0] is s.bridge.original_source.display_pyramid
                    row['previous_cache_closed']=True
                source=s.bridge.original_source
                m=source.metadata
                row['meta']={'width':m.width,'height':m.height,'pages':m.page_count,'dtype':m.dtype}
                report['environment'].update(dpr=s.window.devicePixelRatio(), ui_dpr=s.ui.property('displayPixelRatio'),
                    viewport=[s.viewport.width(),s.viewport.height()], graphics_api=str(s.window.rendererInterface().graphicsApi()))
                if args.model and m.format=='JPEG':
                    s.bridge.research.loadModel(str(args.model))
                    spin(app,lambda:not s.bridge.research.loading,120)
                    assert not s.bridge.research.error
                    assert s.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{'point_mode':'contrast_proposals'})
                    spin(app,lambda:s.bridge.analysis['state']!='RUNNING',180)
                    assert s.bridge.analysis['hasResult'],s.bridge.analysis
                    row['counts']=dict(Counter(p['type'] for p in s.bridge.research.rows))
                    assert row['counts']=={'BPD':245,'TED':1398,'TSD':1303}
                    if args.reference_result:
                        reference=json.loads(args.reference_result.read_text(encoding='utf8'))['predictions']
                        assert s.bridge.research.rows==reference
                        row['unchanged_predictions']=True
                if args.benchmark:
                    # Same TD-02 scale/filter/30 alternating QTest pan + zoom assignments.
                    row['benchmark']=s.case(4,'ALL' if s.bridge.research.rows else 'OFF',args.repeats)
                    s.ui.setProperty('activeTool','Pan')
                    scene,local=pointer(s,.35,.65)
                    rows=[]
                    for i in range(args.repeats):
                        before=source_anchor(s,local)
                        result=s.command(lambda d=120 if i%2==0 else -120, p=scene:wheel(s,p,d))
                        result['anchor_error']=math.dist(before,source_anchor(s,local))
                        rows.append(result)
                    row['cursor_wheel_benchmark']={'submission_ms':stats([r['swap_ms'] for r in rows]),
                        'anchor_max_error':max(r['anchor_error'] for r in rows)}
                row['pages']=[]
                for page in sorted({0,m.page_count//2,m.page_count-1}):
                    if source.page_index!=page:
                        zoom=s.ui.property('effectiveZoom')
                        pan=[s.viewer.property('panX'),s.viewer.property('panY')]
                        assert s.bridge.requestPage(page)
                        spin(app,lambda p=page:s.bridge.original_source.page_index==p and not s.bridge.stack_viewer.busy,120)
                        s.settle()
                        assert s.ui.property('effectiveZoom')==zoom
                        assert [s.viewer.property('panX'),s.viewer.property('panY')]==pan
                    page_row={'page':page,'anchors':anchor_cases(s)}
                    if not args.no_quality:
                        page_row['quality']=s.quality(f'page-{page}')
                        assert all(r['exact'] for r in page_row['quality'])
                    row['pages'].append(page_row)
                    if not args.baseline_ref:
                        assert all(r['pass'] for r in page_row['anchors']['rows'])
                    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
                if m.page_count>1:
                    for page in [m.page_count-1,m.page_count//2,0]:
                        s.bridge.requestPage(page)
                    spin(app,lambda:s.bridge.original_source.page_index==0 and not s.bridge.stack_viewer.busy,120)
                    row['latest_page_request']=True
                row['interaction']=s.interactions()
                if s.bridge.research.rows and args.reference_result:
                    assert s.bridge.research.rows==reference
                    row['predictions_after_interactions_unchanged']=True
                row['sha_after']=digest(path)
                assert row['sha_before']==row['sha_after']
                row['cache_bytes']=s.view._display_cache[5].sizeInBytes() if s.view._display_cache else 0
                assert row['cache_bytes']<=32*1024**2
                previous=s.bridge.original_source.display_pyramid
                print(json.dumps({'file':path.name,'max_anchor_error':max(r['error'] for p in row['pages'] for r in p['anchors']['rows']),
                    'sha_preserved':True}),flush=True)
            report['warnings']=s.warnings
            assert not s.warnings
    except Exception as exc:
        report['error']=repr(exc)
        raise
    finally:
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        s.close()


if __name__=='__main__':
    main()
