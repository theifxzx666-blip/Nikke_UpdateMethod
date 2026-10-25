# -*- coding: utf-8 -*-
"""文本链验证：解密 lsc → 查表结构 → 用用户给的锚点反查。

锚点：
  9 个新角色技能英文名
  称号候选 NOSTALGIA / GODDESS OF VICTORY
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Codex\临时\nikke_ce008")
from dec import decrypt_nkdb  # noqa: E402

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device\locale")

SKILLS = [
    "Beyond the Fade: Bloom", "Beyond the Fade: Sword Dance", "Beyond the Fade: Goddeath",
    "Divine Light", "Celestial Haven", "Garden of Arcadia",
    "Sharpened Resolve", "Synthetic World", "Distant New World",
]
TITLES = ["NOSTALGIA", "GODDESS OF VICTORY"]
CHARS = ["Scarlet: Goddeath", "Rapunzel: Sanctuary", "Marian: Queen"]


def load(name):
    src = D / name
    dec = D / (src.stem + ".dec")
    if not dec.exists():
        data = src.read_bytes()
        if data[:4] == b"NKDB":
            raw = decrypt_nkdb(data)
        else:
            raw = data
        dec.write_bytes(raw)
    return sqlite3.connect(f"file:{dec}?mode=ro", uri=True)


for name in ["Locale_Skill.lsc", "Locale_Profile.lsc", "Locale_Character.lsc",
             "Locale_CharacterCostume.lsc", "Locale_Stage.lsc", "Locale_Event.lsc"]:
    con = load(name)
    tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    print("=" * 78)
    print(f"{name} 表={tabs}")
    for t in tabs:
        cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
        cnt = con.execute(f'select count(*) from "{t}"').fetchone()[0]
        print(f"  [{t}] rows={cnt:,} cols={cols}")
        for row in con.execute(f'select * from "{t}" limit 2'):
            print("    ", [str(v)[:90] for v in row])
    con.close()

# ---- 技能锚点 ----
print("\n" + "=" * 78)
print("技能名反查（Locale_Skill）")
con = load("Locale_Skill.lsc")
tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
for t in tabs:
    cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
    text_cols = [c for c in cols if c.lower() not in ("id", "key")]
    for s in SKILLS:
        for c in text_cols:
            q = f'select * from "{t}" where "{c}" like ? limit 3'
            rows = list(con.execute(q, (f"%{s}%",)))
            if rows:
                print(f"  ✔ 「{s}」命中 [{t}].[{c}] × {len(rows)}")
                for r in rows[:2]:
                    print("      ", [str(v)[:70] for v in r])
                break
        else:
            continue
        break
    else:
        continue
    break
con.close()

# ---- 称号锚点 ----
print("\n" + "=" * 78)
print("称号锚点（Locale_Profile）")
con = load("Locale_Profile.lsc")
tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
for t in tabs:
    cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
    for tt in TITLES:
        for c in cols:
            if c.lower() in ("id",):
                continue
            try:
                rows = list(con.execute(f'select * from "{t}" where "{c}" like ? limit 5',
                                        (f"%{tt}%",)))
            except Exception:
                continue
            if rows:
                print(f"  ✔ 「{tt}」命中 [{t}].[{c}] × {len(rows)}")
                for r in rows[:3]:
                    print("      ", [str(v)[:80] for v in r])
con.close()
