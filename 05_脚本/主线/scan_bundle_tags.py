# -*- coding: utf-8 -*-
"""扫描 bundle 内的 ASCII 片段，找出被引用的怪物标签（xmg001 / eea002 等）。"""
import re
import sys
from pathlib import Path

TAG = re.compile(rb"(?:x|e|m|b)[a-z]{2}\d{3}(?:_[a-z0-9]+)*")
DIRS = [Path(r"D:\Codex\临时\nikke_intl_20261029\device")]

files = sys.argv[1:] or []
if not files:
    files = [str(p) for d in DIRS for p in sorted(d.glob("*.bundle"))]

for f in files:
    p = Path(f)
    if not p.exists():
        continue
    data = p.read_bytes()
    # 只取可打印 ASCII 串
    hits = {}
    for m in TAG.finditer(data):
        t = m.group(0).decode("ascii", "ignore")
        hits[t] = hits.get(t, 0) + 1
    if hits:
        top = sorted(hits.items(), key=lambda x: -x[1])[:14]
        print(f"{p.name}  ({p.stat().st_size//1024} KB)  ->  {', '.join(f'{k}×{v}' for k, v in top)}")
