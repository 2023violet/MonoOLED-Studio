from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QFontComboBox, QFormLayout, QInputDialog,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from atomic_io import atomic_write_bytes
from bitmap_encoding import MonoBitmap, encode_bitmap
from font_pack import FontPack
from output_formatter import OutputItem, format_output
from output_profiles import EncodingProfile, OutputProfile, RasterProfile, TextFormatProfile, builtin_profiles
from project_workspace import PROJECT_FILENAME, ProjectWorkspace
from ui_controls import StudioSelect

QComboBox = StudioSelect


_MODE_VALUES = {
    '逐行式': ('horizontal', 'row_major'),
    '行列式': ('horizontal', 'column_major'),
    '逐列式': ('vertical', 'column_major'),
    '列行式（SSD1306 VLSB）': ('vertical', 'row_major'),
}


class _GenerationSignals(QObject):
    completed = Signal(int, object, object)
    failed = Signal(int, str)


class _GenerationTask(QRunnable):
    def __init__(self, generation_id, bitmaps, profile, symbol):
        super().__init__()
        self.generation_id = generation_id
        self.bitmaps = bitmaps
        self.profile = profile
        self.symbol = symbol
        self.signals = _GenerationSignals()

    def run(self):
        try:
            items = []
            for spec in self.bitmaps:
                encoded = encode_bitmap(spec['bitmap'], self.profile.encoding)
                items.append(OutputItem(
                    name=spec['name'], encoded=encoded, codepoint=spec.get('codepoint'),
                    width=spec['bitmap'].width, height=spec['bitmap'].height,
                    bearing_x=spec.get('bearing_x', 0), bearing_y=spec.get('bearing_y', 0),
                    advance=spec.get('advance', 0),
                ))
            formatted = format_output(items, self.profile.text, symbol=self.symbol)
            self.signals.completed.emit(self.generation_id, formatted, items)
        except Exception as exc:
            self.signals.failed.emit(self.generation_id, str(exc))


class OutputWorkbench(QWidget):
    """Pixel Studio's deterministic encoding, preview, animation and save surface."""

    def __init__(self, window, inspector_layout, root_layout):
        super().__init__(window)
        self.window = window
        self.project_root = window.project_root
        self.preferences = window.preferences
        self.project = self._load_project()
        self.temporary = self.project is None
        self._generation_id = 0
        self._running = False
        self._pending = None
        self._last_formatted = None
        self._last_items = ()
        self._last_valid_profile = None
        self._applying_profile = False
        self._trace_index = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._generate_timer = QTimer(self)
        self._generate_timer.setSingleShot(True)
        self._generate_timer.setInterval(80)
        self._generate_timer.timeout.connect(self.generate_now)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._persist_profile)
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self.next_step)
        self._build_controls(inspector_layout)
        self._build_output(root_layout)
        self._canvas_display_changed(); self._display_changed()
        self._load_active_profile()
        self._source_changed()

    def _load_project(self):
        if self.window.project_workspace is not None:
            return self.window.project_workspace
        manifest = self.project_root / PROJECT_FILENAME
        if not manifest.is_file():
            return None
        try:
            return ProjectWorkspace.load(manifest)
        except (OSError, ValueError):
            return None

    def group_titles(self):
        return tuple(group.title() for group in self._groups)

    def _group(self, title, parent_layout):
        group = QGroupBox(title)
        form = QFormLayout(group)
        parent_layout.addWidget(group)
        self._groups.append(group)
        return form

    @staticmethod
    def _combo(items):
        combo = QComboBox()
        for label, value in items:
            combo.addItem(label, value)
        return combo

    def _build_controls(self, layout):
        self._groups = []
        source = self._group('来源', layout)
        self.source_combo = self._combo((('当前 Pixel 画布', 'canvas'), ('当前选区', 'selection'), ('当前 Designer 场景帧', 'scene'), ('项目 Font Pack', 'font')))
        self.profile_combo = QComboBox()
        self.font_combo = QComboBox()
        self.characters = QLineEdit()
        self.characters.setPlaceholderText('留空时按 Unicode 码点排序')
        source.addRow('数据源', self.source_combo)
        source.addRow('输出配置', self.profile_combo)
        profile_actions=QHBoxLayout();self.new_profile_button=QPushButton('另存配置');self.delete_profile_button=QPushButton('删除配置');profile_actions.addWidget(self.new_profile_button);profile_actions.addWidget(self.delete_profile_button);source.addRow('',profile_actions)
        source.addRow('Font Pack', self.font_combo)
        source.addRow('字符范围', self.characters)
        self.temporary_label = QLabel('临时配置（关闭后不保存）' if self.temporary else '项目配置')
        source.addRow('', self.temporary_label)
        self._populate_sources()

        raster = self._group('字模与图片', layout)
        self.alignment_combo = self._combo((('相对于整体', 'font_set'), ('相对于字宽', 'glyph_width')))
        self.threshold_mode = self._combo((('亮度阈值', 'luma'), ('RGB 全部达到阈值', 'rgb_all')))
        self.threshold = QSpinBox(); self.threshold.setRange(0, 255); self.threshold.setValue(128)
        self.red = QSpinBox(); self.green = QSpinBox(); self.blue = QSpinBox()
        for control in (self.red, self.green, self.blue): control.setRange(0, 255); control.setValue(255)
        self.invert_source = QCheckBox('反转栅格结果')
        self.antialias = self._combo((('1×', 1), ('2×', 2), ('4×', 4)))
        raster.addRow('对齐方式', self.alignment_combo); raster.addRow('阈值模式', self.threshold_mode)
        raster.addRow('亮度', self.threshold); raster.addRow('R', self.red); raster.addRow('G', self.green); raster.addRow('B', self.blue)
        raster.addRow('', self.invert_source); raster.addRow('抗锯齿', self.antialias)
        self.raster_hint = QLabel('1-bit 素材不再次阈值化'); self.raster_hint.setWordWrap(True); raster.addRow('', self.raster_hint)

        encoding = self._group('点阵', layout)
        self.mode_combo = self._combo(tuple((name, name) for name in _MODE_VALUES))
        self.bit_order = self._combo((('高位在前：首点 → bit7', 'msb_first'), ('低位在前：首点 → bit0', 'lsb_first')))
        self.polarity = self._combo((('阳码：亮点编码为 1', 'one_is_lit'), ('阴码：亮点编码为 0', 'zero_is_lit')))
        encoding.addRow('取模方式', self.mode_combo); encoding.addRow('位序', self.bit_order); encoding.addRow('极性', self.polarity)

        formatting = self._group('格式', layout)
        self.container = self._combo((('文本数组', 'text'), ('二进制 BIN', 'binary')))
        self.radix = self._combo((('十六进制', 'hex'), ('十进制', 'decimal')))
        self.bytes_per_line = QSpinBox(); self.bytes_per_line.setRange(1, 256); self.bytes_per_line.setValue(16)
        self.index_entries_per_line = QSpinBox(); self.index_entries_per_line.setRange(1, 256); self.index_entries_per_line.setValue(16)
        self.index_mode = self._combo((('无索引', 'none'), ('内联索引', 'inline'), ('独立索引文件', 'sidecar')))
        self.minimal = QCheckBox('精简数据'); self.compact = QCheckBox('紧凑格式')
        formatting.addRow('容器', self.container); formatting.addRow('输出进制', self.radix)
        formatting.addRow('每行字节', self.bytes_per_line); formatting.addRow('每行索引', self.index_entries_per_line); formatting.addRow('索引', self.index_mode)
        formatting.addRow('', self.minimal); formatting.addRow('', self.compact)
        self.template_fields = {}
        for label, name in (
            ('段前缀', 'segment_prefix'), ('段后缀', 'segment_suffix'),
            ('注释前缀', 'comment_prefix'), ('注释后缀', 'comment_suffix'),
            ('数据前缀', 'data_prefix'), ('数据后缀', 'data_suffix'),
            ('行前缀', 'line_prefix'), ('行后缀', 'line_suffix'), ('行尾缀', 'line_end'),
        ):
            edit = QLineEdit(); self.template_fields[name] = edit; formatting.addRow(label, edit)

        display = self._group('显示', layout)
        self.background_color = QLineEdit(str(self.preferences.get('pixel_studio.canvas_background', '#000000')))
        self.grid_color = QLineEdit(str(self.preferences.get('pixel_studio.grid_color', '#495028')))
        self.fill_color = QLineEdit(str(self.preferences.get('pixel_studio.pixel_fill', '#FFFFFF')))
        self.border_color = QLineEdit(str(self.preferences.get('pixel_studio.pixel_border', '#FFFF00')))
        self.pixel_size = QSpinBox(); self.pixel_size.setRange(1, 40); self.pixel_size.setValue(self.window.canvas.zoom)
        self.output_font = QFontComboBox(); self.output_font_size = QSpinBox(); self.output_font_size.setRange(8, 32); self.output_font_size.setValue(14)
        self.animation_speed = self._combo((('0.5×', 0.5), ('1×', 1.0), ('2×', 2.0)))
        self.reset_display_button = QPushButton('重置显示')
        display.addRow('画布背景', self.background_color); display.addRow('网格线', self.grid_color)
        display.addRow('像素填充', self.fill_color); display.addRow('像素边框', self.border_color); display.addRow('像素大小', self.pixel_size)
        display.addRow('输出字体', self.output_font); display.addRow('字体大小', self.output_font_size)
        display.addRow('动画速度', self.animation_speed); display.addRow('', self.reset_display_button)

        self.validation_label = QLabel(); self.validation_label.setWordWrap(True); layout.addWidget(self.validation_label)
        for control in self._configuration_controls():
            signal = getattr(control, 'currentIndexChanged', None) or getattr(control, 'valueChanged', None) or getattr(control, 'toggled', None) or getattr(control, 'textChanged', None)
            signal.connect(self._configuration_changed)
        self.source_combo.currentIndexChanged.connect(self._source_changed)
        self.profile_combo.currentIndexChanged.connect(self._profile_selected)
        self.new_profile_button.clicked.connect(self._save_as_profile);self.delete_profile_button.clicked.connect(self._delete_profile)
        self.new_profile_button.setEnabled(not self.temporary);self.delete_profile_button.setEnabled(not self.temporary)
        self.output_font.currentFontChanged.connect(self._display_changed)
        self.output_font_size.valueChanged.connect(self._display_changed)
        for edit in (self.background_color,self.grid_color,self.fill_color,self.border_color): edit.textChanged.connect(self._canvas_display_changed)
        self.pixel_size.valueChanged.connect(self._pixel_size_changed)
        self.animation_speed.currentIndexChanged.connect(self._speed_changed)
        self.reset_display_button.clicked.connect(self._reset_display)
        saved_font=str(self.preferences.get('pixel_studio.output_font',''))
        if saved_font:self.output_font.setCurrentFont(QFont(saved_font))
        self.output_font_size.setValue(int(self.preferences.get('pixel_studio.output_font_size',14)))

    def _build_output(self, root_layout):
        panel = QWidget(); self.bottom_panel=panel; panel.setObjectName('OutputWorkbenchBottom')
        body = QHBoxLayout(panel)
        animation = QVBoxLayout(); self.animation_label = QLabel('尚未生成字模'); self.animation_label.setMinimumWidth(260); self.animation_label.setWordWrap(True); animation.addWidget(self.animation_label)
        animation_actions = QHBoxLayout()
        self.previous_button = QPushButton('上一步'); self.play_button = QPushButton('播放'); self.next_button = QPushButton('下一步')
        for button in (self.previous_button, self.play_button, self.next_button): animation_actions.addWidget(button)
        animation.addLayout(animation_actions); body.addLayout(animation)
        self.output_text = QPlainTextEdit(); self.output_text.setReadOnly(True); self.output_text.setObjectName('OutputText'); body.addWidget(self.output_text, 1)
        root_layout.addWidget(panel)
        actions = QHBoxLayout(); self.collapse_button=QPushButton('收起输出');actions.addWidget(self.collapse_button);actions.addStretch(1)
        self.generate_button = QPushButton('生成字模'); self.generate_button.setObjectName('GenerateBitmapButton')
        self.copy_button = QPushButton('复制数组'); self.copy_button.setObjectName('CopyArrayButton')
        self.save_button = QPushButton('保存字模'); self.save_button.setObjectName('SaveBitmapButton')
        self.clear_button = QPushButton('清除输出'); self.clear_button.setObjectName('ClearOutputButton')
        for button in (self.generate_button, self.copy_button, self.save_button, self.clear_button): actions.addWidget(button)
        root_layout.addLayout(actions)
        self.generate_button.clicked.connect(self.generate_now); self.copy_button.clicked.connect(self.copy_output)
        self.save_button.clicked.connect(self.save_output); self.clear_button.clicked.connect(self.clear_output)
        self.previous_button.clicked.connect(self.previous_step); self.next_button.clicked.connect(self.next_step); self.play_button.clicked.connect(self.toggle_play)
        self.collapse_button.clicked.connect(self._toggle_bottom_panel)

    def _toggle_bottom_panel(self):
        visible=not self.bottom_panel.isVisible();self.bottom_panel.setVisible(visible);self.collapse_button.setText('收起输出' if visible else '展开输出')

    def _configuration_controls(self):
        return (
            self.alignment_combo, self.threshold_mode, self.threshold, self.red, self.green, self.blue,
            self.invert_source, self.antialias, self.mode_combo, self.bit_order, self.polarity,
            self.container, self.radix, self.bytes_per_line, self.index_entries_per_line, self.index_mode, self.minimal,
            self.compact, *self.template_fields.values(), self.characters, self.font_combo,
        )

    def _populate_sources(self):
        self.font_combo.clear()
        for manifest in sorted(self.project_root.rglob('fontpack.json')):
            try:
                pack = FontPack.load(manifest.parent)
                self.font_combo.addItem(pack.name, manifest.parent.relative_to(self.project_root).as_posix())
            except Exception:
                continue

    def _load_active_profile(self):
        active, saved = self.project.get_output_profiles() if self.project else ('ssd1306_vlsb_c', {})
        profiles = {**builtin_profiles(), **saved}
        self.profile_combo.blockSignals(True); self.profile_combo.clear()
        for profile_id, profile in profiles.items(): self.profile_combo.addItem(profile.name, profile_id)
        self.profile_combo.setCurrentIndex(max(0, self.profile_combo.findData(active))); self.profile_combo.blockSignals(False)
        profile=profiles[active if active in profiles else self.profile_combo.currentData()];self._last_valid_profile=profile;self._apply_profile(profile)

    def _apply_profile(self, profile):
        self._applying_profile=True
        axis = profile.encoding.bit_axis; order = profile.encoding.group_order
        mode = next(name for name, values in _MODE_VALUES.items() if values == (axis, order))
        controls = (
            (self.alignment_combo, profile.raster.alignment), (self.threshold_mode, profile.raster.threshold_mode),
            (self.antialias, profile.raster.antialias_scale), (self.mode_combo, mode),
            (self.bit_order, profile.encoding.bit_order), (self.polarity, profile.encoding.polarity),
            (self.container, profile.text.container), (self.radix, profile.text.radix),
            (self.index_mode, profile.text.index_mode),
        )
        for control, value in controls:
            control.blockSignals(True); control.setCurrentIndex(control.findData(value)); control.blockSignals(False)
        for control, value in ((self.threshold, profile.raster.luma_threshold), (self.red, profile.raster.red_threshold), (self.green, profile.raster.green_threshold), (self.blue, profile.raster.blue_threshold), (self.bytes_per_line, profile.text.bytes_per_line), (self.index_entries_per_line, profile.text.index_entries_per_line)):
            control.blockSignals(True); control.setValue(value); control.blockSignals(False)
        self.invert_source.setChecked(profile.raster.invert_source); self.minimal.setChecked(profile.text.minimal_data); self.compact.setChecked(profile.text.compact_spacing)
        for name, edit in self.template_fields.items(): edit.setText(getattr(profile.text, name).replace('\n', '\\n'))
        self._applying_profile=False

    def _profile(self):
        bit_axis, group_order = _MODE_VALUES[self.mode_combo.currentData()]
        raster = RasterProfile(
            alignment=self.alignment_combo.currentData(), threshold_mode=self.threshold_mode.currentData(),
            luma_threshold=self.threshold.value(), red_threshold=self.red.value(), green_threshold=self.green.value(),
            blue_threshold=self.blue.value(), invert_source=self.invert_source.isChecked(), antialias_scale=self.antialias.currentData(),
        )
        defaults = asdict(TextFormatProfile())
        defaults.update(
            container=self.container.currentData(), radix=self.radix.currentData(), bytes_per_line=self.bytes_per_line.value(), index_entries_per_line=self.index_entries_per_line.value(),
            index_mode=self.index_mode.currentData(), minimal_data=self.minimal.isChecked(), compact_spacing=self.compact.isChecked(),
        )
        for name, edit in self.template_fields.items(): defaults[name] = edit.text().replace('\\n', '\n')
        return OutputProfile(
            name=self.profile_combo.currentText() or 'Output Profile', raster=raster,
            encoding=EncodingProfile(bit_axis=bit_axis, group_order=group_order, bit_order=self.bit_order.currentData(), polarity=self.polarity.currentData()),
            text=TextFormatProfile(**defaults),
        )

    def _configuration_changed(self, *_):
        if self._applying_profile:return
        self._validate_source()
        self._generate_timer.start()
        if self.project: self._save_timer.start()

    def _profile_selected(self, *_):
        if not self.profile_combo.currentData(): return
        _, saved = self.project.get_output_profiles() if self.project else ('ssd1306_vlsb_c', {})
        profiles = {**builtin_profiles(), **saved}
        profile = profiles.get(str(self.profile_combo.currentData()))
        if profile: self._apply_profile(profile); self._configuration_changed()

    def _persist_profile(self):
        if not self.project or not self.profile_combo.currentData(): return
        try:
            profile=self._profile();self.project.upsert_output_profile(str(self.profile_combo.currentData()), profile, activate=True);self._last_valid_profile=profile
            self.validation_label.setText('配置已保存到项目')
        except Exception as exc:
            self.validation_label.setText(f'配置保存失败：{exc}')
            if self._last_valid_profile:self._apply_profile(self._last_valid_profile)

    def _save_as_profile(self):
        if not self.project:return
        profile_id,ok=QInputDialog.getText(self,'另存配置','配置 ID（小写字母、数字、_、-）')
        if not ok or not profile_id:return
        name,ok=QInputDialog.getText(self,'另存配置','显示名称',text=profile_id)
        if not ok or not name:return
        try:
            current=self._profile();profile=OutputProfile(name=name,raster=current.raster,encoding=current.encoding,text=current.text)
            self.project.upsert_output_profile(profile_id,profile,activate=True);self._load_active_profile()
        except Exception as exc:self.validation_label.setText(str(exc))

    def _delete_profile(self):
        if not self.project:return
        profile_id=str(self.profile_combo.currentData() or '')
        _,saved=self.project.get_output_profiles()
        if profile_id not in saved:self.validation_label.setText('内置模板尚未保存到项目，无法删除');return
        try:self.project.delete_output_profile(profile_id);self._load_active_profile()
        except Exception as exc:self.validation_label.setText(str(exc))

    def _source_changed(self, *_):
        kind = self.source_combo.currentData()
        is_font = kind == 'font'
        self.font_combo.setEnabled(is_font); self.characters.setEnabled(is_font)
        for control in (self.alignment_combo, self.threshold_mode, self.threshold, self.red, self.green, self.blue, self.invert_source, self.antialias): control.setEnabled(False)
        self.raster_hint.setText('当前来源已经是 1-bit，不会再次阈值化')
        self.index_mode.setEnabled(is_font)
        if not is_font: self.index_mode.setCurrentIndex(self.index_mode.findData('none'))
        self._validate_source(); self._generate_timer.start()

    def _validate_source(self):
        kind = self.source_combo.currentData()
        error = ''
        if kind == 'selection' and not self.window.canvas.selection: error = '当前没有选区，无法生成选区字模'
        elif kind == 'font' and self.font_combo.count() == 0: error = '项目中没有可用的 Font Pack'
        elif kind == 'scene' and self.project is None: error = '当前不是项目，无法读取 Designer 场景'
        self.validation_label.setText(error)
        self.generate_button.setEnabled(not error)
        return not error

    def _source_bitmaps(self):
        kind = self.source_combo.currentData()
        if kind == 'canvas':
            return [{'name': self.window.path.stem if self.window.path else 'oled_bitmap', 'bitmap': MonoBitmap.from_rows(self.window.document.pixels)}]
        if kind == 'selection':
            x, y, width, height = self.window.canvas.selection
            rows = [row[x:x + width] for row in self.window.document.pixels[y:y + height]]
            return [{'name': 'selection', 'bitmap': MonoBitmap.from_rows(rows)}]
        if kind == 'font':
            pack = FontPack.load(self.project_root / str(self.font_combo.currentData()))
            requested = self.characters.text()
            chars = list(dict.fromkeys(requested)) if requested else sorted(pack.characters(), key=ord)
            specs = []
            for char in chars:
                glyph = pack.glyph(char)
                specs.append({'name': char, 'codepoint': ord(char), 'bitmap': MonoBitmap.from_rows(glyph.pixels), 'bearing_x': glyph.metrics.bearing_x, 'bearing_y': glyph.metrics.bearing_y, 'advance': glyph.metrics.advance})
            return specs
        from bitmap_encoding import bitmap_from_framebuffer
        from render import render_scene
        from scene import init_state, load_scene
        scene = load_scene(self.project.screen_path(self.project.active_screen), project_root=self.project.root)
        rendered = render_scene(scene, init_state(scene))
        return [{'name': self.project.active_screen, 'bitmap': bitmap_from_framebuffer(rendered.framebuffer)}]

    def generate_now(self):
        if not self._validate_source(): return
        try:
            profile = self._profile(); bitmaps = self._source_bitmaps()
            if not bitmaps: raise ValueError('当前来源没有可输出内容')
        except Exception as exc:
            self.validation_label.setText(str(exc)); return
        self._generation_id += 1
        request = (self._generation_id, bitmaps, profile, bitmaps[0]['name'])
        if self._running:
            self._pending = request
            return
        self._start_request(request)

    def _start_request(self, request):
        generation_id, bitmaps, profile, symbol = request
        self._running = True
        task = _GenerationTask(generation_id, bitmaps, profile, symbol)
        task.signals.completed.connect(self._generation_completed)
        task.signals.failed.connect(self._generation_failed)
        self._pool.start(task)

    def _finish_request(self):
        self._running = False
        if self._pending:
            request, self._pending = self._pending, None
            self._start_request(request)

    def _generation_completed(self, generation_id, formatted, items):
        if generation_id == self._generation_id:
            self._last_formatted = formatted; self._last_items = tuple(items); self._trace_index = 0
            text = formatted.preview_text
            if formatted.preview_truncated: text += '\n\n[预览已截断；保存仍会写入完整结果]'
            if not text and formatted.data: text = formatted.data.hex(' ')
            self.output_text.setPlainText(text); self._show_trace()
        self._finish_request()

    def _generation_failed(self, generation_id, message):
        if generation_id == self._generation_id: self.validation_label.setText(message)
        self._finish_request()

    def _show_trace(self):
        if not self._last_items: self.animation_label.setText('尚未生成字模'); return
        encoded = self._last_items[0].encoded
        self._trace_index %= max(1, encoded.byte_count)
        step = encoded.trace_step(self._trace_index)
        points=step.coordinates
        if self.source_combo.currentData()=='selection' and self.window.canvas.selection:
            ox,oy,_,_=self.window.canvas.selection;points=tuple(None if point is None else (point[0]+ox,point[1]+oy) for point in points)
        self.window.canvas.trace_points=points if self.source_combo.currentData() in {'canvas','selection'} else ();self.window.canvas.update()
        coords = ', '.join('补位' if point is None else f'({point[0]},{point[1]})' for point in step.coordinates)
        bit_names = 'bit7 → bit0' if self.bit_order.currentData() == 'msb_first' else 'bit0 → bit7'
        self.animation_label.setText(f'第 {step.index + 1}/{encoded.byte_count} 字节 · {bit_names}\n{coords}\n当前字节：0x{step.value:02X}')

    def previous_step(self): self._trace_index -= 1; self._show_trace()
    def next_step(self): self._trace_index += 1; self._show_trace()

    def toggle_play(self):
        if self._animation_timer.isActive(): self._animation_timer.stop(); self.play_button.setText('播放')
        else: self._speed_changed(); self._animation_timer.start(); self.play_button.setText('暂停')

    def _speed_changed(self, *_): self._animation_timer.setInterval(int(800 / float(self.animation_speed.currentData() or 1)))

    def copy_output(self):
        if self._last_formatted:
            text = self._last_formatted.text or self._last_formatted.data.hex(' ')
            QApplication.clipboard().setText(text)

    def save_output(self):
        if not self._last_formatted: self.generate_now(); return False
        binary = self._profile().text.container == 'binary'
        path = QFileDialog.getSaveFileName(self, '保存字模', str(self.project_root / ('bitmap.bin' if binary else 'bitmap.h')), 'BIN (*.bin)' if binary else 'Header (*.h);;Text (*.txt)')[0]
        if not path: return False
        raw = self._last_formatted.data if binary else self._last_formatted.text.encode('utf-8')
        try:
            atomic_write_bytes(path, raw)
            if self._profile().text.index_mode == 'sidecar' and self._last_formatted.sidecar_text:
                target = Path(path); atomic_write_bytes(target.with_name(target.stem + '_index.h'), self._last_formatted.sidecar_text.encode('utf-8'))
        except OSError as exc:
            QMessageBox.warning(self, '保存字模', str(exc)); return False
        self.validation_label.setText(f'已保存 · SHA-256 {hashlib.sha256(raw).hexdigest()}')
        return True

    def clear_output(self):
        self._animation_timer.stop(); self.play_button.setText('播放'); self.output_text.clear(); self.animation_label.setText('尚未生成字模'); self._last_formatted = None; self._last_items = ();self.window.canvas.trace_points=();self.window.canvas.update()

    def _display_changed(self, *_):
        if not hasattr(self,'output_text'):return
        self.output_text.setFont(QFont(self.output_font.currentFont().family(), self.output_font_size.value()))
        self.preferences.set('pixel_studio.output_font', self.output_font.currentFont().family(), save=False)
        self.preferences.set('pixel_studio.output_font_size', self.output_font_size.value(), save=True)

    def _reset_display(self):
        self.background_color.setText('#000000');self.grid_color.setText('#495028');self.fill_color.setText('#FFFFFF');self.border_color.setText('#FFFF00');self.pixel_size.setValue(10)
        self.output_font_size.setValue(14); self.animation_speed.setCurrentIndex(self.animation_speed.findData(1.0)); self._display_changed()

    def _canvas_display_changed(self, *_):
        fields=(('背景',self.background_color),('线条',self.grid_color),('填充',self.fill_color),('边框',self.border_color))
        invalid=[]
        for label,edit in fields:
            valid=QColor(edit.text()).isValid()
            edit.setStyleSheet('' if valid else 'border: 1px solid #D93F3F;')
            if not valid:invalid.append(label)
        if invalid:
            self.validation_label.setText('颜色格式无效：'+ '、'.join(invalid));return
        canvas=self.window.canvas;canvas.background_color=self.background_color.text();canvas.grid_color=self.grid_color.text();canvas.fill_color=self.fill_color.text();canvas.pixel_border_color=self.border_color.text();canvas.invalidate_base_cache();canvas.update()
        for key,edit in (('canvas_background',self.background_color),('grid_color',self.grid_color),('pixel_fill',self.fill_color),('pixel_border',self.border_color)):
            self.preferences.set('pixel_studio.'+key,edit.text(),save=False)
        self.preferences.save()

    def _pixel_size_changed(self,value):
        self.window.set_zoom(int(value));self.preferences.set('pixel_studio.pixel_size',int(value),save=True)

    def document_changed(self):
        self._validate_source(); self._generate_timer.start()

    def selection_changed(self):
        self._validate_source()
        if self.source_combo.currentData() == 'selection': self._generate_timer.start()
