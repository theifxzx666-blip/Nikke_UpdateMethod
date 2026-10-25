# -*- coding: utf-8 -*-
"""把莱彻模型导出成 glTF 2.0 二进制（.glb），供 Three.js / Blender 直接打开。

和参考站 nkas.pages.dev 的差别（实测它的 glb：1 个 node、skins=0、animations=0，
即**纯静态烘焙网格**，网页里的"动"只是 OrbitControls 让用户自己拖）：
本脚本额外导出 **skin + animation**，所以是真正的骨骼动画，能在浏览器里播。

坐标与朝向（实测对齐，不靠猜）：
  - 直接用 Unity 世界坐标当 glTF 坐标。用 nkas 的 glb 反查过：
    xba003 body 的 min/max = [-11.09,-0.17,-9.54]~[11.09,26.71,5.27]，
    与我方 skin_world 算出的包围盒（22.17×26.88×14.81，中心 (0,13.3,-2.1)）逐轴吻合。
  - UV 的 v 必须取反：Unity 的 v=0 在贴图**底边**，glTF 的 (0,0) 在**左上角**。
    与 render_monster_standee.raster 里的 `vi = (1-v)*th` 等价。
  - 三角形缠绕顺序不做翻转，改用 doubleSided=True 规避（nkas 也这么做）。

用法：
  python export_glb.py xba003 2phase
  python export_glb.py xba003 2phase --anim anim_xba003_2phase_idle.bundle
  python export_glb.py all
"""
import base64
import hashlib
import io
import json
import struct
import sys
from pathlib import Path

import numpy as np
import UnityPy
from PIL import Image
from UnityPy.helpers import MeshHelper

sys.path.insert(0, str(Path(__file__).parent))
import render_monster_standee as R
import pose_from_clip as P

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\glb")

MON = {"xba003": "spotmonster_xba003_dmtr.bundle",
       "eba002": "spotmonster_eba002_hsta.bundle"}

CT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
      5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}

# 朝向对齐：模型在包里是「背对相机」存的（渲染器早就用 diag(-1,1,-1) 烘过一遍，
# 否则看到的是外壳内表面，整片死黑）。glTF 的默认视角同样是相机在 +Z 看向原点，
# 所以这里对顶点/骨骼/IBM 统一乘 A，让 glb 在任何查看器里打开都是正面。
A3 = np.array([-1.0, 1.0, -1.0])
A4 = np.diag([-1.0, 1.0, -1.0, 1.0])


def rot_quat(q):
    """四元数绕 Y 转 180°（共轭）：(x,y,z,w) → (-x, y, -z, w)"""
    return (-q[0], q[1], -q[2], q[3])


def rot_pos(p):
    return (p[0] * A3[0], p[1] * A3[1], p[2] * A3[2])


class Builder:
    def __init__(self):
        self.bin = bytearray()
        self.gltf = {
            "asset": {"version": "2.0", "generator": "nikke-glb-exporter"},
            "scene": 0,
            "scenes": [{"nodes": []}],
            "nodes": [], "meshes": [], "materials": [], "textures": [],
            "images": [], "samplers": [], "accessors": [],
            "bufferViews": [], "buffers": [],
            "skins": [], "animations": [],
        }
        self.tex_cache = {}
        self.joints = []          # glTF node index 列表（骨骼）
        self.node_of_bone = {}    # bone path_id → node index

    # ---------- 底层写 buffer ----------
    def _view(self, data: bytes, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        off = len(self.bin)
        self.bin += data
        v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
        if target:
            v["target"] = target
        self.gltf["bufferViews"].append(v)
        return len(self.gltf["bufferViews"]) - 1

    def acc_vec(self, arr, comp, typ, target=None, minmax=False):
        arr = np.asarray(arr)
        fmt, sz = CT[comp]
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[typ]
        flat = arr.reshape(-1)
        # count 必须是「元素个数」，不是扁平后的 float 个数。
        # 之前写 int(len(arr))，传 (N,3) 时 len=N 碰巧对；一旦调用方先 reshape(-1)
        # 再传进来，len 就变成 3N，count 因此虚报 3 倍，
        # Three.js 解析时报 "Invalid typed array length"。统一用 size//ncomp 消除这个坑。
        count = int(flat.size // ncomp)
        data = flat.astype(np.dtype(fmt if fmt != "f" else np.float32)).tobytes()
        bv = self._view(data, target)
        a = {"bufferView": bv, "componentType": comp, "count": count, "type": typ}
        if minmax:
            v = flat.astype(float).reshape(-1, ncomp)
            a["min"] = [float(x) for x in v.min(0)]
            a["max"] = [float(x) for x in v.max(0)]
        self.gltf["accessors"].append(a)
        return len(self.gltf["accessors"]) - 1

    def acc_mat4(self, mats):
        arr = np.asarray(mats, np.float32).reshape(-1, 16)
        bv = self._view(arr.tobytes())
        self.gltf["accessors"].append({"bufferView": bv, "componentType": 5126,
                               "count": len(arr), "type": "MAT4"})
        return len(self.gltf["accessors"]) - 1

    # ---------- 贴图 ----------
    def texture(self, tex):
        im = tex.image
        if im.mode not in ("RGBA", "RGB"):
            im = im.convert("RGBA")
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        raw = buf.getvalue()
        # 贴图去重：莱彻 11 个材质其实共用同一张图集，逐材质各存一份会让
        # xba003_2phase 里 88% 的体积都是同一张图重复 11 次（15.09 MB → 贴图占 13.32 MB）。
        key = hashlib.sha1(raw).hexdigest()
        if key in self.tex_cache:
            return self.tex_cache[key]
        bv = self._view(raw)
        self.gltf["images"].append({"bufferView": bv, "mimeType": "image/png"})
        self.gltf["samplers"].append({"magFilter": 9729, "minFilter": 9987,
                              "wrapS": 10497, "wrapT": 10497})
        self.gltf["textures"].append({"sampler": len(self.gltf["samplers"]) - 1,
                              "source": len(self.gltf["images"]) - 1})
        idx = len(self.gltf["textures"]) - 1
        self.tex_cache[key] = idx
        return idx

    # ---------- 骨骼 ----------
    def build_skeleton(self, tfs, gname, tid2go, root_tids):
        """把 bones 的祖先链建成 glTF node 树，返回 bone path_id → node idx。"""
        children = {}
        for k, d in tfs.items():
            f = d.m_Father.m_PathID
            children.setdefault(f if f in tfs else 0, []).append(k)

        keep = set()
        for b in root_tids:
            cur, guard = b, 0
            while cur in tfs and guard < 128:
                keep.add(cur)
                cur = tfs[cur].m_Father.m_PathID
                guard += 1

        def add(tid):
            d = tfs[tid]
            q = d.m_LocalRotation
            po = d.m_LocalPosition
            sc = d.m_LocalScale
            self.gltf["nodes"].append({
                "name": gname.get(d.m_GameObject.m_PathID, f"n{tid}"),
                "translation": list(rot_pos((po.x, po.y, po.z))),
                "rotation": list(rot_quat((q.x, q.y, q.z, q.w))),
                "scale": [sc.x, sc.y, sc.z],
                "children": [],
            })
            idx = len(self.gltf["nodes"]) - 1
            self.node_of_bone[tid] = idx
            for c in sorted(children.get(tid, [])):
                if c in keep:
                    self.gltf["nodes"][idx]["children"].append(add(c))
            if not self.gltf["nodes"][idx]["children"]:
                del self.gltf["nodes"][idx]["children"]
            return idx

        roots = [t for t in keep if tfs[t].m_Father.m_PathID not in keep]
        root_idx = []
        for r in sorted(roots):
            root_idx.append(add(r))
        return root_idx


def export(tag, phase, clip_name=None, anim_frames=None, out_name=None):
    mb = DEV / MON[tag]
    env = UnityPy.load(str(mb))
    tfs, gname, world = R.build_world(env)
    tid2go = {k: gname.get(d.m_GameObject.m_PathID, "") for k, d in tfs.items()}
    byid = {o.path_id: o for o in env.objects}

    # ---- 收集网格（按变体根过滤阶段）----
    picked = []
    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        smr = o.read()
        gid = smr.m_GameObject.m_PathID
        tid = next((k for k, d in tfs.items() if d.m_GameObject.m_PathID == gid), None)
        if tid is None:
            continue
        chain = R.ancestor_chain(tid, tfs, tid2go)
        if phase not in R.variant_root(chain):
            continue
        mesh = smr.m_Mesh.read()
        h = MeshHelper.MeshHandler(mesh)
        h.process()
        if not h.m_Vertices or not h.m_IndexBuffer:
            continue
        picked.append((smr, mesh, h, tid))

    print(f"阶段 {phase}: {len(picked)} 个网格")
    if not picked:
        raise SystemExit("没有网格")

    B = Builder()
    want_skin = clip_name is not None

    def make_mat(smr, si):
        """按子网格下标取材质并登记到 glTF。

        Unity 的 Mesh 有 m_SubMeshes、Renderer 有 m_Materials，两者一一对应。
        老代码只取 m_Materials[0]，导致第 2 个子网格被贴上第 1 个的图集。
        """
        mats = [m for m in (smr.m_Materials or []) if m.path_id]
        mat_obj = mats[min(si, len(mats) - 1)].read() if mats else None
        mname = mat_obj.m_Name if mat_obj else f"mat_{len(B.gltf['materials'])}"
        tex_idx = None
        if mat_obj is not None:
            try:
                t = R.tex_of(mat_obj)
                if t is not None:
                    tex_idx = B.texture(t)
            except Exception as e:
                print("   贴图读取失败", mname, e)
        mat = {"name": mname, "doubleSided": True,
               "alphaMode": "MASK", "alphaCutoff": 0.5,
               "pbrMetallicRoughness": {"metallicFactor": 0.0,
                                        "roughnessFactor": 1.0}}
        if tex_idx is not None:
            mat["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex_idx}
        else:
            mat["pbrMetallicRoughness"]["baseColorFactor"] = [0.8, 0.8, 0.85, 1.0]
        B.gltf["materials"].append(mat)
        return len(B.gltf["materials"]) - 1, mname

    # 蒙皮骨骼集合
    bone_pids = []
    for smr, mesh, h, tid in picked:
        for b in (smr.m_Bones or []):
            if b.path_id and b.path_id not in bone_pids:
                bone_pids.append(b.path_id)

    if want_skin:
        root_idx = B.build_skeleton(tfs, gname, tid2go, bone_pids)
    else:
        root_idx = []

    mesh_node = {"name": f"{tag}_{phase}", "mesh": 0}
    if want_skin:
        mesh_node["skin"] = 0
    B.gltf["nodes"].append(mesh_node)
    mesh_node_idx = len(B.gltf["nodes"]) - 1
    B.gltf["scenes"][0]["nodes"] = root_idx + [mesh_node_idx]

    prims = []
    pos_all, nrm_all = [], []
    for smr, mesh, h, tid in picked:
        V = np.array(h.m_Vertices, float).reshape(-1, 3)
        UV = np.array(h.m_UV0, float).reshape(-1, 2) if h.m_UV0 else None
        if UV is None:
            continue
        UV = UV.copy()
        UV[:, 1] = 1.0 - UV[:, 1]
        # 每个子网格单独成一个 primitive（Unity 的 m_SubMeshes ↔ m_Materials 一一对应）
        subs = [np.array([t for t in sub if len(t) == 3], np.int64).reshape(-1, 3)
                for sub in h.get_triangles()]
        subs = [s for s in subs if len(s)]
        if not subs:
            continue

        if want_skin:
            pos = V
            nb = len(smr.m_Bones or [])
            W = getattr(h, "m_BoneWeights", None)
            I = getattr(h, "m_BoneIndices", None)
            if nb and W and I:
                Wt = np.asarray(W, float).reshape(-1, 4)
                Id = np.clip(np.asarray(I, np.int64).reshape(-1, 4), 0, nb - 1)
                # bone 下标 → joints 数组下标
                idx_of = {b.path_id: i for i, b in enumerate(smr.m_Bones)
                          if b.path_id}
                jmap = np.zeros(nb, np.int64)
                for i, b in enumerate(smr.m_Bones):
                    pid = b.path_id
                    if pid in B.node_of_bone:
                        jmap[i] = bone_pids.index(pid) if pid in bone_pids else 0
                    else:
                        jmap[i] = 0
                J = jmap[Id]
                Wsum = Wt.sum(1, keepdims=True)
                Wsum[Wsum == 0] = 1
                Wt = Wt / Wsum
            else:
                J = np.zeros((len(V), 4), np.uint16)
                Wt = np.zeros((len(V), 4), np.float32)
                Wt[:, 0] = 1
        else:
            pos = R.skin_world(V, smr, mesh, h, world, tfs, tid)
        pos = pos * A3

        # ---- 逐子网格出 primitive ----
        for si, T0 in enumerate(subs):
            used = np.unique(T0)
            remap = np.full(len(V), -1, np.int64)
            remap[used] = np.arange(used.size)
            T = remap[T0]
            p = pos[used]
            u = UV[used]

            # 法线（面积加权，只在本子网格内累加）
            N = np.zeros_like(p)
            q0, q1, q2 = p[T[:, 0]], p[T[:, 1]], p[T[:, 2]]
            fn = np.cross(q1 - q0, q2 - q0)
            for k in range(3):
                np.add.at(N, T[:, k], fn)
            ln = np.linalg.norm(N, axis=1, keepdims=True)
            ln[ln == 0] = 1
            N = N / ln

            mat_idx, mname = make_mat(smr, si)
            attrs = {
                "POSITION": B.acc_vec(p.reshape(-1), 5126, "VEC3", 34962, True),
                "NORMAL": B.acc_vec(N, 5126, "VEC3", 34962),
                "TEXCOORD_0": B.acc_vec(u, 5126, "VEC2", 34962),
            }
            if want_skin:
                attrs["JOINTS_0"] = B.acc_vec(J[used].astype(np.uint16), 5123, "VEC4", 34962)
                attrs["WEIGHTS_0"] = B.acc_vec(Wt[used].astype(np.float32), 5126, "VEC4", 34962)
            idx_acc = B.acc_vec(T.reshape(-1).astype(np.uint32), 5125, "SCALAR", 34963)
            prims.append({"attributes": attrs, "indices": idx_acc, "material": mat_idx})
            print(f"   {mesh.m_Name:34s} sb{si} 顶点 {used.size:6d} 三角 {len(T):6d} 材质 {mname}")

        pos_all.append(pos)

    B.gltf["meshes"].append({"primitives": prims})

    # ---- skin ----
    if want_skin:
        ibm = []
        for pid in bone_pids:
            bp = None
            for smr, mesh, h, tid in picked:
                for i, b in enumerate(smr.m_Bones or []):
                    if b.path_id == pid:
                        bp = R.m4(mesh.m_BindPose[i])
                        break
                if bp is not None:
                    break
            if bp is None:
                bp = np.eye(4)
            # glTF 的 inverseBindMatrix 定义是「把网格空间顶点变换到骨骼空间」，
            # 正好就是 Unity 的 m_BindPose（= boneWorld_atBind⁻¹），**不要再求一次逆**。
            # 之前写成 inv(bp)，等于把绑定姿态又翻了一遍，蒙皮后整体放大/错位
            # （实测 xba003 1 阶段尺寸从 22×27×15 变成 69×102×89，碎片满天飞）。
            # A 必须**左右各乘一次**（共轭）。推导：
            #   节点世界矩阵 W' = A·W·A⁻¹ ；顶点 V' = A·V
            #   要 V_out = jointMatrix·V' = A·(W·bindPose·V)
            #   ⇒ jointMatrix = A·W·bindPose·A⁻¹ = W'·IBM'
            #   ⇒ IBM' = A·bindPose·A （A 自逆）
            # 只左乘或只右乘都会多留一个 A，表现为「部件转错/整片死黑（看到内表面）」。
            ibm.append((A4 @ np.asarray(bp) @ A4).T.reshape(-1))
        ibm_acc = B.acc_mat4(ibm)
        B.gltf["skins"].append({
            "joints": [B.node_of_bone[p] for p in bone_pids],
            "inverseBindMatrices": ibm_acc,
            "skeleton": root_idx[0] if root_idx else B.node_of_bone[bone_pids[0]],
        })

    # ---- 动画 ----
    if want_skin and clip_name:
        cbp = DEV / clip_name
        head = P.pose_for(mb, cbp, phase, 0)
        F = head["stats"]["frames"]
        fr = anim_frames or list(range(F))
        fr = [int(round(x)) for x in fr]
        times = np.array(fr, np.float32) / 30.0

        # 逐骨骼收集 TRS
        seq = {}
        for f in fr:
            pr = P.pose_for(mb, cbp, phase, f)
            for go_pid, (q, po, sc) in pr["pose"].items():
                seq.setdefault(go_pid, []).append((q, po, sc))

        # GameObject path_id → Transform path_id
        go2tid = {d.m_GameObject.m_PathID: k for k, d in tfs.items()}
        chans, samplers = [], []
        n_ch = 0
        for go_pid, lst in seq.items():
            tid = go2tid.get(go_pid)
            if tid is None or tid not in B.node_of_bone:
                continue
            node = B.node_of_bone[tid]
            T = np.array([rot_pos(x[1]) for x in lst], np.float32)
            Q = np.array([rot_quat(x[0]) for x in lst], np.float32)
            S = np.array([x[2] for x in lst], np.float32)
            for path, arr, typ in (("translation", T, "VEC3"),
                                   ("rotation", Q, "VEC4"),
                                   ("scale", S, "VEC3")):
                if np.allclose(arr, arr[0], atol=1e-6):
                    continue      # 常量不必进动画
                ta = B.acc_vec(times, 5126, "SCALAR", None, True)
                va = B.acc_vec(arr, 5126, typ)
                samplers.append({"input": ta, "output": va,
                                 "interpolation": "LINEAR"})
                chans.append({"sampler": len(samplers) - 1,
                              "target": {"node": node, "path": path}})
                n_ch += 1
        if chans:
            B.gltf["animations"].append({
                "name": Path(clip_name).stem,
                "channels": chans, "samplers": samplers})
        print(f"   动画：{len(fr)} 帧，{n_ch} 条通道，{len(seq)} 根骨骼有曲线")

    # ---- 收尾 ----
    while len(B.bin) % 4:
        B.bin.append(0)
    B.gltf["buffers"] = [{"byteLength": len(B.bin)}]

    js = json.dumps(B.gltf, ensure_ascii=False, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    total = 12 + 8 + len(js) + 8 + len(B.bin)
    blob = (struct.pack("<III", 0x46546C67, 2, total)
            + struct.pack("<II", len(js), 0x4E4F534A) + js
            + struct.pack("<II", len(B.bin), 0x004E4942) + bytes(B.bin))

    OUT.mkdir(parents=True, exist_ok=True)
    suffix = "" if want_skin else "_static"
    # 表演动画（登场 / groggy / death）必须单独命名：
    # 用默认的 {tag}_{phase}.glb 会把 3D 查看器正在用的 idle 文件覆盖掉。
    dst = OUT / (out_name or f"{tag}_{phase}{suffix}.glb")
    dst.write_bytes(blob)
    print(f"-> {dst.name}  {len(blob) / 1048576:.2f} MB  "
          f"节点 {len(B.gltf['nodes'])} 材质 {len(B.gltf['materials'])} "
          f"贴图 {len(B.gltf['images'])}")
    return dst


def main():
    a = sys.argv[1:]
    jobs = [
        ("xba003", "1phase", "anim_xba003_1phase_idle.bundle"),
        ("xba003", "2phase", "anim_xba003_2phase_idle.bundle"),
        ("eba002", "1phase", "anim_eba002_1phase_idle.bundle"),
        ("eba002", "2phase", "anim_eba002_2phase_idle.bundle"),
    ]
    if a and a[0] != "all":
        tag = a[0]
        ph = a[1]
        clip = None
        if "--anim" in a:
            clip = a[a.index("--anim") + 1]
        else:
            clip = next((c for t, p, c in jobs if t == tag and p == ph), None)
        on = a[a.index("--out") + 1] if "--out" in a else None
        export(tag, ph, clip, out_name=on)
        return
    for tag, ph, clip in jobs:
        print(f"\n===== {tag} {ph}")
        try:
            export(tag, ph, clip)
        except Exception as e:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
