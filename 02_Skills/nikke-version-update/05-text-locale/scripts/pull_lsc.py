# -*- coding: utf-8 -*-
"""pull_lsc.py —— 按 key 从国际服 saus/raw 拉取文本表并解密为 SQLite。

国际服（152.8.7）文本表不在 store.cdb 里，而是 raw 桶的独立文件：
    files/com.shiftup.patch/saus/raw/<hash>.lsc
catalog 的 files_rawtype 表给出 key -> hash。文件本身是 NKDB（AES-OFB + zlib 分段）。

用法：
    python pull_lsc.py <表名1> [表名2 ...]        # 表名不带 .lsc 后缀也可
    python pull_lsc.py --list                    # 列出全部可拉表
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Codex\临时\nikke_ce008")
from dec import decrypt_nkdb  # noqa: E402

ADB = r"D:\WorkBuddy\Supports\platform-tools\adb.exe"
BASE = "/storage/emulated/0/Android/data/com.proximabeta.nikke/files/com.shiftup.patch/saus/raw"
TMP = "/sdcard/nikke_tmp_1029"
DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
OUT = DEV / "lsc"
CAT = DEV / "saus_catalog.dec"


def adb(*args, timeout=900):
    p = subprocess.run([ADB, *args], capture_output=True, timeout=timeout)
    return p.returncode == 0, (p.stdout or b"").decode("utf-8", "replace").strip()


def keys():
    con = sqlite3.connect(f"file:{CAT}?mode=ro", uri=True)
    d = {k: (h.hex(), s) for k, h, s in
         con.execute("select key,hash,size from files_rawtype where extension='.lsc'")}
    con.close()
    return d


def pull_one(name, table):
    key = name if name.endswith(".lsc") else name + ".lsc"
    if key not in table:
        print(f"  x 键不存在: {key}")
        return None
    hx, size = table[key]
    dec = OUT / (Path(key).stem.replace("/", "_") + ".dec")
    if dec.exists() and dec.stat().st_size > size // 2:
        print(f"  = 已存在 {dec.name} ({dec.stat().st_size:,}B)，跳过")
        return dec
    ok, _ = adb("shell", f"su -c 'cp {BASE}/{hx}.lsc {TMP}/'")
    ok2, msg = adb("pull", f"{TMP}/{hx}.lsc", str(OUT / f"{hx}.lsc"))
    if not (ok and ok2):
        print(f"  x 拉取失败 {key}: {msg}")
        return None
    data = (OUT / f"{hx}.lsc").read_bytes()
    raw = decrypt_nkdb(data) if data[:4] == b"NKDB" else data
    dec.write_bytes(raw)
    (OUT / f"{hx}.lsc").unlink()
    print(f"  ok {key:36s} {size:>10,}B -> {dec.name} {len(raw):>11,}B head={raw[:15]!r}")
    return dec


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    adb("shell", f"su -c 'mkdir -p {TMP} && chmod 777 {TMP}'")
    table = keys()
    args = sys.argv[1:]
    if not args or args[0] == "--list":
        for k, (h, s) in table.items():
            print(f"{k:44s} {s:>11,}")
        raise SystemExit(0)
    print(f"[目标 {len(args)} 张表]")
    for a in args:
        pull_one(a, table)
