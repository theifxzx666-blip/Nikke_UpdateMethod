# -*- coding: utf-8 -*-
"""把渲染结果整理成「一眼能数清 14 种」的产物目录。

上一版把立绘拆成 立绘/（8 张英文名）、立绘_大地图/（6 张）、关底BOSS_立绘/（4 张）三个目录，
打开任一个都只看到「那几个」，所以被问「说新增了怎么还是只有那几个」。这里改成单目录 + 序号 + 中文名。
"""
import shutil
from pathlib import Path

SRC_MON = Path(r"D:/Codex/临时/nikke_intl_20261029/out/monster_standee")
SRC_XRY = Path(r"D:/Codex/临时/nikke_intl_20261029/out/monster_xray")
BASE = Path(r"D:/Codex/Nikke/Nikke_Skills/版本更新/03_历史/20260813_国际服/05_主线_47-48章/07_关卡莱彻")
RECY = Path(r"D:/Codex/Nikke/Nikke_Skills/拆包/05_回收站/20261025_莱彻立绘_旧版")

# 序号, 中文名, 型号, 源文件 stem, 来源
ITEMS = [
    (1, "指环",   "xmg001", "xmg001", "关卡"),
    (2, "海马",   "xma003", "xma003", "关卡"),
    (3, "太阳",   "xeg006", "xeg006", "关卡+大地图"),
    (4, "倒吊者", "xea003", "xea003", "关卡+大地图"),
    (5, "三体",   "eea002", "eea002", "关卡"),
    (6, "双尾",   "meg006", "meg006", "关卡"),
    (7, "穿刺",   "mea001", "mea001", "关卡"),
    (8, "陆蟹",   "mmg005", "mmg005", "关卡"),
    (9, "太空人", "xea002", "xea002", "大地图"),
    (10, "狂笑",  "xea004", "xea004", "大地图"),
    (11, "信差",  "xmg002", "xmg002", "大地图"),
    (12, "肋骨",  "xmg003", "xmg003", "大地图"),
]
BOSS = [
    (13, "安尼希利奥", "xba003", ["xba003_1phase", "xba003_2phase"]),
    (14, "莉贝雷利奥躯体", "eba002", ["eba002_1phase", "eba002_2phase"]),
]

def main():
    RECY.mkdir(parents=True, exist_ok=True)
    # 旧目录进回收站（禁物理删除）
    for name in ("立绘", "立绘_大地图", "关底BOSS_立绘"):
        p = BASE / name
        dst = RECY / name
        if p.exists() and not dst.exists():
            shutil.move(str(p), str(dst))
            print(f"回收 {name}/")
    for f in ("关卡莱彻_总览.png", "关卡莱彻_总览_v3.png"):
        p, dst = BASE / f, RECY / f
        if p.exists() and not dst.exists():
            shutil.move(str(p), str(dst))
            print(f"回收 {f}")

    out = BASE / "立绘"; out.mkdir(exist_ok=True)
    xo = BASE / "透视"; xo.mkdir(exist_ok=True)

    n = 0
    for idx, zh, tag, stem, _src in ITEMS:
        for folder, srcdir, suffix in ((out, SRC_MON, "_立绘"), (xo, SRC_XRY, "_透视")):
            s = srcdir / f"{stem}{suffix}.png"
            if not s.exists():
                print(f"  !! 缺 {s.name}"); continue
            shutil.copy2(s, folder / f"{idx:02d}_{zh}_{tag}.png")
            n += 1
    for idx, zh, tag, stems in BOSS:
        for folder, srcdir, suffix in ((out, SRC_MON, "_立绘"), (xo, SRC_XRY, "_透视")):
            for st in stems:
                s = srcdir / f"{st}{suffix}.png"
                if not s.exists():
                    print(f"  !! 缺 {s.name}"); continue
                ph = "1阶段" if "1phase" in st else "2阶段"
                shutil.copy2(s, folder / f"{idx:02d}_{zh}_{tag}_{ph}.png")
                n += 1
    print(f"\n落地 {n} 个文件")
    for folder in (out, xo):
        fs = sorted(folder.glob("*.png"))
        print(f"\n[{folder.name}] {len(fs)} 张")
        for p in fs:
            print("   ", p.name, f"{p.stat().st_size/1024:.0f} KB")

if __name__ == "__main__":
    main()
