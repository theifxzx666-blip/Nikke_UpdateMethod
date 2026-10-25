# -*- coding: utf-8 -*-
"""导出 CE009（PERSONA ON FRONTLINE）在 Locale_Event 里的全部文本。

CE009 是场地型联动活动，剧情对话不在 Locale_MainScenario（那是主线 + 章节型活动用的），
也不在其余 8 张 Locale_* 表里。客户端实际下发的 CE009 文本只有：
  - event_ce009_narrativesign_description_*  场景告示牌正文（女仆咖啡厅、宿舍守则、电视节目…）
  - CE009_NpcChange_* / CE009_FieldChange_*  场地状态变化提示
  - event_mpr_*                              P5R 小游戏 UI 文案（选择角色 / 人格面具 / 强化…）

产物：03_活动/PERSONA ON FRONTLINE（ce009）/活动文本/
"""
import sqlite3
from pathlib import Path

LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")
OUT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\03_活动\PERSONA ON FRONTLINE（ce009）\活动文本")
LANGS = [("zh-CN", "简中"), ("zh-TW", "繁中"), ("ja", "日文"), ("en", "英文"), ("ko", "韩文")]


def cat(k):
    kl = k.lower()
    if "narrativesign" in kl:
        return "场景告示牌"
    if "npcchange" in kl:
        return "NPC 状态变化"
    if "fieldchange" in kl:
        return "场地状态变化"
    if kl.startswith("event_mpr"):
        return "P5R 小游戏 UI"
    if kl.startswith("event_ce009"):
        return "活动其他"
    return "其他"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{LSC/'Locale_Event.dec'}?mode=ro", uri=True)
    rows = [r for r in con.execute(
        'select "Key","zh-CN","zh-TW","ja","en","ko" from Locale_Event')
        if "ce009" in str(r[0]).lower() or str(r[0]).lower().startswith("event_mpr")]
    rows.sort(key=lambda r: (cat(r[0]), r[0]))
    print("CE009 文本条目", len(rows))

    # 三语/五语汇总表
    tsv = ["# CE009（PERSONA ON FRONTLINE）客户端下发的全部文本",
           "# 来源 Locale_Event；CE009 没有剧情对话条目（见 00_说明.md）",
           "\t".join(["分类", "键", "简中", "繁中", "日文", "英文", "韩文"])]
    for r in rows:
        cells = [cat(r[0]), r[0]] + [("" if r[i] is None else str(r[i]).replace("\t", " ").replace("\n", "\\n"))
                                    for i in range(1, 6)]
        tsv.append("\t".join(cells))
    (OUT / "CE009_活动文本_全语言.tsv").write_text("\n".join(tsv) + "\n", encoding="utf-8-sig")

    # 按语种出纯文本，便于直接阅读
    for li, (col, tag) in enumerate(LANGS):
        lines = [f"CE009 · PERSONA ON FRONTLINE — 客户端下发文本（{tag}）",
                 f"条目数：{len(rows)}",
                 "=" * 72, ""]
        cur = None
        for r in rows:
            c = cat(r[0])
            if c != cur:
                lines += ["", f"## {c}", ""]
                cur = c
            lines.append(f"[{r[0]}]")
            lines.append("" if r[li + 1] is None else str(r[li + 1]))
            lines.append("")
        (OUT / f"CE009_{tag}.txt").write_text("\n".join(lines), encoding="utf-8-sig")

    from collections import Counter
    print("分类分布", Counter(cat(r[0]) for r in rows))
    print("->", OUT)


if __name__ == "__main__":
    main()
