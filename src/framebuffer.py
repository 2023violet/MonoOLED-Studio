from __future__ import annotations


class FrameBuffer:
    """Logical monochrome framebuffer with deterministic SSD13xx-style VLSB export."""

    def __init__(self, width: int = 128, height: int = 32):
        if width <= 0 or height <= 0:
            raise ValueError("framebuffer dimensions must be positive")
        self.width = int(width)
        self.height = int(height)
        self._rows = [bytearray(self.width) for _ in range(self.height)]

    def _check(self, x: int, y: int) -> None:
        if not isinstance(x, int) or not isinstance(y, int):
            raise TypeError("pixel coordinates must be integers")
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError(f"pixel ({x},{y}) outside {self.width}x{self.height}")

    def set_pixel(self, x: int, y: int, on: bool = True) -> None:
        self._check(x, y)
        self._rows[y][x] = 1 if on else 0

    def get_pixel(self, x: int, y: int) -> int:
        self._check(x, y)
        return int(self._rows[y][x])

    def or_mask(self, mask, x: int, y: int) -> None:
        if not isinstance(x, int) or not isinstance(y, int):
            raise TypeError("mask origin must use integer coordinates")
        for my, row in enumerate(mask):
            for mx, value in enumerate(row):
                if not value:
                    continue
                tx, ty = x + mx, y + my
                if 0 <= tx < self.width and 0 <= ty < self.height:
                    self._rows[ty][tx] = 1

    def to_rows(self) -> list[list[int]]:
        return [list(row) for row in self._rows]

    def to_vlsb(self) -> bytes:
        if self.height % 8 != 0:
            raise ValueError("VLSB export requires height divisible by 8")
        out = bytearray(self.width * (self.height // 8))
        for y, row in enumerate(self._rows):
            page = y // 8
            bit = 1 << (y % 8)
            base = page * self.width
            for x, value in enumerate(row):
                if value:
                    out[base + x] |= bit
        return bytes(out)
