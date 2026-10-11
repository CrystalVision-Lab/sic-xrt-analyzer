"""Actual Qt workspace persistence and saved provider, with immutable fixture science."""
import hashlib
import json
import shutil
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QUrl
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_defect_result import bundle
from test_result_ux import DistributedCandidates
from test_ui_analysis_contract import invoke

from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.workspace import import_experiment

pytest_plugins=('test_toolbar',)


def jpg(w, tmp_path, name='synthetic-before.jpg'):
    path=tmp_path/name
    image=np.full((512,512,3),120,np.uint8)
    image[250:258,250:258]=255
    Image.fromarray(image).save(path,quality=100,subsampling=0)
    w.bridge.pipeline.adapter=DistributedCandidates()
    w.open(path)
    return path


def analyze(w):
    assert w.bridge.requestAnalysis('FULL_IMAGE',0,0,0,0,{})
    spin(w.app,lambda:w.bridge.analysis['hasResult'])
    spin(w.app,lambda:not w.bridge.projects.busy)
    assert not w.bridge.projects.error,w.bridge.projects.error
    return w.bridge.pipeline.result


def wait(w):
    spin(w.app,lambda:not w.bridge.projects.busy,30)


def save_ui(w, path):
    invoke(w.item('projectSaveAction'),'trigger')
    w.window.grabWindow()
    assert w.item('projectSaveDialog').property('visible')
    w.item('projectNameInput').setProperty('text','Synthetic Wafer Study')
    w.item('projectPathInput').setProperty('text',str(path))
    w.click('projectCommitSave')
    wait(w)
    assert not w.bridge.projects.error,w.bridge.projects.error


def test_gui_save_load_saved_run_without_inference_and_exact_export(workbench,tmp_path):
    w=workbench
    original=jpg(w,tmp_path)
    sha=hashlib.sha256(original.read_bytes()).hexdigest()
    live=analyze(w)
    c=w.bridge.projects
    assert c.dirty and len(c.project.analysis_runs)==1
    w.bridge.research.exportResult(str(tmp_path/'live-export'))
    before={p.name:p.read_bytes() for p in Path(w.bridge.research.export_path).iterdir()}
    save_ui(w,tmp_path/'study.json')
    assert not c.dirty and c.project.image_sources[0].content_hash
    c.close();w.bridge.clearImage()
    c.open(str(tmp_path/'study.json'));wait(w)
    assert len(c.project.analysis_runs)==1
    # Never make a fake pipeline completion or invoke an adapter on history open.
    w.bridge.pipeline.adapter=None
    c.selectRun(c.project.analysis_runs[0].run_id);wait(w)
    spin(w.app,lambda:w.bridge.research.saved is not None and w.bridge.research.pixels_available)
    assert w.bridge.pipeline.result is None and not w.bridge.analysis['hasResult']
    r=w.bridge.research
    assert r.state['counts']=={'BPD':245,'TED':1398,'TSD':1303}
    assert r.state['runInfo']['origin']=='저장된 이력'
    r.selectCandidate(r.rows[0]['id'])
    spin(w.app,lambda:bool(r.thumbnail_source))
    assert r.state['selection']['run_id']==c.selected_run
    assert r.state['selected']['scores']==[.6605,.3365,.003]
    r.exportResult(str(tmp_path/'saved-export'))
    after={p.name:p.read_bytes() for p in Path(r.export_path).iterdir()}
    assert before==after
    assert live.analysis_id==r.saved.run.result_id
    assert hashlib.sha256(original.read_bytes()).hexdigest()==sha


def test_multiple_runs_roles_and_source_history(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    jpg(w,tmp_path);a=analyze(w);b=analyze(w)
    assert a.analysis_id!=b.analysis_id and len(c.project.analysis_runs)==2
    c.captureCurrent();wait(w)
    assert len(c.project.analysis_runs)==2
    first=c.project.image_sources[0]
    c.setRole(first.source_id,'BEFORE_ANNEALING')
    jpg(w,tmp_path,'synthetic-after.jpg');wait(w);analyze(w)
    assert len(c.project.image_sources)==2 and len(c.project.analysis_runs)==3
    second=c.project.image_sources[-1]
    assert second.role.value=='UNKNOWN'  # Names never determine acquisition roles.
    c.setRole(second.source_id,'AFTER_ANNEALING')
    c.save(str(tmp_path/'multi.json'),'Study');wait(w)
    snapshot=c.project
    c.open(str(tmp_path/'multi.json'));wait(w)
    assert c.project==snapshot
    assert [s.role.value for s in c.project.image_sources]==['BEFORE_ANNEALING','AFTER_ANNEALING']


@pytest.mark.parametrize('fault',['json','schema','missing'])
def test_failed_open_preserves_workspace_and_selection(workbench,tmp_path,fault):
    w=workbench;c=w.bridge.projects
    jpg(w,tmp_path);analyze(w)
    c.save(str(tmp_path/'good.json'),'Study');wait(w)
    snapshot,path=c.project,c.path
    bad=tmp_path/'bad.json'
    if fault=='json':bad.write_text('{broken',encoding='utf-8')
    if fault=='schema':
        payload=json.loads(Path(path).read_text(encoding='utf-8'));payload['schema_version']='999';bad.write_text(json.dumps(payload),encoding='utf-8')
    c.open(str(bad));wait(w)
    assert c.error and c.project==snapshot and c.path==path


@pytest.mark.parametrize('failure',['disk','revision','different-project','write'])
def test_failed_save_keeps_dirty_and_disk_history(workbench,tmp_path,monkeypatch,failure):
    w=workbench;c=w.bridge.projects
    jpg(w,tmp_path);analyze(w)
    path=tmp_path/'saved.json';c.save(str(path),'Study');wait(w)
    c.rename('Changed','');snapshot=c.project
    if failure=='revision':
        external=ProjectStore().load(path);ProjectStore().save(path,external.evolve(project_name='External'),expected_revision=external.revision)
    if failure=='different-project':
        other=tmp_path/'other.json';ProjectStore().save(other,AnalysisProject('Other'));path=other
    before=path.read_bytes()
    if failure in ('disk','write'):
        def fail(*args,**kwargs):raise OSError(28 if failure=='disk' else 13,'Synthetic storage failure')
        monkeypatch.setattr(ProjectStore,'save',fail)
    c.save(str(path),'');wait(w)
    assert c.error and c.dirty and c.project==snapshot
    assert path.read_bytes()==before


def test_save_as_keeps_identity_and_recent_paths(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    jpg(w,tmp_path);analyze(w)
    c.save(str(tmp_path/'one.json'),'Study');wait(w)
    snapshot=c.project
    c.save(str(tmp_path/'folder'/'two.json'),'');wait(w)
    assert c.project==snapshot and c.project.project_id==snapshot.project_id
    assert ProjectStore().load(tmp_path/'one.json')==ProjectStore().load(tmp_path/'folder'/'two.json')
    assert len(c.recent)==2
    c.removeRecent(str(tmp_path/'one.json'))
    assert len(c.recent)==1


def test_missing_source_metadata_and_safe_hash_relink(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    original=jpg(w,tmp_path);analyze(w)
    path=tmp_path/'project.json';c.save(str(path),'Study');wait(w)
    record=c.project.image_sources[0]
    moved=tmp_path/'moved.jpg';shutil.move(original,moved)
    c.open(str(path));wait(w)
    assert c.availability[record.source_id].status=='MISSING'
    w.bridge.pipeline.adapter=None
    c.selectRun(c.project.analysis_runs[0].run_id);wait(w)
    r=w.bridge.research
    assert r.saved is not None and len(r.rows)==2946 and not r.pixels_available
    assert r.state['points']==[]
    r.selectCandidate(r.rows[0]['id'])
    assert r.state['selected'] and not r.thumbnail_source
    bad=tmp_path/'wrong.jpg';Image.fromarray(np.zeros((512,512,3),np.uint8)).save(bad)
    snapshot=c.project;c.relink(record.source_id,str(bad));wait(w)
    assert c.error and c.project==snapshot
    c.relink(record.source_id,str(moved));wait(w)
    assert not c.error and c.dirty
    c.selectRun(c.project.analysis_runs[0].run_id);wait(w)
    spin(w.app,lambda:r.pixels_available)
    assert w.bridge.pipeline.result is None


def test_hash_unavailable_never_trusts_same_filename(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    original=jpg(w,tmp_path);analyze(w)
    source=c.project.image_sources[0]
    c.relink(source.source_id,str(original));wait(w)
    assert c.error and not source.content_hash
    c.verifySource(source.source_id);wait(w)
    assert not c.error and c.project.image_sources[0].content_hash


def test_dirty_guard_cancel_preserves_state_and_roi_order(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    jpg(w,tmp_path);analyze(w)
    snapshot=c.project
    invoke(w.item('projectNewAction'),'trigger')
    w.window.grabWindow()
    assert w.item('projectDirtyDialog').property('visible')
    w.click('projectDirtyCancel')
    assert c.project==snapshot and c.dirty
    w.state.setProperty('zoom',4.)
    w.bridge.research.setFilter('BPD',False,'')
    assert c.project==snapshot
    w.window.setProperty('allowQuit',False)
    w.window.close()
    assert w.window.isVisible() and w.item('projectDirtyDialog').property('visible')
    w.click('projectDirtyCancel')


def test_tiff_register_only_no_bpd_or_model(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    before=w.path.read_bytes()
    c.create('TIFF sources',str(tmp_path/'tiff.json'));wait(w)
    c.registerCurrent();wait(w)
    assert len(c.project.image_sources)==1 and not c.project.analysis_runs
    assert c.project.image_sources[0].page_count==3
    assert c.project.image_sources[0].calibration.spatial_axis_type=='UNKNOWN'
    assert not w.state.property('inputCompatible')
    c.selectSource(c.project.image_sources[0].source_id,'');wait(w)
    spin(w.app,lambda:not w.state.property('loading'))
    assert not w.item('importExperiment').isVisible()
    assert w.bridge.pipeline.result is None
    assert w.path.read_bytes()==before


def test_experiment_import_namespace_assets_save_as_and_restore(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    source,folder=bundle(tmp_path)
    w.open(source.path)
    e=w.bridge.experiments;e.load(str(folder));spin(w.app,lambda:not e.loading)
    assert not e.error
    c.importCurrentExperiment();wait(w)
    assert not c.error,c.error
    snapshot=c.project
    assert snapshot.project_id!=e.project.project_id and len(snapshot.defect_instances)==1
    c.importCurrentExperiment();wait(w)
    assert c.project is snapshot
    c.save(str(tmp_path/'study'/'p.json'),'Study');wait(w)
    assert not c.error,c.error
    instance=c.project.defect_instances[0];geometry=next(g for g in c.project.geometries if g.geometry_id==instance.geometry_id)
    c.save(str(tmp_path/'copy'/'p.json'),'');wait(w)
    assert not c.error,c.error
    assert c.project.defect_instances[0].instance_id==instance.instance_id
    from sic_xrt_analyzer.results.workspace import dependency_rows
    rows,errors=dependency_rows(c.path,c.project,instance.source_id,geometry.page_index)
    assert not errors and len(rows)==1 and len(rows[0]['paths'])==3
    assert rows[0]['id']==instance.instance_id
    assert rows[0]['mask']['path'].startswith(str(tmp_path/'copy'))
    assert snapshot.defect_instances[0].assessment.ground_truth_eligible is False


def test_cancel_late_open_cannot_replace_active_project(workbench,tmp_path,monkeypatch):
    w=workbench;c=w.bridge.projects
    c.create('Old',str(tmp_path/'old.json'));wait(w)
    ProjectStore().save(tmp_path/'new.json',AnalysisProject('New'))
    old=c.project;entered,release=Event(),Event()
    original=ProjectStore.load
    def delayed(store,path):
        entered.set();assert release.wait(10);return original(store,path)
    monkeypatch.setattr(ProjectStore,'load',delayed)
    c.open(str(tmp_path/'new.json'));spin(w.app,entered.is_set)
    c.cancel();release.set();QTest.qWait(100)
    assert c.project is old and not c.busy


@pytest.mark.parametrize('size',[(1100,700),(1440,900),(1920,1080)])
def test_real_gui_project_open_and_run_click(workbench,tmp_path,size):
    w=workbench;c=w.bridge.projects
    jpg(w,tmp_path);analyze(w)
    path=tmp_path/'gui.json';c.save(str(path),'GUI replay');wait(w)
    run=c.project.analysis_runs[0]
    c.close();invoke(w.window,'closeImage')
    w.bridge.pipeline.adapter=None
    w.window.resize(*size)
    invoke(w.item('projectOpenAction'),'trigger')
    dialog=w.item('projectOpenFileDialog')
    dialog.setProperty('selectedFile',QUrl.fromLocalFile(str(path)))
    invoke(dialog,'close')
    dialog.accepted.emit();wait(w)
    invoke(w.item('projectWorkspaceAction'),'trigger')
    w.window.grabWindow()
    w.click('projectRun0')
    spin(w.app,lambda:w.bridge.research.pixels_available)
    QTest.qWait(60);w.window.grabWindow()
    assert w.item('resultExplorer').isVisible()
    assert w.item('resultOrigin').property('text').startswith('저장된 이력')
    assert c.selected_run==run.run_id and w.bridge.pipeline.result is None
    w.click('nextCandidate')
    spin(w.app,lambda:bool(w.bridge.research.thumbnail_source))
    assert w.item('analysisOverlay').isVisible()
    assert w.item('candidateThumbnail').property('source').toString()


@pytest.mark.parametrize('name',['','   ','x'*201])
def test_invalid_new_project_keeps_existing_state(workbench,tmp_path,name):
    w=workbench;c=w.bridge.projects
    c.create('Existing',str(tmp_path/'existing.json'));wait(w)
    old=c.project
    c.create(name,str(tmp_path/'invalid.json'))
    assert c.error and c.project is old and not (tmp_path/'invalid.json').exists()


def test_saved_geometry_project_reload_and_selection(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    source,folder=bundle(tmp_path)
    w.open(source.path)
    e=w.bridge.experiments;e.load(str(folder));spin(w.app,lambda:not e.loading)
    e.select(e.rows[0]['id']);spin(w.app,lambda:bool(e.preview))
    c.importCurrentExperiment();wait(w)
    path=tmp_path/'persist/p.json';c.save(str(path),'Geometry');wait(w)
    mapped_id=c.project.defect_instances[0].instance_id
    assert c.last_view['selected_id']==mapped_id
    c.close();invoke(w.window,'closeImage')
    w.bridge.pipeline.adapter=None
    c.open(str(path));wait(w)
    c.restoreView();wait(w)
    spin(w.app,lambda:bool(e.rows) and bool(e.preview))
    assert e.selected_id==mapped_id and len(e.rows[0]['paths'])==3
    w.state.setProperty('maskMode','fill')
    spin(w.app,lambda:w.item('geometryOverlay').stats['maskCount']>0)
    assert w.bridge.pipeline.result is None


def test_missing_asset_metadata_and_corrupt_asset_rejection(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    source,folder=bundle(tmp_path);w.open(source.path)
    e=w.bridge.experiments;e.load(str(folder));spin(w.app,lambda:not e.loading)
    c.importCurrentExperiment();wait(w)
    path=tmp_path/'persist/p.json';c.save(str(path),'Geometry');wait(w)
    masks=[g for g in c.project.geometries if g.mask_reference]
    mask=ProjectStore().resolve_asset(path,masks[0].mask_reference)
    content=mask.read_bytes();mask.unlink()
    c.open(str(path));wait(w)
    assert not c.error and c.project.defect_instances and any('MISSING' in s for s in c.asset_status.values())
    snapshot=c.project;mask.write_bytes(b'corrupt')
    c.open(str(path));wait(w)
    assert c.error and c.project is snapshot
    mask.write_bytes(content)


def test_cancel_hash_rejects_old_progress_and_publication(workbench,tmp_path,monkeypatch):
    w=workbench;c=w.bridge.projects
    jpg(w,tmp_path);analyze(w)
    record=c.project.image_sources[0];old=c.project
    from sic_xrt_analyzer.results import sources
    original=sources._hash_snapshot
    entered,release=Event(),Event()
    def delayed(path,**kwargs):
        entered.set();assert release.wait(10)
        return original(path,**kwargs)
    monkeypatch.setattr(sources,'_hash_snapshot',delayed)
    c.verifySource(record.source_id);spin(w.app,entered.is_set)
    c.cancel();release.set();QTest.qWait(100)
    assert c.project is old and not c.busy and not c.project.image_sources[0].content_hash


def test_same_grouping_run_and_review_snapshot_are_not_duplicated(workbench,tmp_path):
    w=workbench;c=w.bridge.projects
    image=np.full((512,512,3),120,np.uint8)
    from sic_xrt_analyzer.analysis.bpd_samples import synthetic_sample
    image[100:260,100:260]=synthetic_sample('y',rgb=True)
    path=tmp_path/'synthetic-y.jpg';Image.fromarray(image).save(path,quality=100,subsampling=0)
    w.bridge.pipeline.adapter=DistributedCandidates();w.open(path);analyze(w)
    from test_bpd_structure import settings

    from sic_xrt_analyzer.analysis.bpd_structure import detect_structures
    from sic_xrt_analyzer.analysis.contracts import Region
    from sic_xrt_analyzer.results.bpd_experiment import (
        attach_experiment,
        comparison_image,
        save_experiment_bundle,
    )
    from sic_xrt_analyzer.results.contracts import (
        ReviewEvent,
        ReviewStatus,
        ReviewTarget,
    )
    from sic_xrt_analyzer.results.reviews import ReviewRepository, prediction_snapshot
    project=c.project;observation=project.observations[0]
    prediction,run_id=prediction_snapshot(project,ReviewTarget.OBSERVATION,observation.observation_id)
    from sic_xrt_analyzer.analysis.contracts import utc_now
    event=ReviewEvent('synthetic-review',ReviewTarget.OBSERVATION,observation.observation_id,'synthetic-qa',ReviewStatus.UNCERTAIN,prediction,utc_now(),1,source_run_id=run_id)
    project=ReviewRepository().append(project,event)
    experiment=detect_structures(w.bridge.original_source,Region(100,100,160,160),settings())
    attached=attach_experiment(project,experiment,source_id=project.image_sources[0].source_id,run_id=run_id)
    folder=tmp_path/'grouped';save_experiment_bundle(folder,attached,comparison_image(experiment,project,attached))
    imported,dependency=import_experiment(c.project,attached.project,attached.manifest,folder)
    assert len(imported.analysis_runs)==1 and len(imported.observations)==2946
    assert len(imported.review_events)==1 and imported.review_events[0].review_status==ReviewStatus.UNCERTAIN
    assert dependency and imported.defect_instances
