# -*- coding: utf-8 -*-
"""把 spotmonster(hd) 里的 3D 怪物模型渲成「立绘」（绑定姿态静帧）。

为什么是绑定姿态：这批莱彻在客户端里是 SkinnedMesh + 骨骼动画，没有 2D 立绘。
绑定姿态下 bone_world × bindpose = 单位矩阵，蒙皮顶点就等于原始顶点，
所以直接把 Mesh 顶点按 Transform 层级摆到世界空间、正交投影、按 UV 采样贴图，
得到的就是模型在 T/绑定姿态下的正面静帧 —— 这与「骨骼还原成立绘」是同一件事。

渲染：正交前视（Unity 约定角色朝 +Z，相机在 +Z 侧沿 −Z 看），
z-buffer + alpha 剪影（alpha<0.5 丢弃），4× 超采样后缩到目标尺寸做抗锯齿。
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import UnityPy
from PIL import Image
from UnityPy.helpers.MeshHelper import MeshHandler

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\monster_standee")
XRAY = Path(r"D:\Codex\临时\nikke_intl_20261029\out\monster_xray")
SS = 2          # 超采样倍率（画布已放大到 1200×1400，2× 足够）
TARGET_H = 1400  # 画布高度（实际输出）
# 统一画布宽高比：所有立绘同尺寸，拼图里不会因宽高比不同而显得「趴着」或「歪」
CANVAS_W, CANVAS_H = 1200, 1400


def quat_mat(q):
    x, y, z, w = q.x, q.y, q.z, q.w
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], float)


def quat_mat4(q):
    """(x, y, z, w) 元组 → 3×3 旋转矩阵。pose 覆盖表用的是元组，不是 UnityPy 对象。"""
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], float)


def build_world(env, pose=None):
    """Transform.path_id → 4×4 世界矩阵。

    pose：{GameObject path_id: (quat xyzw, pos xyz, scale xyz)}，非 None 时覆盖
    对应节点的 local TRS —— 这是把「关卡内 idle 姿态」套进骨架的入口，
    键用 GameObject path_id 而不是 Transform path_id，因为 pose 是跳过 clip 名
    直接按骨骼名解析出来的。
    """
    tfs = {}
    for o in env.objects:
        if o.type.name == "Transform":
            tfs[o.path_id] = o.read()

    go_name = {}
    for o in env.objects:
        if o.type.name == "GameObject":
            go_name[o.path_id] = o.read().m_Name

    def local(d):
        m = np.eye(4)
        if pose is not None:
            ov = pose.get(d.m_GameObject.m_PathID)
            if ov is not None:
                q, p, s = ov
                m[:3, :3] = quat_mat4(q) @ np.diag(s)
                m[:3, 3] = p
                return m
        s = d.m_LocalScale
        m[:3, :3] = quat_mat(d.m_LocalRotation) @ np.diag([s.x, s.y, s.z])
        p = d.m_LocalPosition
        m[:3, 3] = [p.x, p.y, p.z]
        return m

    cache = {}

    def world(tid):
        if tid in cache:
            return cache[tid]
        d = tfs[tid]
        m = local(d)
        f = d.m_Father.m_PathID
        if f in tfs:
            m = world(f) @ m
        cache[tid] = m
        return m

    return tfs, go_name, world


def tex_of(mat):
    """取 _MainTex 里第一张能读出来、且不是投影贴图的 Texture2D。

    材质里同时挂了 _MainTex / _DissolveTexture / 若干 ShaderGraph 采样贴图，
    前几张的 PPtr 指向别的资源包（读会抛 FileNotFound），必须逐张 try。
    """
    got = []
    try:
        for k, v in mat.m_SavedProperties.m_TexEnvs:
            if k != "_MainTex":
                continue
            try:
                t = v.m_Texture.read()
            except Exception:
                continue
            if t is None or t.m_Name.startswith("monster_shadow"):
                continue
            got.append(t)
    except Exception:
        pass
    return got[0] if got else None


def ancestor_chain(tid, tfs, tid2go):
    """Transform path_id → 从自身到根的名字列表。"""
    chain, cur, guard = [], tid, 0
    while cur in tfs and guard < 64:
        chain.append(tid2go.get(cur, ""))
        f = tfs[cur].m_Father.m_PathID
        cur = f if f in tfs else None
        guard += 1
    return chain


def variant_root(chain):
    """从祖先链取**变体根**（名字含 `_var` 的那个）；找不到再退回最近含 1phase/2phase 的节点。

    为什么必须按 `_var` 根判，不能按「最近一个名字带 1phase/2phase 的节点」判：
    xba003 的 `xba003_1phase_magiccarpet_skin` 名字带 1phase，实际**挂在
    `xbga03_2phase_var` 下**（客户端原文如此，xbga03 的 a 不是笔误）。
    按最近命中会把它判成 1 阶段，结果是「1 阶段图里混进 2 阶段的部件、2 阶段图里丢掉它」。
    实测 `ancestor_chain` 是自身→根的顺序，所以从末尾往前的第一个 `_var` 才是变体根。
    """
    for c in reversed(chain):
        if "_var" in c.lower():
            return c
    return next((c for c in chain if "1phase" in c or "2phase" in c), "")


def phase_groups(bundle):
    """列出包里出现的阶段分组（按变体根 `*_var` 判定）。"""
    env = UnityPy.load(str(bundle))
    tfs, go_name, _ = build_world(env)
    tid2go = {k: go_name.get(d.m_GameObject.m_PathID, "") for k, d in tfs.items()}
    seen = set()
    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        tid = next((k for k, d in tfs.items()
                    if d.m_GameObject.m_PathID == o.read().m_GameObject.m_PathID), None)
        if tid is None:
            continue
        for c in ancestor_chain(tid, tfs, tid2go):
            if "_var" in c.lower():
                seen.add("1phase" if "1phase" in c else "2phase")
                break
    return sorted(seen)


def m4(bp):
    """UnityPy 的 Matrix4x4（e00..e33）→ numpy 4×4"""
    return np.array([[bp.e00, bp.e01, bp.e02, bp.e03],
                     [bp.e10, bp.e11, bp.e12, bp.e13],
                     [bp.e20, bp.e21, bp.e22, bp.e23],
                     [bp.e30, bp.e31, bp.e32, bp.e33]], float)


def skin_world(V, smr, mesh, h, world, tfs, tid):
    """按骨骼蒙皮把顶点摆到世界空间。

    以前这里是 `M @ V`（只用渲染节点世界矩阵，完全不看骨骼），实测后果很严重：
    每个骨骼的 skinMat = boneWorld @ bindPose 都是同一个 diag(-1, 1, -1)
    （即整体绕 Y 转 180°），说明模型在包里存的是**背对相机**的朝向，
    直接渲染等于一直在看外壳的内表面 —— 47 章 BOSS 中间那块死黑大面片就是这么来的。
    真正算上蒙皮后朝向与部件位置才对。
    """
    nb = len(smr.m_Bones or [])
    bp = list(mesh.m_BindPose or [])
    W = getattr(h, "m_BoneWeights", None)
    I = getattr(h, "m_BoneIndices", None)
    if nb == 0 or len(bp) != nb or not W or not I:
        M = world(tid)
        return (M[:3, :3] @ V.T).T + M[:3, 3]

    skins = np.zeros((nb, 4, 4), float)
    for i in range(nb):
        bt = smr.m_Bones[i].path_id
        Bw = world(bt) if bt in tfs else np.eye(4)
        skins[i] = Bw @ m4(bp[i])

    Wt = np.asarray(W, float).reshape(-1, 4)
    Id = np.clip(np.asarray(I, np.int64).reshape(-1, 4), 0, nb - 1)
    Vh = np.c_[V, np.ones(len(V))]
    out = np.zeros((len(V), 3), float)
    for k in range(4):
        p = np.einsum("nij,nj->ni", skins[Id[:, k]], Vh)
        out += Wt[:, k:k + 1] * p[:, :3]
    return out


def render(bundle, dst, name, phase=None, xray=False, pose=None):
    env = UnityPy.load(str(bundle))
    tfs, go_name, world = build_world(env, pose)
    tid2go = {k: go_name.get(d.m_GameObject.m_PathID, "") for k, d in tfs.items()}

    parts = []          # (V_world(N,3), UV(N,2), tris(M,3), texarray(H,W,4), mesh名, M)
    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        smr = o.read()
        go = smr.m_GameObject
        gid = go.m_PathID
        # 找该 GO 的 Transform
        tid = None
        for k, d in tfs.items():
            if d.m_GameObject.m_PathID == gid:
                tid = k
                break
        if tid is None:
            continue
        if phase:
            chain = ancestor_chain(tid, tfs, tid2go)
            owned = variant_root(chain)
            if phase not in owned:
                continue
        M = world(tid)
        mesh = smr.m_Mesh.read()
        h = MeshHandler(mesh)
        h.process()
        if not h.m_Vertices or not h.m_IndexBuffer:
            continue
        V = np.array(h.m_Vertices, float).reshape(-1, 3)
        UV = np.array(h.m_UV0, float).reshape(-1, 2) if h.m_UV0 else None
        if UV is None:
            continue
        # Unity 的 m_SubMeshes 与 m_Materials 一一对应：必须逐子网格配自己的贴图。
        # 老写法把子网格合并、统一用 m_Materials[0]，会让第 2 块几何贴上第 1 块
        # 的图集（实测 eba002 身体占 12,710/20,308 个顶点，全被贴成头部图集）。
        subs = [np.array([t for t in sub if len(t) == 3], np.int64).reshape(-1, 3)
                for sub in h.get_triangles()]
        subs = [s for s in subs if len(s)]
        if not subs:
            continue

        mats = []
        for m in (smr.m_Materials or []):
            try:
                mats.append(m.read())
            except Exception:
                mats.append(None)

        Vw = skin_world(V, smr, mesh, h, world, tfs, tid)
        for si, T in enumerate(subs):
            mat = mats[min(si, len(mats) - 1)] if mats else None
            if mat is None:
                mat = next((x for x in mats if x is not None), None)
            tx = tex_of(mat) if mat is not None else None
            if tx is None:
                continue
            img = tx.image.convert("RGBA")
            ta = np.asarray(img, dtype=np.float32) / 255.0
            parts.append((Vw, UV, T, ta, f"{mesh.m_Name}_sb{si}", M))

    if not parts:
        print("!! 没有可渲染的网格:", name)
        return None

    # ---- 朝向：按主部件（顶点最多）的渲染节点矩阵自动判定，不 hardcode 型号 ----
    # 实测这批包全部把「绕 Y 转 180°」烘进了骨骼与节点（diag(-1,1,-1)）：
    # 不抵掉就是相机对着背面/外壳内表面，47 章 1 阶段中间那块死黑面片就是这么来的。
    # 2026-10-25 三修：原来只对 xba003 / eba002 硬编码 flip，其余 12 型全是背面 —— 就是「歪了」。
    main = max(parts, key=lambda p: len(p[0]))
    R3 = main[5][:3, :3].astype(float).copy()
    det3 = np.linalg.det(R3)
    if abs(det3) > 1e-9:
        R3 /= np.cbrt(abs(det3))
    need_flip = bool(R3[0, 0] < -0.8 and R3[2, 2] < -0.8)
    if need_flip:
        parts = [(np.c_[-p[0][:, 0], p[0][:, 1], -p[0][:, 2]],) + p[1:] for p in parts]

    # ---- 统一画布：按最长边归一，避免宽扁模型在拼图里显得「趴着」 ----
    allv = np.vstack([p[0] for p in parts])
    lo, hi = allv.min(0), allv.max(0)
    ctr = (lo + hi) / 2.0
    span_x = max(hi[0] - lo[0], 1e-3)
    span_y = max(hi[1] - lo[1], 1e-3)
    Hh, Ww = TARGET_H * SS, int(round(TARGET_H * SS * CANVAS_W / CANVAS_H))
    MARGIN = 0.92
    scale = min(Hh * MARGIN / span_y, Ww * MARGIN / span_x)

    canvas = np.zeros((Hh, Ww, 4), np.float32)
    zbuf = np.full((Hh, Ww), -1e9, np.float32)

    def sx(x):
        return (x - ctr[0]) * scale + Ww / 2.0

    def sy(y):
        return Hh / 2.0 - (y - ctr[1]) * scale

    # ---- 光栅化：不透明件先写深度，半透明件后混合且不写深度 ----
    # 改前所有像素一律 alpha-over 且都写深度：半透明装甲先写入后，
    # 后面更近的不透明件被 z 判定挡住 → 画面出现「洞」和锯齿碎片，这就是破碎感的一半来源。
    OPAQUE = 0.95
    ALPHA_TEST = 0.02

    def raster(Vw, UV, T, ta, transparent_pass):
        th, tw = ta.shape[:2]
        px, py, pz = sx(Vw[:, 0]), sy(Vw[:, 1]), Vw[:, 2]
        drew = 0
        for tri in T:
            i0, i1, i2 = tri
            x0, y0, x1, y1, x2, y2 = px[i0], py[i0], px[i1], py[i1], px[i2], py[i2]
            minx, maxx = int(math.floor(min(x0, x1, x2))), int(math.ceil(max(x0, x1, x2)))
            miny, maxy = int(math.floor(min(y0, y1, y2))), int(math.ceil(max(y0, y1, y2)))
            minx, maxx = max(0, minx), min(Ww - 1, maxx)
            miny, maxy = max(0, miny), min(Hh - 1, maxy)
            if minx > maxx or miny > maxy:
                continue
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-9:
                continue
            X, Y = np.meshgrid(np.arange(minx, maxx + 1) + 0.5,
                               np.arange(miny, maxy + 1) + 0.5)
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
            col = ta[vi, ui]
            a = col[:, :, 3]
            pick = (a >= OPAQUE) if not transparent_pass else (a > ALPHA_TEST)
            pick &= inside
            if transparent_pass:
                pick &= (a < OPAQUE)
            if not pick.any():
                continue
            sub_z = zbuf[miny:maxy + 1, minx:maxx + 1]
            upd = pick & (z >= sub_z - 1e-3)
            if not upd.any():
                continue
            dsub = canvas[miny:maxy + 1, minx:maxx + 1]
            if not transparent_pass:
                sub_z[upd] = z[upd]
                dsub[upd, :3] = col[upd][:, :3]
                dsub[upd, 3] = 1.0
            else:
                sa = col[upd][:, 3:4]
                dsub[upd] = sa * col[upd] + (1.0 - sa) * dsub[upd]
                drew += int(upd.sum())
        return drew

    # 不透明件：按中心 z 从远到近（配合 z-buffer，顺序其实不敏感）
    if xray:
        # 透视版：深色底 + 外壳压到 22% + 核心件（cm_core）原色。
        # 上一版把外壳 alpha 降到 0.10 又没填底，透明画布在白底看图时等于全白 —— 白做了。
        canvas[:] = np.array([0.07, 0.07, 0.09, 1.0], np.float32)
        cores = [p for p in parts if "cm_core" in p[4]]
        shells = [p for p in parts if "cm_core" not in p[4]]
        if cores:
            for Vw, UV, T, ta, mname, _M in cores:
                raster(Vw, UV, T, ta, transparent_pass=False)
            for Vw, UV, T, ta, mname, _M in sorted(shells, key=lambda p: float(p[0][:, 2].mean())):
                ta2 = ta.copy()
                ta2[:, :, 3] *= 0.22
                raster(Vw, UV, T, ta2, transparent_pass=True)
        else:
            # 没有独立核心网格的型号（核心画在贴图上），退化成半透明整体轮廓
            for Vw, UV, T, ta, mname, _M in sorted(parts, key=lambda p: float(p[0][:, 2].mean())):
                ta2 = ta.copy()
                ta2[:, :, 3] *= 0.55
                raster(Vw, UV, T, ta2, transparent_pass=True)
    else:
        for Vw, UV, T, ta, mname, _M in sorted(parts, key=lambda p: float(p[0][:, 2].mean())):
            raster(Vw, UV, T, ta, transparent_pass=False)
        # 半透明件：按三角形中心 z 从远到近，深度测试但不写深度
        for Vw, UV, T, ta, mname, _M in sorted(parts, key=lambda p: float(p[0][:, 2].mean())):
            raster(Vw, UV, T, ta, transparent_pass=True)

    im = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8), "RGBA")
    im = im.resize((Ww // SS, Hh // SS), Image.LANCZOS)
    im.save(dst)
    n_tri = int(sum(len(p[2]) for p in parts))
    print("-> %-26s %s  %d 部件 %d 三角 %s%s" % (
        name, dst.name, len(parts), n_tri, im.size, "  [flip]" if need_flip else ""))
    return dict(file=dst.name, parts=len(parts), tris=n_tri, size=list(im.size),
                flipped=need_flip,
                bbox_lo=[round(float(x), 3) for x in lo],
                bbox_hi=[round(float(x), 3) for x in hi],
                meshes=[p[4] for p in parts])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    XRAY.mkdir(parents=True, exist_ok=True)
    manifest = {}
    # 命令行可只重渲指定型号：python render_monster_standee.py xba003 eba002
    want = {a for a in sys.argv[1:] if not a.startswith("-")}
    for b in sorted(D.glob("spotmonster_*.bundle")):
        tag = b.name.split("_")[1]
        if want and tag not in want:
            continue
        phs = phase_groups(b)
        if len(phs) > 1:
            # 多阶段 BOSS：两套形态的骨骼位置完全不同，混渲会在中间拉出一个空档，
            # 必须按父节点分组各出一张。
            print(f"[{tag}] 检出 {len(phs)} 个阶段：{phs}")
            for ph in phs:
                r = render(b, OUT / f"{tag}_{ph}_立绘.png", f"{tag}_{ph}", phase=ph)
                if r:
                    manifest[f"{tag}_{ph}"] = r
                rx = render(b, XRAY / f"{tag}_{ph}_透视.png", f"{tag}_{ph}", phase=ph, xray=True)
                if rx:
                    manifest[f"{tag}_{ph}_透视"] = rx
        else:
            r = render(b, OUT / f"{tag}_立绘.png", tag)
            if r:
                manifest[tag] = r
            rx = render(b, XRAY / f"{tag}_透视.png", tag, xray=True)
            if rx:
                manifest[tag + "_透视"] = rx
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    print("->", OUT / "manifest.json")


if __name__ == "__main__":
    sys.exit(main())
