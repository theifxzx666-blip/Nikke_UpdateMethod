# -*- coding: utf-8 -*-
"""
lsc_sprite.py —— 从 NIKKE 文本库（.lsc 解密后的 SQLite）直接导出 sprite 图。

结论（2026-10-25 实测）：lss/lsc 内 sprite.texture **不是加密**，而是 Unity 的
ASTC 纹理块原始数据（扁平 block 布局，每块 16 字节）。长度满足
    len == ceil(w/bw) * ceil(bh/h 同) * 16
即可反推块尺寸。解出后必须做**垂直翻转**（Unity 纹理原点在左下）。

用法：
    python lsc_sprite.py <某表.dec> [输出目录] [--all]
    --all  不筛选，导出该表全部 sprite（默认也只导全部，参数留作扩展）

依赖：texture2ddecoder（UnityPy 自带）、Pillow
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import texture2ddecoder as t2d
from PIL import Image

# ASTC 合法块尺寸（按命中概率排序，5x5 是 NIKKE 实测默认）
BLOCKS = [
    (5, 5), (4, 4), (6, 6), (8, 8), (6, 5), (5, 4), (8, 5), (8, 6),
    (10, 5), (10, 6), (10, 8), (10, 10), (12, 10), (12, 12),
]


def guess_block(nbytes: int, w: int, h: int):
    """用字节数反推 ASTC 块尺寸；无匹配返回 None。"""
    for bw, bh in BLOCKS:
        if math.ceil(w / bw) * math.ceil(h / bh) * 16 == nbytes:
            return bw, bh
    return None


def decode_sprite(texture: bytes, w: int, h: int):
    """返回 (PIL.Image RGBA, (bw,bh))；失败返回 (None, None)。"""
    d = bytes(texture)
    bs = guess_block(len(d), w, h)
    if not bs:
        return None, None
    bgra = t2d.decode_astc(d, w, h, bs[0], bs[1])
    im = Image.frombytes("RGBA", (w, h), bgra, "raw", "BGRA")
    # Unity 纹理原点在左下 → 垂直翻转回正
    return im.transpose(Image.FLIP_TOP_BOTTOM), bs


def export(sqlite_path, out_dir, verbose=True):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    has = con.execute(
        "select count(*) from sqlite_master where type='table' and name='sprite'"
    ).fetchone()[0]
    if not has:
        if verbose:
            print(f"[{Path(sqlite_path).stem}] 无 sprite 表，跳过")
        return 0, 0, {}
    rows = list(con.execute("select id,name,width,height,texture from sprite order by name"))
    con.close()

    manifest, ok, fail = [], 0, 0
    block_stat = {}
    for sid, name, w, h, tx in rows:
        if not tx or not w or not h:
            fail += 1
            continue
        im, bs = decode_sprite(tx, w, h)
        if im is None:
            fail += 1
            if verbose:
                print(f"  x {name} {w}x{h} len={len(tx)} 无匹配块尺寸")
            continue
        fn = name if name.lower().endswith(".png") else name + ".png"
        target = out / fn
        # sprite.name 可能带语言子目录前缀（如 de/EVENT_BANNER_x.png）
        target.parent.mkdir(parents=True, exist_ok=True)
        im.save(target)
        ok += 1
        key = f"{bs[0]}x{bs[1]}"
        block_stat[key] = block_stat.get(key, 0) + 1
        manifest.append({"id": sid, "name": name, "width": w, "height": h,
                         "block": key, "bytes": len(tx), "file": fn})
    (out / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    if verbose:
        print(f"[{Path(sqlite_path).stem}] 成功 {ok} / 失败 {fail}  块尺寸分布 {block_stat}")
        print(f"  -> {out}")
    return ok, fail, block_stat


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else Path(src).with_suffix("").name + "_png"
    export(src, dst)
