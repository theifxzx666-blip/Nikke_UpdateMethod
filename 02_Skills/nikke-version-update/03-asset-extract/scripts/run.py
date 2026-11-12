# -*- coding: utf-8 -*-
r"""run.py — 03 资源提取的编排看板

先设环境变量，再看板：

    set NIKKE_WORK=D:\...\本期工作区
    set NIKKE_PY=D:\Codex\依赖\venv-nikke\Scripts\python.exe
    python scripts\run.py --status

选料变量（不设就对应的步骤标 BLOK，不会拿上一期的路径去凑）：

    NIKKE_BUNDLE        当期主包（给 dump_skill_icons 用）
    NIKKE_NAMES         要导的技能图标名，空格分隔（名字从 04 的静态表来，不猜）
    NIKKE_MODEL         目标莱彻型号，如 xba003
    NIKKE_PHASE         阶段目录名，如 2phase

产物按各脚本自己的落点声明（脚本内部都读 NIKKE_WORK，所以固定是 <WORK>\out\...）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runlib import Board, Step, main, pred_min_count  # noqa: E402

STEPS = [
    Step(
        "01", "皮肤键基线（键→cID→名称）",
        cmd=("{PY}", "{SCRIPTS}/export_costume.py"),
        outs=("{WORK}/out/costume_baseline.csv",),
        pred="全新基线，一期跑一次",
        note="读 device\\locale 下的 .lss，先确保 02 已解密",
    ),
    Step(
        "02", "莱彻立绘（绑定姿态，全量）",
        cmd=("{PY}", "{SCRIPTS}/render_monster_standee.py"),
        needs=("{WORK}/device",),
        outs=("{WORK}/out/monster_standee/manifest.json",
              "{WORK}/out/monster_standee/*_立绘.png"),
        pred="manifest + 立绘，比值须 ≥1.5",
        check=pred_min_count(".png", 3),
    ),
    Step(
        "03", "莱彻透视 / 拆件",
        cmd=("{PY}", "{SCRIPTS}/render_monster_xray.py"),
        needs=("{WORK}/out/monster_standee/manifest.json",),
        outs=("{WORK}/out/monster_standee/xray/*_透视.png",
              "{WORK}/out/monster_standee/xray/*_拆解.png"),
        pred="外壳 30% 透明，让内部 cm_core 显形",
    ),
    Step(
        "04", "网格自检（人眼看偏差）",
        manual="python verify_skin.py —— 直出 vs 蒙皮两套坐标，偏差大说明部件会错位。"
               "脚本只打印不落盘，必须人读输出再决定要不要继续。",
        outs=(),  # 无产物，纯人工关口
    ),
    Step(
        "05", "模型转 glb",
        cmd=("{PY}", "{SCRIPTS}/export_glb.py", "{MODEL}", "{PHASE}"),
        needs=("{WORK}/device",),
        outs=("{WORK}/out/glb/*.glb",),
        pred="animations > 0 且通道数 > 0，否则是个不动的模型且不报错",
        note="型号/阶段由 NIKKE_MODEL / NIKKE_PHASE 给，例 xba003 2phase",
    ),
    Step(
        "06", "glb 偏移修复",
        manual="python fix_glb_offset.py --dry  先看命中哪些，确认后再 --all。"
               "--dry 不改文件；直接 --all 会把误判的也搬走。",
        outs=("{WORK}/out/glb/*.glb",),
    ),
    Step(
        "07", "技能图标",
        cmd=("{PY}", "{SCRIPTS}/dump_skill_icons.py", "{BUNDLE}", "{OUT}/icons", "{NAMES}"),
        outs=("{OUT}/icons/*.png",),
        pred="名字取自静态表，不许猜",
        note="NIKKE_BUNDLE + NIKKE_NAMES 都要给",
    ),
    Step(
        "08", "BGM",
        manual="python build_bgm.py —— 输出目录由脚本顶部 BASE 决定（当前写死 20260813 那一期）。"
               "换期先改 BASE 再跑，否则会写进上一期的 08_BGM。",
        outs=(),
    ),
    Step(
        "09", "台词配音包",
        manual="python build_voice_pack.py —— 默认 c870/c871/c872 三语链路，"
               "换角色先改脚本顶部常量与 DST 期号目录。",
        outs=(),
    ),
    Step(
        "10", "大地图上的莱彻（反查型号）",
        manual="python scan_map_monsters.py —— 从模型包反查型号再配中文名。"
               "中文名只走 Locale_Monster 的 _name（131 条最干净），"
               "_appearance_name 854 条里只 2 条含中文。",
        outs=(),
    ),
]

if __name__ == "__main__":
    raise SystemExit(main(Board(
        "03-asset-extract · 资源提取（贴图 / 模型 / 音频）", STEPS,
        note="上游 02-bundle-pull 给 .bundle；下游 06 渲动画 / 08 出报告",
        extra={
            "BUNDLE": "NIKKE_BUNDLE",
            "NAMES": "NIKKE_NAMES",
            "MODEL": "NIKKE_MODEL",
            "PHASE": "NIKKE_PHASE",
        },
    )))
