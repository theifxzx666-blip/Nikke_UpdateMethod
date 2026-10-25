# -*- coding: utf-8 -*-
"""list_lss_tables.py —— 列出 .lss / .lsc（实为 SQLite）里的全部表、行数、列名。

用法：
  python list_lss_tables.py <文件或目录> [...] [--key-like Locale_]
  目录会递归找 *.lss / *.lsc / *.dec / *.db

为什么要这一步：表名与字段名是本项目最容易「凭记忆写错」的地方。
先列再查，是所有后续取数的前置。
"""
from __future__ import annotations
import argparse, os, sqlite3, sys

EXTS = (".lss", ".lsc", ".dec", ".db")


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for dp, _dn, fn in os.walk(p):
                for f in fn:
                    if f.lower().endswith(EXTS):
                        yield os.path.join(dp, f)
        elif os.path.isfile(p):
            yield p


def probe(path: str, key_like: str | None) -> None:
    with open(path, "rb") as fh:
        head = fh.read(16)
    if not head.startswith(b"SQLite format 3"):
        print(f"\n## {os.path.basename(path)}  —— 不是 SQLite（头 {head[:8]!r}），先解密")
        return

    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        print(f"\n## {os.path.basename(path)}  打开失败：{e}")
        return

    print(f"\n## {os.path.basename(path)}  {os.path.getsize(path):,} B")
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    except sqlite3.Error as e:
        print(f"   查表失败：{e}")
        return

    for t in tables:
        if key_like and key_like.lower() not in t.lower():
            continue
        try:
            n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        except sqlite3.Error as e:
            print(f"   - {t}: 读失败 {e}")
            continue
        print(f"   - {t}  {n} 行  ({len(cols)} 列: {', '.join(cols[:10])}"
              f"{' …' if len(cols) > 10 else ''})")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--key-like", default=None, help="只看表名含该子串的表")
    a = ap.parse_args()

    files = list(iter_files(a.paths))
    if not files:
        sys.exit("[FATAL] 没找到 .lss/.lsc/.dec/.db")
    print(f"共 {len(files)} 个文件")
    for p in sorted(files):
        probe(p, a.key_like)


if __name__ == "__main__":
    main()
