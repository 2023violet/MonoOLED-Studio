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
from pixel_studio_qt import PixelCanvas, PixelStudioWindow, _document_pixmap
from preferences import PreferencesStore, default_preferences


def _studio_window(tmp_path, qtbot):
    preferences = PreferencesStore(tmp_path / 'preferences.json', default_preferences())
    window = PixelStudioWindow(preferences=preferences, project_root=tmp_path)
    qtbot.addWidget(window)
    window.show()
    return window


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


def test_preview_stroke_patches_cached_pixmap_without_rebuilds(tmp_path, qtbot):
    window = _studio_window(tmp_path, qtbot)
    # direct document edits outside the canvas must emit the same signals the
    # canvas tools emit, exactly like production callers do
    window.document.pencil(0, 0, 1)
    window.canvas.pixelsChanged.emit((0, 0, 0, 0))
    window.refresh_preview()
    rebuilds = window._preview_rebuilds
    assert rebuilds >= 1

    for x in range(2, 14):
        window.document.brush(x, 1, 1)
        window.canvas.pixelsChanged.emit((x, 1, x, 1))
    window.refresh_preview()

    assert window._preview_rebuilds == rebuilds
    expected = _document_pixmap(window.document, 2).toImage()
    actual = window.preview.pixmap().toImage()
    for x, y in ((2, 1), (7, 1), (13, 1), (0, 0)):
        assert actual.pixelColor(x * 2, y * 2).rgba() == expected.pixelColor(x * 2, y * 2).rgba()


def test_preview_rebuilds_after_structural_changes_only(tmp_path, qtbot):
    window = _studio_window(tmp_path, qtbot)
    window.refresh_preview()
    rebuilds = window._preview_rebuilds

    window.document.pencil(1, 1, 1)
    window.canvas.documentChanged.emit()  # structural path
    assert window._preview_rebuilds == rebuilds + 1

    window.undo()  # full-document snapshot restore -> rebuild
    assert window._preview_rebuilds == rebuilds + 2
    assert window.preview.pixmap().toImage().pixelColor(2, 2).redF() < 0.5


def test_preview_selection_change_neither_patches_nor_rebuilds(tmp_path, qtbot):
    window = _studio_window(tmp_path, qtbot)
    window.refresh_preview()
    rebuilds = window._preview_rebuilds

    window.canvas.selection = (0, 0, 4, 4)
    window.refresh_preview()

    assert window._preview_rebuilds == rebuilds
    assert '点亮' in window.selection_info.text()
