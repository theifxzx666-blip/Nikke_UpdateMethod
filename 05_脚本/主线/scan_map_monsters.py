# -*- coding: utf-8 -*-
"""从大地图模型包读出真实出现在该章地图上的莱彻型号，并接上中文名。"""
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import UnityPy

SD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")
DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")

TAG = re.compile(r"^([xemb])([a-z]{2})(\d{3})")


def jl(n):
    return json.loads((SD / (n + ".json")).read_text(encoding="utf-8"))


def monster_names():
    """MonsterModelTable.MonPrefab -> 中文名（经 MonsterTable.NameLocalkey）。"""
    f = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\文本\原始文本库_lss\Locale_Monster.lss")
    con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
    loc = dict(con.execute('select "Key","zh-CN" from Locale_Monster'))
    con.close()

    models = {m["Id"]: m for m in jl("MonsterModelTable")}
    out = {}
    for r in jl("MonsterTable"):
        mid = r.get("MonsterModelId")
        m = models.get(mid)
        if not m:
            continue
        key = (r.get("NameLocalkey") or "").split(":", 1)[-1]
        zh = loc.get(key, "")
        if not zh:
            continue
        pf = m["MonPrefab"]
        out.setdefault(pf, set()).add(zh)
    return out, models


def scan(bundle):
    env = UnityPy.load(str(bundle))
    c = Counter()
    for obj in env.objects:
        if obj.type.name not in ("GameObject", "Transform", "Mesh", "AnimationClip"):
            continue
        try:
            d = obj.read()
            n = getattr(d, "m_Name", "") or ""
        except Exception:
            continue
        m = TAG.match(n)
        if m:
            c[m.group(1) + m.group(2) + m.group(3)] += 1
    return c


names, models = monster_names()
for b in sys.argv[1:]:
    p = DEV / b
    print("=" * 90)
    print("##", b, f"{p.stat().st_size/1048576:.0f} MB")
    c = scan(p)
    print(f"   命中型号 {len(c)} 种")
    for tag, n in sorted(c.items()):
        zh = "、".join(sorted(names.get(tag, []))[:4]) or "（名称表无对应）"
        mdl = [m for m in models.values() if m["MonPrefab"] == tag]
        grade = mdl[0]["Grade"] if mdl else "?"
        size = mdl[0]["Size"] if mdl else "?"
        print(f"   {tag:10s} 出现{n:4d}次  中文名={zh}  Grade={grade} Size={size}")
