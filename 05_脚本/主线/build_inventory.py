# -*- coding: utf-8 -*-
"""build_inventory.py —— 从一期交付目录生成三张采集明细表。

输出（写到 <期目录>/../01_采集明细/ 或 --out 指定）：
  采集明细_<期次>.csv    素材级溯源表，一行一个交付素材（含来源键/来源包）
  全量文件_<期次>.csv    全量文件表，一行一个文件（用于「行数=文件数」验收）
  采集明细_总表.csv       跨期汇总，分类 × 类型（所有对外数字的唯一出处）

用法：
  python build_inventory.py --root <期目录> [--out <输出目录>] [--write]
  默认只报告（dry-run），--write 才落盘。

设计要点（踩过的坑，改脚本前先读）：
  E-22  素材清单 ≠ 全量文件清单。前者只登记二进制素材，不含 txt/tsv/md。
        所以这里是两张表，不是一张扩字段。
  E-03  所有对外数字从「总表」取，其他文档引用不复算。
  来源键一律从「既有清单 join」或「文件名正则」读出，不猜。
  来源包从全局 bundle 索引按 5 条固定规则匹配，命中不上就留空，不编。
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re, sys
from collections import Counter, defaultdict

# ---- 环境常量（跨期不变）------------------------------------------------
BASE_KEYS = r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点\_干跑_20261025\00_基线_键清单"
CLIENT_VER = "152.8.7"          # 每期改：见 00_规范/技术选型.md 第零节
SKIP_DIRS = {"_构建"}            # 中间件不算交付

# 键 → 包名前缀规则（_probe_key2bundle.py 已验证 5/5 全命中）
BUNDLE_RULES = [
    ("立绘_高清", r"^icons-char-full\(hd\)_assets_{k}_[0-9a-f]{{32}}\.bundle$"),
    ("立绘", r"^icons-char-full\(sd\)_assets_{k}_[0-9a-f]{{32}}\.bundle$"),
    ("半身像", r"^icons-char-mi\(hd\)_assets_mi_{k}_s_[0-9a-f]{{32}}\.bundle$"),
    ("小人立绘", r"^sdcharacters_assets_{k}_var_[0-9a-f]{{32}}\.bundle$"),
    ("爆裂", r"^spotskillcutscene_assets_{k}_cut_scene_[0-9a-f]{{32}}\.bundle$"),
    # 大厅站立：spine/standing/<cXXX>/<NN>_hd_<hash>（见 pull_spine.py 第 5 行注释，实测命中 9/9）
    ("大厅动画", r"^spinestandingcharactergroup\(hd\)_assets_spine/standing/{c}/{nn}_hd_[0-9a-f]{{32}}\.bundle$"),
    # BOSS 模型：spotmonster(hd)_assets_spotmonster/<型号>_<dmtr|hsta>_<hash>，一个型号一份
    ("BOSS模型", r"^spotmonster\(hd\)_assets_spotmonster/{p}_[a-z]+_[0-9a-f]{{32}}\.bundle$"),
    # BOSS 表演动画：spotmonsteranimation_assets_s.../<型号>_<阶段>_<动作>[-raw]_<hash>
    ("BOSS动画", r"^spotmonsteranimation_assets_spotmonsteranimation/{k}(?:[-_][a-z0-9\-]+)?-raw_[0-9a-f]{{32}}\.bundle$"),
]
# 清单的 kind → 上面规则的 label。素材清单用「角色立绘SI」这种业务名，规则用产物名，必须显式映射
KIND2RULE = {
    "角色立绘HD": "立绘_高清",
    "角色立绘": "立绘",
    "角色立绘SI": "半身像",
    "Spine小人立绘": "小人立绘",
    "爆裂动画GIF": "爆裂",
    "爆裂首帧": "爆裂",
    "爆裂特写贴图": "爆裂",
    "大厅动画GIF": "大厅动画",
    "大厅动画首帧": "大厅动画",
    "BOSS动画模型": "BOSS模型",
    "BOSS表演动画GIF": "BOSS动画",
    "BOSS零件透视": "BOSS模型",
}

# 提取方式（按分类 + 文件名特征）
def extract_method(cat: str, name: str, kind: str) -> str:
    if name.endswith(".glb"):
        return "UnityPy Mesh+Skin 导出"
    if "3D查看器" in name:
        return "手写（three.js）"
    if name.endswith((".gif",)):
        return "Spine 渲染 + PIL 合成"
    if "分层时序" in name:
        return "Timeline 解析"
    if name.endswith("_首帧.png"):
        return "Spine 渲染（取前景最高帧）"
    if cat == "04_卡池横幅":
        return "lss ASTC 解码"
    if cat in ("01_新角色", "02_新皮肤"):
        return "UnityPy Texture2D"
    if cat == "07_角色爆裂特写":
        return "UnityPy Texture2D"
    if cat == "06_角色大厅站立动画":
        return "Spine 渲染 + PIL 合成"
    if cat == "03_活动":
        if name.endswith((".txt", ".tsv", ".md", ".xlsx")):
            return "lss SQLite 查询"
        return "UnityPy Texture2D"
    if cat == "05_主线_47-48章":
        if name.endswith((".tsv", ".md", ".json", ".txt")):
            return "lss / 静态表 / Timeline 解析"
        if "零件透视" in name or "判定" in name:
            return "UnityPy + 手写判定表"
        return "UnityPy Texture2D"
    if name.endswith((".md", ".csv", ".pdf")):
        return "脚本生成"
    return "UnityPy"

# 优先级（按分类 + 类型，口径见 00_规范/采集优先级.md）
P0_KINDS = {"角色立绘", "角色立绘HD", "角色立绘SI", "Spine小人立绘", "技能图标",
            "爆裂动画GIF", "爆裂首帧", "爆裂特写贴图", "活动横幅",
            "活动剧情插画HD", "教学图", "活动道具", "增益图标"}
def priority(cat: str, kind: str, name: str) -> str:
    if cat == "05_主线_47-48章" and name.endswith(".txt"):
        return "P0"          # 剧情文本属 P0
    if kind in P0_KINDS:
        return "P0"
    if cat == "02_新皮肤":
        return "P0"
    if cat == "04_卡池横幅":
        return "P0"
    if cat == "07_角色爆裂特写":
        return "P0"
    if name.endswith((".glb",)):
        return "P2"
    return "P1"


# 派生产物：本来就没有单一来源键（说明/清单/一览/拼图/手写页）
RE_DERIVED = re.compile(r"(^00_|说明$|清单$|一览|预览|拼图|判定总表|freaiming|framing\.js$)")
def is_derived(rel: str) -> bool:
    bn = os.path.basename(rel)
    return bool(RE_DERIVED.search(bn)) or bn.endswith((".md", ".html", ".js"))


def refine_kind(cat: str, rel: str, kind: str, cat07: dict) -> str:
    """把清单的粗 kind 细分，让「贴图张数」这类对外数字能对上 00_汇总.tsv。
    踩坑记录 E-04：清单 kind=爆裂特写贴图 共 99 条，实际贴图只有 84 张，
    差额是时序 tsv / 角色图集 / 说明 被归到了同一个 kind。
    07 的类别一律读 tsv，不按文件名猜（`c872_skillcut_00.png` 就不以 `_skillcut.png` 结尾）。"""
    bn = os.path.basename(rel)
    if cat == "07_角色爆裂特写":
        if rel in cat07:
            return cat07[rel]          # 直接采用汇总表的类别
        if bn.startswith("00_"):
            return "汇总与说明"
        if bn == "分层时序.png":
            return "分层时序图"
        if bn.startswith("时序_") or bn == "节点贴图.tsv":
            return "时序表"
        if bn.endswith(".tsv"):
            return "时序表"
        return "其他"
    if cat == "06_角色大厅站立动画":
        if bn.startswith("00_"):
            return "汇总与说明"
        if bn.endswith("_首帧.png"):
            return "大厅动画首帧"
        if bn.endswith(".gif"):
            return "大厅动画GIF"
    return kind


def verify_tsv07(root: str, detail: list, cat07: dict) -> None:
    """交叉校验：分类贴图条数 == 00_汇总.tsv 合计行之和（15/42/27=84）"""
    p = os.path.join(root, "07_角色爆裂特写", "00_汇总.tsv")
    if not os.path.isfile(p):
        return
    tot = 0
    per = []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh, delimiter="\t")
        hdr = next(rd, None) or []
        if "类别" not in hdr:
            return
        i_dir, i_cat, i_v = hdr.index("目录"), hdr.index("类别"), hdr.index("贴图名")
        for r in rd:
            if len(r) > max(i_dir, i_cat, i_v) and r[i_cat] == "合计":
                try:
                    v = int(r[i_v])
                except ValueError:
                    continue
                tot += v
                per.append(f"{r[i_dir]}={v}")
    got = sum(1 for d in detail if d["分类"] == "07_角色爆裂特写" and d["类型"] in set(cat07.values()))
    flag = "OK" if got == tot else "!! 不一致"
    print(f"交叉校验 贴图数：汇总表 {' + '.join(per)} = {tot}｜明细表 分类贴图 {got}  → {flag}")


def default_out(root: str) -> str:
    """默认写到「版本更新/01_采集明细」。向上找含 AGENTS.md 的根，找不到退回同级。"""
    p = root
    for _ in range(4):
        p = os.path.dirname(p)
        if not p or p == os.path.dirname(p):
            break
        if os.path.isfile(os.path.join(p, "AGENTS.md")) or os.path.basename(p) == "版本更新":
            return os.path.join(p, "01_采集明细")
    return os.path.join(os.path.dirname(root), "01_采集明细")


def md5_head(path: str, n: int = 65536) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        h.update(fh.read(n))
    return h.hexdigest()[:12]


def load_bundle_index():
    """桶 -> [bundle 名]；文件不存在时返回空（不报错，来源包留空）"""
    idx = {}
    if not os.path.isdir(BASE_KEYS):
        return idx
    for f in os.listdir(BASE_KEYS):
        if not f.endswith("_keys.txt"):
            continue
        b = f[: -len("_keys.txt")]
        names = []
        try:
            with open(os.path.join(BASE_KEYS, f), encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    s = line.strip()
                    if s.endswith(".bundle"):
                        names.append(s)
        except OSError:
            continue
        idx[b] = names
    return idx


def find_bundle(idx, key: str, kind: str):
    """按 5 条规则找包；返回 '<桶>:<包名>' 或 ''"""
    label = KIND2RULE.get(kind, kind)
    m = re.match(r"^c(\d+)_(\d+)$", key or "")
    vals = {
        "k": re.escape(key or ""),
        "p": re.escape((key or "").split("_")[0]),
        "c": f"c{m.group(1)}" if m else re.escape((key or "").split("_")[0]),
        "nn": m.group(2) if m else "",
    }
    pat = None
    for lb, rx in BUNDLE_RULES:
        if lb == label:
            try:
                pat = re.compile(rx.format(**vals))
            except (KeyError, IndexError):
                pat = None
            break
    if pat is None:
        return ""
    for bucket, names in idx.items():
        for n in names:
            if pat.match(n):
                return f"{bucket}:{n}"
    return ""


# ---- 各分类的「子类 + 资源键」推导 --------------------------------------
RE_CHAR_DIR = re.compile(r"_c(\d+)(?:_(\d+))?$")
RE_ANIM = re.compile(r"^(c\d+_\d+)_(idle|action)")
RE_CUT = re.compile(r"^(c\d+_\d+)_skillcut")
RE_BANNER = re.compile(r"(?:GACHA|PASS)_(C\d+(?:_\d+)?)", re.I)

def derive(cat: str, rel: str, kind: str, ctx: dict):
    """→ (子类, 资源键)。ctx: {'tsv07':..., 'boss_exact':..., 'boss_prefix':...}"""
    tsv07 = ctx.get("tsv07") or {}
    parts = rel.split("/")
    if cat == "01_新角色":
        sub = parts[1] if len(parts) > 2 else ""
        m = RE_CHAR_DIR.search(sub)
        return sub, (f"c{m.group(1)}_00" if m else "")
    if cat == "02_新皮肤":
        sub = parts[1] if len(parts) > 2 else ""
        m = RE_CHAR_DIR.search(sub)
        return sub, (f"c{m.group(1)}_{m.group(2) or '00'}" if m else "")
    if cat == "03_活动":
        sub = parts[1] if len(parts) > 2 else ""
        m = re.search(r"（(ce\d+)）", sub)
        return sub, (m.group(1) if m else "")
    if cat == "04_卡池横幅":
        bn = os.path.basename(rel)
        m = re.search(r"GACHA_(C\d+(?:_\d+)?)", bn, re.I)
        if m:
            return "角色卡池", f"c{m.group(1)[1:]}"
        m = re.search(r"EVENT_BANNER_(.+?)(?:_S)?\.png$", bn, re.I)
        return ("通行证" if "PASS" in bn.upper() else "卡池横幅"), (m.group(1) if m else "")
    if cat == "06_角色大厅站立动画":
        sub = parts[1] if len(parts) > 2 else ""
        m = RE_ANIM.match(os.path.basename(rel))
        if m:
            return sub, m.group(1)
        m2 = RE_CHAR_DIR.search(sub)
        return sub, (f"c{m2.group(1)}_{m2.group(2) or '00'}" if m2 else "")
    if cat == "07_角色爆裂特写":
        sub = parts[1] if len(parts) > 2 else ""
        m = RE_CUT.match(os.path.basename(rel))
        if m:
            return sub, m.group(1)
        key = tsv07.get(rel) or ""
        if not key:
            m2 = RE_CHAR_DIR.search(sub)
            key = f"c{m2.group(1)}_00" if m2 else ""
        return sub, key
    if cat.startswith("05_"):
        if "关卡莱彻" in rel:
            bn = os.path.basename(rel)
            # ① 动图/00_说明.md 里那张 GIF→glb 对照表（实测 12 行）
            ex = ctx.get("boss_exact") or {}
            if bn in ex:
                return "关卡莱彻", ex[bn]
            # ② 表格里没有的「基础阶段循环」：中文名 → 型号代码 + 阶段
            pf = ctx.get("boss_prefix") or {}
            m = re.match(r"^(.+?)_(\d)阶段$", os.path.splitext(bn)[0])
            if m and m.group(1) in pf:
                return "关卡莱彻", f"{pf[m.group(1)]}_{m.group(2)}phase"
            m = re.search(r"(?:^|/)([a-z]{3}\d{3})_(\d)phase", rel)
            return "关卡莱彻", (f"{m.group(1)}_{m.group(2)}phase" if m else "")
        if "剧情插画" in rel:
            m = re.search(r"eventscene_(chap_\d+_\d+)", os.path.basename(rel))
            return "剧情插画", (m.group(1) if m else "")
        if "04_剧情文本" in rel:
            m = re.search(r"(\d+章|[a-z]{2}\d{3})", os.path.basename(rel))
            return "剧情文本", (m.group(1) if m else "")
        bn = os.path.basename(rel)
        if bn.startswith("EVENT_BANNER_"):
            # 章节预告图，键就是 lss sprite 名本身（去掉 328x108 缩略的 _S）
            return "章节预告图", re.sub(r"_S\.png$", "", bn)
        return parts[1] if len(parts) > 2 else "主线", ""
    return "", ""


def load_boss_map(root: str):
    """05/07_关卡莱彻/动图/00_说明.md → ({gif名: glb名去后缀}, {中文前缀: 型号前缀})
    这张表是实测产物（12 行），不是推测，见该文件第二节「文件清单」。"""
    p = os.path.join(root, "05_主线_47-48章", "07_关卡莱彻", "动图", "00_说明.md")
    exact, prefix = {}, {}
    if not os.path.isfile(p):
        return exact, prefix
    with open(p, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = re.match(r"\|\s*`([^`]+\.gif)`\s*\|\s*`([^`]+\.glb)`\s*\|", line)
            if not m:
                continue
            g, gl = m.group(1), m.group(2)
            exact[g] = gl[:-4]
            prefix[g.split("_")[0]] = gl.split("_")[0]
    return exact, prefix


def load_tsv07(root: str):
    """07_角色爆裂特写/00_汇总.tsv → ({相对路径: 资源ID}, {相对路径: 类别})
    类别直接取 tsv 的「类别」列，不在脚本里二次判断 —— 口径以这张表为准（E-03/E-04）。"""
    p = os.path.join(root, "07_角色爆裂特写", "00_汇总.tsv")
    key_map, cat_map = {}, {}
    if not os.path.isfile(p):
        return key_map, cat_map
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh, delimiter="\t")
        hdr = next(rd, None)
        if not hdr or "相对路径" not in hdr:
            return key_map, cat_map
        i_p, i_k = hdr.index("相对路径"), hdr.index("资源ID")
        i_c = hdr.index("类别") if "类别" in hdr else None
        for r in rd:
            if len(r) > max(i_p, i_k) and r[i_p]:
                rel = "07_角色爆裂特写/" + r[i_p].replace("\\", "/")
                key_map[rel] = r[i_k]
                if i_c is not None and len(r) > i_c:
                    cat_map[rel] = r[i_c]
    return key_map, cat_map


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="期目录，如 .../03_历史/20260813_国际服")
    ap.add_argument("--period", default=None, help="期次名，默认取 root 目录名")
    ap.add_argument("--out", default=None, help="输出目录，默认 root 的兄弟目录 01_采集明细")
    ap.add_argument("--write", action="store_true", help="真正落盘（默认只报告）")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    period = a.period or os.path.basename(root.rstrip("\\/"))
    outdir = a.out or default_out(root)

    # ---- 读素材清单 ----
    man = os.path.join(root, "_素材清单.csv")
    if not os.path.isfile(man):
        sys.exit(f"[FATAL] 找不到 {man}")
    with open(man, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    kind_of = {r["name"].replace("\\", "/"): r["kind"] for r in rows}
    link_of = {r["name"].replace("\\", "/"): ("硬链接" if str(r.get("nlink", "1")) not in ("", "1") else "独立")
               for r in rows}

    tsv07, cat07 = load_tsv07(root)
    boss_exact, boss_prefix = load_boss_map(root)
    ctx = {"tsv07": tsv07, "boss_exact": boss_exact, "boss_prefix": boss_prefix}
    idx = load_bundle_index()
    if not idx:
        print(f"[WARN] 包索引不存在：{BASE_KEYS} —— 来源包列将全部留空")

    # ---- 素材溯源表 ----
    detail, miss_key, miss_pkg = [], [], []
    for r in rows:
        rel = r["name"].replace("\\", "/")
        parts = rel.split("/")
        cat = parts[0]
        kind = r["kind"]
        sub, key = derive(cat, rel, kind, ctx)
        if not key:
            if is_derived(rel):
                key = "派生"
            else:
                miss_key.append(rel)
        pkg = find_bundle(idx, key, kind) if key and key != "派生" else ""
        if key and key != "派生" and not pkg:
            miss_pkg.append((rel, key))
        p = os.path.join(root, rel)
        detail.append({
            "期次": period,
            "客户端版本": CLIENT_VER,
            "分类": cat,
            "子类": sub,
            "文件名": os.path.basename(rel),
            "相对路径": rel,
            "类型": refine_kind(cat, rel, kind, cat07),
            "字节": os.path.getsize(p) if os.path.isfile(p) else 0,
            "来源键": key,
            "来源包": pkg,
            "提取方式": extract_method(cat, rel, kind),
            "链接状态": link_of.get(rel, "独立"),
            "优先级": priority(cat, kind, rel),
            "校验": md5_head(p) if os.path.isfile(p) else "",
        })

    # ---- 全量文件表 ----
    allfiles = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace("\\", "/")
            if rel in ("_素材清单.csv",):
                continue
            allfiles.append({
                "期次": period, "相对路径": rel,
                "后缀": os.path.splitext(f)[1].lower() or "(无)",
                "字节": os.path.getsize(p),
                "分类": rel.split("/")[0] if "/" in rel else "(顶层)",
                "在素材溯源表": "是" if rel in kind_of else "否",
            })
    allfiles.sort(key=lambda x: x["相对路径"])

    # ---- 总表（分类 × 类型）----
    agg = defaultdict(lambda: [0, 0])
    for d in detail:
        k = (d["分类"], d["类型"])
        agg[k][0] += 1
        agg[k][1] += d["字节"]
    total = [{
        "期次": period, "分类": c, "类型": t, "文件数": n, "字节": b,
        "MB": round(b / 1048576, 2),
        "P0文件数": sum(1 for d in detail if d["分类"] == c and d["类型"] == t and d["优先级"] == "P0"),
    } for (c, t), (n, b) in sorted(agg.items())]

    # ---- 报告 ----
    print(f"期次 {period}｜客户端 {CLIENT_VER}")
    print(f"素材溯源表 {len(detail)} 行｜全量文件表 {len(allfiles)} 行｜总表 {len(total)} 行")
    n_derived = sum(1 for d in detail if d["来源键"] == "派生")
    print(f"来源键：实体 {len(detail) - n_derived} / 派生 {n_derived}")
    print(f"  应溯源但无键 {len(miss_key)} 条", miss_key[:5] if miss_key else "")
    print(f"  有键但未匹配到包 {len(miss_pkg)} 条（活动类属正常，包名无代号规则）", miss_pkg[:3] if miss_pkg else "")
    print("按分类：", dict(Counter(d["分类"] for d in detail)))
    print("按优先级：", dict(Counter(d["优先级"] for d in detail)))
    verify_tsv07(root, detail, cat07)
    n_reg = sum(1 for f in allfiles if f["在素材溯源表"] == "是")
    print(f"全量文件中登记在素材表的 {n_reg} / {len(allfiles)}")

    if not a.write:
        print("\n[dry-run] 加 --write 落盘")
        return

    os.makedirs(outdir, exist_ok=True)
    def dump(name, data, cols):
        p = os.path.join(outdir, name)
        with open(p, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(data)
        print(f"  → {p}  ({len(data)} 行)")

    dump(f"采集明细_{period}.csv", detail, list(detail[0].keys()))
    dump(f"全量文件_{period}.csv", allfiles, list(allfiles[0].keys()))
    dump("采集明细_总表.csv", total, list(total[0].keys()))


if __name__ == "__main__":
    main()
