#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把指定的 UnityCache __data 复制到设备 /sdcard 下并拉回本地（逐个 cp，避免长命令截断）。"""
import subprocess
import sys
from pathlib import Path

ADB = r"D:\WorkBuddy\Supports\platform-tools\adb.exe"
LIST = Path(r"D:\Codex\临时\nikke_cn_20260930\uc_probe.txt")
OUT = Path(r"D:\Codex\临时\nikke_cn_20260930\uc_probe")
STAGE = "/sdcard/_ucp"


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def main():
    paths = LIST.read_text(encoding="utf-8").split()
    run([ADB, "shell", f"su -c 'rm -rf {STAGE}'"])
    run([ADB, "shell", f"su -c 'mkdir -p {STAGE}'"])
    run([ADB, "shell", f"su -c 'chmod 777 {STAGE}'"])
    ok = 0
    for i, p in enumerate(paths, 1):
        dst = f"{STAGE}/s{i:02d}.bundle"
        r = run([ADB, "shell", f"su -c 'cp \"{p}\" {dst} && chmod 666 {dst}'"])
        if r.returncode:
            print(f"FAIL {i}: {r.stderr.strip()[:110]}")
        else:
            ok += 1
    print(f"设备侧就绪 {ok}/{len(paths)}")
    OUT.mkdir(parents=True, exist_ok=True)
    r = run([ADB, "pull", f"{STAGE}/.", str(OUT)])
    print(r.stdout.strip()[-160:] or r.stderr.strip()[-160:])
    files = sorted(OUT.glob("*.bundle"))
    print(f"本地 {len(files)} 个，共 {round(sum(f.stat().st_size for f in files)/2**20,1)} MiB")


if __name__ == "__main__":
    main()
