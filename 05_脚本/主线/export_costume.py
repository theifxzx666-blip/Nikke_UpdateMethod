# -*- coding: utf-8 -*-
"""导出皮肤键全量基线（含 cID/序号/名称），供 10-29 diff。"""
import collections
import csv
import re
import sqlite3
from pathlib import Path

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device\locale")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out")
OUT.mkdir(exist_ok=True)

ch = sqlite3.connect(f"file:{D / 'Locale_Character.dec'}?mode=ro", uri=True)
cname = {}
for (k, e, z) in ch.execute('select Key,en,"zh-CN" from Locale_Character'):
    m = re.fullmatch(r"(\d+)_name", k)
    if m:
        cname[int(m.group(1))] = (e, z)
ch.close()

cs = sqlite3.connect(f"file:{D / 'Locale_CharacterCostume.dec'}?mode=ro", uri=True)
names, descs, others = {}, {}, []
for (k, e, z) in cs.execute('select Key,en,"zh-CN" from Locale_CharacterCostume'):
    m = re.fullmatch(r"(\d+)_(\d+)_costume_name", k)
    if m:
        names[(int(m.group(1)), int(m.group(2)))] = (k, e, z)
        continue
    m = re.fullmatch(r"(\d+)_(\d+)_description", k)
    if m:
        descs[(int(m.group(1)), int(m.group(2)))] = (k, e, z)
        continue
    others.append((k, e, z))
cs.close()

print(f"costume_name {len(names)} 条 / description {len(descs)} 条 / 其他 {len(others)} 条")

rows = []
for (cid, seq), (k, e, z) in sorted(names.items()):
    d = descs.get((cid, seq))
    rows.append([cid, cname.get(cid, ("?", "?"))[0], cname.get(cid, ("?", "?"))[1],
                 seq, k, e, z,
                 d[0] if d else "", (d[1] or "").replace("\n", " ") if d else ""])
with open(OUT / "costume_baseline.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["cID", "角色EN", "角色CN", "皮肤序号", "name键", "皮肤名EN", "皮肤名CN", "desc键", "描述"])
    w.writerows(rows)
print(f"→ out/costume_baseline.csv ({len(rows)} 行)")

# 只有 description 没有 name 的
only_d = sorted(set(descs) - set(names))
print(f"\n仅有 description 无 name 的皮肤 {len(only_d)} 个:")
for cid, seq in only_d:
    print(f"   cID={cid} seq={seq} {cname.get(cid, ('?',''))[0]} → {descs[(cid,seq)][1][:40]!r}")

# 每个 cID 的皮肤数
per = collections.Counter(c for c, s in names)
print(f"\n有皮肤的角色 {len(per)} 个，皮肤总数 {sum(per.values())}")
print("皮肤最多的 8 个角色:")
for cid, n in per.most_common(8):
    print(f"   {cid:4d} {cname.get(cid,('?',''))[0]:26s} {n} 套")

print("\n其他键（非 cID 数字型）:")
for k, e, z in others:
    print(f"   {k:36s} | {str(e)[:40]}")
