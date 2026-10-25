# -*- coding: utf-8 -*-
"""47/48 章关卡内出现的莱彻（Rapture）：立绘 + 强度分级 + 技能（图标 + 描述）。

链路（全部字段来自文件，不写死）：
  CampaignStageTable.FieldMonsterId
    → MonsterFieldTable（35 条，直接命中：预制体 / 属性 / Boss / 战力 / 场地技能）
    → MonsterTable（8 位 FieldMonsterId 与 10 位实体 Id 前缀匹配 → 同族 5~7 条）
         → MonsterModelTable（按 MonPrefab：Grade / Size / Attribute / MoveType）
         → MonsterSkillTable（SkillData[].SkillId）
    → Locale_*.dec（zh-CN / en 文本）
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

SD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")
LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")
DST = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\05_主线_47-48章\07_关卡莱彻")
ART = Path(r"D:\Codex\临时\nikke_intl_20261029\out\monster_standee")
ICON_DIR = [Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\UI图标HD\icons-monster_full(hd)"),
            Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\UI图标HD\icons-monster(hd)"),
            Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\技能资源\技能图标")]

GRADE_CN = {0: "无", 1: "无私级", 2: "仆从级", 3: "主宰级", 4: "领主级",
            5: "暴君级", 6: "异端者", 7: "女王"}
GRADE_EN = {0: "None", 1: "Selfless", 2: "Servant", 3: "Master", 4: "Lord",
            5: "Tyrant", 6: "Heretic", 7: "Queen"}
ATTR_CN = {0: "无", 1: "全属性", 2: "金属", 3: "生物", 4: "能量", 5: "未知"}
GRADE_T_CN = {0: "无", 1: "杂兵", 2: "爪牙", 3: "精英", 4: "百夫长", 5: "首领"}
SIZE_CN = {0: "无", 1: "小型", 2: "中型", 3: "大型", 4: "巨型"}
MOVE_CN = {0: "无", 1: "步行", 2: "飞行"}
GEN_CN = {0: "无", 1: "普通", 2: "暗物质"}

# 关卡类别：CampaignStageTable.StageCategory
CAT_CN = {0: "普通关", 1: "普通关", 2: "精英关", 3: "EX 关", 4: "章末BOSS"}


def jload(n):
    return json.loads((SD / n).read_text(encoding="utf-8"))


def build_locale():
    """把 9 张 Locale_*.dec 的 zh-CN / en 合并成 key → (zh, en)。"""
    m = {}
    for f in sorted(LSC.glob("Locale_*.dec")):
        con = sqlite3.connect(f"file:{f}?mode=ro", uri=True)
        t = [r[0] for r in con.execute("select name from sqlite_master where type='table'")][0]
        for k, zh, en in con.execute(f'select "Key","zh-CN","en" from "{t}"'):
            if k and (k not in m or (not m[k][0] and zh)):
                m[k] = (zh or "", en or "")
        con.close()
    return m


def text(loc, key):
    if not key:
        return "", ""
    k = key.split(":", 1)[-1] if ":" in key else key
    for cand in (key, k):
        if cand in loc:
            return loc[cand]
    return "", ""


def find_icon(name):
    """技能图标：先按 <SkillIcon>.png 精确找，再退一步模糊找。"""
    if not name:
        return None
    for d in ICON_DIR:
        if not d.exists():
            continue
        p = d / (name + ".png")
        if p.exists():
            return p
        hits = list(d.glob("*" + name + "*.png"))
        if len(hits) == 1:
            return hits[0]
    return None


def main():
    DST.mkdir(parents=True, exist_ok=True)
    stages = jload("CampaignStageTable.json")
    chapters = jload("CampaignChapterTable.json")
    field = {r["Id"]: r for r in jload("MonsterFieldTable.json")}
    mons = jload("MonsterTable.json")
    models = jload("MonsterModelTable.json")
    skills = {r["Id"]: r for r in jload("MonsterSkillTable.json")}
    loc = build_locale()
    print("locale 键", len(loc))

    chap_by_id = {c["Id"]: c["Chapter"] for c in chapters}
    target = {47, 48}

    # 1) 统计每个 FieldMonsterId 出现在哪些关、什么类别
    use = defaultdict(lambda: dict(stages=[], cats=Counter(), chapters=Counter()))
    for s in stages:
        ch = chap_by_id.get(s.get("ChapterId"))
        if ch not in target:
            continue
        fid = s.get("FieldMonsterId")
        if not fid:
            continue
        u = use[fid]
        u["stages"].append(s.get("Id"))
        u["cats"][s.get("StageCategory")] += 1
        u["chapters"][ch] += 1

    model_by_prefab = {}
    for r in models:
        model_by_prefab.setdefault(r["MonPrefab"], r)

    rows, skill_rows = [], []
    for fid in sorted(use, key=lambda x: -len(use[x]["stages"])):
        u = use[fid]
        f = field.get(fid)
        if not f:
            rows.append([str(fid), "—", "（MonsterFieldTable 无此 Id）"])
            continue
        prefab = f["MonPrefab"]
        fam = [m for m in mons if str(m["Id"]).startswith(str(fid))]
        grades = Counter(m["UiGrade"] for m in fam)
        ui = grades.most_common(1)[0][0] if grades else 0
        # MonsterModelTable 里没有 _sd_var 变体，退回基础预制体；再退回最长前缀匹配
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

        zh, en = text(loc, f.get("NameLocalkey"))
        dzh, _ = text(loc, f.get("DescriptionLocalkey"))
        # intl 客户端没有下发 Locale_Monster（9 张 Locale_*.dec + 设备 lss 缓存里都搜不到），
        # 所以怪物名与图鉴描述为空 —— 用「—」占位，不猜译名。
        zh = zh or "—"
        en = en or "—"
        dzh = (dzh or "—")

        # 技能：场地技能 + 所有实体的 SkillData
        sk_ids = list(f.get("FieldSkillId") or [])
        for m in fam:
            for sd in (m.get("SkillData") or []):
                sid = sd.get("SkillId") or 0
                if sid:
                    sk_ids.append(sid)
            if m.get("PassiveSkillId"):
                sk_ids.append(m["PassiveSkillId"])
        seen, sk_list = set(), []
        for sid in sk_ids:
            if sid in seen:
                continue
            seen.add(sid)
            sk_list.append(sid)

        for sid in sk_list:
            sr = skills.get(sid)
            if not sr:
                skill_rows.append([str(fid), prefab, zh, str(sid), "（MonsterSkillTable 无此 Id）",
                                   "", "", "", ""])
                continue
            sn, sen = text(loc, sr.get("NameLocalkey"))
            sd_, _ = text(loc, sr.get("DescriptionLocalkey"))
            icon = sr.get("SkillIcon") or ""
            ipp = find_icon(icon)
            skill_rows.append([str(fid), prefab, zh, str(sid), sn, sen,
                               icon, str(ipp.name) if ipp else "", sd_])
            if ipp:
                dst = DST / "技能图标" / (ipp.name)
                dst.parent.mkdir(exist_ok=True)
                if not dst.exists():
                    dst.write_bytes(ipp.read_bytes())

        art = ART / ("%s_立绘.png" % prefab.split("_")[0])
        rows.append([
            str(fid), prefab, zh, en,
            "+".join(str(c) for c in sorted(u["chapters"])),
            str(len(u["stages"])),
            " / ".join("%s×%d" % (CAT_CN.get(c, "类别%d" % c), n)
                       for c, n in sorted(u["cats"].items())),
            "是" if f.get("IsBoss") else "否",
            "{:,}".format(f.get("FightingPower") or 0),
            ATTR_CN.get(f.get("Attribute", 0), "?"),
            "%s / %s" % (GRADE_T_CN.get(mod["Grade"], "?") if mod else "?",
                         SIZE_CN.get(mod["Size"], "?") if mod else "?"),
            GEN_CN.get(mod["MonsterGeneration"], "?") if mod else "?",
            MOVE_CN.get(mod["MoveType"], "?") if mod else "?",
            "%s（%s）" % (GRADE_CN.get(ui, "?"), GRADE_EN.get(ui, "?")),
            str(len(fam)),
            str(len(sk_list)),
            mod_prefab,
            dzh.replace("\t", " ").replace("\n", " "),
            art.name if art.exists() else "",
        ])

    head = ["FieldMonsterId", "预制体", "中文名", "英文名", "出现章", "关卡数", "关卡类别",
            "BOSS", "战力", "属性", "型号/体量", "生成型", "移动", "强度分级",
            "同族实体数", "技能数", "型号表预制体", "图鉴描述", "立绘文件"]
    tsv = ["\t".join(head)] + ["\t".join(r) for r in rows]
    p1 = DST / "关卡莱彻_清单.tsv"
    p1.write_text("# 第 47/48 章关卡内出现的莱彻（Rapture）\n"
                  "# 强度分级 = MonsterTable.UiGrade（MonsterUIGradeType 枚举）\n"
                  "# 型号/体量 = MonsterModelTable.Grade / Size；生成型 = MonsterGeneration\n"
                  "# 数据来源：CampaignStageTable → MonsterFieldTable → MonsterTable → MonsterModelTable\n"
                  + "\n".join(tsv) + "\n", encoding="utf-8-sig")

    head2 = ["FieldMonsterId", "预制体", "敌人中文名", "技能Id", "技能名", "技能名(en)",
             "图标键", "图标文件", "技能描述"]
    tsv2 = ["\t".join(head2)] + ["\t".join(r) for r in skill_rows]
    p2 = DST / "关卡莱彻_技能.tsv"
    p2.write_text("# 莱彻技能（MonsterSkillTable + Locale_Skill）\n"
                  "# 技能来源：MonsterFieldTable.FieldSkillId（场地技能）+ MonsterTable.SkillData[].SkillId\n"
                  + "\n".join(tsv2) + "\n", encoding="utf-8-sig")

    # 立绘
    for r in rows:
        n = r[-1]
        if n and (ART / n).exists():
            dst = DST / "立绘" / n
            dst.parent.mkdir(exist_ok=True)
            if not dst.exists():
                dst.write_bytes((ART / n).read_bytes())

    print("->", p1, len(rows), "行")
    print("->", p2, len(skill_rows), "行")
    miss = [r for r in skill_rows if not r[7]]
    print("图标缺失", len(miss), "条：", sorted({(r[2], r[6]) for r in miss})[:12])


if __name__ == "__main__":
    sys.exit(main())
