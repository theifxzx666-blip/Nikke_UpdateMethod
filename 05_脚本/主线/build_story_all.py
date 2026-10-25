# -*- coding: utf-8 -*-
"""全量剧情文本导出：活动剧情（Main + Sub 双表）+ 番外篇（SideStory）。

修正背景：
  旧版 build_event_story.py 只读 Locale_MainScenario，因此把「只存在
  Locale_SubScenario 里」的 46 个活动整批漏掉了 —— 其中就包括 ce009
  （PERSONA ON FRONTLINE，3,286 条对话）。本脚本改为双表合并。

数据源（全部来自设备 sa/152.8.7 的 saus 桶 raw，NKDB 加密，已解密缓存）：
  Locale_MainScenario  活动 key = event_<活动>_*
  Locale_SubScenario   活动 key = event_<活动>_*（另含 d_contents / d_subquest 等）
  Locale_SideStory     番外篇 key = s<编号>_<段>_<句|title>

产物：
  04_剧情文本/活动剧情/<活动>/{简中,繁中,日文,英文,韩文}.txt
  04_剧情文本/活动剧情/00_活动清单.tsv
  04_剧情文本/活动剧情/00_全部活动_简中合集.txt
  04_剧情文本/番外篇/<编号_篇名>/{...}.txt
  04_剧情文本/番外篇/00_番外清单.tsv
"""
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

CACHE = Path(r"D:\Codex\临时\nikke_intl_20261029\dec_cache")
OUT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\05_主线_47-48章\04_剧情文本")
LANGS = [("zh-CN", "简中"), ("zh-TW", "繁中"), ("ja", "日文"), ("en", "英文"), ("ko", "韩文")]
COLS = '"Key","zh-CN","zh-TW","ja","en","ko"'


def natkey(k):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(k))]


# 活动剧情的段落优先级：序章 → 正篇 → 幕间 → 尾声 → 气泡 → NPC → 内容
STAGE_RANK = {"prologue": 0, "intermission": 2, "epilogue": 3,
              "balloon": 4, "npctalk": 5, "mini": 6}
TRACK_RANK = {"e": 0, "s": 1}


def story_order(key):
    """把活动 key 拆成可读顺序：章 → 阶段 → 段 → 轨 → 句。

    实测 ce009 的形态：
      event_<act>_<章>_<段>_<e|s>_<句>      正篇，每章 6 段，e/s 两条并行轨
      event_<act>_<章>_prologue_<句>        序章
      event_<act>_<章>_intermission_<段>_<e|s>_<句>
      event_<act>_<章>_epilogue_<句>
      event_<act>_balloon_<段>_<句>         气泡对话（无章）
      event_<act>_npctalk_<段>_<句>         NPC 对话
      d_contents_<act>_mini_<段>_<句>       迷你游戏开场
    e / s 两条轨各自推进时间，真实交错顺序在场景脚本里（不在 locale 表），
    所以这里按「段 → e → s」排，并在正文用分隔行标出轨别。
    """
    k = str(key)
    body = re.sub(r"^(event|d_contents)_", "", k)
    parts = body.split("_")
    if len(parts) < 3:
        return ([99], [0])
    rest = parts[1:]
    head = rest[0]
    if head.isdigit():
        ch = int(head)
        rest = rest[1:]
        rank = STAGE_RANK.get(rest[0], 1) if rest else 1
        if rest and rest[0] in STAGE_RANK:
            rest = rest[1:]
    else:
        ch = 99                                  # 无章归属（balloon / npctalk / mini）
        rank = STAGE_RANK.get(head, 1)
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


def conn(name):
    return sqlite3.connect(f"file:{CACHE / (name + '.dec')}?mode=ro", uri=True)


# ---------------------------------------------------------------- 活动剧情
def build_events():
    rows = []          # (来源表, key, zh, tw, ja, en, ko)
    for tbl, src in [("Locale_MainScenario", "Main"), ("Locale_SubScenario", "Sub")]:
        con = conn(tbl)
        got = con.execute(
            f"select {COLS} from {tbl} where \"Key\" like 'event\\_%' escape '\\' "
            f"or \"Key\" like 'd\\_contents\\_%' escape '\\'"
        ).fetchall()
        con.close()
        print(f"  {tbl}: event_* + d_contents_* {len(got):,} 条")
        rows += [(src,) + tuple(r) for r in got]

    groups = defaultdict(list)      # 活动名（小写）-> [(src,key,...)]
    spelling = defaultdict(Counter)  # 小写 -> {原始写法: 条数}
    for r in rows:
        # [A-Za-z0-9] 不能只写 [a-z0-9]：早期活动代号是 PascalCase
        # （BunnyX777 1289 条、BlueWaterIsland 26 条），小写正则会整批漏掉
        m = re.match(r"^(?:event|d_contents)_([A-Za-z0-9]+)", str(r[1]))
        if not m:
            continue
        # 分组键用小写：Locale 里同一活动存在 `BlueWaterIsland` 与 `bluewaterisland`
        # 两种写法（26 + 62 条），按原样分组会得到两个组，而 Windows 目录不分
        # 大小写 → 后写的把先写的覆盖掉，静默丢一批（E-39）
        groups[m.group(1).lower()].append(r)
        spelling[m.group(1).lower()][m.group(1)] += 1
    print(f"  合并后活动 {len(groups)} 个")
    for k, v in spelling.items():
        if len(v) > 1:
            print(f"  [WARN] 大小写撞车 {k}：{dict(v)} —— 已按小写并为一个活动，"
                  f"目录名用 {v.most_common(1)[0][0]}")

    d = OUT / "活动剧情"
    d.mkdir(parents=True, exist_ok=True)
    manifest = ["# 活动剧情清单（Main = Locale_MainScenario，Sub = Locale_SubScenario）",
                "# 旧版只取 Main，漏掉 46 个只存在于 Sub 的活动（含 ce009）",
                "活动名\t条目数\tMain条目\tSub条目\t目录名"]
    allzh, total = [], 0
    def section_of(key):
        """返回 (分隔标题, 是否换段)。用于在正文里标出「章 / 段 / 轨」。"""
        k = str(key)
        m = re.match(r"^(?:event|d_contents)_([A-Za-z0-9]+)_(.*)$", k)
        if not m:
            return "", False
        rest = m.group(2)
        mm = re.match(r"^(\d+)_(\w+?)_(e|s)_", rest)
        if mm:
            return f"第 {mm.group(1)} 章 · 第 {mm.group(2)} 段 · {'e 轨（方舟侧）' if mm.group(3)=='e' else 's 轨（联动角色侧）'}", True
        mm = re.match(r"^(\d+)_(prologue|intermission|epilogue)_", rest)
        if mm:
            nm = {"prologue": "序章", "intermission": "幕间", "epilogue": "尾声"}[mm.group(2)]
            return f"第 {mm.group(1)} 章 · {nm}", True
        mm = re.match(r"^(\w+?)_(\d+)_(e|s)_", rest)
        if mm and mm.group(1) in ("prologue", "intermission", "epilogue", "balloon", "npctalk"):
            nm = {"prologue": "序章", "intermission": "幕间", "epilogue": "尾声",
                  "balloon": "气泡对话", "npctalk": "NPC 对话"}[mm.group(1)]
            return f"{nm} {mm.group(2)} · {'e 轨' if mm.group(3)=='e' else 's 轨'}", True
        mm = re.match(r"^(balloon|npctalk|mini)_(\d+)_", rest)
        if mm:
            nm = {"balloon": "气泡对话", "npctalk": "NPC 对话",
                  "mini": "迷你游戏 · 开场"}[mm.group(1)]
            return f"{nm} · 第 {int(mm.group(2))} 组", True
        return "", False

    for name in sorted(groups, key=lambda x: -len(groups[x])):
        disp = spelling[name].most_common(1)[0][0]      # 原始写法，做目录名
        rs = sorted(groups[name], key=lambda r: story_order(r[1]))
        total += len(rs)
        nmain = sum(1 for r in rs if r[0] == "Main")
        nsub = len(rs) - nmain
        manifest.append(f"{disp}\t{len(rs)}\t{nmain}\t{nsub}\t{disp}")
        sub = d / disp
        sub.mkdir(exist_ok=True)
        for li, (_, tag) in enumerate(LANGS):
            lines = [f"活动剧情 · {disp}（{tag}）",
                     f"来源：Locale_MainScenario {nmain} 条 + Locale_SubScenario {nsub} 条",
                     f"条目数：{len(rs)}",
                     "=" * 72]
            cur = None
            for r in rs:
                v = r[li + 2]
                if v is None or str(v).strip() == "":
                    continue
                sec, _ = section_of(r[1])
                if sec and sec != cur:
                    cur = sec
                    lines += ["", "── " + sec + " " + "─" * max(4, 56 - len(sec)), ""]
                lines.append(f"[{r[1]}]")
                lines.append(str(v).replace("\r\n", "\n"))
                lines.append("")
            (sub / f"{tag}.txt").write_text("\n".join(lines), encoding="utf-8-sig")
            if tag == "简中":
                allzh.append(f"\n{'='*72}\n活动：{disp}（{len(rs)} 条）\n{'='*72}")
                allzh.extend(lines[4:])

    (d / "00_活动清单.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8-sig")
    (d / "00_全部活动_简中合集.txt").write_text("\n".join(allzh), encoding="utf-8-sig")
    print(f"  -> 活动 {len(groups)} 个 / 条目 {total:,}")


# ---------------------------------------------------------------- 番外篇
def build_sidestory():
    # 篇名不在 Locale_SideStory 里（那里只有段落标题），而在 Locale_Stage 的
    # SIDESTORY_<n>_STAGE_<m> 条目，形如「GINGERBREAD HOUSE-14」，去掉 -数字 后缀即篇名。
    names = {}
    try:
        con = conn("Locale_Stage")
        for k, v in con.execute(
                'select "Key","zh-CN" from Locale_Stage where upper("Key") like \'SIDESTORY\\_%\' escape \'\\\''):
            m = re.match(r"^SIDESTORY_(\d+)_STAGE_(\d+)$", str(k), re.I)
            if m and v:
                nm = re.sub(r"\s*-\s*\d+\s*$", "", str(v)).strip()
                if nm:
                    names.setdefault(int(m.group(1)), nm)
        con.close()
    except Exception as e:
        print("  篇名读取失败：", e)
    print(f"  篇名 {len(names)} 个：{names}")

    con = conn("Locale_SideStory")
    rows = con.execute(f"select {COLS} from Locale_SideStory").fetchall()
    con.close()
    print(f"  Locale_SideStory: {len(rows):,} 条")

    g = defaultdict(list)
    other = []
    for r in rows:
        # 两种键：s<N>_<段>_<句|title> 与 m_s<N>_<段>_<句>（番外 4 的第 06~10 段，97 条）。
        # 只写 ^s(\d+)_ 会把 m_s004_* 整批丢进「未归组」
        m = re.match(r"^(?:m_)?s(\d+)_(\d+)_(.+)$", str(r[0]))
        if m:
            g[int(m.group(1))].append(r)
        else:
            other.append(r)
    print(f"  番外 {len(g)} 篇")

    d = OUT / "番外篇"
    d.mkdir(parents=True, exist_ok=True)
    manifest = ["# 番外篇清单（Locale_SideStory，key = s<编号>_<段>_<句|title>）",
                "# 数据源：设备 sa/152.8.7 · saus 桶 · Locale_SideStory.lsc（3,096,270 B）",
                "编号\t篇名（简中）\t段数\t条目数\t目录名"]
    for sid in sorted(g):
        rs = sorted(g[sid], key=lambda r: natkey(r[0]))
        title = names.get(sid) or "篇名待定"
        # 段数 = title 条数（每段一条 _title）
        nseg = sum(1 for r in rs if str(r[0]).endswith("_title"))
        safe = re.sub(r'[\\/:*?"<>|\s]+', "_", title).strip("_")[:40]
        folder = f"s{sid:03d}_{safe}"
        manifest.append(f"s{sid:03d}\t{title}\t{nseg}\t{len(rs)}\t{folder}")
        sub = d / folder
        sub.mkdir(exist_ok=True)
        for li, (_, tag) in enumerate(LANGS):
            lines = [f"番外篇 {sid} · {title}（{tag}）",
                     "来源：Locale_SideStory，Key = s%03d_*" % sid,
                     f"条目数：{len(rs)}",
                     "=" * 72]
            for r in rs:
                v = r[li + 1]
                if v is None or str(v).strip() == "":
                    continue
                lines.append(f"[{r[0]}]")
                lines.append(str(v).replace("\r\n", "\n"))
                lines.append("")
            (sub / f"{tag}.txt").write_text("\n".join(lines), encoding="utf-8-sig")

    if other:
        sub = d / "_未归组"
        sub.mkdir(exist_ok=True)
        lines = ["番外篇 · 未能按 s<编号>_<段> 归组的条目", f"条目数：{len(other)}", "=" * 72]
        for r in sorted(other, key=lambda r: natkey(r[0])):
            if r[1] and str(r[1]).strip():
                lines += [f"[{r[0]}]", str(r[1]).replace("\r\n", "\n"), ""]
        (sub / "简中.txt").write_text("\n".join(lines), encoding="utf-8-sig")
        print(f"  未归组 {len(other)} 条")

    (d / "00_番外清单.tsv").write_text("\n".join(manifest) + "\n", encoding="utf-8-sig")
    print(f"  -> 番外 {len(g)} 篇 / 条目 {sum(len(v) for v in g.values()):,}")


if __name__ == "__main__":
    print("[活动剧情]")
    build_events()
    # 番外篇默认不导：本期已判定「Locale_SideStory 那 6 篇不是 8-13 当期内容」
    # （见 00_本期概览.md 十五修第 3 节），产物已移入 拆包/05_回收站。
    # 重跑本脚本会把它重新写回 04_剧情文本/番外篇/，记得再移出去。
    # 需要时显式开：WITH_SIDE=1 python build_story_all.py
    if os.environ.get("WITH_SIDE") == "1":
        print("[番外篇]")
        build_sidestory()
    else:
        print("[番外篇] 跳过（WITH_SIDE=1 才导，本期口径不含番外）")
    print("->", OUT)
