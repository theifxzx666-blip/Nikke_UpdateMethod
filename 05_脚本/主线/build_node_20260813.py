# -*- coding: utf-8 -*-
"""build_node_20260813.py —— 生成「2026-08-13 国际服更新还原包」的证据与清单。

数据源（全部本地实测产物，不联网、不猜）：
  1. D:\\Codex\\临时\\nikke_intl_20261029\\device\\lsc\\*.dec   ← pull_lsc.py 从设备 saus/raw 拉取并解密
  2. D:\\Codex\\Nikke\\Nikke_Skills\\拆包\\02_Skills\\mpdump\\out\\  ← StaticData_152 静态表导出
  3. 拆包\\00_资源库\\版本节点\\_干跑_20261025\\00_基线_静态表\\  ← 基线静态表快照

输出（写到版更节点目录）：
  06_证据\\01_文本证据.tsv      键 -> en / zh-CN / ja + 来源
  06_证据\\02_角色属性.tsv      CharacterTable 中 c870 / c871 / c580 的实测字段
  06_证据\\03_皮肤清单.tsv      Locale_CharacterCostume 全量 183 条（含本期 5 件标记）
  06_证据\\04_活动路标_ce009.md  ce009 剧情路标 21 条（中英对照）
"""
import json
import sqlite3
from pathlib import Path

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
LSC = DEV / "lsc"
MPD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")
NODE = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
EV = NODE / "06_证据"

CIDS = [870, 871, 580]


def con(name):
    return sqlite3.connect(f"file:{LSC / name}?mode=ro", uri=True)


def row(tbl, key):
    c = con(tbl + ".dec")
    r = c.execute(f'select Key,en,[zh-CN],ja from "{tbl}" where Key=?', (key,)).fetchone()
    c.close()
    return r


# ---------- 01 文本证据 ----------
K = []
for cid in CIDS:
    # CV 键无单一 `NNN_cv`，客户端分语言挂在 `NNN_cv_en/_ja/_ko`（三行内容一致）
    K += [(f"{cid}_name", "Locale_Character"), (f"c{cid}_description", "Locale_Character"),
          (f"{cid}_cv_en", "Locale_Character"), (f"{cid}_cv_ja", "Locale_Character")]

# 皮肤：本期 5 件（870_01/02、871_01/02、580_01）
for cid, sk in [(870, "01"), (870, "02"), (871, "01"), (871, "02"), (580, "01")]:
    K += [(f"{cid}_{sk}_costume_name", "Locale_CharacterCostume"),
          (f"{cid}_{int(sk)}_description", "Locale_CharacterCostume")]

# 技能：爆裂 / 技能1 / 技能2（键由 CharacterTable 的 UltiSkillId/Skill1Id/Skill2Id 前 5 位推出）
SK = {"870": ["18703", "28701", "28702"], "871": ["18713", "28711", "28712"]}
for cid, ks in SK.items():
    for k in ks:
        K += [(f"{k}_name", "Locale_Skill"), (f"{k}_description", "Locale_Skill")]

lines = ["键\t英文\t简体中文\t日文\t来源表"]
miss = []
for key, tbl in K:
    try:
        r = row(tbl, key)
    except Exception as e:  # noqa: BLE001
        r = None
    if not r:
        miss.append(f"{tbl}:{key}")
        continue
    cells = [(x or "").replace("\t", " ").replace("\n", " ⏎ ") for x in r]
    lines.append("\t".join(cells + [tbl]))
(EV / "01_文本证据.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"[01] 文本证据 {len(lines)-1} 条，缺失 {len(miss)}：{miss}")

# ---------- 02 角色属性 ----------
ct = json.load(open(MPD / "CharacterTable.json", encoding="utf-8"))
rows = []
for cid in CIDS:
    rec = [x for x in ct if x["NameLocalkey"] == f"Locale_Character:{cid}_name"]
    if not rec:
        continue
    base = min(rec, key=lambda x: x["GradeCoreId"])
    rows.append({
        "cID": cid,
        "CharacterTable.Id": base["Id"],
        "NameLocalkey": base["NameLocalkey"],
        "OriginalRare(3=SSR)": base["OriginalRare"],
        "Corporation": base["Corporation"],
        "Class": base["Class"],
        "ElementId": ",".join(map(str, base["ElementId"])),
        "UseBurstSkill": base["UseBurstSkill"],
        "UltiSkillId": base["UltiSkillId"],
        "Skill1Id": base["Skill1Id"],
        "Skill2Id": base["Skill2Id"],
        "Squad": base["Squad"],
        "CvLocalkey": base["CvLocalkey"],
    })
hdr = list(rows[0].keys())
out = ["\t".join(hdr)] + ["\t".join(str(r[h]) for h in hdr) for r in rows]
(EV / "02_角色属性.tsv").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"[02] 角色属性 {len(rows)} 行")

# ---------- 03 皮肤清单 ----------
c = con("Locale_CharacterCostume.dec")
cos = list(c.execute('select Key,en,[zh-CN] from Locale_CharacterCostume '
                     'where Key like "%_costume_name" order by Key'))
c.close()
NEW = {"870_01", "870_02", "871_01", "871_02", "580_01"}
out = ["键\t归属cID\t序号\t英文名\t简体中文名\t是否本期新增"]
for k, en, zh in cos:
    cid, seq = k.replace("_costume_name", "").split("_")
    tag = "本期新增" if f"{cid}_{seq}" in NEW else ""
    out.append(f"{k}\t{cid}\t{seq}\t{(en or '').replace(chr(9),' ')}\t{(zh or '').replace(chr(9),' ')}\t{tag}")
(EV / "03_皮肤清单.tsv").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"[03] 皮肤清单 {len(cos)} 条（本期新增 5 件标记）")

# ---------- 04 活动路标 ----------
c = con("Locale_Event.dec")
ns = list(c.execute('select Key,en,[zh-CN] from Locale_Event '
                    'where Key like "event_ce009_narrativesign_description_%" order by Key'))
c.close()
md = ["# ce009 剧情路标文本（21 条，客户端原文）", "",
      "> 来源：`Locale_Event.lsc` → 键 `event_ce009_narrativesign_description_01..21`。",
      "> 这类文本是活动地图内可交互提示（宿舍守则、电视节目、女仆咖啡厅菜单），是判定 ce009 = PERSONA 联动的直接文本证据。", ""]
for k, en, zh in ns:
    md.append(f"### {k.split('_')[-1]}")
    md.append(f"- **中**：{(zh or '').replace(chr(10),' / ')}")
    md.append(f"- **EN**：{(en or '').replace(chr(10),' / ')}")
    md.append("")
(EV / "04_活动路标_ce009.md").write_text("\n".join(md), encoding="utf-8")
print(f"[04] 活动路标 {len(ns)} 条")

# ---------- 校验汇总 ----------
chk = ["# 本包数据校验记录", "",
       "| 项 | 值 |", "| :--- | :--- |",
       f"| 文本证据条数 | {len(lines)-1} |",
       f"| 文本证据缺失键 | {len(miss)} {miss if miss else ''} |",
       f"| 角色属性行数 | {len(rows)} |",
       f"| 皮肤 `_costume_name` 总数 | {len(cos)} |",
       f"| 本期新增皮肤 | {len(NEW)} |",
       f"| ce009 路标条数 | {len(ns)} |"]
(EV / "05_校验汇总.md").write_text("\n".join(chk) + "\n", encoding="utf-8")
print("[05] 校验汇总写入")
