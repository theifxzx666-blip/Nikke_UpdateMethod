# -*- coding: utf-8 -*-
"""
地图还原 v4：把坐标点位叠到重建出来的章节地图上，出一张可直接看的 PNG。

用法
----
python compose_map.py <坐标 tsv> <底图 png> <章节号> <章节中文名> <输出 png> [--title 标题]
"""
import sys, io, json, os
from PIL import Image, ImageDraw, ImageFont

FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_R = r"C:\Windows\Fonts\msyh.ttc"

# 类型 -> (颜色, 图例文字, 优先级)
STYLE = {
    "StageSpawner": ((214, 40, 40), "关卡节点", 3),
    "ItemSpawner": ((240, 160, 20), "宝箱 / 收集品", 2),
    "Door": ((90, 170, 70), "门", 1),
    "Portal": ((60, 120, 220), "传送门", 1),
    "PortalSet": ((60, 120, 220), "传送门组", 1),
    "LevelTrigger": ((150, 90, 200), "关卡触发器", 1),
    "InteractionActionTrigger": ((150, 90, 200), "交互触发器", 1),
    "SquadSpawner": ((20, 150, 160), "队伍出生点", 1),
    "CameraPoint": ((110, 110, 110), "默认镜头点", 0),
}


def load_tsv(path):
    lines = io.open(path, encoding="utf-8-sig").read().splitlines()
    rows = []
    hdr = None
    for ln in lines:
        if ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if hdr is None:
            hdr = parts
            continue
        rows.append(dict(zip(hdr, parts)))
    return rows


def main():
    tsv, base, chap, cname, out = sys.argv[1:6]
    title = None
    if "--title" in sys.argv:
        title = sys.argv[sys.argv.index("--title") + 1]

    meta = json.load(open(base + ".json", encoding="utf-8"))
    x0, z1, sc = meta["x0"], meta["z1"], meta["scale"]
    rows = load_tsv(tsv)

    img = Image.open(base).convert("RGBA")
    W, H = img.size
    # 透明区域垫米色，否则转 RGB 会变黑
    bg = Image.new("RGBA", img.size, (246, 245, 241, 255))
    bg.alpha_composite(img)
    img = bg
    d = ImageDraw.Draw(img)

    f_num = ImageFont.truetype(FONT_B, int(15 * sc / 6))
    f_small = ImageFont.truetype(FONT_R, int(12 * sc / 6))
    f_lg = ImageFont.truetype(FONT_B, int(22 * sc / 6))
    rad = max(11, int(11 * sc / 6))

    def px(x, z):
        return (x - x0) * sc, (z1 - z) * sc

    order = sorted(rows, key=lambda r: STYLE.get(r["class"], ((0, 0, 0), "", 0))[2])

    drawn = {}
    for r in order:
        cls = r["class"]
        if cls not in STYLE:
            continue
        color, _, pri = STYLE[cls]
        x, z = float(r["x"]), float(r["z"])
        cx, cy = px(x, z)
        if not (-20 < cx < W + 20 and -20 < cy < H + 20):
            continue
        if cls == "StageSpawner":
            sid = r.get("stageid") or ""
            try:
                n = int(sid) % 1000
            except ValueError:
                n = 0
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(255, 255, 255), outline=color, width=2)
            t = str(n)
            bb = d.textbbox((0, 0), t, font=f_num)
            d.text((cx - (bb[2] - bb[0]) / 2, cy - (bb[3] - bb[1]) / 2 - 2), t, font=f_num, fill=color)
        elif cls == "ItemSpawner":
            s = rad * 0.55
            d.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], fill=color, outline=(120, 70, 0))
        else:
            s = rad * 0.45
            d.rectangle([cx - s, cy - s, cx + s, cy + s], fill=color, outline=(255, 255, 255))
        drawn[cls] = drawn.get(cls, 0) + 1

    # 标题条
    bar_h = int(54 * sc / 6)
    pad_b = int(34 * sc / 6)
    canvas = Image.new("RGBA", (W, H + bar_h + pad_b), (250, 250, 248, 255))
    canvas.paste(img, (0, bar_h))
    d2 = ImageDraw.Draw(canvas)
    ttl = title or f"第 {chap} 章  {cname}"
    d2.text((16, int(12 * sc / 6)), ttl, font=f_lg, fill=(32, 32, 32))
    sub = (f"关卡 {drawn.get('StageSpawner',0)} · 收集品 {drawn.get('ItemSpawner',0)}"
           f" · 门 {drawn.get('Door',0)} · 传送门 {drawn.get('Portal',0)+drawn.get('PortalSet',0)}"
           f" ｜ 坐标为客户端真实世界坐标，最大位移误差 < 1px")
    d2.text((16, bar_h - int(16 * sc / 6)), sub, font=f_small, fill=(110, 110, 110))

    # 图例
    lx, ly = 16, H + bar_h + int(8 * sc / 6)
    for cls, (color, label, pri) in sorted(STYLE.items(), key=lambda kv: -kv[1][2]):
        if not drawn.get(cls):
            continue
        s = int(10 * sc / 6)
        d2.rectangle([lx, ly + 2, lx + s, ly + 2 + s], fill=color)
        txt = f"{label} {drawn[cls]}"
        d2.text((lx + s + 6, ly), txt, font=f_small, fill=(70, 70, 70))
        lx += d2.textlength(txt, font=f_small) + int(28 * sc / 6)

    canvas.convert("RGB").save(out, quality=95)
    print("→", out, canvas.size, "点位", drawn)


main()
