# -*- coding: utf-8 -*-
"""把「大厅站立」Spine 动画渲成 GIF + 首帧 PNG。

与 BOSS 3D 那套同一思路：headless Chrome + CDP 驱动页面里的
window.__spine.seek(t) 定帧，再走 canvas.toDataURL 取像素（同步读，
不会差帧），最后 PIL 合成。

三个必须遵守的约束（与 3D 版一致）：
  1. 不能用 Page.captureScreenshot —— 合成器异步，连拍会拿到上一帧；
  2. 裁剪框必须用整段动画的并集包围盒，逐帧自适应会让角色「呼吸」；
  3. GIF 帧延迟以 10 ms 为粒度，帧数要反解，不能按 fps 直接除。

用法：
  python export_lobby_gif.py                  # assets/ 下全部
  python export_lobby_gif.py --only c870_00
  python export_lobby_gif.py --anim idle --long 900
"""
import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import websocket
from PIL import Image

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9415
BASE = "http://127.0.0.1:8766/index.html"
ROOT = r"D:\Codex\临时\nikke_intl_20261029\spine_render"
ASSETS = os.path.join(ROOT, "assets")
OUT_GIF = r"D:\Codex\临时\nikke_intl_20261029\out\lobby_gif"
OUT_PNG = r"D:\Codex\临时\nikke_intl_20261029\out\lobby_png"
OUT_WEBP = r"D:\Codex\临时\nikke_intl_20261029\out\lobby_webp"
COLORS = 256


class CDP:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=600)
        self.n = 0

    def send(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("method") == "Runtime.exceptionThrown":
                d = m["params"]["exceptionDetails"]
                print("  [页面异常]", str(d.get("exception", {}).get("description", d.get("text")))[:200])
                continue
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    def ev(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise, timeout=900000)
        res = r.get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(str(res.get("description"))[:300])
        return res.get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def start_chrome(prof):
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
            f"--user-data-dir={prof}", "--window-size=1200,1400",
            "--force-device-scale-factor=1"]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2) as r:
                tabs = json.load(r)
            for t in tabs:
                if t.get("type") == "page":
                    return p, t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.4)
    p.kill()
    raise SystemExit("chrome 未就绪")


def plan_frames(clip, target_fps=15, n_min=16, n_max=130):
    """在 10 ms 网格上反解帧数，让 n×ms 最贴近原时长。"""
    best = None
    for ms in range(20, 201, 10):
        n = round(clip * 1000 / ms)
        if n < n_min or n > n_max:
            continue
        err = abs(n * ms / 1000 - clip) / clip
        fps = 1000 / ms
        score = err * 3 + abs(fps - target_fps) / target_fps
        if best is None or score < best[0]:
            best = (score, n, ms)
    if best is None:
        return max(n_min, round(clip * target_fps)), int(round(1000 / target_fps / 10) * 10)
    return best[1], best[2]


def to_img(data_url):
    b = data_url.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b))).convert("RGB")


def save_gif(frames, path, delay):
    pal = frames[0].quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT)
    qs = [pal] + [f.quantize(colors=COLORS, method=Image.Quantize.MEDIANCUT,
                             dither=Image.Dither.NONE) for f in frames[1:]]
    qs[0].save(path, save_all=True, append_images=qs[1:], duration=delay,
               loop=0, optimize=True, disposal=1)


def save_webp(frames, path, delay, quality=92):
    """动画 WebP：全彩无损色、无 GIF 色带，体积通常只有 GIF 的三到五成。"""
    frames[0].save(path, format="WEBP", save_all=True, append_images=frames[1:],
                   duration=delay, loop=0, quality=quality, method=4,
                   allow_mixed=True, minimize_size=False)


def motion_pct(frames):
    """动幅：取最多 7 帧两两比对，返回全局最大平均像素差（%）。

    不能用「首帧 vs 半周期帧」—— 循环动画在半周期处常常回到近似姿态，
    那样会算出接近 0，误判成「没动」。
    """
    import numpy as np
    n = len(frames)
    idx = sorted(set(round(i * (n - 1) / min(6, n - 1)) for i in range(min(7, n))))
    arr = [np.asarray(frames[i], dtype="float32") for i in idx]
    mx = 0.0
    for i in range(len(arr)):
        for j in range(i + 1, len(arr)):
            mx = max(mx, float(abs(arr[i] - arr[j]).mean() / 255 * 100))
    return mx


def diff_pct(a, b):
    import numpy as np
    x = np.asarray(a, dtype="float32")
    y = np.asarray(b, dtype="float32")
    return float(abs(x - y).mean() / 255 * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--anim", default="idle")
    ap.add_argument("--long", type=int, default=1000, help="输出长边像素")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--suffix", default="", help="输出文件名后缀，如 _action")
    ap.add_argument("--camera", default="idle",
                    help="用哪条动画的包围盒定构图（默认 idle）。"
                         "action 之类含飞出粒子的动画必须借 idle 的框，否则角色会被缩得很小")
    a = ap.parse_args()

    os.makedirs(OUT_GIF, exist_ok=True)
    os.makedirs(OUT_PNG, exist_ok=True)
    os.makedirs(OUT_WEBP, exist_ok=True)

    names = sorted(d for d in os.listdir(ASSETS)
                   if os.path.isdir(os.path.join(ASSETS, d))
                   and os.path.exists(os.path.join(ASSETS, d, d + ".skel")))
    if a.only:
        names = [n for n in names if n in a.only]
    print(f"待导出 {len(names)} 套：{names}")

    prof = os.path.join(ROOT, "_prof_exp")
    shutil.rmtree(prof, ignore_errors=True)
    proc, ws_url = start_chrome(prof)
    cdp = CDP(ws_url)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")

    ok = 0
    results = []
    try:
        for name in names:
            print(f"\n=== {name} ===")
            url = f"{BASE}?asset=assets/{name}/{name}&ui=0&ss=2"
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

            anims = [x["name"] for x in info["animations"]]
            if a.anim not in anims:
                print(f"  无 {a.anim} 动画（有 {anims[:6]}…），跳过")
                continue
            cam_anim = a.camera if a.camera in anims else a.anim
            cdp.ev(f"window.__spine.setAnim('{cam_anim}')")
            b = cdp.ev("window.__spine.measure(12)")
            ar = b["w"] / b["h"]
            # 画布按 long/SS 摆，实际像素 = long（超采样 2 倍后再降采样）
            css_h = max(60, round(a.long / 2))
            css_w = max(40, round(css_h * ar))
            px = cdp.ev(f"window.__spine.resize({css_w},{css_h})")
            if cam_anim != a.anim:
                cdp.ev(f"window.__spine.setAnim('{a.anim}', true)")
            clip = [x for x in info["animations"] if x["name"] == a.anim][0]["duration"]
            n, delay = plan_frames(clip, a.fps)
            out_w, out_h = round(a.long * ar), a.long
            cam_txt = "" if cam_anim == a.anim else f"[构图取自 {cam_anim}] "
            print(f"  {cam_txt}渲染 {px[0]}×{px[1]} px → 输出 {out_w}×{out_h} · {a.anim} {clip:.2f}s "
                  f"-> {n} 帧 × {delay}ms = {n*delay/1000:.2f}s")

            frames, t0 = [], time.time()
            for i in range(n):
                t = (i / n) * clip
                cdp.ev(f"window.__spine.seek({t:.6f})")
                im = to_img(cdp.ev("window.__spine.capture()"))
                frames.append(im.resize((out_w, out_h), Image.LANCZOS))
            cost = time.time() - t0

            gif = os.path.join(OUT_GIF, f"{name}{a.suffix}.gif")
            save_gif(frames, gif, delay)
            webp = os.path.join(OUT_WEBP, f"{name}{a.suffix}.webp")
            try:
                save_webp(frames, webp, delay)
                webp_sz = os.path.getsize(webp) / 1048576
            except Exception as e:
                webp_sz = None
                print("  WebP 失败:", e)
            frames[0].save(os.path.join(OUT_PNG, f"{name}{a.suffix}_首帧.png"))
            d = motion_pct(frames)
            sz = os.path.getsize(gif) / 1048576
            wtxt = f"{webp_sz:.2f} MB" if webp_sz else "—"
            print(f"  {frames[0].size[0]}×{frames[0].size[1]} · {n} 帧 · "
                  f"GIF {sz:.2f} MB / WebP {wtxt} · "
                  f"动幅 {d:.2f}% · 耗时 {cost:.1f}s")
            results.append((name + a.suffix, frames[0].size, n, delay, clip, sz, webp_sz, d, cost))
            ok += 1
    finally:
        cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)

    print(f"\n完成 {ok} / {len(names)}")
    if results:
        man = []
        print(f"\n{'套':<9}{'输出尺寸':<12}{'帧':>4}{'间隔':>6}{'时长':>8}"
              f"{'GIF MB':>8}{'WebP MB':>9}{'动幅%':>7}")
        for (name, size, n, delay, clip, sz, wsz, d, cost) in results:
            print(f"{name:<9}{str(size[0])+'×'+str(size[1]):<12}{n:>4}{delay:>6}"
                  f"{clip:>8.2f}{sz:>8.2f}{(wsz or 0):>9.2f}{d:>7.2f}")
            man.append({
                "id": name, "out": f"{size[0]}x{size[1]}", "frames": n,
                "delay_ms": delay, "clip_s": round(clip, 3),
                "gif_mb": round(sz, 2), "webp_mb": round(wsz, 2) if wsz else None,
                "motion_pct": round(d, 2),
            })
        # 合并写：--only 只导一部分时不能把其它套的记录冲掉。
        # （早先这里是 "w" 直写，补导 c580 时把原有 7 套的清单全清了）
        mpath = os.path.join(OUT_GIF, f"_manifest{a.suffix}.json")
        old = []
        if os.path.exists(mpath):
            try:
                with open(mpath, encoding="utf-8") as f:
                    old = json.load(f)
            except Exception:
                old = []
        by = {m["id"]: m for m in old}
        for m in man:
            by[m["id"]] = m
        merged = [by[k] for k in sorted(by)]
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"→ out/lobby_gif/_manifest{a.suffix}.json（{len(merged)} 条）")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
