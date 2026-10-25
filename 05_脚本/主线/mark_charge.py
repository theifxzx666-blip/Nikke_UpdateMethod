# -*- coding: utf-8 -*-
"""在战斗场景图上标「多判充能点位」。

两种用法：
  1) 站位图：按阵位相机渲染一帧，在准星应放的位置打标记
       python mark_charge.py <asm.json> <bundle> <charge.json> <outdir> [--w 1600]
  2) 总绘图：广角框住 5 个阵位，把每个点位落在世界空间的位置打出来
       python mark_charge.py <asm.json> <bundle> <charge.json> <out.png> --overview [--w 1800]

点位的世界位置 = 枪口 org + 方向(yaw,pitch) × 首个命中距离；
屏幕位置由「眼点 → 该世界点」投影得到，和游戏里"把准星压在那个物件上"是同一件事。
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import render_battle_scene as R
from render_overview import rasterize, make_wide, unit


def font(sz):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", sz)
    except Exception:
        return ImageFont.load_default()


def dirs_of(yaw, pitch):
    y, p = math.radians(yaw), math.radians(pitch)
    return np.array([math.sin(y) * math.cos(p), math.sin(p), math.cos(y) * math.cos(p)])


def hit_world(org, rec):
    """枪口射线的首个命中点（世界坐标）。"""
    d = rec["objs"][0]["d"] if rec.get("objs") else 20.0
    return np.array(org, float) + dirs_of(rec["yaw"], rec["pitch"]) * d


def draw_reticle(d, x, y, n, r=13, col=(255, 92, 92), tag=None, dy=0):
    d.ellipse([x - r, y - r, x + r, y + r], outline=col, width=3)
    for a, b in (((-r - 9, 0), (-r - 3, 0)), ((r + 3, 0), (r + 9, 0)),
                 ((0, -r - 9), (0, -r - 3)), ((0, r + 3), (0, r + 9))):
        d.line([(x + a[0], y + a[1]), (x + b[0], y + b[1])], fill=col, width=3)
    f = font(20)
    d.text((x + r + 6, y - 12 + dy), tag or ("%d判" % n), font=f, fill=col)


def main():
    a = sys.argv[1:]
    asm_p, bundle_p, chg_p, out_p = Path(a[0]), Path(a[1]), Path(a[2]), Path(a[3])
    W = 1600
    overview = "--overview" in a
    label = asm_p.stem.replace("asm_", "")
    for x in a[4:]:
        if x.startswith("--w="):
            W = int(x.split("=")[1])
        elif x.startswith("--label="):
            label = x.split("=")[1]
    A = json.loads(asm_p.read_text(encoding="utf-8"))
    C = json.loads(chg_p.read_text(encoding="utf-8"))
    tmap = A.get("textures") or {}
    need = {tmap[str(p["tex"])] for p in A["props"] if str(p.get("tex")) in tmap}
    TEX = R.load_tex(str(bundle_p), need)
    SKY = R.load_sky(str(bundle_p))

    if overview:
        H = int(round(W * 9 / 16))
        chars = np.array([s["character"] for s in A["slots"]], float)
        cam, fwd, right, up = make_wide(chars)
        canvas, project = rasterize(A, TEX, cam, fwd, right, up, W, H, 50.0, SKY)
        d = ImageDraw.Draw(canvas, "RGBA")

        def px(P):
            s, z = project(np.array([P], float))
            return (float(s[0][0]), float(s[0][1])) if z[0] > 0.2 else None

        for k, s in enumerate(A["slots"], 1):
            ch = np.array(s["character"], float)
            p = px(ch)
            if p:
                d.ellipse([p[0] - 15, p[1] - 15, p[0] + 15, p[1] + 15],
                          fill=(255, 196, 0, 70), outline=(255, 196, 0), width=3)
                d.text((p[0] - 5, p[1] - 10), str(k), font=font(20), fill=(255, 255, 255))

        # 多判点按屏幕近邻聚类：多个阵位命中同一处时合并成一个圈，避免叠字
        pts = []
        for k, s in enumerate(A["slots"], 1):
            r = C["slots"].get(str(k), {}).get("rec")
            if not r or not r.get("objs"):
                continue
            wp = hit_world(C["slots"][str(k)]["origin"], r)
            q_ = px(wp)
            if q_:
                pts.append((k, q_[0], q_[1], r["n"]))
        clusters = []
        for k, x, y, n in pts:
            for c in clusters:
                if abs(c["x"] - x) < 55 and abs(c["y"] - y) < 45:
                    c["ks"].append(k); c["ns"].append(n)
                    c["x"] = sum(c["x"], 0) / 2 if False else (c["x"] + x) / 2
                    c["y"] = (c["y"] + y) / 2
                    break
            else:
                clusters.append(dict(x=x, y=y, ks=[k], ns=[n]))
        for c in clusters:
            n = max(c["ns"])
            draw_reticle(d, c["x"], c["y"], n)
            f = font(19)
            lab = "阵位%s → %d判" % ("·".join(str(i) for i in c["ks"]), n)
            ty = c["y"] - 34
            tw = d.textlength(lab, font=f)
            d.rectangle([c["x"] + 16, ty - 2, c["x"] + 26 + tw, ty + 24], fill=(10, 12, 18, 190))
            d.text((c["x"] + 20, ty), lab, font=f, fill=(255, 170, 170))

        d.rectangle([0, 0, W, 86], fill=(12, 16, 24, 220))
        d.text((20, 10), "战场总览 · %s ｜ 5 个阵位 + 多判充能点" % label, font=font(30), fill=(240, 244, 250))
        d.text((20, 50), "广角 fov 50°（垂直；包内无 Camera 组件，机位自建）｜红圈=单发可穿的多判点",
               font=font(16), fill=(160, 172, 192))
        canvas.convert("RGB").save(out_p)
        print("->", out_p, canvas.size)
        return

    outdir = out_p
    outdir.mkdir(parents=True, exist_ok=True)
    H = int(round(W * 9 / 16))
    for k, s in enumerate(A["slots"], 1):
        cv = R.render(A, TEX, k - 1, W, 60, label, " ｜ 已标多判充能点", SKY)
        d = ImageDraw.Draw(cv, "RGBA")
        r = C["slots"].get(str(k), {}).get("rec")
        if r and r.get("pixel"):
            x, y = r["pixel"]
            sx, sy = x * W / 1600.0, y * H / 900.0
            if 0 <= sx < W and 0 <= sy < H:
                draw_reticle(d, sx, sy, r["n"])
                f = font(17)
                d.text((sx + 22, sy + 10), "yaw %+.2f°  pitch %+.2f°  %.1f%%" % (
                    r["yaw"], r["pitch"], r["n"] * 2.8), font=f, fill=(255, 190, 190))
        dst = outdir / ("%s_s%d.png" % (label, k))
        cv.save(dst)
        print("->", dst, " 峰值 %d 段 / 1°稳定 %d 段" % (
            C["slots"][str(k)]["n_max"], C["slots"][str(k)]["n_1deg"]))


if __name__ == "__main__":
    main()
