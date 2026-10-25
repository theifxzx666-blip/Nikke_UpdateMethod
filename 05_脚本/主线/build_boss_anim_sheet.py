# -*- coding: utf-8 -*-
"""把 BOSS 表演动画的代表帧拼成一张预览图，供 PDF「表演动画」页使用。

为什么不直接把 GIF 塞进 PDF：Chrome 打印 GIF 只取第一帧，而登场/战败的头一帧
往往还是"静止标准站姿"或已经散架，看不出动作。所以从每条 GIF 抽中段帧，
拼成对比图，PDF 里放这张静态图，GIF 本体留给目录里的文件。
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageSequence
import numpy as np

ROOT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
GIF_DIR = ROOT / "05_主线_47-48章" / "07_关卡莱彻" / "动图"
OUT = GIF_DIR / "00_预览.png"

# (GIF 文件名, 标题, 副标题)
JOBS = [
    ("安尼希利奥_1阶段_登场.gif",           "安尼希利奥 · 登场",      "12phase · 1 阶段骨架"),
    ("安尼希利奥_2阶段_转阶段开始.gif",     "安尼希利奥 · 转阶段",    "groggy_start"),
    ("安尼希利奥_2阶段_战败.gif",           "安尼希利奥 · 战败",      "death · 只有 2 阶段"),
    ("莉贝雷利奥躯体_1阶段_登场.gif",       "莉贝雷利奥躯体 · 登场",  "intro_01 · 1 阶段骨架"),
    ("莉贝雷利奥躯体_2阶段_转阶段循环.gif", "莉贝雷利奥躯体 · 转阶段", "groggy_loop"),
    ("莉贝雷利奥躯体_2阶段_战败.gif",       "莉贝雷利奥躯体 · 战败",  "death"),
]

CELL_W, CELL_H = 400, 460      # 单格画面区
PAD = 14
LABEL_H = 46
COLS = 3

FONT = r"C:/Windows/Fonts/msyh.ttc"


def pick_frame(gif: Path) -> Image.Image:
    """挑「主体最完整」的一帧。

    踩过的两个坑：
      · 固定比例取样（0.55 / 0.75）：安尼希利奥登场的后半段模型已落出画面，
        取到纯黑；莉贝雷利奥 1 阶段登场取到模型飞升、只剩两条腿的帧。
      · 改成「前景像素最多」：莉贝雷利奥战败的碎屑帧前景像素反而更多
        （碎屑撒得满屏都是），挑出来还是一片黑。
    最终按「前景像素数 × 填充率」打分：填充率 = 前景像素 / 前景包围盒面积，
    碎屑帧包围盒大、填充率低，自然压下去。
    """
    im = Image.open(gif)
    frames = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    if not frames:
        raise RuntimeError(f"{gif.name} 里一帧都没有")
    a0 = np.asarray(frames[0])
    bg = np.median(np.array([a0[0, 0], a0[0, -1], a0[-1, 0], a0[-1, -1]]), axis=0)
    best, best_s = 0, -1.0
    for i, f in enumerate(frames):
        a = np.asarray(f).astype(np.int16)
        m = np.abs(a - bg).max(axis=2) > 18
        n = int(m.sum())
        if n < 200:
            continue
        ys, xs = np.where(m)
        area = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)
        fill = n / max(area, 1)
        s = n * (fill ** 2)          # 数量 × 填充率平方：既要有内容，又要成团
        if s > best_s:
            best, best_s = i, s
    return frames[best]


def fit_box(im: Image.Image, w: int, h: int) -> Image.Image:
    """等比缩放到装进 w×h，不放大超过 1.0 以免糊。"""
    sw, sh = im.size
    k = min(w / sw, h / sh, 1.0)
    return im.resize((max(1, int(sw * k)), max(1, int(sh * k))), Image.LANCZOS)


def main():
    rows = (len(JOBS) + COLS - 1) // COLS
    W = PAD + COLS * (CELL_W + PAD)
    H = PAD + rows * (CELL_H + LABEL_H + PAD) + 54
    sheet = Image.new("RGBA", (W, H), (17, 20, 26, 255))
    dr = ImageDraw.Draw(sheet)

    f_hd = ImageFont.truetype(FONT, 26)
    f_name = ImageFont.truetype(FONT, 17)
    f_sub = ImageFont.truetype(FONT, 13)
    dr.text((PAD + 2, 14), "关底 BOSS 表演动画 · 代表帧", font=f_hd, fill=(232, 238, 246))
    dr.text((PAD + 2, 44),
            "12 条动画各自独立成 GIF；此处每条取「主体最完整」的一帧，完整动作见同目录 .gif",
            font=f_sub, fill=(122, 132, 150))

    top = 54 + PAD
    for i, (fn, title, sub) in enumerate(JOBS):
        gif = GIF_DIR / fn
        if not gif.exists():
            print("!! 缺文件", gif)
            continue
        fr = pick_frame(gif).convert("RGBA")
        fr = fit_box(fr, CELL_W, CELL_H)
        cx = PAD + (i % COLS) * (CELL_W + PAD)
        cy = top + (i // COLS) * (CELL_H + LABEL_H + PAD)
        # 画面居中
        ox = cx + (CELL_W - fr.width) // 2
        oy = cy + (CELL_H - fr.height) // 2
        # 深色底衬，避免透明区直接暴露到页面底色
        dr.rounded_rectangle([cx, cy, cx + CELL_W, cy + CELL_H], 6,
                             fill=(24, 28, 36, 255))
        sheet.alpha_composite(fr, (ox, oy))
        dr.text((cx + 2, cy + CELL_H + 8), title, font=f_name, fill=(226, 232, 240))
        dr.text((cx + 2, cy + CELL_H + 28), sub, font=f_sub, fill=(110, 120, 138))

    sheet.convert("RGB").save(OUT, "PNG", optimize=True)
    print("->", OUT, sheet.size)


if __name__ == "__main__":
    main()
