# -*- coding: utf-8 -*-
"""建国际服停服前基线快照（五套）。

替代旧 make_baseline.py：旧版硬编码 152.8.7、只处理 5 桶、且把「复制文件」当成基线，
不产出静态表 / 清单 / 对象名，也没有回读校验。本版按 _干跑_20261025 的成熟结构重写。

用法（工作区由 INT_ROOT 指定，默认见下）：
    set INT_ROOT=D:\\Codex\\临时\\nikke_intl_<日期>
    python make_baseline_v2.py [--out <基线目录>] [--only catalog,keys,static,lists,names]

约定：
  * 设备拉取目录 = <INT_ROOT>\\device\\  ，内含 <桶>_catalog.ndb / <桶>_catalog.dec / <桶>.cdb.idx
  * 静态数据 zip   = <INT_ROOT>\\out\\sdplain\\StaticData_<日期>_plain.zip
  * 输出目录       = <拆包>\\00_资源库\\版本节点\\_基线_<期次>\\

每一步都做回读校验；任何一步数字对不上就抛异常，不静默通过（易错清单 E-31 同类）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

# ---------------- 环境 ----------------
BUCKETS = ["core", "dp", "ja", "en", "ko", "fd", "saus"]
# 只对前 5 桶做键 diff；en/ko 是语言桶、键集与 ja 完全相同（实测 2107），单独记号即可
LANG_BUCKETS = {"ja", "en", "ko"}
CORE_BUCKETS = {"core", "dp"}

INT_ROOT = Path(r"D:\Codex\临时\nikke_intl_20261029")
DEV = INT_ROOT / "device"
SDPLAIN = INT_ROOT / "out" / "sdplain"

PACK_ROOT = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\00_资源库\版本节点")
DEFAULT_OUT = PACK_ROOT / "_基线_20261029"
# 静态表导出器（C#/MemoryPack，见 build_static 的说明）
MPDUMP = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\bin\Release\net8.0\mpdump.exe")

# 11 张判据表（10-29 判「框/称号/皮肤/卡池/通行证/活动」的第一判据）
# ProfileCardObjectTable 是「个人主页」的物件总表（背景/贴纸/称号 badge 三类），
# 只有它能回答「本期新增了哪些个人主页装饰」，UserTitleTable 只覆盖称号文字本体。
STATIC_TABLES = [
    "CharacterCostumeTable",
    "UserFrameTable",
    "UserTitleTable",
    "UserTitleAssemblyTable",
    "ProfileCardObjectTable",
    "PassManagerTable",
    "EventManagerTable",
    "TrailMarkerEventTable",
    "GachaTypeTable",
    "GachaSelectupListTable",
    "GachaListProbTable",
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ro(db: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


# ---------------- 1. catalog ----------------
def build_catalog(out: Path, log: list) -> dict:
    dst = out / "00_基线_catalog"
    dst.mkdir(parents=True, exist_ok=True)
    buckets = []
    for b in BUCKETS:
        ndb = DEV / f"{b}_catalog.ndb"
        dec = DEV / f"{b}_catalog.dec"
        if not ndb.exists():
            log.append(f"  [跳过] {b}: 无 {ndb.name}")
            continue
        shutil.copy2(ndb, dst / ndb.name)
        shutil.copy2(dec, dst / dec.name)
        idx = None
        for cand in (DEV / f"{b}.cdb.idx", DEV / f"{b}/store.cdb.idx"):
            if cand.exists():
                idx = cand
                break
        if idx:
            shutil.copy2(idx, dst / f"{b}.cdb.idx")

        con = ro(dec)
        keys = con.execute("select count(*) from files_chunktype").fetchone()[0]
        raw = con.execute("select count(*) from files_rawtype").fetchone()[0]
        chunks = con.execute("select count(*) from chunks").fetchone()[0]
        comp = con.execute("select sum(compressed_size) from chunks").fetchone()[0] or 0
        orig = con.execute("select sum(original_size) from chunks").fetchone()[0] or 0
        con.close()

        rec = {
            "bucket": b,
            "ndb_bytes": ndb.stat().st_size,
            "dec_bytes": dec.stat().st_size,
            "keys": keys,
            "rawtype": raw,
            "chunks": chunks,
            "compressed_gb": round(comp / 2 ** 30, 3),
            "original_gb": round(orig / 2 ** 30, 3),
            "ndb_sha256": sha256(ndb),
            "dec_sha256": sha256(dec),
        }
        buckets.append(rec)
        log.append(f"  {b:5s} ndb={rec['ndb_bytes']:>10,}  keys={keys:>7,}  "
                   f"raw={raw:>4}  chunks={chunks:>6,}  原始={rec['original_gb']:>7.2f} GB")
    return {"buckets": buckets}


# ---------------- 2. 键清单 ----------------
def build_keys(out: Path, manifest: dict, log: list) -> None:
    dst = out / "00_基线_键清单"
    dst.mkdir(parents=True, exist_ok=True)
    for rec in manifest["buckets"]:
        b = rec["bucket"]
        con = ro(DEV / f"{b}_catalog.dec")
        keys = [r[0] for r in con.execute("select key from files_chunktype order by key")]
        raws = con.execute(
            "select file_id, key, size, lower(hex(hash)) from files_rawtype order by file_id"
        ).fetchall()
        con.close()
        (dst / f"{b}_keys.txt").write_text("\n".join(keys) + "\n", encoding="utf-8")
        (dst / f"{b}_raw_keys.tsv").write_text(
            "\n".join(f"{rid}\t{nm}\t{size}\t{h}" for rid, nm, size, h in raws) + "\n",
            encoding="utf-8")
        rec["keys_written"] = len(keys)
        rec["raw_written"] = len(raws)
        assert len(keys) == rec["keys"], f"{b} 键数回读不一致 {len(keys)} != {rec['keys']}"
        log.append(f"  {b:5s} keys={len(keys):>7,}  raw={len(raws):>4}")


# ---------------- 3. 静态表 ----------------
def build_static(out: Path, log: list) -> dict:
    """静态表走 mpdump（C#/MemoryPack），不要自己解 .mpk。

    实测（2026-10-26）：.mpk 是 **MemoryPack** 序列化，必须有 C# 侧的类型定义
    （`02_Skills\\mpdump\\Data\\JsonStaticData.cs`）才能反序列化；Python 侧硬解只能
    猜字段顺序，一改 schema 就全错。mpdump.exe 支持 179 张表，直接调。
    """
    dst = out / "00_基线_静态表"
    dst.mkdir(parents=True, exist_ok=True)
    all_dir = dst / "_mpdump全量"
    zp = sorted(SDPLAIN.glob("StaticData_*_plain.zip"))
    if not zp:
        log.append("  [跳过] 无 StaticData_*_plain.zip")
        return {"pack": None, "tables": []}
    zp = zp[-1]

    if not (all_dir / "_entries.txt").exists():
        import subprocess
        exe = MPDUMP
        if not exe.exists():
            log.append(f"  [跳过] 找不到 {exe}")
            return {"pack": zp.name, "tables": [], "error": "mpdump 缺失"}
        r = subprocess.run([str(exe), str(zp), str(all_dir)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        ok = sum(1 for ln in (r.stdout or "").splitlines() if ln.startswith("[OK]"))
        log.append(f"  mpdump 导出 {ok} 张表 -> _mpdump全量\\")
        if ok == 0:
            log.append(f"  [警告] mpdump 无产出：{r.stderr[-300:] if r.stderr else '-'}")
    else:
        log.append("  _mpdump全量 已存在，跳过重跑")

    out_tables = []
    for t in STATIC_TABLES:
        src = all_dir / f"{t}.json"
        if not src.exists():
            log.append(f"  [缺失] {t}")
            continue
        rows = json.loads(src.read_text(encoding="utf-8"))
        ids = sorted({r.get("Id") for r in rows if isinstance(r, dict) and "Id" in r})
        out_tables.append({"table": t, "rows": len(rows), "unique_ids": len(ids),
                           "bytes": src.stat().st_size})
        log.append(f"  {t:26s} rows={len(rows):>7,}  Id={len(ids):>7,}  {src.stat().st_size:>9,} B")

    all_tables = sorted(p.stem for p in all_dir.glob("*.json"))
    (dst / "_全部表清单.txt").write_text("\n".join(all_tables) + "\n", encoding="utf-8")
    log.append(f"  全部表 {len(all_tables):,} 张 -> _全部表清单.txt")
    return {"pack": zp.name, "pack_sha256": sha256(zp), "tables": out_tables,
            "all_tables": len(all_tables), "via": "mpdump"}


# ---------------- 4. 清单（皮肤 / 剧情代号 / 战场代号） ----------------
def _load_table(out: Path, name: str):
    p = out / "00_基线_静态表" / "_mpdump全量" / f"{name}.json"
    if not p.exists():
        p = out / "00_基线_静态表" / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _locale(out: Path, table: str) -> dict:
    """读解密后的 Locale 表，返回 Key -> en / zh-CN。"""
    p = DEV / "lsc" / f"{table}.dec"
    if not p.exists():
        p = DEV / "locale" / f"{table}.dec"
    if not p.exists():
        p = DEV / "locale2" / f"{table}.dec"
    if not p.exists():
        return {}
    con = ro(p)
    cols = [r[1] for r in con.execute(f'pragma table_info("{table}")')]
    use = [c for c in ("en", "zh-CN") if c in cols]
    rows = {}
    for r in con.execute(f'select Key,{",".join(chr(34)+c+chr(34) for c in use)} from "{table}"'):
        rows[r[0]] = r[1:]
    con.close()
    return rows


def build_lists(out: Path, log: list) -> dict:
    dst = out / "00_基线_清单"
    dst.mkdir(parents=True, exist_ok=True)
    res = {}

    # 4.1 皮肤基线：CharacterCostumeTable + Locale_CharacterCostume + Locale_Character
    #     皮肤名/描述键直接取表里的 *Locale 字段（不让脚本自己拼，E-01 同类）
    ct = _load_table(out, "CharacterCostumeTable")
    loc = _locale(out, "Locale_CharacterCostume")
    chars = _locale(out, "Locale_Character")
    if ct is not None:
        lines = ["Id\tcID\t角色EN\t角色CN\t皮肤序号\t皮肤名键\t皮肤名EN\t皮肤名CN\t描述键\t描述\t获取分类\t商店价Id"]
        for r in ct:
            rid, idx = r.get("ResourceId"), r.get("CostumeIndex")
            if rid is None or idx is None:
                continue
            nk = (r.get("CostumeNameLocale") or "").split(":")[-1]
            dk = (r.get("CostumeDescriptionLocale") or "").split(":")[-1]
            cen, ccn = (chars.get(f"{rid}_name") or ("", ""))[:2]
            en, cn = (loc.get(nk) or ("", ""))[:2]
            desc = (loc.get(dk) or ("",))[0]
            lines.append("\t".join(str(x) for x in (
                r.get("Id"), rid, cen, ccn, idx, nk, en, cn, dk,
                (desc or "").replace("\t", " ").replace("\n", " "),
                r.get("CostumeShopType", ""), r.get("CostumeShopPriceId", ""))))
        (dst / "皮肤基线.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        res["costume_rows"] = len(lines) - 1
        log.append(f"  皮肤基线.tsv{'':<10} {len(lines)-1:,} 行")

    # 4.2 剧情代号：从 Key 里解析（表结构是 Key + 9 语言列，没有 cID 列）
    #     Key 形态实测（2026-10-26）：
    #       d_Counseling_elegg_boomandshock_01_1        正文行
    #       d_counseling_anis_sparklingsummer_01_title   只有标题（没有正文行）
    #       d_nikke_ce004_01_01_1                        活动剧情，三层数字
    #       d_nikke_snowwhite_heavyarms_04_1             个人剧情，两层数字
    #     规则：先剥尾部 `_title`，再剥掉**所有**尾部 `_<数字>` 段，剩下的就是代号。
    #     不能改回非贪婪 `(.+?)_(\d+)_(\d+)$` —— 那样 `ce004_01_01_1` 会得到 `CE004_01`，
    #     把同一活动的不同集拆成不同代号（E-31 同类：静默多算）。
    STORY = {
        "counseling": ("Locale_Counseling", re.compile(r"^d_Counseling_(.+?)$", re.I)),
        "nikke_episode": ("Locale_NikkeEpisode", re.compile(r"^d_nikke_(.+?)$", re.I)),
    }

    def _code(rest: str) -> str:
        s = rest
        while True:
            if s.lower().endswith("_title"):
                s = s[:-6]
                continue
            m = re.search(r"_\d+$", s)
            if m:
                s = s[: m.start()]
                continue
            break
        return s.upper()

    for tag, (t, pat) in STORY.items():
        p = next((c for c in (DEV / "locale2" / f"{t}.dec",
                              DEV / "dec_cache" / f"{t}.dec",
                              DEV / "lsc" / f"{t}.dec") if c.exists()), None)
        if p is None:
            log.append(f"  [跳过] {t} 未解密")
            continue
        con = ro(p)
        ks = [r[0] for r in con.execute(f'select Key from "{t}"')]
        con.close()
        codes: dict[str, int] = {}
        for k in ks:
            m = pat.match(k or "")
            if not m:
                continue
            c = _code(m.group(1))
            if c and not c.isdigit():
                codes[c] = codes.get(c, 0) + 1
        (dst / f"剧情代号_{tag}.json").write_text(
            json.dumps({"table": t, "key_rows": len(ks), "codes": len(codes),
                        "map": dict(sorted(codes.items()))}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        res[f"story_{tag}"] = len(codes)
        log.append(f"  剧情代号_{tag}.json{'':<6} {len(codes):,} 个代号 / {len(ks):,} 行")

    # 4.3 战场代号：只取「主场景」= fcbg_<场景>[_hard|_story]_<三位号>
    #     实测形态：fcbg_arkcity_001 / fcbg_arkcity_hard_002 / fcbg_arkcity_story_003
    #     排除：*_skybox、*_bg_06、*_barrierdoor_01_left（这些都是同一个战场的部件）
    #     必须先剥 `_<32hex>.bundle` 尾巴（E-40 同类），否则每个 bundle 都成独立代号
    HASH_TAIL = re.compile(r"_[0-9a-f]{32}(\.bundle)?$")
    BATTLE = re.compile(r"(f[ce]bg_[a-z]+(?:_(?:hard|story))?_\d{3})$")
    fc: dict[str, list[str]] = {}
    for b in CORE_BUCKETS:
        kp = out / "00_基线_键清单" / f"{b}_keys.txt"
        if not kp.exists():
            continue
        for k in kp.read_text(encoding="utf-8").splitlines():
            low = HASH_TAIL.sub("", k.lower())
            m = BATTLE.search(low)
            if m:
                fc.setdefault(m.group(1), []).append(f"{b}/{k}")
    if fc:
        (dst / "战场代号.json").write_text(
            json.dumps({"count": len(fc),
                        "main": sum(1 for k in fc if k.startswith("fcbg_")),
                        "event": sum(1 for k in fc if k.startswith("febg_")),
                        "map": {k: len(v) for k, v in sorted(fc.items())}},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        res["battle_codes"] = len(fc)
        res["battle_main"] = sum(1 for k in fc if k.startswith("fcbg_"))
        res["battle_event"] = sum(1 for k in fc if k.startswith("febg_"))
        log.append(f"  战场代号.json{'':<11} {len(fc):,} 个"
                   f"（主线 {res['battle_main']} / 活动 {res['battle_event']}）")

    return res


# ---------------- 5. 对象名（头像框 / 称号） ----------------
def build_names(out: Path, log: list) -> dict:
    dst = out / "00_基线_对象名"
    dst.mkdir(parents=True, exist_ok=True)
    res = {}

    uf = _load_table(out, "UserFrameTable")
    if uf is not None:
        rows = [{"Id": r.get("Id"), "ResourceId": r.get("ResourceId"),
                 "SubResourceId": r.get("SubResourceId"), "TabType": r.get("TabType")}
                for r in uf]
        res["frames"] = len(rows)
        res["frame_resources"] = len({r["ResourceId"] for r in rows if r["ResourceId"]})
        (dst / "头像框.json").write_text(
            json.dumps({"count": len(rows),
                        "unique_resource": res["frame_resources"],
                        "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        log.append(f"  头像框.json             {len(rows):,} 行 / "
                   f"{res['frame_resources']:,} 个 ResourceId")

    for table, tag, icon_f, name_f in (
            ("UserTitleTable", "称号", "IconResourceId", "NameLocaleKey"),
            ("UserTitleAssemblyTable", "称号装配", "IconId", "TitleLocaleKey")):
        rows = _load_table(out, table)
        if rows is None:
            continue
        # 字段名两表不同：UserTitleTable 用 IconResourceId/NameLocaleKey，
        # 装配表用 IconId/TitleLocaleKey。旧版统一取 IconResource/TitleLocaleKey，
        # 结果 250 行全 None，等于没存名字（2026-10-26 修）。
        slim = [{"Id": r.get("Id"),
                 "IconResource": r.get(icon_f) or "",
                 "LocaleKey": r.get(name_f) or ""} for r in rows]
        codes = sorted({str(s["IconResource"]) for s in slim if s["IconResource"]})
        missing = sum(1 for s in slim if not s["LocaleKey"])
        if missing:
            log.append(f"  !! {tag}.json 有 {missing} 行没有 LocaleKey —— 字段名可能又变了")
        (dst / f"{tag}.json").write_text(
            json.dumps({"table": table, "count": len(slim), "icon_codes": len(codes),
                        "codes": codes, "rows": slim}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        res[tag] = {"rows": len(slim), "codes": len(codes)}
        log.append(f"  {tag}.json{'':<10} {len(slim):,} 行 / {len(codes):,} 个图标代号")

    # 个人主页物件（背景 / 贴纸 / 称号 badge）——判「本期新增装饰」的唯一总表
    pc = _load_table(out, "ProfileCardObjectTable")
    if pc is not None:
        rows = [{"Id": r.get("Id"), "Type": r.get("ObjectType"), "Sub": r.get("ObjectSubType"),
                 "Grade": r.get("GradeType"), "ResourceId": r.get("ResourceId") or "",
                 "LocaleKey": r.get("NameLocalkey") or ""} for r in pc]
        (dst / "个人主页.json").write_text(
            json.dumps({"table": "ProfileCardObjectTable", "count": len(rows),
                        "by_type": {f"{t}-{s}": sum(1 for r in rows if r["Type"] == t and r["Sub"] == s)
                                    for t, s in sorted({(r["Type"], r["Sub"]) for r in rows})},
                        "rows": rows}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        res["个人主页"] = len(rows)
        log.append(f"  个人主页.json           {len(rows):,} 行（背景/贴纸/称号三类）")

    return res


# ---------------- 主流程 ----------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--only", default="catalog,keys,static,lists,names")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    todo = {s.strip() for s in args.only.split(",") if s.strip()}

    log: list[str] = []

    log.append("[1/5] catalog")
    man = build_catalog(out, log) if "catalog" in todo else {"buckets": []}
    # 即便只跑后续步骤，也要能从已落地文件回填桶信息
    if "catalog" not in todo and (out / "00_基线_catalog" / "manifest.json").exists():
        man = json.loads((out / "00_基线_catalog" / "manifest.json").read_text(encoding="utf-8"))
    man.setdefault("buckets", [])

    if "keys" in todo and man["buckets"]:
        log.append("[2/5] 键清单")
        build_keys(out, man, log)

    log.append("[3/5] 静态表")
    sd = build_static(out, log) if "static" in todo else {}
    if "static" not in todo and (out / "00_基线_静态表").exists():
        sd = {"pack": "-", "tables": [{"table": p.stem} for p in
                                      (out / "00_基线_静态表").glob("*.json")]}

    log.append("[4/5] 清单")
    ls = build_lists(out, log) if "lists" in todo else {}

    log.append("[5/5] 对象名")
    nm = build_names(out, log) if "names" in todo else {}

    manifest = {
        "期次": "20261029_国际服",
        "包名": "com.proximabeta.nikke",
        "快照时间": "2026-10-26 02:30 (GMT+8)",
        "设备": "e9711d88 / 25102RKBEC / Android 17",
        "三要素": {
            "versionName": "152.8.7",
            "versionCode": 1520807,
            "lastUpdateTime": "2026-10-21 21:33:58",
            "catalog_mtime": "2026-10-21 21:38:30~31",
            "store_cdb_mtime": "2026-10-21 21:49:00~42",
        },
        "静态数据": sd,
        "清单": ls,
        "对象名": nm,
        "桶": man["buckets"],
    }
    (out / "00_基线_catalog" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(log))
    print(f"\n完成 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
