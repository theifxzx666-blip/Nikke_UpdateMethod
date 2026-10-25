# -*- coding: utf-8 -*-
"""重建 07_关卡莱彻：补中文名 / 图鉴描述、新增大地图莱彻清单、新增关底 BOSS（真实 Boss 而非 FieldMonster）。

链路（全部字段来自文件）：
  CampaignStageTable.FieldMonsterId → MonsterFieldTable → MonsterModelTable → MonsterTable
  MonsterTable.NameLocalkey / DescriptionLocalkey → Locale_Monster.lss（zh-CN）
  大地图莱彻：campaignmapmodelgroup_010/011.bundle 里的 GameObject/Mesh 名（型号标签）
  关底 BOSS：Locale_Monster 里 UiGrade=6 的暴君/异端者条目 + 本章剧情 CG
"""
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

SD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")
DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
BASE = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
DST = BASE / r"05_主线_47-48章\07_关卡莱彻"
ILL = BASE / r"05_主线_47-48章\05_图片资源\剧情插画"
LSS = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\文本\原始文本库_lss\Locale_Monster.lss")

GRADE_CN = {0: "无", 1: "无私级", 2: "仆从级", 3: "主宰级", 4: "领主级", 5: "暴君级", 6: "异端者", 7: "女王"}
ATTR_CN = {0: "无", 1: "全属性", 2: "金属", 3: "生物", 4: "能量", 5: "未知"}
# UiGrade 与 MonsterModelTable.Grade 是同一套 1~7 阶梯、只是两个字段，用同一套词，避免同页出现两种译名。
# 依据：把 MonsterTable 全表 2,204 行按 UiGrade 分组、再从 Locale_Monster 的 *_description
# 正文里抽「级别：X」，得到 1→无我(88) 2→从者(539)/仆人(80) 3→大师(821)/超越(23) 4→领主(311)
# 5→暴君(245) 6→异端者(61) 7→女王(6)，阶梯一致。图鉴正文那套译名另存在「图鉴级别」列。
GRADE_T_CN = dict(GRADE_CN)
SIZE_CN = {0: "无", 1: "小型", 2: "中型", 3: "大型", 4: "巨型"}
MOVE_CN = {0: "无", 1: "步行", 2: "飞行"}
GEN_CN = {0: "无", 1: "普通", 2: "暗物质"}
CAT_CN = {0: "普通关", 1: "普通关", 2: "精英关", 3: "EX 关", 4: "章末BOSS"}


def jl(n):
    return json.loads((SD / (n + ".json")).read_text(encoding="utf-8"))


def locale():
    con = sqlite3.connect(f"file:{LSS}?mode=ro", uri=True)
    d = dict(con.execute('select "Key","zh-CN" from Locale_Monster'))
    con.close()
    return d


def base_name(v):
    return re.sub(r"\s*\[[^\]]*\]$", "", v or "")


def main():
    loc = locale()
    models = {m["Id"]: m for m in jl("MonsterModelTable")}
    mons = jl("MonsterTable")
    fld = {f["Id"]: f for f in jl("MonsterFieldTable")}
    stages = jl("CampaignStageTable")

    # 型号表按 MonPrefab 建索引；FieldMonster 的 MonPrefab 常带 _sd_var 后缀
    by_prefab = defaultdict(list)
    for m in models.values():
        by_prefab[m["MonPrefab"]].append(m)

    def model_of(prefab):
        if prefab in by_prefab:
            return by_prefab[prefab][0]
        stripped = re.sub(r"_sd_var$|_var$|_sd$", "", prefab)
        return by_prefab.get(stripped, [None])[0]

    def names_of(mid):
        out = []
        for r in mons:
            if r.get("MonsterModelId") != mid:
                continue
            k = (r.get("NameLocalkey") or "").split(":", 1)[-1]
            v = base_name(loc.get(k, ""))
            if v and v not in out:
                out.append(v)
        return out

    print("== 421003 / 422001 名称 =", names_of(421003), names_of(422001))

    # ---------- 1. 关卡莱彻（战斗内 FieldMonsterId） ----------
    # per[fid] = {"n": {ch: 关数}, "cats": Counter}
    per = defaultdict(lambda: {"n": Counter(), "cats": Counter()})
    for r in stages:
        sid = str(r["Id"])
        if not sid.startswith(("6047", "7047", "8047", "6048", "7048", "8048")):
            continue
        ch = 47 if sid[2:4] == "47" else 48
        fid = r["FieldMonsterId"]
        per[fid]["n"][ch] += 1
        per[fid]["cats"][CAT_CN[r["StageCategory"]]] += 1

    def uigrade_of(mid):
        """按 MonsterModelId 收全部实体行的 UiGrade。
        x* 系型号在 MonsterTable 里只有 10 位实体 Id，用 8 位 FieldMonsterId 查不到，
        所以必须反查整个型号，不能只查那一条。"""
        c = Counter(r.get("UiGrade") for r in mons if r.get("MonsterModelId") == mid)
        c.pop(None, None)
        if not c:
            return "—", ""
        u, _ = c.most_common(1)[0]
        return GRADE_T_CN.get(u, str(u)), f"UiGrade {u}"

    def handle_of(mid):
        """图鉴口径：代码（阵营）/ 级别。来自 <Localkey>_description 正文，同一型号多阵营并存。"""
        codes, levels = [], []
        for r in mons:
            if r.get("MonsterModelId") != mid:
                continue
            k = (r.get("DescriptionLocalkey") or "").split(":", 1)[-1]
            v = re.sub(r"[\r\n]+", " ", loc.get(k, "") or "")
            for m in re.finditer(r"代码：([^\s级]+)", v):
                if m.group(1) not in codes:
                    codes.append(m.group(1))
            for m in re.finditer(r"级别：([^\s世]+)", v):
                if m.group(1) not in levels:
                    levels.append(m.group(1))
        return "/".join(levels), "/".join(codes)

    rows = []
    for fid, d in per.items():
        f = fld[fid]
        mdl = model_of(f["MonPrefab"])
        names = names_of(mdl["Id"]) if mdl else []
        ug, ug_raw = uigrade_of(mdl["Id"]) if mdl else ("—", "")
        lv, cd = handle_of(mdl["Id"]) if mdl else ("—", "—")
        rows.append({
            "fid": fid, "prefab": f["MonPrefab"],
            "zh": names[0] if names else "",
            "zh_all": "/".join(names),
            "n": sum(d["n"].values()), "n47": d["n"].get(47, 0), "n48": d["n"].get(48, 0),
            "cats": d["cats"],
            "boss": f["IsBoss"], "fp": f["FightingPower"],
            "attr": ATTR_CN.get(f["Attribute"], str(f["Attribute"])),
            "grade": GRADE_CN.get(mdl["Grade"], "?") if mdl else "?",
            "size": SIZE_CN.get(mdl["Size"], "?") if mdl else "?",
            "gen": GEN_CN.get(mdl["MonsterGeneration"], "?") if mdl else "?",
            "move": MOVE_CN.get(mdl["MoveType"], "?") if mdl else "?",
            "uigrade": ug, "uigrade_raw": ug_raw,
            "level": lv, "code": cd,
            "model": mdl["MonPrefab"] if mdl else "",
        })

    rows.sort(key=lambda x: (-x["n"], x["zh"]))
    print(f"== 关卡莱彻：{len(rows)} 种（去重后；47章 {sum(1 for r in rows if r['n47'])} 种 / "
          f"48章 {sum(1 for r in rows if r['n48'])} 种，两章都在 {sum(1 for r in rows if r['n47'] and r['n48'])} 种）")
    print(f"== 强度分级：{[(r['zh'], r['uigrade']) for r in rows]}")

    # ---------- 2. 大地图莱彻 ----------
    def scan(bundle):
        import UnityPy
        env = UnityPy.load(str(DEV / bundle))
        c = Counter()
        tag = re.compile(r"^([xemb][a-z]{2}\d{3})")
        for obj in env.objects:
            if obj.type.name not in ("GameObject", "Transform", "Mesh", "AnimationClip"):
                continue
            try:
                n = getattr(obj.read(), "m_Name", "") or ""
            except Exception:
                continue
            m = tag.match(n)
            if m:
                c[m.group(1)] += 1
        return c

    map_rows = []
    for ch, bundle in ((47, "campaignmapmodelgroup_010.bundle"), (48, "campaignmapmodelgroup_011.bundle")):
        for tag, n in sorted(scan(bundle).items()):
            mdl = model_of(tag)
            names = names_of(mdl["Id"]) if mdl else []
            map_rows.append({
                "ch": ch, "tag": tag, "n": n,
                "zh": names[0] if names else "",
                "grade": GRADE_CN.get(mdl["Grade"], "?") if mdl else "?",
                "size": SIZE_CN.get(mdl["Size"], "?") if mdl else "?",
                "attr": ATTR_CN.get(mdl["Attribute"], "?") if mdl else "?",
                "move": MOVE_CN.get(mdl["MoveType"], "?") if mdl else "?",
                "model": mdl["MonPrefab"] if mdl else "",
            })
    print(f"== 大地图莱彻：47章 {sum(1 for r in map_rows if r['ch']==47)} 种 / "
          f"48章 {sum(1 for r in map_rows if r['ch']==48)} 种")

    # ---------- 3. 关底 BOSS ----------
    # 本章剧情 CG 即 Boss 画面；名字取 Locale_Monster 里 UiGrade=6 的条目
    boss_src = []
    for mid, cg in ((451003, ["eventscene_chap_47_01.png"]),
                    (231004, ["eventscene_chap_48_01_1.png", "eventscene_chap_48_01_2.png"])):
        mdl = models[mid]
        boss_src.append((mid, mdl, names_of(mid), cg))

    # ---------- 输出 ----------
    DST.mkdir(parents=True, exist_ok=True)
    hdr = ("# 第 47/48 章关卡内出现的莱彻（Rapture）—— 按型号去重，一行一个型号\n"
           "# 中文名 = Locale_Monster 原表（键 <id>_name，去掉 [阵营] 后缀）；这是第 10 张本地化表，\n"
           "#          上一版只翻了设备 lsc/ 里的 9 张 Locale_*.dec，所以中文名整列为空。\n"
           "# 强度分级 = MonsterTable.UiGrade（按 MonsterModelId 收全部实体行取众数；\n"
           "#          x* 系型号只有 10 位实体 Id，用 8 位 FieldMonsterId 查不到，必须反查型号）。\n"
           "#          UiGrade 与 型号等级 是同一套 1~7 阶梯的两个不同字段，只有关底 BOSS 451003 不一致。\n"
           "# 型号等级 / 体量 = MonsterModelTable.Grade / Size。\n"
           "# 图鉴级别 = Locale_Monster 的 <Localkey>_description 正文「级别：X」。\n"
           "#          注意这是同一阶梯的另一套译名：无我 / 从者 / 大师 / 领主 / 暴君 / 异端者 / 女王；\n"
           "# 图鉴级别 / 图鉴代码 = Locale_Monster 的 <Localkey>_description 正文\n"
           "#          「代码：Z.E.U.S. 级别：仆人 世代：暗物质」；同一型号多阵营并存，所以是斜杠分隔。\n"
           "# 数据来源：CampaignStageTable → MonsterFieldTable → MonsterModelTable → MonsterTable\n"
           "中文名\t预制体\t型号表预制体\t47章关数\t48章关数\t合计关数\t关卡类别\t强度分级\tUiGrade原值\t型号等级/体量\t属性\t生成型\t移动\tBOSS\t战力\t图鉴级别\t图鉴代码\t名表同族名\tFieldMonsterId\t立绘文件\n")
    lines = [hdr]
    for r in rows:
        cats = " / ".join(f"{k}×{v}" for k, v in sorted(r["cats"].items(), key=lambda kv: -kv[1]))
        lines.append("\t".join([
            r["zh"] or "—", r["prefab"], r["model"] or "—",
            (str(r["n47"]) if r["n47"] else "—"), (str(r["n48"]) if r["n48"] else "—"), str(r["n"]), cats,
            r["uigrade"], r["uigrade_raw"] or "—",
            f"{r['grade']}/{r['size']}", r["attr"], r["gen"], r["move"],
            "是" if r["boss"] else "否", f"{r['fp']:,}",
            r["level"] or "—", r["code"] or "—", r["zh_all"] or "—",
            str(r["fid"]), (r["model"] + "_立绘.png") if r["model"] else "—",
        ]))
    (DST / "关卡莱彻_清单.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    hdr2 = ("# 第 47/48 章大地图上游荡的莱彻（不是战斗内的 FieldMonster）\n"
            "# 型号标签直接从 campaignmapmodelgroup_010/011.bundle 的 GameObject / Mesh 名读取\n"
            "# 出现次 = 该包内以该型号命名的对象个数\n"
            "章\t型号\t中文名\t出现次\t强度\t体量\t属性\t移动\t型号表预制体\n")
    lines2 = [hdr2]
    for r in map_rows:
        lines2.append("\t".join([f"{r['ch']}章", r["tag"], r["zh"] or "—", str(r["n"]),
                                 r["grade"], r["size"], r["attr"], r["move"], r["model"]]))
    (DST / "大地图莱彻_清单.tsv").write_text("\n".join(lines2) + "\n", encoding="utf-8-sig")

    bossdir = DST / "关底BOSS"
    bossdir.mkdir(exist_ok=True)
    import shutil
    info = []
    for mid, mdl, names, cgs in boss_src:
        ch = 47 if mid == 451003 else 48
        for i, cg in enumerate(cgs):
            src = ILL / ("47章" if ch == 47 else "48章") / cg
            if src.exists():
                dst = bossdir / f"{ch}章_{cg}"
                shutil.copy2(src, dst)
                info.append((ch, mid, mdl, names, dst.name, src.name))
    print("== 关底BOSS 拷贝:", [i[4] for i in info])

    with (DST / "关底BOSS_实测.tsv").open("w", encoding="utf-8-sig") as f:
        f.write("# 关底 BOSS 实体与本章剧情 CG 的对应\n"
                "# 注意：CampaignStageTable.FieldMonsterId 是大地图游荡怪，不是关底 BOSS 本体\n"
                "章\t关卡\tBOSS 中文名\t型号表预制体\t强度\t体量\t属性\t移动\tUiGrade\t图鉴同族名\tCG 文件\n")
        for ch, mid, mdl, names, dstname, srcname in info:
            ug = {r["UiGrade"] for r in mons if r.get("MonsterModelId") == mid}
            ug_txt = "/".join(GRADE_T_CN.get(u, str(u)) for u in sorted(ug)) or "—"
            f.write("\t".join([f"{ch}章", f"{ch}-36", names[0] if names else "—", mdl["MonPrefab"],
                               GRADE_CN.get(mdl["Grade"], "?"), SIZE_CN.get(mdl["Size"], "?"),
                               ATTR_CN.get(mdl["Attribute"], "?"), MOVE_CN.get(mdl["MoveType"], "?"),
                               ug_txt, "/".join(names), dstname]) + "\n")

    print("done")


if __name__ == "__main__":
    main()
