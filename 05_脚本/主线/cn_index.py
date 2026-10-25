#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""扫描目录下全部国服 catalog，出索引表：span / keys / entries / 关键资源命中数。

用法：python cn_index.py <catalog 目录> [--out index.tsv]
"""
import json
import sys
from pathlib import Path

# 统计这几个前缀在 m_InternalIds 里出现多少次，用来判断 group 装了什么
PROBES = ["icons-char-full", "icons-char-mi", "sdcharacters",
          "spinestanding", "spotskillcutscene", "icons-costume",
          "audiogroupui", "campaignmapmodel"]


def main():
    d = Path(sys.argv[1])
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None

    rows = []
    for f in sorted(d.glob("*.json")):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[!] {f.name} 读不动：{e}")
            continue
        ids = j.get("m_InternalIds", [])
        blob = "\n".join(ids)
        rec = {
            "file": f.name,
            "bytes": f.stat().st_size,
            "span": j.get("m_ProjSpan", ""),
            "internal_ids": len(ids),
        }
        for p in PROBES:
            rec[p] = blob.count(p)
        rows.append(rec)

    hdr = ["file", "bytes", "span", "internal_ids"] + PROBES
    w = {k: max(len(k), *(len(str(r[k])) for r in rows)) for k in hdr}
    print("  ".join(k.ljust(w[k]) for k in hdr))
    for r in rows:
        print("  ".join(str(r[k]).ljust(w[k]) for k in hdr))

    if out:
        with out.open("w", encoding="utf-8", newline="") as f:
            f.write("\t".join(hdr) + "\n")
            for r in rows:
                f.write("\t".join(str(r[k]) for k in hdr) + "\n")
        print("->", out)


if __name__ == "__main__":
    main()
