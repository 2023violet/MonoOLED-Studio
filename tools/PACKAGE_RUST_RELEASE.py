"""Assemble the MonoOLED Studio V2 release candidate for the current platform (G5).

Inputs are the release binaries already built by ``cargo build --release``.
Outputs go to ``--out`` (default ``dist-rust/``) together with ``SHA256SUMS``:

* Windows: ``MonoOLED-Studio-<ver>-windows-<arch>.zip``
* macOS:   ``MonoOLED-Studio-<ver>-macos-<arch>.dmg`` (unsigned ``.app``; hdiutil)
* Linux:   ``monooled-studio_<debver>_<arch>.deb`` (dpkg-deb)

Only standard tools of each platform are used; nothing is downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP = 'MonoOLED Studio'
NOTICE = """MonoOLED Studio {version}

MIT License — see LICENSE.

Third-party components are listed with their licences by `cargo deny list`
(policy: deny.toml). The user interface is built with Slint
(https://slint.dev) under the Slint Royalty-free License 2.0; the required
attribution is shown in Help → About.
"""


def version() -> str:
    text = (ROOT / 'Cargo.toml').read_text(encoding='utf-8')
    match = re.search(r'^\[workspace\.package\][^\[]*?^version\s*=\s*"([^"]+)"', text, re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit('workspace version not found in Cargo.toml')
    return match.group(1)


def arch() -> str:
    machine = platform.machine().lower()
    return {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine, machine)


def binaries(target: Path) -> tuple[Path, Path]:
    suffix = '.exe' if sys.platform == 'win32' else ''
    gui, cli = target / f'monooled-studio{suffix}', target / f'mono{suffix}'
    for path in (gui, cli):
        if not path.is_file():
            raise SystemExit(f'missing release binary: {path} (run cargo build --release first)')
    return gui, cli


def write_notice(folder: Path, ver: str) -> None:
    shutil.copy2(ROOT / 'LICENSE', folder / 'LICENSE')
    (folder / 'NOTICE.txt').write_text(NOTICE.format(version=ver), encoding='utf-8')


def package_windows(target: Path, out: Path, ver: str) -> Path:
    gui, cli = binaries(target)
    archive = out / f'MonoOLED-Studio-{ver}-windows-{arch()}.zip'
    stage = out / 'stage-windows' / f'MonoOLED-Studio-{ver}'
    shutil.rmtree(stage.parent, ignore_errors=True)
    stage.mkdir(parents=True)
    shutil.copy2(gui, stage / gui.name)
    shutil.copy2(cli, stage / cli.name)
    write_notice(stage, ver)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                zf.write(path, path.relative_to(stage.parent).as_posix())
    shutil.rmtree(stage.parent)
    return archive


def package_macos(target: Path, out: Path, ver: str) -> Path:
    gui, cli = binaries(target)
    stage = out / 'stage-macos'
    shutil.rmtree(stage, ignore_errors=True)
    bundle = stage / f'{APP}.app' / 'Contents'
    (bundle / 'MacOS').mkdir(parents=True)
    (bundle / 'Resources').mkdir(parents=True)
    shutil.copy2(gui, bundle / 'MacOS' / 'monooled-studio')
    shutil.copy2(cli, bundle / 'MacOS' / 'mono')
    shutil.copy2(ROOT / 'apps' / 'mono-desktop' / 'assets' / 'monooled.icns', bundle / 'Resources' / 'monooled.icns')
    short = ver.split('-')[0]
    (bundle / 'Info.plist').write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>{APP}</string>
  <key>CFBundleDisplayName</key><string>{APP}</string>
  <key>CFBundleIdentifier</key><string>io.github.monooled.studio</string>
  <key>CFBundleExecutable</key><string>monooled-studio</string>
  <key>CFBundleIconFile</key><string>monooled.icns</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{short}</string>
  <key>CFBundleVersion</key><string>{ver}</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
""", encoding='utf-8')
    write_notice(stage, ver)
    os.symlink('/Applications', stage / 'Applications')
    image = out / f'MonoOLED-Studio-{ver}-macos-{arch()}.dmg'
    image.unlink(missing_ok=True)
    subprocess.run(['hdiutil', 'create', '-volname', APP, '-srcfolder', str(stage), '-ov', '-format', 'UDZO', str(image)], check=True)
    shutil.rmtree(stage)
    return image


def package_linux(target: Path, out: Path, ver: str) -> Path:
    gui, cli = binaries(target)
    deb_arch = {'x64': 'amd64', 'arm64': 'arm64'}.get(arch(), arch())
    deb_version = ver.replace('-', '~')  # 2.0.0~rc.1 sorts before 2.0.0
    root = out / 'stage-linux'
    shutil.rmtree(root, ignore_errors=True)
    lib = root / 'usr' / 'lib' / 'monooled-studio'
    lib.mkdir(parents=True)
    shutil.copy2(gui, lib / 'monooled-studio')
    shutil.copy2(cli, lib / 'mono')
    for path in (lib / 'monooled-studio', lib / 'mono'):
        path.chmod(0o755)
    bin_dir = root / 'usr' / 'bin'
    bin_dir.mkdir(parents=True)
    # `/usr/bin/mono` belongs to the Mono runtime; the CLI is installed as monooled-cli.
    os.symlink('../lib/monooled-studio/monooled-studio', bin_dir / 'monooled-studio')
    os.symlink('../lib/monooled-studio/mono', bin_dir / 'monooled-cli')
    apps = root / 'usr' / 'share' / 'applications'
    apps.mkdir(parents=True)
    (apps / 'monooled-studio.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName=MonoOLED Studio\n'
        'Comment=Monochrome OLED design, pixel authoring and firmware array export\n'
        'Exec=monooled-studio %f\nIcon=monooled-studio\nTerminal=false\nCategories=Graphics;Development;\n',
        encoding='utf-8')
    icons = root / 'usr' / 'share' / 'icons' / 'hicolor' / '256x256' / 'apps'
    icons.mkdir(parents=True)
    shutil.copy2(ROOT / 'apps' / 'mono-desktop' / 'assets' / 'monooled.png', icons / 'monooled-studio.png')
    doc = root / 'usr' / 'share' / 'doc' / 'monooled-studio'
    doc.mkdir(parents=True)
    shutil.copy2(ROOT / 'LICENSE', doc / 'copyright')
    (doc / 'NOTICE.txt').write_text(NOTICE.format(version=ver), encoding='utf-8')
    control = root / 'DEBIAN'
    control.mkdir()
    size_kb = sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink()) // 1024
    (control / 'control').write_text(
        f'Package: monooled-studio\nVersion: {deb_version}\nArchitecture: {deb_arch}\n'
        'Maintainer: MonoOLED Studio maintainers <noreply@users.noreply.github.com>\n'
        f'Installed-Size: {size_kb}\n'
        'Depends: libc6, libfontconfig1, libxkbcommon0, libxkbcommon-x11-0, libx11-6, libxcursor1, libxrandr2, libxi6, libgl1, libegl1, libwayland-client0\n'
        'Section: graphics\nPriority: optional\n'
        'Description: Monochrome OLED design and firmware export workbench\n'
        ' Scene Designer, Pixel Studio, Font Lab and the output workbench for 1-bit OLED UIs.\n',
        encoding='utf-8')
    package = out / f'monooled-studio_{deb_version}_{deb_arch}.deb'
    package.unlink(missing_ok=True)
    subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(root), str(package)], check=True)
    shutil.rmtree(root)
    return package


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--target-dir', default=str(ROOT / 'target' / 'release'))
    ap.add_argument('--out', default=str(ROOT / 'dist-rust'))
    args = ap.parse_args()
    target, out = Path(args.target_dir), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ver = version()
    if sys.platform == 'win32':
        artifact = package_windows(target, out, ver)
    elif sys.platform == 'darwin':
        artifact = package_macos(target, out, ver)
    else:
        artifact = package_linux(target, out, ver)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    with (out / 'SHA256SUMS').open('a', encoding='utf-8') as sums:
        sums.write(f'{digest}  {artifact.name}\n')
    print(artifact)
    print(f'sha256 {digest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
