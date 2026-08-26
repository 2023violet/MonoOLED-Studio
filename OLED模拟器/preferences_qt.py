from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QScrollArea, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget,
)

from commands import CommandRegistry, ShortcutConflictError
from i18n import Translator
from preferences import PreferencesStore, default_preferences
from theme_system import THEME_NAMES
from ui_metrics import build_ui_metrics
from ui_controls import PopupManager, StudioButton, StudioSelect, StudioNumericInput

QPushButton = StudioButton
QComboBox = StudioSelect
QSpinBox = StudioNumericInput


_TEXT = {
    'zh_CN': {
        'title': '偏好设置', 'search': '搜索设置…',
        'section.general': '常规', 'section.appearance': '外观', 'section.input': '输入',
        'section.shortcuts': '快捷键', 'section.canvas': '画布', 'section.pixel': 'Pixel Studio',
        'section.autosave': '自动保存与恢复', 'section.performance': '性能',
        'section.advanced': '高级', 'section.about': '关于',
        'page.general.title': '常规', 'page.general.desc': '全局应用设置。',
        'page.appearance.title': '外观', 'page.appearance.desc': '主题、显示模式、界面密度和缩放。修改后立即生效。',
        'page.input.title': '输入', 'page.input.desc': '画布鼠标与平移行为。',
        'page.shortcuts.title': '快捷键', 'page.shortcuts.desc': '所有可编辑快捷键由同一命令注册表校验并绑定。',
        'page.canvas.title': '画布', 'page.canvas.desc': '仅影响编辑器辅助层，不会写入 OLED framebuffer。',
        'page.pixel.title': 'Pixel Studio', 'page.pixel.desc': '鼠标优先的单色像素编辑：左键绘制，右键擦除。',
        'page.autosave.title': '自动保存与恢复', 'page.autosave.desc': '崩溃恢复快照与普通撤销历史相互独立。',
        'page.performance.title': '性能', 'page.performance.desc': '控制拖拽预览、校验时机、缓存和性能诊断。',
        'page.advanced.title': '高级', 'page.advanced.desc': '维护、缓存与工作区恢复操作。',
        'page.about.title': '关于', 'page.about.desc': '应用版本与构建信息。',
        'label.language': '语言', 'label.startup': '启动', 'check.reopen': '重新打开上次项目',
        'label.theme_mode': '主题模式', 'label.theme': '配色主题', 'label.density': '界面密度', 'label.ui_scale': '界面缩放',
        'label.wheel': '鼠标滚轮', 'label.middle': '中键拖动', 'check.space_pan': 'Space + 左键拖动平移画布',
        'label.snap': '吸附', 'check.grid': '显示像素网格', 'check.bounds': '显示边界', 'check.rulers': '显示标尺', 'check.zones': '显示区域',
        'label.left': '鼠标左键', 'label.right': '鼠标右键', 'value.draw': '绘制 / 置 1', 'value.erase': '擦除 / 置 0',
        'label.brush': '画笔大小', 'check.interpolation': '连续笔划插值', 'check.pixel_grid': '显示像素网格', 'check.actual_preview': '显示 1:1 实际尺寸预览',
        'check.autosave': '启用自动保存', 'label.autosave_interval': '间隔（分钟）', 'label.snapshots': '恢复快照数量', 'check.prompt_recovery': '发现更新恢复数据时提示',
        'label.drag_preview': '拖拽预览', 'label.validation': '校验时机', 'label.undo': '撤销历史', 'label.cache': '资产缓存（MB）', 'check.overlay': '显示性能信息',
        'button.clear_cache': '清除资产缓存', 'button.reset_workspace': '重置工作区布局', 'button.reset_all': '重置全部偏好设置',
        'label.cache_action': '缓存', 'label.workspace_action': '工作区', 'label.danger': '危险操作',
        'label.build': '构建', 'about': 'MonoOLED Studio\nVersion 8.4.4\nWindows Real-Qt GA Final Closure',
        'shortcut.preferences.open': '打开偏好设置', 'shortcut.workspace.canvas_only': '仅画布模式',
        'shortcut.project.save': '保存项目', 'shortcut.designer.undo': '撤销', 'shortcut.designer.redo': '重做',
        'shortcut.pixel.pencil': 'Pixel 铅笔', 'shortcut.pixel.select': 'Pixel 选择', 'shortcut.pixel.fill': 'Pixel 填充',
        'shortcut.conflict': '快捷键冲突：{error}',
        'mode.system': '跟随系统', 'mode.light': '浅色', 'mode.dark': '深色',
        'density.compact': '紧凑', 'density.comfortable': '舒适', 'density.spacious': '宽松',
        'wheel.zoom': '缩放', 'wheel.none': '无操作', 'pan.pan': '平移', 'pan.none': '无操作',
        'snap.off': '关闭', 'perf.fast': '快速', 'perf.exact': '精确',
        'validation.edit_complete': '编辑完成时', 'validation.idle': '空闲时', 'validation.continuous': '持续校验',
    },
    'en_US': {
        'title': 'Preferences', 'search': 'Search settings…',
        'section.general': 'General', 'section.appearance': 'Appearance', 'section.input': 'Input',
        'section.shortcuts': 'Shortcuts', 'section.canvas': 'Canvas', 'section.pixel': 'Pixel Studio',
        'section.autosave': 'Autosave & Recovery', 'section.performance': 'Performance',
        'section.advanced': 'Advanced', 'section.about': 'About',
        'page.general.title': 'General', 'page.general.desc': 'Global application preferences.',
        'page.appearance.title': 'Appearance', 'page.appearance.desc': 'Theme mode, color theme, interface density and scale. Changes apply immediately.',
        'page.input.title': 'Input', 'page.input.desc': 'Canvas mouse and pan behavior.',
        'page.shortcuts.title': 'Shortcuts', 'page.shortcuts.desc': 'All editable shortcuts are validated and bound through one command registry.',
        'page.canvas.title': 'Canvas', 'page.canvas.desc': 'Editor overlays only; they never enter the OLED framebuffer.',
        'page.pixel.title': 'Pixel Studio', 'page.pixel.desc': 'Mouse-first monochrome authoring: left draws, right erases.',
        'page.autosave.title': 'Autosave & Recovery', 'page.autosave.desc': 'Crash-recovery snapshots are separate from ordinary undo history.',
        'page.performance.title': 'Performance', 'page.performance.desc': 'Control drag preview, validation timing, cache and performance diagnostics.',
        'page.advanced.title': 'Advanced', 'page.advanced.desc': 'Maintenance, cache and workspace recovery actions.',
        'page.about.title': 'About', 'page.about.desc': 'Application version and build information.',
        'label.language': 'Language', 'label.startup': 'Startup', 'check.reopen': 'Reopen last project',
        'label.theme_mode': 'Theme mode', 'label.theme': 'Color theme', 'label.density': 'Density', 'label.ui_scale': 'UI scale',
        'label.wheel': 'Mouse wheel', 'label.middle': 'Middle drag', 'check.space_pan': 'Space + left drag pans canvas',
        'label.snap': 'Snap', 'check.grid': 'Show pixel grid', 'check.bounds': 'Show bounds', 'check.rulers': 'Show rulers', 'check.zones': 'Show zones',
        'label.left': 'Left mouse', 'label.right': 'Right mouse', 'value.draw': 'Draw / Set 1', 'value.erase': 'Erase / Set 0',
        'label.brush': 'Brush size', 'check.interpolation': 'Stroke interpolation', 'check.pixel_grid': 'Show pixel grid', 'check.actual_preview': 'Actual-size preview',
        'check.autosave': 'Enable autosave', 'label.autosave_interval': 'Interval (minutes)', 'label.snapshots': 'Recovery snapshots', 'check.prompt_recovery': 'Prompt when newer recovery data is found',
        'label.drag_preview': 'Drag preview', 'label.validation': 'Validation', 'label.undo': 'Undo history', 'label.cache': 'Asset cache (MB)', 'check.overlay': 'Performance overlay',
        'button.clear_cache': 'Clear asset cache', 'button.reset_workspace': 'Reset workspace layout', 'button.reset_all': 'Reset all preferences',
        'label.cache_action': 'Cache', 'label.workspace_action': 'Workspace', 'label.danger': 'Danger zone',
        'label.build': 'Build', 'about': 'MonoOLED Studio\nVersion 8.4.4\nWindows Real-Qt GA Final Closure',
        'shortcut.preferences.open': 'Open Preferences', 'shortcut.workspace.canvas_only': 'Canvas Only',
        'shortcut.project.save': 'Save project', 'shortcut.designer.undo': 'Undo', 'shortcut.designer.redo': 'Redo',
        'shortcut.pixel.pencil': 'Pixel Pencil', 'shortcut.pixel.select': 'Pixel Select', 'shortcut.pixel.fill': 'Pixel Fill',
        'shortcut.conflict': 'Shortcut conflict: {error}',
        'mode.system': 'System', 'mode.light': 'Light', 'mode.dark': 'Dark',
        'density.compact': 'Compact', 'density.comfortable': 'Comfortable', 'density.spacious': 'Spacious',
        'wheel.zoom': 'Zoom', 'wheel.none': 'None', 'pan.pan': 'Pan', 'pan.none': 'None',
        'snap.off': 'Off', 'perf.fast': 'Fast', 'perf.exact': 'Exact',
        'validation.edit_complete': 'On edit complete', 'validation.idle': 'During idle', 'validation.continuous': 'Continuous',
    },
}


class PreferencesWindow(QMainWindow):
    preferencesChanged = Signal()
    clearAssetCacheRequested = Signal()
    resetWorkspaceRequested = Signal()

    SECTIONS = ('general','appearance','input','shortcuts','canvas','pixel','autosave','performance','advanced','about')

    def __init__(self, store: PreferencesStore, translator: Translator, parent=None):
        super().__init__(parent)
        self.store = store
        self.tr = translator
        self._text_bindings: list[tuple[QWidget, str, str]] = []
        self._page_headers: dict[str, tuple[QLabel, QLabel]] = {}
        self.shortcut_edits: dict[str, QLineEdit] = {}
        self._loading = False
        self._save_timer=QTimer(self); self._save_timer.setSingleShot(True); self._save_timer.setInterval(150); self._save_timer.timeout.connect(self.store.save)
        self.resize(920, 660)
        self.setMinimumSize(720, 520)
        self._build()
        self._load_values()
        self._retranslate()

    def _t(self, key: str, **values) -> str:
        lang = self.tr.language if self.tr.language in _TEXT else 'en_US'
        value = _TEXT[lang].get(key, _TEXT['en_US'].get(key, key))
        return value.format(**values) if values else value

    def _bind_text(self, widget: QWidget, key: str, attr: str = 'setText') -> QWidget:
        self._text_bindings.append((widget, key, attr))
        return widget

    def _label(self, key: str) -> QLabel:
        return self._bind_text(QLabel(), key)  # type: ignore[return-value]

    def _check(self, key: str) -> QCheckBox:
        return self._bind_text(QCheckBox(), key)  # type: ignore[return-value]

    def _button(self, key: str) -> QPushButton:
        return self._bind_text(QPushButton(), key)  # type: ignore[return-value]

    def _section_label(self, section: str) -> str:
        return self._t(f'section.{section}')

    def _build(self):
        root = QWidget(); root.setObjectName('PreferencesRoot'); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(18, 16, 18, 16); outer.setSpacing(10)
        self.preferences_title = self._bind_text(QLabel(), 'title'); self.preferences_title.setObjectName('HeroTitle'); outer.addWidget(self.preferences_title)
        self.search = QLineEdit(); outer.addWidget(self.search)
        body = QHBoxLayout(); body.setSpacing(14); outer.addLayout(body, 1)
        self.nav = QListWidget(); self.nav.setObjectName('PreferencesNavigation'); self.nav.setMinimumWidth(168); self.nav.setMaximumWidth(280); self.nav.setMinimumSize(168,1)
        for _ in self.SECTIONS: self.nav.addItem('')
        body.addWidget(self.nav)
        self.stack = QStackedWidget(); self.stack.setObjectName('PreferencesStack'); body.addWidget(self.stack, 1)

        self.language = QComboBox(); self.language.addItem('简体中文', 'zh_CN'); self.language.addItem('English', 'en_US')
        self.start_last = self._check('check.reopen')
        self.stack.addWidget(self._page('general', [('label.language', self.language), ('label.startup', self.start_last)]))

        self.theme_mode = QComboBox();
        for data in ('system','light','dark'): self.theme_mode.addItem('', data)
        self.theme = QComboBox();
        for name in THEME_NAMES: self.theme.addItem(name.replace('-', ' ').title(), name)
        self.density = QComboBox();
        for data in ('compact','comfortable','spacious'): self.density.addItem('', data)
        self.ui_scale = QComboBox();
        for text, data in (('Auto','auto'),('90%','90%'),('100%','100%'),('110%','110%'),('125%','125%'),('150%','150%')): self.ui_scale.addItem(text, data)
        self.stack.addWidget(self._page('appearance', [('label.theme_mode', self.theme_mode), ('label.theme', self.theme), ('label.density', self.density), ('label.ui_scale', self.ui_scale)]))

        self.wheel = QComboBox(); self.wheel.addItem('', 'zoom'); self.wheel.addItem('', 'none')
        self.middle = QComboBox(); self.middle.addItem('', 'pan'); self.middle.addItem('', 'none')
        self.space_pan = self._check('check.space_pan')
        self.stack.addWidget(self._page('input', [('label.wheel', self.wheel), ('label.middle', self.middle), ('', self.space_pan)]))

        shortcut_rows=[]
        for command_id in default_preferences()['shortcuts']:
            edit=QLineEdit(); edit.setClearButtonEnabled(True); self.shortcut_edits[command_id]=edit
            shortcut_rows.append((f'shortcut.{command_id}', edit))
        self.shortcut_error=QLabel(); self.shortcut_error.setObjectName('ErrorText'); self.shortcut_error.setWordWrap(True); self.shortcut_error.hide()
        shortcut_rows.append(('', self.shortcut_error))
        self.stack.addWidget(self._page('shortcuts', shortcut_rows))

        self.grid=self._check('check.grid'); self.bounds=self._check('check.bounds'); self.rulers=self._check('check.rulers'); self.zones=self._check('check.zones')
        self.snap=QComboBox()
        for label,data in (('Off',0),('1 px',1),('2 px',2),('4 px',4),('8 px',8)): self.snap.addItem(label,data)
        self.stack.addWidget(self._page('canvas', [('',self.grid),('',self.bounds),('',self.rulers),('',self.zones),('label.snap',self.snap)]))

        self.left_action=self._label('value.draw'); self.right_action=self._label('value.erase')
        self.brush_size=QSpinBox(); self.brush_size.setRange(1,8)
        self.interpolation=self._check('check.interpolation'); self.pixel_grid=self._check('check.pixel_grid'); self.actual_preview=self._check('check.actual_preview')
        self.stack.addWidget(self._page('pixel', [('label.left',self.left_action),('label.right',self.right_action),('label.brush',self.brush_size),('',self.interpolation),('',self.pixel_grid),('',self.actual_preview)]))

        self.autosave=self._check('check.autosave'); self.autosave_minutes=QSpinBox(); self.autosave_minutes.setRange(1,60); self.snapshots=QSpinBox(); self.snapshots.setRange(1,100); self.prompt_recovery=self._check('check.prompt_recovery')
        self.stack.addWidget(self._page('autosave', [('',self.autosave),('label.autosave_interval',self.autosave_minutes),('label.snapshots',self.snapshots),('',self.prompt_recovery)]))

        self.drag_preview=QComboBox(); self.drag_preview.addItem('', 'fast'); self.drag_preview.addItem('', 'exact')
        self.validation=QComboBox(); self.validation.addItem('', 'edit_complete'); self.validation.addItem('', 'idle'); self.validation.addItem('', 'continuous')
        self.undo_history=QSpinBox(); self.undo_history.setRange(10,2000); self.asset_cache=QSpinBox(); self.asset_cache.setRange(32,4096); self.perf_overlay=self._check('check.overlay')
        self.stack.addWidget(self._page('performance', [('label.drag_preview',self.drag_preview),('label.validation',self.validation),('label.undo',self.undo_history),('label.cache',self.asset_cache),('',self.perf_overlay)]))

        self.clear_cache=self._button('button.clear_cache'); self.reset_layout=self._button('button.reset_workspace'); self.reset_all=self._button('button.reset_all'); self.reset_all.setObjectName('DangerButton')
        self.clear_cache.clicked.connect(self.clearAssetCacheRequested.emit); self.reset_layout.clicked.connect(self.resetWorkspaceRequested.emit); self.reset_all.clicked.connect(self._reset_all)
        self.stack.addWidget(self._page('advanced', [('label.cache_action',self.clear_cache),('label.workspace_action',self.reset_layout),('label.danger',self.reset_all)]))

        self.about=self._label('about'); self.about.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.stack.addWidget(self._page('about', [('label.build',self.about)]))

        self.nav.currentRowChanged.connect(self._nav_changed); self.nav.setCurrentRow(0)
        self.search.textChanged.connect(self._search_changed)
        for widget in (self.language,self.theme_mode,self.theme,self.density,self.ui_scale,self.wheel,self.middle,self.snap,self.drag_preview,self.validation): widget.currentIndexChanged.connect(self._controls_changed)
        for widget in (self.start_last,self.space_pan,self.grid,self.bounds,self.rulers,self.zones,self.interpolation,self.pixel_grid,self.actual_preview,self.autosave,self.prompt_recovery,self.perf_overlay): widget.toggled.connect(self._controls_changed)
        for widget in (self.brush_size,self.autosave_minutes,self.snapshots,self.undo_history,self.asset_cache): widget.valueChanged.connect(self._controls_changed)
        for edit in self.shortcut_edits.values(): edit.editingFinished.connect(self._shortcuts_changed)

    def _page(self, section: str, rows):
        scroll=QScrollArea(); scroll.setObjectName('PreferencesScroll'); scroll.setWidgetResizable(True)
        scroll.viewport().setObjectName('PreferencesViewport')
        page=QWidget(); page.setObjectName('PreferencesPage'); layout=QVBoxLayout(page); layout.setContentsMargins(6,4,16,18); layout.setSpacing(0)
        h=QLabel(); h.setObjectName('CardTitle'); layout.addWidget(h)
        d=QLabel(); d.setObjectName('Muted'); d.setWordWrap(True); layout.addWidget(d); layout.addSpacing(18)
        self._page_headers[section]=(h,d)
        form=QFormLayout(); form.setHorizontalSpacing(36); form.setVerticalSpacing(16); form.setLabelAlignment(Qt.AlignLeft|Qt.AlignVCenter)
        for key,widget in rows:
            if key:
                label=QLabel(); self._text_bindings.append((label,key,'setText')); form.addRow(label,widget)
            else: form.addRow('',widget)
        layout.addLayout(form); layout.addStretch(1); scroll.setWidget(page); return scroll

    def _nav_changed(self, row: int):
        PopupManager.close_all()
        self.stack.setCurrentIndex(max(0, int(row)))

    def _retranslate(self):
        self.setWindowTitle(self._t('title')); self.search.setPlaceholderText(self._t('search'))
        for widget,key,attr in self._text_bindings: getattr(widget,attr)(self._t(key))
        for section,(heading,desc) in self._page_headers.items():
            heading.setText(self._t(f'page.{section}.title')); desc.setText(self._t(f'page.{section}.desc'))
        current=self.nav.currentRow()
        for i,section in enumerate(self.SECTIONS): self.nav.item(i).setText(self._section_label(section))
        self.nav.setCurrentRow(max(0,current))
        for idx,data in enumerate(('system','light','dark')): self.theme_mode.setItemText(idx,self._t(f'mode.{data}'))
        for idx,data in enumerate(('compact','comfortable','spacious')): self.density.setItemText(idx,self._t(f'density.{data}'))
        self.wheel.setItemText(0,self._t('wheel.zoom')); self.wheel.setItemText(1,self._t('wheel.none'))
        self.middle.setItemText(0,self._t('pan.pan')); self.middle.setItemText(1,self._t('pan.none'))
        self.snap.setItemText(0,self._t('snap.off'))
        self.drag_preview.setItemText(0,self._t('perf.fast')); self.drag_preview.setItemText(1,self._t('perf.exact'))
        self.validation.setItemText(0,self._t('validation.edit_complete')); self.validation.setItemText(1,self._t('validation.idle')); self.validation.setItemText(2,self._t('validation.continuous'))

    def _search_changed(self, text: str):
        q=text.strip().casefold()
        if not q: return
        keywords={'general':'language startup 语言 启动','appearance':'theme color dark light density scale 主题 外观 密度','input':'mouse wheel pan space 鼠标 平移','shortcuts':'keyboard command hotkey 快捷键','canvas':'grid bounds rulers zones snap 网格 标尺 吸附','pixel':'draw erase brush pixel stroke preview 绘制 擦除 画笔 像素','autosave':'autosave recovery snapshot crash 自动保存 恢复','performance':'performance validation undo cache overlay 性能 校验 缓存','advanced':'reset cache workspace 高级 重置','about':'version build 版本 关于'}
        for i,name in enumerate(self.SECTIONS):
            if q in (self._section_label(name)+' '+keywords.get(name,'')).casefold(): self.nav.setCurrentRow(i); break

    @staticmethod
    def _set_combo(combo: QComboBox, data):
        idx=combo.findData(data)
        if idx>=0: combo.setCurrentIndex(idx)

    def _load_values(self):
        self._loading=True
        self._set_combo(self.language,self.store.get('language','zh_CN')); self.start_last.setChecked(bool(self.store.get('startup.reopen_last_project',False)))
        self._set_combo(self.theme_mode,self.store.get('appearance.theme_mode','system')); self._set_combo(self.theme,self.store.get('appearance.color_theme','monooled-light')); self._set_combo(self.density,self.store.get('appearance.density','comfortable')); self._set_combo(self.ui_scale,self.store.get('appearance.ui_scale','auto'))
        self._set_combo(self.wheel,self.store.get('input.wheel_action','zoom')); self._set_combo(self.middle,self.store.get('input.middle_drag','pan')); self.space_pan.setChecked(self.store.get('input.space_drag','pan')=='pan')
        self.grid.setChecked(bool(self.store.get('canvas.grid',True))); self.bounds.setChecked(bool(self.store.get('canvas.bounds',True))); self.rulers.setChecked(bool(self.store.get('canvas.rulers',True))); self.zones.setChecked(bool(self.store.get('canvas.zones',False))); self._set_combo(self.snap,int(self.store.get('canvas.snap',0)))
        self.brush_size.setValue(int(self.store.get('pixel_studio.brush_size',1))); self.interpolation.setChecked(bool(self.store.get('pixel_studio.stroke_interpolation',True))); self.pixel_grid.setChecked(bool(self.store.get('pixel_studio.pixel_grid',True))); self.actual_preview.setChecked(bool(self.store.get('pixel_studio.actual_preview',True)))
        self.autosave.setChecked(bool(self.store.get('autosave.enabled',True))); self.autosave_minutes.setValue(int(self.store.get('autosave.interval_minutes',3))); self.snapshots.setValue(int(self.store.get('autosave.snapshots',10))); self.prompt_recovery.setChecked(bool(self.store.get('autosave.prompt_recovery',True)))
        self._set_combo(self.drag_preview,self.store.get('performance.drag_preview','fast')); self._set_combo(self.validation,self.store.get('performance.validation_mode','edit_complete')); self.undo_history.setValue(int(self.store.get('performance.undo_history',200))); self.asset_cache.setValue(int(self.store.get('performance.asset_cache_mb',512))); self.perf_overlay.setChecked(bool(self.store.get('performance.overlay',False)))
        for command_id,edit in self.shortcut_edits.items(): edit.setText(str(self.store.get(f'shortcuts.{command_id}',default_preferences()['shortcuts'][command_id])))
        self.shortcut_error.hide(); self._loading=False

    def _schedule_save(self):
        self._save_timer.start()

    def flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop(); self.store.save()

    def closeEvent(self,event):  # noqa: N802
        self.flush_pending_save(); super().closeEvent(event)

    def _controls_changed(self, *_):
        if self._loading: return
        new_language=self.language.currentData()
        self.store.set('language',new_language,save=False); self.store.set('startup.reopen_last_project',self.start_last.isChecked(),save=False)
        self.store.set('appearance.theme_mode',self.theme_mode.currentData(),save=False); self.store.set('appearance.color_theme',self.theme.currentData(),save=False); self.store.set('appearance.density',self.density.currentData(),save=False); self.store.set('appearance.ui_scale',self.ui_scale.currentData(),save=False)
        self.store.set('input.wheel_action',self.wheel.currentData(),save=False); self.store.set('input.middle_drag',self.middle.currentData(),save=False); self.store.set('input.space_drag','pan' if self.space_pan.isChecked() else 'none',save=False)
        self.store.set('canvas.grid',self.grid.isChecked(),save=False); self.store.set('canvas.bounds',self.bounds.isChecked(),save=False); self.store.set('canvas.rulers',self.rulers.isChecked(),save=False); self.store.set('canvas.zones',self.zones.isChecked(),save=False); self.store.set('canvas.snap',self.snap.currentData(),save=False)
        self.store.set('pixel_studio.brush_size',self.brush_size.value(),save=False); self.store.set('pixel_studio.stroke_interpolation',self.interpolation.isChecked(),save=False); self.store.set('pixel_studio.pixel_grid',self.pixel_grid.isChecked(),save=False); self.store.set('pixel_studio.actual_preview',self.actual_preview.isChecked(),save=False)
        self.store.set('autosave.enabled',self.autosave.isChecked(),save=False); self.store.set('autosave.interval_minutes',self.autosave_minutes.value(),save=False); self.store.set('autosave.snapshots',self.snapshots.value(),save=False); self.store.set('autosave.prompt_recovery',self.prompt_recovery.isChecked(),save=False)
        self.store.set('performance.drag_preview',self.drag_preview.currentData(),save=False); self.store.set('performance.validation_mode',self.validation.currentData(),save=False); self.store.set('performance.undo_history',self.undo_history.value(),save=False); self.store.set('performance.asset_cache_mb',self.asset_cache.value(),save=False); self.store.set('performance.overlay',self.perf_overlay.isChecked(),save=False)
        self._schedule_save()
        if new_language!=self.tr.language: self.tr.set_language(new_language); self._retranslate()
        self.preferencesChanged.emit()

    def _shortcuts_changed(self):
        if self._loading: return
        mapping={command_id:edit.text().strip() for command_id,edit in self.shortcut_edits.items()}
        registry=CommandRegistry()
        for command_id,default in default_preferences()['shortcuts'].items(): registry.register(command_id,shortcut=default)
        try: registry.apply_bindings(mapping,ignore_unknown=False)
        except ShortcutConflictError as exc:
            self.shortcut_error.setText(self._t('shortcut.conflict',error=str(exc))); self.shortcut_error.show(); return
        self.shortcut_error.hide()
        for command_id,value in mapping.items(): self.store.set(f'shortcuts.{command_id}',value,save=False)
        self._schedule_save(); self.preferencesChanged.emit()

    def set_language(self, language: str):
        if language not in _TEXT: language='en_US'
        if language==self.tr.language:return False
        self.tr.set_language(language); self._retranslate(); return True

    def apply_runtime_settings(self,runtime):
        m=build_ui_metrics(runtime.density,runtime.ui_scale)
        self.nav.setMinimumWidth(m['nav_min']); self.nav.setMaximumWidth(max(m['nav_min']+80,280))

    def _reset_all(self):
        self.store.data=default_preferences(); self.store.save(); self.tr.set_language(self.store.get('language','zh_CN')); self._load_values(); self._retranslate(); self.preferencesChanged.emit()

    def layout_violations(self) -> list[str]:
        violations=[]
        if self.centralWidget() is None or self.centralWidget().width()<=0: violations.append('central_widget')
        if self.nav.width()<150: violations.append('navigation_width')
        if self.stack.width()<=0: violations.append('stack_width')
        current=self.stack.currentWidget()
        if current is None or current.width()<=0 or current.height()<=0: violations.append('current_page')
        if self.search.height()<=0: violations.append('search')
        return violations
