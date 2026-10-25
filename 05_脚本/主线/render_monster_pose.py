# -*- coding: utf-8 -*-
"""把 idle clip 的姿态套到骨架上重渲，出「绑定姿态 vs 关卡内 idle 姿态」对照。

用法：
  python render_monster_pose.py            # 全部 4 份
  python render_monster_pose.py xba003 2phase
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import render_monster_standee as R
import pose_from_clip as P

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\monster_pose")

CASES = [
    ("xba003", "spotmonster_xba003_dmtr.bundle", "1phase", "anim_xba003_1phase_idle.bundle"),
    ("xba003", "spotmonster_xba003_dmtr.bundle", "2phase", "anim_xba003_2phase_idle.bundle"),
    ("eba002", "spotmonster_eba002_hsta.bundle", "1phase", "anim_eba002_1phase_idle.bundle"),
    ("eba002", "spotmonster_eba002_hsta.bundle", "2phase", "anim_eba002_2phase_idle.bundle"),
]


def font(sz):
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    want = sys.argv[1:] or None
    rows = []
    for tag, mb, ph, cb in CASES:
        if want and not (want[0] in tag and (len(want) < 2 or want[1] in ph)):
            continue
        mbp, cbp = DEV / mb, DEV / cb
        head = P.pose_for(mbp, cbp, ph, 0)
        F = head["stats"]["frames"]
        frames = [0, F // 2, F - 1]

        # 绑定姿态
        r0 = R.render(mbp, OUT / f"{tag}_{ph}_bind.png", f"{tag}_{ph} 绑定", phase=ph)
        # idle 三帧
        outs = [OUT / f"{tag}_{ph}_bind.png"]
        for f in frames:
            pr = P.pose_for(mbp, cbp, ph, f)
            r = R.render(mbp, OUT / f"{tag}_{ph}_idle_{f:03d}.png",
                         f"{tag}_{ph} idle f{f}", phase=ph, pose=pr["pose"])
            if r:
                outs.append(OUT / f"{tag}_{ph}_idle_{f:03d}.png")
                rows.append(dict(tag=tag, phase=ph, frame=f, frames=F,
                                 bones=pr["stats"]["bones_hit"],
                                 rot=pr["stats"]["rot_curves"],
                                 moved=pr["stats"]["rot_unit"]))

        # 拼四条横排对照
        ims = [Image.open(p).convert("RGBA") for p in outs]
        labels = ["绑定姿态"] + [f"idle 第 {f} 帧" for f in frames[:len(ims) - 1]]
        gap, top = 12, 44
        w, h = ims[0].size
        sheet = Image.new("RGB", (len(ims) * (w + gap) + gap, h + top + gap), (250, 251, 253))
        d = ImageDraw.Draw(sheet)
        d.text((gap, 12), f"{tag} {ph}　绑定姿态 vs 关卡内 idle（{F} 帧 @30fps）",
               fill=(20, 24, 32), font=font(22))
        for i, (im, lb) in enumerate(zip(ims, labels)):
            x = gap + i * (w + gap)
            sheet.paste(im.convert("RGB"), (x, top), im)
            d.text((x + 6, top + h + 2), lb, fill=(90, 98, 110), font=font(16))
        sp = OUT / f"{tag}_{ph}_对照.png"
        sheet.save(sp)
        print("->", sp.name)

    print("\n帧数据：")
    for r in rows:
        print("  ", r)


if __name__ == "__main__":
    main()
