from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QToolButton, QVBoxLayout, QWidget, QSplitter, QFrame,
)

from font_generator import generate_glyphs
from i18n import DEFAULT_LANGUAGE, Translator
from pixel_studio import PixelDocument, insert_fontpack_text
from font_pack import FontPack
from preferences import PreferencesStore
from runtime_settings import RuntimeSettings
from preference_delta import PreferenceDelta
from system_theme import SystemThemeProvider
from qt_theme import build_stylesheet
from theme_system import get_theme, resolve_theme_name
from ui_controls import StudioButton, StudioToolButton, StudioSelect, StudioNumericInput
QPushButton = StudioButton
QToolButton = StudioToolButton

TOOLS = ('Pencil', 'Eraser', 'Line', 'Rectangle', 'Fill', 'Select')


def _document_pixmap(document: PixelDocument, scale: int = 1) -> QPixmap:
    raw = bytearray(document.width * document.height * 4)
    i = 0
    for row in document.pixels:
        for value in row:
            c = 255 if value else 0
            raw[i:i + 4] = bytes((c, c, c, 255)); i += 4
    image = QImage(bytes(raw), document.width, document.height, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(image).scaled(
        max(1, document.width * scale), max(1, document.height * scale),
        Qt.KeepAspectRatio, Qt.FastTransformation,
    )


class ImageImportDialog(QDialog):
    def __init__(self, path: str | Path, tr: Translator, parent=None):
        super().__init__(parent); self.path = Path(path); self.tr = tr
        self.document = PixelDocument.from_image(self.path)
        self.setWindowTitle(tr('pixel.import.title')); self.resize(620, 420)
        layout = QVBoxLayout(self); form = QFormLayout()
        self.threshold = QSpinBox(); self.threshold.setRange(0,255); self.threshold.setValue(128)
        self.invert = QCheckBox(tr('pixel.import.invert'))
        form.addRow(tr('pixel.import.threshold'), self.threshold); form.addRow('', self.invert); layout.addLayout(form)
        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(240); layout.addWidget(self.preview,1)
        row=QHBoxLayout(); row.addStretch(1); cancel=QPushButton(tr('dialog.cancel')); apply=QPushButton(tr('pixel.import.apply')); apply.setObjectName('PrimaryButton')
        cancel.clicked.connect(self.reject); apply.clicked.connect(self.accept); row.addWidget(cancel); row.addWidget(apply); layout.addLayout(row)
        self.threshold.valueChanged.connect(self._refresh); self.invert.toggled.connect(self._refresh); self._refresh()

    def _refresh(self):
        self.document=PixelDocument.from_image(self.path,threshold=self.threshold.value(),invert=self.invert.isChecked())
        self.preview.setPixmap(_document_pixmap(self.document,max(1,min(8,260//max(1,self.document.height)))))

    def converted_document(self): return self.document


class CanvasResizeDialog(QDialog):
    def __init__(self,document,tr:Translator,parent=None):
        super().__init__(parent);self.tr=tr;self.setWindowTitle(tr('pixel.canvas_size_title'));layout=QVBoxLayout(self);form=QFormLayout();self.width=StudioNumericInput();self.width.setRange(1,4096);self.width.setValue(document.width);self.height=StudioNumericInput();self.height.setRange(1,4096);self.height.setValue(document.height);self.anchor=StudioSelect()
        anchors=(('pixel.anchor.top_left','top-left'),('pixel.anchor.top','top'),('pixel.anchor.top_right','top-right'),('pixel.anchor.left','left'),('pixel.anchor.center','center'),('pixel.anchor.right','right'),('pixel.anchor.bottom_left','bottom-left'),('pixel.anchor.bottom','bottom'),('pixel.anchor.bottom_right','bottom-right'))
        for key,data in anchors:self.anchor.addItem(tr(key),data)
        self.anchor.setCurrentIndex(self.anchor.findData('center'));form.addRow(tr('pixel.width'),self.width);form.addRow(tr('pixel.height'),self.height);form.addRow(tr('pixel.anchor'),self.anchor);layout.addLayout(form);row=QHBoxLayout();row.addStretch(1);cancel=StudioButton(tr('dialog.cancel'));apply=StudioButton(tr('pixel.resize'));apply.setObjectName('PrimaryButton');cancel.clicked.connect(self.reject);apply.clicked.connect(self.accept);row.addWidget(cancel);row.addWidget(apply);layout.addLayout(row)
    def values(self):return self.width.value(),self.height.value(),self.anchor.currentData()


class TextInsertDialog(QDialog):
    def __init__(self,project_root: str|Path,document: PixelDocument,tr:Translator,parent=None):
        super().__init__(parent);self.tr=tr;self.project_root=Path(project_root).resolve();self.setWindowTitle(tr('pixel.insert_title'));layout=QVBoxLayout(self);form=QFormLayout()
        self.text=QLineEdit('TEXT');self.font=StudioSelect();self.x=StudioNumericInput();self.y=StudioNumericInput();self.tracking=StudioNumericInput()
        self.x.setRange(0,max(0,document.width-1));self.y.setRange(0,max(0,document.height-1));self.tracking.setRange(-8,32);self.tracking.setValue(0)
        for manifest in sorted(self.project_root.rglob('fontpack.json')):
            try:
                pack=FontPack.load(manifest.parent);rel=manifest.parent.relative_to(self.project_root).as_posix();self.font.addItem(f'{pack.name} · {pack.cell[0]}×{pack.cell[1]}',rel)
            except Exception:continue
        form.addRow(tr('pixel.text'),self.text);form.addRow(tr('pixel.font_pack'),self.font);form.addRow('X',self.x);form.addRow('Y',self.y);form.addRow(tr('pixel.tracking'),self.tracking);layout.addLayout(form)
        self.hint=QLabel(tr('pixel.font_hint'));self.hint.setObjectName('Muted');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        row=QHBoxLayout();row.addStretch(1);cancel=StudioButton(tr('dialog.cancel'));apply=StudioButton(tr('pixel.action.insert_bitmap_text'));apply.setObjectName('PrimaryButton');cancel.clicked.connect(self.reject);apply.clicked.connect(self.accept);row.addWidget(cancel);row.addWidget(apply);layout.addLayout(row)
        if self.font.count()==0:apply.setEnabled(False);self.hint.setText(tr('pixel.font_missing'))
    def values(self):return self.text.text(),self.font.currentData(),self.x.value(),self.y.value(),self.tracking.value()


class PixelCanvas(QWidget):
    documentChanged = Signal()
    cursorChanged = Signal(int, int)
    selectionChanged = Signal(object)
    zoomChanged = Signal(int)

    def __init__(self, document: PixelDocument, parent=None):
        super().__init__(parent)
        self.document=document; self.zoom=20; self.tool='Pencil'; self.start=None; self.selection=None
        self._selection_drag_origin=None; self._selection_preview=None
        self._stroke_last=None; self._stroke_value=1; self._stroke_button=None
        self._pan_active=False; self._pan_origin=None; self._pan_scroll=(0,0); self._space_down=False
        self.show_grid=True; self.stroke_interpolation=True; self.theme_name='monooled-light'
        self.wheel_action='zoom'; self.middle_pan_enabled=True; self.space_pan_enabled=True; self.brush_size=1
        self.setMouseTracking(True); self.setFocusPolicy(Qt.StrongFocus); self._sync_size()

    def _sync_size(self): self.setFixedSize(self.document.width*self.zoom+1,self.document.height*self.zoom+1)
    def set_document(self,document): self.document=document; self.selection=None; self._sync_size(); self.update()

    def _scroll_area(self):
        parent=self.parentWidget()
        while parent is not None:
            if isinstance(parent,QScrollArea): return parent
            parent=parent.parentWidget()
        return None

    def paintEvent(self,event):
        t=get_theme(self.theme_name); painter=QPainter(self); painter.fillRect(self.rect(),QColor('#111113')); z=self.zoom
        painter.setPen(Qt.NoPen); painter.setBrush(QColor('#FFFFFF'))
        for y,row in enumerate(self.document.pixels):
            for x,value in enumerate(row):
                if value:painter.drawRect(x*z,y*z,z,z)
        if self.show_grid and z>=8:
            painter.setPen(QPen(QColor(t['canvas.grid']),1))
            for x in range(self.document.width+1):painter.drawLine(x*z,0,x*z,self.document.height*z)
            for y in range(self.document.height+1):painter.drawLine(0,y*z,self.document.width*z,y*z)
        if self.selection:
            x,y,w,h=self.selection
            if self._selection_preview:x+=self._selection_preview[0]; y+=self._selection_preview[1]
            painter.setPen(QPen(QColor(t['canvas.selection']),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush); painter.drawRect(x*z,y*z,w*z,h*z)
        painter.end()

    def _pixel(self,event): return int(event.position().x()//self.zoom),int(event.position().y()//self.zoom)
    def _in_bounds(self,x,y): return 0<=x<self.document.width and 0<=y<self.document.height

    def _begin_pan(self,event):
        area=self._scroll_area()
        if not area:return False
        self._pan_active=True; self._pan_origin=event.globalPosition().toPoint(); self._pan_scroll=(area.horizontalScrollBar().value(),area.verticalScrollBar().value()); self.setCursor(Qt.ClosedHandCursor); return True

    def _pan_move(self,event):
        area=self._scroll_area()
        if not area or not self._pan_origin:return
        now=event.globalPosition().toPoint(); delta=now-self._pan_origin
        area.horizontalScrollBar().setValue(self._pan_scroll[0]-delta.x()); area.verticalScrollBar().setValue(self._pan_scroll[1]-delta.y())

    def mousePressEvent(self,event):
        if event.button()==Qt.MiddleButton and self.middle_pan_enabled:
            self._begin_pan(event); return
        if event.button()==Qt.LeftButton and self._space_down and self.space_pan_enabled:
            self._begin_pan(event); return
        if event.button() not in (Qt.LeftButton,Qt.RightButton):return
        x,y=self._pixel(event)
        if not self._in_bounds(x,y):return
        self.setFocus(Qt.MouseFocusReason); self.start=(x,y); self._stroke_button=event.button()
        if self.tool=='Select':
            if event.button()!=Qt.LeftButton:self.start=None; return
            if self.selection:
                sx,sy,sw,sh=self.selection
                if sx<=x<sx+sw and sy<=y<sy+sh:
                    self._selection_drag_origin=(x,y); self._selection_preview=(0,0); return
            self._selection_drag_origin=None; self._selection_preview=None; return
        # OLED semantics: left sets pixels, right clears them. Eraser left is kept
        # as an optional traditional tool, but Pencil never requires switching.
        value=0 if event.button()==Qt.RightButton or self.tool=='Eraser' else 1
        self._stroke_value=value; self._stroke_last=(x,y); self.document.begin_gesture()
        if self.tool in ('Pencil','Eraser'):
            self.document.brush(x,y,value,size=self.brush_size); self.documentChanged.emit(); self.update()
        elif self.tool=='Fill':
            self.document.flood_fill(x,y,value); self.document.end_gesture(); self.start=None; self._stroke_last=None; self.documentChanged.emit(); self.update()

    def mouseMoveEvent(self,event):
        x,y=self._pixel(event); self.cursorChanged.emit(x,y)
        if self._pan_active:
            self._pan_move(event); return
        if self.tool=='Select' and self._selection_drag_origin and (event.buttons()&Qt.LeftButton):
            ox,oy=self._selection_drag_origin; self._selection_preview=(x-ox,y-oy); self.update(); return
        buttons=event.buttons()
        if not (buttons&(Qt.LeftButton|Qt.RightButton)) or self.tool not in ('Pencil','Eraser') or not self._in_bounds(x,y):return
        last=self._stroke_last or (x,y)
        if self.stroke_interpolation:self.document.brush_segment(last[0],last[1],x,y,self._stroke_value,size=self.brush_size)
        else:self.document.brush(x,y,self._stroke_value,size=self.brush_size)
        self._stroke_last=(x,y); self.documentChanged.emit(); self.update()

    def mouseReleaseEvent(self,event):
        if self._pan_active and event.button() in (Qt.MiddleButton,Qt.LeftButton):
            self._pan_active=False; self._pan_origin=None; self.unsetCursor(); return
        if event.button() not in (Qt.LeftButton,Qt.RightButton) or not self.start:return
        x0,y0=self.start; x1,y1=self._pixel(event); self.start=None
        x1=max(0,min(self.document.width-1,x1)); y1=max(0,min(self.document.height-1,y1))
        if self.tool=='Select':
            if event.button()!=Qt.LeftButton:return
            if self._selection_drag_origin and self.selection:
                dx,dy=self._selection_preview or (0,0); sx,sy,sw,sh=self.selection
                nx=max(0,min(self.document.width-sw,sx+dx)); ny=max(0,min(self.document.height-sh,sy+dy)); adx,ady=nx-sx,ny-sy
                if adx or ady:self.document.move_region(sx,sy,sw,sh,adx,ady); self.selection=(nx,ny,sw,sh); self.documentChanged.emit()
                self._selection_drag_origin=None; self._selection_preview=None; self.selectionChanged.emit(self.selection); self.update(); return
            xa,xb=sorted((x0,x1)); ya,yb=sorted((y0,y1)); self.selection=(xa,ya,xb-xa+1,yb-ya+1); self.selectionChanged.emit(self.selection); self.update(); return
        value=0 if event.button()==Qt.RightButton or self.tool=='Eraser' else 1
        if self.tool=='Line':self.document.line(x0,y0,x1,y1,value=value)
        elif self.tool=='Rectangle':self.document.rectangle(x0,y0,x1,y1,value=value)
        elif self.tool in ('Pencil','Eraser'):
            self.document.end_gesture(); self._stroke_last=None; self.documentChanged.emit(); self.update(); return
        else:
            self.document._gesture_before=None; return
        self.document.end_gesture(); self._stroke_last=None; self.documentChanged.emit(); self.update()

    def wheelEvent(self,event):
        if self.wheel_action != 'zoom':
            event.ignore(); return
        delta=event.angleDelta().y()
        if not delta:return
        step=2 if delta>0 else -2; self.zoom=max(4,min(40,self.zoom+step)); self._sync_size(); self.zoomChanged.emit(self.zoom); self.update(); event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Space and not event.isAutoRepeat():self._space_down=bool(self.space_pan_enabled); event.accept(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key_Space and not event.isAutoRepeat():self._space_down=False; event.accept(); return
        super().keyReleaseEvent(event)

    def leaveEvent(self,event): self.cursorChanged.emit(-1,-1); super().leaveEvent(event)


class PixelStudioWindow(QMainWindow):
    assetSaved=Signal(str)

    def __init__(self,path: str|Path|None=None,language: str=DEFAULT_LANGUAGE,parent=None,preferences: PreferencesStore|None=None,project_root: str|Path|None=None):
        super().__init__(parent); self.preferences=preferences or PreferencesStore.load(); self.tr=Translator(language or self.preferences.get('language',DEFAULT_LANGUAGE)); self.path=Path(path).resolve() if path else None; self.project_root=Path(project_root).resolve() if project_root else (self.path.parent if self.path else Path.cwd()).resolve(); self.clipboard=None
        if parent is not None:self.setWindowFlags(Qt.Widget)
        self.document_id='asset:'+str(self.path) if self.path else f'pixel:new:{id(self)}'; self.title=self.path.name if self.path else self.tr('pixel.title')
        self.document=PixelDocument.from_image(self.path) if self.path else PixelDocument(32,16)
        self.document.set_max_undo(int(self.preferences.get('performance.undo_history',200)))
        self.setWindowTitle(f"MonoOLED Studio · {self.tr('pixel.title')}"); self.resize(1180,780)
        self._runtime_settings=None; self._resolved_theme=None; self.system_theme=SystemThemeProvider(self)
        self._build_ui(); self.apply_preferences(initial=True); self.refresh_preview()

    def _build_ui(self):
        tr=self.tr; root=QWidget(); root.setObjectName('AppRoot'); self.setCentralWidget(root); layout=QVBoxLayout(root); layout.setContentsMargins(6,6,6,6); layout.setSpacing(6)
        header=QHBoxLayout(); self.title_label=QLabel(tr('pixel.title')); self.title_label.setObjectName('PanelTitle'); header.addWidget(self.title_label); header.addStretch(1)
        self.undo_btn=QPushButton(tr('action.undo')); self.undo_btn.setProperty('trKey','action.undo'); self.undo_btn.clicked.connect(self.undo); self.redo_btn=QPushButton(tr('action.redo')); self.redo_btn.setProperty('trKey','action.redo'); self.redo_btn.clicked.connect(self.redo); header.addWidget(self.undo_btn); header.addWidget(self.redo_btn)
        header.addWidget(QLabel(tr('pixel.zoom'))); self.zoom_combo=StudioSelect(); self.zoom_combo.addItem('Fit','fit'); [self.zoom_combo.addItem(f'{z}×',z) for z in (4,6,8,10,12,16,20,24,32,40)]; self.zoom_combo.setCurrentText('Fit'); self._zoom_mode='fit'; self.zoom_combo.currentIndexChanged.connect(self._zoom_control_changed); header.addWidget(self.zoom_combo)
        self.save_btn=QPushButton(tr('pixel.action.save')); self.save_btn.setProperty('trKey','pixel.action.save'); self.save_btn.setObjectName('PrimaryButton'); self.save_btn.clicked.connect(self.save_png); header.addWidget(self.save_btn); layout.addLayout(header)

        self.workspace_splitter = QSplitter(Qt.Horizontal); self.workspace_splitter.setChildrenCollapsible(True)
        self.tool_rail=QWidget(); self.tool_rail.setObjectName('ToolRail'); rail=QVBoxLayout(self.tool_rail); rail.setContentsMargins(8,8,8,8); rail.setSpacing(5); self.tool_buttons={}
        symbols={'Pencil':'✎','Eraser':'⌫','Line':'╱','Rectangle':'□','Fill':'▣','Select':'↖'}
        for name in TOOLS:
            b=QToolButton(); b.setObjectName('ToolRailButton'); b.setText(symbols[name]); b.setToolTip(tr(f'pixel.tool.{name}')); b.setCheckable(True); b.clicked.connect(lambda _=False,n=name:self.set_tool(n)); rail.addWidget(b); self.tool_buttons[name]=b
        self.tool_buttons['Pencil'].setChecked(True); rail.addStretch(1); self.workspace_splitter.addWidget(self.tool_rail)
        self._tool_shortcuts={}
        for command_id,tool in (('pixel.pencil','Pencil'),('pixel.select','Select'),('pixel.fill','Fill')):
            shortcut=QShortcut(QKeySequence(),self); shortcut.activated.connect(lambda t=tool:self.set_tool(t)); self._tool_shortcuts[command_id]=shortcut

        canvas_frame=QFrame(); canvas_frame.setObjectName('CanvasWorkspace'); center=QVBoxLayout(canvas_frame); center.setContentsMargins(4,4,4,4); center.setSpacing(4)
        self.canvas=PixelCanvas(self.document); self.canvas_scroll=QScrollArea(); self.canvas_scroll.setWidget(self.canvas); self.canvas_scroll.setWidgetResizable(False); self.canvas_scroll.setFrameShape(QFrame.NoFrame); center.addWidget(self.canvas_scroll,1); self.workspace_splitter.addWidget(canvas_frame)

        # Flat context inspector: no Selection/Export tabs and no card soup.
        self.inspector_scroll=QScrollArea(); self.inspector_scroll.setWidgetResizable(True); self.inspector_scroll.setMinimumWidth(265); inspector=QWidget(); inspector.setObjectName('InspectorRoot'); il=QVBoxLayout(inspector); il.setContentsMargins(10,10,10,10); il.setSpacing(7)
        self.section_labels=[]
        def section(key, fallback=None):
            text=tr(key) if key else str(fallback or '')
            label=QLabel(text); label.setObjectName('InspectorSection'); label.setProperty('trKey',key or ''); il.addWidget(label); self.section_labels.append(label)
        section('pixel.preview'); self.preview=QLabel(); self.preview.setMinimumSize(220,110); self.preview.setAlignment(Qt.AlignCenter); il.addWidget(self.preview); self.info=QLabel(); self.info.setObjectName('Muted'); il.addWidget(self.info)
        section('pixel.tool.Select'); self.selection_info=QLabel('—'); self.selection_info.setObjectName('Muted'); self.selection_info.setWordWrap(True); il.addWidget(self.selection_info)
        for key,fn in [('pixel.action.copy',self.copy_selection),('pixel.action.cut',self.cut_selection),('pixel.action.paste',self.paste_selection)]:b=QPushButton(tr(key) if '.' in key else key); b.setProperty('trKey',key if '.' in key else ''); b.clicked.connect(fn); il.addWidget(b)
        section('pixel.section.text_font'); self.insert_text_btn=QPushButton(tr('pixel.action.insert_bitmap_text')); self.insert_text_btn.setProperty('trKey','pixel.action.insert_bitmap_text'); self.insert_text_btn.clicked.connect(self.insert_bitmap_text); il.addWidget(self.insert_text_btn)
        section('pixel.section.transform')
        for key,fn in [('pixel.action.invert',self.invert),('pixel.action.flip_h',self.flip_h),('pixel.action.flip_v',self.flip_v),('pixel.action.canvas_size',self.resize_canvas),('pixel.action.rotate90',self.rotate90),('pixel.action.rotate180',self.rotate180),('pixel.action.rotate270',self.rotate270),('pixel.action.crop_selection',self.crop_selection),('pixel.action.clear',self.clear)]:b=QPushButton(tr(key) if '.' in key else key); b.setProperty('trKey',key if '.' in key else ''); b.clicked.connect(fn); il.addWidget(b)
        section('pixel.tab.export')
        for key,fn in [('pixel.action.open',self.open_image),('pixel.action.save',self.save_png),('pixel.action.export_bin',self.save_bin),('pixel.action.export_c',self.save_c_header),('pixel.action.font',self.font_generator)]:b=QPushButton(tr(key) if '.' in key else key); b.setProperty('trKey',key if '.' in key else ''); b.clicked.connect(fn); il.addWidget(b)
        il.addStretch(1); self.inspector_scroll.setWidget(inspector); self.workspace_splitter.addWidget(self.inspector_scroll); self.workspace_splitter.setSizes([56,900,280]); layout.addWidget(self.workspace_splitter,1)
        self.pixel_status=QLabel(self.tr('font.status.pixel')); self.pixel_status.setObjectName('Muted'); self.statusBar().addWidget(self.pixel_status,1)
        self.input_hint=QLabel(self.tr('pixel.input_hint')); self.input_hint.setObjectName('Muted'); self.statusBar().addPermanentWidget(self.input_hint)
        self.canvas.documentChanged.connect(self._document_changed); self.canvas.cursorChanged.connect(self._cursor_changed); self.canvas.selectionChanged.connect(lambda _v:self.refresh_preview()); self.canvas.zoomChanged.connect(self._canvas_zoom_changed)
        self.canvas_scroll.viewport().installEventFilter(self)

    def _host_theme(self,runtime):
        host=self.window()
        inherited=getattr(host,'_resolved_theme',None)
        if inherited:return inherited
        return resolve_theme_name(runtime.color_theme,runtime.theme_mode,system_dark=self.system_theme.is_dark())

    def apply_runtime_delta(self,delta):
        runtime=delta.after
        theme=self._host_theme(runtime)
        theme_changed=theme!=self._resolved_theme
        self._runtime_settings=runtime; self._resolved_theme=theme
        if delta.language_changed and runtime.language!=self.tr.language:
            self.tr.set_language(runtime.language); self.retranslate_ui()
        if delta.appearance_changed or theme_changed:
            # Embedded editors inherit the application stylesheet. Only a real
            # top-level Pixel window owns a local stylesheet.
            if self.parentWidget() is None:self.setStyleSheet(build_stylesheet(theme,runtime.density,ui_scale=runtime.ui_scale))
            self.canvas.theme_name=theme; self.canvas.update()
        if delta.pixel_changed or delta.performance_changed:
            self.canvas.show_grid=runtime.pixel_grid; self.canvas.stroke_interpolation=runtime.stroke_interpolation; self.canvas.wheel_action=runtime.wheel_action; self.canvas.middle_pan_enabled=runtime.middle_pan; self.canvas.space_pan_enabled=runtime.space_pan; self.canvas.brush_size=runtime.brush_size
            self.document.set_max_undo(runtime.undo_history); self.preview.setVisible(runtime.actual_preview)
            self.canvas.update(); self.refresh_preview()
        if delta.shortcuts_changed:
            for command_id,shortcut in self._tool_shortcuts.items():shortcut.setKey(QKeySequence(runtime.shortcuts.get(command_id,'')))

    def apply_preferences(self,initial=False):
        runtime=RuntimeSettings.from_preferences(self.preferences)
        previous=self._runtime_settings
        delta=(PreferenceDelta(previous,runtime,frozenset({'language','theme','metrics','pixel','performance','shortcuts'})) if previous is None else PreferenceDelta.between(previous,runtime))
        self.apply_runtime_delta(delta)
        if initial:
            if runtime.language!=self.tr.language:self.tr.set_language(runtime.language)
            self.retranslate_ui(); self.refresh_preview()

    def retranslate_ui(self):
        self.setWindowTitle(f"MonoOLED Studio · {self.tr('pixel.title')}"); self.title_label.setText(self.tr('pixel.title'))
        for button in self.findChildren(QPushButton):
            key=button.property('trKey')
            if key:
                try:button.setText(self.tr(str(key)))
                except KeyError:pass
        for name,button in self.tool_buttons.items():button.setToolTip(self.tr(f'pixel.tool.{name}'))
        for label in getattr(self,'section_labels',[]):
            key=label.property('trKey')
            if key:
                try:label.setText(self.tr(str(key)))
                except KeyError:pass
        self.input_hint.setText(self.tr('pixel.input_hint'))

    def copy_selection(self):
        if self.canvas.selection:x,y,w,h=self.canvas.selection; self.clipboard=self.document.copy_region(x,y,w,h)
    def cut_selection(self):
        if not self.canvas.selection:return
        self.copy_selection(); x,y,w,h=self.canvas.selection; self.document._snapshot()
        for yy in range(y,y+h):
            for xx in range(x,x+w):self.document._set_raw(xx,yy,0)
        self.canvas.update(); self.refresh_preview()
    def paste_selection(self):
        if not self.clipboard:return
        x,y=self.canvas.selection[:2] if self.canvas.selection else (0,0); self.document.paste_region(x,y,self.clipboard); self.canvas.update(); self.refresh_preview()
    def font_generator(self):
        chars,ok=QInputDialog.getText(self,self.tr('pixel.action.font'),self.tr('pixel.font.characters'))
        if not ok or not chars:return
        output=QFileDialog.getExistingDirectory(self,self.tr('pixel.font.output'))
        if not output:return
        generate_glyphs(chars,output_dir=output,cell=(12,16)); QMessageBox.information(self,self.tr('pixel.action.font'),self.tr('pixel.font.done',count=len(dict.fromkeys(chars))))
    def set_tool(self,name):
        self.canvas.tool=name
        for n,b in self.tool_buttons.items():b.setChecked(n==name)
    def _fit_zoom(self):
        vp=self.canvas_scroll.viewport().size(); return max(1,min(40,int(min(max(1,vp.width()-12)/max(1,self.document.width),max(1,vp.height()-12)/max(1,self.document.height)))))
    def _apply_fit_zoom(self):
        if getattr(self,'_zoom_mode','manual')=='fit': self.set_zoom(self._fit_zoom(),from_control=False)
    def _zoom_control_changed(self,_index):
        data=self.zoom_combo.currentData(); self._zoom_mode='fit' if data=='fit' else 'manual'; self.set_zoom(self._fit_zoom() if data=='fit' else int(data),from_control=False)
    def set_zoom(self,value,from_control=True):
        self.canvas.zoom=max(1,min(40,int(value))); self.canvas._sync_size(); self.canvas.update()
        if from_control:self._zoom_mode='manual'
    def _canvas_zoom_changed(self,value):
        self._zoom_mode='manual'; text=f'{value}×'; idx=self.zoom_combo.findText(text)
        if idx>=0:self.zoom_combo.setCurrentIndex(idx)
    def eventFilter(self,obj,event):
        from PySide6.QtCore import QEvent
        if obj is self.canvas_scroll.viewport() and event.type()==QEvent.Resize:self._apply_fit_zoom()
        return super().eventFilter(obj,event)
    def _pick(self,save=False,filter='PNG (*.png)'):
        fn=QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName; return fn(self,self.tr('pixel.title'),str(self.path or Path.cwd()),filter)[0]
    def open_image(self):
        path=self._pick()
        if not path:return
        try:
            dialog=ImageImportDialog(path,self.tr,self)
        except ValueError as exc:
            QMessageBox.warning(self,self.tr('pixel.import.title'),str(exc)); return
        if dialog.exec()!=QDialog.Accepted:return
        self.path=Path(path); self.document=dialog.converted_document(); self.document.set_max_undo(int(self.preferences.get('performance.undo_history',200))); self.canvas.set_document(self.document); self.refresh_preview()
    def _document_changed(self):
        self.refresh_preview(); self.title=(self.path.name if self.path else self.tr('pixel.title'))+(' ●' if self.document.dirty else '')
        parent=self.parentWidget()
        while parent is not None:
            if hasattr(parent,'indexOf') and hasattr(parent,'setTabText'):
                i=parent.indexOf(self)
                if i>=0:parent.setTabText(i,self.title);break
            parent=parent.parentWidget()

    def save(self): return self.save_png()

    def save_png(self):
        path=str(self.path) if self.path else self._pick(save=True)
        if not path:return
        self.path=self.document.save_png(path); self.document_id='asset:'+str(self.path.resolve()); self.title=self.path.name; self.assetSaved.emit(str(self.path)); self.refresh_preview(); self._document_changed()
    def save_bin(self):
        path=self._pick(save=True,filter='BIN (*.bin)')
        if path:self.document.save_bin(path)
    def save_c_header(self):
        path=self._pick(save=True,filter='C Header (*.h)')
        if not path:return
        default=(self.path.stem if self.path else 'oled_bitmap').replace('-','_').replace(' ','_'); symbol,ok=QInputDialog.getText(self,self.tr('pixel.action.export_c'),self.tr('pixel.symbol'),text=default)
        if ok and symbol:self.document.save_c_header(path,symbol)
    def undo(self):
        if self.document.undo():self.canvas.update(); self.refresh_preview()
    def redo(self):
        if self.document.redo():self.canvas.update(); self.refresh_preview()
    def invert(self):self.document.invert(); self.canvas.update(); self.refresh_preview()
    def flip_h(self):self.document.flip_horizontal(); self.canvas.update(); self.refresh_preview()
    def flip_v(self):self.document.flip_vertical(); self.canvas.update(); self.refresh_preview()
    def clear(self):self.document.clear(); self.canvas.update(); self.refresh_preview()
    def resize_canvas(self):
        dialog=CanvasResizeDialog(self.document,self.tr,self)
        if dialog.exec()!=QDialog.Accepted:return
        w,h,anchor=dialog.values();self.document.resize_canvas(w,h,anchor=anchor);self.canvas.set_document(self.document);self._apply_fit_zoom();self.refresh_preview()
    def rotate90(self):self.document.rotate90();self.canvas.set_document(self.document);self.refresh_preview()
    def rotate180(self):self.document.rotate180();self.canvas.set_document(self.document);self.refresh_preview()
    def rotate270(self):self.document.rotate270();self.canvas.set_document(self.document);self.refresh_preview()
    def crop_selection(self):
        if not self.canvas.selection:return
        self.document.crop(*self.canvas.selection);self.canvas.selection=None;self.canvas.set_document(self.document);self.refresh_preview()

    def insert_bitmap_text(self):
        dialog=TextInsertDialog(self.project_root,self.document,self.tr,self)
        if dialog.exec()!=QDialog.Accepted:return
        text,font_id,x,y,tracking=dialog.values()
        if not text or not font_id:return
        try:
            pack=FontPack.load(self.project_root/str(font_id));w,h=insert_fontpack_text(self.document,pack,text,x,y,tracking=tracking)
        except Exception as exc:QMessageBox.warning(self,self.tr('pixel.insert_title'),str(exc));return
        self.canvas.selection=(x,y,w,h) if w and h else None;self.canvas.update();self._document_changed();self.refresh_preview()

    def _cursor_changed(self,x,y):self.pixel_status.setText(self.tr('font.status.pixel') if x<0 else self.tr('pixel.cursor',x=x,y=y))
    def layout_violations(self):
        issues=[]; widgets=[self.zoom_combo,*self.tool_buttons.values(),self.canvas_scroll,self.inspector_scroll,self.preview]
        for widget in widgets:
            if not widget.isVisible():continue
            if widget.width()<=0 or widget.height()<=0:issues.append('zero-size:'+widget.__class__.__name__); continue
            visible=widget.visibleRegion().boundingRect()
            if visible.width()<max(8,widget.width()//2) or visible.height()<max(8,widget.height()//2):issues.append('clipped:'+widget.__class__.__name__)
        return issues
    def refresh_preview(self):
        if getattr(self,'_zoom_mode','manual')=='fit':self._apply_fit_zoom()
        if bool(self.preferences.get('pixel_studio.actual_preview',True)):self.preview.setPixmap(_document_pixmap(self.document,2))
        else:self.preview.clear()
        self.info.setText(f'{self.document.width} × {self.document.height} · {len(self.document.to_vlsb())} B VLSB')
        if self.canvas.selection:x,y,w,h=self.canvas.selection; self.selection_info.setText(self.tr('pixel.selection',x=x,y=y,w=w,h=h))
        else:self.selection_info.setText(self.tr('pixel.selection.none'))
