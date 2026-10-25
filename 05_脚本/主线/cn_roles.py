#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从分卷 diff 里提取本期新增的 cID → 资源类型 → 角色/皮肤名。

用法：python cn_roles.py
"""
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

CN_ROOT = Path(os.environ.get("CN_ROOT", r"D:\Codex\临时\nikke_cn_20260930"))
OUT = CN_ROOT / "out"
LSS = CN_ROOT / "lss"

# 键族 → (资源标签, 正则)
PATTERNS = [
    ("立绘HD", re.compile(r"^icons-char-full\(hd\)_assets_(c\d+)_(\d+)$")),
    ("立绘SD", re.compile(r"^icons-char-full\(sd\)_assets_(c\d+)_(\d+)$")),
    ("半身像", re.compile(r"^icons-char-mi\(hd\)_assets_mi_(c\d+)_(\d+)_s$")),
    ("小人", re.compile(r"^sdcharacters_assets_(c\d+)_(\d+)_var$")),
    ("爆裂", re.compile(r"^spotskillcutscene_assets_(c\d+)_(\d+)_cut_scene$")),
    ("大厅", re.compile(r"^spinestandingcharactergroup\(hd\)_assets_spine/standing/(c\d+)/\d+_hd$")),
]


def name_of(cid: str):
    num = cid[1:]
    con = sqlite3.connect(f"file:{LSS/'Locale_Character.lss'}?mode=ro", uri=True)
    r = con.execute('select "zh-CN" from Locale_Character where "Key"=?', (f"{num}_name",)).fetchone()
    con.close()
    return r[0] if r else ""


def main():
    lines = (OUT / "分卷diff_v2.tsv").read_text(encoding="utf-8").splitlines()[1:]
    hits = defaultdict(lambda: defaultdict(set))     # cid -> 标签 -> {后缀}
    for line in lines:
        p = line.split("\t")
        if len(p) < 4 or p[1] != "新增":
            continue
        stem = p[2]
        for tag, pat in PATTERNS:
            m = pat.match(stem)
            if m:
                suffix = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
                hits[m.group(1)][tag].add(suffix or "-")
                break

    rows = []
    for cid in sorted(hits, key=lambda x: int(x[1:])):
        tags = hits[cid]
        newbie = any("00" in s for s in tags.get("立绘HD", set()))
        rows.append({
            "cid": cid,
            "name": name_of(cid),
            "类型": "新角色" if newbie else "新皮肤/补件",
            "资源": "/".join(sorted(tags)),
            "后缀": ",".join(sorted({s for v in tags.values() for s in v})),
        })

    w = [max(len(str(r[k])) for r in rows + [{k: k}]) for k in ("cid", "name", "类型", "资源", "后缀")]
    print(f"{'cid':<{w[0]}}  {'角色名':<{w[1]}}  {'类型':<{w[2]}}  {'资源':<{w[3]}}  后缀")
    for r in rows:
        print(f"{r['cid']:<{w[0]}}  {r['name']:<{w[1]}}  {r['类型']:<{w[2]}}  {r['资源']:<{w[3]}}  {r['后缀']}")

    print(f"\n共 {len(rows)} 个 cID：新角色 {sum(1 for r in rows if r['类型']=='新角色')}，"
          f"新皮肤/补件 {sum(1 for r in rows if r['类型']!='新角色')}")

    with (OUT / "本期新增角色.tsv").open("w", encoding="utf-8", newline="") as f:
        f.write("cID\t角色名\t类型\t资源\t时装后缀\n")
        for r in rows:
            f.write(f"{r['cid']}\t{r['name']}\t{r['类型']}\t{r['资源']}\t{r['后缀']}\n")
    print("->", OUT / "本期新增角色.tsv")


if __name__ == "__main__":
    main()
