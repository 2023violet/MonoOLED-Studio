from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from statistics import quantiles
from time import perf_counter

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas


def test_pencil_drag_patches_cache_and_commits_once(qtbot):
    document = PixelDocument(128, 64)
    canvas = PixelCanvas(document)
    canvas.zoom = 8
    canvas._sync_size()
    qtbot.addWidget(canvas)
    canvas.show()
    qtbot.waitExposed(canvas)
    canvas.grab()
    initial_builds = canvas._base_cache_builds
    live = QSignalSpy(canvas.pixelsChanged)
    committed = QSignalSpy(canvas.documentChanged)

    point = lambda x: QPoint(x * 8 + 4, 12)
    QTest.mousePress(canvas, Qt.LeftButton, pos=point(1))
    for x in range(2, 21):
        QTest.mouseMove(canvas, point(x))
        QApplication.processEvents()
        canvas.grab()
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=point(20))
    QApplication.processEvents()

    assert live.count() >= 2
    assert committed.count() == 1
    assert canvas._base_cache_builds == initial_builds
    assert all(document.get(x, 1) == 1 for x in range(1, 21))


@pytest.mark.parametrize(('zoom', 'budget_ms'), ((8, 16), (20, 16), (40, 25)))
def test_incremental_128x64_stroke_p95_stays_within_budget(qtbot, zoom, budget_ms):
    document = PixelDocument(128, 64)
    canvas = PixelCanvas(document)
    canvas.zoom = zoom
    canvas._sync_size()
    qtbot.addWidget(canvas)
    canvas.show()
    canvas.grab()
    initial_builds = canvas._base_cache_builds
    timings = []

    document.begin_gesture()
    for step in range(100):
        x = step % 100
        y = 8 + (step % 3)
        started = perf_counter()
        document.brush(x, y, 1)
        canvas._patch_base_cache((x, y, x, y))
        timings.append((perf_counter() - started) * 1000)
    document.end_gesture()

    p95 = quantiles(timings, n=20, method='inclusive')[18]
    assert p95 <= budget_ms, f'zoom={zoom} p95={p95:.2f}ms budget={budget_ms}ms'
    assert canvas._base_cache_builds == initial_builds
