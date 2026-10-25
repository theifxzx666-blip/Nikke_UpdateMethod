# -*- coding: utf-8 -*-
"""验证莱彻网格：绑定姿态直出 vs 真实蒙皮，两者是否一致。

V_direct = SMR.worldMatrix @ V
V_skin   = Σ w_i @ (bone_i.worldMatrix @ bindpose_i^-1) @ V

两者一致 → 直出没问题；偏差大 → 必须做蒙皮，否则部件错位。
"""
import sys
import numpy as np
from pathlib import Path

import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

sys.path.insert(0, str(Path(__file__).parent))
import render_monster_standee as R

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
TAGS = ["xmg001", "xma003", "xeg006", "xea003", "eea002", "mea001", "meg006", "mmg005"]


def get_weights(h, n):
    """从 MeshHandler 拿逐顶点 (索引[4], 权重[4])"""
    bw = getattr(h, "m_BoneWeights", None)
    if bw is None:
        return None
    idx = np.zeros((n, 4), np.int64)
    w = np.zeros((n, 4), np.float64)
    for i, x in enumerate(bw):
        if i >= n:
            break
        try:
            idx[i] = [x.boneIndex0, x.boneIndex1, x.boneIndex2, x.boneIndex3]
            w[i] = [x.weight0, x.weight1, x.weight2, x.weight3]
        except AttributeError:
            arr = list(x)
            idx[i] = arr[4:8]
            w[i] = arr[:4]
    return idx, w


def main():
    for tag in TAGS:
        bp = next(DEV.glob(f"spotmonster_{tag}_*.bundle"), None)
        if bp is None:
            continue
        env = UnityPy.load(str(bp))
        tfs, names, world = R.build_world(env)
        print("=" * 96)
        print(f"### {tag}")
        for o in env.objects:
            if o.type.name != "SkinnedMeshRenderer":
                continue
            smr = o.read()
            mesh = smr.m_Mesh.read()
            h = MeshHandler(mesh)
            h.process()
            if not h.m_Vertices:
                continue
            V = np.array(h.m_Vertices, float).reshape(-1, 3)
            n = len(V)

            tid = None
            for k, t in tfs.items():
                if t.m_GameObject.m_PathID == smr.m_GameObject.m_PathID:
                    tid = k
                    break
            M = world(tid)
            Va = (M[:3, :3] @ V.T).T + M[:3, 3]

            bones = list(smr.m_Bones or [])
            bps = list(getattr(mesh, "m_BindPose", None) or [])
            got = get_weights(h, n)
            print(f"  {mesh.m_Name:20s} v={n:5d} bones={len(bones):3d} bindpose={len(bps):3d} "
                  f"weights={'有' if got else '无'}")
            if not bones or len(bps) != len(bones) or got is None:
                lo, hi = Va.min(0), Va.max(0)
                print(f"      直出 bbox y[{lo[1]:7.2f},{hi[1]:7.2f}]  （缺蒙皮数据）")
                continue

            mats = np.tile(np.eye(4), (len(bones), 1, 1))
            for bi, b in enumerate(bones):
                bt = b.m_PathID
                if bt not in tfs:
                    continue
                Mw = world(bt)
                try:
                    raw = bps[bi]
                    B = np.array(getattr(raw, "m_BindPose", raw), float).reshape(4, 4)
                except Exception:
                    continue
                mats[bi] = Mw @ np.linalg.inv(B)

            idx, w = got
            Vw = np.zeros_like(V)
            wsum = np.zeros(n)
            for k in range(4):
                wk = w[:, k]
                nz = wk > 1e-6
                if not nz.any():
                    continue
                Mi = mats[idx[nz, k]]                     # (m,4,4)
                vv = V[nz]                                # (m,3)
                Vw[nz] += wk[nz, None] * (np.einsum("mij,mj->mi", Mi[:, :3, :3], vv) + Mi[:, :3, 3])
                wsum[nz] += wk[nz]
            ok = wsum > 1e-6
            Vw[ok] /= wsum[ok, None]
            Vw[~ok] = Va[~ok]

            d = float(np.abs(Vw - Va).max())
            lo_a, hi_a = Va.min(0), Va.max(0)
            lo_b, hi_b = Vw.min(0), Vw.max(0)
            flag = "【必须蒙皮】" if d > 0.01 else "（一致，直出即可）"
            print(f"      直出 x[{lo_a[0]:7.2f},{hi_a[0]:7.2f}] y[{lo_a[1]:7.2f},{hi_a[1]:7.2f}]")
            print(f"      蒙皮 x[{lo_b[0]:7.2f},{hi_b[0]:7.2f}] y[{lo_b[1]:7.2f},{hi_b[1]:7.2f}]"
                  f"  max|Δ|={d:.4f} {flag}")


if __name__ == "__main__":
    main()
