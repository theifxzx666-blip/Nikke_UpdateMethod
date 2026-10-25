# -*- coding: utf-8 -*-
"""把 8 张莱彻立绘拼成一张总览图（带分级/属性/体量/出现章节标注）。

立绘本身来自 render_monster_standee.py（绑定姿态正交渲染），这里只做排版：
按 alpha 真实内容框裁掉多余空白，等比缩放进格子，避免不同体量的模型看起来大小失衡。
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DST = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\05_主线_47-48章\07_关卡莱彻")
ART = DST / "立绘"

FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"

COLS, ROWS = 4, 2
CELL_W, CELL_H = 450, 720
GAP = 12
PAD = 30
HEAD_H = 96

BG = (247, 247, 249)
PANEL = (255, 255, 255)
LINE = (218, 220, 226)
INK = (28, 30, 34)
SUB = (104, 110, 120)
BOSS_RED = (176, 24, 24)


def font(sz, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, sz)


def read_rows():
    """读 清单.tsv，返回 {立绘文件名: 行字典}。"""
    p = DST / "关卡莱彻_清单.tsv"
    lines = [x for x in p.read_text(encoding="utf-8-sig").splitlines() if x and not x.startswith("#")]
    head = lines[0].split("\t")
    out = {}
    for ln in lines[1:]:
        c = ln.split("\t")
        if len(c) < len(head):
            continue
        d = dict(zip(head, c))
        out[d["立绘文件"]] = d
    return out


def trim(im):
    """按 alpha>8 裁到真实内容框，四周留 2% 呼吸位。"""
    a = im.getchannel("A")
    box = a.point(lambda v: 255 if v > 8 else 0).getbbox()
    if box:
        im = im.crop(box)
    w, h = im.size
    pad = int(max(w, h) * 0.02)
    out = Image.new("RGBA", (w + pad * 2, h + pad * 2), (255, 255, 255, 0))
    out.paste(im, (pad, pad))
    return out


def fit(im, box_w, box_h):
    w, h = im.size
    s = min(box_w / w, box_h / h)
    return im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)


def main():
    meta = read_rows()
    names = sorted(ART.glob("*_立绘.png"))
    if not names:
        print("没有立绘")
        return 1

    W = PAD * 2 + COLS * CELL_W + (COLS - 1) * GAP
    H = HEAD_H + PAD + ROWS * CELL_H + (ROWS - 1) * GAP + PAD
    canvas = Image.new("RGB", (W, H), BG)
    dr = ImageDraw.Draw(canvas)

    dr.text((PAD, 26), "第 47 / 48 章关卡莱彻 · 立绘总览", font=font(34, True), fill=INK)
    dr.text((PAD, 68), f"{len(names)} 种 · 绑定姿态正交渲染 · 客户端内为 3D 模型，无 2D 立绘",
            font=font(17), fill=SUB)

    img_h = 520          # 立绘区高度
    for i, p in enumerate(names):
        r, c = divmod(i, COLS)
        x0 = PAD + c * (CELL_W + GAP)
        y0 = HEAD_H + PAD + r * (CELL_H + GAP)
        d = meta.get(p.name, {})

        dr.rounded_rectangle([x0, y0, x0 + CELL_W, y0 + CELL_H], 14, fill=PANEL, outline=LINE, width=2)
        im = fit(trim(Image.open(p).convert("RGBA")), CELL_W - 40, img_h)
        canvas.paste(im, (x0 + (CELL_W - im.width) // 2, y0 + 22), im)

        name = (d.get("预制体") or p.stem.replace("_立绘", ""))
        is_boss = d.get("BOSS") == "是"
        ty = y0 + img_h + 44
        dr.text((x0 + 22, ty), name, font=font(27, True), fill=BOSS_RED if is_boss else INK)

        body = (d.get("型号等级/体量") or "?/?").split("/")[-1]
        tag = "%s · %s" % (d.get("强度分级", "?"), body)
        dr.text((x0 + 22, ty + 40), tag, font=font(18), fill=SUB)

        l2 = "属性 %s ｜ 生成型 %s" % (d.get("属性", "?"), d.get("生成型", "?"))
        dr.text((x0 + 22, ty + 68), l2, font=font(18), fill=SUB)

        def _n(k):
            v = d.get(k, "?")
            return "无" if v in ("—", "", None) else f"{v} 关"
        l3 = "47章 %s ｜ 48章 %s" % (_n("47章关数"), _n("48章关数"))
        dr.text((x0 + 22, ty + 96), l3, font=font(18), fill=SUB)

        if is_boss:
            dr.rounded_rectangle([x0 + CELL_W - 92, y0 + 16, x0 + CELL_W - 16, y0 + 52], 8, fill=BOSS_RED)
            dr.text((x0 + CELL_W - 80, y0 + 22), "BOSS", font=font(18, True), fill=(255, 255, 255))

    out = DST / "关卡莱彻_总览.png"
    tmp = Path(r"D://Codex//临时//_sheet_tmp.png")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(tmp)          # 目标常被资源管理器/预览占用，先落临时盘再替换
    os.replace(tmp, out)
    print("->", out, canvas.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
