# -*- coding: utf-8 -*-
"""批量拉取 + 导出：按 catalog 键正则匹配一族资源，逐个解包导出贴图 / 音频。

用法：
  python pull_batch.py --bucket dp --match "scenariobackground\\(hd\\)_assets_eventscene_chap_4[78]"
                       --kind tex --out "<目录>" [--manifest <tsv>] [--limit N]

要点：
  * 每个 bundle 单独走 pull_chunks（逐 chunk dd），避免 pull_bundle 的拼接错位
  * 贴图取包内面积最大的 Texture2D，原样导出（不做缩放，保真）
  * 音频直接取 AudioClip.samples（UnityPy 已解码为 wav），原样落盘
"""
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import UnityPy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pull_chunks  # noqa: E402

D = pull_chunks.D
BUCKETS = ["core", "dp", "saus", "ja", "fd"]


def all_keys():
    out = []
    for b in BUCKETS:
        c = sqlite3.connect(f"file:{D / (b + '_catalog.dec')}?mode=ro", uri=True)
        for (k,) in c.execute("select key from files_chunktype"):
            out.append((b, k))
        c.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=None)
    ap.add_argument("--match", required=True)
    ap.add_argument("--kind", default="tex", choices=["tex", "audio", "both"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--name-map", default=None, help="json 文件：{键后缀: 输出名}")
    a = ap.parse_args()

    rx = re.compile(a.match)
    keys = [(b, k) for b, k in all_keys()
            if rx.search(k) and (a.bucket is None or b == a.bucket)]
    keys.sort(key=lambda x: x[1])
    if a.limit:
        keys = keys[:a.limit]
    print(f"[match] {len(keys)} 个键")
    if not keys:
        raise SystemExit("无匹配键")

    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    nmap = {}
    if a.name_map:
        nmap = json.loads(Path(a.name_map).read_text(encoding="utf-8"))

    rows = []
    for i, (b, k) in enumerate(keys, 1):
        stem = re.sub(r"_[0-9a-f]{32}\.bundle$", "", k)
        stem = stem.split("_assets_", 1)[-1].replace("/", "_")
        tag = nmap.get(stem, stem)
        print(f"\n[{i}/{len(keys)}] {b} {stem}")
        try:
            bp = pull_chunks.pull(b, k, "_batch_cur.bundle")
        except SystemExit as e:
            print("   !! 拉取失败", e)
            rows.append([b, k, "", "", "", "拉取失败"])
            continue
        env = UnityPy.load(str(bp))
        got = []
        if a.kind in ("tex", "both"):
            texs = []
            for o in env.objects:
                if o.type.name != "Texture2D":
                    continue
                try:
                    d = o.read()
                    texs.append((d.m_Width * d.m_Height, d))
                except Exception:
                    pass
            if texs:
                texs.sort(key=lambda x: -x[0])
                d = texs[0][1]
                fp = outdir / f"{tag}.png"
                d.image.save(fp)
                got.append(f"tex {d.m_Width}x{d.m_Height} {d.m_TextureFormat} "
                           f"{fp.stat().st_size/1024:.0f}KB")
                rows.append([b, k, tag + ".png", f"{d.m_Width}x{d.m_Height}",
                             f"{fp.stat().st_size/1024:.0f}KB", "ok"])
            else:
                rows.append([b, k, "", "", "", "无 Texture2D"])
        if a.kind in ("audio", "both"):
            clips = []
            for o in env.objects:
                if o.type.name != "AudioClip":
                    continue
                try:
                    clips.append(o.read())
                except Exception:
                    pass
            if not clips:
                rows.append([b, k, "", "", "", "无 AudioClip"])
            for c in clips:
                try:
                    samples = c.samples
                except Exception as e:
                    rows.append([b, k, "", "", "", f"解码失败 {e}"])
                    continue
                for fn, data in samples.items():
                    fp = outdir / (tag + ("" if fn.endswith((".wav", ".ogg")) else ".wav"))
                    fp.write_bytes(data)
                    got.append(f"aud {c.m_Length:.2f}s {c.m_Frequency}Hz "
                               f"ch{c.m_Channels} {fp.stat().st_size/1024:.0f}KB")
                    rows.append([b, k, fp.name, f"{c.m_Length:.2f}s",
                                 f"{fp.stat().st_size/1024:.0f}KB", "ok"])
        # 不删中间包（见 pull_chunks.pull 的说明），固定名 _batch_cur.bundle 下一轮覆盖
        for g in got:
            print("   ", g)

    if a.manifest:
        p = Path(a.manifest)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = ["bucket\tkey\t导出文件\t规格\t体积\t状态"]
        lines += ["\t".join(r) for r in rows]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n[manifest] {p}  {len(rows)} 行")


if __name__ == "__main__":
    main()
