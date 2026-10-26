# -*- coding: utf-8 -*-
"""导出活动剧情对话文本（与主线剧情同一张表 Locale_MainScenario）。

主线 key 形如 d_main_<章>_<节>_<序>；活动 key 形如
  event_<活动名>_<章>_<段>_<序>      例 event_twoxtwolove_1ch_01_1
  event_<活动名>_<段>_e_<序>         例 event_lastkingdom1_01_e_1
所以按「第 2 段」把活动名切出来即可分组。

产物：04_剧情文本/活动剧情/<活动名>_<语种>.txt
     04_剧情文本/活动剧情/00_活动清单.tsv
"""
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")
OUT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\05_主线_47-48章\04_剧情文本\活动剧情")
LANGS = [("zh-CN", "简中"), ("zh-TW", "繁中"), ("ja", "日文"), ("en", "英文"), ("ko", "韩文")]


def natkey(k):
    """按自然序排：把数字段转成 int"""
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", k)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{LSC/'Locale_MainScenario.dec'}?mode=ro", uri=True)

    rows = con.execute(
        'select "Key","zh-CN","zh-TW","ja","en","ko" from Locale_MainScenario '
        'where "Key" like \'event\\_%\' escape \'\\\''
    ).fetchall()
    print("活动剧情行数", len(rows))

    groups = defaultdict(list)
    bad = 0
    for r in rows:
        k = r[0]
        parts = k.split("_")
        if len(parts) < 3:
            bad += 1
            continue
        groups[parts[1]].append(r)
    print("活动数", len(groups), "无法归组的", bad)

    manifest = ["# 活动剧情清单（来源 Locale_MainScenario，key 前缀 event_<活动名>_*）",
                "# 条目数 = 该活动的对话/文本条目数（含分支与旁白）",
                "# 目录结构：活动剧情/<活动名>/{简中,繁中,日文,英文,韩文}.txt",
                "活动名\t条目数\t首个键\t末个键"]
    total = 0
    allzh = []
    for name in sorted(groups, key=lambda x: -len(groups[x])):
        rs = sorted(groups[name], key=lambda r: natkey(r[0]))
        total += len(rs)
        manifest.append(f"{name}\t{len(rs)}\t{rs[0][0]}\t{rs[-1][0]}")
        sub = OUT / name
        sub.mkdir(exist_ok=True)
        for li, (col, tag) in enumerate(LANGS):
            lines = [f"活动剧情 · {name}（{tag}）",
                     f"来源：Locale_MainScenario，Key = event_{name}_*",
                     f"条目数：{len(rs)}",
                     "=" * 72]
            for r in rs:
                v = r[li + 1]
                if v is None or str(v).strip() == "":
                    continue
                lines.append(f"[{r[0]}]")
                lines.append(str(v).replace("\r\n", "\n"))
                lines.append("")
            (sub / f"{tag}.txt").write_text("\n".join(lines), encoding="utf-8-sig")
            if col == "zh-CN":
                allzh.append(f"\n{'='*72}\n活动：{name}（{len(rs)} 条）\n{'='*72}")
                allzh.extend(lines[4:])

    (OUT / "00_活动清单.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8-sig")
    (OUT / "00_全部活动_简中合集.txt").write_text("\n".join(allzh), encoding="utf-8-sig")
    print(f"-> 活动 {len(groups)} 个 / 条目 {total} / 文件 {len(groups)*len(LANGS)+2}")
    print("->", OUT)


if __name__ == "__main__":
    main()
