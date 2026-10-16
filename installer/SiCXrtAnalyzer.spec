# Build only explicit app packages and public runtimes; never collect research artifacts.
import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
root=Path(SPECPATH).parent
sys.path.insert(0, str(root/'src'))
sys.path.insert(0, str(root/'tools'))
from windows_build_environment import validate_binary_sources
from windows_bundle_policy import slim_toc, validate_retained_imports, write_report
jdk=Path(os.environ["XRT_BUILD_JDK"])
datas=collect_data_files('sic_xrt_analyzer')+collect_data_files('roifile')+collect_data_files('skimage', includes=['*.pyi','**/*.pyi'])
for dep in ['numpy','scipy','scikit-image','tifffile','imagecodecs','onnxruntime','onnx','cryptography','packaging','JPype1','keyring','Pillow','httpx','PySide6','PySide6_Addons','PySide6_Essentials','shiboken6']:
    datas+=copy_metadata(dep)
datas += [(str(root/'installer/THIRD-PARTY-NOTICES.txt'),'.'),(str(root/'LICENSE'),'.'),(str(root/'installer/PYTHON-LICENSE.txt'),'.'),(str(root/'NOTICE'),'.'),(str(root/'installer/CORRESPONDING-SOURCE.md'),'.'),(str(root/'artifacts/imagej-runtime'),'runtimes/imagej'),(str(root/'artifacts/fiji-runtime'),'runtimes/fiji'),(str(jdk),'runtimes/openjdk')]
a=Analysis([str(root/'installer/launcher.py')],pathex=[str(root/'src')],binaries=[],datas=datas,hiddenimports=collect_submodules('imagecodecs')+collect_submodules('sic_xrt_analyzer')+['PySide6.QtQuick3D','PySide6.QtWidgets','PySide6.QtSvg','onnxruntime','onnx','jpype','keyring.backends.Windows'],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['PySide6.QtWebEngineCore','PySide6.QtWebEngineQuick','PySide6.QtWebEngineWidgets','PySide6.QtWebView','PyQt5','PyQt6','PySide2','torch','tensorflow','matplotlib','IPython','ipywidgets','notebook','pytest','xrt_server','xrt_portal'],noarchive=False)
# Cached analyses must obey the same provenance rule as fresh builds.
validate_binary_sources(a.binaries, [Path(sys.prefix), Path(sys.base_prefix),
    Path(os.environ.get('WINDIR', 'C:/Windows')), jdk,
    root/'artifacts/imagej-runtime', root/'artifacts/fiji-runtime'])
# PyInstaller 6.22 does not implement qml_exclude_plugins; filter actual TOCs.
a.binaries, removed_binaries = slim_toc(a.binaries)
a.datas, removed_datas = slim_toc(a.datas)
removed = removed_binaries + removed_datas
validate_retained_imports(a.binaries, removed)
selection_report = Path(workpath) / 'bundle-selection.json'
write_report(selection_report, removed)
a.datas += [('bundle-selection.json', str(selection_report), 'DATA')]
pyz=PYZ(a.pure)
gui=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SiCXrtApp',icon=str(root/'src/sic_xrt_analyzer/ui/assets/app-icon.ico'),debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False)
worker=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SiCXrtWorker',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(gui,worker,a.binaries,a.datas,strip=False,upx=False,name='SiCXrtAnalyzer')
