# -*- coding: utf-8 -*-
"""修「动画把整具模型搬到画面外」—— 把根节点的位移通道相对化。

背景（2026-10-25 实测 `xba003_2phase_death.glb`）：
  查看器里渲染全黑。逐层排查排除了数据损坏：
    · 与 idle 版 glb 相比，节点 TRS / IBM / 贴图(md5) / 权重完全一致
    · 动画通道无 NaN/Inf，数值范围也不夸张
  numpy 直接做 LBS 后发现首帧蒙皮包围盒落在 min=[-14.65,116.41,-106.43]
  max=[14.59,155.44,-87.54] —— 形状正常（29×39×19，与 idle 同），
  位置在 y≈136、z≈-97，也就是被抬到 100 多米外。
  再用「单通道隔离法」定位到唯一元凶：

      node 5  root2_phase2  的 translation 通道
      单独应用首帧值 → 模型中心 (-0.07, 139.39, -97.74)

  也就是说死亡动画把整个 root2 节点挪走了，模型自然在画框外；
  GIF 导出逐帧量「可见像素」量到的全是背景，于是报「采样到的颜色太少」。

修法：这类通道**减去自身首帧值**（相对化）。动画里的相对运动全部保留，
只是不再跑到一百米外。已经相对化的文件再跑一次不会有变化（位移 < 阈值即跳过）。

用法：
  python fix_glb_offset.py --all          # SRC（原始导出）→ models/
  python fix_glb_offset.py --all --dry    # 只报告
  python fix_glb_offset.py xba003_2phase_death.glb
"""
import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from probe_glb_skin_bbox import MODELS, acc, load_glb as _load_models, world_matrices  # noqa: E402

# 原始导出目录：从原件读、往 models 写，避免重复运行在已修的文件上再叠一次
SRC = Path(r"D:\Codex\临时\nikke_intl_20261029\out\glb")
THR = 40.0        # 单独造成这么大的位移就认为是「被搬走了」
NPTS = 600        # 检测时用的采样顶点数


def load_glb(fn):
    p = SRC / fn
    if not p.exists():
        return _load_models(fn)
    b = p.read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    j = json.loads(b[20:20 + n].decode("utf-8"))
    off = 20 + n
    ln = struct.unpack_from("<I", b, off)[0]
    return j, b[off + 8: off + 8 + ln]


def write_glb(fn, j, binc):
    js = json.dumps(j, separators=(",", ":")).encode("utf-8")
    while len(js) % 4:
        js += b" "
    while len(binc) % 4:
        binc += b"\x00"
    total = 12 + 8 + len(js) + 8 + len(binc)
    out = bytearray()
    out += b"glTF" + struct.pack("<II", 2, total)
    out += struct.pack("<I", len(js)) + b"JSON" + js
    out += struct.pack("<I", len(binc)) + b"BIN\x00" + binc
    (MODELS / fn).write_bytes(bytes(out))


def analyze(j, binc):
    """返回 [(通道下标, 节点下标, 节点名, 位移量)] —— 只是应用首帧就能搬走模型的通道。"""
    an = j["animations"][0]
    skin = j["skins"][0]
    joints = skin["joints"]
    ibm = np.transpose(acc(j, binc, skin["inverseBindMatrices"]).reshape(-1, 4, 4),
                       (0, 2, 1))
    prim = j["meshes"][0]["primitives"][0]
    at = prim["attributes"]
    P = acc(j, binc, at["POSITION"])
    idx = np.linspace(0, len(P) - 1, min(NPTS, len(P))).astype(int)
    Ph = np.concatenate([P[idx], np.ones((len(idx), 1))], axis=1)
    JI = acc(j, binc, at["JOINTS_0"]).astype(int)[idx]
    Wt = acc(j, binc, at["WEIGHTS_0"])[idx]
    base = [dict(nd) for nd in j["nodes"]]

    def center():
        W = world_matrices(j)
        JM = np.stack([W.get(joints[k], np.eye(4)) @ ibm[k] for k in range(len(joints))])
        out = np.zeros((len(Ph), 3))
        for k in range(4):
            w = Wt[:, k:k + 1]
            if not w.any():
                continue
            out += w * np.einsum("nij,nj->ni", JM[JI[:, k]], Ph)[:, :3]
        return (out.min(0) + out.max(0)) / 2

    ref = center()
    hits = []
    for ci, ch in enumerate(an["channels"]):
        if ch["target"]["path"] != "translation":
            continue
        vals = acc(j, binc, an["samplers"][ch["sampler"]]["output"])
        node = ch["target"]["node"]
        j["nodes"][node]["translation"] = [float(x) for x in vals[0]]
        d = float(np.linalg.norm(center() - ref))
        j["nodes"] = [dict(nd) for nd in base]
        if d >= THR:
            hits.append((ci, node, j["nodes"][node].get("name"), d))
    return hits


def fix(fn, dry=False):
    j, binc = load_glb(fn)
    hits = analyze(j, binc)
    if not hits:
        print(f"  {fn:34s} 无异常位移通道 —— 不动")
        return 0
    names = ", ".join(f"{nm}({d:.0f})" for _, _, nm, d in hits)
    if dry:
        print(f"  {fn:34s} 需相对化：{names}")
        return 1
    an = j["animations"][0]
    for ci, node, nm, _ in hits:
        ch = an["channels"][ci]
        s = an["samplers"][ch["sampler"]]
        a = j["accessors"][s["output"]]
        bv = j["bufferViews"][a["bufferView"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        buf = bytearray(binc)
        vals = np.frombuffer(bytes(buf[off:off + a["count"] * 12]), np.float32) \
                 .reshape(-1, 3).astype(np.float64)
        base = vals[0].copy()
        vals -= base
        buf[off:off + a["count"] * 12] = np.asarray(vals, np.float32).tobytes()
        binc = bytes(buf)
    write_glb(fn, j, binc)
    print(f"  {fn:34s} 已相对化：{names}")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    files = a.glb
    if a.all:
        files = sorted(p.name for p in SRC.glob("*.glb"))
    if not files:
        print(__doc__)
        return 1
    n = 0
    for f in files:
        n += fix(f, dry=a.dry)
    print(f"\n{'需处理' if a.dry else '已处理'} {n} / {len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
