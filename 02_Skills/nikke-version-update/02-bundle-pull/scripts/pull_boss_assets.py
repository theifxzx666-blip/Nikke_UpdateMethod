# -*- coding: utf-8 -*-
"""批量拉 BOSS 模型 + 两阶段 idle 动画，并按语义命名落地。

为什么单独写：pull_bundle.py 落地文件名固定为「<桶>.bundle」，连续拉多个会互相覆盖
（本轮实测第二次拉完第一个就丢了）。这里每拉完立刻重命名。
"""
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pull_bundle as P

DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")

JOBS = [
    # (bucket, 完整键, 落地文件名)
    ("core", "spotmonsteranimation_assets_spotmonsteranimation/xba003_1phase_idle-raw_c2ab81705812cf6ad6a6cd9c9b3a4bed.bundle",
     "anim_xba003_1phase_idle.bundle"),
    ("core", "spotmonsteranimation_assets_spotmonsteranimation/xba003_2phase_idle-raw_f8bf16c7002ab9a36ef3ade8bf92b8da.bundle",
     "anim_xba003_2phase_idle.bundle"),
    ("core", "spotmonsteranimation_assets_spotmonsteranimation/eba002_1phase_idle-raw_2e55ffb0a51f36649f9ab32a95eea962.bundle",
     "anim_eba002_1phase_idle.bundle"),
    ("core", "spotmonsteranimation_assets_spotmonsteranimation/eba002_2phase_idle-raw_4269f5d9ce523b4d41e6214d4d37fa5b.bundle",
     "anim_eba002_2phase_idle.bundle"),
]


def main():
    # 先把上一轮遗留的未命名包收编
    legacy = DEV / "spotmonsteranimation.bundle"
    if legacy.exists():
        shutil.move(str(legacy), str(DEV / "anim_xba003_2phase_idle.bundle"))
        print("收编遗留包 → anim_xba003_2phase_idle.bundle")

    for bucket, key, name in JOBS:
        dst = DEV / name
        if dst.exists():
            print(f"跳过（已存在）{name}")
            continue
        print(f"\n===== {name}")
        try:
            bp = P.pull(bucket, key, 0)
            src = DEV / (bp.stem + ".bundle")
            if not src.exists():
                src = bp
            shutil.move(str(src), str(dst))
            print(f"    → {name}  {dst.stat().st_size/1024:.0f} KB")
        except Exception as e:
            print(f"    !! 失败 {e}")
    print("\n落地清单：")
    for f in sorted(DEV.glob("anim_*.bundle")):
        print(f"   {f.name:34s} {f.stat().st_size/1024:8.0f} KB")


if __name__ == "__main__":
    main()
