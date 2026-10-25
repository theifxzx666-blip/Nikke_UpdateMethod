# -*- coding: utf-8 -*-
"""建立国际服 152.8.7 基线快照 + 干跑产物归位。"""
import hashlib
import shutil
import sqlite3
from pathlib import Path

SRC = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
OUT = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点\_干跑_20261025")
CAT = OUT / "00_基线_catalog"
KEYS = OUT / "00_基线_键清单"
SHOT = OUT / "样例_头像框"

for d in (OUT, CAT, KEYS, SHOT):
    d.mkdir(parents=True, exist_ok=True)

BUCKETS = ["core", "dp", "saus", "ja", "fd"]
lines = []
for b in BUCKETS:
    dec = SRC / f"{b}_catalog.dec"
    ndb = SRC / f"{b}_catalog.ndb"
    if not dec.exists():
        continue
    shutil.copy2(dec, CAT / dec.name)
    if ndb.exists():
        shutil.copy2(ndb, CAT / ndb.name)
    con = sqlite3.connect(f"file:{dec}?mode=ro", uri=True)
    keys = [r[0] for r in con.execute("select key from files_chunktype order by key")]
    raw = [(r[0], r[1]) for r in con.execute(
        "select key, lower(hex(hash)) from files_rawtype order by key")]
    (KEYS / f"{b}_keys.txt").write_text("\n".join(keys), encoding="utf-8")
    (KEYS / f"{b}_raw_keys.tsv").write_text(
        "\n".join(f"{k}\t{h}" for k, h in raw), encoding="utf-8")
    chunks = con.execute("select count(*) from chunks").fetchone()[0]
    comp = con.execute("select sum(compressed_size) from chunks").fetchone()[0] or 0
    orig = con.execute("select sum(original_size) from chunks").fetchone()[0] or 0
    con.close()

    def sha(p):
        h = hashlib.sha256()
        h.update(p.read_bytes())
        return h.hexdigest()

    lines.append({
        "bucket": b,
        "keys": len(keys),
        "raw": len(raw),
        "chunks": chunks,
        "comp_gb": round(comp / 2**30, 2),
        "orig_gb": round(orig / 2**30, 2),
        "dec_sha256": sha(dec),
        "ndb_sha256": sha(ndb) if ndb.exists() else "-",
    })
    print(f"{b}: 键={len(keys):,} raw={len(raw)} chunk={chunks:,} "
          f"压缩={comp/2**30:.2f}GB 原始={orig/2**30:.2f}GB")

for p in (SRC / "png").glob("*.png"):
    shutil.copy2(p, SHOT / p.name)
    print("样例:", p.name)

# 索引与 URL 快照（供更新后 diff 用）
for n in ("core", "dp", "ja", "fd"):
    s = SRC / f"{n}.cdb.idx"
    if s.exists():
        shutil.copy2(s, CAT / s.name)

import json
(CAT / "manifest.json").write_text(
    json.dumps({"version": "152.8.7", "device": "e9711d88 / 25102RKBEC",
                "package": "com.proximabeta.nikke", "android": "17",
                "snapshot_at": "2026-10-25", "buckets": lines},
               ensure_ascii=False, indent=2), encoding="utf-8")
print("完成 ->", OUT)
