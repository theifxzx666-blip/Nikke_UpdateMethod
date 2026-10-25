# -*- coding: utf-8 -*-
"""把爆裂特写的解析产物归集到交付目录。

输入：out/cutscene_lw/（时序 / 分层 / 节点贴图 / 贴图）
输出：版本更新/03_历史/20260813_国际服/07_角色爆裂特写/
      每套一个目录：背景板 / 角色 / 特效图集 / 遮罩与卡片 / 通用复用 + 时序 + 分层图
"""
import csv
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path(r"D:\Codex\临时\nikke_intl_20261029\out\cutscene_lw")
DST = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\07_角色爆裂特写")
LOBBY = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
             r"\06_角色大厅站立动画\00_清单.tsv")
# 爆裂特写只有 3 个包（c870_00 / c871_00 / c872_00）—— 每个角色一份，
# 同一角色的多套时装共用。与大厅站立（每时装一份 bundle）不同。
SETS = ["c870_00", "c871_00", "c872_00"]
# 该角色的时装数（写进汇总表，说明「三套共用」）
COS_N = {"c870": 3, "c871": 3, "c872": 1}


def role_map():
    """从 06 的清单拿「资源ID → (角色, 时装, 目录名)」。"""
    m = {}
    if not LOBBY.exists():
        return m
    with LOBBY.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            cid = r["资源ID"]
            m[cid] = (r["角色"], r["时装"], r["目录"])
    return m


def cutscene_cover(cid):
    """爆裂特写的角色图集（Spine 图集整张），用作封面。"""
    d = SRC / f"{cid.split('_')[0]}_贴图"
    for cand in (f"{cid}_skillcut.png", f"{cid.replace('_00','')}_skillcut_00.png",
                 f"{cid.split('_')[0]}_00_skillcut.png"):
        p = d / cand
        if p.exists():
            return p
    # 兜底：同前缀的任意 skillcut
    hits = sorted(d.glob("*skillcut*.png"))
    return hits[0] if hits else None


def classify(name, bg_tex, black_tex, cid_prefix, cid):
    """按贴图名判断归属。返回 (类别, 子目录)。"""
    n = name.lower()
    if name in bg_tex:
        return "背景板", "01_背景板"
    if name in black_tex:
        return "黑底", "01_背景板"
    if "skillcut" in n:
        return "角色图集", ""
    if cid_prefix in n or cid.replace("_00", "") in n:
        if "dis" in n or "dissolve" in n:
            return "溶解图", "02_角色特效"
        if "mask" in n:
            return "遮罩", "03_遮罩与卡片"
        if "card" in n:
            return "爆裂卡片", "03_遮罩与卡片"
        return "角色特效图集", "02_角色特效"
    if "card" in n:
        return "爆裂卡片", "03_遮罩与卡片"
    if "mask" in n:
        return "遮罩", "03_遮罩与卡片"
    return "跨角色复用", "04_跨角色复用"


def main():
    rm = role_map()
    DST.mkdir(parents=True, exist_ok=True)
    rows = []

    for cid in SETS:
        pfx = cid.split("_")[0]                       # c870
        texdir = SRC / f"{pfx}_贴图"
        if not texdir.exists():
            print(f"!! {cid}: 缺 {texdir}")
            continue

        # 背景板 / 黑底贴图（由节点映射决定，不靠命名猜）
        bg_tex, black_tex = set(), set()
        mapf = SRC / f"{pfx}_节点贴图.tsv"
        if mapf.exists():
            for r in csv.DictReader(mapf.open(encoding="utf-8-sig"), delimiter="\t"):
                go, tex = r["GameObject"], r["贴图"]
                if not tex:
                    continue
                if go == "fx_bg" or go.startswith("fx_bg_0"):
                    # fx_bg_glow / fx_bg_ptc 是背景粒子，不算背景板本身
                    if go == "fx_bg" or re.fullmatch(r"fx_bg_\d+", go):
                        bg_tex.add(tex)
                if go == "black_bg":
                    black_tex.add(tex)

        role, cos, _ = rm.get(cid, ("?", "?", ""))
        folder = f"{role}_{pfx}"
        out = DST / folder
        for sub in ("01_背景板", "02_角色特效", "03_遮罩与卡片", "04_跨角色复用"):
            (out / sub).mkdir(parents=True, exist_ok=True)

        n_by = {}
        for p in sorted(texdir.glob("*.png")):
            name = p.stem
            cat, sub = classify(name, bg_tex, black_tex, pfx, cid)
            dst = (out / sub / f"{name}.png") if sub else (out / f"{name}.png")
            shutil.copy2(p, dst)
            im = Image.open(p)
            n_by[cat] = n_by.get(cat, 0) + 1
            rows.append([folder, cid, role, f"{COS_N.get(pfx,1)} 套时装共用", cat, name,
                         f"{im.size[0]}x{im.size[1]}",
                         f"{p.stat().st_size/1048576:.2f}",
                         dst.relative_to(DST).as_posix()])

        # 时序 / 分层 / 节点映射
        for src_name, dst_name in ((f"{pfx}_时序.tsv", "时序_原始.tsv"),
                                   (f"{pfx}_分层.tsv", "时序_分层.tsv"),
                                   (f"{pfx}_节点贴图.tsv", "节点贴图.tsv"),
                                   (f"{pfx}_分层.png", "分层时序.png")):
            s = SRC / src_name
            if s.exists():
                shutil.copy2(s, out / dst_name)
        # 分层图里的 cid 换成「角色_时装」
        png = out / "分层时序.png"
        if png.exists():
            im = Image.open(png)
            print(f"  {folder}: {n_by} 分层图 {im.size[0]}×{im.size[1]}")

        ok = sum(n_by.values())
        rows.append([folder, cid, role, f"{COS_N.get(pfx,1)} 套时装共用", "合计", str(ok), "", "", ""])

    # ---- 汇总表
    tsv = DST / "00_汇总.tsv"
    with tsv.open("w", encoding="utf-8-sig") as f:
        f.write("目录\t资源ID\t角色\t时装\t类别\t贴图名\t尺寸\tMB\t相对路径\n")
        for r in rows:
            f.write("\t".join(r) + "\n")

    # ---- 总览图：7 张背景板横排（回答「背景板长什么样」）
    tiles = []
    for cid in SETS:
        pfx = cid.split("_")[0]
        mapf = SRC / f"{pfx}_节点贴图.tsv"
        bg = None
        if mapf.exists():
            for r in csv.DictReader(mapf.open(encoding="utf-8-sig"), delimiter="\t"):
                _go = r["GameObject"]
                if (_go == "fx_bg" or re.fullmatch(r"fx_bg_\d+", _go)) and r["贴图"]:
                    cand = SRC / f"{pfx}_贴图" / f"{r['贴图']}.png"
                    if cand.exists():
                        bg = cand
                        break
        if bg is None:
            continue
        role, cos, _ = rm.get(cid, (cid, "", ""))
        tiles.append((Image.open(bg).convert("RGB"), f"{role} {cos}", bg.stem))

    if tiles:
        H, pad, lab = 300, 12, 42
        ws = [max(160, round(im.width * H / im.height)) for im, _, _ in tiles]
        W = sum(ws) + pad * (len(tiles) + 1)
        sheet = Image.new("RGB", (W, H + lab + pad * 2), (14, 17, 22))
        d = ImageDraw.Draw(sheet)
        try:
            f9 = ImageFont.truetype(r"C:/Windows/Fonts/msyh.ttc", 15)
        except Exception:
            f9 = ImageFont.load_default()
        x = pad
        for (im, label, tex), w in zip(tiles, ws):
            sheet.paste(im.resize((w, H), Image.LANCZOS), (x, pad))
            d.text((x + w // 2, pad + H + 6), label, font=f9,
                   fill=(214, 222, 233), anchor="ma")
            d.text((x + w // 2, pad + H + 24), tex[:34], font=f9,
                   fill=(120, 132, 150), anchor="ma")
            x += w + pad
        sheet.save(DST / "00_背景板一览.png")
        print(f"背景板一览 {sheet.size[0]}×{sheet.size[1]}")

    print(f"交付 {len(SETS)} 套 → {DST}")


if __name__ == "__main__":
    main()
