# -*- coding: utf-8 -*-
"""多判充能点位扫描（移植自 Nikke_ChargeMap 的 scan_px/scan_best 思路，改喂我们的 asm.json）。

原理（依据 ChargeMap docs/02-充能点算法.md，ConfigBattleTable 实证）：
  一次攻击的爆裂充能 = 命中件数 × per_shot
  即充能与「一枪穿几件」成正比，与伤害无关 → 只要最大化命中件数。

链路：
  枪口 org = slots[k].character + (0, GUN_H, 0)
  瞄准方向 (yaw, pitch) → 射线 → 数 soft/medium/hard 里被打穿的**不同物体**数
  遮挡：ground / static_object / cover_object 命中距离 < 目标距离时，目标作废
  自家掩体（cover_object）既不计段数，也挡视线

与 ChargeMap 的差异（必须写清楚，避免被当成同口径）：
  1. 他们的 assemble 用 `g/n/v/i` 短键，我们的 asm 用 `root/name/v/tri`
  2. 他们的相机俯角由运行时 Cinemachine 驱动（未实证），我们同样没有 Camera 组件，
     只用 angular 域本身（不含相机），所以**点位以角度给出，像素位置单独按阵位相机投影**
  3. 不做蒙特卡洛（缺相机标定），只报「峰值段数 + 1°窗口稳定段数」，不给 A/B/C/D 等级

用法：
  python scan_charge_points.py asm_sbg_001.json [--step 0.25] [--yaw -45,45] [--pitch -6,30]
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

HITBOX = {"soft": 100, "medium": 500, "hard": 1000}
BLOCK = {"ground", "static_object", "cover_object"}
MAX_SPAN = 60.0      # 超远景件剔除（m）
MAX_DIST = 60.0      # 命中距离上限（m）
MIN_DIST = 0.8       # 太近的不算（贴着枪口）
GUN_H = 1.45         # 枪口相对脚下高度（ChargeMap 的表现参数）


def load_asm(path):
    A = json.loads(Path(path).read_text(encoding="utf-8"))
    hit_v, hit_own, hit_name, hit_grp = [], [], [], []
    blk_v = [], [], []
    blk_v = []
    objs = []
    skipped = {"huge": 0, "noncol": 0}
    for p in A["props"]:
        root = p.get("root")
        V = np.array(p.get("v") or [], float)
        idx = np.array(p.get("tri") or [], np.int64)
        if len(V) == 0 or len(idx) < 3:
            continue
        span = float(np.max(V.max(0) - V.min(0)))
        if span > MAX_SPAN:
            skipped["huge"] += 1
            continue
        if root in HITBOX:
            oi = len(objs)
            objs.append(dict(name=p["name"], grp=root, hp=HITBOX[root], span=round(span, 2),
                             center=[round(float(x), 2) for x in V.mean(0)]))
            for t in idx.reshape(-1, 3):
                if t.max() < len(V):
                    hit_v.append(V[t])
                    hit_own.append(oi)
        elif root in BLOCK:
            for t in idx.reshape(-1, 3):
                if t.max() < len(V):
                    blk_v.append(V[t])
    hit_tri = np.array(hit_v, float) if hit_v else np.zeros((0, 3, 3))
    blk_tri = np.array(blk_v, float) if blk_v else np.zeros((0, 3, 3))
    return A, objs, hit_tri, np.array(hit_own, np.int32), blk_tri, skipped


def ray_dirs(yaw, pitch):
    """yaw 绕 Y（0 = +Z），pitch 抬起为正。"""
    y = np.radians(yaw)
    p = np.radians(pitch)
    return np.stack([np.sin(y) * np.cos(p), np.sin(p), np.cos(y) * np.cos(p)], -1)


def seg_dist(org, dirs, tri):
    """Möller–Trumbore：返回 (M, T) 距离矩阵，未命中为 inf。"""
    v0 = tri[:, 0, :]
    e1 = tri[:, 1, :] - v0
    e2 = tri[:, 2, :] - v0
    pv = np.cross(dirs[:, None, :], e2[None, :, :])
    det = np.einsum("tj,mtj->mt", e1, pv)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    tv = org[None, None, :] - v0[None, :, :]
    u = np.einsum("mtj,mtj->mt", np.broadcast_to(tv, (len(dirs),) + tv.shape[1:]), pv) * inv
    qv = np.cross(tv, e1[None, :, :])
    vv = np.einsum("mj,mtj->mt", dirs, qv) * inv
    t = np.einsum("tj,mtj->mt", e2, qv) * inv
    hit = ok & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (t > MIN_DIST)
    return np.where(hit, t, np.inf)


def count_segments(org, dirs, hit_tri, hit_own, blk_tri, nobj, batch=128):
    """逐方向数「穿透件数」；返回 (n_obj, detail) 列表，detail 为 [(obj, dist)]。"""
    M = len(dirs)
    n = np.zeros(M, np.int16)
    det = [None] * M
    for s in range(0, M, batch):
        d = dirs[s:s + batch]
        th = seg_dist(org, d, hit_tri) if len(hit_tri) else np.full((len(d), 0), np.inf)
        tb = seg_dist(org, d, blk_tri) if len(blk_tri) else np.full((len(d), 0), np.inf)
        bd = tb.min(1) if tb.shape[1] else np.full(len(d), np.inf)
        bd = np.minimum(bd, MAX_DIST)
        for i in range(len(d)):
            row = th[i]
            m = row < bd[i]
            if not m.any():
                continue
            own = hit_own[m]
            tt = row[m]
            first = {}
            for o, t in zip(own.tolist(), tt.tolist()):
                if o not in first or t < first[o]:
                    first[o] = t
            n[s + i] = len(first)
            det[s + i] = sorted(first.items(), key=lambda x: x[1])
    return n, det


def min_filter(cnt, k):
    if k <= 1:
        return cnt.copy()
    pad = k // 2
    a = np.pad(cnt, pad, mode="edge")
    h, w = cnt.shape
    return np.min(np.stack([a[dj:dj + h, di:di + w] for dj in range(k) for di in range(k)]), 0)


def slot_camera(A, slot):
    s = A["slots"][slot]
    cam = np.array(s["camera"], float)
    ax = s.get("axes") or {}
    fwd = np.array(ax["fwd"], float)
    right = np.array(ax["right"], float)
    up = np.array(ax["up"], float)
    for v in (fwd, right, up):
        v /= np.linalg.norm(v)
    return cam, fwd, right, up


def to_pixel(A, slot, org, yaw, pitch, W=1600, H=900, fov=60.0, dist=20.0):
    """把「枪口方向」换成该阵位相机下的屏幕像素（准星位置）。
    注意：准星与枪口不是同一点（相机在角色后上方），所以这里直接投枪口射线上一点，
    与 ChargeMap 的「像素反推枪口角」是反方向，数值会差几像素，仅作标注参考。"""
    cam, fwd, right, up = slot_camera(A, slot)
    dirs = ray_dirs(yaw, pitch)
    P = org + dirs * dist
    v = P - cam
    tf = math.tan(math.radians(fov) / 2)
    aspect = W / H
    z = v @ fwd
    if z <= 0.1:
        return None
    sx = (v @ right) / (z * tf * aspect) * 0.5 + 0.5
    sy = 0.5 - (v @ up) / (z * tf) * 0.5
    return [round(float(sx * W), 1), round(float(sy * H), 1)]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    step = 0.25
    yaw_r = (-45.0, 45.0)
    pitch_r = (-6.0, 30.0)
    for a in sys.argv[1:]:
        if a.startswith("--step="):
            step = float(a.split("=")[1])
        elif a.startswith("--yaw="):
            v = a.split("=")[1].split(","); yaw_r = (float(v[0]), float(v[1]))
        elif a.startswith("--pitch="):
            v = a.split("=")[1].split(","); pitch_r = (float(v[0]), float(v[1]))
    src = Path(args[0])
    A, objs, hit_tri, hit_own, blk_tri, skipped = load_asm(src)
    print("%s  hitbox obj=%d tri=%d | block tri=%d | 剔除远景 %d" % (
        src.name, len(objs), len(hit_tri), len(blk_tri), skipped["huge"]))
    for o in objs:
        print("   %-6s %-44s hp %4d  span %.1f" % (o["grp"], o["name"][:44], o["hp"], o["span"]))

    gy = np.round(np.arange(yaw_r[0], yaw_r[1] + 1e-9, step), 4)
    gp = np.round(np.arange(pitch_r[0], pitch_r[1] + 1e-9, step), 4)
    out = dict(scene=src.stem, step=step, yaw=list(yaw_r), pitch=list(pitch_r),
               gun_h=GUN_H, hitbox=HITBOX, blocked_from=sorted(BLOCK),
               note="段数=单发穿透的可破坏物件数；遮挡与自家掩体已截断；角度为枪口方向",
               objects=objs, slots={})
    for k, s in enumerate(A["slots"], 1):
        org = np.array(s["character"], float) + np.array([0, GUN_H, 0])
        YY, PP = np.meshgrid(gy, gp)
        dirs = ray_dirs(YY.ravel(), PP.ravel())
        n, det = count_segments(org, dirs, hit_tri, hit_own, blk_tri, len(objs))
        cnt = n.reshape(len(gp), len(gy))
        k1 = max(1, int(round(1.0 / step)) | 1)
        e1 = min_filter(cnt, k1)
        mx = int(cnt.max())
        r1 = int(e1.max())
        # 推荐点 = 1° 窗口内不掉段的格里段数最高者
        rec = None
        if r1 > 0:
            cand = np.where(e1 == r1)
            best = int(np.argmax(cnt[cand]))
            j, i = int(cand[0][best]), int(cand[1][best])
            yaw, pit = float(gy[i]), float(gp[j])
            idx = j * len(gy) + i
            # 同格 ±1 邻域里取段数最高（并列取更靠中心）
            hits = det[idx] or []
            rec = dict(yaw=yaw, pitch=pit, n=int(cnt[j, i]), n_1deg=r1,
                       objs=[dict(name=objs[o]["name"], grp=objs[o]["grp"], hp=objs[o]["hp"],
                                  d=round(float(t), 2), center=objs[o]["center"])
                             for o, t in hits],
                       pixel=to_pixel(A, k - 1, org, yaw, pit,
                                      dist=(hits[0][1] if hits else 20.0)))
        hist = {str(v): int((cnt == v).sum()) for v in range(mx, 0, -1)}
        out["slots"][str(k)] = dict(cover=s["cover"], char=s["character"],
                                    origin=[round(float(x), 3) for x in org],
                                    n_max=mx, n_1deg=r1, rec=rec, hist=hist)
        print("  阵位%d  org %s  峰值 %d 段  1°稳定 %d 段  推荐 %s" % (
            k, [round(float(x), 2) for x in org], mx, r1,
            ("yaw%+.2f pitch%+.2f  %d件" % (rec["yaw"], rec["pitch"], rec["n"])) if rec else "-"))
        if rec:
            print("        命中：" + ", ".join("%s(%.1fm)" % (o["name"][:28], o["d"]) for o in rec["objs"]))
    dst = src.with_name(src.stem.replace("asm_", "charge_") + ".json")
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", dst)


if __name__ == "__main__":
    main()
