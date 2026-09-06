from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from time import perf_counter

import pytest

pytest.importorskip('PySide6')
pytest.importorskip('pytestqt')

from PySide6.QtTest import QSignalSpy, QTest

from pixel_studio import PixelDocument
from pixel_studio_qt import PixelCanvas, PixelStudioWindow
from ui_latency import timing_budget
from preferences import PreferencesStore, default_preferences


def _window(tmp_path, qtbot):
    preferences = PreferencesStore(tmp_path / 'preferences.json', default_preferences())
    window = PixelStudioWindow(preferences=preferences, project_root=tmp_path)
    qtbot.addWidget(window)
    window.show()
    return window


def test_base_pixmap_rebuild_budget_large_canvas(qtbot):
    """Full cache rebuild on a 256x128 all-lit canvas must stay in budget.

    Baseline before the scaled-fill fast path: ~40-50ms per rebuild (per-pixel
    drawRect loop); wheel zoom felt janky because every notch paid this cost.
    The C-level bytes-expansion + indexed-QImage path lands ~14-17ms; budget
    20ms keeps 2x headroom over the measured reality while still locking out
    the per-pixel drawRect baseline (~45ms).
    """
    document = PixelDocument(256, 128)
    document.rectangle(0, 0, 255, 127, filled=True)
    canvas = PixelCanvas(document)
    canvas.zoom = 8
    canvas._sync_size()
    qtbot.addWidget(canvas)
    canvas.show()
    qtbot.waitExposed(canvas)
    canvas.grab()
    canvas._invalidate_base_cache()

    started = perf_counter()
    canvas._base_pixmap()
    elapsed = (perf_counter() - started) * 1000.0

    assert elapsed <= timing_budget(20.0), f'base cache rebuild took {elapsed:.1f}ms (budget 20ms)'


def test_set_zoom_same_value_skips_invalidation_and_signal(tmp_path, qtbot):
    """Fit-mode refits call set_zoom with unchanged values; they must not
    invalidate the whole pixel cache or emit zoomChanged again."""
    window = _window(tmp_path, qtbot)
    window.set_zoom(12)
    window.canvas.grab()
    builds = window.canvas._base_cache_builds
    spy = QSignalSpy(window.canvas.zoomChanged)

    window.set_zoom(12)

    assert window.canvas._base_cache_builds == builds
    assert spy.count() == 0


def test_borders_still_render_after_fast_fill_path(tmp_path, qtbot):
    """The scaled-fill fast path must not lose the configurable pixel border."""
    from PySide6.QtGui import QImage

    window = _window(tmp_path, qtbot)
    window.document.pencil(2, 2, 1)
    window.canvas.pixelsChanged.emit((2, 2, 2, 2))
    window.canvas.grab()
    image = window.canvas.grab().toImage().convertToFormat(QImage.Format_RGBA8888)
    z = window.canvas.zoom
    # grab() renders at device pixels: map logical sample points through DPR
    dpr = image.devicePixelRatio() or 1.0
    sx = lambda logical: int(round(logical * dpr))
    # lit pixel centre is fill white; its outermost row is the 1px yellow border
    centre = image.pixelColor(sx(z * 2 + z // 2), sx(z * 2 + z // 2))
    edge = image.pixelColor(sx(z * 2), sx(z * 2 + 1))
    assert centre.redF() > 0.9 and centre.greenF() > 0.9
    assert edge.redF() > 0.9 and edge.greenF() > 0.9 and edge.blueF() < 0.2
