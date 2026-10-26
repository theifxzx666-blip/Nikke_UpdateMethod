# -*- coding: utf-8 -*-
r"""run.py — 06 Spine 动画渲染的编排看板

    set NIKKE_WORK=D:\...\本期工作区
    python scripts\run.py --status

前置：spine_render\ 目录摆好（index.html + vendor\ + assets\<name>\<name>.{skel,atlas,png}），
并起静态服务 `python -m http.server 8766`（file:// 下 ES module 与 fetch 全被拦）。

产物落点由脚本自己定（读 NIKKE_WORK）：out\lobby_gif\ / out\lobby_webp\ / out\cut_gif\。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runlib import Board, Step, main, pred_min_count  # noqa: E402

STEPS = [
    Step(
        "01", "摆目录（index.html + vendor + assets）",
        manual=r"把 renderer\index.html 与整个 renderer\vendor\ 拷进 <工作区>\spine_render\，"
               r"资源放 assets\<name>\<name>.{skel,atlas,png}。vendor 必须有 —— "
               r"它是 @esotericsoftware/spine-player 的产物，缺了页面白屏。",
        outs=("{WORK}/spine_render/index.html", "{WORK}/spine_render/vendor/"),
        pred="vendor 是目录，存在即可",
    ),
    Step(
        "02", "起静态服务 8766",
        manual=r"在 spine_render\ 里 python -m http.server 8766，"
               r"浏览器验一次 http://127.0.0.1:8766/index.html?asset=assets/<name>/<name>&ui=0&ss=2 "
               r"能出图再往下。渲染脚本通过 CDP 连这个页面。",
        outs=(),
    ),
    Step(
        "03", "拉骨架三件套",
        cmd=("{PY}", "{SCRIPTS}/pull_spine.py"),
        needs=("{WORK}/device",),
        outs=("{WORK}/spine_render/assets/",),
        pred="每个角色一套 .skel/.atlas/.png",
    ),
    Step(
        "04", "大厅动画 GIF / WebP / 首帧 PNG",
        cmd=("{PY}", "{SCRIPTS}/export_lobby_gif.py", "--long", "1000", "--fps", "15"),
        needs=("{WORK}/spine_render/index.html", "{WORK}/spine_render/assets/"),
        outs=("{WORK}/out/lobby_gif/*.gif", "{WORK}/out/lobby_webp/*.webp"),
        pred="取景用整段动画并集，不许逐帧自适应（否则画面抽搐）",
        check=pred_min_count(".gif", 1),
    ),
    Step(
        "05", "爆裂特写（多层叠加）",
        cmd=("{PY}", "{SCRIPTS}/export_cutscene_gif.py", "--long", "1000", "--fps", "15"),
        needs=("{WORK}/spine_render/assets/",),
        outs=("{WORK}/out/cut_gif/_manifest.json", "{WORK}/out/cut_gif/*.gif"),
        pred="层序写在脚本 JOBS 里，改角色先改 JOBS",
        note="c870 的 idle 不属于爆裂，只挂第 0 层 + hide=0 借包围盒",
    ),
    Step(
        "06", "全帧网格验收（人眼看）",
        cmd=("{PY}", "{SCRIPTS}/check_gif.py", "{WORK}/out/lobby_gif", "{WORK}/out/cut_gif",
             "--out", "{OUT}/gif验收"),
        needs=("{WORK}/out/lobby_gif/",),
        outs=("{OUT}/gif验收/*全帧网格.png",),
        pred="每格标帧号 + 覆盖率%，空帧描红框；这张图必须人眼看一遍再交付",
        note="动幅取最多 7 帧两两比对，不能用首帧 vs 半周期帧（循环动画会算出近似 0）",
    ),
]

if __name__ == "__main__":
    raise SystemExit(main(Board(
        "06-spine-render · Spine 动画渲染", STEPS,
        note="上游 03-asset-extract；下游 08-deliver-pdf。渲染必须走 http://127.0.0.1:8766",
    )))
