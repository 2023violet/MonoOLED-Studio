from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize, QRect, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QImage
from PySide6.QtWidgets import QWidget

from canvas_geometry import canvas_widget_size
from theme_system import get_theme
from micro_signature import primary_corner_spec, smart_guide_anchor_points


def adaptive_grid_stride(zoom: int) -> int:
    """Return a readable major-grid stride without hiding the grid at low zoom."""
    z=max(1,int(zoom))
    if z >= 8: return 1
    if z >= 4: return 2
    if z >= 2: return 4
    return 8


class OLEDCanvas(QWidget):
    elementSelected = Signal(str)              # compatibility / primary selection
    selectionChanged = Signal(object)          # tuple[str, ...]
    elementMoved = Signal(str, int, int)
    dragStarted = Signal(str)
    dragFinished = Signal(str)
    pixelHovered = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas_w = 128
        self._canvas_h = 32
        self._rows: list[list[int]] = [[0] * self._canvas_w for _ in range(self._canvas_h)]
        self._frame_image = QImage(self._canvas_w,self._canvas_h,QImage.Format_Grayscale8)
        self._frame_image.fill(0)
        self._elements: tuple[dict, ...] = ()
        self._selected_ids: set[str] = set()
        self._selection_order: list[str] = []
        self._primary_id: str | None = None
        self._marquee_start: tuple[int,int] | None = None
        self._marquee_end: tuple[int,int] | None = None
        self._marquee_ctrl = False
        self._marquee_base: list[str] = []
        self._zoom = 8
        self._show_grid = True
        self._show_bounds = True
        self._show_rulers = True
        self._guides={'x':(), 'y':()}
        self._guide_anchors_active=False
        self._zones=[]
        self._margin = 26
        self._theme_name = 'monooled-light'
        self._drag_id: str | None = None
        self._last_pixel: tuple[int, int] | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(self.sizeHint())

    @property
    def canvas_size(self) -> tuple[int, int]:
        return self._canvas_w, self._canvas_h

    @property
    def zoom(self) -> int:
        return self._zoom

    @property
    def selected_ids(self) -> tuple[str, ...]:
        valid={str(item.get('id')) for item in self._elements}
        return tuple(eid for eid in self._selection_order if eid in self._selected_ids and eid in valid)

    @property
    def primary_id(self) -> str | None:
        return self._primary_id if self._primary_id in self._selected_ids else (self.selected_ids[-1] if self.selected_ids else None)

    def sizeHint(self) -> QSize:  # noqa: N802
        w, h = canvas_widget_size(self._canvas_w, self._canvas_h, self._zoom, margin=self._margin)
        return QSize(w, h)

    def set_zoom(self, zoom: int) -> None:
        self._zoom = max(1, int(zoom))
        size = self.sizeHint()
        self.setMinimumSize(size)
        self.resize(size)
        self.updateGeometry()
        self.update()

    def set_theme(self, theme_name: str) -> None:
        self._theme_name = str(theme_name or 'monooled-light')
        self.update()

    def set_overlays(self, *, grid: bool, bounds: bool, rulers: bool | None = None) -> None:
        self._show_grid = bool(grid)
        self._show_bounds = bool(bounds)
        if rulers is not None:
            self._show_rulers = bool(rulers)
        self.update()

    def set_guides(self, guides, *, anchors: bool = False) -> None:
        self._guides={'x':tuple(guides.get('x',())), 'y':tuple(guides.get('y',()))}
        self._guide_anchors_active=bool(anchors)
        self.update()

    def set_zones(self, zones) -> None:
        self._zones=list(zones or []); self.update()

    def set_selection(self, element_ids, primary=None) -> None:
        valid = {str(item.get('id')) for item in self._elements}
        order=[]
        for value in element_ids:
            eid=str(value)
            if eid in valid and eid not in order:order.append(eid)
        self._selection_order=order; self._selected_ids=set(order)
        self._primary_id=str(primary) if primary is not None and str(primary) in self._selected_ids else (order[-1] if order else None)
        self.update()

    def set_frame(self, render_result, selected_id=None) -> None:
        fb = render_result.framebuffer
        new_w, new_h = int(fb.width), int(fb.height)
        size_changed = (new_w, new_h) != (self._canvas_w, self._canvas_h)
        self._canvas_w = new_w
        self._canvas_h = new_h
        self._rows = fb.to_rows()
        gray = bytes(255 if value else 0 for row in self._rows for value in row)
        self._frame_image = QImage(gray,new_w,new_h,new_w,QImage.Format_Grayscale8).copy()
        self._elements = render_result.resolved_elements
        if selected_id is None:
            pass
        elif isinstance(selected_id, str):
            self._selected_ids = {selected_id}; self._selection_order=[selected_id]; self._primary_id=selected_id
        else:
            order=list(dict.fromkeys(str(v) for v in selected_id)); self._selected_ids=set(order); self._selection_order=order
            if self._primary_id not in self._selected_ids:self._primary_id=order[-1] if order else None
        if size_changed:
            size = self.sizeHint()
            self.setMinimumSize(size)
            self.resize(size)
            self.updateGeometry()
        self.update()

    def _origin(self) -> tuple[int, int]:
        return self._margin, self._margin

    def _to_pixel(self, px: float, py: float) -> tuple[int, int] | None:
        ox, oy = self._origin()
        x = int((px - ox) // self._zoom)
        y = int((py - oy) // self._zoom)
        if 0 <= x < self._canvas_w and 0 <= y < self._canvas_h:
            return x, y
        return None

    def _hit_test(self, x: int, y: int) -> str | None:
        for item in reversed(self._elements):
            if not item.get('visible'):
                continue
            ix, iy, iw, ih = (item.get(k) for k in ('x', 'y', 'w', 'h'))
            if None in (ix, iy, iw, ih):
                continue
            if int(ix) <= x < int(ix) + int(iw) and int(iy) <= y < int(iy) + int(ih):
                return str(item['id'])
        return None

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        t=get_theme(self._theme_name)
        painter.fillRect(self.rect(), QColor(t['surface.canvas']))
        ox, oy = self._origin()
        canvas_w = self._canvas_w * self._zoom
        canvas_h = self._canvas_h * self._zoom
        painter.fillRect(ox, oy, canvas_w, canvas_h, QColor('#000000'))

        z = self._zoom
        # Framebuffer pixels are rasterized once in set_frame; painting uses one
        # nearest-neighbour image blit instead of up to 8192 drawRect calls.
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.drawImage(QRect(ox,oy,canvas_w,canvas_h), self._frame_image)

        if self._show_grid:
            stride=adaptive_grid_stride(z)
            pen = QPen(QColor(t['canvas.grid'])); pen.setWidth(1); painter.setPen(pen)
            xs=list(range(0,self._canvas_w+1,stride))
            ys=list(range(0,self._canvas_h+1,stride))
            if xs[-1] != self._canvas_w: xs.append(self._canvas_w)
            if ys[-1] != self._canvas_h: ys.append(self._canvas_h)
            for x in xs:
                px = ox + x * z; painter.drawLine(px, oy, px, oy + canvas_h)
            for y in ys:
                py = oy + y * z; painter.drawLine(ox, py, ox + canvas_w, py)

        if self._show_bounds:
            for item in self._elements:
                if not item.get('visible'):
                    continue
                vals = [item.get(k) for k in ('x', 'y', 'w', 'h')]
                if any(v is None for v in vals):
                    continue
                x, y, w, h = map(int, vals)
                selected = str(item.get('id')) in self._selected_ids
                color = QColor(t['canvas.selection'] if selected else t['text.muted']); color.setAlpha(240 if selected else 120)
                pen = QPen(color); pen.setWidth(2 if selected else 1); pen.setStyle(Qt.SolidLine if selected else Qt.DashLine)
                painter.setPen(pen); painter.setBrush(Qt.NoBrush)
                painter.drawRect(ox + x*z, oy + y*z, max(1,w*z-1), max(1,h*z-1))
                corner=primary_corner_spec(zoom=z,selected=selected,primary=str(item.get('id'))==self.primary_id)
                if corner.visible:
                    accent=QColor(t['accent.primary']); accent.setAlphaF(corner.opacity); cpen=QPen(accent,corner.stroke,Qt.SolidLine); cpen.setCapStyle(Qt.SquareCap); painter.setPen(cpen)
                    px=ox+x*z-1; py=oy+y*z-1
                    painter.drawLine(px,py,px+corner.arm,py); painter.drawLine(px,py,px,py+corner.arm)

        # Multi-selection overlay: group bounds + equal/unequal spacing cues.
        selected_items=[item for item in self._elements if str(item.get('id')) in self._selected_ids and item.get('visible')]
        if len(selected_items)>=2:
            try:
                left=min(int(i['x']) for i in selected_items); top=min(int(i['y']) for i in selected_items)
                right=max(int(i['x'])+int(i['w']) for i in selected_items); bottom=max(int(i['y'])+int(i['h']) for i in selected_items)
                group=QColor(t['accent.primary']); group.setAlpha(220); painter.setPen(QPen(group,1,Qt.DashLine)); painter.setBrush(Qt.NoBrush)
                painter.drawRect(ox+left*z-2,oy+top*z-2,max(1,(right-left)*z+3),max(1,(bottom-top)*z+3))
                painter.setFont(QFont('Segoe UI',7)); painter.drawText(ox+left*z, max(10,oy+top*z-5), f'{len(selected_items)} selected')
                ordered=sorted(selected_items,key=lambda i:int(i['x']))
                for a,b in zip(ordered,ordered[1:]):
                    gap=int(b['x'])-(int(a['x'])+int(a['w']))
                    if gap>0:
                        x1=ox+(int(a['x'])+int(a['w']))*z; x2=ox+int(b['x'])*z; yy=oy+min(int(a['y']),int(b['y']))*z+4
                        painter.drawLine(x1,yy,x2,yy); painter.drawText((x1+x2)//2-12,yy-10,24,9,Qt.AlignCenter,f'{gap}px')
            except Exception:
                pass

        # Editor-only zones and smart alignment guides.
        for zone in self._zones:
            try: x,y,w,h=(int(zone[k]) for k in ('x','y','w','h'))
            except Exception: continue
            color=QColor(t['accent.primary']); color.setAlpha(80); pen=QPen(color); pen.setStyle(Qt.DotLine); painter.setPen(pen); painter.setBrush(Qt.NoBrush)
            painter.drawRect(ox+x*z,oy+y*z,max(1,w*z-1),max(1,h*z-1))
        guide=QColor(t['accent.primary']); guide.setAlpha(210); painter.setPen(QPen(guide,1,Qt.DashLine))
        for x in self._guides.get('x',()): painter.drawLine(ox+x*z,oy,ox+x*z,oy+canvas_h)
        for y in self._guides.get('y',()): painter.drawLine(ox,oy+y*z,ox+canvas_w,oy+y*z)
        if self._guide_anchors_active and self.primary_id:
            primary=next((item for item in self._elements if str(item.get('id'))==self.primary_id and item.get('visible')),None)
            if primary is not None:
                try: geometry=tuple(int(primary[k]) for k in ('x','y','w','h'))
                except Exception: geometry=None
                points=smart_guide_anchor_points(self._guides,geometry)
                if points:
                    anchor=QColor(t['accent.primary']); painter.setPen(Qt.NoPen); painter.setBrush(anchor); painter.setRenderHint(QPainter.Antialiasing,True)
                    d=4.0
                    for ax,ay in points:
                        cx=ox+ax*z; cy=oy+ay*z
                        painter.drawEllipse(QRectF(cx-d/2.0,cy-d/2.0,d,d))
                    painter.setRenderHint(QPainter.Antialiasing,False)

        if self._show_rulers:
            painter.setPen(QColor(t['text.muted']))
            painter.setFont(QFont('Segoe UI', 7))
            step = 8 if self._canvas_w >= 64 else 4
            for x in range(0, self._canvas_w + 1, step):
                px=ox+x*z; painter.drawLine(px, oy-5, px, oy-1); painter.drawText(px-8, oy-8, 16, 8, Qt.AlignCenter, str(x))
            for y in range(0, self._canvas_h + 1, 8):
                py=oy+y*z; painter.drawLine(ox-5, py, ox-1, py); painter.drawText(0, py-6, ox-8, 12, Qt.AlignRight|Qt.AlignVCenter, str(y))

        if self._marquee_start and self._marquee_end:
            x0,y0=self._marquee_start; x1,y1=self._marquee_end; xa,xb=sorted((x0,x1)); ya,yb=sorted((y0,y1))
            mc=QColor(t['accent.primary']); mc.setAlpha(180); painter.setPen(QPen(mc,1,Qt.DashLine)); fill=QColor(t['accent.soft']); fill.setAlpha(45); painter.setBrush(fill)
            painter.drawRect(ox+xa*z,oy+ya*z,max(1,(xb-xa+1)*z),max(1,(yb-ya+1)*z))

        painter.setPen(QPen(QColor(t['border.normal']))); painter.setBrush(Qt.NoBrush)
        painter.drawRect(ox-1, oy-1, canvas_w+1, canvas_h+1)
        painter.end()

    def _emit_selection(self):
        self.selectionChanged.emit(self.selected_ids)
        if self.primary_id:self.elementSelected.emit(self.primary_id)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        pos = self._to_pixel(event.position().x(), event.position().y())
        if pos is None:
            return
        hit = self._hit_test(*pos); ctrl=bool(event.modifiers() & Qt.ControlModifier)
        if hit:
            if ctrl:
                if hit in self._selected_ids:
                    self._selected_ids.remove(hit); self._selection_order=[e for e in self._selection_order if e!=hit]; self._primary_id=self._selection_order[-1] if self._selection_order else None
                    self._drag_id=None
                else:
                    self._selected_ids.add(hit); self._selection_order.append(hit); self._primary_id=hit; self._drag_id=hit
            else:
                if hit not in self._selected_ids:
                    self._selected_ids={hit}; self._selection_order=[hit]
                elif hit in self._selection_order:
                    self._selection_order=[e for e in self._selection_order if e!=hit]+[hit]
                self._primary_id=hit; self._drag_id=hit
            self._last_pixel=pos; self._emit_selection()
            if self._drag_id:
                self.dragStarted.emit(hit); self.setCursor(Qt.ClosedHandCursor)
            self.update()
        else:
            self._marquee_start=pos; self._marquee_end=pos; self._marquee_ctrl=ctrl; self._marquee_base=list(self.selected_ids)
            if not ctrl:
                self._selected_ids.clear(); self._selection_order.clear(); self._primary_id=None; self._emit_selection()
            self.update()
        self.setFocus()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = self._to_pixel(event.position().x(), event.position().y())
        if pos is not None:
            self.pixelHovered.emit(pos[0], pos[1], int(self._rows[pos[1]][pos[0]]))
        if self._marquee_start and event.buttons() & Qt.LeftButton and pos is not None:
            self._marquee_end=pos; self.update(); return
        if self._drag_id and self._last_pixel and pos is not None and event.buttons() & Qt.LeftButton:
            dx = pos[0]-self._last_pixel[0]; dy = pos[1]-self._last_pixel[1]
            if dx or dy:
                self.elementMoved.emit(self._drag_id, dx, dy); self._last_pixel = pos
            return
        if pos is not None and self._hit_test(*pos): self.setCursor(Qt.OpenHandCursor)
        else: self.unsetCursor()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button()==Qt.LeftButton and self._marquee_start:
            end=self._to_pixel(event.position().x(),event.position().y()) or self._marquee_end or self._marquee_start
            x0,y0=self._marquee_start; x1,y1=end; xa,xb=sorted((x0,x1)); ya,yb=sorted((y0,y1)); hits=[]
            for item in self._elements:
                if not item.get('visible'):continue
                try:ix,iy,iw,ih=(int(item[k]) for k in ('x','y','w','h'))
                except Exception:continue
                if ix<=xb and ix+iw-1>=xa and iy<=yb and iy+ih-1>=ya:hits.append(str(item['id']))
            if self._marquee_ctrl:
                order=list(self._marquee_base); chosen=set(order)
                for eid in hits:
                    if eid in chosen: chosen.remove(eid); order=[v for v in order if v!=eid]
                    else: chosen.add(eid); order.append(eid)
                self._selection_order=order; self._selected_ids=set(order); self._primary_id=order[-1] if order else None
            else:
                self._selection_order=hits; self._selected_ids=set(hits); self._primary_id=hits[-1] if hits else None
            self._marquee_start=None; self._marquee_end=None; self._marquee_base=[]; self._emit_selection(); self.update(); super().mouseReleaseEvent(event); return
        if event.button() == Qt.LeftButton:
            drag_id=self._drag_id; self._drag_id=None; self._last_pixel=None; self.unsetCursor()
            if drag_id: self.dragFinished.emit(drag_id)
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.pixelHovered.emit(-1,-1,0)
        super().leaveEvent(event)

