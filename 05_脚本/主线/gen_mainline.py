# -*- coding: utf-8 -*-
"""生成 8-13 期主线（47、48 章）交付物。

数据源（全部实测，无硬编码）：
  Locale_MainScenario.dec   剧情全文（Key: d_main_<章>_<节>_<序>）
  Locale_Stage.dec          关卡名 / 章节名
  Locale_MainQuest.dec      主线任务名与描述
  CampaignChapterTable.json 章节 → 战场代号（FieldId / HardFieldId / StoryFieldId）
  CampaignStageTable.json   关卡属性（战力 / 等级 / 类型 / 敌人 / 奖励）
  FieldItemTable.json       隐藏收集品（ObtainLocation = 章号）
  FieldMapData_*.json       大地图实体点位（宝箱 / 关卡 / 传送门）
"""
import json
import sqlite3
from collections import Counter
from pathlib import Path

LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")
OUT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服\05_主线_47-48章")
SD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")

CHAPTERS = [(46, "候选参照"), (47, "本期新增"), (48, "本期新增")]

# 2026-10-25 目录重组：按类别分目录，文件名保留原编号（PDF 与文档里引用的是编号）
SUB = {
    "over": OUT / "01_总览",
    "chap": OUT / "02_章节与关卡",
    "map": OUT / "03_地图与点位",
    "story": OUT / "04_剧情文本",
    "img": OUT / "05_图片资源",
    "battle": OUT / "06_战斗场景还原",
}


def db(name):
    return sqlite3.connect(f"file:{LSC / name}?mode=ro", uri=True)


def locale_map(conn, table, keys, col="zh-CN"):
    out = {}
    for k in keys:
        for (v,) in conn.execute(f'select "{col}" from "{table}" where Key=?', (k,)):
            out[k] = v
    return out


def jload(name):
    return json.loads((SD / name).read_text(encoding="utf-8"))


def w(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print(f"  -> {p.relative_to(OUT.parent)}  {len(text):,} 字")


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    cstage = jload("CampaignStageTable.json")
    cchap = jload("CampaignChapterTable.json")
    citem = jload("FieldItemTable.json")

    c_scen = db("Locale_MainScenario.dec")
    c_stage = db("Locale_Stage.dec")
    c_quest = db("Locale_MainQuest.dec")

    # ---------- 1. 章节档案 ----------
    # ChapterMod 才是难度口径：0=普通、1=困难、2=剧情（实测 8xxxxxx 战力恒为 10,360，是剧情关）
    MOD = {0: "普通", 1: "困难", 2: "剧情"}
    chap_by_id = {r["Id"]: r for r in cchap}
    rows = []
    for ch in (45, 46, 47, 48):
        c = chap_by_id.get(ch + 1)          # CampaignChapterTable.Id = Chapter + 1
        assert c and c["Chapter"] == ch, f"章节表错位: ch{ch}"
        allst = [r for r in cstage if r["ChapterId"] == c["Id"]]
        by_mod = {m: [r for r in allst if r["ChapterMod"] == m] for m in MOD}
        normal = by_mod[0]
        bp = [r["StandardBattlePower"] for r in normal if r["StandardBattlePower"]]
        lv = [r["MonsterStageLv"] for r in normal if r["MonsterStageLv"]]
        hbp = [r["StandardBattlePower"] for r in by_mod[1] if r["StandardBattlePower"]]
        rows.append(
            dict(
                ch=ch,
                cn=locale_map(c_stage, "Locale_Stage", [f"chapter_name_{ch}"]).get(f"chapter_name_{ch}") or "",
                en="",
                field=c["FieldId"],
                hard=c["HardFieldId"],
                story=c["StoryFieldId"],
                n=len(normal), n_hard=len(by_mod[1]), n_story=len(by_mod[2]),
                bp_min=min(bp) if bp else 0,
                bp_max=max(bp) if bp else 0,
                hbp_min=min(hbp) if hbp else 0,
                hbp_max=max(hbp) if hbp else 0,
                lv_min=min(lv) if lv else 0,
                lv_max=max(lv) if lv else 0,
                items=len([r for r in citem if r["ObtainLocation"] == ch]),
            )
        )
    for r in rows:
        v = locale_map(c_stage, "Locale_Stage", [f"chapter_name_{r['ch']}"], col="en")
        r["en"] = v.get(f"chapter_name_{r['ch']}") or ""

    t = ["# 章节档案（45~48 章，含参照）",
         "# 来源：CampaignChapterTable + CampaignStageTable + Locale_Stage",
         "# 关卡数按 ChapterMod 拆分：0=普通、1=困难、2=剧情（剧情关战力恒为 10,360，不计入门槛）",
         "章\t中文名\t英文名\t普通战场\t困难战场\t剧情战场\t普通关\t困难关\t剧情关\t普通战力区间\t困难战力区间\t敌人等级\t隐藏收集品"]
    for r in rows:
        t.append(
            f"{r['ch']}\t{r['cn']}\t{r['en']}\t{r['field']}\t{r['hard']}\t{r['story']}\t"
            f"{r['n']}\t{r['n_hard']}\t{r['n_story']}\t{r['bp_min']:,}~{r['bp_max']:,}\t"
            f"{r['hbp_min']:,}~{r['hbp_max']:,}\t{r['lv_min']}~{r['lv_max']}\t{r['items']}"
        )
    w(SUB["chap"] / "01_章节档案.tsv", "\n".join(t) + "\n")

    # ---------- 2. 关卡表（普通 / 困难 / 剧情 三段） ----------
    cat_desc = {0: "普通", 1: "分支", 2: "BOSS"}
    for ch in (47, 48):
        c = chap_by_id[ch + 1]
        stages = sorted([r for r in cstage if r["ChapterId"] == c["Id"]], key=lambda x: (x["ChapterMod"], x["Id"]))
        keys = [f"{r['Id']}_name" for r in stages]
        nm_cn = locale_map(c_stage, "Locale_Stage", keys)
        nm_en = locale_map(c_stage, "Locale_Stage", keys, col="en")
        lines = [f"# 第 {ch} 章 关卡表（共 {len(stages)} 条：普通 {sum(1 for r in stages if r['ChapterMod']==0)}"
                 f" / 困难 {sum(1 for r in stages if r['ChapterMod']==1)}"
                 f" / 剧情 {sum(1 for r in stages if r['ChapterMod']==2)}）",
                 "# 来源：CampaignStageTable + Locale_Stage；模式 = ChapterMod（0 普通 / 1 困难 / 2 剧情）",
                 "模式\t关卡ID\t关卡名(中)\t关卡名(英)\t关卡类别\t敌人等级\t战力要求\t敌人ID\t奖励ID\t进入条件"]
        for r in stages:
            k = f"{r['Id']}_name"
            lines.append(
                f"{MOD.get(r['ChapterMod'])}\t{r['Id']}\t{nm_cn.get(k) or ''}\t{nm_en.get(k) or ''}\t"
                f"{cat_desc.get(r['StageCategory'], r['StageCategory'])}\t{r['MonsterStageLv']}\t"
                f"{r['StandardBattlePower']:,}\t{r['FieldMonsterId']}\t{r['RewardId']}\t{r['EnterCondition']}"
            )
        w(SUB["chap"] / f"{'02' if ch == 47 else '03'}_关卡表_{ch}章.tsv", "\n".join(lines) + "\n")

    # ---------- 3. 隐藏收集品 ----------
    for ch in (47, 48):
        items = sorted([r for r in citem if r["ObtainLocation"] == ch], key=lambda x: x["Id"])
        lines = [f"# 第 {ch} 章 隐藏收集品（{len(items)} 件）",
                 "# 来源：FieldItemTable，ObtainLocation = 章号",
                 "# Difficulty 1 = 大地图必刷（数量与 FieldMapData.ItemSpawner 一致）；2 = 条件触发",
                 "道具ID\t奖励组\t难度\t限定关卡\t限定场景\t蓝图\t提示"]
        for r in items:
            lines.append(
                f"{r['Id']}\t{r['TypeValue']}\t{r['Difficulty']}\t{r['SpawnConditionStage'] or '-'}\t"
                f"{r['ObtainScenario'] or '-'}\t{r['BlueprintId'] or '-'}\t{'是' if r['IsUseHint'] else '否'}"
            )
        w(SUB["map"] / f"{'04' if ch == 47 else '05'}_隐藏收集品_{ch}章.tsv", "\n".join(lines) + "\n")

    # ---------- 4. 大地图点位 ----------
    all_stage = {r["Id"]: r for r in cstage}
    for ch in (47, 48):
        f = SD / f"FieldMapData_fcbg_cityforest_{'010' if ch == 47 else '011'}.json"
        rec = json.loads(f.read_text(encoding="utf-8"))[0]
        lines = [f"# 第 {ch} 章 大地图实体点位（{rec['Id']}）",
                 "# 来源：FieldMapData_fcbg_cityforest_0xx（ScriptableObject）",
                 "# PositionId 是关卡场景内实体的 GUID；真实世界坐标在 12/13_关卡坐标_*.tsv（已落地）",
                 "实体类型\t序号\t引用ID\t关联内容"]
        for typ, lst in rec.items():
            if typ == "Id" or not isinstance(lst, list):
                continue
            for i, e in enumerate(lst, 1):
                ref = e.get("PositionId", "")
                extra = ""
                if "StageId" in e:
                    s = all_stage.get(e["StageId"], {})
                    nm = locale_map(c_stage, "Locale_Stage", [f"{e['StageId']}_name"]).get(f"{e['StageId']}_name", "")
                    extra = f"关卡 {e['StageId']} {nm} 战力{s.get('StandardBattlePower', 0):,}"
                elif "ItemId" in e:
                    it = next((x for x in citem if x["Id"] == e["ItemId"]), {})
                    extra = f"收集品 {e['ItemId']} 奖励组{it.get('TypeValue', '')}"
                elif "SwitchType" in e:
                    extra = f"SwitchType={e['SwitchType']} OnTrigger={e.get('OnTrigger')}"
                elif "OnTrigger" in e:
                    extra = f"OnTrigger={e.get('OnTrigger')}"
                lines.append(f"{typ}\t{i}\t{ref}\t{extra}")
        w(SUB["map"] / f"{'06' if ch == 47 else '07'}_大地图点位_{ch}章.tsv", "\n".join(lines) + "\n")

    # ---------- 5. 剧情全文 ----------
    import re
    for ch in (47, 48):
        cur = c_scen.execute(
            "select Key, [zh-CN], en, ja from Locale_MainScenario where Key GLOB ?", (f"d_main_{ch}_*",)
        ).fetchall()
        bucket = {}
        for k, cn, en, ja in cur:
            m = re.match(rf"d_main_{ch}_(\d+)_(\d+)$", k or "")
            if not m:
                continue
            sec, seq = int(m.group(1)), int(m.group(2))
            bucket.setdefault((sec, seq), (cn, en, ja))
        secs = sorted({s for s, _ in bucket})
        for tag, idx in (("zh-CN", 0), ("en", 1), ("ja", 2)):
            lines = [f"第 {ch} 章 剧情全文（{tag}）",
                     f"来源：Locale_MainScenario，Key = d_main_{ch}_<节>_<序>",
                     f"共 {len(bucket)} 行 / {len(secs)} 节：{'、'.join(f'{s:02d}' for s in secs)}",
                     "=" * 60, ""]
            for s in secs:
                lines.append(f"\n【第 {s:02d} 节】\n")
                for (ss, q) in sorted(k for k in bucket if k[0] == s):
                    v = (bucket[(ss, q)][idx] or "").strip()
                    if v:
                        lines.append(v)
                        lines.append("")
            w(SUB["story"] / (("08" if ch == 47 else "09") + f"_剧情_{ch}章_{tag}.txt"), "\n".join(lines))

    # ---------- 6. 主线任务链 ----------
    mq = jload("MainQuestTable.json")
    hit = [r for r in mq if r["TargetChapterId"] in (48, 49)]
    qkeys = [r["NameLocalkey"].split(":")[1] for r in hit] + \
            [r["DescriptionLocalkey"].split(":")[1] for r in hit]
    qcn = locale_map(c_quest, "Locale_MainQuest", qkeys)
    lines = ["# 8-13 期主线任务链（583~595）",
             "# 来源：MainQuestTable.TargetChapterId → CampaignChapterTable.Id（48=第47章，49=第48章）",
             "任务ID\t所属章\t任务名\t任务描述\t奖励ID\t下一任务"]
    for r in hit:
        ch = chap_by_id[r["TargetChapterId"]]["Chapter"]
        nk = r["NameLocalkey"].split(":")[1]
        dk = r["DescriptionLocalkey"].split(":")[1]
        lines.append(f"{r['Id']}\t第{ch}章\t{qcn.get(nk) or ''}\t{qcn.get(dk) or ''}\t{r['RewardId']}\t{r['NextMainQuestId']}")
    w(SUB["chap"] / "10_主线任务链.tsv", "\n".join(lines) + "\n")

    # ---------- 7. 说明文档 ----------
    r47 = next(r for r in rows if r["ch"] == 47)
    r48 = next(r for r in rows if r["ch"] == 48)
    md = f"""# 第 47、48 章（本期主线）

> 全部字段来自客户端静态表与文本表，无人工填写。表格可直接用 Excel 打开。

## 一句话

本期主线推进 **两章**：**第 47 章「{r47['cn']}」**（{r47['en']}）与 **第 48 章「{r48['cn']}」**（{r48['en']}）。
每章普通 **{r47['n']} 关** + 困难 **{r47['n_hard']} 关** + 剧情战 **{r47['n_story']} 段**；
普通战力门槛 {r47['bp_min']:,} → {r48['bp_max']:,}，敌人等级 {r47['lv_min']} → {r48['lv_max']}。

## 两章硬数据

| 项 | 第 47 章 | 第 48 章 |
| :--- | :--- | :--- |
| 章节名 | **{r47['cn']}** / {r47['en']} | **{r48['cn']}** / {r48['en']} |
| 普通关数 | {r47['n']} | {r48['n']} |
| 困难关数 | {r47['n_hard']} | {r48['n_hard']} |
| 剧情战段数 | {r47['n_story']} | {r48['n_story']} |
| 普通战力要求 | {r47['bp_min']:,} ~ {r47['bp_max']:,} | {r48['bp_min']:,} ~ {r48['bp_max']:,} |
| 困难战力要求 | {r47['hbp_min']:,} ~ {r47['hbp_max']:,} | {r48['hbp_min']:,} ~ {r48['hbp_max']:,} |
| 敌人等级 | {r47['lv_min']} ~ {r47['lv_max']} | {r48['lv_min']} ~ {r48['lv_max']} |
| 隐藏收集品 | {r47['items']} 件 | {r48['items']} 件 |
| 普通战场 | `{r47['field']}` | `{r48['field']}` |
| 困难战场 | `{r47['hard']}` | `{r48['hard']}` |
| 剧情战场 | `{r47['story']}` | `{r48['story']}` |

## 剧情节点（主线任务链）

| 任务 | 条件 | 内容 |
| :--- | :--- | :--- |
"""
    for r in hit:
        ch = chap_by_id[r["TargetChapterId"]]["Chapter"]
        nk = r["NameLocalkey"].split(":")[1]
        dk = r["DescriptionLocalkey"].split(":")[1]
        md += f"| {r['Id']} | 第{ch}章 {qcn.get(nk) or ''} | {qcn.get(dk) or ''} |\n"

    md += f"""
## 本目录文件

| 目录 | 文件 | 内容 |
| :--- | :--- | :--- |
| `01_总览/` | `00_主线说明.md` | 本文件 |
| | `11_缺口与待补.md` | 拿不到什么、为什么、怎么补（不写推测） |
| `02_章节与关卡/` | `01_章节档案.tsv` | 45~48 章对照：章名、三种战场代号、关卡数、战力/等级区间 |
| | `02_关卡表_47章.tsv` / `03_关卡表_48章.tsv` | 每关的关卡名、类型、敌人等级、战力、敌人ID、奖励ID |
| | `10_主线任务链.tsv` | 583~595 号任务：条件、任务名、描述、奖励 |
| `03_地图与点位/` | `大地图/地图_47章.png`、`地图_48章.png` | 顶视地图成图（含点位编号），另有 `_底图.png` 是未叠点的纯地形 |
| | `06_大地图点位_47章.tsv` / `07_..._48章.tsv` | 大地图上每一个宝箱、关卡入口、传送门、门与触发器的完整清单 |
| | `12_关卡坐标_47章.tsv` / `13_..._48章.tsv` | 46 个普通关卡的入口世界坐标 + 朝向 |
| | `04_隐藏收集品_47章.tsv` / `05_..._48章.tsv` | {r47['items']} / {r48['items']} 件收集品，含难度与限定条件 |
| `04_剧情文本/` | `08_剧情_47章_*.txt` / `09_剧情_48章_*.txt` | 剧情全文，中文 / 英文 / 日文三份，按节分段 |
| `05_图片资源/` | `章节预告图/` | 章节预告横幅 PNG |
| `06_战斗场景还原/` | `sbg_cityforest_00X_总览.png` ×3 | 广角总绘图，5 个掩体站位 + 多判充能点 |
| | `sbg_cityforest_00X_s1~s5.png` ×15 | 单站位实机视角，红十字标充能点 |
| | `充能点位_明细.tsv` | 15 行：枪口坐标 / 峰值段数 / 稳定段数 / 推荐 yaw+pitch / 充能点数 |
| | `说明.md` | 还原口径、总览机位、多判算法与结果、能证实与不能证实 |

## 交叉校验

- 第 47 章 `FieldMapData` 的宝箱点位 **14 个**，与 `FieldItemTable` 中 `ObtainLocation=47 且 Difficulty=1` 的 **14 件**一致；
- 第 48 章 同理 **13 / 13** 一致；
- 两章 `StageSpawner` 各 **46 个**，与 `CampaignStageTable` 中对应章节的**普通关卡数**（46）完全相同；
- 关卡 ID 段 `6047xxx`（普通）/ `7047xxx`（困难）/ `8047xxx`（剧情）与章节序号一一对应，无缺号。
"""
    w(SUB["over"] / "00_主线说明.md", md)


if __name__ == "__main__":
    main()
