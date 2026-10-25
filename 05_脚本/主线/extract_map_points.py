# -*- coding: utf-8 -*-
"""
地图还原 v2：把 campaignlevelmapgroup bundle 解成「带关号 + 世界坐标」的点位清单。

原理
----
`campaignlevelmapgroup_assets_<战场代号>_<hash>.bundle`（core 桶）就是章节大地图场景。
每个点位 = GameObject + 一个 NK.Field 脚本（MonoBehaviour），脚本里带 `_positionId`(GUID)
与业务字段（`StageSpawner._stageId` / `ItemSpawner._itemId` …）；
坐标在那个 GameObject 的 `Transform.m_LocalPosition`。

所以 **GUID -> 脚本业务字段 -> Transform 坐标** 三段拼起来，地图就还原了。

用法
----
python extract_map_points.py <bundle> <FieldMapData.json> <输出前缀>
"""
import sys, json, io
import UnityPy

# 每种实体取哪些业务字段（按优先级）
BIZ = {
    "StageSpawner": ("_stageId", "_monsterFieldIconName", "_eventID", "_fogOfWarUnitType"),
    "ItemSpawner": ("_itemId", "_isCompleteReward", "_interactionDistance"),
    "Door": ("_doorType", "_startState", "_distanceBetweenDoors"),
    "Portal": ("_portalType", "_isBrokenState"),
    "PortalSet": ("_portalType", "_isActionLinked", "_reverseState"),
    "LevelTrigger": ("_triggerControlCondition", "_switchType", "_holdingTime"),
    "InteractionActionTrigger": ("_triggerTableID", "_triggerTableArchiveID", "_isCompleteReward"),
    "CameraPoint": ("ZoomMinDistance", "ZoomMaxDistance"),
    "SquadSpawner": (),
}

TAG = "dst"


def vec(d, k):
    v = d.get(k) or {}
    return v.get("x"), v.get("y"), v.get("z")


def extract(bundle_path):
    env = UnityPy.load(bundle_path)
    objs = list(env.objects)

    script_name = {}
    for o in objs:
        if o.type.name == "MonoScript":
            try:
                script_name[o.path_id] = o.read_typetree().get("m_ClassName") or "?"
            except Exception:
                pass

    # GameObject.path_id -> Transform 数据
    go2tr = {}
    gameset = set()
    for o in objs:
        t = o.type.name
        if t == "GameObject":
            gameset.add(o.path_id)
        elif t == "Transform":
            try:
                d = o.read_typetree()
            except Exception:
                continue
            g = (d.get("m_GameObject") or {}).get("m_PathID")
            go2tr[g] = d

    # 遍历所有对象，把「同一 GameObject 上的组件」聚到一起
    comps = {}
    for o in objs:
        t = o.type.name
        if t not in ("MonoBehaviour", "BoxCollider", "SphereCollider", "MeshRenderer",
                     "MeshFilter", "NavMeshObstacle", "Camera", "Animator"):
            continue
        try:
            d = o.read_typetree()
        except Exception:
            continue
        g = (d.get("m_GameObject") or {}).get("m_PathID")
        comps.setdefault(g, []).append((t, o.path_id, d))

    out = []
    for go, lst in comps.items():
        mb = [(pid, d) for (t, pid, d) in lst if t == "MonoBehaviour"]
        for pid, d in mb:
            sp = (d.get("m_Script") or {}).get("m_PathID")
            cls = script_name.get(sp, "?")
            guid = (d.get("_positionId") or "").strip().lower()
            if not guid:
                continue
            tr = go2tr.get(go) or {}
            x, y, z = vec(tr, "m_LocalPosition")
            rx, ry, rz, rw = (lambda v: (v.get("x"), v.get("y"), v.get("z"), v.get("w")))(
                tr.get("m_LocalRotation") or {})
            rec = {
                "class": cls, "guid": guid, "go_path_id": go,
                "x": x, "y": y, "z": z, "rx": rx, "ry": ry, "rz": rz, "rw": rw,
                "use_target_camera": d.get("_useTargetCamera"),
                "is_awake_load": d.get("_isAwakeLoad"),
                "custom_param": (d.get("_customParam") or "").strip(),
            }
            for f in BIZ.get(cls, ()):
                v = d.get(f)
                if isinstance(v, list):
                    v = ",".join(str(i) for i in v)
                rec[f.lower()] = v
            out.append(rec)
    return out, len(script_name), len(gameset)


def collect_field_guids(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and len(v) == 36 and v.count("-") == 4:
                acc.setdefault(v.lower(), k)
            else:
                collect_field_guids(v, acc)
    elif isinstance(node, list):
        for v in node:
            collect_field_guids(v, acc)


def main():
    bundle, fmap, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    recs, n_script, n_go = extract(bundle)
    print(f"[bundle] GameObject {n_go} / MonoScript {n_script} / 带 _positionId 的点位 {len(recs)}")

    fm = json.load(io.open(fmap, encoding="utf-8"))
    acc = {}
    collect_field_guids(fm, acc)
    print(f"[FieldMapData] {len(acc)} 个 GUID")

    by_guid = {r["guid"]: r for r in recs}
    hit = [g for g in acc if g in by_guid]
    miss = [g for g in acc if g not in by_guid]
    extra = [r for g in by_guid if g not in acc for r in [by_guid[g]]]
    print(f"[匹配] 命中 {len(hit)} / 未命中 {len(miss)} / bundle 内多余 {len(extra)}")

    rows = []
    for g in hit:
        r = dict(by_guid[g])
        r["field_node"] = acc[g]
        rows.append(r)

    cols = ["class", "field_node", "guid", "x", "y", "z", "rx", "ry", "rz", "rw",
            "use_target_camera", "is_awake_load",
            "_stageid", "_monsterfieldiconname", "_eventid", "_fogofwarunittype",
            "_itemid", "_iscompletereward", "_interactiondistance",
            "_doortype", "_startstate", "_distancebetweendoors",
            "_portaltype", "_isbrokenstate", "_isactionlinked", "_reversestate",
            "_triggercontrolcondition", "_switchtype", "_holdingtime",
            "_triggertableid", "_triggertablearchiveid",
            "zoommindistance", "zoommaxdistance", "custom_param"]
    with io.open(prefix + "_坐标.tsv", "w", encoding="utf-8-sig", newline="") as f:
        f.write("# 世界坐标 = 该点位 GameObject 的 Transform.m_LocalPosition\n")
        f.write("# 关号 = StageSpawner._stageId；道具 = ItemSpawner._itemId（均来自客户端脚本字段，非推导）\n")
        f.write("\t".join(c.strip("_") for c in cols) + "\n")
        for r in sorted(rows, key=lambda r: (r["class"], str(r.get("_stageid") or ""))):
            f.write("\t".join("" if r.get(c) is None else str(r.get(c)).lower() if c == "guid" else str(r.get(c))
                              for c in cols) + "\n")
    print("→", prefix + "_坐标.tsv", len(rows), "行")

    if miss:
        with io.open(prefix + "_未命中.txt", "w", encoding="utf-8") as f:
            for g in sorted(miss):
                f.write(f"{g}\t{acc[g]}\n")
        print("→", prefix + "_未命中.txt", len(miss))
    if extra:
        with io.open(prefix + "_多余点位.tsv", "w", encoding="utf-8") as f:
            f.write("class\tguid\tx\tz\tstageId\titemId\n")
            for r in extra:
                f.write(f'{r["class"]}\t{r["guid"]}\t{r["x"]}\t{r["z"]}\t{r.get("_stageid")}\t{r.get("_itemid")}\n')
        print("→", prefix + "_多余点位.tsv", len(extra))


if __name__ == "__main__":
    main()
