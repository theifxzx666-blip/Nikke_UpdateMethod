# -*- coding: utf-8 -*-
"""把爆裂特写三套产物归入 01_新角色/<角色>/爆裂动画/。

输入（都已在临时目录准备好）：
  out/sk1_<cid>.gif                Spine 角色层逐帧渲染
  out/cutscene_lw/<cid>_时序.tsv     Timeline 分层时序
  out/cutscene_lw/<cid>_贴图/        特效图集
  device/sfx_<cid>.bundle          角色音效包（ult_cutscene 等）

用法：
  python pack_cutscene.py <stage_root>
"""
import shutil
import sys
from pathlib import Path

import UnityPy

OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out")
# 用战斗内实播的那份包（spotskillcutscene）解析，与 GIF 同源；
# livewallpaperprefabs 里那份时间轴数值完全一致，只是贴图多 1~2 张。
LW = OUT / "cutscene_sk"
DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")

CHARS = [
    ("c870", "QUEEN（真）_c870"),
    ("c871", "雪子_c871"),
    ("c872", "埃癸斯_c872"),
]

# 音效：只取爆裂相关三条，其余（fire / sk1_buff / sk2_buff / sk1_hit_world）不在本目录范围
SFX_KEEP = {
    "ult_cutscene": "爆裂特写",
    "ult_cut": "爆裂切入",
    "ult_1more": "追加攻击",
}


def export_sfx(cid, dstdir):
    """爆裂音效。

    这批 AudioClip 的 PCM 不在包内：m_AudioData 为 None，
    数据挂在 `archive:/CAB-<hash>/CAB-<hash>.resource` 上，
    而 catalog 里没有对应的 .resource 条目 —— 定位不到 chunk，所以取不出来。
    这里只做存在性核对，不写文件。
    """
    bp = DEV / f"sfx_{cid}.bundle"
    if not bp.exists():
        return 0, 0
    env = UnityPy.load(str(bp))
    found = missing = 0
    for o in env.objects:
        if o.type.name != "AudioClip":
            continue
        try:
            d = o.read()
        except Exception:
            continue
        nm = str(getattr(d, "m_Name", "") or "")
        tail = nm[len(cid) + 1:] if nm.startswith(cid + "_") else nm
        if tail not in SFX_KEEP:
            continue
        found += 1
        if getattr(d, "m_AudioData", None) is not None:
            try:
                (dstdir / f"{nm}（{SFX_KEEP[tail]}）.wav").write_bytes(d.samples)
            except Exception:
                pass
        else:
            missing += 1
    return found, missing


def main():
    root = Path(sys.argv[1])
    for cid, dirname in CHARS:
        base = root / "01_新角色" / dirname / "爆裂动画"
        tex = base / "特效贴图"
        sfx = base / "爆裂音效"
        tex.mkdir(parents=True, exist_ok=True)
        sfx.mkdir(parents=True, exist_ok=True)

        gif = OUT / f"sk1_{cid}.gif"
        ok_gif = False
        if gif.exists():
            shutil.copy2(gif, base / f"爆裂特写_{cid}.gif")
            ok_gif = True

        tsv = LW / f"{cid}_时序.tsv"
        ok_tsv = False
        if tsv.exists():
            shutil.copy2(tsv, base / f"爆裂特写_分层时序_{cid}.tsv")
            ok_tsv = True

        src_tex = LW / f"{cid}_贴图"
        ntex = 0
        if src_tex.exists():
            for p in sorted(src_tex.glob("*.png")):
                shutil.copy2(p, tex / p.name)
                ntex += 1

        nsfx, nmiss = export_sfx(cid, sfx)

        sz = (base / f"爆裂特写_{cid}.gif").stat().st_size / 1048576 if ok_gif else 0
        print(f"[{cid}] {dirname}\n  gif={'OK %.2fMB' % sz if ok_gif else '缺'}"
              f"  tsv={'OK' if ok_tsv else '缺'}  贴图={ntex}  音效=命中{nsfx}/无数据{nmiss}\n  → {base}")


if __name__ == "__main__":
    main()
