# -*- coding: utf-8 -*-
"""
同卷递归移动（保留硬链接 / inode）。

为什么不用 shutil.move 或 robocopy：
- shutil.move 整目录 rename 时，只要树里任何一个目录被别的进程持有句柄（资源管理器、
  索引器、残留的 http.server），就会 WinError 5 拒绝访问 —— 而且是整棵树都动不了。
- robocopy /MOVE 会先复制再删除，等于把硬链接全部还原成独立副本（本期 1.2 GB 会翻倍）。

本脚本的做法：能整目录 rename 就整目录 rename；rename 失败且是目录就下钻，
只移条目 ; 移到叶子仍是文件就直接 rename 文件。全程同卷 rename，
inode 不变，硬链接关系原样保留。

用法：
    python move_tree.py <src> <dst> [--apply]
不给 --apply 只预演（报告哪些条目需要下钻）。
"""
import os
import sys

FAIL = []


def move_tree(src, dst, apply=True, depth=0, log=None):
    if log is None:
        log = []
    if not os.path.isdir(dst):
        if apply:
            os.makedirs(dst, exist_ok=True)
        log.append(("mkdir", dst))
    for name in sorted(os.listdir(src)):
        s, d = os.path.join(src, name), os.path.join(dst, name)
        try:
            if apply:
                os.rename(s, d)
            log.append(("rename", s))
        except PermissionError:
            if os.path.isdir(s):
                log.append(("drill-down", s))
                move_tree(s, d, apply, depth + 1, log)
            else:
                FAIL.append(s)
                log.append(("FILE-LOCKED", s))
        except FileExistsError:
            FAIL.append(s)
            log.append(("EXISTS", s))
    return log


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, dst = sys.argv[1], sys.argv[2]
    apply = "--apply" in sys.argv
    log = move_tree(src, dst, apply)
    ren = sum(1 for a, _ in log if a == "rename")
    drill = [p for a, p in log if a == "drill-down"]
    print(f"{'执行' if apply else '预演'}：整目录 rename {ren} 项，需下钻 {len(drill)} 项")
    for p in drill[:10]:
        print("  下钻:", p.replace(src, "."))
    if FAIL:
        print("失败（仍被占用）：")
        for p in FAIL[:20]:
            print("  ", p.replace(src, "."))
        return 2
    if apply:
        # 收尾：清掉已经空掉的源骨架
        left = []
        for dp, dn, fn in os.walk(src):
            if fn or dn:
                left.append(dp)
        print("源目录残留条目:", len(left))
        if not left:
            for dp, dn, fn in os.walk(src, topdown=False):
                try:
                    os.rmdir(dp)
                except OSError:
                    pass
            print("源骨架已清空")
    return 0


if __name__ == "__main__":
    sys.exit(main())
