# -*- coding: utf-8 -*-
"""
路径重写：把 8-13 期的旧路径全部改到新位置（迁移后一次性执行）。

背景
----
交付目录从
    拆包\04_临时车间\版更\20260813_国际服
搬到
    版本更新\03_历史\20260813_国际服
120 个脚本的 BASE / ROOT / DST / OUT 常量全是写死的绝对路径，不重写就全部指向空目录。
文档里的目录树、清单元数据同理。

规则表（按顺序执行，长串先跑，避免短串抢先替换后长串匹配不上）
------------------------------------------------------------
1. 转义双反斜杠形式（Markdown 代码块里出现过）  `04_临时车间\\版更`
2. 反斜杠绝对/相对形式                          `拆包\04_临时车间\版更`
3. 正斜杠形式                                  `拆包/04_临时车间/版更`
4. 去掉 拆包 前缀的残余                         `04_临时车间\版更` / `04_临时车间/版更`
5. 纯相对提示（脚本里 print 的操作提示）        `..\版更\20260813_国际服`
6. 裸目录名（docstring 里）                     `版更\20260813_国际服` / `版更/20260813_国际服`
7. 两个过程产物已归位到 _构建\                   `\_报告.html`  → `\_构建\报告.html`
                                               `\_报告素材`  → `\_构建\PDF缓存`

不动的
------
`拆包\04_临时车间\版更\_归档_20260813_v1_技术版`：
那是 v1 技术版的证据链，里面的路径是当时的真实记录，改了等于伪造历史。

用法
----
    python rewrite_paths.py           预演，逐文件报告命中数
    python rewrite_paths.py --apply   落盘
"""
import os
import sys

BASE_OLD_BS = "拆包" + "\\" + "04_临时车间" + "\\" + "版更"
BASE_NEW_BS = "版本更新" + "\\" + "03_历史"
BASE_OLD_FS = "拆包/04_临时车间/版更"
BASE_NEW_FS = "版本更新/03_历史"
PERIOD = "20260813_国际服"

RULES = [
    # 1 转义双反斜杠
    ("04_临时车间\\\\版更", "版本更新\\\\03_历史"),
    # 2/3 带 拆包 前缀
    (BASE_OLD_BS, BASE_NEW_BS),
    (BASE_OLD_FS, BASE_NEW_FS),
    # 4 残余（去掉前缀的写法）
    ("04_临时车间\\版更", "版本更新\\03_历史"),
    ("04_临时车间/版更", "版本更新/03_历史"),
    # 5 相对提示
    ("..\\版更\\" + PERIOD,
     "D:\\Codex\\Nikke\\Nikke_Skills\\版本更新\\03_历史\\" + PERIOD),
    # 6 裸目录名
    ("版更\\" + PERIOD, "版本更新\\03_历史\\" + PERIOD),
    ("版更/" + PERIOD, "版本更新/03_历史/" + PERIOD),
    # 7 过程产物归位
    ("\\_报告.html", "\\_构建\\报告.html"),
    ("/_报告.html", "/_构建/报告.html"),
    ("\\_报告素材", "\\_构建\\PDF缓存"),
    ("/_报告素材", "/_构建/PDF缓存"),
]

ROOTS = [
    r"D:\Codex\Nikke\Nikke_Skills\拆包\04_临时车间\脚本",
    r"D:\Codex\Nikke\Nikke_Skills\版本更新",
]
SKIP = ("_归档_20260813_v1_技术版", "__pycache__", "06_回收站",
        # 本脚本自身：规则表里就写着旧路径，不能改自己
        "rewrite_paths.py",
        # 规范文档里的 grep 校验语句要保留「旧路径」字样才有意义，手工维护
        "版本更新_整理与蒸馏_Prompt_v1.0.md")
EXTS = (".py", ".md", ".csv", ".tsv", ".json", ".html", ".txt", ".bat")


def main():
    apply = "--apply" in sys.argv
    files, hits = 0, 0
    details = []
    for root in ROOTS:
        for dp, dn, fn in os.walk(root):
            if any(s in dp for s in SKIP):
                dn[:] = []
                continue
            for f in fn:
                if not f.lower().endswith(EXTS):
                    continue
                p = os.path.join(dp, f)
                if any(s in p for s in SKIP):
                    continue
                try:
                    s = open(p, encoding="utf-8").read()
                except UnicodeDecodeError:
                    continue
                n = 0
                for old, new in RULES:
                    c = s.count(old)
                    if c:
                        s = s.replace(old, new)
                        n += c
                if n:
                    files += 1
                    hits += n
                    details.append((n, p))
                    if apply:
                        open(p, "w", encoding="utf-8", newline="").write(s)
    for n, p in details:
        print(f"{n:>3} 处  {p}")
    print(f"\n{'已落盘' if apply else '预演'}：{files} 个文件，{hits} 处替换")


if __name__ == "__main__":
    main()
