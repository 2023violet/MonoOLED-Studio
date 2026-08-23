from __future__ import annotations


def canvas_widget_size(width: int, height: int, zoom: int, *, margin: int = 18) -> tuple[int, int]:
    width = int(width); height = int(height); zoom = int(zoom); margin = int(margin)
    if width <= 0 or height <= 0 or zoom <= 0 or margin < 0:
        raise ValueError('canvas dimensions/zoom must be positive and margin non-negative')
    return width * zoom + margin * 2, height * zoom + margin * 2


def fit_integer_zoom(
    width: int,
    height: int,
    *,
    viewport_w: int,
    viewport_h: int,
    margin: int = 18,
    min_zoom: int = 1,
    max_zoom: int = 16,
) -> int:
    width = int(width); height = int(height)
    usable_w = max(1, int(viewport_w) - 2 * int(margin))
    usable_h = max(1, int(viewport_h) - 2 * int(margin))
    by_w = usable_w // max(1, width)
    by_h = usable_h // max(1, height)
    return max(int(min_zoom), min(int(max_zoom), max(1, min(by_w, by_h))))
