# -*- coding: utf-8 -*-
"""raw 区间 → 逐 chunk zstd 解压 → 按 file_offset 拼回 .bundle → UnityPy 导出 PNG。"""
import json
import sys
from pathlib import Path

import zstandard
import UnityPy

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
LO = 5197946003
TRIM_HEAD = 3219
raw = (D / "frame_raw.bin").read_bytes()
segs = json.loads((D / "frame_segs.json").read_text())
dctx = zstandard.ZstdDecompressor()

out = bytearray()
for s in segs:
    start = s["store_offset"] - LO + TRIM_HEAD
    comp = raw[start:start + s["comp"]]
    dec = dctx.decompress(comp, max_output_size=max(s["orig"], 1) * 2)
    assert len(dec) == s["orig"], f"长度不符 {len(dec)} != {s['orig']}"
    assert s["file_offset"] == len(out), f"拼接位置不符 {s['file_offset']} != {len(out)}"
    out += dec

print(f"拼装完成 {len(out):,}B  head={bytes(out[:8])}")
bundle = D / "icons-user_frame_hd.bundle"
bundle.write_bytes(out)

env = UnityPy.load(str(bundle))
counts = {}
objs = []
for obj in env.objects:
    counts[obj.type.name] = counts.get(obj.type.name, 0) + 1
    objs.append(obj)
print("对象类型统计:", counts)
print("对象总数:", len(objs))

names = []
outdir = D / "png"
outdir.mkdir(exist_ok=True)
n_png = 0
for obj in env.objects:
    if obj.type.name in ("Sprite", "Texture2D"):
        try:
            data = obj.read()
            name = getattr(data, "m_Name", None) or getattr(data, "name", "unnamed")
            names.append((obj.type.name, name))
            if obj.type.name == "Texture2D" and n_png < 5:
                img = data.image
                p = outdir / f"{name}.png"
                img.save(p)
                n_png += 1
                print(f"  导出 {p.name}  {img.size}")
        except Exception as e:
            print(f"  导出失败 {obj.type.name}: {str(e)[:80]}")

print(f"\nSprite/Texture2D 名称共 {len(names)} 条，前 12:")
for t, n in names[:12]:
    print(f"  [{t}] {n}")
