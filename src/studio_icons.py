from __future__ import annotations

"""Deterministic studio icon registry.

Every icon is drawn with QPainter line recipes in a 16x16 logical space
(1.5px round-cap strokes) — no fonts, no emoji, no platform glyph drift.
``studio_icon(name, color, size)`` renders any registered recipe in the
requested theme color so buttons can be re-tinted when the theme changes.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICON_SIZE = 16


def _pen(color: str) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _polyline(painter: QPainter, *points) -> None:
    for start, end in zip(points, points[1:]):
        painter.drawLine(QPointF(*start), QPointF(*end))


def _pencil(painter: QPainter) -> None:
    _polyline(painter, (3, 12), (12, 4), (10, 5), (12, 7), (3, 14), (6, 13))


def _eraser(painter: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3, 10); path.lineTo(8.8, 4.2); path.lineTo(13, 8.4)
    path.lineTo(7.4, 14); path.lineTo(4.6, 14); path.closeSubpath()
    painter.drawPath(path)
    _polyline(painter, (7, 14), (14, 14))


def _line(painter: QPainter) -> None:
    _polyline(painter, (3, 13), (13, 3))


def _rectangle(painter: QPainter) -> None:
    painter.drawRect(QRectF(3, 3, 10, 10))


def _fill(painter: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(4, 7); path.lineTo(8.2, 2.8); path.lineTo(13.2, 7.8)
    path.lineTo(8.8, 12.2); path.closeSubpath()
    painter.drawPath(path)
    _polyline(painter, (5, 8), (12, 8), (11, 13), (14, 13))


def _select(painter: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(3, 2.5); path.lineTo(12.4, 8.2); path.lineTo(8.2, 9.2)
    path.lineTo(10.7, 13.4); path.lineTo(8.8, 14.4); path.lineTo(6.5, 10.2)
    path.lineTo(3, 13); path.closeSubpath()
    painter.drawPath(path)


def _copy(painter: QPainter) -> None:
    painter.drawRect(QRectF(5.5, 2.5, 8, 8))
    painter.drawRect(QRectF(2.5, 5.5, 8, 8))


def _cut(painter: QPainter) -> None:
    painter.drawEllipse(QRectF(2.8, 10.2, 3.6, 3.6))
    painter.drawEllipse(QRectF(9.6, 10.2, 3.6, 3.6))
    _polyline(painter, (4.6, 10.6), (11.4, 2.6), (8, 7), (4.6, 2.6), (11.4, 10.6))


def _paste(painter: QPainter) -> None:
    painter.drawRect(QRectF(3.5, 4, 9, 10))
    painter.drawRect(QRectF(6, 2.5, 4, 3))


def _undo(painter: QPainter) -> None:
    painter.drawArc(QRectF(3.5, 4.5, 9, 8), 30 * 16, 160 * 16)
    _polyline(painter, (3.4, 9.4), (3.4, 5.4), (7, 5.4))


def _redo(painter: QPainter) -> None:
    painter.drawArc(QRectF(3.5, 4.5, 9, 8), 350 * 16, -160 * 16)
    _polyline(painter, (12.6, 9.4), (12.6, 5.4), (9, 5.4))


def _save(painter: QPainter) -> None:
    painter.drawRect(QRectF(3, 3, 10, 10))
    painter.drawRect(QRectF(5.5, 9, 5, 4))
    painter.drawRect(QRectF(6, 3.5, 4, 3))


def _open(painter: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(2.5, 12.5); path.lineTo(2.5, 4.5); path.lineTo(6, 4.5)
    path.lineTo(8, 6.5); path.lineTo(13.5, 6.5); path.lineTo(13.5, 12.5)
    path.closeSubpath()
    painter.drawPath(path)


def _export_bin(painter: QPainter) -> None:
    _polyline(painter, (3, 9.5), (3, 13), (13, 13), (13, 9.5))
    _polyline(painter, (8, 2.5), (8, 9.5), (5.5, 7), (8, 9.5), (10.5, 7))


def _export_h(painter: QPainter) -> None:
    painter.drawRect(QRectF(3.5, 2.5, 9, 11))
    _polyline(painter, (6.2, 6), (5, 8), (6.2, 10))
    _polyline(painter, (9.8, 6), (11, 8), (9.8, 10))


def _invert(painter: QPainter) -> None:
    painter.drawEllipse(QRectF(3, 3, 10, 10))
    path = QPainterPath()
    path.moveTo(8, 3)
    path.arcTo(QRectF(3, 3, 10, 10), 90, -180)
    path.closeSubpath()
    painter.fillPath(path, painter.pen().color())


def _flip_h(painter: QPainter) -> None:
    pen = painter.pen()
    dashed = QPen(pen)
    dashed.setDashPattern([2, 2])
    painter.setPen(dashed)
    _polyline(painter, (8, 2), (8, 14))
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(2.5, 4); path.lineTo(6.5, 8); path.lineTo(2.5, 12); path.closeSubpath()
    painter.drawPath(path)
    path = QPainterPath()
    path.moveTo(13.5, 4); path.lineTo(9.5, 8); path.lineTo(13.5, 12); path.closeSubpath()
    painter.drawPath(path)


def _flip_v(painter: QPainter) -> None:
    pen = painter.pen()
    dashed = QPen(pen)
    dashed.setDashPattern([2, 2])
    painter.setPen(dashed)
    _polyline(painter, (2, 8), (14, 8))
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(4, 2.5); path.lineTo(8, 6.5); path.lineTo(12, 2.5); path.closeSubpath()
    painter.drawPath(path)
    path = QPainterPath()
    path.moveTo(4, 13.5); path.lineTo(8, 9.5); path.lineTo(12, 13.5); path.closeSubpath()
    painter.drawPath(path)


def _rotate(painter: QPainter) -> None:
    painter.drawArc(QRectF(3.5, 3.5, 9, 9), 40 * 16, 260 * 16)
    _polyline(painter, (12.6, 3.6), (12.9, 6.9), (9.8, 6.4))


def _crop(painter: QPainter) -> None:
    _polyline(painter, (5, 2), (5, 11), (14, 11))
    _polyline(painter, (2, 5), (11, 5), (11, 14))


def _clear(painter: QPainter) -> None:
    _polyline(painter, (3.5, 4.5), (12.5, 4.5))
    _polyline(painter, (6, 2.5), (10, 2.5))
    painter.drawRect(QRectF(4.5, 4.5, 7, 9))
    _polyline(painter, (6.5, 7), (6.5, 11), (9.5, 7), (9.5, 11))


def _text(painter: QPainter) -> None:
    _polyline(painter, (4, 3.5), (12, 3.5))
    _polyline(painter, (8, 3.5), (8, 13))


def _generate(painter: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(9.5, 2); path.lineTo(4, 9); path.lineTo(7.6, 9)
    path.lineTo(6.8, 14); path.lineTo(12.2, 6.8); path.lineTo(8.4, 6.8)
    path.closeSubpath()
    painter.drawPath(path)


def _font(painter: QPainter) -> None:
    _polyline(painter, (8, 3), (4, 13), (8, 3), (12, 13))
    _polyline(painter, (5.5, 9.2), (10.5, 9.2))


def _zoom_fit(painter: QPainter) -> None:
    painter.drawRect(QRectF(3.5, 3.5, 9, 9))
    _polyline(painter, (5.5, 6.5), (7, 8), (5.5, 6.5), (7, 5.5), (5.5, 6.5))
    _polyline(painter, (10.5, 9.5), (9, 8), (10.5, 9.5), (9, 10.5), (10.5, 9.5))


def _gear(painter: QPainter) -> None:
    painter.drawEllipse(QRectF(5, 5, 6, 6))
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        _polyline(painter,
                  (8 + 4.4 * math.cos(rad), 8 + 4.4 * math.sin(rad)),
                  (8 + 6.6 * math.cos(rad), 8 + 6.6 * math.sin(rad)))


def _collapse(painter: QPainter) -> None:
    _polyline(painter, (4, 6), (8, 10), (12, 6))


_RECIPES = {
    'pencil': _pencil, 'eraser': _eraser, 'line': _line, 'rectangle': _rectangle,
    'fill': _fill, 'select': _select, 'copy': _copy, 'cut': _cut, 'paste': _paste,
    'undo': _undo, 'redo': _redo, 'save': _save, 'open': _open,
    'export-bin': _export_bin, 'export-h': _export_h, 'invert': _invert,
    'flip-h': _flip_h, 'flip-v': _flip_v, 'rotate': _rotate, 'crop': _crop,
    'clear': _clear, 'text': _text, 'generate': _generate, 'font': _font,
    'zoom-fit': _zoom_fit, 'gear': _gear, 'collapse': _collapse,
}

_FALLBACK = _rectangle


def icon_names() -> tuple[str, ...]:
    return tuple(_RECIPES)


def studio_icon(name: str, color: str, size: int = 16) -> QIcon:
    """Render the named recipe in ``color`` at ``size`` device pixels."""
    size = max(8, int(size))
    scale = size / ICON_SIZE
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(scale, scale)
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    recipe = _RECIPES.get(str(name or '').strip().lower(), _FALLBACK)
    recipe(painter)
    painter.end()
    return QIcon(pixmap)
