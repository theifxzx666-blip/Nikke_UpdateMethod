# -*- coding: utf-8 -*-
"""核心件清单：每个型号有没有「独立的核心几何体」，还是核心只画在贴图上。

回答「为什么有些莱彻看不到核心」：
  A 有 cm_core_* 网格  → 核心是独立几件，但被外壳整件包住，正常立绘里被遮
  B 无 cm_core 网格    → 核心不是几何体，是贴图上的发光区域，渲染出来就是一块亮的平面
"""
import json
import numpy as np
import UnityPy
from pathlib import Path
from UnityPy.helpers.MeshHelper import MeshHandler
import render_monster_standee as R

DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")
BASE = Path(r"D:/Codex/Nikke/Nikke_Skills/版本更新/03_历史/20260813_国际服/05_主线_47-48章/07_关卡莱彻")

ITEMS = [
    ("01", "指环", "xmg001"), ("02", "海马", "xma003"), ("03", "太阳", "xeg006"),
    ("04", "倒吊者", "xea003"), ("05", "三体", "eea002"), ("06", "双尾", "meg006"),
    ("07", "穿刺", "mea001"), ("08", "陆蟹", "mmg005"), ("09", "太空人", "xea002"),
    ("10", "狂笑", "xea004"), ("11", "信差", "xmg002"), ("12", "肋骨", "xmg003"),
    ("13", "安尼希利奥", "xba003"), ("14", "莉贝雷利奥躯体", "eba002"),
]

rows = []
for idx, zh, tag in ITEMS:
    b = next((p for p in [DEV / f"spotmonster_{tag}_dmtr.bundle",
                          DEV / f"spotmonster_{tag}_hsta.bundle"] if p.exists()), None)
    if b is None:
        b = next(iter(sorted(DEV.glob(f"spotmonster_{tag}_*.bundle"))), None)
    if b is None:
        print("!! 缺包", tag); continue
    env = UnityPy.load(str(b))
    meshes, cores = [], []
    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        smr = o.read(); mesh = smr.m_Mesh.read()
        h = MeshHandler(mesh); h.process()
        if not h.m_Vertices:
            continue
        nv = len(h.m_Vertices)
        T = [t for sub in h.get_triangles() for t in sub if len(t) == 3] if h.m_IndexBuffer else []
        meshes.append((mesh.m_Name, nv, len(T)))
        if "cm_core" in mesh.m_Name:
            cores.append((mesh.m_Name, nv, len(T)))
    if cores:
        kind = "A 独立核心件"
        core_desc = " / ".join(f"{n}({v}顶点/{t}三角)" for n, v, t in cores)
    else:
        kind = "B 无独立核心件"
        core_desc = "—（核心为贴图上的发光区，非几何体）"
    rows.append([idx, zh, tag, str(len(meshes)), kind, core_desc,
                 " / ".join(m[0] for m in meshes)])

hdr = ("# 莱彻核心件清单（2026-10-25 三修）\n"
       "# A = 包里存在名字含 cm_core 的独立网格：核心是几何体，但只从装甲缝隙里露出 0.35~0.79% 画面，\n"
       "#     正常立绘里几乎看不出（数值见 装配件_可见性.tsv，透视版见 透视/）\n"
       "# B = 包里没有 cm_core 网格：核心不是几何体，是贴图上的发光区域，所以「看不到核心」不是漏渲\n"
       "# 所有型号的全部 SkinnedMeshRenderer 都已渲染（另有 monster_shadow 属地面投影，已排除）\n"
       "序号\t中文名\t型号\t渲染网格数\t核心类型\t核心网格（顶点/三角）\t全部网格\n")
out = BASE / "核心件清单.tsv"
out.write_text("\n".join([hdr] + ["\t".join(r) for r in rows]) + "\n", encoding="utf-8-sig")
print(f"-> {out.name}  {len(rows)} 行\n")
for r in rows:
    print(f"  {r[0]} {r[1]:8s} {r[2]:8s} 网格{r[3]:>3s}  {r[4]}  {r[5][:52]}")
