from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, QEasingCurve, QPropertyAnimation, Qt, Signal, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout, QCheckBox, QComboBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QMainWindow, QMessageBox, QScrollArea, QSpinBox, QStackedWidget, QSizePolicy, QLayout,
    QVBoxLayout, QWidget,
)

from commands import CommandRegistry, ShortcutConflictError
from i18n import Translator
from preferences import PreferencesStore, default_preferences
from ui_metrics import build_ui_metrics
from ui_controls import PopupManager, StudioButton, StudioSelect, StudioNumericInput
from version_info import load_version

APP_VERSION = load_version()

QPushButton = StudioButton
QComboBox = StudioSelect
QSpinBox = StudioNumericInput


_TEXT = {
    'zh_CN': {
        'eyebrow': 'MONOOLED STUDIO · 工作区偏好',
        'title': '设置', 'search': '搜索设置、功能或关键词…', 'search.no_results': '未找到匹配设置',
        'status.saving': '正在保存…', 'status.saved': '已保存', 'status.failed': '保存失败',
        'confirm.reset_all.title': '重置全部设置', 'confirm.reset_all.body': '这会恢复所有偏好设置为默认值，且需要重新配置个人选项。是否继续？',
        'section.general': '常规', 'section.appearance': '外观', 'section.canvas': '画布与输入', 'section.keyboard': '键盘',
        'section.pixel': 'Pixel Studio', 'section.recovery': '恢复', 'section.advanced': '高级',
        'page.general.title': '常规', 'page.general.desc': '控制语言、启动行为等全局偏好。建议先从这里完成基础配置。',
        'page.appearance.title': '外观', 'page.appearance.desc': '控制主题、信息密度、界面缩放和动效偏好；修改后立即生效。',
        'page.canvas.title': '画布与输入', 'page.canvas.desc': '鼠标操作、平移、画布辅助层与吸附集中管理，保持编辑手感稳定。',
        'page.keyboard.title': '键盘', 'page.keyboard.desc': '集中管理所有可编辑快捷键；冲突会立即提示，不会静默覆盖。',
        'page.pixel.title': 'Pixel Studio', 'page.pixel.desc': '控制单色像素编辑器的画笔与预览行为；左键绘制、右键擦除为固定产品语义。',
        'page.recovery.title': '恢复', 'page.recovery.desc': '自动保存、恢复快照、撤销历史与校验时机集中管理，降低意外退出风险。',
        'page.advanced.title': '高级', 'page.advanced.desc': '性能策略、缓存与维护工具集中在这里；多数用户保持默认即可。',
        'group.general': '应用基础', 'group.appearance': '视觉与动效', 'group.color': '外观模式', 'group.geometry': '界面尺寸与密度',
        'group.input': '画布操作', 'group.canvas': '画布辅助层', 'group.shortcuts': '键盘快捷键',
        'group.pixel_behavior': '绘制行为', 'group.pixel_view': '像素预览',
        'group.autosave': '自动保存', 'group.recovery': '恢复与历史',
        'group.performance': '性能策略', 'group.maintenance': '维护工具', 'group.danger': '危险操作', 'group.about': '构建信息',
        'label.language': '语言', 'label.startup': '启动', 'check.reopen': '重新打开上次项目',
        'label.theme_mode': '外观模式', 'label.density': '界面密度', 'label.ui_scale': '界面缩放', 'check.reduced_motion': '减少界面动效',
        'label.wheel': '鼠标滚轮', 'label.middle': '中键拖动', 'check.space_pan': 'Space + 左键拖动平移画布',
        'label.snap': '吸附', 'check.grid': '显示像素网格', 'check.bounds': '显示边界', 'check.rulers': '显示标尺', 'check.zones': '显示区域',
        'label.left': '鼠标左键', 'label.right': '鼠标右键', 'value.draw': '绘制 / 置 1', 'value.erase': '擦除 / 置 0',
        'label.brush': '画笔大小', 'check.interpolation': '连续笔划插值', 'check.pixel_grid': '显示像素网格', 'check.actual_preview': '显示 1:1 实际尺寸预览',
        'check.autosave': '启用自动保存', 'label.autosave_interval': '间隔（分钟）', 'label.snapshots': '恢复快照数量', 'check.prompt_recovery': '发现更新恢复数据时提示',
        'label.drag_preview': '拖拽预览', 'label.validation': '校验时机', 'label.undo': '撤销历史', 'label.cache': '资产缓存（MB）', 'check.overlay': '显示性能信息',
        'button.clear_cache': '清除资产缓存', 'button.reset_workspace': '重置工作区布局', 'button.reset_all': '重置全部偏好设置',
        'label.cache_action': '缓存', 'label.workspace_action': '工作区', 'label.danger': '重置全部设置',
        'label.build': '构建', 'about': f'MonoOLED Studio\nVersion {APP_VERSION}\nInitial Release',
        'shortcut.preferences.open': '打开设置', 'shortcut.workspace.canvas_only': '仅画布模式',
        'shortcut.project.save': '保存项目', 'shortcut.designer.undo': '撤销', 'shortcut.designer.redo': '重做',
        'shortcut.pixel.pencil': 'Pixel 铅笔', 'shortcut.pixel.select': 'Pixel 选择', 'shortcut.pixel.fill': 'Pixel 填充',
        'shortcut.conflict': '快捷键冲突：{error}',
        'mode.system': '跟随系统', 'mode.light': '浅色', 'mode.dark': '深色',
        'density.compact': '紧凑', 'density.comfortable': '舒适', 'density.spacious': '宽松',
        'wheel.zoom': '缩放', 'wheel.none': '无操作', 'pan.pan': '平移', 'pan.none': '无操作',
        'snap.off': '关闭', 'perf.fast': '快速', 'perf.exact': '精确',
        'validation.edit_complete': '编辑完成时', 'validation.idle': '空闲时', 'validation.continuous': '持续校验',
        'help.language': '切换整个工作台、Pixel Studio 与 Font Lab 的界面语言。',
        'help.startup': '启用后，下次启动会尝试恢复最近一次打开的项目。',
        'help.theme_mode': '“跟随系统”会根据 Windows 外观自动选择浅色或深色主题。',
        'help.density': '改变控件高度与间距，不影响 OLED 画布像素。',
        'help.ui_scale': '只缩放应用界面，不改变项目画布、导出尺寸或像素数据。',
        'help.reduced_motion': '关闭设置页切换等非必要过渡动画，适合低性能环境或动效敏感用户。',
        'help.input': '只改变编辑器交互方式，不会写入项目或 framebuffer。',
        'help.canvas_grid': '网格、边界、标尺和区域均为编辑辅助层，永远不会进入 OLED 导出。',
        'help.snap': '吸附以真实 OLED 像素为单位；关闭时允许自由定位。',
        'help.shortcuts': '快捷键由统一命令注册表校验。冲突会在本页立即提示，不会静默覆盖。',
        'help.pixel_behavior': '左右键语义固定；这里仅调整画笔尺寸与连续笔划。',
        'help.pixel_view': '这些选项只影响 Pixel Studio 的编辑预览。',
        'help.autosave': '自动保存用于减少意外退出造成的数据损失，与普通撤销历史相互独立。',
        'help.snapshots': '保留更多恢复快照会占用少量磁盘空间，但提高恢复范围。',
        'help.validation': '“编辑完成时”是推荐默认值；持续校验反馈更快，但大型项目开销更高。',
        'help.undo': '决定编辑器与 Pixel Studio 可保留的撤销步骤上限。',
        'help.asset_cache': '增大缓存可减少重复资产解析；内存紧张时可适当降低。',
        'help.overlay': '用于诊断性能问题，普通使用建议关闭。',
        'help.maintenance': '清缓存不会删除项目资产；重置布局只恢复工作区面板位置。',
        'help.reset_all': '恢复所有偏好设置为默认值。此操作会立即保存，并需要重新配置个性化选项。',
    },
    'en_US': {
        'eyebrow': 'MONOOLED STUDIO · WORKSPACE PREFERENCES',
        'title': 'Settings', 'search': 'Search settings, features, or keywords…', 'search.no_results': 'No matching setting',
        'status.saving': 'Saving…', 'status.saved': 'Saved', 'status.failed': 'Save failed',
        'confirm.reset_all.title': 'Reset all settings', 'confirm.reset_all.body': 'This restores every preference to its default and requires personal options to be configured again. Continue?',
        'section.general': 'General', 'section.appearance': 'Appearance', 'section.canvas': 'Canvas & Input', 'section.keyboard': 'Keyboard',
        'section.pixel': 'Pixel Studio', 'section.recovery': 'Recovery', 'section.advanced': 'Advanced',
        'page.general.title': 'General', 'page.general.desc': 'Global language and startup preferences. Start here for the essential application setup.',
        'page.appearance.title': 'Appearance', 'page.appearance.desc': 'Theme, information density, UI scale, and motion preferences. Changes apply immediately.',
        'page.canvas.title': 'Canvas & Input', 'page.canvas.desc': 'Mouse behavior, panning, canvas guides, and snapping in one predictable editing model.',
        'page.keyboard.title': 'Keyboard', 'page.keyboard.desc': 'Manage every editable shortcut in one place. Conflicts are reported immediately and never overwrite silently.',
        'page.pixel.title': 'Pixel Studio', 'page.pixel.desc': 'Monochrome authoring behavior and preview options. Left draws and right erases by fixed product semantics.',
        'page.recovery.title': 'Recovery', 'page.recovery.desc': 'Autosave, recovery snapshots, undo history, and validation timing are managed together to reduce data-loss risk.',
        'page.advanced.title': 'Advanced', 'page.advanced.desc': 'Performance strategy, caches, and maintenance tools. Defaults are recommended for most users.',
        'group.general': 'Application basics', 'group.appearance': 'Visuals & motion', 'group.color': 'Appearance mode', 'group.geometry': 'Interface size & density',
        'group.input': 'Canvas interaction', 'group.canvas': 'Canvas guides', 'group.shortcuts': 'Keyboard shortcuts',
        'group.pixel_behavior': 'Drawing behavior', 'group.pixel_view': 'Pixel preview',
        'group.autosave': 'Autosave', 'group.recovery': 'Recovery & history',
        'group.performance': 'Performance strategy', 'group.maintenance': 'Maintenance tools', 'group.danger': 'Danger zone', 'group.about': 'Build information',
        'label.language': 'Language', 'label.startup': 'Startup', 'check.reopen': 'Reopen last project',
        'label.theme_mode': 'Appearance mode', 'label.density': 'Interface density', 'label.ui_scale': 'UI scale', 'check.reduced_motion': 'Reduce interface motion',
        'label.wheel': 'Mouse wheel', 'label.middle': 'Middle drag', 'check.space_pan': 'Space + left drag pans canvas',
        'label.snap': 'Snap', 'check.grid': 'Show pixel grid', 'check.bounds': 'Show bounds', 'check.rulers': 'Show rulers', 'check.zones': 'Show zones',
        'label.left': 'Left mouse', 'label.right': 'Right mouse', 'value.draw': 'Draw / Set 1', 'value.erase': 'Erase / Set 0',
        'label.brush': 'Brush size', 'check.interpolation': 'Stroke interpolation', 'check.pixel_grid': 'Show pixel grid', 'check.actual_preview': 'Actual-size preview',
        'check.autosave': 'Enable autosave', 'label.autosave_interval': 'Interval (minutes)', 'label.snapshots': 'Recovery snapshots', 'check.prompt_recovery': 'Prompt when newer recovery data is found',
        'label.drag_preview': 'Drag preview', 'label.validation': 'Validation', 'label.undo': 'Undo history', 'label.cache': 'Asset cache (MB)', 'check.overlay': 'Performance overlay',
        'button.clear_cache': 'Clear asset cache', 'button.reset_workspace': 'Reset workspace layout', 'button.reset_all': 'Reset all preferences',
        'label.cache_action': 'Cache', 'label.workspace_action': 'Workspace', 'label.danger': 'Reset all settings',
        'label.build': 'Build', 'about': f'MonoOLED Studio\nVersion {APP_VERSION}\nInitial Release',
        'shortcut.preferences.open': 'Open Settings', 'shortcut.workspace.canvas_only': 'Canvas Only',
        'shortcut.project.save': 'Save project', 'shortcut.designer.undo': 'Undo', 'shortcut.designer.redo': 'Redo',
        'shortcut.pixel.pencil': 'Pixel Pencil', 'shortcut.pixel.select': 'Pixel Select', 'shortcut.pixel.fill': 'Pixel Fill',
        'shortcut.conflict': 'Shortcut conflict: {error}',
        'mode.system': 'System', 'mode.light': 'Light', 'mode.dark': 'Dark',
        'density.compact': 'Compact', 'density.comfortable': 'Comfortable', 'density.spacious': 'Spacious',
        'wheel.zoom': 'Zoom', 'wheel.none': 'None', 'pan.pan': 'Pan', 'pan.none': 'None',
        'snap.off': 'Off', 'perf.fast': 'Fast', 'perf.exact': 'Exact',
        'validation.edit_complete': 'On edit complete', 'validation.idle': 'During idle', 'validation.continuous': 'Continuous',
        'help.language': 'Changes the language across the workbench, Pixel Studio, and Font Lab.',
        'help.startup': 'When enabled, the next launch attempts to restore the most recently opened project.',
        'help.theme_mode': 'System follows the Windows appearance automatically; Light and Dark override it.',
        'help.density': 'Changes control height and spacing only. OLED canvas pixels are never affected.',
        'help.ui_scale': 'Scales the application UI without changing project canvas, export size, or pixel data.',
        'help.reduced_motion': 'Suppresses non-essential Settings transitions for motion-sensitive or lower-performance environments.',
        'help.input': 'Interaction preferences affect editor navigation only and never enter project output.',
        'help.canvas_grid': 'Grid, bounds, rulers, and zones are editor overlays and never enter the OLED framebuffer.',
        'help.snap': 'Snapping uses real OLED pixels. Disable it for unrestricted positioning.',
        'help.shortcuts': 'Bindings are validated by one command registry. Conflicts are reported here instead of silently replacing another action.',
        'help.pixel_behavior': 'Mouse semantics are fixed; this group controls brush footprint and continuous stroke interpolation.',
        'help.pixel_view': 'These options change Pixel Studio authoring previews only.',
        'help.autosave': 'Autosave reduces data loss after an unexpected exit and is independent from normal undo history.',
        'help.snapshots': 'More snapshots consume a small amount of disk space but extend the recovery window.',
        'help.validation': 'On edit complete is recommended. Continuous feedback is faster but costs more on large projects.',
        'help.undo': 'Controls the maximum undo history retained by the editor and Pixel Studio.',
        'help.asset_cache': 'A larger cache reduces repeated asset parsing; lower it when memory is constrained.',
        'help.overlay': 'A diagnostic surface for performance investigations; keep it off during normal use.',
        'help.maintenance': 'Clearing cache does not delete project assets; resetting layout restores panel geometry only.',
        'help.reset_all': 'Restores every preference to defaults immediately and requires personal options to be configured again.',
    },
}

# Search accepts common product wording in addition to the visible localized copy.
# These terms are deliberately keyed to a setting row so results still focus the
# relevant control rather than merely opening a broad category.
_SEARCH_ALIASES = {
    'label.ui_scale': ('interface scale', '界面比例'),
    'label.danger': ('reset all preferences', '重置所有偏好'),
    'button.reset_all': ('reset all preferences', '重置所有偏好'),
}


class SettingsTextColumn(QWidget):
    """Text container that propagates QLabel height-for-width through nested layouts.

    QWidget does not reliably expose the height-for-width requirement of wrapped
    child labels through another layout on Windows.  This container makes that
    relationship explicit and synchronizes its minimum height whenever its width
    changes, so the outer SettingRow cannot collapse two-line helper copy into a
    one-line row.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text_widgets: list[QWidget] = []

    def register_text_widget(self, widget: QWidget):
        self._text_widgets.append(widget)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width: int):  # noqa: N802
        layout = self.layout()
        if layout is None:
            return super().sizeHint().height()
        margins = layout.contentsMargins()
        inner_width = max(1, int(width) - margins.left() - margins.right())
        visible = [widget for widget in self._text_widgets if not widget.isHidden()]
        heights = []
        for widget in visible:
            if widget.hasHeightForWidth():
                heights.append(max(0, widget.heightForWidth(inner_width)))
            else:
                heights.append(max(0, widget.sizeHint().height()))
        spacing = max(0, layout.spacing()) * max(0, len(heights) - 1)
        return margins.top() + margins.bottom() + sum(heights) + spacing

    def _sync_minimum_height(self, width: int):
        required = max(0, self.heightForWidth(max(1, int(width))))
        if self.minimumHeight() != required:
            self.setMinimumHeight(required)
            self.updateGeometry()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._sync_minimum_height(event.size().width())

    def refresh_height(self):
        self._sync_minimum_height(self.width())

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        width = max(1, self.width(), hint.width())
        return QSize(hint.width(), max(hint.height(), self.heightForWidth(width)))

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        width = max(1, self.width(), hint.width())
        return QSize(hint.width(), max(hint.height(), self.heightForWidth(width)))


class SettingRow(QWidget):
    """Responsive settings row with an independent text column.

    Wrapped label/help copy lives in its own vertical layout.  The control is a
    sibling column, never a grid item spanning the same text rows.  Qt can
    therefore resolve height-for-width for the copy before the outer row
    calculates its height, which prevents the Windows clipping/overlap seen in
    translated Settings pages.
    """
    row_vertical_padding = 10
    row_control_width = 220
    _unbounded_width = 16777215

    def __init__(self, label: QLabel | None, control: QWidget, help_label: QLabel | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName('SettingRow')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.label = label
        self.control = control
        self.help_label = help_label
        self.is_compact = False
        self._layout_mode: bool | None = None
        self._rebuild_count = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, self.row_vertical_padding, 0, 0)
        outer.setSpacing(self.row_vertical_padding)

        self._content = QWidget(self)
        self._content.setObjectName('SettingRowContent')
        self._content.setMinimumWidth(0)
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._flow = QBoxLayout(QBoxLayout.LeftToRight, self._content)
        self._flow.setContentsMargins(0, 0, 0, 0)
        self._flow.setSpacing(20)

        self._text_column = SettingsTextColumn(self._content)
        self._text_column.setMinimumWidth(0)
        self._text_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._text_layout = QVBoxLayout(self._text_column)
        self._text_layout.setContentsMargins(0, 0, 0, 0)
        self._text_layout.setSpacing(3)
        if self.label is not None:
            self.label.setMinimumWidth(0)
            self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._text_layout.addWidget(self.label)
            self._text_column.register_text_widget(self.label)
        if self.help_label is not None:
            self.help_label.setMinimumWidth(0)
            self.help_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self._text_layout.addWidget(self.help_label)
            self._text_column.register_text_widget(self.help_label)
        self._has_text = self.label is not None or self.help_label is not None
        self._text_column.setVisible(self._has_text)

        self._control_column = QWidget(self._content)
        self._control_column.setMinimumWidth(0)
        self._control_column.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._control_layout = QVBoxLayout(self._control_column)
        self._control_layout.setContentsMargins(0, 0, 0, 0)
        self._control_layout.setSpacing(0)
        self._control_layout.addWidget(self.control)
        self._control_layout.addStretch(1)

        self._flow.addWidget(self._text_column, 1)
        self._flow.addWidget(self._control_column, 0)
        outer.addWidget(self._content)

        self.divider = QFrame(self)
        self.divider.setObjectName('SettingRowDivider')
        self.divider.setFrameShape(QFrame.HLine)
        outer.addWidget(self.divider)
        self.set_compact(False)

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, width: int):  # noqa: N802
        outer = self.layout()
        margins = outer.contentsMargins() if outer is not None else None
        left = margins.left() if margins is not None else 0
        right = margins.right() if margins is not None else 0
        top = margins.top() if margins is not None else 0
        bottom = margins.bottom() if margins is not None else 0
        content_width = max(1, int(width) - left - right)
        control_hint = self.control.sizeHint().height()
        control_min = self.control.minimumSizeHint().height()
        control_height = max(0, control_hint, control_min)
        if not self._has_text:
            text_height = 0
        elif self.is_compact:
            text_height = self._text_column.heightForWidth(content_width)
        else:
            control_width = min(self.row_control_width, max(0, self._control_column.maximumWidth()))
            text_width = max(1, content_width - control_width - max(0, self._flow.spacing()))
            text_height = self._text_column.heightForWidth(text_width)
        if self.is_compact and self._has_text:
            content_height = text_height + max(0, self._flow.spacing()) + control_height
        else:
            content_height = max(text_height, control_height)
        divider_height = max(1, self.divider.sizeHint().height()) if hasattr(self, 'divider') else 1
        outer_spacing = max(0, outer.spacing()) if outer is not None else 0
        return top + bottom + content_height + outer_spacing + divider_height

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        width = max(1, self.width(), hint.width())
        return QSize(hint.width(), max(hint.height(), self.heightForWidth(width)))

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        width = max(1, self.width(), hint.width())
        return QSize(hint.width(), max(hint.height(), self.heightForWidth(width)))

    def _limit_control(self, compact: bool):
        bounded = isinstance(self.control, (QLineEdit, QComboBox, QSpinBox, QPushButton, StudioSelect, StudioNumericInput, StudioButton))
        if bounded:
            self.control.setMinimumWidth(0 if compact else 180)
            self.control.setMaximumWidth(360 if compact else self.row_control_width)
        self.control.setSizePolicy(QSizePolicy.Expanding if compact and bounded else QSizePolicy.Preferred, QSizePolicy.Fixed)
        if compact:
            self._control_column.setMaximumWidth(self._unbounded_width)
            self._control_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        else:
            self._control_column.setMaximumWidth(self.row_control_width)
            self._control_column.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    def refresh_geometry(self):
        for widget in (self.label, self.help_label, self.control):
            if widget is not None:
                widget.updateGeometry()
        self._text_layout.invalidate()
        self._text_column.refresh_height()
        self._control_layout.invalidate()
        self._flow.invalidate()
        self._text_column.updateGeometry()
        self._control_column.updateGeometry()
        self._content.updateGeometry()
        self.updateGeometry()
        self._flow.activate()

    def set_compact(self, compact: bool):
        compact = bool(compact)
        if self._layout_mode is compact:
            self.refresh_geometry()
            return False
        self._layout_mode = compact
        self.is_compact = compact
        self._rebuild_count += 1
        self._limit_control(compact)
        self._flow.setDirection(QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight)
        self._flow.setSpacing(10 if compact else 20)
        self._flow.setStretch(0, 0 if compact else 1)
        self._flow.setStretch(1, 0)
        self._control_layout.setAlignment(
            self.control,
            (Qt.AlignLeft if compact else Qt.AlignRight) | Qt.AlignTop,
        )
        self.refresh_geometry()
        return True


class PreferencesView(QWidget):
    preferencesChanged = Signal()
    clearAssetCacheRequested = Signal()
    resetWorkspaceRequested = Signal()

    # V12.3 Compact Professional Preferences: task-oriented, desktop-first IA.
    SECTIONS = ('general','appearance','canvas','pixel','keyboard','recovery','advanced')
    content_breakpoint = 700
    content_max_width = 760
    nav_width = 172
    section_gap = 30
    row_vertical_padding = 10
    row_control_width = 220
    header_search_width = 280

    def __init__(self, store: PreferencesStore, translator: Translator, parent=None):
        super().__init__(parent)
        self.store = store
        self.tr = translator
        self._text_bindings: list[tuple[QWidget, str, str]] = []
        self._page_headers: dict[str, tuple[QLabel, QLabel]] = {}
        self.shortcut_edits: dict[str, QLineEdit] = {}
        self._search_targets: list[tuple[str, QLabel]] = []
        self._search_rows: list[tuple[str, SettingRow, QLabel | None, QLabel | None]] = []
        self._search_aliases_by_row: dict[SettingRow, str] = {}
        self._search_match: QLabel | None = None
        self._page_animation: QPropertyAnimation | None = None
        self._animated_widget: QWidget | None = None
        self._page_layouts=[]
        self._page_contents=[]
        self._scrolls=[]
        self._content_by_scroll: dict[QScrollArea, QWidget] = {}
        self._viewport_to_scroll: dict[QWidget, QScrollArea] = {}
        self._setting_rows: list[SettingRow] = []
        self._rows_by_scroll: dict[QScrollArea, list[SettingRow]] = {}
        self._section_layouts=[]
        self._loading = False
        self._last_save_error = ''
        self._save_timer=QTimer(self); self._save_timer.setSingleShot(True); self._save_timer.setInterval(150); self._save_timer.timeout.connect(self._save_now)
        self._save_feedback_timer=QTimer(self); self._save_feedback_timer.setSingleShot(True); self._save_feedback_timer.setInterval(1100); self._save_feedback_timer.timeout.connect(self._clear_save_state)
        self._responsive_timer=QTimer(self); self._responsive_timer.setSingleShot(True); self._responsive_timer.setInterval(0); self._responsive_timer.timeout.connect(self._apply_responsive_layout)
        self.resize(980, 720)
        # Embedded Settings must accept the tab viewport; only PreferencesWindow owns a window minimum.
        self.setMinimumSize(0, 0)
        from runtime_settings import RuntimeSettings
        runtime = RuntimeSettings.from_preferences(store)
        self._metrics = build_ui_metrics(runtime.density, runtime.ui_scale)
        self._build()
        self._load_values()
        self._retranslate()
        self._clear_save_state()

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
        box=QCheckBox(); box.setProperty('settingsTextKey', key); box.setAccessibleName(self._t(key)); return box

    def _button(self, key: str) -> QPushButton:
        return self._bind_text(QPushButton(), key)  # type: ignore[return-value]

    def _help(self, key: str) -> QLabel:
        help_label=self._bind_text(QLabel(),key); help_label.setObjectName('SettingsFieldHelp'); help_label.setWordWrap(True); help_label.setMinimumWidth(0); help_label.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        return help_label  # type: ignore[return-value]

    def _section_label(self, section: str) -> str:
        return self._t(f'section.{section}')

    def _build(self):
        self.setObjectName('PreferencesRoot')
        m=self._metrics
        outer = QVBoxLayout(self); self._outer_layout=outer
        outer.setContentsMargins(24, 22, 24, 24); outer.setSpacing(18)

        # Compact header: title and transient status left, search on the right.
        top=QHBoxLayout(); top.setSpacing(12)
        self.preferences_title = self._bind_text(QLabel(), 'title'); self.preferences_title.setObjectName('PageTitle'); top.addWidget(self.preferences_title)
        top.addStretch(1)
        self.save_status=QLabel(); self.save_status.setObjectName('SettingsSaveStatus'); self.save_status.setAlignment(Qt.AlignRight|Qt.AlignVCenter); self.save_status.hide(); top.addWidget(self.save_status)
        self.search = QLineEdit(); self.search.setObjectName('SettingsSearch'); self.search.setClearButtonEnabled(True); self.search.setMinimumWidth(200); self.search.setMaximumWidth(self.header_search_width); self.search.installEventFilter(self); top.addWidget(self.search)
        self._find_shortcut=QShortcut(QKeySequence.Find,self); self._find_shortcut.setContext(Qt.WidgetWithChildrenShortcut); self._find_shortcut.activated.connect(self._focus_search)
        outer.addLayout(top)

        body = QHBoxLayout(); self._body_layout=body; body.setSpacing(30); outer.addLayout(body, 1)
        nav_column=QVBoxLayout(); nav_column.setContentsMargins(0,0,0,0); nav_column.setSpacing(10)
        self.nav = QListWidget(); self.nav.setObjectName('PreferencesNavigation'); self.nav.setMinimumWidth(148); self.nav.setMaximumWidth(self.nav_width); self.nav.setMinimumHeight(1); self.nav.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Expanding); self.nav.setUniformItemSizes(True)
        for _ in self.SECTIONS: self.nav.addItem('')
        nav_column.addWidget(self.nav,1)
        self.footer_product=QLabel('MonoOLED Studio'); self.footer_product.setObjectName('SettingsFooterProduct'); nav_column.addWidget(self.footer_product)
        self.footer_version=QLabel(f'v{APP_VERSION}'); self.footer_version.setObjectName('SettingsFooterVersion'); nav_column.addWidget(self.footer_version)
        body.addLayout(nav_column)
        self.stack = QStackedWidget(); self.stack.setObjectName('PreferencesStack'); body.addWidget(self.stack, 1)

        # Controls preserve the validated semantic settings model; only presentation changes in V12.3.
        self.language = QComboBox(); self.language.addItem('简体中文', 'zh_CN'); self.language.addItem('English', 'en_US')
        self.start_last = self._check('check.reopen')
        self.theme_mode = QComboBox(); [self.theme_mode.addItem('',data) for data in ('system','light','dark')]
        self.density = QComboBox(); [self.density.addItem('',data) for data in ('compact','comfortable','spacious')]
        self.ui_scale = QComboBox(); [self.ui_scale.addItem(text,data) for text,data in (('Auto','auto'),('90%','90%'),('100%','100%'),('110%','110%'),('125%','125%'),('150%','150%'))]
        self.reduced_motion=self._check('check.reduced_motion')
        self.wheel = QComboBox(); self.wheel.addItem('', 'zoom'); self.wheel.addItem('', 'none')
        self.middle = QComboBox(); self.middle.addItem('', 'pan'); self.middle.addItem('', 'none')
        self.space_pan = self._check('check.space_pan')
        self.grid=self._check('check.grid'); self.bounds=self._check('check.bounds'); self.rulers=self._check('check.rulers'); self.zones=self._check('check.zones')
        self.snap=QComboBox(); [self.snap.addItem(label,data) for label,data in (('Off',0),('1 px',1),('2 px',2),('4 px',4),('8 px',8))]
        self.left_action=self._label('value.draw'); self.right_action=self._label('value.erase')
        self.brush_size=QSpinBox(); self.brush_size.setRange(1,8)
        self.interpolation=self._check('check.interpolation'); self.pixel_grid=self._check('check.pixel_grid'); self.actual_preview=self._check('check.actual_preview')
        self.autosave=self._check('check.autosave'); self.autosave_minutes=QSpinBox(); self.autosave_minutes.setRange(1,60)
        self.snapshots=QSpinBox(); self.snapshots.setRange(1,100); self.prompt_recovery=self._check('check.prompt_recovery')
        self.validation=QComboBox(); [self.validation.addItem('',data) for data in ('edit_complete','idle','continuous')]
        self.undo_history=QSpinBox(); self.undo_history.setRange(10,2000)
        self.drag_preview=QComboBox(); self.drag_preview.addItem('', 'fast'); self.drag_preview.addItem('', 'exact')
        self.asset_cache=QSpinBox(); self.asset_cache.setRange(32,4096); self.perf_overlay=self._check('check.overlay')
        self.clear_cache=self._button('button.clear_cache'); self.reset_layout=self._button('button.reset_workspace'); self.reset_all=self._button('button.reset_all'); self.reset_all.setObjectName('DangerButton')
        self.clear_cache.clicked.connect(self.clearAssetCacheRequested.emit); self.reset_layout.clicked.connect(self.resetWorkspaceRequested.emit); self.reset_all.clicked.connect(self._reset_all)
        self.shortcut_error=QLabel(); self.shortcut_error.setObjectName('ErrorText'); self.shortcut_error.setWordWrap(True); self.shortcut_error.hide()
        for command_id in default_preferences()['shortcuts']:
            edit=QLineEdit(); edit.setClearButtonEnabled(True); self.shortcut_edits[command_id]=edit

        # General
        scroll,layout=self._page_shell('general')
        self._add_section(scroll,layout,'general','group.general',[
            ('label.language',self.language,'help.language'),('label.startup',self.start_last,'help.startup')
        ])
        self.stack.addWidget(scroll)

        # Appearance
        scroll,layout=self._page_shell('appearance')
        self._add_section(scroll,layout,'appearance','group.appearance',[
            ('label.theme_mode',self.theme_mode,'help.theme_mode'),('label.density',self.density,'help.density'),
            ('label.ui_scale',self.ui_scale,'help.ui_scale'),('',self.reduced_motion,'help.reduced_motion')
        ])
        self.stack.addWidget(scroll)

        # Canvas & Input
        scroll,layout=self._page_shell('canvas')
        self._add_section(scroll,layout,'canvas','group.input',[
            ('label.wheel',self.wheel,'help.input'),('label.middle',self.middle,None),('',self.space_pan,None)
        ])
        layout.addSpacing(self.section_gap)
        self._add_section(scroll,layout,'canvas','group.canvas',[
            ('',self.grid,'help.canvas_grid'),('',self.bounds,None),('',self.rulers,None),('',self.zones,None),('label.snap',self.snap,'help.snap')
        ])
        self.stack.addWidget(scroll)

        # Pixel Studio
        scroll,layout=self._page_shell('pixel')
        self._add_section(scroll,layout,'pixel','group.pixel_behavior',[
            ('label.left',self.left_action,'help.pixel_behavior'),('label.right',self.right_action,None),('label.brush',self.brush_size,None),('',self.interpolation,None)
        ])
        layout.addSpacing(self.section_gap)
        self._add_section(scroll,layout,'pixel','group.pixel_view',[
            ('',self.pixel_grid,'help.pixel_view'),('',self.actual_preview,None)
        ])
        self.stack.addWidget(scroll)

        # Keyboard gets its own developer-tool mental model.
        scroll,layout=self._page_shell('keyboard')
        keyboard_rows=[(f'shortcut.{command_id}', edit, None) for command_id,edit in self.shortcut_edits.items()]
        section=self._add_section(scroll,layout,'keyboard','group.shortcuts',keyboard_rows,section_help='help.shortcuts')
        section.layout().addWidget(self.shortcut_error)
        self.stack.addWidget(scroll)

        # Recovery
        scroll,layout=self._page_shell('recovery')
        self._add_section(scroll,layout,'recovery','group.autosave',[
            ('',self.autosave,'help.autosave'),('label.autosave_interval',self.autosave_minutes,None),('label.snapshots',self.snapshots,'help.snapshots'),('',self.prompt_recovery,None)
        ])
        layout.addSpacing(self.section_gap)
        self._add_section(scroll,layout,'recovery','group.recovery',[
            ('label.validation',self.validation,'help.validation'),('label.undo',self.undo_history,'help.undo')
        ])
        self.stack.addWidget(scroll)

        # Advanced: ordinary rows stay borderless; only the danger zone is a card.
        scroll,layout=self._page_shell('advanced')
        self._add_section(scroll,layout,'advanced','group.performance',[
            ('label.drag_preview',self.drag_preview,None),('label.cache',self.asset_cache,'help.asset_cache'),('',self.perf_overlay,'help.overlay')
        ])
        layout.addSpacing(self.section_gap)
        self._add_section(scroll,layout,'advanced','group.maintenance',[
            ('label.cache_action',self.clear_cache,'help.maintenance'),('label.workspace_action',self.reset_layout,None)
        ])
        layout.addSpacing(self.section_gap)
        self._add_section(scroll,layout,'advanced','group.danger',[
            ('label.danger',self.reset_all,'help.reset_all')
        ],danger=True)
        self.stack.addWidget(scroll)

        self.nav.currentRowChanged.connect(self._nav_changed); self.nav.setCurrentRow(0)
        self.search.textChanged.connect(self._search_changed)
        for widget in (self.language,self.theme_mode,self.density,self.ui_scale,self.wheel,self.middle,self.snap,self.drag_preview,self.validation): widget.currentIndexChanged.connect(self._controls_changed)
        for widget in (self.start_last,self.reduced_motion,self.space_pan,self.grid,self.bounds,self.rulers,self.zones,self.interpolation,self.pixel_grid,self.actual_preview,self.autosave,self.prompt_recovery,self.perf_overlay): widget.toggled.connect(self._controls_changed)
        for widget in (self.brush_size,self.autosave_minutes,self.snapshots,self.undo_history,self.asset_cache): widget.valueChanged.connect(self._controls_changed)
        for edit in self.shortcut_edits.values(): edit.editingFinished.connect(self._shortcuts_changed)
        self._apply_responsive_layout()

    def _setting_row(self, section: str, key: str, widget: QWidget, help_key: str|None=None) -> SettingRow:
        label=None
        if not key and isinstance(widget,QCheckBox):
            key=str(widget.property('settingsTextKey') or '')
        if key:
            label=QLabel(); label.setObjectName('SettingRowLabel'); label.setWordWrap(True); label.setMinimumWidth(0); label.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred); self._text_bindings.append((label,key,'setText')); self._search_targets.append((section,label))
        help_label=self._help(help_key) if help_key else None
        if label is not None:
            label.setBuddy(widget)
        row=SettingRow(label,widget,help_label)
        row.row_vertical_padding=self.row_vertical_padding
        row.row_control_width=self.row_control_width
        self._setting_rows.append(row)
        self._search_rows.append((section,row,label,help_label))
        aliases=[]
        for lang in ('zh_CN','en_US'):
            if key: aliases.append(_TEXT[lang].get(key,''))
            if help_key: aliases.append(_TEXT[lang].get(help_key,''))
        aliases.extend(_SEARCH_ALIASES.get(key, ()))
        self._search_aliases_by_row[row]=' '.join(x for x in aliases if x).casefold()
        self._sync_row_accessibility(row)
        return row

    def _sync_row_accessibility(self, row: SettingRow):
        name = row.label.text().strip() if row.label is not None else str(row.control.accessibleName() or '').strip()
        description = row.help_label.text().strip() if row.help_label is not None else ''
        if name:
            row.control.setAccessibleName(name)
        row.control.setAccessibleDescription(description)
        if isinstance(row.control, StudioSelect):
            row.control.button.setAccessibleName(name)
            row.control.button.setAccessibleDescription(description)

    def _focus_search(self):
        self.search.setFocus(Qt.ShortcutFocusReason)
        self.search.selectAll()

    def _add_section(self, scroll: QScrollArea, layout: QVBoxLayout, section: str, title_key: str, rows, *, danger=False, section_help: str|None=None):
        group=QFrame() if danger else QWidget()
        if danger: group.setObjectName('PreferencesDangerCard')
        else: group.setObjectName('PreferencesSection')
        box=QVBoxLayout(group); self._section_layouts.append(box)
        box.setContentsMargins(16,14,16,16) if danger else box.setContentsMargins(0,0,0,0)
        box.setSpacing(0)
        title=self._bind_text(QLabel(),title_key); title.setObjectName('SettingsSectionTitle'); box.addWidget(title)
        if section_help:
            section_help_label=self._help(section_help); section_help_label.setObjectName('SettingsSectionHelp'); box.addSpacing(4); box.addWidget(section_help_label)
        box.addSpacing(10)
        rows_for_scroll=self._rows_by_scroll.setdefault(scroll,[])
        for key,widget,help_key in rows:
            row=self._setting_row(section,key,widget,help_key); rows_for_scroll.append(row); box.addWidget(row)
        layout.addWidget(group)
        return group

    def _page_shell(self, section: str):
        scroll=QScrollArea(); scroll.setObjectName('PreferencesScroll'); scroll.setWidgetResizable(True); self._scrolls.append(scroll)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setObjectName('PreferencesViewport'); scroll.viewport().installEventFilter(self); self._viewport_to_scroll[scroll.viewport()]=scroll
        page=QWidget(); page.setObjectName('PreferencesPage')
        page_layout=QVBoxLayout(page); page_layout.setContentsMargins(8,4,18,28); page_layout.setSpacing(0); page_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        content=QWidget(); content.setObjectName('PreferencesContent'); content.setMinimumWidth(0); content.setMaximumWidth(self.content_max_width); self._page_contents.append(content); self._content_by_scroll[scroll]=content
        layout=QVBoxLayout(content); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0); self._page_layouts.append((page_layout,layout))
        h=QLabel(); h.setObjectName('PageTitle'); layout.addWidget(h)
        d=QLabel(); d.setObjectName('Muted'); d.setWordWrap(True); layout.addWidget(d); layout.addSpacing(24)
        self._page_headers[section]=(h,d)
        page_layout.addWidget(content,0,Qt.AlignHCenter|Qt.AlignTop); page_layout.addStretch(1); scroll.setWidget(page)
        return scroll,layout

    def _set_save_state(self,state: str):
        self._save_feedback_timer.stop()
        self.save_status.setProperty('saveState',state); self.save_status.setText(self._t(f'status.{state}')); self.save_status.setVisible(True)
        detail=self._last_save_error if state=='failed' else ''
        self.save_status.setToolTip(detail); self.save_status.setAccessibleDescription(detail)
        self.save_status.style().unpolish(self.save_status); self.save_status.style().polish(self.save_status)
        if state=='saved': self._save_feedback_timer.start()

    def _clear_save_state(self):
        self.save_status.setVisible(False)

    def _save_now(self):
        try:
            self.store.save()
        except OSError as exc:
            self._last_save_error=str(exc)
            self._set_save_state('failed')
            return False
        self._last_save_error=''
        self._set_save_state('saved')
        return True

    def _nav_changed(self, row: int):
        PopupManager.close_all(); index=max(0,int(row)); self.stack.setCurrentIndex(index); self._apply_responsive_layout()
        if self._page_animation is not None:self._page_animation.stop(); self._page_animation=None
        if self._animated_widget is not None:self._animated_widget.setGraphicsEffect(None); self._animated_widget=None
        if self.reduced_motion.isChecked() or os.environ.get('MONOOLED_REDUCED_MOTION')=='1': return
        widget=self.stack.currentWidget(); effect=QGraphicsOpacityEffect(widget); widget.setGraphicsEffect(effect); self._animated_widget=widget
        animation=QPropertyAnimation(effect,b'opacity',self); animation.setDuration(120); animation.setStartValue(0.90); animation.setEndValue(1.0); animation.setEasingCurve(QEasingCurve.OutCubic)
        def done(w=widget):
            w.setGraphicsEffect(None)
            if self._animated_widget is w:self._animated_widget=None
        animation.finished.connect(done); self._page_animation=animation; animation.start()

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
        for row in self._setting_rows:
            if isinstance(row.control,QCheckBox):
                key=str(row.control.property('settingsTextKey') or '')
                if key and row.label is None: row.control.setAccessibleName(self._t(key))
            self._sync_row_accessibility(row)
        state=str(self.save_status.property('saveState') or '')
        if state in ('saving','saved','failed'): self.save_status.setText(self._t(f'status.{state}'))

    def _search_changed(self, text: str):
        q=text.strip().casefold()
        if self._search_match is not None:
            self._search_match.setObjectName('SettingRowLabel'); self._search_match.style().unpolish(self._search_match); self._search_match.style().polish(self._search_match); self._search_match=None
        self.search.setProperty('searchMiss',False); self.search.setToolTip(''); self.search.setAccessibleDescription(''); self.search.style().unpolish(self.search); self.search.style().polish(self.search)
        if not q:return
        keywords={
            'general':'language startup reopen 语言 启动 全局',
            'appearance':'appearance system light dark density scale motion 外观 跟随系统 浅色 深色 密度 缩放 动效',
            'canvas':'mouse wheel pan space grid bounds rulers zones snap 鼠标 平移 网格 标尺 吸附 输入 画布',
            'pixel':'draw erase brush pixel stroke preview 绘制 擦除 画笔 像素 预览',
            'keyboard':'shortcut keyboard hotkey command 快捷键 键盘 命令',
            'recovery':'autosave recovery snapshot undo validation crash 自动保存 恢复 撤销 校验',
            'advanced':'performance cache overlay reset advanced 性能 缓存 重置 高级',
        }
        target_section=None; target_row=None; target_label=None
        for section,row,label,help_label in self._search_rows:
            label_text=label.text() if label is not None else ''
            help_text=help_label.text() if help_label is not None else ''
            control_text=''
            if isinstance(row.control,StudioSelect): control_text=row.control.currentText()
            elif isinstance(row.control,QLabel): control_text=row.control.text()
            if q in f"{label_text} {help_text} {control_text} {self._search_aliases_by_row.get(row,'')}".casefold():
                target_section=section; target_row=row; target_label=label; break
        if target_section is None:
            for name in self.SECTIONS:
                if q in (self._section_label(name)+' '+keywords.get(name,'')).casefold(): target_section=name; break
        if target_section is not None:
            self.nav.setCurrentRow(self.SECTIONS.index(target_section))
            if target_label is not None:
                self._search_match=target_label; target_label.setObjectName('SearchMatch'); target_label.style().unpolish(target_label); target_label.style().polish(target_label)
            current=self.stack.currentWidget()
            if target_row is not None and isinstance(current,QScrollArea):
                QTimer.singleShot(0,lambda s=current,r=target_row:s.ensureWidgetVisible(r,16,16))
        else:
            message=self._t('search.no_results')
            self.search.setProperty('searchMiss',True); self.search.setToolTip(message); self.search.setAccessibleDescription(message); self.search.style().unpolish(self.search); self.search.style().polish(self.search)

    @staticmethod
    def _set_combo(combo: QComboBox, data):
        idx=combo.findData(data)
        if idx>=0: combo.setCurrentIndex(idx)

    def _load_values(self):
        self._loading=True
        self._set_combo(self.language,self.store.get('language','zh_CN')); self.start_last.setChecked(bool(self.store.get('startup.reopen_last_project',False)))
        self._set_combo(self.theme_mode,self.store.get('appearance.theme_mode','system')); self._set_combo(self.density,self.store.get('appearance.density','comfortable')); self._set_combo(self.ui_scale,self.store.get('appearance.ui_scale','auto')); self.reduced_motion.setChecked(bool(self.store.get('appearance.reduced_motion',False)))
        self._set_combo(self.wheel,self.store.get('input.wheel_action','zoom')); self._set_combo(self.middle,self.store.get('input.middle_drag','pan')); self.space_pan.setChecked(self.store.get('input.space_drag','pan')=='pan')
        self.grid.setChecked(bool(self.store.get('canvas.grid',True))); self.bounds.setChecked(bool(self.store.get('canvas.bounds',True))); self.rulers.setChecked(bool(self.store.get('canvas.rulers',True))); self.zones.setChecked(bool(self.store.get('canvas.zones',False))); self._set_combo(self.snap,int(self.store.get('canvas.snap',0)))
        self.brush_size.setValue(int(self.store.get('pixel_studio.brush_size',1))); self.interpolation.setChecked(bool(self.store.get('pixel_studio.stroke_interpolation',True))); self.pixel_grid.setChecked(bool(self.store.get('pixel_studio.pixel_grid',True))); self.actual_preview.setChecked(bool(self.store.get('pixel_studio.actual_preview',True)))
        self.autosave.setChecked(bool(self.store.get('autosave.enabled',True))); self.autosave_minutes.setValue(int(self.store.get('autosave.interval_minutes',3))); self.snapshots.setValue(int(self.store.get('autosave.snapshots',10))); self.prompt_recovery.setChecked(bool(self.store.get('autosave.prompt_recovery',True)))
        self._set_combo(self.drag_preview,self.store.get('performance.drag_preview','fast')); self._set_combo(self.validation,self.store.get('performance.validation_mode','edit_complete')); self.undo_history.setValue(int(self.store.get('performance.undo_history',200))); self.asset_cache.setValue(int(self.store.get('performance.asset_cache_mb',512))); self.perf_overlay.setChecked(bool(self.store.get('performance.overlay',False)))
        for command_id,edit in self.shortcut_edits.items(): edit.setText(str(self.store.get(f'shortcuts.{command_id}',default_preferences()['shortcuts'][command_id])))
        self.shortcut_error.hide(); self._loading=False

    def _schedule_save(self):
        self._set_save_state('saving'); self._save_timer.start()

    def flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop(); self._save_now()
        elif str(self.save_status.property('saveState') or '')=='failed':
            self._save_now()

    def closeEvent(self,event):  # noqa: N802
        self.flush_pending_save(); super().closeEvent(event)

    def _controls_changed(self, *_):
        if self._loading: return
        new_language=self.language.currentData()
        self.store.set('language',new_language,save=False); self.store.set('startup.reopen_last_project',self.start_last.isChecked(),save=False)
        self.store.set('appearance.theme_mode',self.theme_mode.currentData(),save=False); self.store.set('appearance.density',self.density.currentData(),save=False); self.store.set('appearance.ui_scale',self.ui_scale.currentData(),save=False); self.store.set('appearance.reduced_motion',self.reduced_motion.isChecked(),save=False)
        self.store.set('input.wheel_action',self.wheel.currentData(),save=False); self.store.set('input.middle_drag',self.middle.currentData(),save=False); self.store.set('input.space_drag','pan' if self.space_pan.isChecked() else 'none',save=False)
        self.store.set('canvas.grid',self.grid.isChecked(),save=False); self.store.set('canvas.bounds',self.bounds.isChecked(),save=False); self.store.set('canvas.rulers',self.rulers.isChecked(),save=False); self.store.set('canvas.zones',self.zones.isChecked(),save=False); self.store.set('canvas.snap',self.snap.currentData(),save=False)
        self.store.set('pixel_studio.brush_size',self.brush_size.value(),save=False); self.store.set('pixel_studio.stroke_interpolation',self.interpolation.isChecked(),save=False); self.store.set('pixel_studio.pixel_grid',self.pixel_grid.isChecked(),save=False); self.store.set('pixel_studio.actual_preview',self.actual_preview.isChecked(),save=False)
        self.store.set('autosave.enabled',self.autosave.isChecked(),save=False); self.store.set('autosave.interval_minutes',self.autosave_minutes.value(),save=False); self.store.set('autosave.snapshots',self.snapshots.value(),save=False); self.store.set('autosave.prompt_recovery',self.prompt_recovery.isChecked(),save=False)
        self.store.set('performance.drag_preview',self.drag_preview.currentData(),save=False); self.store.set('performance.validation_mode',self.validation.currentData(),save=False); self.store.set('performance.undo_history',self.undo_history.value(),save=False); self.store.set('performance.asset_cache_mb',self.asset_cache.value(),save=False); self.store.set('performance.overlay',self.perf_overlay.isChecked(),save=False)
        self._schedule_save()
        if new_language!=self.tr.language:
            self.tr.set_language(new_language); self._retranslate(); self._settle_after_text_change()
        self.preferencesChanged.emit()

    def _shortcuts_changed(self):
        if self._loading: return
        origin=self.sender() if isinstance(self.sender(),QLineEdit) else None
        for edit in self.shortcut_edits.values():
            edit.setProperty('validationState',''); edit.style().unpolish(edit); edit.style().polish(edit)
        mapping={command_id:edit.text().strip() for command_id,edit in self.shortcut_edits.items()}
        registry=CommandRegistry()
        for command_id,default in default_preferences()['shortcuts'].items(): registry.register(command_id,shortcut=default)
        try: registry.apply_bindings(mapping,ignore_unknown=False)
        except ShortcutConflictError as exc:
            self.shortcut_error.setText(self._t('shortcut.conflict',error=str(exc))); self.shortcut_error.show()
            if origin is not None:
                origin.setProperty('validationState','error'); origin.style().unpolish(origin); origin.style().polish(origin)
            current=self.stack.currentWidget()
            if isinstance(current,QScrollArea): QTimer.singleShot(0,lambda s=current:s.ensureWidgetVisible(self.shortcut_error,16,16))
            return
        self.shortcut_error.hide()
        for edit in self.shortcut_edits.values():
            edit.setProperty('validationState',''); edit.style().unpolish(edit); edit.style().polish(edit)
        for command_id,value in mapping.items(): self.store.set(f'shortcuts.{command_id}',value,save=False)
        self._schedule_save(); self.preferencesChanged.emit()

    def set_language(self, language: str):
        if language not in _TEXT: language='en_US'
        changed=language!=self.tr.language
        if changed:
            self.tr.set_language(language); self._retranslate()
        self._settle_after_text_change()
        return changed

    def _settle_after_text_change(self):
        for heading,desc in self._page_headers.values():
            heading.updateGeometry(); desc.updateGeometry()
        for row in self._setting_rows:
            row.refresh_geometry()
        self._schedule_responsive_layout()
        QTimer.singleShot(0,self.stabilize_layout)

    def _apply_layout_metrics(self):
        # Settings may be embedded in a narrow editor tab.  Shell chrome compresses
        # before row content so the viewport remains the source of truth for reflow.
        narrow = self.width() > 0 and self.width() < 860
        if narrow:
            self._outer_layout.setContentsMargins(12,12,12,16); self._outer_layout.setSpacing(12)
            self._body_layout.setSpacing(16); self.nav.setMaximumWidth(148); self.search.setMinimumWidth(140)
        else:
            self._outer_layout.setContentsMargins(24,22,24,24); self._outer_layout.setSpacing(18)
            self._body_layout.setSpacing(30); self.nav.setMaximumWidth(self.nav_width); self.search.setMinimumWidth(200)
        self._apply_responsive_layout()

    def _effective_content_width(self, scroll: QScrollArea) -> int:
        page=scroll.widget(); viewport_width=max(0,int(scroll.viewport().width()))
        if page is None or page.layout() is None:return min(viewport_width,self.content_max_width)
        margins=page.layout().contentsMargins()
        return max(0,min(viewport_width-margins.left()-margins.right(),self.content_max_width))

    def _schedule_responsive_layout(self):
        self._responsive_timer.start()

    def _apply_responsive_layout(self):
        for scroll in self._scrolls:
            target_width = self._effective_content_width(scroll)
            content = self._content_by_scroll.get(scroll)
            if content is not None:
                content.setMaximumWidth(self.content_max_width)
                content.setMinimumWidth(target_width)
                content.updateGeometry()
            available = target_width
            compact = available > 0 and available < self.content_breakpoint
            for row in self._rows_by_scroll.get(scroll,[]):
                row.set_compact(compact)
                row.refresh_geometry()

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.search and event.type()==QEvent.KeyPress and event.key()==Qt.Key_Escape:
            self.search.clear(); event.accept(); return True
        if watched in self._viewport_to_scroll and event.type() in (QEvent.Resize,QEvent.LayoutRequest,QEvent.Show,QEvent.Hide):
            self._schedule_responsive_layout()
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):  # noqa: N802
        self._schedule_responsive_layout(); super().resizeEvent(event)

    def stabilize_layout(self):
        """Establish deterministic row geometry before first paint."""
        self.ensurePolished(); self.nav.ensurePolished(); self.stack.ensurePolished(); self._apply_layout_metrics()
        self.nav.doItemsLayout(); self.nav.updateGeometry()
        current=self.stack.currentWidget()
        if isinstance(current,QScrollArea):
            for row in self._rows_by_scroll.get(current,[]):
                row.refresh_geometry()
        if current is not None:
            current.ensurePolished(); current.updateGeometry()
            if current.layout() is not None: current.layout().invalidate(); current.layout().activate()
            if isinstance(current,QScrollArea):
                page=current.widget()
                if page is not None and page.layout() is not None: page.layout().invalidate(); page.layout().activate(); page.updateGeometry()
                content=self._content_by_scroll.get(current)
                if content is not None and content.layout() is not None: content.layout().invalidate(); content.layout().activate(); content.updateGeometry()
                current.viewport().updateGeometry(); current.viewport().update()
        if self.layout() is not None: self.layout().invalidate(); self.layout().activate()
        self.updateGeometry(); self.update()

    def showEvent(self,event):  # noqa: N802
        self.stabilize_layout(); QTimer.singleShot(0,self.stabilize_layout); super().showEvent(event)

    def apply_runtime_settings(self,runtime):
        self._metrics=build_ui_metrics(runtime.density,runtime.ui_scale)
        if bool(runtime.reduced_motion)!=self.reduced_motion.isChecked():
            self._loading=True; self.reduced_motion.setChecked(bool(runtime.reduced_motion)); self._loading=False
        self._apply_layout_metrics(); self.stabilize_layout()

    def _reset_all(self):
        answer=QMessageBox.question(
            self,self._t('confirm.reset_all.title'),self._t('confirm.reset_all.body'),
            QMessageBox.Yes|QMessageBox.No,QMessageBox.No,
        )
        if answer!=QMessageBox.Yes:return
        self.store.data=default_preferences(); self._save_now(); self.tr.set_language(self.store.get('language','zh_CN')); self._load_values(); self._retranslate(); self._settle_after_text_change(); self.preferencesChanged.emit()

    def layout_violations(self) -> list[str]:
        violations=[]
        if self.width()<=0 or self.height()<=0: violations.append('preferences_view')
        if self.nav.width()<120: violations.append('navigation_width')
        if self.stack.width()<=0: violations.append('stack_width')
        current=self.stack.currentWidget()
        if current is None or not isinstance(current,QScrollArea) or current.width()<=0 or current.height()<=0:
            violations.append('current_page'); return violations
        if self.search.height()<=0: violations.append('search')

        # Header controls must remain disjoint even when translated labels or Save
        # feedback temporarily become wider.
        header_widgets=[self.preferences_title,self.search]
        if self.save_status.isVisible(): header_widgets.append(self.save_status)
        header_rects=[QRect(w.mapTo(self,QPoint(0,0)),w.size()) for w in header_widgets if w.isVisible()]
        for i,left in enumerate(header_rects):
            for right in header_rects[i+1:]:
                if left.intersects(right): violations.append('header_overlap')

        viewport=current.viewport(); content=self._content_by_scroll.get(current)
        if content is None: violations.append('current_content'); return violations
        content_rect=QRect(content.mapTo(viewport,QPoint(0,0)),content.size())
        if content_rect.left()<0 or content_rect.right()>=viewport.width(): violations.append('content_horizontal_overflow')
        if current.horizontalScrollBar().isVisible(): violations.append('horizontal_scrollbar')

        current_rows = self._rows_by_scroll.get(current, [])
        expected_compact=self._effective_content_width(current)>0 and self._effective_content_width(current)<self.content_breakpoint
        row_rects=[]
        for row in current_rows:
            if row.is_compact!=expected_compact: violations.append('responsive_mode_mismatch')
            row_rect=QRect(row.mapTo(viewport,QPoint(0,0)),row.size()); row_rects.append(row_rect)
            row_in_content=QRect(row.mapTo(content,QPoint(0,0)),row.size())
            if row_in_content.left()<0 or row_in_content.right()>=content.width(): violations.append('setting_row_horizontal_overflow')
            control_rect=QRect(row.control.mapTo(row._content,QPoint(0,0)),row.control.size())
            if control_rect.left()<0 or control_rect.right()>=row._content.width(): violations.append('setting_control_overflow')
            if row._has_text:
                required_text_height=row._text_column.heightForWidth(max(1,row._text_column.width()))
                if row._text_column.height()<required_text_height: violations.append('setting_text_column_vertical_clipping')
            text_column_rect=QRect(row._text_column.mapTo(row,QPoint(0,0)),row._text_column.size())
            control_column_rect=QRect(row._control_column.mapTo(row,QPoint(0,0)),row._control_column.size())
            if row.is_compact:
                if row._has_text and control_column_rect.top()<=text_column_rect.bottom(): violations.append('setting_row_overlap')
            elif not text_column_rect.intersected(control_column_rect).isEmpty():
                violations.append('setting_row_overlap')
            if row.label is not None:
                needed=row.label.heightForWidth(max(1,row.label.width())) if row.label.hasHeightForWidth() else row.label.sizeHint().height()
                if row.label.height()<needed: violations.append('setting_label_vertical_clipping')
            if row.help_label is not None:
                needed=row.help_label.heightForWidth(max(1,row.help_label.width())) if row.help_label.hasHeightForWidth() else row.help_label.sizeHint().height()
                if row.help_label.height()<needed: violations.append('setting_help_vertical_clipping')
            if row._content.geometry().intersects(row.divider.geometry()): violations.append('setting_row_internal_overlap')
        ordered=sorted(row_rects,key=lambda r:(r.top(),r.left()))
        for prev,curr in zip(ordered,ordered[1:]):
            if prev.intersects(curr): violations.append('setting_row_overlap')

        sections=[w for w in content.findChildren(QWidget) if w.objectName() in ('PreferencesSection','PreferencesDangerCard')]
        section_rects=sorted((QRect(w.mapTo(viewport,QPoint(0,0)),w.size()) for w in sections if w.isVisible()),key=lambda r:(r.top(),r.left()))
        for prev,curr in zip(section_rects,section_rects[1:]):
            if prev.intersects(curr): violations.append('setting_section_overlap')
        return list(dict.fromkeys(violations))



class PreferencesWindow(QMainWindow):
    """Compatibility floating host; MonoOLED Studio embeds PreferencesView in a tab."""
    preferencesChanged = Signal()
    clearAssetCacheRequested = Signal()
    resetWorkspaceRequested = Signal()

    def __init__(self, store: PreferencesStore, translator: Translator, parent=None):
        super().__init__(parent, Qt.Window)
        self.view = PreferencesView(store, translator, parent=self); self.setCentralWidget(self.view)
        self.resize(1000, 740); self.setMinimumSize(720, 560)
        self.view.preferencesChanged.connect(self.preferencesChanged.emit)
        self.view.clearAssetCacheRequested.connect(self.clearAssetCacheRequested.emit)
        self.view.resetWorkspaceRequested.connect(self.resetWorkspaceRequested.emit)
        self.setWindowTitle(self.view._t('title'))

    def __getattr__(self, name):
        view = self.__dict__.get('view')
        if view is not None and hasattr(view, name): return getattr(view, name)
        raise AttributeError(name)

    def apply_runtime_settings(self, runtime): return self.view.apply_runtime_settings(runtime)

    def set_language(self, language: str):
        changed = self.view.set_language(language); self.setWindowTitle(self.view._t('title')); return changed

    def layout_violations(self): return self.view.layout_violations()

    def closeEvent(self, event):  # noqa: N802
        self.view.flush_pending_save(); super().closeEvent(event)
