# -*- coding: utf-8 -*-
"""新角色台词语音包：文本 + 日/英/韩三语配音。

链路（每个字段都可回溯到文件）：
  1. `runtime_data/saus/{ja,en,ko}/catalog.ndb`（NKDB 加密的 SQLite）
       -> AssetEntity.Key = 语音地址（如 c870_Battle_Enter_1）
       -> FileInfoEntity.Id  = .nab 包路径
  2. `saus/{lang}/chunk/store.cdb` 逐 chunk dd 取出 .nab（UnityFS）-> AudioClip
  3. `Locale_Character.lsc` 提供 ko / en / ja / zh-TW / zh-CN 台词原文

用法：
  python build_voice_pack.py            # 默认 c870/c871/c872
"""
import io
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import UnityPy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nkdb_dec            # noqa: E402
import pull_chunks         # noqa: E402

ADB = r"D:\WorkBuddy\Supports\platform-tools\adb.exe"
BASE = "/storage/emulated/0/Android/data/com.proximabeta.nikke/files/com.shiftup.patch"
DEV = Path(r"D:\Codex\临时\nikke_intl_20261029\device")
LSC = DEV / "lsc"
DST = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服\01_新角色")

LANGS = [("ja", "日配")]   # en/ko 语音包在本机未下发（只有 catalog），只能取日配
CIDS = ["c870", "c871", "c872"]

VOICE_CN = {
    "Attractive_Up": "好感度提升", "Battle_Enter": "战斗开始", "Battle_Ready": "战斗准备",
    "Damage": "受击", "Die": "阵亡", "Field_Go": "战场出发", "Field_Touch": "战场互动",
    "FullBurst": "爆裂技能", "Ult_Skill": "爆裂技能", "Ult_Skill_Ready": "爆裂就绪",
    "Gacha_Get": "抽卡获得", "Gift": "收礼", "Kill_Monster": "击杀",
    "Lobby_Stay": "大厅待机", "Lobby_Stay_Love": "大厅待机·好感",
    "Lobby_Touch": "大厅互动", "Lobby_Touch_Love": "大厅互动·好感",
    "Outpost_Touch": "前哨基地互动", "Party_Deploy": "编队出击",
    "Reinforce": "支援请求", "Reload": "换弹", "Win": "胜利",
}


def ensure_catalog(lang):
    """语音地址目录 = saus/<lang>/raw/*.cat（NKDB），不是 catalog.ndb。

    catalog.ndb 是 chunk 目录（表名 files_chunktype 那套），不含资源地址。
    """
    dec = DEV / f"{lang}_asset_catalog.dec"
    if dec.exists():
        return dec
    env = dict(**__import__("os").environ, MSYS_NO_PATHCONV="1")
    p = subprocess.run([ADB, "shell", f"su -c 'ls -1 {BASE}/{lang}/raw/*.cat'"],
                       capture_output=True, env=env)
    cat = [x for x in (p.stdout or b"").decode("utf-8", "replace").split() if x.endswith(".cat")]
    if not cat:
        raise SystemExit(f"{lang} 桶没有 raw/*.cat，无法解析语音地址")
    src = DEV / f"{lang}_asset_catalog.cat"
    p = subprocess.run([ADB, "pull", cat[0], str(src)], capture_output=True, env=env)
    if p.returncode != 0:
        raise SystemExit(f"拉取 {cat[0]} 失败: {p.stderr[:200]}")
    dec.write_bytes(nkdb_dec.decrypt_nkdb(src.read_bytes()))
    print(f"  [catalog] {lang} <- {Path(cat[0]).name}")
    return dec


def voice_index(lang):
    """{语音地址: (相对路径, 体积)} —— 只取 c87x。"""
    con = sqlite3.connect(f"file:{ensure_catalog(lang)}?mode=ro", uri=True)
    rows = con.execute(
        'select a."Key", f."RelativePath", f."Size" from AssetEntity a '
        'join FileInfoEntity f on f."Id"=a."FileId" '
        'where a."Key" like ? or a."Key" like ? or a."Key" like ? '
        'order by a."Key"', ("c870%", "c871%", "c872%")).fetchall()
    con.close()
    return {k: (p, s) for k, p, s in rows}


def locale_texts():
    con = sqlite3.connect(f"file:{LSC / 'Locale_Character.dec'}?mode=ro", uri=True)
    out = {}
    for k, ko, en, ja, tw, cn in con.execute(
            'select "Key","ko","en","ja","zh-TW","zh-CN" from Locale_Character '
            'where "Key" like ? or "Key" like ? or "Key" like ?',
            ("c870%", "c871%", "c872%")):
        out[k] = dict(ko=ko or "", en=en or "", ja=ja or "", tw=tw or "", cn=cn or "")
    con.close()
    return out


def char_names():
    """名字键是 `{三位数}_name`（如 870_name），不是 c870_name —— 取自 CharacterTable.NameLocalkey。"""
    con = sqlite3.connect(f"file:{LSC / 'Locale_Character.dec'}?mode=ro", uri=True)
    out = {}
    for cid in CIDS:
        r = con.execute('select "zh-CN","en","ja","zh-TW" from Locale_Character '
                        'where "Key"=?', (f"{cid[1:]}_name",)).fetchone()
        out[cid] = r or ("", "", "", "")
    con.close()
    return out


def pull_nab(lang, rel, cache):
    """rel = 'ab/xxxx.nab'；同一 hash 只拉一次。"""
    h = Path(rel).stem
    if h in cache:
        return cache[h]
    bp = pull_chunks.D / f"_vc_{lang}_{h[:12]}.bundle"
    if not bp.exists() or bp.stat().st_size < 1024:
        pull_chunks.pull(lang, rel, bp.name)
    cache[h] = bp
    return bp


def export_lang(lang, cid, outdir, cache):
    """导出该语言该角色的全部语音，返回 {语音键: (文件名, 时长秒, 采样率)}。"""
    idx = voice_index(lang)
    keys = {k: v for k, v in idx.items() if k.startswith(cid + "_")}
    # 先把需要的 .nab 全部拉下来
    for k, (rel, _sz) in keys.items():
        pull_nab(lang, rel, cache)
    got = {}
    for bp in {cache[Path(rel).stem] for rel, _ in keys.values()}:
        env = UnityPy.load(str(bp))
        for o in env.objects:
            if o.type.name != "AudioClip":
                continue
            try:
                c = o.read()
            except Exception:
                continue
            if not c.m_Name.startswith(cid + "_"):
                continue
            try:
                samples = c.samples
            except Exception:
                continue
            for fn, data in samples.items():
                ext = ".wav" if not fn.lower().endswith((".wav", ".ogg")) else Path(fn).suffix
                fp = outdir / (c.m_Name + ext)
                fp.write_bytes(data)
                got[c.m_Name] = (fp.name, round(float(c.m_Length), 2),
                                 int(c.m_Frequency), int(c.m_Channels),
                                 fp.stat().st_size)
    return got


def one_line(s):
    """台词原文含换行，直接写进 tsv 会把一条记录拆成多行；转成字面 \\n。"""
    return str(s).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace("\t", " ")


def vtype(key):
    """c870_Lobby_Touch_Love_1 -> (Lobby_Touch_Love, 1)"""
    body = key.split("_", 1)[1]
    m = re.match(r"^(.*?)_(\d+)$", body)
    if m:
        return m.group(1), int(m.group(2))
    return body, 0


def main():
    names = char_names()
    loc = locale_texts()
    rows = []

    # 角色目录名沿用 01_新角色 现有命名：'QUEEN（真）_c870' 之类
    dirs = {p.name: p for p in DST.iterdir() if p.is_dir()}
    cmap = {}
    for cid in CIDS:
        for nm, p in dirs.items():
            if nm.endswith("_" + cid):
                cmap[cid] = p
                break
        cmap.setdefault(cid, DST / cid)

    for cid in CIDS:
        vdir = cmap[cid] / "台词与配音"
        vdir.mkdir(parents=True, exist_ok=True)
        zh, en, ja, tw = names[cid]
        print(f"\n=== {cid} {zh} -> {vdir.relative_to(DST)}")
        per_lang = {}
        for lang, lang_cn in LANGS:
            sub = vdir / f"语音_{lang_cn}"
            sub.mkdir(parents=True, exist_ok=True)
            cache = {}
            got = export_lang(lang, cid, sub, cache)
            per_lang[lang] = got
            print(f"  {lang_cn}: {len(got)} 条  "
                  f"{sum(v[4] for v in got.values())/1048576:.1f}MB")
        keys = sorted(set().union(*[set(v) for v in per_lang.values()]),
                      key=lambda k: (vtype(k)[0], vtype(k)[1]))
        for k in keys:
            vt, n = vtype(k)
            t = loc.get(k, {})
            rec = [cid, zh, vt, VOICE_CN.get(vt, vt), n, k,
                   t.get("ja", ""), t.get("tw", ""), t.get("cn", ""),
                   t.get("en", ""), t.get("ko", "")]
            for lang, _cn in LANGS:
                g = per_lang[lang].get(k)
                rec.append(f"{g[0]}|{g[1]}s" if g else "—")
            rows.append(rec)

    hdr = ["角色code", "角色名(简中)", "语音类型", "语音类型(中文)", "序号", "语音键",
           "日文台词", "繁中台词", "简中台词", "英文台词", "韩文台词",
           "配音文件|时长"]
    for cid in CIDS:
        vdir = cmap[cid] / "台词与配音"
        sub = [r for r in rows if r[0] == cid]
        lines = [
            f"# {names[cid][0]}（{cid}）全部台词语音",
            "# 音频来源：runtime_data/saus/ja 语音包（AssetEntity → FileInfoEntity → .nab）",
            "# 文本来源：Locale_Character.lsc 的 ja / zh-TW / zh-CN / en / ko 列，原文直取",
            "# 国际服语音包按语言分桶（saus/ja、saus/en、saus/ko）；本机只下发了 ja（3.8 GB），"
            "en / ko 桶里仅有 catalog、没有语音数据，故只输出日配",
        ]
        lines.append("\t".join(hdr))
        lines += ["\t".join(one_line(x) for x in r) for r in sub]
        (vdir / "台词_全语言.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[ok] {vdir / '台词_全语言.tsv'}  {len(sub)} 行")

    print(f"\n合计 {len(rows)} 条语音记录")


if __name__ == "__main__":
    main()
