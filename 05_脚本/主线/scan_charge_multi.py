# -*- coding: utf-8 -*-
"""多判充能点位：每阵位输出 Top-K 个互相分开的多判点，并剔除单判点。

与 scan_charge_points.py 的区别（口径一致，只改采集与筛选）：
  1. 判定口径完全沿用 scan_charge_points（0.25° 栅格、Möller–Trumbore、
     ground/static_object/cover_object 遮挡截断、按 owner 去重计件）
  2. 1° 方框最小值腐蚀后的段数 < 2 的点位**直接丢弃**（单判点不要）
  3. 每阵位不再只报 1 个推荐点，而是在多判格里按段数降序贪心取 Top-K，
     相邻点之间要求角度间距 >= SPREAD 度，避免 6 个点挤在同一簇

用法：
  python scan_charge_multi.py asm_sbg_001.json asm_sbg_002.json asm_sbg_003.json
输出：
  out/charge_multi_<场景>.json + 汇总 tsv（由 build 侧写入业务目录）
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_charge_points import (  # noqa: E402
    GUN_H, HITBOX, load_asm, ray_dirs, count_segments, min_filter, to_pixel,
)

STEP = 0.25
YAW = (-45.0, 45.0)
PITCH = (-6.0, 30.0)
TOPK = 6          # 每阵位最多输出几个多判点
MIN_SEG = 2       # 多判门槛：稳定段数 >= 2
SPREAD = 2.0      # 相邻候选点的最小角距（度）


def pick_top(e1, cnt, gy, gp, k=TOPK, min_seg=MIN_SEG, spread=SPREAD):
    """贪心取 Top-K 多判点，彼此角距 >= spread。

    排序键 = (1°窗口稳定段数, 峰值段数) 双降序 —— 先给实战能站住的点，
    再给「峰值够但窗口窄」的点（这类点在 003 战场是唯一能拿到的多判点）。
    门槛作用在**峰值段数**上：峰值 < min_seg 视为单判，直接丢弃。
    """
    stable = e1.astype(np.int32)
    raw = cnt.astype(np.int32)
    ok = raw >= min_seg
    if not ok.any():
        return []
    key = (stable[ok] * 100 + raw[ok])
    flats = np.nonzero(ok.ravel())[0]
    order = np.argsort(-key, kind="stable")
    out = []
    for flat in flats[order]:
        j, i = divmod(int(flat), len(gy))
        yaw, pit = float(gy[i]), float(gp[j])
        if any((yaw - p[0]) ** 2 + (pit - p[1]) ** 2 < spread ** 2 for p in out):
            continue
        out.append((yaw, pit, int(raw[j, i]), j, i))
        if len(out) >= k:
            break
    return out


def main():
    paths = [Path(a) for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a.startswith("--topk="):
            globals()["TOPK"] = int(a.split("=")[1])
        elif a.startswith("--step="):
            globals()["STEP"] = float(a.split("=")[1])
    gy = np.round(np.arange(YAW[0], YAW[1] + 1e-9, STEP), 4)
    gp = np.round(np.arange(PITCH[0], PITCH[1] + 1e-9, STEP), 4)

    for src in paths:
        A, objs, hit_tri, hit_own, blk_tri, skipped = load_asm(src)
        scene = A.get("scene") or src.stem.replace("asm_", "")
        res = dict(scene=scene, step=STEP, yaw=list(YAW), pitch=list(PITCH),
                   gun_h=GUN_H, hitbox=HITBOX,
                   note="段数=单发穿透的可破坏物件数；遮挡与自家掩体已截断；"
                        "只保留 1° 窗口稳定段数>=2 的多判点",
                   objects=objs, slots={})
        print(f"\n=== {scene}  hitbox={len(objs)} obj  block_tri={len(blk_tri)} "
              f"剔除远景={skipped['huge']}")
        for k, s in enumerate(A["slots"], 1):
            org = np.array(s["character"], float) + np.array([0, GUN_H, 0])
            YY, PP = np.meshgrid(gy, gp)
            dirs = ray_dirs(YY.ravel(), PP.ravel())
            n, det = count_segments(org, dirs, hit_tri, hit_own, blk_tri, len(objs))
            cnt = n.reshape(len(gp), len(gy))
            k1 = max(1, int(round(1.0 / STEP)) | 1)
            e1 = min_filter(cnt, k1)
            picks = pick_top(e1, cnt, gy, gp)
            pts = []
            for r, (yaw, pit, v, j, i) in enumerate(picks, 1):
                idx = j * len(gy) + i
                hits = det[idx] or []
                pts.append(dict(
                    rank=r, yaw=round(yaw, 2), pitch=round(pit, 2),
                    n_seg=int(cnt[j, i]), n_1deg=int(e1[j, i]),
                    stable=bool(e1[j, i] >= MIN_SEG),
                    charge=int(cnt[j, i]) * 4,
                    pixel=to_pixel(A, k - 1, org, yaw, pit,
                                   dist=(hits[0][1] if hits else 20.0)),
                    hits=[dict(name=objs[o]["name"], grp=objs[o]["grp"],
                               hp=objs[o]["hp"], d=round(float(t), 2))
                          for o, t in hits]))
            mx = int(cnt.max())
            res["slots"][str(k)] = dict(
                cover=s["cover"], char=s["character"],
                origin=[round(float(x), 3) for x in org],
                n_max=mx, n_1deg_max=int(e1.max()),
                multi_cells=int((cnt >= MIN_SEG).sum()),
                stable_cells=int((e1 >= MIN_SEG).sum()), points=pts)
            head = "  阵位%d 峰值%d段 稳定%d段 多判格%d个(其中1°稳定%d个)" % (
                k, mx, int(e1.max()), int((cnt >= MIN_SEG).sum()),
                int((e1 >= MIN_SEG).sum()))
            print(head)
            if not pts:
                print("        —— 无多判点（全部为单判，已剔除）")
            for p in pts:
                print("        #%d yaw%+7.2f pitch%+6.2f  %d件/%d点 %s 命中 %s" % (
                    p["rank"], p["yaw"], p["pitch"], p["n_seg"], p["charge"],
                    "稳" if p["stable"] else "窄",
                    ", ".join("%s(%.1fm)" % (h["name"][:22], h["d"]) for h in p["hits"])))
        dst = src.with_name(src.stem.replace("asm_", "charge_multi_") + ".json")
        dst.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print("->", dst)


if __name__ == "__main__":
    main()
