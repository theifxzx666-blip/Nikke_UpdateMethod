# -*- coding: utf-8 -*-
r"""render_battle_scene.py — 把装配好的战斗场景按【实机相机】透视投影渲染成图

原理
----
战场全部是「0.5 单位厚的平板 + billboard」的美术约定，所以只要拿到
世界顶点 + UV + 贴图 + 相机位姿，就能做出与实机一致的构图：
  · 相机位置取 slots[n].camera（锚点 camera_position，每张战场 5 个阵位各一组）
  · 朝向取 slots[n].axes 的 fwd / right / up —— 这是 camera_position 自身
    Transform 世界矩阵的三列，即相机真实的朝向。
    不能用 aim_position - camera_position 反推：aim 只是准星点，距相机 0.1 单位，
    反推出来的朝向会被这点位移带偏（实测 cityforest_001 会算成朝 -X-Z，
    结果整片战场都落到相机背后，只剩 73 个三角）。
  · 透视投影（相机无 Camera 组件时 fov=60 / near 0.1 / far 300，
    与 ChargeMap 八张图实测一致，并在角标里标注为默认值）
  · 画家算法：按三角形相机空间深度降序绘制，不做背面剔除（平板两面都可能朝外）

用法：
  python render_battle_scene.py <asm.json> <bundle> <out.png> [--slot 0] [--w 1600] [--fov 60]
  python render_battle_scene.py <asm.json> <bundle> <out_prefix> --all [--w 1280]
"""
import sys, os, json, math
import numpy as np
import UnityPy
from PIL import Image, ImageDraw, ImageFont

FALLBACK_COL = {"ground": (58, 66, 52), "static_object": (96, 104, 112),
                "hard": (150, 120, 90), "medium": (120, 130, 90),
                "soft": (140, 110, 90), "noncol_object": (70, 78, 92),
                "cover_object": (110, 96, 120), "dynamic_object": (100, 90, 130)}


def load_tex(bundle, need):
    env = UnityPy.load(bundle)
    out = {}
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        if d.m_Name not in need:
            continue
        try:
            out[d.m_Name] = d.image.convert("RGBA")
        except Exception:
            continue
    return out


def load_sky(bundle):
    """天空盒：包里没有 RenderSettings / Camera，但三张天空贴图在 bundle 里
    （sbg_<场景>_skybox_side / _upper / _under）。side 是 360° 柱状全景，
    upper / under 是纯色盖子 → 按方向向量直接采样即可。"""
    env = UnityPy.load(bundle)
    sky = {}
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        n = d.m_Name
        if "_skybox_" not in n:
            continue
        try:
            im = d.image.convert("RGBA")
        except Exception:
            continue
        if n.endswith("_side"):
            sky["side"] = np.asarray(im)
        elif n.endswith("_upper"):
            sky["upper"] = np.asarray(im).reshape(-1, 4).mean(0)
        elif n.endswith("_under"):
            sky["under"] = np.asarray(im).reshape(-1, 4).mean(0)
    return sky


def paint_sky(cv, cam, fwd, right, up, tf, aspect, sky):
    """按像素方向向量采样天空盒；没有贴图时保持深色底。"""
    H, W = cv.shape[:2]
    side = sky.get("side")
    if side is None:
        return cv
    sh, sw = side.shape[:2]
    xs = ((np.arange(W) + 0.5) / W * 2 - 1) * tf * aspect
    ys = (1 - (np.arange(H) + 0.5) / H * 2) * tf
    gx, gy = np.meshgrid(xs, ys)
    d = (fwd[None, None, :] + right[None, None, :] * gx[..., None]
         + up[None, None, :] * gy[..., None])
    d /= np.linalg.norm(d, axis=2, keepdims=True)
    elev = np.arcsin(np.clip(d[..., 1], -1, 1))
    az = np.arctan2(d[..., 0], d[..., 2])
    u = (az / (2 * math.pi) + 0.5) % 1.0
    v = elev / math.pi + 0.5                     # 天顶 v=1 → 贴图顶行
    ix = np.clip(u * (sw - 1), 0, sw - 1).astype(np.int32)
    iy = np.clip((1 - v) * (sh - 1), 0, sh - 1).astype(np.int32)
    img = side[iy, ix].astype(np.float32)
    # 极点附近过渡到 upper / under 的纯色盖
    up_c = sky.get("upper")
    un_c = sky.get("under")
    if up_c is not None:
        t = np.clip((np.degrees(elev) - 38.0) / 32.0, 0, 1)[..., None]
        img = img * (1 - t) + up_c.astype(np.float32)[None, None, :] * t
    if un_c is not None:
        t = np.clip((-np.degrees(elev) - 12.0) / 28.0, 0, 1)[..., None]
        img = img * (1 - t) + un_c.astype(np.float32)[None, None, :] * t
    cv[:, :, :] = img
    return cv


def norm(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def camera_of(A, slot):
    """返回 (cam, fwd, right, up, src)。优先用 slots[].axes（相机自身旋转），
    缺失时退化为 aim-cam，再缺失用 +Z。"""
    slots = A.get("slots") or []
    s = slots[slot] if slot < len(slots) else {}
    cam = np.array(s.get("camera") or [0, 0, 0], float)
    ax = s.get("axes") or {}
    if ax.get("fwd") and ax.get("right") and ax.get("up"):
        fwd = norm(ax["fwd"])
        right = norm(ax["right"])
        up = norm(ax["up"])
        return cam, fwd, right, up, "相机 Transform 世界矩阵"
    aim = s.get("aim")
    if aim:
        fwd = norm(np.array(aim, float) - cam)
        right = norm(np.cross(np.array([0.0, 1.0, 0.0]), fwd))
        up = np.cross(fwd, right)
        return cam, fwd, right, up, "aim 反推（兜底）"
    return cam, np.array([0.0, 0.0, 1.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), "默认 +Z（兜底）"


def render(A, TEX, slot, W, fov, scene_label, NOTE, SKY=None):
    H = int(round(W * 9 / 16))
    cam, fwd, right, up, src = camera_of(A, slot)
    print("[i] 阵位 %d 相机 %s 朝向 %s（%s）" % (slot + 1, [round(float(x), 2) for x in cam],
                                            [round(float(x), 2) for x in fwd], src))

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
    cv[:, :, 0], cv[:, :, 1], cv[:, :, 2], cv[:, :, 3] = 18, 24, 34, 255
    if SKY:
        cv = paint_sky(cv, cam, fwd, right, up, tf, aspect, SKY)

    tmap = A.get("textures") or {}
    tris = []
    for p in A["props"]:
        V = np.array(p["v"], float)
        idx = p.get("tri") or []
        if len(V) == 0 or not idx:
            continue
        UV = np.array(p["uv"], float) if p.get("uv") else None
        img = TEX.get(tmap.get(str(p.get("tex") or 0)))
        scr, vz = project(V)
        tri = np.array(idx, np.int64).reshape(-1, 3)
        for t in tri:
            if t.max() >= len(V):
                continue
            if (vz[t] <= 0.05).any():
                # 任一点在相机背后 → 整片跳过（近平面裁剪对平板件无视觉影响）
                continue
            tris.append((float(vz[t].mean()), p, t, scr, UV, img))
    print("[i] 三角面 %d（可见）" % len(tris))
    tris.sort(key=lambda x: -x[0])

    ta_cache = {}

    def img_arr(img):
        k = id(img)
        if k not in ta_cache:
            ta_cache[k] = np.asarray(img.convert("RGBA"))
        return ta_cache[k]

    drawn = 0
    for z, p, t, scr, UV, img in tris:
        s = scr[t]
        minx = max(int(math.floor(s[:, 0].min())), 0)
        maxx = min(int(math.ceil(s[:, 0].max())) + 1, W)
        miny = max(int(math.floor(s[:, 1].min())), 0)
        maxy = min(int(math.ceil(s[:, 1].max())) + 1, H)
        if minx >= maxx or miny >= maxy:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx) + 0.5, np.arange(miny, maxy) + 0.5)
        x0, y0 = s[0]
        x1, y1 = s[1]
        x2, y2 = s[2]
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(det) < 1e-9:
            continue
        w0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / det
        w1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / det
        w2 = 1.0 - w0 - w1
        eps = -0.002
        m = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        if not m.any():
            continue
        yy = gy[m].astype(np.int32)
        xx = gx[m].astype(np.int32)
        if img is None or UV is None or t.max() >= len(UV):
            col = np.array(FALLBACK_COL.get(p.get("root"), (80, 88, 100)), np.float32)
            cv[yy, xx, :3] = col
            drawn += 1
            continue
        ta = img_arr(img)
        th, tw = ta.shape[:2]
        uu = w0[m] * UV[t[0]][0] + w1[m] * UV[t[1]][0] + w2[m] * UV[t[2]][0]
        vv = w0[m] * UV[t[0]][1] + w1[m] * UV[t[1]][1] + w2[m] * UV[t[2]][1]
        # Unity UV 原点在左下
        ix = np.clip((uu % 1.0) * (tw - 1), 0, tw - 1).astype(np.int32)
        iy = np.clip((1.0 - (vv % 1.0)) * (th - 1), 0, th - 1).astype(np.int32)
        px = ta[iy, ix]
        alpha = px[:, 3] > 8
        if not alpha.any():
            continue
        a = (px[alpha, 3:4].astype(np.float32) / 255.0)
        dst = cv[yy[alpha], xx[alpha], :3]
        cv[yy[alpha], xx[alpha], :3] = px[alpha, :3].astype(np.float32) * a + dst * (1.0 - a)
        drawn += 1
    print("[i] 实绘三角 %d" % drawn)

    canvas = Image.fromarray(np.clip(cv, 0, 255).astype(np.uint8), "RGBA")

    # 角标
    try:
        f = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 26)
        fs = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
    except Exception:
        f = fs = ImageFont.load_default()
    d2 = ImageDraw.Draw(canvas)
    d2.rectangle([0, 0, W, 84], fill=(14, 18, 26, 215))
    d2.text((18, 10), "战斗场景还原 · %s ｜ 阵位 %d" % (scene_label, slot + 1),
            font=f, fill=(240, 244, 250))
    d2.text((18, 48), "相机 %s ｜ fov %.0f%s ｜ 物体 %d ｜ 可见三角 %d ｜ 绘出三角 %d ｜ %s" % (
        [round(x, 2) for x in cam], fov, NOTE, A["n_props"], len(tris), drawn, src),
        font=fs, fill=(168, 178, 196))
    return canvas.convert("RGB")


def main():
    a = sys.argv
    if len(a) < 4:
        print(__doc__)
        return 2
    asm_p, bundle, outp = a[1], a[2], a[3]
    slot, W, fov, allm, nosky = 0, 1600, 60.0, False, False
    label = None
    for i, x in enumerate(a):
        if x == "--slot":
            slot = int(a[i + 1])
        elif x == "--w":
            W = int(a[i + 1])
        elif x == "--fov":
            fov = float(a[i + 1])
        elif x == "--all":
            allm = True
        elif x == "--nosky":
            nosky = True
        elif x == "--label":
            label = a[i + 1]

    A = json.load(open(asm_p, encoding="utf-8"))
    scene_label = label or A.get("scene") or os.path.splitext(os.path.basename(bundle))[0]
    NOTE = "" if A.get("camera") else "（默认值，包内无 Camera 组件）"

    need = set(v for v in (A.get("textures") or {}).values())
    need = {A["textures"][str(p["tex"])] for p in A["props"]
            if p.get("tex") and str(p["tex"]) in A.get("textures", {})}
    print("[i] 需要贴图 %d 张" % len(need))
    TEX = load_tex(bundle, need)
    print("[i] 实际加载 %d 张" % len(TEX))
    SKY = None if nosky else load_sky(bundle)
    print("[i] 天空盒 %s" % (sorted(SKY) if SKY else "无（用纯色底）"))

    if not allm:
        img = render(A, TEX, slot, W, fov, scene_label, NOTE, SKY)
        img.save(outp, quality=95)
        print("[OK] %s  %dx%d" % (outp, img.width, img.height))
        return 0

    # --all：5 个阵位各出一张 + 2x3 拼图
    imgs = []
    for si in range(5):
        im = render(A, TEX, si, W, fov, scene_label, NOTE, SKY)
        p = "%s_s%d.png" % (outp, si + 1)
        im.save(p, quality=95)
        imgs.append(im)
        print("[OK] %s" % p)
    tw, th = imgs[0].size
    sheet = Image.new("RGB", (tw * 2, th * 3), (10, 13, 19))
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % 2) * tw, (i // 2) * th))
    # 第 6 格放信息卡，免得留一块死黑
    card = Image.new("RGB", (tw, th), (16, 21, 31))
    dc = ImageDraw.Draw(card)
    try:
        f1 = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 30)
        f2 = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 20)
    except Exception:
        f1 = f2 = ImageFont.load_default()
    dc.text((40, 40), "%s" % scene_label, font=f1, fill=(235, 240, 250))
    dc.text((40, 84), "五阵位相机（世界坐标）", font=f2, fill=(150, 162, 182))
    y = 130
    for si, s in enumerate(A.get("slots") or []):
        cam = s.get("camera") or [0, 0, 0]
        dc.text((40, y), "阵位 %d   X %7.2f   Y %6.2f   Z %7.2f" % (
            si + 1, float(cam[0]), float(cam[1]), float(cam[2])), font=f2, fill=(198, 208, 226))
        y += 34
    bb = A.get("bbox") or [[0, 0, 0], [0, 0, 0]]
    y += 16
    for ln in ("轨道：spotbackground(hd) · %s" % (A.get("bundle") or ""),
               "物体 %d ／ 包围盒 X %.1f~%.1f  Z %.1f~%.1f" % (
                   A.get("n_props", 0), bb[0][0], bb[1][0], bb[0][2], bb[1][2]),
               "相机朝向取 camera_position 世界矩阵（非 aim 反推）"):
        dc.text((40, y), ln, font=f2, fill=(126, 138, 158))
        y += 32
    sheet.paste(card, (tw, th * 2))
    sp = "%s_5阵位.png" % outp
    sheet.save(sp, quality=92)
    print("[OK] %s  %dx%d" % (sp, sheet.width, sheet.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
