# -*- coding: utf-8 -*-
"""把 livewallpaperprefabs.bundle 里 ce009 大厅动画的粒子层还原成 GIF。

数据来源（全部读文件）：
  14 个 ParticleSystem 的模块参数 + 相机 + 各发射器世界坐标
      → out/lw_spec.json（probe_lw.py 用 UnityPy 摊平的）
  5 张 FX 贴图          → out/lw_tex/*.png
  主插画                → 03_活动/…/大厅动画_主图_1000x1000.png

做不到的（交付说明里必须写）：
  1. 这是**参数驱动的动效重现**，不是引擎画面。Unity 粒子走自定义 shader，
     Bloom / Vignette / ChannelMixer 三个后处理 Volume 也在包里但 shader 不在，
     无法执行。
  2. 两个 fx_char_uv 是 UV 扭曲发射器（材质 mode=4），本身不产生可见像素，跳过。
  3. 粒子位置用 GameObject 的序列化位姿；Timeline / Cinemachine 运行时的镜头位移不复现。
"""
import json
import math
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out")
SPEC = OUT / "lw_spec.json"
TEXD = OUT / "lw_tex"
ART = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\03_活动\PERSONA ON FRONTLINE（ce009）\大厅动画\大厅动画_主图_1000x1000.png")

W = H = 1000
FPS = 12.5      # 12.5fps × 4s = 50 帧，帧间隔正好 80ms（GIF 以 10ms 为单位，无取整误差）
DUR = 4.0
SEED = 20260813
MAX_PX = 1200          # 单粒子最大像素边长（超屏光斑按屏宽截）
SKIP = {"fx_char_uv_01", "fx_char_uv_02", "FX"}

ATLAS = {              # 贴图名 → 网格，与 UVModule.tilesX/Y 一致
    "fx_EventScene_ce009_01_atlas": (3, 3),
    "fx_event_enter_ce009_atlas_01": (2, 4),
}


# ---------------- 曲线求值 ----------------

def norm(v, d=0.0):
    """MinMaxCurve → (最小, 最大)。state: 0 常量 / 2 两常量随机 / 3 两曲线随机。"""
    if not v:
        return d, d
    st = v.get("state")
    s = v.get("scalar")
    mn = v.get("min")
    keys = v.get("keys") or []
    if st == 0:
        s = d if s is None else s
        return s, s
    if st == 2:
        return (d if mn is None else mn), (d if s is None else s)
    if keys:
        vals = [k[1] for k in keys]
        return min(vals), max(vals)
    a = d if mn is None else mn
    b = d if s is None else s
    return min(a, b), max(a, b)


def curve_at(v, u, d=0.0):
    """按归一化寿命 u∈[0,1] 求值（曲线端点线性插值）。"""
    if not v:
        return d
    st = v.get("state")
    if st == 0:
        s = v.get("scalar")
        return d if s is None else s
    keys = v.get("keys") or []
    if len(keys) < 2:
        lo, hi = norm(v, d)
        return 0.5 * (lo + hi)
    u = min(max(u, 0.0), 1.0)
    for i in range(len(keys) - 1):
        t0, v0 = keys[i]
        t1, v1 = keys[i + 1]
        if t0 <= u <= t1:
            if t1 - t0 <= 1e-9:
                return v1
            return v0 + (v1 - v0) * ((u - t0) / (t1 - t0))
    return keys[-1][1] if u >= keys[-1][0] else keys[0][1]


def rnd(*keys):
    """跨进程稳定的伪随机数发生器。"""
    h = 0
    for k in keys:
        h = zlib.crc32(("%s|" % (k,)).encode("utf-8"), h)
    return np.random.default_rng(SEED ^ h)


# ---------------- 精灵 ----------------
_SPR = {}
_SCALED = {}


def tile_img(atlas, tx, ty, row, col):
    key = (atlas["name"], tx, ty, row, col)
    if key in _SPR:
        return _SPR[key]
    im = atlas["img"]
    w, h = im.size
    cw, ch = w / tx, h / ty
    _SPR[key] = im.crop((int(round(col * cw)), int(round(row * ch)),
                         int(round((col + 1) * cw)), int(round((row + 1) * ch))))
    return _SPR[key]


def sprite(atlas, tx, ty, row, col, px, rot):
    px = int(max(2, min(MAX_PX, round(px))))
    rot = round(rot, 1)
    key = (atlas["name"], tx, ty, row, col, px, rot)
    if key in _SCALED:
        return _SCALED[key]
    im = tile_img(atlas, tx, ty, row, col).resize((px, px), Image.BILINEAR)
    if abs(rot) % 360 > 0.4:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=False)
    arr = np.asarray(im, dtype=np.uint8)
    if px <= 300:
        _SCALED[key] = arr
        if len(_SCALED) > 500:
            _SCALED.clear()
    return arr


# ---------------- 发射计划 ----------------

def build_particles(s, atlas):
    """一个发射器在一个循环周期内的全部粒子（位置/尺寸/角度一次算定）。"""
    P = s["prefab_len"] or DUR
    floor_ = max(1, int(s["max_particles"] or 1))
    life_lo, life_hi = norm(s["life"], 1.0)
    size_lo, size_hi = norm(s["size"], 1.0)
    rot_lo, rot_hi = norm(s["rot"], 0.0)
    r_lo, r_hi = norm(s["shape"].get("radius"), 0.0)
    sx, sy = (s["shape"].get("scale") or [1.0, 1.0, 0.0])[:2]
    stype = s["shape"].get("type")
    rgba = s["start_rgba"] or [1.0, 1.0, 1.0, 1.0]
    tx, ty = atlas["tiles"]
    uv = s["uv"]
    idx = int(round(((uv.get("start_frame") or {}).get("scalar") or 0.0) * tx * ty))
    idx = min(max(idx, 0), tx * ty - 1)
    fixed_row, fixed_col = idx // tx, idx % tx
    # UVModule.rowMode=1（Random）**不复现**：本图集里两个卡片格一旦被随机抽中，
    # 会按 20+ 世界单位铺成整屏半透明卡片，与「舞台光 / 光斑」语义冲突。
    # 统一取 startFrame 指向的那一格 —— 该格在图集里就是对应该发射器的图案。
    rand_row = False

    # 发射事件
    events = []          # (t0, n, tag)
    rate = max(norm(s["emission"], 0.0))
    if rate > 1e-6:
        n = min(int(round(rate * P)), floor_ * 4)
        for k in range(n):
            events.append((k * P / n, 1, ("r", k)))
    for bi, b in enumerate(s.get("bursts") or []):
        cnt = int(round(max(norm(b.get("cnt"), 1.0))))
        cyc = max(1, int(b.get("cycles") or 1))
        step = b.get("repeat") or P
        total = cnt * cyc
        if total > floor_ * 4:
            cyc = max(1, (floor_ * 4) // max(cnt, 1))
        for c in range(cyc):
            events.append((((b.get("t") or 0.0) + c * step) % P, cnt, ("b", bi, c)))

    out = []
    for t0, cnt, tag in events:
        for j in range(cnt):
            r = rnd(s["host"], tag, j)
            life = r.uniform(life_lo, life_hi) if life_hi > life_lo else life_lo
            if life <= 0:
                continue
            size = r.uniform(size_lo, size_hi) if size_hi > size_lo else size_lo
            if stype == 10:                                  # Circle：圆盘内均匀取点
                rr = math.sqrt(r.random()) * max(r_lo, r_hi)
                th = r.random() * 2 * math.pi
                off = (rr * math.cos(th), rr * math.sin(th), 0.0)
            elif stype == 5:                                 # Box：矩形内均匀取点
                a, b = sorted((abs(sx) / 2, abs(sy) / 2))
                off = (r.uniform(-b, b), r.uniform(-a, a), 0.0)
            else:
                off = (0.0, 0.0, 0.0)
            rot = math.degrees(r.uniform(rot_lo, rot_hi) if rot_hi > rot_lo else rot_lo)
            row = int(r.integers(0, ty)) if rand_row else fixed_row
            out.append(dict(t0=t0, life=life, size=size, rot=rot, row=row, col=fixed_col,
                            pos=np.array(s["world_pos"], float) + np.array(off, float),
                            rgba=rgba, size_curve=s["size_over_life"]))
    return out, P


def main():
    doc = json.loads(SPEC.read_text(encoding="utf-8"))
    cam = np.array(doc["camera"]["pos"], float)
    fov = doc["camera"]["fov"]
    tan_half = math.tan(math.radians(fov) / 2.0)

    atlases = {}
    for n, (tx, ty) in ATLAS.items():
        atlases[n] = dict(name=n, tiles=(tx, ty),
                          img=Image.open(TEXD / (n + ".png")).convert("RGBA"))

    layers = []
    for s in doc["particles"]:
        if s["host"] in SKIP:
            continue
        tex = (s["render"].get("tex") or [None])[0]
        if tex not in atlases:
            continue
        plist, P = build_particles(s, atlases[tex])
        layers.append(dict(
            host=s["host"], atlas=atlases[tex], P=P, parts=plist,
            add="_add" in "".join(s["render"].get("mats") or []),
            n=len(plist),
            # vignett 的格位 (2,1) 是**整格铺满**的暗色贴图（边框 alpha 均值 151/255），
            # 在引擎里就是一张盖住画面的暗角片。按四边对齐铺满整帧，比按 3D 四边形投影可靠。
            fullscreen=(s["host"] == "vignett")))

    for L in layers:
        print("  %-24s %-6s %2d 个粒子  周期 %.1fs" % (
            L["host"], "加色" if L["add"] else "半透", L["n"], L["P"]))

    art = Image.open(ART).convert("RGB").resize((W, H), Image.LANCZOS)
    base = np.asarray(art, dtype=np.float32) / 255.0

    frames = []
    for fi in range(int(round(FPS * DUR))):
        t = fi / FPS
        img = base.copy()
        for L in layers:
            if L["fullscreen"] and L["parts"]:
                p0 = L["parts"][0]
                tx, ty = L["atlas"]["tiles"]
                cell = tile_img(L["atlas"], tx, ty, p0["row"], p0["col"])
                cell = cell.resize((W, H), Image.BILINEAR)
                sub = np.asarray(cell, dtype=np.float32) / 255.0
                srgb = sub[:, :, :3] * np.array(p0["rgba"][:3], np.float32)
                sa = (sub[:, :, 3] * p0["rgba"][3])[:, :, None]
                img = img * (1.0 - sa) + srgb * sa
                continue
            for p in L["parts"]:
                age = (t - p["t0"]) % L["P"]
                if age > p["life"]:
                    continue
                rel = p["pos"] - cam
                depth = rel[2]
                if depth <= 1.0:
                    continue
                k = (H / 2.0) / (depth * tan_half)
                size = p["size"] * curve_at(p["size_curve"], age / p["life"], 1.0)
                px = size * k
                if px < 1.5:
                    continue
                cx = W / 2.0 + rel[0] * k
                cy = H / 2.0 - rel[1] * k
                if cx < -px or cx > W + px or cy < -px or cy > H + px:
                    continue
                tx, ty = L["atlas"]["tiles"]
                spr = sprite(L["atlas"], tx, ty, p["row"], p["col"], px, -p["rot"])
                sh, sw = spr.shape[:2]
                x0, y0 = int(round(cx - sw / 2)), int(round(cy - sh / 2))
                xs, ys = max(0, x0), max(0, y0)
                xe, ye = min(W, x0 + sw), min(H, y0 + sh)
                if xe <= xs or ye <= ys:
                    continue
                sub = spr[ys - y0:ye - y0, xs - x0:xe - x0].astype(np.float32) / 255.0
                srgb = sub[:, :, :3] * np.array(p["rgba"][:3], np.float32)
                sa = (sub[:, :, 3] * p["rgba"][3])[:, :, None]
                dst = img[ys:ye, xs:xe]
                if L["add"]:
                    img[ys:ye, xs:xe] = dst + srgb * sa
                else:
                    img[ys:ye, xs:xe] = dst * (1.0 - sa) + srgb * sa
        frames.append(Image.fromarray(
            (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)))
        if fi % 10 == 0:
            print("  帧 %d/%d" % (fi + 1, int(round(FPS * DUR))), flush=True)

    pal = frames[0].quantize(colors=256, method=Image.MEDIANCUT)
    qs = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    gif = OUT / "大厅动画_ce009_recon.gif"
    qs[0].save(gif, save_all=True, append_images=qs[1:],
               duration=int(1000 / FPS), loop=0, optimize=True, disposal=2)
    frames[0].save(OUT / "大厅动画_ce009_recon_f000.png")
    frames[len(frames) // 2].save(OUT / "大厅动画_ce009_recon_f030.png")
    print("->", gif, "%.1f MB" % (gif.stat().st_size / 1048576), len(qs), "帧")


if __name__ == "__main__":
    sys.exit(main())
