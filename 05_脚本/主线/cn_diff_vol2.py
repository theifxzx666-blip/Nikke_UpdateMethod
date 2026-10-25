#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""国服分卷 diff（v2）：以 m_InternalIds 为准，不只看 entries。

为什么要改：
  m_InternalIds 是「本卷需要下载的全部 bundle」；
  m_EntryDataString 只是「可被 Addressables 按地址寻址的资源」。
  实测 826995931.json（角色卷）：internalIds 里 838 条 `spine/standing/cNNN/NN_hd`
  （大厅动画），但 entries 只覆盖 3242 个 bundle，**一条 standing 都没有** ——
  大厅动画是代码按路径直载，不注册 entry。只看 entries 会整批漏掉（E-40）。

输出：分卷diff_v2.tsv（状态 / 卷 / bundle基名 / 新hash / 旧hash）
"""
import os
import re
import sys
from pathlib import Path

import cn_catalog as C

CN_ROOT = Path(os.environ.get("CN_ROOT", r"D:\Codex\临时\nikke_cn_20260930"))
W = CN_ROOT / "cat_all"
HASH_TAIL = re.compile(r"^(.*)_([0-9a-f]{32})\.bundle$")

# ⚠ VOLS 是**本期配对结果**，下期必须重配（不能按 span 名配，同 span 有多份）。
# 重配方法：先跑 cn_index.py 出 03_catalog分卷索引.tsv，按内容特征挑：
#   主卷        audiogroupui 命中 > 1000
#   角色卷      icons-char-full + icons-char-mi + spinestanding 三者都 > 0
#   小人卷      sdcharacters > 0（有 spotskillcutscene 的那份是「未和谐」）
#   地图卷      campaignmapmodel > 0
#   字段卷      其余 NK.Field
# 每卷取「上期」与「本期」各一份，且两份的 internal_ids 数量差要与实际更新量相称。
VOLS = [
    ("主卷",         "1716443029.json",  "-1213342216.json"),
    ("角色卷-和谐",   "-9140668.json",    "826995931.json"),
    ("角色卷-未和谐", "-272983779.json",  "666337561.json"),
    ("小人卷-和谐",   "905886413.json",   "1841243444.json"),
    ("小人卷-未和谐", "-370290636.json",  "-53511240.json"),
    ("地图卷",       "1408848161.json",  "-1635625071.json"),
    ("字段卷",       "-1386349302.json", "583498100.json"),
]


def ids_of(path: Path):
    """bundle 基名 → hash（来自 m_InternalIds，全量）。"""
    r = C.parse(path)
    out = {}
    for x in r["internal_ids"]:
        name = C.bundle_name(x)
        m = HASH_TAIL.match(name)
        if m:
            out[m.group(1)] = m.group(2)
    return r, out


def main():
    out_dir = CN_ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, tot = [], [0, 0, 0]

    for vol, bf, tf in VOLS:
        rb, b = ids_of(W / bf)
        rt, t = ids_of(W / tf)
        add, rem = t.keys() - b.keys(), b.keys() - t.keys()
        chg = {k for k in b.keys() & t.keys() if b[k] != t[k]}
        tot[0] += len(add); tot[1] += len(chg); tot[2] += len(rem)
        print(f"{vol:<14} bundle {len(b):>6}→{len(t):<6} "
              f"新增 {len(add):>5}｜变更 {len(chg):>5}｜消失 {len(rem):>3}")
        for k in add:
            rows.append((vol, "新增", k, t[k], ""))
        for k in rem:
            rows.append((vol, "消失", k, "", b[k]))
        for k in chg:
            rows.append((vol, "变更", k, t[k], b[k]))

    print(f"\n合计 新增 {tot[0]}｜变更 {tot[1]}｜消失 {tot[2]}")
    order = {"新增": 0, "变更": 1, "消失": 2}
    rows.sort(key=lambda r: (order[r[1]], r[0], r[2]))
    p = out_dir / "分卷diff_v2.tsv"
    with p.open("w", encoding="utf-8", newline="") as f:
        f.write("卷\t状态\tbundle基名\t新hash\t旧hash\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    print("->", p)


if __name__ == "__main__":
    main()
