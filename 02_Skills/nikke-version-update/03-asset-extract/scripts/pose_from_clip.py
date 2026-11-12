# -*- coding: utf-8 -*-
"""从 muscle clip 里解出骨骼姿态（local TRS），供渲染器覆盖绑定姿态。

解出来的为什么不是「肌肉值」：
  这几份 idle 的 m_MuscleClip.m_IndexArray 200 项**全是 -1**，即 200 条肌肉 DoF
  全取常量 0（= 无旋转偏移）。真正在动的是 m_ClipBindingConstant.genericBindings
  里的 generic TRS 曲线（pos/rot/scale），共 278~873 条。

数据布局（全部实测确认，不是按文档推的）：
  - genericBindings[i] → (path hash, attribute)，attribute 1=pos(3float) 2=rot(4float) 3=scale(3float)
  - m_ValueArrayDelta：按 genericBindings 顺序、逐分量平铺，长度正好
    103*3 + 103*4 + 72*3 = 937（1 阶段）；每项 m_Start/m_Stop 就是首帧/末帧值
  - m_Clip.data.m_DenseClip.m_SampleArray：帧 × 曲线，按 (首帧值, 末帧值) 双值匹配
    可把每一列唯一对应到某个 (曲线, 分量)
  - Avatar.m_TOS：[(path hash, "root/.../骨骼名")]，hash 与 genericBindings.path 同一套

  rot 曲线按四元数取出后 |q| 实测全部 = 1.000（148/148），可用来校验匹配。
"""
from pathlib import Path

import numpy as np
import UnityPy

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
NF = {1: 3, 2: 4, 3: 3, 4: 3}
ANAME = {1: "pos", 2: "rot", 3: "scale", 4: "euler"}


def _clip_of(bundle_path):
    env = UnityPy.load(str(bundle_path))
    for o in env.objects:
        if o.type.name == "AnimationClip":
            return env, o.read_typetree()
    raise RuntimeError(f"没有 AnimationClip: {bundle_path}")


def _parse(clip):
    """返回 (gb, fmap, dense矩阵)。fmap[i] = (curveIdx, compIdx, start, stop)"""
    mc = clip["m_MuscleClip"]
    data = mc["m_Clip"]["data"]
    gb = clip["m_ClipBindingConstant"]["genericBindings"]
    delta = mc["m_ValueArrayDelta"]
    d = data["m_DenseClip"]
    F, C = d["m_FrameCount"], d["m_CurveCount"]
    A = np.array(d["m_SampleArray"], np.float32).reshape(F, C)

    fmap, fi = [], 0
    for ci_curve, g in enumerate(gb):
        for k in range(NF[g["attribute"]]):
            dv = delta[fi]
            fmap.append((ci_curve, k, float(dv["m_Start"]), float(dv["m_Stop"])))
            fi += 1
    if fi != len(delta):
        raise RuntimeError(f"delta 长度对不上：{fi} vs {len(delta)}")
    return gb, fmap, A


def _colmap(fmap, A, tol=1e-5):
    """Dense 列 → float 索引。(首帧, 末帧) 双值匹配。"""
    S = np.array([f[2] for f in fmap])
    T = np.array([f[3] for f in fmap])
    first, last = A[0], A[-1]
    used = np.zeros(len(fmap), bool)
    out = {}
    for dc in range(A.shape[1]):
        cand = np.where((np.abs(S - first[dc]) < tol) &
                        (np.abs(T - last[dc]) < tol) & (~used))[0]
        if len(cand) == 0:
            cand = np.where((np.abs(S - first[dc]) < 1e-3) & (~used))[0]
        if len(cand) == 0:
            out[dc] = None
            continue
        p = int(cand[0])
        used[p] = True
        out[dc] = p
    return out


def _fpos(fmap, colmap):
    """float 索引 → Dense 列（无则 None）"""
    r = {}
    for dc, p in colmap.items():
        if p is not None:
            r[p] = dc
    return r


def sample_curves(clip, frame):
    """取指定帧的所有曲线值。

    返回 {(path_hash, attribute): [分量值...]}，以及每条曲线的来源标记。
    """
    gb, fmap, A = _parse(clip)
    colmap = _colmap(fmap, A)
    fp = _fpos(fmap, colmap)
    frame = max(0, min(frame, A.shape[0] - 1))

    out = {}
    src = {"dense": 0, "const": 0, "missing": 0}
    for fi, (ci_curve, k, s, t) in enumerate(fmap):
        g = gb[ci_curve]
        key = (int(g["path"]), int(g["attribute"]))
        slot = out.setdefault(key, [None] * NF[g["attribute"]])
        if abs(s - t) <= 1e-9:
            slot[k] = s
            src["const"] += 1
        elif fi in fp:
            slot[k] = float(A[frame, fp[fi]])
            src["dense"] += 1
        else:
            slot[k] = s          # 兜底用参考值（实测未触发过）
            src["missing"] += 1
    return out, src, A.shape


def load_tos(bundle_path, phase):
    """读对应阶段的 Avatar.m_TOS → {path hash: 完整路径}"""
    env = UnityPy.load(str(bundle_path))
    tos, picked = {}, None
    for o in env.objects:
        if o.type.name != "Avatar":
            continue
        tt = o.read_typetree()
        nm = tt["m_Name"]
        if phase not in nm:
            continue
        picked = nm
        for k, p in tt["m_TOS"]:
            tos[int(k)] = str(p)
        break
    if not tos:
        raise RuntimeError(f"{bundle_path.name} 里没有 {phase} 的 Avatar")
    return tos, picked


def pose_for(monster_bundle, clip_bundle, phase, frame):
    """算出一帧的骨骼 local TRS 覆盖表 {GameObject path_id: (quat xyzw, pos xyz, scale xyz)}"""
    _, clip = _clip_of(clip_bundle)
    tos, avatar_name = load_tos(monster_bundle, phase)
    curves, src, shape = sample_curves(clip, frame)

    env = UnityPy.load(str(monster_bundle))
    # GameObject 名 → (path_id, 完整路径)
    tfs, go_name, father = {}, {}, {}
    for o in env.objects:
        if o.type.name != "Transform":
            continue
        d = o.read()
        tfs[o.path_id] = d
        go_name[d.m_GameObject.m_PathID] = o.path_id
        father[o.path_id] = d.m_Father.path_id if d.m_Father else 0

    gname = {}
    for o in env.objects:
        if o.type.name == "GameObject":
            gname[o.path_id] = o.read().m_Name

    def full_path(tid):
        parts, cur, guard = [], tid, 0
        while cur and cur in tfs and guard < 96:
            parts.append(gname.get(tfs[cur].m_GameObject.m_PathID, ""))
            cur = father[cur]
            guard += 1
        return "/".join(reversed(parts))

    # 路径 → transform path_id。
    # Avatar.m_TOS 里的路径是**相对模型根**写的（例如 "root/xba003_1phase_orbiter_01/..."），
    # 而 Transform 上溯得到的完整路径还多出
    # "xba003_dmtr/xba003_dmtr_resource/xba003_dmtr_model/xba003_1phase_var/" 这几层，
    # 所以用「后缀索引」匹配，并按阶段过滤（1phase 在 xba003_1phase_var 下，
    # 2phase 在 xbga03_2phase_var 下）。
    suf = {}
    for tid in tfs:
        fp_ = full_path(tid)
        if phase not in fp_:
            continue
        parts = fp_.split("/")
        for i in range(len(parts)):
            suf.setdefault("/".join(parts[i:]), []).append(tid)

    cur_by_path = {}
    for (h, attr), vals in curves.items():
        if None in vals:
            continue
        p = tos.get(h)
        if not p:
            continue
        tids = suf.get(p)
        if not tids:
            continue
        cur_by_path.setdefault(tuple(tids), {})[attr] = vals

    pose = {}
    n_hit = n_rot_ok = n_rot = 0
    for tids, d in cur_by_path.items():
        t = tfs[tids[0]]
        # 缺的分量沿用绑定姿态
        q = tuple(d[2]) if 2 in d else (
            t.m_LocalRotation.x, t.m_LocalRotation.y,
            t.m_LocalRotation.z, t.m_LocalRotation.w)
        pos = tuple(d[1]) if 1 in d else (
            t.m_LocalPosition.x, t.m_LocalPosition.y, t.m_LocalPosition.z)
        sc = tuple(d[3]) if 3 in d else (
            t.m_LocalScale.x, t.m_LocalScale.y, t.m_LocalScale.z)
        if 2 in d:
            n_rot += 1
            if abs(np.linalg.norm(q) - 1.0) < 0.05:
                n_rot_ok += 1
        for tid in tids:
            pose[tfs[tid].m_GameObject.m_PathID] = (q, pos, sc)
        n_hit += 1

    # 曲线里的唯一 path 数 —— 用来判断「这骨架是不是这条动画的那一条」
    n_path = len({int(g["path"]) for g in clip["m_ClipBindingConstant"]["genericBindings"]})
    if n_hit == 0 or (n_path >= 20 and n_hit < n_path * 0.15):
        # 静默返回空表/几乎空的表会一路滑到「0 条通道」的 glb —— 看起来导出成功，
        # 其实是个不动的静态模型，而且不会报错。这里直接掐断。
        # 实例：eba002_2phase_intro_01 按 2phase 取骨架只命中 1/338（实际绑 1 阶段骨架）；
        #      eba002_2phase_death_jelly 在本期两个模型包里 4 个 Avatar 全命中 0。
        raise RuntimeError(
            f"{clip_bundle.name} 的曲线与 {avatar_name} 对不上"
            f"（{n_path} 个唯一骨骼路径，只命中 {n_hit} 个）。"
            f"该动画绑的是另一套骨架：换个 phase 再取，或确认模型包里有没有对应形态。")

    return dict(pose=pose, stats=dict(
        avatar=avatar_name, frame=frame, frames=shape[0],
        curves=len(curves), bones_hit=n_hit, rot_curves=n_rot, rot_unit=n_rot_ok,
        src=src))
