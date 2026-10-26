# -*- coding: utf-8 -*-
"""从 standing bundle 里导出 Spine 三件套（.skel / .atlas / .png）。

NIKKE 的大厅角色是 Spine 4.1 骨骼动画，资源形态实测：
  TextAsset  <char>_<idx>.skel   Spine 4.1.20 二进制骨架（含 animation 列表）
  TextAsset  <char>_<idx>.atlas  文本图集描述（含 pma / scale）
  Texture2D  <char>_<idx>        2048×2048 图集（多角色共用一张很常见）

用法：
  python export_spine.py <bundle 路径> <输出目录> [文件前缀]
"""
import sys
from pathlib import Path

import UnityPy


def main():
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    prefix = sys.argv[3] if len(sys.argv) > 3 else None
    out.mkdir(parents=True, exist_ok=True)

    env = UnityPy.load(str(src))
    got = {"skel": None, "atlas": None, "tex": None}
    for o in env.objects:
        if o.type.name == "TextAsset":
            d = o.read()
            raw = bytes(d.m_Script.encode("utf-8", "surrogateescape"))
            nm = str(d.m_Name)
            if nm.endswith(".skel"):
                got["skel"] = (nm, raw)
            elif nm.endswith(".atlas"):
                got["atlas"] = (nm, raw)
        elif o.type.name == "Texture2D":
            d = o.read()
            if got["tex"] is None:
                got["tex"] = (str(d.m_Name), d)

    if not (got["skel"] and got["atlas"]):
        raise SystemExit(f"未找到 skel/atlas：{src.name}")

    base = prefix or Path(got["skel"][0]).stem
    (out / f"{base}.skel").write_bytes(got["skel"][1])
    (out / f"{base}.atlas").write_bytes(got["atlas"][1])

    tex_name = None
    if got["tex"]:
        nm, d = got["tex"]
        img = d.image
        if img is None:
            raise SystemExit("Texture2D 解码失败")
        png = out / f"{nm}.png"
        img.save(png)
        tex_name = nm
        print(f"  texture {nm} {img.size[0]}x{img.size[1]} mode={img.mode}")

    # atlas 里写的第一行就是它期望的贴图文件名，核对一下
    first = got["atlas"][1].split(b"\r\n")[0].decode("utf-8", "replace")
    print(f"  skel {len(got['skel'][1]):,}B  atlas {len(got['atlas'][1]):,}B  期望贴图={first}")
    if tex_name and first != f"{tex_name}.png":
        # 名字对不上时补一个副本，让 spine runtime 能直接加载
        from shutil import copyfile
        copyfile(out / f"{tex_name}.png", out / first)
        print(f"  贴图名不匹配 -> 另存 {first}")

    print(f"  -> {out} / {base}.skel + .atlas + {first}")


if __name__ == "__main__":
    main()
