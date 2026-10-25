# -*- coding: utf-8 -*-
"""
批量导出 4 个 BOSS 形态的 idle 动图（GIF）。

渲染/量化/编码全部由查看器里的 `gif-export.js` 完成 —— 本脚本只负责
「开浏览器 → 切模型 → 点导出 → 收文件」，所以命令行导出与页面按钮导出的
结果是同一套算法，不会出现两份实现慢慢跑偏。

依赖：本地 http 服务（`启动查看器.bat` 会开在 8777，或手动
      `python -m http.server 8765 --bind 127.0.0.1`）。

用法：
  python export_gif.py                       # 默认 900 长边 / 15fps
  python export_gif.py --size 1200 --fps 20
  python export_gif.py --only xba003_2phase
"""
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import websocket

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9334
PAGE = "http://127.0.0.1:8765/index.html"
OUT_DIR = r"D:\Codex\临时\nikke_intl_20261029\out\gif_page\batch"

MODELS = [
    ("xba003", 1, "xba003_1phase", "安尼希利奥_1阶段"),
    ("xba003", 2, "xba003_2phase", "安尼希利奥_2阶段"),
    ("eba002", 1, "eba002_1phase", "莉贝雷利奥躯体_1阶段"),
    ("eba002", 2, "eba002_2phase", "莉贝雷利奥躯体_2阶段"),
]


class CDP:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=600)
        self.n = 0
        self.errs = []

    def send(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                self.errs.append(str(d.get("exception", {}).get("description", d.get("text"))))
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def ev(self, expr, await_promise=False):
        r = self.send("Runtime.evaluate", expression=expr,
                      returnByValue=True, awaitPromise=await_promise,
                      timeout=900000)
        res = r.get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(res.get("description", "eval error"))
        return res.get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def wait_server(timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(PAGE, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def start_chrome(prof):
    os.makedirs(prof, exist_ok=True)
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
            "--no-first-run", "--no-default-browser-check", "--window-size=960,960",
            f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
            f"--user-data-dir={prof}", "about:blank"]
    log = open(os.path.join(OUT_DIR, "_chrome.log"), "wb")
    p = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=2) as r:
                for t in json.loads(r.read()):
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return p, t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    p.kill()
    raise RuntimeError("Chrome 调试端口没起来")


def wait_file(path, timeout=240, stable=1.5):
    """等下载完成：文件存在且大小在 stable 秒内不再变化。"""
    end = time.time() + timeout
    last = -1
    t_same = 0
    while time.time() < end:
        if os.path.exists(path):
            sz = os.path.getsize(path)
            if sz == last and sz > 0:
                t_same += 0.4
                if t_same >= stable:
                    return True
            else:
                last, t_same = sz, 0
        time.sleep(0.4)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=900)
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    if not wait_server():
        print("本地 http 服务未响应，先启动：")
        print(r"  cd 3D查看器 && python -m http.server 8765 --bind 127.0.0.1")
        return 1

    prof = os.path.join(OUT_DIR, "_prof")
    proc, ws_url = start_chrome(prof)
    cdp = CDP(ws_url)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")

    ok = 0
    try:
        for boss, phase, key, label in MODELS:
            if a.only and key not in a.only:
                continue
            print("\n" + "=" * 60, flush=True)
            print(f"{key}  ({label})", flush=True)
            cdp.send("Page.navigate", url=f"{PAGE}?boss={boss}&phase={phase}&play=0&ui=0&bg=dark")
            time.sleep(1.5)

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

            # 用 base64 回传而不是浏览器下载：headless 的下载通道不稳定，
            # 而且这样能拿到真实的字节数做校验。
            t0 = time.time()
            js = """
            (async () => {
              const r = await window.__nkas.exportGif({longEdge: %d, fps: %d, dark: true});
              const buf = new Uint8Array(await r.blob.arrayBuffer());
              let s = '';
              const CH = 0x8000;
              for (let i = 0; i < buf.length; i += CH)
                s += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
              return JSON.stringify({w: r.width, h: r.height, frames: r.frames,
                                     delay: r.delay, bytes: r.bytes, elapsed: r.elapsed,
                                     loop: r.loopSec, b64: btoa(s)});
            })()
            """ % (a.size, a.fps)
            res = cdp.ev(js, await_promise=True)
            if not res:
                print("  导出返回空", flush=True)
                continue
            d = json.loads(res)
            b64 = d.pop("b64")
            raw = base64.b64decode(b64)

            dst = os.path.join(OUT_DIR, f"{label}_{a.size}p_{a.fps}fps.gif")
            with open(dst, "wb") as f:
                f.write(raw)

            print(f"  部件 {info['parts']} · 骨骼 {info['bones']}", flush=True)
            print(f"  {d['w']}×{d['h']} · {d['frames']} 帧 × {d['delay']}ms "
                  f"= {d['loop']:.2f}s · {len(raw)/1048576:.2f} MB", flush=True)
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

    print(f"\n完成 {ok} / {len(MODELS)}", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
