from __future__ import annotations

from pathlib import Path
import re
import struct
import subprocess
import sys
import zlib


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"


def _png(path: Path, rows: list[bytes], width: int) -> None:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, len(rows), 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOLS / "CHECK_SMOKE_SCREENSHOT.py"), str(path)],
        capture_output=True, text=True, check=False,
    )


def test_blank_screenshot_fails(tmp_path: Path) -> None:
    shot = tmp_path / "blank.png"
    _png(shot, [b"\x20\x20\x20" * 1200 for _ in range(700)], 1200)
    result = _check(shot)
    assert result.returncode == 1
    assert "mostly one colour" in result.stderr


def test_recorded_installed_screenshots_pass() -> None:
    shots = sorted((ROOT / "docs" / "rewrite" / "g5").glob("installed-*.png"))
    assert shots
    for shot in shots:
        result = _check(shot)
        assert result.returncode == 0, result.stderr


def test_package_version_matches_workspace() -> None:
    result = subprocess.run(
        [sys.executable, str(TOOLS / "PACKAGE_RUST_RELEASE.py"), "--print-version"],
        capture_output=True, text=True, check=True,
    )
    cargo = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    match = re.search(r'^\[workspace\.package\][^\[]*?^version\s*=\s*"([^"]+)"', cargo, re.MULTILINE | re.DOTALL)
    assert match and result.stdout.strip() == match.group(1)
