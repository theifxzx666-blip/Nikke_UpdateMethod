# -*- coding: utf-8 -*-
"""剧情插画总览（联系表）：把 47 / 48 章全部剧情插画排成一张图，带编号。

用途：一眼核对某张画面属于哪一章，以及确认有没有漏采。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
            r"\05_主线_47-48章\05_图片资源\剧情插画")


def font(sz, bold=False):
    for p in ((r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def sheet(files, title, cols, cell, dst):
    pad, cap = 12, 34
    rows = (len(files) + cols - 1) // cols
    W = cols * (cell + pad) + pad
    H = rows * (cell + cap + pad) + pad + 44
    im = Image.new("RGB", (W, H), (248, 249, 251))
    d = ImageDraw.Draw(im)
    d.text((pad, 12), title, fill=(20, 24, 32), font=font(19, True))
    for i, f in enumerate(files):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = 44 + r * (cell + cap + pad)
        try:
            t = Image.open(f).convert("RGB")
            t.thumbnail((cell, cell), Image.LANCZOS)
            im.paste(t, (x + (cell - t.width) // 2, y + (cell - t.height) // 2))
        except Exception:
            d.rectangle([x, y, x + cell, y + cell], outline=(220, 60, 60))
        d.rectangle([x, y, x + cell, y + cell], outline=(208, 214, 224))
        d.text((x + 2, y + cell + 8), f.stem, fill=(40, 46, 58), font=font(13))
    im.save(dst, optimize=True)
    print("->", dst.name, im.size)


def main():
    for ch, cols in (("47章", 4), ("48章", 7)):
        d = BASE / ch
        files = sorted(d.glob("*.png"))
        if not files:
            print("!! 空目录", d)
            continue
        sheet(files, f"第 {ch[:-1]} 章 剧情插画总览（{len(files)} 张，原图 2048×2048）",
              cols, 250 if cols == 7 else 330, BASE / f"00_{ch}_总览.png")


if __name__ == "__main__":
    main()
