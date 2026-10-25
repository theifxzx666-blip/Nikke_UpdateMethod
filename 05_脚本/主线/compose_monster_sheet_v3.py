# -*- coding: utf-8 -*-
"""14 种莱彻总览：8 种关卡内 + 6 种大地图（去重后 14），关底 BOSS 单独两张附在末尾。"""
import json
import sqlite3
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")
SRC = Path(r"D:/Codex/临时/nikke_intl_20261029/out/monster_standee")
BASE = Path(r"D:/Codex/Nikke/Nikke_Skills/版本更新/03_历史/20260813_国际服/05_主线_47-48章/07_关卡莱彻")
LSS = Path(r"D:/Codex/Nikke/Nikke_Skills/拆包/00_资源库/文本/原始文本库_lss/Locale_Monster.lss")

# 型号 → (文件名, 中文名, 来源)
ITEMS = [
    ("xmg001", "指环", "关卡"),
    ("xma003", "海马", "关卡"),
    ("xeg006", "太阳", "关卡 + 大地图"),
    ("xea003", "倒吊者", "关卡 + 大地图"),
    ("eea002", "三体", "关卡"),
    ("meg006", "双尾", "关卡"),
    ("mea001", "穿刺", "关卡"),
    ("mmg005", "陆蟹", "关卡"),
    ("xea002", "太空人", "大地图"),
    ("xea004", "狂笑", "大地图"),
    ("xmg002", "信差", "大地图"),
    ("xmg003", "肋骨", "大地图"),
]

FONT = None
for f in (r"C:/Windows/Fonts/msyhbd.ttc", r"C:/Windows/Fonts/msyh.ttc", r"C:/Windows/Fonts/simhei.ttf"):
    if Path(f).exists():
        FONT = f
        break
f_big = ImageFont.truetype(FONT, 30) if FONT else ImageFont.load_default()
f_mid = ImageFont.truetype(FONT, 23) if FONT else ImageFont.load_default()
f_sm = ImageFont.truetype(FONT, 17) if FONT else ImageFont.load_default()

CELL_W, CELL_H = 306, 452
COLS = 6
ROWS = (len(ITEMS) + COLS - 1) // COLS
PAD = 18
HEAD = 74

W = COLS * CELL_W + PAD * 2
H = HEAD + ROWS * CELL_H + PAD
canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
d = ImageDraw.Draw(canvas)

d.text((PAD, 18), "第 47 / 48 章莱彻总览 · 12 种（另有 2 种关底 BOSS）", font=f_big, fill=(24, 24, 28, 255))
d.text((PAD, 52), "8 种关卡内 + 6 种大地图，太阳 / 倒吊者两者共有，去重 12 种｜关底 BOSS 另见 关底BOSS_立绘/",
       font=f_sm, fill=(110, 110, 120, 255))

for i, (tag, zh, src) in enumerate(ITEMS):
    r, c = divmod(i, COLS)
    x0 = PAD + c * CELL_W
    y0 = HEAD + r * CELL_H
    img_p = SRC / f"{tag}_立绘.png"
    if not img_p.exists():
        continue
    im = Image.open(img_p).convert("RGBA")
    box_h = CELL_H - 92
    box_w = CELL_W - 26
    s = min(box_w / im.width, box_h / im.height)
    im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    canvas.alpha_composite(im2, (x0 + (CELL_W - im2.width) // 2, y0 + (box_h - im2.height) // 2))
    ty = y0 + box_h + 4
    tw = d.textlength(zh, font=f_mid)
    d.text((x0 + (CELL_W - tw) / 2, ty), zh, font=f_mid, fill=(20, 20, 24, 255))
    sub = f"{tag} · {src}"
    tw2 = d.textlength(sub, font=f_sm)
    d.text((x0 + (CELL_W - tw2) / 2, ty + 30), sub, font=f_sm, fill=(120, 120, 130, 255))

out = BASE / "关卡莱彻_总览_v3.png"
tmp = Path(r"D:/Codex/临时/_sheet_v3.png")
canvas.convert("RGB").save(tmp, quality=95)
import shutil
shutil.move(str(tmp), str(out))
print(f"→ {out.name} {canvas.size}")
