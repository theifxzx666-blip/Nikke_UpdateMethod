# -*- coding: utf-8 -*-
r"""sync_skills.py — Skill 唯一源 → 运行副本的单向同步，附带「自足性」体检

背景
----
同一批 SKILL.md 曾同时存在于三处：
  · C:\Users\1E_6\.workbuddy\skills\           （运行副本，WorkBuddy 加载用）
  · <项目>\版本更新\02_Skills\nikke-version-update\  （项目内副本）
  · D:\Codex\Nikke\Nikke_UpdateMethod\02_Skills\...  （方法论仓库，有 git）
实测 6 个 Skill 里已有 2 个在三处之间漂移（md5 不同、行数相同，属静默改写）。
本脚本把方向收敛成单向：**只从唯一源写到运行副本，永不反向**。

自足性（本脚本存在的第二个理由）
--------------------------------
SKILL.md 里写了 `python xxx.py`，但 `scripts\` 里没有这个文件 —— 这种 Skill 单独拷走
就一行都跑不起来。实测 6 个 Skill 共引用 16 个 .py，只有 6 个在目录内，缺 10 个。
所以 --apply 前先体检，缺脚本的 Skill 直接拒绝同步，不静默放过。

用法
----
  python sync_skills.py --check                 # 只比对，列漂移 + 列缺失脚本
  python sync_skills.py --check --verbose       # 再列出每个文件的 md5
  python sync_skills.py --apply                 # 单向同步（缺脚本的 Skill 会被跳过并报错）
  python sync_skills.py --apply --force         # 明知缺脚本也要同步
  python sync_skills.py --check --src <目录> --dst <目录>

退出码
------
  0 = 无漂移 / 同步成功
  1 = 有漂移 / 有 Skill 因不自足被跳过
  2 = 路径不对（源目录不存在）

约定
----
· 运行副本的目录名取自 SKILL.md frontmatter 的 name 字段，**不从源目录名推**
  （源目录叫 `01-baseline-diff`，副本要叫 `nikke-baseline-diff`）
· 只增改不删：副本里多出来的目录只报告，由人决定去留
· 复制时整目录覆盖，`__pycache__` 与 `.git` 跳过
"""

import argparse
import hashlib
import re
import shutil
import sys
from pathlib import Path

# 默认路径：本机实际布局。换机器用 --src / --dst 覆盖，不改这里。
DEFAULT_SRC = Path(r"D:\Codex\Nikke\Nikke_UpdateMethod\02_Skills\nikke-version-update")
DEFAULT_DST = Path(r"C:\Users\1E_6\.workbuddy\skills")

# 复制时跳过的目录名（缓存、版本库、npm 依赖 —— 都不是 Skill 的内容）。
# vendor 里是 @esotericsoftware/spine-player 的产物，由 renderer\package.json
# 声明、npm install 生成，不入库也不参与同步；否则每次 apply 都会把本地依赖删掉。
SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode", "node_modules", "vendor"}

# 从 SKILL.md 提取 .py 文件名。只认反引号里或命令行里的裸文件名，
# 避免把 `mkdocs.py` 这种正文里的例子也算进来 —— 加前缀要求：必须是 word 边界上的 xxx.py
PY_RE = re.compile(r"(?<![\w./\\-])([A-Za-z_][A-Za-z0-9_]*\.py)\b")


def md5_of(path: Path) -> str:
    """算文件 md5，用来判断两处内容是否一致（比 mtime 可靠）。"""
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_frontmatter_name(skill_md: Path) -> str:
    """读 SKILL.md 开头两行 --- 之间的 name 字段。读不到就抛错，不猜。"""
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        raise ValueError(f"{skill_md}: 没有 frontmatter（开头缺 --- 块）")
    for line in m.group(1).split("\n"):
        line = line.strip()
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("\"'")
            if not name:
                raise ValueError(f"{skill_md}: frontmatter 的 name 是空的")
            return name
    raise ValueError(f"{skill_md}: frontmatter 里没有 name 字段")


def collect_skills(src: Path) -> dict:
    """扫源目录下所有「含 SKILL.md 的一级子目录」，返回 {skill_name: 源目录}。"""
    found = {}
    for d in sorted(src.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        found[read_frontmatter_name(d / "SKILL.md")] = d
    return found


def check_self_sufficient(skill_dir: Path):
    """自足性体检：SKILL.md 提到的 .py 是否都在 scripts\\ 下。

    返回 (missing, orphan_hint)：
      missing      = 提到但目录内没有的脚本名（排序后的 list）
      orphan_hint  = scripts\\ 下存在但 SKILL.md 没提的脚本（不算错，仅提示）
    """
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
    # 先把 frontmatter 去掉，避免 description 里的字样被误算
    body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S)

    mentioned = set(PY_RE.findall(body))
    have = {p.name for p in (skill_dir / "scripts").glob("*.py")} if (skill_dir / "scripts").is_dir() else set()

    missing = sorted(mentioned - have)
    orphan = sorted(have - mentioned)
    return missing, orphan


def iter_files(root: Path):
    """遍历目录下所有文件（相对路径），跳过 SKIP_DIRS。"""
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        yield p.relative_to(root)


def compare_one(src_dir: Path, dst_dir: Path) -> dict:
    """比对单个 Skill 的源与副本，返回差异分类。"""
    r = {"added": [], "changed": [], "missing": [], "extra": []}
    if not dst_dir.exists():
        r["missing"] = ["<整个目录不存在>"]
        return r

    s_files = {str(x) for x in iter_files(src_dir)}
    d_files = {str(x) for x in iter_files(dst_dir)}

    for rel in sorted(s_files):
        sp, dp = src_dir / rel, dst_dir / rel
        if rel not in d_files:
            r["added"].append(rel)
        elif md5_of(sp) != md5_of(dp):
            r["changed"].append(rel)

    r["extra"] = sorted(d_files - s_files)
    return r


def cmd_check(src: Path, dst: Path, verbose: bool) -> int:
    skills = collect_skills(src)
    if not skills:
        print(f"[fail] no skill (with SKILL.md) under {src}")
        return 2

    print(f"source  {src}")
    print(f"target  {dst}")
    print(f"skills  {len(skills)}\n")

    drift_total = 0
    bad_total = 0

    for name, sdir in skills.items():
        ddir = dst / name
        missing_py, orphan_py = check_self_sufficient(sdir)
        diff = compare_one(sdir, ddir)

        drift = len(diff["added"]) + len(diff["changed"]) + len(diff["missing"])
        drift_total += drift
        if missing_py:
            bad_total += 1

        state = "OK" if (drift == 0 and not missing_py) else "DRIFT"
        print(f"[{state:5s}] {name}")
        if missing_py:
            print(f"         not self-sufficient, missing {len(missing_py)} script(s):")
            print(f"           {', '.join(missing_py)}")
        if drift:
            print(f"         files need sync: "
                  f"added {len(diff['added'])} / changed {len(diff['changed'])} / "
                  f"missing {len(diff['missing'])}")
        if diff["extra"]:
            print(f"         only in target (left alone): {len(diff['extra'])} file(s)")
        if verbose:
            for rel in diff["added"]:
                print(f"           + {rel}")
            for rel in diff["changed"]:
                print(f"           ~ {rel}")
            for rel in diff["missing"]:
                print(f"           - {rel}")

    print(f"\nsummary: {len(skills)} skill(s), {drift_total} file(s) to sync, "
          f"{bad_total} not self-sufficient")
    return 0 if (drift_total == 0 and bad_total == 0) else 1


def cmd_apply(src: Path, dst: Path, force: bool) -> int:
    skills = collect_skills(src)
    if not skills:
        print(f"[fail] no skill (with SKILL.md) under {src}")
        return 2

    rc = 0
    for name, sdir in skills.items():
        missing_py, _ = check_self_sufficient(sdir)
        if missing_py and not force:
            print(f"[skip] {name}: not self-sufficient, missing {len(missing_py)} script(s)")
            print(f"       {', '.join(missing_py)}")
            print(f"       fix scripts\\ first, or re-run with --force")
            rc = 1
            continue

        ddir = dst / name
        ddir.mkdir(parents=True, exist_ok=True)

        # 先删掉「源侧已没有、目标侧还在」的陈旧文件，但不整目录 rmtree ——
        # 目标侧可能有 vendor / node_modules 这类生成物，rmtree 会连本地依赖一起清掉。
        src_files = {str(x) for x in iter_files(sdir)}
        for rel in sorted({str(x) for x in iter_files(ddir)} - src_files):
            stale = ddir / rel
            if any(part in SKIP_DIRS for part in Path(rel).parts):
                continue
            stale.unlink()

        n = 0
        for rel in sorted(src_files):
            target = ddir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sdir / rel, target)
            n += 1
        print(f"[sync] {name}: {n} file(s) -> {ddir}")

    # 运行副本里多出来的 nikke-* 目录，只报告
    known = set(skills)
    extra = [d.name for d in dst.iterdir()
             if d.is_dir() and d.name.startswith("nikke-") and d.name not in known]
    if extra:
        print(f"\n[note] {len(extra)} nikke-* dir(s) in target have no source, left alone:")
        for e in extra:
            print(f"       {e}")

    print(f"\ndone: {len(skills)} skill(s) synced")
    return rc


def main():
    ap = argparse.ArgumentParser(
        description="Sync skills from the single source to the runtime copy, "
                    "with a self-sufficiency check.")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC, help="single source dir")
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST, help="runtime copy dir")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="compare only, do not write")
    g.add_argument("--apply", action="store_true", help="sync source -> target")
    ap.add_argument("--verbose", action="store_true", help="list every differing file")
    ap.add_argument("--force", action="store_true",
                    help="apply even if a skill is not self-sufficient")
    a = ap.parse_args()

    if not a.src.is_dir():
        print(f"[fail] source not found: {a.src}")
        return 2
    if not a.dst.is_dir():
        print(f"[fail] target not found: {a.dst}")
        return 2

    if a.check:
        return cmd_check(a.src, a.dst, a.verbose)
    return cmd_apply(a.src, a.dst, a.force)


if __name__ == "__main__":
    sys.exit(main())
