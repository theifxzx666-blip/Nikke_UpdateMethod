# -*- coding: utf-8 -*-
"""补拉大地图专用莱彻（xea002 / xea004 / xmg002 / xmg003）。

这些型号只在大地图巡逻，不进关卡 FieldMonsterId，所以上一版清单里没有、
也没有立绘。pull_bundle.py 落地名固定会互相覆盖，这里每拉一个立刻改名。
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pull_bundle as P

DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")
KEYS = {
    "xea002": "spotmonster(hd)_assets_spotmonster/xea002_8865b6f6dc5fd5a39279782b1288c836.bundle",
    "xea004": "spotmonster(hd)_assets_spotmonster/xea004_d3f14e6245f46d42293655b031856a4a.bundle",
    "xmg002": "spotmonster(hd)_assets_spotmonster/xmg002_e4b6cb409a7a0dc4ffeed5439749f7f5.bundle",
    "xmg003": "spotmonster(hd)_assets_spotmonster/xmg003_2a2f194d092072701372ee1a72e9ffb2.bundle",
}

for tag, key in KEYS.items():
    dst = DEV / f"spotmonster_{tag}_map.bundle"
    if dst.exists():
        print(f"跳过 {tag}（已存在）")
        continue
    print(f"\n===== {tag}")
    try:
        bp = P.pull("core", key, 0)
        src = DEV / (bp.stem + ".bundle")
        if not src.exists():
            src = bp
        shutil.move(str(src), str(dst))
        print(f"    → {dst.name}  {dst.stat().st_size/1048576:.1f} MB")
    except Exception as e:
        print(f"    !! {e}")

print("\n落地：")
for f in sorted(DEV.glob("spotmonster_*.bundle")):
    print(f"   {f.name:44s} {f.stat().st_size/1048576:6.1f} MB")
