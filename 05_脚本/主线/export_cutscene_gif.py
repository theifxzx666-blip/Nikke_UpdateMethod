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
  4. **分段取景**（segs）：演出里带「切镜」时，一个取景框必然框不住两段。
     逐层单独量过（probe_layer_scale.py），这两套的切镜是**动画自己在缩**：
        c872  t≈1.80 角色高 4321 → 2456（一帧内，1.76×）
        c871  t≈3.05 角色高 1944 → 1023（0.28 秒内，1.9×）
     不给每段单独取景，缩下去那半段就只剩个小人 —— 这正是
     「爆裂还原得差、人物缩得很小」的第二个来源（第一个是骨架框被撑飞）。

用法：
  python export_cutscene_gif.py                 # 三套全出
  python export_cutscene_gif.py --only c871
  python export_cutscene_gif.py --long 1200
"""
import argparse
import json
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
     "hide": "0", "autofit": 0.9,
     "start": 0.100, "dur": 4.333, "trim": 0.650, "note": "场景→卡面",
     "out": "c870_00_skillcut"},
    # 开头 0~0.95s 是卡面入场的极端缩放：卡片被压成一条白线/白方块，
    # 渲出来是坏帧（不是空帧，覆盖率 2~11% 躲过了空帧过滤）。
    # 直接裁掉，从角色出场（t≈1.0）那一帧起步。
    # 切镜：t≈3.05 角色从 1944 缩到 1023（变成远处小人 + 凤凰升起）。
    # 分两段取景，后段按「凤凰 + 小人」的并集框，凤凰才能铺满。
    # 切镜有三级：t≈0.80（卡面入场收尾）/ 2.20（凤凰开始升起）/ 3.00（变远处小人）。
    # 逐帧量到的内容高度：0.90~2.10 段 88~92%、2.30~2.90 段 60%、3.10 之后 32%。
    {"id": "雪子_c871", "asset": "c871_00_skillcut",
     "layers": ["skillcut_1", "skillcut_0"], "fit": 1, "q": 0.9, "autofit": 0.9,
     "segs": [[0.100, 2.200], [2.200, 3.000], [3.000, 4.583]],
     "start": 0.100, "dur": 4.483, "trim": 0.950, "note": "骨骼演出·三段",
     "out": "c871_00_skillcut"},
    # 三段：t≈1.80 一次「一帧内腰斩」（4321→2456），t≈2.47 碎玻璃层升起
    # （bg_skillcut_1 从 0 长到 4935）。三段各自取景，每段都能铺满。
    {"id": "埃癸斯_c872", "asset": "c872_skillcut_00",
     "layers": ["bg_skillcut_1", "skillcut_1"], "fit": 1, "q": 0.9, "autofit": 0.9,
     "segs": [[0.100, 1.800], [1.800, 2.450], [2.450, 4.200]],
     "start": 0.100, "dur": 4.100, "trim": 0.0, "note": "骨骼演出·三段",
     "out": "c872_00_skillcut"},
]


PAD = 1.06      # fitCamera 会给包围盒留 3% 边（两侧），换算时要乘回去


def probe_rects(cdp, t0, t1, n=16):
    """在 [t0,t1] 这一段里采 n 帧，返回每帧「非背景像素」的**画布像素**矩形。

    只取像素矩形，不取 probePixels 换算出来的 world —— 那套换算是按
    `bounds` 反推的，同一帧在不同相机下能差 2.5 倍（c871 t=1.0 量到 2202 和 5499），
    拿它当绝对尺度会翻车。像素占比是硬的：占画面多少就是多少。
    """
    rects = []
    for i in range(n):
        t = t0 + (i + 0.5) / n * (t1 - t0)
        cdp.ev(f"window.__spine.seek({t:.5f})")
        r = cdp.ev("JSON.stringify(window.__spine.probePixels(30))")
        if r and r != "null":
            rects.append(json.loads(r)["px"])
    return rects


def box_from_rects(rects, b0, q=0.9):
    """把「内容占画布的比例」换算成一个新的相机框。

    前提：当前画布的宽高比 == b0 的宽高比。此时 fitCamera 会把 b0 放大 3% 边
    之后**正好**铺满画布，于是「像素占比」和「世界占比」是同一个数，
    框 = b0 × 占比，中心按内容中心平移。不依赖相机内部尺度，因此不会随任务漂。

    先剔离群帧再取 q 分位：c872 在 t≈0.70 有一帧特效（爆裂的放射线）横跨整个画面，
    量到 90%×91%，一帧就把整段的框撑到天际 —— 这就是「中段人物缩成一个小人」的源头。
    判据用中位数的 1.8 倍，稳；剔完不足 3 帧就退回全集。

    取 q 分位而不是并集：让「主体最大那几帧刚好铺满」，动作帧手伸出画外是正常的；
    整段都缩小才是错的。
    """
    if len(rects) < 3:
        return None

    def qv(vals, p):
        a = sorted(vals)
        return a[min(len(a) - 1, max(0, round(p * (len(a) - 1))))]

    hs = [r["y1"] - r["y0"] + 1 for r in rects]
    ws = [r["x1"] - r["x0"] + 1 for r in rects]
    mh, mw = qv(hs, 0.5), qv(ws, 0.5)
    keep = [r for r, h, w in zip(rects, hs, ws)
            if h <= 1.8 * mh and w <= 1.8 * mw]
    if len(keep) < 3:
        keep = rects
    drop = len(rects) - len(keep)

    lo, hi = (1 - q) / 2, 1 - (1 - q) / 2
    x0 = qv([r["x0"] for r in keep], lo)
    x1 = qv([r["x1"] for r in keep], hi)
    y0 = qv([r["y0"] for r in keep], lo)
    y1 = qv([r["y1"] for r in keep], hi)
    W, H = rects[0]["w"], rects[0]["h"]
    fw, fh = (x1 - x0 + 1) / W, (y1 - y0 + 1) / H
    fw, fh = min(fw, 1.0), min(fh, 1.0)
    bw, bh = b0["w"] * PAD, b0["h"] * PAD
    return {
        "cx": b0["cx"] + (((x0 + x1) / 2) / W - 0.5) * bw,
        "cy": b0["cy"] + (0.5 - ((y0 + y1) / 2) / H) * bh,
        "w": bw * fw,
        "h": bh * fh,
        "cov": (round(fw * 100), round(fh * 100)),
        "drop": drop,
    }


def expand_to_ar(b, ar):
    """把框撑到指定宽高比 —— 只加边、不裁内容。

    分段的宽高比天然不同（c872：前段 0.95 / 中段 0.65 / 后段 1.06），
    可 GIF 画布只能有一个尺寸。统一到同一个 ar 后每段各占各的，
    补出来的边就是背景色，和画面底色一致，看不出来。
    """
    w, h = b["w"], b["h"]
    if w / h < ar:
        w = h * ar
    else:
        h = w / ar
    return {"cx": b["cx"], "cy": b["cy"], "w": w, "h": h}


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
            # fitq 固定 1.0：探针相机要用「并集框」，它一定装得下全部内容。
            # 用 0.9 会让 measure 先收紧一遍，收紧后的框里可能已经有内容被切掉，
            # 探针就量不到它，越量越小 —— 取景是两步，第一步只许大不许小。
            url = (f"{L.BASE}?asset=assets/{aset}/{aset}"
                   f"&ui=0&ss=2&layers={','.join(j['layers'])}"
                   f"&fit={j['fit']}&fitq=1.0")
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
            b_sk = cdp.ev("window.__spine.measure(12)")
            # 骨架 getBounds 给的框会被「某一个附件在某一帧被放大到天上」撑飞：
            # c870 的 skillcut_1 报 39675×34396，但实际画出来的内容只有 3005×3010，
            # 结果是**每一帧都恒定只占画面 63%×65%**，人物被均匀压小 —— 这就是
            # 「爆裂还原得差、人物缩得很小」的直接来源。改成渲一遍再看像素在哪。
            #
            # 探针必须让画布宽高比 == 骨架框宽高比：只有这样 fitCamera 才会把
            # 骨架框正好铺满画布，「像素占比」才等于「世界占比」（见 box_from_rects）。
            ar_sk = b_sk["w"] / b_sk["h"]
            probe_h = 300
            probe_w = max(60, round(probe_h * ar_sk))
            cdp.ev(f"window.__spine.setBounds({json.dumps(b_sk)})")
            cdp.ev(f"window.__spine.resize({probe_w},{probe_h})")

            # 分段：没写 segs 就是整条一段
            segs = j.get("segs") or [[start, start + dur]]
            # trim 落在第一段里（抬起点）、末段超出动画长度（削终点）——
            # segs 里写的是时间轴绝对秒数，手写容易写超，统一夹到有效区间
            segs = [[max(s, start), min(e, start + dur)] for s, e in segs]
            segs = [[s, e] for s, e in segs if e - s > 0.10]
            if not segs:
                print("  !! 分段全部退化，跳过")
                continue

            if j.get("autofit"):
                boxes = []
                for s, e in segs:
                    rects = probe_rects(cdp, s, e)
                    b = box_from_rects(rects, b_sk, j["autofit"])
                    if b is None:
                        print(f"  !! 段 {s:.2f}~{e:.2f} 像素探测失败"
                              f"（拿到 {len(rects)} 帧），沿用骨架框")
                        b = dict(b_sk, cov=(0, 0))
                    boxes.append(b)
            else:
                boxes = [dict(b_sk, cov=(0, 0))] * len(segs)

            # 统一宽高比：GIF 画布只能有一个尺寸，各段各补各的边（只加不裁）
            ar = max(b["w"] / b["h"] for b in boxes)
            seg_desc = " | ".join(
                f"段{k+1} 量到 {b['cov'][0]}%×{b['cov'][1]}% → 框 {b['w']:.0f}×{b['h']:.0f}"
                if b["cov"] != (0, 0) else f"段{k+1} 用骨架框 {b['w']:.0f}×{b['h']:.0f}"
                for k, b in enumerate(boxes))
            boxes = [expand_to_ar(b, ar) for b in boxes]
            print(f"  取景：{seg_desc}　统一比例 {ar:.2f}")

            css_h = max(60, round(a.long / 2))
            css_w = max(40, round(css_h * ar))
            out_w, out_h = round(a.long * ar), a.long
            delay = max(20, round(1000 / a.fps))
            print(f"  输出 {out_w}×{out_h} · " + " / ".join(
                f"+{e - s:.2f}s" for s, e in segs))

            frames, t0 = [], time.time()
            seg_first_end = 0        # 第 1 段占到第几帧 —— 首帧 PNG 只在第 1 段里挑
            for k, (s, e) in enumerate(segs):
                cdp.ev(f"window.__spine.setBounds({json.dumps(boxes[k])})")
                cdp.ev(f"window.__spine.resize({css_w},{css_h})")
                # 每段按自己的时长派帧，合起来总帧数≈整条 × fps
                n = max(3, round((e - s) * a.fps))
                for i in range(n):
                    # 帧中心采样，且从演出窗起点算 —— 不从 0 开始，
                    # 0~0.1s 是淡入前的空窗，那一帧骨架还没出场，渲出来就是纯黑。
                    t = s + ((i + 0.5) / n) * (e - s)
                    cdp.ev(f"window.__spine.seek({t:.6f})")
                    im = L.to_img(cdp.ev("window.__spine.capture()"))
                    frames.append(im.resize((out_w, out_h), Image.LANCZOS))
                if k == 0:
                    seg_first_end = len(frames)
            n = len(frames)
            cost = time.time() - t0

            gif = os.path.join(OUT_GIF, f"{j['out']}.gif")
            # 先验原始渲染帧的覆盖率，再验写出的 GIF：
            # 两者不一致就说明是 GIF 调色板/合并的问题，不是渲染的问题。
            #
            # 覆盖率的口径是「离背景色多远」，不是「亮度和多高」。
            # 早先用亮度阈值 (>60) 判，黑衣角色几乎全被算成空 —— c871 明明满幅
            # 跳舞的那一帧只报 23%，结果首帧 PNG 挑中了最暗的一帧。
            import numpy as np
            BG_PX = np.array([14, 17, 22], dtype="int16")
            cov_raw = [float((np.abs(np.asarray(f.convert("RGB"), dtype="int16") - BG_PX)
                              .sum(axis=2) > 30).mean() * 100) for f in frames]
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

            # 首帧 PNG 取「前景最多」的那一帧，不是第 0 帧（演出席开头是淡入，首帧常常是全黑）。
            # 只在第 1 段里挑：分段取景后每段都被归一化过，覆盖率差不多，
            # 一路取全场最大会挑到「碎玻璃/凤凰」那段（c872 上一版就挑到了第 60 帧），
            # 放进 PDF 角色卡的是特效而不是角色。
            pool = range(seg_first_end) if seg_first_end >= 3 else range(len(frames))
            best_i = max(pool, key=lambda i: cov_raw[i])
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
                            "segs": [[round(s, 3), round(e, 3)] for s, e in segs],
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
    mp = os.path.join(OUT_GIF, "_manifest.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("->", mp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
