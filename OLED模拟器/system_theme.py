from __future__ import annotations

try:
    from PySide6.QtCore import QObject, Signal, Qt, Slot
    from PySide6.QtGui import QGuiApplication
    PYSIDE_AVAILABLE = True
except Exception:  # pragma: no cover
    PYSIDE_AVAILABLE = False

if PYSIDE_AVAILABLE:
    class SystemThemeProvider(QObject):
        """Application appearance source with explicit signal ownership."""
        themeChanged = Signal(bool)

        def __init__(self, parent=None):
            super().__init__(parent)
            app = QGuiApplication.instance()
            self._fallback_dark = False
            self._hints = app.styleHints() if app is not None else None
            if app is not None:
                try:
                    self._fallback_dark = app.palette().color(app.palette().Window).value() < 128
                except Exception:
                    self._fallback_dark = False
            if self._hints is not None and hasattr(self._hints, 'colorSchemeChanged'):
                self._hints.colorSchemeChanged.connect(self._on_color_scheme_changed)

        @Slot()
        def _on_color_scheme_changed(self, *_):
            self.themeChanged.emit(self.is_dark())

        def close(self):
            hints = self._hints
            self._hints = None
            if hints is not None and hasattr(hints, 'colorSchemeChanged'):
                try:
                    hints.colorSchemeChanged.disconnect(self._on_color_scheme_changed)
                except (RuntimeError, TypeError):
                    pass

        def is_dark(self) -> bool:
            app = QGuiApplication.instance()
            if app is None:
                return self._fallback_dark
            hints = app.styleHints()
            if hasattr(hints, 'colorScheme'):
                try:
                    return hints.colorScheme() == Qt.ColorScheme.Dark
                except Exception:
                    pass
            return self._fallback_dark
else:
    class SystemThemeProvider:
        def __init__(self, *a, **k): self._fallback_dark = False
        def is_dark(self): return False
        def close(self): return None
