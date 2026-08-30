from __future__ import annotations
from pathlib import Path
from PIL import Image
from assets import load_bitmap


def convert_bitmap(source: str | Path, target: str | Path) -> Path:
    """Write a canonical OLED preview asset: black background, white lit pixels."""
    asset = load_bitmap(source)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new('L', (asset.width, asset.height), 0)
    px = image.load()
    for y, row in enumerate(asset.pixels):
        for x, value in enumerate(row):
            px[x, y] = 255 if value else 0
    image.save(target, format='PNG')
    return target


def convert_directory(source_dir: str | Path, target_dir: str | Path) -> list[Path]:
    source_dir, target_dir = Path(source_dir), Path(target_dir)
    outputs=[]
    for src in sorted(source_dir.rglob('*')):
        if src.is_file() and src.suffix.lower() in {'.png','.bmp'}:
            rel=src.relative_to(source_dir).with_suffix('.png')
            outputs.append(convert_bitmap(src, target_dir/rel))
    return outputs
