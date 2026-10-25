# -*- coding: utf-8 -*-
"""把 MonsterPartsTable 里两只关底 BOSS 的全部部件行导成一张可查的表。

为什么要这张表：`_判定.tsv` 只列**渲染网格**（能画出来的），而表里有 12 行
`parts_col_8xx / 9xx` 的 PartsSkin 是空的 —— 它们是纯碰撞体，画不出来，
但照样可受击、有血条。看图会漏掉它们，查表才不会。
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_boss_parts_xray as B          # noqa: E402

OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\boss_parts_xray\00_判定总表.tsv")

TARGETS = [
    (451003, "47章 安尼希利奥"),
    (251016, "48章 莉贝雷利奥躯体"),
]


def main():
    rows, loc = B.load_parts()
    lines = [
        "# 关底 BOSS 部件判定总表（源：MonsterPartsTable，715 行）",
        "# HpRatio / DamageHpRatio 是表里的原值，未做换算；主部件基准 10000。",
        "# 可见网格 = PartsSkin 有值且能在模型包里找到；空 = 纯碰撞体，画不出来。",
        "BOSS\tId\t中文名\tPartsType\tIsMainPart\t可受击\t有血条\tHpRatio\tDamageHpRatio\t"
        "DefenceRatio\t可见网格\tPartsObject\tLinkedPartsId\tDestroyAfterAnim",
    ]
    for mid, zh in TARGETS:
        rs = [r for r in rows if r.get("MonsterModelId") == mid]
        lines.append(f"### {zh} · MonsterModelId {mid} · {len(rs)} 行")
        for r in rs:
            key = str(r.get("PartsNameLocalkey") or "")
            nm = loc.get(key.split(":", 1)[1], "") if ":" in key else ""
            lines.append("\t".join(str(x) for x in [
                zh.split(" ")[1], r.get("Id"), nm or "（无名）", r.get("PartsType"),
                "是" if r.get("IsMainPart") else "否",
                "是" if r.get("IsPartsDamageAble") else "否",
                "是" if r.get("VisibleHp") else "否",
                r.get("HpRatio"), r.get("DamageHpRatio"), r.get("DefenceRatio"),
                r.get("PartsSkin") or "（无·纯碰撞体）",
                ", ".join(r.get("PartsObject") or []),
                r.get("LinkedPartsId") or "",
                r.get("DestroyAfterAnim") or "",
            ]))
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8-sig")
    print(f"→ {OUT}  {len(lines)} 行")


if __name__ == "__main__":
    main()
