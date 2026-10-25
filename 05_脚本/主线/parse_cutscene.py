# -*- coding: utf-8 -*-
"""解析爆裂特写包（livewallpaperprefabs / eventscene_c87x_cutscene）里的 Timeline 结构。

背景：
  `spotskillcutscene_assets_c87x_00_cut_scene` 那个包**不带 TypeTree**，
  PlayableDirector / TimelineAsset 读不出来，所以之前只能确认「粒子时序不可还原」。
  但同一套特写在 `livewallpaperprefabs_assets_livewallpaper/eventscene_c87x_cutscene`
  里另有一份打包，**TypeTree 是完整的**：
    TimelineAsset.m_Tracks  →  TrackAsset.m_Clips[].m_Start / m_Duration
    PlayableDirector.m_SceneBindings → Track ↔ GameObject 绑定
  于是每一层的出场时间可以从文件里直接读出来，不用猜。

产出：
  <out>/<cid>_时序.tsv      每条轨道每个片段的起止时间
  <out>/<cid>_贴图/*.png    包内全部 Texture2D（特效图集，原样导出）
  <out>/<cid>_音频/*.wav    Audio Track 引用的 AudioClip（爆裂音效）

用法：
  python parse_cutscene.py <bundle> <cid> <out_dir>
"""
import sys
from pathlib import Path

import UnityPy

clip_list = []


def tt(o):
    """尽量按 typetree 读；读不出来返回 None。"""
    try:
        return o.read_typetree()
    except Exception:
        return None


def name_of(o):
    if o is None:
        return ""
    d = tt(o)
    if isinstance(d, dict):
        return str(d.get("m_Name", "")) or ""
    try:
        return str(getattr(o.read(), "m_Name", "") or "")
    except Exception:
        return ""


def cls_of(objs, mb_tt):
    """MonoBehaviour 的 m_Script → MonoScript.m_ClassName。"""
    pp = (mb_tt or {}).get("m_Script") or {}
    o = objs.get(pp.get("m_PathID"))
    if o is None:
        return ""
    d = tt(o)
    return str((d or {}).get("m_ClassName", "")) if isinstance(d, dict) else ""


def main():
    bp = Path(sys.argv[1])
    cid = sys.argv[2]
    outdir = Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)

    env = UnityPy.load(str(bp))
    objs = {o.path_id: o for o in env.objects}

    # ---- 找 TimelineAsset（每个包里 2 个 PlayableDirector，取含 m_Tracks 且轨道最多的）
    best = None
    for o in env.objects:
        if o.type.name != "PlayableDirector":
            continue
        d = tt(o)
        if not d:
            continue
        ta = objs.get((d.get("m_PlayableAsset") or {}).get("m_PathID"))
        if ta is None:
            continue
        t = tt(ta)
        if not t or "m_Tracks" not in t:
            continue
        n = len(t.get("m_Tracks") or [])
        if best is None or n > best[2]:
            best = (o, d, n, t, ta)

    if best is None:
        raise SystemExit(f"{bp.name}: 找不到带 m_Tracks 的 TimelineAsset")

    dir_obj, dir_tt, ntracks, tasset, ta_obj = best
    print(f"[timeline] {tasset.get('m_Name')}  tracks={ntracks}  "
          f"duration={tasset.get('m_FixedDuration')}s")

    # ---- Track ↔ GameObject 绑定
    bind = {}
    for sb in (dir_tt.get("m_SceneBindings") or []):
        k = (sb.get("key") or {}).get("m_PathID")
        v = (sb.get("value") or {}).get("m_PathID")
        if k and v:
            bind[k] = name_of(objs.get(v))

    # ---- 递归走轨道树
    rows = []

    def walk(pid, path):
        o = objs.get(pid)
        if o is None:
            return
        d = tt(o)
        if not d:
            return
        nm = str(d.get("m_Name", "")) or "?"
        cls = cls_of(objs, d) or o.type.name
        full = f"{path}/{nm}" if path else nm
        go = bind.get(pid, "")

        clips = d.get("m_Clips") or []
        if not clips:
            rows.append([full, cls, go, "-", "", "", "", "", ""])
        for i, c in enumerate(clips, 1):
            st = float(c.get("m_Start") or 0.0)
            du = float(c.get("m_Duration") or 0.0)
            a = objs.get((c.get("m_Asset") or {}).get("m_PathID"))
            anm = name_of(a)
            aty = a.type.name if a is not None else ""
            # ControlPlayableAsset 指向真实粒子 GO，取它的 m_SourceGameObject
            if aty == "MonoBehaviour" and a is not None:
                ad = tt(a) or {}
                src = objs.get((ad.get("m_SourceGameObject") or {}).get("m_PathID"))
                if src is not None:
                    anm = (anm or "") + "→" + name_of(src)
            rows.append([full, cls, go, str(i), f"{st:.3f}",
                         f"{st + du:.3f}", f"{du:.3f}", aty, anm])

        for ch in (d.get("m_Children") or []):
            walk((ch or {}).get("m_PathID"), full)

    for pp in (tasset.get("m_Tracks") or []):
        walk((pp or {}).get("m_PathID"), "")

    # ---- 写 tsv（按起始时间排序，方便看层级编排）
    hdr = ["轨道", "轨道类型", "绑定对象", "片段#", "起始s", "结束s", "时长s",
           "资源类型", "资源名"]
    tsv = outdir / f"{cid}_时序.tsv"
    body = rows[:]
    body.sort(key=lambda r: (r[4] == "", float(r[4]) if r[4] else 0.0))
    with tsv.open("w", encoding="utf-8-sig") as f:
        f.write("\t".join(hdr) + "\n")
        for r in body:
            f.write("\t".join(str(x).replace("\t", " ") for x in r) + "\n")
    print(f"[tsv] {tsv}  {len(rows)} 行")

    # ---- 贴图原样导出
    tdir = outdir / f"{cid}_贴图"
    tdir.mkdir(exist_ok=True)
    ntex = 0
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        try:
            d = o.read()
            im = d.image
        except Exception:
            continue
        nm = str(getattr(d, "m_Name", "") or f"tex_{o.path_id}")
        im.save(tdir / f"{nm}.png")
        ntex += 1
    print(f"[tex] {tdir}  {ntex} 张")

    # ---- 音频
    adir = outdir / f"{cid}_音频"
    adir.mkdir(exist_ok=True)
    naud = 0
    for o in env.objects:
        if o.type.name != "AudioClip":
            continue
        try:
            d = o.read()
            nm = str(getattr(d, "m_Name", "") or f"aud_{o.path_id}")
            (adir / f"{nm}.wav").write_bytes(d.samples)
            naud += 1
        except Exception:
            pass
    print(f"[aud] {adir}  {naud} 条")


if __name__ == "__main__":
    main()
