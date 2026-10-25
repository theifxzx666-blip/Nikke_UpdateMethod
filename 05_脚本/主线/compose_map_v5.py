# -*- coding: utf-8 -*-
"""大地图合成 v5：标点改徽章样式 + 重叠位移 + 引导线 + 悬浮图例 + 比例尺。

用法：
  python compose_map_v5.py <坐标 tsv> <底图 png> <章节号> <章节名> <输出 png> \
         [--title 标题] [--stage-cat <关卡表 tsv>] [--accent RRGGBB]

改进点（相对 v4）：
  1. 标点由「白底细环 + 小数字」改为**实心彩色徽章**：白字粗体、白色外环、
     向下柔和投影，浅灰水泥底图上也压得住
  2. 标点密集处做**贪心避让**：按优先级依次找空位，位移后补一条细引导线回真实位置
  3. 图例从底部一行挤排改为**地图内右上角悬浮卡片**，带色块/数量/说明
  4. 关卡按类别着色（普通 / 多敌·精英 / BOSS），BOSS 额外加角标
  5. 自动裁掉底图四周透明留白，画布不再有大片米色空边
  6. 加 20 m 比例尺（比例来自底图 json 的 scale，实测 11 px/m）
  7. 全程 2× 超采样后降采样，圆环与文字边缘无锯齿
"""
import io
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SS = 2                       # 超采样倍数
FONT_B = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_R = r"C:\Windows\Fonts\msyh.ttc"

# 实体类型 -> (颜色, 图例文字, 优先级, 形状)
STYLE = {
    "StageSpawner": ((214, 40, 40), "关卡节点", 9, "circle"),
    "ItemSpawner": ((232, 163, 23), "宝箱 / 收集品", 6, "diamond"),
    "Door": ((46, 139, 87), "门", 4, "square"),
    "Portal": ((29, 111, 208), "传送门", 4, "square"),
    "PortalSet": ((29, 111, 208), "传送门组", 4, "square"),
    "LevelTrigger": ((123, 63, 160), "关卡触发器", 2, "square"),
    "InteractionActionTrigger": ((123, 63, 160), "交互触发器", 2, "square"),
    "SquadSpawner": ((14, 140, 140), "队伍出生点", 3, "square"),
    "CameraPoint": ((110, 110, 110), "默认镜头点", 0, "square"),
}
# 关卡类别 -> 覆盖色（优先级高于 StageSpawner 基色）
CAT_COLOR = {
    "普通": (214, 40, 40),
    "多敌关": (232, 108, 12),
    "精英关": (232, 108, 12),
    "BOSS 关": (142, 14, 14),
}


def load_tsv(path):
    rows, hdr = [], None
    for ln in io.open(path, encoding="utf-8-sig").read().splitlines():
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if hdr is None:
            hdr = parts
            continue
        rows.append(dict(zip(hdr, parts)))
    return rows


# 关卡表里「关卡类别」列有字符串与原始枚举值混用的情况，这里统一归一化
CAT_NORM = {"普通": "普通", "0": "普通", "BOSS": "BOSS 关", "4": "BOSS 关",
            "3": "多敌关", "2": "精英关", "1": "普通"}


def load_stage_cat(path):
    """关卡表 -> {stageid: 类别中文}，只取「普通」模式避免同名重复。"""
    out = {}
    for r in load_tsv(path):
        if r.get("模式") != "普通":
            continue
        sid = r.get("关卡ID", "")
        cat = CAT_NORM.get(r.get("关卡类别", ""), "普通")
        if sid:
            out[sid] = cat
    return out


def rrect(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def shadow_of(size, shapes, blur, dy, alpha):
    """把一组形状画进遮罩 -> 模糊 -> 返回 RGBA 阴影层。"""
    m = Image.new("L", size, 0)
    dm = ImageDraw.Draw(m)
    shapes(dm)
    m = m.filter(ImageFilter.GaussianBlur(blur))
    if dy:
        m2 = Image.new("L", size, 0)
        m2.paste(m, (0, dy))
        m = m2
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    sh.putalpha(m.point(lambda v: int(v * alpha / 255)))
    return sh


def main():
    argv = sys.argv[1:]
    pos = [a for a in argv if not a.startswith("--")]
    tsv, base, chap, cname, out = pos[:5]

    def opt(name, default=None):
        if name in argv:
            return argv[argv.index(name) + 1]
        return default

    title = opt("--title")
    cat_tsv = opt("--stage-cat")
    accent = tuple(int(opt("--accent", "D62828")[i:i + 2], 16) for i in (0, 2, 4))

    meta = json.loads(Path(base + ".json").read_text(encoding="utf-8"))
    x0, z1, sc = meta["x0"], meta["z1"], meta["scale"]
    rows = load_tsv(tsv)
    cats = load_stage_cat(cat_tsv) if cat_tsv else {}

    img = Image.open(base).convert("RGBA")
    W0, H0 = img.size

    # ---- 裁掉四周透明留白 ----
    bb = img.getbbox()
    pad = 10
    cx0 = max(0, bb[0] - pad)
    cy0 = max(0, bb[1] - pad)
    cx1 = min(W0, bb[2] + pad)
    cy1 = min(H0, bb[3] + pad)
    img = img.crop((cx0, cy0, cx1, cy1))
    W, H = img.size

    # 底图透明处垫暖米色
    bgp = Image.new("RGBA", (W, H), (246, 245, 241, 255))
    bgp.alpha_composite(img)
    img = bgp

    def px(x, z):
        return (x - x0) * sc - cx0, (z1 - z) * sc - cy0

    # ---- 标点几何 ----
    R_MAIN = 15          # 关卡徽章半径
    R_SIDE = 9.5         # 其他标点半径
    marks = []
    for r in rows:
        cls = r.get("class", "")
        if cls not in STYLE:
            continue
        try:
            x, z = float(r["x"]), float(r["z"])
        except (KeyError, ValueError):
            continue
        pxx, pxy = px(x, z)
        if not (-40 < pxx < W + 40 and -40 < pxy < H + 40):
            continue
        color, label, pri, shape = STYLE[cls]
        cat = ""
        if cls == "StageSpawner":
            cat = cats.get(r.get("stageid", ""), "")
            if cat in CAT_COLOR:
                color = CAT_COLOR[cat]
            try:
                num = str(int(r.get("stageid") or 0) % 1000)
            except ValueError:
                num = ""
            radius = R_MAIN
        else:
            num = ""
            radius = R_SIDE
        marks.append(dict(cls=cls, cat=cat, color=color, label=label, pri=pri,
                          shape=shape, x=pxx, y=pxy, num=num, rad=radius))

    # ---- 贪心避让 ----
    marks.sort(key=lambda m: (-m["pri"], m["y"], m["x"]))
    placed = []
    for m in marks:
        r = m["rad"]
        ox = oy = 0.0
        if m["num"]:
            cand = [(0, 0)]
            for ring in range(1, 9):
                step = 7 * ring
                for a in range(0, 360, 30):
                    cand.append((math.cos(math.radians(a)) * step,
                                 math.sin(math.radians(a)) * step))
            for dx, dy in cand:
                bx0, by0 = m["x"] + dx - r - 2, m["y"] + dy - r - 2
                bx1, by1 = m["x"] + dx + r + 2, m["y"] + dy + r + 2
                if all(bx1 < p[0] or bx0 > p[2] or by1 < p[1] or by0 > p[3]
                       for p in placed):
                    ox, oy = dx, dy
                    break
            placed.append((m["x"] + ox - r - 2, m["y"] + oy - r - 2,
                           m["x"] + ox + r + 2, m["y"] + oy + r + 2))
        m["cx"], m["cy"] = m["x"] + ox, m["y"] + oy

    # ---- 底色层（2× 超采样）----
    CW, CH = W * SS, H * SS
    base2 = img.resize((CW, CH), Image.LANCZOS)

    # 阴影层
    def shapes(dm):
        for m in marks:
            r = m["rad"] * SS
            cx, cy = m["cx"] * SS, m["cy"] * SS
            if m["shape"] == "circle":
                dm.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
            elif m["shape"] == "diamond":
                s = r * 0.95
                dm.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], fill=255)
            else:
                s = r * 0.8
                dm.rounded_rectangle([cx - s, cy - s, cx + s, cy + s], radius=r * 0.3, fill=255)

    sh = shadow_of((CW, CH), shapes, blur=5 * SS // 2, dy=2 * SS, alpha=110)
    base2.alpha_composite(sh)

    d = ImageDraw.Draw(base2)
    f_num = ImageFont.truetype(FONT_B, int(15 * SS))
    for m in marks:
        r = m["rad"] * SS
        cx, cy = m["cx"] * SS, m["cy"] * SS
        col = m["color"] + (255,)
        # 白色外环
        if m["shape"] == "circle":
            d.ellipse([cx - r - 1.6 * SS, cy - r - 1.6 * SS,
                       cx + r + 1.6 * SS, cy + r + 1.6 * SS], fill=(255, 255, 255, 235))
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        elif m["shape"] == "diamond":
            s = r * 0.95
            s2 = s + 1.6 * SS
            d.polygon([(cx, cy - s2), (cx + s2, cy), (cx, cy + s2), (cx - s2, cy)],
                      fill=(255, 255, 255, 235))
            d.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], fill=col)
        else:
            s = r * 0.8
            s2 = s + 1.4 * SS
            d.rounded_rectangle([cx - s2, cy - s2, cx + s2, cy + s2],
                                radius=r * 0.35, fill=(255, 255, 255, 235))
            d.rounded_rectangle([cx - s, cy - s, cx + s, cy + s],
                                radius=r * 0.28, fill=col)
        if m["num"]:
            t = m["num"]
            bb2 = d.textbbox((0, 0), t, font=f_num)
            d.text((cx - (bb2[2] - bb2[0]) / 2 - bb2[0],
                    cy - (bb2[3] - bb2[1]) / 2 - bb2[1]), t,
                   font=f_num, fill=(255, 255, 255, 255))

    # 引导线（位移 > 3px 才画）
    for m in marks:
        if not m["num"]:
            continue
        if abs(m["cx"] - m["x"]) < 3 and abs(m["cy"] - m["y"]) < 3:
            continue
        d.line([(m["x"] * SS, m["y"] * SS), (m["cx"] * SS, m["cy"] * SS)],
               fill=(60, 60, 60, 170), width=max(1, SS))
        rr = 2 * SS
        d.ellipse([m["x"] * SS - rr, m["y"] * SS - rr,
                   m["x"] * SS + rr, m["y"] * SS + rr],
                  fill=(255, 255, 255, 230), outline=(90, 90, 90, 200))

    # ---- 图例卡片（右上角）----
    cnt = {}
    for m in marks:
        key = m["label"] if not m["cat"] else f"关卡 · {m['cat']}"
        cnt[key] = cnt.get(key, 0) + 1
    order = ["关卡 · 普通", "关卡 · 多敌关", "关卡 · 精英关", "关卡 · BOSS 关"]
    order = [k for k in order if k in cnt] + \
            [k for k in cnt if k not in order]
    color_of = {"关卡 · 普通": CAT_COLOR["普通"], "关卡 · 多敌关": CAT_COLOR["多敌关"],
                "关卡 · 精英关": CAT_COLOR["精英关"], "关卡 · BOSS 关": CAT_COLOR["BOSS 关"]}
    for m in marks:
        color_of.setdefault(m["label"], m["color"])

    f_leg = ImageFont.truetype(FONT_B, int(12.5 * SS))
    f_cnt = ImageFont.truetype(FONT_R, int(12.5 * SS))
    lh = int(23 * SS)
    cw_max = 0
    for k in order:
        cw_max = max(cw_max, d.textlength(k, font=f_leg) + d.textlength(str(cnt[k]), font=f_cnt))
    card_w = int(cw_max + 62 * SS)
    card_h = int(lh * len(order) + 22 * SS)
    cxp = CW - card_w - int(16 * SS)
    cyp = int(16 * SS)
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    dc = ImageDraw.Draw(card)
    rrect(dc, [0, 0, card_w - 1, card_h - 1], int(10 * SS),
          fill=(255, 255, 255, 240), outline=(0, 0, 0, 26), width=max(1, SS))
    for i, k in enumerate(order):
        yy = int(11 * SS) + i * lh
        rr = 6 * SS
        cc = color_of[k] + (255,)
        dc.ellipse([20 * SS - rr, yy + lh // 2 - rr + 2, 20 * SS + rr, yy + lh // 2 + rr + 2],
                   fill=cc)
        dc.text((20 * SS + rr + 9 * SS, yy), k, font=f_leg, fill=(38, 38, 38, 255))
        ns = str(cnt[k])
        dc.text((card_w - 16 * SS - dc.textlength(ns, font=f_cnt), yy),
                ns, font=f_cnt, fill=(120, 120, 120, 255))
    cardsh = shadow_of((card_w, card_h),
                       lambda dm2: rrect(dm2, [0, 0, card_w - 1, card_h - 1],
                                         int(10 * SS), fill=255),
                       blur=4 * SS, dy=2 * SS, alpha=90)
    base2.alpha_composite(cardsh, (cxp, cyp))
    base2.alpha_composite(card, (cxp, cyp))

    # ---- 比例尺（左下角）----
    meters = 20
    sb = meters * sc * SS
    bx = int(18 * SS)
    by = CH - int(34 * SS)
    f_sb = ImageFont.truetype(FONT_B, int(11.5 * SS))
    d.rectangle([bx, by, bx + sb, by + 5 * SS], fill=(255, 255, 255, 220))
    seg = sb / 4
    for i in range(4):
        if i % 2 == 0:
            d.rectangle([bx + i * seg, by, bx + (i + 1) * seg, by + 5 * SS],
                        fill=(45, 45, 45, 235))
    d.rectangle([bx, by, bx + sb, by + 5 * SS], outline=(30, 30, 30, 235), width=max(1, SS))
    d.text((bx + sb + 6 * SS, by - 4 * SS), f"{meters} m", font=f_sb, fill=(40, 40, 40, 255))

    map2 = base2.resize((W, H), Image.LANCZOS)

    # ---- 标题带 ----
    bar_h = 74
    pad_b = 12
    canvas = Image.new("RGBA", (W, H + bar_h + pad_b), (250, 250, 248, 255))
    canvas.paste(map2, (0, bar_h))
    dt = ImageDraw.Draw(canvas)

    # 章节号色块
    chip = 46
    rrect(dt, [16, 14, 16 + chip, 14 + chip], 10, fill=accent + (255,))
    f_chip = ImageFont.truetype(FONT_B, 22)
    tw = dt.textlength(str(chap), font=f_chip)
    dt.text((16 + (chip - tw) / 2, 14 + (chip - 38) / 2 + 2), str(chap),
            font=f_chip, fill=(255, 255, 255, 255))

    f_ttl = ImageFont.truetype(FONT_B, 26)
    ttl = title or f"第 {chap} 章  {cname}"
    dt.text((16 + chip + 14, 16), ttl, font=f_ttl, fill=(28, 28, 28, 255))

    # 统计行：彩色小点 + 数字
    f_sub = ImageFont.truetype(FONT_R, 13)
    xs = 16 + chip + 14
    ys = 48
    for k in order:
        cc = color_of[k] + (255,)
        dt.ellipse([xs, ys + 4, xs + 8, ys + 12], fill=cc)
        txt = f"{k.split('·')[-1].strip() if '·' in k else k} {cnt[k]}"
        dt.text((xs + 13, ys), txt, font=f_sub, fill=(92, 92, 92, 255))
        xs += dt.textlength(txt, font=f_sub) + 22
    extra = [m["label"] for m in marks if not m["cat"] and m["label"] not in
             [k.split("·")[-1].strip() for k in order]]
    dts = f"坐标取自客户端 Transform.m_LocalPosition · 比例 {sc:g} px/m"
    dt.text((W - 16 - dt.textlength(dts, font=f_sub), 52), dts,
            font=f_sub, fill=(150, 150, 150, 255))

    canvas.convert("RGB").save(out, quality=95)
    print(f"→ {out}  {canvas.size}  标点 {len(marks)} 个")
    for k in order:
        print(f"    {k}: {cnt[k]}")


if __name__ == "__main__":
    main()
