# -*- coding: utf-8 -*-
"""NIKKE Spine 小人 → 全身静帧 PNG（idle 首帧）。

用法：
    python render_spine.py <spine目录> <stem> <输出png> [动画名] [目标高度px]
"""
import base64
import re
import subprocess
import sys
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
NODE_MODULES = Path(r"D:\Codex\临时\spine_js\node_modules")
WORK = Path(r"D:\Codex\临时\spine_js\work")

APP_JS = r"""
const $ = id => document.getElementById(id);
const L = [];
const log = (...a) => { L.push(a.join(' ')); $('log').textContent = L.join('\n'); };
window.onerror = (m, s, l, c, e) => { log('WINDOW_ERR ' + m + ' @' + l); };

function b64u8(b) {
  const s = atob(b);
  const u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  return u;
}

const TARGET_H = parseInt($('cfg').dataset.h || '2000');
const WANT = $('cfg').dataset.anim || 'idle';
const atlasTxt = $('d-atlas').textContent;
const img = new Image();

img.onload = () => {
  try {
    // atlas 标记 pma:true，贴图是预乘的；canvas 不做预乘，需先反预乘否则边缘发白
    const oc = document.createElement('canvas');
    oc.width = img.width; oc.height = img.height;
    const octx = oc.getContext('2d', { willReadFrequently: true });
    octx.drawImage(img, 0, 0);
    const id = octx.getImageData(0, 0, oc.width, oc.height);
    const px = id.data;
    for (let i = 0; i < px.length; i += 4) {
      const a = px[i + 3];
      if (a > 0 && a < 255) {
        const k = 255 / a;
        px[i] = Math.min(255, px[i] * k);
        px[i + 1] = Math.min(255, px[i + 1] * k);
        px[i + 2] = Math.min(255, px[i + 2] * k);
      }
    }
    octx.putImageData(id, 0, 0);
    const atlas = new spine.TextureAtlas(atlasTxt);
    atlas.pages[0].texture = new spine.CanvasTexture(oc);
    const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
      .readSkeletonData(b64u8($('d-skel').textContent.trim()));
    const sk = new spine.Skeleton(data);
    const st = new spine.AnimationState(new spine.AnimationStateData(data));
    sk.setToSetupPose();
    let anim = WANT;
    if (!data.findAnimation(anim)) anim = data.animations[0].name;
    st.setAnimation(0, anim, true);
    st.update(0);
    st.apply(sk);
    sk.updateWorldTransform();

    const off = new spine.Vector2(), size = new spine.Vector2();
    sk.getBounds(off, size, []);
    const pad = 8;
    const sc = (TARGET_H - pad * 2) / size.y;
    const W = Math.ceil(size.x * sc) + pad * 2;
    const H = Math.ceil(size.y * sc) + pad * 2;
    const cv = $('c');
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    // spine 世界坐标 y 向上 → canvas y 向下
    ctx.setTransform(sc, 0, 0, -sc, pad - off.x * sc, H - pad + off.y * sc);
    const rd = new spine.SkeletonRenderer(ctx);
    rd.triangleRendering = true;
    rd.draw(sk);

    $('out').textContent = cv.toDataURL('image/png');
    log('OK anim=' + anim + ' size=' + W + 'x' + H +
        ' bounds=' + [off.x, off.y, size.x, size.y].map(v => v.toFixed(1)).join(','));
  } catch (e) {
    log('ERR ' + e.message + ' || ' + (e.stack || '').split('\n').slice(0, 3).join(' | '));
  }
};
img.onerror = () => log('PNG_LOAD_FAIL');
img.src = 'data:image/png;base64,' + $('d-png').textContent.trim();
"""


def render(spine_dir: Path, stem: str, out: Path, anim: str = "idle", height: int = 2000) -> str:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "app.js").write_text(APP_JS, encoding="utf-8")
    base = stem
    if not (spine_dir / f"{stem}.png").exists():
        for alt in (f"{stem}_uc", f"{stem}_0"):
            if (spine_dir / f"{alt}.png").exists():
                base = alt
                break
    atlas = (spine_dir / f"{base}.atlas").read_text(encoding="utf-8", errors="replace")
    skel = base64.b64encode((spine_dir / f"{base}.skel").read_bytes()).decode()
    png = base64.b64encode((spine_dir / f"{base}.png").read_bytes()).decode()
    nm = NODE_MODULES.as_posix()
    html = f"""<!DOCTYPE html><meta charset="utf-8">
<style>html,body{{margin:0;background:transparent}}</style>
<div id="cfg" data-anim="{anim}" data-h="{height}" style="display:none"></div>
<canvas id="c" width="8" height="8"></canvas>
<pre id="log" style="color:#c00;font:12px monospace"></pre>
<pre id="out" style="display:none"></pre>
<script id="d-atlas" type="text/plain">{atlas}</script>
<script id="d-skel" type="text/plain">{skel}</script>
<script id="d-png" type="text/plain">{png}</script>
<script src="file:///{nm}/@esotericsoftware/spine-core/dist/iife/spine-core.js"></script>
<script src="file:///{nm}/@esotericsoftware/spine-canvas/dist/iife/spine-canvas.js"></script>
<script src="app.js"></script>"""
    hp = WORK / f"{stem}__{anim}.html"
    hp.write_text(html, encoding="utf-8")

    p = subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        "--virtual-time-budget=12000", "--dump-dom", hp.as_uri()],
                       capture_output=True, timeout=300)
    dom = (p.stdout or b"").decode("utf-8", "replace")
    mlog = re.search(r'<pre id="log"[^>]*>(.*?)</pre>', dom, re.S)
    logtxt = (mlog.group(1) if mlog else "").strip()
    mout = re.search(r'<pre id="out"[^>]*>(data:image/png;base64,[A-Za-z0-9+/=]+)</pre>', dom, re.S)
    if not mout:
        return f"FAIL no-image | log={logtxt[:400]}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(mout.group(1).split(",", 1)[1]))
    from PIL import Image
    w, h = Image.open(out).size
    return f"OK {w}x{h} | {logtxt[:160]}"


if __name__ == "__main__":
    d, stem, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    anim = sys.argv[4] if len(sys.argv) > 4 else "idle"
    hh = int(sys.argv[5]) if len(sys.argv) > 5 else 2000
    print(render(d, stem, out, anim, hh))
