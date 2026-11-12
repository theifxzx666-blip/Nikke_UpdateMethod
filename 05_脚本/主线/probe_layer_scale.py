# -*- coding: utf-8 -*-
"""逐层单独量：某套多层演出里**每一层各自**画了什么、多大、什么时候出现。

为什么需要它：成品 GIF 里「人物缩得很小」有两种完全不同的原因 ——

  取景框虚大        → 整段都小，逐帧占比恒定；
  演出自己在切镜    → 占比一台阶一台阶往下掉。

只看叠起来的画面分不清，因为「缩下去以后」往往还有另一层在长（凤凰升起、
碎玻璃扩散）。一次只留一层量：

  c871  skillcut_0（角色）  前 2.4 s 恒定 2202 → t≈3.0 掉到 1023
        skillcut_1（凤凰）  2.69 s 才出现，从 1216 长到 2092
  c872  skillcut_1（角色）  3920~4510 → t≈1.80 一帧内掉到 2456
        bg_skillcut_1（碎玻璃） 2.47 s 才出现，从 3471 长到 4935

结论直接决定取景怎么改：不是把镜头拉近，而是**按切镜分段各取各的框**。

用法：
  python probe_layer_scale.py                  # 默认那套 JOBS 全量
  python probe_layer_scale.py --only c872 --n 60
输出 JSON：{"<套>/<层名>": [{t,w,h,cx,cy}, ...]}，另在终端打一份直方图。
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_lobby_gif as L

OUT = os.path.join(os.path.dirname(L.ROOT), "_layer_scale.json")

# 换期次时改这里：层名顺序必须和 Timeline 里的 Spine 轨道一致
JOBS = [
    {"tag": "c871", "asset": "c871_00_skillcut",
     "layers": ["skillcut_1", "skillcut_0"], "start": 0.100, "dur": 4.483},
    {"tag": "c872", "asset": "c872_skillcut_00",
     "layers": ["bg_skillcut_1", "skillcut_1"], "start": 0.100, "dur": 4.100},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="只量这些套（按 tag 匹配）")
    ap.add_argument("--n", type=int, default=32, help="每套采样帧数")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    jobs = [j for j in JOBS if not a.only or j["tag"] in a.only]

    prof = os.path.join(L.ROOT, "_prof_probe_layer")
    shutil.rmtree(prof, ignore_errors=True)
    proc, ws = L.start_chrome(prof)
    cdp = L.CDP(ws)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    out = {}
    try:
        for j in jobs:
            for si, solo in enumerate(j["layers"]):
                # hide 收的是「不画」的层序号 —— 除了自己，其余全藏
                hide = ",".join(str(k) for k in range(len(j["layers"])) if k != si)
                url = (f"{L.BASE}?asset=assets/{j['asset']}/{j['asset']}"
                       f"&ui=0&ss=1&layers={','.join(j['layers'])}&fit=0&hide={hide}")
                print(f"\n=== {j['tag']} / {solo}")
                cdp.send("Page.navigate", url=url)
                time.sleep(1.2)
                ok = False
                for _ in range(240):
                    try:
                        if cdp.ev("!!(window.__spine && window.__spine.ready)"):
                            ok = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.5)
                if not ok:
                    print("  加载超时，跳过")
                    continue
                cdp.ev("window.__spine.resize(240,240)")
                rows = []
                n = a.n
                for i in range(n):
                    t = j["start"] + (i + 0.5) / n * j["dur"]
                    cdp.ev(f"window.__spine.seek({t:.5f})")
                    r = cdp.ev("JSON.stringify(window.__spine.probePixels(28))")
                    if not r or r == "null":
                        rows.append({"t": round(t, 3), "h": 0, "w": 0, "cx": 0, "cy": 0})
                    else:
                        d = json.loads(r)["world"]
                        rows.append({"t": round(t, 3), "w": round(d["w"], 1),
                                     "h": round(d["h"], 1), "cx": round(d["cx"], 1),
                                     "cy": round(d["cy"], 1)})
                hs = [x["h"] for x in rows if x["h"] > 0]
                mx = max(hs) if hs else 0
                print(f"  max h={mx:.0f}")
                for x in rows[::2]:
                    pct = x["h"] / mx * 100 if mx else 0
                    bar = "#" * max(0, round(pct / 100 * 36))
                    print(f"   t={x['t']:5.2f} h={x['h']:8.0f} ({pct:5.1f}%) {bar}")
                out[f"{j['tag']}/{solo}"] = rows
    finally:
        cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)

    old = {}
    if os.path.exists(a.out):
        try:
            old = json.load(open(a.out, encoding="utf-8"))
        except Exception:
            old = {}
    old.update(out)
    json.dump(old, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n->", a.out)


if __name__ == "__main__":
    main()
