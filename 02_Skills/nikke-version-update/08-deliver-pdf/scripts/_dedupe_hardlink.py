"""交付目录去重：同内容改硬链接（物理只存一份，两边都能打开）。

规则
- 跳过 06_角色大厅站立动画：那里的 xxx_action_首帧.png 与 xxx_idle_首帧.png
  字节相同是**语义巧合**（两个不同动画的首帧恰好一样），不是重复，合并会误导。
- 主副本选择：
    *.gif 出现在 01_新角色  → 01 为实体（用户指定「留 01 的」）
    其他图在 07_角色爆裂特写 → 07 为实体（有 01_背景板/02_角色特效/… 分类，且清单登记在此）
    剧情插画                 → 05_主线_47-48章/05_图片资源/剧情插画 为实体
    03_活动 下的文本         → 03_活动 为实体
- 已经是同一 inode 的跳过。

用 --write 才真正执行；默认只报告。
"""
import hashlib
import os
import sys
from collections import defaultdict

ROOT = r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
SKIP_TOP = ("_构建", "06_角色大厅站立动画")
MIN_SIZE = 50000


def rank(p):
    rel = p.replace("\\", "/")
    if rel.endswith(".gif"):
        return 0 if "01_新角色" in rel else 1
    if "07_角色爆裂特写" in rel:
        return 0
    if "05_图片资源/剧情插画" in rel:
        return 0
    if rel.startswith("./03_活动"):
        return 0
    if "05_主线_47-48章/04_剧情文本" in rel:
        return 1
    return 5


def main(write: bool):
    groups = defaultdict(list)
    for dp, dn, fn in os.walk(ROOT):
        if any(s in dp for s in SKIP_TOP):
            continue
        for f in fn:
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_size < MIN_SIZE:
                continue
            with open(p, "rb") as fh:
                d = hashlib.md5(fh.read(65536)).hexdigest() + str(st.st_size)
            groups[d].append((p, st))

    dup = {k: v for k, v in groups.items() if len(v) > 1}
    saved = 0
    linked = 0
    for k, v in sorted(dup.items(), key=lambda x: -x[1][0][1].st_size):
        v.sort(key=lambda x: rank(x[0]))
        src, sst = v[0]
        for p, st in v[1:]:
            if st.st_ino == sst.st_ino and st.st_dev == sst.st_dev:
                continue
            saved += st.st_size
            linked += 1
            print(f"{'LINK' if write else 'WOULD'} {st.st_size/1048576:6.2f}MB  "
                  f"{os.path.relpath(p, ROOT)}")
            print(f"      -> {os.path.relpath(src, ROOT)}")
            if write:
                os.remove(p)
                os.link(src, p)
    print(f"\n重复组 {len(dup)}　待链接 {linked} 个文件　"
          f"{'已省' if write else '可省'} {saved/1048576:.1f} MB")


if __name__ == "__main__":
    main("--write" in sys.argv)
