# -*- coding: utf-8 -*-
"""文档路径体检：把 md 里反引号包着的路径挨个落地核对，找出「写了但不存在」的。

为什么需要：迁移/改名之后文档里的路径一定会残留旧的（E-31 / E-33）。
grep 只能证明「字符串变了」，只有落地 exists() 才能证明「还能用」。

判定口径
--------
- 只查**带扩展名的文件**与**以分隔符结尾的目录**；`layers/fit/fitq` 这类参数串自动跳过
- 裸文件名（`make_pdf_v2.py`）在整个 ROOT 下按文件名索引查找，不要求写全路径
- 相对路径（`00_规范/易错清单.md`）按「ROOT 下任一路径以它结尾」匹配，兼容不同层级
- `<ROOT>` / `{期次}` / `*` 等占位符一律跳过

用法：
  python check_doc_paths.py                 # 默认 AGENTS.md + 00_规范 + 02_Skills
  python check_doc_paths.py <md…>
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# 默认指向作者本机工程根；换机器 / 换 clone 位置时用 DOC_ROOT 覆盖
ROOT = Path(os.environ.get("DOC_ROOT") or Path(__file__).resolve().parents[2])
EXT = r"(?:md|py|tsv|csv|json|html|htm|txt|pdf|lss|lsc|dec|skel|atlas|png|gif|webp|glb|wav|mp3|bat|ps1)"
FILE_TAIL = re.compile(rf"\.{EXT}$", re.I)
SPAN = re.compile(r"`([^`\n]{2,140})`")
SKIP = ("<", ">", "{", "}", "*", "|", "$", "％", "…", "://")
# 这些文件名本身就带占位/示例语义，不当作要落地的路径
SKIP_SPAN = ("YYYY-MM-DD", "xxx_", ".workbuddy/", "首帧.png", "..", " ")
# WORK 工作区里的相对路径（不在 ROOT 下，按约定由 <WORK> 提供），只 WARN
WORK_PREFIX = ("spine_render", "out", "dec_cache", "device", "spine_js",
               "assets", "files", "mpdump", "spine/", "拆包/")
# 国服产线在 <CN_ROOT> 下的固定工作目录，同样只 WARN
WORK_PREFIX_CN = ("cat_all", "lss", "uc_probe", "saus", "apkmeta")
# 设备侧绝对路径（Android）与 PC 客户端内部路径（如国服 runtime_data\...），只 WARN
DEVICE_PREFIX = ("/storage/", "/sdcard/", "/data/", "/system/", "runtime_data/", "nikke_Data/")
# 文档里的 `00_资源库\...` 实际位于 `拆包\00_资源库\...`（跨根引用，按需 exists 探测，不做全量索引）
ALIAS_ROOT = ("00_资源库/", Path(r"D:\Codex\Nikke\Nikke_Skills\拆包"))
# 运行时才生成的产物名（文档里作为「会产出什么」出现），只 WARN
OUTPUT_NAME = {"raw_keys.tsv", "00_导出报告.tsv", "00_活动清单.tsv", "_报告.pdf",
               "基线说明.md"}
# 计划中、尚未写的脚本（文档里作为「下一步要做什么」出现），只 WARN
PLANNED = {"map_cache.py"}
# 形如 `a2.example.com/path.json` 的域名相对路径，不是本地路径，跳过
DOMAIN_PATH = re.compile(r"^[a-z0-9][a-z0-9\-]*(\.[a-z0-9\-]+)*\.[a-z]{2,6}/", re.I)

# 原始 Prompt 已于 10-26 移入 06_回收站，ROOT 内不再有这两份，白名单留空即可。
# 若有人把它们拷回 00_规范，不要加白名单跳过——那等于让 190 KB 的旧口径重新参与引用。
SKIP_FILE = ()
# 额外索引的外部目录（ROOT 之外的既定资源位置）
EXTRA_ROOTS = [Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")]


def norm(s: str) -> str:
    s = s.strip().strip("\"'").replace("\\", "/")
    return s.rstrip("/")


def main() -> None:
    targets = [Path(x) for x in sys.argv[1:]] or (
        [ROOT / "AGENTS.md"]
        + sorted((ROOT / "00_规范").rglob("*.md"))
        + sorted((ROOT / "02_Skills").rglob("*.md")))

    # 建索引：全量相对路径（小写）+ 文件名 → 是否存在
    rels, names = set(), set()
    for base in [ROOT] + EXTRA_ROOTS:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            try:
                rels.add(p.relative_to(ROOT).as_posix().lower()
                         if base == ROOT else p.as_posix().lower())
                names.add(p.name.lower())
            except ValueError:
                names.add(p.name.lower())

    bad, warn, checked, skipped = [], [], 0, 0
    for f in targets:
        if not f.exists():
            print(f"[!] 文件本身不存在：{f}")
            continue
        if any(k in f.name for k in SKIP_FILE):
            continue
        txt = f.read_text(encoding="utf-8")
        done = set()
        for span in SPAN.findall(txt):
            s = norm(span)
            if not s or any(t in span for t in SKIP) or any(t in span for t in SKIP_SPAN):
                skipped += 1
                continue
            if DOMAIN_PATH.match(s):                          # 域名下的路径，不是本地路径
                skipped += 1
                continue
            if s.startswith(DEVICE_PREFIX):                   # Android 设备路径
                warn_early = True
            else:
                warn_early = False
            if s.startswith(".") and FILE_TAIL.search(s) and "/" not in s:
                skipped += 1                                  # `.lss` / `.png` 这种纯扩展名
                continue
            is_dir = span.strip().endswith(("/", "\\"))
            if not (FILE_TAIL.search(s) or is_dir):
                skipped += 1
                continue
            if (f, s) in done:
                continue
            done.add((f, s))
            checked += 1

            if warn_early:                                    # 设备路径，本地必然不存在
                warn.append((f, span))
                continue

            if re.match(r"^[a-zA-Z]:", s):                     # 绝对路径
                ok = Path(s.replace("/", "\\")).exists() or (s.lower() in rels)
            elif s.lower().startswith(ALIAS_ROOT[0]) or s.lower() == "00_资源库":   # 跨根：00_资源库 → 拆包\00_资源库
                ok = (ALIAS_ROOT[1] / s.replace("/", "\\")).exists()
            elif "/" in s:
                ok = s.lower() in rels or any(r.endswith("/" + s.lower()) for r in rels)
            else:
                ok = s.lower() in names
            if ok:
                continue
            low = s.lower()
            base = low.rsplit("/", 1)[-1]
            if base in {x.lower() for x in OUTPUT_NAME} or base.startswith("_"):
                warn.append((f, span))            # 运行时产物，跑完才有
            elif base in {x.lower() for x in PLANNED}:
                warn.append((f, span))            # 计划中的脚本，还没写
            elif low.startswith(WORK_PREFIX) or low.split("/", 1)[0] in WORK_PREFIX_CN:
                warn.append((f, span))            # <WORK> / <CN_ROOT> 工作区
            else:
                bad.append((f, span))

    print(f"扫描 {len(targets)} 个 md｜检查 {checked} 处路径｜跳过 {skipped} 处非路径片段")
    if warn:
        print(f"\n[WARN] {len(warn)} 处是 <WORK> 工作区相对路径（不在 ROOT 下，属正常）：")
        for f, span in warn[:12]:
            print(f"  `{span}`")
    if not bad:
        print("\n[OK] ROOT 内路径全部落地存在")
        return
    print(f"\n[FAIL] {len(bad)} 处落地不到：")
    for f, span in bad:
        try:
            r = f.relative_to(ROOT).as_posix()
        except ValueError:
            r = str(f)
        print(f"  {r}\t`{span}`")
    sys.exit(1)


if __name__ == "__main__":
    main()
