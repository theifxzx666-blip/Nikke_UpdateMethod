# -*- coding: utf-8 -*-
"""大 bundle 的逐 chunk 拉取。

pull_bundle.pull() 假设「按 store_offset 排序后文件偏移正好首尾相接」，对跨多个 pak、
chunk 在 store 里不连续的包不成立（会报「拼接错位」）。这里改成：
每个 chunk 单独 dd 一小段 → 逐块装回原文 → 按 file_offset 排序拼接。
代价是 adb 调用次数 = chunk 数（十几到几十次），但不需要一次搬几个 GB。
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import zstandard

ADB = r"D:\WorkBuddy\Supports\platform-tools\adb.exe"
BASE = "/storage/emulated/0/Android/data/com.proximabeta.nikke/files/com.shiftup.patch"
TMP = "/sdcard/nikke_tmp_1029"
D = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
BS = 4096


def adb_sh(cmd, timeout=900):
    p = subprocess.run([ADB, "shell", f"su -c '{cmd}'"],
                       capture_output=True, timeout=timeout)
    return (p.stdout or b"").decode("utf-8", "replace"), (p.stderr or b"").decode("utf-8", "replace")


def load_idx(bucket):
    b = (D / f"{bucket}.cdb.idx").read_bytes()
    n = int.from_bytes(b[8:12], "little")
    idx, off = {}, 12
    for _ in range(n):
        h = b[off:off + 16].hex()
        pos = int.from_bytes(b[off + 16:off + 24], "little")
        comp = int.from_bytes(b[off + 24:off + 28], "little")
        idx[h] = (pos, comp)
        off += 28
    return idx


def key_chunks(bucket, key):
    con = sqlite3.connect(f"file:{D / (bucket + '_catalog.dec')}?mode=ro", uri=True)
    r = con.execute("select file_id from files_chunktype where key=?", (key,)).fetchone()
    if not r:
        con.close()
        raise SystemExit("键不存在: " + key)
    rows = list(con.execute(
        "select m.file_offset, c.hash, c.original_size, c.compressed_size "
        "from chunk_file_map m join chunks c on c.chunk_id=m.chunk_id "
        "where m.file_id=? order by m.file_offset", (r[0],)))
    con.close()
    return rows


def pull(bucket, key, out_name=None):
    idx = load_idx(bucket)
    rows = key_chunks(bucket, key)
    dctx = zstandard.ZstdDecompressor()

    adb_sh(f"rm -rf {TMP}/ch && mkdir -p {TMP}/ch")
    cmds = []
    metas = []
    for i, (fo, h, orig, comp) in enumerate(rows):
        hx = h.hex() if isinstance(h, (bytes, bytearray)) else str(h).lower()
        pos = idx[hx][0]
        nb = (comp + BS - 1) // BS + 1
        cmds.append(f"dd if={BASE}/{bucket}/chunk/store.cdb of={TMP}/ch/{i}.bin "
                    f"bs={BS} skip={pos // BS} count={nb} 2>/dev/null")
        metas.append(dict(i=i, fo=fo, orig=orig, comp=comp, pos=pos))
    adb_sh(" && ".join(cmds) + f" && chmod -R 666 {TMP}/ch", timeout=1800)

    out = bytearray()
    for m in metas:
        lp = D / f"_ch_{m['i']}.bin"
        p = subprocess.run([ADB, "pull", f"{TMP}/ch/{m['i']}.bin", str(lp)],
                           capture_output=True, timeout=600)
        if p.returncode != 0:
            raise SystemExit(f"pull chunk {m['i']} 失败")
        raw = lp.read_bytes()
        # 不删中间文件：本机 safe-delete 补丁对 os.remove / Path.unlink 都会拦截，
        # 每轮删除数超阈值后直接 fail-closed，会把整个批处理进程带崩。
        # 文件名固定为 _ch_{i}.bin，下一轮直接覆盖，不会堆积。
        trim = m["pos"] - (m["pos"] // BS) * BS
        dec = dctx.decompress(raw[trim:trim + m["comp"]],
                              max_output_size=max(m["orig"], 1) * 2)
        assert len(dec) == m["orig"], f"chunk {m['i']} 长度 {len(dec)} != {m['orig']}"
        assert m["fo"] == len(out), f"拼接错位 chunk{m['i']} {m['fo']} != {len(out)}"
        out += dec
    name = out_name or ("mon_" + Path(key).name)
    bp = D / name
    bp.write_bytes(bytes(out))
    print(f"[ok] {key}\n      {len(out):,}B → {bp.name} head={bytes(out[:8])}")
    return bp


if __name__ == "__main__":
    bucket, key = sys.argv[1], sys.argv[2]
    nm = sys.argv[3] if len(sys.argv) > 3 else None
    pull(bucket, key, nm)
