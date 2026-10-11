"""Opt-in actual Qt project save/restart/history QA; no physical mouse acceptance.

Requires explicit originals/model or --synthetic. Artifacts and private captures
stay under a new output folder. Never trains, modifies or uploads originals.
"""
import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from benchmark_viewer import digest, spin
from benchmark_viewer_interaction import Session
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt, QUrl
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from validate_defect_result_ui import SyntheticAdapter, generated, invoke

from sic_xrt_analyzer.ui.prepared_view import PreparedView


def wait(s):
    spin(s.app,lambda:not s.bridge.projects.busy,180)
    assert not s.bridge.projects.error,s.bridge.projects.error


def click(s, name):
    s.window.grabWindow()
    obj=s.item(name)
    assert obj.isVisible() and obj.property('enabled'),name
    point=obj.mapToScene(QPointF(obj.width()/2,obj.height()/2))
    QTest.mouseClick(s.window,Qt.LeftButton,Qt.NoModifier,QPoint(round(point.x()),round(point.y())))
    QTest.qWait(50)


def capture(s, name):
    QTest.qWait(70)
    assert s.window.grabWindow().save(str(s.output/(name+'.png')))


def exports(s, path):
    assert s.bridge.research.exportResult(str(path)),s.bridge.research.error
    return {p.name:p.read_bytes() for p in Path(s.bridge.research.export_path).iterdir()}


def payload(s):
    return [(r['id'],r['point_id'],r['x'],r['y'],r['type'],r['scores'],r['score'],r['low_score']) for r in s.bridge.research.rows]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic',action='store_true')
    parser.add_argument('--image',type=Path)
    parser.add_argument('--model',type=Path)
    parser.add_argument('--experiment',type=Path)
    parser.add_argument('--tiff',type=Path,action='append',default=[])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.synthetic == bool(args.image):parser.error('Use either --synthetic or explicit --image/--model')
    if not args.synthetic and not args.model:parser.error('Actual RGB validation needs approved model')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    app=QApplication([]);QQuickStyle.setStyle('Basic')
    holder={};paint=PreparedView.paint
    report={'synthetic':args.synthetic,'manual_mouse_acceptance':'PENDING','scopes':[],'tiff':[]}
    before={str(p.resolve()):digest(p) for p in ([args.image,args.model/'model.onnx',args.model/'manifest.json'] if not args.synthetic else [])+args.tiff}
    s=None
    try:
        with patch.object(PreparedView,'paint',lambda item,painter:holder['s'].paint(paint,item,painter)):
            def session(directory):
                directory.mkdir(parents=True,exist_ok=True)
                obj=Session.__new__(Session);holder['s']=obj
                Session.__init__(obj,app,directory)
                obj.window.setTitle('XRT-RESULT-TD-04 automated workspace QA')
                obj.window.raise_();obj.window.requestActivate()
                return obj
            s=session(output/'first')
            if args.synthetic:
                image,experiment=generated(output)
                s.bridge.pipeline.adapter=SyntheticAdapter()
            else:
                image=args.image.resolve();experiment=args.experiment
                s.bridge.research.loadModel(str(args.model.resolve()))
                spin(app,lambda:not s.bridge.research.loading,120)
                assert not s.bridge.research.error,s.bridge.research.error
            source_sha=digest(image)
            s.open(image)
            c=s.bridge.projects
            saved_payloads={};saved_exports={}
            for scope,roi in [('FULL_IMAGE',(0,0,0,0)),*([('ROI',(1003,1011,1495,1495))] if not args.synthetic else [])]:
                assert s.bridge.requestAnalysis(scope,*roi,{})
                spin(app,lambda:s.bridge.analysis['hasResult'],300);wait(s)
                result=s.bridge.pipeline.result
                saved_payloads[result.analysis_id]=payload(s)
                saved_exports[result.analysis_id]=exports(s,output/('export-'+scope))
                counts=dict(Counter(r['type'] for r in s.bridge.research.rows))
                expected={'BPD':245,'TED':1398,'TSD':1303} if scope=='FULL_IMAGE' else {'BPD':3,'TED':779,'TSD':9}
                assert counts==expected,counts
                report['scopes'].append({'scope':scope,'total':len(s.bridge.research.rows),'counts':counts,'result_id':result.analysis_id})
            s.bridge.research.selectCandidate(s.bridge.research.rows[0]['id'])
            spin(app,lambda:bool(s.bridge.research.thumbnail_source),30)
            invoke(s.item('projectSaveAction'),'trigger');capture(s,'save-dialog')
            s.item('projectNameInput').setProperty('text','SYNTHETIC Workspace QA' if args.synthetic else 'Actual RGB Workspace QA')
            project_file=output/'workspace.json'
            s.item('projectPathInput').setProperty('text',str(project_file))
            click(s,'projectCommitSave');wait(s)
            assert not c.dirty
            if experiment:
                e=s.bridge.experiments;e.load(str(experiment.resolve()));spin(app,lambda:not e.loading,120)
                assert not e.error,e.error
                e.select(next(r['id'] for r in e.rows if r['kind']=='BRANCHED_GRAPH'))
                spin(app,lambda:bool(e.preview),30)
                c.importCurrentExperiment();wait(s)
                c.save('','');wait(s)
                report['structures']=len(c.project.defect_instances)
            for number,tiff in enumerate(args.tiff,1):
                s.open(tiff.resolve());wait(s)
                if not any(x.source_reference==str(tiff.resolve()) for x in c.project.image_sources):c.registerCurrent();wait(s)
                assert s.bridge.pipeline.result is None
                assert not s.ui.property('canAnalyze')
                assert not s.item('importExperiment').isVisible()
                source=c.project.image_sources[-1]
                assert source.page_count==s.bridge.original_source.metadata.page_count
                assert source.calibration.spatial_axis_type=='UNKNOWN'
                report['tiff'].append({'file':tiff.name,'pages':source.page_count,'dtype':source.dtype,'model_runs':0})
                capture(s,f'tiff-{number}')
            # Restore selected JPG geometry before saving view preferences.
            if experiment:
                record=next(x for x in c.project.image_sources if x.source_reference==str(image))
                c.selectSource(record.source_id,'');wait(s)
                spin(app,lambda:bool(s.bridge.experiments.rows),180)
                s.bridge.experiments.select(next(r['id'] for r in s.bridge.experiments.rows if r['kind']=='BRANCHED_GRAPH'))
                spin(app,lambda:bool(s.bridge.experiments.preview),30)
            c.save('','');wait(s)
            original_project=c.project
            c.save(str(output/'copy'/'workspace.json'),'');wait(s)
            assert c.project==original_project
            s.close();s=None
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
            (output/'restart').mkdir(exist_ok=True)
            shutil.copyfile(output/'first/prefs.ini',output/'restart/prefs.ini')
            s=session(output/'restart')
            # No adapter is required to view saved results after a fresh engine.
            s.bridge.research.loader.invalidate()
            s.bridge.research.loading=False
            s.bridge.pipeline.adapter=None
            invoke(s.item('projectOpenAction'),'trigger')
            picker=s.item('projectOpenFileDialog');picker.setProperty('selectedFile',QUrl.fromLocalFile(str(project_file)));invoke(picker,'close');picker.accepted.emit()
            wait(s);c=s.bridge.projects
            assert c.project.project_id==original_project.project_id
            c.restoreView();wait(s)
            if experiment:
                spin(app,lambda:bool(s.bridge.experiments.rows),180)
                # View settings are local and separate from the project manifest.
                selected=original_project.defect_instances[0]
                s.bridge.experiments.select(selected.instance_id)
                spin(app,lambda:bool(s.bridge.experiments.preview),30)
            for size in [(1100,700),(1440,900),(1920,1080)]:
                s.window.resize(*size)
                invoke(s.item('projectWorkspaceAction'),'trigger');capture(s,f'{size[0]}-workspace')
                invoke(s.item('projectWorkspaceDialog'),'close')
                for run in c.project.analysis_runs:
                    if run.result_id not in saved_payloads:continue
                    c.selectRun(run.run_id);wait(s)
                    spin(app,lambda:s.bridge.research.pixels_available,180)
                    assert s.bridge.pipeline.result is None and not s.bridge.analysis['hasResult']
                    assert payload(s)==saved_payloads[run.result_id]
                    assert exports(s,output/(f'restored-{size[0]}-'+run.scope.value))==saved_exports[run.result_id]
                    s.bridge.research.selectCandidate(s.bridge.research.rows[0]['id'])
                    spin(app,lambda:bool(s.bridge.research.thumbnail_source),30)
                    capture(s,f'{size[0]}-saved-{run.scope.value}')
            report['saved_runs_equal']=True;report['legacy_export_bytes_equal']=True
            report['pipeline_inference_during_replay']=0
            report['raw_source_sha_preserved']=digest(image)==source_sha
            assert report['raw_source_sha_preserved']
            assert not s.warnings,s.warnings
            report['qml_warnings']=s.warnings
            assert all(digest(Path(path))==sha for path,sha in before.items())
            report['originals_and_model_sha_preserved']=True
            report['status']='PASS'
    finally:
        if s:s.close()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
