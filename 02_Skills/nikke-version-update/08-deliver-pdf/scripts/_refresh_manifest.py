# -*- coding: utf-8 -*-
"""刷新 `_素材清单.csv`：更新已有行的体积、补登新文件、剔除已不存在的行。

与 `append_manifest.py` 的区别：那个只「补新行」、不改旧值，
本轮 GIF 被重出覆盖（体积全变）、番外篇整块撤出（整批路径已不存在），
只追加会留下一堆过期 size 和幽灵行，所以这里做一次全量对齐。

用法：
  python _refresh_manifest.py           # 只报告，不写
  python _refresh_manifest.py --write   # 实际写回
"""
import csv
import sys
from pathlib import Path

ROOT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
CSV = ROOT / "_素材清单.csv"
FIELDS = ["name", "kind", "mode", "size", "inode", "nlink", "src"]


def main():
    write = "--write" in sys.argv
    with CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    kept, gone, resized, relinked = [], [], 0, 0
    for r in rows:
        p = ROOT / r["name"]
        if not p.is_file():
            gone.append(r["name"])
            continue
        st = p.stat()
        real = st.st_size
        if str(real) != str(r["size"]):
            resized += 1
            r["size"] = real
        # 去重（2026-10-26）会把重复副本改成硬链接，inode / nlink 全变；
        # 清单要跟着走，否则「哪一份是实体」就查不出来了。
        if str(st.st_ino) != str(r["inode"]):
            r["inode"] = str(st.st_ino)
        if str(st.st_nlink) != str(r["nlink"]):
            r["nlink"] = str(st.st_nlink)
        if r["mode"] != "脚本生成":
            m = "硬链接" if st.st_nlink > 1 else "复制"
            if m != r["mode"]:
                relinked += 1
                r["mode"] = m
        kept.append(r)

    have = {r["name"] for r in kept}
    added = []
    # 默认不补新行 —— 这份 CSV 登记的是「值得说明的产物」，不是全量文件树，
    # 无脑 rglob 会把 1600 多个 png/排版素材全塞进去。要补新行得显式 --add。
    if "--add" in sys.argv:
        for p in ROOT.rglob("*"):
            if not p.is_file() or p.name == "_素材清单.csv":
                continue
            rel = p.relative_to(ROOT).as_posix()
            if rel in have:
                continue
            if "07_角色爆裂特写" not in rel:
                continue
            kept.append({"name": rel, "kind": "爆裂特写贴图", "mode": "复制",
                         "size": p.stat().st_size, "inode": "", "nlink": "", "src": ""})
            added.append(rel)

    print(f"总行 {len(rows)} → {len(kept)}")
    print(f"体积更新 {resized}")
    print(f"链接状态变更 {relinked}")
    print(f"剔除失效 {len(gone)}")
    for g in gone[:10]:
        print("  -", g)
    if len(gone) > 10:
        print(f"  … 另 {len(gone)-10} 条")
    print(f"新增 {len(added)}")
    for a in added[:10]:
        print("  +", a)
    if len(added) > 10:
        print(f"  … 另 {len(added)-10} 条")

    if write:
        with CSV.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(kept)
        print("已写入", CSV)
    else:
        print("（未写入，加 --write 生效）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
