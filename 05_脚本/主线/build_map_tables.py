# -*- coding: utf-8 -*-
"""
把「坐标 tsv」+「关卡表」合成为交付用的两张表：
  1) 大地图点位表（全部实体，含世界坐标）
  2) 关卡坐标表（只保留 StageSpawner，便于直接画图 / 做工具）

用法
----
python build_map_tables.py <坐标tsv> <关卡表tsv> <章号> <输出目录>
"""
import sys, io, os, math


def read_tsv(path):
    lines = [l for l in io.open(path, encoding="utf-8-sig").read().splitlines() if l.strip()]
    hdr, rows, comments = None, [], []
    for ln in lines:
        if ln.startswith("#"):
            comments.append(ln)
            continue
        p = ln.split("\t")
        if hdr is None:
            hdr = p
        else:
            rows.append(dict(zip(hdr, p)))
    return comments, hdr, rows


def yaw_deg(r):
    try:
        ry, rw = float(r["ry"]), float(r["rw"])
    except (KeyError, ValueError):
        return ""
    return f"{math.degrees(2 * math.atan2(ry, rw)):.1f}"


def main():
    pos_tsv, stage_tsv, chap, outdir = sys.argv[1:5]
    _, _, pos = read_tsv(pos_tsv)
    _, _, st = read_tsv(stage_tsv)

    # 关卡ID -> 关卡名（只取普通模式）
    name = {}
    for r in st:
        if r.get("模式") == "普通":
            name[r["关卡ID"]] = r["关卡名(中)"]

    label = {
        "StageSpawner": lambda r: f'{r.get("stageid","")}',
        "ItemSpawner": lambda r: f'收集品 {r.get("itemid","")}',
        "Door": lambda r: "门",
        "Portal": lambda r: "传送门",
        "PortalSet": lambda r: "传送门组",
        "LevelTrigger": lambda r: f'关卡触发器 cond={r.get("triggercontrolcondition","")}',
        "InteractionActionTrigger": lambda r: f'交互触发器 {r.get("triggertableid","")}',
        "SquadSpawner": lambda r: "队伍出生点",
        "CameraPoint": lambda r: "默认镜头点",
    }

    # 1) 点位表
    rows = []
    for r in pos:
        cls = r["class"]
        if cls not in label:
            continue
        rows.append([
            cls, label[cls](r), r["guid"],
            f'{float(r["x"]):.2f}', f'{float(r["y"]):.2f}', f'{float(r["z"]):.2f}',
            yaw_deg(r),
            name.get(r.get("stageid", ""), "") if cls == "StageSpawner" else "",
        ])
    pri = {"StageSpawner": 0, "ItemSpawner": 1}
    rows.sort(key=lambda x: (pri.get(x[0], 2), x[1]))

    km = os.path.join(outdir, '03_地图与点位')
    os.makedirs(km, exist_ok=True)
    p1 = os.path.join(km, f'06_大地图点位_{chap}章.tsv' if chap == "47" else f'07_大地图点位_{chap}章.tsv')
    with io.open(p1, "w", encoding="utf-8-sig", newline="") as f:
        f.write(f"# 第 {chap} 章 大地图实体点位（世界坐标）\n")
        f.write("# 坐标来源：campaignlevelmapgroup_assets_fcbg_cityforest_0XX 的 Transform.m_LocalPosition\n")
        f.write("# 关号来源：StageSpawner._stageId；道具来源：ItemSpawner._itemId（脚本字段直读，非推导）\n")
        f.write("# 朝向 = 绕 Y 轴角度（度），0 为 +Z\n")
        f.write("实体类型\t名称/关号\tPositionId\tX\tY\tZ\t朝向°\t关卡名\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    print("→", p1, len(rows), "行")

    # 2) 关卡坐标表
    stg = sorted([r for r in pos if r["class"] == "StageSpawner"],
                 key=lambda r: int(r.get("stageid") or 0))
    p2 = os.path.join(km, f'12_关卡坐标_{chap}章.tsv')
    with io.open(p2, "w", encoding="utf-8-sig", newline="") as f:
        f.write(f"# 第 {chap} 章 普通关卡的世界坐标（46 条，与 StageSpawner 一一对应）\n")
        f.write("# 用途：把收集品 / 关卡直接画到章节地图上，或喂给工具做路径规划\n")
        f.write("关卡ID\t关卡\t关卡名\tX\tZ\t朝向°\n")
        for r in stg:
            sid = r.get("stageid", "")
            f.write("\t".join([sid, f"{chap}-{int(sid) % 1000}", name.get(sid, ""),
                               f'{float(r["x"]):.2f}', f'{float(r["z"]):.2f}', yaw_deg(r)]) + "\n")
    print("→", p2, len(stg), "行")


main()
