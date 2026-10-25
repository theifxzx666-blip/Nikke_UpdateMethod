# -*- coding: utf-8 -*-
"""总览图（14 种）+ 两个 BOSS 的双阶段对照图。立绘已统一 1200×1400 画布，直接等比缩放即可。"""
import sqlite3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(r"D:/Codex/Nikke/Nikke_Skills/版本更新/03_历史/20260813_国际服/05_主线_47-48章/07_关卡莱彻")
LIB = BASE / "立绘"
DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")

FONT = r"C:/Windows/Fonts/msyhbd.ttc"
F = lambda s: ImageFont.truetype(FONT, s)

ITEMS = [
    ("01_指环_xmg001.png", "指环", "xmg001 · 关卡"),
    ("02_海马_xma003.png", "海马", "xma003 · 关卡"),
    ("03_太阳_xeg006.png", "太阳", "xeg006 · 关卡 + 大地图"),
    ("04_倒吊者_xea003.png", "倒吊者", "xea003 · 关卡 + 大地图"),
    ("05_三体_eea002.png", "三体", "eea002 · 关卡"),
    ("06_双尾_meg006.png", "双尾", "meg006 · 关卡"),
    ("07_穿刺_mea001.png", "穿刺", "mea001 · 关卡"),
    ("08_陆蟹_mmg005.png", "陆蟹", "mmg005 · 关卡"),
    ("09_太空人_xea002.png", "太空人", "xea002 · 大地图"),
    ("10_狂笑_xea004.png", "狂笑", "xea004 · 大地图"),
    ("11_信差_xmg002.png", "信差", "xmg002 · 大地图"),
    ("12_肋骨_xmg003.png", "肋骨", "xmg003 · 大地图"),
    ("13_安尼希利奥_xba003_1阶段.png", "安尼希利奥", "xba003 · 关底 BOSS 1 阶段"),
    ("14_莉贝雷利奥躯体_eba002_1阶段.png", "莉贝雷利奥躯体", "eba002 · 关底 BOSS 1 阶段"),
]

def sheet():
    COLS, CW, CH = 5, 300, 380
    ROWS = (len(ITEMS) + COLS - 1) // COLS
    PAD, HEAD = 22, 96
    W = COLS * CW + PAD * 2
    H = HEAD + ROWS * CH + PAD
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.text((PAD, 18), "第 47 / 48 章 莱彻总览 · 14 种", font=F(34), fill=(20, 20, 26))
    d.text((PAD, 58), "关卡内 8 种 + 大地图 6 种（太阳 / 倒吊者共有，去重 12）+ 关底 BOSS 2 种 ｜ 全部为客户端 3D 模型正面正交渲染",
           font=F(17), fill=(110, 110, 120))
    for i, (fn, zh, sub) in enumerate(ITEMS):
        r, c = divmod(i, COLS)
        x0, y0 = PAD + c * CW, HEAD + r * CH
        p = LIB / fn
        if not p.exists():
            d.text((x0 + 10, y0 + 10), f"缺 {fn}", font=F(16), fill=(200, 0, 0)); continue
        im = Image.open(p).convert("RGBA")
        box_w, box_h = CW - 16, CH - 78
        s = min(box_w / im.width, box_h / im.height)
        im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        canvas.paste(im2, (x0 + (CW - im2.width) // 2, y0 + (box_h - im2.height) // 2), im2)
        tw = d.textlength(zh, font=F(24))
        d.text((x0 + (CW - tw) / 2, y0 + box_h + 2), zh, font=F(24), fill=(24, 24, 28))
        tw2 = d.textlength(sub, font=F(15))
        d.text((x0 + (CW - tw2) / 2, y0 + box_h + 32), sub, font=F(15), fill=(120, 120, 130))
    out = BASE / "莱彻总览_14种.png"
    canvas.save(out)
    print("->", out.name, canvas.size)

def boss_pair():
    pairs = [
        ("13", "安尼希利奥", "xba003（型号 451003 · 暴君级 · 异化者）", "安尼希利奥_双阶段对照.png"),
        ("14", "莉贝雷利奥躯体", "eba002（型号 251016 · H.S.T.A.）", "莉贝雷利奥躯体_双阶段对照.png"),
    ]
    for idx, zh, sub, outname in pairs:
        fs = sorted(LIB.glob(f"{idx}_{zh}_*_*阶段.png"))
        if len(fs) < 2:
            print("  !! 缺阶段图", idx); continue
        CW, CH = 620, 760
        W, H = CW * len(fs) + 44, CH + 118
        canvas = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(canvas)
        d.text((22, 16), f"{zh} · 第 {idx} 号关底 BOSS", font=F(30), fill=(20, 20, 26))
        d.text((22, 54), sub, font=F(17), fill=(110, 110, 120))
        for i, p in enumerate(fs):
            im = Image.open(p).convert("RGBA")
            s = min((CW - 16) / im.width, (CH - 56) / im.height)
            im2 = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
            x0 = 22 + i * CW
            canvas.paste(im2, (x0 + (CW - im2.width) // 2, 92), im2)
            tag = "1 阶段" if "1阶段" in p.name else "2 阶段"
            tw = d.textlength(tag, font=F(22))
            d.text((x0 + (CW - tw) / 2, H - 34), tag, font=F(22), fill=(30, 30, 36))
        out = BASE / outname
        canvas.save(out)
        print("->", outname, canvas.size)

if __name__ == "__main__":
    sheet()
    boss_pair()
