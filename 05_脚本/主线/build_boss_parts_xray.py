# -*- coding: utf-8 -*-
"""关底 BOSS 逐部件透视图 + 核心判定标注。

与 `立绘/透视/` 的区别：
  那张是「整体外壳 22% + 核心件原色」，一张图看全部；
  这里是**每个部件一张格**（该部件原色、其余幽灵化），回答「这块长在哪、能不能打」。

判定字段来自 MonsterPartsTable（见 Prompt v2.3 22.3）：
  IsPartsDamageAble  能否受击
  VisibleHp          是否显示独立血条
  HpRatio            血量占比（主部件 10000，7 / 100 / 150 属低血量）
"""
import csv
import json
import math
import re
import sqlite3
from pathlib import Path

import numpy as np
import UnityPy
from PIL import Image, ImageDraw, ImageFont
from UnityPy.helpers.MeshHelper import MeshHandler

import render_monster_standee as R

DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
SD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")
LSS = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\文本\原始文本库_lss\Locale_Monster.lss")
OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\boss_parts_xray")

TARGETS = [
    ("xba003", "dmtr", 451003, "安尼希利奥", "47 章"),
    ("eba002", "hsta", 251016, "莉贝雷利奥躯体", "48 章"),
]

CELL = 400
COLS = 5


def load_parts():
    d = json.loads((SD / "MonsterPartsTable.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{LSS}?mode=ro", uri=True)
    loc = {k: v for k, v in con.execute('select "Key","zh-CN" from Locale_Monster')}
    con.close()
    return d, loc


def parts_meta(rows, loc, phase):
    """PartsSkin（可见几何名）→ 中文名 + 判定字段。phase 用来过滤两阶段重名。"""
    m = {}
    for r in rows:
        skin = str(r.get("PartsSkin") or "")
        if not skin:
            continue
        # 不按名字里的 1phase/2phase 过滤：xbga03_1phase_dl_skin 虽然名字带 1phase，
        # 实际挂在 xbga03_2phase_var 下（Prompt 17.2 的坑）。PartsSkin 在表里唯一，
        # 直接按名字匹配即可，多加一层阶段判断反而会把 2 阶段里的 4 个箱子滤掉。
        key = str(r.get("PartsNameLocalkey") or "")
        nm = loc.get(key.split(":", 1)[1], "") if ":" in key else ""
        m[skin] = {
            "id": r.get("Id"), "name": nm or "（无名）",
            "type": r.get("PartsType"),
            "hp": r.get("HpRatio"), "dmg": r.get("DamageHpRatio"),
            "hit": bool(r.get("IsPartsDamageAble")),
            "vh": bool(r.get("VisibleHp")),
            "main": bool(r.get("IsMainPart")),
            "obj": ", ".join(r.get("PartsObject") or [])[:40],
        }
    return m


def lookup_part(meta, mesh):
    """按网格名找表里的部件行。

    坑：MonsterPartsTable 的 PartsSkin 只登记了 **1 阶段** 的网格名
    （xbga03_1phase_dl/dr/ul/ur_skin），2 阶段的同一批部件实际网格叫
    xba003_2phase_parts_dl/dr/ul/ur_skin —— 名字不连续。
    这里做一次别名映射，并把命中的原表名回写给标签，标明是「推定对应」。
    """
    if mesh in meta:
        return meta[mesh], ""
    m = re.match(r"xba003_2phase_parts_(\w+)_skin$", mesh)
    if m:
        alt = f"xbga03_1phase_{m.group(1)}_skin"
        if alt in meta:
            return meta[alt], alt
    return {}, ""


def collect(bundle, phase):
    env = UnityPy.load(str(bundle))
    tfs, go_name, world = R.build_world(env)
    tid2go = {k: go_name.get(d.m_GameObject.m_PathID, "") for k, d in tfs.items()}
    out = []
    for o in env.objects:
        if o.type.name != "SkinnedMeshRenderer":
            continue
        smr = o.read()
        mesh = smr.m_Mesh.read()
        tid = next((k for k, d in tfs.items()
                    if d.m_GameObject.m_PathID == smr.m_GameObject.m_PathID), None)
        if tid is None:
            continue
        ch = R.ancestor_chain(tid, tfs, tid2go)
        owned = next((c for c in ch if "1phase" in c or "2phase" in c), "")
        if phase not in owned:
            continue
        h = MeshHandler(mesh)
        h.process()
        if not h.m_Vertices or not h.m_IndexBuffer or not h.m_UV0:
            continue
        V = np.array(h.m_Vertices, float).reshape(-1, 3)
        UV = np.array(h.m_UV0, float).reshape(-1, 2)
        T = np.array([t for sub in h.get_triangles() for t in sub if len(t) == 3], np.int64)
        mat = None
        for mm in (smr.m_Materials or []):
            try:
                mat = mm.read()
                break
            except Exception:
                pass
        tx = R.tex_of(mat) if mat is not None else None
        if tx is None:
            continue
        ta = np.asarray(tx.image.convert("RGBA"), float) / 255.0
        Vw = R.skin_world(V, smr, mesh, h, world, tfs, tid)
        out.append({"V": np.c_[-Vw[:, 0], Vw[:, 1], -Vw[:, 2]], "UV": UV, "T": T,
                    "ta": ta, "mesh": mesh.m_Name})
    return out


def raster(p, ctr, sc, S, buf, zb):
    """把单件光栅化进**外部** buf/zb。

    必须能共用一个 buffer：幽灵层如果每件各叠一次，4~9 件 × 0.24 alpha
    累积起来接近不透明，画面会一片亮，高亮件反而看不出来。
    """
    V, UV, T, ta = p["V"], p["UV"], p["T"], p["ta"]
    px = (V[:, 0] - ctr[0]) * sc + S / 2
    py = S / 2 - (V[:, 1] - ctr[1]) * sc
    pz = V[:, 2]
    th, tw = ta.shape[:2]
    for tri in T:
        i0, i1, i2 = tri
        x0, y0, x1, y1, x2, y2 = px[i0], py[i0], px[i1], py[i1], px[i2], py[i2]
        minx = max(0, int(math.floor(min(x0, x1, x2))))
        maxx = min(S - 1, int(math.ceil(max(x0, x1, x2))))
        miny = max(0, int(math.floor(min(y0, y1, y2))))
        maxy = min(S - 1, int(math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        X, Y = np.meshgrid(np.arange(minx, maxx + 1) + 0.5,
                           np.arange(miny, maxy + 1) + 0.5)
        w0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / den
        w1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / den
        w2 = 1 - w0 - w1
        ins = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not ins.any():
            continue
        z = w0 * pz[i0] + w1 * pz[i1] + w2 * pz[i2]
        u = w0 * UV[i0, 0] + w1 * UV[i1, 0] + w2 * UV[i2, 0]
        v = w0 * UV[i0, 1] + w1 * UV[i1, 1] + w2 * UV[i2, 1]
        ui = np.clip((u * tw).astype(np.int32), 0, tw - 1)
        vi = np.clip(((1 - v) * th).astype(np.int32), 0, th - 1)
        col = ta[vi, ui]
        ok = ins & (col[:, :, 3] > 0.02)
        if not ok.any():
            continue
        sz = zb[miny:maxy + 1, minx:maxx + 1]
        upd = ok & (z >= sz - 1e-3)
        if not upd.any():
            continue
        sz[upd] = z[upd]
        ds = buf[miny:maxy + 1, minx:maxx + 1]
        a = col[upd][:, 3:4]
        ds[upd] = a * col[upd] + (1 - a) * ds[upd]
def ghostify(buf, k=0.16):
    """整层（不是逐件）压暗降透明，只做一次。"""
    if not buf[:, :, 3].any():
        return buf
    g = buf[:, :, :3].mean(axis=2, keepdims=True)
    buf[:, :, :3] = 0.07 + 0.30 * g
    buf[:, :, 3] *= k
    return buf


def to_img(buf):
    return Image.fromarray((np.clip(buf, 0, 1) * 255).astype(np.uint8), "RGBA")


def fit(dr, txt, font, maxw):
    """按像素宽度截断，末尾补省略号。

    名牌行、信息行、网格行三种字号不同，统一走这里，避免某一列横向
    溢出到相邻格（上一版就是 15px 的 `Type 14 · HP 150 · 可受击·有血条`
    串到右边格子上去了）。
    """
    if dr.textlength(txt, font=font) <= maxw:
        return txt
    while txt and dr.textlength(txt + "…", font=font) > maxw:
        txt = txt[:-1]
    return txt + "…" if txt else ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tabs, loc = load_parts()
    f_name = ImageFont.truetype(r"C:/Windows/Fonts/msyh.ttc", 19)
    f_meta = ImageFont.truetype(r"C:/Windows/Fonts/msyh.ttc", 15)
    f_hd = ImageFont.truetype(r"C:/Windows/Fonts/msyh.ttc", 34)

    for tag, suf, mid, zh, chap in TARGETS:
        bundle = DEV / f"spotmonster_{tag}_{suf}.bundle"
        rows = [r for r in tabs if r.get("MonsterModelId") == mid]
        for phase in ("1phase", "2phase"):
            parts = collect(bundle, phase)
            if not parts:
                print(f"  {tag} {phase}: 无网格，跳过")
                continue
            meta = parts_meta(rows, loc, phase)

            # 每件各自的取景框：小部件（炮塔）按全身缩放会缩成几十像素，
            # 看不出形状。幽灵层用同一套取景，所以位置关系仍然保留。
            boxes = []
            for p in parts:
                v = p["V"]
                c = (v.min(0) + v.max(0)) / 2
                sp = max(v[:, 1].max() - v[:, 1].min(),
                         v[:, 0].max() - v[:, 0].min(), 1e-3)
                boxes.append((c, sp))
            S = CELL

            n = len(parts)
            # 件数不超过 6 就排一行（6 件按 5 列会变成 5+1，右边空一大块）
            cols = n if n <= 6 else COLS
            rows_n = (n + cols - 1) // cols
            LAB_H = 74
            W = cols * CELL
            H = rows_n * (CELL + LAB_H) + 118
            canvas = Image.new("RGB", (W, H), (14, 17, 22))
            dr = ImageDraw.Draw(canvas)

            dr.text((24, 22), f"{zh} · {chap} · {phase} · 零件透视",
                    font=f_hd, fill=(232, 238, 246))
            hit = sum(1 for p in parts
                      if meta.get(p["mesh"], {}).get("hit"))
            dr.text((24, 70), f"{n} 个可见部件 · 其中 {hit} 个可受击 · "
                              f"幽灵层 16% · 红描边为目标件 · 右下角小图为整体定位",
                    font=f_meta, fill=(122, 132, 150))

            # 整体定位缩略图：每格右下角贴一份，用红框标出该件在全身的位置
            TH = 132
            allv0 = np.vstack([q["V"] for q in parts])
            c_tsr = (allv0.min(0) + allv0.max(0)) / 2
            s_tsr = max(allv0[:, 1].max() - allv0[:, 1].min(),
                        allv0[:, 0].max() - allv0[:, 0].min(), 1e-3)
            sc_tsr = S * 0.86 / s_tsr * 2.0
            ab = np.zeros((S, S, 4), np.float32)
            az = np.full((S, S), -1e9, np.float32)
            for q in parts:
                raster(q, c_tsr, sc_tsr, S, ab, az)
            all_thumb = to_img(ab).convert("RGB").resize((TH, TH), Image.LANCZOS)

            def box_on_thumb(p):
                v = p["V"]
                x0 = (v[:, 0].min() - c_tsr[0]) * sc_tsr + S / 2
                x1 = (v[:, 0].max() - c_tsr[0]) * sc_tsr + S / 2
                y0 = S / 2 - (v[:, 1].max() - c_tsr[1]) * sc_tsr
                y1 = S / 2 - (v[:, 1].min() - c_tsr[1]) * sc_tsr
                k = TH / S
                return (max(0.0, x0 * k), max(0.0, y0 * k),
                        min(float(TH - 1), x1 * k), min(float(TH - 1), y1 * k))

            for i, p in enumerate(parts):
                r0, c0 = divmod(i, cols)
                oy = 118 + r0 * (CELL + LAB_H)
                ox = c0 * CELL
                ctr, span = boxes[i]
                sc = CELL * 0.84 / span * 2.0

                # 幽灵层：全部非目标件画进同一个 buffer，再整体压暗一次
                gb = np.zeros((S, S, 4), np.float32)
                gz = np.full((S, S), -1e9, np.float32)
                for j, q in enumerate(parts):
                    if j == i:
                        continue
                    raster(q, ctr, sc, S, gb, gz)
                tile = to_img(ghostify(gb))

                # 目标件：正常渲染 + 粗红描边
                tb = np.zeros((S, S, 4), np.float32)
                tz = np.full((S, S), -1e9, np.float32)
                raster(p, ctr, sc, S, tb, tz)
                m = tb[:, :, 3] > 0.30
                # 描边走**内侧**：目标件常占满整格，画在外侧会被格子边切掉
                ero = m.copy()
                for _ in range(2):                       # erode 2 圈 → 2px 内描边
                    ero = (ero & np.roll(ero, 1, 0) & np.roll(ero, -1, 0)
                           & np.roll(ero, 1, 1) & np.roll(ero, -1, 1))
                edge = m & ~ero
                tb[edge] = [255, 70, 70, 1.0]
                tile = Image.alpha_composite(tile, to_img(tb))
                canvas.paste(tile.convert("RGB"), (ox, oy), tile)
                # 定位小图
                tx0, ty0 = ox + CELL - TH - 8, oy + CELL - TH - 8
                canvas.paste(all_thumb, (tx0, ty0))
                bx = box_on_thumb(p)
                # clamp 后可能出现 x1 < x0（部件整体在取景框外），先排序再保证最小 4px
                xa, xb_ = sorted((bx[0], bx[2]))
                ya, yb_ = sorted((bx[1], bx[3]))
                xa = min(max(1.0, xa), TH - 6.0)
                xb_ = min(max(xb_, xa + 4), TH - 2.0)
                ya = min(max(1.0, ya), TH - 6.0)
                yb_ = min(max(yb_, ya + 4), TH - 2.0)
                dr.rectangle([tx0 + xa, ty0 + ya, tx0 + xb_, ty0 + yb_],
                             outline=(255, 70, 70), width=2)
                dr.rectangle([tx0, ty0, tx0 + TH - 1, ty0 + TH - 1],
                             outline=(52, 60, 72), width=1)

                mt, alias = lookup_part(meta, p["mesh"])
                if mt:
                    nm = mt.get("name") or "（表内无部件名）"
                else:
                    # 表里没有该 PartsSkin 的行 —— 多为「主体」，不是漏登记
                    nm = "主体（未登记部件行）"
                hp = mt.get("hp", "")
                hitv = "可受击" if mt.get("hit") else "不可受击"
                vh = "·有血条" if mt.get("vh") else ""
                col = (246, 173, 85) if mt.get("hit") else (150, 158, 172)
                if hp in (7, 100, 150) and mt.get("hit"):
                    col = (248, 113, 113)      # 低血量 = 弱点
                dr.text((ox + 8, oy + CELL + 2),
                        fit(dr, nm, f_name, CELL - 16), font=f_name, fill=col)
                meta_line = f"Type {mt.get('type','?')} · HP {hp} · {hitv}{vh}"
                if dr.textlength(meta_line, font=f_meta) > CELL - 16:
                    meta_line = f"Type {mt.get('type','?')} · HP {hp} · {hitv}"
                dr.text((ox + 8, oy + CELL + 26),
                        fit(dr, meta_line, f_meta, CELL - 16),
                        font=f_meta, fill=(150, 160, 176))
                _note = f"名对应 {alias}" if alias else p["mesh"]
                dr.text((ox + 8, oy + CELL + 48),
                        fit(dr, _note, f_meta, CELL - 16),
                        font=f_meta, fill=(150, 130, 90) if alias else (96, 106, 122))
                dr.rectangle([ox, oy, ox + CELL - 1, oy + CELL + LAB_H - 2],
                             outline=(38, 44, 54))

            png = OUT / f"{tag}_{phase}_零件透视.png"
            canvas.save(png)
            print(f"{tag} {phase}: {n} 件 → {png.name}  {W}×{H}")

            # 判定表
            tsv = OUT / f"{tag}_{phase}_判定.tsv"
            with tsv.open("w", encoding="utf-8-sig") as f:
                f.write("可见网格\t中文名\tPartsType\tHpRatio\tDamageHpRatio\t可受击\t有血条\t"
                        "PartsObject\t对应原表名\t顶点数\t尺寸_宽高深\n")
                for p in parts:
                    mt, alias = lookup_part(meta, p["mesh"])
                    v = p["V"]
                    size = "×".join(f"{x:.1f}" for x in (v.max(0) - v.min(0)))
                    f.write(f"{p['mesh']}\t{mt.get('name','')}\t{mt.get('type','')}\t"
                            f"{mt.get('hp','')}\t{mt.get('dmg','')}\t"
                            f"{'是' if mt.get('hit') else '否'}\t"
                            f"{'是' if mt.get('vh') else '否'}\t{mt.get('obj','')}\t"
                            f"{alias or '（同名命中）' if mt else '（表内无登记）'}\t"
                            f"{len(v)}\t{size}\n")


if __name__ == "__main__":
    main()
