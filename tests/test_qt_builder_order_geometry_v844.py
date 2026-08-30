from __future__ import annotations

import sys
from pathlib import Path

import pytest

SIM = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SIM))

pytest.importorskip("PySide6")

from gui import OLEDDesignerWindow


def test_responsive_tick_repairs_stale_oversized_inspector_pane(qtbot):
    window = OLEDDesignerWindow("main_scene", "zh_CN")
    qtbot.addWidget(window)
    window.resize(900, 620)
    window.show()
    qtbot.wait(50)
    window._responsive_tick()
    qtbot.wait(10)

    # Simulate a QSettings-restored splitter state after the responsive bucket
    # has already been computed for this window size.
    calls = []
    original_set_sizes = window.workspace_splitter.setSizes
    window.workspace_splitter.setSizes = lambda sizes: (calls.append(tuple(sizes)), original_set_sizes(sizes))[1]
    window.workspace_splitter.sizes = lambda: [0, 616, 638]
    window._layout_bucket = (180, 280, True)
    calls.clear()
    window._responsive_tick()
    qtbot.wait(10)

    assert calls, "responsive tick must repair splitter state even when bucket is unchanged"
    window.session.document.dirty = False
    window.close()
