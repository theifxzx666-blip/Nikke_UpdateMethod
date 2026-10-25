# -*- coding: utf-8 -*-
"""在线验收：打开 GitHub Pages 上的 3D 查看器，确认 glb 真的加载、动画真的在播。

只做三件事：
  1. 打开页面，等 window.__nkas 就绪；
  2. 读 __nkas.bbox()（WebGL 内容用 canvas.toDataURL 取像素，不能用 Page.captureScreenshot）；
  3. 两个路径各截一张：默认四个 idle、以及 ?glb= 点名的战败动画。

用法：python verify_pages_3d.py
"""
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
PORT = 9419
PROXY = "http://127.0.0.1:7897"
BASE = "https://theifxzx666-blip.github.io/Nikke_Lecher_3D/"
OUT = r"D:\Codex\临时\nikke_intl_20261029\out\_pageschk"

# 探测 127.0.0.1 必须绕开 http_proxy，否则 urlopen 会把本地端口也丢给代理
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class CDP:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=120)
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
                      awaitPromise=await_promise, timeout=120000)
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
    args = [CHROME, "--headless=new", "--hide-scrollbars",
            f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
            f"--user-data-dir={prof}", "--window-size=1280,900",
            f"--proxy-server={PROXY}",
            "--use-gl=angle", "--use-angle=swiftshader",   # 无头也要真 WebGL
            "--enable-unsafe-swiftshader"]
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            with _OPENER.open(f"http://127.0.0.1:{PORT}/json", timeout=2) as r:
                for t in json.load(r):
                    if t.get("type") == "page":
                        return p, t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    p.kill()
    raise SystemExit("chrome 未就绪")


def shot(cdp, path):
    d = cdp.ev("document.querySelector('canvas').toDataURL('image/png')")
    if not d or not d.startswith("data:image"):
        print("  !! 取不到画布")
        return False
    with open(path, "wb") as f:
        f.write(base64.b64decode(d.split(",", 1)[1]))
    print("  ->", path, round(os.path.getsize(path) / 1024, 1), "KB")
    return True


def wait_ready(cdp, n=180):
    """等到 bbox() 真的返回包围盒 —— 光等 __nkas 存在不够，
    页面脚本注册完探针到模型加载完之间有一段空窗，那段时间截出来是全黑的。"""
    for _ in range(n):
        try:
            if cdp.ev("!!(window.__nkas && window.__nkas.bbox && window.__nkas.bbox())"):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "_pageschk_prof")
    shutil.rmtree(prof, ignore_errors=True)
    proc, ws = start_chrome(prof)
    cdp = CDP(ws)
    cdp.send("Page.enable")
    cdp.send("Runtime.enable")
    ok = True
    try:
        # 1) 默认：四个 idle
        print("\n=== 默认页（四个 idle）===")
        cdp.send("Page.navigate", url=BASE)
        time.sleep(2)
        if not wait_ready(cdp):
            print("  !! 页面未就绪")
            ok = False
        else:
            time.sleep(3)
            print("  bbox:", cdp.ev("JSON.stringify(window.__nkas.bbox())"))
            print("  标题:", cdp.ev("window.__nkas.name || (document.querySelector('#meta')||{}).innerText || ''"))
            ok &= shot(cdp, os.path.join(OUT, "online_idle.png"))

        # 2) 点名一条战败动画
        print("\n=== ?glb= 点名（莉贝雷利奥 2 阶段战败）===")
        cdp.send("Page.navigate", url=BASE + "?glb=eba002_2phase_death.glb"
                 "&title=莉贝雷利奥躯体_2阶段_战败&play=0")
        time.sleep(2)
        if wait_ready(cdp):
            time.sleep(3)
            print("  bbox:", cdp.ev("JSON.stringify(window.__nkas.bbox())"))
            ok &= shot(cdp, os.path.join(OUT, "online_death.png"))
        else:
            print("  !! 未就绪")
            ok = False
    finally:
        cdp.close()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        shutil.rmtree(prof, ignore_errors=True)
    print("\n验收:", "通过" if ok else "有问题")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
