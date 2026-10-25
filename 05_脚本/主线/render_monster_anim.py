# -*- coding: utf-8 -*-
"""把任意 clip 的任意帧渲出来，并合成「序列带 / 叠影图」，用来表现游戏内的动态。

为什么单独写：单帧永远表现不出「碎片悬浮 / 装甲开合」。
之前的 4 张 idle 立绘是固定帧，用户看到的是一张静止图，判断不了动态。

用法：
  python render_monster_anim.py xba003 2phase appearance
  python render_monster_anim.py xba003 2phase appearance 8      # 取 8 帧
  python render_monster_anim.py all                              # 全部预设

产物（out/monster_anim/）：
  <tag>_<clip>_f000.png ...        单帧
  <tag>_<clip>_序列.png            横排序列带
  <tag>_<clip>_叠影.png            多帧平均叠加（残影，表现运动轨迹）
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import render_monster_standee as R
import pose_from_clip as P

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\monster_anim")

MON = {
    "xba003": "spotmonster_xba003_dmtr.bundle",
    "eba002": "spotmonster_eba002_hsta.bundle",
}
# key -> (模型, clip 包, 阶段, 中文说明)
CLIP = {
    "appear12":  ("xba003", "anim_xba003_12phase_appearance.bundle", "1phase", "1→2 阶段过渡（1 阶段骨架上播）"),
    "idle2":     ("xba003", "anim_xba003_2phase_idle.bundle",        "2phase", "2 阶段 idle"),
    "skillidle2": ("xba003", "anim_xba003_2phase_skillidle.bundle",  "2phase", "2 阶段技能待机"),
    "idle1":     ("xba003", "anim_xba003_1phase_idle.bundle",        "1phase", "1 阶段 idle"),
    "idle2e":    ("eba002", "anim_eba002_2phase_idle.bundle",        "2phase", "2 阶段 idle"),
    "intro01":   ("eba002", "anim_eba002_2phase_intro01.bundle",     "1phase", "2 阶段出场 01（1 阶段骨架上播）"),
    "intro02":   ("eba002", "anim_eba002_2phase_intro02.bundle",     "2phase", "2 阶段出场 02"),
    "groggy":    ("eba002", "anim_eba002_2phase_groggy.bundle",      "2phase", "2 阶段破防循环"),
    "idle1e":    ("eba002", "anim_eba002_1phase_idle.bundle",        "1phase", "1 阶段 idle"),
}


def font(sz):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def run(tag_key, nframe=8, phase=None):
    tag, cb, ph, label = CLIP[tag_key]
    mb = DEV / MON[tag]
    cbp = DEV / cb
    phase = phase or ph

    head = P.pose_for(mb, cbp, ph, 0)
    F = head["stats"]["frames"]
    frames = [int(round(x)) for x in np.linspace(0, F - 1, nframe)]

    outs = []
    for f in frames:
        dst = OUT / f"{tag}_{tag_key}_f{f:03d}.png"
        pr = P.pose_for(mb, cbp, ph, f)
        r = R.render(mb, dst, f"{tag} {tag_key} f{f}", phase=ph, pose=pr["pose"])
        if r:
            outs.append((f, dst))
        print(f"   帧 {f:3d}/{F}  →  {'ok' if r else 'skip'}  "
              f"骨骼 {pr['stats']['bones_hit']}")

    if not outs:
        print("   !! 无有效帧")
        return

    ims = [Image.open(p).convert("RGBA") for _, p in outs]
    w, h = ims[0].size
    gap, top = 10, 46
    sheet = Image.new("RGB", (len(ims) * (w + gap) + gap, h + top + gap), (250, 251, 253))
    d = ImageDraw.Draw(sheet)
    d.text((gap, 12), f"{tag} {ph}　{label}（共 {F} 帧，取 {len(ims)} 帧）",
           fill=(20, 24, 32), font=font(22))
    for i, (im, (f, _)) in enumerate(zip(ims, outs)):
        x = gap + i * (w + gap)
        sheet.paste(im.convert("RGB"), (x, top), im)
        d.text((x + 4, top + h + 2), f"f{f}", fill=(90, 98, 110), font=font(14))
    sp = OUT / f"{tag}_{tag_key}_序列.png"
    sheet.save(sp)
    print("  ->", sp.name)

    # 叠影：把多帧按 alpha 取最大（保留每帧最亮处），表现运动包络
    base = np.array(ims[0], np.float32)
    acc = base
    for im in ims[1:]:
        a = np.array(im, np.float32)
        acc = np.maximum(acc, a)
    ghost = Image.fromarray(acc.astype(np.uint8))
    gp = OUT / f"{tag}_{tag_key}_叠影.png"
    ghost.save(gp)
    print("  ->", gp.name)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a = sys.argv[1:]
    if not a or a[0] == "all":
        for k in CLIP:
            print(f"\n===== {k}")
            run(k)
        return
    n = 8
    if a[0] == "eba002":
        key = "idle2e"
    else:
        key = "idle2"
    if len(a) >= 2 and a[1] in CLIP:
        key = a[1]
    if len(a) >= 3:
        n = int(a[2])
    print(f"===== {key}  {n} 帧")
    run(key, n)


if __name__ == "__main__":
    main()
