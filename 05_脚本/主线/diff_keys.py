# -*- coding: utf-8 -*-
"""diff_keys.py —— 对比两期 bundle 键清单，按业务族分组输出「本期新增」。

用法：
  python diff_keys.py --old <基线>/core_keys.txt --new <本期>/core_keys.txt \
                      --out <输出>/新增键.tsv [--removed <删除键.tsv>]

为什么不用简单 set 差：一个桶 4 万个 bundle，裸差集出来 2 万行没法看。
分族之后人眼能对账：爆裂多了 3 个 = 本期 3 个新角色各一条爆裂包。

分族规则是**按实测包名前缀**写的，新增前缀要补到 FAMILY 里，否则落到「未分类」。
"""
from __future__ import annotations
import argparse, os, re, sys
from collections import Counter, defaultdict

# (族名, 匹配包名的正则)。有序匹配，先命中先用。
FAMILY = [
    ("爆裂演出",   r"^spotskillcutscene_assets_"),
    ("立绘_HD",    r"^icons-char-full\(hd\)_assets_"),
    ("立绘_SD",    r"^icons-char-full\(sd\)_assets_"),
    ("半身像",     r"^icons-char-mi\(hd\)_assets_"),
    ("小人立绘",   r"^sdcharacters_assets_"),
    ("大厅站立",   r"^spinestandingcharactergroup"),
    ("BOSS动画",   r"^spotmonsteranimation_assets_"),
    ("BOSS模型",   r"^spotmonster\(hd\)_assets_|^spotmonster\(sd\)_assets_"),
    ("BOSS地图",   r"^spotmonstermap_assets_"),
    ("壁纸与场景", r"^livewallpaperprefabs_assets_"),
    ("剧情插画",   r"^scenariobackground\(hd\)_assets_|^scenariobackground_assets_"),
    ("战斗场景",   r"^spotbackground"),
    ("音频",       r"^audiogroup"),
    ("特效",       r"^effect-|_library_assets_fx_"),
    ("UI",         r"^ui|^view_assets_|^prefab"),
    ("文本表",     r"\.lss$|\.lsc$|catalog"),
]

RE_CHAR = re.compile(r"_c(\d{3})_(\d{2})")
RE_EVENT = re.compile(r"ce(\d{3})")
RE_CHAP = re.compile(r"chap_(\d+)_(\d+)")
RE_DATE = re.compile(r"event_(\d{6})")


def family(name: str) -> str:
    for label, rx in FAMILY:
        if re.search(rx, name, re.I):
            return label
    return "未分类"


def rid(name: str) -> str:
    m = RE_CHAR.search(name)
    if m:
        return f"c{m.group(1)}_{m.group(2)}"
    m = RE_EVENT.search(name)
    if m:
        return f"ce{m.group(1)}"
    m = RE_CHAP.search(name)
    if m:
        return f"chap_{m.group(1)}_{m.group(2)}"
    m = RE_DATE.search(name)
    if m:
        return f"event_{m.group(1)}"
    return ""


def load(p: str) -> set:
    with open(p, encoding="utf-8", errors="ignore") as fh:
        return {ln.strip() for ln in fh if ln.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, help="上一期 <桶>_keys.txt")
    ap.add_argument("--new", required=True, help="本期 <桶>_keys.txt")
    ap.add_argument("--out", required=True, help="新增键 TSV 输出路径")
    ap.add_argument("--removed", default=None, help="删除键 TSV（可选）")
    a = ap.parse_args()

    for p in (a.old, a.new):
        if not os.path.isfile(p):
            sys.exit(f"[FATAL] 找不到 {p}")

    old, new = load(a.old), load(a.new)
    added = sorted(new - old)
    removed = sorted(old - new)

    print(f"基线 {len(old)}｜本期 {len(new)}｜新增 {len(added)}｜删除 {len(removed)}")

    fam = Counter(family(n) for n in added)
    print("\n新增按族：")
    for k, v in fam.most_common():
        print(f"  {v:>5}  {k}")

    # 每个族里有哪些资源 id（人眼对账用）
    per = defaultdict(Counter)
    for n in added:
        per[family(n)][rid(n)] += 1
    print("\n各族的资源 id：")
    for f, c in per.items():
        ids = ", ".join(f"{k}({v})" for k, v in list(c.most_common(8)) if k)
        print(f"  {f}: {ids or '—'}")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write("族\t资源id\t包名\n")
        for n in added:
            fh.write(f"{family(n)}\t{rid(n)}\t{n}\n")
    print(f"\n→ {a.out}")

    if a.removed:
        with open(a.removed, "w", encoding="utf-8-sig", newline="") as fh:
            fh.write("族\t资源id\t包名\n")
            for n in removed:
                fh.write(f"{family(n)}\t{rid(n)}\t{n}\n")
        print(f"→ {a.removed}")

    if fam.get("未分类"):
        print(f"\n[注意] 未分类 {fam['未分类']} 条 —— 新前缀要补进 FAMILY 表，"
              f"样例：{next(n for n in added if family(n) == '未分类')}")


if __name__ == "__main__":
    main()
