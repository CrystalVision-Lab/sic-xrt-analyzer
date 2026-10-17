"""Immutable analysis workspace, explicit save/load/history; never starts inference."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
from threading import Event

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from sic_xrt_analyzer.analysis.contracts import AnalysisState
from sic_xrt_analyzer.results import AnalysisProject, ProjectStore
from sic_xrt_analyzer.results.contracts import ImageRole
from sic_xrt_analyzer.results.sources import (
    SourceAvailability,
    inspect_source,
    relink_source,
    verify_content_hash,
)
from sic_xrt_analyzer.results.workspace import (
    SavedResultPresentation,
    add_source,
    capture_live,
    dependency_rows,
    import_experiment,
    inspect_dependencies,
    publish_dependencies,
)

from .latest_reader import LatestReader
from .research_controller import local_path


class ProjectController(QObject):
    changed = Signal()
    sourceRequested = Signal(str)
    resultRequested = Signal()
    operationFinished = Signal(str, bool)
    progress = Signal(int, object, object)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.project = self.saved_snapshot = None
        self.path = self.error = self.message = self.job = ''
        self.busy = self.dirty = self.read_only = False
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.callback = None
        self.token = Event()
        self.epoch = 0
        self.done = self.total = 0
        self.progress.connect(self._progress)
        self.availability = {}
        self.dependencies = []
        self.asset_status = {}
        self.selected_source = self.selected_run = ''
        self.pending_source = None
        self.last_view = {}
        self.deferred = []
        self.last_live = ''
        self._cached_project = None
        self._cached_sources = []
        self._cached_runs = []
        self.recent = bridge._settings.value('recentAnalysisProjects',[]) or []
        if not isinstance(self.recent,list): self.recent=[]
        bridge.pipeline.changed.connect(self._pipeline_changed)
        bridge.imageOpened.connect(self._image_opened)

    @Slot(int, object, object)
    def _progress(self, epoch, done, total):
        if epoch == self.epoch and self.busy:
            self.done,self.total=done,total
            self.changed.emit()

    def _begin(self, job, function, callback, token=None, keep_error=False):
        if self.busy:
            self.error='프로젝트 작업이 끝나거나 취소된 뒤 다시 시도하세요.'
            self.changed.emit();return False
        self.epoch+=1
        self.token=token or Event()
        # Background deferred captures must not hide an error the user has not seen.
        self.busy,self.job,self.done,self.total=True,job,0,0
        if not keep_error:self.error=''
        self.callback=callback
        self.changed.emit()
        self.reader.submit(function)
        return True

    def _hash_options(self, token, epoch):
        # The job receives the actual token via a closure after _begin establishes it.
        return {'cancelled':token.is_set,
                'progress':lambda d,t:self.progress.emit(epoch,d,t)}

    @Slot(object, str)
    def _ready(self, value, error):
        job,callback=self.job,self.callback
        self.busy=False;self.job='';self.callback=None
        carried,self.error=self.error,''
        if error:
            self.error=error
            if job=='save' and '[Errno 13]' in error:self.read_only=True
        else:
            try:callback(value)
            except (OSError,ValueError,KeyError) as exc:self.error=str(exc)
        ok=not self.error
        if ok and carried:self.error=carried
        self.changed.emit()
        # Drain queued captures after failures too; each failure pops one entry.
        self.resume_deferred()
        self.operationFinished.emit(job,ok)

    def saving(self):
        """Name the write that currently owns the project file, or ''."""
        if self.job=='save':return '프로젝트 저장'
        for name,job,label in (('wafer_map_controller','save','Wafer Map 배치 저장'),
                               ('stack3d_controller','save','3D 세션 저장'),
                               ('registration_controller','approve-save','정합 승인 저장')):
            controller=getattr(self.bridge,name,None)
            if controller and controller.job==job:return label
        return ''

    def refuse_while_saving(self):
        # Saved history is append-only, so edits made during a write cannot be merged afterwards.
        label=self.saving()
        if label:
            self.error=f'{label}이 끝난 뒤 다시 시도하세요. 저장 중에는 프로젝트를 변경할 수 없습니다.'
            self.changed.emit()
        return bool(label)

    def registration_busy(self):
        registration=getattr(self.bridge,'registration_controller',None)
        return bool(registration and registration.busy)

    def resume_deferred(self):
        if self.deferred and not self.busy and not self.saving():
            result,manifest=self.deferred.pop(0)
            self._capture(result,manifest,keep_error=True)

    @Slot()
    def cancel(self):
        if self.job not in ('open','select','hash','relink'):return
        self.token.set();self.reader.invalidate();self.epoch+=1
        self.busy=False;self.job='';self.callback=None
        self.changed.emit()

    def _stack3d_pending(self):
        controller=getattr(self.bridge,"stack3d_controller",None)
        if controller and controller.manual_pending:
            self.error="수동 3D Track 초안을 저장하거나 초안 취소한 뒤 프로젝트를 전환하세요."
            self.changed.emit()
            return True
        return False

    def _analysis_busy(self):
        stack3d=getattr(self.bridge,"stack3d_controller",None)
        if stack3d and stack3d.job=="save":
            self.error="3D 세션 저장을 완료한 뒤 전환하세요.";self.changed.emit();return True
        wafer=getattr(self.bridge,"wafer_map_controller",None)
        if wafer and wafer.job=="save":
            self.error="Wafer Map 배치 저장을 완료한 뒤 전환하세요.";self.changed.emit();return True
        registration=getattr(self.bridge,"registration_controller",None)
        if registration and registration.job=="approve-save":
            self.error="정합 승인 저장 완료 후 프로젝트를 전환하세요."
            self.changed.emit();return True
        review=getattr(self.bridge,"review_controller",None)
        if review and review.pending:
            self.error="작성 중인 검수·영역 초안을 기록하거나 취소하세요."
            self.changed.emit();return True
        if self.bridge.pipeline.state == AnalysisState.RUNNING:
            self.error='분석 완료 또는 취소 후 프로젝트·저장 이력을 전환하세요.'
            self.changed.emit();return True
        return False

    def _replace(self, project):
        if project is not self.project:
            if self.refuse_while_saving():return False
            self.project=project;self.dirty=True
        self.changed.emit()
        return True

    def _pipeline_changed(self):
        r=self.bridge.pipeline.result
        if r is None or r.status!=AnalysisState.COMPLETED or r.analysis_id==self.last_live:return
        self.last_live=r.analysis_id
        if r.request.source.metadata.page_count!=1:return
        manifest=getattr(getattr(self.bridge.pipeline.adapter,'classifier',None),'manifest',None)
        if self.project is None:
            self.project=AnalysisProject('새 분석 프로젝트');self.dirty=True
        self.dirty=True
        if self.busy:self.deferred.append((r,manifest));self.changed.emit()
        else:self._capture(r,manifest)

    def _capture(self, result, manifest=None, keep_error=False):
        if self.saving():
            self.deferred.append((result,manifest))
            self.message='저장이 끝나면 분석 결과를 프로젝트에 추가합니다.'
            self.changed.emit();return
        snapshot=self.project
        def publish(p):self._replace(p)
        self._begin('capture',lambda:capture_live(snapshot,result,manifest),publish,keep_error=keep_error)

    @Slot()
    def captureCurrent(self):
        result=self.bridge.pipeline.result
        if result is None or result.status!=AnalysisState.COMPLETED or result.request.source.metadata.page_count!=1:
            self.error='추가할 완료된 2D 분석 결과가 없습니다.';self.changed.emit();return
        if self.project is None:
            self.project=AnalysisProject('새 분석 프로젝트');self.dirty=True
        manifest=getattr(getattr(self.bridge.pipeline.adapter,'classifier',None),'manifest',None)
        self._capture(result,manifest)

    @Slot()
    def registerCurrent(self):
        if self.busy or self.refuse_while_saving():return
        source=self.bridge.original_source
        if source is None:self.error='등록할 원본 이미지를 먼저 여세요.';self.changed.emit();return
        if self.project is None:
            self.project=AnalysisProject('새 분석 프로젝트');self.dirty=True
        snapshot=self.project
        def publish(value):
            p,record=value
            self._replace(p)
            self.availability[record.source_id]=inspect_source(record)
            self.selected_source=record.source_id
        self._begin('register',lambda:add_source(snapshot,source),publish)

    @Slot(str, str)
    def create(self, name, filename):
        if self._stack3d_pending():return
        if self._analysis_busy():return
        try:
            if not name.strip() or len(name.strip())>200:raise ValueError('프로젝트 이름은 1–200자여야 합니다.')
            path=local_path(filename).absolute()
            if path.is_symlink():raise ValueError('프로젝트 파일은 심볼릭 링크로 생성할 수 없습니다.')
            if path.exists():raise ValueError('새 프로젝트는 기존 파일이 없는 경로에 생성하세요.')
            p=AnalysisProject(name.strip())
        except (OSError,ValueError) as exc:self.error=str(exc);self.changed.emit();return
        def write():ProjectStore().save(path,p);return p
        def publish(p):
            self._activate(p,path,{},{})
            self.bridge.research_controller.show_live()
        self._begin('create',write,publish)

    @Slot(str, str)
    def save(self, filename='', name=''):
        if self.refuse_while_saving():return
        if self.registration_busy():
            # Its result would land on the snapshot being written and be dropped by this save.
            self.error='정합 작업이 끝난 뒤 프로젝트를 저장하세요.';self.changed.emit();return
        review=getattr(self.bridge,'review_controller',None)
        if review and review.pending:
            self.error='작성 중인 판정·도형을 검수 기록으로 확정한 뒤 프로젝트를 저장하세요.';self.changed.emit();return
        if self.busy:return
        snapshot=self.project
        if snapshot is None:
            self.error='저장할 프로젝트나 완료된 분석 결과가 없습니다.';self.changed.emit();return
        old_path=self.path
        path=local_path(filename or self.path).absolute() if (filename or self.path) else None
        if path is None:self.error='프로젝트 저장 위치를 선택하세요.';self.changed.emit();return
        if filename and path.exists() and (not old_path or path.resolve()!=Path(old_path).resolve()):
            self.error='다른 이름으로 저장은 새 경로만 허용합니다. 기존 프로젝트를 덮어쓰지 않습니다.';self.changed.emit();return
        if name:
            if not name.strip() or len(name.strip())>200:self.error='유효한 프로젝트 이름을 입력하세요.';self.changed.emit();return
            if snapshot.project_name!=name.strip():snapshot=snapshot.evolve(project_name=name.strip())
        self._replace(snapshot)
        expected=self.saved_snapshot.revision if self.saved_snapshot and (old_path and path.resolve()==Path(old_path).resolve()) else None
        dependencies=tuple(self.dependencies)
        token=Event();options=self._hash_options(token,self.epoch+1)
        def write():
            updated=[]
            for s in snapshot.image_sources:
                if s.page_count==1 and not s.content_hash:
                    status=inspect_source(s)
                    if status.pixels_available:s=verify_content_hash(s,**options)
                updated.append(s)
            p=snapshot.evolve(image_sources=tuple(updated)) if tuple(updated)!=snapshot.image_sources else snapshot
            publish_dependencies(path,p,dependencies,old_path)
            ProjectStore().save(path,p,expected_revision=expected)
            return p
        def publish(p):
            if self.project is not snapshot:
                # Never replace newer in-memory edits with the written snapshot.
                self.saved_snapshot=p;self.path=str(path);self.read_only=False
                self.error='저장 중 프로젝트가 변경되어 최신 내용은 저장되지 않았습니다. 프로젝트를 다시 여세요.'
                return
            self.project=self.saved_snapshot=p;self.path=str(path);self.dirty=False;self.read_only=False
            self.dependencies=[];self.message='저장됨 · 원본 이미지는 포함하지 않습니다.'
            self._remember(p,path)
            self._save_view(p)
            previous_availability=self.availability
            prior_sources={s.source_id:s for s in snapshot.image_sources}
            self.availability={s.source_id:inspect_source(s) for s in p.image_sources}
            for source in p.image_sources:
                old=prior_sources.get(source.source_id)
                prior_status=previous_availability.get(source.source_id)
                if self.availability[source.source_id].pixels_available and source.content_hash and ((old and old.content_hash!=source.content_hash) or (prior_status and prior_status.status=="HASH_MATCH")):
                    self.availability[source.source_id]=SourceAvailability("HASH_MATCH",True,"이 세션에서 SHA 검증된 원본입니다.")
        self._begin('save',write,publish,token)

    @Slot(str)
    def open(self, filename):
        if self._stack3d_pending():return
        if self._analysis_busy():return
        path=local_path(filename).resolve()
        def read():
            p=ProjectStore().load(path)
            return p,{s.source_id:inspect_source(s) for s in p.image_sources},inspect_dependencies(path,p)
        def publish(value):self._activate(value[0],path,value[1],value[2]);self.bridge.research_controller.show_live()
        self._begin('open',read,publish)

    def _activate(self, project, path, availability, assets):
        stack3d=getattr(self.bridge,"stack3d_controller",None)
        if stack3d:stack3d.resetProject()
        registration=getattr(self.bridge,"registration_controller",None)
        if registration:registration.resetProject()
        wafer=getattr(self.bridge,"wafer_map_controller",None)
        if wafer:wafer.resetProject()
        review=getattr(self.bridge,'review_controller',None)
        if review:review.cancel()
        self.project=self.saved_snapshot=project;self.path=str(path);self.dirty=False;self.read_only=False
        self.availability=availability;self.asset_status=assets;self.dependencies=[]
        self.selected_source=self.selected_run='';self.pending_source=None;self.deferred=[]
        self.last_view=self.bridge._settings.value('projectView/'+project.project_id,{}) or {}
        self.bridge.research_controller.experiments.unload()
        self._remember(project,path)

    def _save_view(self, project):
        research=self.bridge.research_controller
        run=research.saved.run if research.saved and research.saved.project.project_id==project.project_id else next(
            (r for r in project.analysis_runs if self.bridge.pipeline.result and r.result_id==self.bridge.pipeline.result.analysis_id),None)
        current=self.bridge.original_source
        source=next((s for s in project.image_sources if current and s.file_identity.canonical_path==current.identity.canonical_path),None)
        source_id=run.source_id if run else source.source_id if source else self.selected_source
        selected=research.selected_id if research.selection_kind=='OBSERVATION' else research.experiments.selected_id
        if research.selection_kind=='DEFECT_INSTANCE' and not research.experiments.saved_origin:
            for descriptor in project.model_provenance:
                mapping=descriptor.manifest_snapshot.get('mapping',{})
                if selected in mapping:selected=mapping[selected];break
        self.last_view={'source_id':source_id,'run_id':run.run_id if run else '',
            'kind':research.selection_kind,'selected_id':selected}
        self.bridge._settings.setValue('projectView/'+project.project_id,self.last_view)
        self.bridge._settings.sync()

    @Slot()
    def restoreView(self):
        if self.last_view.get('run_id'):self.selectRun(self.last_view['run_id'])
        elif self.last_view.get('source_id'):self.selectSource(self.last_view['source_id'],'')

    def _restore_selection(self):
        if self.selected_source!=self.last_view.get('source_id') or self.selected_run!=self.last_view.get('run_id',''):return
        if self.last_view.get('kind')=='OBSERVATION':self.bridge.research_controller.selectCandidate(self.last_view.get('selected_id',''))
        elif self.last_view.get('kind')=='DEFECT_INSTANCE':self.bridge.research_controller.experiments.select(self.last_view.get('selected_id',''))

    def _remember(self, project, path):
        self.recent=[{'path':str(path),'name':project.project_name}]+[r for r in self.recent if isinstance(r,dict) and r.get('path')!=str(path)]
        self.recent=self.recent[:10]
        self.bridge._settings.setValue('recentAnalysisProjects',self.recent)
        self.bridge._settings.sync()

    @Slot(str)
    def removeRecent(self, path):
        self.recent=[r for r in self.recent if r.get('path')!=path]
        self.bridge._settings.setValue('recentAnalysisProjects',self.recent);self.bridge._settings.sync();self.changed.emit()

    @Slot(str, str)
    def selectSource(self, source_id, run_id=''):
        controller=getattr(self.bridge,"stack3d_controller",None)
        if controller and controller.source and source_id!=controller.source.source_id and self._stack3d_pending():return
        if self._analysis_busy():return
        if self.project is None or self.busy:return
        source=next((s for s in self.project.image_sources if s.source_id==source_id),None)
        run=next((r for r in self.project.analysis_runs if r.run_id==run_id and r.source_id==source_id),None) if run_id else None
        if source is None or (run_id and run is None):return
        if source.page_count != 1 and run:
            self.error='TIFF는 스택 탐색·3D용 원본입니다. JPG 분석 결과와 구분합니다.';self.changed.emit();return
        snapshot=self.project
        token=Event();options=self._hash_options(token,self.epoch+1)
        def read():
            status=inspect_source(source,verify_hash=bool(source.content_hash),**options) if (run or (source.page_count==1 and source.content_hash)) else inspect_source(source)
            if run and not source.content_hash:
                status=replace(status,pixels_available=False,status='HASH_UNAVAILABLE',detail='원본 SHA를 명시적으로 검증한 뒤 Overlay를 표시할 수 있습니다.')
            rows,errors=dependency_rows(self.path,snapshot,source_id,run.page_index if run else 0) if self.path and status.pixels_available and source.page_count == 1 else ([],[])
            return status,rows,errors
        def publish(value):
            status,rows,errors=value
            self.availability[source_id]=status
            self.selected_source,self.selected_run=source_id,run_id
            self.bridge.research_controller.experiments.unload()
            if run:self.bridge.research_controller.show_saved(SavedResultPresentation(snapshot,run))
            else:self.bridge.research_controller.show_live()
            self.pending_source=(source,run,rows,errors) if status.pixels_available else None
            self.sourceRequested.emit(source.source_reference if status.pixels_available else '')
            if not status.pixels_available and run:QTimer.singleShot(0,self.resultRequested.emit)
        self._begin('select',read,publish,token)

    @Slot(str)
    def selectRun(self, run_id):
        if self.project is None:return
        run=next((r for r in self.project.analysis_runs if r.run_id==run_id),None)
        if run:self.selectSource(run.source_id,run_id)

    def _image_opened(self, result):
        if result.get('workingCopy'):return
        if not result.get('ok'):
            self.pending_source=None;return
        original=self.bridge.original_source
        if self.pending_source:
            record,run,rows,errors=self.pending_source
            self.pending_source=None
            if original.path!=record.source_reference:return
            try:
                original.validate_identity()
                if (original.identity.file_size,original.identity.mtime_ns)!=(record.file_identity.file_size,record.file_identity.mtime_ns):raise ValueError('원본 Identity가 변경됐습니다.')
                if run:
                    self.bridge.research_controller.show_saved(SavedResultPresentation(self.project,run,original))
                    QTimer.singleShot(0,self.resultRequested.emit)
                if rows:
                    self.bridge.research_controller.experiments.adopt_saved(original,rows,self.path)
                    QTimer.singleShot(0,self.resultRequested.emit)
                if errors:self.error='실험 자산 연결 필요: '+'; '.join(errors)
                QTimer.singleShot(0,self._restore_selection)
            except ValueError as exc:self.error=str(exc)
            self.changed.emit();return
        if self.project is not None and not self.busy:self.registerCurrent()

    @Slot()
    def manualImageRequested(self):
        self.pending_source=None;self.selected_run='';self.bridge.research_controller.show_live()

    @Slot(str, str)
    def setRole(self, source_id, role):
        if self.project is None or self.busy:return
        try:
            sources=tuple(replace(s,role=ImageRole(role)) if s.source_id==source_id else s for s in self.project.image_sources)
            if sources!=self.project.image_sources:self._replace(self.project.evolve(image_sources=sources))
        except ValueError as exc:self.error=str(exc);self.changed.emit()

    @Slot(str, str)
    def rename(self, name, unused=''):
        if self.project and not self.busy and name.strip() and len(name.strip())<=200 and name.strip()!=self.project.project_name:
            self._replace(self.project.evolve(project_name=name.strip()))

    @Slot(str)
    def verifySource(self, source_id):
        self._source_change(source_id,'hash','')

    @Slot(str, str)
    def relink(self, source_id, filename):
        self._source_change(source_id,'relink',filename)

    def _source_change(self, source_id, job, filename):
        if self.project is None or self.refuse_while_saving():return
        snapshot=self.project
        source=next((s for s in snapshot.image_sources if s.source_id==source_id),None)
        if source is None:return
        token=Event();options=self._hash_options(token,self.epoch+1)
        def read():
            updated=verify_content_hash(source,**options) if job=='hash' else relink_source(source,local_path(filename),**options)
            return snapshot.evolve(image_sources=tuple(updated if s.source_id==source_id else s for s in snapshot.image_sources))
        def publish(p):
            self._replace(p)
            self.availability[source_id]=SourceAvailability('HASH_MATCH',True,'명시적 SHA 검증이 완료됐습니다.')
            self.message='SHA 검증 완료' if job=='hash' else '원본 재연결 완료 · 프로젝트를 저장하세요.'
        self._begin(job,read,publish,token)

    @Slot()
    def importCurrentExperiment(self):
        if self.busy or self.refuse_while_saving():return
        e=self.bridge.research_controller.experiments
        if e.project is None or not e.manifest or e.saved_origin:
            self.error='먼저 단일 페이지 2D 이미지의 TD02 실험 번들을 불러오세요.';self.changed.emit();return
        if self.project is None:
            self.project=AnalysisProject('새 분석 프로젝트');self.dirty=True
        snapshot=self.project
        incoming,manifest,folder,source=e.project,e.manifest,e.folder,e.source
        def read():
            from sic_xrt_analyzer.results.bpd_experiment import load_experiment_bundle

            from .experiment_controller import same_source
            loaded,checked=load_experiment_bundle(folder)
            if loaded!=incoming or checked!=manifest:raise ValueError('실험 번들이 불러온 뒤 변경됐습니다.')
            same_source(source,checked)
            return import_experiment(snapshot,incoming,manifest,folder)
        def publish(value):
            p,dependency=value
            self._replace(p)
            if dependency:self.dependencies.append(dependency)
            self.message='실험 근거·Mask를 프로젝트에 추가했습니다. 저장 시 종속 자산을 보존합니다.'
        self._begin('import',read,publish)

    @Slot()
    def close(self):
        if self._stack3d_pending():return
        if self._analysis_busy():return
        if self.busy:return
        self.bridge.review_controller.cancel()
        self.project=self.saved_snapshot=None;self.path='';self.dirty=False
        self.availability={};self.asset_status={};self.dependencies=[];self.deferred=[]
        self.selected_source=self.selected_run='';self.pending_source=None
        self.bridge.research_controller.experiments.unload();self.bridge.research_controller.show_live();self.changed.emit()

    def shutdown(self):
        self.token.set();self.reader.shutdown()

    @Property('QVariantMap',notify=changed)
    def state(self):
        p=self.project
        if self._cached_project is not p:
            self._cached_project=p
            counts=Counter(o.run_id for o in p.observations) if p else Counter()
            source_runs=Counter(r.source_id for r in p.analysis_runs) if p else Counter()
            self._cached_sources=[{'id':s.source_id,'name':s.display_name,'path':s.source_reference,
                'format':s.acquisition_metadata.get('format',''),'role':s.role.value,
                'pages':s.page_count,'hashAvailable':bool(s.content_hash),'runs':source_runs[s.source_id]}
                for s in p.image_sources] if p else []
            self._cached_runs=[{'id':r.run_id,'sourceId':r.source_id,'date':r.started_at.isoformat(),
                'model':r.model_version,'scope':r.scope.value,'count':counts[r.run_id],'status':r.run_status.value}
                for r in p.analysis_runs] if p else []
        sources=[]
        for row in self._cached_sources:
            status=self.availability.get(row['id'])
            sources.append({**row,'status':status.status if status else 'UNKNOWN','detail':status.detail if status else ''})
        runs=self._cached_runs
        return {'active':p is not None,'name':p.project_name if p else '', 'id':p.project_id if p else '',
            'revision':p.revision if p else 0,'path':self.path,'dirty':self.dirty,'busy':self.busy,
            'readOnly':self.read_only,'job':self.job,'error':self.error,'message':self.message,'done':self.done,'total':self.total,
            'canCancel':self.job in ('open','select','hash','relink'),
            'sources':sources,'runs':runs,'sourceCount':len(sources),'runCount':len(runs),
            'recent':self.recent,'selectedSource':self.selected_source,'selectedRun':self.selected_run,
            'lastView':self.last_view,'assetStatus':self.asset_status,'structureCount':len(p.defect_instances) if p else 0,'reviewCount':len(p.review_events) if p else 0,
            'needsSource':any(s['status'] in ('MISSING','IDENTITY_MISMATCH','UNREADABLE','HASH_UNAVAILABLE') for s in sources),
            'savedActive':self.bridge.research_controller.saved is not None}
