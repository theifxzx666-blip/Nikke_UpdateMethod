# -*- coding: utf-8 -*-
"""拉关底 BOSS 的「大地图 / 单挑」版本模型。

动机：战斗包里 2phase 的 body 网格在绑定姿态下是散开的（1181 个连通块、手臂与主体分离），
而 spotmonstermap 是地图上摆好姿态的静态展示模型，很可能就是完整形态。
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pull_bundle as P

DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")

JOBS = [
    ("spotmonstermap_assets_spotmonstermap/xba003_dmtr_map_28a2cec7dec2788c0e15ced4e31ef1c6.bundle",
     "map_xba003_dmtr.bundle"),
    ("spotmonstermap_assets_spotmonstermap/eba002_hsta_map_9ec72ed3ff741420d5ec3018544d62db.bundle",
     "map_eba002_hsta.bundle"),
    ("spotmonstermap_assets_spotmonstermap/eba002_hsta_singleraid_map_24a3524cd13abc4ff6908761f6e06412.bundle",
     "map_eba002_singleraid.bundle"),
]

for key, name in JOBS:
    dst = DEV / name
    if dst.exists():
        print("跳过（已存在）", name)
        continue
    print(f"\n===== {name}")
    try:
        bp = P.pull("core", key, 0)
        src = DEV / (bp.stem + ".bundle")
        if not src.exists():
            src = bp
        shutil.move(str(src), str(dst))
        print(f"    → {name}  {dst.stat().st_size/1048576:.1f} MB")
    except Exception as e:
        print(f"    !! {e}")

print("\n落地：")
for f in sorted(DEV.glob("map_*.bundle")):
    print(f"   {f.name:34s} {f.stat().st_size/1048576:6.1f} MB")
