# -*- coding: utf-8 -*-
r"""event_template_probe.py — 活动奖励「模板 15 口径」复算 / 对账

用途
    给一个 EventManager.Id（活动主体），算出「活动模板收益」表里的 15 个口径，
    用于①新一期活动套模板②对归档模板复核。2026-10-26 与归档
    `00_资源库\文本\活动收益\活动模板收益_zh-CN.xlsx` 84 期逐值对账：79/84 完全一致。

口径（与归档表逐列同名）
    主线关数 / 一次性 / 可重复 / 一次性主机合计 / 挑战关数 / 任务条数 / 签到档数 /
    商店项数 / 地图件数 / 天数 / 活动代号 / 地图 prefab / 可重复单次产出

关键实测（不要凭直觉改）
  1. 「主机」= ItemPieceTable 里 ItemSubType==14 的 8 件（5 企业 + 3 职业），
     不是名字里带「主机」的道具 —— 名字是 locale key，匹配不到中文。
  2. 子模块全部由 EventManagerTable.ParentsEventId 反查，不靠 ID 位数猜：
     sys 5=剧情 10=带地图 11=商店 20=挑战 2=签到 4=协同 62/57…=小游戏。
  3. 关卡组 = EventDungeonTable.DifficultGroup 前缀 + 后 3 位（101 普通 / 201 困难）。
  4. 商店只认 sys=11 子模块存在者；商店行用 ContentsShopTable.BgResourceId
     == 活动代号（banner 名去掉 _S）关联，商品数按 BundleId 数 ContentsShopProductTable。
  5. 天数 = 该活动 EventField 名下 FieldItem 的 (max DespawnTime − min SpawnTime)，
     与时区无关；无地图活动没有 FieldItem，天数为空。

已知差异（不是 bug，是旧结构）
    40001 / 40006 / 80100 / 80200 / 81600 五期的「一次性主机」比归档低 2~23，
    原因是 2022~2023 旧结构把主机也塞进挑战首通或地图产出。2024-10 之后的结构逐值一致。

用法
    python event_template_probe.py --event 83300
    python event_template_probe.py --all --tsv 场景规模.tsv
    python event_template_probe.py --all --compare "<活动模板收益_zh-CN.xlsx>"
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_STATIC = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点"
                      r"\_基线_20261029\00_基线_静态表\_mpdump全量")

COLS = ["EventManager.Id", "活动代号", "sys", "地图 prefab", "开始", "结束", "天数",
        "主线关数", "一次性", "可重复", "一次性主机合计", "挑战关数", "任务条数",
        "签到档数", "商店项数", "地图件数", "可重复单次产出"]


def _load(d: Path, name: str):
    p = d / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"缺表 {p} —— 检查 --static 是否指到 _mpdump全量")
    return json.loads(p.read_text(encoding="utf-8"))


class Tables:
    def __init__(self, d: Path):
        self.d = d
        self.EM = _load(d, "EventManagerTable")
        self.ES = _load(d, "EventStoryTable")
        self.ED = {r["Id"]: r for r in _load(d, "EventDungeonTable")}
        self.EDS = _load(d, "EventDungeonStageTable")
        self.SB = {r["Id"]: r for r in _load(d, "EventDungeonSpotBattleTable")}
        self.EML = _load(d, "EventMissionListTable")
        self.LGE = _load(d, "LoginEventTable")
        self.CSP = _load(d, "ContentsShopProductTable")
        self.CS = _load(d, "ContentsShopTable")
        self.FI = _load(d, "FieldItemTable")
        self.EF = _load(d, "EventFieldTable")
        self.RW = {r["Id"]: r for r in _load(d, "RewardTable")}
        # 主机 = ItemSubType 14 的碎片（5 企业 + 3 职业）
        self.HOME = {r["Id"] for r in _load(d, "ItemPieceTable") if r.get("ItemSubType") == 14}

        self.EMBY = {r["Id"]: r for r in self.EM}
        self.GROUPS = collections.defaultdict(list)
        for r in self.EDS:
            self.GROUPS[r["Group"]].append(r)
        self.ALLG = sorted(self.GROUPS)

    # ---- 基础 ----
    def stages_of(self, dungeon_id: int) -> list:
        d = self.ED.get(dungeon_id)
        if not d:
            return []
        base = str(d["DifficultGroup"])
        out = []
        for g in self.ALLG:
            if str(g).startswith(base) and len(str(g)) == len(base) + 3:
                out += sorted(self.GROUPS[g], key=lambda x: x["Step"])
        return out

    def code_of(self, eid: int) -> str:
        b = (self.EMBY.get(eid) or {}).get("EventBannerResourceId") or ""
        b = b.replace("EVENT_BANNER_", "")
        return b[:-2] if b.endswith("_S") else b

    def kids(self, eid: int) -> dict:
        ids = sorted({r["Id"] for r in self.EM if r.get("ParentsEventId") == eid} | {eid})
        m = collections.defaultdict(list)
        for k in ids:
            if k in self.EMBY:
                m[self.EMBY[k]["EventSystemType"]].append(k)
        return m

    def homes(self, reward_id: int) -> int:
        n = 0
        for e in (self.RW.get(reward_id) or {}).get("Rewards", []):
            if e.get("RewardType") == 5 and e.get("RewardId") in self.HOME:
                n += e["RewardValue"]
        return n

    # ---- 单期 ----
    def compute(self, eid: int) -> dict:
        sysmap = self.kids(eid)
        main_es = [s for s in self.ES if s["EventId"] in sysmap[5]]
        chal_es = [s for s in self.ES if s["EventId"] in sysmap[20]]
        main_ids = [s["DungeonId1"] for s in main_es]
        main_st = [x for d in main_ids for x in self.stages_of(d)]
        chal_st = [x for s in chal_es for x in self.stages_of(s["DungeonId1"])]
        once = [x for x in main_st if not x["IsRepeatClear"]]
        rep = [x for x in main_st if x["IsRepeatClear"]]
        home = sum(self.homes((self.SB.get(x["Id"]) or {}).get("ClearRewardId") or 0) for x in once)

        field = next((f for f in self.EF if f["EventId"] == eid), None)
        days, d0, d1, nmap = "", "", "", 0
        if field:
            tf = [i for i in self.FI if i["ObtainLocation"] == field["Id"]]
            nmap = len(tf)
            sp = [i["SpawnTime"] for i in tf if i.get("SpawnTime")]
            dp = [i["DespawnTime"] for i in tf if i.get("DespawnTime")]
            if sp and dp:
                f = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
                d0, d1 = min(sp)[:10], max(dp)[:10]
                days = round((f(max(dp)) - f(min(sp))).total_seconds() / 86400)

        mgrp = sorted({r["Group"] for r in self.EML if r["Group"] // 100 in main_ids})
        ntasks = len([r for r in self.EML if r["Group"] in mgrp])
        nlogin = len([r for r in self.LGE if r["EventId"] in sysmap[2]])

        nshop = 0
        if sysmap[11] and main_ids:
            cand = [r for r in self.CS if r["BgResourceId"] == self.code_of(eid)]
            want = {90000 + d for d in main_ids}
            pick = [r for r in cand if r["BundleId"] in want] \
                or [r for r in self.CS if r["BundleId"] in want] or cand
            nshop = sum(len([p for p in self.CSP if p["BundleId"] == r["BundleId"]]) for r in pick[:1])

        tpl = ""
        if rep:
            agg = collections.OrderedDict()
            rid = (self.SB.get(rep[0]["Id"]) or {}).get("ClearRewardId") or 0
            for e in (self.RW.get(rid) or {}).get("Rewards", []):
                k = (e["RewardType"], e["RewardId"])
                agg[k] = agg.get(k, 0) + e["RewardValue"]
            tpl = " + ".join("t%d:%d×%d" % (k[0], k[1], v) for k, v in agg.items())

        return {"EventManager.Id": eid, "活动代号": self.code_of(eid),
                "sys": self.EMBY[eid]["EventSystemType"],
                "地图 prefab": field["FieldDesignMap"] if field else "",
                "开始": d0, "结束": d1, "天数": days,
                "主线关数": len(main_st), "一次性": len(once), "可重复": len(rep),
                "一次性主机合计": home, "挑战关数": len(chal_st), "任务条数": ntasks,
                "签到档数": nlogin, "商店项数": nshop, "地图件数": nmap,
                "可重复单次产出": tpl,
                # 给「17 页收益表单」用的活动定义块
                "_定义块": {"EID": eid, "children": sorted(sysmap),
                            "sysmap": {str(k): v for k, v in sysmap.items()},
                            "main_dungeons": main_ids,
                            "main_event_story": [s["Id"] for s in main_es],
                            "challenge_event_story": [s["Id"] for s in chal_es],
                            "event_item": next((s["EventItemId"] for s in main_es if s.get("EventItemId")), 0),
                            "field_id": field["Id"] if field else 0}}

    def all_events(self) -> list:
        return [r["Id"] for r in self.EM if r["EventSystemType"] in (5, 10)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", default=str(DEFAULT_STATIC))
    ap.add_argument("--event", type=int, default=0, help="单个 EventManager.Id")
    ap.add_argument("--all", action="store_true", help="全部 sys 5/10 活动")
    ap.add_argument("--tsv", default="", help="写 TSV")
    ap.add_argument("--json", default="", help="写 JSON（含定义块）")
    ap.add_argument("--compare", default="", help="与归档 xlsx 逐值对账")
    a = ap.parse_args()

    T = Tables(Path(a.static))
    eids = [a.event] if a.event else (T.all_events() if a.all else [83300])
    rows = [T.compute(e) for e in eids]

    if a.tsv:
        p = Path(a.tsv); p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            f.write("\t".join(COLS) + "\n")
            for r in rows:
                f.write("\t".join(str(r[c]) for c in COLS) + "\n")
        print(f"TSV → {p}")
    if a.json:
        p = Path(a.json); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"JSON → {p}")

    if not a.tsv and not a.json:
        w = [8, 18, 4, 26, 11, 11, 5, 7, 7, 7, 12, 7, 7, 7, 7, 7]
        print("".join(c.ljust(x) for c, x in zip(COLS[:16], w)))
        print("-" * sum(w))
        for r in rows:
            print("".join(str(r[c]).ljust(x) for c, x in zip(COLS[:16], w)))

    if a.compare:
        try:
            import openpyxl
        except ImportError:
            print("!! 对账需要 openpyxl（用 D:\\Codex\\依赖\\venv-nikke\\Scripts\\python.exe）")
            return 2
        wb = openpyxl.load_workbook(a.compare, data_only=True)
        exp = {}
        for r in list(wb["1_有地图_逐期"].iter_rows(values_only=True))[4:]:
            if r[1]:
                exp[r[1]] = {"主线关数": r[6], "一次性": r[7], "可重复": r[8], "一次性主机合计": r[9],
                             "挑战关数": r[10], "任务条数": r[11], "签到档数": r[12],
                             "商店项数": r[13], "地图件数": r[14]}
        for r in list(wb["2_无地图_逐期"].iter_rows(values_only=True))[4:]:
            if r[0] and str(r[0]).isdigit():
                exp[int(r[0])] = {"主线关数": r[2], "一次性": r[3], "可重复": r[4],
                                  "一次性主机合计": r[5], "挑战关数": r[6], "任务条数": r[7]}
        ok, bad = 0, []
        for eid, e in sorted(exp.items()):
            if eid not in T.EMBY:
                bad.append((eid, "不在 EventManagerTable")); continue
            c = T.compute(eid)
            diff = [(k, c[k], v) for k, v in e.items() if v is not None and c[k] != v]
            (bad.append((eid, T.code_of(eid), diff)) if diff else None)
            ok += (not diff)
        print(f"\n对账：完全一致 {ok}/{len(exp)}；有差异 {len(bad)} 期")
        for b in bad:
            print("  ", b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
