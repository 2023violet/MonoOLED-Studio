#!/usr/bin/env python3
"""Build a Microsoft .res file containing an application icon without rc.exe.

This exists so the cross-compiled native launcher can carry the same icon as the
Qt/PyInstaller application. Windows PyInstaller builds still consume the .ico
file directly through MonoOLEDStudio.spec.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

RT_ICON = 3
RT_GROUP_ICON = 14
LANG_EN_US = 0x0409
MEMORY_FLAGS = 0x1030  # MOVEABLE | PURE | DISCARDABLE


def _align4(data: bytearray) -> None:
    while len(data) % 4:
        data.append(0)


def _ordinal(value: int) -> bytes:
    return struct.pack('<HH', 0xFFFF, value)


def _record(type_id: int, name_id: int, payload: bytes) -> bytes:
    type_bytes = _ordinal(type_id)
    name_bytes = _ordinal(name_id)
    variable = bytearray(type_bytes + name_bytes)
    _align4(variable)
    tail = struct.pack('<IHHII', 0, MEMORY_FLAGS, LANG_EN_US, 0, 0)
    header_size = 8 + len(variable) + len(tail)
    out = bytearray(struct.pack('<II', len(payload), header_size))
    out.extend(variable)
    out.extend(tail)
    assert len(out) == header_size
    out.extend(payload)
    _align4(out)
    return bytes(out)


def build_res(ico_path: Path, output_path: Path) -> Path:
    raw = ico_path.read_bytes()
    reserved, icon_type, count = struct.unpack_from('<HHH', raw, 0)
    if reserved != 0 or icon_type != 1 or count < 1:
        raise ValueError('input is not a Windows ICO file')

    entries = []
    images = []
    for index in range(count):
        off = 6 + index * 16
        width, height, colors, reserved_byte, planes, bpp, size, data_off = struct.unpack_from('<BBBBHHII', raw, off)
        payload = raw[data_off:data_off + size]
        if len(payload) != size:
            raise ValueError('truncated ICO image payload')
        resource_id = index + 1
        entries.append((width, height, colors, reserved_byte, planes, bpp, size, resource_id))
        images.append((resource_id, payload))

    # Null resource header required by .res format.
    output = bytearray(struct.pack('<IIHHHHIHHII', 0, 32, 0xFFFF, 0, 0xFFFF, 0, 0, 0, 0, 0, 0))
    assert len(output) == 32

    for resource_id, payload in images:
        output.extend(_record(RT_ICON, resource_id, payload))

    group = bytearray(struct.pack('<HHH', 0, 1, count))
    for width, height, colors, reserved_byte, planes, bpp, size, resource_id in entries:
        group.extend(struct.pack('<BBBBHHIH', width, height, colors, reserved_byte, planes, bpp, size, resource_id))
    output.extend(_record(RT_GROUP_ICON, 1, bytes(group)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('ico', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    build_res(args.ico, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
