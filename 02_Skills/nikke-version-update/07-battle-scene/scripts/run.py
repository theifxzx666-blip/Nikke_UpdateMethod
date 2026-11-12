# -*- coding: utf-8 -*-
r"""run.py — 07 战场场景的编排看板

    set NIKKE_WORK=D:\...\本期工作区
    python scripts\run.py --status

选料变量（不设对应步骤标 BLOK）：

    NIKKE_BUNDLE    当期战场包，如 <工作区>\device\sbg_001.bundle
    NIKKE_TAG       同一包的短名，用来命名产物，如 sbg_001
    NIKKE_FIELDMAP  地图数据 JSON（地图链路才要）
    NIKKE_CHAP      章号，如 29

两条独立链路：**战场场景**（01~05）与 **地图点位**（06~08）。后者不依赖前者，
别把它们串成一条，也别指望地图的逻辑去验战场。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runlib import Board, Step, main  # noqa: E402


def check_mesh(files):
    """装配产物的三角面判据。

    ratio = 三角 / 顶点。**门限 1.5**，实测正常 1.88、只取 zmin 层 0.91。
    纯 quad billboard 场景 0.5 是例外 —— 1 quad = 4 顶点 2 三角，那种场景
    props 里全是 quad，没有 mesh，此时 0.5 才算正常。
    """
    for f in files:
        if f.suffix.lower() != ".json":
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            return False, f"{f.name} 读不动: {e}"

        props = d.get("props") or []
        tri = sum(len(p.get("tri") or ()) // 3 for p in props)
        vert = sum(len(p.get("v") or ()) for p in props)
        if vert == 0:
            return False, "顶点为 0 —— 网格没读出来"
        ratio = tri / vert
        kinds = d.get("kinds") or {}
        only_quad = set(kinds) == {"quad"}

        tag = "objects=%d tri=%d vert=%d ratio=%.2f" % (len(props), tri, vert, ratio)
        if ratio >= 1.5:
            return True, tag
        if only_quad and 0.45 <= ratio <= 0.55:
            return True, tag + "（纯 quad，0.5 是例外）"
        return False, tag + " —— 低于 1.5，先查是不是只取了 zmin 层"

    return False, "产物里没有装配 JSON"


STEPS = [
    Step(
        "01", "装配（bundle → asm.json）",
        cmd=("{PY}", "{SCRIPTS}/build_battle_scene.py",
             "{BUNDLE}", "{OUT}/asm/asm_{TAG}.json"),
        needs=("{BUNDLE}",),
        outs=("{OUT}/asm/asm_{TAG}.json",),
        pred="四个数必须都打印：objects / tri / vert / ratio",
        check=check_mesh,
    ),
    Step(
        "02", "全景渲图",
        cmd=("{PY}", "{SCRIPTS}/render_overview.py",
             "{OUT}/asm/asm_{TAG}.json", "{BUNDLE}",
             "{OUT}/png/{TAG}_overview.png", "--w", "1800", "--pitch", "42", "--dist", "30"),
        needs=("{OUT}/asm/asm_{TAG}.json",),
        outs=("{OUT}/png/{TAG}_overview.png",),
        pred="朝向取 slots[n].axes，不许用 aim − camera 反推",
    ),
    Step(
        "03", "阵位渲图（1~5 各一张）",
        manual=r"对 k=1..5 依次跑：python render_battle_scene.py "
               r"{OUT}\asm\asm_{TAG}.json {BUNDLE} {OUT}\png\{TAG}_s<k>.png --slot <k>。"
               r"相机朝向必须用 slots[k-1].axes —— 用 aim−camera 反推会算成相机背后，"
               r"整片战场只剩几十个三角。",
        needs=("{OUT}/asm/asm_{TAG}.json",),
        outs=("{OUT}/png/{TAG}_s1.png", "{OUT}/png/{TAG}_s2.png", "{OUT}/png/{TAG}_s3.png",
              "{OUT}/png/{TAG}_s4.png", "{OUT}/png/{TAG}_s5.png"),
        pred="5 张齐全才算完",
    ),
    Step(
        "04", "扫充能点（多阵位）",
        cmd=("{PY}", "{SCRIPTS}/scan_charge_multi.py", "{OUT}/asm/asm_*.json"),
        needs=("{OUT}/asm/asm_{TAG}.json",),
        outs=("{OUT}/asm/charge_multi_*.json",),
        pred="1° 窗口是椭圆不是方框：@1600×900 fov60 → 横向 26.67 px/°、纵向 12.51 px/°",
        note="输入文件名必须含 'asm_'，脚本按 asm_→charge_multi_ 改名",
    ),
    Step(
        "05", "充能点落图",
        manual=r"python mark_charge_multi.py —— 写死 sbg_001~003 与 BASE 输出目录、"
               r"临时目录在 D:\Codex\临时\_charge。换期先改这三处再跑。",
        outs=(),
    ),
    Step(
        "06", "地图点位（另一条链路）",
        cmd=("{PY}", "{SCRIPTS}/extract_map_points.py",
             "{BUNDLE}", "{FIELDMAP}", "{OUT}/map/{TAG}"),
        needs=("{FIELDMAP}",),
        outs=("{OUT}/map/{TAG}_坐标.tsv",),
        pred="GUID → 脚本字段 → Transform 三段链路，缺一段就查不出来",
        note="同目录还会出 _未命中.txt / _多余点位.tsv，未命中非 0 要回头看",
    ),
    Step(
        "07", "地图渲图",
        cmd=("{PY}", "{SCRIPTS}/render_map.py", "{BUNDLE}", "{CHAP}", "{OUT}/map/ch{CHAP}.png"),
        needs=("{OUT}/map/{TAG}_坐标.tsv",),
        outs=("{OUT}/map/ch{CHAP}.png",),
        pred="子网格多的背景件要逐个渲，别只取第一个 submesh",
    ),
    Step(
        "08", "地图表（坐标 + 关卡）",
        manual=r"python build_map_tables.py <坐标tsv> <关卡表tsv> <章号> <输出目录> —— "
               r"第二张表是子集，行数比第一张少是正常的，不是漏读。",
        outs=(),
    ),
]

if __name__ == "__main__":
    raise SystemExit(main(Board(
        "07-battle-scene · 战场场景与地图点位", STEPS,
        note="战场（01~05）与地图（06~08）是两条独立链路；*_col 碰撞网格必须滤掉",
        extra={
            "BUNDLE": "NIKKE_BUNDLE",
            "TAG": "NIKKE_TAG",
            "FIELDMAP": "NIKKE_FIELDMAP",
            "CHAP": "NIKKE_CHAP",
        },
    )))
