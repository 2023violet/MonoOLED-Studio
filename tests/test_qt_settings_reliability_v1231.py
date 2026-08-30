import os
from pathlib import Path

import pytest

pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from i18n import Translator
from preferences import PreferencesStore
from preferences_qt import PreferencesView
from qt_theme import build_stylesheet
from runtime_settings import RuntimeSettings

# Pairwise/boundary matrix. The module itself is re-run at every mandatory
# QT_SCALE_FACTOR by RUN_WINDOWS_TEST_GROUPS.py, so DPI is an outer axis.
MATRIX_CASES = (
    (700, 560, 'zh_CN', 'light', 'compact', '90%'),
    (760, 600, 'en_US', 'dark', 'comfortable', '100%'),
    (900, 620, 'zh_CN', 'system', 'spacious', '110%'),
    (980, 680, 'en_US', 'light', 'compact', '125%'),
    (1180, 720, 'zh_CN', 'dark', 'comfortable', '150%'),
    (1440, 900, 'en_US', 'system', 'spacious', '90%'),
    (760, 680, 'zh_CN', 'dark', 'spacious', '150%'),
    (900, 720, 'en_US', 'light', 'comfortable', '125%'),
)


def _view(qtbot, tmp_path):
    store = PreferencesStore.load(tmp_path / 'preferences.json')
    view = PreferencesView(store, Translator('en_US'))
    qtbot.addWidget(view)
    view.show()
    QApplication.processEvents()
    return view, store


def _apply_case(view, store, *, language, theme, density, ui_scale):
    store.set('language', language, save=False)
    store.set('appearance.theme_mode', theme, save=False)
    store.set('appearance.density', density, save=False)
    store.set('appearance.ui_scale', ui_scale, save=False)
    runtime = RuntimeSettings.from_preferences(store)
    QApplication.instance().setStyleSheet(build_stylesheet('monooled-dark' if theme == 'dark' else 'monooled-light', density, runtime.ui_scale))
    view.set_language(language)
    view.apply_runtime_settings(runtime)
    view.stabilize_layout()
    QApplication.processEvents()


def test_settings_pairwise_boundary_matrix_has_no_overlap_or_horizontal_overflow(qtbot, tmp_path):
    view, store = _view(qtbot, tmp_path)
    for width, height, language, theme, density, ui_scale in MATRIX_CASES:
        view.resize(width, height)
        _apply_case(view, store, language=language, theme=theme, density=density, ui_scale=ui_scale)
        for page_index in range(view.nav.count()):
            view.nav.setCurrentRow(page_index)
            view.stabilize_layout()
            QApplication.processEvents()
            assert view.layout_violations() == [], (width, height, language, theme, density, ui_scale, page_index, view.layout_violations())
            current = view.stack.currentWidget()
            assert not current.horizontalScrollBar().isVisible()


def test_settings_500_cycle_resize_language_scale_page_search_soak(qtbot, tmp_path):
    view, store = _view(qtbot, tmp_path)
    widths = (700, 760, 900, 980, 1180, 1440)
    scales = ('90%', '100%', '110%', '125%', '150%')
    densities = ('compact', 'comfortable', 'spacious')
    themes = ('system', 'light', 'dark')
    languages = ('zh_CN', 'en_US')
    searches = ('grid', '快捷键', 'cache', 'theme', '')
    for i in range(500):
        view.resize(widths[i % len(widths)], 560 + (i % 5) * 60)
        language = languages[(i // 7) % len(languages)]
        ui_scale = scales[(i // 11) % len(scales)]
        density = densities[(i // 13) % len(densities)]
        theme = themes[(i // 17) % len(themes)]
        _apply_case(view, store, language=language, theme=theme, density=density, ui_scale=ui_scale)
        view.nav.setCurrentRow(i % view.nav.count())
        if i % 19 == 0:
            view.search.setText(searches[(i // 19) % len(searches)])
        view.stabilize_layout()
        QApplication.processEvents()
        assert view.layout_violations() == [], (i, view.layout_violations())
