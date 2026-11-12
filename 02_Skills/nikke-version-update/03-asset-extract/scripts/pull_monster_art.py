# -*- coding: utf-8 -*-
"""为 47/48 章的 8 个 FieldMonsterId 拉取 spotmonster(hd) 立绘包，并打印对象清单。

链路：CampaignStageTable.FieldMonsterId → MonsterFieldTable.MonPrefab → spotmonster(hd) 键
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Codex\临时\nikke_intl_20261029")
import pull_bundle as PB  # noqa: E402

D = PB.D
WANT = ["eea002", "mmg005", "mea001", "meg006", "xma003", "xmg001", "xea003", "xeg006"]
GROUP = "spotmonster(hd)"


def keys_for(prefix):
    con = sqlite3.connect(f"file:{D / 'core_catalog.dec'}?mode=ro", uri=True)
    rows = [r[0] for r in con.execute(
        "select key from files_chunktype where key like ?", (GROUP + "%",))]
    con.close()
    hit = [k for k in rows if ("/"+prefix) in k and "_" + prefix in k]
    # 精确：文件名以 <prefix>_ 开头
    hit = [k for k in rows if Path(k).name.startswith(prefix + "_")]
    # 排除测试变体
    hit = [k for k in hit if "test" not in Path(k).name]
    return hit


def main():
    report = {}
    for p in WANT:
        ks = keys_for(p)
        if not ks:
            print("!! 没有键:", p)
            continue
        k = ks[0]
        bp = D / pathlib_name(k)
        print("\n==== %s  <- %s" % (p, Path(k).name))
        try:
            got = PB.pull("core", k)
            import shutil
            shutil.move(str(got), str(bp))
            items = PB.dump(bp, 0)
            report[p] = dict(key=k, bundle=bp.name, items=items)
        except Exception as e:
            print("!! 失败", type(e).__name__, e)
            report[p] = dict(key=k, error=str(e)[:200])
    (D / "monster_art_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n->", D / "monster_art_report.json")


def pathlib_name(k):
    return "spotmonster_" + Path(k).name


if __name__ == "__main__":
    main()
