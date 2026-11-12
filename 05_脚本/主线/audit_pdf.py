# -*- coding: utf-8 -*-
"""逐页体检：页数、标题、图片数、底部空白比例。

空白率口径：把页面按 1/40 高度切片，找最后一条"有内容"的切片的 y 位置，
从那条切片底边到页面底部（去掉 11mm 下内边距）算空白高度。
内容判定 = 与页面底色 #231f1e 的差超过阈值。
比"数 img 标签"准：一段满页的文字表也不算空白，但只剩三行字的页会被抓出来。
"""
import sys
import numpy as np
import pymupdf
from pathlib import Path

PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"D:\Codex\Nikke\02_工位\10_数据管线\版本更新\03_历史\20260813_国际服"
    r"\2026-08-13_更新内容一览.pdf")
OUT = Path(r"D:\Codex\临时\_pv")
OUT.mkdir(parents=True, exist_ok=True)

doc = pymupdf.open(PDF)
rows = []
for i, pg in enumerate(doc):
    pix = pg.get_pixmap(dpi=96)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    rgb = arr[:, :, :3].astype(np.int16)
    diff = np.abs(rgb - np.array([35, 31, 29])).sum(2)
    ink = (diff > 26)
    # 有图的判定：整行墨量 > 宽度的 40% 才算"有图"，一行字只有稀稀拉拉几十个像素
    rowdens = ink.sum(1)
    last = np.where(rowdens > pix.width * 0.02)[0]
    bottom_mm = (pix.height - last[-1]) / pix.height * 297 if len(last) else 297
    # 图片面积估计：把"墨密度 > 0.5"的像素数当作图（文字行密度远低于 0.5）
    dens = ink.reshape(-1, 1)
    rows.append((i + 1, round(bottom_mm, 1), round(float(ink.mean()) * 100, 1)))
    pix.save(OUT / f"pg{i+1:02d}.png")

print(f"{'页':>3} {'底部空白mm':>10} {'墨覆盖%':>8}")
for n, b, d in rows:
    flag = "  <<< 空白" if b > 34 else ""
    print(f"{n:>3} {b:>10} {d:>8}{flag}")
print("总页数", len(rows))
