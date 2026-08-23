from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter

from asset_library import AssetLibrary
from autosave import AutoSaveManager
from asset_convert import convert_bitmap
from c_export import write_c_header
from component_templates import TemplateLibrary
from design_rules import check_design_rules
from batch_validate import build_state_matrix, validate_matrix, write_matrix_report
from editor_model import EditorSession
from evidence import frame_evidence
from exporter import ExportBlockedError, export_scene
from handoff import build_handoff_package
from i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Translator
from pixel_diff import diff_framebuffers
from scene_diff import diff_scenes
from thumbnail_wall import build_thumbnail_wall
from presets import clinical_states
from project_workspace import ProjectWorkspace, create_project
from responsive_layout import plan_layout, header_policy
from professional_workspace import workspace_plan, WorkspaceMode
from selection_model import SelectionModel
from workspace_host import EditorRegistry, CallbackEditor
from performance_profiler import PerformanceProfiler
from selection_tools import align, align_to, distribute, measure, selection_metrics, snap_positions, smart_guides
from canvas_geometry import fit_integer_zoom
from qt_theme import COLORS, METRICS, build_stylesheet
from scene import ROOT, load_scene, scene_root
from session_log import SessionLogger
from validate import has_blockers
from preferences import PreferencesStore, default_preferences
from runtime_settings import RuntimeSettings
from preference_delta import PreferenceDelta
from system_theme import SystemThemeProvider
from commands import CommandRegistry, ShortcutConflictError
from theme_system import resolve_theme_name
from automation_service import StudioAutomationService
from diagnostics import configure_diagnostics, get_logger

APP_TITLE = 'MonoOLED Studio'
APP_VERSION = '8.4.0'
ZOOM_LEVELS = (1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24)
RUN_SPEEDS = {'1×': 1000, '2×': 500, '5×': 200, '10×': 100}
CANVAS_PRESETS = {'96×16': (96, 16), '128×32': (128, 32), '128×64': (128, 64), '256×64': (256, 64)}
DEFAULT_PROJECT = ROOT / 'CuringLite.project.oled.json'

try:
    import PySide6
    from PySide6.QtCore import QEvent, QFileSystemWatcher, QPoint, QRect, QSettings, QSignalBlocker, Qt, QTimer
    from PySide6.QtGui import QAction, QColor, QCloseEvent, QIcon, QImage, QKeySequence, QPixmap, QShortcut
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QFormLayout,
        QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
        QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
        QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget, QAbstractItemView,
    )
    from qt_canvas import OLEDCanvas
    from qt_widgets import ProfessionalPanel, StatusPill
    from pixel_studio_qt import PixelStudioWindow
    from preferences_qt import PreferencesWindow
    from font_lab_qt import FontLabEditor
    from qt_interaction import FocusOriginFilter, set_button_role
    from ui_controls import StudioButton, StudioToolButton, StudioSelect, StudioNumericInput, StudioSegmentedControl, PopupManager
    from automation_qt import QtAutomationBridge
    QPushButton = StudioButton
    QToolButton = StudioToolButton
    QComboBox = StudioSelect
    QSpinBox = StudioNumericInput
    PYSIDE_AVAILABLE = True
    PYSIDE_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    PYSIDE_AVAILABLE = False
    PYSIDE_IMPORT_ERROR = exc


def _log_dir(scene: dict) -> Path:
    root = scene_root(scene)
    target = root / '.oled' / 'logs'
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MonoOLEDStudio' / 'logs'
        base.mkdir(parents=True, exist_ok=True)
        return base



def _decorate_project_scene(scene: dict, project: ProjectWorkspace | None) -> dict:
    if project is not None:
        scene['_project_path'] = str(project.path)
        scene['_asset_dirs'] = list(project.asset_dirs)
        scene['_design_rules'] = dict(project.data.get('design_rules') or {})
    return scene

def _load_source(source: str):
    candidate = Path(source)
    if candidate.exists() and candidate.name.endswith('.oled.json'):
        project = ProjectWorkspace.load(candidate)
        scene = _decorate_project_scene(load_scene(project.screen_path(project.active_screen), project_root=project.root), project)
        return project, scene
    if source == 'main_scene' and DEFAULT_PROJECT.exists():
        project = ProjectWorkspace.load(DEFAULT_PROJECT)
        scene = _decorate_project_scene(load_scene(project.screen_path(project.active_screen), project_root=project.root), project)
        return project, scene
    scene = load_scene(source)
    return None, scene


if PYSIDE_AVAILABLE:
    class PlaceholderDialog(QDialog):
        def __init__(self, tr: Translator, parent=None):
            super().__init__(parent)
            self.setWindowTitle(tr('dialog.placeholder_title'))
            self.setModal(True)
            layout = QVBoxLayout(self); form = QFormLayout()
            self.id_edit = QLineEdit('new_element')
            self.x = QSpinBox(); self.y = QSpinBox(); self.w = QSpinBox(); self.h = QSpinBox()
            for spin in (self.x, self.y): spin.setRange(-8192, 8192)
            for spin in (self.w, self.h): spin.setRange(1, 8192)
            self.w.setValue(12); self.h.setValue(8)
            form.addRow(tr('dialog.placeholder_id'), self.id_edit)
            grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(6)
            for i, (label, spin) in enumerate((('X', self.x), ('Y', self.y), ('W', self.w), ('H', self.h))):
                row, col = i // 2, (i % 2) * 2
                grid.addWidget(QLabel(label), row, col); grid.addWidget(spin, row, col + 1)
            form.addRow(grid); layout.addLayout(form)
            row = QHBoxLayout(); cancel = QPushButton(tr('dialog.cancel')); ok = QPushButton(tr('dialog.ok')); ok.setObjectName('PrimaryButton')
            cancel.clicked.connect(self.reject); ok.clicked.connect(self.accept)
            row.addStretch(1); row.addWidget(cancel); row.addWidget(ok); layout.addLayout(row)

        def values(self):
            return self.id_edit.text().strip(), self.x.value(), self.y.value(), self.w.value(), self.h.value()


    class CommandPalette(QDialog):
        def __init__(self, tr: Translator, commands: list[tuple[str, str, object]], parent=None):
            super().__init__(parent); self.setModal(True); self.resize(520, 430)
            self.setWindowTitle(tr('command.title')); self.commands = commands
            layout = QVBoxLayout(self); self.search = QLineEdit(); self.search.setPlaceholderText(tr('command.search'))
            self.list = QListWidget(); layout.addWidget(self.search); layout.addWidget(self.list, 1)
            self.search.textChanged.connect(self._rebuild); self.list.itemActivated.connect(self._activate)
            self._rebuild(''); self.search.setFocus()

        def _rebuild(self, query: str):
            q = query.casefold().strip(); self.list.clear()
            for key, label, callback in self.commands:
                if q and q not in label.casefold() and q not in key.casefold(): continue
                item = QListWidgetItem(label); item.setData(Qt.UserRole, (key, callback)); self.list.addItem(item)
            if self.list.count(): self.list.setCurrentRow(0)

        def _activate(self, item):
            _key, callback = item.data(Qt.UserRole); self.accept(); QTimer.singleShot(0, callback)


    class OLEDDesignerWindow(QMainWindow):
        def __init__(self, source: str = 'main_scene', language: str = DEFAULT_LANGUAGE):
            super().__init__()
            self.settings = QSettings('MonoOLEDStudio', 'MonoOLEDStudio')
            self.preferences = PreferencesStore.load()
            saved_lang = str(self.preferences.get('language', language))
            self.tr = Translator(saved_lang if saved_lang in SUPPORTED_LANGUAGES else language)
            app = QApplication.instance()
            if app is not None and not hasattr(app, '_monooled_focus_filter'):
                app._monooled_focus_filter = FocusOriginFilter(app)
                app.installEventFilter(app._monooled_focus_filter)
            self.system_theme=SystemThemeProvider(self)
            if hasattr(self.system_theme,'themeChanged'): self.system_theme.themeChanged.connect(self.apply_preferences)
            self._runtime_preferences=None
            self._resolved_theme=None
            self._applied_style_signature=None
            self.command_registry = CommandRegistry()
            defaults=default_preferences()['shortcuts']
            for command_id, shortcut in defaults.items():
                self.command_registry.register(command_id, shortcut=shortcut)
            custom_bindings=dict(self.preferences.get('shortcuts', {}) or {})
            accepted, rejected = self.command_registry.apply_bindings_best_effort(custom_bindings)
            if rejected:
                # Preserve every non-conflicting user choice; only conflicting
                # commands fall back to their defaults.
                merged=dict(defaults); merged.update(accepted)
                self.preferences.data['shortcuts']=merged; self.preferences.save()
            self._preferences_window = None
            self.project, self.scene = _load_source(source)
            self.diag_logger = configure_diagnostics(_log_dir(self.scene)); self.diag_logger.info('Starting %s %s',APP_TITLE,APP_VERSION)
            self.pending_logs: list[dict] = []
            self.selection_model=SelectionModel()
            self.selected_ids: list[str] = []
            self.selected_id: str | None = None
            self.editor_registry=EditorRegistry()
            self._syncing = False
            self._last_frame_signature = None
            self._last_validation_findings = []
            self._layout_bucket = None
            self._diagnostics_open = True
            self._saved_scene_snapshot = deepcopy(self.scene)
            self._saved_frame = None
            self.profiler = PerformanceProfiler(max_samples=180)
            self.workspace_mode = WorkspaceMode.DESIGN

            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.log_path = _log_dir(self.scene) / f'qt_gui_session_{stamp}.jsonl'
            self.logger = SessionLogger(self.log_path, callback=self._on_log)
            self.session = EditorSession(self.scene, logger=self.logger, max_history=int(self.preferences.get('performance.undo_history', 200)))
            self.automation_service=StudioAutomationService.for_editor(self.scene,source_path=self.scene.get('_path'),selection_model=self.selection_model,editor_session=self.session,permission='edit',project_workspace=self.project)
            self.autosave = AutoSaveManager(self.scene, keep=int(self.preferences.get('autosave.snapshots', 10)))
            self.asset_library = self._make_asset_library()
            self.template_library = TemplateLibrary(scene_root(self.scene) / '.oled' / 'templates.json')

            self.run_timer = QTimer(self); self.run_timer.timeout.connect(self._runtime_tick)
            self.autosave_timer = QTimer(self); self.autosave_timer.setInterval(max(1, int(self.preferences.get('autosave.interval_minutes', 3))) * 60_000); self.autosave_timer.timeout.connect(self._autosave_tick); self.autosave_timer.start() if self.preferences.get('autosave.enabled', True) else None
            self.validation_timer=QTimer(self); self.validation_timer.setSingleShot(True); self.validation_timer.setInterval(250); self.validation_timer.timeout.connect(self._update_validation_panel)
            self.layout_timer = QTimer(self); self.layout_timer.setSingleShot(True); self.layout_timer.setInterval(24); self.layout_timer.timeout.connect(self._responsive_tick)
            self.asset_watcher = QFileSystemWatcher(self); self.asset_watcher.fileChanged.connect(self._asset_changed); self.asset_watcher.directoryChanged.connect(self._asset_directory_changed)

            self._menus = {}; self._actions: dict[str, QAction] = {}
            self._build_ui(); self.agent_bridge=QtAutomationBridge(self.automation_service,self); self.agent_bridge.commandCompleted.connect(self._agent_command_completed); self._build_menu(); self.apply_preferences(initial=True); self._bind_shortcuts(); self._connect_responsive_events()
            self._rebuild_screens(); self._rebuild_elements(); self._scan_assets(); self._scan_fonts()
            if self.scene.get('elements'): self.select_element(str(self.scene['elements'][0]['id']))
            self.retranslate_ui(); self.refresh_all(keep_selection=True); self._flush_pending_logs(); self._capture_saved_baseline()
            self._restore_window_state()
            QTimer.singleShot(120, self._prompt_recovery_if_needed)

        # ---------- model / project ----------
        def _make_asset_library(self):
            root = scene_root(self.scene)
            dirs = self.project.asset_dirs if self.project else tuple(self.scene.get('asset_dirs', ['.']))
            return AssetLibrary(root, dirs, cache_budget_mb=int(self.preferences.get('performance.asset_cache_mb',512)))

        def _reset_session(self, scene: dict):
            self.scene = scene; self.session = EditorSession(scene, logger=self.logger, max_history=int(self.preferences.get('performance.undo_history', 200))); self.automation_service=StudioAutomationService.for_editor(self.scene,source_path=self.scene.get('_path'),selection_model=self.selection_model,editor_session=self.session,permission='edit',project_workspace=self.project);
            if hasattr(self,'agent_bridge'):self.agent_bridge.set_service(self.automation_service)
            self.autosave = AutoSaveManager(scene, keep=int(self.preferences.get('autosave.snapshots', 10)))
            self.asset_library = self._make_asset_library(); self.template_library = TemplateLibrary(scene_root(self.scene) / '.oled' / 'templates.json'); self.selection_model.clear(); self.selected_ids=[]; self.selected_id=None; self._last_frame_signature=None
            self._configure_state_controls(); self._rebuild_elements(); self._scan_assets(); self._scan_fonts(); self.retranslate_ui(); self.refresh_all(keep_selection=True); self._capture_saved_baseline()

        def _capture_saved_baseline(self):
            self._saved_scene_snapshot = deepcopy(self.scene)
            try: self._saved_frame = self.session.render().framebuffer
            except Exception: self._saved_frame = None

        # ---------- UI ----------
        def _build_ui(self):
            self.setWindowTitle(APP_TITLE); self.resize(1500, 920); self.setMinimumSize(900, 620)
            icon_path=Path(__file__).resolve().parent/'branding'/'monooled_studio.ico'
            if icon_path.exists(): self.setWindowIcon(QIcon(str(icon_path)))
            root = QWidget(self); root.setObjectName('AppRoot'); self.setCentralWidget(root)
            root_layout = QVBoxLayout(root); root_layout.setContentsMargins(8,6,8,6); root_layout.setSpacing(6)

            # Compact professional-editor command bar. Low-frequency actions remain
            # available from menus / command palette instead of competing with the canvas.
            header = QWidget(); header.setObjectName('EditorCommandBar'); header_row=QHBoxLayout(header); header_row.setContentsMargins(6,2,6,2); header_row.setSpacing(6)
            titles=QVBoxLayout(); titles.setSpacing(0); self.hero_title=QLabel(); self.hero_title.setObjectName('PanelTitle'); self.hero_subtitle=QLabel(); self.hero_subtitle.setObjectName('Muted'); titles.addWidget(self.hero_title); titles.addWidget(self.hero_subtitle); header_row.addLayout(titles)
            header_row.addStretch(1)
            self.pixel_status=StatusPill(); header_row.addWidget(self.pixel_status)
            self.header_design=QPushButton('Design'); self.header_design.setObjectName('PrimaryButton'); self.header_design.clicked.connect(lambda:self.set_workspace_mode(WorkspaceMode.DESIGN)); self.header_design.setEnabled(False)
            self.header_pixel=QPushButton(); self.header_pixel.setObjectName('SecondaryButton'); self.header_pixel.clicked.connect(self.open_pixel_studio)
            self.header_review=QPushButton('Review'); self.header_review.setObjectName('SecondaryButton'); self.header_review.clicked.connect(lambda:self.set_workspace_mode(WorkspaceMode.REVIEW))
            header_row.addWidget(self.header_design); header_row.addWidget(self.header_pixel); header_row.addWidget(self.header_review)
            self.header_project=QPushButton(); self.header_project.setObjectName('SecondaryButton'); self.header_project.clicked.connect(self.open_project_dialog)
            self.header_save=QPushButton(); self.header_save.setObjectName('SecondaryButton'); self.header_save.clicked.connect(self.route_save)
            self.header_validate=QPushButton(); self.header_validate.setObjectName('SecondaryButton'); self.header_validate.clicked.connect(self.batch_validate)
            self.header_handoff=QPushButton(); self.header_handoff.setObjectName('PrimaryButton'); self.header_handoff.clicked.connect(self.export_handoff)
            self.header_diagnostics=QToolButton(); self.header_diagnostics.setObjectName('GhostButton'); self.header_diagnostics.clicked.connect(self.toggle_diagnostics)
            self.header_settings=QToolButton(); self.header_settings.setObjectName('GhostButton'); self.header_settings.setText('⚙'); self.header_settings.clicked.connect(self.open_preferences); self.header_settings.setToolTip('Preferences (Ctrl+,)')
            self.header_agent=QToolButton(); self.header_agent.setObjectName('GhostButton'); self.header_agent.setText('AI'); self.header_agent.setToolTip('Code AI Agent Bridge'); self.header_agent.clicked.connect(self.toggle_agent_bridge)
            for w in (self.header_project,self.header_save,self.header_validate,self.header_handoff,self.header_diagnostics,self.header_agent,self.header_settings): header_row.addWidget(w)
            root_layout.addWidget(header)
            self.editor_tabs=QTabWidget(); self.editor_tabs.setObjectName('WorkspaceTabs'); self.editor_tabs.setTabsClosable(True); self.editor_tabs.setMovable(True); self.editor_tabs.currentChanged.connect(self._editor_tab_changed); self.editor_tabs.tabCloseRequested.connect(self._close_editor_tab); root_layout.addWidget(self.editor_tabs,1)

            self.vertical_splitter=QSplitter(Qt.Vertical); self.vertical_splitter.setChildrenCollapsible(True)
            self.workspace_splitter=QSplitter(Qt.Horizontal); self.workspace_splitter.setChildrenCollapsible(True)

            # LEFT — navigation/library rail. This collapses before canvas space is sacrificed.
            self.left_card=ProfessionalPanel(); self.left_card.setObjectName('ProfessionalPanel'); self.left_tabs=QTabWidget(); self.left_card.body.addWidget(self.left_tabs,1)
            screens_page=QWidget(); sl=QVBoxLayout(screens_page); sl.setContentsMargins(0,0,0,0); sl.setSpacing(6); self.screen_list=QListWidget(); self.screen_list.currentItemChanged.connect(self._screen_changed); sl.addWidget(self.screen_list,1)
            srow=QGridLayout(); srow.setSpacing(4); self.screen_new=QPushButton(); self.screen_new.clicked.connect(self.new_screen); self.screen_duplicate=QPushButton(); self.screen_duplicate.clicked.connect(self.duplicate_screen); self.screen_delete=QPushButton(); self.screen_delete.clicked.connect(self.delete_screen); srow.addWidget(self.screen_new,0,0); srow.addWidget(self.screen_duplicate,0,1); srow.addWidget(self.screen_delete,1,0,1,2); sl.addLayout(srow); self.left_tabs.addTab(screens_page,'')
            elements_page=QWidget(); el=QVBoxLayout(elements_page); el.setContentsMargins(0,0,0,0); el.setSpacing(6); self.element_list=QListWidget(); self.element_list.setSelectionMode(QAbstractItemView.ExtendedSelection); self.element_list.itemSelectionChanged.connect(self._element_selection_changed); el.addWidget(self.element_list,1)
            erow=QGridLayout(); erow.setSpacing(4); self.add_button=QPushButton(); self.add_button.clicked.connect(self.add_placeholder); self.assign_button=QPushButton(); self.assign_button.clicked.connect(self.assign_bitmap); self.delete_button=QPushButton(); self.delete_button.setObjectName('DangerButton'); self.delete_button.clicked.connect(self.remove_selected); erow.addWidget(self.add_button,0,0); erow.addWidget(self.assign_button,0,1); erow.addWidget(self.delete_button,1,0,1,2); el.addLayout(erow); self.left_tabs.addTab(elements_page,'')
            assets_page=QWidget(); al=QVBoxLayout(assets_page); al.setContentsMargins(0,0,0,0); al.setSpacing(6); self.asset_search=QLineEdit(); self.asset_search.textChanged.connect(self._filter_assets); self.asset_list=QListWidget(); self.asset_list.itemDoubleClicked.connect(self.place_asset); al.addWidget(self.asset_search); al.addWidget(self.asset_list,1); arow=QHBoxLayout(); arow.setSpacing(4); self.asset_import=QPushButton(); self.asset_import.clicked.connect(self.import_asset); self.asset_rescan=QPushButton(); self.asset_rescan.clicked.connect(self._scan_assets); arow.addWidget(self.asset_import); arow.addWidget(self.asset_rescan); al.addLayout(arow); self.left_tabs.addTab(assets_page,'')
            fonts_page=QWidget(); fl=QVBoxLayout(fonts_page); fl.setContentsMargins(0,0,0,0); fl.setSpacing(6); self.font_list=QListWidget(); self.font_list.itemDoubleClicked.connect(lambda _item:self.open_font_lab()); fl.addWidget(self.font_list,1); frow=QHBoxLayout(); self.font_new=QPushButton('New Font'); self.font_new.clicked.connect(self.new_font_pack); self.font_open=QPushButton('Open Font'); self.font_open.clicked.connect(self.open_font_lab); self.font_rescan=QPushButton('Rescan'); self.font_rescan.clicked.connect(self._scan_fonts); frow.addWidget(self.font_new); frow.addWidget(self.font_open); frow.addWidget(self.font_rescan); fl.addLayout(frow); self.left_tabs.addTab(fonts_page,'Fonts')
            self.workspace_splitter.addWidget(self.left_card)

            # CENTER — canvas-first workspace. No dashboard card/shadow chrome.
            self.canvas_card=ProfessionalPanel(); self.canvas_card.setObjectName('CanvasWorkspace')
            tools=QHBoxLayout(); tools.setSpacing(5); self.frame_status=StatusPill(); tools.addWidget(self.frame_status); tools.addStretch(1)
            self.zoom_label=QLabel(); self.zoom_label.setObjectName('Muted'); self.zoom_combo=QComboBox(); self.zoom_combo.addItem('Auto','auto'); [self.zoom_combo.addItem(f'{z}×',z) for z in ZOOM_LEVELS]; self.zoom_combo.currentIndexChanged.connect(self._zoom_changed)
            self.grid_check=QCheckBox(); self.grid_check.setChecked(True); self.bounds_check=QCheckBox(); self.bounds_check.setChecked(True); self.ruler_check=QCheckBox(); self.ruler_check.setChecked(True); self.zones_check=QCheckBox(); self.zones_check.setChecked(False)
            self.grid_check.toggled.connect(self._overlay_changed); self.bounds_check.toggled.connect(self._overlay_changed); self.ruler_check.toggled.connect(self._overlay_changed); self.zones_check.toggled.connect(self._overlay_changed)
            self.snap_combo=QComboBox(); [self.snap_combo.addItem(v,g) for v,g in [('Off',0),('1 px',1),('2 px',2),('4 px',4),('8 px',8)]]
            for w in (self.zoom_label,self.zoom_combo,self.grid_check,self.bounds_check,self.ruler_check,self.zones_check,self.snap_combo): tools.addWidget(w)
            self.canvas_card.body.addLayout(tools)
            context=QHBoxLayout(); context.setSpacing(4); self.context_label=QLabel(); self.context_label.setObjectName('Muted'); context.addWidget(self.context_label); context.addStretch(1)
            self.context_pixel=QPushButton(); self.context_pixel.setObjectName('SecondaryButton'); self.context_pixel.clicked.connect(self.open_pixel_studio); self.context_duplicate=QPushButton(); self.context_duplicate.setObjectName('SecondaryButton'); self.context_duplicate.clicked.connect(self.duplicate_selected_elements); self.context_lock=QPushButton(); self.context_lock.setObjectName('SecondaryButton'); self.context_lock.clicked.connect(self.toggle_selected_lock); context.addWidget(self.context_pixel); context.addWidget(self.context_duplicate); context.addWidget(self.context_lock); self.canvas_card.body.addLayout(context)
            self.canvas=OLEDCanvas(); self.canvas.selectionChanged.connect(self._canvas_selection_changed); self.canvas.elementMoved.connect(self._canvas_move); self.canvas.dragFinished.connect(self._finish_canvas_drag); self.canvas.pixelHovered.connect(self._pixel_hovered)
            self.canvas_scroll=QScrollArea(); self.canvas_scroll.setWidgetResizable(False); self.canvas_scroll.setFrameShape(QFrame.NoFrame); self.canvas_scroll.setWidget(self.canvas); self.canvas_card.body.addWidget(self.canvas_scroll,1)
            self.canvas_hint=QLabel(); self.canvas_hint.setObjectName('Muted'); self.canvas_hint.setWordWrap(True); self.canvas_card.body.addWidget(self.canvas_hint)
            self.workspace_splitter.addWidget(self.canvas_card)

            # RIGHT — contextual inspector. Low-frequency state/canvas controls live
            # behind a separate State tab instead of permanently consuming height.
            self.inspector_tabs=QTabWidget(); self.inspector_tabs.setMinimumWidth(260)
            self.inspector_page=QScrollArea(); self.inspector_page.setWidgetResizable(True); self.inspector_page.setObjectName('InspectorRoot')
            inspector_inner=QWidget(); inspector_inner.setObjectName('InspectorRoot'); self.inspector_layout=QVBoxLayout(inspector_inner); self.inspector_layout.setContentsMargins(4,4,4,4); self.inspector_layout.setSpacing(6)
            self.properties_card=ProfessionalPanel(); form=QFormLayout(); form.setVerticalSpacing(6); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            self.id_edit=QLineEdit(); self.id_edit.setReadOnly(True); self.type_edit=QLineEdit(); self.type_edit.setReadOnly(True); self.resource_edit=QLineEdit(); self.resource_edit.setReadOnly(True); self.prop_id_label=QLabel(); self.prop_type_label=QLabel(); self.prop_asset_label=QLabel(); form.addRow(self.prop_id_label,self.id_edit); form.addRow(self.prop_type_label,self.type_edit)
            geom_widget=QWidget(); geom_grid=QGridLayout(geom_widget); geom_grid.setContentsMargins(0,0,0,0); geom_grid.setHorizontalSpacing(6); geom_grid.setVerticalSpacing(4); self.geom_spins={}
            for index,key in enumerate(('x','y','w','h')):
                row=index // 2; col=(index % 2) * 2; label=QLabel(key.upper()); label.setObjectName('Muted'); spin=QSpinBox(); spin.setRange(-8192 if key in ('x','y') else 1,8192); spin.valueChanged.connect(lambda value,field=key:self._apply_geometry_live(field,value)); spin.editingFinished.connect(self._finish_geometry_edit); self.geom_spins[key]=spin; geom_grid.addWidget(label,row,col); geom_grid.addWidget(spin,row,col+1)
            form.addRow(geom_widget); form.addRow(self.prop_asset_label,self.resource_edit); self.properties_card.body.addLayout(form)
            flags=QHBoxLayout(); self.lock_check=QCheckBox(); self.lock_check.toggled.connect(self._lock_changed); self.hidden_check=QCheckBox(); self.hidden_check.toggled.connect(self._hidden_changed); flags.addWidget(self.lock_check); flags.addWidget(self.hidden_check); flags.addStretch(1); self.properties_card.body.addLayout(flags); self.inspector_layout.addWidget(self.properties_card)

            self.align_card=ProfessionalPanel(); self.align_reference_combo=QComboBox(); self.align_reference_combo.addItem(self.tr('align.selection_bounds'),'selection'); self.align_reference_combo.addItem(self.tr('align.primary'),'primary'); self.align_reference_combo.addItem(self.tr('align.canvas'),'canvas'); self.align_card.body.addWidget(self.align_reference_combo); ag=QGridLayout(); ag.setSpacing(4); self.align_buttons={}
            for idx,(key,mode) in enumerate([('left','left'),('center_h','hcenter'),('right','right'),('top','top'),('center_v','vcenter'),('bottom','bottom')]):
                b=QPushButton(); b.clicked.connect(lambda _=False,m=mode:self.align_selected(m)); self.align_buttons[key]=b; ag.addWidget(b,idx//3,idx%3)
            self.distribute_h=QPushButton(); self.distribute_h.clicked.connect(lambda:self.distribute_selected('horizontal')); self.distribute_v=QPushButton(); self.distribute_v.clicked.connect(lambda:self.distribute_selected('vertical')); ag.addWidget(self.distribute_h,2,0); ag.addWidget(self.distribute_v,2,1); self.snap_button=QPushButton(); self.snap_button.clicked.connect(self.snap_selected); ag.addWidget(self.snap_button,2,2); self.align_card.body.addLayout(ag); self.measure_label=QLabel(); self.measure_label.setObjectName('Muted'); self.measure_label.setWordWrap(True); self.align_card.body.addWidget(self.measure_label); self.inspector_layout.addWidget(self.align_card); self.inspector_layout.addStretch(1)
            self.inspector_page.setWidget(inspector_inner); self.inspector_tabs.addTab(self.inspector_page,'')

            self.state_page=QScrollArea(); self.state_page.setWidgetResizable(True); state_inner=QWidget(); state_inner.setObjectName('InspectorRoot'); self.state_layout=QVBoxLayout(state_inner); self.state_layout.setContentsMargins(4,4,4,4); self.state_layout.setSpacing(6)
            self.canvas_config_panel=ProfessionalPanel(); self.canvas_config_card=self.canvas_config_panel; cf=QFormLayout(); cf.setVerticalSpacing(6); self.canvas_preset_combo=QComboBox(); self.canvas_preset_combo.addItems([*CANVAS_PRESETS.keys(),'Custom']); self.canvas_preset_combo.currentTextChanged.connect(self._canvas_preset_changed); self.canvas_width_spin=QSpinBox(); self.canvas_width_spin.setRange(16,4096); self.canvas_height_spin=QSpinBox(); self.canvas_height_spin.setRange(8,2048); self.canvas_height_spin.setSingleStep(8); self.canvas_apply_button=QPushButton(); self.canvas_apply_button.clicked.connect(self.apply_canvas_size); self.canvas_size_labels={'preset':QLabel(),'width':QLabel(),'height':QLabel()}; cf.addRow(self.canvas_size_labels['preset'],self.canvas_preset_combo); cf.addRow(self.canvas_size_labels['width'],self.canvas_width_spin); cf.addRow(self.canvas_size_labels['height'],self.canvas_height_spin); self.canvas_config_panel.body.addLayout(cf); self.canvas_config_panel.body.addWidget(self.canvas_apply_button); self.state_layout.addWidget(self.canvas_config_panel)
            self.runtime_panel=ProfessionalPanel(); self.runtime_card=self.runtime_panel; rf=QFormLayout(); rf.setVerticalSpacing(6); self.mode_combo=QComboBox(); self.phase_combo=QComboBox(); self.battery_spin=QSpinBox(); self.seconds_spin=QSpinBox(); self.speed_combo=QComboBox(); self.speed_combo.addItems(RUN_SPEEDS); self.runtime_labels={k:QLabel() for k in ('mode','phase','battery','seconds','speed')}
            for key,w in [('mode',self.mode_combo),('phase',self.phase_combo),('battery',self.battery_spin),('seconds',self.seconds_spin),('speed',self.speed_combo)]: rf.addRow(self.runtime_labels[key],w)
            self.runtime_panel.body.addLayout(rf); rr=QHBoxLayout(); rr.setSpacing(4); self.play_button=QPushButton(); self.play_button.setObjectName('PrimaryButton'); self.play_button.clicked.connect(self.toggle_play); self.step_button=QPushButton(); self.step_button.clicked.connect(self.step_runtime); self.reset_button=QPushButton(); self.reset_button.clicked.connect(self.reset_runtime); rr.addWidget(self.play_button); rr.addWidget(self.step_button); rr.addWidget(self.reset_button); self.runtime_panel.body.addLayout(rr); self.elapsed_label=QLabel(); self.elapsed_label.setObjectName('Muted'); self.runtime_panel.body.addWidget(self.elapsed_label); self.state_layout.addWidget(self.runtime_panel); self.state_layout.addStretch(1)
            self.mode_combo.currentTextChanged.connect(lambda value:self._state_changed('mode',value)); self.phase_combo.currentIndexChanged.connect(self._phase_changed); self.battery_spin.valueChanged.connect(lambda value:self._state_changed('battery',value)); self.seconds_spin.valueChanged.connect(lambda value:self._state_changed('seconds',value)); self.speed_combo.currentTextChanged.connect(self._speed_changed)
            self.state_page.setWidget(state_inner); self.inspector_tabs.addTab(self.state_page,'')
            self.workspace_splitter.addWidget(self.inspector_tabs)
            self.vertical_splitter.addWidget(self.workspace_splitter)

            # BOTTOM — problems/diff/log drawer, collapsed by default for canvas focus.
            self.diagnostics_tabs=QTabWidget(); self.validation_card=ProfessionalPanel(); self.validation_status=StatusPill(); self.validation_list=QListWidget(); self.validation_card.body.addWidget(self.validation_status); self.validation_card.body.addWidget(self.validation_list,1); self.diff_card=ProfessionalPanel(); self.diff_status=StatusPill(); self.diff_label=QLabel(); self.diff_label.setWordWrap(True); self.diff_card.body.addWidget(self.diff_status); self.diff_card.body.addWidget(self.diff_label); self.logs_card=ProfessionalPanel(); self.log_text=QPlainTextEdit(); self.log_text.setReadOnly(True); self.log_text.document().setMaximumBlockCount(1000); self.logs_card.body.addWidget(self.log_text,1); self.diagnostics_tabs.addTab(self.validation_card,''); self.diagnostics_tabs.addTab(self.diff_card,''); self.diagnostics_tabs.addTab(self.logs_card,''); self.vertical_splitter.addWidget(self.diagnostics_tabs)
            self.scene_editor_host=QWidget(); self.scene_editor_host.setObjectName('SceneEditorHost'); scene_editor_layout=QVBoxLayout(self.scene_editor_host); scene_editor_layout.setContentsMargins(0,0,0,0); scene_editor_layout.addWidget(self.vertical_splitter)
            self.scene_editor_host.document_id='scene:active'; self.editor_tabs.addTab(self.scene_editor_host,'Designer')
            self.editor_registry.open(CallbackEditor('scene:active','Designer',save=self.save_scene,undo=self.undo,redo=self.redo,dirty=lambda:self.session.document.dirty))

            self.truth_label=QLabel(); self.truth_label.setObjectName('Muted'); self.statusBar().addWidget(self.truth_label,1)
            self.perf_label=QLabel(self.tr('performance.preview_idle')); self.perf_label.setObjectName('Muted'); self.statusBar().addPermanentWidget(self.perf_label)
            self.app_status=StatusPill(); self.statusBar().addPermanentWidget(self.app_status); self.agent_status=QLabel(self.tr('agent.off')); self.agent_status.setObjectName('Muted'); self.statusBar().addPermanentWidget(self.agent_status); self._configure_state_controls()
            self._diagnostics_open=False; self.vertical_splitter.setSizes([1000,0])

        def _build_menu(self):
            bar=self.menuBar(); self._menus['file']=bar.addMenu(''); self._menus['edit']=bar.addMenu(''); self._menus['arrange']=bar.addMenu(''); self._menus['run']=bar.addMenu(''); self._menus['view']=bar.addMenu(''); self._menus['tools']=bar.addMenu(''); self._menus['help']=bar.addMenu('')
            def action(name,menu,callback,shortcut=None):
                a=QAction(self); a.triggered.connect(callback); a.setShortcut(QKeySequence(shortcut)) if shortcut else None; menu.addAction(a); self._actions[name]=a; return a
            action('new_project',self._menus['file'],self.new_project,'Ctrl+N'); action('open_project',self._menus['file'],self.open_project_dialog,'Ctrl+Shift+O'); action('open_scene',self._menus['file'],self.open_scene_dialog,'Ctrl+O'); action('save',self._menus['file'],self.route_save,self.command_registry.shortcut('project.save')); action('handoff',self._menus['file'],self.export_handoff,'Ctrl+Shift+E'); action('export_current',self._menus['file'],self.export_current); action('export_all',self._menus['file'],self.export_all); self._menus['file'].addSeparator(); action('exit',self._menus['file'],self.close)
            action('undo',self._menus['edit'],self.route_undo,self.command_registry.shortcut('designer.undo')); action('redo',self._menus['edit'],self.route_redo,self.command_registry.shortcut('designer.redo')); action('add_placeholder',self._menus['edit'],self.add_placeholder); action('assign_bitmap',self._menus['edit'],self.assign_bitmap); action('delete',self._menus['edit'],self.remove_selected,'Delete')
            action('front',self._menus['arrange'],lambda:self._reorder_selected(True)); action('back',self._menus['arrange'],lambda:self._reorder_selected(False)); action('group',self._menus['arrange'],self.group_selected,'Ctrl+G'); action('ungroup',self._menus['arrange'],self.ungroup_selected,'Ctrl+Shift+G')
            action('play',self._menus['run'],self.toggle_play,'Space'); action('step',self._menus['run'],self.step_runtime); action('reset',self._menus['run'],self.reset_runtime); action('validate',self._menus['run'],self.batch_validate)
            action('diagnostics',self._menus['view'],self.toggle_diagnostics,'Ctrl+J'); action('design_mode',self._menus['view'],lambda:self.set_workspace_mode(WorkspaceMode.DESIGN)); action('review_mode',self._menus['view'],lambda:self.set_workspace_mode(WorkspaceMode.REVIEW)); action('toggle_navigator',self._menus['view'],self.toggle_navigator,'Ctrl+1'); action('toggle_inspector',self._menus['view'],self.toggle_inspector,'Ctrl+2'); action('canvas_only',self._menus['view'],self.toggle_canvas_only,self.command_registry.shortcut('workspace.canvas_only')); action('reset_workspace',self._menus['view'],self.reset_workspace_layout)
            action('preferences',self._menus['tools'],self.open_preferences,self.command_registry.shortcut('preferences.open')); action('pixel_studio',self._menus['tools'],self.open_pixel_studio,'Ctrl+Shift+P'); action('font_lab',self._menus['tools'],self.open_font_lab,'Ctrl+Shift+F'); action('bitmap_text',self._menus['tools'],self.insert_bitmap_text); action('agent_bridge',self._menus['tools'],self.toggle_agent_bridge); action('asset_health',self._menus['tools'],self.show_asset_health); action('save_template',self._menus['tools'],self.save_template); action('insert_template',self._menus['tools'],self.insert_template); action('convert_asset',self._menus['tools'],self.convert_asset); action('export_c_header',self._menus['tools'],self.export_c_header); action('thumbnail_wall',self._menus['tools'],self.export_thumbnail_wall); action('autosave',self._menus['tools'],lambda:self._autosave_tick(force=True)); action('restore_autosave',self._menus['tools'],self.restore_autosave); action('command_palette',self._menus['tools'],self.show_command_palette,'Ctrl+K'); action('about',self._menus['help'],self.show_about)

        def _apply_command_shortcuts(self):
            defaults=default_preferences()['shortcuts']
            custom_bindings=dict(self.preferences.get('shortcuts', {}) or {})
            accepted,rejected=self.command_registry.apply_bindings_best_effort(custom_bindings)
            if rejected:
                merged=dict(defaults); merged.update(accepted); self.preferences.data['shortcuts']=merged; self.preferences.save()
            mapping={'project.save':'save','designer.undo':'undo','designer.redo':'redo','workspace.canvas_only':'canvas_only','preferences.open':'preferences'}
            for command_id,action_name in mapping.items():
                action=self._actions.get(action_name)
                if action is not None: action.setShortcut(QKeySequence(self.command_registry.shortcut(command_id)))
            if hasattr(self,'header_settings'):
                self.header_settings.setToolTip(self.tr('action.preferences')+f" ({self.command_registry.shortcut('preferences.open')})")

        def _bind_shortcuts(self):
            self._nudge_shortcuts=[]
            for sequence,dx,dy in [('Left',-1,0),('Right',1,0),('Up',0,-1),('Down',0,1),('Shift+Left',-10,0),('Shift+Right',10,0),('Shift+Up',0,-10),('Shift+Down',0,10)]:
                sc=QShortcut(QKeySequence(sequence),self); sc.activated.connect(lambda dx=dx,dy=dy:self.nudge_selected(dx,dy)); self._nudge_shortcuts.append(sc)

        def _connect_responsive_events(self):
            self.canvas_scroll.viewport().installEventFilter(self)
            self.workspace_splitter.splitterMoved.connect(lambda *_:self._schedule_canvas_fit())
            self.vertical_splitter.splitterMoved.connect(lambda *_:self._schedule_canvas_fit())

        def eventFilter(self,obj,event):  # noqa: N802
            if obj is self.canvas_scroll.viewport() and event.type() in (QEvent.Resize,QEvent.Show): self._schedule_canvas_fit()
            return super().eventFilter(obj,event)

        def resizeEvent(self,event):  # noqa: N802
            super().resizeEvent(event); self._schedule_responsive()

        def _schedule_responsive(self): self.layout_timer.start()
        def _schedule_canvas_fit(self): QTimer.singleShot(16,self._fit_canvas_zoom)
        def _responsive_tick(self):
            runtime=getattr(self,'_runtime_preferences',None) or RuntimeSettings.from_preferences(self.preferences)
            p=plan_layout(self.width(),self.height(),runtime.density,runtime.ui_scale); wp=workspace_plan(self.width(),self.height(),self.workspace_mode); bucket=(p.left_width,p.inspector_width,wp.compact)
            if bucket!=self._layout_bucket:
                self.left_card.setVisible(wp.left_visible)
                self.workspace_splitter.setSizes([p.left_width,p.canvas_width,p.inspector_width]); self._layout_bucket=bucket
            hp=header_policy(p)
            self.hero_subtitle.setVisible(hp.show_subtitle)
            self.pixel_status.setVisible(hp.show_status)
            self.header_project.setVisible(hp.show_project)
            self.header_validate.setVisible(hp.show_validate)
            self.header_save.setVisible(hp.show_save)
            self.header_handoff.setVisible(hp.show_handoff)
            self.header_design.setVisible(not hp.compact)
            self.header_pixel.setVisible(not hp.compact)
            self.header_review.setVisible(not hp.compact)
            self.header_diagnostics.setVisible(not hp.compact)
            if self._diagnostics_open:
                total=max(1,self.vertical_splitter.height()); self.vertical_splitter.setSizes([max(300,total-p.diagnostics_height),p.diagnostics_height])
            self._fit_canvas_zoom()

        def toggle_diagnostics(self):
            self._diagnostics_open=not self._diagnostics_open; total=max(1,self.vertical_splitter.height())
            if self._diagnostics_open:
                runtime=getattr(self,'_runtime_preferences',None) or RuntimeSettings.from_preferences(self.preferences); p=plan_layout(self.width(),self.height(),runtime.density,runtime.ui_scale); self.vertical_splitter.setSizes([max(300,total-p.diagnostics_height),p.diagnostics_height])
            else: self.vertical_splitter.setSizes([total,0])
            self._schedule_canvas_fit()

        def toggle_navigator(self):
            self.left_card.setVisible(not self.left_card.isVisible()); self._schedule_canvas_fit()

        def toggle_inspector(self):
            self.inspector_tabs.setVisible(not self.inspector_tabs.isVisible()); self._schedule_canvas_fit()

        def toggle_canvas_only(self):
            active = not getattr(self, '_canvas_only', False)
            self._canvas_only = active
            if active:
                self._canvas_only_restore = (self.left_card.isVisible(), self.inspector_tabs.isVisible(), self._diagnostics_open)
                self.left_card.hide(); self.inspector_tabs.hide(); self._diagnostics_open = False; self.vertical_splitter.setSizes([max(1,self.vertical_splitter.height()),0])
            else:
                left, inspector, diagnostics = getattr(self, '_canvas_only_restore', (True, True, False))
                self.left_card.setVisible(left); self.inspector_tabs.setVisible(inspector); self._diagnostics_open = diagnostics
            self._schedule_canvas_fit()

        def reset_workspace_layout(self):
            self.settings.remove('workspaceSplitter'); self.settings.remove('verticalSplitter'); self._layout_bucket=None; self._schedule_responsive()

        def set_workspace_mode(self, mode):
            self.workspace_mode=WorkspaceMode(mode)
            review=self.workspace_mode==WorkspaceMode.REVIEW
            self.header_design.setEnabled(review); self.header_review.setEnabled(not review)
            set_button_role(self.header_design, 'SecondaryButton' if review else 'PrimaryButton'); set_button_role(self.header_review, 'PrimaryButton' if review else 'SecondaryButton')
            for widget in (self.add_button,self.assign_button,self.delete_button,self.context_pixel,self.context_duplicate,self.context_lock,self.lock_check,self.hidden_check): widget.setEnabled(not review)
            for spin in self.geom_spins.values(): spin.setEnabled(not review)
            self.align_card.setVisible(not review)
            if review:
                self._diagnostics_open=True; self.diagnostics_tabs.setCurrentIndex(1)
            self._layout_bucket=None; self._responsive_tick(); self.refresh_all(keep_selection=True)

        def show_performance_report(self):
            drag=self.profiler.summary('drag_preview'); full=self.profiler.summary('full_refresh')
            QMessageBox.information(self,self.tr('performance.title'),self.tr('performance.summary',drag_avg=drag.avg_ms,drag_max=drag.max_ms,full_avg=full.avg_ms,full_max=full.max_ms))

        # ---------- i18n ----------
        def retranslate_ui(self):
            t=self.tr; self.hero_title.setText(t('app.title')); self.hero_subtitle.setText(t('app.subtitle'))
            self.header_design.setText(t('workspace.design')); self.header_pixel.setText(t('action.pixel_studio')); self.header_review.setText(t('workspace.review')); self.header_project.setText(t('action.open_project')); self.header_save.setText(t('action.save')); self.header_validate.setText(t('action.batch_validate')); self.header_handoff.setText(t('action.handoff')); self.header_diagnostics.setText(t('action.diagnostics')); self.header_settings.setToolTip(t('action.preferences')+' (Ctrl+,)')
            self.left_card.set_title(t('panel.workspace')); self.left_tabs.setTabText(0,t('panel.screens')); self.left_tabs.setTabText(1,t('panel.elements')); self.left_tabs.setTabText(2,t('panel.assets')); self.left_tabs.setTabText(3,t('panel.fonts')); self.font_new.setText(t('action.new_font')); self.font_open.setText(t('action.open_font')); self.font_rescan.setText(t('asset.rescan'))
            self.inspector_tabs.setTabText(0,t('panel.properties')); self.inspector_tabs.setTabText(1,t('panel.runtime'))
            self.screen_new.setText(t('action.new_screen')); self.screen_duplicate.setText(t('action.duplicate')); self.screen_delete.setText(t('action.delete')); self.add_button.setText(t('action.add_placeholder')); self.assign_button.setText(t('action.assign_bitmap')); self.delete_button.setText(t('action.delete')); self.asset_search.setPlaceholderText(t('asset.search')); self.asset_import.setText(t('asset.import')); self.asset_rescan.setText(t('asset.rescan'))
            self.canvas_card.set_title(t('panel.canvas')); self.context_pixel.setText(t('action.pixel_studio')); self.context_duplicate.setText(t('action.duplicate')); self.context_lock.setText(t('property.locked')); self.canvas_card.set_subtitle(t('canvas.production',width=self.scene['canvas']['w'],height=self.scene['canvas']['h'])); self.zoom_label.setText(t('state.zoom')); self.grid_check.setText(t('toggle.grid')); self.bounds_check.setText(t('toggle.bounds')); self.ruler_check.setText(t('toggle.rulers')); self.zones_check.setText(t('toggle.zones')); self.canvas_hint.setText(t('canvas.overlay_hint'))
            self.properties_card.set_title(t('panel.properties')); self.prop_id_label.setText(t('property.id')); self.prop_type_label.setText(t('property.type')); self.prop_asset_label.setText(t('property.asset')); self.lock_check.setText(t('property.locked')); self.hidden_check.setText(t('property.hidden'))
            self.align_card.set_title(t('panel.arrange')); self.align_reference_combo.setItemText(self.align_reference_combo.findData('selection'),t('align.selection_bounds')); self.align_reference_combo.setItemText(self.align_reference_combo.findData('primary'),t('align.primary')); self.align_reference_combo.setItemText(self.align_reference_combo.findData('canvas'),t('align.canvas')); labels={'left':'align.left','center_h':'align.hcenter','right':'align.right','top':'align.top','center_v':'align.vcenter','bottom':'align.bottom'}
            for k,b in self.align_buttons.items(): b.setText(t(labels[k]))
            self.distribute_h.setText(t('align.distribute_h')); self.distribute_v.setText(t('align.distribute_v')); self.snap_button.setText(t('align.snap'))
            self.canvas_config_card.set_title(t('panel.canvas_settings')); self.canvas_size_labels['preset'].setText(t('canvas.preset')); self.canvas_size_labels['width'].setText(t('canvas.width')); self.canvas_size_labels['height'].setText(t('canvas.height')); self.canvas_apply_button.setText(t('action.apply_canvas'))
            self.runtime_card.set_title(t('panel.runtime')); [self.runtime_labels[k].setText(t(f'state.{k}')) for k in self.runtime_labels]; self.step_button.setText(t('action.step')); self.reset_button.setText(t('action.reset')); self._update_play_button()
            self.validation_card.set_title(t('panel.validation')); self.diff_card.set_title(t('panel.diff')); self.logs_card.set_title(t('panel.logs')); self.diagnostics_tabs.setTabText(0,t('panel.validation')); self.diagnostics_tabs.setTabText(1,t('panel.diff')); self.diagnostics_tabs.setTabText(2,t('panel.logs')); self.truth_label.setText(t('footer.truth'))
            if not self.profiler.summary('drag_preview').count:self.perf_label.setText(t('performance.preview_idle'))
            menu_names={'file':'menu.file','edit':'menu.edit','arrange':'menu.arrange','run':'menu.run','view':'menu.view','tools':'menu.tools','help':'menu.help'}
            for k,v in menu_names.items(): self._menus[k].setTitle(t(v))
            action_keys={'new_project':'action.new_project','open_project':'action.open_project','open_scene':'action.open_scene','save':'action.save','handoff':'action.handoff','export_current':'action.export_current','export_all':'action.export_all','exit':'action.exit','undo':'action.undo','redo':'action.redo','add_placeholder':'action.add_placeholder','assign_bitmap':'action.assign_bitmap','delete':'action.delete','front':'action.front','back':'action.back','group':'action.group','ungroup':'action.ungroup','play':'action.play','step':'action.step','reset':'action.reset','validate':'action.batch_validate','diagnostics':'action.diagnostics','design_mode':'workspace.design','review_mode':'workspace.review','toggle_navigator':'view.navigator','toggle_inspector':'view.inspector','canvas_only':'view.canvas_only','reset_workspace':'view.reset_workspace','preferences':'action.preferences','asset_health':'action.asset_health','save_template':'action.save_template','insert_template':'action.insert_template','convert_asset':'action.convert_asset','export_c_header':'action.export_c_header','thumbnail_wall':'action.thumbnail_wall','autosave':'action.autosave','restore_autosave':'action.restore_autosave','command_palette':'command.title','pixel_studio':'action.pixel_studio','font_lab':'action.open_font','bitmap_text':'action.bitmap_text','agent_bridge':'action.agent_bridge','about':'action.about'}
            for name,key in action_keys.items(): self._actions[name].setText(t(key))
            self._rebuild_phase_combo(); self._sync_runtime_controls(); self._retranslate_validation_panel(); self._update_measurement(); self._schedule_responsive()

        def change_language(self,language):
            if language not in SUPPORTED_LANGUAGES:return
            self.preferences.set('language',language)
            self.apply_preferences()
            self.logger.log('LANGUAGE',language=language)

        def _apply_status_theme(self,theme):
            for name in ('pixel_status','frame_status','validation_status','diff_status','app_status'):
                widget=getattr(self,name,None)
                if widget is not None and hasattr(widget,'set_theme'): widget.set_theme(theme)

        def _sync_canvas_preferences(self,runtime):
            if hasattr(self,'grid_check'):
                for widget,value in ((self.grid_check,runtime.grid),(self.bounds_check,runtime.bounds),(self.ruler_check,runtime.rulers),(self.zones_check,runtime.zones)):
                    blocker=QSignalBlocker(widget); widget.setChecked(bool(value)); del blocker
                idx=self.snap_combo.findData(runtime.snap)
                if idx>=0:
                    blocker=QSignalBlocker(self.snap_combo); self.snap_combo.setCurrentIndex(idx); del blocker
            if hasattr(self,'canvas'):
                self.canvas.set_overlays(grid=runtime.grid,bounds=runtime.bounds,rulers=runtime.rulers)
                self.canvas.set_zones(self.scene.get('zones',[]) if runtime.zones else [])
                self.canvas.update()

        def apply_preferences(self, *_args, initial=False):
            runtime=RuntimeSettings.from_preferences(self.preferences)
            previous=self._runtime_preferences
            delta=(PreferenceDelta(previous,runtime,frozenset({'language','theme','metrics','canvas','pixel','autosave','performance','shortcuts','startup'}))
                   if previous is None else PreferenceDelta.between(previous,runtime))
            system_dark=self.system_theme.is_dark() if hasattr(self,'system_theme') else False
            theme=resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=system_dark)
            resolved_theme_changed=theme!=self._resolved_theme
            self._runtime_preferences=runtime; self._resolved_theme=theme
            if not initial and not delta.effects and not resolved_theme_changed:return
            if delta.language_changed or delta.appearance_changed or resolved_theme_changed: PopupManager.close_all()

            # Appearance is expensive. Global Qt repolish only when the resolved
            # stylesheet signature actually changes (Theme Mode may change while
            # resolving to the same visual theme).
            style_signature=(theme,runtime.density,runtime.ui_scale)
            style_changed=style_signature!=self._applied_style_signature
            if initial or style_changed:
                app=QApplication.instance()
                if app is not None: app.setStyleSheet(build_stylesheet(theme,runtime.density,ui_scale=runtime.ui_scale))
                self._applied_style_signature=style_signature
                if hasattr(self,'canvas'): self.canvas.set_theme(theme)
                self._apply_status_theme(theme)
                if self._preferences_window is not None:
                    try:self._preferences_window.apply_runtime_settings(runtime)
                    except RuntimeError:self._preferences_window=None
                self._schedule_responsive()

            # Language is independent from renderer/theme. Never refresh product truth here.
            if initial or delta.language_changed:
                language=runtime.language
                if language in SUPPORTED_LANGUAGES and language!=self.tr.language:self.tr.set_language(language)
                if self._preferences_window is not None:
                    try:self._preferences_window.set_language(language)
                    except RuntimeError:self._preferences_window=None
                if not initial:self.retranslate_ui()

            if initial or delta.canvas_changed:self._sync_canvas_preferences(runtime)

            if initial or delta.performance_changed:
                limit=runtime.undo_history; self.session.max_history=limit; self.session._undo=self.session._undo[-limit:]; self.session._redo=self.session._redo[-limit:]
                self.asset_library.set_cache_budget_mb(runtime.asset_cache_mb)
                self.perf_label.setVisible(runtime.performance_overlay)

            if initial or delta.autosave_changed:
                self.autosave_timer.setInterval(runtime.autosave_interval_ms); self.autosave.set_keep(runtime.autosave_snapshots)
                if runtime.autosave_enabled:
                    if not self.autosave_timer.isActive():self.autosave_timer.start()
                else:self.autosave_timer.stop()

            if initial or delta.shortcuts_changed:self._apply_command_shortcuts()

            # V8.1: all embedded editors receive the same delta; no legacy top-level
            # Pixel window list remains as a second source of preference truth.
            if hasattr(self,'editor_registry'):
                self.editor_registry.apply_runtime_delta(delta)

        def open_preferences(self):
            if self._preferences_window is None:
                self._preferences_window=PreferencesWindow(self.preferences,self.tr,parent=None)
                self._preferences_window.preferencesChanged.connect(self.apply_preferences)
                if hasattr(self._preferences_window,'clearAssetCacheRequested'): self._preferences_window.clearAssetCacheRequested.connect(self._clear_asset_cache)
                if hasattr(self._preferences_window,'resetWorkspaceRequested'): self._preferences_window.resetWorkspaceRequested.connect(self.reset_workspace_layout)
            self._preferences_window.show(); self._preferences_window.raise_(); self._preferences_window.activateWindow()

        def _clear_asset_cache(self):
            self.asset_library.clear_cache(); self._scan_assets(); self.app_status.setText(self.tr('status.asset_normalized')); self.app_status.set_status('success')

        # ---------- project/screens/assets ----------
        def open_project_dialog(self):
            path,_=QFileDialog.getOpenFileName(self,self.tr('dialog.open_project'),str(ROOT),'OLED Project (*.oled.json);;JSON (*.json)')
            if path:self._open_project(Path(path))
        def _open_project(self,path:Path):
            project=ProjectWorkspace.load(path); self.project=project; scene=_decorate_project_scene(load_scene(project.screen_path(project.active_screen),project_root=project.root),project); self._reset_session(scene); self._rebuild_screens(); self.preferences.set('startup.last_project',str(project.path)); self.logger.log('PROJECT_OPEN',path=str(path))
        def new_project(self):
            root=QFileDialog.getExistingDirectory(self,self.tr('dialog.new_project')); 
            if not root:return
            name,ok=QInputDialog.getText(self,self.tr('dialog.new_project'),self.tr('project.name'))
            if ok and name.strip(): self.project=create_project(root,name=name.strip()); self._open_project(self.project.path)
        def _rebuild_screens(self):
            blocker=QSignalBlocker(self.screen_list); self.screen_list.clear()
            if self.project:
                for ref in self.project.screens:
                    item=QListWidgetItem(ref.label); item.setData(Qt.UserRole,ref.id); self.screen_list.addItem(item)
                    if ref.id==self.project.active_screen:self.screen_list.setCurrentItem(item)
            else:
                item=QListWidgetItem(Path(self.scene.get('_path','scene')).stem); item.setData(Qt.UserRole,'__scene__'); self.screen_list.addItem(item); self.screen_list.setCurrentItem(item)
            del blocker
        def _screen_changed(self,current,_prev):
            if not current or not self.project:return
            sid=str(current.data(Qt.UserRole));
            if sid==self.project.active_screen:return
            if self.session.document.dirty:
                choice=QMessageBox.question(self,self.tr('dialog.unsaved_title'),self.tr('dialog.unsaved_message'),QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
                if choice==QMessageBox.Cancel:
                    self._rebuild_screens(); return
                if choice==QMessageBox.Save:
                    self.save_scene()
                    if self.session.document.dirty:
                        self._rebuild_screens(); return
            self.project.set_active_screen(sid); self.project.save(); self._reset_session(_decorate_project_scene(load_scene(self.project.screen_path(sid),project_root=self.project.root),self.project))
        def new_screen(self):
            if not self.project:return self._show_error(self.tr('project.required'))
            sid,ok=QInputDialog.getText(self,self.tr('action.new_screen'),self.tr('screen.id'))
            if ok and sid.strip():
                try:self.project.add_screen(sid.strip(),label=sid.strip(),canvas=(int(self.scene['canvas']['w']),int(self.scene['canvas']['h']))); self._rebuild_screens()
                except Exception as exc:self._show_error(str(exc))
        def duplicate_screen(self):
            if not self.project:return
            sid=self.project.active_screen; new_id,ok=QInputDialog.getText(self,self.tr('action.duplicate'),self.tr('screen.id'),text=sid+'_copy')
            if ok and new_id.strip():
                try:self.project.duplicate_screen(sid,new_id=new_id.strip(),label=new_id.strip()); self._rebuild_screens()
                except Exception as exc:self._show_error(str(exc))
        def delete_screen(self):
            if not self.project:return
            try:self.project.remove_screen(self.project.active_screen); self._rebuild_screens(); self._reset_session(_decorate_project_scene(load_scene(self.project.screen_path(self.project.active_screen),project_root=self.project.root),self.project))
            except Exception as exc:self._show_error(str(exc))

        def open_scene_dialog(self):
            path,_=QFileDialog.getOpenFileName(self,self.tr('dialog.open_scene'),str(scene_root(self.scene)),'Scene JSON (*.json);;All Files (*)')
            if path:self.project=None; self._reset_session(load_scene(Path(path)))

        def _sync_asset_directory_watchers(self):
            wanted=[]
            for rel in self.asset_library.asset_dirs:
                path=(self.asset_library.root/rel).resolve()
                if path.exists() and path.is_dir():
                    wanted.append(str(path))
                    wanted.extend(str(p.resolve()) for p in path.rglob('*') if p.is_dir())
            current=set(self.asset_watcher.directories()); desired=set(wanted)
            remove=list(current-desired); add=list(desired-current)
            if remove:self.asset_watcher.removePaths(remove)
            if add:self.asset_watcher.addPaths(add)

        def _scan_assets(self):
            try:
                self.asset_library.scan(); self._sync_asset_directory_watchers(); self._filter_assets(self.asset_search.text() if hasattr(self,'asset_search') else '')
            except Exception as exc:
                if hasattr(self,'app_status'): self.app_status.setText(str(exc)); self.app_status.set_status('warning')
        def _filter_assets(self,query):
            if not hasattr(self,'asset_list'):return
            self.asset_list.clear()
            for entry in self.asset_library.search(query):
                label=f'{Path(entry.rel_path).name}   {entry.width}×{entry.height}' if entry.valid else f'⚠ {Path(entry.rel_path).name}'
                item=QListWidgetItem(label); item.setData(Qt.UserRole,entry.rel_path); item.setToolTip(entry.rel_path if entry.valid else entry.error); self.asset_list.addItem(item)
        def import_asset(self):
            path,_=QFileDialog.getOpenFileName(self,self.tr('asset.import'),str(Path.home()),self.tr('dialog.image_filter'))
            if path:
                try:entry=self.asset_library.import_asset(path); self._scan_assets(); self.app_status.setText(self.tr('status.asset_imported')); self.app_status.set_status('success'); return entry
                except Exception as exc:self._show_error(str(exc))
        def place_asset(self,item=None):
            item=item or self.asset_list.currentItem();
            if not item:return
            rel=str(item.data(Qt.UserRole)); path=scene_root(self.scene)/rel
            if self.selected_id and self.session.document.element(self.selected_id).get('type')=='placeholder':
                try:self.session.assign_bitmap(self.selected_id,path); self._rebuild_elements(); self.refresh_all(keep_selection=True); return
                except Exception as exc:return self._show_error(str(exc))
            stem=Path(rel).stem; eid=stem; existing={str(e.get('id')) for e in self.scene.get('elements',[])}; i=2
            while eid in existing:eid=f'{stem}_{i}'; i+=1
            try:
                self.session.add_placeholder(eid,x=0,y=0,w=1,h=1); self.session.assign_bitmap(eid,path); self.selected_ids=[eid]; self.selected_id=eid; self._rebuild_elements(); self.refresh_all(keep_selection=True)
            except Exception as exc:self._show_error(str(exc))
        def _asset_directory_changed(self,_path): self._scan_assets()
        def show_asset_health(self):
            used=set()
            if hasattr(self,'last_render'):
                for p in self.last_render.used_files:
                    try:used.add(Path(p).resolve().relative_to(scene_root(self.scene)).as_posix())
                    except ValueError:pass
            h=self.asset_library.health_report(used_paths=used); QMessageBox.information(self,self.tr('action.asset_health'),self.tr('asset.health_summary',count=len(self.asset_library.entries),duplicates=len(h.duplicates),unused=len(h.unused),invalid=len(h.invalid)))

        def save_template(self):
            if not self.selected_ids:
                return
            name,ok=QInputDialog.getText(self,self.tr('action.save_template'),self.tr('template.name'))
            if not ok or not name.strip():
                return
            elements=[deepcopy(self.session.document.element(eid)) for eid in self.selected_ids]
            try:
                self.template_library.save_template(name.strip(),elements)
                self.app_status.setText(self.tr('template.saved',name=name.strip())); self.app_status.set_status('success')
            except Exception as exc:self._show_error(str(exc))

        def insert_template(self):
            names=self.template_library.names()
            if not names:
                return self._show_error(self.tr('template.none'))
            name,ok=QInputDialog.getItem(self,self.tr('action.insert_template'),self.tr('template.name'),names,0,False)
            if not ok:return
            prefix,ok=QInputDialog.getText(self,self.tr('action.insert_template'),self.tr('template.prefix'),text=f'{name}_')
            if not ok:return
            try:
                items=self.template_library.instantiate(name,prefix=prefix,offset=(0,0)); ids=self.session.add_elements(items,label='template_insert'); self.selected_ids=ids; self.selected_id=ids[-1] if ids else None; self._rebuild_elements(); self.refresh_all(keep_selection=True)
            except Exception as exc:self._show_error(str(exc))

        def convert_asset(self):
            source,_=QFileDialog.getOpenFileName(self,self.tr('action.convert_asset'),str(scene_root(self.scene)),self.tr('dialog.image_filter'))
            if not source:return
            target_dir=scene_root(self.scene)/'assets'/'converted'; target=target_dir/(Path(source).stem+'.png')
            try:
                convert_bitmap(source,target)
                if self.project and 'assets' not in self.project.data.setdefault('asset_dirs',[]):self.project.data['asset_dirs'].append('assets'); self.project.save()
                self.asset_library=self._make_asset_library(); self._scan_assets(); self.app_status.setText(self.tr('asset.converted',path=str(target))); self.app_status.set_status('success')
            except Exception as exc:self._show_error(str(exc))

        def _project_symbol(self):
            raw=str(self.scene.get('product') or (self.project.data.get('name') if self.project else '') or 'monooled_project').strip().lower()
            clean=''.join(ch if ch.isalnum() else '_' for ch in raw).strip('_')
            return clean or 'monooled_project'

        def export_c_header(self):
            path,_=QFileDialog.getSaveFileName(self,self.tr('action.export_c_header'),str(scene_root(self.scene)/'exports'/'current_frame.h'),'C Header (*.h)')
            if not path:return
            try:
                write_c_header(self.session.render().framebuffer,path,name=self._project_symbol()+'_oled_frame'); self.app_status.setText(self.tr('status.exported',path=path)); self.app_status.set_status('success')
            except Exception as exc:self._show_error(str(exc))

        def export_thumbnail_wall(self):
            path,_=QFileDialog.getSaveFileName(self,self.tr('action.thumbnail_wall'),str(scene_root(self.scene)/'exports'/'screen_overview.png'),'PNG (*.png)')
            if not path:return
            try:
                states=clinical_states(self.scene,seconds=int(self.session.runtime.state.get('seconds',0)),battery=int(self.session.runtime.state.get('battery',0))) if {'mode','phase'}<=set(self.scene.get('states',{})) else {'current':dict(self.session.runtime.state)}
                with tempfile.TemporaryDirectory(prefix='oled_wall_') as td:
                    export_scene(self.scene,Path(td),states); refs=[Path(td)/'reference'/f'{name}.png' for name in states]; build_thumbnail_wall(refs,path,columns=min(4,max(1,len(refs))),scale=4)
                self.app_status.setText(self.tr('status.exported',path=path)); self.app_status.set_status('success')
            except Exception as exc:self._show_error(str(exc))

        # ---------- selection / properties ----------
        def _rebuild_elements(self):
            current=set(self.selected_ids); blocker=QSignalBlocker(self.element_list); self.element_list.clear()
            for element in self.scene.get('elements',[]):
                flags=(' 🔒' if element.get('locked') else '')+(' ◌' if element.get('hidden') else '')
                item=QListWidgetItem(f"{element.get('id')}  ·  {element.get('type')}{flags}"); item.setData(Qt.UserRole,element.get('id')); self.element_list.addItem(item); item.setSelected(str(element.get('id')) in current)
            del blocker
        def _element_selection_changed(self):
            if self._syncing:return
            ids=[str(i.data(Qt.UserRole)) for i in self.element_list.selectedItems()]
            primary=str(self.element_list.currentItem().data(Qt.UserRole)) if self.element_list.currentItem() and self.element_list.currentItem().isSelected() else (ids[-1] if ids else None)
            self._set_selection(ids,source='list',primary=primary)
        def _canvas_selection_changed(self,ids): self._set_selection(list(ids),source='canvas',primary=self.canvas.primary_id)
        def _set_selection(self,ids,source,primary=None):
            self.selection_model.replace(ids,primary=primary); self.selected_ids=list(self.selection_model.ids); self.selected_id=self.selection_model.primary_id
            if source!='list':
                self._syncing=True
                for i in range(self.element_list.count()):self.element_list.item(i).setSelected(str(self.element_list.item(i).data(Qt.UserRole)) in self.selected_ids)
                self._syncing=False
            if source!='canvas':self.canvas.set_selection(self.selected_ids,self.selected_id)
            self._sync_properties(); self._update_measurement()
        def select_element(self,element_id):
            if any(str(e.get('id'))==element_id for e in self.scene.get('elements',[])):self._set_selection([element_id],source='api',primary=element_id)
        def _sync_properties(self):
            self._syncing=True
            try:
                if not self.selected_id:self.id_edit.clear(); self.type_edit.clear(); self.resource_edit.clear(); return
                e=self.session.document.element(self.selected_id); g=self.session.geometry(self.selected_id); self.id_edit.setText(self.selected_id); self.type_edit.setText(str(e.get('type',''))); self.resource_edit.setText(self._resource_description(e)); vals={'x':g.x,'y':g.y,'w':g.w,'h':g.h}
                for k,s in self.geom_spins.items():
                    s.setValue(vals[k])
                    editable=bool(g.editable[k]) and not e.get('locked') and self.workspace_mode==WorkspaceMode.DESIGN
                    if k in ('w','h'):
                        s.setEnabled(not e.get('locked')); s.setReadOnly(not editable)
                        s.setToolTip('' if editable else self.tr('property.native_size_locked'))
                    else:
                        s.setReadOnly(False); s.setEnabled(editable)
                self.lock_check.setChecked(bool(e.get('locked'))); self.hidden_check.setChecked(bool(e.get('hidden'))); self.context_label.setText(self.selected_id); self.context_pixel.setEnabled(e.get('type')=='image' and self.workspace_mode==WorkspaceMode.DESIGN)
            finally:self._syncing=False
        @staticmethod
        def _resource_description(e):
            if e.get('type')=='image':return str(e.get('asset',''))
            if e.get('type') in {'digits','image_seq'}:return f"{e.get('dir','')}{e.get('pattern','')}"
            if e.get('type')=='text':return str(e.get('font_header',''))
            if e.get('type')=='placeholder':return f"DRAFT: {e.get('label',e.get('id'))}"
            return ''
        def _apply_geometry_live(self,field,value):
            if self._syncing or not self.selected_id:return
            try:
                self.session.set_geometry(self.selected_id,coalesce=True,**{field:int(value)})
                self.refresh_drag_preview()
            except Exception as exc:self.app_status.setText(str(exc)); self.app_status.set_status('warning')

        def _finish_geometry_edit(self):
            self.session.end_coalesced_edit()
            self.refresh_all(keep_selection=True)

        def _canvas_move(self,element_id,dx,dy):
            ids=self.selected_ids if element_id in self.selected_ids else [element_id]
            self.session.batch_move(ids,dx,dy,coalesce=True)
            self.refresh_drag_preview()

        def _finish_canvas_drag(self,_element_id=None):
            self.session.end_coalesced_edit()
            self.refresh_all(keep_selection=True)

        def refresh_drag_preview(self):
            """Fast interaction path: render + canvas + geometry only.

            Validation, diff, evidence hashing, file-watcher maintenance and log
            emission are deliberately deferred until gesture commit.
            """
            started=perf_counter(); result=self.session.render(); self.last_render=result
            guides=smart_guides(self.session,self.selected_id,tolerance=1) if self.selected_id else {'x':(),'y':()}
            self.canvas.set_guides(guides); self.canvas.set_zones(self.scene.get('zones',[]) if self.zones_check.isChecked() else []); self.canvas.set_frame(result,self.selected_ids)
            self._sync_properties()
            elapsed=(perf_counter()-started)*1000.0; self.profiler.record('drag_preview',elapsed)
            summary=self.profiler.summary('drag_preview'); self.perf_label.setText(self.tr('performance.preview_live',latest=summary.latest_ms,avg=summary.avg_ms))
            runtime=getattr(self,'_runtime_preferences',RuntimeSettings.from_preferences(self.preferences))
            if runtime.drag_preview=='exact': self._update_diff(result.framebuffer)
            if runtime.validation_mode=='continuous': self._update_validation_panel()

        def nudge_selected(self,dx,dy):
            self.session.batch_move(self.selected_ids,dx,dy,coalesce=False)
            self.refresh_all(keep_selection=True)
        def _lock_changed(self,value):
            if self._syncing or not self.selected_ids:return
            self.session.set_locked(self.selected_ids,bool(value)); self._rebuild_elements(); self.refresh_all(keep_selection=True)
        def _hidden_changed(self,value):
            if self._syncing or not self.selected_ids:return
            self.session.set_hidden(self.selected_ids,bool(value)); self._rebuild_elements(); self.refresh_all(keep_selection=True)
        def _reorder_selected(self,front):
            if not self.selected_ids:return
            (self.session.bring_to_front if front else self.session.send_to_back)(self.selected_ids); self._rebuild_elements(); self.refresh_all(keep_selection=True)
        def group_selected(self):
            if len(self.selected_ids)<2:return
            gid,ok=QInputDialog.getText(self,self.tr('action.group'),self.tr('group.id'),text='group_1')
            if ok and gid:self.session.group_elements(self.selected_ids,group_id=gid); self._rebuild_elements()
        def ungroup_selected(self):
            if self.selected_ids:self.session.ungroup_elements(self.selected_ids); self._rebuild_elements()
        def align_selected(self,mode):
            if len(self.selected_ids)<1:return
            reference=getattr(self,'align_reference_combo',None).currentData() if getattr(self,'align_reference_combo',None) else 'selection'
            if reference=='selection' and len(self.selected_ids)<2:return
            align_to(self.session,self.selected_ids,mode,reference=reference or 'selection',primary_id=self.selected_id,canvas=(int(self.scene['canvas']['w']),int(self.scene['canvas']['h']))); self.refresh_all(keep_selection=True)
        def distribute_selected(self,axis):
            if len(self.selected_ids)>=3:distribute(self.session,self.selected_ids,axis); self.refresh_all(keep_selection=True)
        def snap_selected(self):
            grid=int(self.snap_combo.currentData() or 1); snap_positions(self.session,self.selected_ids,grid=max(1,grid)); self.refresh_all(keep_selection=True)
        def _update_measurement(self):
            if len(self.selected_ids)==2:
                m=measure(self.session,*self.selected_ids); self.measure_label.setText(self.tr('measure.summary',dx=m.dx,dy=m.dy,hgap=m.horizontal_gap,vgap=m.vertical_gap))
            elif len(self.selected_ids)>2:
                m=selection_metrics(self.session,self.selected_ids); gaps=' / '.join(str(v) for v in m.horizontal_gaps) or '—'; self.measure_label.setText(self.tr('measure.multi',count=len(self.selected_ids),width=m.bounds[2],height=m.bounds[3],gaps=gaps))
            else:self.measure_label.setText(self.tr('measure.hint'))

        # ---------- state / canvas ----------
        def _configure_state_controls(self):
            states=self.scene.get('states',{}); self._syncing=True; self.mode_combo.clear(); mode=states.get('mode',{}); self.mode_combo.addItems([str(v) for v in mode.get('values',[])])
            battery=states.get('battery',{'min':0,'max':4}); seconds=states.get('seconds',{'min':0,'max':999}); self.battery_spin.setRange(int(battery.get('min',0)),int(battery.get('max',4))); self.seconds_spin.setRange(int(seconds.get('min',0)),int(seconds.get('max',999))); self.canvas_width_spin.setValue(int(self.scene['canvas']['w'])); self.canvas_height_spin.setValue(int(self.scene['canvas']['h'])); dims=(int(self.scene['canvas']['w']),int(self.scene['canvas']['h'])); self.canvas_preset_combo.setCurrentText(next((n for n,s in CANVAS_PRESETS.items() if s==dims),'Custom')); self._syncing=False
        def _canvas_preset_changed(self,name):
            if self._syncing or name not in CANVAS_PRESETS:return
            w,h=CANVAS_PRESETS[name]; self._syncing=True; self.canvas_width_spin.setValue(w); self.canvas_height_spin.setValue(h); self._syncing=False
        def apply_canvas_size(self):
            try:self.session.set_canvas_size(self.canvas_width_spin.value(),self.canvas_height_spin.value()); self.refresh_all(keep_selection=True); self.retranslate_ui(); self._fit_canvas_zoom()
            except Exception as exc:self._show_error(str(exc))
        def _rebuild_phase_combo(self):
            current=self.session.runtime.state.get('phase','standby'); blocker=QSignalBlocker(self.phase_combo); self.phase_combo.clear(); self.phase_combo.addItem(self.tr('runtime.standby'),'standby'); self.phase_combo.addItem(self.tr('runtime.running'),'running'); self.phase_combo.setCurrentIndex(max(0,self.phase_combo.findData(current))); del blocker
        def _sync_runtime_controls(self):
            state=self.session.runtime.state; self._syncing=True; self.mode_combo.setCurrentText(str(state.get('mode',''))); self.phase_combo.setCurrentIndex(max(0,self.phase_combo.findData(state.get('phase')))); self.battery_spin.setValue(int(state.get('battery',0))); self.seconds_spin.setValue(int(state.get('seconds',0))); self.elapsed_label.setText(self.tr('runtime.elapsed',seconds=self.session.runtime.elapsed)); self._syncing=False
        def _state_changed(self,name,value):
            if not self._syncing:self.session.set_state(name,value); self.refresh_all(keep_selection=True)
        def _phase_changed(self):
            if not self._syncing and self.phase_combo.currentData():self._state_changed('phase',self.phase_combo.currentData())
        def _speed_changed(self,_v):
            if self.run_timer.isActive():self.run_timer.start(RUN_SPEEDS.get(self.speed_combo.currentText(),1000))
        def toggle_play(self): self.run_timer.stop() if self.run_timer.isActive() else self.run_timer.start(RUN_SPEEDS.get(self.speed_combo.currentText(),1000)); self._update_play_button()
        def _update_play_button(self):
            text=self.tr('action.pause') if self.run_timer.isActive() else self.tr('action.play'); self.play_button.setText(text); self._actions.get('play').setText(text) if self._actions.get('play') else None
        def _runtime_tick(self):self.session.step(1); self.refresh_all(keep_selection=True)
        def step_runtime(self):self.session.step(1); self.refresh_all(keep_selection=True)
        def reset_runtime(self):self.run_timer.stop(); self._update_play_button(); self.session.reset(); self.refresh_all(keep_selection=True)

        # ---------- canvas / zoom / diff ----------
        def _zoom_changed(self):
            data=self.zoom_combo.currentData(); self._fit_canvas_zoom() if data=='auto' else self.canvas.set_zoom(int(data))
        def _fit_canvas_zoom(self):
            if self.zoom_combo.currentData()!='auto':return
            size=self.canvas_scroll.viewport().size(); cw,ch=int(self.scene['canvas']['w']),int(self.scene['canvas']['h']); self.canvas.set_zoom(fit_integer_zoom(cw,ch,viewport_w=max(1,size.width()),viewport_h=max(1,size.height()),margin=28,min_zoom=1,max_zoom=24))
        def _overlay_changed(self):self.canvas.set_overlays(grid=self.grid_check.isChecked(),bounds=self.bounds_check.isChecked(),rulers=self.ruler_check.isChecked())
        def _pixel_hovered(self,x,y,value):
            self.pixel_status.setText(self.tr('pixel.none') if x<0 else self.tr('pixel.status',x=x,y=y,value=value,page=y//8,bit=y%8,byte=(y//8)*int(self.scene['canvas']['w'])+x)); self.pixel_status.set_status('neutral')
        def _update_diff(self,current=None):
            if self._saved_frame is None:return
            if current is None: current=self.session.render().framebuffer
            if (current.width,current.height)!=(self._saved_frame.width,self._saved_frame.height):self.diff_status.setText(self.tr('diff.size_changed')); self.diff_status.set_status('warning'); return
            d=diff_framebuffers(self._saved_frame,current); sd=diff_scenes(self._saved_scene_snapshot,self.scene); self.diff_status.setText(self.tr('diff.status',pixels=d.changed_pixels,percent=d.percent)); self.diff_status.set_status('success' if d.changed_pixels==0 else 'accent'); detail=self.tr('diff.bbox',bbox=str(d.bbox) if d.bbox else '—')+' · '+self.tr('diff.scene',added=len(sd.added),removed=len(sd.removed),changed=len(sd.changed)); self.diff_label.setText(detail)

        # ---------- validation / logs / refresh ----------
        def _render_validation_panel(self,findings):
            self.validation_list.clear()
            if not findings:self.validation_list.addItem(self.tr('finding.none')); self.validation_status.setText(self.tr('status.valid')); self.validation_status.set_status('success')
            else:
                blockers=sum(1 for f in findings if f.severity in {'ERROR','BLOCKER'}); self.validation_status.setText(self.tr('status.invalid',count=len(findings),blockers=blockers)); self.validation_status.set_status('danger' if blockers else 'warning'); [self.validation_list.addItem(f'{f.severity}/{f.code} — {f.message}') for f in findings]
            return findings
        def _update_validation_panel(self):
            findings=list(self.session.validate()); findings.extend(check_design_rules(self.scene,self.scene.get('_design_rules') or {})); self._last_validation_findings=list(findings); return self._render_validation_panel(findings)
        def _retranslate_validation_panel(self):
            # Language switching must not synchronously re-run validation. Scene edits
            # update the cache through refresh_all; here we only repaint translated chrome.
            return self._render_validation_panel(list(getattr(self,'_last_validation_findings',())))
        def batch_validate(self):
            matrix=build_state_matrix(self.scene,integer_policy='boundaries'); summary=validate_matrix(self.scene,matrix); rules=check_design_rules(self.scene,self.scene.get('_design_rules') or {}); rule_blockers=sum(1 for f in rules if f.severity in {'ERROR','BLOCKER'}); findings=summary.findings+len(rules); blockers=summary.blockers+rule_blockers; self.logger.log('BATCH_VALIDATE',cases=summary.cases,findings=findings,blockers=blockers); self.app_status.setText(self.tr('batch.status',cases=summary.cases,findings=findings,blockers=blockers)); self.app_status.set_status('success' if blockers==0 else 'danger'); self._update_validation_panel()
        def refresh_all(self,*,keep_selection=False):
            started=perf_counter(); result=self.session.render(); self.last_render=result;
            guides=smart_guides(self.session,self.selected_id,tolerance=1) if self.selected_id else {'x':(),'y':()}
            self.canvas.set_guides(guides); self.canvas.set_zones(self.scene.get('zones',[]) if self.zones_check.isChecked() else []); self.canvas.set_overlays(grid=self.grid_check.isChecked(),bounds=self.bounds_check.isChecked(),rulers=self.ruler_check.isChecked()); self.canvas.set_frame(result,self.selected_ids); self._schedule_canvas_fit()
            self._syncing=True; self.canvas_width_spin.setValue(int(self.scene['canvas']['w'])); self.canvas_height_spin.setValue(int(self.scene['canvas']['h'])); dims=(int(self.scene['canvas']['w']),int(self.scene['canvas']['h'])); self.canvas_preset_combo.setCurrentText(next((n for n,s in CANVAS_PRESETS.items() if s==dims),'Custom')); self._syncing=False
            if keep_selection:self._sync_properties()
            self._sync_runtime_controls();
            runtime=getattr(self,'_runtime_preferences',RuntimeSettings.from_preferences(self.preferences))
            if runtime.validation_mode=='idle': self.validation_timer.start()
            else: self._update_validation_panel()
            self._update_diff(result.framebuffer); self._update_asset_watcher(result.used_files)
            evidence=frame_evidence(result,dict(self.session.runtime.state),elapsed=self.session.runtime.elapsed,project_root=scene_root(self.scene)); signature=(evidence['sha256'],tuple(evidence['state'].items()),evidence['elapsed'])
            if signature!=self._last_frame_signature:self.logger.log('FRAME',**evidence); self._last_frame_signature=signature
            self.frame_status.setText(self.tr('status.frame',bytes=evidence['framebuffer_bytes'],lit=evidence['lit_pixels'])); self.frame_status.set_status('neutral'); self.setWindowTitle(APP_TITLE+(' •' if self.session.document.dirty else ''))
            elapsed=(perf_counter()-started)*1000.0; self.profiler.record('full_refresh',elapsed); summary=self.profiler.summary('full_refresh'); self.perf_label.setToolTip(self.tr('performance.full_refresh_tip',latest=summary.latest_ms,avg=summary.avg_ms,max=summary.max_ms))
        def _update_asset_watcher(self,used_files):
            wanted={str(Path(p).resolve()) for p in used_files if Path(p).exists()}; current=set(self.asset_watcher.files()); remove=list(current-wanted); add=list(wanted-current); self.asset_watcher.removePaths(remove) if remove else None; self.asset_watcher.addPaths(add) if add else None
        def _asset_changed(self,path):self.logger.log('ASSET_CHANGED',path=path); self.refresh_all(keep_selection=True); self._scan_assets()
        def _on_log(self,record):
            if not hasattr(self,'log_text'):self.pending_logs.append(record); return
            self.log_text.appendPlainText(json.dumps(record,ensure_ascii=False,sort_keys=True)); bar=self.log_text.verticalScrollBar(); bar.setValue(bar.maximum())
        def _flush_pending_logs(self):
            for r in self.pending_logs:self._on_log(r)
            self.pending_logs.clear()

        def duplicate_selected_elements(self):
            if not self.selected_ids:return
            copies=[]; existing={str(e.get('id')) for e in self.scene.get('elements',[])}
            for eid in self.selected_ids:
                e=deepcopy(self.session.document.element(eid)); base=f'{eid}_copy'; nid=base; i=2
                while nid in existing:nid=f'{base}_{i}';i+=1
                existing.add(nid); e['id']=nid
                if 'x' in e:e['x']=int(e['x'])+1
                if 'y' in e:e['y']=int(e['y'])+1
                copies.append(e)
            ids=self.session.add_elements(copies,label='duplicate'); self.selected_ids=ids; self.selected_id=ids[-1] if ids else None; self._rebuild_elements(); self.refresh_all(keep_selection=True)

        def toggle_selected_lock(self):
            if not self.selected_ids:return
            lock=not all(bool(self.session.document.element(eid).get('locked')) for eid in self.selected_ids); self.session.set_locked(self.selected_ids,lock); self._rebuild_elements(); self.refresh_all(keep_selection=True)

        # ---------- edit / autosave ----------
        def undo(self):
            if self.session.undo():self._rebuild_elements(); self.refresh_all(keep_selection=True)
        def redo(self):
            if self.session.redo():self._rebuild_elements(); self.refresh_all(keep_selection=True)
        def add_placeholder(self):
            d=PlaceholderDialog(self.tr,self)
            if d.exec()!=QDialog.Accepted:return
            eid,x,y,w,h=d.values()
            try:self.session.add_placeholder(eid,x=x,y=y,w=w,h=h); self.selected_ids=[eid]; self.selected_id=eid; self._rebuild_elements(); self.refresh_all(keep_selection=True)
            except Exception as exc:self._show_error(str(exc))
        def assign_bitmap(self):
            if not self.selected_id:return
            path,_=QFileDialog.getOpenFileName(self,self.tr('dialog.assign_bitmap'),str(scene_root(self.scene)),self.tr('dialog.image_filter'))
            if path:
                try:self.session.assign_bitmap(self.selected_id,path); self._rebuild_elements(); self.refresh_all(keep_selection=True); self._scan_assets()
                except Exception as exc:self._show_error(str(exc))
        def remove_selected(self):
            if not self.selected_ids:return
            if QMessageBox.question(self,self.tr('action.delete'),self.tr('dialog.delete_multi',count=len(self.selected_ids)),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
            for eid in list(self.selected_ids):self.session.remove_element(eid)
            self.selected_ids=[]; self.selected_id=None; self._rebuild_elements(); self.refresh_all(keep_selection=True)
        def _autosave_tick(self,force=False):
            if force or self.session.document.dirty:
                path=self.autosave.snapshot(reason='manual' if force else 'timer'); self.logger.log('AUTOSAVE',path=str(path)); self.app_status.setText(self.tr('status.autosaved')); self.app_status.set_status('neutral')
        def _prompt_recovery_if_needed(self):
            runtime=getattr(self,'_runtime_preferences',RuntimeSettings.from_preferences(self.preferences))
            if not runtime.prompt_recovery:return
            candidate=self.autosave.recovery_candidate()
            if not candidate:return
            box=QMessageBox(self); box.setWindowTitle(self.tr('autosave.recovery_title')); box.setText(self.tr('autosave.recovery_message')); box.setInformativeText(str(candidate)); box.setStandardButtons(QMessageBox.Yes|QMessageBox.No); box.setDefaultButton(QMessageBox.Yes)
            if box.exec()==QMessageBox.Yes:
                payload=AutoSaveManager.load_snapshot(candidate); payload['_path']=self.scene['_path']; payload['_root']=self.scene['_root']; self._reset_session(payload); self.session.document.dirty=True; self.logger.log('AUTOSAVE_RECOVERY',path=str(candidate))

        def restore_autosave(self):
            candidate=self.autosave.latest_recovery()
            if not candidate:return self._show_error(self.tr('autosave.none'))
            payload=AutoSaveManager.load_snapshot(candidate); payload['_path']=self.scene['_path']; payload['_root']=self.scene['_root']; self._reset_session(payload); self.session.document.dirty=True; self.logger.log('AUTOSAVE_RESTORE',path=str(candidate))

        # ---------- save/export/handoff ----------
        def save_scene(self):
            try:path=self.session.save(); self._capture_saved_baseline(); self.logger.log('SAVE_UI',path=str(path)); self.app_status.setText(self.tr('status.saved')); self.app_status.set_status('success'); self.refresh_all(keep_selection=True)
            except Exception as exc:self._show_error(str(exc))
        def export_current(self):
            output=QFileDialog.getExistingDirectory(self,self.tr('dialog.export_current'))
            if output:self._perform_export(Path(output),{'current':dict(self.session.runtime.state)})
        def export_all(self):
            output=QFileDialog.getExistingDirectory(self,self.tr('dialog.export_all'))
            if output:self._perform_export(Path(output),clinical_states(self.scene,seconds=int(self.session.runtime.state.get('seconds',0)),battery=int(self.session.runtime.state.get('battery',0))))
        def _perform_export(self,output,states):
            try:summary=export_scene(self.scene,output,states)
            except ExportBlockedError as exc:self._show_error(str(exc)); return
            except Exception as exc:self._show_error(str(exc)); return
            self.logger.log('EXPORT',output=str(summary.output_dir),frames=summary.frame_count); self.app_status.setText(self.tr('status.exported',path=str(summary.output_dir))); self.app_status.set_status('success')
        def export_handoff(self):
            path,_=QFileDialog.getSaveFileName(self,self.tr('action.handoff'),str(scene_root(self.scene)/'exports'/'OLED_Code_AI_Handoff.zip'),'ZIP (*.zip)')
            if not path:return
            states=clinical_states(self.scene,seconds=int(self.session.runtime.state.get('seconds',0)),battery=int(self.session.runtime.state.get('battery',0))) if {'mode','phase'}<=set(self.scene.get('states',{})) else {'current':dict(self.session.runtime.state)}
            try:summary=build_handoff_package(self.scene,path,states=states); self.app_status.setText(self.tr('handoff.done',frames=summary.frame_count,path=path)); self.app_status.set_status('success')
            except Exception as exc:self._show_error(str(exc))

        def _editor_tab_changed(self,index):
            if index<0:return
            widget=self.editor_tabs.widget(index); doc_id=getattr(widget,'document_id',None)
            if doc_id and self.editor_registry.get(doc_id):self.editor_registry.activate(doc_id)

        def _close_editor_tab(self,index):
            if index<=0:return
            widget=self.editor_tabs.widget(index)
            if getattr(getattr(widget,'document',None),'dirty',False):
                choice=QMessageBox.question(self,self.tr('dialog.close'),self.tr('dialog.save_changes'),QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
                if choice==QMessageBox.Cancel:return
                if choice==QMessageBox.Save and hasattr(widget,'save'):widget.save()
            doc_id=getattr(widget,'document_id',None); self.editor_tabs.removeTab(index); self.editor_registry.close(doc_id) if doc_id else None; widget.deleteLater()

        def route_save(self):
            editor=self.editor_registry.active
            return editor.save() if editor else self.save_scene()
        def route_undo(self):
            editor=self.editor_registry.active
            return editor.undo() if editor else self.undo()
        def route_redo(self):
            editor=self.editor_registry.active
            return editor.redo() if editor else self.redo()

        def open_pixel_studio(self):
            path=None
            if self.selected_id:
                try:
                    element=self.session.document.element(self.selected_id)
                    if element.get('type')=='image' and element.get('asset'):path=(scene_root(self.scene)/str(element.get('asset'))).resolve()
                except Exception:path=None
            if path is None:
                chosen,_=QFileDialog.getOpenFileName(self,self.tr('action.pixel_studio'),str(scene_root(self.scene)),self.tr('dialog.image_filter')); path=Path(chosen).resolve() if chosen else None
                if path is None:return
            doc_id='asset:'+str(path)
            existing=self.editor_registry.get(doc_id)
            if existing is not None:
                for i in range(self.editor_tabs.count()):
                    if getattr(self.editor_tabs.widget(i),'document_id',None)==doc_id:self.editor_tabs.setCurrentIndex(i);return
            editor=PixelStudioWindow(path,language=self.tr.language,parent=self.editor_tabs,preferences=self.preferences,project_root=scene_root(self.scene)); editor.assetSaved.connect(self._pixel_asset_saved); editor.document_id=doc_id
            self.editor_registry.open(editor); idx=self.editor_tabs.addTab(editor,path.name); self.editor_tabs.setCurrentIndex(idx)

        def _pixel_asset_saved(self,path):
            self.logger.log('PIXEL_ASSET_SAVED',path=str(path)); self._scan_assets(); self.refresh_all(keep_selection=True)

        def _font_root(self):
            root=scene_root(self.scene); target=root/'.oled'/'fonts'; target.mkdir(parents=True,exist_ok=True); return target

        def _scan_fonts(self):
            if not hasattr(self,'font_list'):return
            self.font_list.clear(); roots=[]
            base=scene_root(self.scene)
            for manifest in base.rglob('fontpack.json'):
                try:
                    rel=manifest.parent.relative_to(base).as_posix(); roots.append(rel)
                except ValueError:continue
            self.font_list.addItems(sorted(dict.fromkeys(roots)))

        def new_font_pack(self):
            name,ok=QInputDialog.getText(self,self.tr('font.new_title'),self.tr('font.pack_name'),text='Clinical 5x7')
            if not ok or not name.strip():return
            safe=''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name.strip()).strip('_') or 'font_pack'; root=self._font_root()/safe
            from font_pack import create_font_pack
            create_font_pack(root,name.strip(),cell=(5,8),baseline=6,advance=6).save(); self._scan_fonts(); self.open_font_lab(root)

        def open_font_lab(self,root=None):
            if root is None:
                item=self.font_list.currentItem() if hasattr(self,'font_list') else None
                if item:root=(scene_root(self.scene)/item.text()).resolve()
                else:
                    chosen=QFileDialog.getExistingDirectory(self,self.tr('font.open_title'),str(self._font_root())); root=Path(chosen).resolve() if chosen else None
            if not root:return
            root=Path(root).resolve(); doc_id='font:'+str(root)
            if self.editor_registry.get(doc_id):
                for i in range(self.editor_tabs.count()):
                    if getattr(self.editor_tabs.widget(i),'document_id',None)==doc_id:self.editor_tabs.setCurrentIndex(i);return
            editor=FontLabEditor(root,parent=self.editor_tabs,language=self.tr.language); editor.fontSaved.connect(lambda _p:(self._scan_fonts(),self.refresh_all(keep_selection=True))); self.editor_registry.open(editor)
            runtime=self._runtime_preferences or RuntimeSettings.from_preferences(self.preferences); editor.apply_runtime_delta(PreferenceDelta(runtime,runtime,frozenset({'language','theme','metrics','performance'})))
            idx=self.editor_tabs.addTab(editor,'Font · '+root.name); self.editor_tabs.setCurrentIndex(idx)

        def insert_bitmap_text(self):
            if self.workspace_mode!=WorkspaceMode.DESIGN:return
            root=QFileDialog.getExistingDirectory(self,self.tr('font.select_title'),str(self._font_root()))
            if not root:return
            from font_pack import FontPack
            try:pack=FontPack.load(root)
            except Exception as exc:self._show_error(str(exc));return
            text,ok=QInputDialog.getText(self,self.tr('bitmap.text_title'),self.tr('bitmap.text'),text='TEXT')
            if not ok or not text:return
            missing=[ch for ch in text if ch not in pack.characters()]
            if missing:self._show_error(self.tr('font.missing_glyphs',glyphs=str(missing)));return
            eid,ok=QInputDialog.getText(self,self.tr('bitmap.text_title'),self.tr('bitmap.element_id'),text='bitmap_text_1')
            if not ok or not eid:return
            try:
                rel=Path(root).resolve().relative_to(scene_root(self.scene)).as_posix()
            except ValueError:self._show_error(self.tr('font.inside_project'));return
            self.session.add_elements([{'id':eid,'type':'bitmap_text','text':text,'font_pack':rel,'x':0,'y':0}],label='bitmap_text_insert'); self._rebuild_elements(); self._set_selection([eid],source='api',primary=eid); self.refresh_all(keep_selection=True)

        def toggle_agent_bridge(self):
            if self.agent_bridge.running:
                self.agent_bridge.stop(); self.agent_status.setText(self.tr('agent.off')); self.header_agent.setProperty('active',False); return
            endpoint=self.agent_bridge.start(); self.agent_status.setText(self.tr('agent.status.local',port=endpoint['port'])); QMessageBox.information(self,self.tr('agent.bridge.title'),self.tr('agent.bridge.started',host=endpoint['host'],port=endpoint['port'],permission=endpoint['permission'],token=endpoint['token']))

        def _agent_command_completed(self,response):
            if 'result' not in response or response['result'].get('revision') is None:
                return
            result=response['result']
            if result.get('active_screen_changed'):
                # Automation API 1.0 switches the existing scene/session object in
                # place.  Rebind only UI projections; do not create a second Agent
                # service or a second source of project truth.
                self.autosave = AutoSaveManager(self.scene, keep=int(self.preferences.get('autosave.snapshots', 10)))
                self._configure_state_controls(); self._rebuild_screens(); self._scan_assets(); self._scan_fonts(); self._capture_saved_baseline()
            elif result.get('project_structure_changed'):
                self._rebuild_screens()
            self.selected_ids=list(self.selection_model.ids); self.selected_id=self.selection_model.primary_id; self._rebuild_elements(); self.refresh_all(keep_selection=True); self.logger.log('AGENT_COMMAND',response=response)

        def show_about(self):
            QMessageBox.information(self,self.tr('action.about'),f'<b>MonoOLED Studio</b><br>Version {APP_VERSION}<br><br>{self.tr("app.subtitle")}')

        # ---------- command palette ----------
        def show_command_palette(self):
            cmds=[('save',self.tr('action.save'),self.save_scene),('validate',self.tr('action.batch_validate'),self.batch_validate),('handoff',self.tr('action.handoff'),self.export_handoff),('undo',self.tr('action.undo'),self.undo),('redo',self.tr('action.redo'),self.redo),('assets',self.tr('action.asset_health'),self.show_asset_health),('template_save',self.tr('action.save_template'),self.save_template),('template_insert',self.tr('action.insert_template'),self.insert_template),('convert',self.tr('action.convert_asset'),self.convert_asset),('c_header',self.tr('action.export_c_header'),self.export_c_header),('overview',self.tr('action.thumbnail_wall'),self.export_thumbnail_wall),('diagnostics',self.tr('action.diagnostics'),self.toggle_diagnostics),('design_mode',self.tr('workspace.design'),lambda:self.set_workspace_mode(WorkspaceMode.DESIGN)),('review_mode',self.tr('workspace.review'),lambda:self.set_workspace_mode(WorkspaceMode.REVIEW)),('performance',self.tr('performance.title'),self.show_performance_report)]
            CommandPalette(self.tr,cmds,self).exec()

        # ---------- diagnostics / window persistence ----------
        def _show_error(self,message):
            get_logger('ui').error('%s',message)
            QMessageBox.critical(self,self.tr('dialog.error'),message); self.app_status.setText(message); self.app_status.set_status('danger')
        def layout_violations(self):
            issues=[]; leaves=[
                self.id_edit,self.type_edit,self.resource_edit,*self.geom_spins.values(),
                self.canvas_width_spin,self.canvas_height_spin,self.canvas_apply_button,
                self.header_pixel,self.header_review,self.header_project,self.header_settings,
                self.header_save,self.header_validate,self.header_handoff,self.header_diagnostics,
                self.screen_new,self.screen_duplicate,self.screen_delete,self.add_button,self.assign_button,self.delete_button,
                self.asset_import,self.asset_rescan,*self.align_buttons.values(),self.distribute_h,self.distribute_v,self.snap_button,
                self.mode_combo,self.phase_combo,self.battery_spin,self.seconds_spin,self.speed_combo,self.play_button,self.step_button,self.reset_button,
            ]
            for widget in leaves:
                if not widget.isVisible(): continue
                if widget.width()<=0 or widget.height()<=0:issues.append('zero-size:'+widget.__class__.__name__); continue
                vp=widget.visibleRegion().boundingRect()
                if vp.width()<max(8,widget.width()//2) or vp.height()<max(8,widget.height()//2):issues.append('clipped:'+widget.__class__.__name__)
            return issues
        def _restore_window_state(self):
            geometry=self.settings.value('geometry'); state=self.settings.value('windowState');
            if geometry:self.restoreGeometry(geometry)
            else:self.showMaximized()
            if state:self.restoreState(state)
            ws=self.settings.value('workspaceSplitter'); vs=self.settings.value('verticalSplitter')
            if ws:self.workspace_splitter.restoreState(ws)
            if vs:self.vertical_splitter.restoreState(vs)
            QTimer.singleShot(0,self._responsive_tick)
        def closeEvent(self,event:QCloseEvent):  # noqa:N802
            if self.session.document.dirty:
                box=QMessageBox(self); box.setWindowTitle(self.tr('dialog.unsaved_title')); box.setText(self.tr('dialog.unsaved_message')); box.setStandardButtons(QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel); result=box.exec()
                if result==QMessageBox.Cancel:event.ignore(); return
                if result==QMessageBox.Save:
                    try:self.session.save()
                    except Exception as exc:self._show_error(str(exc)); event.ignore(); return
            self.settings.setValue('geometry',self.saveGeometry()); self.settings.setValue('windowState',self.saveState()); self.settings.setValue('workspaceSplitter',self.workspace_splitter.saveState()); self.settings.setValue('verticalSplitter',self.vertical_splitter.saveState()); self.preferences.set('language',self.tr.language,save=False); self.preferences.set('startup.last_project',str(self.project.path) if self.project else '',save=False); self.preferences.save(); self.run_timer.stop(); self.autosave_timer.stop(); self.validation_timer.stop()
            if hasattr(self,'agent_bridge'): self.agent_bridge.stop()
            if hasattr(self,'system_theme'): self.system_theme.close()
            try:self.logger.write_markdown(self.log_path.with_suffix('.md'))
            finally:self.logger.close()
            event.accept()


def check_environment(source: str) -> int:
    if not PYSIDE_AVAILABLE:
        print(f'CORE CHECK FAIL: PySide6 is not installed ({PYSIDE_IMPORT_ERROR})',file=sys.stderr); return 2
    try:
        _project,scene=_load_source(source); session=EditorSession(scene); result=session.render(); findings=session.validate(); raw=result.framebuffer.to_vlsb(); expected=int(scene['canvas']['w'])*(int(scene['canvas']['h'])//8)
        if len(raw)!=expected or has_blockers(findings):return 2
        print(f"CORE CHECK PASS: PySide6={PySide6.__version__}, canvas={scene['canvas']['w']}x{scene['canvas']['h']}, framebuffer={len(raw)} bytes, elements={len(scene.get('elements',[]))}"); return 0
    except Exception as exc:print(f'CORE CHECK FAIL: {exc}',file=sys.stderr); return 2


def run_startup_smoke(source: str) -> int:
    """Construct and show the real main window, process events, then close."""
    if not PYSIDE_AVAILABLE:
        print(f'STARTUP SMOKE FAIL: PySide6 is not installed ({PYSIDE_IMPORT_ERROR})',file=sys.stderr); return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setOrganizationName('MonoOLEDStudio'); app.setStyle('Fusion'); app.setStyleSheet(build_stylesheet())
    w=None
    try:
        w=OLEDDesignerWindow(source,'zh_CN'); w.resize(1180,720); w.setAttribute(Qt.WA_DontShowOnScreen,True); w.show(); app.processEvents(); app.processEvents()
        if not w.isVisible(): raise RuntimeError('main window did not become visible')
        if w.layout_violations(): raise RuntimeError('layout violations: '+','.join(w.layout_violations()))
        w.session.document.dirty=False; w.close(); app.processEvents()
        print('STARTUP SMOKE PASS: QApplication + OLEDDesignerWindow constructed, shown, processed, and closed'); return 0
    except Exception as exc:
        if w is not None:
            try: w.session.document.dirty=False; w.close(); app.processEvents()
            except Exception: pass
        print(f'STARTUP SMOKE FAIL: {exc}',file=sys.stderr); return 2


def run_layout_smoke(source: str) -> int:
    if not PYSIDE_AVAILABLE:return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion'); app.setStyleSheet(build_stylesheet()); failures=[]
    for width,height,language in [(900,620,'zh_CN'),(900,620,'en_US'),(960,680,'zh_CN'),(960,680,'en_US'),(1100,700,'zh_CN'),(1100,700,'en_US'),(1180,720,'zh_CN'),(1180,720,'en_US'),(1440,900,'zh_CN'),(1440,900,'en_US'),(1920,1080,'zh_CN'),(1920,1080,'en_US'),(2560,1440,'zh_CN'),(2560,1440,'en_US')]:
        w=OLEDDesignerWindow(source,language); w.resize(width,height); w.show(); app.processEvents(); QTimer.singleShot(30,lambda:None); app.processEvents(); issues=w.layout_violations(); failures.extend([f'{width}x{height}/{language}:{x}' for x in issues]); w.session.document.dirty=False; w.close(); app.processEvents()
    if failures:print('LAYOUT SMOKE FAIL:\n'+'\n'.join(failures),file=sys.stderr); return 2
    print('LAYOUT SMOKE PASS: 14 window/language combinations'); return 0


def run_interaction_smoke(source: str) -> int:
    if not PYSIDE_AVAILABLE:return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion'); app.setStyleSheet(build_stylesheet()); w=OLEDDesignerWindow(source,'zh_CN'); w.resize(1440,900); w.show(); app.processEvents(); failures=[]
    try:
        target='battery' if any(e.get('id')=='battery' for e in w.scene.get('elements',[])) else str(w.scene['elements'][0]['id']); w.select_element(target); before=w.session.geometry(target); raw0=w.session.render().framebuffer.to_vlsb(); w.geom_spins['x'].setValue(before.x+1); app.processEvents(); raw1=w.session.render().framebuffer.to_vlsb();
        if w.session.geometry(target).x!=before.x+1:failures.append('live-x')
        if raw0==raw1:failures.append('live-render')
        w._finish_geometry_edit(); w.undo(); app.processEvents();
        if w.session.geometry(target).x!=before.x:failures.append('undo')
        w.change_language('en_US'); app.processEvents();
        if w.tr.language!='en_US':failures.append('i18n')
        w.canvas_width_spin.setValue(256); w.canvas_height_spin.setValue(64); w.apply_canvas_size(); app.processEvents();
        if len(w.session.render().framebuffer.to_vlsb())!=2048:failures.append('dynamic-canvas')
        if w.layout_violations():failures.append('layout')
    except Exception as exc:failures.append(f'exception:{exc}')
    finally:w.session.document.dirty=False; w.close(); app.processEvents()
    if failures:print('INTERACTION SMOKE FAIL:\n'+'\n'.join(failures),file=sys.stderr); return 2
    print('INTERACTION SMOKE PASS: live geometry, rerender, undo, i18n, dynamic canvas'); return 0


def run_soak_smoke(source: str, cycles: int = 240) -> int:
    if not PYSIDE_AVAILABLE:return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion'); app.setStyleSheet(build_stylesheet())
    w=OLEDDesignerWindow(source,'zh_CN'); w.resize(1180,720); w.show(); app.processEvents(); failures=[]
    try:
        target='battery' if any(e.get('id')=='battery' for e in w.scene.get('elements',[])) else str(w.scene['elements'][0]['id'])
        w.select_element(target); base=w.session.geometry(target).x
        sizes=((900,620),(960,680),(1100,700),(1180,720),(1440,900),(1920,1080))
        for i in range(max(1,int(cycles))):
            width,height=sizes[i%len(sizes)]; w.resize(width,height); w._responsive_tick()
            desired=base+(i&1); w.geom_spins['x'].setValue(desired); w._finish_geometry_edit()
            if i%20==0:w.change_language('en_US' if w.tr.language=='zh_CN' else 'zh_CN')
            if i%30==0:w.toggle_diagnostics(); w.toggle_diagnostics()
            app.processEvents()
            raw=w.session.render().framebuffer.to_vlsb(); expected=int(w.scene['canvas']['w'])*(int(w.scene['canvas']['h'])//8)
            if len(raw)!=expected:failures.append(f'framebuffer@{i}'); break
            if w.session.geometry(target).x!=desired:failures.append(f'geometry@{i}'); break
            issues=w.layout_violations()
            if issues:failures.append(f'layout@{i}:'+','.join(issues)); break
    except Exception as exc:failures.append(f'exception:{exc}')
    finally:w.session.document.dirty=False; w.close(); app.processEvents()
    if failures:print('SOAK SMOKE FAIL:\n'+'\n'.join(failures),file=sys.stderr); return 2
    print(f'SOAK SMOKE PASS: {cycles} resize/edit/i18n/render cycles'); return 0


def build_parser():
    p=argparse.ArgumentParser(description=APP_TITLE); p.add_argument('--scene',default='main_scene'); p.add_argument('--project',default=''); p.add_argument('--language',default=DEFAULT_LANGUAGE,choices=SUPPORTED_LANGUAGES); p.add_argument('--check',action='store_true',help='legacy alias for --core-check'); p.add_argument('--core-check',action='store_true',help='runtime dependency and renderer check'); p.add_argument('--startup-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--smoke-ms',type=int,default=0,help=argparse.SUPPRESS); p.add_argument('--layout-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--interaction-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--soak-smoke',action='store_true',help=argparse.SUPPRESS); return p


def main(argv=None):
    args=build_parser().parse_args(argv); source=args.project or args.scene
    if args.check or args.core_check:return check_environment(source)
    if args.startup_smoke:return run_startup_smoke(source)
    if args.layout_smoke:return run_layout_smoke(source)
    if args.interaction_smoke:return run_interaction_smoke(source)
    if args.soak_smoke:return run_soak_smoke(source)
    if not PYSIDE_AVAILABLE:print('PySide6 is required.',file=sys.stderr); return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setOrganizationName('MonoOLEDStudio'); icon=Path(__file__).resolve().parent/'branding'/'monooled_studio.ico'; app.setWindowIcon(QIcon(str(icon))) if icon.exists() else None; app.setStyle('Fusion'); pref=PreferencesStore.load(); runtime=RuntimeSettings.from_preferences(pref); system_dark=app.palette().window().color().value()<128; theme=resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=system_dark); app.setStyleSheet(build_stylesheet(theme,runtime.density,ui_scale=runtime.ui_scale));
    if not args.project and args.scene=='main_scene' and runtime.reopen_last_project and runtime.last_project and Path(runtime.last_project).exists(): source=runtime.last_project
    w=OLEDDesignerWindow(source,args.language); w.show(); QTimer.singleShot(args.smoke_ms,w.close) if args.smoke_ms>0 else None; return app.exec()


if __name__=='__main__':raise SystemExit(main())
