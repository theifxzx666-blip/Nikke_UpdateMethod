# -*- coding: utf-8 -*-
r"""build_battle_scene.py — 从 spotbackground(hd) 包还原「进入战斗后的关卡场景」

与 ChargeMap 版 build_assembly.py 的差别（必须改的地方）：
  · ChargeMap 那批图（swamplandjungle/motherwhalefield）的 Mesh 是未压缩的 m_VertexData；
    主线区域（cityforest 等）的 Mesh 全部走 m_CompressedMesh → 必须用 MeshHandler 解压，
    否则读出来 0 个顶点。
  · 三角面统一取全部 submesh 合并（战场美术都是单材质平板，submesh 只影响贴图分区）。

数据链路（全部客户端实证）：
  spotbackground(hd)_assets_sbg_<场景>_<hash>.bundle       （core 桶）
    ├─ SpotSingleMap          视差分层 Near/Mid/Far/End 的 _objectList → 层归属
    ├─ Transform 父链          m_Father → TRS 合成世界矩阵
    ├─ MeshFilter / MeshCollider → Mesh（压缩）→ MeshHandler → 顶点/UV/三角
    ├─ MeshRenderer → Material → Texture2D
    ├─ RuntimeTextureInstanceSetter._sprite → Sprite → Texture2D（无 Mesh 的 billboard 件）
    ├─ NKSpotCover.CoverIndex  → 该物体属于 cover_1..5 哪个阵位
    └─ Camera（spotcameracontrol）→ fov / near / far / clearFlags

用法：
  python build_battle_scene.py <bundle> <out.json>
"""
import sys, os, json, struct, collections
import numpy as np
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

ROOTS = {"static_object", "dynamic_object", "noncol_object", "cover_object",
         "hard", "medium", "soft", "NotCombatZone", "ground"}
ANCHOR_KEYS = {"character_position", "aim_position", "camera_position",
               "hide_position", "cover_1", "cover_2", "cover_3", "cover_4",
               "cover_5", "cover_object", "cover"}
LAYERS = ("Near", "Mid", "Far", "End")


# ---------------- 矩阵 ----------------
def trs(pos, rot, scl):
    x, y, z, w = rot
    xx, yy, zz = x * x, y * y, z * z
    m = [[1 - 2 * (yy + zz), 2 * (x * y - z * w), 2 * (x * z + y * w), pos[0]],
         [2 * (x * y + z * w), 1 - 2 * (xx + zz), 2 * (y * z - x * w), pos[1]],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (xx + yy), pos[2]],
         [0.0, 0.0, 0.0, 1.0]]
    for j in range(3):
        for i in range(3):
            m[i][j] *= scl[j]
    return m


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def apply(m, p):
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def v3(d, w=0.0):
    return (d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0))


def v4(d, w=1.0):
    return (d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0), d.get("w", w))


def pid(d):
    return (d or {}).get("m_PathID", 0)


def planar_uv(pts):
    """战场板件的 UV 重建。

    实测（sbg_001，cityforest 全族）：这批 Mesh 的 m_VertexData.m_DataSize
    只有 顶点数 × 12 字节（76 顶点 = 912 B），m_Channels 里 channel 0 以外
    全为 dimension=0、m_CompressedMesh.m_UV 的 m_NumItems 也是 0 ——
    **没有 UV 通道**。美术流程是「按贴图轮廓裁一块平板」，UV 由导图工具生成后
    被剥掉了，所以只能按板件包围盒平面投影还原：
      · 法线轴 = 三向尺度最小的那根（板厚固定 0.5）
      · 竖立板（法线为 X/Z）→ V 轴取 Y（美术上 Y 是竖直方向）
      · 躺平板（法线为 Y）→ V 轴取 Z，U 轴取 X
    验证：sbg_cityforest_sn_building02 板件 5.75×7.33（比 0.784）
          贴图 402×512（比 0.785），完全吻合。
    """
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    lo = (min(xs), min(ys), min(zs))
    ext = [max(xs) - lo[0], max(ys) - lo[1], max(zs) - lo[2]]
    normal = min(range(3), key=lambda i: ext[i])
    if normal != 1:
        vax, uax = 1, (2 if normal == 0 else 0)
    else:
        vax, uax = 2, 0
    su = ext[uax] or 1e-6
    sv = ext[vax] or 1e-6
    return [(round((p[uax] - lo[uax]) / su, 5), round((p[vax] - lo[vax]) / sv, 5))
            for p in pts]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    bundle, out = sys.argv[1], sys.argv[2]
    env = UnityPy.load(bundle)
    objs = list(env.objects)
    print("[i] bundle 内对象 %d 个" % len(objs))

    script_name = {}
    for o in objs:
        if o.type.name == "MonoScript":
            d = o.read()
            script_name[o.path_id] = getattr(d, "m_ClassName", None) or "?"

    trs_map, go_name, go_comp = {}, {}, {}
    rend, mat, spr, tex, mb = {}, {}, {}, {}, []
    mesh_pts, mesh_uv, mesh_tri = {}, {}, {}
    uv_src = {}
    meshfilter, mesh_by_name = {}, {}

    for o in objs:
        t = o.type.name
        if t == "Transform":
            tt = o.read_typetree()
            trs_map[o.path_id] = dict(p=v3(tt.get("m_LocalPosition", {})),
                                      q=v4(tt.get("m_LocalRotation", {})),
                                      s=v3(tt.get("m_LocalScale", {})),
                                      father=pid(tt.get("m_Father")),
                                      go=pid(tt.get("m_GameObject")))
        elif t == "GameObject":
            tt = o.read_typetree()
            go_name[o.path_id] = tt.get("m_Name", "")
            go_comp[o.path_id] = [c["component"]["m_PathID"] for c in tt.get("m_Component", [])]
        elif t == "Mesh":
            tt = o.read_typetree()
            try:
                h = MeshHandler(o.read())
                h.process()
                V = h.m_Vertices
                UV = h.m_UV0
                T = h.get_triangles()
            except Exception as e:
                print("  [!] mesh %s 解压失败 %s" % (tt.get("m_Name"), e))
                continue
            if not V:
                continue
            idx = []
            for sub in T:
                # get_triangles() 的每个 submesh 可能是 list / ndarray / tuple-of-tuple，
                # 一律 np.ravel 拍平再转 int，否则 int(tuple) 直接抛 TypeError。
                for x in np.ravel(np.asarray(sub, dtype=object)):
                    idx.append(int(x))
            mesh_pts[o.path_id] = [tuple(round(c, 5) for c in v) for v in V]
            if UV:
                mesh_uv[o.path_id] = [tuple(round(c, 5) for c in u) for u in UV]
                uv_src[o.path_id] = "mesh"
            else:
                mesh_uv[o.path_id] = planar_uv(mesh_pts[o.path_id])
                uv_src[o.path_id] = "planar"
            mesh_tri[o.path_id] = idx
            mesh_by_name[tt.get("m_Name", "")] = o.path_id
        elif t == "MeshFilter":
            tt = o.read_typetree()
            meshfilter[pid(tt.get("m_GameObject"))] = pid(tt.get("m_Mesh"))
        elif t == "MeshCollider":
            tt = o.read_typetree()
            g, m = pid(tt.get("m_GameObject")), pid(tt.get("m_Mesh"))
            if m and not meshfilter.get(g):
                meshfilter[g] = m
        elif t == "MeshRenderer":
            tt = o.read_typetree()
            rend[pid(tt.get("m_GameObject"))] = [pid(x) for x in (tt.get("m_Materials") or [])]
        elif t == "Material":
            tt = o.read_typetree()
            sp = tt.get("m_SavedProperties", {}) or {}
            te = {}
            for it in (sp.get("m_TexEnvs") or []):
                k, v = (it if isinstance(it, (list, tuple)) else (it.get("first"), it.get("second")))
                kn = k if isinstance(k, str) else (k or {}).get("name")
                te[kn] = pid((v or {}).get("m_Texture"))
            mat[o.path_id] = dict(name=tt.get("m_Name"), tex=te)
        elif t == "Sprite":
            tt = o.read_typetree()
            r = tt.get("m_Rect", {}) or {}
            pv = tt.get("m_Pivot", {}) or {}
            spr[o.path_id] = dict(name=tt.get("m_Name", ""),
                                  tex=pid((tt.get("m_RD") or {}).get("texture")),
                                  w=r.get("width", 0.0) or 0.0, h=r.get("height", 0.0) or 0.0,
                                  ptu=tt.get("m_PixelsToUnits", 100.0) or 100.0,
                                  px=pv.get("x", 0.5), py=pv.get("y", 0.0))
        elif t == "Texture2D":
            tex[o.path_id] = o.read().m_Name
        elif t == "MonoBehaviour":
            try:
                tt = o.read_typetree()
            except Exception:
                continue
            mb.append((script_name.get(pid(tt.get("m_Script")), "?"), tt))

    print("[i] mesh %d ／ 材质 %d ／ 贴图 %d ／ Sprite %d" % (
        len(mesh_pts), len(mat), len(tex), len(spr)))

    go_tr = {}
    for gid, comps in go_comp.items():
        for c in comps:
            if c in trs_map:
                go_tr[gid] = c
                break

    cache = {}

    def world(tid, depth=0):
        if tid in cache:
            return cache[tid]
        t = trs_map.get(tid)
        if t is None or depth > 64:
            return [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        local = trs(t["p"], t["q"], t["s"])
        f = t["father"]
        m = mat_mul(world(f, depth + 1), local) if f else local
        cache[tid] = m
        return m

    def root_group(gid):
        cur, g = gid, 0
        tr = trs_map.get(go_tr.get(gid, 0))
        while tr and tr["father"] and g < 64:
            ft = trs_map.get(tr["father"])
            if not ft:
                break
            cur = ft["go"]
            if go_name.get(cur, "") in ROOTS:
                return go_name[cur]
            tr = ft
            g += 1
        return go_name.get(gid, "")

    # 分类索引
    grader, tex_setter, cover_owner, single_map, cam = {}, {}, {}, None, None
    for sn, tt in mb:
        g = pid(tt.get("m_GameObject"))
        if "CollisionGradeType" in tt:
            grader[g] = tt["CollisionGradeType"]
        if sn == "RuntimeTextureInstanceSetter":
            tex_setter[g] = (pid(tt.get("_sprite")), pid(tt.get("_material")))
        if sn in ("NKSpotCover", "NKSpotCoverObject") and "CoverIndex" in tt:
            cover_owner[g] = tt["CoverIndex"]
        if sn == "SpotSingleMap":
            single_map = tt
    for o in objs:
        if o.type.name == "Camera":
            t = o.read_typetree()
            cam = dict(fov=t.get("field of view"), near=t.get("near"), far=t.get("far"),
                       ortho=t.get("orthographic"), clear=t.get("m_ClearFlags"),
                       bg=[round(t.get("m_BackGroundColor", {}).get(k, 0), 4) for k in ("r", "g", "b", "a")])
            break

    layers, root2layer = {}, {}
    if single_map:
        for lname in LAYERS:
            grp = single_map.get(lname) or {}
            ids = [pid(x) for x in (grp.get("_objectList") or [])]
            layers[lname] = dict(scrollWidth=grp.get("_scrollWidth"), n=len(ids))
            for r in ids:
                goid = trs_map[r]["go"] if r in trs_map else r
                root2layer[goid] = lname

    def walk_layer(gid):
        cur, g = gid, 0
        while cur and g < 80:
            if cur in root2layer:
                return root2layer[cur]
            tr = trs_map.get(go_tr.get(cur, 0))
            if not tr or not tr["father"]:
                break
            ft = trs_map.get(tr["father"])
            if not ft:
                break
            cur = ft["go"]
            g += 1
        return None

    def tex_of(gid):
        """取物体贴图：RuntimeTextureInstanceSetter._sprite → Sprite → Texture2D，兜底材质贴图"""
        sid, mid_ = tex_setter.get(gid, (0, 0))
        if sid and sid in spr:
            return spr[sid]["tex"]
        for mid in (rend.get(gid) or []):
            for k, tid in (mat.get(mid, {}).get("tex") or {}).items():
                if tid and tid in tex:
                    return tid
        return 0

    props, anchors = [], collections.defaultdict(list)
    anchor_slot = []            # 每个锚点归属哪个 cover（cover_1..5），配对相机的唯一正确依据
    COVER_N = {"cover_1", "cover_2", "cover_3", "cover_4", "cover_5"}

    def parent_cover(gid):
        """归属阵位优先用 NKSpotCover.CoverIndex（组件级权威字段），
        名字兜底（cover_1..5）。只用名字会错：hide_position / character_position
        常挂在 cover_object 下，最近的 cover_N 未必是它真正的阵位。"""
        cur, g = gid, 0
        tr = trs_map.get(go_tr.get(cur, 0))
        while g < 24:
            if cur in cover_owner:
                return int(cover_owner[cur])
            nm = go_name.get(cur, "")
            if nm in COVER_N:
                return int(nm.split("_")[-1])
            if not tr or not tr["father"]:
                break
            ft = trs_map.get(tr["father"])
            if not ft:
                break
            cur = ft["go"]
            tr = ft
            g += 1
        return None

    for gid in go_comp:
        name = go_name.get(gid, "")
        tid = go_tr.get(gid)
        if tid is None:
            continue
        m = world(tid)
        wx, wy, wz = apply(m, (0, 0, 0))
        base = name.split(" (")[0]

        if base in ANCHOR_KEYS or name in ANCHOR_KEYS:
            pos = [round(wx, 3), round(wy, 3), round(wz, 3)]
            anchors[base].append(pos)
            ax = None
            if base == "camera_position":
                # 相机朝向不能拿 aim 反推：aim 只是准星点，在相机前方 0.1 单位。
                # 真正的朝向是 camera_position 自身 Transform 的旋转 → 取世界矩阵三列。
                def col(m, j):
                    v = (m[0][j], m[1][j], m[2][j])
                    n = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5 or 1.0
                    return [round(c / n, 5) for c in v]
                ax = dict(right=col(m, 0), up=col(m, 1), fwd=col(m, 2))
            anchor_slot.append([base, parent_cover(gid), pos, ax])
            continue

        mid = meshfilter.get(gid)
        # MeshFilter.m_Mesh 运行时常为 0 → 按「mesh 名 == GameObject 名」兜底
        if not mid or mid not in mesh_pts:
            mid = mesh_by_name.get(name) or mesh_by_name.get(base)
        if mid and mid in mesh_pts:
            # ground_col / *_col 是地形碰撞网格，不是可视美术，混进来会整片糊住画面
            if base.endswith("_col") or name.endswith("_col"):
                continue
            pts = [apply(m, p) for p in mesh_pts[mid]]
            props.append(dict(kind="mesh", name=name, root=root_group(gid),
                              layer=walk_layer(gid), grade=grader.get(gid),
                              cover=cover_owner.get(gid),
                              tex=tex_of(gid), tid=tex_of(gid),
                              uvs=uv_src.get(mid),
                              v=[[round(c, 4) for c in p] for p in pts],
                              uv=mesh_uv.get(mid) or [],
                              tri=mesh_tri.get(mid) or []))
            continue

        sid, _ = tex_setter.get(gid, (0, 0))
        sp = spr.get(sid) if sid else None
        if sp and sp["w"] > 0:
            wu = sp["w"] / max(sp["ptu"], 1e-6)
            hu = sp["h"] / max(sp["ptu"], 1e-6)
            x0, x1 = -sp["px"] * wu, (1 - sp["px"]) * wu
            y0, y1 = -sp["py"] * hu, (1 - sp["py"]) * hu
            corners = [apply(m, (x0, y0, 0)), apply(m, (x1, y0, 0)),
                       apply(m, (x1, y1, 0)), apply(m, (x0, y1, 0))]
            props.append(dict(kind="quad", name=name, root=root_group(gid),
                              layer=walk_layer(gid), grade=grader.get(gid),
                              cover=cover_owner.get(gid), tex=sp["tex"],
                              v=[[round(c, 4) for c in p] for p in corners],
                              uv=[[0, 0], [1, 0], [1, 1], [0, 1]], tri=[0, 1, 2, 0, 2, 3]))

    anchor_out = {k: list(v) for k, v in anchors.items()}
    # 阵位配对：camera_position / aim_position / character_position / hide_position
    # 在 5 个 cover 根下的【局部坐标完全相同】（cam 0.6,0,-4.9；char -0.6,-2.34,-0.4；
    # aim -0.1,0,-0.1），世界差异全来自 cover 根自身的 TRS。
    # 所以必须按 cover 归属直接建索引，不能按键名列表 pop(0) —— 后者取的是全局第一个，
    # 会把 cover_3 的 aim 配给 cover_1。
    slot_acc = {}
    KEYMAP = {"camera_position": "camera", "aim_position": "aim",
              "character_position": "character", "hide_position": "hide"}
    for base, cov, pos, ax in anchor_slot:
        if cov in (1, 2, 3, 4, 5) and base in KEYMAP:
            slot_acc.setdefault(cov, {})[KEYMAP[base]] = pos
            if ax:
                slot_acc[cov]["axes"] = ax
    slots = []
    for ci in range(1, 6):
        d = slot_acc.get(ci, {})
        slots.append(dict(cover="cover_%d" % ci, camera=d.get("camera"), aim=d.get("aim"),
                          character=d.get("character"), hide=d.get("hide"),
                          axes=d.get("axes")))
    ground = [p for p in props if p["root"] == "ground"]
    allv = [c for p in props for c in p["v"]]
    bbox = None
    if allv:
        bbox = [[round(min(c[i] for c in allv), 2) for i in range(3)],
                [round(max(c[i] for c in allv), 2) for i in range(3)]]

    stem = os.path.basename(bundle)
    scene_key = (stem.split("_assets_")[-1].split("_")[0] if "_assets_" in stem
                 else os.path.splitext(stem)[0])
    out_d = dict(
        bundle=stem,
        scene=scene_key,
        camera=cam, anchors=anchor_out, slots=slots, layers=layers,
        bbox=bbox, n_props=len(props),
        roots=dict(collections.Counter(p["root"] for p in props)),
        kinds=dict(collections.Counter(p["kind"] for p in props)),
        uvs=dict(collections.Counter(p.get("uvs") for p in props if p["kind"] == "mesh")),
        textures={str(k): v for k, v in tex.items()},
        props=props)
    json.dump(out_d, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print("[OK] %s" % out)
    print("  物体 %d（mesh %d / quad %d） 锚点组 %s" % (
        len(props), sum(1 for p in props if p["kind"] == "mesh"),
        sum(1 for p in props if p["kind"] == "quad"), sorted(anchor_out)))
    print("  相机 %s" % cam)
    print("  包围盒 %s" % (bbox,))
    print("  根分组 %s" % out_d["roots"])
    print("  UV 来源 %s" % out_d["uvs"])
    print("  分层 %s" % {k: v["n"] for k, v in layers.items()})
    print("  大小 %.2f MB" % (os.path.getsize(out) / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(main())
