# -*- coding: utf-8 -*-
"""输出关卡信息总表 + 关底 BOSS 明细。

数据源（全部实测）：
  CampaignStageTable.json   关卡属性：Id / ChapterId / ChapterMod / StageCategory /
                            MonsterStageLv / StandardBattlePower / FieldMonsterId / RewardId
  CampaignChapterTable.json 章 → 大地图（FieldId / HardFieldId / StoryFieldId）
  MonsterFieldTable.json    FieldMonsterId → 预制体 / 属性 / IsBoss
  MonsterModelTable.json    预制体 → 型号（Grade）/ 体量（Size）/ 生成型
  MonsterTable.json         UiGrade（强度分级）/ SkillData（技能）
  Locale_Stage.dec          关卡名（中/英）
  12/13_关卡坐标_*.tsv      普通关在大地图上的世界坐标
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

SD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")
LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")
OUT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\05_主线_47-48章")

MOD = {0: "普通", 1: "困难", 2: "剧情"}
# 与 07_关卡莱彻 的 CAT_CN 保持一致：0/1 普通、2 精英、3 多敌、4 章末 BOSS
CAT = {0: "普通关", 1: "普通关", 2: "精英关", 3: "EX 关", 4: "章末BOSS"}
GRADE_CN = {0: "无", 1: "无私级", 2: "仆从级", 3: "主宰级", 4: "领主级",
            5: "暴君级", 6: "异端者", 7: "女王"}
# MonsterModelTable.Grade / Size 枚举（与 07_关卡莱彻 的口径一致）
GRADE_T_CN = {1: "杂兵", 2: "爪牙", 3: "精英", 4: "百夫长", 5: "首领"}
SIZE_CN = {1: "小型", 2: "中型", 3: "大型", 4: "巨型"}
GENERA_CN = {1: "普通", 2: "暗物质"}


def jload(n):
    return json.loads((SD / n).read_text(encoding="utf-8"))


def loc_stage():
    con = sqlite3.connect(f"file:{LSC / 'Locale_Stage.dec'}?mode=ro", uri=True)
    out = {}
    for k, zh, en in con.execute('select "Key","zh-CN","en" from Locale_Stage'):
        out[k] = (zh, en)
    return out


def main():
    stages = jload("CampaignStageTable.json")
    chapters = jload("CampaignChapterTable.json")
    field = {r["Id"]: r for r in jload("MonsterFieldTable.json")}
    models = jload("MonsterModelTable.json")
    mons = jload("MonsterTable.json")
    nm = loc_stage()

    model_by_prefab = {}
    for r in models:
        model_by_prefab.setdefault(r["MonPrefab"], r)

    chap_by_id = {c["Id"]: c for c in chapters}
    FIELD_KEY = {0: "FieldId", 1: "HardFieldId", 2: "StoryFieldId"}

    # 普通关坐标（大地图 StageSpawner 世界坐标）
    coord = {}
    for ch, f in ((47, "12_关卡坐标_47章.tsv"), (48, "13_关卡坐标_48章.tsv")):
        p = OUT / "03_地图与点位" / f
        if not p.exists():
            continue
        for ln in p.read_text(encoding="utf-8-sig").splitlines():
            if not ln or ln.startswith("#") or ln.startswith("关卡ID"):
                continue
            c = ln.split("\t")
            if len(c) >= 5:
                coord[int(c[0])] = (c[3], c[4])

    def mon_info(fid):
        """FieldMonsterId → (预制体, 型号, 体量, 强度分级, 生成型, 技能数, 型号表预制体)"""
        f = field.get(fid)
        if not f:
            return ("—",) * 7
        prefab = f["MonPrefab"]
        mod = model_by_prefab.get(prefab)
        mod_prefab = prefab
        if mod is None:
            base = prefab.replace("_sd_var", "").replace("_var", "")
            if base in model_by_prefab:
                mod, mod_prefab = model_by_prefab[base], base
        if mod is None:
            cands = [k for k in model_by_prefab if prefab.startswith(k)]
            if cands:
                mod_prefab = max(cands, key=len)
                mod = model_by_prefab[mod_prefab]

        fam = [m for m in mons if str(m["Id"]).startswith(str(fid))]
        ui = Counter(m["UiGrade"] for m in fam).most_common(1)[0][0] if fam else 0
        sk = set(f.get("FieldSkillId") or [])
        for m in fam:
            for sd in (m.get("SkillData") or []):
                if sd.get("SkillId"):
                    sk.add(sd["SkillId"])

        grade = GRADE_T_CN.get(mod["Grade"], "?") if mod else "?"
        size = SIZE_CN.get(mod["Size"], "?") if mod else "?"
        gen = GENERA_CN.get(mod.get("MonsterGeneration"), str(mod.get("MonsterGeneration"))) if mod else "?"
        return (prefab, grade, size, GRADE_CN.get(ui, "?"), gen, str(len(sk)), mod_prefab)

    # ---------- 1. 关卡信息总表 ----------
    # 关卡编号直接取 Locale_Stage 的关卡名前缀（47-1 / 47-13A-1 / 47-36 / EX），与游戏内显示一致
    no_by_id = {}
    for r in stages:
        zh, _ = nm.get(f"{r['Id']}_name", ("", ""))
        if zh and zh.split():
            no_by_id[r["Id"]] = zh.split()[0]
    # 剧情战关没有本地化名，用普通关的 StageChild 反查它挂在哪个关卡下
    child_of = {}
    for r in stages:
        sc = r.get("StageChild") or 0
        if sc and r["Id"] in no_by_id:
            child_of[sc] = no_by_id[r["Id"]]

    head = ["模式", "关卡ID", "关卡编号", "关卡名", "关卡类型", "类别码", "敌人等级",
            "战力要求", "莱彻预制体", "型号", "体量", "强度分级", "生成型", "技能数",
            "大地图", "地图X", "地图Z", "奖励ID", "进入条件", "备注"]
    lines = ["# 第 47 / 48 章 全关卡信息总表（普通 46 + 困难 46 + 剧情 6，每章 98 条）",
             "# 关卡类型 = CampaignStageTable.StageCategory：0/1 普通关、2 精英关、3 EX 关、4 章末BOSS",
             "# 莱彻 = 该关的 FieldMonsterId（CampaignStageTable 每关只挂 1 个场地怪）"
             "→ MonsterFieldTable → MonsterModelTable",
             "# 大地图 = CampaignChapterTable.FieldId / HardFieldId / StoryFieldId（按模式区分）",
             "# 地图X / 地图Z = 大地图 StageSpawner 的世界坐标，只有普通关落点（困难/剧情共用同一张图）",
             "# 剧情战关（8047xxx）在 Locale_Stage 里没有关卡名，编号按 StageChild 回挂到父关",
             "\t".join(head)]
    cnt_cat = {}
    for chid, ch in ((48, 47), (49, 48)):
        c = chap_by_id[chid]
        for m in (0, 1, 2):
            rows = sorted([r for r in stages if r["ChapterId"] == chid and r["ChapterMod"] == m],
                          key=lambda x: x["Id"])
            fmap = c[FIELD_KEY[m]]
            for r in rows:
                zh, _ = nm.get(f"{r['Id']}_name", ("", ""))
                no = no_by_id.get(r["Id"]) or (f"{child_of[r['Id']]}（剧情）" if r["Id"] in child_of else "—")
                prefab, grade, size, ui, gen, nsk, _ = mon_info(r["FieldMonsterId"])
                xy = coord.get(r["Id"]) if m == 0 else None

                notes = []
                if r["StageCategory"] == 3:
                    notes.append("EX")
                if r["StageCategory"] == 4:
                    notes.append("章末BOSS")
                if r.get("StageChild"):
                    notes.append(f"有剧情战子关 {r['StageChild']}")
                if r["Id"] in child_of:
                    notes.append(f"对应普通关 {child_of[r['Id']]}")

                lines.append("\t".join([
                    MOD[m], str(r["Id"]), no, zh or "（无本地化名称）",
                    CAT.get(r["StageCategory"], f"类别{r['StageCategory']}"),
                    str(r["StageCategory"]), str(r["MonsterStageLv"]),
                    f"{r['StandardBattlePower']:,}", prefab, grade, size, ui, gen, nsk,
                    fmap, xy[0] if xy else "—", xy[1] if xy else "—",
                    str(r["RewardId"]), str(r["EnterCondition"]),
                    "；".join(notes) or "—",
                ]))
                k = (ch, MOD[m], CAT.get(r["StageCategory"]))
                cnt_cat[k] = cnt_cat.get(k, 0) + 1
    p1 = OUT / "02_章节与关卡" / "04_关卡信息总表.tsv"
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    print("->", p1.name, len(lines) - 7, "条")

    # ---------- 1b. 重写 02/03_关卡表（修正关卡类别标注） ----------
    # 旧版把 StageCategory=2 直接写成「BOSS」，3/4 又漏成裸数字，导致关底 BOSS 看不出来。
    for chid, ch, fn in ((48, 47, "02_关卡表_47章.tsv"), (49, 48, "03_关卡表_48章.tsv")):
        rows = sorted([r for r in stages if r["ChapterId"] == chid],
                      key=lambda x: (x["ChapterMod"], x["Id"]))
        n_by_mod = Counter(r["ChapterMod"] for r in rows)
        tl = [f"# 第 {ch} 章 关卡表（共 {len(rows)} 条：普通 {n_by_mod[0]}"
              f" / 困难 {n_by_mod[1]} / 剧情 {n_by_mod[2]}）",
              "# 来源：CampaignStageTable + Locale_Stage；模式 = ChapterMod（0 普通 / 1 困难 / 2 剧情）",
              "# 关卡类别 = StageCategory：0/1 普通关、2 精英关、3 EX 关、4 章末BOSS",
              "模式\t关卡ID\t关卡编号\t关卡名(中)\t关卡名(英)\t关卡类别\t敌人等级\t战力要求\t敌人ID\t奖励ID\t进入条件"]
        for r in rows:
            zh, en = nm.get(f"{r['Id']}_name", ("", ""))
            no = no_by_id.get(r["Id"]) or (f"{child_of[r['Id']]}（剧情）" if r["Id"] in child_of else "—")
            tl.append("\t".join([
                MOD[r["ChapterMod"]], str(r["Id"]), no, zh or "（无本地化名称）", en or "—",
                CAT.get(r["StageCategory"], f"类别{r['StageCategory']}"),
                str(r["MonsterStageLv"]), f"{r['StandardBattlePower']:,}",
                str(r["FieldMonsterId"]), str(r["RewardId"]), str(r["EnterCondition"]),
            ]))
        pf = OUT / "02_章节与关卡" / fn
        pf.write_text("\n".join(tl) + "\n", encoding="utf-8-sig")
        print("->", fn, len(tl) - 4, "条")

    # ---------- 2. 关底 BOSS ----------
    bh = ["章", "模式", "关卡ID", "关卡编号", "关卡名", "BOSS 预制体", "FieldMonsterId",
          "强度分级", "型号", "体量", "生成型", "敌人等级", "战力要求", "技能数", "技能Id",
          "专属战斗场景", "大地图", "地图X", "地图Z", "奖励ID"]
    blines = ["# 第 47 / 48 章 关底 BOSS（StageCategory = 4，每章普通/困难/剧情各 1 关）",
              "# 「专属战斗场景」= 客户端 spotbackground(hd) 里形如 sbg_cityforest<BOSS预制体>_00x 的场景包；",
              "#   实测本章两个 BOSS 都没有专属场景，关底战复用 sbg_cityforest_001/002/003 通用战斗背景",
              "\t".join(bh)]
    for chid, ch in ((48, 47), (49, 48)):
        c = chap_by_id[chid]
        rows = sorted([r for r in stages if r["ChapterId"] == chid and r["StageCategory"] == 4],
                      key=lambda x: (x["ChapterMod"], x["Id"]))
        for r in rows:
            zh, _ = nm.get(f"{r['Id']}_name", ("", ""))
            f = field.get(r["FieldMonsterId"], {})
            prefab, grade, size, ui, gen, nsk, _ = mon_info(r["FieldMonsterId"])
            fam = [m for m in mons if str(m["Id"]).startswith(str(r["FieldMonsterId"]))]
            sk = set(f.get("FieldSkillId") or [])
            for m in fam:
                for sd in (m.get("SkillData") or []):
                    if sd.get("SkillId"):
                        sk.add(sd["SkillId"])
            xy = coord.get(r["Id"]) if r["ChapterMod"] == 0 else None
            blines.append("\t".join([
                f"第 {ch} 章", MOD[r["ChapterMod"]], str(r["Id"]),
                no_by_id.get(r["Id"], "—"), zh or "（无本地化名称）",
                prefab, str(r["FieldMonsterId"]), ui, grade, size, gen,
                str(r["MonsterStageLv"]), f"{r['StandardBattlePower']:,}", nsk,
                ",".join(str(s) for s in sorted(sk)),
                "无（复用 cityforest 通用背景）",
                c[FIELD_KEY[r["ChapterMod"]]],
                xy[0] if xy else "—", xy[1] if xy else "—", str(r["RewardId"]),
            ]))
    p2 = OUT / "02_章节与关卡" / "05_关底BOSS.tsv"
    p2.write_text("\n".join(blines) + "\n", encoding="utf-8-sig")
    print("->", p2.name, len(blines) - 4, "条")

    # ---------- 3. 每章关卡类别分布 ----------
    pl = ["# 每章关卡类别分布（普通 / 困难 / 剧情 分开统计）", "章\t模式\t类别\t关卡数"]
    for k in sorted(cnt_cat):
        pl.append(f"{k[0]}\t{k[1]}\t{k[2]}\t{cnt_cat[k]}")
    p3 = OUT / "02_章节与关卡" / "06_关卡类别分布.tsv"
    p3.write_text("\n".join(pl) + "\n", encoding="utf-8-sig")
    print("->", p3.name, len(pl) - 2, "行")

    for k in sorted(cnt_cat):
        print("   ", k, cnt_cat[k])
    return 0


if __name__ == "__main__":
    sys.exit(main())
