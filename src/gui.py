from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from time import perf_counter

from asset_library import AssetLibrary
from autosave import AutoSaveManager
from asset_convert import convert_bitmap
from c_export import write_c_header
from component_templates import TemplateLibrary
from design_rules import check_design_rules
from batch_validate import build_state_matrix, validate_matrix
from export_matrix import build_export_states
from editor_model import EditorSession
from evidence import frame_evidence
from exporter import ExportBlockedError, export_scene
from handoff import build_handoff_package
from i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Translator
from pixel_diff import diff_framebuffers
from scene_diff import diff_scenes
from thumbnail_wall import build_thumbnail_wall
from project_workspace import ProjectWorkspace, create_project
from responsive_layout import plan_layout, header_policy
from ui_metrics import build_ui_metrics
from professional_workspace import workspace_plan, WorkspaceMode
from selection_model import SelectionModel
from workspace_host import EditorRegistry, CallbackEditor, editor_is_dirty
from performance_profiler import PerformanceProfiler
from ui_performance import RefreshWorkPlan, InteractionTrace
from selection_tools import align_to, distribute, measure, selection_metrics, snap_positions, smart_guides
from canvas_geometry import fit_integer_zoom
from scene import ROOT, load_scene, scene_root
from session_log import SessionLogger
from validate import has_blockers
from preferences import PreferencesStore, default_preferences
from runtime_settings import RuntimeSettings
from preference_delta import PreferenceDelta
from commands import CommandRegistry
from theme_system import resolve_theme_name
from micro_signature import modified_geometry_fields
from state_schema import schema_from_scene
from state_preview import build_state_editor_specs, coerce_editor_value
from preview_capabilities import preview_capabilities, timeline_metadata
from workspace_chrome import canvas_context_actions, editor_chrome_state
from automation_service import StudioAutomationService
from diagnostics import configure_diagnostics, get_logger
from windows_chrome import apply_windows_chrome
from version_info import load_version

APP_TITLE = 'MonoOLED Studio'
APP_VERSION = load_version()
ZOOM_LEVELS = (1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24)
RUN_SPEEDS = {'1×': 1000, '2×': 500, '5×': 200, '10×': 100}
CANVAS_PRESETS = {'96×16': (96, 16), '128×32': (128, 32), '128×64': (128, 64), '256×64': (256, 64)}
DEFAULT_PROJECT = None

try:
    import PySide6
    from PySide6.QtCore import QEvent, QFileSystemWatcher, QPoint, QSize, QSettings, QSignalBlocker, QThread, Qt, QTimer
    from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QFormLayout,
        QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
        QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
        QSizePolicy, QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget, QAbstractItemView,
    )
    from qt_theme import build_adaptive_stylesheet, build_theme_palette
    from system_theme import SystemThemeProvider
    from qt_canvas import OLEDCanvas
    from qt_widgets import ProfessionalPanel, StatusPill
    from pixel_studio_qt import PixelStudioWindow
    from preferences_qt import PreferencesView, PreferencesWindow
    from font_lab_qt import FontLabEditor
    from qt_interaction import FocusOriginFilter
    from ui_controls import StudioButton, StudioToolButton, StudioSelect, StudioNumericInput, StudioSegmentedControl, StudioStateDot, StudioMarkedLabel, PopupManager
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


def _apply_application_theme(app, theme: str, density: str, ui_scale: float) -> None:
    """Apply appearance as one deterministic application-wide transaction.

    The adaptive QSS reads semantic colors from the application palette, so a
    theme-only change must not reinstall the same stylesheet across every
    widget.  Reinstall QSS only when density/scale changes; palette propagation
    plus one event flush makes a theme switch visible immediately.
    """
    palette = build_theme_palette(theme)
    signature = f'{theme}:{density}:{ui_scale}'
    stylesheet = build_adaptive_stylesheet(density, ui_scale=ui_scale)
    app.setPalette(palette)
    if app.styleSheet() != stylesheet:
        app.setStyleSheet(stylesheet)
    app.setProperty('monooledAdaptiveStyleSignature', signature)
    for window in app.topLevelWidgets():
        try:
            window.setPalette(palette)
            style = window.style()
            style.unpolish(window)
            style.polish(window)
            apply_windows_chrome(window, theme)
            window.update()
        except RuntimeError:
            continue
    app.processEvents()



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
    if source == 'main_scene' and DEFAULT_PROJECT is not None and DEFAULT_PROJECT.exists():
        project = ProjectWorkspace.load(DEFAULT_PROJECT)
        scene = _decorate_project_scene(load_scene(project.screen_path(project.active_screen), project_root=project.root), project)
        return project, scene
    scene = load_scene(source)
    return None, scene

def _validated_last_project_source(value: str) -> str | None:
    """Return a last-project path only after its manifest and active scene load.

    A stale/corrupt preference must never prevent the application from reaching
    its normal default startup source.
    """
    text=str(value or '').strip()
    if not text:
        return None
    candidate=Path(text)
    if not candidate.exists() or not candidate.is_file():
        return None
    try:
        _load_source(text)
    except Exception:
        return None
    return text



if PYSIDE_AVAILABLE:
    # Imported only after the PySide availability gate so a headless ``gui``
    # import retains its existing failure-free behavior.
    from gui_designer_mixin import DesignerActionsMixin
    from gui_editor_mixin import EditorTabsMixin
    from gui_project_mixin import ProjectWorkspaceMixin
    from gui_resource_mixin import ResourceWorkflowMixin

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


    class OLEDDesignerWindow(ProjectWorkspaceMixin, ResourceWorkflowMixin, DesignerActionsMixin, EditorTabsMixin, QMainWindow):
        def __init__(self, source: str = 'main_scene', language: str = DEFAULT_LANGUAGE):
            super().__init__()
            self.settings = QSettings('MonoOLEDStudio', 'MonoOLEDStudio')
            self._startup_warnings=[]
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
                self.preferences.data['shortcuts']=merged
                try:self.preferences.save()
                except OSError as exc:self._startup_warnings.append(('SHORTCUT_REPAIR_SAVE_FAIL',str(exc)))
            self._preferences_window = None
            self._preferences_view = None
            self._startup_trace = InteractionTrace('startup')
            self.project, self.scene = _load_source(source)
            self.diag_logger = configure_diagnostics(_log_dir(self.scene)); self.diag_logger.info('Starting %s %s',APP_TITLE,APP_VERSION)
            for code,detail in self._startup_warnings:self.diag_logger.warning('%s: %s',code,detail)
            self.pending_logs: list[dict] = []
            self.selection_model=SelectionModel()
            self.selected_ids: list[str] = []
            self.selected_id: str | None = None
            self.editor_registry=EditorRegistry()
            self._syncing = False
            self._last_frame_signature = None
            self._last_validation_findings = []
            self._layout_bucket = None
            self._closing = False
            self._diagnostics_open = True
            self._saved_scene_snapshot = deepcopy(self.scene)
            self._saved_frame = None
            self.profiler = PerformanceProfiler(max_samples=180)
            self.workspace_mode = WorkspaceMode.DESIGN

            stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            self.log_path = _log_dir(self.scene) / f'qt_gui_session_{stamp}_p{os.getpid()}.jsonl'
            self.logger = SessionLogger(self.log_path, callback=self._on_log)
            self.session = EditorSession(self.scene, logger=self.logger, max_history=int(self.preferences.get('performance.undo_history', 200)))
            self.automation_service=StudioAutomationService.for_editor(self.scene,source_path=self.scene.get('_path'),selection_model=self.selection_model,editor_session=self.session,permission='edit',project_workspace=self.project)
            self.autosave = AutoSaveManager(self.scene, keep=int(self.preferences.get('autosave.snapshots', 10)))
            self.asset_library = self._make_asset_library()
            self.template_library = TemplateLibrary(scene_root(self.scene) / '.oled' / 'templates.json')

            self.run_timer = QTimer(self); self.run_timer.timeout.connect(self._runtime_tick)
            self.autosave_timer = QTimer(self); self.autosave_timer.setInterval(max(1, int(self.preferences.get('autosave.interval_minutes', 3))) * 60_000); self.autosave_timer.timeout.connect(self._autosave_tick); self.autosave_timer.start() if self.preferences.get('autosave.enabled', True) else None
            self.validation_timer=QTimer(self); self.validation_timer.setSingleShot(True); self.validation_timer.setInterval(250); self.validation_timer.timeout.connect(self._update_validation_panel)
            self.deferred_refresh_timer=QTimer(self); self.deferred_refresh_timer.setSingleShot(True); self.deferred_refresh_timer.timeout.connect(self._run_deferred_refresh); self._deferred_result=None
            self.layout_timer = QTimer(self); self.layout_timer.setSingleShot(True); self.layout_timer.setInterval(24); self.layout_timer.timeout.connect(self._responsive_tick)
            self.asset_watcher = QFileSystemWatcher(self); self.asset_watcher.fileChanged.connect(self._asset_changed); self.asset_watcher.directoryChanged.connect(self._asset_directory_changed)

            self._menus = {}; self._actions: dict[str, QAction] = {}
            self._build_ui(); self.agent_bridge=QtAutomationBridge(self.automation_service,self); self.agent_bridge.commandCompleted.connect(self._agent_command_completed); self._build_menu(); self.apply_preferences(initial=True); self._bind_shortcuts(); self._connect_responsive_events()
            self._rebuild_screens(); self._rebuild_elements()
            if self.scene.get('elements'): self.select_element(str(self.scene['elements'][0]['id']))
            self.retranslate_ui(); self.refresh_all(keep_selection=True); self._flush_pending_logs(); self._capture_saved_baseline()
            self._restore_window_state()
            self._startup_trace.mark('ui_constructed')
            QTimer.singleShot(0, self._schedule_post_show_startup)
            QTimer.singleShot(120, self._prompt_recovery_if_needed)

        def _schedule_post_show_startup(self):
            """Move non-critical discovery behind the first event-loop paint."""
            if self._closing:
                return
            self._startup_trace.mark('first_event_loop')
            QTimer.singleShot(0, self._post_show_scan_assets)
            QTimer.singleShot(35, self._post_show_scan_fonts)

        def _post_show_scan_assets(self):
            if self._closing:
                return
            started=perf_counter(); self._scan_assets(); elapsed=(perf_counter()-started)*1000.0; self.profiler.record('startup.asset_scan',elapsed); self._startup_trace.mark('assets_ready')

        def _post_show_scan_fonts(self):
            if self._closing:
                return
            started=perf_counter(); self._scan_fonts(); elapsed=(perf_counter()-started)*1000.0; self.profiler.record('startup.font_scan',elapsed); self._startup_trace.mark('fonts_ready'); self.logger.log('STARTUP_TRACE',**self._startup_trace.as_dict())

        # ---------- model / project ----------
        def _make_asset_library(self):
            root = scene_root(self.scene)
            dirs = self.project.asset_dirs if self.project else tuple(self.scene.get('asset_dirs', ['assets']))
            return AssetLibrary(root, dirs, cache_budget_mb=int(self.preferences.get('performance.asset_cache_mb',512)))

        def _reset_session(self, scene: dict):
            self.scene = scene; self.session = EditorSession(scene, logger=self.logger, max_history=int(self.preferences.get('performance.undo_history', 200))); self.automation_service=StudioAutomationService.for_editor(self.scene,source_path=self.scene.get('_path'),selection_model=self.selection_model,editor_session=self.session,permission='edit',project_workspace=self.project);
            if hasattr(self,'agent_bridge'):self.agent_bridge.set_service(self.automation_service)
            self.autosave = AutoSaveManager(scene, keep=int(self.preferences.get('autosave.snapshots', 10)))
            self.asset_library = self._make_asset_library(); self.template_library = TemplateLibrary(scene_root(self.scene) / '.oled' / 'templates.json'); self.selection_model.clear(); self.selected_ids=[]; self.selected_id=None; self._last_frame_signature=None
            self._configure_state_controls(); self._rebuild_elements(); self.retranslate_ui(); self.refresh_all(keep_selection=True); self._capture_saved_baseline(); QTimer.singleShot(0,self._schedule_post_show_startup)

        def _capture_saved_baseline(self):
            self._saved_scene_snapshot = deepcopy(self.scene)
            try: self._saved_frame = self.session.render().framebuffer
            except Exception: self._saved_frame = None
            if hasattr(self, 'document_dirty_dot'):
                self._update_document_dirty_marker()
                self._update_inspector_modified_markers()

        def _saved_element_baseline(self, element_id):
            snapshot=getattr(self,'_saved_scene_snapshot',None)
            if not isinstance(snapshot,dict):return None
            target=str(element_id or '')
            return next((e for e in snapshot.get('elements',[]) if str(e.get('id'))==target),None)

        def _update_document_dirty_marker(self):
            if hasattr(self,'document_dirty_dot'):
                self.document_dirty_dot.set_active(bool(getattr(getattr(self,'session',None),'document',None) and self.session.document.dirty))

        def _update_inspector_modified_markers(self, current=None):
            labels=getattr(self,'geom_labels',{})
            if not labels:return
            if current is None and self.selected_id:
                try: current=self.session.document.element(self.selected_id)
                except Exception: current=None
            baseline=self._saved_element_baseline(self.selected_id) if self.selected_id else None
            changed=set(modified_geometry_fields(current,baseline))
            for key,label in labels.items():label.set_marked(key in changed)

        # ---------- UI ----------
        def _build_ui(self):
            self.setWindowTitle(APP_TITLE); self.resize(1500, 920); self.setMinimumSize(900, 620)
            icon_path=Path(__file__).resolve().parent/'branding'/'monooled_studio.ico'
            if icon_path.exists(): self.setWindowIcon(QIcon(str(icon_path)))
            initial_runtime=RuntimeSettings.from_preferences(self.preferences)
            m=build_ui_metrics(initial_runtime.density,initial_runtime.ui_scale); self._ui_metrics=m
            root = QWidget(self); root.setObjectName('AppRoot'); self.setCentralWidget(root)
            root_layout = QVBoxLayout(root); self._root_layout=root_layout
            root_layout.setContentsMargins(m['space_normal'],m['space_compact'],m['space_normal'],m['space_compact']); root_layout.setSpacing(m['space_compact'])

            # UI Craft v1.0 command bar: explicit left / center / right ownership.
            # The center remains the workspace mode; Save is the only strong CTA.
            header = QWidget(); self._header_bar=header; header.setObjectName('EditorCommandBar'); header.setMinimumHeight(m['control']+2*m['space_tight'])
            header_row=QGridLayout(header); self._header_layout=header_row
            header_row.setContentsMargins(m['space_compact'],m['space_micro'],m['space_compact'],m['space_micro']); header_row.setHorizontalSpacing(m['space_compact'])
            header_row.setColumnStretch(0,1); header_row.setColumnStretch(2,1)

            command_left=QWidget(); command_left.setObjectName('CommandBarLeft'); left_row=QHBoxLayout(command_left); self._command_left_layout=left_row
            left_row.setContentsMargins(0,0,0,0); left_row.setSpacing(m['space_compact'])
            self.header_project=QToolButton(); self.header_project.setObjectName('GhostButton'); self.header_project.clicked.connect(self.open_project_dialog)
            self.header_undo=QToolButton(); self.header_undo.setObjectName('GhostButton'); self.header_undo.setText('↶'); self.header_undo.clicked.connect(self.route_undo)
            self.header_redo=QToolButton(); self.header_redo.setObjectName('GhostButton'); self.header_redo.setText('↷'); self.header_redo.clicked.connect(self.route_redo)
            self.document_dirty_dot=StudioStateDot('dirty'); self.document_dirty_dot.setObjectName('DocumentDirtyDot')
            titles=QVBoxLayout(); titles.setSpacing(0); self.hero_title=QLabel(); self.hero_title.setObjectName('PanelTitle'); self.hero_subtitle=QLabel(); self.hero_subtitle.setObjectName('Muted'); titles.addWidget(self.hero_title); titles.addWidget(self.hero_subtitle)
            left_row.addWidget(self.header_project); left_row.addWidget(self.header_undo); left_row.addWidget(self.header_redo); left_row.addWidget(self.document_dirty_dot,0,Qt.AlignVCenter); left_row.addLayout(titles)

            command_center=QWidget(); command_center.setObjectName('CommandBarCenter'); center_row=QHBoxLayout(command_center); center_row.setContentsMargins(0,0,0,0); center_row.setSpacing(0)
            self.workspace_segment=StudioSegmentedControl(('Design','Pixel','Review')); self.workspace_segment.setObjectName('WorkspaceSegmentedControl')
            self.workspace_segment.currentIndexChanged.connect(self._workspace_segment_changed); center_row.addWidget(self.workspace_segment)
            self.header_design=self.workspace_segment.button(0); self.header_pixel=self.workspace_segment.button(1); self.header_review=self.workspace_segment.button(2)

            command_right=QWidget(); command_right.setObjectName('CommandBarRight'); right_row=QHBoxLayout(command_right); self._command_right_layout=right_row
            right_row.setContentsMargins(0,0,0,0); right_row.setSpacing(m['space_compact'])
            self.pixel_status=StatusPill()
            self.header_validate=QPushButton(); self.header_validate.setObjectName('SecondaryButton'); self.header_validate.clicked.connect(self.batch_validate)
            self.header_handoff=QPushButton(); self.header_handoff.setObjectName('SecondaryButton'); self.header_handoff.clicked.connect(self.export_handoff)
            self.header_save=QPushButton(); self.header_save.setObjectName('PrimaryButton'); self.header_save.clicked.connect(self.route_save)
            self.header_diagnostics=QToolButton(); self.header_diagnostics.setObjectName('GhostButton'); self.header_diagnostics.clicked.connect(self.toggle_diagnostics)
            self.header_settings=QToolButton(); self.header_settings.setObjectName('GhostButton'); self.header_settings.setCheckable(True); self.header_settings.clicked.connect(self.toggle_preferences); self.header_settings.setToolTip('Preferences (Ctrl+,)')
            self.header_agent=QToolButton(); self.header_agent.setObjectName('GhostButton'); self.header_agent.setToolTip('Code AI Agent Bridge'); self.header_agent.clicked.connect(self.toggle_agent_bridge)
            icon_dir=Path(__file__).resolve().parent/'branding'/'icons'
            for widget,name in ((self.header_project,'project'),(self.header_diagnostics,'diagnostics'),(self.header_agent,'agent'),(self.header_settings,'settings')):
                icon=icon_dir/f'{name}.svg'
                if icon.exists(): widget.setIcon(QIcon(str(icon)))
            for w in (self.pixel_status,self.header_validate,self.header_handoff,self.header_save,self.header_diagnostics,self.header_agent,self.header_settings): right_row.addWidget(w)
            header_row.addWidget(command_left,0,0,Qt.AlignLeft|Qt.AlignVCenter); header_row.addWidget(command_center,0,1,Qt.AlignCenter); header_row.addWidget(command_right,0,2,Qt.AlignRight|Qt.AlignVCenter)
            root_layout.addWidget(header)
            self.editor_tabs=QTabWidget(); self.editor_tabs.setObjectName('WorkspaceTabs'); self.editor_tabs.setTabsClosable(True); self.editor_tabs.setMovable(True); self.editor_tabs.currentChanged.connect(self._editor_tab_changed); self.editor_tabs.tabCloseRequested.connect(self._close_editor_tab); root_layout.addWidget(self.editor_tabs,1)

            self.vertical_splitter=QSplitter(Qt.Vertical); self.vertical_splitter.setChildrenCollapsible(True)
            self.workspace_splitter=QSplitter(Qt.Horizontal); self.workspace_splitter.setChildrenCollapsible(False)

            # LEFT — navigation/library rail. This collapses before canvas space is sacrificed.
            self.left_card=ProfessionalPanel(); self.left_card.setObjectName('ProfessionalPanel'); self.left_tabs=QTabWidget(); self.left_card.body.addWidget(self.left_tabs,1)
            screens_page=QWidget(); sl=QVBoxLayout(screens_page); sl.setContentsMargins(0,0,0,0); sl.setSpacing(m['space_compact']); self.screen_list=QListWidget(); self.screen_list.currentItemChanged.connect(self._screen_changed); sl.addWidget(self.screen_list,1)
            srow=QGridLayout(); srow.setSpacing(m['space_tight']); self.screen_new=QPushButton(); self.screen_new.clicked.connect(self.new_screen); self.screen_duplicate=QPushButton(); self.screen_duplicate.clicked.connect(self.duplicate_screen); self.screen_delete=QPushButton(); self.screen_delete.clicked.connect(self.delete_screen); srow.addWidget(self.screen_new,0,0); srow.addWidget(self.screen_duplicate,0,1); srow.addWidget(self.screen_delete,1,0,1,2); sl.addLayout(srow); self.left_tabs.addTab(screens_page,'')
            elements_page=QWidget(); el=QVBoxLayout(elements_page); el.setContentsMargins(0,0,0,0); el.setSpacing(m['space_compact']); self.element_list=QListWidget(); self.element_list.setSelectionMode(QAbstractItemView.ExtendedSelection); self.element_list.itemSelectionChanged.connect(self._element_selection_changed); el.addWidget(self.element_list,1)
            erow=QGridLayout(); erow.setSpacing(m['space_tight']); self.add_button=QPushButton(); self.add_button.clicked.connect(self.add_placeholder); self.assign_button=QPushButton(); self.assign_button.clicked.connect(self.assign_bitmap); self.delete_button=QPushButton(); self.delete_button.setObjectName('DangerButton'); self.delete_button.clicked.connect(self.remove_selected); erow.addWidget(self.add_button,0,0); erow.addWidget(self.assign_button,0,1); erow.addWidget(self.delete_button,1,0,1,2); el.addLayout(erow); self.left_tabs.addTab(elements_page,'')
            assets_page=QWidget(); al=QVBoxLayout(assets_page); al.setContentsMargins(0,0,0,0); al.setSpacing(m['space_compact']); self.asset_search=QLineEdit(); self.asset_search.textChanged.connect(self._filter_assets); self.asset_list=QListWidget(); self.asset_list.itemDoubleClicked.connect(self.place_asset); self.asset_empty_title=QLabel(); self.asset_empty_title.setObjectName('EmptyStateTitle'); self.asset_empty_title.hide(); self.asset_empty_guidance=QLabel(); self.asset_empty_guidance.setObjectName('EmptyStateGuidance'); self.asset_empty_guidance.setWordWrap(True); self.asset_empty_guidance.hide(); al.addWidget(self.asset_search); al.addWidget(self.asset_empty_title); al.addWidget(self.asset_empty_guidance); al.addWidget(self.asset_list,1); arow=QHBoxLayout(); arow.setSpacing(m['space_tight']); self.asset_import=QPushButton(); self.asset_import.clicked.connect(self.import_asset); self.asset_rescan=QPushButton(); self.asset_rescan.clicked.connect(self._scan_assets); arow.addWidget(self.asset_import); arow.addWidget(self.asset_rescan); al.addLayout(arow); self.left_tabs.addTab(assets_page,'')
            fonts_page=QWidget(); fl=QVBoxLayout(fonts_page); fl.setContentsMargins(0,0,0,0); fl.setSpacing(m['space_compact']); self.font_list=QListWidget(); self.font_list.itemDoubleClicked.connect(lambda _item:self.open_font_lab()); self.font_empty_title=QLabel(); self.font_empty_title.setObjectName('EmptyStateTitle'); self.font_empty_title.hide(); self.font_empty_guidance=QLabel(); self.font_empty_guidance.setObjectName('EmptyStateGuidance'); self.font_empty_guidance.setWordWrap(True); self.font_empty_guidance.hide(); fl.addWidget(self.font_empty_title); fl.addWidget(self.font_empty_guidance); fl.addWidget(self.font_list,1); frow=QHBoxLayout(); frow.setSpacing(m['space_tight']); self.font_new=QPushButton('New Font'); self.font_new.clicked.connect(self.new_font_pack); self.font_open=QPushButton('Open Font'); self.font_open.clicked.connect(self.open_font_lab); self.font_rescan=QPushButton('Rescan'); self.font_rescan.clicked.connect(self._scan_fonts); frow.addWidget(self.font_new); frow.addWidget(self.font_open); frow.addWidget(self.font_rescan); fl.addLayout(frow); self.left_tabs.addTab(fonts_page,'Fonts')
            self.workspace_splitter.addWidget(self.left_card)

            # CENTER — canvas-first workspace. No dashboard card/shadow chrome.
            self.canvas_card=ProfessionalPanel(); self.canvas_card.setObjectName('CanvasWorkspace'); self.canvas_card.setMinimumWidth(300); self.canvas_card.body.setContentsMargins(m['space_section'],m['space_group'],m['space_section'],m['space_section']); self.canvas_card.body.setSpacing(m['space_normal']); self.canvas_card.setProperty('canvasFocus',False)
            tools=QHBoxLayout(); tools.setSpacing(m['space_compact']); self.frame_status=StatusPill(); tools.addWidget(self.frame_status); tools.addStretch(1)
            self.zoom_label=QLabel(); self.zoom_label.setObjectName('Muted'); self.zoom_combo=QComboBox(); self.zoom_combo.button.setProperty('technicalValue',True); self.zoom_combo.addItem('Auto','auto'); [self.zoom_combo.addItem(f'{z}×',z) for z in ZOOM_LEVELS]; self.zoom_combo.currentIndexChanged.connect(self._zoom_changed)
            self.grid_check=QCheckBox(); self.grid_check.setChecked(True); self.bounds_check=QCheckBox(); self.bounds_check.setChecked(True); self.ruler_check=QCheckBox(); self.ruler_check.setChecked(True); self.zones_check=QCheckBox(); self.zones_check.setChecked(False)
            self.grid_check.toggled.connect(self._overlay_changed); self.bounds_check.toggled.connect(self._overlay_changed); self.ruler_check.toggled.connect(self._overlay_changed); self.zones_check.toggled.connect(self._overlay_changed)
            self.snap_combo=QComboBox(); [self.snap_combo.addItem(v,g) for v,g in [('Off',0),('1 px',1),('2 px',2),('4 px',4),('8 px',8)]]
            for w in (self.zoom_label,self.zoom_combo,self.grid_check,self.bounds_check,self.ruler_check,self.zones_check,self.snap_combo): tools.addWidget(w)
            self.canvas_card.body.addLayout(tools)
            self.context_bar=QWidget(); self.context_bar.setObjectName('CanvasContextBar'); context=QHBoxLayout(self.context_bar); context.setContentsMargins(0,0,0,0); context.setSpacing(m['space_tight']); self.context_label=QLabel(); self.context_label.setObjectName('Muted'); context.addWidget(self.context_label); context.addStretch(1)
            self.context_duplicate=QPushButton(); self.context_duplicate.setObjectName('SecondaryButton'); self.context_duplicate.clicked.connect(self.duplicate_selected_elements); self.context_lock=QPushButton(); self.context_lock.setObjectName('SecondaryButton'); self.context_lock.clicked.connect(self.toggle_selected_lock); context.addWidget(self.context_duplicate); context.addWidget(self.context_lock); self.canvas_card.body.addWidget(self.context_bar); self.context_bar.hide()
            self.canvas=OLEDCanvas(); self.canvas.selectionChanged.connect(self._canvas_selection_changed); self.canvas.dragStarted.connect(self._start_canvas_drag); self.canvas.elementMoved.connect(self._canvas_move); self.canvas.dragFinished.connect(self._finish_canvas_drag); self.canvas.pixelHovered.connect(self._pixel_hovered)
            self.canvas_scroll=QScrollArea(); self.canvas_scroll.setWidgetResizable(False); self.canvas_scroll.setFrameShape(QFrame.NoFrame); self.canvas_scroll.viewport().setObjectName('CanvasViewport'); self.canvas_scroll.setWidget(self.canvas); self.canvas_card.body.addWidget(self.canvas_scroll,1)
            self.canvas_hint=QLabel(); self.canvas_hint.setObjectName('Muted'); self.canvas_hint.setWordWrap(True); self.canvas_card.body.addWidget(self.canvas_hint)
            self.workspace_splitter.addWidget(self.canvas_card)

            # RIGHT — contextual inspector. Low-frequency state/canvas controls live
            # behind a separate State tab instead of permanently consuming height.
            self.inspector_tabs=QTabWidget(); self.inspector_tabs.setMinimumWidth(260)
            self.inspector_page=QScrollArea(); self.inspector_page.setWidgetResizable(True); self.inspector_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.inspector_page.setObjectName('InspectorRoot')
            self.inspector_inner=QWidget(); self.inspector_inner.setObjectName('InspectorRoot'); self.inspector_inner.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred); self.inspector_layout=QVBoxLayout(self.inspector_inner); self.inspector_layout.setContentsMargins(m['space_tight'],m['space_tight'],m['space_tight'],m['space_tight']); self.inspector_layout.setSpacing(m['space_section'])
            self.properties_card=ProfessionalPanel(); form=QFormLayout(); form.setVerticalSpacing(m['space_compact']); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            self.id_edit=QLineEdit(); self.id_edit.setObjectName('TechnicalInput'); self.id_edit.setReadOnly(True); self.type_edit=QLineEdit(); self.type_edit.setReadOnly(True); self.resource_edit=QLineEdit(); self.resource_edit.setObjectName('TechnicalInput'); self.resource_edit.setReadOnly(True); self.prop_id_label=QLabel(); self.prop_type_label=QLabel(); self.prop_asset_label=QLabel(); form.addRow(self.prop_id_label,self.id_edit); form.addRow(self.prop_type_label,self.type_edit)
            geom_widget=QWidget(); geom_grid=QGridLayout(geom_widget); geom_grid.setContentsMargins(0,0,0,0); geom_grid.setHorizontalSpacing(m['space_compact']); geom_grid.setVerticalSpacing(m['space_tight']); self.geom_spins={}; self.geom_labels={}
            for index,key in enumerate(('x','y','w','h')):
                row=index // 2; col=(index % 2) * 2; label=StudioMarkedLabel(key.upper()); self.geom_labels[key]=label; spin=QSpinBox(); spin.setObjectName('TechnicalInput'); spin.setMinimumWidth(56); spin.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed); spin.setRange(-8192 if key in ('x','y') else 1,8192); spin.valueChanged.connect(lambda value,field=key:self._apply_geometry_live(field,value)); spin.editingFinished.connect(self._finish_geometry_edit); self.geom_spins[key]=spin; geom_grid.addWidget(label,row,col); geom_grid.addWidget(spin,row,col+1)
            form.addRow(geom_widget); form.addRow(self.prop_asset_label,self.resource_edit); self.properties_card.body.addLayout(form)
            flags=QHBoxLayout(); self.lock_check=QCheckBox(); self.lock_check.toggled.connect(self._lock_changed); self.hidden_check=QCheckBox(); self.hidden_check.toggled.connect(self._hidden_changed); flags.addWidget(self.lock_check); flags.addWidget(self.hidden_check); flags.addStretch(1); self.properties_card.body.addLayout(flags); self.inspector_layout.addWidget(self.properties_card)

            self.align_card=ProfessionalPanel(); self.align_reference_combo=QComboBox(); self.align_reference_combo.addItem(self.tr('align.selection_bounds'),'selection'); self.align_reference_combo.addItem(self.tr('align.primary'),'primary'); self.align_reference_combo.addItem(self.tr('align.canvas'),'canvas'); self.align_card.body.addWidget(self.align_reference_combo); ag=QGridLayout(); ag.setSpacing(4); self.align_grid=ag; self.align_buttons={}
            for idx,(key,mode) in enumerate([('left','left'),('center_h','hcenter'),('right','right'),('top','top'),('center_v','vcenter'),('bottom','bottom')]):
                b=QPushButton(); b.clicked.connect(lambda _=False,m=mode:self.align_selected(m)); self.align_buttons[key]=b
            self.distribute_h=QPushButton(); self.distribute_h.clicked.connect(lambda:self.distribute_selected('horizontal')); self.distribute_v=QPushButton(); self.distribute_v.clicked.connect(lambda:self.distribute_selected('vertical')); self.snap_button=QPushButton(); self.snap_button.clicked.connect(self.snap_selected); self._layout_alignment_actions(False); self.align_card.body.addLayout(ag); self.measure_label=QLabel(); self.measure_label.setObjectName('Muted'); self.measure_label.setWordWrap(True); self.align_card.body.addWidget(self.measure_label); self.inspector_layout.addWidget(self.align_card); self.inspector_layout.addStretch(1)
            self.inspector_page.setWidget(self.inspector_inner); self.inspector_tabs.addTab(self.inspector_page,'')

            self.state_page=QScrollArea(); self.state_page.setWidgetResizable(True); self.state_page.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.state_inner=QWidget(); self.state_inner.setObjectName('InspectorRoot'); self.state_inner.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred); self.state_layout=QVBoxLayout(self.state_inner); self.state_layout.setContentsMargins(m['space_tight'],m['space_tight'],m['space_tight'],m['space_tight']); self.state_layout.setSpacing(m['space_section'])
            self.canvas_config_panel=ProfessionalPanel(); self.canvas_config_card=self.canvas_config_panel; cf=QFormLayout(); cf.setVerticalSpacing(6); cf.setRowWrapPolicy(QFormLayout.WrapLongRows); self.canvas_preset_combo=QComboBox(); self.canvas_preset_combo.addItems([*CANVAS_PRESETS.keys(),'Custom']); self.canvas_preset_combo.currentTextChanged.connect(self._canvas_preset_changed); self.canvas_width_spin=QSpinBox(); self.canvas_width_spin.setObjectName('TechnicalInput'); self.canvas_width_spin.setRange(16,4096); self.canvas_height_spin=QSpinBox(); self.canvas_height_spin.setObjectName('TechnicalInput'); self.canvas_height_spin.setRange(8,2048); self.canvas_height_spin.setSingleStep(8); self.canvas_apply_button=QPushButton(); self.canvas_apply_button.clicked.connect(self.apply_canvas_size); self.canvas_size_labels={'preset':QLabel(),'width':QLabel(),'height':QLabel()}; cf.addRow(self.canvas_size_labels['preset'],self.canvas_preset_combo); cf.addRow(self.canvas_size_labels['width'],self.canvas_width_spin); cf.addRow(self.canvas_size_labels['height'],self.canvas_height_spin); self.canvas_config_panel.body.addLayout(cf); self.canvas_config_panel.body.addWidget(self.canvas_apply_button); self.state_layout.addWidget(self.canvas_config_panel)
            self.runtime_panel=ProfessionalPanel(); self.runtime_card=self.runtime_panel
            self.state_editors={}
            self.preview_frame_section=QWidget(); pf=QVBoxLayout(self.preview_frame_section); pf.setContentsMargins(0,0,0,0); pf.setSpacing(m['space_tight']); self.preview_frame_title=QLabel(); self.preview_frame_title.setObjectName('PanelTitle'); self.preview_frame_label=QLabel(); self.preview_frame_label.setObjectName('TechnicalValue'); pf.addWidget(self.preview_frame_title); pf.addWidget(self.preview_frame_label); self.runtime_panel.body.addWidget(self.preview_frame_section)
            self.preview_state_section=QWidget(); ps=QVBoxLayout(self.preview_state_section); ps.setContentsMargins(0,0,0,0); ps.setSpacing(m['space_tight']); self.preview_state_title=QLabel(); self.preview_state_title.setObjectName('PanelTitle'); ps.addWidget(self.preview_state_title)
            self.state_status_label=QLabel(); self.state_status_label.setObjectName('StateSchemaStatus'); self.state_status_label.setWordWrap(True)
            self.state_form=QFormLayout(); self.state_form.setVerticalSpacing(m['space_compact']); self.state_form.setRowWrapPolicy(QFormLayout.WrapLongRows); self.state_form_host=QWidget(); self.state_form_host.setLayout(self.state_form); ps.addWidget(self.state_status_label); ps.addWidget(self.state_form_host); self.runtime_panel.body.addWidget(self.preview_state_section)
            self.preview_timeline_section=QWidget(); pt=QVBoxLayout(self.preview_timeline_section); pt.setContentsMargins(0,0,0,0); pt.setSpacing(m['space_tight']); self.preview_timeline_title=QLabel(); self.preview_timeline_title.setObjectName('PanelTitle'); pt.addWidget(self.preview_timeline_title)
            rf=QFormLayout(); rf.setVerticalSpacing(m['space_compact']); rf.setRowWrapPolicy(QFormLayout.WrapLongRows); self.speed_label=QLabel(); self.speed_combo=QComboBox(); self.speed_combo.addItems(RUN_SPEEDS); rf.addRow(self.speed_label,self.speed_combo); pt.addLayout(rf)
            self.timeline_status_label=QLabel(); self.timeline_status_label.setObjectName('Muted'); self.timeline_status_label.setWordWrap(True); pt.addWidget(self.timeline_status_label)
            rr=QHBoxLayout(); rr.setSpacing(m['space_tight']); self.play_button=QPushButton(); self.play_button.setObjectName('PrimaryButton'); self.play_button.clicked.connect(self.toggle_play); self.step_button=QPushButton(); self.step_button.clicked.connect(self.step_runtime); self.reset_button=QPushButton(); self.reset_button.clicked.connect(self.reset_runtime); rr.addWidget(self.play_button); rr.addWidget(self.step_button); rr.addWidget(self.reset_button); pt.addLayout(rr); self.elapsed_label=QLabel(); self.elapsed_label.setObjectName('TechnicalValue'); pt.addWidget(self.elapsed_label); self.runtime_panel.body.addWidget(self.preview_timeline_section)
            self.preview_validation_section=QWidget(); pv=QVBoxLayout(self.preview_validation_section); pv.setContentsMargins(0,0,0,0); pv.setSpacing(m['space_tight']); self.preview_validation_title=QLabel(); self.preview_validation_title.setObjectName('PanelTitle'); self.preview_validation_label=QLabel(); self.preview_validation_label.setObjectName('Muted'); self.preview_validation_label.setWordWrap(True); pv.addWidget(self.preview_validation_title); pv.addWidget(self.preview_validation_label); self.runtime_panel.body.addWidget(self.preview_validation_section); self.state_layout.addWidget(self.runtime_panel); self.state_layout.addStretch(1)
            self.speed_combo.currentTextChanged.connect(self._speed_changed)
            self.state_page.setWidget(self.state_inner); self.inspector_tabs.addTab(self.state_page,'')
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
            bar=self.menuBar(); self._menus['file']=bar.addMenu(''); self._menus['edit']=bar.addMenu(''); self._menus['arrange']=bar.addMenu(''); self._menus['view']=bar.addMenu(''); self._menus['tools']=bar.addMenu(''); self._menus['help']=bar.addMenu('')
            def action(name,menu,callback,shortcut=None):
                a=QAction(self); a.triggered.connect(callback); a.setShortcut(QKeySequence(shortcut)) if shortcut else None; menu.addAction(a); self._actions[name]=a; return a
            action('new_project',self._menus['file'],self.new_project,'Ctrl+N'); action('open_project',self._menus['file'],self.open_project_dialog,'Ctrl+Shift+O'); action('open_scene',self._menus['file'],self.open_scene_dialog,'Ctrl+O'); action('save',self._menus['file'],self.route_save,self.command_registry.shortcut('project.save')); action('handoff',self._menus['file'],self.export_handoff,'Ctrl+Shift+E'); action('export_current',self._menus['file'],self.export_current); action('export_all',self._menus['file'],self.export_all); self._menus['file'].addSeparator(); action('exit',self._menus['file'],self.close)
            action('undo',self._menus['edit'],self.route_undo,self.command_registry.shortcut('designer.undo')); action('redo',self._menus['edit'],self.route_redo,self.command_registry.shortcut('designer.redo')); action('add_placeholder',self._menus['edit'],self.add_placeholder); action('assign_bitmap',self._menus['edit'],self.assign_bitmap); action('delete',self._menus['edit'],self.remove_selected,'Delete')
            action('front',self._menus['arrange'],lambda:self._reorder_selected(True)); action('back',self._menus['arrange'],lambda:self._reorder_selected(False)); action('group',self._menus['arrange'],self.group_selected,'Ctrl+G'); action('ungroup',self._menus['arrange'],self.ungroup_selected,'Ctrl+Shift+G')
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
            self.inspector_page.viewport().installEventFilter(self)
            self.state_page.viewport().installEventFilter(self)
            self.canvas.installEventFilter(self)
            self.workspace_splitter.splitterMoved.connect(lambda *_:self._schedule_canvas_fit())
            self.vertical_splitter.splitterMoved.connect(lambda *_:self._schedule_canvas_fit())

        def eventFilter(self,obj,event):  # noqa: N802
            if obj is self.canvas_scroll.viewport() and event.type() in (QEvent.Resize,QEvent.Show): self._schedule_canvas_fit()
            if obj in (self.inspector_page.viewport(), self.state_page.viewport()) and event.type() in (QEvent.Resize,QEvent.Show):
                self._sync_scroll_content_width(self.inspector_page if obj is self.inspector_page.viewport() else self.state_page)
            if obj is self.canvas and event.type() in (QEvent.FocusIn,QEvent.FocusOut):
                focused=event.type()==QEvent.FocusIn
                self.canvas_card.setProperty('canvasFocus',focused)
                style=self.canvas_card.style(); style.unpolish(self.canvas_card); style.polish(self.canvas_card); self.canvas_card.update()
            return super().eventFilter(obj,event)

        def resizeEvent(self,event):  # noqa: N802
            super().resizeEvent(event); self._schedule_responsive()

        def _schedule_responsive(self): self.layout_timer.start()
        def _schedule_canvas_fit(self): QTimer.singleShot(16,self._fit_canvas_zoom)
        def _sync_scroll_content_width(self, scroll):
            viewport_width = scroll.viewport().width()
            if viewport_width <= 0:
                return
            content = scroll.widget()
            content.setMinimumWidth(0)
            content.setMaximumWidth(viewport_width)
            content.resize(viewport_width, max(content.height(), content.sizeHint().height()))
        def _layout_alignment_actions(self,compact):
            while self.align_grid.count(): self.align_grid.takeAt(0)
            placements=(('left',0,0,1,1),('right',0,1,1,1),('center_h',1,0,1,2),('top',2,0,1,1),('bottom',2,1,1,1),('center_v',3,0,1,2))
            columns=2; row=4
            for key,r,c,rs,cs in placements: self.align_grid.addWidget(self.align_buttons[key],r,c,rs,cs)
            for button in (self.distribute_h,self.distribute_v,self.snap_button):
                self.align_grid.addWidget(button,row,0,1,columns); row+=1
            for column in range(3): self.align_grid.setColumnStretch(column,1 if column<columns else 0)

        def _responsive_tick(self):
            if self._closing:
                return
            runtime=getattr(self,'_runtime_preferences',None) or RuntimeSettings.from_preferences(self.preferences)
            p=plan_layout(self.width(),self.height(),runtime.density,runtime.ui_scale); wp=workspace_plan(self.width(),self.height(),self.workspace_mode); bucket=(p.left_width,p.inspector_width,wp.compact)
            if bucket!=self._layout_bucket:
                self.left_card.setVisible(wp.left_visible)
                self.workspace_splitter.setSizes([p.left_width,p.canvas_width,p.inspector_width]); self._layout_alignment_actions(wp.compact); self._layout_bucket=bucket
            elif self.workspace_splitter.sizes() and self.workspace_splitter.sizes()[-1] > wp.inspector_width + 4:
                # A restored QSettings splitter state can retain an oversized inspector
                # after the responsive bucket was already computed for the new window size.
                self.workspace_splitter.setSizes([p.left_width,p.canvas_width,p.inspector_width])
            # QScrollArea can retain a content width from a restored layout
            # state.  Keep both inspector pages horizontally bounded by the
            # current viewport while allowing their content to grow vertically.
            for scroll in (self.inspector_page, self.state_page):
                self._sync_scroll_content_width(scroll)
            if (
                any(scroll.widget().width() > scroll.viewport().width() for scroll in (self.inspector_page, self.state_page))
                and getattr(self, '_scroll_width_resync_bucket', None) != bucket
            ):
                # A resize can update the viewport after this pass. One queued
                # retry per responsive bucket lets Qt settle without a timer loop.
                self._scroll_width_resync_bucket = bucket
                QTimer.singleShot(0, self._responsive_tick)
            hp=header_policy(p)
            self.hero_subtitle.setVisible(hp.show_subtitle)
            self.pixel_status.setVisible(hp.show_status)
            self.header_project.setVisible(hp.show_project)
            self.header_validate.setVisible(hp.show_validate)
            self.header_save.setVisible(hp.show_save)
            self.header_handoff.setVisible(hp.show_handoff)
            self.workspace_segment.setVisible(not hp.compact)
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
            # Workspace-mode changes alter editability/chrome, not scene truth. Do
            # not pay for a full render/validation cycle just to switch modes.
            mode_to_index = {WorkspaceMode.DESIGN: 0, WorkspaceMode.PIXEL: 1, WorkspaceMode.REVIEW: 2}
            index=mode_to_index.get(self.workspace_mode,0)
            if self.workspace_segment.currentIndex()!=index:
                blocker=QSignalBlocker(self.workspace_segment); self.workspace_segment.setCurrentIndex(index); del blocker
            review=self.workspace_mode==WorkspaceMode.REVIEW
            for widget in (self.add_button,self.assign_button,self.delete_button,self.lock_check,self.hidden_check): widget.setEnabled(not review)
            for spin in self.geom_spins.values(): spin.setEnabled(not review)
            self.align_card.setVisible(not review)
            if review:
                self._diagnostics_open=True; self.diagnostics_tabs.setCurrentIndex(1)
            self._sync_properties(); self._sync_context_actions(); self._sync_editor_chrome()
            self._layout_bucket=None; self._responsive_tick(); self.canvas.update()

        def _activate_scene_editor(self, mode):
            for i in range(self.editor_tabs.count()):
                if getattr(self.editor_tabs.widget(i),'document_id',None)=='scene:active':
                    self.editor_tabs.setCurrentIndex(i)
                    break
            self.set_workspace_mode(mode)

        def _workspace_segment_changed(self, index):
            """Route workspace mode and always reactivate the Scene Editor for Design/Review."""
            if index == 0:
                self._activate_scene_editor(WorkspaceMode.DESIGN)
            elif index == 1:
                editor=self.open_pixel_studio()
                if editor is None:self._sync_editor_chrome()
            elif index == 2:
                self._activate_scene_editor(WorkspaceMode.REVIEW)

        def show_performance_report(self):
            drag=self.profiler.summary('drag_preview'); full=self.profiler.summary('full_refresh')
            QMessageBox.information(self,self.tr('performance.title'),self.tr('performance.summary',drag_avg=drag.avg_ms,drag_max=drag.max_ms,full_avg=full.avg_ms,full_max=full.max_ms))

        # ---------- i18n ----------
        def retranslate_ui(self):
            t=self.tr; self.hero_title.setText(t('app.title')); self.hero_subtitle.setText(t('app.subtitle'))
            self.workspace_segment.setItemText(0,t('workspace.design')); self.workspace_segment.setItemText(1,t('action.pixel_studio')); self.workspace_segment.setItemText(2,t('workspace.review')); self.header_project.setText(''); self.header_project.setToolTip(t('action.open_project')); self.header_undo.setToolTip(t('action.undo')); self.header_redo.setToolTip(t('action.redo')); self.header_save.setText(t('action.save')); self.header_validate.setText(t('action.batch_validate')); self.header_handoff.setText(t('action.handoff')); self.header_diagnostics.setText(''); self.header_diagnostics.setToolTip(t('action.diagnostics')); self.header_agent.setText(''); self.header_agent.setToolTip(t('action.agent_bridge')); self.header_settings.setText(''); self.header_settings.setToolTip(t('action.preferences')+f" ({self.command_registry.shortcut('preferences.open')})")
            self.asset_empty_title.setText(t('panel.assets')); self.asset_empty_guidance.setText(t('asset.empty')); self.font_empty_title.setText(t('panel.fonts')); self.font_empty_guidance.setText(t('font.empty'))
            self.left_card.set_title(t('panel.workspace')); self.left_tabs.setTabText(0,t('panel.screens')); self.left_tabs.setTabText(1,t('panel.elements')); self.left_tabs.setTabText(2,t('panel.assets')); self.left_tabs.setTabText(3,t('panel.fonts')); self.font_new.setText(t('action.new_font')); self.font_open.setText(t('action.open_font')); self.font_rescan.setText(t('asset.rescan'))
            self.inspector_tabs.setTabText(0,t('panel.properties')); self.inspector_tabs.setTabText(1,t('panel.preview'))
            self.screen_new.setText(t('action.new_screen')); self.screen_duplicate.setText(t('action.duplicate')); self.screen_delete.setText(t('action.delete')); self.add_button.setText(t('action.add_placeholder')); self.assign_button.setText(t('action.assign_bitmap')); self.delete_button.setText(t('action.delete')); self.asset_search.setPlaceholderText(t('asset.search')); self.asset_import.setText(t('asset.import')); self.asset_rescan.setText(t('asset.rescan'))
            self.canvas_card.set_title(t('panel.canvas')); self.context_duplicate.setText(t('action.duplicate')); self._sync_context_actions(); self.canvas_card.set_subtitle(t('canvas.production',width=self.scene['canvas']['w'],height=self.scene['canvas']['h'])); self.zoom_label.setText(t('state.zoom')); self.grid_check.setText(t('toggle.grid')); self.bounds_check.setText(t('toggle.bounds')); self.ruler_check.setText(t('toggle.rulers')); self.zones_check.setText(t('toggle.zones')); self.canvas_hint.setText(t('canvas.overlay_hint'))
            self.properties_card.set_title(t('panel.properties')); self.prop_id_label.setText(t('property.id')); self.prop_type_label.setText(t('property.type')); self.prop_asset_label.setText(t('property.asset')); self.lock_check.setText(t('property.locked')); self.hidden_check.setText(t('property.hidden'))
            self.align_card.set_title(t('panel.arrange')); self.align_reference_combo.setItemText(self.align_reference_combo.findData('selection'),t('align.selection_bounds')); self.align_reference_combo.setItemText(self.align_reference_combo.findData('primary'),t('align.primary')); self.align_reference_combo.setItemText(self.align_reference_combo.findData('canvas'),t('align.canvas')); labels={'left':'align.left','center_h':'align.hcenter','right':'align.right','top':'align.top','center_v':'align.vcenter','bottom':'align.bottom'}
            for k,b in self.align_buttons.items(): b.setText(t(labels[k]))
            self.distribute_h.setText(t('align.distribute_h')); self.distribute_v.setText(t('align.distribute_v')); self.snap_button.setText(t('align.snap'))
            self.canvas_config_card.set_title(t('panel.canvas_settings')); self.canvas_size_labels['preset'].setText(t('canvas.preset')); self.canvas_size_labels['width'].setText(t('canvas.width')); self.canvas_size_labels['height'].setText(t('canvas.height')); self.canvas_apply_button.setText(t('action.apply_canvas'))
            self.runtime_card.set_title(t('panel.preview')); self.preview_frame_title.setText(t('preview.frame')); self.preview_state_title.setText(t('preview.state')); self.preview_timeline_title.setText(t('preview.timeline')); self.preview_validation_title.setText(t('preview.validation')); self.speed_label.setText(t('state.speed')); self.step_button.setText(t('action.step')); self.reset_button.setText(t('action.reset')); self._update_play_button(); self._update_timeline_controls(); self._update_preview_validation_summary()
            self.validation_card.set_title(t('panel.validation')); self.diff_card.set_title(t('panel.diff')); self.logs_card.set_title(t('panel.logs')); self.diagnostics_tabs.setTabText(0,t('panel.validation')); self.diagnostics_tabs.setTabText(1,t('panel.diff')); self.diagnostics_tabs.setTabText(2,t('panel.logs')); self.truth_label.setText(t('footer.truth'))
            if not self.profiler.summary('drag_preview').count:self.perf_label.setText(t('performance.preview_idle'))
            menu_names={'file':'menu.file','edit':'menu.edit','arrange':'menu.arrange','view':'menu.view','tools':'menu.tools','help':'menu.help'}
            for k,v in menu_names.items(): self._menus[k].setTitle(t(v))
            action_keys={'new_project':'action.new_project','open_project':'action.open_project','open_scene':'action.open_scene','save':'action.save','handoff':'action.handoff','export_current':'action.export_current','export_all':'action.export_all','exit':'action.exit','undo':'action.undo','redo':'action.redo','add_placeholder':'action.add_placeholder','assign_bitmap':'action.assign_bitmap','delete':'action.delete','front':'action.front','back':'action.back','group':'action.group','ungroup':'action.ungroup','diagnostics':'action.diagnostics','design_mode':'workspace.design','review_mode':'workspace.review','toggle_navigator':'view.navigator','toggle_inspector':'view.inspector','canvas_only':'view.canvas_only','reset_workspace':'view.reset_workspace','preferences':'action.preferences','asset_health':'action.asset_health','save_template':'action.save_template','insert_template':'action.insert_template','convert_asset':'action.convert_asset','export_c_header':'action.export_c_header','thumbnail_wall':'action.thumbnail_wall','autosave':'action.autosave','restore_autosave':'action.restore_autosave','command_palette':'command.title','pixel_studio':'action.pixel_studio','font_lab':'action.open_font','bitmap_text':'action.bitmap_text','agent_bridge':'action.agent_bridge','about':'action.about'}
            for name,key in action_keys.items(): self._actions[name].setText(t(key))
            for i in range(self.editor_tabs.count()):
                doc_id=getattr(self.editor_tabs.widget(i),'document_id',None)
                if doc_id=='scene:active':
                    self.editor_tabs.setTabText(i,t('workspace.design'))
                elif doc_id=='settings:preferences':
                    self.editor_tabs.setTabText(i,t('action.preferences').rstrip('…').rstrip('.'))
                elif isinstance(doc_id,str) and doc_id.startswith('font:'):
                    self.editor_tabs.setTabText(i,t('panel.fonts')+' · '+Path(doc_id[5:]).name)
            self._sync_runtime_controls(); self._retranslate_validation_panel(); self._update_measurement(); self._schedule_responsive()

        def change_language(self,language):
            if language not in SUPPORTED_LANGUAGES:return
            self.preferences.set('language',language)
            self.apply_preferences()
            self.logger.log('LANGUAGE',language=language)

        def _apply_ui_metrics(self,runtime):
            m=build_ui_metrics(runtime.density,runtime.ui_scale); self._ui_metrics=m
            if hasattr(self,'_root_layout'):
                self._root_layout.setContentsMargins(m['space_normal'],m['space_compact'],m['space_normal'],m['space_compact']); self._root_layout.setSpacing(m['space_compact'])
            if hasattr(self,'_header_bar'): self._header_bar.setMinimumHeight(m['control']+2*m['space_tight'])
            if hasattr(self,'_header_layout'):
                self._header_layout.setContentsMargins(m['space_compact'],m['space_micro'],m['space_compact'],m['space_micro']); self._header_layout.setHorizontalSpacing(m['space_compact'])
            if hasattr(self,'_command_left_layout'): self._command_left_layout.setSpacing(m['space_compact'])
            if hasattr(self,'_command_right_layout'): self._command_right_layout.setSpacing(m['space_compact'])
            for button in (getattr(self,'header_project',None),getattr(self,'header_undo',None),getattr(self,'header_redo',None),getattr(self,'header_diagnostics',None),getattr(self,'header_agent',None),getattr(self,'header_settings',None)):
                if button is not None: button.setIconSize(QSize(m['icon'],m['icon']))
            for panel in self.findChildren(ProfessionalPanel): panel.apply_metrics(m)
            if hasattr(self,'canvas_card'):
                self.canvas_card.body.setContentsMargins(m['space_section'],m['space_group'],m['space_section'],m['space_section']); self.canvas_card.body.setSpacing(m['space_normal'])
            if hasattr(self,'inspector_layout'):
                self.inspector_layout.setContentsMargins(m['space_tight'],m['space_tight'],m['space_tight'],m['space_tight']); self.inspector_layout.setSpacing(m['space_section'])
            if hasattr(self,'state_layout'):
                self.state_layout.setContentsMargins(m['space_tight'],m['space_tight'],m['space_tight'],m['space_tight']); self.state_layout.setSpacing(m['space_section'])
            if hasattr(self,'geom_grid'):
                self.geom_grid.setHorizontalSpacing(m['space_compact']); self.geom_grid.setVerticalSpacing(m['space_tight'])

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

            metrics_signature=(runtime.density,runtime.ui_scale)
            metrics_changed=metrics_signature!=self._applied_style_signature
            if initial or metrics_changed or resolved_theme_changed:
                app=QApplication.instance()
                if app is not None:_apply_application_theme(app,theme,runtime.density,runtime.ui_scale)
                self._applied_style_signature=metrics_signature
                if initial or metrics_changed:self._apply_ui_metrics(runtime)
                if hasattr(self,'canvas'): self.canvas.set_theme(theme)
                self._apply_status_theme(theme)
                if self._preferences_view is not None:
                    try:self._preferences_view.apply_runtime_settings(runtime)
                    except RuntimeError:self._preferences_view=None
                if self._preferences_window is not None:
                    try:self._preferences_window.apply_runtime_settings(runtime)
                    except RuntimeError:self._preferences_window=None
                self._schedule_responsive()
                # Apply the first responsive pass synchronously so callers that
                # switch metrics and immediately inspect layout state cannot see
                # stale scroll-content widths before the queued timer fires.
                self._responsive_tick()

            # Language is independent from renderer/theme. Never refresh product truth here.
            if initial or delta.language_changed:
                language=runtime.language
                if language in SUPPORTED_LANGUAGES and language!=self.tr.language:self.tr.set_language(language)
                if self._preferences_view is not None:
                    try:self._preferences_view.set_language(language)
                    except RuntimeError:self._preferences_view=None
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

        def toggle_preferences(self, _checked=False):
            current=self.editor_tabs.currentWidget() if hasattr(self,'editor_tabs') else None
            if getattr(current,'document_id',None)=='settings:preferences':
                target_id=getattr(self,'_last_work_editor_doc_id','scene:active')
                target_index=-1
                for i in range(self.editor_tabs.count()):
                    if getattr(self.editor_tabs.widget(i),'document_id',None)==target_id:
                        target_index=i; break
                if target_index<0:
                    for i in range(self.editor_tabs.count()):
                        if getattr(self.editor_tabs.widget(i),'document_id',None)=='scene:active':
                            target_index=i; break
                if target_index<0: target_index=0
                self.editor_tabs.setCurrentIndex(target_index); self._sync_editor_chrome(); return self.editor_tabs.currentWidget()
            return self.open_preferences()

        def open_preferences(self):
            current_index=self.editor_tabs.currentIndex() if hasattr(self,'editor_tabs') else -1
            current=self.editor_tabs.currentWidget() if hasattr(self,'editor_tabs') else None
            current_doc_id=getattr(current,'document_id',None)
            if current_index >= 0 and current_doc_id and current_doc_id!='settings:preferences':
                self._last_work_editor_doc_id=current_doc_id
            doc_id='settings:preferences'
            for i in range(self.editor_tabs.count()):
                if getattr(self.editor_tabs.widget(i),'document_id',None)==doc_id:
                    view=self.editor_tabs.widget(i); self.editor_tabs.setCurrentIndex(i); view.stabilize_layout(); QTimer.singleShot(0,view.stabilize_layout); self._sync_editor_chrome(); return view
            view=PreferencesView(self.preferences,self.tr,parent=self.editor_tabs); view.document_id='settings:preferences'; self._preferences_view=view
            view.preferencesChanged.connect(self.apply_preferences); view.clearAssetCacheRequested.connect(self._clear_asset_cache); view.resetWorkspaceRequested.connect(self.reset_workspace_layout)
            runtime=self._runtime_preferences or RuntimeSettings.from_preferences(self.preferences); view.apply_runtime_settings(runtime)
            idx=self.editor_tabs.addTab(view,self.tr('action.preferences').rstrip('…').rstrip('.')); self.editor_tabs.setCurrentIndex(idx); view.stabilize_layout(); QTimer.singleShot(0,view.stabilize_layout); self._sync_editor_chrome(); return view

        def _clear_asset_cache(self):
            self.asset_library.clear_cache(); self._scan_assets(); self.app_status.setText(self.tr('status.asset_normalized')); self.app_status.set_status('success')

        # ---------- project/screens/assets ----------
        def _confirm_scene_transition(self):
            return self._project_confirm_scene_transition()

        def _confirm_project_transition(self):
            return self._project_confirm_project_transition()

        def _close_project_bound_editors(self):
            return self._project_close_project_bound_editors()

        def open_project_dialog(self):
            return self._project_open_project_dialog()
        def _load_project_candidate(self,path:Path):
            return self._project_load_project_candidate(path)
        def _remember_last_project(self,value):
            return self._project_remember_last_project(value)
        def _commit_project_candidate(self,project,scene):
            return self._project_commit_project_candidate(project,scene)
        def _open_project(self,path:Path):
            return self._project_open_project(path)
        def new_project(self):
            return self._project_new_project()
        def _rebuild_screens(self):
            return self._project_rebuild_screens()
        def _screen_changed(self,current,_prev):
            return self._project_screen_changed(current,_prev)
        def new_screen(self):
            return self._project_new_screen()
        def duplicate_screen(self):
            return self._project_duplicate_screen()
        def delete_screen(self):
            return self._project_delete_screen()

        def open_scene_dialog(self):
            return self._project_open_scene_dialog()

        def _sync_asset_directory_watchers(self):
            return self._resource_sync_asset_directory_watchers()

        def _scan_assets(self):
            return self._resource_scan_assets()
        def _filter_assets(self,query):
            return self._resource_filter_assets(query)
        def import_asset(self):
            return self._resource_import_asset()
        def place_asset(self,item=None):
            return self._resource_place_asset(item)
        def _asset_directory_changed(self,_path): return self._resource_asset_directory_changed(_path)
        def show_asset_health(self):
            return self._resource_show_asset_health()

        def save_template(self):
            return self._resource_save_template()

        def insert_template(self):
            return self._resource_insert_template()

        def convert_asset(self):
            return self._resource_convert_asset()

        def _project_symbol(self):
            return self._resource_project_symbol()

        def export_c_header(self):
            return self._resource_export_c_header()

        def export_thumbnail_wall(self):
            return self._resource_export_thumbnail_wall()

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
                if not self.selected_id:
                    self.id_edit.clear(); self.type_edit.clear(); self.resource_edit.clear(); self._update_inspector_modified_markers(None); self._sync_context_actions(); return
                e=self.session.document.element(self.selected_id); g=self.session.geometry(self.selected_id); self.id_edit.setText(self.selected_id); self.type_edit.setText(str(e.get('type',''))); self.resource_edit.setText(self._resource_description(e)); vals={'x':g.x,'y':g.y,'w':g.w,'h':g.h}
                for k,s in self.geom_spins.items():
                    s.setValue(vals[k])
                    editable=bool(g.editable[k]) and not e.get('locked') and self.workspace_mode==WorkspaceMode.DESIGN
                    if k in ('w','h'):
                        s.setEnabled(not e.get('locked')); s.setReadOnly(not editable)
                        s.setToolTip('' if editable else self.tr('property.native_size_locked'))
                    else:
                        s.setReadOnly(False); s.setEnabled(editable)
                self.lock_check.setChecked(bool(e.get('locked'))); self.hidden_check.setChecked(bool(e.get('hidden'))); self.context_label.setText(self.selected_id); self._update_inspector_modified_markers(e); self._sync_context_actions()
            finally:self._syncing=False
        def _sync_context_actions(self):
            if not hasattr(self,'context_bar'):return
            locks=[]
            for eid in self.selected_ids:
                try:locks.append(bool(self.session.document.element(eid).get('locked')))
                except Exception:locks.append(False)
            actions=canvas_context_actions(self.selected_ids,self.workspace_mode.value,locks)
            self.context_bar.setVisible(bool(actions))
            self.context_duplicate.setVisible('duplicate' in actions)
            lock_action='unlock' if 'unlock' in actions else 'lock'
            self.context_lock.setVisible(lock_action in actions)
            self.context_lock.setText(self.tr('action.unlock') if lock_action=='unlock' else self.tr('action.lock'))
            self.context_label.setText(self.selected_id or '')

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

        def _start_canvas_drag(self,_element_id=None):
            self.deferred_refresh_timer.stop()
            self.validation_timer.stop()
            self._deferred_result=None

        def _finish_canvas_drag(self,_element_id=None):
            self.session.end_coalesced_edit()
            self.refresh_all(keep_selection=True)
            # The commit path validates synchronously below.  Keep the rest of
            # the deferred bookkeeping, but do not validate the same gesture a
            # second time when the deferred timer expires.
            self.deferred_refresh_timer.stop()
            self.validation_timer.stop()
            self._update_validation_panel()
            self._run_deferred_refresh(include_validation=False)

        def refresh_drag_preview(self):
            """Fast interaction path: render + canvas + geometry only.

            Validation, diff, evidence hashing, file-watcher maintenance and log
            emission are deliberately deferred until gesture commit.
            """
            started=perf_counter(); result=self.session.render(); self.last_render=result
            guides=smart_guides(self.session,self.selected_id,tolerance=1) if self.selected_id else {'x':(),'y':()}
            self.canvas.set_guides(guides,anchors=True); self.canvas.set_zones(self.scene.get('zones',[]) if self.zones_check.isChecked() else []); self.canvas.set_frame(result,self.selected_ids)
            self._sync_properties(); self._update_document_dirty_marker()
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
        def _clear_state_editors(self):
            while self.state_form.count():
                item=self.state_form.takeAt(0); widget=item.widget()
                if widget is not None: widget.deleteLater()
            self.state_editors.clear()

        def _configure_state_controls(self):
            self.preview_capabilities=preview_capabilities(self.scene); self._timeline_meta=timeline_metadata(self.scene); self._clear_state_editors(); self._syncing=True
            result=build_state_editor_specs(schema_from_scene(self.scene))
            if not result.valid:
                codes=', '.join(str(error.get('code','SCHEMA')) for error in result.errors)
                self.state_status_label.setText(self.tr('state.schema_invalid',errors=codes)); self.state_status_label.setVisible(True)
            elif not result.fields:
                self.state_status_label.setText(self.tr('state.empty')); self.state_status_label.setVisible(True)
            else:
                self.state_status_label.clear(); self.state_status_label.setVisible(False)
                for field in result.fields:
                    label=QLabel(field.label); label.setObjectName(f'StateLabel_{field.name}')
                    if field.editor_kind=='combo':
                        editor=QComboBox(); blocker=QSignalBlocker(editor)
                        for value in field.values: editor.addItem(str(value),value)
                        editor.setCurrentIndex(0 if field.values else -1); del blocker
                        editor.currentIndexChanged.connect(lambda _index,name=field.name:self._state_editor_combo_changed(name))
                    else:
                        editor=QSpinBox(); editor.setRange(field.minimum,field.maximum); editor.setValue(field.initial)
                        editor.valueChanged.connect(lambda value,name=field.name:self._state_changed(name,value))
                    editor.setObjectName(f'StateEditor_{field.name}'); editor.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
                    self.state_form.addRow(label,editor); self.state_editors[field.name]={'name':field.name,'spec':field.spec,'field':field,'label':label,'editor':editor}
            self.canvas_width_spin.setValue(int(self.scene['canvas']['w'])); self.canvas_height_spin.setValue(int(self.scene['canvas']['h'])); dims=(int(self.scene['canvas']['w']),int(self.scene['canvas']['h'])); self.canvas_preset_combo.setCurrentText(next((n for n,s in CANVAS_PRESETS.items() if s==dims),'Custom')); self._syncing=False
            self._timeline_defined='timeline' in self.preview_capabilities; self.preview_state_section.setVisible('state' in self.preview_capabilities); self.preview_timeline_section.setVisible(self._timeline_defined); self.preview_validation_section.setVisible('validation' in self.preview_capabilities); self._update_timeline_controls()
        def _canvas_preset_changed(self,name):
            if self._syncing or name not in CANVAS_PRESETS:return
            w,h=CANVAS_PRESETS[name]; self._syncing=True; self.canvas_width_spin.setValue(w); self.canvas_height_spin.setValue(h); self._syncing=False
        def apply_canvas_size(self):
            try:self.session.set_canvas_size(self.canvas_width_spin.value(),self.canvas_height_spin.value()); self.refresh_all(keep_selection=True); self.retranslate_ui(); self._fit_canvas_zoom()
            except Exception as exc:self._show_error(str(exc))
        def _state_editor_combo_changed(self,name):
            binding=self.state_editors.get(name)
            if binding is not None: self._state_changed(name,binding['editor'].currentData(),binding=binding)

        def _update_timeline_controls(self):
            defined=bool(getattr(self,'_timeline_defined',False)); self.preview_timeline_section.setVisible(defined); controls=(self.play_button,self.step_button,self.reset_button,self.speed_label,self.speed_combo)
            for widget in controls: widget.setEnabled(defined)
            self.timeline_status_label.setVisible(False)
            meta=getattr(self,'_timeline_meta',{'step':1,'unit':'step'}); self.elapsed_label.setText(self.tr('preview.timeline_position',position=self.session.runtime.elapsed,unit=meta.get('unit','step')) if defined else '')
            action=self._actions.get('play') if hasattr(self,'_actions') else None
            if action is not None: action.setEnabled(defined)

        def _sync_runtime_controls(self):
            state=self.session.runtime.state; self._syncing=True
            for name,binding in self.state_editors.items():
                editor=binding['editor']; field=binding['field']; blocker=QSignalBlocker(editor); value=state.get(name,field.initial)
                valid,value=coerce_editor_value(field,value)
                if valid:
                    if field.editor_kind=='combo': editor.setCurrentIndex(max(0,editor.findData(value)))
                    else: editor.setValue(value)
                del blocker
            self._syncing=False; self._update_timeline_controls()
        def _state_changed(self,name,value,*,binding=None):
            if self._syncing:return
            binding=binding or self.state_editors.get(name)
            if binding is None:return
            valid,value=coerce_editor_value(binding['field'],value)
            if not valid:return
            try:self.session.set_state(name,value); self.refresh_all(keep_selection=True)
            except Exception as exc:self._show_error(str(exc)); self._sync_runtime_controls()
        def _speed_changed(self,_v):
            if self.run_timer.isActive():self.run_timer.start(RUN_SPEEDS.get(self.speed_combo.currentText(),1000))
        def toggle_play(self):
            if not getattr(self,'_timeline_defined',False):return
            self.run_timer.stop() if self.run_timer.isActive() else self.run_timer.start(RUN_SPEEDS.get(self.speed_combo.currentText(),1000)); self._update_play_button()
        def _update_play_button(self):
            text=self.tr('action.pause') if self.run_timer.isActive() else self.tr('action.play'); self.play_button.setText(text); action=self._actions.get('play') if hasattr(self,'_actions') else None; action.setText(text) if action else None
        def _runtime_tick(self):
            if getattr(self,'_timeline_defined',False):self.session.step(self._timeline_meta['step']); self.refresh_all(keep_selection=True)
        def step_runtime(self):
            if getattr(self,'_timeline_defined',False):self.session.step(self._timeline_meta['step']); self.refresh_all(keep_selection=True)
        def reset_runtime(self):
            if not getattr(self,'_timeline_defined',False):return
            self.run_timer.stop(); self._update_play_button(); self.session.reset(); self.refresh_all(keep_selection=True)

        # ---------- canvas / zoom / diff ----------
        def _zoom_changed(self):
            data=self.zoom_combo.currentData(); self._fit_canvas_zoom() if data=='auto' else self.canvas.set_zoom(int(data))
        def _fit_canvas_zoom(self):
            if self._closing:
                return
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

        def _update_preview_frame_summary(self,result):
            if not hasattr(self,'preview_frame_label') or result is None:return
            raw=result.framebuffer.to_vlsb(); lit=sum(sum(row) for row in result.framebuffer.to_rows())
            self.preview_frame_label.setText(self.tr('preview.frame_summary',width=result.framebuffer.width,height=result.framebuffer.height,bytes=len(raw),lit=lit))
            return len(raw),lit

        def _update_preview_validation_summary(self,findings=None):
            if not hasattr(self,'preview_validation_label'):return
            values=list(self._last_validation_findings if findings is None else findings)
            self.preview_validation_label.setText(self.tr('preview.valid') if not values else self.tr('preview.invalid',count=len(values)))

        # ---------- validation / logs / refresh ----------
        def _render_validation_panel(self,findings):
            self.validation_list.clear()
            if not findings:self.validation_list.addItem(self.tr('finding.none')); self.validation_status.setText(self.tr('status.valid')); self.validation_status.set_status('success')
            else:
                blockers=sum(1 for f in findings if f.severity in {'ERROR','BLOCKER'}); self.validation_status.setText(self.tr('status.invalid',count=len(findings),blockers=blockers)); self.validation_status.set_status('danger' if blockers else 'warning'); [self.validation_list.addItem(f'{f.severity}/{f.code} — {f.message}') for f in findings]
            self._update_preview_validation_summary(findings); return findings
        def _update_validation_panel(self):
            findings=list(self.session.validate()); findings.extend(check_design_rules(self.scene,self.scene.get('_design_rules') or {})); self._last_validation_findings=list(findings); return self._render_validation_panel(findings)
        def _retranslate_validation_panel(self):
            # Language switching must not synchronously re-run validation. Scene edits
            # update the cache through refresh_all; here we only repaint translated chrome.
            return self._render_validation_panel(list(getattr(self,'_last_validation_findings',())))
        def batch_validate(self):
            matrix=build_state_matrix(self.scene,integer_policy='boundaries'); summary=validate_matrix(self.scene,matrix); rules=check_design_rules(self.scene,self.scene.get('_design_rules') or {}); rule_blockers=sum(1 for f in rules if f.severity in {'ERROR','BLOCKER'}); findings=summary.findings+len(rules); blockers=summary.blockers+rule_blockers; self.logger.log('BATCH_VALIDATE',cases=summary.cases,findings=findings,blockers=blockers); self.app_status.setText(self.tr('batch.status',cases=summary.cases,findings=findings,blockers=blockers)); self.app_status.set_status('success' if blockers==0 else 'danger'); self._update_validation_panel()
        def _schedule_deferred_refresh(self,result=None):
            if result is not None:self._deferred_result=result
            runtime=getattr(self,'_runtime_preferences',None) or RuntimeSettings.from_preferences(self.preferences)
            delay=250 if runtime.validation_mode=='idle' else (70 if runtime.validation_mode=='continuous' else 120)
            self.deferred_refresh_timer.start(delay)

        def _run_deferred_refresh(self,*,include_validation=True):
            result=self._deferred_result or getattr(self,'last_render',None); self._deferred_result=None
            if result is None:return
            started=perf_counter(); self._update_validation_panel() if include_validation else None; self._update_diff(result.framebuffer); self._update_asset_watcher(result.used_files)
            evidence=frame_evidence(result,dict(self.session.runtime.state),elapsed=self.session.runtime.elapsed,project_root=scene_root(self.scene)); signature=(evidence['sha256'],tuple(evidence['state'].items()),evidence['elapsed'])
            if signature!=self._last_frame_signature:self.logger.log('FRAME',**evidence); self._last_frame_signature=signature
            self.profiler.record('deferred_refresh',(perf_counter()-started)*1000.0)

        def refresh_all(self,*,keep_selection=False):
            started=perf_counter(); plan=RefreshWorkPlan.for_scene_commit(); result=self.session.render(); self.last_render=result
            guides=smart_guides(self.session,self.selected_id,tolerance=1) if self.selected_id else {'x':(),'y':()}
            self.canvas.set_guides(guides,anchors=False); self.canvas.set_zones(self.scene.get('zones',[]) if self.zones_check.isChecked() else []); self.canvas.set_overlays(grid=self.grid_check.isChecked(),bounds=self.bounds_check.isChecked(),rulers=self.ruler_check.isChecked()); self.canvas.set_frame(result,self.selected_ids); self._schedule_canvas_fit()
            self._syncing=True; self.canvas_width_spin.setValue(int(self.scene['canvas']['w'])); self.canvas_height_spin.setValue(int(self.scene['canvas']['h'])); dims=(int(self.scene['canvas']['w']),int(self.scene['canvas']['h'])); self.canvas_preset_combo.setCurrentText(next((n for n,s in CANVAS_PRESETS.items() if s==dims),'Custom')); self._syncing=False
            if keep_selection and plan.properties:self._sync_properties()
            if plan.runtime:self._sync_runtime_controls()
            bytes_count,lit=self._update_preview_frame_summary(result); self.frame_status.setText(self.tr('status.frame',bytes=bytes_count,lit=lit)); self.frame_status.set_status('neutral')
            self._update_document_dirty_marker(); self.setWindowTitle(APP_TITLE+(' •' if self.session.document.dirty else '')); self._schedule_deferred_refresh(result)
            elapsed=(perf_counter()-started)*1000.0; self.profiler.record('full_refresh',elapsed); summary=self.profiler.summary('full_refresh'); self.perf_label.setToolTip(self.tr('performance.full_refresh_tip',latest=summary.latest_ms,avg=summary.avg_ms,max=summary.max_ms))

        def _update_asset_watcher(self,used_files):
            wanted={str(Path(p).resolve()) for p in used_files if Path(p).exists()}; current=set(self.asset_watcher.files()); remove=list(current-wanted); add=list(wanted-current); self.asset_watcher.removePaths(remove) if remove else None; self.asset_watcher.addPaths(add) if add else None
        def _asset_changed(self,path):
            if self._closing:
                return
            self.logger.log('ASSET_CHANGED',path=path); self.refresh_all(keep_selection=True); QTimer.singleShot(80,self._scan_assets)
        def _on_log(self,record):
            if not hasattr(self,'log_text'):self.pending_logs.append(record); return
            self.log_text.appendPlainText(json.dumps(record,ensure_ascii=False,sort_keys=True)); bar=self.log_text.verticalScrollBar(); bar.setValue(bar.maximum())
        def _flush_pending_logs(self):
            for r in self.pending_logs:self._on_log(r)
            self.pending_logs.clear()

        def duplicate_selected_elements(self):
            return self._designer_duplicate_selected_elements()

        def toggle_selected_lock(self):
            return self._designer_toggle_selected_lock()

        # ---------- edit / autosave ----------
        def undo(self):
            return self._designer_undo()
        def redo(self):
            return self._designer_redo()
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
            try:self.session.remove_elements(self.selected_ids)
            except Exception as exc:self._show_error(str(exc));return
            self.selected_ids=[]; self.selected_id=None; self._rebuild_elements(); self.refresh_all(keep_selection=True)
        def _autosave_tick(self,force=False):
            if force or self.session.document.dirty:
                try:path=self.autosave.snapshot(reason='manual' if force else 'timer')
                except (OSError, ValueError) as exc:
                    self.logger.log('AUTOSAVE_FAIL',error=str(exc)); self.app_status.setText(self.tr('status.autosave_failed')); self.app_status.setToolTip(str(exc)); self.app_status.set_status('danger'); return False
                self.logger.log('AUTOSAVE',path=str(path)); self.app_status.setText(self.tr('status.autosaved')); self.app_status.setToolTip(''); self.app_status.set_status('neutral'); return path
        def _prompt_recovery_if_needed(self):
            if self._closing:
                return
            runtime=getattr(self,'_runtime_preferences',RuntimeSettings.from_preferences(self.preferences))
            if not runtime.prompt_recovery:return
            candidate=self.autosave.recovery_candidate()
            if not candidate:return
            box=QMessageBox(self); self._recovery_prompt=box; box.setWindowTitle(self.tr('autosave.recovery_title')); box.setText(self.tr('autosave.recovery_message')); box.setInformativeText(str(candidate)); box.setStandardButtons(QMessageBox.Yes|QMessageBox.No); box.setDefaultButton(QMessageBox.Yes)
            def complete(result):
                self._recovery_prompt=None
                if result != QMessageBox.Yes:return
                try:payload=AutoSaveManager.load_snapshot(candidate)
                except Exception as exc:self._show_error(str(exc));return
                payload['_path']=self.scene['_path']; payload['_root']=self.scene['_root']; self._reset_session(payload); self.session.document.dirty=True; self.logger.log('AUTOSAVE_RECOVERY',path=str(candidate))
            box.finished.connect(complete); box.open()

        def restore_autosave(self):
            candidate=self.autosave.latest_recovery()
            if not candidate:return self._show_error(self.tr('autosave.none'))
            try:payload=AutoSaveManager.load_snapshot(candidate)
            except Exception as exc:self._show_error(str(exc));return
            if not self._confirm_scene_transition():return
            payload['_path']=self.scene['_path']; payload['_root']=self.scene['_root']; self._reset_session(payload); self.session.document.dirty=True; self.logger.log('AUTOSAVE_RESTORE',path=str(candidate))

        # ---------- save/export/handoff ----------
        def save_scene(self):
            return self._project_save_scene()
        def export_current(self):
            return self._project_export_current()
        def export_all(self):
            return self._project_export_all()
        def _perform_export(self,output,states):
            return self._project_perform_export(output,states)
        def export_handoff(self):
            return self._project_export_handoff()

        def _sync_editor_chrome(self):
            return self._editor_sync_chrome()

        def _editor_tab_changed(self,index):
            return self._editor_tab_changed_impl(index)

        def _close_editor_tab(self,index):
            if index<=0:return
            widget=self.editor_tabs.widget(index)
            if hasattr(widget,'can_close') and not widget.can_close():return
            if getattr(widget,'document_id',None)=='settings:preferences':
                if hasattr(widget,'flush_pending_save'):widget.flush_pending_save()
                self._preferences_view=None; self.editor_tabs.removeTab(index); widget.deleteLater(); return
            if editor_is_dirty(widget):
                choice=QMessageBox.question(self,self.tr('dialog.close'),self.tr('dialog.save_changes'),QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
                if choice==QMessageBox.Cancel:return
                if choice==QMessageBox.Save and hasattr(widget,'save'):
                    try:widget.save()
                    except Exception as exc:self._show_error(str(exc));return
                    if editor_is_dirty(widget):return
            doc_id=getattr(widget,'document_id',None); self.editor_tabs.removeTab(index); self.editor_registry.close(doc_id) if doc_id else None; widget.deleteLater()

        def route_save(self):
            current=self.editor_tabs.currentWidget() if hasattr(self,'editor_tabs') else None
            if getattr(current,'document_id',None)=='settings:preferences':
                return current.flush_pending_save() if hasattr(current,'flush_pending_save') else None
            editor=self.editor_registry.active
            return editor.save() if editor else self.save_scene()
        def route_undo(self):
            current=self.editor_tabs.currentWidget() if hasattr(self,'editor_tabs') else None
            if getattr(current,'document_id',None)=='settings:preferences':return None
            editor=self.editor_registry.active
            return editor.undo() if editor else self.undo()
        def route_redo(self):
            current=self.editor_tabs.currentWidget() if hasattr(self,'editor_tabs') else None
            if getattr(current,'document_id',None)=='settings:preferences':return None
            editor=self.editor_registry.active
            return editor.redo() if editor else self.redo()

        def open_pixel_studio(self):
            return self._editor_open_pixel_studio()

        def _pixel_editor_identity_changed(self,path,editor=None):
            if editor is None:return
            try:self.editor_registry.rekey(editor)
            except (KeyError,ValueError) as exc:self._show_error(str(exc));return
            self.logger.log('PIXEL_ASSET_OPENED',path=str(path))

        def _pixel_asset_saved(self,path,editor=None):
            return self._editor_pixel_asset_saved(path, editor)

        def _font_root(self):
            return self._resource_font_root()

        def _scan_fonts(self):
            return self._resource_scan_fonts()

        def new_font_pack(self):
            return self._resource_new_font_pack()

        def open_font_lab(self,root=None):
            return self._editor_open_font_lab(root)

        def insert_bitmap_text(self):
            return self._resource_insert_bitmap_text()

        def toggle_agent_bridge(self):
            if self.agent_bridge.running:
                self.agent_bridge.stop(); self.agent_status.setText(self.tr('agent.off')); self.header_agent.setProperty('active',False); return
            endpoint=self.agent_bridge.start(); self.agent_status.setText(self.tr('agent.status.local',port=endpoint['port'])); QMessageBox.information(self,self.tr('agent.bridge.title'),self.tr('agent.bridge.started',host=endpoint['host'],port=endpoint['port'],permission=endpoint['permission'],token=endpoint['token']))

        def _agent_command_completed(self,response):
            if 'result' not in response or response['result'].get('revision') is None:
                return
            result=response['result']
            if result.get('active_screen_changed'):
                # Automation API 1.x switches the existing scene/session object in
                # place.  Rebind only UI projections; do not create a second Agent
                # service or a second source of project truth.
                self.autosave = AutoSaveManager(self.scene, keep=int(self.preferences.get('autosave.snapshots', 10)))
                self._configure_state_controls(); self._rebuild_screens(); self._capture_saved_baseline(); QTimer.singleShot(0,self._schedule_post_show_startup)
            elif result.get('project_structure_changed'):
                self._rebuild_screens()
            self.selected_ids=list(self.selection_model.ids); self.selected_id=self.selection_model.primary_id; self._rebuild_elements(); self.refresh_all(keep_selection=True); self.logger.log('AGENT_COMMAND',response=response)

        def show_about(self):
            QMessageBox.information(self,self.tr('action.about'),f'<b>MonoOLED Studio</b><br>Version {APP_VERSION}<br><br>{self.tr("app.subtitle")}')

        # ---------- command palette ----------
        def show_command_palette(self):
            cmds=[('save',self.tr('action.save'),self.route_save),('validate',self.tr('action.batch_validate'),self.batch_validate),('handoff',self.tr('action.handoff'),self.export_handoff),('undo',self.tr('action.undo'),self.route_undo),('redo',self.tr('action.redo'),self.route_redo),('assets',self.tr('action.asset_health'),self.show_asset_health),('template_save',self.tr('action.save_template'),self.save_template),('template_insert',self.tr('action.insert_template'),self.insert_template),('convert',self.tr('action.convert_asset'),self.convert_asset),('c_header',self.tr('action.export_c_header'),self.export_c_header),('overview',self.tr('action.thumbnail_wall'),self.export_thumbnail_wall),('diagnostics',self.tr('action.diagnostics'),self.toggle_diagnostics),('design_mode',self.tr('workspace.design'),lambda:self.set_workspace_mode(WorkspaceMode.DESIGN)),('review_mode',self.tr('workspace.review'),lambda:self.set_workspace_mode(WorkspaceMode.REVIEW)),('performance',self.tr('performance.title'),self.show_performance_report)]
            CommandPalette(self.tr,cmds,self).exec()

        # ---------- diagnostics / window persistence ----------
        def _show_error(self,message):
            message=str(message); get_logger('ui').error('%s',message)
            concise=message.splitlines()[0].strip() if message.strip() else self.tr('error.summary')
            if len(concise)>180: concise=concise[:177]+'…'
            box=QMessageBox(QMessageBox.Critical,self.tr('dialog.error'),self.tr('error.summary'),parent=self); box.setObjectName('ErrorSummary'); box.setInformativeText(concise); box.setDetailedText(message); box.exec()
            self.app_status.setText(self.tr('error.status')); self.app_status.setToolTip(message); self.app_status.set_status('danger')
        def layout_violations(self):
            issues=[]; scroll_areas=(self.inspector_page,self.state_page)
            for scroll in scroll_areas:
                if scroll.widget().width()>scroll.viewport().width(): issues.append('horizontal-overflow:'+scroll.objectName())
            leaves=[
                self.id_edit,self.type_edit,self.resource_edit,*self.geom_spins.values(),
                self.canvas_width_spin,self.canvas_height_spin,self.canvas_apply_button,
                self.header_pixel,self.header_review,self.header_project,self.header_undo,self.header_redo,self.header_settings,
                self.header_save,self.header_validate,self.header_handoff,self.header_diagnostics,
                self.screen_new,self.screen_duplicate,self.screen_delete,self.add_button,self.assign_button,self.delete_button,
                self.asset_import,self.asset_rescan,*self.align_buttons.values(),self.distribute_h,self.distribute_v,self.snap_button,
                self.state_status_label,self.timeline_status_label,self.speed_label,self.speed_combo,self.play_button,self.step_button,self.reset_button,
                *(binding['editor'] for binding in self.state_editors.values()),
            ]
            for widget in leaves:
                if not widget.isVisible(): continue
                if widget.width()<=0 or widget.height()<=0:issues.append('zero-size:'+widget.__class__.__name__); continue
                scroll=next((area for area in scroll_areas if area.isAncestorOf(widget)),None)
                if scroll is not None:
                    content=scroll.widget(); position=widget.mapTo(content,QPoint(0,0))
                    if position.x()<0 or position.x()+widget.width()>content.width(): issues.append('clipped-horizontal:'+widget.__class__.__name__)
                    continue
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
        def _confirm_open_editor_changes(self):
            for i in range(1,self.editor_tabs.count()):
                widget=self.editor_tabs.widget(i)
                if hasattr(widget,'can_close') and not widget.can_close():return False
                if getattr(widget,'document_id',None)=='settings:preferences' or not editor_is_dirty(widget):
                    continue
                title=self.editor_tabs.tabText(i)
                choice=QMessageBox.question(
                    self,self.tr('dialog.unsaved_title'),self.tr('dialog.unsaved_editor_message',title=title),
                    QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save,
                )
                if choice==QMessageBox.Cancel:return False
                if choice==QMessageBox.Save and hasattr(widget,'save'):
                    try:widget.save()
                    except Exception as exc:self._show_error(str(exc));return False
                    if editor_is_dirty(widget):return False
            return True

        def closeEvent(self,event:QCloseEvent):  # noqa:N802
            if not self._confirm_open_editor_changes():event.ignore(); return
            if self.session.document.dirty:
                box=QMessageBox(self); box.setWindowTitle(self.tr('dialog.unsaved_title')); box.setText(self.tr('dialog.unsaved_message')); box.setStandardButtons(QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel); result=box.exec()
                if result==QMessageBox.Cancel:event.ignore(); return
                if result==QMessageBox.Save:
                    try:self.session.save()
                    except Exception as exc:self._show_error(str(exc)); event.ignore(); return
            self._closing = True
            if self._preferences_view is not None:
                self._preferences_view.flush_pending_save(); self._preferences_view=None
            if self._preferences_window is not None:
                self._preferences_window.close(); self._preferences_window = None
            self.settings.setValue('geometry',self.saveGeometry()); self.settings.setValue('windowState',self.saveState()); self.settings.setValue('workspaceSplitter',self.workspace_splitter.saveState()); self.settings.setValue('verticalSplitter',self.vertical_splitter.saveState()); self.preferences.set('language',self.tr.language,save=False); self.preferences.set('startup.last_project',str(self.project.path) if self.project else '',save=False)
            try:self.preferences.save()
            except OSError as exc:self.logger.log('PREFERENCES_SAVE_FAIL',error=str(exc))
            self.run_timer.stop(); self.autosave_timer.stop(); self.validation_timer.stop()
            if hasattr(self,'agent_bridge'): self.agent_bridge.stop()
            if hasattr(self,'system_theme'): self.system_theme.close()
            try:
                self.logger.write_markdown(self.log_path.with_suffix('.md'))
            except Exception as exc:
                self.diag_logger.warning('SESSION_REPORT_FAIL: %s',exc)
            finally:
                self.logger.close()
            event.accept()


def check_environment(source: str) -> int:
    if not PYSIDE_AVAILABLE:
        print(f'CORE CHECK FAIL: PySide6 is not installed ({PYSIDE_IMPORT_ERROR})',file=sys.stderr); return 2
    try:
        _project,scene=_load_source(source); session=EditorSession(scene); result=session.render(); findings=session.validate(); raw=result.framebuffer.to_vlsb(); expected=int(scene['canvas']['w'])*(int(scene['canvas']['h'])//8)
        if len(raw)!=expected or has_blockers(findings):return 2
        print(f"CORE CHECK PASS: PySide6={PySide6.__version__}, canvas={scene['canvas']['w']}x{scene['canvas']['h']}, framebuffer={len(raw)} bytes, elements={len(scene.get('elements',[]))}"); return 0
    except Exception as exc:print(f'CORE CHECK FAIL: {exc}',file=sys.stderr); return 2


def _settle_window_layout(app,window,max_passes: int = 12) -> bool:
    previous=None; stable_passes=0
    for _ in range(max(2,int(max_passes))):
        window._responsive_tick()
        layout=window.centralWidget().layout() if window.centralWidget() is not None else None
        if layout is not None: layout.activate()
        app.sendPostedEvents(); app.processEvents()
        signature=(
            window.size().toTuple(),tuple(window.workspace_splitter.sizes()),tuple(window.vertical_splitter.sizes()),
            window.inspector_page.viewport().size().toTuple(),window.state_page.viewport().size().toTuple(),window._layout_bucket,
            tuple(widget.geometry().getRect() for widget in (*window.geom_spins.values(),*window.align_buttons.values(),window.distribute_h,window.distribute_v,window.snap_button,*(binding['editor'] for binding in window.state_editors.values()))),
        )
        if signature==previous:
            stable_passes+=1
            if stable_passes>=1:return True
        else:stable_passes=0
        previous=signature
    return False


def run_startup_smoke(source: str) -> int:
    """Construct and show the real main window, process events, then close."""
    if not PYSIDE_AVAILABLE:
        print(f'STARTUP SMOKE FAIL: PySide6 is not installed ({PYSIDE_IMPORT_ERROR})',file=sys.stderr); return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setOrganizationName('MonoOLEDStudio'); app.setStyle('Fusion')
    pref=PreferencesStore.load(); runtime=RuntimeSettings.from_preferences(pref); system_dark=app.palette().window().color().value()<128
    theme=resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=system_dark); _apply_application_theme(app,theme,runtime.density,runtime.ui_scale)
    w=None
    try:
        w=OLEDDesignerWindow(source,runtime.language); w.resize(1180,720); w.setAttribute(Qt.WA_DontShowOnScreen,True); w.show()
        if not _settle_window_layout(app,w): raise RuntimeError('layout did not settle')
        if not w.isVisible(): raise RuntimeError('main window did not become visible')
        if w.layout_violations(): raise RuntimeError('layout violations: '+','.join(w.layout_violations()))
        w.session.document.dirty=False; w.close(); app.processEvents()
        print('STARTUP SMOKE PASS: QApplication + OLEDDesignerWindow constructed, shown, processed, and closed'); return 0
    except Exception as exc:
        if w is not None:
            try: w.session.document.dirty=False; w.close(); app.processEvents()
            except Exception: pass
        print(f'STARTUP SMOKE FAIL: {exc}',file=sys.stderr); return 2



def run_font_smoke(source: str) -> int:
    """Exercise the real Font Lab async generation and existing-pack reopen path."""
    if not PYSIDE_AVAILABLE:
        print(f'FONT SMOKE FAIL: PySide6 is not installed ({PYSIDE_IMPORT_ERROR})',file=sys.stderr); return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setOrganizationName('MonoOLEDStudio'); app.setStyle('Fusion')
    pref=PreferencesStore.load(); runtime=RuntimeSettings.from_preferences(pref); system_dark=app.palette().window().color().value()<128
    theme=resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=system_dark); _apply_application_theme(app,theme,runtime.density,runtime.ui_scale)
    failures=[]
    td=Path(tempfile.mkdtemp(prefix='monooled-font-smoke-'))
    root=td/'font'; editor=None; reopened=None
    try:
        try:
            editor=FontLabEditor(root,name='GA Font',cell=(16,16),language=runtime.language); editor.setAttribute(Qt.WA_DontShowOnScreen,True); editor.show(); app.processEvents()
            editor.chars.setText('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'+''.join(chr(code) for code in range(0x400,0x500)))
            started=perf_counter(); editor.generate(); dispatch=perf_counter()-started
            if dispatch>0.5: failures.append(f'generate-dispatch-blocked:{dispatch:.3f}s')
            deadline=perf_counter()+15.0; event_passes=0
            while editor.generation_in_progress and perf_counter()<deadline:
                app.processEvents(); event_passes+=1; QThread.msleep(5)
            app.processEvents()
            if editor.generation_in_progress: failures.append('generation-timeout')
            if event_passes<1: failures.append('event-loop-not-observed')
            if failures: raise RuntimeError(';'.join(failures))
            pack=editor.pack
            for ch in '0123456789':
                if ch not in pack.characters() or not any(any(row) for row in pack.glyph(ch).pixels): failures.append(f'empty-glyph:{ch}')
            editor.close(); app.processEvents(); editor=None
            manifest=root/'fontpack.json'; before=manifest.stat().st_mtime_ns
            started=perf_counter(); reopened=FontLabEditor(root,language=runtime.language); reopen_elapsed=perf_counter()-started
            if reopen_elapsed>=2.0: failures.append(f'reopen-slow:{reopen_elapsed:.3f}s')
            if manifest.stat().st_mtime_ns!=before: failures.append('reopen-rewrote-manifest')
            reopened.close(); app.processEvents(); reopened=None
        except Exception as exc:
            failures.append(f'exception:{exc}')
    finally:
        for widget in (editor,reopened):
            if widget is not None:
                try: widget.close(); app.processEvents()
                except Exception: pass
        cleanup_deadline=perf_counter()+3.0
        while td.exists():
            try:
                shutil.rmtree(td)
            except OSError as exc:
                if perf_counter()>=cleanup_deadline:
                    failures.append(f'cleanup:{exc}')
                    break
                app.processEvents(); QThread.msleep(50)
    if failures: print('FONT SMOKE FAIL:\n'+'\n'.join(dict.fromkeys(failures)),file=sys.stderr); return 2
    print('FONT SMOKE PASS: async generation + nonblocking event loop + exact glyph output + existing-pack reopen'); return 0


def run_layout_smoke(source: str) -> int:
    if not PYSIDE_AVAILABLE:return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion'); _apply_application_theme(app,'monooled-light','comfortable',1.0); failures=[]
    for width,height,language in [(900,620,'zh_CN'),(900,620,'en_US'),(960,680,'zh_CN'),(960,680,'en_US'),(1100,700,'zh_CN'),(1100,700,'en_US'),(1180,720,'zh_CN'),(1180,720,'en_US'),(1440,900,'zh_CN'),(1440,900,'en_US'),(1920,1080,'zh_CN'),(1920,1080,'en_US'),(2560,1440,'zh_CN'),(2560,1440,'en_US')]:
        w=OLEDDesignerWindow(source,language); w.resize(width,height); w.show(); settled=_settle_window_layout(app,w); issues=w.layout_violations() if settled else ['layout-did-not-settle']; failures.extend([f'{width}x{height}/{language}:{x}' for x in issues]); w.session.document.dirty=False; w.close(); app.processEvents()
    if failures:print('LAYOUT SMOKE FAIL:\n'+'\n'.join(failures),file=sys.stderr); return 2
    print('LAYOUT SMOKE PASS: 14 window/language combinations'); return 0


def _settle_preferences_layout(app, view, max_passes: int = 12) -> bool:
    previous=None; stable_passes=0
    for _ in range(max(2,int(max_passes))):
        view.stabilize_layout()
        current=view.stack.currentWidget()
        if current is not None and current.layout() is not None: current.layout().activate()
        app.sendPostedEvents(); app.processEvents()
        current=view.stack.currentWidget()
        rows=view._rows_by_scroll.get(current,[]) if current is not None else []
        signature=(
            view.size().toTuple(),view.nav.currentRow(),
            current.viewport().size().toTuple() if current is not None else (0,0),
            tuple((row.is_compact,row.geometry().getRect(),row.control.geometry().getRect()) for row in rows),
        )
        if signature==previous:
            stable_passes+=1
            if stable_passes>=1:return True
        else: stable_passes=0
        previous=signature
    return False


def run_settings_smoke(source: str) -> int:
    """Exercise embedded Settings across boundary widths and preference deltas."""
    if not PYSIDE_AVAILABLE:
        print(f'SETTINGS SMOKE FAIL: PySide6 is not installed ({PYSIDE_IMPORT_ERROR})',file=sys.stderr); return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion')
    w=OLEDDesignerWindow(source,'zh_CN'); w.resize(1180,720); w.show(); app.processEvents(); failures=[]
    configs=(
        (900,620,'zh_CN','light','compact','90%'),
        (980,680,'en_US','dark','comfortable','100%'),
        (1180,720,'zh_CN','system','spacious','125%'),
        (1440,900,'en_US','dark','compact','150%'),
    )
    try:
        view=w.open_preferences()
        for width,height,language,theme,density,ui_scale in configs:
            w.resize(width,height)
            w.preferences.set('language',language,save=False); w.preferences.set('appearance.theme_mode',theme,save=False)
            w.preferences.set('appearance.density',density,save=False); w.preferences.set('appearance.ui_scale',ui_scale,save=False)
            w.apply_preferences(); app.processEvents()
            for page_index in range(view.nav.count()):
                view.nav.setCurrentRow(page_index)
                if not _settle_preferences_layout(app,view): failures.append(f'settle:{width}x{height}/{language}/{ui_scale}/p{page_index}'); break
                issues=view.layout_violations()
                if issues: failures.append(f'layout:{width}x{height}/{language}/{ui_scale}/p{page_index}:'+','.join(issues)); break
            if failures: break
    except Exception as exc: failures.append(f'exception:{exc}')
    finally:
        w.session.document.dirty=False; w.close(); app.processEvents()
    if failures: print('SETTINGS SMOKE FAIL:\n'+'\n'.join(failures),file=sys.stderr); return 2
    print('SETTINGS SMOKE PASS: embedded Settings boundary matrix, all pages'); return 0


def run_settings_soak(source: str, cycles: int = 500) -> int:
    """Long Settings state-machine soak: resize/page/language/theme/scale/search."""
    if not PYSIDE_AVAILABLE:return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion')
    w=OLEDDesignerWindow(source,'zh_CN'); w.resize(1180,720); w.show(); app.processEvents(); failures=[]
    widths=((900,620),(960,680),(1100,700),(1180,720),(1440,900))
    scales=('90%','100%','110%','125%','150%'); densities=('compact','comfortable','spacious'); themes=('system','light','dark'); languages=('zh_CN','en_US'); searches=('grid','快捷键','cache','theme','')
    try:
        view=w.open_preferences()
        for i in range(max(1,int(cycles))):
            width,height=widths[i%len(widths)]; w.resize(width,height)
            w.preferences.set('language',languages[(i//7)%len(languages)],save=False)
            w.preferences.set('appearance.ui_scale',scales[(i//11)%len(scales)],save=False)
            w.preferences.set('appearance.density',densities[(i//13)%len(densities)],save=False)
            w.preferences.set('appearance.theme_mode',themes[(i//17)%len(themes)],save=False)
            w.apply_preferences(); view.nav.setCurrentRow(i%view.nav.count())
            if i%19==0:view.search.setText(searches[(i//19)%len(searches)])
            if not _settle_preferences_layout(app,view): failures.append(f'settle@{i}'); break
            issues=view.layout_violations()
            if issues: failures.append(f'layout@{i}:'+','.join(issues)); break
    except Exception as exc: failures.append(f'exception:{exc}')
    finally:
        w.session.document.dirty=False; w.close(); app.processEvents()
    if failures: print('SETTINGS SOAK FAIL:\n'+'\n'.join(failures),file=sys.stderr); return 2
    print(f'SETTINGS SOAK PASS: {cycles} embedded resize/page/language/theme/scale/search cycles'); return 0


def run_interaction_smoke(source: str) -> int:
    if not PYSIDE_AVAILABLE:return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion'); _apply_application_theme(app,'monooled-light','comfortable',1.0); w=OLEDDesignerWindow(source,'zh_CN'); w.resize(1440,900); w.show(); failures=[]
    try:
        if not _settle_window_layout(app,w):failures.append('layout-did-not-settle')
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
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setStyle('Fusion'); _apply_application_theme(app,'monooled-light','comfortable',1.0)
    w=OLEDDesignerWindow(source,'zh_CN'); w.resize(1180,720); w.show(); app.processEvents(); failures=[]
    try:
        target='battery' if any(e.get('id')=='battery' for e in w.scene.get('elements',[])) else str(w.scene['elements'][0]['id'])
        w.select_element(target); base=w.session.geometry(target).x
        sizes=((900,620),(960,680),(1100,700),(1180,720),(1440,900),(1920,1080))
        for i in range(max(1,int(cycles))):
            width,height=sizes[i%len(sizes)]; w.resize(width,height)
            if not _settle_window_layout(app,w):failures.append(f'layout-settle@{i}'); break
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
    p=argparse.ArgumentParser(description=APP_TITLE); p.add_argument('--scene',default='main_scene'); p.add_argument('--project',default=''); p.add_argument('--language',default=DEFAULT_LANGUAGE,choices=SUPPORTED_LANGUAGES); p.add_argument('--check',action='store_true',help='legacy alias for --core-check'); p.add_argument('--core-check',action='store_true',help='runtime dependency and renderer check'); p.add_argument('--startup-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--smoke-ms',type=int,default=0,help=argparse.SUPPRESS); p.add_argument('--layout-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--interaction-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--soak-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--settings-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--font-smoke',action='store_true',help=argparse.SUPPRESS); p.add_argument('--settings-soak',action='store_true',help=argparse.SUPPRESS); p.add_argument('--settings-soak-cycles',type=int,default=500,help=argparse.SUPPRESS); return p


def main(argv=None):
    args=build_parser().parse_args(argv); source=args.project or args.scene
    if args.check or args.core_check:return check_environment(source)
    if args.startup_smoke:return run_startup_smoke(source)
    if args.layout_smoke:return run_layout_smoke(source)
    if args.settings_smoke:return run_settings_smoke(source)
    if args.font_smoke:return run_font_smoke(source)
    if args.settings_soak:return run_settings_soak(source,args.settings_soak_cycles)
    if args.interaction_smoke:return run_interaction_smoke(source)
    if args.soak_smoke:return run_soak_smoke(source)
    if not PYSIDE_AVAILABLE:print('PySide6 is required.',file=sys.stderr); return 2
    app=QApplication.instance() or QApplication(sys.argv[:1]); app.setApplicationName(APP_TITLE); app.setOrganizationName('MonoOLEDStudio'); icon=Path(__file__).resolve().parent/'branding'/'monooled_studio.ico'; app.setWindowIcon(QIcon(str(icon))) if icon.exists() else None; app.setStyle('Fusion'); pref=PreferencesStore.load(); runtime=RuntimeSettings.from_preferences(pref); system_dark=app.palette().window().color().value()<128; theme=resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=system_dark); _apply_application_theme(app,theme,runtime.density,runtime.ui_scale);
    if not args.project and args.scene=='main_scene' and runtime.reopen_last_project and runtime.last_project:
        remembered=_validated_last_project_source(runtime.last_project)
        if remembered:
            source=remembered
        else:
            pref.set('startup.last_project','',save=False)
            try:pref.save()
            except OSError:pass
    w=OLEDDesignerWindow(source,args.language); w.show(); QTimer.singleShot(args.smoke_ms,w.close) if args.smoke_ms>0 else None; return app.exec()


if __name__=='__main__':raise SystemExit(main())
