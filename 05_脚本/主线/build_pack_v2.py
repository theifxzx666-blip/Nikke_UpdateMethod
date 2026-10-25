# -*- coding: utf-8 -*-
"""重建 2026-08-13 国际服版更包（玩家向）。

素材唯一落盘裁决：
  - 资源库已有立绘/半身像 → 硬链接（不占盘）
  - 本次新采/新渲染（高清插画、活动图、小人立绘） → 复制（唯一副本）
"""
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
RES = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库")
EXP = Path(r"D:\Codex\临时\nikke_intl_20261029\device\png")
SPINE_OUT = Path(r"D:\Codex\临时\spine_js\out")
BANNER = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点\_干跑_20261025\06_预演数据\banner_260813")
LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")

TAG = re.compile(r"<[^>]+>")

CHARS = [
    dict(cid="870", name="QUEEN（真）", en="Queen (Makoto)", ja="クイーン（真）", rare=3, burst=3,
         cv="佐藤利奈", sk=["18703", "28701", "28702"]),
    dict(cid="871", name="雪子", en="Yukiko", ja="雪子", rare=3, burst=3,
         cv="小清水亚美", sk=["18713", "28711", "28712"]),
    dict(cid="872", name="埃癸斯", en="Aigis", ja="アイギス", rare=2, burst=2,
         cv="坂本真绫", sk=["18723", "28721", "28722"]),
]

SKINS = [
    dict(code="870_01", owner="QUEEN（真）", name="秀尽学园学生会长",
         en="Shujin Academy Student Council President", how="活动获得"),
    dict(code="870_02", owner="QUEEN（真）", name="女王睡衣",
         en="Queen's Pajamas (Ver. NIKKE Collabo)", how="活动 PASS"),
    dict(code="871_01", owner="雪子", name="天城屋旅馆和服",
         en="Amagi Inn Kimono", how="活动获得"),
    dict(code="871_02", owner="雪子", name="冬日雅居",
         en="Winter Roomwear (Ver. NIKKE Collabo)", how="活动 PASS"),
    dict(code="580_01", owner="潘托姆", name="圣洁怪盗",
         en="Saint Thief", how="时装抽取"),
]

RARE = {1: "R", 2: "SR", 3: "SSR"}
BURST = {1: "I", 2: "II", 3: "III"}
ITEM_KIND = {
    "ce009_item_": "活动道具",
    "ce009_icn_buff_": "增益图标",
    "ce009_skill_icn_": "技能图标",
    "ce009_enemy_": "敌人立绘",
    "ele_ce009_tutorial_": "教学图",
}

manifest = []


def clean(s):
    return TAG.sub("", s or "").replace("\\n", " ").strip()


def ln(src: Path, dst: Path, kind: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
        st = dst.stat()
        manifest.append(dict(name=dst.relative_to(ROOT).as_posix(), kind=kind,
                             src=src.as_posix(), mode="硬链接",
                             inode=st.st_ino, nlink=st.st_nlink, size=st.st_size))
    except OSError as e:
        shutil.copy2(src, dst)
        st = dst.stat()
        manifest.append(dict(name=dst.relative_to(ROOT).as_posix(), kind=kind,
                             src=src.as_posix(), mode=f"复制({e.errno})",
                             inode=st.st_ino, nlink=st.st_nlink, size=st.st_size))


def cp(src: Path, dst: Path, kind: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    shutil.copy2(src, dst)
    st = dst.stat()
    manifest.append(dict(name=dst.relative_to(ROOT).as_posix(), kind=kind,
                         src=src.as_posix(), mode="复制", inode=st.st_ino,
                         nlink=st.st_nlink, size=st.st_size))


def char_dir_assets(code: str, sub: str, dest: Path):
    """code 形如 ``870_00``；sub 是资源库里的中文目录名。"""
    dest.mkdir(parents=True, exist_ok=True)
    hd = RES / "角色立绘HD" / sub / f"c{code}_uc_tex.png"
    sd = RES / "角色立绘" / sub / f"c{code}.png"
    si = RES / "角色立绘SI" / f"si_c{code}_s_uc_tex.png"
    pupp = SPINE_OUT / f"c{code}_idle.png"
    if hd.exists():
        ln(hd, dest / "立绘_高清.png", "角色立绘HD")
    if sd.exists():
        ln(sd, dest / "立绘.png", "角色立绘")
    if si.exists():
        ln(si, dest / "半身像.png", "角色立绘SI")
    if pupp.exists():
        cp(pupp, dest / "小人立绘.png", "Spine小人立绘")


def main():
    con_c = sqlite3.connect(f"file:{LSC / 'Locale_Character.dec'}?mode=ro", uri=True)
    con_k = sqlite3.connect(f"file:{LSC / 'Locale_Skill.dec'}?mode=ro", uri=True)
    con_s = sqlite3.connect(f"file:{LSC / 'Locale_CharacterCostume.dec'}?mode=ro", uri=True)

    def one(con, key):
        r = con.execute(f"select en,[zh-CN],ja from {con.execute('select name from sqlite_master').fetchone()[0]} where Key=?", (key,))
        return r.fetchone()

    # ---------- 01 新角色 ----------
    for c in CHARS:
        d = ROOT / "01_新角色" / f"{c['name']}_c{c['cid']}"
        char_dir_assets(f"{c['cid']}_00", f"{c['name']}_c{c['cid']}_00", d)
        desc = one(con_c, f"c{c['cid']}_description")
        skills = []
        for p in c["sk"]:
            n = one(con_k, f"{p}_name")
            ds = one(con_k, f"{p}_description")
            skills.append((clean(n[1] if n else ""), clean(n[0] if n else ""),
                           clean(ds[1] if ds else ""), clean(ds[0] if ds else "")))
        lines = [f"# {c['name']}（{c['en']}）  c{c['cid']}",
                 "",
                 f"- **稀有度**：{RARE[c['rare']]}",
                 f"- **爆裂阶段**：{BURST[c['burst']]}",
                 f"- **CV**：{c['cv']}",
                 f"- **日文名**：{c['ja']}",
                 ""]
        if desc:
            lines += ["## 角色简介（中文）", "", desc[1], "", "## 角色简介（英文）", "", desc[0], ""]
        lines += ["## 技能", "", "| 类型 | 中文名 | 英文名 |", "| :--- | :--- | :--- |"]
        for i, (zh, en, _, _) in enumerate(skills):
            lines.append(f"| {'大招' if i == 0 else f'技能 {i}'} | **{zh}** | {en} |")
        lines.append("")
        for i, (zh, en, dsz, dse) in enumerate(skills):
            lines += [f"### {'大招' if i == 0 else f'技能 {i}'} · {zh}", "", dsz or "（无描述）", ""]
        lines += ["## 素材", "",
                  "| 文件 | 说明 |", "| :--- | :--- |",
                  "| 立绘_高清.png | 1024×1024 图集页贴图，人物只占中间一块，不是最高清 |",
                  "| 立绘.png | 缩略立绘（约 280×450） |",
                  "| 半身像.png | 128×128 头像 |",
                  "| 小人立绘.png | Spine idle 首帧渲染，1800 高、透明底，分辨率最高 |", ""]
        (d / "角色信息.md").write_text("\n".join(lines), encoding="utf-8")

    # ---------- 02 新皮肤 ----------
    for s in SKINS:
        d = ROOT / "02_新皮肤" / f"{s['name']}_c{s['code']}"
        owner_dir = None
        for c in CHARS:
            if c["name"] == s["owner"]:
                owner_dir = f"{c['name']}_c{c['cid']}"
        base = owner_dir or f"{s['owner']}_c{s['code'].split('_')[0]}"
        char_dir_assets(s["code"], f"{base}_{s['code'].split('_')[1]}", d)
        lines = [f"# {s['name']}（{s['en']}）", "",
                 f"- **所属角色**：{s['owner']}",
                 f"- **皮肤编号**：c{s['code']}",
                 f"- **获取方式**：{s['how']}", "",
                 "## 素材", "",
                 "| 文件 | 说明 |", "| :--- | :--- |",
                 "| 立绘_高清.png | 1024×1024 图集页贴图，人物只占中间一块，不是最高清 |",
                 "| 立绘.png | 缩略立绘（约 280×450） |",
                 "| 半身像.png | 128×128 头像 |",
                 "| 小人立绘.png | Spine idle 首帧渲染，1800 高、透明底，分辨率最高 |", ""]
        (d / "皮肤信息.md").write_text("\n".join(lines), encoding="utf-8")

    # ---------- 03 活动 ----------
    act = ROOT / "03_活动" / "PERSONA ON FRONTLINE（ce009）"
    for p in sorted(EXP.glob("EventScene_ce009_*.png")):
        no = p.stem.replace("EventScene_ce009_", "").replace("_", "-")
        cp(p, act / "剧情插画" / f"剧情插画_{no}.png", "活动剧情插画HD")
    for p in sorted(EXP.glob("ce009_*.png")) + sorted(EXP.glob("ele_ce009_*.png")):
        kind = next((v for k, v in ITEM_KIND.items() if p.stem.startswith(k)), "活动图")
        sub = "活动教学图" if kind == "教学图" else "活动道具与图标"
        cp(p, act / sub / f"{p.stem}.png", kind)
    (act / "活动说明.md").write_text(
        "# PERSONA ON FRONTLINE（ce009）\n\n"
        "- **活动类型**：剧情活动（故事事件）\n"
        "- **联动对象**：Persona 系列（P3 / P4 / P5）\n"
        "- **关联主线**：击败第 49 章后解锁\n\n"
        "## 收录内容\n\n"
        "| 类别 | 数量 | 说明 |\n| :--- | :--- | :--- |\n"
        "| 剧情插画 | 8 | 2048×2048 高清，按剧情节点序号 |\n"
        "| 活动道具与图标 | 14 | 活动内道具、增益、技能图标 |\n"
        "| 活动教学图 | 8 | 活动玩法说明图，512×400 |\n", encoding="utf-8")

    # ---------- 04 卡池横幅 ----------
    for p in sorted(BANNER.glob("EVENT_BANNER_*.png")):
        if "TRAILMARKER" in p.name:
            continue
        ln(p, ROOT / "04_卡池横幅" / p.name, "活动横幅")

    # ---------- 05 主线预告 ----------
    for p in sorted(BANNER.glob("EVENT_BANNER_TRAILMARKER_01*.png")):
        ln(p, ROOT / "05_主线预告图" / p.name, "主线预告图")
    (ROOT / "05_主线预告图" / "说明.md").write_text(
        "# 主线预告图（TRAILMARKER_01）\n\n"
        "这两张图属于游戏内的「追迹标记」入口，用于**主线第 49 章开放预告**，"
        "不属于本期联名活动，因此单独存放。\n\n"
        "> 上一版误把它归进活动目录，已按内容归位。\n", encoding="utf-8")

    print(f"素材条目 {len(manifest)}")
    import csv
    with (ROOT / "_素材清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "kind", "mode", "size", "inode", "nlink", "src"])
        w.writeheader()
        for m in manifest:
            w.writerow(m)
    return manifest


if __name__ == "__main__":
    m = main()
    from collections import Counter
    print(Counter(x["kind"] for x in m))
    print(Counter(x["mode"] for x in m))
