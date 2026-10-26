# -*- coding: utf-8 -*-
"""08_BGM：把客户端里无扩展名的裸 WAV 转成可直接播放的 .wav + .mp3，并出曲目表。

客户端里的 BGM 资产是 RIFF/WAVE PCM（44100Hz 16bit 立体声），只是导出时没有扩展名，
所以双击无法用播放器打开。本脚本：
  1. 原文件原位改名 .wav（内容零改动，无损）
  2. 用 lameenc 编 256kbps mp3（体积约 1/6）
  3. JukeboxListTable + BGMTriggerTable 出曲目表（曲名 / 作曲 / 时长 / 触发位置）
"""
import io
import json
import wave
from pathlib import Path

import lameenc

SD = Path(r"D:\Codex\Nikke\Nikke_Skills\拆包\02_Skills\mpdump\out")
BASE = Path(r"D:\Codex\Nikke\Nikke_Skills\版本更新\03_历史\20260813_国际服"
            r"\05_主线_47-48章\08_BGM")


def jl(n):
    return json.loads((SD / (n + ".json")).read_text(encoding="utf-8"))


def convert(raw: Path):
    """raw 可以是无扩展名原文件，也可以是已改名的 .wav。"""
    wav_p = raw if raw.suffix == ".wav" else raw.with_suffix(".wav")
    if not wav_p.exists():
        raw.rename(wav_p)
    with wave.open(str(wav_p), "rb") as w:
        ch, sw, sr, nframes = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        pcm = w.readframes(nframes)
    dur = nframes / sr
    mp3_p = wav_p.with_suffix(".mp3")
    if not mp3_p.exists():
        enc = lameenc.Encoder()
        enc.set_bit_rate(256)
        enc.set_in_sample_rate(sr)
        enc.set_channels(ch)
        enc.set_quality(2)
        mp3_p.write_bytes(bytes(enc.encode(pcm)) + bytes(enc.flush()))
    return wav_p, mp3_p, dur, ch, sr, sw * 8


def main():
    jb = {r["Bgm"]: r for r in jl("JukeboxListTable")}
    trig = jl("BGMTriggerTable")
    spot = {r["BgmLoop"]: r for r in jl("BGMSpotThemeTable")}

    rows = []
    for ch_dir in sorted(BASE.iterdir()):
        if not ch_dir.is_dir():
            continue
        for raw in sorted(ch_dir.iterdir()):
            if raw.suffix.lower() not in ("", ".wav") or not raw.is_file():
                continue
            wav_p, mp3_p, dur, ch, sr, bits = convert(raw)
            base = wav_p.stem
            info = jb.get(base, {})
            seg = ""
            if not info:
                # 分段文件（_intro / _loop）归属于去掉后缀的主条目
                for suf, label in (("_intro", "前奏段"), ("_loop", "循环段")):
                    if base.endswith(suf):
                        parent = jb.get(base[: -len(suf)])
                        if parent:
                            info = dict(parent)
                            info["Name"] = f"{parent['Name']}（{label}）"
                            info["PlayTime"] = ""
                            seg = label
                        break
            # 触发位置（同类合并：战斗·关卡 6047031~6047043 共 11 关）
            bykind = {}
            for t in trig:
                if t.get("BgmLoop") != base:
                    continue
                kind = {1: "场景/大地图", 2: "关卡内", 3: "战斗", 4: "剧情", 5: "据点"}.get(
                    t["BgmType"], f"类型{t['BgmType']}")
                key = kind
                if t.get("EventId"):
                    key = f"{kind}·活动{t['EventId']}"
                elif str(t.get("TypeValue")) not in ("0", "None", ""):
                    tv = str(t.get("TypeValue"))
                    key = f"{kind}·第{tv}章" if kind.startswith("场景") else f"{kind}·关卡"
                bykind.setdefault(key, []).append(str(t.get("TypeValue")))
            uses = []
            for k, v in bykind.items():
                v = sorted({x for x in v if x not in ("0", "None", "")})
                if k.endswith("关卡") and v:
                    uses.append(f"{k} {v[0]}~{v[-1]}（{len(v)} 关）")
                else:
                    uses.append(k)
            rows.append({
                "dir": ch_dir.name, "base": base,
                "title": info.get("Name", ""), "artist": info.get("Artist", ""),
                "play_time": info.get("PlayTime", ""), "loop": "是" if info.get("IsLoop") else "",
                "dur": dur, "wav": wav_p.name, "mp3": mp3_p.name,
                "size_mb": wav_p.stat().st_size / 1048576,
                "mp3_mb": mp3_p.stat().st_size / 1048576,
                "uses": "、".join(uses) or "—",
                "spot": "是" if base in spot else "",
                "fmt": f"{sr}Hz/{bits}bit/{'立体声' if ch == 2 else str(ch)+'ch'}",
            })
            print(f"{ch_dir.name}/{base}: {dur:.1f}s  {rows[-1]['size_mb']:.1f}MB → "
                  f"{rows[-1]['mp3_mb']:.1f}MB  {rows[-1]['title'] or '(无曲名条目)'}")

    with (BASE / "00_曲目表.tsv").open("w", encoding="utf-8-sig") as f:
        f.write("# 第 47 / 48 章 BGM\n"
                "# 曲名 / 作曲 = JukeboxListTable（游戏内唱片机官方条目）；时长 = 该表 PlayTime\n"
                "# 触发位置 = BGMTriggerTable.BgmType（1 场景 2 关卡 3 战斗 4 剧情 5 据点）\n"
                "# .wav 是从客户端原样取名（内容零改动），.mp3 是 256kbps 转码\n"
                "目录\t文件名\t曲名\t作曲\t官方时长(s)\t循环\t实测时长(s)\t采样\tWAV 体积(MB)\tMP3 体积(MB)\t触发位置\t.spot主题\tWAV\tMP3\n")
        for r in rows:
            f.write("\t".join([
                r["dir"], r["base"], r["title"] or "—", r["artist"] or "—",
                str(r["play_time"] or "—"), r["loop"] or "—", f"{r['dur']:.1f}",
                r["fmt"], f"{r['size_mb']:.1f}", f"{r['mp3_mb']:.1f}",
                r["uses"], r["spot"] or "—", r["wav"], r["mp3"],
            ]) + "\n")
    print("曲目表 ->", BASE / "00_曲目表.tsv")


if __name__ == "__main__":
    main()
