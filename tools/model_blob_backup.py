"""Static scripts for digest-checked model volume snapshots. Keys are never included."""

BACKUP = r"""
import hashlib,json,pathlib,re,tarfile
root=pathlib.Path('/data/models');inventory={}
references=json.loads(pathlib.Path('/backup/model_refs.json').read_text())
with tarfile.open('/backup/models.tar','w') as archive:
 if root.exists():
  for directory in sorted(root.iterdir()):
   if directory.name.startswith('.stage-'):continue
   if directory.is_symlink() or not directory.is_dir() or not re.fullmatch('[0-9a-f]{64}',directory.name):raise ValueError('Unsafe model directory')
   for file in sorted(directory.iterdir()):
    if file.is_symlink() or not file.is_file() or file.name not in ('model.onnx','manifest.json','candidate-registry.json'):raise ValueError('Unsafe model file')
    if file.stat().st_size> (64*1024**2 if file.name=='model.onnx' else 1024**2):raise ValueError('Model size')
    key=directory.name+'/'+file.name
    h=hashlib.sha256()
    with file.open('rb') as f:
     for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    inventory[key]=h.hexdigest();archive.add(file,arcname=key,recursive=False)
if any(inventory.get(k)!=v for k,v in references.items()):raise ValueError('DB model reference missing or corrupted')
pathlib.Path('/backup/models.json').write_text(json.dumps(inventory,sort_keys=True))
"""
RESTORE = r"""
import hashlib,json,pathlib,re,tarfile
root=pathlib.Path('/data/models');root.mkdir(exist_ok=True)
expected=json.loads(pathlib.Path('/backup/models.json').read_text());references=json.loads(pathlib.Path('/backup/model_refs.json').read_text());found=set();total=0
if any(expected.get(k)!=v for k,v in references.items()):raise ValueError('Model DB inventory mismatch')
with tarfile.open('/backup/models.tar') as archive:
 for entry in archive:
  if not entry.isfile() or not re.fullmatch(r'[0-9a-f]{64}/(model.onnx|manifest.json|candidate-registry.json)',entry.name):raise ValueError('Unsafe model archive')
  if entry.name in found or not 0<entry.size<=(64*1024**2 if entry.name.endswith('/model.onnx') else 1024**2):raise ValueError('Model bounds')
  total+=entry.size
  if total>1024**3:raise ValueError('Model quota')
  target=root/entry.name;target.parent.mkdir(exist_ok=True)
  if target.exists() or target.parent.is_symlink():raise ValueError('Model destination not empty')
  h=hashlib.sha256()
  with archive.extractfile(entry) as source,target.open('xb') as output:
   for chunk in iter(lambda:source.read(1024**2),b''):h.update(chunk);output.write(chunk)
  if h.hexdigest()!=expected.get(entry.name):raise ValueError('Model blob hash mismatch')
  found.add(entry.name)
if found!=set(expected):raise ValueError('Model inventory mismatch')
"""
