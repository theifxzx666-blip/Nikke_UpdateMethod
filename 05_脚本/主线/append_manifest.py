# -*- coding: utf-8 -*-
"""把新产出的文件增量追加进 `_素材清单.csv`。

为什么不重跑 `build_pack_v2.py`：那是整包重建脚本，会重新编排整个交付目录，
本轮只是新增了几个子目录，没必要冒重构风险。

只追加不删除，已登记的路径原样保留。
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
CSV = ROOT / "_素材清单.csv"

# 目录关键字 → kind 名（按最长匹配优先）
KIND = [
    ("07_角色爆裂特写", "爆裂特写贴图"),
    ("零件透视", "BOSS零件透视"),
    ("动图", "BOSS表演动画GIF"),
    ("插画_GINGERBREAD HOUSE", "番外篇插画"),
    ("3D查看器/models", "BOSS动画模型"),
]


def kind_of(rel: str) -> str:
    for k, v in KIND:
        if k in rel:
            return v
    return "其他"


def main():
    rows = []
    with CSV.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    have = {r["name"] for r in rows}

    added = 0
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.name == "_素材清单.csv":
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in have:
            continue
        if not any(k in rel for k, _ in KIND):
            continue        # 只登记本轮新增的几类，别把说明文档也刷进去
        st = p.stat()
        rows.append({
            "name": rel, "kind": kind_of(rel), "mode": "复制",
            "size": st.st_size, "inode": "", "nlink": "",
            "src": "",
        })
        added += 1

    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "kind", "mode", "size", "inode", "nlink", "src"])
        w.writeheader()
        w.writerows(rows)
    print(f"新增 {added} 条，总计 {len(rows)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
