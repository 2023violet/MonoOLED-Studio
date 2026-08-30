from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def build_thumbnail_wall(images, output: str | Path, *, columns: int=4, scale: int=4, gap: int=16, label_height: int=18) -> Path:
    paths=[Path(p) for p in images]
    if not paths: raise ValueError('thumbnail wall requires at least one image')
    if columns<1 or scale<1: raise ValueError('columns/scale must be positive')
    opened=[]
    try:
        for p in paths:
            opened.append(Image.open(p).convert('1'))
        cell_w=max(im.width for im in opened)*scale
        cell_h=max(im.height for im in opened)*scale+label_height
        rows=(len(opened)+columns-1)//columns
        canvas=Image.new('RGB',(columns*cell_w+(columns+1)*gap,rows*cell_h+(rows+1)*gap),(245,245,247))
        draw=ImageDraw.Draw(canvas)
        for i,(p,im) in enumerate(zip(paths,opened)):
            row,col=divmod(i,columns); x=gap+col*(cell_w+gap); y=gap+row*(cell_h+gap)
            thumb=im.resize((im.width*scale,im.height*scale),Image.Resampling.NEAREST).convert('RGB')
            # production preview remains black background / white lit
            canvas.paste(thumb,(x,y))
            draw.text((x,y+cell_h-label_height+2),p.stem,fill=(29,29,31))
        output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); canvas.save(output)
        return output
    finally:
        for im in opened: im.close()
