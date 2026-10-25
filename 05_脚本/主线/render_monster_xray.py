# -*- coding: utf-8 -*-
"""莱彻「透视版」立绘 + 装配件拆解图。

背景：莱彻是骨骼动画件，客户端里 AnimationClip 曲线全部为空（被剥离），
只能按绑定姿态渲染。而绑定姿态下部分装配件（最典型是 cm_core 能量核心）
被外壳完全包裹，正常立绘中可见像素为 0 —— 看起来就像"缺了核心"。

本脚本输出两类图，把内部结构如实呈现出来：
  1. 透视版：外壳（*_body / *_legs）按 30% 不透明绘制，内部核心/框架/附属件正常，
     让被包裹的装配件显形。半透明是**渲染手法**，不是原始材质。
  2. 拆解图：每个装配件单独渲染成小图并标注名称、顶点数、是否被包裹。

产物：
  out/monster_standee/xray/<tag>_透视.png
  out/monster_standee/xray/<tag>_拆解.png
"""
import math
import sys
from pathlib import Path

import numpy as np
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import render_monster_standee as R

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\monster_standee\xray")
TAGS = ["xmg001", "xma003", "xeg006", "xea003", "eea002", "mea001", "meg006", "mmg005"]
TARGET_H = 1200
SS = 2
ALPHA_TEST = 0.02
GHOST_ALPHA = 0.28          # 外壳在透视版里的不透明度


def collect(env):
    """取全部可渲染件，附带 GameObject 名与网格名"""
    tfs, names, world = R.build_world(env)
    parts = []
    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        smr = o.read()
        try:
            go = smr.m_GameObject.read().m_Name
        except Exception:
            go = "?"
        tid = None
        for k, t in tfs.items():
            if t.m_GameObject.m_PathID == smr.m_GameObject.m_PathID:
                tid = k
                break
        if tid is None:
            continue
        M = world(tid)
        mesh = smr.m_Mesh.read()
        h = MeshHandler(mesh)
        h.process()
        if not h.m_Vertices or not h.m_IndexBuffer or not h.m_UV0:
            continue
        V = np.array(h.m_Vertices, float).reshape(-1, 3)
        UV = np.array(h.m_UV0, float).reshape(-1, 2)
        tris = [t for sub in h.get_triangles() for t in sub if len(t) == 3]
        if not tris:
            continue
        T = np.array(tris, np.int64)
        mat = None
        for m in (smr.m_Materials or []):
            try:
                mat = m.read()
                break
            except Exception:
                pass
        tx = R.tex_of(mat) if mat is not None else None
        if tx is None:
            continue
        ta = np.asarray(tx.image.convert("RGBA"), dtype=np.float32) / 255.0
        Vw = (M[:3, :3] @ V.T).T + M[:3, 3]
        parts.append(dict(go=go, mesh=mesh.m_Name, mat=mat.m_Name, V=Vw, Vlocal=V,
                          UV=UV, T=T, tex=ta, M=M))

    # 朝向归一，与 render_monster_standee 用同一判据：
    # 模型包给每根骨骼烘了绕 Y 180°（主件矩阵左上 -1、右下 -1），
    # 不抵消就看的是外壳内表面，图和立绘会左右反倒、看着"歪"。
    if parts:
        main = max(parts, key=lambda p: len(p["V"]))
        R3 = np.array(main["M"][:3, :3], float).copy()
        det3 = float(np.linalg.det(R3))
        if abs(det3) > 1e-9:
            R3 /= np.cbrt(abs(det3))
        if bool(R3[0, 0] < -0.8 and R3[2, 2] < -0.8):
            for p in parts:
                p["V"] = np.c_[-p["V"][:, 0], p["V"][:, 1], -p["V"][:, 2]]
    return parts


def is_shell(p):
    """外壳判定：网格名带 body / legs（这些是包住核心的机体外壳）"""
    n = p["mesh"].lower()
    return ("_body" in n) or n.endswith("body") or "legs" in n


def raster(parts, Hh, Ww, ctr, scale, ghost=False, only=None):
    """光栅化。ghost=True 时外壳件按 GHOST_ALPHA 绘制。only 指定只画某个部件。"""
    canvas = np.zeros((Hh, Ww, 4), np.float32)
    zbuf = np.full((Hh, Ww), -1e9, np.float32)
    owner = np.full((Hh, Ww), -1, np.int32)
    order = sorted(range(len(parts)), key=lambda i: float(parts[i]["V"][:, 2].mean()))
    for pi in order:
        p = parts[pi]
        if only is not None and pi != only:
            continue
        ta = p["tex"]
        th, tw = ta.shape[:2]
        px = (p["V"][:, 0] - ctr[0]) * scale + Ww / 2.0
        py = Hh / 2.0 - (p["V"][:, 1] - ctr[1]) * scale
        pz = p["V"][:, 2]
        UV = p["UV"]
        a_mul = GHOST_ALPHA if (ghost and is_shell(p)) else 1.0
        cnt = 0
        for tri in p["T"]:
            i0, i1, i2 = tri
            x0, y0, x1, y1, x2, y2 = px[i0], py[i0], px[i1], py[i1], px[i2], py[i2]
            minx = max(0, int(math.floor(min(x0, x1, x2))))
            maxx = min(Ww - 1, int(math.ceil(max(x0, x1, x2))))
            miny = max(0, int(math.floor(min(y0, y1, y2))))
            maxy = min(Hh - 1, int(math.ceil(max(y0, y1, y2))))
            if minx > maxx or miny > maxy:
                continue
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-9:
                continue
            xs = np.arange(minx, maxx + 1) + 0.5
            ys = np.arange(miny, maxy + 1) + 0.5
            X, Y = np.meshgrid(xs, ys)
            w0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / den
            w1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / den
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not inside.any():
                continue
            z = w0 * pz[i0] + w1 * pz[i1] + w2 * pz[i2]
            u = w0 * UV[i0, 0] + w1 * UV[i1, 0] + w2 * UV[i2, 0]
            v = w0 * UV[i0, 1] + w1 * UV[i1, 1] + w2 * UV[i2, 1]
            ui = np.clip((u * tw).astype(np.int32), 0, tw - 1)
            vi = np.clip(((1.0 - v) * th).astype(np.int32), 0, th - 1)
            col = ta[vi, ui].copy()
            col[:, :, 3] *= a_mul
            ok = inside & (col[:, :, 3] > ALPHA_TEST)
            if not ok.any():
                continue
            sz = zbuf[miny:maxy + 1, minx:maxx + 1]
            so = owner[miny:maxy + 1, minx:maxx + 1]
            upd = ok & (z >= sz - 1e-3)
            if not upd.any():
                continue
            sz[upd] = z[upd]
            so[upd] = pi
            dsub = canvas[miny:maxy + 1, minx:maxx + 1]
            sa = col[upd][:, 3:4]
            dsub[upd] = sa * col[upd] + (1.0 - sa) * dsub[upd]
            cnt += int(upd.sum())
    # 全部画完后统计最终归属，才是真正的"看得见多少"
    vis = {pi: int((owner == pi).sum()) for pi in range(len(parts))}
    return canvas, vis


def to_img(canvas, Ww, Hh):
    im = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8), "RGBA")
    return im.resize((Ww // SS, Hh // SS), Image.LANCZOS)


def font(sz):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
              r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for tag in TAGS:
        bp = next(DEV.glob(f"spotmonster_{tag}_*.bundle"), None)
        if bp is None:
            continue
        env = UnityPy.load(str(bp))
        parts = collect(env)
        if not parts:
            continue
        allv = np.vstack([p["V"] for p in parts])
        lo, hi = allv.min(0), allv.max(0)
        ctr = (lo + hi) / 2
        span_y = max(hi[1] - lo[1], 1e-3)
        span_x = max(hi[0] - lo[0], 1e-3)
        Hh = TARGET_H * SS
        MARGIN = 0.94
        scale = Hh * MARGIN / span_y
        Ww = max(int(round(span_x * scale / MARGIN)), 64)

        # 1) 正常渲染，记录每件可见像素
        base, vis = raster(parts, Hh, Ww, ctr, scale, ghost=False)
        # 2) 透视
        xr, _ = raster(parts, Hh, Ww, ctr, scale, ghost=True)
        to_img(xr, Ww, Hh).save(OUT / f"{tag}_透视.png")

        hidden = [i for i, p in enumerate(parts) if vis.get(i, 0) < Ww * Hh * 0.0002]
        print(f"== {tag}  部件 {len(parts)}  被包裹 {len(hidden)}: "
              f"{[(parts[i]['go'], vis.get(i, 0)) for i in hidden]}")

        # 3) 拆解图：每个可见装配件单独渲染
        # 同名件（比如左右两条手臂）加序号区分
        seen = {}
        for p in parts:
            k = p["go"]
            seen[k] = seen.get(k, 0) + 1
            p["label"] = k if seen[k] == 1 and sum(
                1 for q in parts if q["go"] == k) == 1 else f"{k} #{seen[k]}"

        cells = []
        for i, p in enumerate(parts):
            c, _ = raster(parts, Hh, Ww, ctr, scale, ghost=False, only=i)
            im = to_img(c, Ww, Hh)
            bb = im.getbbox()
            if bb:
                im = im.crop(bb)
            cells.append((im, p, vis.get(i, 0)))

        # 排成网格
        cell_h = 300
        pad = 18
        n = len(cells)
        cols = 4 if n > 4 else max(n, 1)
        rows = (n + cols - 1) // cols
        cw = (max((c[0].width for c in cells), default=100))
        cw = min(max(cw, 120), 340)
        tw = cols * (cw + pad) + pad
        th = rows * (cell_h + pad + 42) + pad + 46
        sheet = Image.new("RGBA", (tw, th), (255, 255, 255, 255))
        d = ImageDraw.Draw(sheet)
        f1, f2 = font(17), font(14)
        d.text((pad, 12), f"{tag} · 装配件拆解（{n} 件，按网格逐个渲染）", fill=(20, 24, 32), font=f1)
        for k, (im, p, v) in enumerate(cells):
            r_, c_ = divmod(k, cols)
            x = pad + c_ * (cw + pad)
            y = 46 + r_ * (cell_h + pad + 42)
            box = (x, y, x + cw, y + cell_h)
            d.rectangle(box, outline=(206, 212, 222), width=1, fill=(250, 251, 253))
            t = im.copy()
            t.thumbnail((cw - 12, cell_h - 12), Image.LANCZOS)
            sheet.alpha_composite(t, (x + (cw - t.width) // 2, y + (cell_h - t.height) // 2))
            nm = p.get("label") or p["go"]
            if v < Ww * Hh * 0.0002:
                d.text((x + 6, y + cell_h + 4), f"{nm}  ⚠ 被包裹", fill=(198, 40, 40), font=f2)
            else:
                d.text((x + 6, y + cell_h + 4), nm, fill=(28, 33, 41), font=f2)
            d.text((x + 6, y + cell_h + 22),
                   f"{len(p['V'])} 顶点 · {p['mat']} · 可见 {v/(SS*SS):.0f}px",
                   fill=(122, 132, 148), font=f2)
        sheet.convert("RGB").save(OUT / f"{tag}_拆解.png")
        print(f"   -> {tag}_透视.png / {tag}_拆解.png")


if __name__ == "__main__":
    main()
