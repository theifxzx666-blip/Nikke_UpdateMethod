# -*- coding: utf-8 -*-
"""剧情三表合并导出（活动 + 番外）。

为什么需要这个脚本
------------------
剧情文本散在三张表里，且**没有任何一张能单独导全**：

    Locale_MainScenario   主线 d_main_* + 单章式活动 event_*
    Locale_SubScenario    多章式活动（ce003~ce00N 等）+ 支线 / 内容关 / 雪境
    Locale_SideStory      番外篇 s<N>_*

只读 Main 会整批漏掉「只存在于 Sub」的活动（历史事故：漏 46 个活动，含 ce009
PERSONA ON FRONTLINE 3,286 条对话）。本脚本强制双表合并。

用法
----
# ① 先体检（不落盘）：必须「不可归组 0 条」，否则停下来修正则
python merge_story.py --check

# ② 正式导出
python merge_story.py --out "D:\\…\\04_剧情文本"

# ③ 只导活动 / 只导番外
python merge_story.py --out OUT --only event
python merge_story.py --out OUT --only side

产物
----
<out>/活动剧情/<活动代号>/{简中,繁中,日文,英文,韩文}.txt
<out>/活动剧情/00_活动清单.tsv          活动 / 条目数 / Main 条 / Sub 条
<out>/活动剧情/00_全部活动_简中合集.txt
<out>/番外篇/<编号_篇名>/{五语}.txt
<out>/番外篇/00_番外清单.tsv
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_CACHE = os.environ.get(
    "NIKKE_DEC_CACHE", r"D:\Codex\临时\nikke_intl_20261029\dec_cache")
LANGS = [("zh-CN", "简中"), ("zh-TW", "繁中"), ("ja", "日文"),
         ("en", "英文"), ("ko", "韩文")]
KEY_COL = "Key"

# 活动代号：[A-Za-z0-9] —— 只写 [a-z0-9] 会漏掉 PascalCase 活动
# （实测 BunnyX777 1,289 条、BlueWaterIsland 26 条，共 1,315 条整批丢失）
ACT_RE = re.compile(r"^(?:event|d_contents)_([A-Za-z0-9]+)")
# 活动 key 的三类形态（chapter 段可为数字或缺省）
STAGE_RANK = {"prologue": 0, "intermission": 2, "epilogue": 3,
              "balloon": 4, "npctalk": 5, "mini": 6}
TRACK_RANK = {"e": 0, "s": 1}
TRACK_CN = {"e": "e 轨（方舟侧）", "s": "s 轨（联动角色侧）"}
STAGE_CN = {"prologue": "序章", "intermission": "幕间", "epilogue": "尾声",
            "balloon": "气泡对话", "npctalk": "NPC 对话", "mini": "迷你游戏 · 开场"}


def die(msg: str) -> "NoReturn":
    print(f"[FATAL] {msg}", file=sys.stderr)
    sys.exit(2)


def conn(cache: Path, name: str) -> sqlite3.Connection:
    p = cache / f"{name}.dec"
    if not p.exists():
        die(f"找不到 {p}")
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def natkey(k):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(k))]


def story_order(key):
    """(章, 阶段, 段…, 轨) 排序键。

    实测形态（以 ce009 为例）：
      event_<act>_<章>_<段>_<e|s>_<句>        正篇
      event_<act>_<章>_prologue_<句>          序章
      event_<act>_<章>_intermission_<段>_<e|s>_<句>
      event_<act>_<章>_epilogue_<句>
      event_<act>_balloon_<段>_<句>           气泡（无章）
      event_<act>_npctalk_<段>_<句>           NPC（无章）
      d_contents_<act>_mini_<段>_<句>         迷你游戏开场

    e / s 是两条并行时间轨，真实交错顺序记在场景脚本里（不在 locale 表），
    这里只能按「段 → e → s」排，并在正文里标出轨别。
    """
    parts = re.sub(r"^(?:event|d_contents)_", "", str(key)).split("_")
    if len(parts) < 3:
        return ([99, 0], [0])
    rest, head = parts[1:], parts[1]
    if head.isdigit():
        ch = int(head)
        rest = rest[1:]
        rank = STAGE_RANK.get(rest[0], 1) if rest else 1
        if rest and rest[0] in STAGE_RANK:
            rest = rest[1:]
    else:
        ch, rank = 99, STAGE_RANK.get(head, 1)
        rest = rest[1:]
    seg, tr = [], 0
    for t in rest:
        if t.isdigit():
            seg.append(int(t))
        elif t == "title":
            seg.append(-1)
            break
        elif t in TRACK_RANK:
            tr = TRACK_RANK[t]
            break
        else:
            seg.append(999)
            break
    return ([ch, rank] + seg, [tr])


def section_of(key: str) -> str:
    """正文分隔标题：章 · 段 · 轨；无归属返回空串。"""
    m = re.match(r"^(?:event|d_contents)_[A-Za-z0-9]+_(.*)$", str(key))
    if not m:
        return ""
    rest = m.group(1)
    mm = re.match(r"^(\d+)_(\w+?)_(e|s)_", rest)
    if mm and mm.group(2).isdigit():
        return (f"第 {mm.group(1)} 章 · 第 {mm.group(2)} 段 · "
                f"{TRACK_CN.get(mm.group(3), mm.group(3))}")
    mm = re.match(r"^(\d+)_(prologue|intermission|epilogue)_", rest)
    if mm:
        return f"第 {mm.group(1)} 章 · {STAGE_CN[mm.group(2)]}"
    mm = re.match(r"^(\w+?)_(\d+)_(e|s)_", rest)
    if mm and mm.group(1) in STAGE_CN:
        return f"{STAGE_CN[mm.group(1)]} {mm.group(2)} · {TRACK_CN.get(mm.group(3), '')}"
    mm = re.match(r"^(balloon|npctalk|mini)_(\d+)_", rest)
    if mm:
        return f"{STAGE_CN[mm.group(1)]} · 第 {int(mm.group(2))} 组"
    return ""


# ------------------------------------------------------------------ 体检
def collect(cache: Path, tables: list[tuple[str, str]]):
    rows, bad = [], []
    spelling: dict = defaultdict(Counter)   # 小写 -> {原始写法: 条数}
    for tbl, tag in tables:
        c = conn(cache, tbl)
        q = (f'select "{KEY_COL}","zh-CN","zh-TW","ja","en","ko" from "{tbl}" '
             f'where "{KEY_COL}" like \'event\\_%\' escape \'\\\' '
             f'or "{KEY_COL}" like \'d\\_contents\\_%\' escape \'\\\'')
        got = c.execute(q).fetchall()
        c.close()
        print(f"  {tbl}: event_* + d_contents_* = {len(got):,} 条")
        for r in got:
            m = ACT_RE.match(str(r[0]))
            if m:
                # 小写分组：Locale 里同一活动有 `BlueWaterIsland` 与 `bluewaterisland`
                # 两种写法（26 + 62 条），按原样分组会得到两个组，而 Windows 目录
                # 不分大小写 → 后写的覆盖先写的，静默丢一批（E-39）
                rows.append((tag, m.group(1).lower()) + tuple(r))
                spelling[m.group(1).lower()][m.group(1)] += 1
            else:
                bad.append((tbl, r[0]))
    return rows, bad, spelling


def check(cache: Path, tables) -> int:
    rows, bad, _sp = collect(cache, tables)
    acts = defaultdict(int)
    for r in rows:
        acts[r[1]] += 1
    print(f"\n可归组 {len(rows):,} 条 / 活动 {len(acts)} 个")
    if bad:
        lost = defaultdict(int)
        for _t, k in bad:
            m = ACT_RE.match(str(k))
            lost[m.group(1) if m else "?"] += 1
        print(f"[FAIL] 不可归组 {len(bad):,} 条，涉及 {len(lost)} 个代号：")
        for k, v in sorted(lost.items(), key=lambda x: -x[1]):
            print(f"   {k}\t{v} 条")
        print("  → 这些条目会被静默丢弃。先修 ACT_RE（常见原因：代号含大写/短横/点）。")
        return 1
    print("[OK] 不可归组 0 条，可以导出")
    return 0


# ------------------------------------------------------------------ 活动
def build_events(cache: Path, out: Path, tables) -> tuple[int, int]:
    rows, bad, spelling = collect(cache, tables)
    for k, v in sorted(spelling.items()):
        if len(v) > 1:
            print(f"  [WARN] 大小写撞车 {k}：{dict(v)} —— 已并为一个活动，"
                  f"目录名用 {v.most_common(1)[0][0]}")
    groups = defaultdict(list)
    for r in rows:
        groups[r[1]].append(r)

    d = out / "活动剧情"
    d.mkdir(parents=True, exist_ok=True)
    man = ["# 活动剧情清单（Main=Locale_MainScenario / Sub=Locale_SubScenario）",
           "# 只读 Main 会漏掉仅存在于 Sub 的活动；两表都必须开",
           "活动代号\t条目数\tMain条\tSub条"]
    allzh, total = [], 0

    for name in sorted(groups, key=lambda x: (-len(groups[x]), x)):
        disp = spelling[name].most_common(1)[0][0]      # 原始写法，做目录名
        rs = sorted(groups[name], key=lambda r: story_order(r[2]))
        total += len(rs)
        nmain = sum(1 for r in rs if r[0] == "Main")
        man.append(f"{disp}\t{len(rs)}\t{nmain}\t{len(rs) - nmain}")
        sub = d / disp
        sub.mkdir(exist_ok=True)
        for li, (_col, tag) in enumerate(LANGS):
            lines = [f"活动剧情 · {disp}（{tag}）",
                     f"来源：Locale_MainScenario {nmain} 条 + "
                     f"Locale_SubScenario {len(rs) - nmain} 条",
                     f"条目数：{len(rs)}", "=" * 72]
            cur = None
            for r in rs:
                v = r[li + 3]
                if v is None or str(v).strip() == "":
                    continue
                sec = section_of(r[2])
                if sec and sec != cur:
                    cur = sec
                    lines += ["", f"── {sec} " + "─" * max(4, 56 - len(sec)), ""]
                lines += [f"[{r[2]}]", str(v).replace("\r\n", "\n"), ""]
            (sub / f"{tag}.txt").write_text("\n".join(lines), encoding="utf-8-sig")
            if tag == "简中":
                allzh.append(f"\n{'=' * 72}\n活动：{disp}（{len(rs)} 条）\n{'=' * 72}")
                allzh.extend(lines[4:])

    (d / "00_活动清单.tsv").write_text("\n".join(man) + "\n", encoding="utf-8-sig")
    (d / "00_全部活动_简中合集.txt").write_text("\n".join(allzh), encoding="utf-8-sig")
    print(f"  -> 活动 {len(groups)} 个 / 条目 {total:,}")
    return len(groups), total


# ------------------------------------------------------------------ 番外
def build_side(cache: Path, out: Path, side_tbl: str, stage_tbl: str) -> int:
    """番外篇。篇名不在 Locale_SideStory 里，要从 Locale_Stage 反查。"""
    names = {}
    try:
        c = conn(cache, stage_tbl)
        for k, v in c.execute(
                f'select "{KEY_COL}","zh-CN" from "{stage_tbl}" '
                f'where upper("{KEY_COL}") like \'SIDESTORY\\_%\' escape \'\\\''):
            m = re.match(r"^SIDESTORY_(\d+)_STAGE_(\d+)$", str(k), re.I)
            if m and v:
                nm = re.sub(r"\s*-\s*\d+\s*$", "", str(v)).strip()
                if nm:
                    names.setdefault(int(m.group(1)), nm)
        c.close()
    except SystemExit:
        raise
    except Exception as e:                              # noqa: BLE001
        print(f"  [WARN] 篇名反查失败（篇名将退化为编号）：{e}")

    c = conn(cache, side_tbl)
    rows = c.execute(
        f'select "{KEY_COL}","zh-CN","zh-TW","ja","en","ko" from "{side_tbl}" '
        f'where lower("{KEY_COL}") like \'s%\' '
        f'or lower("{KEY_COL}") like \'m\\_s%\' escape \'\\\'').fetchall()
    c.close()

    groups = defaultdict(list)
    for r in rows:
        # 实测两种键：s<N>_…（常规）与 m_s<N>_…（番外 4 的第 06~10 段，97 条）
        # 只写 ^s(\d+)_ 会把 m_s004_* 整批丢掉
        m = re.match(r"^(?:m_)?s(\d+)_", str(r[0]), re.I)
        if m:
            groups[int(m.group(1))].append(r)
        else:
            print(f"  [WARN] 番外表无法归组：{r[0]}")
    if not groups:
        print("  (番外表无 s<N>_ 形态条目，跳过)")
        return 0

    d = out / "番外篇"
    d.mkdir(parents=True, exist_ok=True)
    man = ["# 番外篇清单（Locale_SideStory；篇名反查自 Locale_Stage）",
           "编号\t篇名\t条目数\t目录名"]
    for n in sorted(groups):
        nm = names.get(n, "")
        dirn = f"{n:03d}_{nm}" if nm else f"{n:03d}"
        man.append(f"{n}\t{nm}\t{len(groups[n])}\t{dirn}")
        sub = d / dirn
        sub.mkdir(exist_ok=True)
        rs = sorted(groups[n], key=lambda r: natkey(r[0]))
        for li, (_col, tag) in enumerate(LANGS):
            lines = [f"番外篇 · {nm or n}（{tag}）",
                     f"条目数：{len(rs)}", "=" * 72]
            for r in rs:
                v = r[li + 1]
                if v is None or str(v).strip() == "":
                    continue
                lines += [f"[{r[0]}]", str(v).replace("\r\n", "\n"), ""]
            (sub / f"{tag}.txt").write_text("\n".join(lines), encoding="utf-8-sig")
    (d / "00_番外清单.tsv").write_text("\n".join(man) + "\n", encoding="utf-8-sig")
    print(f"  -> 番外 {len(groups)} 篇 / 条目 {sum(len(v) for v in groups.values()):,}")
    return len(groups)


def main() -> None:
    ap = argparse.ArgumentParser(description="剧情三表合并导出")
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="all", choices=["all", "event", "side"])
    ap.add_argument("--check", action="store_true", help="只体检不落盘")
    ap.add_argument("--main-table", default="Locale_MainScenario")
    ap.add_argument("--sub-table", default="Locale_SubScenario")
    ap.add_argument("--side-table", default="Locale_SideStory")
    ap.add_argument("--stage-table", default="Locale_Stage")
    a = ap.parse_args()

    cache = Path(a.cache)
    if not cache.is_dir():
        die(f"缓存目录不存在：{cache}")
    tabs = [(a.main_table, "Main"), (a.sub_table, "Sub")]

    if a.check:
        sys.exit(check(cache, tabs))

    if not a.out:
        die("导出必须给 --out（或先跑 --check）")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    if a.only in ("all", "event"):
        n, t = build_events(cache, out, tabs)
        if n == 0:
            die("活动 0 个 —— 表名或 LIKE 写错了，不要交付空目录")
    if a.only in ("all", "side"):
        build_side(cache, out, a.side_table, a.stage_table)
    print(f"-> {out}")


if __name__ == "__main__":
    main()
