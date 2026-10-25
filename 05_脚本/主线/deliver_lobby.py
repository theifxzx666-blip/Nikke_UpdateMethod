# -*- coding: utf-8 -*-
"""把已渲好的大厅站立动画归集到版更交付目录。

来源：D:\\Codex\\临时\\nikke_intl_20261029\\out\\lobby_{gif,webp,png}
去向：<版更>\\06_角色大厅站立动画\\<角色>_<cID>_<序号>_<时装名>\\

同时生成：
  · 00_全角色一览.png（7 套 idle 首帧拼图，带名字）
  · 00_清单.tsv（逐套登记尺寸/帧数/时长/体积/动幅）
"""
import csv
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path(r"D:\Codex\临时\nikke_intl_20261029\out")
DST = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
           r"\06_角色大厅站立动画")

# cID_序号 → (角色, cID, 序号, 时装名)
SETS = {
    "c870_00": ("QUEEN（真）", "c870", "00", "默认"),
    "c870_01": ("QUEEN（真）", "c870", "01", "秀尽学园学生会长"),
    "c870_02": ("QUEEN（真）", "c870", "02", "女王睡衣"),
    "c871_00": ("雪子", "c871", "00", "默认"),
    "c871_01": ("雪子", "c871", "01", "天城屋旅馆和服"),
    "c871_02": ("雪子", "c871", "02", "冬日雅居"),
    "c872_00": ("埃癸斯", "c872", "00", "默认"),
    # 2026-10-25 补：本期「时装抽取」上的圣洁怪盗（潘托姆）。c580 的 standing bundle
    # 一直在 catalog 里（00 默认 / 01 圣洁怪盗），但之前只拿它渲过一张 idle 首帧当小人立绘，
    # 没做整段动画 —— 属于漏采，不是资源缺失。
    "c580_00": ("潘托姆", "c580", "00", "默认"),
    "c580_01": ("潘托姆", "c580", "01", "圣洁怪盗"),
}

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]


def font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def folder_name(cid_key):
    name, cid, idx, costume = SETS[cid_key]
    return f"{name}_{cid}_{idx}_{costume}"


def load_manifest(name):
    f = SRC / "lobby_gif" / name
    if not f.exists():
        return {}
    return {m["id"]: m for m in json.loads(f.read_text(encoding="utf-8"))}


def main():
    DST.mkdir(parents=True, exist_ok=True)
    man = {}
    man.update(load_manifest("_manifest.json"))
    man.update(load_manifest("_manifest_action.json"))
    rows = []
    for key in SETS:
        name, cid, idx, costume = SETS[key]
        outdir = DST / folder_name(key)
        outdir.mkdir(parents=True, exist_ok=True)
        for anim in ("idle", "action"):
            sfx = "" if anim == "idle" else "_action"
            stem = f"{key}{sfx}"            # 渲染产物名（idle 无后缀）
            dstem = f"{key}_{anim}"         # 交付文件名（统一带动画名）
            # 只交付「GIF + 首帧 PNG」两种。
            # 动画 WebP 虽然体积更小、色彩更干净，但玩家的使用场景是直接看 / 丢进剪辑软件，
            # GIF 兼容性更好；WebP 属于中间产物，不再随包交付（渲染脚本仍会生成，留在 out/lobby_webp）。
            srcs = [
                (SRC / "lobby_gif" / f"{stem}.gif", outdir / f"{dstem}.gif"),
                (SRC / "lobby_png" / f"{stem}_首帧.png", outdir / f"{dstem}_首帧.png"),
            ]
            for s, d in srcs:
                if not s.exists():
                    print(f"  !! 缺文件 {s}")
                    continue
                shutil.copy2(s, d)
            g = SRC / "lobby_gif" / f"{stem}.gif"
            if g.exists():
                im = Image.open(g)
                meta = man.get(stem, {})
                delay = meta.get("delay_ms", 70)
                rows.append({
                    "目录": folder_name(key),
                    "资源ID": key,
                    "角色": name,
                    "序号": idx,
                    "时装": costume,
                    "动画": anim,
                    "尺寸": f"{im.size[0]}x{im.size[1]}",
                    "帧数": im.n_frames,
                    "时长s": f"{im.n_frames * delay / 1000:.2f}",
                    "动幅%": (f'{meta["motion_pct"]:.2f}'
                             if meta.get("motion_pct") is not None else ""),
                    "GIF_MB": round(g.stat().st_size / 1048576, 2),
                })
                im.close()

    with open(DST / "00_清单.tsv", "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        wr.writeheader()
        wr.writerows(rows)

    # 一览图：7 套 idle 首帧等高横排。每个格位的宽度取「图宽」与「标签宽」的较大者，
    # 否则窄角色（如埃癸斯 304px）的标签会压到隔壁。
    H = 760
    pad, label_h = 46, 52
    tiles = []
    for key in SETS:
        p = DST / folder_name(key) / f"{key}_idle_首帧.png"
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        w = round(im.width * H / im.height)
        tiles.append((im.resize((w, H), Image.LANCZOS), folder_name(key)))
    if tiles:
        f = font(22)
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        slot_w = []
        for im, label in tiles:
            tw = probe.textlength(label, font=f)
            slot_w.append(max(im.width, int(tw) + 16))
        W = sum(slot_w) + pad * (len(tiles) + 1)
        sheet = Image.new("RGB", (W, H + label_h + pad * 2), (14, 17, 22))
        d = ImageDraw.Draw(sheet)
        x = pad
        for (im, label), sw in zip(tiles, slot_w):
            cx = x + sw // 2
            sheet.paste(im, (cx - im.width // 2, pad))
            d.text((cx, pad + H + 14), label, font=f,
                   fill=(214, 222, 233), anchor="ma")
            x += sw + pad
            if x < W - pad:      # 格位之间加一条细分隔线，避免标签读串行
                d.line([(x - pad // 2, pad), (x - pad // 2, pad + H + 22)],
                       fill=(52, 60, 72), width=2)
        sheet.save(DST / "00_全角色一览.png")
        print(f"一览图 {sheet.size[0]}×{sheet.size[1]}")

    print(f"\n交付 {len(SETS)} 套 → {DST}")
    print(f"{'目录':<34}{'idle':>16}{'action':>16}")
    for key in SETS:
        fn = folder_name(key)
        i = next((r for r in rows if r["资源ID"] == key and r["动画"] == "idle"), {})
        a = next((r for r in rows if r["资源ID"] == key and r["动画"] == "action"), {})
        print(f"{fn:<34}{i.get('尺寸','-'):>10}/{i.get('GIF_MB','-'):>4}"
              f"{a.get('尺寸','-'):>10}/{a.get('GIF_MB','-'):>4}")
    total_gif = sum(r["GIF_MB"] for r in rows)
    print(f"\n合计 GIF {total_gif:.1f} MB · {len(SETS)} 套 × 2 条 = {len(rows)} 条")


if __name__ == "__main__":
    main()
