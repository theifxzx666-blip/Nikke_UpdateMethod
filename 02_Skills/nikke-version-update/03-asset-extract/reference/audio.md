# 音频：BGM 与台词配音

## 一、BGM：客户端里的 WAV 没有扩展名

客户端 BGM 是 RIFF/WAVE PCM（**44100 Hz / 16 bit / 立体声**），导出时没写扩展名，
所以双击打不开 —— 不是文件坏了。

```bash
python build_bgm.py
```

三步，全部可核对：

1. 原文件**原位改名** `.wav`（内容零改动，无损）
2. `lameenc` 编 256 kbps `.mp3`（体积约 1/6，给不方便播 wav 的场合）
3. `JukeboxListTable` + `BGMTriggerTable` 出曲目表（曲名 / 作曲 / 时长 / 触发位置）

键族：`audiogroup_assets_bgm_*`。

## 二、台词配音：文本 + 三语语音

```bash
python build_voice_pack.py      # 默认 c870 / c871 / c872
```

链路（每一步都能回溯到文件）：

```
saus/{ja,en,ko}/catalog.ndb        NKDB 加密的 SQLite
  └─ AssetEntity.Key = 语音地址（如 c870_Battle_Enter_1）
  └─ FileInfoEntity.Id = .nab 包路径
saus/{lang}/chunk/store.cdb        逐 chunk dd 取出 .nab（UnityFS）→ AudioClip
Locale_Character.lsc               台词原文（ko / en / ja / zh-TW / zh-CN）
```

产物：`台词_全语言.tsv` + 各语言 wav。

## 三、判据

| # | 判据 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 采样率 | 44100 / 16 bit / 立体声。不符说明拿到的是另一类流 |
| 2 | 非静音 | 抽 3 条算 RMS，接近 0 说明取错条目 |
| 3 | 条数对得上 | wav 条数 = 台词表该角色的行数 × 语言数；少一条要能说出为什么 |
| 4 | 文本非空 | `zh-CN` 列不允许整列为空（空说明取错了表） |

## 四、只做日配时的口径

本期只出日配（`saus/ja`）是**策略选择，不是漏采**。要在 `说明.md` 写明：
「本期配音仅日配，en / ko 未采」。否则下一次会被当成残档返工。
