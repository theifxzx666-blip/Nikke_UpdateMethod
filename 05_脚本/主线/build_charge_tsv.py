# -*- coding: utf-8 -*-
"""把 charge_multi_*.json 汇总成业务目录里的两张 tsv。

输出：
  06_战斗场景还原/充能点位_多判.tsv        每阵位 Top-K 多判点（明细）
  06_战斗场景还原/充能点位_阵位概览.tsv    每阵位一行：峰值/稳定/多判格数/首推点
"""
import json
from pathlib import Path

OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out")
DST = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\05_主线_47-48章\06_战斗场景还原")
FAR = 40.0   # 命中距离超过此值标「远端」


def main():
    scenes = []
    for n in ("001", "002", "003"):
        p = OUT / f"charge_multi_sbg_{n}.json"
        scenes.append(json.loads(p.read_text(encoding="utf-8")))

    rows = []
    head = ["战场", "阵位", "掩护位", "排名", "yaw(°)", "pitch(°)", "段数",
            "1°窗口稳定段数", "稳定性", "单发充能点数", "准星像素(x,y)",
            "最近命中距离(m)", "命中物件(按距离)", "备注"]
    for sc in scenes:
        for k in sorted(sc["slots"], key=int):
            s = sc["slots"][k]
            for p in s["points"]:
                dmax = max(h["d"] for h in p["hits"]) if p["hits"] else 0
                rows.append([
                    sc["scene"], k, s["cover"], p["rank"], p["yaw"], p["pitch"],
                    p["n_seg"], p["n_1deg"], "稳" if p["stable"] else "窄",
                    p["charge"],
                    "%.1f, %.1f" % tuple(p["pixel"]) if p["pixel"] else "—",
                    p["hits"][0]["d"] if p["hits"] else "—",
                    " | ".join("%s %sm" % (h["name"].replace("sbg_cityforest_", ""), h["d"])
                               for h in p["hits"]),
                    "远端" if dmax >= FAR else "",
                ])

    def w(name, header, body, notes):
        p = DST / name
        lines = ["# " + x for x in notes]
        lines.append("\t".join(header))
        for r in body:
            lines.append("\t".join(str(x) for x in r))
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[ok] {p}  {len(body)} 行")
        return p

    w("充能点位_多判.tsv", head, rows, [
        "第 47/48 章三套战场（sbg_cityforest_001/002/003）的可破坏物件多判点位",
        "判据：单发穿透的可破坏物件数（段数）≥2，单判点（段数=1）已全部剔除",
        "段数按「不同物件」去重计数；ground/static_object/cover_object 会截断视线",
        "稳定性「稳」= 1° 方框内段数不下降；「窄」= 峰值够但窗口 <1°，需精确对准",
        "单发充能点数 = 段数 × 4（ConfigBattleTable.ulti_gauge_shot_hit=4）",
        "角度为枪口朝向（yaw 0=+Z，pitch 抬枪为正），不是准星屏幕角，二者差几像素",
        "准星像素按该阵位相机 fov=60° / 1600×900 投影，仅作标注参考",
    ])

    ov = []
    for sc in scenes:
        for k in sorted(sc["slots"], key=int):
            s = sc["slots"][k]
            top = s["points"][0] if s["points"] else None
            ov.append([
                sc["scene"], k, s["cover"],
                "%.2f, %.2f, %.2f" % tuple(s["origin"]),
                s["n_max"], s["n_1deg_max"], s["multi_cells"], s["stable_cells"],
                len(s["points"]),
                "yaw%+.2f / pitch%+.2f" % (top["yaw"], top["pitch"]) if top else "—",
                top["charge"] if top else "—",
                "是" if (top and top["stable"]) else ("否（只有窄窗多判点）" if top else "无多判点"),
            ])
    w("充能点位_阵位概览.tsv",
      ["战场", "阵位", "掩护位", "枪口世界坐标(x,y,z)", "峰值段数", "1°稳定段数",
       "多判格数", "其中1°稳定格数", "已列候选点数", "首推点位", "首推单发充能", "是否稳健"],
      ov, [
          "每阵位一行的总览；明细见 充能点位_多判.tsv",
          "多判格数 = 0.25° 栅格上段数≥2 的格子数；1°稳定格数 = 其中 1° 方框不降段的格子数",
          "「无多判点」表示该阵位在整个 yaw±45°/pitch−6~30° 范围内不存在同时命中 2 件的位置",
      ])

    cov = sum(1 for sc in scenes for k in sc["slots"] if sc["slots"][k]["points"])
    tot = sum(len(sc["slots"]) for sc in scenes)
    print("\n合计多判点 %d 个，覆盖 %d/%d 个阵位" % (len(rows), cov, tot))


if __name__ == "__main__":
    main()
