# -*- coding: utf-8 -*-
"""关底 BOSS 装配件构成表。

为什么不用 MonsterPartsTable 对齐：该表 PartsObject 登记的是预制体根节点
（xba003_1phase_var / phase_body）与碰撞体（parts_col_701…），与渲染网格名不是一套命名，
硬对齐只会得到满屏「否」。这里只列包里真实存在的 SkinnedMeshRenderer。
"""
import json
import UnityPy
from pathlib import Path
from UnityPy.helpers.MeshHelper import MeshHandler
import render_monster_standee as R

DEV = Path(r"D:/Codex/临时/nikke_intl_20261029/device")
SD = Path(r"D:/Codex/Nikke/Nikke_Skills/拆包/02_Skills/mpdump/out")
DST = Path(r"D:/Codex/Nikke/Nikke_Skills/版本更新/03_历史/20260813_国际服"
           r"\05_主线_47-48章\07_关卡莱彻")


def jl(n):
    return json.loads((SD / (n + ".json")).read_text(encoding="utf-8"))


PARTS = jl("MonsterPartsTable")
TARGET = [
    ("xba003", "dmtr", 451003, "47章 安尼希利奥 [D.M.T.R.]"),
    ("eba002", "hsta", 251016, "48章 莉贝雷利奥躯体 [H.S.T.A.]"),
]

rows, summ = [], []
for tag, suf, mid, zh in TARGET:
    bundle = DEV / f"spotmonster_{tag}_{suf}.bundle"
    env = UnityPy.load(str(bundle))
    tfs, go_name, world = R.build_world(env)
    tid2go = {k: go_name.get(d.m_GameObject.m_PathID, "") for k, d in tfs.items()}
    reg = [p for p in PARTS if p.get("MonsterModelId") == mid]
    n_col = sum(1 for p in reg for o in (p.get("PartsObject") or []) if str(o).startswith("parts_col"))
    cnt = 0
    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        smr = o.read()
        mesh = smr.m_Mesh.read()
        tid = next((k for k, d in tfs.items()
                    if d.m_GameObject.m_PathID == smr.m_GameObject.m_PathID), None)
        chain = R.ancestor_chain(tid, tfs, tid2go) if tid else []
        ph = next((c for c in chain if "1phase" in c or "2phase" in c), "—")
        parent = chain[1] if len(chain) > 1 else "—"
        h = MeshHandler(mesh)
        h.process()
        nv = len(h.m_Vertices) if h.m_Vertices else 0
        tris = [t for sub in h.get_triangles() for t in sub if len(t) == 3] if h.m_IndexBuffer else []
        rows.append([zh, ph, parent, mesh.m_Name, str(nv), str(len(tris))])
        cnt += 1
    summ.append([zh, str(mid), str(len(reg)), str(n_col), str(cnt)])

rows.sort(key=lambda r: (r[0], r[1], -int(r[5])))
hdr = ("# 关底 BOSS 的装配件构成（只列包里真实存在的渲染网格）\n"
       "# 阶段 = 该网格所在父链里出现 1phase / 2phase 的节点，两个阶段骨骼位置不同，必须分开渲染\n"
       "# 渲染网格数 < MonsterPartsTable 登记数，因为后者含碰撞体与预制体根节点（见 关底BOSS_部件统计.tsv）\n"
       "BOSS\t阶段\t父节点\t网格名\t顶点\t三角\n")
(DST / "关底BOSS_部件构成.tsv").write_text(
    "\n".join([hdr] + ["\t".join(r) for r in rows]) + "\n", encoding="utf-8-sig")

shdr = ("# 表格登记部件 vs 实际渲染网格\n"
        "# 登记部件里 parts_col_* 是碰撞体、phase_body / *_var 是预制体根节点，都不是渲染网格\n"
        "BOSS\t型号Id\t表格登记部件数\t其中碰撞体(parts_col)\t实际渲染网格数\n")
(DST / "关底BOSS_部件统计.tsv").write_text(
    "\n".join([shdr] + ["\t".join(r) for r in summ]) + "\n", encoding="utf-8-sig")

print("→ 关底BOSS_部件构成.tsv")
for r in rows:
    print("   ", " | ".join(r))
print("\n→ 关底BOSS_部件统计.tsv")
for r in summ:
    print("   ", " | ".join(r))
