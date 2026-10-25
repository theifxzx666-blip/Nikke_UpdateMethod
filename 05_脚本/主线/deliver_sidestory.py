# -*- coding: utf-8 -*-
"""番外篇插画归集：当期那一篇 → 交付目录 + 一览图 + 清单。

只处理当期（GINGERBREAD HOUSE / side_06）。往期 5 篇的键位在
out/sidestory_cg/00_往期_仅列位置.tsv 里，不落盘。
"""
import csv
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path(r"D:\Codex\临时\nikke_intl_20261029\out\sidestory_cg\side_06")
DST = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\05_主线_47-48章\04_剧情文本\番外篇\插画_GINGERBREAD HOUSE")

SIDE = 6
TITLE = "GINGERBREAD HOUSE"
ONLINE = "2026-10-08"


def key_num(p):
    """eventscene_side_06_03_2 → (3, 2)，用于排序与编号。"""
    m = re.search(r"side_06_(\d+)(?:_(\d+))?__", p.name)
    if not m:
        return (999, 999)
    return (int(m.group(1)), int(m.group(2) or 0))


def main():
    DST.mkdir(parents=True, exist_ok=True)
    files = sorted(SRC.glob("*.png"), key=key_num)
    print(f"{len(files)} 张")

    rows = []
    for i, p in enumerate(files, 1):
        seg, seq = key_num(p)
        # 原文件名 eventscene_side_06_03_2__EventScene_Side_06_03_2.png
        tex = p.stem.split("__")[-1]
        new = f"{i:02d}_段{seg:02d}" + (f"_{seq}" if seq else "") + f"_{tex}.png"
        dst = DST / new
        shutil.copy2(p, dst)
        im = Image.open(p)
        rows.append([f"{i:02d}", f"段 {seg:02d}" + (f" / {seq}" if seq else ""),
                     tex, f"{im.size[0]}x{im.size[1]}",
                     f"{p.stat().st_size/1048576:.2f} MB", new])

    # 清单
    tsv = DST / "00_插画清单.tsv"
    with tsv.open("w", encoding="utf-8-sig") as f:
        f.write(f"# 番外篇 · {TITLE}（第 {SIDE:02d} 篇）· 2026-10-08 维护后实装\n")
        f.write("# 只采当期这一篇；往期 5 篇未落盘（见 out/sidestory_cg/00_往期_仅列位置.tsv）\n")
        f.write("序号\t段\t贴图名\t尺寸\t体积\t文件\n")
        for r in rows:
            f.write("\t".join(r) + "\n")

    # 一览图：4 列
    if files:
        COLS, TH, PAD, LAB = 4, 360, 10, 34
        n = len(files)
        rn = (n + COLS - 1) // COLS
        W = COLS * (TH + PAD) + PAD
        H = rn * (TH + LAB + PAD) + PAD + 76
        sheet = Image.new("RGB", (W, H), (14, 17, 22))
        d = ImageDraw.Draw(sheet)
        f_h = ImageFont.truetype(r"C:/Windows/Fonts/msyh.ttc", 26)
        f_l = ImageFont.truetype(r"C:/Windows/Fonts/msyh.ttc", 15)
        d.text((PAD + 6, 20), f"{TITLE} · 番外篇插画（{n} 张 · 2048×2048）",
               font=f_h, fill=(232, 238, 246))
        d.text((PAD + 6, 52), f"第 {SIDE:02d} 篇 · 2026-10-08 实装 · 键族 eventscene_side_06_*",
               font=f_l, fill=(122, 132, 150))
        for i, (p, r) in enumerate(zip(files, rows)):
            c, rr = i % COLS, i // COLS
            x = PAD + c * (TH + PAD)
            y = 76 + PAD + rr * (TH + LAB + PAD)
            im = Image.open(p).convert("RGB")
            im.thumbnail((TH, TH), Image.LANCZOS)
            ox = x + (TH - im.width) // 2
            oy = y + (TH - im.height) // 2
            sheet.paste(im, (ox, oy))
            d.rectangle([x, y, x + TH, y + TH], outline=(38, 44, 54))
            d.text((x + 2, y + TH + 6), r[1], font=f_l, fill=(214, 222, 233))
            d.text((x + 2, y + TH + 20), f"{r[3]}  {r[4]}", font=f_l, fill=(110, 120, 136))
        sheet.save(DST / "00_一览.png")
        print(f"一览图 {sheet.size[0]}×{sheet.size[1]}")

    print(f"→ {DST}")


if __name__ == "__main__":
    main()
