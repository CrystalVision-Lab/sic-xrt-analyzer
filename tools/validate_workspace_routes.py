"""Opt-in Qt workspace routes, native lifecycle and independent-process replay.

Native HWND inspection is read-only. Selection is an accepted-payload injection,
not physical Explorer input. All mutable/missing sources here are generated.
"""
import argparse
import json
import os
import shutil
import time
from pathlib import Path
from threading import Thread

import numpy as np
import tifffile
from benchmark_viewer import digest, spin
from benchmark_viewer_interaction import Session
from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot, qVersion
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from validate_defect_result_ui import SyntheticAdapter, generated, invoke
from validate_project_workspace import capture, click, payload, wait


def accepted(s, name, path):
    picker=s.item(name)
    # Actual native acceptance closes first; keep that lifecycle in payload QA.
    invoke(picker,'close');QTest.qWait(50)
    picker.setProperty('selectedFile',QUrl.fromLocalFile(str(path.resolve())))
    picker.accepted.emit();wait(s)


def replay(s, project, report):
    sha=digest(project)
    invoke(s.item('projectOpenAction'),'trigger')
    accepted(s,'projectOpenFileDialog',project)
    c=s.bridge.projects
    runs=[r for r in c.project.analysis_runs if r.result_id]
    for run in runs:
        c.selectRun(run.run_id);wait(s)
        spin(s.app,lambda:s.bridge.research.pixels_available,180)
        assert s.bridge.pipeline.adapter is None and s.bridge.pipeline.result is None
        rows=payload(s)
        assert len(rows)==len([o for o in c.project.observations if o.run_id==run.run_id])
        s.bridge.research.selectCandidate(rows[0][0])
        spin(s.app,lambda:bool(s.bridge.research.thumbnail_source),30)
        capture(s,'fresh-process-'+run.scope.value)
    assert digest(project)==sha
    report.update(independent_process_replay=True,model_adapter=None,model_runs=0,
                  project_uuid=c.project.project_id,runs=len(runs),manifest_unchanged=True)


class CancelNative(QObject):
    requested=Signal(QObject)

    @Slot(QObject)
    def reject(self, picker):
        invoke(picker,'reject')


def routes(s, output, cycles, report):
    c=s.bridge.projects
    invoke(s.item('projectNewAction'),'trigger');capture(s,'new-project')
    s.item('projectNameInput').setProperty('text','SYNTHETIC Two Image Study')
    main=output/'study.json';empty=output/'empty.json'
    s.item('projectPathInput').setProperty('text',str(main))
    click(s,'projectCommitSave');wait(s)
    assert not c.dirty and not c.project.image_sources
    c.create('SYNTHETIC Empty Study',str(empty));wait(s)
    c.open(str(main));wait(s)
    image,_=generated(output)
    s.bridge.pipeline.adapter=SyntheticAdapter()
    s.open(image);wait(s)
    assert s.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{})
    spin(s.app,lambda:s.bridge.analysis['hasResult'],60);wait(s)
    c.save('','');wait(s)
    run=c.project.analysis_runs[0].run_id
    first=c.project.image_sources[0].source_id
    second=output/'SYNTHETIC_REFERENCE.jpg';shutil.copyfile(image,second)
    s.open(second);wait(s)
    c.setRole(first,'BEFORE_ANNEALING');c.setRole(c.project.image_sources[-1].source_id,'AFTER_ANNEALING')
    c.save('','');wait(s)
    invoke(s.item('projectWorkspaceAction'),'trigger');capture(s,'image-run-list')
    invoke(s.item('projectWorkspaceDialog'),'close')
    invoke(s.window,'openRecentManager');capture(s,'recent-projects')
    invoke(s.item('recentProjectManager'),'close')
    c.rename('SYNTHETIC Unsaved Study')
    invoke(s.item('projectOpenAction'),'trigger');capture(s,'dirty-confirmation')
    click(s,'projectDirtyCancel');assert c.dirty
    invoke(s.item('projectSaveAction'),'trigger');wait(s)
    invoke(s.item('projectSaveAsAction'),'trigger');capture(s,'save-as')
    accepted(s,'projectSaveFileDialog',output/'copy.json')
    click(s,'projectCommitSave');wait(s)
    assert c.path==str((output/'copy.json').resolve())
    # Close/reopen native dialogs using production managed native route.
    native=[]
    coordinator=CancelNative()
    coordinator.requested.connect(coordinator.reject,Qt.QueuedConnection)
    if os.name=='nt':
        from dialog_lifecycle_probe import native_windows
        for number in range(cycles):
            for name in ('projectOpenFileDialog','projectSaveFileDialog','projectRelinkFileDialog'):
                picker=s.item(name);state={}
                def observe(p=picker, record=state):
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline:
                        windows=native_windows()
                        if windows:
                            record['hwnd']=windows
                            coordinator.requested.emit(p)
                            return
                        time.sleep(.01)
                    record['error']='Native window not observed'
                    coordinator.requested.emit(p)
                worker=Thread(target=observe);worker.start()
                invoke(picker,'open');s.app.processEvents()
                worker.join(12)
                assert not worker.is_alive()
                spin(s.app,lambda p=picker:not p.property('visible'),10)
                state['managed']=bool(picker.property('managedNative'))
                assert 'error' not in state,state
                native.append({'cycle':number+1,'dialog':name,**state})
    report.update(native_cycles=cycles,native_rejects=native)
    (output/'native-observations.json').write_text(json.dumps(native,indent=2),encoding='utf8')
    # Repeated normal accepted payload routes, not physical native selection.
    for number in range(cycles):
        for target in (empty,main):
            invoke(s.item('projectOpenAction'),'trigger')
            accepted(s,'projectOpenFileDialog',target)
            assert c.path==str(target.resolve())
    c.selectRun(run);wait(s);spin(s.app,lambda:s.bridge.research.pixels_available,30)
    capture(s,'saved-candidate')
    # Only this tool's generated fixture moves; actual XRT originals never do.
    missing=output/'SYNTHETIC_RELOCATED.jpg';image.rename(missing)
    c.selectRun(run);wait(s)
    assert not s.bridge.research.pixels_available and s.bridge.research.rows
    s.bridge.research.selectCandidate(s.bridge.research.rows[0]['id'])
    invoke(s.item('projectWorkspaceAction'),'trigger');capture(s,'missing-original')
    invoke(s.item('projectWorkspaceDialog'),'close')
    c.relink(first,str(missing));wait(s);c.save('','');wait(s)
    tiff=output/'SYNTHETIC_stack.tif'
    tifffile.imwrite(tiff,np.arange(3*64*64,dtype=np.uint16).reshape(3,64,64),imagej=True)
    s.open(tiff);wait(s)
    assert not s.ui.property('canAnalyze') and s.bridge.pipeline.result is None
    c.save('','');wait(s)
    invoke(s.item('projectWorkspaceAction'),'trigger')
    QTest.qWait(150);capture(s,'tiff-project');invoke(s.item('projectWorkspaceDialog'),'close')
    malformed=output/'malformed.json';malformed.write_text('{}',encoding='utf8')
    old=c.project;c.open(str(malformed));spin(s.app,lambda:not c.busy,30)
    assert c.error and c.project==old
    capture(s,'load-error');invoke(s.item('projectOperationDialog'),'close')
    c.open(str(main));wait(s)
    assert not c.dirty
    # Test window-close and application-exit request routes separately.
    c.rename('SYNTHETIC Dirty Exit');s.window.close();QTest.qWait(50)
    assert s.item('projectDirtyDialog').property('visible') and s.window.isVisible()
    click(s,'projectDirtyCancel');c.save('','');wait(s)
    report.update(native_cycles=cycles,native_rejects=native,
                  accepted_project_switches=cycles*2,source_roles_explicit=True,
                  missing_metadata=True,hash_relink=True,tiff_model_runs=0,
                  save_as_same_project=True,dirty_close_cancel=True,
                  originals_policy='generated sources only')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--project',type=Path,help='Read-only replay in a fresh process')
    parser.add_argument('--cycles',type=int,default=10)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    app=QApplication([]);QQuickStyle.setStyle('Basic');s=Session(app,output)
    s.window.setTitle('XRT-RESULT-TD-04 workspace routes QA')
    s.window.resize(1100,700);s.window.raise_();s.window.requestActivate()
    report={'qt':qVersion(),'platform':os.name,'manual_mouse_acceptance':'PENDING'}
    try:
        if args.project:replay(s,args.project.resolve(),report)
        else:routes(s,output,args.cycles,report)
        assert not s.warnings,s.warnings
        report.update(status='PASS',qml_warnings=s.warnings)
    finally:
        s.close();(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='native_rejects'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
