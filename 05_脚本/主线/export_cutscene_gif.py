# -*- coding: utf-8 -*-
"""把「爆裂特写」的 Spine 演出渲成 GIF + 首帧 PNG。

与大厅站立那套（export_lobby_gif.py）同一条管线，区别只有三点：

  1. **多层叠加**：一次爆裂演出由同一个骨架的两个实例同时驱动
     （Timeline 里两条 SpineAnimationStateTrack）。只播一条会缺件 ——
     c872 的 skillcut_1 单独渲只有「头 + 双手」，bg_skillcut_1 单独渲是空画面。
  2. **指定取景层**（?fit=）：背景层常常铺满画面或飞到很远，
     混进并集会把主体缩成一个点，所以取景只认前景那一层。
  3. 图层组合不是猜的，是从包里的 Timeline 读出来的（见 _probe_cut_tracks.py）：
        c870  TL0 0.100~4.083  skillcut_1 + skillcut_2
        c871  TL0 0.100~4.483  skillcut_0 + skillcut_1
        c872  TL1 0.100~4.200  skillcut_1 + bg_skillcut_1

用法：
  python export_cutscene_gif.py                 # 三套全出
  python export_cutscene_gif.py --only c871
  python export_cutscene_gif.py --long 1200
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_lobby_gif as L
from PIL import Image

OUT_GIF = r"D:\Codex\临时\nikke_intl_20261029\out\cut_gif"
OUT_PNG = r"D:\Codex\临时\nikke_intl_20261029\out\cut_png"

# id 用交付目录名，方便直接对着拷
# start / dur 来自 _probe_cut_tracks.py 读出的 Timeline 主演出窗
# （0.100 起，前面 0.1 秒是淡入前的空窗 —— 从 0 开始导会得到一张纯黑首帧）
JOBS = [
    # c870 是「场景 → 卡面」式爆裂（TL0 只有 skillcut_1 + skillcut_2，0.100~4.083）：
    #   skillcut_1 = 漫画卡面；skillcut_2 = 机车场景
    # **idle 不属于爆裂** —— 它在另一个 Timeline（TL1 3.983 起）里，是壁纸循环。
    # 前一版把 idle 当成「卡面层」叠进去，结果 4 秒全是同一张静止卡面，
    # 真正的演出被盖在下面。
    # 现在 idle 只作「取景参照」挂在第 0 层、用 hide=0 不画：
    # 它自己的包围盒 4500×4381 正好是卡面大小，能让构图回到正常比例
    # （skillcut 两条自带 11879×15102 的包围盒，拿它取景主体只剩一成）。
    # 开头 0~0.65s 两条都还没出场（渲染空帧），一并裁掉。
    {"id": "QUEEN（真）_c870", "asset": "c870_00_skillcut",
     "layers": ["idle", "skillcut_2", "skillcut_1"], "fit": 0, "q": 1.0,
     "hide": "0",
     "start": 0.100, "dur": 4.333, "trim": 0.650, "note": "场景→卡面",
     "out": "c870_00_skillcut"},
    # 开头 0~0.95s 是卡面入场的极端缩放：卡片被压成一条白线/白方块，
    # 渲出来是坏帧（不是空帧，覆盖率 2~11% 躲过了空帧过滤）。
    # 直接裁掉，从角色出场（t≈1.0）那一帧起步。
    {"id": "雪子_c871", "asset": "c871_00_skillcut",
     "layers": ["skillcut_1", "skillcut_0"], "fit": 1, "q": 0.9,
     "start": 0.100, "dur": 4.483, "trim": 0.950, "note": "骨骼演出",
     "out": "c871_00_skillcut"},
    {"id": "埃癸斯_c872", "asset": "c872_skillcut_00",
     "layers": ["bg_skillcut_1", "skillcut_1"], "fit": 1, "q": 0.9,
     "start": 0.100, "dur": 4.100, "trim": 0.0, "note": "骨骼演出",
     "out": "c872_00_skillcut"},
]


def save_gif_durs(frames, path, durs, colors=256):
    """写 GIF，支持每帧不同时长（空格帧被并进相邻帧后，时长要累加回去）。"""
    qs = [frames[0].quantize(colors=colors, method=Image.Quantize.MEDIANCUT)]
    qs += [f.quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                      dither=Image.Dither.NONE) for f in frames[1:]]
    qs[0].save(path, save_all=True, append_images=qs[1:], duration=durs,
               loop=0, optimize=True, disposal=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--long", type=int, default=1000, help="输出长边像素")
    ap.add_argument("--fps", type=int, default=15)
    a = ap.parse_args()

    jobs = JOBS
    if a.only:
        jobs = [j for j in JOBS if any(k in j["id"] or k in j["asset"] for k in a.only)]
    if not jobs:
        raise SystemExit("没有匹配的套")

    os.makedirs(OUT_GIF, exist_ok=True)
    os.makedirs(OUT_PNG, exist_ok=True)

    prof = os.path.join(L.ROOT, "_prof_cutexp")
    shutil.rmtree(prof, ignore_errors=True)
    proc, ws = L.start_chrome(prof)
    cdp = L.CDP(ws)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")

    results = []
    try:
        for j in jobs:
            name, aset = j["id"], j["asset"]
            print(f"\n=== {name}  ({j['note']})  layers={j['layers']} fit={j['fit']}")
            url = (f"{L.BASE}?asset=assets/{aset}/{aset}"
                   f"&ui=0&ss=2&layers={','.join(j['layers'])}"
                   f"&fit={j['fit']}&fitq={j['q']}")
            if j.get("hide"):
                url += f"&hide={j['hide']}"
            cdp.send("Page.navigate", url=url)
            time.sleep(1.2)
            info = None
            for _ in range(240):
                try:
                    if cdp.ev("!!(window.__spine && window.__spine.ready)"):
                        info = cdp.ev("window.__spine.info()")
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not info:
                print("  加载超时，跳过")
                continue

            got = cdp.ev("window.__spine.layers()")
            if got != j["layers"]:
                print(f"  !! 层不一致：{got}")
            durations = {x["name"]: x["duration"] for x in info["animations"]}
            clip = max(durations[n] for n in j["layers"] if n in durations)
            # trim：裁掉开头多少秒（那段渲出来是白线/灰条，留着就是坏帧）
            trim = j.get("trim", 0.0)
            start = j["start"] + trim
            dur = min(j["dur"], clip) - trim
            if dur <= 0.5:
                print(f"  !! trim 过大（{trim}s），跳过")
                continue
            b = cdp.ev("window.__spine.measure(12)")
            ar = b["w"] / b["h"]
            css_h = max(60, round(a.long / 2))
            css_w = max(40, round(css_h * ar))
            px = cdp.ev(f"window.__spine.resize({css_w},{css_h})")
            n, delay = L.plan_frames(dur, a.fps)
            out_w, out_h = round(a.long * ar), a.long
            print(f"  构图 {b['w']:.0f}×{b['h']:.0f} (比例 {ar:.3f}) · "
                  f"渲染 {px[0]}×{px[1]} px → 输出 {out_w}×{out_h} · "
                  f"区间 {start:.3f}~{start + dur:.3f}s -> {n} 帧 × {delay}ms")

            frames, t0 = [], time.time()
            for i in range(n):
                # 帧中心采样，且从演出窗起点算 —— 不从 0 开始，
                # 0~0.1s 是淡入前的空窗，那一帧骨架还没出场，渲出来就是纯黑。
                t = start + ((i + 0.5) / n) * dur
                cdp.ev(f"window.__spine.seek({t:.6f})")
                im = L.to_img(cdp.ev("window.__spine.capture()"))
                frames.append(im.resize((out_w, out_h), Image.LANCZOS))
            cost = time.time() - t0

            gif = os.path.join(OUT_GIF, f"{j['out']}.gif")
            # 先验原始渲染帧的覆盖率，再验写出的 GIF：
            # 两者不一致就说明是 GIF 调色板/合并的问题，不是渲染的问题。
            import numpy as np
            cov_raw = [float((np.abs(np.asarray(f, dtype="int16")).sum(axis=2) > 60).mean() * 100)
                       for f in frames]
            empty_raw = [i for i, c in enumerate(cov_raw) if c < 0.5]

            # 空格帧并进相邻帧：多层叠加时偶发整帧渲染不出来（c871 出现过 3 帧），
            # 直接留着就是黑闪。删掉这一帧、把它的 70ms 累加到前一帧，
            # 总时长不变，视觉上只是那一段少一帧。
            # 首帧为空时没有「前一帧」，把时长顺延给下一帧（carry）。
            keep, durs, carry = [], [], 0
            for i, f in enumerate(frames):
                if cov_raw[i] < 0.5:
                    if durs:
                        durs[-1] += delay
                    else:
                        carry += delay
                    continue
                keep.append(f)
                durs.append(delay + carry)
                carry = 0
            if carry:            # 整段都空（不该发生）：兜底留末帧
                durs[-1] += carry
            if not keep:
                keep, durs = [frames[-1]], [delay * len(frames)]
            save_gif_durs(keep, gif, durs)

            # 首帧 PNG 取「前景最多」的那一帧，不是第 0 帧（演出席开头是淡入，首帧常常是全黑）
            best_i = max(range(len(frames)), key=lambda i: cov_raw[i])
            png = os.path.join(OUT_PNG, f"{j['out']}_首帧.png")
            frames[best_i].save(png)
            d = L.motion_pct(frames)
            sz = os.path.getsize(gif) / 1048576
            # 写进 GIF 的实际帧数可能少于渲染帧数：PIL 的 optimize 会把
            # 连续完全相同的帧合并（时长累加，总时长不变）。清单记实际值，别记渲染值。
            import PIL.ImageSequence as _IS
            real_n = sum(1 for _ in _IS.Iterator(Image.open(gif)))
            total_s = sum(durs) / 1000
            print(f"  {out_w}×{out_h} · 帧 {real_n}/{n}（合并 {n - real_n}） · "
                  f"时长 {total_s:.2f}s · GIF {sz:.2f} MB · 动幅 {d:.2f}% · 耗时 {cost:.1f}s · "
                  f"首帧取第 {best_i} 帧（覆盖 {cov_raw[best_i]:.1f}%）")
            if empty_raw:
                print(f"  !! 渲染空帧 {len(empty_raw)} 个：{empty_raw[:12]}"
                      f"（已并入相邻帧，不留黑闪）")
            results.append({"id": name, "file": j["out"], "size": f"{out_w}x{out_h}", "frames": real_n,
                            "frames_rendered": n, "delay_ms": delay,
                            "total_s": round(total_s, 2), "clip_s": round(dur, 3),
                            "start_s": round(start, 3), "trim_s": round(trim, 3),
                            "empty_frames": len(empty_raw),
                            "gif_mb": round(sz, 2), "motion_pct": round(d, 2),
                            "layers": j["layers"], "hide": j.get("hide", ""),
                            "fit": j["fit"], "note": j["note"]})
    finally:
        cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)

    print(f"\n完成 {len(results)} / {len(jobs)}")
    import json
    mp = os.path.join(OUT_GIF, "_manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("->", mp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
