"""Display real Qt/Windows dialogs and reject programmatically, without OS input.

This diagnoses lifetime/COM and cancellation only. It cannot establish that a
person can choose a file, confirm Save, or recover native keyboard/mouse focus.
"""
import argparse
import faulthandler
import json
import time
from pathlib import Path

import psutil
from PySide6.QtCore import QMetaObject, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from validate_rc_session import Session, memory


def main():
    faulthandler.enable()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeat',type=int,default=20)
    parser.add_argument('--dialog',choices=('all','open','save','results'),default='all')
    parser.add_argument('--qml-dispatch',action='store_true',help='Dispatch through QML ids to distinguish Python QObject wrappers')
    parser.add_argument('--qml-root',type=Path,default=Path('src/sic_xrt_analyzer/ui'))
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    app = QGuiApplication([]); QQuickStyle.setStyle('Basic')
    assert app.platformName() == 'windows'
    s = Session(app,args.output.resolve(),args.qml_root.resolve())
    process = psutil.Process()
    report = {'platform':app.platformName(),'interaction':'Qt open/reject; native OS input NOT tested',
              'dispatch':'QML ids' if args.qml_dispatch else 'Python QObject wrappers','cases':[]}
    def evaluate(code):
        expression = QQmlExpression(QQmlEngine.contextForObject(s.window),s.window,code)
        value = expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
        return value[0] if isinstance(value,tuple) else value
    try:
        print('STAGE source-open',flush=True)
        s.open(args.input)
        print('STAGE source-ready',flush=True)
        identity = s.bridge.original_source.identity
        candidates = [s.item('openImageDialog')]
        for title in ('이미지 전체 파일의 새 복사본 저장 (기존 파일 덮어쓰기 불가)','결과를 저장할 폴더'):
            matches = [n for n in s.window.findChildren(QObject)
                       if n.property('title') == title]
            assert len(matches) == 1, title
            candidates.extend(matches)
        print('STAGE dialogs-found',flush=True)
        selected = list(zip(('open','save','results'),('openDialog','imageSaveDialog','resultsDialog'),candidates))
        if args.dialog != 'all':
            selected = [selected[('open','save','results').index(args.dialog)]]
        for name,qml_id,dialog in selected:
            row = {'kind':name,'iterations':args.repeat,
                   'memory_before':memory(),'handles_before':process.num_handles(),'durations':[]}
            for _index in range(args.repeat):
                print(f'STAGE {name} iteration {_index+1} opening',flush=True)
                start = time.monotonic()
                if args.qml_dispatch:
                    evaluate(qml_id+'.open()')
                else:
                    assert QMetaObject.invokeMethod(dialog,'open')
                s.wait(lambda d=dialog, key=qml_id: evaluate(key+'.visible') if args.qml_dispatch else d.property('visible'),timeout=10)
                QTest.qWait(100)
                if args.qml_dispatch:
                    evaluate(qml_id+'.reject()')
                else:
                    assert QMetaObject.invokeMethod(dialog,'reject')
                print(f'STAGE {name} iteration {_index+1} reject-returned',flush=True)
                s.wait(lambda d=dialog, key=qml_id: not (evaluate(key+'.visible') if args.qml_dispatch else d.property('visible')),timeout=10)
                assert s.bridge.original_source.identity == identity
                assert not s.state.property('opening') and not s.state.property('loadError')
                row['durations'].append(round(time.monotonic()-start,3))
            row.update(memory_after=memory(),handles_after=process.num_handles())
            report['cases'].append(row)
            print(json.dumps(row),flush=True)
    finally:
        report['shutdown_seconds'] = round(s.close(),3)
        report['qml_warnings'] = s.warnings
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')


if __name__ == '__main__':
    main()
