"""Keyboard-first review queue in the real QML window: decisions, undo, page accept, sync."""
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from test_analysis_pipeline import spin
from test_result_ux import analyzed

from sic_xrt_analyzer.sync.protocol import digest

pytest_plugins = ('test_toolbar',)


def events(queue):
    with sqlite3.connect(queue.outbox.path) as db:
        return [r[0] for r in db.execute("SELECT decision FROM labels ORDER BY rowid")]


def open_queue(w):
    analyzed(w)
    queue = w.bridge.reviewQueue
    w.click('startReviewQueue')
    spin(w.app, lambda: queue.state['active'] and not queue.state['busy'], 30)
    assert w.item('reviewQueueDialog').property('visible')
    spin(w.app, lambda: bool(queue.state['current'].get('image')), 30)
    return queue


def test_keys_record_decisions_undo_and_show_on_image(workbench):
    w = workbench
    queue = open_queue(w)
    first = queue.state['current']
    # The least certain candidate (smallest top-1 minus top-2 margin) comes first.
    assert first['id'] == 'candidate_000000'
    QTest.keyClick(w.window, Qt.Key_0)
    assert queue.state['decisions'][first['id']] == 'NOT_DEFECT'
    second = queue.state['current']
    assert second['id'] != first['id']
    QTest.keyClick(w.window, Qt.Key_Space)  # accept the model class
    assert queue.state['decisions'][second['id']] == second['type']
    QTest.keyClick(w.window, Qt.Key_Z)
    assert second['id'] not in queue.state['decisions']
    assert queue.state['current']['id'] == second['id']
    QTest.keyClick(w.window, Qt.Key_3)
    assert queue.state['decisions'][second['id']] == 'TSD'
    assert events(queue) == ['NOT_DEFECT', second['type'], 'RETRACTED', 'TSD']
    overlay = w.item('analysisOverlay')
    assert overlay.property('decisions')[first['id']] == 'NOT_DEFECT'
    label = queue.outbox.pending("")[0]['payload']
    assert label['queue']['kind'] == 'uncertain' and label['candidate']['scores'] == [0.6605, 0.3365, 0.003]
    assert label['crop'] is None  # crops are sent only after explicit consent


def test_page_accept_crop_consent_and_sync(workbench, monkeypatch):
    w = workbench
    queue = open_queue(w)
    w.click('reviewQueueSendCrops')
    assert queue.state['sendCrops']
    QTest.keyClick(w.window, Qt.Key_Return)
    assert queue.state['reviewed'] == 24
    stored = [r['payload'] for r in queue.outbox.pending("", 1000)]
    assert {s['mode'] for s in stored} == {'batch_implicit'}
    assert all(s['crop'] and s['crop']['rect'][2:] == [128, 128] for s in stored)

    sent = []

    class Transport:
        endpoint = 'https://server.test'

        def __init__(self, endpoint, token, cancel=None):
            pass

        def request(self, method, path, body):
            sent.extend(body['labels'])
            return {'status': 'ACKNOWLEDGED', 'accepted': len(body['labels']),
                    'receipts': [{'event_id': v['event_id'], 'payload_hash': digest(v)} for v in body['labels']]}

    monkeypatch.setattr('sic_xrt_analyzer.sync.client.Transport', Transport)
    monkeypatch.setattr(w.bridge.sync_controller, 'endpoint', 'https://server.test')
    monkeypatch.setattr(w.bridge.sync_controller, 'token', lambda: 'synthetic-token', raising=False)
    w.click('reviewQueueSync')
    spin(w.app, lambda: not queue.state['syncing'], 30)
    assert len(sent) == 24 and queue.state['pending'] == 0 and queue.state['sent'] == 24
    QTest.keyClick(w.window, Qt.Key_Escape)
    spin(w.app, lambda: not queue.state['active'])
