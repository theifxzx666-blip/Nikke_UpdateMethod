# -*- coding: utf-8 -*-
"""直接用已导出的 spine 三件套重渲爆裂特写 GIF（不再需要原始 bundle）。

用法：
  python drive_render.py <spine_dir> <stem> <out_gif> [--anim X] [--bb x0,y0,x1,y1]
                        [--height 820] [--fps 20]
  python drive_render.py <spine_dir> <stem> --list          # 只列动画名与时长
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_spine_seq as R


def list_anims(sdir: Path, stem: str, height=820, fps=20.0):
    _img, log = R._run_chrome(sdir, stem, height, fps, "", 0, 1, "meta", bb="")
    m = re.search(r"animations=([^\n|]*(?:\|[^\n]*)?)", log)
    print(log)
    if m:
        print("\n[anims]")
        for x in m.group(1).split("|"):
            print("   ", x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sdir")
    ap.add_argument("stem")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--anim", default="")
    ap.add_argument("--bb", default="")
    ap.add_argument("--height", type=int, default=820)
    ap.add_argument("--fps", type=float, default=20.0)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    sdir = Path(a.sdir)
    if a.list:
        list_anims(sdir, a.stem, a.height, a.fps)
        return
    if not a.out:
        raise SystemExit("需要 out_gif 或 --list")

    info, logtxt = R.render(sdir, a.stem, Path(a.out), a.height, a.fps,
                            a.anim, 6, a.bb)
    print("[render]", logtxt)
    if info:
        sz = Path(a.out).stat().st_size / 1048576
        print(f"[gif] {a.out}  {info['frames']} 帧 "
              f"{info['cell'][0]}x{info['cell'][1]} 每帧 {info['delay']}ms {sz:.2f}MB")
        print(f"[anim] {info['anim']} {info['dur']}s bb={info['bb']}")


if __name__ == "__main__":
    main()
