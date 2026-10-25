# -*- coding: utf-8 -*-
"""生成玩家向《2026-08-13 国际服更新内容一览》PDF。

技能名 / 简介一律从 Locale_Skill、Locale_Character 读取，不硬编码。
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
ROOT = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服")
LSC = Path(r"D:\Codex\临时\nikke_intl_20261029\device\lsc")
# 技能数值的唯一权威表：SkillInfoTable（按 GroupId 分组，SkillLevel 1~15）
SKILL_JSON = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out\SkillInfoTable.json")
# icons-skill(hd) 包里按 Icon 名导出的 128×128 图标
ICON_SRC = Path(r"D:\Codex\临时\nikke_intl_20261029\out\skill_icons")
# dp 桶（下载包）全量键清单，用于统计扫图/插画键的分布，不在脚本里写数
KEYLIST = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点\_干跑_20261025\00_基线_键清单\dp_keys.txt")
HTML = ROOT / "_构建" / "报告.html"
PDF = ROOT / "2026-08-13_更新内容一览.pdf"

# ---------------------------------------------------------------- 简版开关
# 简版不另写脚本：同一份 HTML，按页白名单删出来。另写必然两份数据各自维护，
# 一定会分裂（E-03 就是这么来的）。
#   BRIEF=1 python make_pdf_v2.py                      → 用默认白名单
#   BRIEF=1 BRIEF_PAGES=0,1,2,4,6,11,21,47 python make_pdf_v2.py
BRIEF = os.environ.get("BRIEF") == "1"
# 默认白名单对齐 00_规范/交付模板/简版模板.md 的 5 章：
#   0 封面 / 1 本期有什么 / 2,4,6 三名角色 / 11 活动 / 21 主线 / 47 素材汇总
# 每期页数会变，**白名单必须按当期实际页序核对一遍再跑**（先用 --html-only 看页标题）
BRIEF_PAGES = {int(x) for x in
               os.environ.get("BRIEF_PAGES", "0,1,2,4,6,11,21,47").split(",") if x.strip()}
# 简版里不许出现的词（读者不需要知道怎么拆的）
BRIEF_WORDS = ("Timeline", "Spine", "bundle", "UnityPy", "mdump",
               ".lss", ".lsc", "adb", "CDP", "脚本", "拆包")
# 简版把技术词换成人话，只作用于白名单页。顺序有意义：先长后短。
BRIEF_REWRITE = [("Spine 动画", "骨骼动画"), ("Spine", "骨骼动画"),
                 ("Timeline", "时间轴"), ("bundle", "资源包"),
                 ("UnityPy", "解包工具"), ("mdump", ""),
                 (".lss", "配置表"), (".lsc", "配置表"),
                 ("adb", ""), ("CDP", ""), ("脚本", "工具"), ("拆包", "解析")]
HTML_OUT = (HTML.with_name("报告_简版.html") if BRIEF else HTML)
PDF_OUT = (PDF.with_name(PDF.name.replace("更新内容一览", "更新内容简版"))
           if BRIEF else PDF)
# 3D 查看器的线上地址（2026-10-25 部署，仓库 theifxzx666-blip/Nikke_Lecher_3D）
VIEWER_URL = "https://theifxzx666-blip.github.io/Nikke_Lecher_3D/"

TAG = re.compile(r"<[^>]+>")
VAR = re.compile(r"\{description_value_\d+\}")
# 技能描述里的三种标记：数值占位符 / 术语分组 / 富文本配色
SVAR = re.compile(r"\{description_value_(\d+)\}")
SWG = re.compile(r"<word_group=\d+>(.*?)</word_group>", re.S)
SCOLOR = re.compile(r"<color=#([0-9A-Fa-f]{6})>(.*?)</color>", re.S)

CHARS = [
    dict(dir="QUEEN（真）_c870", name="QUEEN（真）", en="Queen (Makoto)", cid="870",
         rare="SSR", burst="III", cv="佐藤利奈", origin="Persona 5", how="角色卡池",
         sk=["18703", "28701", "28702"]),
    dict(dir="雪子_c871", name="雪子", en="Yukiko", cid="871",
         rare="SSR", burst="III", cv="小清水亚美", origin="Persona 4", how="角色卡池",
         sk=["18713", "28711", "28712"]),
    dict(dir="埃癸斯_c872", name="埃癸斯", en="Aigis", cid="872",
         rare="SR", burst="II", cv="坂本真绫", origin="Persona 3", how="活动赠送（无独立卡池）",
         sk=["18723", "28721", "28722"]),
]

SKINS = [
    dict(dir="秀尽学园学生会长_c870_01", name="秀尽学园学生会长", en="Shujin Academy Student Council President",
         owner="QUEEN（真）", how="活动获得"),
    dict(dir="女王睡衣_c870_02", name="女王睡衣", en="Queen's Pajamas (Ver. NIKKE Collabo)",
         owner="QUEEN（真）", how="活动 PASS"),
    dict(dir="天城屋旅馆和服_c871_01", name="天城屋旅馆和服", en="Amagi Inn Kimono",
         owner="雪子", how="活动获得"),
    dict(dir="冬日雅居_c871_02", name="冬日雅居", en="Winter Roomwear (Ver. NIKKE Collabo)",
         owner="雪子", how="活动 PASS"),
    dict(dir="圣洁怪盗_c580_01", name="圣洁怪盗", en="Saint Thief",
         owner="潘托姆", how="时装抽取"),
]

CSS = """
@page { size:A4 portrait; margin:13mm 13mm 14mm; }
* { box-sizing:border-box; }
body { margin:0; font-family:"Microsoft YaHei UI","Microsoft YaHei",sans-serif;
       font-size:10pt; color:#1c2028; line-height:1.6; }
.page { page-break-after:always; height:266mm; display:flex; flex-direction:column; overflow:hidden; }
.page:last-child { page-break-after:auto; }
h1,h2,h3 { margin:0; font-weight:700; }
img { display:block; }
.mono { font-family:Consolas,monospace; }
/* 线上地址：Chrome 打印时会把 <a href> 带成 PDF 的链接注解，纸上也能点 */
a { color:#3d5afe; text-decoration:none; border-bottom:.4mm dotted #a8b8f5; }
.url { font-family:Consolas,monospace; font-size:8.6pt; word-break:break-all; }

.cover { height:266mm; background:linear-gradient(150deg,#0e1220 0%,#1a2340 46%,#2b1f3e 100%);
         color:#fff; border-radius:5mm; padding:16mm 15mm; position:relative; overflow:hidden; }
.cover .kicker { font-size:8.5pt; letter-spacing:.34em; color:#8fa6d8; }
.cover h1 { font-size:33pt; line-height:1.16; margin:5mm 0 3mm; }
.cover .sub { font-size:11.5pt; color:#b9c6e4; }
.cover .badges { margin-top:5mm; position:relative; z-index:3; }
.cover .badge { display:inline-block; padding:1.2mm 2.8mm; border:.35mm solid #5d76b8;
                border-radius:2mm; font-size:8pt; color:#a8bbe6; margin:0 2mm 2mm 0; }
.cover .meta { position:absolute; left:15mm; bottom:14mm; font-size:8.5pt;
               color:#94a2c4; line-height:1.9; z-index:3; }
.cover .heroes { position:absolute; right:6mm; bottom:-4mm; display:flex;
                 align-items:flex-end; gap:0; z-index:1; }
.cover .heroes img { height:132mm; filter:drop-shadow(0 5mm 9mm rgba(0,0,0,.5)); }

.h2 { font-size:16pt; border-left:1.6mm solid #3d5afe; padding-left:3mm; margin-bottom:3.5mm; }
.h2 small { font-size:9pt; color:#7b8494; font-weight:400; margin-left:2mm; }
.lead { color:#4a5261; font-size:9.5pt; margin-bottom:5mm; }
table { width:100%; border-collapse:collapse; font-size:9pt; }
th,td { padding:2.2mm 2.6mm; border-bottom:.3mm solid #e3e7ef; text-align:left; vertical-align:top; }
th { background:#f4f6fb; font-weight:700; color:#33405c; }
.tag { display:inline-block; padding:.4mm 2mm; border-radius:1.4mm; font-size:8pt;
       background:#eef1f9; color:#3b4a6b; margin-right:1.2mm; }
.tag.ssr { background:#fff2d8; color:#8a5a00; }
.tag.sr  { background:#e8f2ff; color:#1a5ba8; }

.grid3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:4mm; }
.card { border:.3mm solid #e3e7ef; border-radius:3mm; padding:3mm; background:#fbfcfe; }
.card .nm { font-weight:700; font-size:11pt; margin-top:1.5mm; }
.card .en { font-size:8pt; color:#8892a6; }

.charTop { display:flex; gap:8mm; }
.charTop .art { flex:0 0 58%; background:#f5f7fc; border-radius:3mm; padding:3mm;
                align-self:flex-start; }
.charTop .art img { width:100%; height:auto; }
.charTop .info { flex:1; padding-top:2mm; }
.cname { font-size:26pt; font-weight:700; line-height:1.2; }
.cen { font-size:10pt; color:#8892a6; margin-bottom:3.5mm; }
.kv { font-size:9.5pt; color:#3c4455; margin-bottom:1.1mm; }
.kv b { color:#1c2028; }
.desc { margin:4mm 0 6mm; font-size:10pt; color:#4a5261; line-height:1.8; }
.skills { display:grid; grid-template-columns:repeat(3,1fr); gap:4mm; margin-top:5mm; }
.skills .row { padding:3mm; border:.3mm solid #e3e7ef; border-radius:2.5mm;
               background:#fbfcfe; display:flex; gap:3mm; align-items:center; }
.skills .k { font-size:7.6pt; color:#8892a6; }
.skills .n { font-size:9.6pt; font-weight:700; color:#1c2028; line-height:1.35; }
.skills .d { font-size:9.2pt; color:#67708a; margin-top:.6mm; line-height:1.55; }

.skdet .skblk { border:.3mm solid #e3e7ef; border-radius:3mm; padding:3mm 3.6mm;
                margin-bottom:3.2mm; background:#fbfcfe; }
.skdet .hd { display:flex; gap:3mm; align-items:center;
             border-bottom:.3mm solid #edf0f6; padding-bottom:2mm; margin-bottom:2mm; }
.skdet .ic { width:14mm; height:14mm; border-radius:2.4mm; flex:0 0 14mm;
             background:linear-gradient(140deg,#1a2131,#2b3752);
             display:flex; align-items:center; justify-content:center; }
.skdet .ic img { width:11mm; height:11mm; }
.skdet .k { font-size:7.8pt; color:#8892a6; letter-spacing:.06em; }
.skdet .n { font-size:12pt; font-weight:700; color:#1c2028; line-height:1.35; }
.skdet .bd { font-size:8.7pt; line-height:1.56; color:#39404f; }
.skdet .ln { margin-bottom:.7mm; }
.skdet .kw { color:#0f62c9; }
.skills .ic { width:13mm; height:13mm; border-radius:2mm; flex:0 0 13mm;
              background:linear-gradient(140deg,#1a2131,#2b3752);
              display:flex; align-items:center; justify-content:center; }
.skills .ic img { width:10mm; height:10mm; }
.files { margin-top:4mm; font-size:7.8pt; color:#8892a6; line-height:1.75;
         border-top:1px dashed #dde3ee; padding-top:2mm; }
.files b { color:#5b6479; font-weight:600; }

.skin { display:flex; gap:5mm; margin-bottom:6mm; height:116mm; }
.skin .a { flex:0 0 50%; background:#f5f7fc; border-radius:3mm; padding:3mm;
           display:flex; align-items:center; justify-content:center; }
.skin .a img { width:auto; height:auto; max-width:100%; max-height:100%; }
.skin .b { flex:1; padding-top:1mm; }
.skin h3 { font-size:14pt; margin-bottom:1mm; }
.skin .en { font-size:8.5pt; color:#8892a6; margin-bottom:3mm; }

.wall2 { display:grid; grid-template-columns:1fr 1fr; gap:4mm; }
.wall2 figure { margin:0; }
.wall2 img { width:100%; border-radius:2.5mm; }
.wall2 figcaption { font-size:8pt; color:#7b8494; margin-top:1mm; }
.row5 { display:grid; grid-template-columns:repeat(5,1fr); gap:2mm; margin-top:3mm; }
.row5 img { width:100%; border-radius:1.5mm; }
.row5 div.t { font-size:7.4pt; color:#7b8494; text-align:center; margin-top:0.6mm; }
.side4 { display:grid; grid-template-columns:repeat(4,1fr); gap:3mm; margin-top:4mm; }
.side4 img { width:100%; height:56mm; object-fit:contain; border-radius:1.5mm; background:#0e1116; }
.side4 div.t { font-size:7.4pt; color:#4a5261; text-align:center; margin-top:1mm; line-height:1.35; }
/* 大厅动画 9 套用 5 列（4 列会剩一个孤零零的尾图） */
.side5 { display:grid; grid-template-columns:repeat(5,1fr); gap:2.4mm; margin-top:3.5mm; }
.side5 img { width:100%; height:44mm; object-fit:contain; border-radius:1.5mm; background:#0e1116; }
.side5 div.t { font-size:6.8pt; color:#4a5261; text-align:center; margin-top:.8mm; line-height:1.3; }
.icons { display:grid; grid-template-columns:repeat(6,1fr); gap:2.4mm; }
.icons figure { margin:0; text-align:center; }
.icons img { width:100%; border-radius:1.6mm; background:#f5f7fc; }
.icons figcaption { font-size:6.5pt; color:#8892a6; margin-top:.6mm;
                    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.note { font-size:8.5pt; color:#7b8494; margin-top:3mm; }
.tight th, .tight td { padding:1.0mm 1.5mm; }
.stage th, .stage td { padding:0.7mm 1.3mm; }
.nowrap { white-space:nowrap; }

/* 活动剧情清单：48 行拆成左右两栏，避免单表过长 */
.two { display:flex; gap:5mm; align-items:flex-start; }
.two > div { flex:1; min-width:0; }
.act th, .act td { padding:.5mm 1.4mm; font-size:6.9pt; line-height:1.16; }
.act td.n { text-align:right; font-family:Consolas,monospace; }
.sample { font-size:7.2pt; line-height:1.52; background:#f7f9fd; border-left:1.2mm solid #3d5afe;
          padding:2.4mm 3mm; white-space:pre-wrap; color:#39404f; border-radius:0 2mm 2mm 0; }
/* 透视 / 装配件拆解 图格 */
.p4 { display:grid; grid-template-columns:repeat(4,1fr); gap:2.4mm; }
.p2 { display:grid; grid-template-columns:1fr 1fr; gap:3mm 4mm; }
.p4 figure, .p2 figure { margin:0; text-align:center; }
.p4 img { width:100%; height:44mm; object-fit:contain; border-radius:2mm;
          background:linear-gradient(165deg,#6c7789,#59637a); }
.p2 img { width:100%; height:45mm; object-fit:contain; border-radius:2mm; background:#f7f9fd; }
.p4 figcaption, .p2 figcaption { font-size:7.3pt; color:#6b7488; margin-top:.7mm; }
.p4 figcaption b, .p2 figcaption b { color:#26303f; }
"""


# PDF 用的中间图缓存。**不是交付物**，全量可重建（实测：整个目录移走后重跑，
# 第 39/48 页像素差异 0.000%）。
# 放 _构建/ 下，与交付物用下划线前缀区分；不进 _素材清单.csv。
CACHE = ROOT / "_构建" / "PDF缓存"


def pic(src: Path, maxh: int = 1500) -> Path:
    """裁掉透明边并按高度限制缩放，缓存到 _报告素材，避免 PDF 体积爆炸。
    有不透明需求（立绘/小人）的留 PNG，纯实景图（场景还原）转 JPEG。

    缓存必须带源文件指纹：早期版本只按文件名缓存，导致源图重渲之后 PDF 里永远是旧图
    （阵位图、莱彻总览图都踩过这个坑，症状是"改了脚本但画面没变"）。"""
    st = src.stat()
    stamp = f"{int(st.st_mtime)}:{st.st_size}"
    out = CACHE / src.parent.name / f"{src.stem}.png"
    outj = out.with_suffix(".jpg")
    stp = out.with_suffix(".stamp")
    if stp.exists() and stp.read_text() == stamp:
        if out.exists():
            return out
        if outj.exists():
            return outj
    for p in (out, outj):                    # 源图变了 → 丢掉旧缓存
        if p.exists():
            p.unlink()
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    if im.height > maxh:
        im = im.resize((max(1, round(im.width * maxh / im.height)), maxh), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    if im.getextrema()[3][0] < 250:          # 有透明像素 → 必须 PNG
        im.save(out, optimize=True)
        res = out
    else:
        im.convert("RGB").save(outj, quality=90, optimize=True)
        res = outj
    stp.write_text(stamp)
    return res


def u(p: Path) -> str:
    return pic(p).as_uri()


def imgsize(p: Path) -> str:
    """页脚「资源文件」列尺寸用：读源图裁掉透明边后的真实像素尺寸，不手写。"""
    from PIL import Image
    with Image.open(p) as im:
        im = im.convert("RGBA")
        bb = im.getbbox()
        w, h = (bb[2] - bb[0], bb[3] - bb[1]) if bb else im.size
    return f"{w}×{h}"


def best_art(d: Path) -> Path:
    """同一张立绘在目录里有多个规格，取裁掉透明边后像素面积最大的那张。

    踩坑记录：`立绘_高清.png` 其实是 1024×1024 的**图集页**，人物只占 565×920；
    真正分辨率最高的是 `小人立绘.png`（1800 高，全透明底、无图集留白），
    文件名的"小人"是采集阶段的遗留命名，画面就是同一张全身立绘，不是 Q 版。
    所以这里不按文件名判断，按实测像素面积取最大。"""
    cand = [p for p in (d / "小人立绘.png", d / "立绘_高清.png") if p.exists()]
    if not cand:
        raise FileNotFoundError(d)
    def area(p: Path) -> int:
        from PIL import Image
        with Image.open(p) as im:
            im = im.convert("RGBA")
            bb = im.getbbox()
            return (bb[2] - bb[0]) * (bb[3] - bb[1]) if bb else im.size[0] * im.size[1]
    return max(cand, key=area)


def clean(s: str) -> str:
    s = TAG.sub("", s or "")
    s = VAR.sub("X", s)
    s = re.sub(r"\s*\n\s*", " ", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def load_skills():
    """技能一律取 SkillLevel=10 的那一条 + 该条的 DescriptionValueList。

    链路（全部客户端实证）：
      CharacterTable.ResourceId → Skill1Id/Skill2Id/UltiSkillId
        → SkillInfoTable.Id → GroupId → 同 GroupId 且 SkillLevel=10 的记录
    文案取 DescriptionLocalkey（= Locale_Skill:<GroupId>_description），
    里面的 {description_value_01..11} 逐个替换成该条的 DescriptionValueList。
    """
    info = {r["GroupId"]: r for r in json.loads(SKILL_JSON.read_text(encoding="utf-8"))
            if r.get("SkillLevel") == 10}
    con = sqlite3.connect(f"file:{LSC / 'Locale_Skill.dec'}?mode=ro", uri=True)
    con_c = sqlite3.connect(f"file:{LSC / 'Locale_Character.dec'}?mode=ro", uri=True)

    def loc(key):
        r = con.execute("select [zh-CN] from Locale_Skill where Key=?", (key,)).fetchone()
        return r[0] if r else ""

    for c in CHARS:
        r = con_c.execute("select [zh-CN] from Locale_Character where Key=?",
                          (f"c{c['cid']}_description",)).fetchone()
        c["desc"] = clean(r[0]) if r else ""
        items = []
        for i, g in enumerate(c["sk"]):
            rec = info.get(int(g))
            if not rec:
                items.append(dict(type="", name=g, lines=["（SkillInfoTable 无 GroupId=%s 的 10 级记录）" % g],
                                  icon=None, raw=""))
                continue
            typ = loc(rec["InfoDescriptionLocalkey"].split(":")[-1])
            nm = loc(rec["NameLocalkey"].split(":")[-1])
            vals = [v.get("DescriptionValue", "") for v in rec["DescriptionValueList"]]
            lines = render_desc(loc(rec["DescriptionLocalkey"].split(":")[-1]), vals)
            icon = ICON_SRC / (rec["Icon"] + ".png")
            if icon.exists():
                dest = ROOT / "01_新角色" / c["dir"] / f"技能图标_{i + 1}_{typ or ('技能%d' % i)}.png"
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(icon, dest)
                icon = dest
            else:
                icon = None
            items.append(dict(type=typ, name=nm, lines=lines, icon=icon,
                              gid=g, raw=loc(rec["DescriptionLocalkey"].split(":")[-1])))
        c["skills"] = items


def render_desc(raw, vals):
    """把客户端富文本转成可排版的 HTML 行。
    <color=..>..</color> 可能跨行，先在每个色块内部把换行换成闭合+重开，
    否则按行切开会出现未闭合的 span。"""
    s = (raw or "").replace("\r", "")

    def _v(m):
        i = int(m.group(1)) - 1
        return vals[i] if 0 <= i < len(vals) else ""

    s = SVAR.sub(_v, s)
    s = SWG.sub(lambda m: f'<b class="kw">{m.group(1)}</b>', s)

    def _c(m):
        col, inner = m.group(1), m.group(2)
        inner = inner.replace("\n", f'</span><br><span style="color:#{col}">')
        return f'<span style="color:#{col}">{inner}</span>'

    s = SCOLOR.sub(_c, s)
    return [x.strip() for x in s.split("\n") if x.strip()]


def short(text: str, n=62) -> str:
    text = text.replace("■", "").strip()
    return text if len(text) <= n else text[:n] + "…"


def page_char(c) -> str:
    d = ROOT / "01_新角色" / c["dir"]
    # 概览只列「图标 + 类型 + 名称」，全文与 10 级数值放下一页，避免截断
    rows = []
    for s in c["skills"]:
        icon = f'<img src="{u(s["icon"])}">' if s["icon"] else ""
        rows.append(f'<div class="row"><div class="ic">{icon}</div>'
                    f'<div class="tx"><div class="k">{s["type"]}</div>'
                    f'<div class="n">{s["name"]}</div></div></div>')
    sk = "".join(rows)
    # 立绘只贴 1 张（分辨率最高的那张）；其余规格不重复贴图，只在页脚列文件名与尺寸
    art = best_art(d)
    others = [x for x in ("立绘.png", "立绘_高清.png", "半身像.png", "小人立绘.png")
              if (d / x).exists() and x != art.name]
    fl = f'本页立绘：<b>{art.name}</b>　{imgsize(art)}　（每名角色只贴这一张）'
    if others:
        fl += "<br>同目录其他规格（不重复贴图）：" + "　".join(
            f'<b>{x}</b> {imgsize(d / x)}' for x in others)
    return f"""
<div class="page">
  <div class="h2">新角色 · {c['name']}</div>
  <div class="charTop">
    <div class="art"><img src="{u(art)}"></div>
    <div class="info">
      <div class="cname">{c['name']}</div>
      <div class="cen">{c['en']}</div>
      <div class="kv"><span class="tag {'ssr' if c['rare']=='SSR' else 'sr'}">{c['rare']}</span>
        <span class="tag">爆裂 {c['burst']}</span>
        <span class="tag">{c['origin']}</span></div>
      <div class="kv">CV：<b>{c['cv']}</b></div>
      <div class="kv">获取方式：<b>{c['how']}</b></div>
      <div class="desc">{c['desc']}</div>
      <div class="files">{fl}</div>
    </div>
  </div>
  <div class="skills">{sk}</div>
</div>"""


def page_skill_detail(c) -> str:
    blocks = ""
    for s in c["skills"]:
        body = "".join(f'<div class="ln">{x}</div>' for x in s["lines"])
        icon = f'<img src="{u(s["icon"])}">' if s["icon"] else ""
        blocks += f"""
<div class="skblk">
  <div class="hd"><div class="ic">{icon}</div>
    <div><div class="k">{s['type']}</div><div class="n">{s['name']}</div></div></div>
  <div class="bd">{body}</div>
</div>"""
    return f"""
<div class="page">
  <div class="h2">技能详情 · {c['name']} <small>全部数值取 10 级</small></div>
  <div class="lead">数值取客户端 SkillInfoTable 中 SkillLevel=10 的记录；文案为该条 DescriptionLocalkey 的官方中文，
    {{description_value_01}} 一类占位符已按同一条记录的 DescriptionValueList 填入，全文不截断。</div>
  <div class="skdet">{blocks}</div>
</div>"""


def page_skins(pair, idx, total) -> str:
    body = ""
    for s in pair:
        d = ROOT / "02_新皮肤" / s["dir"]
        art = best_art(d)
        others = [x for x in ("立绘.png", "立绘_高清.png", "半身像.png", "小人立绘.png")
                  if (d / x).exists() and x != art.name]
        fl = f'本页立绘：<b>{art.name}</b>　{imgsize(art)}'
        if others:
            fl += "<br>同目录其他规格（不重复贴图）：" + "　".join(
                f'<b>{x}</b> {imgsize(d / x)}' for x in others)
        body += f"""
<div class="skin">
  <div class="a"><img src="{u(art)}"></div>
  <div class="b">
    <h3>{s['name']}</h3>
    <div class="en">{s['en']}</div>
    <div class="kv">所属角色：<b>{s['owner']}</b></div>
    <div class="kv">获取方式：<b>{s['how']}</b></div>
    <div class="files">{fl}</div>
  </div>
</div>"""
    return f"""
<div class="page">
  <div class="h2">新皮肤 <small>{idx}–{idx+len(pair)-1} / {total}</small></div>
  {body}
</div>"""


def _drop_block(src: str, cls: str) -> str:
    """删掉 class 含 cls 的顶层 div。

    按标签深度配对，不用 `.*?` 正则硬抠 —— .note/.warn 里常嵌 <div>，
    懒惰正则会在第一个内层 </div> 处截断，留下半截标签把后面整页搞坏。
    """
    opener = re.compile(r'<div class="[^"]*(?<![A-Za-z0-9_-])%s(?![A-Za-z0-9_-])[^"]*"[^>]*>'
                        % re.escape(cls))
    tag = re.compile(r"<div\b|</div>")
    out, i = [], 0
    while True:
        m = opener.search(src, i)
        if not m:
            out.append(src[i:])
            return "".join(out)
        out.append(src[i:m.start()])
        depth, j = 1, m.end()
        while depth and j < len(src):
            t = tag.search(src, j)
            if not t:
                j = len(src)
                break
            depth += 1 if t.group(0) == "<div" else -1
            j = t.end()
        i = j


def apply_brief(src: str) -> str:
    """按 BRIEF_PAGES 白名单把详版 HTML 删成简版。"""
    head, *rest = src.split('<div class="page">')
    if not rest:
        print("!! 没有 .page 分页，简版退化为详版 —— 不要这样交付")
        return src
    keep, dropped = [], []
    for i, body in enumerate(rest):
        if i not in BRIEF_PAGES:
            m = (re.search(r'<div class="h2">(.*?)</div>', body, re.S)
                 or re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S))
            t = TAG.sub("", m.group(1)).strip().replace("\n", " ")[:24] if m else "?"
            dropped.append(f"{i}={t}")
            continue
        keep.append('<div class="page">' + _drop_block(_drop_block(body, "note"), "warn"))
    out = head + "".join(keep)
    if "</body>" not in out:                      # 末页被删时补回闭合标签
        out += "\n</body>\n</html>\n"
    for a, b in BRIEF_REWRITE:
        out = out.replace(a, b)
    plain = TAG.sub("", out)
    hits = [w for w in BRIEF_WORDS if w in plain]
    shown = ", ".join(dropped[:8]) + (f" …共 {len(dropped)} 页" if len(dropped) > 8 else "")
    print(f"简版 {len(keep)} 页（白名单 {sorted(BRIEF_PAGES)}）｜删：{shown}")
    if hits:
        print(f"!! 简版里仍有技术词：{hits} —— 交付前必须删掉或改写")
    return out


def main():
    load_skills()
    act = ROOT / "03_活动" / "PERSONA ON FRONTLINE（ce009）"
    illus = sorted((act / "剧情插画").glob("*.png"))
    items = sorted((act / "活动道具与图标").glob("*.png"))
    tuts = sorted((act / "活动教学图").glob("*.png"))
    banners = [b for b in sorted((ROOT / "04_卡池横幅").glob("EVENT_BANNER_*.png"))
               if not b.name.endswith("_S.png")]
    ml = ROOT / "05_主线_47-48章"
    trail = [t for t in sorted((ml / "05_图片资源" / "章节预告图").glob("*.png"))
             if not t.name.endswith("_S.png")]
    act_banner = act / "EVENT_BANNER_CE009.png"

    # 主线数据全部从 tsv 读，不在脚本里写数
    # 2026-10-25 目录重组：文件按类别进子目录，这里做名字 → 相对路径的映射
    SUB = {
        "01_章节档案.tsv": "02_章节与关卡/01_章节档案.tsv",
        "10_主线任务链.tsv": "02_章节与关卡/10_主线任务链.tsv",
        "12_关卡坐标_47章.tsv": "03_地图与点位/12_关卡坐标_47章.tsv",
        "13_关卡坐标_48章.tsv": "03_地图与点位/13_关卡坐标_48章.tsv",
    }

    def tsv(name):
        p = ml / SUB.get(name, name)
        rows = [l.split("\t") for l in p.read_text(encoding="utf-8-sig").splitlines()
                if l and not l.startswith("#")]
        return rows[0], rows[1:]

    _, chap_rows = tsv("01_章节档案.tsv")
    chap = {r[0]: dict(zip(["ch", "cn", "en", "field", "hard", "story", "n", "nh", "ns",
                            "bp", "hbp", "lv", "items"], r)) for r in chap_rows}
    _, quest_rows = tsv("10_主线任务链.tsv")
    q47 = [r for r in quest_rows if r[1] == "第47章"]
    q48 = [r for r in quest_rows if r[1] == "第48章"]

    # 关卡坐标：取每章第一关，写进地图页做样例
    def first_stage(name):
        _, rr = tsv(name)
        if not rr:
            return "—"
        r = rr[0]
        return f'{r[1]}　X {r[3]}　Z {r[4]}　朝向 {r[5]}°'

    c47_first = first_stage("12_关卡坐标_47章.tsv")
    c48_first = first_stage("13_关卡坐标_48章.tsv")

    heroes = "".join(
        f'<img src="{u(ROOT / "01_新角色" / c["dir"] / "小人立绘.png")}">' for c in CHARS)

    overview = "".join(f"""
<div class="card">
  <img src="{u(ROOT / '01_新角色' / c['dir'] / '半身像.png')}" style="width:100%;height:60mm;object-fit:contain">
  <div class="nm">{c['name']}</div>
  <div class="en">{c['en']}</div>
  <div style="margin-top:1.5mm"><span class="tag {'ssr' if c['rare']=='SSR' else 'sr'}">{c['rare']}</span>
    <span class="tag">爆裂 {c['burst']}</span></div>
</div>""" for c in CHARS)

    illus_pages = ""
    for start in range(0, len(illus), 2):
        chunk = illus[start:start + 2]
        figs = "".join(
            f'<figure><img src="{u(p)}"><figcaption>剧情插画 {p.stem.split("_")[-1].replace("-", " / ")}'
            f'　2048×2048</figcaption></figure>' for p in chunk)
        illus_pages += f"""
<div class="page">
  <div class="h2">活动剧情插画 <small>{start+1}–{start+len(chunk)} / {len(illus)}</small></div>
  <div class="wall2">{figs}</div>
</div>"""

    icon_figs = "".join(
        f'<figure><img src="{u(p)}"><figcaption>{p.stem}</figcaption></figure>' for p in items)
    tut_pages = ""
    for start in range(0, len(tuts), 4):
        chunk = tuts[start:start + 4]
        figs = "".join(
            f'<figure><img src="{u(p)}"><figcaption>{p.stem.replace("ele_ce009_tutorial_", "教学图 ")}'
            f'</figcaption></figure>' for p in chunk)
        tut_pages += f"""
<div class="page">
  <div class="h2">活动教学图 <small>{start+1}–{start+len(chunk)} / {len(tuts)}</small></div>
  <div class="lead">活动玩法说明图，512×400 原图。</div>
  <div class="wall2">{figs}</div>
</div>"""

    # ---- 战斗场景还原（从 spotbackground(hd) 包按实机相机透视投影重建）----
    BS = ml / "06_战斗场景还原"
    ASM = Path(r"D:\Codex\临时\nikke_intl_20261029\out")
    battle_pages, battle_rows = "", ""
    for sh in sorted(BS.glob("*_总览.png")):
        key = sh.stem.replace("_总览", "")
        asm_p = ASM / ("asm_sbg_%s.json" % key.rsplit("_", 1)[-1])
        n_ob = n_tri = 0
        bbox = ["—", "—"]
        slot_rows = ""
        if asm_p.exists():
            A2 = json.loads(asm_p.read_text(encoding="utf-8"))
            n_ob = A2["n_props"]
            n_tri = sum(len(p.get("tri") or []) // 3 for p in A2["props"])
            if A2.get("bbox"):
                bbox = [" ".join(str(x) for x in A2["bbox"][0]),
                        " ".join(str(x) for x in A2["bbox"][1])]
            for si, s in enumerate(A2.get("slots") or []):
                cam = s.get("camera") or [0, 0, 0]
                slot_rows += (f'<tr><td>阵位 {si + 1}</td>'
                              f'<td class="mono">{cam[0]:.2f}　{cam[1]:.2f}　{cam[2]:.2f}</td>'
                              f'<td class="mono">{s.get("cover", "")}　/　camera_position</td></tr>')
        battle_rows += (f'<tr><td><b>{key}</b></td><td>{n_ob}</td><td>{n_tri:,}</td>'
                        f'<td>{bbox[0]}<br>→ {bbox[1]}</td></tr>')
        slots_html = "".join(
            f'<div><img src="{u(p)}"><div class="t">阵位 {i}</div></div>'
            for i in range(1, 6) for p in [BS / f"{key}_s{i}.png"] if p.exists())
        battle_pages += f"""
<div class="page">
  <div class="h2">进入战斗的关卡场景 · {key} <small>总绘图 + 五个站位</small></div>
  <div class="lead">不是截图。几何、贴图、相机位姿全部从客户端现场包还原。总绘图是自建广角平视，
    一张里同时能看清五个掩体站位；下面五张是各阵位实机视角，红十字是单发能穿多件可破坏物的充能点位。</div>
  <img src="{u(sh)}" style="width:100%;max-height:118mm;object-fit:contain;border-radius:2.5mm">
  <div class="row5">{slots_html}</div>
  <table style="margin-top:2mm;font-size:8.4pt;line-height:1.35">
    <tr><th style="width:16%">站位</th><th style="width:40%">相机 X / Y / Z</th>
        <th>锚点</th></tr>
    {slot_rows}
  </table>
  <div class="note">同一套战场只换相机位置、朝向不变 —— 这正是游戏内换掩体时的镜头行为。
    单张原图（1600×900）与充能点位明细见包内 <b>05_主线_47-48章/06_战斗场景还原/</b>。</div>
</div>"""

    banner_figs = "".join(
        f'<div style="margin-bottom:5mm"><img src="{u(p)}" style="width:100%;border-radius:2.5mm"></div>'
        for p in banners)
    trail_figs = "".join(
        f'<div style="margin-bottom:5mm"><img src="{u(p)}" style="width:100%;border-radius:2.5mm"></div>'
        for p in trail)

    # ---- 关卡信息 / 关底 BOSS / 关卡莱彻（2026-10-25 新增）----
    def rtsv(p):
        rows = [l.split("\t") for l in p.read_text(encoding="utf-8-sig").splitlines()
                if l and not l.startswith("#")]
        return rows[0], rows[1:]

    CHAPDIR = ml / "02_章节与关卡"
    _, stage_all = rtsv(CHAPDIR / "04_关卡信息总表.tsv")
    _, boss_rows = rtsv(CHAPDIR / "05_关底BOSS.tsv")
    _, mon_rows = rtsv(ml / "07_关卡莱彻" / "关卡莱彻_清单.tsv")
    _, mapmon_rows = rtsv(ml / "07_关卡莱彻" / "大地图莱彻_清单.tsv")
    _, bossmon_rows = rtsv(ml / "07_关卡莱彻" / "关底BOSS_实测.tsv")
    _, bgm_rows = rtsv(ml / "08_BGM" / "00_曲目表.tsv")
    _, sk_rows = rtsv(ml / "07_关卡莱彻" / "关卡莱彻_技能.tsv")

    # ---- 活动剧情清单（2026-10-25 十轮：三表合并后重做）----
    # 00_活动清单.tsv 列：活动名 / 条目数 / Main条目 / Sub条目 / 目录名
    EV = ml / "04_剧情文本" / "活动剧情"
    _, act_rows = rtsv(EV / "00_活动清单.tsv")
    act_sorted = sorted(act_rows, key=lambda r: -int(r[1]))
    n_act = len(act_sorted)
    n_act_lines = sum(int(r[1]) for r in act_sorted)

    def _i(row, idx):
        try:
            return int(row[idx] if len(row) > idx and row[idx] else 0)
        except ValueError:
            return 0

    n_main_only = sum(1 for r in act_rows if _i(r, 2) > 0 and _i(r, 3) == 0)
    n_sub_only = sum(1 for r in act_rows if _i(r, 2) == 0 and _i(r, 3) > 0)
    n_both = sum(1 for r in act_rows if _i(r, 2) > 0 and _i(r, 3) > 0)
    n_main_sum = sum(_i(r, 2) for r in act_rows)
    n_sub_sum = sum(_i(r, 3) for r in act_rows)

    # 番外篇：本期不采（详见剧情页末尾的注释），所以这里不再读清单

    TOP_N = 60            # 双栏只列前 60，其余在 tsv 里

    def act_tbl(rows):
        body = "".join(f'<tr><td class="mono">{r[0]}</td><td class="n">{_i(r, 1):,}</td>'
                       f'<td class="n">{_i(r, 2) or "—"}</td><td class="n">{_i(r, 3) or "—"}</td></tr>'
                       for r in rows)
        return ('<table class="act"><tr><th>活动（资源名）</th>'
                '<th style="width:14%;text-align:right">条目</th>'
                '<th style="width:13%;text-align:right">Main</th>'
                '<th style="width:13%;text-align:right">Sub</th></tr>'
                f'{body}</table>')

    top = act_sorted[:TOP_N]
    half = (len(top) + 1) // 2
    act_two = (f'<div class="two"><div>{act_tbl(top[:half])}</div>'
               f'<div>{act_tbl(top[half:])}</div></div>')

    # 抽样：取 ce006（联动活动，体量适中的一部）的前 6 条，原样贴出
    SAMP_ACT = "ce006"
    samp_lines, nk = [], 0
    for ln in (EV / SAMP_ACT / "简中.txt").read_text(encoding="utf-8-sig").splitlines()[4:]:
        if ln.startswith("["):
            if nk >= 6:
                break
            nk += 1
        samp_lines.append(ln)
    samp_txt = "\n".join(samp_lines).strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    samp_n = dict((r[0], r[1]) for r in act_rows)[SAMP_ACT]

    # CE009 客户端下发的全部文本（无剧情对话，见包内 00_说明.md）
    c9_rows = [l.split("\t") for l in (act / "非剧情文本_UI与告示牌" / "CE009_活动文本_全语言.tsv")
               .read_text(encoding="utf-8-sig").splitlines()
               if l and not l.startswith("#")][1:]
    n_c9 = len(c9_rows)
    c9_cat = {}
    for r in c9_rows:
        ex = (r[2] if len(r) > 2 else "").replace("\\n", " / ").replace("\\r", "").strip()
        ex = ex[:30] + ("…" if len(ex) > 30 else "")
        d = c9_cat.setdefault(r[0], [0, ex])
        d[0] += 1
    c9_tab = "".join(f'<tr><td>{k}</td><td class="mono">{v[0]}</td>'
                     f'<td>{v[1]}</td></tr>'
                     for k, v in sorted(c9_cat.items(), key=lambda x: -x[1][0]))

    # ---- 主线插画 + 剧情量（live 统计，不写死）----
    def chap_illus():
        """按 scenariobackground(hd)_assets_eventscene_chap_<章>_* 统计每章插画数。"""
        cnt, total = {}, 0
        for ln in KEYLIST.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not ln.startswith("scenariobackground(hd)_"):
                continue
            total += 1
            m = re.search(r"_assets_eventscene_chap_(\d+)_", ln)
            if m:
                c = int(m.group(1))
                cnt[c] = cnt.get(c, 0) + 1
        return cnt, total

    def mainline_stat():
        """从 Locale_MainScenario 统计每章的剧情段数与条目数。

        注意：除 d_main_<章号>_* 外还有 d_main_01af_* 一类非纯数字章号（旁支/联动），
        它们不归入章节统计，这里直接跳过。"""
        con = sqlite3.connect(f"file:{LSC / 'Locale_MainScenario.dec'}?mode=ro", uri=True)
        per = {}
        for (k,) in con.execute("select [Key] from Locale_MainScenario"):
            if not k.startswith("d_main_"):
                continue
            p = k.split("_")
            if len(p) < 4 or not p[2].isdigit():
                continue
            d = per.setdefault(int(p[2]), [set(), 0])
            d[0].add(p[3])
            d[1] += 1
        con.close()
        return per

    illus_cnt, illus_total = chap_illus()
    ml_stat = mainline_stat()
    chap_tab = ""
    for c in sorted(illus_cnt)[-7:]:
        seg, ent = ml_stat.get(c, [set(), 0])
        hi = ' style="background:#fff4f4"' if illus_cnt[c] <= 1 else ""
        chap_tab += (f'<tr{hi}><td class="mono"><b>{c}</b></td>'
                     f'<td class="mono">{len(seg)}</td>'
                     f'<td class="mono">{ent:,}</td>'
                     f'<td class="mono"><b>{illus_cnt[c]}</b></td></tr>')

    # ---- 莱彻装配件可见性（读 diag_parts_visible.py 的产物）----
    PARTS_TSV = ml / "07_关卡莱彻" / "装配件_可见性.tsv"
    parts_rows = []
    if PARTS_TSV.exists():
        parts_rows = [l.split("\t") for l in
                      PARTS_TSV.read_text(encoding="utf-8").splitlines()
                      if l and not l.startswith("#")][1:]
    mon_stat = {}
    for r in parts_rows:
        d = mon_stat.setdefault(r[0], dict(n=0, hid=[], core=None, corepct=None))
        d["n"] += 1
        if r[8] == "是":
            d["hid"].append(r[1])
        if r[1].startswith("cm_core") and d["core"] is None:
            d["core"] = r[5]
            d["corepct"] = r[6]
    vis_tab = ""
    for tag in ("xmg001", "xma003", "xeg006", "xea003", "eea002", "mea001", "meg006", "mmg005"):
        d = mon_stat.get(tag)
        if not d:
            continue
        hid = "、".join(f'<span class="mono">{x}</span>' for x in d["hid"]) or "无"
        core = (f'可见 {int(d["core"]):,} px（{d["corepct"]}%）') if d["core"] else "无独立核心件"
        vis_tab += (f'<tr><td class="mono"><b>{tag}</b></td><td class="mono">{d["n"]}</td>'
                    f'<td>{hid}</td><td>{core}</td></tr>')

    # 04_关卡信息总表 的列序
    # 0模式 1关卡ID 2关卡编号 3关卡名 4关卡类型 5类别码 6敌人等级 7战力要求 8莱彻预制体
    # 9型号 10体量 11强度分级 12生成型 13技能数 14大地图 15地图X 16地图Z 17奖励ID 18进入条件 19备注

    def stage_page(ch):
        pref = "6047" if ch == 47 else "6048"
        nrows = [r for r in stage_all if r[0] == "普通" and r[1].startswith(pref)]
        hard = {r[2]: r[7] for r in stage_all if r[0] == "困难"}

        def rowhtml(r):
            hl = ' style="background:#fff4f4"' if r[4] == "章末BOSS" else ""
            xy = r[15]
            try:
                xy = f"{float(r[15]):.1f}, {float(r[16]):.1f}"
            except (TypeError, ValueError):
                pass
            return (f'<tr{hl}>'
                    f'<td class="mono"><b>{r[2]}</b></td><td>{r[4]}</td>'
                    f'<td class="mono">{r[6]}</td><td class="mono">{r[7]}</td>'
                    f'<td class="mono">{hard.get(r[2], "—")}</td>'
                    f'<td class="mono">{r[8]}</td><td>{r[9]} / {r[10]}</td>'
                    f'<td>{r[11]}</td><td class="mono nowrap">{xy}</td></tr>')

        THEAD = ('<tr><th style="width:8%">编号</th><th style="width:9%">类型</th>'
                 '<th style="width:6%">等级</th>'
                 '<th style="width:12%">战力(普通)</th><th style="width:12%">战力(困难)</th>'
                 '<th style="width:20%">莱彻</th><th style="width:11%">型号 / 体量</th>'
                 '<th style="width:9%">分级</th><th>地图坐标 X, Z</th></tr>')
        drama = [r for r in stage_all if r[0] == "剧情" and r[2].startswith(f"{ch}-")]

        body = "".join(rowhtml(r) for r in nrows)
        dline = "、".join(f'{r[2].replace("（剧情）", "")}（{r[8]}）' for r in drama)
        return f"""
<div class="page">
  <div class="h2">第 {ch} 章 · 关卡一览 <small>普通 / 困难 / 剧情 三套，逐关数据</small></div>
  <div class="lead">全部字段读自 <b>CampaignStageTable</b> 与 <b>Locale_Stage</b>，没有一条是数出来的。
    关卡类型按 <b>StageCategory</b> 分：普通关 / 精英关 / EX 关 / 章末BOSS；红底那行就是关底 BOSS。
    困难关战力单列一列，与普通关逐关对应。</div>
  <table class="tight stage" style="font-size:6.7pt;line-height:1.18">
    {THEAD}
    {body}
  </table>
  <div class="note">剧情战共 {len(drama)} 关（{dline}），在 <b>Locale_Stage</b> 里没有关卡名，
    编号按父关回挂；都用同一模板（等级 52、战力 10,360），战力不能当门槛看。<br>
    EX 关战力要求写 0 表示不校验战力，敌人等级反而比关底 BOSS 高 —— 属于通关后的额外挑战。</div>
</div>"""

    stage_pages = stage_page(47) + stage_page(48)

    # 关底 BOSS
    def uniq_skills(fid):
        seen, out = set(), []
        for r in sk_rows:
            if r[0] != fid or r[4] in seen:
                continue
            seen.add(r[4])
            out.append(r)
        return out

    BOSS_ART = ml / "07_关卡莱彻" / "立绘"
    # 2026-10-25 三修：立绘统一改名成「序号_中文名_型号」，而 05_关底BOSS.tsv 第 5 列记的是
    # 关卡表里的 FieldMonsterId（47 章写 eea002），不是 BOSS 本体，所以按章直接映射。
    BOSS_ART_MAP = {"第 47 章": "13_安尼希利奥_xba003_1阶段.png",
                    "第 48 章": "14_莉贝雷利奥躯体_eba002_1阶段.png"}
    bcols, btab = "", ""
    for ch in ("第 47 章", "第 48 章"):
        rows = [r for r in boss_rows if r[0] == ch]
        if not rows:
            continue
        r0 = rows[0]
        art = BOSS_ART / BOSS_ART_MAP.get(ch, f"{r0[5]}_立绘.png")
        bcols += f"""
  <div style="flex:1;text-align:center">
    <div style="background:#f5f7fc;border-radius:3mm;padding:3mm;height:92mm;
                display:flex;align-items:center;justify-content:center">
      <img src="{u(art)}" style="max-width:100%;max-height:100%">
    </div>
    <div style="font-weight:700;font-size:12pt;margin-top:2mm">{ch} 关底 · {r0[5]}</div>
    <div style="font-size:8.4pt;color:#8892a6">{r0[7]} · {r0[8]} / {r0[9]} · 生成型 {r0[10]}</div>
  </div>"""
        for r in rows:
            btab += (f'<tr><td>{r[0]}</td><td>{r[1]}</td><td class="mono">{r[2]}</td>'
                     f'<td class="mono"><b>{r[3]}</b></td><td class="mono">{r[11]}</td>'
                     f'<td class="mono">{r[12]}</td><td class="mono">{r[19]}</td></tr>')

    skill_cells = ""
    for ch in ("第 47 章", "第 48 章"):
        rows = [r for r in boss_rows if r[0] == ch]
        if not rows:
            continue
        fid = rows[0][6]
        # 注意：不能复用 items 这个名字 —— 它是「活动道具与图标」的文件列表，
        # 后面「活动道具与图标」和「本包收录」两处都还在用它，覆盖后页面上会变
        # 成「2 张」这种诡异数字。
        sk_items = uniq_skills(fid)
        body = "".join(
            f'<tr><td class="mono">{r[3]}</td><td><b>{r[4]}</b></td>'
            f'<td>{r[8] or "（无描述，属常规远程攻击）"}</td></tr>' for r in sk_items)
        skill_cells += f"""
  <div style="flex:1">
    <div style="font-weight:700;font-size:10pt;margin-bottom:1.6mm">{ch} · {rows[0][5]} 的技能
      <span style="font-weight:400;color:#8892a6;font-size:8pt">（{len(sk_items)} 种 / {rows[0][13]} 个技能位）</span></div>
    <table style="font-size:7.8pt;line-height:1.35">{body}</table>
  </div>"""

    boss_page = f"""
<div class="page">
  <div class="h2">关底关卡 <small>第 47、48 章各一个，普通 / 困难 / 剧情各一关</small></div>
  <div class="lead">章末关卡靠 <b>CampaignStageTable.StageCategory = 4</b> 识别
    （<b>MonsterFieldTable.IsBoss</b> 对这两关都是 False，拿它筛会漏）。<br>
    ⚠ 本页列的是<b>关卡</b>，不是 BOSS 本体：表里的 <span class="mono">eea002</span> / <span class="mono">xea003</span>
    是这两关登记的<b>大地图巡逻怪</b>。真正的关底 BOSS 是<b>安尼希利奥</b>与<b>莉贝雷利奥躯体</b>，见后面「大地图莱彻 &amp; 关底 BOSS」那页。</div>
  <div style="display:flex;gap:7mm">{bcols}</div>
  <table class="tight" style="margin-top:4mm;font-size:8pt;line-height:1.3">
    <tr><th style="width:12%">章</th><th style="width:9%">模式</th><th style="width:13%">关卡ID</th>
        <th style="width:10%">编号</th><th style="width:11%">等级</th><th style="width:15%">战力要求</th>
        <th>奖励ID</th></tr>
    {btab}
  </table>
  <div style="display:flex;gap:7mm;margin-top:4mm">{skill_cells}</div>
  <div class="note">两个 BOSS 都<b>没有专属战斗场景</b>：老章节的 BOSS 场地会命名成
    <b>sbg_cityforest&lt;BOSS预制体&gt;_00x</b>（如 sbg_cityforesteba001_001、sbg_cityforestundercrystalxbg001_001），
    而拿 eea002 / xea003 去搜 spotbackground(hd) 全部 174 个包 0 命中，
    47 / 48 章的关底战复用的是 sbg_cityforest_001 / 002 / 003 通用背景。<br>
    技能名与描述取 <b>Locale_Skill</b> 官方原文；同一技能在多个技能位上会重复出现（难度分级用），所以「技能位」比「技能种类」多。</div>
</div>"""

    # 关卡莱彻（8 种，按型号去重，两章合并成一行）
    # 0中文名 1预制体 2型号表预制体 3第47章关数 4第48章关数 5合计关数 6关卡类别 7强度分级
    # 8UiGrade原值 9型号等级/体量 10属性 11生成型 12移动 13BOSS 14战力 15图鉴级别 16图鉴代码
    # 17名表同族名 18FieldMonsterId 19立绘文件
    mon_tab = ""
    for r in mon_rows:
        hl = ' style="background:#fff4f4"' if r[13] == "是" else ""
        body = r[9].split("/")[-1]          # 型号等级/体量 → 只取体量（等级另有一列）
        mon_tab += (f'<tr{hl}>'
                    f'<td><b>{r[0]}</b></td><td class="mono">{r[1]}</td>'
                    f'<td class="mono">{r[3]}</td><td class="mono">{r[4]}</td>'
                    f'<td>{r[6]}</td><td>{r[7]}</td><td>{body}</td>'
                    f'<td class="nowrap">{r[10]}</td><td class="nowrap">{r[11]}</td>'
                    f'<td class="nowrap">{r[12]}</td></tr>')

    monster_pages = f"""
<div class="page">
  <div class="h2">本章莱彻总览 <small>14 种，全部从静态表 + 模型包读出</small></div>
  <div class="lead">这批莱彻在客户端里<b>没有 2D 立绘</b>，全是 SkinnedMesh 3D 模型 + 骨骼动画，
    下面 14 格是<b>正面正交</b>渲染的静帧（统一 1200×1400 画布，不是截图、不是手绘）：
    关卡内 8 + 大地图 6 − 两者共有的太阳 / 倒吊者 = <b>12 种</b>，再加两个关底 BOSS（这里各取 1 阶段）。
    下表只列关卡内的 8 种。</div>
  <img src="{u(ml / '07_关卡莱彻' / '莱彻总览_14种.png')}"
       style="width:100%;max-height:126mm;object-fit:contain;border-radius:2.5mm">
  <table class="tight" style="margin-top:3mm;font-size:8.6pt;line-height:1.35">
    <tr><th style="width:12%">中文名</th><th style="width:18%">预制体</th>
        <th style="width:6%">47章</th><th style="width:6%">48章</th>
        <th style="width:22%">关卡类别</th><th style="width:11%">强度分级</th>
        <th style="width:7%">体量</th><th style="width:6%">属性</th>
        <th style="width:6%">生成型</th><th>移动</th></tr>
    {mon_tab}
  </table>
  <div class="note">中文名取自第 10 张本地化表 <b>Locale_Monster</b>（键 <span class="mono">&lt;id&gt;_name</span>，
    去掉尾部的 <span class="mono">[H.S.T.A.]</span> 这类阵营后缀）；上一版只翻了设备里的 9 张表所以整列为空。<br>
    「47章 / 48章」= 该型号作为 <b>CampaignStageTable.FieldMonsterId</b> 各出现在多少关（普通 + 困难 + 剧情都算）。
    每关只挂 1 种，这是表结构决定的；<b>大地图上还有另外 6 种在巡逻</b>，不算在这张表里 —— 见下一页。<br>
    「强度分级」= <b>MonsterTable.UiGrade</b>，按 <b>MonsterModelId</b> 收该型号<b>全部</b>实体行取众数
    （<b>x*</b> 系 4 个型号在表里只有 10 位 Id，用 8 位 FieldMonsterId 查不到，上一版因此整列是「—」）。
    它与 <b>MonsterModelTable.Grade</b> 是同一套 1~7 阶梯的两个字段，只有关底 BOSS 那只会不一致（见下页）。<br>
    每关刷几只拿不到：177 张导出表里没有任何「关卡 → 怪物编成 / 波次 / 数量」的外键，
    战斗场景包里也只有几何与贴图、没有刷怪点。</div>
</div>"""

    # 大地图莱彻 + 关底 BOSS（2026-10-25 二修）
    mapmon_tab = ""
    seen = {}
    order = []
    for r in mapmon_rows:
        k = r[1]
        if k not in seen:
            seen[k] = {"zh": r[2], "a": "—", "b": "—", "g": r[4], "s": r[5], "m": r[7]}
            order.append(k)
        if r[0].startswith("47"):
            seen[k]["a"] = r[3]
        else:
            seen[k]["b"] = r[3]
    for k in order:
        d = seen[k]
        mapmon_tab += (f'<tr><td><b>{d["zh"]}</b></td><td class="mono">{k}</td>'
                       f'<td class="mono">{d["a"]}</td><td class="mono">{d["b"]}</td>'
                       f'<td>{d["g"]} / {d["s"]}</td><td>{d["m"]}</td></tr>')

    boss_cards = ""
    for fn, t1, t2 in [
        ("安尼希利奥_双阶段对照.png", "安尼希利奥 · 1 阶段 / 2 阶段", "xba003_dmtr · 型号 451003"),
        ("莉贝雷利奥躯体_双阶段对照.png", "莉贝雷利奥躯体 · 1 阶段 / 2 阶段", "eba002_hsta · 型号 251016"),
    ]:
        boss_cards += (
            f'<div style="flex:1">'
            f'<img src="{u(ml / "07_关卡莱彻" / fn)}" '
            f'style="width:100%;border-radius:2mm">'
            f'<div style="font-size:7.6pt;line-height:1.3;margin-top:1.2mm;text-align:center">'
            f'<b>{t1}</b><br><span class="mono" style="color:#7b8494;font-size:7pt">{t2}</span></div></div>')

    boss2_page = f"""
<div class="page">
  <div class="h2">大地图莱彻 &amp; 关底 BOSS <small>BOSS 立绘这次从模型包里渲出来了</small></div>
  <div class="lead">上一张表是「进关前在大地图上巡逻的那只」。大地图上一共摆了几种，要直接读地图模型包
    <b>campaignmapmodelgroup_010 / _011</b> 里的 GameObject 名 —— 那里还有 6 种，其中 4 种上一版完全没提。</div>
  <table class="tight" style="font-size:8pt;line-height:1.25">
    <tr><th style="width:16%">中文名</th><th style="width:16%">型号</th>
        <th style="width:15%">47 章出现次</th><th style="width:15%">48 章出现次</th>
        <th style="width:20%">型号等级 / 体量</th><th>移动</th></tr>
    {mapmon_tab}
  </table>
  <div class="note" style="margin-top:1.5mm">两章去重后是 <b>12 种</b>（关卡 8 + 大地图 6 − 重叠的
    <b>太阳</b>、<b>倒吊者</b>）；再算上两个关底 BOSS，本章新莱彻共 <b>14 种</b>。</div>

  <div style="display:flex;gap:3mm;margin-top:3mm">
    {boss_cards}
  </div>
  <div class="note" style="margin-top:2.5mm">
    <b>48 章的名字要纠正</b>：上一版写「水母 <span class="mono">eea004</span>」是错的。
    「水母」是另一只莱彻（型号 <span class="mono">231004</span>）。这次从模型包名
    <span class="mono">eba002_hsta</span> → <b>MonsterModelTable</b> 型号 <span class="mono">251016</span> →
    <span class="mono">Locale_Monster:2510160111_name</span> 一路反查，得到的是
    <b>莉贝雷利奥躯体 [H.S.T.A.]</b>，链条闭合。<br>
    <b>为什么现在才有立绘</b>：这两个模型包（<span class="mono">spotmonster_xba003_dmtr</span> /
    <span class="mono">spotmonster_eba002_hsta</span>）此前没下发到本机，这次用 adb 拉回后渲染。
    过程中发现包内给<b>每根骨骼</b>都烘了 <span class="mono">diag(-1,1,-1)</span>，
    直接渲染等于对着外壳<b>内表面</b>看 —— 47 章 1 阶段中间那块死黑面片就是这么来的，抵掉翻转后才看到正面与核心。<br>
    两个阶段（<span class="mono">1phase</span> / <span class="mono">2phase</span>）是两套骨骼位置，
    混渲会在中间拉出空档，必须按<b>父节点</b>名分组。剧情 CG 仍保留在
    <span class="mono">关底BOSS/</span> 作人形形态对照。<br>
    <b>2 阶段看着「碎」不是丢件</b>：它的 10 个网格全部渲染了（主体 1 + 浮游炮 5 + 崩甲臂 4），
    三角形最长边只有 6.4（无跨接错误）、连通块 1,181 个 —— 也就是<b>模型在绑定姿态下本来就是崩甲</b>，
    游戏里由 idle 动画驱动那 225 根骨骼悬浮合拢。48 章 1 阶段下沿那两条笔直细线同理，是触须的绑定姿态。</div>
</div>"""

    # BGM（2026-10-25 二修：格式转换 + 曲目表）
    def _trig(t):
        if "关卡" in t:
            seg = t.split("（")[-1].rstrip("）")
            return "战斗 · " + seg
        return t.replace("场景/大地图·", "场景 · ")

    def _files(ch):
        out = []
        for r in bgm_rows:
            if r[0] != ch:
                continue
            out.append(f'<div><span class="mono" style="font-size:7.4pt">{r[1]}</span> '
                       f'<span style="color:#7b8494">{r[6]}s / {r[8]}MB</span></div>')
        return "".join(out)

    bgm_tab = ""
    for r in bgm_rows:
        # 0目录 1文件名 2曲名 3作曲 4官方时长 5循环 6实测时长 7采样 8WAV 9MP3 10触发位置 11主题 12wav 13mp3
        bgm_tab += (f'<tr><td><b>{r[2]}</b></td><td>{r[3]}</td>'
                    f'<td class="mono">{r[6]}</td><td class="mono">{r[4]}</td>'
                    f'<td>{_trig(r[10])}</td><td class="nowrap">{r[0]}</td></tr>')
    bgm_page = f"""
<div class="page">
  <div class="h2">第 47 / 48 章 BGM <small>客户端里是无扩展名的裸 WAV，已转好</small></div>
  <div class="lead">这 11 条从客户端取出来时<b>没有扩展名</b>，双击打不开 —— 文件头是
    <span class="mono">RIFF / WAVE</span>，44.1 kHz、16 bit、立体声，其实是标准 PCM WAV。
    现在每条都出了 <b>.wav</b>（改名，内容零改动）和 <b>.mp3</b>（256 kbps，体积约 1/6），任选其一都能直接播。</div>
  <table class="tight" style="font-size:9.4pt;line-height:1.5">
    <tr><th style="width:30%">曲名</th><th style="width:25%">作曲</th>
        <th style="width:11%">实测时长</th><th style="width:9%">官方</th>
        <th style="width:17%">触发</th><th>目录</th></tr>
    {bgm_tab}
  </table>
  <div style="display:flex;gap:6mm;margin-top:5mm;font-size:8.6pt;line-height:1.75">
    <div style="flex:1"><div style="font-weight:700;margin-bottom:1mm">47章/ 5 条（wav 体积）</div>{_files("47章")}</div>
    <div style="flex:1"><div style="font-weight:700;margin-bottom:1mm">48章/ 6 条（wav 体积）</div>{_files("48章")}</div>
  </div>
  <div class="note">曲名 / 作曲 / 官方时长取自游戏内唱片机表 <b>JukeboxListTable</b>；触发位置取
    <b>BGMTriggerTable.BgmType</b>。<br>
    <span class="mono">bgm_chapter48_spot_reborn_a</span> 包内没有独立 AudioClip，只有
    <span class="mono">SoundCueData</span>，音频在 <span class="mono">_intro</span>（4.4 s）与
    <span class="mono">_loop</span>（113.5 s）两条里 —— 两段相加 117.9 s，与唱片机表登记的 118 s 对得上，
    所以表里标成「REBORN（前奏段 / 循环段）」。</div>
</div>"""

    # ---- 活动剧情文本 / 主线插画核对 / 莱彻装配件（2026-10-25 新增）----
    ILL = ml / "05_图片资源" / "剧情插画"
    # ce009 剧情抽样（前 6 条，简中原文）
    c9_story_lines, nk = [], 0
    c9_txt_p = act / "剧情文本" / "简中.txt"
    if c9_txt_p.exists():
        for ln in c9_txt_p.read_text(encoding="utf-8-sig").splitlines()[4:]:
            if ln.startswith("["):
                if nk >= 6:
                    break
                nk += 1
            c9_story_lines.append(ln)
    c9_story = ("\n".join(c9_story_lines).strip()
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    c9_n = dict((r[0], r[1]) for r in act_rows).get("ce009", "0")

    event_story_page = f"""
<div class="page">
  <div class="h2">活动剧情文本 <small>{n_act} 部 · {n_act_lines:,} 条 · 5 语</small></div>
  <div class="lead">剧情<b>不是一张表</b>。它在三张表里：<b>Locale_MainScenario</b>（主线 + 单章式活动）、
    <b>Locale_SubScenario</b>（<b>多章式活动</b> + 支线 / 内容关）、<b>Locale_SideStory</b>（<b>番外篇</b>）。
    只查第一张，就会漏掉 <b>{n_sub_only}</b> 个只存在于 SubScenario 的活动。</div>
  <table style="font-size:8.6pt;line-height:1.4;margin-bottom:3mm">
    <tr><th style="width:30%">表</th><th style="width:14%">行数</th><th>装什么</th></tr>
    <tr><td class="mono">Locale_MainScenario</td><td class="n">150,219</td><td>主线 d_main_*（章 1~48）+ 单章式活动 event_*</td></tr>
    <tr><td class="mono">Locale_SubScenario</td><td class="n">126,796</td><td><b>多章式活动</b>（ce003~ce009 等）+ 支线 / 内容关 / 雪境</td></tr>
    <tr><td class="mono">Locale_SideStory</td><td class="n">11,317</td><td><b>番外篇</b> s&lt;编号&gt;_&lt;段&gt;_&lt;句&gt;（<b>本期无新增，未采</b>）</td></tr>
  </table>
  <table style="font-size:8.6pt;line-height:1.4">
    <tr><th style="width:30%">合并后</th><th style="width:34%">活动</th><th>条目</th></tr>
    <tr><td>只出现在 MainScenario</td><td class="n"><b>{n_main_only}</b> 部</td><td class="n">{n_main_sum:,}</td></tr>
    <tr><td>只出现在 SubScenario</td><td class="n"><b>{n_sub_only}</b> 部（含 ce009 / ce003~ce008 等）</td><td class="n">{n_sub_sum:,}</td></tr>
    <tr><td>两表都有</td><td class="n"><b>{n_both}</b> 部</td><td class="n">—</td></tr>
    <tr><td><b>合计</b></td><td class="n"><b>{n_act}</b> 部</td><td class="n"><b>{n_act_lines:,}</b></td></tr>
  </table>
  <div class="note">上一版只查了 MainScenario，得到 48 部 / 89,750 条，并据此误判「CE009 没有剧情」。
    修正后活动数 <b>48 → {n_act}</b>，条目 <b>89,750 → {n_act_lines:,}</b>。
    五个语种（简中 / 繁中 / 日文 / 英文 / 韩文）都是客户端原文，未做机器翻译；缺译的条目整条跳过，不占位。</div>
</div>

<div class="page">
  <div class="h2">活动剧情清单 <small>前 {len(top)} 部 · 按条目数排序</small></div>
  {act_two}
  <div class="note">完整 {n_act} 部见 <span class="mono">00_活动清单.tsv</span>（含每部的 Main / Sub 分列与目录名）。
    「条目」= 一条 key 对应的文本，含对话、旁白与分支，不是"句数"。
    排序遵循「先章号 → 再阶段（序章 &lt; 正文段 &lt; 幕间 &lt; 尾声 &lt; 气泡 &lt; NPC &lt; 迷你游戏）→ 再段号 → 最后 e / s 轨」，
    否则序章会排到章节末尾。</div>
</div>

<div class="page">
  <div class="h2">⚠ 更正：CE009 有完整剧情 <small>{int(c9_n):,} 条</small></div>
  <div class="lead">上一版写「CE009 没有剧情对话文本」，<b>这个结论是错的</b>。ce009 属多章式活动，
    正文全在 <b>Locale_SubScenario</b>，共 <b>{int(c9_n):,}</b> 条，是主线级对话。</div>
  <table style="font-size:8.6pt;line-height:1.4">
    <tr><th style="width:18%">部分</th><th>内容</th></tr>
    <tr><td>第 1 章</td><td>序章 → 第 01~06 段 × <b>e 轨 / s 轨</b> → 幕间</td></tr>
    <tr><td>第 2 章</td><td>第 01~06 段 × <b>e 轨 / s 轨</b> → 幕间 → 尾声</td></tr>
    <tr><td>附加</td><td>气泡对话 30 组、NPC 对话 11 组、迷你游戏开场 6 组（41 条 <span class="mono">d_contents_ce009_mini_*</span>）</td></tr>
    <tr><td>双轨含义</td><td><b>e</b> = 方舟侧（安德森副司令 / D-WAVE / 怪盗团）；<b>s</b> = 联动角色侧（雪子 / 埃癸斯 / QUEEN）</td></tr>
  </table>
  <h3 style="margin:4mm 0 2mm;font-size:11.5pt">抽样 · ce009 第一章序章
    <small style="font-weight:400;color:#7a8496;font-size:8.5pt">简中原文</small></h3>
  <div class="sample">{c9_story}</div>
  <div class="note">错因：只查了 <span class="mono">Locale_MainScenario</span> 一张表，
    又拿 <span class="mono">EventStoryTable.PrologueScenario</span> 为空、
    <span class="mono">CampaignStageTable</span> 查不到活动关卡、
    <span class="mono">ce009scenariocontroller</span> 包内无 TextAsset 三条去"佐证"——
    但这三条都只对单章活动成立，与多章活动无关。五语全文在
    <b>03_活动/PERSONA ON FRONTLINE（ce009）/剧情文本/</b>（简中 255,974 B）。</div>
</div>"""

    # ---- 番外篇：本期不采（2026-10-25 十五修）----
    # 客户端 `Locale_SideStory` 里有 6 篇，但国际服 8-13 这次更新**没有新增番外篇**：
    # 8-13 的 patch notes 里 4.x 全部是 COLLAB / 主线 47-48 / 归档回顾，没有任何 Side Story；
    # 客户端里那 6 篇是当前版本（10 月底）累积的历史内容，最近一篇 GINGERBREAD HOUSE
    # 是 10-08 维护后上线的（与 LITTLE WITCH TRICK 同期）。
    # 国服 8-13 有「新增番外篇 MUDFISH」，但那是国服专有，国际服没有。
    # 所以按「只采本期上线内容」的口径，番外篇整块不采、不进 PDF。


    # ---- 角色大厅站立动画（2026-10-25 十轮新增）----
    LOB = ROOT / "06_角色大厅站立动画"
    _, lob_rows = rtsv(LOB / "00_清单.tsv")
    lob_map = {}
    for r in lob_rows:                      # 目录 资源ID 角色 序号 时装 动画 尺寸 帧数 时长s 动幅% GIF_MB
        lob_map.setdefault(r[1], {"dir": r[0], "role": r[2], "idx": r[3],
                                  "cos": r[4], "anims": {}})
        lob_map[r[1]]["anims"][r[5]] = r
    n_lob = len(lob_map)
    n_lob_anim = sum(len(v["anims"]) for v in lob_map.values())
    lob_total_gif = sum(float(r[10]) for r in lob_rows)

    lob_tbl = ""
    for k, v in lob_map.items():
        a = v["anims"].get("idle", [])
        b = v["anims"].get("action", [])
        lob_tbl += (f'<tr><td>{v["role"]}　<b>{v["cos"]}</b></td><td class="mono">{k}</td>'
                    f'<td class="n">{a[6] if a else "—"}</td><td class="n">{a[7] if a else "—"}</td>'
                    f'<td class="n">{b[7] if b else "—"}</td><td class="n">{b[8] if b else "—"}</td></tr>')

    lob_thumbs = "".join(
        f'<div><img src="{u(LOB / v["dir"] / (k + "_idle_首帧.png"))}">'
        f'<div class="t">{v["role"]}<br><span style="color:#7a8496">{v["cos"]}</span></div></div>'
        for k, v in lob_map.items()
        if (LOB / v["dir"] / (k + "_idle_首帧.png")).exists())

    lobby_page = f"""
<div class="page">
  <div class="h2">角色大厅站立动画 <small>Spine · {n_lob} 套着装 · {n_lob_anim} 条动画</small></div>
  <div class="lead">大厅里<b>站在主界面上的角色</b>不是一张静图，是 Spine 4.1 骨骼动画 ——
    每套着装都有一份独立骨架，内含 12~28 条动画。这与活动奖励那张「大厅动态壁纸」<b>是两种东西</b>：
    后者是单 slot 的整幅画面 + 粒子特效（见前文），前者是真正的骨骼动画。<br>
    本期 4 名角色共 9 套：QUEEN（真）3 套、雪子 3 套、埃癸斯 1 套，以及<b>补采的潘托姆 2 套</b> ——
    潘托姆的骨架一直躺在客户端里，早先只拿它渲过一张 idle 首帧当皮肤页的小人立绘，整段动画漏了。</div>
  <table style="font-size:8.4pt;line-height:1.4">
    <tr><th style="width:26%">角色 / 着装</th><th style="width:16%">资源 ID</th>
        <th style="width:15%;text-align:right">idle 尺寸</th>
        <th style="width:11%;text-align:right">idle 帧</th>
        <th style="width:11%;text-align:right">action 帧</th>
        <th style="text-align:right">action 时长</th></tr>
    {lob_tbl}
  </table>
  <div class="side5">{lob_thumbs}</div>
  <div class="note">上排为各套 <b>idle</b> 首帧。完整一览见
    <b>06_角色大厅站立动画/00_全角色一览.png</b>，逐帧参数见 <b>00_清单.tsv</b>。
    <b>idle</b> = 大厅里一直循环的站立待机；<b>action</b> = 点击角色触发的演出
    （QUEEN 唤摩托、埃癸斯开枪、雪子掩嘴笑、潘托姆甩裙摆等）。</div>
</div>

<div class="page">
  <div class="h2">大厅站立动画 · 怎么渲的 <small>以及两个真坑</small></div>
  <div class="lead">Spine 官方 runtime <b>4.1.56</b>（spine-core + spine-webgl）跑在无头 Chrome 的 WebGL 里，
    用 CDP 调 <span class="mono">__spine.seek(t)</span> 逐帧定格，再 <span class="mono">canvas.toDataURL()</span>
    取像素 —— <b>不能用 Page.captureScreenshot</b>，合成器异步，连拍会拿到上一帧。</div>
  <h3 style="margin:2mm 0 2mm;font-size:11.5pt">坑 1 · 一次 <span class="mono">update(t)</span> 跳到位，画面"不动"</h3>
  <div style="font-size:8.8pt;line-height:1.5;color:#39414f">
    <span class="mono">AnimationState.update(t)</span> 直接大跨度跳到位，会跳过中间帧，混合结果与逐帧播放不一致 ——
    症状是某些套逐帧几乎完全一致（动幅 0.00%~0.5%），但资源本身没问题（抽帧看角色完整、姿态正常）。
    改成以 <b>1/60 s 为步长累加</b>推进后，同几套动幅升到 <b>2.2%~3.8%</b>。
  </div>
  <h3 style="margin:4mm 0 2mm;font-size:11.5pt">坑 2 · <span class="mono">action</span> 用自己的包围盒定构图</h3>
  <div style="font-size:8.8pt;line-height:1.5;color:#39414f">
    <span class="mono">action</span> 里摩托、弹壳、粒子会飞出很远，包围盒被撑爆，长边 1000 时角色只占画面约 <b>1/3</b>。
    做法：先按 <span class="mono">idle</span> 测包围盒定相机，再切到 <span class="mono">action</span> 且<b>不重测</b> ——
    这也正是游戏内换动作时镜头不动的行为。
  </div>
  <h3 style="margin:4mm 0 2mm;font-size:11.5pt">成对动画 <span class="mono">X</span> / <span class="mono">X_02</span> 不一定是两套</h3>
  <table style="font-size:8.4pt;line-height:1.4">
    <tr><th style="width:52%">逐帧骨骼比对（5 个时刻 × 全部骨骼 worldX/Y/rotation）</th>
        <th style="width:22%;text-align:right">最大差</th><th>结论</th></tr>
    <tr><td class="mono">idle / no / pain / sad / surprise 与其 _02</td><td class="n">0.00000</td><td>纯别名</td></tr>
    <tr><td class="mono">delight vs delight_02</td><td class="n">8.66133</td><td>确实不同</td></tr>
    <tr><td class="mono">idle vs special</td><td class="n">0.00015</td><td>基本等同</td></tr>
    <tr><td class="mono">action vs expression_0</td><td class="n">6.15372</td><td>确实不同</td></tr>
  </table>
  <h3 style="margin:4mm 0 2mm;font-size:11.5pt">交付规格</h3>
  <table style="font-size:8.4pt;line-height:1.4">
    <tr><th style="width:24%">项</th><th>值</th></tr>
    <tr><td>格式</td><td>每套每条动画两份：<b>.gif</b>（256 色，循环播放）+ <b>_首帧.png</b>（单帧静图）</td></tr>
    <tr><td>尺寸 · 帧率</td><td>长边 1000，2 倍超采样后 LANCZOS 降采样；15 fps（帧延迟 70 ms，在 10 ms 网格上反解）</td></tr>
    <tr><td>体积</td><td>GIF 合计 {lob_total_gif:.1f} MB（{n_lob_anim} 条，最长一条是潘托姆·圣洁怪盗的 action 10.40 s）</td></tr>
    <tr><td>背景</td><td>纯色 <span class="mono">#0e1116</span>，只渲角色层</td></tr>
  </table>
  <div class="note"><b>已知边界</b>：① 15 fps 定时定帧不是引擎 60 fps，慢速 idle 无差、action 快速位移偶有顿感；
    ② 每套骨架里除 idle / action 外还有表情变体（delight / sad / pain / surprise / angry / think / no）
    与口型（talk_a/i/u/close/start/end），本期未出图；③ 无音效、无描边光 / Bloom / 色彩分级（在引擎里，包内无 shader）；
    ④ 客户端另有一套 <span class="mono">(sd)</span> 骨架，chunk 不在设备缓存内，未参与出图；
    ⑤ 潘托姆·圣洁怪盗在 prefab 组里比别的套多一份 <span class="mono">01_action</span> 预制体
    （本批唯一），说明这套点击演出是独立挂载的 —— prefab 本身没拆，动画数据在骨架里已全拿到。
    原始 .skel / .atlas / .png 三件套已入库 <b>00_资源库/Spine/待机/</b>，可直接重渲。</div>
</div>"""

    illust_check_page = f"""
<div class="page">
  <div class="h2">主线剧情插画 <small>47 章只有 1 张，不是漏采</small></div>
  <div class="lead">键族 <b>scenariobackground(hd)_assets_eventscene_chap_&lt;章&gt;_&lt;段&gt;</b>，
    全库 <b>{illus_total:,}</b> 个键。按章拆开之后 47 章只有 <b>{illus_cnt.get(47, 0)}</b> 个 ——
    那个包拆开就是 <b>Texture2D × 1 + Sprite × 1</b>，没有第二张可挖。</div>
  <div style="display:flex;gap:5mm;align-items:flex-start">
    <div style="flex:1;text-align:center">
      <img src="{u(ILL / '47章' / 'eventscene_chap_47_01.png')}"
           style="width:100%;height:80mm;object-fit:contain;border-radius:2.5mm;background:#0f1420">
      <div style="font-size:8pt;color:#4a5261;margin-top:1.5mm">
        <b>第 47 章 · 全部 {illus_cnt.get(47, 0)} 张</b>　红发角色在停机坪上腾空</div>
    </div>
    <div style="flex:1;text-align:center">
      <img src="{u(ILL / '00_48章_总览.png')}"
           style="width:100%;height:80mm;object-fit:contain;border-radius:2.5mm;background:#f5f7fc">
      <div style="font-size:8pt;color:#4a5261;margin-top:1.5mm">
        <b>第 48 章 · 全部 {illus_cnt.get(48, 0)} 张</b>　缩略图联系表</div>
    </div>
  </div>
  <table class="tight" style="margin-top:4mm;font-size:8.6pt;line-height:1.32">
    <tr><th style="width:14%">章</th><th style="width:22%">剧情段</th>
        <th style="width:26%">剧情条目</th><th>插画（hd 键）</th></tr>
    {chap_tab}
  </table>
  <div class="note">红底那行是 47 章。<br>
    四类交叉核对，47 章全部 0 命中：<b>spineeventscenesgroup(hd)</b> 剧情 spine 场景 115 个
    （该族最晚只到 22 章）；<b>livewallpaperprefabs</b> 325 个（都是角色爆裂壁纸）；
    <b>core · dp · fd</b> 三桶 grep <b>chap_47</b> 只有 7 个键（5 个 BGM + 这 1 张插画）；
    scenariobackground 其余 40 余个子族（side / main / 各活动名 / 地区名）。<br>
    47 章的 7 段剧情共 {ml_stat.get(47, [set(), 0])[1]:,} 条文本，靠 3D 战场演出与文字推进，
    只有这 1 张关键 CG；48 章 {ml_stat.get(48, [set(), 0])[1]:,} 条文本配 {illus_cnt.get(48, 0)} 张。
    量级差得很远，但资源侧确实如此。</div>
</div>"""

    XR = ml / "07_关卡莱彻"
    # 立绘/透视 目录已统一为「序号_中文名_型号.png」，这里把型号映射过去
    TAG2FILE = {"xmg001": "01_指环_xmg001.png", "xma003": "02_海马_xma003.png",
                "xeg006": "03_太阳_xeg006.png", "xea003": "04_倒吊者_xea003.png",
                "eea002": "05_三体_eea002.png", "meg006": "06_双尾_meg006.png",
                "mea001": "07_穿刺_mea001.png", "mmg005": "08_陆蟹_mmg005.png"}
    xray_page = f"""
<div class="page">
  <div class="h2">关卡莱彻 · 外壳之下 <small>核心件只有多少能看见</small></div>
  <div class="lead">这批莱彻是 3D 模型，<b>装配件是靠骨骼挂在机体上的</b>。
    逐件统计最终可见像素后确认：有独立核心件的型号，核心（<b>cm_core_02</b>，41 顶点圆盘、
    表面四角星纹）在正常立绘里<b>只占 0.35%~0.79% 的画面</b>——就在装甲缝隙里露出那么一圈，
    不是采集漏了，也不是被完全挡住。14 个型号里只有 <b>5 个</b>有这种独立核心件，
    其余 9 个<b>核心画在贴图上</b>，没有对应几何体，再怎么渲染也不会多出一个核心。</div>
  <table class="tight" style="font-size:8pt;line-height:1.3">
    <tr><th style="width:12%">型号</th><th style="width:10%">可渲染件</th>
        <th style="width:36%">0 px 的件</th><th>核心件在立绘里的可见量</th></tr>
    {vis_tab}
  </table>
  <div class="p4" style="margin-top:4mm">{"".join(
        f'<figure><img src="{u(XR / "透视" / TAG2FILE[t])}">'
        f'<figcaption><b>{t}</b></figcaption></figure>'
        for t in ("xmg001", "xma003", "xeg006", "xea003", "eea002", "mea001", "meg006", "mmg005"))}</div>
  <div class="note">上面 8 张是<b>透视图</b>：外壳（<span class="mono">*_body</span> / <span class="mono">*_legs</span>）
    按 22% 不透明度绘制在深色底上，内部件正常绘制，被外壳挡住的核心与框架因此能看清结构。
    <b>半透明是渲染手法，不是原始材质。</b>全部 14 个型号的透视图在
    <span class="mono">07_关卡莱彻/透视/</span>，配 <span class="mono">核心件清单.tsv</span> 说明谁有核心几何件。<br>
    为什么不能还原"关卡内"姿态：模型包里那 19 个 clip 的
    <span class="mono">m_FloatCurves</span> / <span class="mono">m_PositionCurves</span> /
    <span class="mono">m_EulerCurves</span> 确实全为 0 条 —— 但<b>动画数据没被剥离，在另一个包里</b>：
    <span class="mono">spotmonsteranimation</span> 目录下有 <b>408 个</b> 动画 bundle
    （每个型号按动作拆开，如 <span class="mono">xba003_1phase_idle-raw</span>）。
    4 份关底 BOSS 的 idle 已拉回并<b>解开</b>——它走的不是肌肉通道，是 generic TRS 曲线，
    重渲结果见后面《关卡内姿态》那一页。本页 8 张仍是<b>绑定姿态</b>，两套并存便于对比。</div>
</div>"""

    xray2_page = f"""
<div class="page">
  <div class="h2">关卡莱彻 · 装配件拆解 <small>每个件单独一张，标注名称 / 顶点 / 材质 / 可见像素</small></div>
  <div class="lead">同一批模型，把每个装配件单独渲染成一格，标注该件在正常立绘里的最终可见像素。
    和立绘用同一套「远→近排序 + 朝向归一」规则，所以格子里的件和立绘上的件是同一个朝向。</div>
  <div class="p2">{"".join(
        f'<figure><img src="{u(XR / "装配件拆解" / (t + "_拆解.png"))}">'
        f'<figcaption><b>{t}</b>　{mon_stat.get(t, {}).get("n", 0)} 件'
        + (f'　核心 {mon_stat[t]["corepct"]}%' if mon_stat.get(t, {}).get("core") else "　无核心件")
        + '</figcaption></figure>'
        for t in ("xmg001", "xma003", "xeg006", "xea003", "eea002", "mea001", "meg006", "mmg005"))}</div>
  <div class="note">逐件明细（顶点 / 三角 / 可见像素 / 占画面比 / 被 alpha 砍掉的像素）落在
    <b>05_主线_47-48章/07_关卡莱彻/装配件_可见性.tsv</b>，32 行，全部由
    <span class="mono">diag_parts_visible.py</span> 实测生成。<br>
    顺带修掉了渲染器两处会吃掉细节的地方：<b>alpha 测试阈值 0.35 → 0.02</b>
    （原阈值把半透明发光层整片砍掉，xmg001 因此丢 23,476 px、meg006 腿部丢 35,878 px）；
    <b>深度比较</b>从严格大于改为留 1e-3 容差并按部件中心 z 从远到近排序
    （贴合在机体表面的贴片原本会整片消失）。</div>
</div>"""

    # ---- 2026-10-25 九修：零件判定 / 表演动画 / 爆裂细节 ----
    parts_page = f"""
<div class="page">
  <div class="h2">关底 BOSS · 零件判定 <small>哪块能单独打坏、算不算弱点</small></div>
  <div class="lead">之前只回答「核心在画面哪儿」。这一页回答另一半：
    从 <b>MonsterPartsTable</b>（715 行）读出 <b>IsPartsDamageAble</b> / <b>VisibleHp</b> /
    <b>HpRatio</b> 三个字段，再逐件渲染成透视格 —— 目标件原色、其余幽灵化，
    右下角小图红框标出它在全身的位置。</div>
  <img src="{u(ml / '07_关卡莱彻' / '零件透视' / 'xba003_1phase_零件透视.png')}"
       style="width:100%;max-height:40mm;object-fit:contain;border-radius:2.5mm">
  <div style="font-size:7.6pt;color:#6b7488;text-align:center;margin:.6mm 0 1.6mm">
    <b style="color:#26303f">安尼希利奥 · 1 阶段</b>　6 个可见件
  </div>
  <img src="{u(ml / '07_关卡莱彻' / '零件透视' / 'xba003_2phase_零件透视.png')}"
       style="width:100%;max-height:96mm;object-fit:contain;border-radius:2.5mm">
  <div class="note">47 章安尼希利奥共 <b>23 行</b>判定：主体 + <b>小矮人的箱子 I~IV</b>（HP 100）+
    <b>魔女的乌鸦 I~V</b>（HP 150）+ <b>12 个「屠杀的回路」判定盒</b> ——
    外层 <span class="mono">parts_col_801~806</span>（血量等同主体、伤害系数 0）与
    内层 <span class="mono">parts_col_901~906</span>（血量仅主体的 <b>0.07%</b>、伤害系数 1）成对出现，
    六个 Ver 号内外一一对应。<br>
    这 12 个判定盒 <b>PartsSkin 全部为空</b> —— 它们是纯碰撞体，<b>画不出来</b>，
    所以图里看不到，只能查 <b>零件透视/00_判定总表.tsv</b>（两只 BOSS 全部 25 行）。<br>
    48 章莉贝雷利奥躯体只登记 <b>2 行</b>（主体 + 1 个不可受击的 <span class="mono">parts_col_001</span>），
    <b>没有任何分部判定</b>，不套同一张模板。</div>
</div>"""

    anim_page = f"""
<div class="page">
  <div class="h2">关底 BOSS · 表演动画 <small>登场 / 转阶段 / 战败，共 12 条</small></div>
  <div class="lead">一只 BOSS 在关卡里有三类非战斗动作，之前一条都没采。这次全部从
    <b>spotmonsteranimation</b> 包导出成独立 glb，再逐帧渲染成 GIF（一条动画一个文件，
    合并会让骨骼路径对不上的 clip 静默丢通道）。</div>
  <table class="tight" style="font-size:8.8pt">
    <tr><th style="width:26%">动作</th><th style="width:37%">安尼希利奥（47 章）</th>
        <th>莉贝雷利奥躯体（48 章）</th></tr>
    <tr><td><b>登场</b></td><td>1 条（<span class="mono">12phase</span>，两阶段共用）</td>
        <td>3 条（2 阶段分两段演）</td></tr>
    <tr><td><b>转阶段（削韧）</b></td><td>start / loop / end</td><td>start / loop / end</td></tr>
    <tr><td><b>战败</b></td><td>1 条（<b>只有 2 阶段有</b>）</td><td>1 条</td></tr>
  </table>
  <div class="note">两个 BOSS 都<b>没有 1 阶段战败动画</b> —— 1 阶段血量清空是「打进 2 阶段」，
    不是当场死，所以那东西本来就不存在。<br>
    <b>化成胶体的战败</b>（<span class="mono">eba002_2phase_death_jelly</span>）导不出来：
    1255 条曲线里 431 个唯一骨骼路径，在本期两个模型包的全部四个 Avatar 里命中数都是 <b>0</b> ——
    它绑的是独立胶体骨架，本次客户端没有下发对应模型。<br>
    取景是单独算的：登场/战败动画位移很大（莉贝雷利奥战败是环状部件炸开，
    包络是绑定姿态的 29 倍），按绑定姿态定的镜头会让模型跑出画面，
    所以逐帧做蒙皮算出<b>稳健包络</b>（顶点中位数中心 + 92 分位半径）另存一份取景表。<br>
    glb 共 16 个（12 条动画 + 4 个 idle）在 <b>07_关卡莱彻/3D查看器/models/</b>，
    可用查看器的 <span class="mono">?glb=</span> 参数点名加载；GIF 在同一目录上一级的 <b>动图/</b>。</div>
  <img src="{u(ml / '07_关卡莱彻' / '动图' / '00_预览.png')}"
       style="width:100%;max-height:148mm;object-fit:contain;border-radius:2.5mm">
</div>"""

    cut_page = f"""
<div class="page">
  <div class="h2">角色爆裂特写 <small>六层 Timeline，能播的那两层已经渲成 GIF</small></div>
  <div class="lead">一次爆裂演出由六层同时驱动：
    <b>角色层</b>（Spine ×2）/ <b>背景层</b>（背景板）/ <b>卡片层</b>（爆裂卡面）/
    <b>特效层</b>（粒子）/ <b>过渡层</b>（淡入淡出）/ <b>音频层</b>。
    三套各补齐 15 / 42 / 27 张贴图，并出分层时序甘特图，另各出一条 GIF。
    注意每角色<b>只有 1 个爆裂包</b>（同角色多套时装共用），与大厅站立「每时装一份」不同。</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin-top:2mm">
    <figure style="margin:0;text-align:center">
      <img src="{u(ROOT / '07_角色爆裂特写' / 'QUEEN（真）_c870' / 'c870_00_skillcut_首帧.png')}"
           style="width:100%;height:88mm;object-fit:contain;border-radius:2mm;background:#0e1116">
      <figcaption style="font-size:7.3pt;color:#6b7488;margin-top:.7mm">
        <b style="color:#26303f">QUEEN（真）</b>　c870 · 53 帧 · 3.71 s</figcaption></figure>
    <figure style="margin:0;text-align:center">
      <img src="{u(ROOT / '07_角色爆裂特写' / '雪子_c871' / 'c871_00_skillcut_首帧.png')}"
           style="width:100%;height:88mm;object-fit:contain;border-radius:2mm;background:#0e1116">
      <figcaption style="font-size:7.3pt;color:#6b7488;margin-top:.7mm">
        <b style="color:#26303f">雪子</b>　c871 · 49 帧 · 3.43 s</figcaption></figure>
    <figure style="margin:0;text-align:center">
      <img src="{u(ROOT / '07_角色爆裂特写' / '埃癸斯_c872' / 'c872_00_skillcut_首帧.png')}"
           style="width:100%;height:88mm;object-fit:contain;border-radius:2mm;background:#0e1116">
      <figcaption style="font-size:7.3pt;color:#6b7488;margin-top:.7mm">
        <b style="color:#26303f">埃癸斯</b>　c872 · 59 帧 · 4.13 s</figcaption></figure>
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:3mm;margin-top:2.5mm">
    <figure style="margin:0;text-align:center">
      <img src="{u(ROOT / '07_角色爆裂特写' / 'QUEEN（真）_c870' / '分层时序.png')}"
           style="width:100%;height:62mm;object-fit:contain;border-radius:2mm;background:#f7f9fd">
      <figcaption style="font-size:7.3pt;color:#6b7488;margin-top:.7mm">
        <b style="color:#26303f">c870</b>　45 条分层轨道</figcaption></figure>
    <figure style="margin:0;text-align:center">
      <img src="{u(ROOT / '07_角色爆裂特写' / '雪子_c871' / '分层时序.png')}"
           style="width:100%;height:62mm;object-fit:contain;border-radius:2mm;background:#f7f9fd">
      <figcaption style="font-size:7.3pt;color:#6b7488;margin-top:.7mm">
        <b style="color:#26303f">c871</b>　64 条</figcaption></figure>
    <figure style="margin:0;text-align:center">
      <img src="{u(ROOT / '07_角色爆裂特写' / '埃癸斯_c872' / '分层时序.png')}"
           style="width:100%;height:62mm;object-fit:contain;border-radius:2mm;background:#f7f9fd">
      <figcaption style="font-size:7.3pt;color:#6b7488;margin-top:.7mm">
        <b style="color:#26303f">c872</b>　42 条</figcaption></figure>
  </div>
  <div class="note"><b>「做不到能播的动画」这句已经作废。</b>上一版只看了 Timeline 轨道就下了结论，
    回头打开骨架才发现 <span class="mono">skillcut</span> 动画一直在包里。
    但<b>单播一条只出局部</b> —— 一个爆裂骨架里有两套动画：壁纸循环（<span class="mono">idle</span> 系）
    与演出（<span class="mono">skillcut</span> 系），演出是两条
    <span class="mono">Spine Animation State Track</span> 同时驱动的，叠起来才是完整画面：
    c870 <span class="mono">skillcut_2 + skillcut_1</span>（机车场景 → 漫画卡面）、
    c871 <span class="mono">skillcut_0 + skillcut_1</span>（持扇起舞 → 展翼）、
    c872 <span class="mono">bg_skillcut_1 + skillcut_1</span>（角色后撤 → 晶体炸裂）。
    第一版把 <span class="mono">idle</span> 当卡面层叠进 c870，渲出来 4 秒全是一张静止卡面 ——
    壁纸那条不参与演出。<br>
    仍然做不到的三件：<b>音频 0 条</b>（PCM 剥离到包外
    <span class="mono">.resource</span>，而 catalog 里该后缀条目数为 0）；
    <b>粒子参数不可还原</b>（Timeline 只记「哪个粒子在哪段时间启用」，发射率/速度曲线不在包里）；
    <b>后处理不可还原</b>（包内无 shader）。所以 GIF 是「角色层 + 背景/卡面层」两层合成，不含粒子与泛光。
    另：c870 头 0.65 s、c871 头 0.95 s 是卡面入场的极端缩放（渲出来是一条白线／白方块），
    已按时间裁掉，起点为 <span class="mono">0.750 s</span> / <span class="mono">1.050 s</span>。</div>
</div>"""

    # ---- 关卡内 idle 姿态 ----
    IDLE_FILES = ["13_安尼希利奥_xba003_1阶段.png", "13_安尼希利奥_xba003_2阶段.png",
                  "14_莉贝雷利奥躯体_eba002_1阶段.png", "14_莉贝雷利奥躯体_eba002_2阶段.png"]
    IDLE_CAP = ["47 章 <b>安尼希利奥</b> 1 阶段", "47 章 <b>安尼希利奥</b> 2 阶段",
                "48 章 <b>莉贝雷利奥躯体</b> 1 阶段", "48 章 <b>莉贝雷利奥躯体</b> 2 阶段"]
    pose_page = f"""
<div class="page">
  <div class="h2">关底 BOSS · 关卡内姿态 <small>idle 动画解出来了，走的是 generic TRS 曲线</small></div>
  <div class="lead">前几版一直写「要先还原 Humanoid 肌肉空间」，实测这句对这批资源<b>不成立</b>：
    <span class="mono">m_IndexArray</span> 的 200 项<b>全是 -1</b>（200 条肌肉 DoF 全取常量 0）、
    <span class="mono">m_ValueArrayReferencePose</span> 长度为 <b>0</b>、Avatar 的
    <span class="mono">m_Human</span> 长度也是 <b>0</b>。真正在动的是
    <span class="mono">m_ClipBindingConstant.genericBindings</span> 里的 <b>278~873 条 generic 曲线</b>
    （pos / rot / scale），本来就是骨骼 local TRS，不需要过肌肉映射。</div>
  <div class="p4">{"".join(
        f'<figure><img src="{u(XR / "立绘_idle" / fn)}"><figcaption>{cap}</figcaption></figure>'
        for fn, cap in zip(IDLE_FILES, IDLE_CAP))}</div>
  <figure style="margin:3mm 0 0"><img src="{u(XR / "莉贝雷利奥躯体_1阶段_idle对照.png")}"
    style="width:100%;height:54mm;object-fit:contain;border-radius:2mm;background:#f7f9fd">
    <figcaption style="font-size:7.3pt;color:#6b7488;margin-top:.7mm">48 章 1 阶段：左一为绑定姿态，后三张为 idle 第 0 / 51 / 101 帧。
      下沿 6 条缆绳在绑定姿态里是<b>笔直</b>的，idle 里是自然下垂的弧线</figcaption></figure>
  <div class="note">展开方式（实测反推）：<span class="mono">genericBindings[i]</span> 给出
    <b>(path hash, attribute)</b>，attribute 1=pos(3 float)、2=rot(4 float)、3=scale(3 float)；
    <span class="mono">m_ValueArrayDelta</span> 按曲线顺序逐分量平铺，长度正好
    103×3 + 103×4 + 72×3 = <b>937</b>，每项的 <span class="mono">m_Start</span> / <span class="mono">m_Stop</span>
    就是该 float 的首帧值 / 末帧值；用这组双值去匹配
    <span class="mono">m_DenseClip.m_SampleArray</span> 的列即可唯一定位；
    <span class="mono">Avatar.m_TOS</span> 的 hash 与 <span class="mono">path</span> 同一套，可反查骨骼名。<br>
    校验：四份 idle 的旋转曲线按四元数取出后 <b>|q| 全部 = 1.000</b>（103/103、296/296、317/317、290/290）。
    首帧恰好等于绑定姿态——因为 <span class="mono">m_Start</span> 就是首帧值、动画从绑定姿态起步——
    所以取帧一律用中间帧，不用第 0 帧。<br>
    <b>47 章 2 阶段仍然「碎」</b>：175 根骨骼在动，但动的是手臂与弹匣（最大 39.97°），
    外围碎块几乎不平移。它就是这个敞甲形态，不是靠 idle 合拢——这一条推翻了上一版的推断。<br>
    <b>六修追加</b>：上面这些结论都是在「阶段归属判对了」的前提下才成立，而当时判错了
    （见下一页）。两个 2 阶段的图一个是「少了底座」、一个「画成了另一阶段」，
    所以「碎」的观感里混着一部分取件错误。取件修正后，2 阶段的层次
    （人形 / 崩甲团 / 底座）才正常，见下一页的 3D 版本。</div>
</div>"""

    viewer_page = f"""
<div class="page">
  <div class="h2">关底 BOSS · 3D 查看器 <small>真正的骨骼动画，不是「拖动旋转」</small></div>
  <div class="lead">要求是「像别人那样让它动起来，因为还涉及到特效表现，那样更完整」。
    先把参考站 <span class="mono">nkas.pages.dev</span> 的 glb 拉下来拆开：
    <b>1 个 node、<span class="mono">skins=0</span>、<span class="mono">animations=0</span></b> ——
    它是把蒙皮烘成<b>静态网格</b>，网页里的「动」只是
    <span class="mono">OrbitControls</span> 让用户自己拖，模型本身一帧都不动。<br>
    本轮直接导出<b>带骨骼 + idle 动画</b>的 glTF，所以动画是真的在播；
    同时按材质做了 <span class="mono">alphaMode=MASK, alphaCutoff=0.5</span>，
    半透明件不会互相叠出黑边（参考站也是这么处理的）。<br>
    <b>在线版（已部署 GitHub Pages，手机浏览器直接能开）：</b>
    <a class="url" href="{VIEWER_URL}">{VIEWER_URL}</a>
    —— 打开就是 3D 查看器，左侧选模型、下方选动画；数据全部同源打包，
    不依赖任何第三方 CDN，断网也能用（把仓库 zip 下来双击 <span class="mono">index.html</span> 即可）。</div>
  <div class="p4">{"".join(
        f'<figure><img src="{u(XR / "3D查看器" / "截图" / fn)}"><figcaption>{cap}</figcaption></figure>'
        for fn, cap in zip(
            ["查看器_安尼希利奥_1阶段.png", "查看器_安尼希利奥_2阶段.png",
             "查看器_莉贝雷利奥_1阶段.png", "查看器_莉贝雷利奥_2阶段.png"],
            ["47 章 1 阶段", "47 章 2 阶段", "48 章 1 阶段", "48 章 2 阶段"]))}</div>
  <table class="tight" style="font-size:8pt;line-height:1.35">
    <tr><th style="width:30%">glb 文件</th><th>大小</th><th>部件</th><th>蒙皮骨骼</th><th>内置动画</th></tr>
    <tr><td class="mono">xba003_1phase.glb</td><td>1.81 MB</td><td>5</td><td>98</td><td>4.77 s / 144 帧</td></tr>
    <tr><td class="mono">xba003_2phase.glb</td><td>5.39 MB</td><td>11</td><td>275</td><td>2.70 s / 82 帧</td></tr>
    <tr><td class="mono">eba002_1phase.glb</td><td>2.92 MB</td><td>1</td><td>334</td><td>3.37 s / 102 帧</td></tr>
    <tr><td class="mono">eba002_2phase.glb</td><td>3.22 MB</td><td>2</td><td>267</td><td>3.37 s / 102 帧</td></tr>
  </table>
  <div class="note"><b>两个 2 阶段的问题出在「属于哪个阶段」判错了。</b>
    包里 1 阶段 / 2 阶段是两套并列的变体根（<span class="mono">*_1phase_var</span> /
    <span class="mono">*_2phase_var</span>），都 <span class="mono">activeInHierarchy=True</span>。
    旧代码取「最近一个名字带 1phase/2phase 的节点」当归属，于是
    <span class="mono">xba003_1phase_magiccarpet_skin</span>（名字带 1phase、实际挂在
    <span class="mono">xbga03_2phase_var</span> 下）被判成 1 阶段，2 阶段图<b>少了下方底座</b>；
    48 章更严重，2 阶段图画的其实是 1 阶段那 <b>20,308</b> 个顶点，2 阶段自己的
    <b>10,066</b> 个顶点一个都没画。改成按 <span class="mono">_var</span> 变体根判定后两边才正常，
    并用参考站的 glb 反查过：47 章正好 11 个 primitive、48 章正好 2 个，顶点数逐项吻合。<br>
    <b>导出三个坑</b>（都会让结果「看着像碎的」）：① glTF 的
    <span class="mono">inverseBindMatrices</span> 就是 Unity 的 <span class="mono">m_BindPose</span> 本身，
    不要再求一次逆，否则 22×27×15 的模型会变成 69×102×89、碎片满天飞；
    ② 朝向变换必须对顶点 <span class="mono">A·V</span>、节点 <span class="mono">A W A⁻¹</span>、
    IBM <span class="mono">A·bindPose·A</span> 同步做，漏一项就是整片死黑（看到内表面）；
    ③ accessor 的 <span class="mono">count</span> 要用 <span class="mono">size÷分量数</span>，
    别用 <span class="mono">len()</span>，否则 Three.js 报 <span class="mono">Invalid typed array length</span> 白屏。<br>
    <b>线上版另修了一处取景。</b>初始版本把「整段动画的并集」当取景框，结果战败动画
    （环状部件炸飞到很远）把框心整个拖走，模型在画面里缩成一个点；
    改用<b>绑定姿态的真实包围盒</b>定大小、<b>动画首帧的位置</b>定中心后正常。
    已按 idle / 登场 / 战败三个视角在线上逐张截图复验，三种动画都完整在框内。</div>
</div>"""

    html = f"""<!DOCTYPE html><meta charset="utf-8"><style>{CSS}</style>

<div class="page"><div class="cover">
  <div class="kicker">NIKKE · INTERNATIONAL · UPDATE ARCHIVE</div>
  <h1>2026 年 8 月 13 日<br>国际服更新内容一览</h1>
  <div class="sub">Persona 系列联动 · 主线 47/48 章 · 三名新角色 · 五套新皮肤</div>
  <div class="badges">
    <span class="badge">2 章主线</span><span class="badge">3 名角色</span><span class="badge">5 套皮肤</span>
    <span class="badge">1 个联动活动</span><span class="badge">8 张剧情插画</span>
  </div>
  <div class="meta">
    收录：主线章节与剧情 · 角色立绘与技能 · 皮肤 · 活动插画与奖励 · 战斗场景还原<br>
    整理日期 2026-10-25　　对应游戏版本 152.8.7
  </div>
  <div class="heroes">{heroes}</div>
</div></div>

<div class="page">
  <div class="h2">本期都有什么 <small>一眼看完</small></div>
  <div class="lead">这一期主线推进第 47、48 两章，同时是 Persona 系列联动「PERSONA ON FRONTLINE」，上线 3 名角色、5 套皮肤与 1 个剧情活动。</div>
  <table>
    <tr><th style="width:22%">类别</th><th>内容</th></tr>
    <tr><td><b>主线</b></td><td>第 47 章「开战」· 第 48 章「重生」—— 普通关各 46 关（困难各 46 关），战力门槛 806,900 → 875,600</td></tr>
    <tr><td><b>新角色</b></td><td>QUEEN（真）· 雪子 · 埃癸斯（埃癸斯为 SR，无独立卡池，随活动赠送）</td></tr>
    <tr><td><b>新皮肤</b></td><td>秀尽学园学生会长 · 女王睡衣 · 天城屋旅馆和服 · 冬日雅居 · 圣洁怪盗</td></tr>
    <tr><td><b>联动活动</b></td><td>PERSONA ON FRONTLINE —— 通关主线第 48 章后开放</td></tr>
    <tr><td><b>卡池横幅</b></td><td>5 组（2 个角色卡池 · 1 个时装卡池 · 2 个活动 PASS）</td></tr>
    <tr><td><b>剧情插画</b></td><td>8 张，2048×2048 高清原图</td></tr>
  </table>
  <div style="margin-top:8mm" class="grid3">{overview}</div>
  <div class="note">※ 同一角色的不同服装按「皮肤」单独收录，与角色卡分开存放。</div>
</div>

{"".join(page_char(c) + page_skill_detail(c) for c in CHARS)}

{page_skins(SKINS[0:2], 1, len(SKINS))}
{page_skins(SKINS[2:4], 3, len(SKINS))}
{page_skins(SKINS[4:5], 5, len(SKINS))}

<div class="page">
  <div class="h2">活动 · PERSONA ON FRONTLINE</div>
  <div class="lead">无尽跑酷玩法，通关主线第 48 章后解锁。剧情插画共 8 张，全部为 2048×2048 高清原图。</div>
  <img src="{u(act_banner)}" style="width:100%;border-radius:2.5mm;margin-bottom:4mm">
  <div style="display:flex;gap:6mm;align-items:flex-start">
    <div style="flex:0 0 38%">
      <img src="{u(illus[0])}" style="width:100%;height:86mm;object-fit:contain;border-radius:2.5mm;background:#0f1420">
    </div>
    <div style="flex:1">
      <table style="font-size:8.8pt;line-height:1.35">
        <tr><th style="width:30%">项目</th><th>内容</th></tr>
        <tr><td>活动名称</td><td>PERSONA ON FRONTLINE</td></tr>
        <tr><td>活动玩法</td><td>无尽跑酷</td></tr>
        <tr><td>联动作品</td><td>Persona 3 / 4 / 5</td></tr>
        <tr><td>开放条件</td><td>通关主线第 48 章</td></tr>
        <tr><td>出场角色</td><td>QUEEN（真）、雪子、埃癸斯</td></tr>
        <tr><td>剧情插画</td><td>8 张（本包为高清版）</td></tr>
        <tr><td>剧情对话文本</td><td><b>{int(c9_n):,} 条</b>，源自 <span class="mono">Locale_SubScenario</span>（见前文 CE009 更正页）</td></tr>
        <tr><td>非剧情文本</td><td>{n_c9} 条：场景告示牌 21 · P5R 小游戏 UI 91 · 状态 2（<b>不是</b>剧情对话）</td></tr>
      </table>
    </div>
  </div>
  <div class="note">活动内另有道具、增益、技能图标与教学图共 {len(items)+len(tuts)} 张，见后续页面。<br>
    <b>上一版这里写「CE009 没有剧情对话」是错的</b> —— ce009 属多章式活动，正文在
    <span class="mono">Locale_SubScenario</span>，共 <b>{int(c9_n):,} 条</b>，已在前面「CE009 更正」页给出抽样与全文位置。
    本页只讲<b>非剧情文本</b>：<span class="mono">Locale_Event</span> 里的 {n_c9} 条全是活动 UI / 告示牌 / 场地状态提示，
    它们<b>不是</b>剧情对话，单独成表。
    {n_c9} 条见包内 <b>03_活动/PERSONA ON FRONTLINE（ce009）/非剧情文本_UI与告示牌/</b>。</div>
  <table class="tight" style="margin-top:3mm;font-size:8.4pt;line-height:1.3">
    <tr><th style="width:22%">这 {n_c9} 条文本的分类</th><th style="width:10%">条数</th>
        <th>举例（简中原文）</th></tr>
    {c9_tab}
  </table>
</div>

{illus_pages}

<div class="page">
  <div class="h2">活动奖励 · 大厅动画 <small>LiveWallpaper 97</small></div>
  <div class="lead">本期活动能拿到的唯一「带画面」的奖励 —— 大厅动态壁纸 PERSONA ON FRONTLINE。
    画面取自客户端 spine/events/eventscene_ce009_01，奖励图标取自 icons-livewallpaper(hd)。</div>
  <div style="display:flex;gap:7mm;align-items:flex-start">
    <div style="flex:0 0 58%"><img src="{u(act / '大厅动画' / '大厅动画_主图_1000x1000.png')}"
      style="width:100%;border-radius:2.5mm;background:#0f1420"></div>
    <div style="flex:1;text-align:center">
      <img src="{u(act / '大厅动画' / '大厅动画_奖励图标_256x512.png')}"
           style="width:52mm;border-radius:2.5mm;margin:0 auto">
      <div class="note" style="margin-top:2mm">奖励图标 256×512</div>
    </div>
  </div>
  <table style="margin-top:5mm;font-size:9pt">
    <tr><th style="width:20%">项目</th><th>值</th></tr>
    <tr><td>奖励名</td><td>PERSONA ON FRONTLINE</td></tr>
    <tr><td>类型</td><td>动态壁纸（LiveWallpaper）</td></tr>
    <tr><td>ID</td><td>97</td></tr>
    <tr><td>资源</td><td class="mono">livewallpaper/EventScene_ce009_01</td></tr>
    <tr><td>获取</td><td>「PERSONA ON FRONTLINE」活动内获得</td></tr>
    <tr><td>主图尺寸</td><td>1000×1000（图集页 1024，有效画面 1000）</td></tr>
  </table>
  <div class="note">包内另有 128×128 小图标；主图与两张图标都在
    <b>03_活动/PERSONA ON FRONTLINE（ce009）/大厅动画/</b>，
    活动收益表单 <b>6_其他产出</b> 页也已把这些图一并附上。</div>
</div>

<div class="page">
  <div class="h2">活动道具与图标 <small>{len(items)} 张</small></div>
  <div class="lead">活动内使用的道具、增益与技能图标，均为 256×256。</div>
  <div class="icons">{icon_figs}</div>
  <div class="note">从左上到右下依次为：活动道具（金币、炸弹、医疗包、道具箱、特殊卡）、
    增益图标、三名联动角色的技能图标、敌人立绘。</div>
</div>

{tut_pages}

<div class="page">
  <div class="h2">卡池与活动横幅 <small>{len(banners)} 组</small></div>
  <div class="lead">游戏内活动列表使用的横幅，1108×368，另附小尺寸版本。</div>
  {banner_figs}
</div>

<div class="page">
  <div class="h2">本期主线 · 第 47、48 章</div>
  <div class="lead">官方预告图右下角直接印着 <b>47:48 NEW CHAPTER UPDATE</b> —— 两章同期开放，共推进 98 关。</div>
  {trail_figs.replace("width:100%", "width:auto;max-height:30mm;display:block;margin:0 auto")}
  <table style="margin-top:2mm;font-size:9pt;line-height:1.4">
    <tr><th style="width:26%">项目</th><th style="width:37%">第 47 章</th><th>第 48 章</th></tr>
    <tr><td><b>章节名</b></td><td>{chap["47"]["cn"]} / {chap["47"]["en"]}</td><td>{chap["48"]["cn"]} / {chap["48"]["en"]}</td></tr>
    <tr><td>普通关卡</td><td>{chap["47"]["n"]} 关</td><td>{chap["48"]["n"]} 关</td></tr>
    <tr><td>困难关卡</td><td>{chap["47"]["nh"]} 关</td><td>{chap["48"]["nh"]} 关</td></tr>
    <tr><td>战力门槛</td><td>{chap["47"]["bp"]}</td><td>{chap["48"]["bp"]}</td></tr>
    <tr><td>敌人等级</td><td>{chap["47"]["lv"]}</td><td>{chap["48"]["lv"]}</td></tr>
    <tr><td>隐藏收集品</td><td>{chap["47"]["items"]} 件</td><td>{chap["48"]["items"]} 件</td></tr>
  </table>
  <div class="note">战力门槛逐章紧接：46 章收尾在 806,900 正好是 47 章起点，47 章收尾 824,500 又是 48 章起点。</div>
  <h3 style="margin:3mm 0 2mm;font-size:12.5pt">剧情节点 <small style="font-weight:400;color:#7a8496;font-size:9pt">每 5~9 关一个</small></h3>
  <table style="font-size:8.4pt;line-height:1.35">
    <tr><th style="width:12%">任务</th><th style="width:22%">条件</th><th>剧情内容</th></tr>
    {"".join(f'<tr><td>{r[0]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>' for r in q47)}
    {"".join(f'<tr><td>{r[0]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>' for r in q48)}
  </table>
</div>

<div class="page">
  <div class="h2">第 47 章地图 <small>开战 · 从客户端还原</small></div>
  <div class="lead">不是示意图。地图取自客户端地形与图集，点位坐标是游戏内真实世界坐标，叠上去天生对齐。</div>
  <img src="{u(ml / '03_地图与点位' / '大地图' / '地图_47章.png')}" style="width:100%;max-height:168mm;object-fit:contain;border-radius:2.5mm">
  <table style="margin-top:2mm;font-size:9pt;line-height:1.4">
    <tr><th style="width:24%">项目</th><th>值</th></tr>
    <tr><td>世界范围</td><td>X −95.2 ~ 96.4 ／ Z −84.3 ~ 84.3</td></tr>
    <tr><td>点位匹配</td><td><b>69 / 69</b>，零缺失（46 关 · 14 宝箱 · 门 2 · 传送门 2 · 触发器 2 · 出生点 1）</td></tr>
    <tr><td>第一关坐标</td><td>{c47_first}</td></tr>
  </table>
  <div class="note">圆点里的数字是关卡序号。坐标单位是游戏世界单位，X/Z 是地面平面，Y 是高度。</div>
</div>

<div class="page">
  <div class="h2">第 48 章地图 <small>重生 · 从客户端还原</small></div>
  <div class="lead">同一套坐标系，与 47 章无缝衔接。地图边界更靠外，主战场在东南侧的工业区。</div>
  <img src="{u(ml / '03_地图与点位' / '大地图' / '地图_48章.png')}" style="width:100%;max-height:168mm;object-fit:contain;border-radius:2.5mm">
  <table style="margin-top:2mm;font-size:9pt;line-height:1.4">
    <tr><th style="width:24%">项目</th><th>值</th></tr>
    <tr><td>世界范围</td><td>X −99.3 ~ 99.3 ／ Z −92.5 ~ 92.5</td></tr>
    <tr><td>点位匹配</td><td><b>66 / 66</b>，零缺失（46 关 · 13 宝箱 · 门 1 · 传送门 2 · 触发器 1 · 出生点 1 · 镜头点 1）</td></tr>
    <tr><td>第一关坐标</td><td>{c48_first}</td></tr>
  </table>
  <div class="note">完整坐标见包内 <b>03_地图与点位/06·07_大地图点位_*.tsv</b>（全部实体）与 <b>12·13_关卡坐标_*.tsv</b>（46 关）。</div>
</div>

{battle_pages}

<div class="page">
  <div class="h2">战斗场景 · 能对上的是什么 <small>数据边界</small></div>
  <div class="lead">三套背景取自 <b>spotbackground(hd)</b> 包里的 sbg_cityforest_001 / 002 / 003，
    下面这张表是各自的装配规模。章节与背景的对应关系，客户端没有可用的键，这里如实说明。</div>
  <table style="font-size:9pt">
    <tr><th style="width:26%">战场资源</th><th style="width:12%">物体</th><th style="width:14%">三角面</th><th>世界包围盒（X Y Z）</th></tr>
    {battle_rows}
  </table>
  <h3 style="margin:5mm 0 2mm;font-size:12.5pt">能证实的</h3>
  <table style="font-size:9pt;line-height:1.45">
    <tr><td style="width:26%">区域归属</td><td>CampaignChapterTable 里第 47 章 FieldId = <b>fcbg_cityforest_010</b>、
      第 48 章 = <b>fcbg_cityforest_011</b> —— 两章都发生在 cityforest（城市林地）区域</td></tr>
    <tr><td>可用背景</td><td>全客户端 <b>spotbackground(hd)</b> 共 <b>174</b> 个包，其中 cityforest 系列 <b>33 个</b>：
      地面街区 3（就是前面还原的 001/002/003）、空中 1、地下 10、地下·水晶区 8、地下·电梯区 8、
      水晶区 1、eba001 专属 1、eba002 / 轨道电梯专属 1。<b>本机设备缓存只落到了地面那 3 个包</b>，
      其余 30 个没下发到设备，所以没有还原 —— 不是只有三种。完整清单见
      <b>06_战斗场景还原/战场背景_键清单.tsv</b></td></tr>
    <tr><td>活动时间</td><td>FieldItemTable 55033101 起 111 条 ObtainLocation=10033 的道具，
      SpawnTime 2026-08-12T20:00:00Z → DespawnTime 2026-09-09T19:59:59Z</td></tr>
  </table>
  <h3 style="margin:5mm 0 2mm;font-size:12.5pt">不能证实的</h3>
  <div style="font-size:9pt;line-height:1.55;color:#4a5261">
    客户端里没有任何一张表把「某一关」直接指向「某一套 sbg 背景」：
    CampaignStageTable 没有背景字段，全客户端唯一带 <b>Bg</b> 字段的是 TowerTable（爬塔用）；
    spotbackground(hd) 的 174 个键也不带章节标签。所以 <b>哪个关卡用 001、哪个用 003，无法从文件里确定</b>，
    只能进游戏逐关对照。本包按资源自身的编号交付，不猜。
  </div>
  <div class="note">还原口径：几何按 <b>MeshHandler</b> 解压压缩网格后取全部 submesh；
    贴图取 RuntimeTextureInstanceSetter._sprite 或材质贴图路径；这批美术的网格不带 UV 通道，
    按板件包围盒做平面投影重建（板件比与贴图比一致，例：sbg_cityforest_sn_building02 为 5.75×7.33，贴图 402×512）；
    相机取 camera_position 自身 Transform 的世界矩阵三列，不拿 aim 反推；
    天空取 sbg_*_skybox_side / _upper / _under 三张按方向向量球面采样。</div>
</div>

{stage_pages}

{boss_page}

{monster_pages}
{boss2_page}
{bgm_page}

{xray_page}

{xray2_page}

{parts_page}

{anim_page}

{cut_page}

{pose_page}

{viewer_page}

{illust_check_page}

{event_story_page}

{lobby_page}

<div class="page">
  <div class="h2">本包收录了什么</div>
  <table class="tight" style="font-size:8.1pt;line-height:1.4">
    <tr><th style="width:32%">类别</th><th style="width:12%">数量</th><th>说明</th></tr>
    <tr><td>主线 · 章节与剧情</td><td>2 章</td><td>章名 / 98 关 / 收集品 39 件 / 剧情全文 3 语言</td></tr>
    <tr><td>主线 · 章节预告图</td><td>2</td><td>官方 47:48 新章预告</td></tr>
    <tr><td>主线 · 章节地图</td><td>4</td><td>两章各一张带点位、一张纯净底图；附 92 条关卡坐标</td></tr>
    <tr><td>主线 · 战斗场景还原</td><td>18</td><td>3 套战场 × 5 个站位各一张 + 3 张五站位拼图</td></tr>
    <tr><td>角色 · 全身立绘</td><td>3</td><td>每名角色只贴 1 张，取目录里分辨率最高的那张（小人立绘.png，1800 高）</td></tr>
    <tr><td>角色 · 技能图标</td><td>9</td><td>128×128，按「爆裂技能 / 技能1 / 技能2」分文件</td></tr>
    <tr><td>角色 · 半身像</td><td>3</td><td>128×128，适合做头像、介绍图</td></tr>
    <tr><td>角色 · 立绘其他规格</td><td>6</td><td>立绘.png（缩略）/ 立绘_高清.png（1024 图集页）—— 不贴图，只列尺寸</td></tr>
    <tr><td>皮肤 · 全身立绘</td><td>5</td><td>同样只贴 1 张最高分辨率版本</td></tr>
    <tr><td>皮肤 · 立绘其他规格</td><td>15</td><td>立绘 / 立绘_高清 / 半身像，不贴图，只列尺寸</td></tr>
    <tr><td>活动 · 剧情插画</td><td>{len(illus)}</td><td>2048×2048 高清</td></tr>
    <tr><td>活动 · 道具与图标</td><td>{len(items)}</td><td>256×256</td></tr>
    <tr><td>活动 · 教学图</td><td>{len(tuts)}</td><td>512×400</td></tr>
    <tr><td>卡池与活动横幅</td><td>{len(banners)}</td><td>1108×368，另附小尺寸</td></tr>
    <tr><td>活动 · 官方横幅</td><td>1</td><td>EVENT_BANNER_CE009，1108×368</td></tr>
    <tr><td>活动 · 大厅动画</td><td>3</td><td>动态壁纸 LiveWallpaper 97：主图 1000×1000 + 奖励图标 256×512 / 128×128</td></tr>
    <tr><td>主线 · 关卡信息</td><td>196</td><td>两章全量关卡：编号 / 类型 / 等级 / 战力 / 莱彻 / 大地图与坐标；另附关底 BOSS 6 条</td></tr>
    <tr><td>主线 · 关卡莱彻</td><td>8</td><td>8 种莱彻立绘（3D 绑定姿态正交渲染）+ 总览图 + 技能 72 条（官方描述原文）</td></tr>
    <tr><td>主线 · 莱彻透视 / 拆解</td><td>16</td><td>8 张透视图 + 8 张装配件拆解图，另有逐件可见性表 32 行</td></tr>
    <tr><td>主线 · BOSS 关卡内姿态</td><td>4</td><td>4 份 idle 解出的骨骼姿态重渲 + 4 张「绑定 vs idle」对照图</td></tr>
    <tr><td>主线 · BOSS 3D 查看器</td><td>16</td><td>4 个 idle + 12 条表演动画的 glTF（另附取景表 framing.js）+ Three.js 查看器，<b>另有在线版</b> <a href="{VIEWER_URL}">theifxzx666-blip.github.io/Nikke_Lecher_3D</a></td></tr>
    <tr><td>主线 · BOSS 零件判定</td><td>25 行</td><td>两只关底 BOSS 全部判定行（Type / 血量比 / 可受击 / 有血条）+ 4 张零件透视图</td></tr>
    <tr><td>主线 · BOSS 表演动画</td><td>12 条</td><td>登场 / 转阶段（start·loop·end）/ 战败，一条动画一个 GIF + 一个 glb</td></tr>
    <tr><td>主线 · 剧情插画</td><td>40</td><td>47 章 1 张 + 48 章 39 张，2048×2048 原图</td></tr>
    <tr><td>主线 · 活动剧情文本</td><td>{n_act} 部</td><td>{n_act_lines:,} 条 × 5 语（简中 / 繁中 / 日文 / 英文 / 韩文），共 {n_act*5} 个文本；Main / Sub 两表合并</td></tr>
    <tr><td>活动 · CE009 剧情</td><td>{int(c9_n):,}</td><td>第 1~2 章 × 6 段 × e/s 双轨 + 序章/幕间/尾声 + 气泡 30 组 + NPC 11 组 + 迷你游戏开场 41 条，5 语</td></tr>
    <tr><td>活动 · CE009 非剧情文本</td><td>{n_c9}</td><td>场景告示牌 21 + P5R 小游戏 UI 91 + 状态 2（<b>不是</b>剧情对话）</td></tr>
    <tr><td>角色 · 大厅站立动画</td><td>{n_lob} 套</td><td>{n_lob_anim} 条（idle / action），每套 GIF + 首帧 PNG；长边 1000 / 15 fps</td></tr>
    <tr><td>主线 · BGM</td><td>22</td><td>11 条曲目，每条 .wav（原样 44.1 kHz/16 bit）+ .mp3（256 kbps）+ 曲目表</td></tr>
    <tr><td>角色 · 台词与配音</td><td>126</td><td>3 角色 × 42 条日配 wav + 五语台词原文（国际服只下发日配）</td></tr>
    <tr><td>角色 · 爆裂特写动画</td><td>3</td><td>两条 Spine 动画叠层渲染的 GIF（15 fps / 长边 1000）+ 首帧 PNG + 分层时序表 + 特效贴图 15 / 42 / 27 张</td></tr>
  </table>
  <div class="note">
    所有图片均为原图直出，未做压缩或重绘。角色与皮肤页每项只嵌 1 张立绘，
    取的是该目录里裁掉透明边后像素面积最大的那张（统一是 <b>小人立绘.png</b>，1800 高、全透明底）。
    <b>立绘_高清.png 看起来叫"高清"，其实是 1024×1024 的图集页，人物只占中间一块</b>，
    所以不做主图；它与 立绘.png、半身像.png 一样只在页脚列文件名与尺寸，需要时去资源目录取。
  </div>
</div>
"""
    if BRIEF:
        html = apply_brief(html)
    HTML_OUT.write_text(html, encoding="utf-8")
    if "--html-only" in sys.argv:      # 调版式时只出 HTML，便于逐页截图核对
        print("html only ->", HTML_OUT)
        return
    # 先写到临时文件再替换：目标 PDF 被阅读器占用时 Chrome 会静默失败，
    # 脚本却读到旧文件的大小，看着像"生成成功"。
    TMP_PDF = PDF_OUT.with_name("_报告_简版.pdf" if BRIEF else "_报告.pdf")
    if TMP_PDF.exists():
        TMP_PDF.unlink()
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           "--allow-file-access-from-files", "--virtual-time-budget=25000",
           f"--print-to-pdf={TMP_PDF}", HTML_OUT.as_uri()]
    p = subprocess.run(cmd, capture_output=True, timeout=600)
    if not TMP_PDF.exists():
        print("FAIL rc", p.returncode)
        print((p.stderr or b"").decode("utf-8", "replace")[-800:])
        return
    print("生成", round(TMP_PDF.stat().st_size / 1048576, 2), "MB")
    try:
        os.replace(TMP_PDF, PDF_OUT)
        print("已写入", PDF_OUT)
    except OSError as e:
        print(f"!! 目标 PDF 被占用（{e.strerror}）——暂存为 {TMP_PDF.name}，"
              f"关闭阅读器后再改名即可")


if __name__ == "__main__":
    main()
