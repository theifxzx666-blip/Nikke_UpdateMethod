# -*- coding: utf-8 -*-
"""catalog 键族统计 + 目标资源定位（供取数用）。"""
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
BUCKETS = ["core", "dp", "saus", "ja", "fd"]


def con(b):
    return sqlite3.connect(f"file:{D / (b + '_catalog.dec')}?mode=ro", uri=True)


def fam(key):
    k = re.sub(r"_[0-9a-f]{32}.*$", "", key)
    k = re.sub(r"\d+", "#", k)
    return k


total = 0
allfam = Counter()
for b in BUCKETS:
    c = con(b)
    keys = [r[0] for r in c.execute("select key from files_chunktype")]
    raw = [r[0] for r in c.execute("select key from files_rawtype")]
    chunks = c.execute("select count(*) from chunks").fetchone()[0]
    paks = c.execute("select count(*) from paks").fetchone()[0]
    size = c.execute("select sum(compressed_size) from chunks").fetchone()[0] or 0
    ns = c.execute("select sum(original_size) from chunks").fetchone()[0] or 0
    total += len(keys)
    print(f"{b:5s} 键={len(keys):>7,} raw={len(raw):>3} chunk={chunks:>7,} pak={paks:>3} "
          f"压缩后={size/2**30:>6.2f}GB 原始={ns/2**30:>6.2f}GB")
    for k in keys:
        allfam[fam(k)] += 1
    c.close()
print(f"合计 chunktype 键 = {total:,}")

print("\n—— 重点键族命中（跨桶）——")
PATTERNS = {
    "角色立绘 full": r"^icons-char-full",
    "角色头像 mi": r"^icons-char-mi",
    "角色头像 si": r"^icons-char-si",
    "头像框 dynamic": r"^icons-dynamic",
    "头像框 user_frame": r"^icons-user_frame",
    "称号 user_title": r"^icons-user_title",
    "剧情插画": r"^scenariobackground",
    "场景背景": r"^spotbackground",
    "Spine 待机": r"^spinestandingcharactergroup",
    "Spine 战斗": r"^spinecombatcharactergroup",
    "技能图标": r"^icons-skill",
    "活动UI": r"^eventui-",
    "SD 小人": r"^sdcharacters",
    "战场地图": r"^fieldetc-map",
    "个突怪物": r"^(spotmonster|spinemonstergroup|sdmonster|spotweapon)",
}
for label, pat in PATTERNS.items():
    hits = []
    for b in BUCKETS:
        c = con(b)
        n = c.execute("select count(*) from files_chunktype where key regexp ?", (pat,)) \
            if False else None
        # sqlite 无 regexp，用 like 近似
        n = c.execute("select count(*) from files_chunktype where key like ?",
                      (pat.replace("^", "").replace("$", "") + "%",)).fetchone()[0]
        if n:
            ex = [r[0] for r in c.execute(
                "select key from files_chunktype where key like ? limit 2",
                (pat.replace("^", "").replace("$", "") + "%",))]
            hits.append((b, n, ex))
        c.close()
    if hits:
        tot = sum(h[1] for h in hits)
        print(f"  {label:<16} 共 {tot:>6,}  " + "  ".join(f"{b}={n}" for b, n, _ in hits))
        print(f"      例: {hits[0][2][0][:110]}")
