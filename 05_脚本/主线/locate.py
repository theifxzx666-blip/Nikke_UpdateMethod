# -*- coding: utf-8 -*-
"""store.cdb.idx 解析 + 按 catalog 键定位 chunk 区间。

输出给下一步 dd 用的字节区间，供批量取数。
"""
import struct
import sqlite3
import sys
from pathlib import Path

D = Path(r"D:\Codex\临时\nikke_intl_20261029\device")


def load_idx(bucket):
    """返回 dict: hash(bytes16) -> (abs_offset, comp_size)"""
    p = D / f"{bucket}.cdb.idx"
    d = p.read_bytes()
    assert d[:4] == b"CIDX", d[:8]
    count = struct.unpack_from("<I", d, 8)[0]
    idx = {}
    off = 12
    for _ in range(count):
        h = d[off:off + 16]
        o, s = struct.unpack_from("<QI", d, off + 16)
        idx[h] = (o, s)
        off += 28
    return idx, off, len(d)


def key_chunks(bucket, key):
    con = sqlite3.connect(f"file:{D / (bucket + '_catalog.dec')}?mode=ro", uri=True)
    row = con.execute("select file_id from files_chunktype where key=?", (key,)).fetchone()
    if not row:
        con.close()
        return None
    fid = row[0]
    rows = con.execute("""
        select m.file_offset, c.hash, c.original_size, c.compressed_size, c.pak_id, c.pak_offset
        from chunk_file_map m join chunks c on c.chunk_id=m.chunk_id
        where m.file_id=? order by m.file_offset""", (fid,)).fetchall()
    con.close()
    return fid, rows


if __name__ == "__main__":
    bucket = sys.argv[1] if len(sys.argv) > 1 else "dp"
    key = sys.argv[2]
    idx, used, total = load_idx(bucket)
    print(f"idx 条目={len(idx):,} 解析字节={used:,}/{total:,} 尾部剩余={total - used}")
    fid, rows = key_chunks(bucket, key)
    print(f"file_id={fid} chunk 数={len(rows)}")
    tot_orig = sum(r[2] for r in rows)
    print(f"文件原始大小合计={tot_orig:,}B")
    segs = []
    for fo, h, orig, comp, pak, po in rows:
        if h not in idx:
            print(f"  !! hash {h.hex()} 不在 idx")
            continue
        abs_off, idx_size = idx[h]
        if idx_size != comp:
            print(f"  ! 长度不一致 idx={idx_size} chunk={comp} hash={h.hex()}")
        segs.append((fo, abs_off, comp, orig, h.hex()))
    segs.sort()
    for fo, a, c, o, h in segs[:10]:
        print(f"  file_off={fo:>10,} store_off={a:>12,} comp={c:>9,} orig={o:>9,} {h}")
    if segs:
        lo = min(s[1] for s in segs)
        hi = max(s[1] + s[2] for s in segs)
        print(f"总区间 store_off {lo:,} .. {hi:,} = {hi - lo:,}B（连续取段上限）")
        print(f"gap 检查: {[(s[0], s[1]) for s in segs[:3]]}")
