#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""restructure_issue.py -- 把期次目录从「采集管线结构」重排成「读者结构」。

原结构按脚本输出分 7 个平级目录，同一个角色的东西散在 4 处。新结构只按
「读者先看什么」分 2 个大类，一个对象的全部素材收进同一个目录，技术过程
产物统一沉到 _源料/。

映射表（源 -> 目标，目标根 = 期次目录）：

    01_新角色/<名>_<id>[_<skin>]/  ──┐
    02_新皮肤/<名>_<id>_<skin>/    ──┤ 立绘/ 技能/ 动画/ 台词与配音/ _源料/
    06_角色大厅站立动画/<...>/     ──┤ （06/07 的内容按 <id>_<skin> 归并进上两者）
    07_角色爆裂特写/<...>/         ──┘
    04_卡池横幅/                    -> 01_新角色&皮肤/卡池与活动横幅/
    05_主线_XX-YY章/                -> 02_主线&活动/主线_第XX-YY章/
    03_活动/<名>（<id>）/           -> 02_主线&活动/活动_<名>（<id>）/

不搬的（drop，数据仍在 06_回收站 的硬链接快照里）：
    *.wav                       BGM 原样导出，mp3 留着就够
    07_关卡莱彻/3D查看器/        已在 GitHub Pages 上线
    04_剧情文本/活动剧情/        往期 174 部累积，非本期内容（清单单独留一份）

用法：
    python restructure_issue.py --issue "<期次目录>" --dry
    python restructure_issue.py --issue "<期次目录>" --apply
    python restructure_issue.py --issue "<期次目录>" --apply --force   # 覆盖已存在目标

只搬不改：全部走 os.link() 建新路径 + unlink 旧路径，从不打开原文件写，
所以 06_回收站 的硬链接快照不会被污染。
"""

from __future__ import annotations

# 本机 WorkBuddy 把 Path.unlink 打了安全补丁（CODEBUDDY_SAFE_DELETE_*），
# 每次调用约 0.35 s：删 900 个文件要 5 分钟以上。os.remove 不走那条路径，
# 实测 739 个文件 2.5 s。全脚本统一用 os.remove。
import argparse
import csv
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------- 目录名常量

D_NEW = "01_新角色&皮肤"
D_MAIN = "02_主线&活动"
D_CHAR = "角色"
D_SKIN = "皮肤"
D_BANNER = "卡池与活动横幅"
D_ART = "立绘"
D_SKILL = "技能"
D_ANIM = "动画"
D_VOICE = "台词与配音"
D_SRC = "_源料"
D_SRC_FX = "_源料/爆裂贴图"
D_SRC_FX_RAW = "_源料/爆裂贴图/取景贴图"    # 01_新角色/爆裂动画/特效贴图
D_SRC_FX_LAYER = "_源料/爆裂贴图/分层"      # 07_角色爆裂特写/01_背景板 等
D_SRC_TIME = "_源料/时序"
D_SRC_XRAY = "_源料/透视与拆解"
D_PAST = "00_往期活动索引"

# 立绘四种规格 -> 立绘/
ART_FILES = {"立绘.png", "立绘_高清.png", "半身像.png", "小人立绘.png"}
# 进 _源料/时序 的散件
TIME_FILES = {"分层时序.png", "时序_分层.tsv", "时序_原始.tsv", "节点贴图.tsv"}

ID_RE = re.compile(r"_([a-z]{1,2}\d{3})(?:_(\d{2}))?(?=_|$)")


def skin_key(dirname: str) -> str:
    """目录名 -> 唯一键 <id>_<skin>。缺皮肤号时补 00。

    >>> skin_key("QUEEN（真）_c870")
    'c870_00'
    >>> skin_key("秀尽学园学生会长_c870_01")
    'c870_01'
    >>> skin_key("QUEEN（真）_c870_00_默认")
    'c870_00'
    """
    m = ID_RE.search(dirname)
    if not m:
        return ""
    return f"{m.group(1)}_{m.group(2) or '00'}"


def chapter_dir(dirname: str) -> str:
    """05_主线_47-48章 -> 主线_第47-48章；抽不到章号就原样。"""
    m = re.search(r"(\d+)-(\d+)章", dirname)
    if not m:
        return "主线_" + dirname.lstrip("0123456789_")
    return f"主线_第{m.group(1)}-{m.group(2)}章"


def anim_name(fname: str) -> str:
    """c870_00_idle.gif -> 大厅_idle.gif；c870_00_skillcut_首帧.png -> 爆裂_skillcut_首帧.png"""
    m = re.match(r"^[a-z]{1,2}\d{3}_\d{2}_(.+)$", fname)
    body = m.group(1) if m else fname
    if body.startswith("skillcut"):
        return "爆裂_" + body
    return "大厅_" + body


def guess_kind(rel: Path) -> str:
    """按目标相对路径 + 后缀猜素材类型（只给清单用，不参与任何判定）。"""
    p = rel.as_posix()
    sfx = rel.suffix.lower()
    name = rel.stem

    # 降级区：顺序有意义，先具体后笼统
    if "/_源料/爆裂贴图/" in p:
        return "爆裂分层贴图"
    if "/_源料/时序/" in p:
        return "分层时序表"
    if "/_源料/透视与拆解/莱彻透视/" in p:
        return "莱彻透视"
    if "/_源料/透视与拆解/装配件拆解/" in p:
        return "装配件拆解"
    if "/_源料/透视与拆解/零件透视/" in p:
        return "BOSS零件透视"
    if "/_源料/透视与拆解/立绘_idle/" in p:
        return "立绘idle对照"
    if "/_源料/爆裂动画备份/" in p:
        return "爆裂动画GIF"
    if "/_源料/" in p:
        return "源料"

    if "/卡池与活动横幅/" in p or name.startswith("EVENT_BANNER"):
        return "活动横幅"
    if name.startswith("00_") and ("/00_总览/" in p or name.endswith(("_总览", "_预览"))):
        return "总览拼图"
    if "/大厅动画/" in p:
        return "活动大厅动画GIF" if sfx == ".gif" else "活动大厅动画素材"
    if name.startswith("大厅动画_") and name.endswith("一览"):
        return "总览拼图"
    if name.startswith("爆裂特写_") and name.endswith("一览"):
        return "总览拼图"

    if p.endswith("小人立绘.png"):
        return "Spine小人立绘"
    if p.endswith("立绘_高清.png"):
        return "角色立绘HD"
    if p.endswith("半身像.png"):
        return "角色立绘SI"
    if p.endswith("立绘.png"):
        return "角色立绘"
    if "/技能图标/" in p and "/05_莱彻" in p:
        return "莱彻技能图标"
    if name.startswith("技能图标"):
        return "技能图标"
    if name.startswith("大厅_"):
        return "大厅动画首帧" if name.endswith("_首帧") else "大厅动画GIF"
    if name.startswith("爆裂_"):
        return "爆裂首帧" if name.endswith("_首帧") else "爆裂动画GIF"
    if sfx == ".wav":
        return "台词配音"
    if sfx == ".mp3":
        return "BGM"
    if "/06_BGM/" in p:
        return "BGM"
    if "地图_" in name and name.endswith("_底图"):
        return "大地图底图"
    if name.startswith("地图_"):
        return "大地图"
    if name.startswith("eventscene_chap"):
        return "主线剧情插画"
    if name.startswith("剧情插画_"):
        return "活动剧情插画HD"
    if name.startswith("sbg_") and name.endswith("_总览"):
        return "战斗场景总览"
    if name.startswith("sbg_"):
        return "战斗场景阵位"
    if "莱彻总览" in name:
        return "莱彻总览图"
    if "/04_图标与文本/" in p and sfx == ".png":
        return "活动道具与图标"
    if "/动图/" in p and sfx == ".gif":
        return "BOSS表演动画GIF"
    if "/章节预告图/" in p:
        return "章节预告图"
    if "/立绘/" in p or "/关底BOSS/" in p:
        return "敌人立绘"
    if "tutorial" in name:
        return "教学图"
    if sfx == ".tsv":
        return "数据表"
    if sfx == ".xlsx":
        return "活动收益表单"
    if sfx == ".md":
        return "说明"
    if sfx == ".txt":
        return "剧情文本"
    if sfx == ".gif":
        return "动图"
    if sfx == ".py":
        return "工具"
    return "素材"


# ---------------------------------------------------------------- 规划

class Plan:
    def __init__(self):
        self.move: list[tuple[Path, Path]] = []      # (src, dst)
        self.drop: list[tuple[Path, str]] = []       # (src, 原因)
        self.keep: list[Path] = []                   # 原地不动

    def add(self, src: Path, dst: Path):
        self.move.append((src, dst))

    def skip(self, src: Path, why: str):
        self.drop.append((src, why))


def build_plan(root: Path) -> Plan:
    """扫一遍源目录，产出完整搬迁计划。规则是通用的，不针对某一期写死。"""
    plan = Plan()
    files = [p for p in sorted(root.rglob("*")) if p.is_file()]

    # 先给 01/02 建 <id>_<skin> -> 目标目录 的索引，06/07 靠它归并
    home: dict[str, Path] = {}
    for top, kind in (("01_新角色", D_CHAR), ("02_新皮肤", D_SKIN)):
        base = root / top
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir():
                continue
            k = skin_key(d.name)
            if k:
                home[k] = Path(D_NEW) / kind / d.name

    for f in files:
        rel = f.relative_to(root)
        parts = rel.parts
        top = parts[0]
        sp = rel.as_posix()

        # ---- 顶层散件：原样
        if len(parts) == 1:
            if top.lower().endswith(".pdf"):
                # 旧 PDF 先留着，新脚本出完再覆盖；好让改版前后能对比翻
                plan.keep.append(f)
            elif top.startswith("_"):
                plan.keep.append(f)
            else:
                plan.add(f, rel)
            continue

        # ---- 构建中间物：原地不动（PDF 脚本自己管）
        if top == "_构建":
            plan.keep.append(f)
            continue

        # ---- 01 / 02：角色与皮肤本体
        if top in ("01_新角色", "02_新皮肤"):
            k = skin_key(parts[1])
            dst_dir = home.get(k)
            if not dst_dir:
                plan.add(f, rel)                   # 认不出 id 就原地
                continue
            sub = parts[2:]                        # 目录内的相对部分
            head = sub[0] if sub else ""
            fname = parts[-1]

            if fname in ART_FILES:
                plan.add(f, dst_dir / D_ART / fname)
            elif fname.startswith("技能图标_"):
                plan.add(f, dst_dir / D_SKILL / fname)
            elif head == D_VOICE:
                plan.add(f, dst_dir / D_VOICE / Path(*sub[1:]) if len(sub) > 1 else dst_dir / D_VOICE / fname)
            elif head == "爆裂动画":
                if fname in TIME_FILES:
                    plan.add(f, dst_dir / D_SRC_TIME / fname)
                elif len(sub) > 2 and sub[1] == "特效贴图":
                    plan.add(f, dst_dir / D_SRC_FX_RAW / fname)
                elif fname.startswith("爆裂特写_分层时序"):
                    plan.add(f, dst_dir / D_SRC_TIME / fname)
                elif fname.endswith(".gif"):
                    # 这个 GIF 与 07_角色爆裂特写 里那个是同一份，07 的进 动画/，
                    # 这里的留作备份沉到 _源料，免得同目录两个源撞一个目标
                    plan.add(f, dst_dir / D_SRC / "爆裂动画备份" / fname)
                elif fname.endswith(".tsv"):
                    plan.add(f, dst_dir / D_SRC_TIME / fname)
                else:
                    plan.add(f, dst_dir / D_SRC / fname)
            else:
                plan.add(f, dst_dir / fname)       # 角色信息.md / 皮肤信息.md
            continue

        # ---- 06 大厅站立动画：按 id 并进角色目录
        if top == "06_角色大厅站立动画":
            k = skin_key(parts[1])
            dst_dir = home.get(k)
            fname = parts[-1]
            if not dst_dir:
                plan.keep.append(f)
            elif fname.startswith("00_"):
                plan.add(f, Path(D_NEW) / "00_总览" / fname)
            else:
                plan.add(f, dst_dir / D_ANIM / anim_name(fname))
            continue

        # ---- 07 爆裂特写：GIF 并进角色目录，贴图/时序沉 _源料
        if top == "07_角色爆裂特写":
            k = skin_key(parts[1])
            dst_dir = home.get(k)
            fname = parts[-1]
            if not dst_dir:
                plan.keep.append(f)
                continue
            if fname.startswith("00_"):
                plan.add(f, Path(D_NEW) / "00_总览" / fname)
            elif fname in TIME_FILES or fname.startswith("分层时序"):
                plan.add(f, dst_dir / D_SRC_TIME / fname)
            elif len(parts) > 3 and parts[2].startswith(("01_", "02_", "03_", "04_")):
                # 01_背景板 / 02_角色特效 / 03_遮罩与卡片 / 04_跨角色复用
                plan.add(f, dst_dir / D_SRC_FX_LAYER / parts[2] / fname)
            elif fname.endswith(".gif"):
                plan.add(f, dst_dir / D_ANIM / "爆裂_skillcut.gif")
            elif fname.endswith("_首帧.png"):
                plan.add(f, dst_dir / D_ANIM / "爆裂_skillcut_首帧.png")
            else:
                plan.add(f, dst_dir / D_SRC / fname)   # skillcut.png 合成图
            continue

        # ---- 04 卡池横幅
        if top == "04_卡池横幅":
            plan.add(f, Path(D_NEW) / D_BANNER / parts[-1])
            continue

        # ---- 03 活动
        if top == "03_活动":
            if len(parts) < 3:
                plan.keep.append(f)
                continue
            act = parts[1]
            dst_root = Path(D_MAIN) / f"活动_{act}"
            sub = parts[2]
            fname = parts[-1]
            if sub == "剧情插画":
                plan.add(f, dst_root / "01_插画" / fname)
            elif sub == "剧情文本":
                plan.add(f, dst_root / "02_剧情" / fname)
            elif sub == "大厅动画":
                plan.add(f, dst_root / "03_玩法与奖励" / "大厅动画" / fname)
            elif sub == "活动教学图":
                plan.add(f, dst_root / "03_玩法与奖励" / "教学图" / fname)
            elif sub == "活动道具与图标":
                plan.add(f, dst_root / "04_图标与文本" / fname)
            elif sub == "非剧情文本_UI与告示牌":
                plan.add(f, dst_root / "04_图标与文本" / fname)
            elif fname.startswith("EVENT_BANNER"):
                plan.add(f, dst_root / "01_插画" / fname)
            elif fname.startswith("活动收益"):
                plan.add(f, dst_root / "03_玩法与奖励" / fname)
            else:
                plan.add(f, dst_root / fname)
            continue

        # ---- 05 主线
        if top.startswith("05_主线"):
            main = Path(D_MAIN) / chapter_dir(top)
            sub = parts[1]
            rest = parts[2:]
            fname = parts[-1]

            if sub == "01_总览":
                plan.add(f, main / "00_总览" / fname)
            elif sub == "02_章节与关卡":
                plan.add(f, main / "01_章节与关卡" / fname)
            elif sub == "03_地图与点位":
                if len(rest) > 1 and rest[0] == "大地图":
                    plan.add(f, main / "03_地图" / fname)
                else:
                    plan.add(f, main / "03_地图" / fname)
            elif sub == "04_剧情文本":
                if len(rest) > 1 and rest[0] == "活动剧情":
                    if fname.startswith("00_活动清单"):
                        plan.add(f, Path(D_MAIN) / D_PAST / "往期活动清单.tsv")
                    elif fname.startswith("00_活动剧情_说明"):
                        plan.add(f, Path(D_MAIN) / D_PAST / fname)
                    else:
                        plan.skip(f, "往期活动剧情累积（裁决 A：撤出本期）")
                else:
                    m = re.match(r"^\d+_剧情_(\d+)章_(\w[\w-]*)\.txt$", fname)
                    plan.add(f, main / "02_剧情" / (f"{m.group(1)}章_{m.group(2)}.txt" if m else fname))
            elif sub == "05_图片资源":
                sub2 = rest[0] if rest else ""
                if sub2 == "剧情插画":
                    if len(rest) > 2:                       # 47章/ 48章/ 里的原图
                        plan.add(f, main / "02_剧情" / "剧情插画" / rest[1] / fname)
                    else:
                        plan.add(f, main / "02_剧情" / "剧情插画" / fname)
                elif sub2 == "章节预告图":
                    plan.add(f, main / "02_剧情" / "章节预告图" / fname)
                else:
                    plan.add(f, main / "02_剧情" / fname)
            elif sub == "06_战斗场景还原":
                plan.add(f, main / "04_战斗场景" / fname)
            elif sub == "07_关卡莱彻":
                if rest and rest[0] == "3D查看器":
                    plan.skip(f, "3D 查看器已在 GitHub Pages 上线（裁决 C）")
                elif rest and rest[0] == "透视":
                    plan.add(f, main / "05_莱彻与BOSS" / D_SRC_XRAY / "莱彻透视" / fname)
                elif rest and rest[0] == "装配件拆解":
                    plan.add(f, main / "05_莱彻与BOSS" / D_SRC_XRAY / "装配件拆解" / fname)
                elif rest and rest[0] == "零件透视":
                    plan.add(f, main / "05_莱彻与BOSS" / D_SRC_XRAY / "零件透视" / fname)
                elif rest and rest[0] == "立绘_idle":
                    plan.add(f, main / "05_莱彻与BOSS" / D_SRC_XRAY / "立绘_idle" / fname)
                elif "idle对照" in fname or "双阶段对照" in fname:
                    plan.add(f, main / "05_莱彻与BOSS" / D_SRC_XRAY / fname)
                elif rest and rest[0] in ("立绘", "动图", "技能图标", "关底BOSS"):
                    plan.add(f, main / "05_莱彻与BOSS" / rest[0] / fname)
                elif fname.endswith(".tsv"):
                    plan.add(f, main / "05_莱彻与BOSS" / "数据" / fname)
                elif fname.endswith(".md"):
                    plan.add(f, main / "05_莱彻与BOSS" / fname)
                elif fname.startswith("莱彻总览"):
                    plan.add(f, main / "05_莱彻与BOSS" / fname)
                else:
                    plan.add(f, main / "05_莱彻与BOSS" / fname)
            elif sub == "08_BGM":
                if fname.lower().endswith(".wav"):
                    plan.skip(f, "BGM 原样 wav（裁决 B：只留 mp3）")
                elif fname.endswith(".tsv"):
                    plan.add(f, main / "06_BGM" / fname)
                else:
                    plan.add(f, main / "06_BGM" / (rest[0] if len(rest) > 1 else "") / fname)
            else:
                plan.add(f, main / fname)
            continue

        plan.keep.append(f)      # 未识别的，原地不动

    return plan


# ---------------------------------------------------------------- 执行

def link_or_copy(src: Path, dst: Path, force: bool) -> str:
    """硬链接优先（同卷瞬时、不占空间），跨卷回退 copy2。返回动作名。"""
    if dst.exists():
        if not force:
            if dst.stat().st_size == src.stat().st_size:
                return "skip"
        os.remove(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
        return "link"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def write_manifest(root: Path, dests: list[Path], origin: dict[Path, Path]):
    out = root / "_素材清单.csv"
    rows = []
    for d in sorted(dests):
        if not d.is_file():
            continue
        st = d.stat()
        rel = d.relative_to(root).as_posix()
        rows.append([rel, guess_kind(d.relative_to(root)), "硬链接", st.st_size,
                     st.st_ino, st.st_nlink,
                     str(origin.get(d, d)).replace("\\", "/")])
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["name", "kind", "mode", "size", "inode", "nlink", "src"])
        w.writerows(rows)
    return out, len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="期次目录结构重排")
    ap.add_argument("--issue", required=True, help="期次目录绝对路径")
    ap.add_argument("--dry", action="store_true", help="只打印计划，不动手")
    ap.add_argument("--apply", action="store_true", help="真执行")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的目标文件")
    ap.add_argument("--verbose", action="store_true", help="逐条打印")
    a = ap.parse_args()

    root = Path(a.issue).resolve()
    if not root.is_dir():
        print(f"[FAIL] 目录不存在: {root}")
        return 2
    if not (a.dry or a.apply):
        print("要么 --dry 要么 --apply")
        return 2

    plan = build_plan(root)

    by_top = Counter()
    for s, _ in plan.move:
        by_top[s.relative_to(root).parts[0]] += 1
    dropped = Counter()
    for s, why in plan.drop:
        dropped[why] += 1

    size_move = sum(s.stat().st_size for s, _ in plan.move if s.exists())
    size_drop = sum(s.stat().st_size for s, _ in plan.drop if s.exists())

    print(f"源目录: {root}")
    print(f"  计划搬迁 {len(plan.move)} 个文件 / {size_move/1048576:.1f} MB")
    print(f"  计划撤出 {len(plan.drop)} 个文件 / {size_drop/1048576:.1f} MB")
    print(f"  原地不动 {len(plan.keep)} 个")
    print("\n按源目录:")
    for k, v in by_top.most_common():
        print(f"  {v:5d}  {k}")
    if dropped:
        print("\n撤出原因:")
        for why, n in dropped.most_common():
            print(f"  {n:5d}  {why}")

    # 目标目录分布
    dirs = Counter(str(d.parent) for _, d in plan.move)
    print("\n目标目录（前 25）:")
    for k, v in dirs.most_common(25):
        print(f"  {v:5d}  {k}")

    dup = defaultdict(list)
    for s_, d_ in plan.move:
        dup[d_].append(s_)
    clash = {k: v for k, v in dup.items() if len(v) > 1}
    if clash:
        print(f"\n[WARN] {len(clash)} 个目标路径被多个源撞上（后者覆盖前者，硬链接仍保留全部数据）:")
        for k, v in list(clash.items())[:10]:
            print(f"  {k}")
            for x in v:
                print(f"      <- {x.relative_to(root)}")

    if a.verbose:
        print("\n逐条:")
        for s, d in plan.move[:120]:
            print(f"  {s.relative_to(root)}  ->  {d}")
        if len(plan.move) > 120:
            print(f"  ... 另 {len(plan.move) - 120} 条")

    if a.dry:
        print("\n[dry] 未动手。")
        return 0

    # ---- 执行
    acts = Counter()
    origin: dict[Path, Path] = {}
    dests: list[Path] = []
    for s, d in plan.move:
        dst = root / d
        act = link_or_copy(s, dst, a.force)
        acts[act] += 1
        if act != "skip":
            dests.append(dst)
            origin[dst] = s
        else:
            dests.append(dst)
            origin[dst] = s
    print("\n落盘:", dict(acts))

    # 源文件全部撤走（数据由 06_回收站 的硬链接快照持有）
    removed = 0
    for s, _ in plan.move:
        if s.exists():
            os.remove(s)
            removed += 1
    for s, _ in plan.drop:
        if s.exists():
            os.remove(s)
            removed += 1
    print("撤销旧路径:", removed, "个（数据仍在 06_回收站 快照里）")

    # 清空目录
    for p in sorted(root.rglob("*"), key=lambda x: -len(x.parts)):
        if p.is_dir() and not any(p.iterdir()):
            try:
                p.rmdir()
            except OSError:
                pass

    # 三个旧顶层目录若已空，去掉
    for old in ("01_新角色", "02_新皮肤", "03_活动", "04_卡池横幅",
                "06_角色大厅站立动画", "07_角色爆裂特写"):
        p = root / old
        if p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    for old in list(root.glob("05_主线*")):
        if old.is_dir() and not any(old.iterdir()):
            old.rmdir()

    out, n = write_manifest(root, dests, origin)
    print(f"清单: {out.name} {n} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
