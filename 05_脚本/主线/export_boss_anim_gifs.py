# -*- coding: utf-8 -*-
"""BOSS 表演动画 GIF（登场 / 转阶段 / 战败）。

与 export_gif.py 的关系：同一套浏览器驱动 + 同一个 gif-export.js，
区别只是「切模型」的方式 —— idle 那 4 个按 boss+phase 取文件，
这里一条动画一个 glb，得用查看器新加的 `?glb=` 直接点名。

用法：
  python export_boss_anim_gifs.py                 # 全部 12 条
  python export_boss_anim_gifs.py --only xba003_2phase_death
  python export_boss_anim_gifs.py --size 700 --fps 12
"""
import argparse
import base64
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_gif as G                    # noqa: E402

OUT_DIR = r"D:\Codex\临时\nikke_intl_20261029\out\gif_boss_anim"

# (glb 文件, 输出名, 中文标签)
JOBS = [
    ("xba003_1phase_appearance.glb",  "安尼希利奥_1阶段_登场"),
    ("xba003_2phase_groggy_start.glb", "安尼希利奥_2阶段_转阶段开始"),
    ("xba003_2phase_groggy_loop.glb",  "安尼希利奥_2阶段_转阶段循环"),
    ("xba003_2phase_groggy_end.glb",   "安尼希利奥_2阶段_转阶段结束"),
    ("xba003_2phase_death.glb",        "安尼希利奥_2阶段_战败"),

    ("eba002_1phase_intro.glb",        "莉贝雷利奥躯体_1阶段_登场"),
    ("eba002_2phase_intro_01.glb",     "莉贝雷利奥躯体_2阶段_登场1"),
    ("eba002_2phase_intro_02.glb",     "莉贝雷利奥躯体_2阶段_登场2"),
    ("eba002_2phase_groggy_start.glb", "莉贝雷利奥躯体_2阶段_转阶段开始"),
    ("eba002_2phase_groggy_loop.glb",  "莉贝雷利奥躯体_2阶段_转阶段循环"),
    ("eba002_2phase_groggy_end.glb",   "莉贝雷利奥躯体_2阶段_转阶段结束"),
    ("eba002_2phase_death.glb",        "莉贝雷利奥躯体_2阶段_战败"),
]

JS = """
(async () => {
  let r;
  try {
    r = await window.__nkas.exportGif({longEdge: %d, fps: %d, dark: true});
  } catch (e) {
    return JSON.stringify({err: String((e && e.stack) || e)});
  }
  if (!r) return JSON.stringify({err: 'exportGif 返回了空值'});
  const buf = new Uint8Array(await r.blob.arrayBuffer());
  let s = '';
  const CH = 0x8000;
  for (let i = 0; i < buf.length; i += CH)
    s += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
  return JSON.stringify({w: r.width, h: r.height, frames: r.frames,
                         delay: r.delay, bytes: r.bytes, elapsed: r.elapsed,
                         loop: r.loopSec, b64: btoa(s)});
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=760)
    ap.add_argument("--fps", type=int, default=13)
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    if not G.wait_server():
        print("本地 http 服务未响应，先启动：")
        print(r"  cd D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服\05_主线_47-48章\07_关卡莱彻\3D查看器 && "
              r"python -m http.server 8765 --bind 127.0.0.1")
        return 1

    prof = os.path.join(OUT_DIR, "_prof")
    proc, ws_url = G.start_chrome(prof)
    cdp = G.CDP(ws_url)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")

    ok = 0
    jobs = JOBS
    if a.only:
        jobs = [j for j in JOBS if any(k in j[0] for k in a.only)]
    try:
        for i, (glb, label) in enumerate(jobs, 1):
            print("\n" + "=" * 60, flush=True)
            print(f"[{i}/{len(jobs)}] {label}  ← {glb}", flush=True)
            url = (f"{G.PAGE}?glb={glb}&title={label}&play=0&ui=0&bg=dark")
            cdp.send("Page.navigate", url=url)
            time.sleep(1.6)

            info = None
            for _ in range(200):
                try:
                    if cdp.ev("!!(window.__nkas && window.__nkas.ready)"):
                        info = cdp.ev("window.__nkas.info()")
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not info:
                print("  加载超时，跳过", flush=True)
                continue
            print(f"  info={info}", flush=True)
            if not info.get("clipLen"):
                print(f"  !! 无动画（clipLen=0），跳过", flush=True)
                continue

            t0 = time.time()
            try:
                res = cdp.ev(JS % (a.size, a.fps), await_promise=True)
            except Exception as e:
                print(f"  !! 页面内报错：{e}", flush=True)
                for x in cdp.errs[-3:]:
                    print("     " + str(x)[:400], flush=True)
                continue
            if not res:
                print("  导出返回空", flush=True)
                for x in cdp.errs[-3:]:
                    print("     " + str(x)[:400], flush=True)
                continue
            d = json.loads(res)
            if d.get("err"):
                print("  !! " + d["err"][:500], flush=True)
                continue
            raw = base64.b64decode(d.pop("b64"))

            dst = os.path.join(OUT_DIR, f"{label}.gif")
            with open(dst, "wb") as f:
                f.write(raw)
            print(f"  动画 {info['clipLen']:.2f}s · {d['w']}×{d['h']} · "
                  f"{d['frames']} 帧 × {d['delay']}ms = {d['loop']:.2f}s · "
                  f"{len(raw)/1048576:.2f} MB", flush=True)
            print(f"  页面内耗时 {d['elapsed']/1000:.1f}s · 总 {time.time()-t0:.1f}s", flush=True)
            ok += 1
    finally:
        cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)

    print(f"\n完成 {ok} / {len(jobs)}", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
