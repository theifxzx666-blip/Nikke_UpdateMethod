# -*- coding: utf-8 -*-
r"""dump_skill_icons.py — 从 icons-skill(hd) 包里按名字导出技能图标

用法：
  python dump_skill_icons.py <bundle> <outdir> name1 name2 ...

判据：Shield 不是单独对象，图标是 Texture2D；Sprite 只是包装。
导出 PGBA 前先转 RGBA（原图多为 RGBA32，少数 DXT5）。
"""
import sys, os
import UnityPy

def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    bundle, outdir = sys.argv[1], sys.argv[2]
    want = set(sys.argv[3:])
    os.makedirs(outdir, exist_ok=True)

    env = UnityPy.load(bundle)
    got, miss = [], []
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        nm = d.m_Name
        if nm not in want:
            continue
        p = os.path.join(outdir, nm + ".png")
        d.image.save(p)
        got.append((nm, d.m_Width, d.m_Height, os.path.getsize(p)))
    for nm in sorted(want):
        if nm not in {g[0] for g in got}:
            miss.append(nm)
    for nm, w, h, sz in sorted(got):
        print("OK  %-34s %4dx%-4d %6d B" % (nm, w, h, sz))
    if miss:
        print("MISS " + ", ".join(miss))
    return 0

if __name__ == "__main__":
    sys.exit(main())
