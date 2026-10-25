# -*- coding: utf-8 -*-
"""批量：本期角色的 Spine 小人 → 全身静帧。"""
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Codex\临时\spine_js")
from render_spine import render  # noqa: E402

SPINE = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\Spine\待机")
OUT = Path(r"D:\Codex\临时\spine_js\out")

TARGETS = [
    ("QUEEN（真）_c870_00", "c870_00"),
    ("QUEEN（真）_c870_01", "c870_01"),
    ("QUEEN（真）_c870_02", "c870_02"),
    ("雪子_c871_00", "c871_00"),
    ("雪子_c871_01", "c871_01"),
    ("雪子_c871_02", "c871_02"),
    ("埃癸斯_c872_00", "c872_00"),
    ("潘托姆_c580_01", "c580_01"),
]

if __name__ == "__main__":
    for d, stem in TARGETS:
        src = SPINE / d
        if not src.is_dir():
            print(f"SKIP {d} 不存在")
            continue
        out = OUT / f"{stem}_idle.png"
        try:
            print(f"{stem}: {render(src, stem, out, 'idle', 1800)}")
        except Exception as e:
            print(f"{stem}: EXC {e}")
