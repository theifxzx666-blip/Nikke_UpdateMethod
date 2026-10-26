# -*- coding: utf-8 -*-
"""在全部 Locale 表里搜关键词，输出命中表 / 键 / 文本。"""
import sqlite3
import sys
from pathlib import Path

DIRS = [Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc"),
        Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\文本\原始文本库_lss"),
        Path(r"D:\Codex\临时\nikke_ce008")]

terms = sys.argv[1:] or ["安尼希"]

for d in DIRS:
    if not d.exists():
        continue
    for f in sorted(list(d.glob("*.dec")) + list(d.glob("*.lss"))):
        try:
            con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
            tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
            for t in tabs:
                cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
                tcol = "zh-CN" if "zh-CN" in cols else None
                if not tcol:
                    continue
                for term in terms:
                    q = (f'select "Key","{tcol}" from "{t}" '
                         f'where "{tcol}" like ? limit 12')
                    rows = con.execute(q, (f"%{term}%",)).fetchall()
                    if rows:
                        print(f"### {f.name} / {t} / 关键词={term}  ({len(rows)}+ 命中)")
                        for k, v in rows:
                            print("   ", k, "=", v)
            con.close()
        except Exception as e:
            print(f"!! {f.name} {e}")
