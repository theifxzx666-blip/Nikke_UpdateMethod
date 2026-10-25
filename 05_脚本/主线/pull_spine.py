# -*- coding: utf-8 -*-
"""批量拉取「大厅站立」Spine bundle 并导出 .skel/.atlas/.png。

大厅动画的资源定位（实测）：
  dp 桶 · spinestandingcharactergroup(hd)_assets_spine/standing/<角色>/<序号>_hd_<hash>.bundle
    <角色>  = c<3位数字>，如 c870
    <序号>  = 00/01/02…，对应「默认 + 各套时装」
  配套的 spinestandingprefabgroup 里能看到时装名（00_normal / 02_decadent），
  这里只取 charactergroup（骨架），prefab 只是挂载用。

用法：
  python pull_spine.py c870 c871 c872
  python pull_spine.py --only 870:00 870:02
"""
import argparse
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\Codex\临时\nikke_intl_20261029")
sys.path.insert(0, str(ROOT))

import pull_bundle  # noqa: E402

import export_spine  # noqa: E402  （同目录脚本）

DEV = ROOT / "device"
SPINE = ROOT / "spine_render" / "assets"
GROUP = "spinestandingcharactergroup(hd)"


def list_standing(chars):
    """从 dp_catalog 里列出每个角色的 standing bundle 键。"""
    con = sqlite3.connect(f"file:{DEV / 'dp_catalog.dec'}?mode=ro", uri=True)
    keys = [k for (k,) in con.execute(
        "select key from files_chunktype where key like ?", (GROUP + "%",))]
    con.close()
    out = defaultdict(dict)
    for k in keys:
        parts = k.split("/")
        if len(parts) < 4:
            continue
        cid, fn = parts[2], parts[3]
        if chars and cid not in chars:
            continue
        idx = fn.split("_")[0]
        out[cid][idx] = k
    return {c: dict(sorted(v.items())) for c, v in sorted(out.items())}


def costume_names():
    """prefab 组里的时装名：<序号>_<类型>_<hash>.bundle → 序号: 类型"""
    con = sqlite3.connect(f"file:{DEV / 'dp_catalog.dec'}?mode=ro", uri=True)
    keys = [k for (k,) in con.execute(
        "select key from files_chunktype where key like 'spinestandingprefabgroup(hd)%'")]
    con.close()
    out = defaultdict(set)
    for k in keys:
        parts = k.split("/")
        if len(parts) < 4:
            continue
        cid, fn = parts[2], parts[3]
        seg = fn.split("_")
        if len(seg) >= 2:
            out[cid].add((seg[0], seg[1]))
    return {c: sorted(v) for c, v in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chars", nargs="*")
    ap.add_argument("--only", nargs="*", default=None, help="形如 870:00")
    a = ap.parse_args()

    chars = {("c" + x.lstrip("c")) for x in a.chars} if a.chars else None
    want = None
    if a.only:
        want = {tuple(x.replace("c", "").split(":")) for x in a.only}

    plan = list_standing(chars)
    cnames = costume_names()
    total = sum(len(v) for v in plan.values())
    print(f"角色 {len(plan)} 个 / 套装 {total} 套")
    for c, v in plan.items():
        print(f"  {c}: {list(v)}  时装名 {cnames.get(c, [])}")

    ok = 0
    for cid, files in plan.items():
        for idx, key in files.items():
            if want is not None and (cid.lstrip("c"), idx) not in want:
                continue
            print(f"\n=== {cid}/{idx} ===")
            for attempt in range(2):
                try:
                    bp = pull_bundle.pull("dp", key)
                    break
                except Exception as e:
                    print("  重试", e)
                    bp = None
            if not bp or not bp.exists():
                print("  拉取失败，跳过")
                continue
            dst_bundle = DEV / f"standing_{cid}_{idx}.bundle"
            shutil.copyfile(bp, dst_bundle)
            out = SPINE / f"{cid}_{idx}"
            saved = sys.argv[:]
            sys.argv = ["export_spine.py", str(dst_bundle), str(out), f"{cid}_{idx}"]
            try:
                export_spine.main()
                ok += 1
            except SystemExit as e:
                print("  导出失败", e)
            except Exception as e:
                print("  导出异常", e)
            finally:
                sys.argv = saved

    print(f"\n完成 {ok} 套 -> {SPINE}")


if __name__ == "__main__":
    main()
