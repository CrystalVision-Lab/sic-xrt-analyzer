"""Separate opt-in GPU timestamp probe; no changes to product graphics defaults.

Qt supplies borrowed QRhi resources in a render-thread callback. The returned
GPU time belongs to an earlier completed frame, not the current input command.
No physical display timing or isolated upload timing is inferred from it.
"""
import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

import shiboken6
from benchmark_viewer import digest, spin
from benchmark_viewer_interaction import Session, stats
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QRhi, QRhiSwapChain
from PySide6.QtQml import QQmlAbstractUrlInterceptor, QQmlApplicationEngine
from PySide6.QtQuick import QSGRendererInterface
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from sic_xrt_analyzer.ui import prepared_view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jpeg',type=Path)
    parser.add_argument('--model',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('QSG_RENDER_LOOP','basic')
    app = QApplication([])
    QQuickStyle.setStyle('Basic')
    original_load = QQmlApplicationEngine.load
    ui = Path(prepared_view.__file__).parent
    main_qml = (ui/'Main.qml').read_text(encoding='utf8')
    assert 'visible: true; width: 1440' in main_qml
    hidden = args.output/'GPUProbeMain.qml'
    hidden.write_text('import "'+ui.as_uri()+'"\n'+main_qml.replace('visible: true; width: 1440','visible: false; width: 1440',1),encoding='utf8')
    # Observe JS draw-command recording separately from Qt CPU/GPU rendering.
    # This is a test copy, not a new product overlay renderer.
    viewer = (ui/'ImageViewer.qml').read_text(encoding='utf8')
    marker = 'id: analysisOverlay; objectName: "analysisOverlay"; anchors.fill: parent; z: 3'
    begin = viewer.index(marker)
    end = viewer.index('id: toolPreview;',begin)
    block = viewer[begin:end]
    block = block.replace(marker,marker+'\n                signal perfRecorded(real milliseconds, int count)',1)
    draw = 'var c = getContext("2d");'
    assert draw in block
    block = block.replace(draw,'var perfStart = Date.now(), perfCount = 0; '+draw,1)
    block = block.replace('if (!visible) return','if (!visible) { perfRecorded(Date.now()-perfStart,0); return }',1)
    block = block.replace('c.strokeStyle = p.low_score','perfCount++; c.strokeStyle = p.low_score',1)
    ending = '\n                }\n            }\n            Canvas {'
    assert ending in block
    block = block.replace(ending,'\n                    perfRecorded(Date.now()-perfStart,perfCount);'+ending,1)
    overlay_qml = args.output/'GPUProbeViewer.qml'
    overlay_qml.write_text('import "'+ui.as_uri()+'"\n'+viewer[:begin]+block+viewer[end:],encoding='utf8')
    class OverlayUrl(QQmlAbstractUrlInterceptor):
        def intercept(self,url,kind):
            if kind==QQmlAbstractUrlInterceptor.QmlFile and Path(url.toLocalFile())==ui/'ImageViewer.qml':
                return QUrl.fromLocalFile(str(overlay_qml.resolve()))
            return url
    interceptor = OverlayUrl()
    def load_hidden(engine, url):
        engine.addUrlInterceptor(interceptor)
        return original_load(engine,QUrl.fromLocalFile(str(hidden.resolve())))
    with patch.object(QQmlApplicationEngine,'load',load_hidden):
        s = Session(app,args.output)
    config = s.window.graphicsConfiguration()
    config.setTimestamps(True)
    s.window.setGraphicsConfiguration(config)
    samples, errors, overlay_samples = [], [], []
    s.overlay.perfRecorded.connect(lambda ms,count: overlay_samples.append((ms,count)))
    environment = {'timestamps_requested': True, 'graphics_api':str(s.window.rendererInterface().graphicsApi()),
                   'physical_input':'PENDING','isolated_upload_ms':'NOT MEASURED',
                   'gpu_usage_percent':'NOT MEASURED'}
    def observe():
        interface = s.window.rendererInterface()
        rhi_ptr = interface.getResource(s.window,QSGRendererInterface.RhiResource)
        swap_ptr = interface.getResource(s.window,QSGRendererInterface.RhiSwapchainResource)
        if rhi_ptr is None or swap_ptr is None:
            return
        try:
            rhi = shiboken6.wrapInstance(int(rhi_ptr),QRhi)
            swap = shiboken6.wrapInstance(int(swap_ptr),QRhiSwapChain)
            assert not shiboken6.ownedByPython(rhi) and not shiboken6.ownedByPython(swap)
            gpu = swap.currentFrameCommandBuffer().lastCompletedGpuTime()
            info = rhi.driverInfo()
            environment['adapter'] = bytes(info.deviceName).decode(errors='replace')
            environment['timestamps_supported'] = rhi.isFeatureSupported(QRhi.Feature.Timestamps)
            memory = rhi.statistics()
            samples.append({'previous_completed_gpu_ms':gpu*1000,'total_usage_bytes':memory.totalUsageBytes,
                            'used_bytes':memory.usedBytes,'unused_bytes':memory.unusedBytes})
        except (AttributeError,TypeError,ValueError,AssertionError) as exc:
            if repr(exc) not in errors:
                errors.append(repr(exc))
    s.window.afterRendering.connect(observe,Qt.DirectConnection)
    s.window.show()
    result = {'environment':environment,'cases':[]}
    try:
        result['sha_before'] = digest(args.jpeg)
        s.open(args.jpeg)
        s.bridge.research.loadModel(str(args.model))
        spin(app,lambda: not s.bridge.research.loading,120)
        assert not s.bridge.research.error
        assert s.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{'point_mode':'contrast_proposals'})
        spin(app,lambda: s.bridge.analysis['state']!='RUNNING',180)
        assert s.bridge.research.state['counts']=={'TSD':1303,'BPD':245,'TED':1398}
        for scale,kind in [(scale,kind) for scale in [None,4] for kind in ['OFF','ALL','BPD','TED','TSD']]:
            start,overlay_start=len(samples),len(overlay_samples)
            # This separate probe does not monkeypatch paint: frame completion is
            # supplied by actual QQuickWindow signals, not Session paint traces.
            s.ui.setProperty('analysisLayerVisible',kind!='OFF')
            s.bridge.research.setFilter('ALL' if kind=='OFF' else kind,False,'')
            s.set_zoom(scale)
            for i in range(35):
                count=len(s.frames)
                s.viewer.setProperty('panX',float(i*3))
                s.view.update(); s.window.update()
                spin(app,lambda count=count:len(s.frames)>count,5)
            measured=samples[start+5:]
            positive=[p['previous_completed_gpu_ms'] for p in measured if p['previous_completed_gpu_ms']>0]
            visible=[count for _,count in overlay_samples[overlay_start:]]
            result['cases'].append({'overlay':kind,'gpu_completed_frame_ms':stats(positive),
                'scale':scale or 'Fit','samples':len(measured),
                'overlay_js_record_ms':stats([ms for ms,_ in overlay_samples[overlay_start:]]),
                'visible_candidate_count':{'n':len(visible),'min':min(visible),'max':max(visible)} if visible else None,
                'qt_total_usage_bytes':max((p['total_usage_bytes'] for p in measured),default=0)})
        result['errors']=errors
        result['qml_warnings']=s.warnings
        result['zero_memory_counter_means']='NOT MEASURED (backend statistics unavailable), not zero GPU memory'
        result['sha_after'] = digest(args.jpeg)
        assert result['sha_before']==result['sha_after']
    finally:
        (args.output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        s.window.afterRendering.disconnect(observe)
        s.close()


if __name__=='__main__':
    main()
