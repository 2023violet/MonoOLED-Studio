#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
font2png.py —— 点阵字库转 PNG 工具

把 C 语言字模数组（如 8x16 ASCII 字库、OLED/液晶取模数据）转换成每个字符单独的 PNG 图片。
纯 Python 标准库实现；仅 --ttf 模式需要可选的 Pillow。

输出文件名自动携带「尺寸_字体」前缀，避免不同批次图片混淆：
    8x16_ascii_8x16_033_065_A.png
    8x16_ascii_8x16_sheet.png

支持：
  - 任意宽 x 高（8x8 / 8x16 / 16x16 / 12x9 ...）
  - 任意字符集（默认完整 95 个可打印 ASCII）
  - 列行式/行列式取模、高位在前(MSB)/低位在前(LSB)、整页序/逐列 interleaved
  - 缩放倍数、前景色/背景色、反色
  - 总览大图：每个字符带边框和序号标注，方便定位 data[N]
  - --compare 回归对比：与参考 PNG 目录逐像素比对并输出差异高亮图
  - 可选 TTF 模式：任意字号、强制等宽(--mono-w)、垂直对齐(--align)、导出 C 数组

常用示例：
  python font2png.py -i ascii8x16.h -w 8 -H 16
  python font2png.py -i ascii8x16.h -w 8 -H 16 --chars "0123456789" -s 12 --sheet
  python font2png.py -i font.h -w 12 -H 9 --order row --lsb --invert
  python font2png.py --data "0xFC,0x66,..." -w 8 -H 8 --chars "A"
  python font2png.py -i ascii8x16.h -w 8 -H 16 --compare ref_png_dir
  python font2png.py --ttf C:/Windows/Fonts/consola.ttf --size 14 -w 8 -H 16 --align bottom --emit-c myfont.h
"""
import argparse
import math
import os
import re
import struct
import sys
import zlib

NAMED_COLORS = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "gray": (128, 128, 128),
}

SAFE_NAMES = {
    " ": "space", "!": "exclam", '"': "dquote", "#": "hash", "$": "dollar",
    "%": "percent", "&": "amp", "'": "squote", "(": "lparen", ")": "rparen",
    "*": "star", "+": "plus", ",": "comma", "-": "minus", ".": "dot",
    "/": "slash", ":": "colon", ";": "semicolon", "<": "lt", "=": "equal",
    ">": "gt", "?": "question", "@": "at", "[": "lbracket", "\\": "backslash",
    "]": "rbracket", "^": "caret", "_": "underscore", "`": "grave",
    "{": "lbrace", "|": "pipe", "}": "rbrace", "~": "tilde",
}

FONT3X5 = {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", "###", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", "..#", "..#"),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
}


def parse_color(s):
    s = s.strip().lower()
    if s in NAMED_COLORS:
        return NAMED_COLORS[s]
    m = re.fullmatch(r"#?([0-9a-f]{6})", s)
    if m:
        v = int(m.group(1), 16)
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    m = re.fullmatch(r"(\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})", s)
    if m:
        return tuple(min(255, int(x)) for x in m.groups())
    raise ValueError(f"无法识别的颜色: {s}")


def sanitize_tag(s):
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_") or "font"


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    return text


ARRAY_HEAD_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])+\s*=\s*\{")
NUM_RE = re.compile(r"0[xX][0-9A-Fa-f]+|\d+")


def extract_arrays(text):
    text = strip_comments(text)
    result = []
    for m in ARRAY_HEAD_RE.finditer(text):
        name = m.group(1)
        i, depth = m.end(), 1
        while i < len(text) and depth:
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        data = [int(n, 0) & 0xFF for n in NUM_RE.findall(text[m.end():i - 1])]
        if data:
            result.append((name, data))
    return result


def bytes_per_char(w, h, order):
    if order == "col":
        return w * max(1, (h + 7) // 8)
    return ((w + 7) // 8) * h


def decode_glyph(data, off, w, h, order="col", pages="seq", msb=True):
    px = [[0] * w for _ in range(h)]

    def bit(b, k):
        return (b >> (7 - k)) & 1 if msb else (b >> k) & 1

    idx = off
    if order == "col":
        npages = max(1, (h + 7) // 8)
        if pages == "interleave" and npages > 1:
            for x in range(w):
                for p in range(npages):
                    b = data[idx]
                    idx += 1
                    for k in range(8):
                        y = p * 8 + k
                        if y < h:
                            px[y][x] = bit(b, k)
        else:
            for p in range(npages):
                for x in range(w):
                    b = data[idx]
                    idx += 1
                    for k in range(8):
                        y = p * 8 + k
                        if y < h:
                            px[y][x] = bit(b, k)
    else:
        bpr = (w + 7) // 8
        for y in range(h):
            for bx in range(bpr):
                b = data[idx]
                idx += 1
                for k in range(8):
                    x = bx * 8 + k
                    if x < w:
                        px[y][x] = bit(b, k)
    return px


def glyph_to_bytes(px, order="col", pages="seq", msb=True):
    h, w = len(px), len(px[0])
    out = []

    def bit(b, k, on):
        return b | (1 << (7 - k) if msb else 1 << k) if on else b

    if order == "col":
        npages = max(1, (h + 7) // 8)

        def col_byte(x, p):
            b = 0
            for k in range(8):
                y = p * 8 + k
                if y < h:
                    b = bit(b, k, px[y][x])
            return b

        if npages == 1 or pages == "seq":
            for p in range(npages):
                for x in range(w):
                    out.append(col_byte(x, p))
        else:
            for x in range(w):
                for p in range(npages):
                    out.append(col_byte(x, p))
    else:
        bpr = (w + 7) // 8
        for y in range(h):
            for bx in range(bpr):
                b = 0
                for k in range(8):
                    x = bx * 8 + k
                    if x < w:
                        b = bit(b, k, px[y][x])
                out.append(b)
    return out


def render_rows(px, scale, fg, bg, invert):
    h, w = len(px), len(px[0])
    on_c, off_c = bytes(fg), bytes(bg)
    rows = []
    for y in range(h * scale):
        sy = y // scale
        row = bytearray()
        src = px[sy]
        for x in range(w * scale):
            row += on_c if src[x // scale] ^ invert else off_c
        rows.append(row)
    return rows


def write_png(path, rows):
    h = len(rows)
    w = len(rows[0]) // 3
    raw = bytearray()
    for r in rows:
        raw.append(0)
        raw += r

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))


def read_png(path):
    with open(path, "rb") as f:
        d = f.read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG 文件")
    pos, idat, ihdr, plte = 8, b"", None, None
    while pos < len(d):
        ln, tag = struct.unpack(">I4s", d[pos:pos + 8])
        payload = d[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", payload)
        elif tag == b"PLTE":
            plte = payload
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break
        pos += 12 + ln
    w, h, depth, ctype, _, _, interlace = ihdr
    if depth != 8 or interlace != 0:
        raise ValueError("仅支持 8bit 非隔行 PNG")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif ft != 0:
            raise ValueError(f"未知 PNG 滤波类型 {ft}")
        out[y * stride:(y + 1) * stride] = line
        prev = line

    def pixel(x, y):
        o = y * stride + x * ch
        if ctype in (2, 6):
            return tuple(out[o:o + 3])
        if ctype in (0, 4):
            v = out[o]
            return (v, v, v)
        idx = out[o]
        return tuple(plte[idx * 3:idx * 3 + 3]) if plte and idx * 3 + 2 < len(plte) else (0, 0, 0)

    return w, h, pixel


def set_px(line, x, color):
    line[x * 3:x * 3 + 3] = color


def draw_text(canvas, x, y, s, color, scale=2):
    cx = x
    for chch in s:
        g = FONT3X5.get(chch)
        if g:
            for ry, r in enumerate(g):
                for rx, v in enumerate(r):
                    if v == "#":
                        for dy in range(scale):
                            line = canvas[y + ry * scale + dy]
                            for dx in range(scale):
                                set_px(line, cx + rx * scale + dx, color)
        cx += 4 * scale


def draw_rect(canvas, x, y, w, h, color):
    for xx in range(x, x + w):
        set_px(canvas[y], xx, color)
        set_px(canvas[y + h - 1], xx, color)
    for yy in range(y + 1, y + h - 1):
        set_px(canvas[yy], x, color)
        set_px(canvas[yy], x + w - 1, color)


def make_sheet(glyphs, scale, fg, bg, invert, gap=6,
               border=(90, 90, 90), label=(170, 170, 170)):
    n = len(glyphs)
    gw = max(len(p[0]) for p in glyphs) * scale
    gh = max(len(p) for p in glyphs) * scale
    header = 14
    cellw, cellh = gw + 2, header + gh + 2
    cols = max(1, min(n, math.ceil(math.sqrt(n))))
    rows_n = math.ceil(n / cols)
    W = cols * cellw + (cols + 1) * gap
    H = rows_n * cellh + (rows_n + 1) * gap
    canvas = [bytearray(bytes(bg) * W) for _ in range(H)]
    for i, px in enumerate(glyphs):
        r, c = divmod(i, cols)
        x0 = gap + c * (cellw + gap)
        y0 = gap + r * (cellh + gap)
        draw_rect(canvas, x0, y0, cellw, cellh, border)
        draw_text(canvas, x0 + 4, y0 + 2, str(i), label, 2)
        sub = render_rows(px, scale, fg, bg, invert)
        oy, ox = y0 + 1 + header, x0 + 1
        for yy, line in enumerate(sub):
            canvas[oy + yy][ox:ox + len(line)] = line
    return canvas


def glyph_filename(size_str, tag, i, ch):
    code = ord(ch)
    name = ch if ch.isalnum() else SAFE_NAMES.get(ch, f"u{code:04X}")
    return f"{size_str}_{tag}_{i:03d}_{code}_{name}.png"


def ttf_glyphs(chars, ttf_path, size, w, h, align="center"):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        sys.exit("TTF 模式需要 Pillow：请先执行  pip install pillow")
    font = ImageFont.truetype(ttf_path, size)
    out = []
    for chch in chars:
        img = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(img)
        bbox = d.textbbox((0, 0), chch, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (w - tw) // 2 - bbox[0]
        if align == "top":
            ty = -bbox[1]
        elif align == "bottom":
            ty = h - bbox[3]
        else:
            ty = (h - th) // 2 - bbox[1]
        d.text((tx, ty), chch, font=font, fill=255)
        out.append([[1 if img.getpixel((x, y)) >= 128 else 0 for x in range(w)] for y in range(h)])
    return out


def emit_c(path, arr_name, chars, glyph_list, order, pages, msb, w, h):
    all_bytes = [glyph_to_bytes(px, order, pages, msb) for px in glyph_list]
    bpc = len(all_bytes[0])
    lines = [
        f"/* {w}x{h} 点阵字库，共 {len(chars)} 个字符，每字符 {bpc} 字节 */",
        f"/* 取模方式：{'列行式' if order == 'col' else '行列式'}，"
        f"{'高位在前 MSB' if msb else '低位在前 LSB'}"
        + (f"，页序 {pages}" if order == "col" and h > 8 else "")
        + " */",
        f"const unsigned char {arr_name}[{len(chars)}][{bpc}] = {{",
    ]
    for ch, bs in zip(chars, all_bytes):
        hexs = ", ".join(f"0x{b:02X}" for b in bs)
        label = ch if ch not in "*/" else ""
        lines.append(f"    {{{hexs}}},  /* {ord(ch):3d} '{label}' */")
    lines.append("};")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_compare(args, chars, glyph_list, size_str, tag, fg, bg, inv, scale):
    refdir = args.compare
    refs = [f for f in os.listdir(refdir) if f.lower().endswith(".png")]
    w, h = args.width, args.height
    matched, diff_list, missing = 0, [], []

    for i, (ch, px) in enumerate(zip(chars, glyph_list)):
        fname = glyph_filename(size_str, tag, i, ch)
        token = f"_{ord(ch)}_"
        cands = sorted(f for f in refs if f == fname or token in f)
        if not cands:
            missing.append((i, ch))
            continue
        try:
            rw, rh, pix = read_png(os.path.join(refdir, cands[0]))
        except Exception as e:
            print(f"警告：无法读取参考图 {cands[0]}: {e}")
            missing.append((i, ch))
            continue
        if rw % w or rh % h or rw // w != rh // h or rw // w == 0:
            print(f"警告：{cands[0]} 尺寸 {rw}x{rh} 与字模 {w}x{h} 不成整数倍，跳过")
            missing.append((i, ch))
            continue
        s = rw // w
        diff_rows = []
        bad = 0
        sub = render_rows(px, scale, fg, bg, inv)
        for y in range(h):
            for x in range(w):
                r, g, b = pix(x * s + s // 2, y * s + s // 2)
                ref_bit = 1 if (r * 299 + g * 587 + b * 114) // 1000 >= 128 else 0
                if args.ref_invert:
                    ref_bit ^= 1
                mine = px[y][x] ^ inv
                block_c = bytes((255, 0, 0)) if mine != ref_bit else (bytes(fg) if mine else bytes(bg))
                bad += mine != ref_bit
                for dy in range(scale):
                    row = bytearray()
                    for dx in range(scale):
                        row += block_c
                    diff_rows.append(row) if x == 0 else diff_rows[y * scale + dy].extend(row)
        if bad:
            diff_list.append((i, ch, bad, cands[0]))
            write_png(os.path.join(args.out, f"{size_str}_{tag}_diff_{i:03d}_{ord(ch)}.png"), diff_rows)
        else:
            matched += 1

    total = len(chars)
    print(f"\n对比结果：一致 {matched}/{total}，有差异 {len(diff_list)}，缺参考图 {len(missing)}")
    for i, ch, bad, ref in diff_list:
        print(f"  x [{i:3d}] '{ch}' 差异像素 {bad} 个（参考 {ref}），差异图已输出")
    for i, ch in missing:
        print(f"  - [{i:3d}] '{ch}' 未找到参考图")
    if diff_list or missing:
        sys.exit(1)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(
        description="点阵字库转 PNG 工具（任意宽高、任意字符集）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    src = ap.add_mutually_exclusive_group()
    src.add_argument("-i", "--input", help="包含 C 字模数组的 .h/.c/.txt 文件")
    src.add_argument("--data", help="直接给出十六进制字模数据，逗号分隔")
    src.add_argument("--ttf", help="改用 TTF 字体文件生成字模（需 Pillow）")
    ap.add_argument("--size", type=int, default=14, help="TTF 渲染字号（像素）")
    ap.add_argument("-w", "--width", type=int, default=8, help="单字符宽度（像素）")
    ap.add_argument("-H", "--height", type=int, default=16, help="单字符高度（像素）")
    ap.add_argument("--mono-w", type=int, metavar="N",
                    help="TTF 模式：强制所有字符按 N 像素宽的等宽格子渲染（默认用 -w）")
    ap.add_argument("--align", choices=["center", "top", "bottom"], default="center",
                    help="TTF 模式：字符在格子内的垂直对齐方式")
    ap.add_argument("--chars", help="字符集字符串，与数组顺序一一对应；默认为 95 个可打印 ASCII")
    ap.add_argument("--chars-file", help="从文本文件读取字符集（忽略换行/空白）")
    ap.add_argument("--array", help="输入文件含多个数组时指定数组名")
    ap.add_argument("--list", action="store_true", help="仅列出输入文件中找到的数组及长度")
    ap.add_argument("--order", choices=["col", "row"], default="col",
                    help="取模方向：col=列行式(OLED 常用)，row=行列式")
    ap.add_argument("--pages", choices=["seq", "interleave"], default="seq",
                    help="高度>8 时页排布：seq=先整页再下一页，interleave=每列各页连续")
    ap.add_argument("--lsb", action="store_true", help="字节内低位在前(LSB)，默认高位在前(MSB)")
    ap.add_argument("-s", "--scale", type=int, default=8, help="放大倍数")
    ap.add_argument("--fg", default="#FFFFFF", help="前景色，如 #FF0000 / red / 255,0,0")
    ap.add_argument("--bg", default="#000000", help="背景色")
    ap.add_argument("--invert", action="store_true", help="反色显示")
    ap.add_argument("-o", "--out", default="png_out", help="输出目录")
    ap.add_argument("--sheet", action="store_true", help="额外输出一张全部字符的总览图（带网格和序号）")
    ap.add_argument("--tag", help="覆盖文件名中的字体标识（默认取数组名/文件名）")
    ap.add_argument("--compare", metavar="DIR",
                    help="回归对比：与参考 PNG 目录逐像素比对，差异处输出红色高亮图")
    ap.add_argument("--ref-invert", action="store_true", help="对比时参考图先反色再比较")
    ap.add_argument("--emit-c", metavar="FILE", help="TTF 模式下同时导出 C 字模数组到指定文件")
    args = ap.parse_args()

    if args.chars_file:
        with open(args.chars_file, "r", encoding="utf-8") as f:
            chars = [c for c in f.read() if not c.isspace()]
    elif args.chars is not None:
        chars = list(args.chars)
    else:
        chars = [chr(c) for c in range(32, 127)]
    if not chars:
        sys.exit("错误：字符集为空")

    w, h = args.width, args.height
    if w <= 0 or h <= 0:
        sys.exit("错误：宽高必须为正整数")

    if args.ttf:
        if args.size <= 12:
            print("[提示] 矢量字体转极小尺寸(<=12px)点阵可能出现断笔/粘连，"
                  "建议使用专业点阵字体(如 ProFont/Terminus) 或生成后用 --compare 校验。")
        if args.mono_w is not None:
            if args.mono_w <= 0:
                sys.exit("错误：--mono-w 必须为正整数")
            w = args.mono_w
        glyph_list = ttf_glyphs(chars, args.ttf, args.size, w, h, args.align)
        tag = sanitize_tag(args.tag or os.path.splitext(os.path.basename(args.ttf))[0])
        if args.emit_c:
            emit_c(args.emit_c, "font_" + f"{w}x{h}", chars, glyph_list,
                   args.order, args.pages, not args.lsb, w, h)
            print(f"已导出 C 数组 -> {args.emit_c}")
    else:
        if args.input:
            with open(args.input, "r", encoding="utf-8", errors="replace") as f:
                arrays = extract_arrays(f.read())
            if not arrays:
                sys.exit(f"错误：{args.input} 中未找到形如 XXX[] = {{...}} 的数组")
            if args.list:
                for name, data in arrays:
                    print(f"{name}: {len(data)} 字节")
                return
            arr_name = None
            if args.array:
                pick = next((d for n, d in arrays if n == args.array), None)
                if pick is None:
                    names = ", ".join(n for n, _ in arrays)
                    sys.exit(f"错误：找不到数组 {args.array}（现有：{names}）")
                arr_name = args.array
            else:
                bpc0 = bytes_per_char(w, h, args.order)
                want = bpc0 * len(chars)
                exact = [d for _, d in arrays if len(d) == want]
                divisible = [d for _, d in arrays if len(d) % bpc0 == 0]
                pick = (exact or divisible or [max(arrays, key=lambda a: len(a[1]))[1]])[0]
                arr_name = next(n for n, d in arrays if d is pick)
            data = pick
            tag = sanitize_tag(args.tag or arr_name
                               or os.path.splitext(os.path.basename(args.input))[0])
        elif args.data:
            data = [int(n, 0) & 0xFF for n in re.findall(r"0[xX][0-9A-Fa-f]+|\d+", args.data)]
            tag = sanitize_tag(args.tag or "data")
        else:
            ap.print_help()
            sys.exit("\n错误：请通过 -i/--data/--ttf 三选一提供字模来源")

        bpc = bytes_per_char(w, h, args.order)
        avail = len(data) // bpc
        if len(data) % bpc != 0:
            print(f"警告：数据长度 {len(data)} 不是每字符 {bpc} 字节的整数倍，多余部分被忽略")
        if avail < len(chars):
            print(f"警告：数据只够 {avail} 个字符，少于字符集的 {len(chars)} 个，只转换前 {avail} 个")
        n = min(avail, len(chars))
        glyph_list = [
            decode_glyph(data, i * bpc, w, h, args.order, args.pages, not args.lsb)
            for i in range(n)
        ]
        chars = chars[:n]

    size_str = f"{w}x{h}"
    fg, bg = parse_color(args.fg), parse_color(args.bg)
    inv = bool(args.invert)
    os.makedirs(args.out, exist_ok=True)

    if args.compare:
        run_compare(args, chars, glyph_list, size_str, tag, fg, bg, inv, args.scale)
        return

    for i, (ch, px) in enumerate(zip(chars, glyph_list)):
        path = os.path.join(args.out, glyph_filename(size_str, tag, i, ch))
        write_png(path, render_rows(px, args.scale, fg, bg, inv))

    if args.sheet:
        sheet = make_sheet(glyph_list, args.scale, fg, bg, inv)
        write_png(os.path.join(args.out, f"{size_str}_{tag}_sheet.png"), sheet)

    print(f"完成：共输出 {len(glyph_list)} 张 PNG -> {os.path.abspath(args.out)}/"
          + ("（含总览图）" if args.sheet else ""))


if __name__ == "__main__":
    main()
