# -*- coding: utf-8 -*-
"""找出「哪一条动画通道把模型送出画面」。

做法：对每条 translation 通道单独把首帧值写回节点（其它节点保持绑定姿态），
算一次蒙皮后的包围盒中心，看哪条能单独造成 20 以上的位移。
只用采样顶点（默认 600 个），254 条通道也跑得完。
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from probe_glb_skin_bbox import MODELS, acc, load_glb, world_matrices  # noqa: E402


def sample_pts(j, binc, N=600):
    P = acc(j, binc, j["meshes"][0]["primitives"][0]["attributes"]["POSITION"])
    if len(P) > N:
        P = P[:: max(1, len(P) // N)]
    return np.concatenate([P, np.ones((len(P), 1))], axis=1)


def center_for(j, binc, joints, ibm_t):
    W = world_matrices(j)
    JM = np.stack([W.get(joints[k], np.eye(4)) @ ibm_t[k] for k in range(len(joints))])
    return JM


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("--thr", type=float, default=20.0)
    a = ap.parse_args()

    j, binc = load_glb(a.glb)
    base = [dict(nd) for nd in j["nodes"]]
    an = j["animations"][0]
    skin = j["skins"][0]
    joints = skin["joints"]
    ibm = np.transpose(acc(j, binc, skin["inverseBindMatrices"]).reshape(-1, 4, 4),
                       (0, 2, 1))
    prim = j["meshes"][0]["primitives"][0]
    at = prim["attributes"]
    Ph = sample_pts(j, binc)
    JI = acc(j, binc, at["JOINTS_0"]).astype(int)[: len(Ph)]
    Wt = acc(j, binc, at["WEIGHTS_0"])[: len(Ph)]

    def bbox_center():
        W = world_matrices(j)
        JM = np.stack([W.get(joints[k], np.eye(4)) @ ibm[k] for k in range(len(joints))])
        out = np.zeros((len(Ph), 3))
        for k in range(4):
            w = Wt[:, k:k + 1]
            if not w.any():
                continue
            out += w * np.einsum("nij,nj->ni", JM[JI[:, k]], Ph)[:, :3]
        return (out.min(0) + out.max(0)) / 2

    ref = bbox_center()
    print(f"绑定姿态中心 {np.round(ref,2)}")
    hits = []
    for ci, ch in enumerate(an["channels"]):
        if ch["target"]["path"] != "translation":
            continue
        s = an["samplers"][ch["sampler"]]
        vals = acc(j, binc, s["output"])
        node = ch["target"]["node"]
        j["nodes"][node]["translation"] = [float(x) for x in vals[0]]
        c = bbox_center()
        d = float(np.linalg.norm(c - ref))
        j["nodes"] = [dict(nd) for nd in base]
        if d >= a.thr:
            hits.append((d, node, j["nodes"][node].get("name"), np.round(c, 2)))
    hits.sort(reverse=True)
    print(f"单独造成 ≥{a.thr} 位移的通道 {len(hits)} 条：")
    for d, node, nm, c in hits[:12]:
        print(f"   {d:8.2f}  node{node:3d} {nm:28s} 中心 {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
