# -*- coding: utf-8 -*-
"""总绘图（能看清整场 + 5 个阵位）与点位标注。

  python render_overview.py <asm.json> <bundle> <out.png> [--w 1800] [--pitch 42] [--dist 30]

相机是自己搭的俯视机位：不做运行时 Cinemachine（包里没有 Camera 组件），
所以「总绘图」是**按场景几何与阵位自己选的角度**，不是游戏内那一帧 —— 图上会写明。
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import render_battle_scene as R

FONT = None


def font(sz):
    global FONT
    try:
        return ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", sz)
    except Exception:
        return ImageFont.load_default()


def unit(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def make_wide(chars):
    """广角平视总览：相机站在 5 个阵位的中心正后方，用大 fov 一次框住 5 个掩体。

    为什么不用俯视：这套战场是为**平视**搭的布景（大量 billboard 与背板），
    从上往下看会露出背板背面与纯色面，画面糊成一块 —— 试过 42°/50°/62°/70° 都不成。
    """
    cx = float(chars[:, 0].mean())
    cz = float(chars[:, 2].mean())
    cam = np.array([cx, -2.4 + 6.5, cz - 12.5], float)
    tgt = np.array([cx, -0.2, cz + 14.0], float)
    fwd = unit(tgt - cam)
    right = unit(np.cross([0.0, 1.0, 0.0], fwd))
    up = np.cross(fwd, right)
    return cam, fwd, right, up


def make_camera(target, pitch_deg, dist, yaw_deg=0.0):
    """相机站在 target 的**身后**（-Z 侧）并抬高；pitch_deg 为俯角（向下看为正）。

    坐标系：+Z 是从掩体指向敌方的前进方向（阵位 character z≈4.5、掩体 z≈4.9、相机 z≈0），
    所以"身后"是 z 更小的一侧 —— 这一点搞反会拍到战场背面和一片天空。
    """
    t = np.asarray(target, float)
    p = math.radians(pitch_deg)
    y = math.radians(yaw_deg)
    back = np.array([math.sin(y) * math.cos(p), math.sin(p), -math.cos(y) * math.cos(p)]) * dist
    cam = t + back
    fwd = unit(t - cam)
    right = unit(np.cross([0.0, 1.0, 0.0], fwd))
    up = np.cross(fwd, right)
    return cam, fwd, right, up


def rasterize(A, TEX, cam, fwd, right, up, W, H, fov, SKY=None, bg=(16, 20, 28)):
    tf = math.tan(math.radians(fov) / 2.0)
    aspect = W / H

    def project(P):
        v = P - cam
        vz = v @ fwd
        vx = v @ right
        vy = v @ up
        zz = np.where(np.abs(vz) < 1e-4, 1e-4, vz)
        sx = (vx / (zz * tf * aspect)) * 0.5 + 0.5
        sy = 0.5 - (vy / (zz * tf)) * 0.5
        return np.stack([sx * W, sy * H], 1), vz

    cv = np.zeros((H, W, 4), np.float32)
    cv[:, :, 0], cv[:, :, 1], cv[:, :, 2], cv[:, :, 3] = bg[0], bg[1], bg[2], 255
    if SKY:
        cv = R.paint_sky(cv, cam, fwd, right, up, tf, aspect, SKY)

    tmap = A.get("textures") or {}
    items = []
    for p in A["props"]:
        V = np.array(p["v"], float)
        idx = p.get("tri") or []
        if len(V) == 0 or not idx:
            continue
        scr, vz = project(V)
        UV = np.array(p["uv"], float) if p.get("uv") else None
        img = TEX.get(tmap.get(str(p.get("tex") or 0)))
        for t in np.array(idx, np.int64).reshape(-1, 3):
            if t.max() >= len(V):
                continue
            if (vz[t] <= 0.05).any():
                continue
            items.append((float(vz[t].mean()), p, t, scr, UV, img))
    items.sort(key=lambda x: -x[0])
    print("[i] 可见三角 %d" % len(items))

    cache = {}

    def arr(img):
        k = id(img)
        if k not in cache:
            cache[k] = np.asarray(img.convert("RGBA"))
        return cache[k]

    drawn = 0
    for z, p, t, scr, UV, img in items:
        s = scr[t]
        minx, maxx = int(max(math.floor(s[:, 0].min()), 0)), int(min(math.ceil(s[:, 0].max()) + 1, W))
        miny, maxy = int(max(math.floor(s[:, 1].min()), 0)), int(min(math.ceil(s[:, 1].max()) + 1, H))
        if minx >= maxx or miny >= maxy:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx) + 0.5, np.arange(miny, maxy) + 0.5)
        x0, y0 = s[0]; x1, y1 = s[1]; x2, y2 = s[2]
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(det) < 1e-9:
            continue
        w0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / det
        w1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / det
        w2 = 1.0 - w0 - w1
        m = (w0 >= -0.002) & (w1 >= -0.002) & (w2 >= -0.002)
        if not m.any():
            continue
        yy = gy[m].astype(np.int32); xx = gx[m].astype(np.int32)
        if img is None or UV is None or t.max() >= len(UV):
            col = np.array(R.FALLBACK_COL.get(p.get("root"), (80, 88, 100)), np.float32)
            cv[yy, xx, :3] = col
            drawn += 1
            continue
        ta = arr(img)
        th, tw = ta.shape[:2]
        uu = w0[m] * UV[t[0]][0] + w1[m] * UV[t[1]][0] + w2[m] * UV[t[2]][0]
        vv = w0[m] * UV[t[0]][1] + w1[m] * UV[t[1]][1] + w2[m] * UV[t[2]][1]
        ix = np.clip((uu % 1.0) * (tw - 1), 0, tw - 1).astype(np.int32)
        iy = np.clip((1.0 - (vv % 1.0)) * (th - 1), 0, th - 1).astype(np.int32)
        px = ta[iy, ix]
        a = px[:, 3:4].astype(np.float32) / 255.0
        keep = px[:, 3] > 8
        if not keep.any():
            continue
        dst = cv[yy[keep], xx[keep], :3]
        cv[yy[keep], xx[keep], :3] = px[keep, :3].astype(np.float32) * a[keep] + dst * (1 - a[keep])
        drawn += 1
    print("[i] 实绘三角 %d" % drawn)
    return Image.fromarray(np.clip(cv, 0, 255).astype(np.uint8), "RGBA"), project


def main():
    a = sys.argv[1:]
    asm_p, bundle_p, out_p = Path(a[0]), Path(a[1]), Path(a[2])
    W = 1800
    pitch = 42.0
    dist = 30.0
    yaw = 0.0
    label = asm_p.stem
    for x in a[3:]:
        if x.startswith("--w="):
            W = int(x.split("=")[1])
        elif x.startswith("--pitch="):
            pitch = float(x.split("=")[1])
        elif x.startswith("--dist="):
            dist = float(x.split("=")[1])
        elif x.startswith("--yaw="):
            yaw = float(x.split("=")[1])
        elif x.startswith("--label="):
            label = x.split("=")[1]
    H = int(round(W * 9 / 16))

    import json
    A = json.loads(asm_p.read_text(encoding="utf-8"))
    tmap0 = A.get("textures") or {}
    need = {tmap0[str(p["tex"])] for p in A["props"] if str(p.get("tex")) in tmap0}
    print("[i] 需要贴图 %d 张" % len(need))
    TEX = R.load_tex(str(bundle_p), need)
    SKY = R.load_sky(str(bundle_p))

    slots = A["slots"]
    chars = np.array([s["character"] for s in slots], float)
    if pitch > 0:
        target = np.array([chars[:, 0].mean(), chars[:, 1].mean() + 1.0, chars[:, 2].mean() + 6.0])
        cam, fwd, right, up = make_camera(target, pitch, dist, yaw)
        fov = 45.0
    else:
        cam, fwd, right, up = make_wide(chars)
        fov = 78.0
    canvas, project = rasterize(A, TEX, cam, fwd, right, up, W, H, fov, SKY)
    d = ImageDraw.Draw(canvas, "RGBA")

    f1, f2, f3 = font(30), font(18), font(16)
    canvas_w = W

    def px(P):
        s, z = project(np.array([P], float))
        return (float(s[0][0]), float(s[0][1])) if z[0] > 0.2 else None

    # 阵位标记
    for k, s in enumerate(slots, 1):
        ch = np.array(s["character"], float)
        p = px(ch)
        if not p:
            continue
        x, y = p
        r = 15
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 196, 0, 70), outline=(255, 196, 0), width=3)
        d.text((x - 5, y - 9), str(k), font=f2, fill=(255, 255, 255))
        # 朝向箭头（镜头 fwd 的地面投影）
        ax = s.get("axes") or {}
        if ax.get("fwd"):
            fv = np.array(ax["fwd"], float)
            fv[1] = 0
            fv = unit(fv)
            q = px(ch + fv * 3.2)
            if q:
                d.line([x, y, q[0], q[1]], fill=(120, 220, 255), width=3)
                d.text((q[0] + 4, q[1] - 6), "%d" % k, font=f3, fill=(120, 220, 255))
        # 相机位
        c = px(np.array(s["camera"], float))
        if c:
            d.rectangle([c[0] - 6, c[1] - 6, c[0] + 6, c[1] + 6],
                        outline=(180, 200, 230), width=2)
        d.text((x + 20, y - 24), "阵位%d" % k, font=f2, fill=(255, 220, 120))

    d.rectangle([0, 0, W, 86], fill=(12, 16, 24, 220))
    d.text((20, 10), "战场总览 · %s ｜ 5 个阵位" % label, font=f1, fill=(240, 244, 250))
    d.text((20, 50), "机位为自建广角（包内无 Camera 组件）：fov %.0f°、眼点 %s ｜ 物体 %d" % (
        fov, [round(float(x), 1) for x in cam], A["n_props"]), font=f3, fill=(160, 172, 192))
    canvas.convert("RGB").save(out_p)
    print("->", out_p, canvas.size)


if __name__ == "__main__":
    main()
