#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""逐个识别 UnityCache 的 __data 样本。

UnityPy 在个别 bundle 上会 C 层 segfault（try/except 抓不住），
所以每个文件单独起一个子进程，崩了只丢那一个。
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

PY = r"D:\Codex\依赖\venv-nikke\Scripts\python.exe"

CHILD = r'''
import json, sys
from collections import Counter
import UnityPy
f = sys.argv[1]
env = UnityPy.load(f)
types = Counter(o.type.name for o in env.objects)
names = []
for o in env.objects:
    if o.type.name in ("Texture2D", "Sprite", "TextAsset"):
        try:
            d = o.read()
            nm = getattr(d, "m_Name", "") or getattr(d, "name", "")
            if nm:
                if o.type.name == "Texture2D":
                    nm = f"{nm} [{getattr(d,'m_Width',0)}x{getattr(d,'m_Height',0)}]"
                names.append(f"{o.type.name}:{nm}")
        except Exception:
            pass
print(json.dumps({
    "ok": True,
    "types": dict(types.most_common(6)),
    "container": list(env.container.keys())[:4],
    "names": names[:10],
}))
'''


def probe(path: Path):
    r = subprocess.run([PY, "-c", CHILD, str(path)], capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return {"ok": False, "rc": r.returncode, "err": (r.stderr or "").strip()[-120:]}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"ok": False, "rc": -1, "err": "非 JSON 输出"}


def main():
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("uc_probe")
    for f in sorted(d.glob("*.bundle")):
        info = probe(f)
        size = f.stat().st_size / 2 ** 20
        if not info.get("ok"):
            print(f"\n{f.name} {size:.2f} MiB  ✗ rc={info['rc']} {info['err'][:80]}")
            continue
        print(f"\n{f.name} {size:.2f} MiB")
        print("   类型:", info["types"])
        print("   容器:", info["container"])
        print("   资源:", info["names"][:6])


if __name__ == "__main__":
    main()
