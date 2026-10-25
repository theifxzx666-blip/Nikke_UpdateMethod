# -*- coding: utf-8 -*-
"""GIF / WebP 全帧体检：出「全帧缩略网格」+ 逐帧覆盖率，找出黑帧与静止。

为什么必须出网格
----------------
只抽首帧或四帧拼图，会刚好避开坏帧（E-19：首帧 PNG 取「前景最多」那帧，
天然躲开黑帧）。唯一可靠的验收是**逐帧**看一眼。

用法
----
python check_gif.py <gif 或目录> [--cols 8] [--cell 200] [--out 目录]
python check_gif.py a.gif b.gif

产物
----
<gif 同名>_全帧网格.png    每格标「帧号 + 覆盖率%」，空帧格子描红框
终端报告：尺寸 / 帧数 / 时长 / 空帧索引 / 首帧覆盖率 / 动幅%

退出码：0 通过；1 有空帧或几乎不动；2 读不了文件
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

EMPTY_PCT = 0.5      # 覆盖率低于这个值算空帧（与出图脚本同一阈值）
STILL_PCT = 0.2      # 动幅低于这个值算「几乎不动」
COVER_TH = 60        # 像素 RGB 和 > 60 才算前景


def frames_of(p: Path):
    im = Image.open(p)
    durs = []
    fr = []
    for f in ImageSequence.Iterator(im):
        fr.append(f.convert("RGB"))
        durs.append(f.info.get("duration", 0))
    return fr, durs


def coverage(f: Image.Image) -> float:
    a = np.asarray(f, dtype="int16")
    return float((np.abs(a).sum(axis=2) > COVER_TH).mean() * 100)


def motion_pct(fr) -> float:
    """最多取 7 帧两两比对，取全局最大平均像素差。

    不能用「首帧 vs 半周期帧」—— 循环动画在半周期常回到近似姿态，会算出接近 0。
    """
    n = len(fr)
    if n < 2:
        return 0.0
    idx = sorted({round(i * (n - 1) / min(6, n - 1)) for i in range(min(7, n))})
    arr = [np.asarray(fr[i], dtype="float32") for i in idx]
    mx = 0.0
    for i in range(len(arr)):
        for j in range(i + 1, len(arr)):
            mx = max(mx, float(np.abs(arr[i] - arr[j]).mean() / 255 * 100))
    return mx


def grid(fr, cov, cols: int, cell: int) -> Image.Image:
    n = len(fr)
    cols = max(1, min(cols, n))
    rows = (n + cols - 1) // cols
    pad, lab = 4, 16
    w, h = fr[0].size
    sc = min(cell / w, cell / h)
    tw, th = max(1, int(w * sc)), max(1, int(h * sc))
    cw, ch = tw + pad * 2, th + pad * 2 + lab
    out = Image.new("RGB", (cols * cw, rows * ch), (24, 27, 32))
    d = ImageDraw.Draw(out)
    for i, f in enumerate(fr):
        cx, cy = (i % cols) * cw, (i // cols) * ch
        out.paste(f.resize((tw, th), Image.LANCZOS), (cx + pad, cy + pad))
        bad = cov[i] < EMPTY_PCT
        d.rectangle([cx, cy, cx + cw - 1, cy + ch - 1],
                    outline=(220, 60, 60) if bad else (60, 64, 72))
        d.text((cx + pad, cy + pad + th + 2),
               f"{i}  {cov[i]:.1f}%", fill=(240, 120, 120) if bad else (170, 180, 195))
    return out


def check(p: Path, cols: int, cell: int, out_dir: Path | None) -> int:
    try:
        fr, durs = frames_of(p)
    except Exception as e:                              # noqa: BLE001
        print(f"[FAIL] {p.name}: 读不了（{e}）")
        return 2
    if not fr:
        print(f"[FAIL] {p.name}: 0 帧")
        return 2

    cov = [coverage(f) for f in fr]
    empty = [i for i, c in enumerate(cov) if c < EMPTY_PCT]
    mot = motion_pct(fr)
    tot = sum(durs) / 1000
    best = max(range(len(cov)), key=lambda i: cov[i])

    tag = "OK "
    if empty or mot < STILL_PCT:
        tag = "BAD"
    print(f"[{tag}] {p.name}")
    print(f"       {fr[0].size[0]}×{fr[0].size[1]} · {len(fr)} 帧 · {tot:.2f}s · "
          f"间隔 {durs[0] if durs else 0}ms · 动幅 {mot:.2f}%")
    print(f"       首帧覆盖率 {cov[0]:.1f}% · 最满第 {best} 帧 {cov[best]:.1f}% · "
          f"最低 {min(cov):.1f}%")
    if empty:
        print(f"       !! 空帧 {len(empty)} 个：{empty[:20]}{' …' if len(empty) > 20 else ''}")
    if mot < STILL_PCT:
        print(f"       !! 动幅 {mot:.2f}% < {STILL_PCT}%，几乎是静止图")

    g = grid(fr, cov, cols, cell)
    dst = (out_dir or p.parent) / f"{p.stem}_全帧网格.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    g.save(dst)
    print(f"       -> {dst}")
    return 0 if tag == "OK " else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="GIF 全帧体检")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--cell", type=int, default=200, help="单格最长边像素")
    ap.add_argument("--out", default="", help="网格输出目录（默认与 GIF 同目录）")
    a = ap.parse_args()

    targets: list[Path] = []
    for s in a.paths:
        p = Path(s)
        if p.is_dir():
            targets += sorted([x for x in p.rglob("*")
                               if x.suffix.lower() in (".gif", ".webp")])
        elif p.exists():
            targets.append(p)
        else:
            print(f"[SKIP] 不存在：{p}")
    if not targets:
        sys.exit("没有可检查的文件")

    out_dir = Path(a.out) if a.out else None
    codes = [check(p, a.cols, a.cell, out_dir) for p in targets]
    bad = sum(1 for c in codes if c != 0)
    print(f"\n{len(targets) - bad} / {len(targets)} 通过")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
