# -*- coding: utf-8 -*-
"""link_resources.py —— 按「唯一落盘裁决」用硬链接把 8-13 那期的资源归集到版更节点。

裁决（见 Prompt §5.2）：
  原文件唯一落盘在 00_资源库\\ 的类型目录；版更节点只放「分类视图」，
  用硬链接指过去（同盘 D:，不额外占空间，hash/ inode 一致）。

本脚本只做 os.link（硬链接），不做复制、不移动原文件。
输出 06_证据/06_硬链接清单.tsv：源路径 / 目标路径 / inode / nlink / 字节 / sha256前16
"""
import hashlib
import os
from pathlib import Path

RES = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库")
NODE = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
DRY = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点\_干跑_20261025")
EV = NODE / "06_证据"

CHARS = [("QUEEN（真）_c870", 870, ["00", "01", "02"]),
         ("雪子_c871", 871, ["00", "01", "02"])]

# 皮肤 5 件：cID -> [(序号, 中文名)]
SKINS = [
    (870, "01", "秀尽学园学生会长", "Shujin Academy Student Council President"),
    (870, "02", "女王睡衣", "Queen's Pajamas (Ver. NIKKE Collabo)"),
    (871, "01", "天城屋旅馆和服", "Amagi Inn Kimono"),
    (871, "02", "冬日雅居", "Winter Roomwear (Ver. NIKKE Collabo)"),
    (580, "01", "圣洁怪盗", "Saint Thief"),
]
CHAR_DIR = {870: "QUEEN（真）_c870", 871: "雪子_c871", 580: "潘托姆_c580"}

manifest = []
linked = existed = 0


def h16(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def link(src: Path, dst: Path, tag: str):
    global linked, existed
    if not src.exists():
        manifest.append([tag, str(src), str(dst), "-", "-", "-", "源缺失"])
        print(f"  ! 源缺失 {src}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if os.stat(dst).st_ino == os.stat(src).st_ino:
            existed += 1
            manifest.append([tag, str(src), str(dst),
                             str(os.stat(dst).st_ino), str(os.stat(dst).st_nlink),
                             str(dst.stat().st_size), h16(dst)])
            return
        manifest.append([tag, str(src), str(dst), "-", "-", "-",
                         "目标已存在且非同一 inode，跳过"])
        print(f"  ! 目标已存在（不同 inode）{dst}")
        return
    os.link(src, dst)
    st = os.stat(dst)
    linked += 1
    manifest.append([tag, str(src), str(dst), str(st.st_ino), str(st.st_nlink),
                     str(st.st_size), h16(dst)])


# ---------- 1. banner 12 张 ----------
ban = DRY / "06_预演数据" / "banner_260813"
for p in sorted(ban.glob("*.png")):
    link(p, NODE / "05_banner图" / p.name, "banner_全量")
    if p.name.startswith("EVENT_BANNER_TRAILMARKER_01"):
        link(p, NODE / "01_活动_PERSONA联动_ce009" / "banner" / p.name, "banner_活动")

# ---------- 2. 活动插画 8 张 ----------
ill = RES / "剧情插画" / "联动"
for p in sorted(ill.glob("PERSONA ON FRONTLINE（ce009）_*.png")):
    link(p, NODE / "01_活动_PERSONA联动_ce009" / "插画" / p.name, "活动插画")

# ---------- 3. 角色立绘（SD / HD / SD立绘 / SI） ----------
for dirname, cid, seqs in CHARS:
    for seq in seqs:
        sub = f"{dirname.rsplit('_c', 1)[0]}_c{cid}_{seq}"
        n = f"c{cid}_{seq}"
        # 立绘（icons-char-full(sd)）
        for p in (RES / "角色立绘" / sub).glob("*.png"):
            link(p, NODE / "02_新角色" / dirname / "立绘_SD" / p.name, "角色立绘SD")
        # 立绘 HD
        for p in (RES / "角色立绘HD" / sub).glob("*.png"):
            link(p, NODE / "02_新角色" / dirname / "立绘_HD" / p.name, "角色立绘HD")
        # SD 立绘（每个 skin 目录里都有同名共用纹理 ground.png / SDToon_Tex_RimDefault.png，
        # 直接落会撞名，故统一加 cID_序号 前缀）
        for p in (RES / "角色SD立绘" / sub).glob("*.png"):
            link(p, NODE / "02_新角色" / dirname / "SD立绘" / f"{n}__{p.name}", "角色SD立绘")
        # SI
        for p in (RES / "角色立绘SI").glob(f"si_{n}_*.png"):
            link(p, NODE / "02_新角色" / dirname / "SI" / p.name, "角色SI")

# ---------- 4. 皮肤 5 件（指 HD 立绘） ----------
for cid, seq, zh, en in SKINS:
    d = NODE / "03_新皮肤_5件" / f"{CHAR_DIR[cid]}_{seq}_{zh}"
    srcs = list((RES / "角色立绘HD" / f"{CHAR_DIR[cid]}_{seq}").glob("*.png"))
    srcs += list((RES / "角色立绘" / f"{CHAR_DIR[cid]}_{seq}").glob("*.png"))
    for p in srcs:
        prefix = "HD_" if "立绘HD" in str(p) else "SD_"
        link(p, d / (prefix + p.name), "皮肤立绘")

# ---------- 写清单 ----------
hdr = ["类别", "源路径", "目标路径", "inode", "nlink", "字节", "sha256_16"]
out = ["\t".join(hdr)] + ["\t".join(r) for r in manifest]
(EV / "06_硬链接清单.tsv").write_text("\n".join(out) + "\n", encoding="utf-8")

print(f"\n新建硬链接 {linked} 个，已存在同 inode {existed} 个，总条目 {len(manifest)}")
print("按类别：")
from collections import Counter
for k, v in Counter(r[0] for r in manifest).items():
    print(f"  {k:14s} {v}")
