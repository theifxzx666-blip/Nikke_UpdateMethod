# -*- coding: utf-8 -*-
"""补拉两个关底 BOSS 的「表演类」动画（appearance / intro / skill_idle）。

为什么需要：idle 是循环呼吸，碎片在 idle 里几乎不平移（实测外围碎块位移 < 1 单位），
单帧看起来就是「散架」。真正表现「崩甲 / 重组」的是 appearance 与 intro。
键名全部来自 core_catalog.dec 的 files_chunktype 实测查询，不是猜的：

    select key from files_chunktype
    where key like '%spotmonsteranimation%xba003%' or ...eba002%   → 43 条

复用 pull_bundle.pull()，注意它落盘名固定为「<桶>.bundle」，每次拉完立刻改名。
"""
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pull_bundle as P

DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")

JOBS = [
    ("xba003_12phase_appeanrance-raw_57f76a123445287bab5a116bf9b7c23f.bundle",
     "anim_xba003_12phase_appearance.bundle"),
    ("eba002_2phase_intro_01-raw_0d36a633d16bd51175b3114115618993.bundle",
     "anim_eba002_2phase_intro01.bundle"),
    ("eba002_2phase_intro_02-raw_b7e441ce491e586b81cc6a632f092dc8.bundle",
     "anim_eba002_2phase_intro02.bundle"),
    ("xba003_2phase_skill_idle-raw_a6e7738bffe58de08d16ca480d6911a1.bundle",
     "anim_xba003_2phase_skillidle.bundle"),
    ("eba002_2phase_groggy_loop-raw_7ea87657cf7817b543e0646b61ed7e12.bundle",
     "anim_eba002_2phase_groggy.bundle"),
]


def main():
    for fname, name in JOBS:
        dst = DEV / name
        if dst.exists():
            print(f"跳过（已存在）{name}")
            continue
        key = ("spotmonsteranimation_assets_spotmonsteranimation/" + fname)
        print(f"\n===== {name}")
        try:
            bp = P.pull("core", key, 0)
            src = DEV / (bp.stem + ".bundle")
            if not src.exists():
                src = bp
            shutil.move(str(src), str(dst))
            print(f"    → {name}  {dst.stat().st_size / 1024:.0f} KB")
        except Exception as e:
            print(f"    !! 失败 {type(e).__name__}: {e}")
    print("\n落地清单：")
    for f in sorted(DEV.glob("anim_*.bundle")):
        print(f"   {f.name:42s} {f.stat().st_size / 1024:8.0f} KB")


if __name__ == "__main__":
    main()
