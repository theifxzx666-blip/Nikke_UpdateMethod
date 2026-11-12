# -*- coding: utf-8 -*-
"""分析各文本表的 Key 命名族，定位「称号 / 头像框 / 章节 / 技能」的真实前缀。"""
import re
import sqlite3
from collections import Counter
from pathlib import Path

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device\locale")
TABLES = ["Locale_Profile", "Locale_Skill", "Locale_Character",
          "Locale_CharacterCostume", "Locale_Stage", "Locale_Event"]


def prefixes(keys):
    """取键的主族：去掉尾部数字段后的前缀，如 usericon_name_56101 -> usericon_name"""
    c = Counter()
    for k in keys:
        m = re.match(r"^(.*?)(?:_?\d+)+$", k)
        base = m.group(1) if m else k
        base = re.sub(r"(?:_?\d+)$", "", base).rstrip("_") or k
        c[base] += 1
    return c


for t in TABLES:
    con = sqlite3.connect(f"file:{D / (t + '.dec')}?mode=ro", uri=True)
    keys = [r[0] for r in con.execute(f'select "Key" from "{t}"')]
    print("=" * 78)
    print(f"{t}  共 {len(keys):,} 键")
    print("  —— 前 18 个命名族 ——")
    for base, n in prefixes(keys).most_common(18):
        print(f"    {base:<34} {n:>6}")
    for kw in ("title", "frame", "chapter", "Chapter", "rank", "emblem", "name"):
        hit = [k for k in keys if kw in k][:6]
        if hit:
            print(f"  —— 含 {kw!r} 的键（前 6）: {hit}")

# 22261 归属：Locale_Skill 里 222xx 家族
con = sqlite3.connect(f"file:{D / 'Locale_Skill.dec'}?mode=ro", uri=True)
rows = list(con.execute(
    'select "Key", en from Locale_Skill where "Key" like "222%" order by "Key"'))
print("=" * 78)
print(f"Locale_Skill 中 222* 键共 {len(rows)} 条（前 20）")
for k, v in rows[:20]:
    print(f"  {k} = {v}")
