# Build only explicit app packages and public runtimes; never collect research artifacts.
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata
root=Path(SPECPATH).parent
jdk=Path(os.environ["XRT_BUILD_JDK"])
datas=collect_data_files('sic_xrt_analyzer')+collect_data_files('roifile')
for dep in ['numpy','scipy','scikit-image','tifffile','imagecodecs','onnxruntime','onnx','cryptography','packaging','JPype1','keyring','Pillow','httpx','PySide6','PySide6_Addons','PySide6_Essentials','shiboken6']:
    datas+=copy_metadata(dep)
datas += [(str(root/'installer/THIRD-PARTY-NOTICES.txt'),'.'),(str(root/'LICENSE'),'.'),(str(root/'installer/PYTHON-LICENSE.txt'),'.'),(str(root/'NOTICE'),'.'),(str(root/'installer/CORRESPONDING-SOURCE.md'),'.'),(str(root/'artifacts/imagej-runtime'),'runtimes/imagej'),(str(root/'artifacts/fiji-runtime'),'runtimes/fiji'),(str(jdk),'runtimes/openjdk')]
a=Analysis([str(root/'installer/launcher.py')],pathex=[str(root/'src')],binaries=[],datas=datas,hiddenimports=collect_submodules('sic_xrt_analyzer')+['PySide6.QtQuick3D','PySide6.QtWidgets','PySide6.QtSvg','onnxruntime','onnx','jpype','keyring.backends.Windows'],hookspath=[],hooksconfig={'PySide6':{'qml_exclude_plugins':['QtWebEngine','QtQuick3D.AssetUtils']}},runtime_hooks=[],excludes=['PyQt5','PyQt6','PySide2','torch','tensorflow','matplotlib','IPython','ipywidgets','notebook','pytest','xrt_server','xrt_portal'],noarchive=False)
pyz=PYZ(a.pure)
gui=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SiCXrtAnalyzer',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False)
worker=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SiCXrtWorker',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(gui,worker,a.binaries,a.datas,strip=False,upx=False,name='SiCXrtAnalyzer')
