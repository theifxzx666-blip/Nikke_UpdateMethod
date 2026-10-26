# -*- coding: utf-8 -*-
r"""run.py — 04 静态表与数值核对的编排看板

    set NIKKE_WORK=D:\...\本期工作区
    set NIKKE_STATIC=<拆包>\02_Skills\mpdump\out
    set NIKKE_REPO=<拆包>\00_资源库
    python scripts\run.py --status

选料变量：

    NIKKE_EVENT     本期活动 EventManager.Id（给 event_template_probe --event）
    NIKKE_BASE      基线对象名目录（…\_基线_20261029\00_基线_对象名）

本条链只吃静态表，不依赖拉包 —— 键 diff 出完就能算，可与渲染并行。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runlib import Board, Step, main  # noqa: E402

STEPS = [
    Step(
        "01", "解密 .lss → .dec（SQLite）",
        manual=r"对 device\ 下每个 .lss 跑一次（一次一个文件）："
               r"python nkdb_dec.py <工作区>\device\Locale_Character.lss。"
               r"输出 .dec 与源同目录。本期实测 70 个 .lss：Locale_* / perm_* / event_YYMMDD。",
        outs=("{WORK}/device/*.dec",),
        pred="dec 数量应与 lss 相当",
    ),
    Step(
        "02", "先看有什么表（别猜表名）",
        manual=r"python list_lss_tables.py <工作区>\device\*.dec —— 输出每张库的"
               r"表名 + 行数 + 列名。表名以这个输出为准，不许凭记忆写。",
        outs=(),
    ),
    Step(
        "03", "mpdump 静态表全量导出",
        manual=r"cd <拆包>\02_Skills\mpdump 跑一次既有 Dump（365 类型），"
               r"确认能出 JSON 再决定要不要加类型。一张表一个 JSON，落到 out\。",
        outs=("{STATIC}/*.json",),
        pred="JSON 张数应覆盖本期用到的表；缺表先补类型再重跑",
    ),
    Step(
        "04", "活动收益 15 口径（单期）",
        cmd=("{PY}", "{SCRIPTS}/event_template_probe.py",
             "--static", "{STATIC}", "--event", "{EVENT}",
             "--tsv", "{OUT}/活动收益_{EVENT}.tsv",
             "--json", "{OUT}/活动收益_{EVENT}.json"),
        needs=("{STATIC}",),
        outs=("{OUT}/活动收益_{EVENT}.json",),
        pred="15 个口径齐全：关数/一次性/可重复/主机/挑战/任务/签到/商店/地图件数/天数…",
        note="先定组（21 天 / 28 天 / 无地图），再按上期同组数值填 17 页",
    ),
    Step(
        "05", "与归档逐值对账",
        manual=r"python event_template_probe.py --all --compare <活动模板收益_zh-CN.xlsx>"
               r" —— 预期 79/84 期逐值一致；5 期（40001/40006/80100/80200/81600）"
               r"「一次性主机」低 2~23，是 2022~2023 旧结构，登记偏差、不许改脚本去凑。",
        outs=(),
    ),
    Step(
        "06", "个人主页快照（一期一次）",
        cmd=("{PY}", "{SCRIPTS}/profile_assets.py",
             "--static", "{STATIC}", "--snapshot", "{BASE}"),
        needs=("{STATIC}",),
        outs=("{BASE}/头像框.json", "{BASE}/个人主页.json"),
        pred="四层表都要进快照：UserTitleTable / UserTitleAssemblyTable / "
             "ProfileCardObjectTable(type1-sub3) / Locale_Profile",
        note="快照写进基线目录，退出前跑一次；下一期用它当 --baseline",
    ),
    Step(
        "07", "与基线 diff，出新增清单",
        cmd=("{PY}", "{SCRIPTS}/profile_assets.py",
             "--static", "{STATIC}", "--baseline", "{BASE}",
             "--tsv", "{OUT}/个人主页新增.tsv"),
        needs=("{BASE}/头像框.json",),
        outs=("{OUT}/个人主页新增.tsv",),
        pred="头像框必须按 Id 差，不许按 ResourceId 差"
             "（博物馆复刻 27 行与旧段 27/27 完全重合，按 ResourceId 差会误报「无新增」）",
    ),
]

if __name__ == "__main__":
    raise SystemExit(main(Board(
        "04-static-tables · 静态表与数值核对", STEPS,
        note="只吃静态表，不依赖拉包；与 06 渲动画 / 07 战场可并行",
        extra={"EVENT": "NIKKE_EVENT", "BASE": "NIKKE_BASE"},
    )))
