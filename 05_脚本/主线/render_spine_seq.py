# -*- coding: utf-8 -*-
"""爆裂技能特写（spotskillcutscene）里的 Spine 立绘动画 → GIF。

为什么只取 Spine 这一层：
  `spotskillcutscene_assets_c87x_00_cut_scene` 是一个 Timeline 预制体：
  1 个 PlayableDirector + 42 个 ParticleSystem + 6 个空 AnimationClip + 1 套 Spine。
  客户端没有下发 PlayableDirector / TimelineAsset 的 TypeTree，轨道起始时间读不出来，
  6 个 AnimationClip 的曲线又全是空的 —— 也就是说**粒子各层的出场时序无法从文件还原**。
  但 Spine 骨骼（c87x_00_skillcut.skel/.atlas/.png）是完整的，正是爆裂特写里角色那一层，
  所以这里逐帧渲染 Spine 动画，粒子层不掺进来（掺进来只会变成一坨同时爆开的噪点）。

用法：
  python render_spine_seq.py <bundle> <out_gif> [--height 900] [--fps 20] [--anim 名称]
"""
import argparse
import base64
import io
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import UnityPy
from PIL import Image

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
NODE_MODULES = Path(r"D:\Codex\临时\spine_js\node_modules")
WORK = Path(r"D:\Codex\临时\spine_js\work")

APP_JS = r"""
const $ = id => document.getElementById(id);
const L = [];
const log = (...a) => { L.push(a.join(' ')); $('log').textContent = L.join('\n'); };
window.onerror = (m, s, l, c, e) => { log('WINDOW_ERR ' + m + ' @' + l); };

function b64u8(b) {
  const s = atob(b); const u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  return u;
}

const TARGET_H = parseInt($('cfg').dataset.h || '900');
const FPS = parseFloat($('cfg').dataset.fps || '20');
const WANT = $('cfg').dataset.anim || '';
const F0 = parseInt($('cfg').dataset.f0 || '0');
const NREQ = parseInt($('cfg').dataset.n || '0');
const MODE = $('cfg').dataset.mode || 'sheet';
const BB = $('cfg').dataset.bb || '';
const img = new Image();

img.onload = () => {
  try {
    const oc = document.createElement('canvas');
    oc.width = img.width; oc.height = img.height;
    const octx = oc.getContext('2d', { willReadFrequently: true });
    octx.drawImage(img, 0, 0);
    // atlas 声明 pma:true，贴图是预乘的；canvas 不预乘，先反预乘否则边缘发白
    const id = octx.getImageData(0, 0, oc.width, oc.height), px = id.data;
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

    const atlas = new spine.TextureAtlas($('d-atlas').textContent);
    atlas.pages[0].texture = new spine.CanvasTexture(oc);
    const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
      .readSkeletonData(b64u8($('d-skel').textContent.trim()));
    const sk = new spine.Skeleton(data);
    const st = new spine.AnimationState(new spine.AnimationStateData(data));

    const names = data.animations.map(a => a.name + ':' + a.duration.toFixed(2));
    let anim = WANT;
    if (!anim || !data.findAnimation(anim)) {
      anim = data.animations.reduce((b, a) =>
        (!b || a.duration > b.duration) ? a : b, null).name;
    }
    const clip = data.findAnimation(anim);
    const dur = clip.duration;
    const frames = Math.max(2, Math.min(200, Math.round(dur * FPS)));

    function pose(t) {
      st.setAnimation(0, anim, false);
      st.update(0);
      st.apply(sk);
      sk.setToSetupPose();
      st.setAnimation(0, anim, false);
      st.update(0);
      st.apply(sk);
      // 从 0 步进到 t
      st.setAnimation(0, anim, false);
      st.update(0); st.apply(sk);
      let acc = 0;
      const dt = 1 / 240;
      while (acc < t - 1e-6) { st.update(Math.min(dt, t - acc)); acc += dt; }
      st.apply(sk);
      sk.updateWorldTransform();
    }

    // 包围盒。优先用外部给的内容包围盒（data-bb），否则退回骨架并集包围盒。
    // 注意：骨架并集包围盒会被「alpha=0 但尺寸巨大」的背景件撑大，
    // 直接用会让角色缩成一个小点，所以正式出图前先跑一次 mode=bb 量真实内容框。
    let x0, y0, x1, y1;
    if (BB) {
      [x0, y0, x1, y1] = BB.split(',').map(Number);
    } else {
      x0 = 1e9; y0 = 1e9; x1 = -1e9; y1 = -1e9;
      for (let i = 0; i < frames; i++) {
        pose(i / FPS);
        const off = new spine.Vector2(), size = new spine.Vector2();
        sk.getBounds(off, size, []);
        if (size.x <= 0 || size.y <= 0) continue;
        x0 = Math.min(x0, off.x); y0 = Math.min(y0, off.y);
        x1 = Math.max(x1, off.x + size.x); y1 = Math.max(y1, off.y + size.y);
      }
    }
    if (!(x1 > x0 && y1 > y0)) throw new Error('bounds empty');
    const pad = 10;

    if (MODE === 'bb') {
      // 逐帧画到探针画布，扫 alpha 求真实内容包围盒，再换回世界坐标。
      // 骨架 getBounds 会低估（不裁切附件），直接用它当画布边界会把贴图切在边上，
      // 所以先按 8% 外扩再探，保证内容完整落在画布内。
      const ix = (x1 - x0) * 0.08, iy = (y1 - y0) * 0.08;
      x0 -= ix; x1 += ix; y0 -= iy; y1 += iy;
      const psc = (1024 - pad * 2) / Math.max(y1 - y0, 1);
      const pw = Math.max(8, Math.ceil((x1 - x0) * psc) + pad * 2);
      const ph = Math.max(8, Math.ceil((y1 - y0) * psc) + pad * 2);
      const tmp = document.createElement('canvas');
      tmp.width = pw; tmp.height = ph;
      const tctx = tmp.getContext('2d', { willReadFrequently: true });
      const rd2 = new spine.SkeletonRenderer(tctx);
      rd2.triangleRendering = true;
      let cx0 = 1e9, cy0 = 1e9, cx1 = -1e9, cy1 = -1e9;
      // 同时按帧收集，便于剔除个别帧的离群附件（比如某帧突然拉出一个超长影子）
      const perX0 = [], perY0 = [], perX1 = [], perY1 = [];
      for (let i = 0; i < frames; i++) {
        pose(i / FPS);
        tctx.setTransform(1, 0, 0, 1, 0, 0);
        tctx.clearRect(0, 0, pw, ph);
        tctx.setTransform(psc, 0, 0, -psc, pad - x0 * psc, ph - pad + y0 * psc);
        rd2.draw(sk);
        const d = tctx.getImageData(0, 0, pw, ph).data;
        let fx0 = 1e9, fy0 = 1e9, fx1 = -1e9, fy1 = -1e9;
        for (let y = 0; y < ph; y++) {
          const row = y * pw * 4;
          for (let x = 0; x < pw; x++) {
            if (d[row + x * 4 + 3] > 8) {
              if (x < fx0) fx0 = x; if (x > fx1) fx1 = x;
              if (y < fy0) fy0 = y; if (y > fy1) fy1 = y;
            }
          }
        }
        if (fx1 >= fx0) {
          perX0.push(fx0); perY0.push(fy0); perX1.push(fx1); perY1.push(fy1);
          if (fx0 < cx0) cx0 = fx0; if (fx1 > cx1) cx1 = fx1;
          if (fy0 < cy0) cy0 = fy0; if (fy1 > cy1) cy1 = fy1;
        }
      }
      if (cx1 < cx0) throw new Error('probe empty');
      const toW = (px, py) => [
        (px - pad) / psc + x0,
        y0 + (ph - pad - py) / psc,
      ];
      const [rx0, ry1] = toW(cx0, cy0);
      const [rx1, ry0] = toW(cx1, cy1);
      // 稳健框：每侧取 10% / 90% 分位，避免单帧离群把画面撑飞
      const q = (arr, p) => {
        const a = arr.slice().sort((m, n) => m - n);
        return a[Math.min(a.length - 1, Math.max(0, Math.round((a.length - 1) * p)))];
      };
      const sx0 = perX0.length ? q(perX0, 0.10) : cx0;
      const sx1 = perX1.length ? q(perX1, 0.90) : cx1;
      const sy0 = perY0.length ? q(perY0, 0.10) : cy0;
      const sy1 = perY1.length ? q(perY1, 0.90) : cy1;
      const [tx0, ty1] = toW(sx0, sy0);
      const [tx1, ty0] = toW(sx1, sy1);
      log('BB ' + [rx0, ry0, rx1, ry1].map(v => v.toFixed(3)).join(',') +
          ' BBq ' + [tx0, ty0, tx1, ty1].map(v => v.toFixed(3)).join(',') +
          ' anim=' + anim + ' dur=' + dur.toFixed(3) + ' frames=' + frames +
          ' animations=' + names.join('|'));
      return;
    }

    const sc = (TARGET_H - pad * 2) / (y1 - y0);
    const W = Math.ceil((x1 - x0) * sc) + pad * 2;
    const H = TARGET_H;

    // 第二遍：只画本批 [F0, F0+NREQ)
    const b0 = Math.min(frames, Math.max(0, F0));
    const bn = Math.min(NREQ > 0 ? NREQ : frames - b0, frames - b0);
    const sheet = $('c');
    sheet.width = W * Math.max(1, bn); sheet.height = H;
    const ctx = sheet.getContext('2d');
    const rd = new spine.SkeletonRenderer(ctx);
    rd.triangleRendering = true;
    for (let k = 0; k < bn; k++) {
      pose((b0 + k) / FPS);
      ctx.save();
      ctx.beginPath(); ctx.rect(k * W, 0, W, H); ctx.clip();
      // spine 世界 y 向上 → canvas y 向下
      ctx.setTransform(sc, 0, 0, -sc, k * W + pad - x0 * sc, H - pad + y0 * sc);
      rd.draw(sk);
      ctx.restore();
    }
    $('out').textContent = sheet.toDataURL('image/png');
    log('OK anim=' + anim + ' dur=' + dur.toFixed(3) + ' frames=' + frames +
        ' batch=' + b0 + '+' + bn + ' cell=' + W + 'x' + H +
        ' animations=' + names.join('|'));
  } catch (e) {
    log('ERR ' + e.message + ' || ' + (e.stack || '').split('\n').slice(0, 3).join(' | '));
  }
};
img.onerror = () => log('PNG_LOAD_FAIL');
img.src = 'data:image/png;base64,' + $('d-png').textContent.trim();
"""


def extract(bundle: Path, outdir: Path):
    """从爆裂动画包里抠出 spine 三件套，返回 stem。"""
    outdir.mkdir(parents=True, exist_ok=True)
    env = UnityPy.load(str(bundle))
    skel = atlas = png = None
    texs = {}
    for o in env.objects:
        if o.type.name == "TextAsset":
            d = o.read()
            raw = d.m_Script if isinstance(d.m_Script, (bytes, bytearray)) else \
                d.m_Script.encode("utf-8", "surrogateescape")
            if d.m_Name.endswith(".skel"):
                skel = (d.m_Name[:-5], raw)
            elif d.m_Name.endswith(".atlas"):
                atlas = (d.m_Name[:-6], raw)
        elif o.type.name == "Texture2D":
            try:
                d = o.read()
                texs[d.m_Name] = d
            except Exception:
                pass
    if not (skel and atlas):
        raise SystemExit(f"{bundle.name} 里没有 skel/atlas")
    stem = skel[0]
    # atlas 里声明的页图名（去掉 .png）
    page = None
    for ln in atlas[1].decode("utf-8", "replace").splitlines():
        if ln.strip().endswith(".png") and not ln.startswith(" "):
            page = ln.strip()[:-4]
            break
    png = texs.get(page) or texs.get(stem)
    if png is None:
        raise SystemExit(f"找不到 atlas 页图 {page}（包内贴图：{list(texs)[:5]}）")
    (outdir / f"{stem}.skel").write_bytes(skel[1])
    (outdir / f"{stem}.atlas").write_bytes(atlas[1])
    im = png.image.convert("RGBA")
    # atlas 头部声明了页图尺寸（如 size:2048,2048），客户端下发的 Texture2D 可能只有
    # 一半分辨率（本例 1024×1024）。region 的 bounds 是按声明尺寸给的，若不等比缩放贴图，
    # 采样会整个偏出有效区 —— 表现就是几乎全空。这里按声明尺寸等比放大。
    m = re.search(r"^size:\s*(\d+)\s*,\s*(\d+)", atlas[1].decode("utf-8", "replace"), re.M)
    note = ""
    if m:
        aw, ah = int(m.group(1)), int(m.group(2))
        if (aw, ah) != im.size:
            im = im.resize((aw, ah), Image.LANCZOS)
            note = f"（贴图 {png.m_Width}x{png.m_Height} 按 atlas 声明 {aw}x{ah} 放大）"
    im.save(outdir / f"{stem}.png")
    return stem, im.size[0], im.size[1], note


def _run_chrome(sdir, stem, height, fps, anim, f0, nreq, tag, mode="sheet", bb=""):
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "app_seq.js").write_text(APP_JS, encoding="utf-8")
    atlas = (sdir / f"{stem}.atlas").read_text(encoding="utf-8", errors="replace")
    skel = base64.b64encode((sdir / f"{stem}.skel").read_bytes()).decode()
    png = base64.b64encode((sdir / f"{stem}.png").read_bytes()).decode()
    nm = NODE_MODULES.as_posix()
    html = f"""<!DOCTYPE html><meta charset="utf-8">
<style>html,body{{margin:0;background:transparent}}</style>
<div id="cfg" data-anim="{anim}" data-h="{height}" data-fps="{fps}"
     data-f0="{f0}" data-n="{nreq}" data-mode="{mode}" data-bb="{bb}"
     style="display:none"></div>
<canvas id="c" width="8" height="8"></canvas>
<pre id="log" style="color:#c00;font:12px monospace"></pre>
<pre id="out" style="display:none"></pre>
<script id="d-atlas" type="text/plain">{atlas}</script>
<script id="d-skel" type="text/plain">{skel}</script>
<script id="d-png" type="text/plain">{png}</script>
<script src="file:///{nm}/@esotericsoftware/spine-core/dist/iife/spine-core.js"></script>
<script src="file:///{nm}/@esotericsoftware/spine-canvas/dist/iife/spine-canvas.js"></script>
<script src="app_seq.js"></script>"""
    hp = WORK / f"seq_{stem}_{tag}.html"
    hp.write_text(html, encoding="utf-8")
    p = subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        "--virtual-time-budget=180000", "--dump-dom", hp.as_uri()],
                       capture_output=True, timeout=1800)
    dom = (p.stdout or b"").decode("utf-8", "replace")
    mlog = re.search(r'<pre id="log"[^>]*>(.*?)</pre>', dom, re.S)
    logtxt = (mlog.group(1) if mlog else "").strip()
    mout = re.search(r'<pre id="out"[^>]*>(data:image/png;base64,[A-Za-z0-9+/=]+)</pre>', dom, re.S)
    img = None
    if mout:
        img = Image.open(io.BytesIO(
            base64.b64decode(mout.group(1).split(",", 1)[1]))).convert("RGBA")
    return img, logtxt


def probe_bbox(sdir, stem, height, fps, anim):
    img, logtxt = _run_chrome(sdir, stem, height, fps, anim, 0, 0, "bb", mode="bb")
    m = re.search(r"BB ([\-0-9.,]+) anim=(\S+) dur=([0-9.]+) frames=(\d+)", logtxt)
    if not m:
        raise SystemExit(f"包围盒探测失败: {logtxt[:300]}")
    bb = m.group(1)
    print(f"  [bbox] {bb}  anim={m.group(2)} dur={m.group(3)}s frames={m.group(4)}")
    return bb, m.group(2), int(m.group(4)), m.group(3)


def _one_batch(sdir, stem, height, fps, anim, f0, nreq, tag, bb):
    img, logtxt = _run_chrome(sdir, stem, height, fps, anim, f0, nreq, tag, bb=bb)
    if img is None:
        return None, f"FAIL no-image | {logtxt[:400]}"
    m = re.search(r"frames=(\d+) batch=\d+\+(\d+) cell=(\d+)x(\d+)", logtxt)
    if not m:
        return None, f"FAIL no-meta | {logtxt[:300]}"
    return dict(sheet=img, total=int(m.group(1)), bn=int(m.group(2)),
                W=int(m.group(3)), H=int(m.group(4))), logtxt


def render(sdir: Path, stem: str, out_gif: Path, height=900, fps=12.5, anim="", batch=6,
           force_bb=""):
    if force_bb:
        bb, anim = force_bb, anim or "idle"
        _img0, log0 = _run_chrome(sdir, stem, height, fps, anim, 0, 1, "meta", bb=bb)
        m = re.search(r"frames=(\d+)", log0)
        total = int(m.group(1)) if m else 0
        dur = "-"
        print(f"  [bbox] 沿用外部包围盒 {bb}  anim={anim} frames={total}")
    else:
        bb, anim, total, dur = probe_bbox(sdir, stem, height, fps, anim)
    frames = []
    f0 = 0
    while f0 < total:
        info, logtxt = _one_batch(sdir, stem, height, fps, anim, f0, batch, f"{f0:03d}", bb)
        if info is None:
            return None, logtxt
        W, H, bn = info["W"], info["H"], info["bn"]
        for k in range(bn):
            frames.append(info["sheet"].crop((k * W, 0, (k + 1) * W, H)))
        f0 += bn
        print(f"    batch {f0}/{total}  cell={W}x{H}")
        if bn == 0:
            break
    if not frames:
        return None, "FAIL no frames"
    out_gif.parent.mkdir(parents=True, exist_ok=True)
    delay = int(round(1000 / fps))
    bgc = Image.new("RGBA", frames[0].size, (250, 250, 248, 255))
    rgb = []
    for f in frames:
        b = bgc.copy()
        b.alpha_composite(f)
        rgb.append(b.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT,
                                             dither=Image.FLOYDSTEINBERG))
    rgb[0].save(out_gif, save_all=True, append_images=rgb[1:],
                duration=delay, loop=0, optimize=True, disposal=2)
    prev = out_gif.with_name(out_gif.stem + "_首帧预览.png")
    b0 = Image.new("RGBA", frames[0].size, (250, 250, 248, 255))
    b0.alpha_composite(frames[0])
    b0.convert("RGB").save(prev)
    return dict(frames=len(frames), cell=frames[0].size, delay=delay,
                preview=prev, anim=anim, dur=dur, bb=bb), "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("out")
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--fps", type=float, default=12.5)
    ap.add_argument("--anim", default="")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--bb", default="", help="强制使用该内容包围盒 x0,y0,x1,y1")
    ap.add_argument("--spine-dir", default=None)
    a = ap.parse_args()
    bp = Path(a.bundle)
    sdir = Path(a.spine_dir) if a.spine_dir else \
        Path(r"D:\Codex\临时\nikke_intl_20261029\out\cutscene_spine") / bp.stem
    stem, tw, th, note = extract(bp, sdir)
    print(f"[extract] {stem}  atlas 页图 {tw}x{th} {note} -> {sdir}")
    info, logtxt = render(sdir, stem, Path(a.out), a.height, a.fps, a.anim, a.batch, a.bb)
    print("[render]", logtxt)
    if info:
        sz = Path(a.out).stat().st_size / 1048576
        print(f"[gif] {a.out}  {info['frames']} 帧 {info['cell'][0]}x{info['cell'][1]} "
              f"每帧 {info['delay']}ms  {sz:.2f}MB")
        print(f"[anim] {info['anim']}  {info['dur']}s  bb={info['bb']}")


if __name__ == "__main__":
    main()
