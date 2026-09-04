from __future__ import annotations

from pathlib import Path
from PIL import Image

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QKeySequence, QShortcut
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
from qt_theme import build_adaptive_stylesheet, build_theme_palette
from theme_system import get_theme, resolve_theme_name
from ui_metrics import build_ui_metrics
from ui_controls import StudioButton, StudioToolButton, StudioSelect, StudioNumericInput
from micro_signature import pixel_hover_spec
from pixel_hover_performance import hover_damage_rects
from qt_canvas import adaptive_grid_stride
from output_workbench_qt import OutputWorkbench
from bitmap_raster import rasterize_image
from output_profiles import RasterProfile
QPushButton = StudioButton
QToolButton = StudioToolButton

TOOLS = ('Pencil', 'Eraser', 'Line', 'Rectangle', 'Fill', 'Select')


def _tool_icon(name: str, color: str, size: int = 16) -> QIcon:
    # Deterministic monochrome line icon; avoids platform font/emoji glyph drift.
    size=max(12,int(size)); scale=size/16.0
    pixmap=QPixmap(size,size); pixmap.fill(Qt.transparent)
    painter=QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing,True); painter.scale(scale,scale)
    pen=QPen(QColor(color)); pen.setWidthF(1.5); pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin); painter.setPen(pen); painter.setBrush(Qt.NoBrush)
    if name=='Pencil':
        painter.drawLine(3,12,12,4); painter.drawLine(3,14,6,13); painter.drawLine(10,5,12,7)
    elif name=='Eraser':
        path=QPainterPath(); path.moveTo(3,10); path.lineTo(8.8,4.2); path.lineTo(13,8.4); path.lineTo(7.4,14); path.lineTo(4.6,14); path.closeSubpath(); painter.drawPath(path); painter.drawLine(7,14,14,14)
    elif name=='Line':
        painter.drawLine(3,13,13,3)
    elif name=='Rectangle':
        painter.drawRect(3,3,10,10)
    elif name=='Fill':
        path=QPainterPath(); path.moveTo(4,7); path.lineTo(8.2,2.8); path.lineTo(13.2,7.8); path.lineTo(8.8,12.2); path.closeSubpath(); painter.drawPath(path); painter.drawLine(5,8,12,8); painter.drawLine(11,13,14,13)
    elif name=='Select':
        path=QPainterPath(); path.moveTo(3,2.5); path.lineTo(12.4,8.2); path.lineTo(8.2,9.2); path.lineTo(10.7,13.4); path.lineTo(8.8,14.4); path.lineTo(6.5,10.2); path.lineTo(3,13); path.closeSubpath(); painter.drawPath(path)
    painter.end(); return QIcon(pixmap)


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
        self.threshold_mode=StudioSelect(); self.threshold_mode.addItem('亮度阈值','luma'); self.threshold_mode.addItem('RGB 全部达到阈值','rgb_all')
        self.threshold = QSpinBox(); self.threshold.setRange(0,255); self.threshold.setValue(128)
        self.red=QSpinBox(); self.green=QSpinBox(); self.blue=QSpinBox()
        for control in (self.red,self.green,self.blue):control.setRange(0,255);control.setValue(255)
        self.invert = QCheckBox(tr('pixel.import.invert'))
        form.addRow('阈值模式',self.threshold_mode);form.addRow(tr('pixel.import.threshold'), self.threshold);form.addRow('R',self.red);form.addRow('G',self.green);form.addRow('B',self.blue); form.addRow('', self.invert); layout.addLayout(form)
        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignCenter); self.preview.setMinimumHeight(240); layout.addWidget(self.preview,1)
        row=QHBoxLayout(); row.addStretch(1); cancel=QPushButton(tr('dialog.cancel')); apply=QPushButton(tr('pixel.import.apply')); apply.setObjectName('PrimaryButton')
        cancel.clicked.connect(self.reject); apply.clicked.connect(self.accept); row.addWidget(cancel); row.addWidget(apply); layout.addLayout(row)
        for control in (self.threshold_mode,self.threshold,self.red,self.green,self.blue,self.invert):
            signal=getattr(control,'currentIndexChanged',None) or getattr(control,'valueChanged',None) or getattr(control,'toggled',None);signal.connect(self._refresh)
        self.threshold_mode.currentIndexChanged.connect(self._sync_threshold_controls);self._sync_threshold_controls();self._refresh()

    def _sync_threshold_controls(self,*_):
        rgb=self.threshold_mode.currentData()=='rgb_all';self.threshold.setEnabled(not rgb)
        for control in (self.red,self.green,self.blue):control.setEnabled(rgb)

    def _refresh(self):
        with Image.open(self.path) as source:
            profile=RasterProfile(threshold_mode=self.threshold_mode.currentData(),luma_threshold=self.threshold.value(),red_threshold=self.red.value(),green_threshold=self.green.value(),blue_threshold=self.blue.value(),invert_source=self.invert.isChecked())
            bitmap=rasterize_image(source,profile)
        self.document=PixelDocument(bitmap.width,bitmap.height,[list(row) for row in bitmap.rows])
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
            except (OSError, ValueError, KeyError):continue
        form.addRow(tr('pixel.text'),self.text);form.addRow(tr('pixel.font_pack'),self.font);form.addRow('X',self.x);form.addRow('Y',self.y);form.addRow(tr('pixel.tracking'),self.tracking);layout.addLayout(form)
        self.hint=QLabel(tr('pixel.font_hint'));self.hint.setObjectName('Muted');self.hint.setWordWrap(True);layout.addWidget(self.hint)
        row=QHBoxLayout();row.addStretch(1);cancel=StudioButton(tr('dialog.cancel'));apply=StudioButton(tr('pixel.action.insert_bitmap_text'));apply.setObjectName('PrimaryButton');cancel.clicked.connect(self.reject);apply.clicked.connect(self.accept);row.addWidget(cancel);row.addWidget(apply);layout.addLayout(row)
        if self.font.count()==0:apply.setEnabled(False);self.hint.setText(tr('pixel.font_missing'))
    def values(self):return self.text.text(),self.font.currentData(),self.x.value(),self.y.value(),self.tracking.value()


PIXEL_OFF_COLOR = '#000000'
PIXEL_ON_COLOR = '#FFFFFF'


def _line_preview_points(x0: int, y0: int, x1: int, y1: int):
    dx=abs(x1-x0); sx=1 if x0<x1 else -1; dy=-abs(y1-y0); sy=1 if y0<y1 else -1; err=dx+dy
    while True:
        yield x0,y0
        if x0==x1 and y0==y1: break
        e2=2*err
        if e2>=dy: err+=dy; x0+=sx
        if e2<=dx: err+=dx; y0+=sy


def _rectangle_preview_points(x0: int, y0: int, x1: int, y1: int):
    xa,xb=sorted((x0,x1)); ya,yb=sorted((y0,y1))
    for x in range(xa,xb+1):
        yield x,ya
        if yb != ya: yield x,yb
    for y in range(ya+1,yb):
        yield xa,y
        if xb != xa: yield xb,y


class PixelCanvas(QWidget):
    documentChanged = Signal()
    pixelsChanged = Signal(object)
    cursorChanged = Signal(int, int)
    selectionChanged = Signal(object)
    zoomChanged = Signal(int)

    def __init__(self, document: PixelDocument, parent=None):
        super().__init__(parent)
        self.document=document; self.zoom=20; self.tool='Pencil'; self.start=None; self.selection=None
        self._selection_drag_origin=None; self._selection_preview=None; self._shape_preview=None
        self._stroke_last=None; self._stroke_value=1; self._stroke_button=None
        self._pan_active=False; self._pan_origin=None; self._pan_scroll=(0,0); self._space_down=False
        self._hover_pixel=None; self._hover_drawing=False; self._base_cache=None; self._base_cache_builds=0
        self.show_grid=True; self.stroke_interpolation=True; self.theme_name='monooled-light'
        self.background_color=PIXEL_OFF_COLOR;self.fill_color=PIXEL_ON_COLOR;self.grid_color=None;self.pixel_border_color='#FFFF00'
        self.trace_points=()
        self.wheel_action='zoom'; self.middle_pan_enabled=True; self.space_pan_enabled=True; self.brush_size=1
        self.setMouseTracking(True); self.setFocusPolicy(Qt.StrongFocus); self._sync_size()

    def _sync_size(self): self.setFixedSize(self.document.width*self.zoom+1,self.document.height*self.zoom+1); self._invalidate_base_cache()
    def _invalidate_base_cache(self): self._base_cache=None
    invalidate_base_cache = _invalidate_base_cache
    def set_document(self,document): self.document=document; self.selection=None; self._sync_size(); self.update()

    def _base_pixmap(self):
        if self._base_cache is not None and self._base_cache.size()==self.size(): return self._base_cache
        t=get_theme(self.theme_name); pix=QPixmap(self.size()); pix.fill(QColor(self.background_color)); z=self.zoom; painter=QPainter(pix)
        painter.setPen(QPen(QColor(self.pixel_border_color),1) if self.pixel_border_color else Qt.NoPen); painter.setBrush(QColor(self.fill_color))
        for y,row in enumerate(self.document.pixels):
            for x,value in enumerate(row):
                if value:painter.drawRect(x*z,y*z,z,z)
        if self.show_grid:
            stride=adaptive_grid_stride(z); painter.setPen(QPen(QColor(self.grid_color or t['canvas.grid']),1))
            xs=list(range(0,self.document.width+1,stride)); ys=list(range(0,self.document.height+1,stride))
            if xs[-1] != self.document.width: xs.append(self.document.width)
            if ys[-1] != self.document.height: ys.append(self.document.height)
            for x in xs:painter.drawLine(x*z,0,x*z,self.document.height*z)
            for y in ys:painter.drawLine(0,y*z,self.document.width*z,y*z)
        painter.end(); self._base_cache=pix; self._base_cache_builds+=1; return pix

    def _stroke_bounds(self, x0, y0, x1, y1):
        left=(max(1,int(self.brush_size))-1)//2; right=max(1,int(self.brush_size))//2
        return (
            max(0,min(x0,x1)-left), max(0,min(y0,y1)-left),
            min(self.document.width-1,max(x0,x1)+right), min(self.document.height-1,max(y0,y1)+right),
        )

    def _patch_base_cache(self, bounds):
        x0,y0,x1,y1=bounds; z=self.zoom
        damage=QRect(x0*z,y0*z,(x1-x0+1)*z+1,(y1-y0+1)*z+1)
        if self._base_cache is not None:
            painter=QPainter(self._base_cache); painter.fillRect(damage,QColor(self.background_color)); painter.setPen(QPen(QColor(self.pixel_border_color),1) if self.pixel_border_color else Qt.NoPen); painter.setBrush(QColor(self.fill_color))
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):
                    if self.document.pixels[y][x]:painter.drawRect(x*z,y*z,z,z)
            if self.show_grid:
                stride=adaptive_grid_stride(z); painter.setPen(QPen(QColor(self.grid_color or get_theme(self.theme_name)['canvas.grid']),1))
                for x in range((x0//stride)*stride,x1+2,stride):painter.drawLine(x*z,y0*z,x*z,(y1+1)*z)
                for y in range((y0//stride)*stride,y1+2,stride):painter.drawLine(x0*z,y*z,(x1+1)*z,y*z)
            painter.end()
        self.pixelsChanged.emit(bounds); self.update(damage.adjusted(-1,-1,1,1))

    def _set_hover_state(self,hover,drawing):
        hover=hover if hover is None else (int(hover[0]),int(hover[1])); drawing=bool(drawing)
        previous=self._hover_pixel; drawing_changed=drawing!=self._hover_drawing
        if hover==previous and not drawing_changed:return False
        self._hover_pixel=hover; self._hover_drawing=drawing
        damage=hover_damage_rects(previous,hover,self.zoom)
        if drawing_changed and hover is not None and not damage: damage=hover_damage_rects(None,hover,self.zoom)
        for x,y,w,h in damage:self.update(QRect(x,y,w,h))
        return True

    def _scroll_area(self):
        parent=self.parentWidget()
        while parent is not None:
            if isinstance(parent,QScrollArea): return parent
            parent=parent.parentWidget()
        return None

    def paintEvent(self,event):
        t=get_theme(self.theme_name); painter=QPainter(self); painter.drawPixmap(0,0,self._base_pixmap()); z=self.zoom
        if self._shape_preview:
            tool,x0,y0,x1,y1,value=self._shape_preview
            points=_line_preview_points(x0,y0,x1,y1) if tool=='Line' else _rectangle_preview_points(x0,y0,x1,y1)
            color=QColor(PIXEL_ON_COLOR if value else PIXEL_OFF_COLOR)
            painter.setPen(Qt.NoPen); painter.setBrush(color)
            for px,py in points:painter.drawRect(px*z,py*z,z,z)
        if self.selection:
            x,y,w,h=self.selection
            if self._selection_preview:x+=self._selection_preview[0]; y+=self._selection_preview[1]
            painter.setPen(QPen(QColor(t['canvas.selection']),2,Qt.DashLine)); painter.setBrush(Qt.NoBrush); painter.drawRect(x*z,y*z,w*z,h*z)
        if self.trace_points:
            color=QColor(t['accent.primary']);color.setAlpha(90);painter.setPen(QPen(QColor(t['accent.primary']),2));painter.setBrush(color)
            for point in self.trace_points:
                if point is not None:painter.drawRect(point[0]*z+1,point[1]*z+1,max(1,z-2),max(1,z-2))
        hover=pixel_hover_spec(in_bounds=self._hover_pixel is not None,drawing=self._hover_drawing)
        if hover.visible and self._hover_pixel is not None:
            hx,hy=self._hover_pixel; color=QColor(t['accent.primary']); color.setAlphaF(hover.opacity)
            painter.setPen(QPen(color,hover.stroke,Qt.SolidLine)); painter.setBrush(Qt.NoBrush)
            painter.drawRect(hx*z+1,hy*z+1,max(1,z-2),max(1,z-2))
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
        self._set_hover_state((x,y),True)
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
            self.document.brush(x,y,value,size=self.brush_size); self._patch_base_cache(self._stroke_bounds(x,y,x,y))
        elif self.tool in ('Line','Rectangle'):
            self._shape_preview=(self.tool,x,y,x,y,value); self.update()
        elif self.tool=='Fill':
            self._shape_preview=None; self.document.flood_fill(x,y,value); self.document.end_gesture(); self.start=None; self._stroke_last=None; self._invalidate_base_cache(); self.documentChanged.emit(); self.update()

    def mouseMoveEvent(self,event):
        x,y=self._pixel(event)
        hover=(x,y) if self._in_bounds(x,y) else None
        drawing=bool(event.buttons()&(Qt.LeftButton|Qt.RightButton)) and hover is not None
        changed=self._set_hover_state(hover,drawing)
        if changed:self.cursorChanged.emit(x,y if hover is not None else -1)
        if self._pan_active:
            self._pan_move(event); return
        if self.tool=='Select' and self._selection_drag_origin and (event.buttons()&Qt.LeftButton):
            ox,oy=self._selection_drag_origin; self._selection_preview=(x-ox,y-oy); self.update(); return
        buttons=event.buttons()
        if buttons&(Qt.LeftButton|Qt.RightButton) and self.tool in ('Line','Rectangle') and self.start:
            x=max(0,min(self.document.width-1,x)); y=max(0,min(self.document.height-1,y))
            x0,y0=self.start; self._shape_preview=(self.tool,x0,y0,x,y,self._stroke_value); self.update(); return
        if not (buttons&(Qt.LeftButton|Qt.RightButton)) or self.tool not in ('Pencil','Eraser') or not self._in_bounds(x,y):return
        last=self._stroke_last or (x,y)
        if self.stroke_interpolation:self.document.brush_segment(last[0],last[1],x,y,self._stroke_value,size=self.brush_size)
        else:self.document.brush(x,y,self._stroke_value,size=self.brush_size)
        self._stroke_last=(x,y); self._patch_base_cache(self._stroke_bounds(last[0],last[1],x,y))

    def mouseReleaseEvent(self,event):
        if event.button() in (Qt.LeftButton,Qt.RightButton):
            self._set_hover_state(self._hover_pixel,False)
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
                if adx or ady:self.document.move_region(sx,sy,sw,sh,adx,ady); self.selection=(nx,ny,sw,sh); self._invalidate_base_cache(); self.documentChanged.emit()
                self._selection_drag_origin=None; self._selection_preview=None; self.selectionChanged.emit(self.selection); self.update(); return
            xa,xb=sorted((x0,x1)); ya,yb=sorted((y0,y1)); self.selection=(xa,ya,xb-xa+1,yb-ya+1); self.selectionChanged.emit(self.selection); self.update(); return
        value=0 if event.button()==Qt.RightButton or self.tool=='Eraser' else 1
        self._shape_preview=None
        if self.tool=='Line':self.document.line(x0,y0,x1,y1,value=value)
        elif self.tool=='Rectangle':self.document.rectangle(x0,y0,x1,y1,value=value)
        elif self.tool in ('Pencil','Eraser'):
            self.document.end_gesture(); self._stroke_last=None; self.documentChanged.emit(); self.update(); return
        else:
            self.document._gesture_before=None; return
        self.document.end_gesture(); self._stroke_last=None; self._invalidate_base_cache(); self.documentChanged.emit(); self.update()

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

    def leaveEvent(self,event): self._set_hover_state(None,False); self.cursorChanged.emit(-1,-1); super().leaveEvent(event)


class PixelStudioWindow(QMainWindow):
    assetSaved=Signal(str)
    documentIdentityChanged=Signal(str)

    def __init__(self,path: str|Path|None=None,language: str=DEFAULT_LANGUAGE,parent=None,preferences: PreferencesStore|None=None,project_root: str|Path|None=None,project_workspace=None):
        super().__init__(parent); self.preferences=preferences or PreferencesStore.load(); self.tr=Translator(language or self.preferences.get('language',DEFAULT_LANGUAGE)); self.path=Path(path).resolve() if path else None; self.project_workspace=project_workspace;self.project_root=Path(project_root).resolve() if project_root else (self.path.parent if self.path else Path.cwd()).resolve(); self.clipboard=None
        if parent is not None:self.setWindowFlags(Qt.Widget)
        self.document_id='asset:'+str(self.path) if self.path else f'pixel:new:{id(self)}'; self.title=self.path.name if self.path else self.tr('pixel.title')
        self.document=PixelDocument.from_image(self.path) if self.path else PixelDocument(32,16)
        self.document.set_max_undo(int(self.preferences.get('performance.undo_history',200)))
        self.setWindowTitle(f"MonoOLED Studio · {self.tr('pixel.title')}"); self.resize(1180,780)
        self._runtime_settings=None; self._resolved_theme=None; self._adaptive_style_signature=None; self.system_theme=SystemThemeProvider(self)
        self._preview_timer=QTimer(self); self._preview_timer.setSingleShot(True); self._preview_timer.setInterval(80); self._preview_timer.timeout.connect(self.refresh_preview)
        self._build_ui(); self.apply_preferences(initial=True); self.refresh_preview()

    def _build_ui(self):
        tr=self.tr
        runtime=RuntimeSettings.from_preferences(self.preferences); m=build_ui_metrics(runtime.density,runtime.ui_scale); self._ui_metrics=m
        root=QWidget(); root.setObjectName('AppRoot'); self.setCentralWidget(root); layout=QVBoxLayout(root); self._root_layout=layout; layout.setContentsMargins(m['space_compact'],m['space_compact'],m['space_compact'],m['space_compact']); layout.setSpacing(m['space_compact'])
        header_host=QWidget(); self._header_host=header_host; header_host.setObjectName('PixelCommandBar'); header=QHBoxLayout(header_host); self._header_layout=header; header.setContentsMargins(m['space_normal'],m['space_compact'],m['space_normal'],m['space_compact']); header.setSpacing(m['space_normal'])
        self.title_label=QLabel(tr('pixel.title')); self.title_label.setObjectName('PanelTitle'); header.addWidget(self.title_label); header.addStretch(1)
        self.undo_btn=QPushButton(tr('action.undo')); self.undo_btn.setProperty('trKey','action.undo'); self.undo_btn.setObjectName('GhostButton'); self.undo_btn.clicked.connect(self.undo); self.redo_btn=QPushButton(tr('action.redo')); self.redo_btn.setProperty('trKey','action.redo'); self.redo_btn.setObjectName('GhostButton'); self.redo_btn.clicked.connect(self.redo); header.addWidget(self.undo_btn); header.addWidget(self.redo_btn)
        zoom_label=QLabel(tr('pixel.zoom')); zoom_label.setObjectName('Muted'); header.addWidget(zoom_label); self.zoom_combo=StudioSelect(); self.zoom_combo.button.setProperty('technicalValue',True); self.zoom_combo.addItem('Fit','fit'); [self.zoom_combo.addItem(f'{z}×',z) for z in (4,6,8,10,12,16,20,24,32,40)]; self.zoom_combo.setCurrentText('Fit'); self._zoom_mode='fit'; self.zoom_combo.currentIndexChanged.connect(self._zoom_control_changed); header.addWidget(self.zoom_combo)
        self.save_btn=QPushButton(tr('pixel.action.save')); self.save_btn.setProperty('trKey','pixel.action.save'); self.save_btn.setObjectName('PrimaryButton'); self.save_btn.clicked.connect(self.save_png); header.addWidget(self.save_btn); layout.addWidget(header_host)

        self.workspace_splitter = QSplitter(Qt.Horizontal); self.workspace_splitter.setChildrenCollapsible(False)
        self.tool_rail=QWidget(); self.tool_rail.setObjectName('ToolRail'); rail=QVBoxLayout(self.tool_rail); self._rail_layout=rail; rail.setContentsMargins(m['space_normal'],m['space_normal'],m['space_normal'],m['space_normal']); rail.setSpacing(m['space_tight']); self.tool_buttons={}
        for name in TOOLS:
            b=QToolButton(); b.setObjectName('ToolRailButton'); b.setFixedSize(m['control'],m['control']); b.setIconSize(QSize(m['icon'],m['icon'])); b.setToolTip(tr(f'pixel.tool.{name}')); b.setCheckable(True); b.clicked.connect(lambda _=False,n=name:self.set_tool(n)); rail.addWidget(b); self.tool_buttons[name]=b
        self.tool_buttons['Pencil'].setChecked(True); self._refresh_tool_icons('Pencil'); rail.addStretch(1); self.workspace_splitter.addWidget(self.tool_rail)
        self._tool_shortcuts={}
        for command_id,tool in (('pixel.pencil','Pencil'),('pixel.select','Select'),('pixel.fill','Fill')):
            shortcut=QShortcut(QKeySequence(),self); shortcut.activated.connect(lambda t=tool:self.set_tool(t)); self._tool_shortcuts[command_id]=shortcut

        canvas_frame=QFrame(); canvas_frame.setObjectName('CanvasWorkspace'); canvas_frame.setMinimumWidth(300); canvas_frame.setProperty('canvasFocus',False); self.canvas_frame=canvas_frame; center=QVBoxLayout(canvas_frame); self._canvas_layout=center; center.setContentsMargins(m['space_section'],m['space_section'],m['space_section'],m['space_section']); center.setSpacing(m['space_normal'])
        self.canvas=PixelCanvas(self.document); self.canvas_scroll=QScrollArea(); self.canvas_scroll.setObjectName('PixelCanvasScroll'); self.canvas_scroll.viewport().setObjectName('CanvasViewport'); self.canvas_scroll.setWidget(self.canvas); self.canvas_scroll.setWidgetResizable(False); self.canvas_scroll.setFrameShape(QFrame.NoFrame); center.addWidget(self.canvas_scroll,1); self.workspace_splitter.addWidget(canvas_frame)

        # Flat context inspector: no Selection/Export tabs and no card soup.
        self.inspector_scroll=QScrollArea(); self.inspector_scroll.setWidgetResizable(True); self.inspector_scroll.setMinimumWidth(265); inspector=QWidget(); inspector.setObjectName('InspectorRoot'); il=QVBoxLayout(inspector); self._inspector_layout=il; il.setContentsMargins(m['panel_margin'],m['panel_margin'],m['panel_margin'],m['panel_margin']); il.setSpacing(m['space_normal'])
        self.section_labels=[]
        def section(key, fallback=None):
            text=tr(key) if key else str(fallback or '')
            label=QLabel(text); label.setObjectName('InspectorSection'); label.setProperty('trKey',key or ''); il.addWidget(label); self.section_labels.append(label)
        section('pixel.preview'); self.preview=QLabel(); self.preview.setMinimumSize(220,110); self.preview.setAlignment(Qt.AlignCenter); il.addWidget(self.preview); self.info=QLabel(); self.info.setObjectName('TechnicalValue'); il.addWidget(self.info)
        section('pixel.tool.Select'); self.selection_info=QLabel('—'); self.selection_info.setObjectName('TechnicalValue'); self.selection_info.setWordWrap(True); il.addWidget(self.selection_info)
        for key,fn in [('pixel.action.copy',self.copy_selection),('pixel.action.cut',self.cut_selection),('pixel.action.paste',self.paste_selection)]:b=QPushButton(tr(key) if '.' in key else key); b.setProperty('trKey',key if '.' in key else ''); b.clicked.connect(fn); il.addWidget(b)
        section('pixel.section.text_font'); self.insert_text_btn=QPushButton(tr('pixel.action.insert_bitmap_text')); self.insert_text_btn.setProperty('trKey','pixel.action.insert_bitmap_text'); self.insert_text_btn.clicked.connect(self.insert_bitmap_text); il.addWidget(self.insert_text_btn)
        section('pixel.section.transform')
        for key,fn in [('pixel.action.invert',self.invert),('pixel.action.flip_h',self.flip_h),('pixel.action.flip_v',self.flip_v),('pixel.action.canvas_size',self.resize_canvas),('pixel.action.rotate90',self.rotate90),('pixel.action.rotate180',self.rotate180),('pixel.action.rotate270',self.rotate270),('pixel.action.crop_selection',self.crop_selection),('pixel.action.clear',self.clear)]:b=QPushButton(tr(key) if '.' in key else key); b.setProperty('trKey',key if '.' in key else ''); b.clicked.connect(fn); il.addWidget(b)
        section('pixel.tab.export')
        for key,fn in [('pixel.action.open',self.open_image),('pixel.action.save',self.save_png),('pixel.action.export_bin',self.save_bin),('pixel.action.export_c',self.save_c_header),('pixel.action.font',self.font_generator)]:b=QPushButton(tr(key) if '.' in key else key); b.setProperty('trKey',key if '.' in key else ''); b.clicked.connect(fn); il.addWidget(b)
        self.output_workbench=OutputWorkbench(self,il,layout)
        il.addStretch(1); self.inspector_scroll.setWidget(inspector); self.workspace_splitter.addWidget(self.inspector_scroll); self.workspace_splitter.setSizes([56,900,340]); layout.insertWidget(1,self.workspace_splitter,1)
        self.pixel_status=QLabel(self.tr('font.status.pixel')); self.pixel_status.setObjectName('TechnicalValue'); self.statusBar().addWidget(self.pixel_status,1)
        self.input_hint=QLabel(self.tr('pixel.input_hint')); self.input_hint.setObjectName('Muted'); self.statusBar().addPermanentWidget(self.input_hint)
        self.canvas.documentChanged.connect(self._document_changed); self.canvas.pixelsChanged.connect(lambda _bounds:self._preview_timer.start()); self.canvas.pixelsChanged.connect(lambda _bounds:self.output_workbench.document_changed()); self.canvas.cursorChanged.connect(self._cursor_changed); self.canvas.selectionChanged.connect(lambda _v:self.refresh_preview()); self.canvas.selectionChanged.connect(lambda _v:self.output_workbench.selection_changed()); self.canvas.zoomChanged.connect(self._canvas_zoom_changed)
        self.canvas_scroll.viewport().installEventFilter(self); self.canvas.installEventFilter(self)

    def _refresh_tool_icons(self,selected: str | None = None):
        theme=get_theme(self._resolved_theme or 'monooled-light'); active=selected or getattr(self.canvas,'tool','Pencil'); size=self._ui_metrics.get('icon',16)
        for name,button in self.tool_buttons.items():
            color=theme['accent.primary'] if name==active else theme['text.secondary']
            button.setIcon(_tool_icon(name,color,size)); button.setIconSize(QSize(size,size))

    def _apply_ui_metrics(self,runtime):
        m=build_ui_metrics(runtime.density,runtime.ui_scale); self._ui_metrics=m
        self._root_layout.setContentsMargins(m['space_compact'],m['space_compact'],m['space_compact'],m['space_compact']); self._root_layout.setSpacing(m['space_compact'])
        self._header_layout.setContentsMargins(m['space_normal'],m['space_compact'],m['space_normal'],m['space_compact']); self._header_layout.setSpacing(m['space_normal'])
        self._rail_layout.setContentsMargins(m['space_normal'],m['space_normal'],m['space_normal'],m['space_normal']); self._rail_layout.setSpacing(m['space_tight'])
        for button in self.tool_buttons.values(): button.setFixedSize(m['control'],m['control']); button.setIconSize(QSize(m['icon'],m['icon']))
        self._refresh_tool_icons()
        self._canvas_layout.setContentsMargins(m['space_section'],m['space_section'],m['space_section'],m['space_section']); self._canvas_layout.setSpacing(m['space_normal'])
        self._inspector_layout.setContentsMargins(m['panel_margin'],m['panel_margin'],m['panel_margin'],m['panel_margin']); self._inspector_layout.setSpacing(m['space_normal'])

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
        if delta.ui_metrics_changed:self._apply_ui_metrics(runtime)
        if delta.appearance_changed or theme_changed:
            # Embedded editors inherit the application stylesheet. Only a real
            # top-level Pixel window owns a local stylesheet.
            if self.parentWidget() is None:
                self.setPalette(build_theme_palette(theme))
                signature=(theme,runtime.density,runtime.ui_scale)
                if signature!=self._adaptive_style_signature:
                    self.setStyleSheet(build_adaptive_stylesheet(runtime.density,ui_scale=runtime.ui_scale));self._adaptive_style_signature=signature
            self.canvas.theme_name=theme; self.canvas.invalidate_base_cache(); self._refresh_tool_icons(); self.canvas.update()
        if delta.pixel_changed or delta.performance_changed:
            self.canvas.show_grid=runtime.pixel_grid; self.canvas.invalidate_base_cache(); self.canvas.stroke_interpolation=runtime.stroke_interpolation; self.canvas.wheel_action=runtime.wheel_action; self.canvas.middle_pan_enabled=runtime.middle_pan; self.canvas.space_pan_enabled=runtime.space_pan; self.canvas.brush_size=runtime.brush_size
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
        for n,b in self.tool_buttons.items():
            b.setChecked(n==name)
            b.clearFocus()
        self._refresh_tool_icons(name)
        self.canvas.setFocus(Qt.OtherFocusReason)
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
        if obj is self.canvas_scroll.viewport() and event.type()==QEvent.Resize:self._apply_fit_zoom()
        if obj is self.canvas and event.type() in (QEvent.FocusIn,QEvent.FocusOut):
            focused=event.type()==QEvent.FocusIn
            self.canvas_frame.setProperty('canvasFocus',focused)
            style=self.canvas_frame.style(); style.unpolish(self.canvas_frame); style.polish(self.canvas_frame); self.canvas_frame.update()
        return super().eventFilter(obj,event)
    def _pick(self,save=False,filter='PNG (*.png)'):
        fn=QFileDialog.getSaveFileName if save else QFileDialog.getOpenFileName; return fn(self,self.tr('pixel.title'),str(self.path or Path.cwd()),filter)[0]
    def _path_conflicts_with_open_editor(self,path):
        target_id='asset:'+str(Path(path).resolve())
        parent=self.parentWidget()
        while parent is not None:
            if hasattr(parent,'count') and hasattr(parent,'widget'):
                for i in range(parent.count()):
                    other=parent.widget(i)
                    if other is not self and getattr(other,'document_id',None)==target_id:
                        QMessageBox.warning(self,self.tr('pixel.title'),self.tr('pixel.already_open',path=str(Path(path).resolve())))
                        return True
            parent=parent.parentWidget()
        return False
    def open_image(self):
        path=self._pick()
        if not path:return
        try:
            dialog=ImageImportDialog(path,self.tr,self)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self,self.tr('pixel.import.title'),str(exc)); return
        if self._path_conflicts_with_open_editor(path):return
        if self.document.dirty:
            choice=QMessageBox.question(self,self.tr('dialog.unsaved_title'),self.tr('dialog.save_changes'),QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
            if choice==QMessageBox.Cancel:return
            if choice==QMessageBox.Save and not self.save():return
        if dialog.exec()!=QDialog.Accepted:return
        self.path=Path(path).resolve(); self.document=dialog.converted_document(); self.document.set_max_undo(int(self.preferences.get('performance.undo_history',200))); self.canvas.set_document(self.document)
        self.document_id='asset:'+str(self.path); self.title=self.path.name; self.documentIdentityChanged.emit(str(self.path)); self._document_changed(); self.refresh_preview()
    def _document_changed(self):
        self._preview_timer.stop(); self.refresh_preview(); self.output_workbench.document_changed(); self.title=(self.path.name if self.path else self.tr('pixel.title'))+(' ●' if self.document.dirty else '')
        parent=self.parentWidget()
        while parent is not None:
            if hasattr(parent,'indexOf') and hasattr(parent,'setTabText'):
                i=parent.indexOf(self)
                if i>=0:parent.setTabText(i,self.title);break
            parent=parent.parentWidget()

    def save(self): return self.save_png()

    def save_png(self):
        path=str(self.path) if self.path and self.path.suffix.lower()=='.png' else self._pick(save=True)
        if not path:return False
        if self._path_conflicts_with_open_editor(path):return False
        try:
            saved=self.document.save_png(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self,self.tr('pixel.action.save'),str(exc)); return False
        self.path=saved; self.document_id='asset:'+str(self.path.resolve()); self.title=self.path.name; self.assetSaved.emit(str(self.path)); self.refresh_preview(); self._document_changed(); return True
    def save_bin(self):
        path=self._pick(save=True,filter='BIN (*.bin)')
        if not path:return False
        try:self.document.save_bin(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self,self.tr('pixel.action.export_bin'),str(exc)); return False
        return True
    def save_c_header(self):
        path=self._pick(save=True,filter='C Header (*.h)')
        if not path:return False
        default=(self.path.stem if self.path else 'oled_bitmap').replace('-','_').replace(' ','_'); symbol,ok=QInputDialog.getText(self,self.tr('pixel.action.export_c'),self.tr('pixel.symbol'),text=default)
        if not (ok and symbol):return False
        try:self.document.save_c_header(path,symbol)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self,self.tr('pixel.action.export_c'),str(exc)); return False
        return True
    def undo(self):
        if self.document.undo():self.canvas.invalidate_base_cache(); self.canvas.update(); self.refresh_preview()
    def redo(self):
        if self.document.redo():self.canvas.invalidate_base_cache(); self.canvas.update(); self.refresh_preview()
    def invert(self):self.document.invert(); self.canvas.invalidate_base_cache(); self.canvas.update(); self.refresh_preview()
    def flip_h(self):self.document.flip_horizontal(); self.canvas.invalidate_base_cache(); self.canvas.update(); self.refresh_preview()
    def flip_v(self):self.document.flip_vertical(); self.canvas.invalidate_base_cache(); self.canvas.update(); self.refresh_preview()
    def clear(self):self.document.clear(); self.canvas.invalidate_base_cache(); self.canvas.update(); self.refresh_preview()
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
