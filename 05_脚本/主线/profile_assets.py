# -*- coding: utf-8 -*-
r"""profile_assets.py — 个人主页装饰资源：快照 / 与基线 diff

回答的问题
    「本期有没有新增个人主页称号 / 头像框 / 背景 / 贴纸？是哪个活动、哪个个突 BOSS 的？」

四张表的分工（别混）
    UserTitleTable          称号文字本体（250 行）· 图标全是 icn_usertitle_common，不携带独立图
    UserTitleAssemblyTable  装配称号（182 行）· 称号 + 角色半身像 si_cXXX_00_s（AssemblyType=3）
    UserFrameTable          头像框（326 行 / 236 个 ResourceId）· 个突框族 icn_soloraid_<Boss>_tier{n}_frame
    ProfileCardObjectTable  个人主页物件总表（654 行）· ObjectType 0=背景 / 1=贴纸，
                            SubType 3 = 称号 badge（166 行，ResourceId 是裸数字，名在 Locale_Profile:badge_<id>_name）

判新只认 Id 集合差
    * 头像框不能按 ResourceId diff：20011~20093 那 27 行「博物馆」复刻框复用 10011 起的同一个
      ResourceId（实测 326 行只有 236 个唯一值），按 ResourceId 差会漏。
    * 名片物件不能按行数 diff：一个物件占 1 行，但同一活动会一次上 4~6 个贴纸。
    * 称号可以按 Id 差，但**必须同时看 LocaleKey**：旧版基线只存了 Id，
      字段名取错导致 250 行 LocaleKey 全空（2026-10-26 已修，见 make_baseline_v2.build_names）。

用法
    # 打快照（换期次时用，输出结构与 00_基线_对象名 一致）
    python profile_assets.py --static <mpdump全量> --snapshot D:\...\_基线_20261112\00_基线_对象名

    # 与基线比
    python profile_assets.py --static <mpdump全量> --baseline <旧基线>\00_基线_对象名

    # 带中文名（可选，--text 指到解密后的 Locale_*.dec 所在目录）
    python profile_assets.py ... --text D:\Codex\临时\nikke_intl_20261029\device\lsc --lang zh-CN
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

DEFAULT_STATIC = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点"
                      r"\_基线_20261029\00_基线_静态表\_mpdump全量")
DEFAULT_BASE = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点"
                    r"\_基线_20261029\00_基线_对象名")

FRAME_FAMS = [
    (r"icn_soloraid_(.+?)_tier(\d)_frame", "个突"),
    (r"champion_arena_main_.*_tier(\d)_frame", "冠军竞技场"),
    (r"icn_ranking_frame_\d+", "排行"),
    (r"icn_vote_event_(\d+)", "人气投票"),
    (r"icn_ce(\d+)_event_frame", "活动(CE)"),
    (r"icn_side_story_frame", "番外篇"),
]


def load(d: Path, name: str):
    p = d / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def frame_fam(rid: str):
    for pat, tag in FRAME_FAMS:
        m = re.match(pat, rid or "")
        if m:
            return tag, m.groups()
    return "其他", ()


class Text:
    """Locale_*.dec（SQLite）→ key 到目标语言的映射。缺目录时静默降级。"""

    def __init__(self, d: str, lang: str):
        self.d, self.lang, self.cache = (Path(d) if d else None), lang, {}

    def _tab(self, table: str):
        if not self.d:
            return {}
        if table in self.cache:
            return self.cache[table]
        p = self.d / f"Locale_{table}.dec"
        if not p.exists():
            p = self.d / f"Locale_{table}.lss"
        out = {}
        if p.exists():
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
                if "Key" not in cols:
                    continue
                col = self.lang if self.lang in cols else ("en" if "en" in cols else cols[-1])
                out = {k: (v or "") for k, v in con.execute(f'select Key,"{col}" from "{t}"')}
                break
            con.close()
        self.cache[table] = out
        return out

    def __call__(self, key: str):
        if not key or ":" not in key:
            return ""
        t, k = key.split(":", 1)
        return (self._tab(t.replace("Locale_", "")) or {}).get(k, "")


def snapshot(static: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    uf = load(static, "UserFrameTable")
    ut = load(static, "UserTitleTable")
    ua = load(static, "UserTitleAssemblyTable")
    pc = load(static, "ProfileCardObjectTable")

    (dst / "头像框.json").write_text(json.dumps(
        {"count": len(uf), "unique_resource": len({r["ResourceId"] for r in uf if r.get("ResourceId")}),
         "rows": [{"Id": r["Id"], "ResourceId": r.get("ResourceId") or "",
                   "SubResourceId": r.get("SubResourceId") or "", "TabType": r.get("TabType"),
                   "LocaleKey": r.get("NameLocalkey") or ""} for r in uf]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    for table, tag, icon_f, name_f in (("UserTitleTable", "称号", "IconResourceId", "NameLocaleKey"),
                                       ("UserTitleAssemblyTable", "称号装配", "IconId", "TitleLocaleKey")):
        rows = load(static, table)
        slim = [{"Id": r["Id"], "IconResource": r.get(icon_f) or "", "LocaleKey": r.get(name_f) or ""}
                for r in rows]
        codes = sorted({s["IconResource"] for s in slim if s["IconResource"]})
        (dst / f"{tag}.json").write_text(json.dumps(
            {"table": table, "count": len(slim), "icon_codes": len(codes), "codes": codes, "rows": slim},
            ensure_ascii=False, indent=1), encoding="utf-8")

    rows = [{"Id": r["Id"], "Type": r.get("ObjectType"), "Sub": r.get("ObjectSubType"),
             "Grade": r.get("GradeType"), "ResourceId": r.get("ResourceId") or "",
             "LocaleKey": r.get("NameLocalkey") or ""} for r in pc]
    (dst / "个人主页.json").write_text(json.dumps(
        {"table": "ProfileCardObjectTable", "count": len(rows),
         "by_type": {f"{t}-{s}": sum(1 for r in rows if r["Type"] == t and r["Sub"] == s)
                     for t, s in sorted({(r["Type"], r["Sub"]) for r in rows})},
         "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"快照 → {dst}（头像框 {len(uf)} / 称号 {len(ut)} / 装配 {len(ua)} / 名片 {len(pc)}）")


def diff(old: dict, new: list, key="Id"):
    oi = {r[key] for r in old.get("rows", [])}
    add = [r for r in new if r[key] not in oi]
    gone = sorted(oi - {r[key] for r in new})
    return add, gone


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", default=str(DEFAULT_STATIC))
    ap.add_argument("--baseline", default="", help="旧快照目录（含 头像框.json 等）")
    ap.add_argument("--snapshot", default="", help="写快照到该目录")
    ap.add_argument("--text", default="", help="Locale_*.dec 目录")
    ap.add_argument("--lang", default="zh-CN")
    ap.add_argument("--tsv", default="", help="新增清单写 TSV")
    a = ap.parse_args()

    static = Path(a.static)
    if a.snapshot:
        snapshot(static, Path(a.snapshot))
        if not a.baseline:
            return 0

    TX = Text(a.text, a.lang)
    cur = {
        "头像框": {"rows": [{"Id": r["Id"], "ResourceId": r.get("ResourceId") or "",
                          "LocaleKey": r.get("NameLocalkey") or ""}
                         for r in load(static, "UserFrameTable")]},
        "称号": {"rows": [{"Id": r["Id"], "IconResource": r.get("IconResourceId") or "",
                        "LocaleKey": r.get("NameLocaleKey") or ""}
                       for r in load(static, "UserTitleTable")]},
        "称号装配": {"rows": [{"Id": r["Id"], "IconResource": r.get("IconId") or "",
                          "LocaleKey": r.get("TitleLocaleKey") or ""}
                         for r in load(static, "UserTitleAssemblyTable")]},
        "个人主页": {"rows": [{"Id": r["Id"], "Type": r.get("ObjectType"), "Sub": r.get("ObjectSubType"),
                          "ResourceId": r.get("ResourceId") or "",
                          "LocaleKey": r.get("NameLocalkey") or ""}
                         for r in load(static, "ProfileCardObjectTable")]},
    }

    base_dir = Path(a.baseline) if a.baseline else DEFAULT_BASE
    lines, tsv = [], [("类别", "Id", "资源号/图标", "名字键", "中文名", "归族")]
    for tag in ("头像框", "称号", "称号装配", "个人主页"):
        bp = base_dir / f"{tag}.json"
        if not bp.exists():
            lines.append(f"!! 基线缺 {bp} —— 先跑 --snapshot 建一份")
            continue
        old = json.loads(bp.read_text(encoding="utf-8"))
        add, gone = diff(old, cur[tag]["rows"])
        lines.append(f"\n【{tag}】基线 {old.get('count', len(old.get('rows', [])))} → 当前 {len(cur[tag]['rows'])}"
                     f"　新增 {len(add)} / 消失 {len(gone)}")
        if gone:
            lines.append(f"  消失 Id: {gone[:20]}")
        # 归族
        grp = collections.defaultdict(list)
        for r in add:
            if tag == "头像框":
                fam, g = frame_fam(r["ResourceId"])
                sub = ("/".join(x for x in g if x) if g else "")
                grp[f"{fam}·{sub}"].append(r)
            elif tag == "个人主页":
                t = {"0": "背景", "1": "贴纸"}.get(str(r["Type"]), f"Type{r['Type']}")
                sub = "称号badge" if (r["Type"] == 1 and r["Sub"] == 3) else f"Sub{r['Sub']}"
                grp[f"{t}/{sub}"].append(r)
            elif tag == "称号装配":
                grp["装配称号"].append(r)
            else:
                k = re.sub(r"_\d+$", "_#", (r["LocaleKey"] or "").split(":")[-1])
                grp[k].append(r)
        for k, rs in sorted(grp.items(), key=lambda x: -len(x[1])):
            lines.append(f"  · {k}：{len(rs)} 件")
            for r in rs[:12]:
                nm = TX(r["LocaleKey"]) if a.text else ""
                rid = r.get("ResourceId") or r.get("IconResource") or ""
                lines.append(f"      {r['Id']:<7} {rid:<34} {r['LocaleKey']:<52} {nm}")
                tsv.append((tag, r["Id"], rid, r["LocaleKey"], nm, k))
            if len(rs) > 12:
                lines.append(f"      … 另 {len(rs) - 12} 件见 TSV")

    print("\n".join(lines))
    if a.tsv:
        p = Path(a.tsv); p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            for row in tsv:
                f.write("\t".join(str(x) for x in row) + "\n")
        print(f"\nTSV → {p}（{len(tsv) - 1} 行新增）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
