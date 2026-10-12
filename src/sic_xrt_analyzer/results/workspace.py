"""Workspace adapters: explicit immutable import and verified dependency publication.

ProjectStore/schema remain authoritative. Original images are never copied.
"""
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

from sic_xrt_analyzer.imaging.original_source import SourceIdentity

from .adapter import import_legacy_result
from .contracts import FileIdentity, ImageSourceRecord, ModelProvenance
from .persistence import ProjectStore
from .serialization import plain
from .validation import stable_id


def add_source(project, source):
    source.validate_identity()
    m, i = source.metadata, source.identity
    identity = FileIdentity(i.canonical_path, i.file_size, i.mtime_ns)
    found = [s for s in project.image_sources if s.file_identity == identity]
    if found:
        return project, found[0]
    fingerprint = f"{i.canonical_path}|{i.file_size}|{i.mtime_ns}|{m.width}|{m.height}|{m.dtype}|{m.bit_depth}|{m.channels}|{m.page_count}"
    acquisition={'format':m.format}
    if m.format=='TIFF':
        import tifffile
        with tifffile.TiffFile(source.path) as tif:
            acquisition['imagej_metadata']={k:v for k,v in (tif.imagej_metadata or {}).items() if k in ('frames','slices','channels','images','unit','hyperstack')}
    record = ImageSourceRecord(stable_id(project.project_id, 'source:' + fingerprint),
        Path(source.path).name, source.path, m.width, m.height, m.dtype, m.bit_depth,
        m.channels, m.page_count, identity, acquisition_metadata=acquisition)
    return project.evolve(image_sources=project.image_sources + (record,)), record


def capture_live(project, result, manifest=None):
    # Explicit original snapshot reuse, including registered TIFF/JPEG identities.
    identity = result.source_identity
    found = next((s for s in project.image_sources if s.file_identity == FileIdentity(
        identity.canonical_path, identity.file_size, identity.mtime_ns)), None)
    updated=import_legacy_result(project, result, model_manifest=manifest,
                                source_id=found.source_id if found else None)
    if updated is project:return project
    run=next(r for r in updated.analysis_runs if r.result_id==result.analysis_id)
    sources=[]
    for s in updated.image_sources:
        if s.source_id==run.source_id:
            metadata=dict(s.acquisition_metadata)
            orders=dict(metadata.get('workspace_export_order',{}))
            orders[result.analysis_id]={'parameters':order_tree(result.parameters),'summary':order_tree(result.summary)}
            metadata['workspace_export_order']=orders
            s=replace(s,acquisition_metadata=metadata)
        sources.append(s)
    return replace(updated,image_sources=tuple(sources))


def order_tree(value):
    if hasattr(value,'items'):return [[k,order_tree(v)] for k,v in value.items()]
    if isinstance(value,(list,tuple)):return [order_tree(v) for v in value]
    return None


def ordered(value, tree):
    if tree is None:return value
    if hasattr(value,'items'):
        return {k:ordered(value[k],child) for k,child in tree}
    if isinstance(value,(list,tuple)):return [ordered(v,child) for v,child in zip(value,tree)]
    return value


@dataclass(frozen=True)
class SavedResultPresentation:
    """Read-only history provider. Never assigned to AnalysisPipeline.result/state."""
    project: object
    run: object
    source: object = None

    @property
    def rows(self):
        return [{'id': o.source_candidate_id, 'point_id': o.metadata.get('point_id',o.source_candidate_id),
            'number': n+1, 'scores': list(o.raw_scores) if len(o.raw_scores)==3 else [],
            'x': o.x, 'y': o.y, 'type': o.assigned_class or 'unknown',
            'score': o.displayed_score, 'low_score': o.metadata.get('low_score',False)}
            for n, o in enumerate(o for o in self.project.observations if o.run_id == self.run.run_id and o.x is not None)]

    @property
    def analysis_id(self): return self.run.result_id or self.run.run_id
    @property
    def status(self): return self.run.run_status
    @property
    def request(self): return SimpleNamespace(source=self.source, page_index=self.run.page_index)
    @property
    def source_identity(self): return SourceIdentity(**dict(self.run.source_identity))
    @property
    def summary(self): return self._ordered('summary',self.run.summary)

    def _ordered(self, key, value):
        s=next(s for s in self.project.image_sources if s.source_id==self.run.source_id)
        tree=s.acquisition_metadata.get('workspace_export_order',{}).get(self.run.result_id,{}).get(key)
        return ordered(value,tree)
    @property
    def model_id(self): return self.run.model_id
    @property
    def model_version(self): return self.run.model_version
    @property
    def parameters(self): return self._ordered('parameters',self.run.parameters)
    @property
    def completed_at(self): return self.run.completed_at
    @property
    def duration(self): return self.run.duration or 0.
    @property
    def scope(self): return self.run.scope
    @property
    def roi(self): return self.run.analysis_roi


def import_experiment(project, incoming, manifest, folder):
    """Explicit namespace remap; preserve all evidence, assessments and history.

    Includes original grouping runs rather than guessing a match from candidate IDs.
    Duplicate imports reuse the deterministic namespace. No classifier is invoked.
    """
    folder = Path(folder).resolve()
    experiment_id = manifest['experiment_id']
    provenance_id = stable_id(project.project_id, 'experiment-import:' + incoming.project_id + ':' + experiment_id)
    if any(p.provenance_id == provenance_id for p in project.model_provenance):
        return project, None
    references = ['experiment.json', 'project.json', *sorted(manifest['assets'])]
    sha = hashlib.sha256()
    for reference in references:
        path = ProjectStore().resolve_asset(folder/'project.json', reference)
        data = path.read_bytes()
        if len(data) > 64*1024**2:
            raise ValueError('Experiment dependency file exceeds 64 MiB')
        sha.update(reference.encode()); sha.update(hashlib.sha256(data).digest())
    prefix = f'assets/{project.project_id[:12]}/{sha.hexdigest()[:16]}'
    mapping = {}
    fields = [('image_sources','source_id'),('analysis_runs','run_id'),('observations','observation_id'),
        ('predictions','prediction_id'),('geometries','geometry_id'),('defect_instances','instance_id'),
        ('review_events','review_id'),('model_provenance','provenance_id'),('image_relationships','relationship_id')]
    for table, key in fields:
        for row in getattr(incoming, table):
            mapping[getattr(row,key)] = stable_id(project.project_id, 'bundle:' + incoming.project_id + ':' + getattr(row,key))
    for source in incoming.image_sources:
        existing = next((s for s in project.image_sources if s.file_identity == source.file_identity
            and (s.width,s.height,s.dtype,s.channels,s.page_count)==(source.width,source.height,source.dtype,source.channels,source.page_count)),None)
        if existing: mapping[source.source_id] = existing.source_id
    for r in incoming.analysis_runs:
        existing=next((x for x in project.analysis_runs if x.result_id==r.result_id and x.source_id==mapping[r.source_id]),None)
        if existing:
            mapping[r.run_id]=existing.run_id
            mapping[r.provenance_id]=existing.provenance_id
            expected=replace(r,run_id=existing.run_id,project_id=project.project_id,source_id=existing.source_id,provenance_id=existing.provenance_id)
            if expected!=existing:raise ValueError('같은 Run의 원본 분석 이력이 다릅니다.')
            for o in incoming.observations:
                if o.run_id!=r.run_id:continue
                target=next((x for x in project.observations if x.run_id==existing.run_id and x.source_candidate_id==o.source_candidate_id),None)
                if target is None:raise ValueError('같은 Run의 후보 참조가 다릅니다.')
                mapping[o.observation_id]=target.observation_id
                mapping[o.geometry_id]=target.geometry_id
                for pred in incoming.predictions:
                    if pred.observation_id==o.observation_id:
                        stored=next(x for x in project.predictions if x.observation_id==target.observation_id)
                        mapping[pred.prediction_id]=stored.prediction_id
    changes = {name:list(getattr(project,name)) for name,_ in fields}
    for s in incoming.image_sources:
        if not any(x.source_id==mapping[s.source_id] for x in changes['image_sources']):
            changes['image_sources'].append(replace(s,source_id=mapping[s.source_id]))
    for p in incoming.model_provenance:
        changes['model_provenance'].append(replace(p,provenance_id=mapping[p.provenance_id]))
    for r in incoming.analysis_runs:
        changes['analysis_runs'].append(replace(r,run_id=mapping[r.run_id],project_id=project.project_id,
            source_id=mapping[r.source_id],provenance_id=mapping[r.provenance_id]))
    for o in incoming.observations:
        changes['observations'].append(replace(o,observation_id=mapping[o.observation_id],
            run_id=mapping[o.run_id],geometry_id=mapping[o.geometry_id]))
    for p in incoming.predictions:
        changes['predictions'].append(replace(p,prediction_id=mapping[p.prediction_id],
            observation_id=mapping[p.observation_id],provenance_id=mapping[p.provenance_id]))
    for g in incoming.geometries:
        changes['geometries'].append(replace(g,geometry_id=mapping[g.geometry_id],source_id=mapping[g.source_id],
            mask_reference=prefix+'/'+g.mask_reference if g.mask_reference else None))
    for i in incoming.defect_instances:
        changes['defect_instances'].append(replace(i,instance_id=mapping[i.instance_id],source_id=mapping[i.source_id],
            geometry_id=mapping[i.geometry_id],linked_observations=tuple(replace(l,observation_id=mapping[l.observation_id]) for l in i.linked_observations)))
    for r in incoming.review_events:
        original=plain(r.original_prediction)
        if 'prediction_id' in original: original['prediction_id']=mapping[original['prediction_id']]
        if 'prediction_ids' in original: original['prediction_ids']=[mapping[x] for x in original['prediction_ids']]
        if 'geometry_id' in original: original['geometry_id']=mapping[original['geometry_id']]
        changes['review_events'].append(replace(r,review_id=mapping[r.review_id],target_id=mapping[r.target_id],original_prediction=original,
            source_run_id=mapping.get(r.source_run_id,r.source_run_id),
            corrected_geometry_reference=mapping.get(r.corrected_geometry_reference,r.corrected_geometry_reference),
            parent_review_ids=tuple(mapping[x] for x in r.parent_review_ids)))
    for r in incoming.image_relationships:
        if r.transform_reference:
            raise ValueError('Experiment registration assets require a separate explicit import')
        changes['image_relationships'].append(replace(r,relationship_id=mapping[r.relationship_id],
            source_image_id=mapping[r.source_image_id],target_image_id=mapping[r.target_image_id]))
    changes['model_provenance'].append(ModelProvenance(provenance_id,manifest['algorithm'],
        manifest['algorithm_version'],experiment_id,manifest_snapshot={'kind':'EXPERIMENT_IMPORT',
        'reference':prefix+'/experiment.json','bundle_sha256':sha.hexdigest(), 'mapping':mapping,
        'original_project_id':incoming.project_id,'experiment_id':experiment_id,
        'source_id':mapping[manifest['source_id']], 'page_index':manifest['source_identity']['page_index'],
        'validation_status':manifest.get('validation_status','PRELIMINARY_NO_GROUND_TRUTH')}))
    unique_changes={}
    for name,key in fields:
        records={}
        for record in changes[name]:
            identifier=getattr(record,key)
            if identifier in records and records[identifier]!=record:
                raise ValueError('같은 ID의 분석·검수·형상 근거를 변경할 수 없습니다.')
            records[identifier]=record
        unique_changes[name]=tuple(records.values())
    return project.evolve(**unique_changes), (prefix,folder,references)


def dependency_descriptors(project):
    return [p.manifest_snapshot for p in project.model_provenance if p.manifest_snapshot.get('kind')=='EXPERIMENT_IMPORT']


def publish_dependencies(project_path, project, dependencies, old_path=None):
    """Immutable dependency directories first, then caller atomically saves manifest.

    Failure can leave an unreferenced complete directory; it never replaces old assets.
    """
    parent = Path(project_path).resolve().parent
    from sic_xrt_analyzer.registration.assets import copy_assets
    if old_path:
        copy_assets(old_path, project_path, project)
    for d in dependency_descriptors(project):
        prefix = str(Path(d['reference']).parent).replace('\\','/')
        spec = next((x for x in dependencies if x[0]==prefix),None)
        if spec:
            _,source,references=spec
        elif old_path:
            source = ProjectStore().resolve_asset(old_path,d['reference']).parent
            manifest=json.loads((source/'experiment.json').read_text(encoding='utf-8'))
            references=['experiment.json','project.json',*sorted(manifest['assets'])]
        else:
            raise ValueError('Experiment dependency location unavailable')
        target = (parent/prefix).resolve()
        if not target.is_relative_to(parent): raise ValueError('Asset path escapes project directory')
        if target.exists():
            verify_dependency(target,d)
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.parent.resolve().is_relative_to(parent): raise ValueError('Asset parent escapes project directory')
        temporary=Path(tempfile.mkdtemp(prefix='.xrt-assets-',dir=target.parent))
        try:
            for reference in references:
                original=ProjectStore().resolve_asset(source/'project.json',reference)
                destination=temporary/reference
                destination.parent.mkdir(parents=True,exist_ok=True)
                with original.open('rb') as source_stream, destination.open('xb') as target_stream:
                    shutil.copyfileobj(source_stream,target_stream)
                    target_stream.flush();os.fsync(target_stream.fileno())
            verify_dependency(temporary,d)
            os.rename(temporary,target)
            verify_dependency(target,d)  # Verify the final Windows path before manifest commit.
        finally:
            if temporary.exists() and temporary.name.startswith('.xrt-assets-') and temporary.resolve().is_relative_to(parent):
                shutil.rmtree(temporary)


def verify_dependency(folder, descriptor):
    from .bpd_experiment import load_experiment_bundle
    incoming,manifest=load_experiment_bundle(folder)
    sha=hashlib.sha256()
    for reference in ['experiment.json','project.json',*sorted(manifest['assets'])]:
        path=ProjectStore().resolve_asset(Path(folder)/'project.json',reference)
        data=path.read_bytes()
        if len(data)>64*1024**2: raise ValueError('Dependency file exceeds budget')
        sha.update(reference.encode());sha.update(hashlib.sha256(data).digest())
    if sha.hexdigest()!=descriptor['bundle_sha256']: raise ValueError('Experiment dependency integrity mismatch')
    return incoming,manifest


def inspect_dependencies(path, project):
    statuses={}
    for d in dependency_descriptors(project):
        try:
            folder=ProjectStore().resolve_asset(path,d['reference']).parent
            verify_dependency(folder,d)
            statuses[d['experiment_id']]='READY'
        except FileNotFoundError as exc:
            statuses[d['experiment_id']]='MISSING: '+str(exc)
    return statuses


def dependency_rows(path, project, source_id, page):
    from sic_xrt_analyzer.ui.experiment_controller import present_bundle
    rows, errors = [], []
    for d in dependency_descriptors(project):
        if (d['source_id'],d['page_index'])!=(source_id,page):continue
        try:
            folder=ProjectStore().resolve_asset(path,d['reference']).parent
            incoming,manifest=verify_dependency(folder,d)
            for row in present_bundle(folder,incoming,manifest):
                row['id']=d['mapping'][row['id']]
                row['sourceId']=source_id
                for link in row['links']:link['observation_id']=d['mapping'][link['observation_id']]
                rows.append(row)
        except (OSError,ValueError,KeyError) as exc: errors.append(str(exc))
    return rows, errors
