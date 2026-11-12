# -*- coding: utf-8 -*-
r"""distribute_scripts.py — 把 ★主线 的脚本按「入口 + 依赖闭包」分发到 8 个 Skill

为什么需要它
------------
Skill 要能单独拷走就跑，就必须自带脚本；但脚本之间有 import 依赖
（实测 28 个脚本互相引用），手写清单必漏。本脚本用 AST 算传递闭包，
闭包完整才算通过。

规则
----
· CORE 里写「入口脚本」，依赖由程序补，不手写
· 目标目录里不在闭包内的旧脚本会被删掉（避免残留过时版本）
· 每个 Skill 分成入口与依赖两类打印，便于核对
· --check 只比对不写盘

用法
----
  python distribute_scripts.py            # 分发
  python distribute_scripts.py --check    # 只看会不会缺
"""
import ast
import pathlib
import shutil
import sys

SRC = pathlib.Path(r"D:/Codex/Nikke/Nikke_UpdateMethod/05_脚本/主线")
DST = pathlib.Path(r"D:/Codex/Nikke/Nikke_UpdateMethod/02_Skills/nikke-version-update")

# 入口脚本（会直接写在 SKILL.md 命令里的那些）。依赖不用写，程序算。
# 各 Skill 手写的入口，不在主线里、也不许被当作陈旧文件清掉
KEEP = {"run"}

CORE = {
    "01-baseline-diff": ["catalog_stat", "nkdb_dec", "diff_keys",
                         "make_baseline_v2", "key_families"],
    "02-bundle-pull":   ["locate", "pull_bundle", "pull_chunks", "assemble",
                         "pull_batch", "pull_lsc", "scan_bundle_tags", "verify_pull",
                         "pull_boss_assets"],
    "03-asset-extract": ["runlib", "dump_skill_icons", "lsc_sprite", "export_costume",
                         "export_glb", "fix_glb_offset", "pose_from_clip",
                         "render_monster_standee", "render_monster_xray", "verify_skin",
                         "pull_monster_art", "scan_map_monsters",
                         "build_bgm", "build_voice_pack"],
    "04-static-tables": ["runlib", "list_lss_tables", "nkdb_dec",
                         "event_template_probe", "profile_assets"],
    "05-text-locale":   ["export_locale", "merge_story", "build_story_all",
                         "build_event_story", "build_voice_pack", "pull_lsc",
                         "search_locale"],
    "06-spine-render":  ["runlib", "check_gif", "export_lobby_gif", "export_cutscene_gif",
                         "export_spine", "pull_spine", "render_spine"],
    "07-battle-scene":  ["runlib", "build_battle_scene", "render_battle_scene", "render_overview",
                         "mark_charge", "mark_charge_multi",
                         "scan_charge_points", "scan_charge_multi",
                         "extract_map_points", "build_map_tables", "render_map"],
    "08-deliver-pdf":   ["check_pages", "make_pdf_v2", "build_inventory",
                         "_refresh_manifest", "append_manifest", "_dedupe_hardlink"],
}


def local_imports(path: pathlib.Path, known: set) -> set:
    """解析一个脚本 import 了哪些「同目录脚本」。只认 known 里的名字。"""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    out = set()
    for node in ast.walk(tree):
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods = [node.module.split(".")[0]]
        out.update(m for m in mods if m in known)
    return out


def main():
    check = "--check" in sys.argv
    files = {p.stem: p for p in SRC.glob("*.py")}
    known = set(files)

    rc = 0
    for sk, cores in CORE.items():
        missing = [c for c in cores if c not in files]
        if missing:
            print(f"[FAIL] {sk}: entry script(s) not found: {missing}")
            rc = 1
            continue

        # 传递闭包
        closure, stack = set(), list(cores)
        while stack:
            s = stack.pop()
            if s in closure:
                continue
            closure.add(s)
            stack.extend(local_imports(files[s], known) - closure)

        deps = sorted(closure - set(cores))
        target = DST / sk / "scripts"
        if check:
            print(f"{sk:20s} entry {len(cores):2d} + dep {len(deps):2d} = {len(closure):2d}")
            continue

        target.mkdir(parents=True, exist_ok=True)
        for old in target.glob("*.py"):
            # KEEP 里的文件是各 Skill 手写的入口（run.py），不由主线分发，
            # 但也不能当陈旧文件删掉
            if old.stem not in closure and old.stem not in KEEP:
                old.unlink()
        for s in sorted(closure):
            shutil.copy2(files[s], target / f"{s}.py")

        print(f"{sk:20s} entry {len(cores):2d} + dep {len(deps):2d} = {len(closure):2d}")
        if deps:
            print(f"{'':20s} auto: {', '.join(deps)}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
