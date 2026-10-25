# -*- coding: utf-8 -*-
"""对比同一套 Spine 里两个动画变体的同帧画面，输出拼图。

用法：
  python compare_anims.py <spine_dir> <stem> <animA> <animB> <out.png> [--at 0.5]
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_spine_seq as R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sdir")
    ap.add_argument("stem")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("out")
    ap.add_argument("--at", type=float, default=0.5, help="取动画时长的哪一段")
    ap.add_argument("--height", type=int, default=560)
    a = ap.parse_args()
    sdir = Path(a.sdir)

    imgs = []
    for anim in (a.a, a.b):
        # 直接取分位框 BBq（比 BB 抗离群），自己解日志避开 probe_bbox 的严格正则
        _i, log0 = R._run_chrome(sdir, a.stem, a.height, 20.0, anim, 0, 0, "bb", mode="bb")
        m = re.search(r"BBq ([\-0-9.,]+)", log0) or re.search(r"BB ([\-0-9.,]+)", log0)
        ma = re.search(r"anim=(\S+) dur=([0-9.]+) frames=(\d+)", log0)
        if not (m and ma):
            print(f"[{anim}] 探测失败 {log0[:200]}")
            continue
        bb, an, dur, total = m.group(1), ma.group(1), ma.group(2), int(ma.group(3))
        f0 = int(total * a.at)
        info, log = R._one_batch(sdir, a.stem, a.height, 20.0, an, f0, 1, "c", bb)
        if info is None:
            print(f"[{anim}] 渲染失败 {log[:200]}")
            continue
        sh = info["sheet"]
        W, H = info["W"], info["H"]
        cell = sh.crop((0, 0, W, H))
        imgs.append((anim, cell))
        print(f"[{anim}] {an} dur={dur}s frames={total} bb={bb} cell={W}x{H}")

    if not imgs:
        raise SystemExit("两张都没渲出来")
    W = sum(i.size[0] for _, i in imgs) + 20 * (len(imgs) - 1)
    H = max(i.size[1] for _, i in imgs)
    cv = Image.new("RGB", (W, H), (250, 250, 250))
    x = 0
    for _, im in imgs:
        cv.paste(im, (x, 0))
        x += im.size[0] + 20
    cv.save(a.out)
    print(f"[out] {a.out} {W}x{H}  ({' | '.join(n for n, _ in imgs)})")


if __name__ == "__main__":
    main()
