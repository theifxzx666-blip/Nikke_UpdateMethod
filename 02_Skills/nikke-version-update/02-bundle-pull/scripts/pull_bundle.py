# -*- coding: utf-8 -*-
"""通用：给定桶 + bundle 键 → 定位 chunk → adb dd 取段 → zstd 拼装 → UnityPy dump。

用法：
    python pull_bundle.py <bucket> <key> [--png N]
"""
import json
import subprocess
import sys
from pathlib import Path

import zstandard

ADB = r"D:\WorkBuddy\Supports\platform-tools\adb.exe"
BASE = "/storage/emulated/0/Android/data/com.proximabeta.nikke/files/com.shiftup.patch"
TMP = "/sdcard/nikke_tmp_1029"
D = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
BS = 4096


def adb_sh(cmd, timeout=600):
    """adb shell su -c '<cmd>'，返回 stdout 文本。"""
    p = subprocess.run([ADB, "shell", f"su -c '{cmd}'"],
                       capture_output=True, timeout=timeout)
    return (p.stdout or b"").decode("utf-8", "replace"), (p.stderr or b"").decode("utf-8", "replace")


def adb_pull(remote, local):
    p = subprocess.run([ADB, "pull", remote, str(local)],
                       capture_output=True, timeout=900)
    return p.returncode == 0, (p.stdout or b"").decode("utf-8", "replace")


def load_idx(bucket):
    p = D / f"{bucket}.cdb.idx"
    b = p.read_bytes()
    assert b[:4] == b"CIDX", f"idx 头不符 {b[:4]}"
    # 布局：CIDX(4) + version(4) + count(4) + count×28 + footer(16)
    n = int.from_bytes(b[8:12], "little")
    assert 12 + n * 28 <= len(b), f"记录数越界 n={n} size={len(b)}"
    idx = {}
    off = 12
    for _ in range(n):
        h = b[off:off + 16].hex()
        pos = int.from_bytes(b[off + 16:off + 24], "little")
        comp = int.from_bytes(b[off + 24:off + 28], "little")
        idx[h] = (pos, comp)
        off += 28
    return idx, n


def key_chunks(bucket, key):
    import sqlite3
    con = sqlite3.connect(f"file:{D / (bucket + '_catalog.dec')}?mode=ro", uri=True)
    r = con.execute(
        "select file_id from files_chunktype where key=?", (key,)).fetchone()
    if not r:
        con.close()
        raise SystemExit(f"键不存在: {key}")
    fid = r[0]
    rows = list(con.execute(
        "select m.file_offset, c.hash, c.original_size, c.compressed_size, c.pak_id, c.pak_offset "
        "from chunk_file_map m join chunks c on c.chunk_id=m.chunk_id "
        "where m.file_id=? order by m.file_offset", (fid,)))
    con.close()
    return fid, rows


def pull(bucket, key, png=0):
    idx, n = load_idx(bucket)
    fid, rows = key_chunks(bucket, key)
    segs = []
    for fo, h, orig, comp, pak, po in rows:
        hx = h.hex() if isinstance(h, (bytes, bytearray)) else str(h).lower()
        pos, icomp = idx[hx]
        segs.append({"file_offset": fo, "store_offset": pos, "comp": comp, "orig": orig})
    # 读取范围按 store_offset 定，但拼装必须按文件内 file_offset 顺序：
    # store.cdb 是内容寻址，重复 chunk 只存一份，可能出现「靠后的块在更小偏移」
    segs.sort(key=lambda s: s["file_offset"])
    lo = min(s["store_offset"] for s in segs)
    hi = max(s["store_offset"] + s["comp"] for s in segs)
    print(f"[1] {key}\n    fid={fid} chunks={len(segs)} lo={lo:,} hi={hi:,} "
          f"len={hi - lo:,} | 文件总大小 {sum(s['orig'] for s in segs):,}")

    # 按 store 位置聚簇，簇间空隙超过 32MB 就分段拉，避免为几个去重块把整个区间拖下来
    by_store = sorted(segs, key=lambda s: s["store_offset"])
    clusters, cur = [], [by_store[0]]
    for s in by_store[1:]:
        gap = s["store_offset"] - (cur[-1]["store_offset"] + cur[-1]["comp"])
        if gap > 32 * 1024 * 1024:
            clusters.append(cur)
            cur = [s]
        else:
            cur.append(s)
    clusters.append(cur)

    chunks_data = {}
    for ci, cl in enumerate(clusters, 1):
        clo = min(x["store_offset"] for x in cl)
        chi = max(x["store_offset"] + x["comp"] for x in cl)
        clo_al = (clo // BS) * BS
        nbs = (chi - clo_al + BS - 1) // BS
        tag = f"[1.{ci}]" if len(clusters) > 1 else "[1.1]"
        print(f"    {tag} 簇 {len(cl):>3} 块  {clo_al:,} ~ {chi:,}  ({nbs * BS / 1048576:.1f} MB)")
        cmd = (f"dd if={BASE}/{bucket}/chunk/store.cdb of={TMP}/pk.bin "
               f"bs={BS} skip={clo_al // BS} count={nbs} 2>/dev/null && chmod 666 {TMP}/pk.bin")
        adb_sh(cmd)
        ok, msg = adb_pull(f"{TMP}/pk.bin", D / "pk.bin")
        if not ok:
            raise SystemExit(f"拉取失败: {msg}")
        raw = (D / "pk.bin").read_bytes()
        print(f"         拉回 {len(raw):,}B")
        trim = clo - clo_al
        for s in cl:
            st = s["store_offset"] - clo + trim
            chunks_data[s["store_offset"]] = raw[st:st + s["comp"]]

    dctx = zstandard.ZstdDecompressor()
    buf = bytearray()
    for s in segs:
        dec = dctx.decompress(chunks_data[s["store_offset"]], max_output_size=max(s["orig"], 1) * 2)
        assert len(dec) == s["orig"], f"长度不符 {len(dec)} != {s['orig']}"
        assert s["file_offset"] == len(buf), f"拼接错位 {s['file_offset']} != {len(buf)}"
        buf += dec
    bp = D / (key.split("_assets")[0].replace("/", "_") + ".bundle")
    bp.write_bytes(bytes(buf))
    print(f"[3] 拼装 {len(buf):,}B head={bytes(buf[:8])} → {bp.name}")
    return bp


def dump(bp, png=0):
    import UnityPy
    env = UnityPy.load(str(bp))
    from collections import Counter
    cnt = Counter()
    items = []
    outdir = D / "png"
    outdir.mkdir(exist_ok=True)
    saved = 0
    for obj in env.objects:
        cnt[obj.type.name] += 1
        if obj.type.name in ("Sprite", "Texture2D"):
            try:
                dat = obj.read()
                nm = getattr(dat, "m_Name", None) or "unnamed"
                w = h = None
                if obj.type.name == "Texture2D":
                    w, h = dat.m_Width, dat.m_Height
                items.append((obj.type.name, nm, w, h))
                if obj.type.name == "Texture2D" and saved < png:
                    dat.image.save(outdir / f"{nm}.png")
                    saved += 1
            except Exception as e:
                items.append((obj.type.name, f"<err {str(e)[:30]}>", None, None))
    print(f"[4] 对象类型: {dict(cnt)}")
    print(f"    Sprite/Texture2D {len(items)} 条")
    return items


if __name__ == "__main__":
    bucket, key = sys.argv[1], sys.argv[2]
    npng = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[3] == "--png" else 0
    bp = pull(bucket, key, npng)
    items = dump(bp, npng)
    jf = D / (bp.stem + "_objects.json")
    jf.write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"[5] 对象名清单 → {jf.name}")
    for t, n, w, h in items[:15]:
        print(f"    [{t}] {n} {w}x{h}" if w else f"    [{t}] {n}")
