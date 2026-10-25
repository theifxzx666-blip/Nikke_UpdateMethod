# -*- coding: utf-8 -*-
"""在已解密文本表中系统检索锚点词，输出命中明细。"""
import sqlite3
import sys
from pathlib import Path

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device\locale")

TERMS = {
    "Locale_Skill.lsc": [
        "Beyond the Fade", "Goddeath", "Divine Light", "Celestial Haven",
        "Garden of Arcadia", "Sharpened Resolve", "Synthetic World", "Distant New World",
        "Sanctuary", "Queen",
    ],
    "Locale_Character.lsc": [
        "Goddeath", "Sanctuary", "Marian", "Scarlet", "Rapunzel", "Nostalgia",
    ],
    "Locale_CharacterCostume.lsc": [
        "Goddeath", "Sanctuary", "Queen", "Last-Affection", "Lacrimosa",
        "Dear Grace", "Trivisa", "Nostalgia",
    ],
    "Locale_Profile.lsc": [
        "GODDESS OF VICTORY", "Nostalgia", "usertitle_", "usericon_name_56",
    ],
    "Locale_Stage.lsc": ["49-", "50-", "Chapter 49", "Chapter 50"],
}

LANGS = ("en", "zh-CN", "zh-TW", "ja", "ko")


def con_of(name):
    dec = D / (Path(name).stem + ".dec")
    return sqlite3.connect(f"file:{dec}?mode=ro", uri=True)


for name, terms in TERMS.items():
    con = con_of(name)
    table = Path(name).stem
    print("=" * 78)
    print(name)
    for term in terms:
        hits = []
        for lang in LANGS:
            try:
                rows = list(con.execute(
                    f'select "Key","{lang}" from "{table}" where "{lang}" like ? limit 6',
                    (f"%{term}%",)))
            except sqlite3.OperationalError:
                continue
            for k, v in rows:
                hits.append((lang, k, v))
        if not hits:
            print(f"  ✗ {term!r} 无命中")
            continue
        print(f"  ✔ {term!r} 命中 {len(hits)} 条")
        seen = set()
        for lang, k, v in hits:
            if k in seen:
                continue
            seen.add(k)
            print(f"      [{lang}] {k} = {v}")
            if len(seen) >= 4:
                break
    con.close()
