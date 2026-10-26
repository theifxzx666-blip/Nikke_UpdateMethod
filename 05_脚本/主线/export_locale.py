# -*- coding: utf-8 -*-
"""Locale_* 多语导出器（Key → 简中/繁中/日/英/韩）。

用途：从已解密的 `.lss.dec`（SQLite）按表名 / LIKE 前缀导出多语文本。
不写死任何期次、路径、表名 —— 全部由参数传入，可跨版本沿用。

用法示例
--------
# 0) 先看缓存里有哪些表
python export_locale.py --list

# 1) 看某张表的列（确认语言列名，各表一致但别假设）
python export_locale.py --table Locale_Character --probe

# 2) 导出角色名（多数表的 key 是「编号_字段」后缀式，用 '%\\_name' 这种写法才命中）
python export_locale.py --table Locale_Character --like "%\\_name" --out out/角色名

# 3) 导出剧情三表并集（活动 + 番外），TSV
python export_locale.py --table Locale_MainScenario,Locale_SubScenario,Locale_SideStory \
    --out out/剧情全量 --format tsv

# 4) 导出为「每语一个 txt」（便于人工通读）
python export_locale.py --table Locale_Event --out out/活动文案 --format txt

产物
----
tsv  : 一张表一个 `<table>.tsv`（首行 BOM，Excel 直接开）
json : `<table>.json`（list[dict]）
txt  : `<table>_<语言>.txt`（`[Key]` + 正文 + 空行）
每次运行另写 `00_导出报告.tsv`：表 / 行数 / 各语言空缺数 / 参数快照。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_CACHE = os.environ.get(
    "NIKKE_DEC_CACHE", r"D:\Codex\临时\nikke_intl_20261029\dec_cache")
DEFAULT_LANGS = "zh-CN,zh-TW,ja,en,ko"
LANG_CN = {"zh-CN": "简中", "zh-TW": "繁中", "ja": "日文",
           "en": "英文", "ko": "韩文", "de": "德文", "th": "泰文",
           "fr": "法文", "es": "西文"}
KEY_COL = "Key"


def die(msg: str) -> "NoReturn":
    print(f"[FATAL] {msg}", file=sys.stderr)
    sys.exit(2)


def open_db(cache: Path, table: str) -> sqlite3.Connection:
    p = cache / f"{table}.dec"
    if not p.exists():
        p = cache / f"{table}.lss.dec"
    if not p.exists():
        cand = sorted(x.name for x in cache.glob("*.dec"))[:40]
        die(f"找不到 {table}.dec；缓存里现有：{', '.join(cand) or '(空)'}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    if not con.execute(
            "select name from sqlite_master where type='table' and name=?",
            (table,)).fetchone():
        have = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")]
        die(f"{p.name} 里没有表 {table}；该库的表：{', '.join(have) or '(空)'}")
    return con


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def pick_langs(cols: list[str], want: list[str]) -> list[str]:
    """只保留库里真实存在的语言列，缺的报出来（不静默补空）。"""
    got = [c for c in want if c in cols]
    miss = [c for c in want if c not in cols]
    if miss:
        print(f"  [WARN] 库里没有这些语言列，已跳过：{miss}（实际列：{cols}）")
    if not got:
        die(f"没有任何目标语言列命中；库里的列是 {cols}")
    return got


def fetch(con, table, langs, likes, limit):
    sel = ", ".join(f'"{c}"' for c in [KEY_COL] + langs)
    sql = f'select {sel} from "{table}"'
    params: list[str] = []
    if likes:
        # LIKE 里的下划线是通配符，必须 escape；调用方传 "name\\_%" 这种写法
        sql += " where " + " or ".join(
            f'"{KEY_COL}" like ? escape \'\\\'' for _ in likes)
        params += likes
    sql += f' order by "{KEY_COL}"'
    if limit:
        sql += f" limit {int(limit)}"
    cur = con.execute(sql, params)
    return [r[0] for r in cur.description], cur.fetchall()


def write_tsv(path: Path, head: list[str], rows: list[tuple]) -> None:
    def cell(v):
        s = "" if v is None else str(v)
        return s.replace("\t", " ").replace("\r\n", "\\n").replace("\n", "\\n")
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("\t".join(head) + "\n")
        for r in rows:
            f.write("\t".join(cell(v) for v in r) + "\n")


def write_txt(path: Path, rows: list[tuple]) -> None:
    out = []
    for r in rows:
        k, v = r[0], r[1]
        if v is None or str(v).strip() == "":
            continue
        out.append(f"[{k}]")
        out.append(str(v).replace("\r\n", "\n"))
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8-sig")


def main() -> None:
    ap = argparse.ArgumentParser(description="Locale_* 多语导出")
    ap.add_argument("--cache", default=DEFAULT_CACHE, help="解密后的 .dec 目录")
    ap.add_argument("--table", default="", help="表名，逗号分隔可多个")
    ap.add_argument("--like", action="append", default=[],
                    help='SQL LIKE，可多次；下划线需写 "\\_"')
    ap.add_argument("--langs", default=DEFAULT_LANGS)
    ap.add_argument("--out", default="", help="输出目录")
    ap.add_argument("--format", default="tsv", choices=["tsv", "json", "txt"])
    ap.add_argument("--limit", type=int, default=0, help="每表最多导几行（0=全量）")
    ap.add_argument("--list", action="store_true", help="列出缓存里的库及其表")
    ap.add_argument("--probe", action="store_true", help="只打印列名与行数")
    a = ap.parse_args()

    cache = Path(a.cache)
    if not cache.is_dir():
        die(f"缓存目录不存在：{cache}")

    if a.list:
        for p in sorted(cache.glob("*.dec")):
            try:
                con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
                tbs = [r[0] for r in con.execute(
                    "select name from sqlite_master where type='table'")]
                for t in tbs:
                    n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
                    print(f"{p.name}\t{t}\t{n:,}")
                con.close()
            except Exception as e:                       # noqa: BLE001
                print(f"{p.name}\t!(读取失败: {e})")
        return

    tables = [t.strip() for t in a.table.split(",") if t.strip()]
    if not tables:
        die("必须给 --table（或先跑 --list 看有什么）")
    want = [x.strip() for x in a.langs.split(",") if x.strip()]

    if a.probe:
        for t in tables:
            con = open_db(cache, t)
            cols = columns(con, t)
            n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
            print(f"{t}\t{n:,} 行\t列：{cols}")
            con.close()
        return

    out = Path(a.out)
    if not str(out):
        die("导出必须给 --out")
    out.mkdir(parents=True, exist_ok=True)

    report = ["# 导出报告　（参数快照：table=%s｜like=%s｜langs=%s｜format=%s｜limit=%d）"
              % (",".join(tables), a.like or "-", ",".join(want), a.format, a.limit),
              "表\t行数\t" + "\t".join(f"{LANG_CN.get(c, c)}空缺" for c in want)]

    for t in tables:
        con = open_db(cache, t)
        cols = columns(con, t)
        langs = pick_langs(cols, want)
        head, rows = fetch(con, t, langs, a.like, a.limit)
        con.close()

        blank = {c: sum(1 for r in rows if r[head.index(c)] in (None, ""))
                 for c in langs}
        report.append(f"{t}\t{len(rows)}\t" + "\t".join(
            str(blank.get(c, "-")) if c in langs else "-" for c in want))

        if a.format == "tsv":
            write_tsv(out / f"{t}.tsv", head, rows)
        elif a.format == "json":
            (out / f"{t}.json").write_text(json.dumps(
                [dict(zip(head, r)) for r in rows], ensure_ascii=False, indent=1),
                encoding="utf-8")
        else:
            # txt：一次性按语言列各写一份
            for i, c in enumerate(langs):
                write_txt(out / f"{t}_{LANG_CN.get(c, c)}.txt",
                          [(r[0], r[i + 1]) for r in rows])

        print(f"  {t}: {len(rows):,} 行 × {len(langs)} 语 "
              f"（空缺 {sum(blank.values()):,} 格）")

    (out / "00_导出报告.tsv").write_text("\n".join(report) + "\n",
                                         encoding="utf-8-sig")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
