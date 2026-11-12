# -*- coding: utf-8 -*-
"""
地图还原 v3：把章节大地图的 ground mesh 顶视图重建成 PNG。

链路
----
campaignmapmodelgroup(hd) bundle
  -> Mesh `fcbg_cityforest_010_bg_01`（地面，4 个 submesh，各绑一张 bg_0X 图集）
  -> 解 m_CompressedMesh（顶点 / UV / 三角索引）
  -> World(Transform 链) -> 投影到 XZ 平面 -> 按 UV 采样贴图 -> 填三角
输出与原世界坐标同尺度，所以点位 TSV 的 x/z 可直接叠上去。

用法
----
python render_map.py <模型 bundle> <章节号，如 010> <输出 png> [--scale 每世界单位的像素数]
"""
import sys, os, json, math
import numpy as np
from PIL import Image
import UnityPy


# ---------- compressed mesh 解压 ----------
def unpack_float_vec(cv):
    n = cv["m_NumItems"]
    data = cv["m_Data"]
    if isinstance(data, str):
        data = data.encode("latin-1", "ignore")
    data = bytes(data)
    rng = cv["m_Range"]
    start = cv["m_Start"]
    need = n * 2
    out = np.zeros(n, dtype=np.float32)
    if n == 0:
        return out
    buf = np.frombuffer(data[:need], dtype="<u2").astype(np.float32)
    if buf.size < n:
        buf = np.pad(buf, (0, n - buf.size))
    m = buf == 65535.0
    out[:] = buf / 65535.0 * rng + start
    out[m] = 0.0
    return out


def unpack_int_vec(cv):
    n = cv["m_NumItems"]
    data = cv["m_Data"]
    if isinstance(data, (bytes, bytearray, str)):
        if isinstance(data, str):
            data = data.encode("latin-1", "ignore")
        buf = np.frombuffer(bytes(data)[: n * 4], dtype="<u4")
    else:
        buf = np.asarray(data, dtype=np.uint32)
    if buf.size < n:
        buf = np.pad(buf, (0, n - buf.size))
    return buf[:n]


def mesh_data(obj):
    """用 UnityPy 自带 MeshHandler 解压（关键：m_CompressedMesh 的 m_Data 是位流，m_BitSize 决定宽度）。"""
    from UnityPy.helpers.MeshHelper import MeshHandler
    d = obj.read_typetree()
    h = MeshHandler(obj.read())
    h.process()
    V = np.array(h.m_Vertices or [], dtype=np.float64)
    UV = np.array(h.m_UV0 or [], dtype=np.float64) if h.m_UV0 else None
    tri_list = h.get_triangles()
    return d, V, UV, tri_list


# ---------- 变换 ----------
def quat_to_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ], dtype=np.float64)


def build_world(env):
    tr, go2tr = {}, {}
    for o in env.objects:
        if o.type.name != "Transform":
            continue
        d = o.read_typetree()
        tr[o.path_id] = d
        go2tr[(d.get("m_GameObject") or {}).get("m_PathID")] = o.path_id

    cache = {}

    def world(pid, depth=0):
        if pid in cache:
            return cache[pid]
        d = tr[pid]
        lp, lr, ls = d.get("m_LocalPosition") or {}, d.get("m_LocalRotation") or {}, d.get("m_LocalScale") or {}
        L = quat_to_mat((lr.get("x", 0), lr.get("y", 0), lr.get("z", 0), lr.get("w", 1)))
        L = L * np.array([ls.get("x", 1), ls.get("y", 1), ls.get("z", 1)])
        T = np.array([lp.get("x", 0), lp.get("y", 0), lp.get("z", 0)], dtype=np.float64)
        f = (d.get("m_Father") or {}).get("m_PathID")
        if f and f in tr and depth < 60:
            PM, PT = world(f, depth + 1)
            M = PM @ L
            T = PM @ T + PT
        else:
            M = L
        cache[pid] = (M, T)
        return M, T

    return tr, go2tr, world


def main():
    bundle, chap = sys.argv[1], sys.argv[2]
    outpng = sys.argv[3]
    scale = 8.0
    if "--scale" in sys.argv:
        scale = float(sys.argv[sys.argv.index("--scale") + 1])

    env = UnityPy.load(bundle)
    tr, go2tr, world = build_world(env)

    # 贴图
    texname, texobj = {}, {}
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        try:
            nm = o.read_typetree().get("m_Name")
        except Exception:
            continue
        texname[o.path_id] = nm
        texobj[o.path_id] = o

    # 材质 -> 主贴图
    mat_tex = {}
    for o in env.objects:
        if o.type.name != "Material":
            continue
        try:
            d = o.read_typetree()
        except Exception:
            continue
        for k, v in (d.get("m_SavedProperties") or {}).get("m_TexEnvs", []):
            if k in ("_MainTex", "_BaseMap"):
                mat_tex[o.path_id] = (v.get("m_Texture") or {}).get("m_PathID")
                break

    # 找地面 mesh
    go_mesh, go_rend = {}, {}
    for o in env.objects:
        if o.type.name == "MeshFilter":
            d = o.read_typetree()
            go_mesh[(d.get("m_GameObject") or {}).get("m_PathID")] = (d.get("m_Mesh") or {}).get("m_PathID")
        elif o.type.name == "MeshRenderer":
            d = o.read_typetree()
            go_rend[(d.get("m_GameObject") or {}).get("m_PathID")] = d

    mesh_obj = {}
    for o in env.objects:
        if o.type.name == "Mesh":
            mesh_obj[o.path_id] = o

    target = None
    for go, rend in go_rend.items():
        mid = go_mesh.get(go)
        if mid not in mesh_obj:
            continue
        try:
            nm = mesh_obj[mid].read_typetree().get("m_Name") or ""
        except Exception:
            continue
        if nm == f"fcbg_cityforest_{chap}_bg_01":
            target = (go, mid, rend)
            break
    if not target:
        print("找不到地面 mesh"); sys.exit(1)
    go, mid, rend = target
    print("地面 mesh:", mesh_obj[mid].read_typetree().get("m_Name"))

    M, T = world(go2tr[go])
    print("地面 transform: T=", np.round(T, 3), " scale=", np.round([M[0, 0], M[1, 1], M[2, 2]], 3))

    d, V, UV, TRI = mesh_data(mesh_obj[mid])
    print(f"顶点 {len(V)}  UV {0 if UV is None else len(UV)}  三角索引 {len(TRI)}")

    W = (V @ M.T) + T  # 世界坐标

    subs = d["m_SubMeshes"]
    mats = [(m or {}).get("m_PathID") for m in (rend.get("m_Materials") or [])]

    # 视口
    pad = 6.0
    x0, x1 = W[:, 0].min() - pad, W[:, 0].max() + pad
    z0, z1 = W[:, 2].min() - pad, W[:, 2].max() + pad
    Wpx = int(round((x1 - x0) * scale))
    Hpx = int(round((z1 - z0) * scale))
    print(f"世界范围 X[{x0:.1f},{x1:.1f}] Z[{z0:.1f},{z1:.1f}] -> {Wpx}x{Hpx}px @ {scale}px/unit")

    canvas = np.zeros((Hpx, Wpx, 4), dtype=np.uint8)

    def to_px(x, z):
        return (x - x0) * scale, (z1 - z) * scale  # Z 轴向上，图像 y 向下

    stat = []
    for si, s in enumerate(subs):
        tid = mats[si] if si < len(mats) else None
        texid = mat_tex.get(tid)
        tname = texname.get(texid)
        tri = np.array(TRI[si], dtype=np.int64) if si < len(TRI) else np.zeros((0, 3), np.int64)
        if UV is None or texid not in texobj or not len(tri):
            stat.append((si, tname, len(tri), "无贴图/无UV"))
            continue
        img = texobj[texid].read().image.convert("RGBA")
        ta = np.asarray(img).astype(np.uint8)
        th, tw = ta.shape[:2]

        drawn = 0
        for a, b, c in tri:
            if a >= len(W) or b >= len(W) or c >= len(W):
                continue
            p = np.array([to_px(W[a][0], W[a][2]), to_px(W[b][0], W[b][2]), to_px(W[c][0], W[c][2])])
            uvs = np.array([[UV[a][0] * (tw - 1), (1 - UV[a][1]) * (th - 1)],
                            [UV[b][0] * (tw - 1), (1 - UV[b][1]) * (th - 1)],
                            [UV[c][0] * (tw - 1), (1 - UV[c][1]) * (th - 1)]])
            minx = max(int(math.floor(p[:, 0].min())), 0)
            maxx = min(int(math.ceil(p[:, 0].max())) + 1, Wpx)
            miny = max(int(math.floor(p[:, 1].min())), 0)
            maxy = min(int(math.ceil(p[:, 1].max())) + 1, Hpx)
            if minx >= maxx or miny >= maxy:
                continue
            xs = np.arange(minx, maxx) + 0.5
            ys = np.arange(miny, maxy) + 0.5
            gx, gy = np.meshgrid(xs, ys)
            q0, q1, q2 = p[0], p[1], p[2]
            det = (q1[0] - q0[0]) * (q2[1] - q0[1]) - (q1[1] - q0[1]) * (q2[0] - q0[0])
            if abs(det) < 1e-9:
                continue
            if det < 0:                      # 统一成逆时针，权重才落在 [0,1]
                q1, q2 = q2, q1
                uvs = uvs[[0, 2, 1]]         # UV 必须跟着一起换，否则贴图会镜像
                det = -det
            w0 = ((q1[0] - gx) * (q2[1] - gy) - (q1[1] - gy) * (q2[0] - gx)) / det
            w1 = ((q2[0] - gx) * (q0[1] - gy) - (q2[1] - gy) * (q0[0] - gx)) / det
            w2 = 1.0 - w0 - w1
            eps = 0.002
            m = (w0 >= -eps) & (w1 >= -eps) & (w2 >= -eps)
            if not m.any():
                continue
            u = (w0 * uvs[0, 0] + w1 * uvs[1, 0] + w2 * uvs[2, 0])[m]
            v = (w0 * uvs[0, 1] + w1 * uvs[1, 1] + w2 * uvs[2, 1])[m]
            ui = np.clip(u.astype(np.int32), 0, tw - 1)
            vi = np.clip(v.astype(np.int32), 0, th - 1)
            canvas[gy[m].astype(np.int32), gx[m].astype(np.int32)] = ta[vi, ui]
            drawn += 1
        stat.append((si, tname, len(tri), f"绘制 {drawn}"))
        print(f"  submesh{si} 材质贴图={tname} 三角={len(tri)} 绘制={drawn}")

    Image.fromarray(canvas, "RGBA").save(outpng)
    print("→", outpng, canvas.shape)
    json.dump({"x0": x0, "x1": x1, "z0": z0, "z1": z1, "scale": scale,
               "w": Wpx, "h": Hpx, "submeshes": stat},
              open(outpng + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


main()
