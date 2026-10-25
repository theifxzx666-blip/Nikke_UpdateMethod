# -*- coding: utf-8 -*-
"""在单阵位战斗图上标出「全部」多判充能点（每个阵位最多 6 个）。

与 mark_charge.py 的区别：原脚本只标峰值那一个点；本脚本读 充能点位_多判.tsv，
把该阵位排进前 6 的点位全部标出来，并在左上角给一张对照小表。

准星像素来自 tsv（该阵位相机 fov=60° / 1600×900 投影），与重渲画面同源，直接落点。
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import render_battle_scene as R

BASE = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
            r"\05_主线_47-48章\06_战斗场景还原")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out")
DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
TSV = BASE / "充能点位_多判.tsv"
MAXPT = 6


def font(sz, bold=False):
    for p in ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
              "C:/Windows/Fonts/msyh.ttc"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            continue
    return ImageFont.load_default()


def load_points():
    per = defaultdict(list)
    with TSV.open(encoding="utf-8-sig") as f:
        rows = [r for r in f if not r.startswith("#")]
    rd = csv.DictReader(rows, delimiter="\t")
    for r in rd:
        if not r.get("战场"):
            continue
        per[(r["战场"], int(r["阵位"]))].append(r)
    for k in per:
        per[k].sort(key=lambda r: (-int(r["段数"]), -int(r["1°窗口稳定段数"]), float(r["最近命中距离(m)"])))
    return per


def draw_pt(d, x, y, idx, seg, r=16):
    col = (255, 72, 72) if seg >= 3 else (255, 158, 60)
    d.ellipse([x - r, y - r, x + r, y + r], outline=col, width=3)
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        d.line([(x + dx * (r + 2), y + dy * (r + 2)), (x + dx * (r + 10), y + dy * (r + 10))],
               fill=col, width=3)
    d.ellipse([x - 11, y - 11, x + 11, y + 11], fill=(18, 20, 28))
    d.ellipse([x - 11, y - 11, x + 11, y + 11], outline=col, width=2)
    f = font(17, True)
    tw = d.textlength(str(idx), font=f)
    d.text((x - tw / 2, y - 10), str(idx), font=f, fill=(255, 255, 255))


def legend(cv, pts, k):
    d = ImageDraw.Draw(cv, "RGBA")
    pad, lh = 12, 26
    w, h = 470, pad * 2 + 30 + lh * len(pts)
    x0, y0 = 18, 96
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=(10, 13, 20, 205), outline=(64, 78, 102), width=1)
    d.text((x0 + pad, y0 + pad - 2), "阵位 %d · 多判点全表（单发最多穿 %d 件）" % (
        k, max(int(p["段数"]) for p in pts)), font=font(17, True), fill=(226, 234, 246))
    for i, p in enumerate(pts, 1):
        ty = y0 + pad + 30 + lh * (i - 1)
        d.text((x0 + pad, ty), "%d" % i, font=font(15, True), fill=(255, 255, 255))
        d.text((x0 + pad + 20, ty), "yaw %s  pitch %s" % (p["yaw(°)"], p["pitch(°)"]),
               font=font(15), fill=(198, 210, 228))
        d.text((x0 + pad + 232, ty), "%s段 / %s点" % (p["段数"], p["单发充能点数"]),
               font=font(15), fill=(255, 190, 150) if int(p["段数"]) < 3 else (255, 120, 120))
        d.text((x0 + pad + 330, ty), p["稳定性"], font=font(15),
               fill=(150, 210, 170) if p["稳定性"] == "稳" else (210, 190, 150))
    return cv


def main():
    per = load_points()
    W = 1600
    H = 900
    done = 0
    for tag in ("sbg_001", "sbg_002", "sbg_003"):
        A = __import__("json").loads((OUT / f"asm_{tag}.json").read_text(encoding="utf-8"))
        tmap = A.get("textures") or {}
        need = {tmap[str(p["tex"])] for p in A["props"] if str(p.get("tex")) in tmap}
        TEX = R.load_tex(str(DEV / f"{tag}.bundle"), need)
        SKY = R.load_sky(str(DEV / f"{tag}.bundle"))
        label = tag.replace("sbg_", "sbg_cityforest_")
        for k in range(1, 6):
            pts = per.get((tag, k), [])
            cv = R.render(A, TEX, k - 1, W, 60, label,
                          " ｜ 阵位 %d · 多判点 %d 个（最多标 %d）" % (k, len(pts), MAXPT), SKY)
            if pts:
                legend(cv, pts, k)
                d = ImageDraw.Draw(cv, "RGBA")
                for i, p in enumerate(pts, 1):
                    x, y = (float(v) for v in p["准星像素(x,y)"].split(","))
                    if 0 <= x < W and 0 <= y < H:
                        draw_pt(d, x, y, i, int(p["段数"]))
            dst = BASE / f"{label}_s{k}.png"
            tmp = Path(r"D://Codex//临时//_charge"); tmp.mkdir(parents=True, exist_ok=True)
            t = tmp / dst.name
            cv.save(t)
            import shutil
            shutil.move(str(t), str(dst))
            done += 1
            print(f"-> {dst.name}  点位 {len(pts)}")
    print("done", done)


if __name__ == "__main__":
    main()
