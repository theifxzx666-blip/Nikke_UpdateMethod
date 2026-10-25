# -*- coding: utf-8 -*-
"""按「整段动画的包络」算取景框，写成 framing.js 给 3D 查看器用。

为什么需要：查看器的 fit() 用的是加载那一刻的包围盒 —— 那是**绑定姿态**。
但 BOSS 的登场 / 战败动画里有真实的大位移（安尼希利奥登场是从上方落下，
莉贝雷利奥战败是环状部件炸开），绑定姿态的镜头框不住整段动画，
GIF 后半段就只剩背景。

有人会问能不能把这些位移当 root motion 掐掉 —— 实测不行，也不该：
  · 对这批 glb 做「通道减首帧值」，包络和不动完全一样（首帧值本来就是 0）
  · 对 flagged 通道做「冻结」，eba002_2phase_death 的包络仍然 403（绑定只有 33）
  · 而 eba002_2phase_death 顶部通道是 ringtail/circle 一族，末值各自飞到
    x≈262 / y≈245 / z≈195 —— 部件四散，这不是 bug，是爆炸演出本身
所以改取景，不动数据。

输出（3D查看器/framing.js）：
  window.__FRAMING = { "xba003_1phase_appearance.glb": {center:[..], size:[..]}, ... }
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from probe_glb_skin_bbox import acc, world_matrices, MODELS  # noqa: E402

OUT = MODELS.parent / "framing.js"
NFRAME = 32          # 扫多少帧（均匀覆盖整段动画）


def load(fn):
    b = (MODELS / fn).read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    j = json.loads(b[20:20 + n].decode("utf-8"))
    off = 20 + n
    ln = struct.unpack_from("<I", b, off)[0]
    return j, b[off + 8: off + 8 + ln]


def skinned_points(j, binc, cap=4000):
    """蒙皮后的顶点云（下采样到 cap 个），用来做稳健取景统计。

    为什么不用包围盒：莉贝雷利奥战败是环状部件炸开，包围盒被飞散的碎件撑到
    92×369×399（绑定只有 24×33×14）。拿 min/max 定的中点和半径全被碎件带跑，
    主体缩成一个点。改用中位数（对飞出去的少数点不敏感）+ 分位数半径。
    """
    pts = []
    if "skins" in j:
        for s in j["skins"]:
            joints = s["joints"]
            ibm = np.transpose(acc(j, binc, s["inverseBindMatrices"]).reshape(-1, 4, 4),
                               (0, 2, 1))
            W = world_matrices(j)
            JM = np.stack([W.get(joints[k], np.eye(4)) @ ibm[k]
                           for k in range(len(joints))])
            for m in j["meshes"]:
                for p in m["primitives"]:
                    at = p["attributes"]
                    if at.get("JOINTS_0") is None:
                        continue
                    P = acc(j, binc, at["POSITION"])
                    JI = acc(j, binc, at["JOINTS_0"]).astype(int)
                    Wt = acc(j, binc, at["WEIGHTS_0"])
                    Ph = np.concatenate([P, np.ones((len(P), 1))], axis=1)
                    out = np.zeros((len(P), 3))
                    for k in range(4):
                        w = Wt[:, k:k + 1]
                        if not w.any():
                            continue
                        out += w * np.einsum("nij,nj->ni", JM[JI[:, k]], Ph)[:, :3]
                    pts.append(out)
        if not pts:
            return None
        V = np.concatenate(pts)
    else:
        W = world_matrices(j)
        for ni, nd in enumerate(j["nodes"]):
            if "mesh" not in nd:
                continue
            M = W.get(ni, np.eye(4))
            for p in j["meshes"][nd["mesh"]]["primitives"]:
                P = acc(j, binc, p["attributes"]["POSITION"])
                Ph = np.concatenate([P, np.ones((len(P), 1))], axis=1)
                pts.append(np.einsum("ij,nj->ni", M, Ph)[:, :3])
        if not pts:
            return None
        V = np.concatenate(pts)
    if len(V) > cap:
        V = V[np.linspace(0, len(V) - 1, cap).astype(int)]
    return V


def robust_frame(V):
    """(中心, 半径)：中心取分量中位数，半径取 92 分位到中心的距离。"""
    c = np.median(V, axis=0)
    d = np.linalg.norm(V - c, axis=1)
    r = float(np.percentile(d, 92)) * 2.0
    return c, max(r, 1e-3)


def skinned_bbox(j, binc):
    lo = np.full(3, 1e9)
    hi = np.full(3, -1e9)
    if "skins" in j:
        for s in j["skins"]:
            joints = s["joints"]
            ibm = np.transpose(acc(j, binc, s["inverseBindMatrices"]).reshape(-1, 4, 4),
                               (0, 2, 1))
            W = world_matrices(j)
            JM = np.stack([W.get(joints[k], np.eye(4)) @ ibm[k]
                           for k in range(len(joints))])
            for m in j["meshes"]:
                for p in m["primitives"]:
                    at = p["attributes"]
                    if at.get("JOINTS_0") is None:
                        continue
                    P = acc(j, binc, at["POSITION"])
                    JI = acc(j, binc, at["JOINTS_0"]).astype(int)
                    Wt = acc(j, binc, at["WEIGHTS_0"])
                    Ph = np.concatenate([P, np.ones((len(P), 1))], axis=1)
                    out = np.zeros((len(P), 3))
                    for k in range(4):
                        w = Wt[:, k:k + 1]
                        if not w.any():
                            continue
                        out += w * np.einsum("nij,nj->ni", JM[JI[:, k]], Ph)[:, :3]
                    lo = np.minimum(lo, out.min(0))
                    hi = np.maximum(hi, out.max(0))
        return lo, hi
    # 无骨骼：直接用节点世界矩阵变换顶点
    W = world_matrices(j)
    for ni, nd in enumerate(j["nodes"]):
        if "mesh" not in nd:
            continue
        M = W.get(ni, np.eye(4))
        for p in j["meshes"][nd["mesh"]]["primitives"]:
            P = acc(j, binc, p["attributes"]["POSITION"])
            Ph = np.concatenate([P, np.ones((len(P), 1))], axis=1)
            out = np.einsum("ij,nj->ni", M, Ph)[:, :3]
            lo = np.minimum(lo, out.min(0))
            hi = np.maximum(hi, out.max(0))
    return lo, hi


def set_frame(j, binc, frame):
    if not j.get("animations"):
        return False
    an = j["animations"][0]
    for ch in an["channels"]:
        s = an["samplers"][ch["sampler"]]
        v = acc(j, binc, s["output"])
        k = min(frame, len(v) - 1)
        nd = j["nodes"][ch["target"]["node"]]
        nd[ch["target"]["path"]] = [float(x) for x in v[k]]
    return True


def envelope(fn):
    """返回 (稳健中心, 稳健半径, 逐帧 [[cx,cy,cz,r], ...], 关键帧数)

    每帧 r 再做 ±2 帧滑动取大，避免距离忽大忽小地"呼吸"。
    """
    j, binc = load(fn)
    bind = [dict(nd) for nd in j["nodes"]]
    V0 = skinned_points(j, binc)
    bc, br = robust_frame(V0)
    if not j.get("animations"):
        return bc, br, [], 0
    an = j["animations"][0]
    L = max(len(acc(j, binc, s["output"])) for s in an["samplers"])
    per = []
    for f in range(NFRAME):
        j["nodes"] = [dict(nd) for nd in bind]
        set_frame(j, binc, int((L - 1) * f / max(1, NFRAME - 1)))
        V = skinned_points(j, binc)
        per.append(robust_frame(V) if V is not None else (bc, br))
    j["nodes"] = bind
    # 整段用同一个镜头距离，只跟中心。
    # 早先试过逐帧各自算距离，结果是「镜头忽近忽远」：安尼希利奥登场前两帧被上下裁掉、
    # 后两帧缩成一小块。
    # 半径再设一个上限（绑定姿态的 3 倍）：莉贝雷利奥战败的 92 分位半径是 378，
    # 而主体只有 28 —— 直接用会把主体缩成一个点。超过上限的部分是飞散的碎屑，
    # 允许它们出画，主体保证完整。上限取 3.0 是权衡后的值：取 4.5 时战败那条
    # 主体只占画面约五分之一，预览图里几乎看不清；3.0 只影响到战败与登场两条。
    rs = [p[1] for p in per]
    rfix = min(max(rs), br * 3.0)
    track = [[round(float(x), 3) for x in per[i][0]] + [round(rfix, 3)]
             for i in range(len(per))]
    # 交互查看用的静态框：中心取各帧中心的中位数，边长取上面那个固定半径
    centers = np.array([p[0] for p in per])
    uc = np.median(centers, axis=0)
    ur = rfix
    return uc, ur, track, L


def main():
    files = sorted(p.name for p in MODELS.glob("*.glb"))
    data = {}
    print(f"{'文件':<34}{'半径 绑定→包络':>20}{'中心漂移':>22}  说明")
    for fn in files:
        c, r, track, L = envelope(fn)
        if not np.isfinite(c).all():
            print(f"{fn:<34}  空")
            continue
        j, binc = load(fn)
        bind_c, br = robust_frame(skinned_points(j, binc))
        # 交互查看用的是 bind 的真实包围盒（不是稳健分位数）：
        # 绑定姿态没有碎屑问题，只要把模型完整包住就行。
        # 用 92 分位半径会切掉尖端 —— 莉贝雷利奥战败的首帧实测 y 跨 -22.6~9.9，
        # 而 92 分位只覆盖到 ±13.9，紫色部件贴到画顶被裁。
        Vb = skinned_points(j, binc)
        b_lo = Vb.min(axis=0)
        b_hi = Vb.max(axis=0)
        b_size = np.maximum(b_hi - b_lo, 1e-3)
        if track:
            cs = np.array([t[:3] for t in track])
            drift = float(np.linalg.norm(cs - np.median(cs, axis=0), axis=1).max())
            rmax = max(t[3] for t in track)
        else:
            drift, rmax = 0.0, r
        data[fn] = {
            "union": {"center": [round(float(x), 3) for x in c],
                      "size": [round(float(r), 3)] * 3},
            "bind": {"center": [round(float(x), 3) for x in ((b_lo + b_hi) / 2)],
                     "size": [round(float(x), 3) for x in b_size],
                     "radius": round(float(br), 3)},
            "track": track,
        }
        tag = "动画带大位移" if (rmax / max(br, 1e-6) > 1.6 or drift > br * 1.5) else ""
        print(f"{fn:<34}{br:7.1f} → {rmax:6.1f}{drift:14.1f}"
              f"  帧{L:>4} {tag}")
    OUT.write_text(
        "// 由 build_anim_framing.py 生成，勿手改。\n"
        "// 全部走「稳健统计」：中心 = 蒙皮顶点分量中位数，半径 = 92 分位距离 ×2。\n"
        "// 不用包围盒 min/max —— 莉贝雷利奥战败是环状部件炸开，包围盒被碎件撑到 29 倍，\n"
        "// 按它取景主体会缩成一个点。\n"
        "// union: 交互查看用的静态框（center + size，立方体边长）。\n"
        "// track: 逐帧 [cx,cy,cz,r]，GIF 导出逐帧跟随，r 已做 ±2 帧滑动取大。\n"
        "// bind:  绑定姿态的中心与半径，用于判断这条动画到底把画面撑大了多少。\n"
        "window.__FRAMING = " + json.dumps(data, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print("\n->", OUT, f"{len(data)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
