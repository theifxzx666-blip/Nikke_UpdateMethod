# -*- coding: utf-8 -*-
r"""fix_char_skill_md.py — 把 01_新角色/<角色>/角色信息.md 的技能段改成「10 级数值 + 全文」

为什么要有这一步：
  这些 md 早期是从 Locale_Skill 直接抄的原文，`{description_value_01}` 这类占位符原样留着，
  等于没有数值。SkillInfoTable 里每个 GroupId × SkillLevel 才带 DescriptionValueList，
  取 SkillLevel=10 那一条才能把占位符填成 10 级的值。

数据链路：
  CharacterTable.ResourceId → Skill1Id / Skill2Id / UltiSkillId → SkillInfoTable.Id
    → GroupId → 同 GroupId 且 SkillLevel=10 的记录
  名称/类型/描述走 NameLocalkey / InfoDescriptionLocalkey / DescriptionLocalkey（Locale_Skill）

用法：python fix_char_skill_md.py
"""
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服\01_新角色")
LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")
SKILL_JSON = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out\SkillInfoTable.json")

# 角色目录 → 三个技能组（大招 / 技能1 / 技能2），与 PDF 用的是同一组 ID
CHARS = {
    "QUEEN（真）_c870": ["18703", "28701", "28702"],
    "雪子_c871": ["18713", "28711", "28712"],
    "埃癸斯_c872": ["18723", "28721", "28722"],
}

SVAR = re.compile(r"\{description_value_(\d+)\}")
SWG = re.compile(r"<word_group=\d+>(.*?)</word_group>", re.S)
SCOLOR = re.compile(r"<color=#[0-9A-Fa-f]{6}>(.*?)</color>", re.S)


def plain(raw, vals):
    s = (raw or "").replace("\r", "")
    s = SVAR.sub(lambda m: vals[int(m.group(1)) - 1]
                 if int(m.group(1)) - 1 < len(vals) else "?", s)
    s = SWG.sub(r"\1", s)
    s = SCOLOR.sub(r"\1", s)
    return [x.strip() for x in s.split("\n") if x.strip()]


def main():
    info = {r["GroupId"]: r for r in json.loads(SKILL_JSON.read_text(encoding="utf-8"))
            if r.get("SkillLevel") == 10}
    con = sqlite3.connect(f"file:{LSC / 'Locale_Skill.dec'}?mode=ro", uri=True)

    def loc(key):
        r = con.execute("select [zh-CN] from Locale_Skill where Key=?", (key,)).fetchone()
        r2 = con.execute("select [en] from Locale_Skill where Key=?", (key,)).fetchone()
        return (r[0] if r else ""), (r2[0] if r2 else "")

    for dname, groups in CHARS.items():
        d = ROOT / dname
        md = d / "角色信息.md"
        if not md.exists():
            print("[!] 缺 %s" % md)
            continue
        head = md.read_text(encoding="utf-8").split("## 技能")[0].rstrip()

        rows, blocks, icons = [], [], []
        for i, g in enumerate(groups):
            rec = info.get(int(g))
            typ = loc(rec["InfoDescriptionLocalkey"].split(":")[-1])[0]
            zh, en = loc(rec["NameLocalkey"].split(":")[-1])
            vals = [v.get("DescriptionValue", "") for v in rec["DescriptionValueList"]]
            lines = plain(loc(rec["DescriptionLocalkey"].split(":")[-1])[0], vals)
            rows.append("| %s | **%s** | %s |" % (typ, zh, en))
            icon = "技能图标_%d_%s.png" % (i + 1, typ or ("技能%d" % i))
            icons.append(icon)
            used = [v for v in vals if v]
            blocks += ["### %s · %s" % (typ, zh), "",
                       "图标：`%s`　｜　SkillInfoTable GroupId `%s` · SkillLevel **10**" % (icon, g), ""]
            blocks += lines
            blocks += ["", "10 级数值：`description_value_01` 起依次为 **%s**" % " / ".join(used), ""]

        body = ["## 技能", "",
                "| 类型 | 中文名 | 英文名 |", "| :--- | :--- | :--- |"]
        body += rows
        body += [""]
        body += blocks
        body += ["## 素材", "",
                 "| 文件 | 说明 |", "| :--- | :--- |",
                 "| 立绘_高清.png | 全身立绘 HD —— **PDF 只嵌这一张** |",
                 "| 立绘.png | 标准尺寸备份，不进 PDF |",
                 "| 半身像.png | 半身像 / 头像用 |",
                 "| 小人立绘.png | Q 版小人，透明背景 |"]
        for ic in icons:
            body.append("| %s | 技能图标 128×128 |" % ic)
        md.write_text(head + "\n\n" + "\n".join(body).rstrip() + "\n", encoding="utf-8")
        print("[OK] %s" % md)


if __name__ == "__main__":
    main()
