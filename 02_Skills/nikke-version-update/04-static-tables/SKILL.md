---
name: nikke-static-tables
description: NIKKE 静态表与文本库提取——.lss/.lsc 实为 SQLite，用 mpdump 导静态表 JSON；并含两条业务口径：活动奖励模板 15 口径、个人主页称号/头像框四层 diff。当需要「技能数值」「角色属性」「BOSS 零件」「表结构」「lss 里有什么」「活动收益」「头像框新增」「称号新增」时使用。
---

# 04 · 静态表与文本库

**`.lss` / `.lsc` 不是自定义二进制，是 SQLite。** 直接 `sqlite3` 或 Python `sqlite3` 打开即可，
不需要写解析器。

---

## 触发条件

- 要技能数值（10 级）、角色属性、BOSS 零件判定
- 要确认某张静态表里有没有某一行
- 要判断「这个数字从哪张表来」

## 输入 / 输出

| 方向 | 内容 |
| :--- | :--- |
| 输入 | `<WORK>/device/*.lss`（从 `saus` 桶拉，需先 NKDB 解密） |
| 输出 | `<输出>/<表名>.json`（mpdump 导出）+ `<输出>/表清单.tsv` |

---

## 编排看板

```bash
python scripts\run.py --status          # 看板：DONE / PEND / MAN! / BLOK
python scripts\run.py --run 05          # 只跑某一步
python scripts\run.py --run all --dry    # 先看整条链要跑什么，不动手
python scripts\run.py --run all          # 按序跑，任一步失败就停
```

`done` 只由「产物存在 + 判据通过」推出，**不看有没有跑过** —— 删掉产物就是重跑，
不存在需要清理的状态文件。改常量 / 要人眼看图的步骤标 `MAN!`，`--run` 只把做法打出来，
不假装能自动；跑完命令后看板会重算产物判据，**脚本返回 0 但产物不合格照样算失败**。

| 变量 | 作用 |
| :--- | :--- |
| `NIKKE_WORK` | 当期工作区。脚本内部都读它来定产物落点 |
| `NIKKE_PY` | venv 解释器（`D://Codex//依赖//venv-nikke//Scripts//python.exe`），缺 UnityPy 的 Python 跑不了 |
| `NIKKE_STATIC` | mpdump 输出目录（静态表 JSON） |
| `NIKKE_REPO` | 拆包资源库根 |
| `NIKKE_EVENT` / `NIKKE_BASE` | 本期活动 `EventManager.Id` / 基线对象名目录 |
引擎是同目录的 `runlib.py`：占位符解析 + 产物判定 + 强制 UTF-8 起子进程
（`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，否则中文控制台下 UnityPy/json 里的中文直接炸）。

## 步骤

### 1. 拉 `.lss` 并解密

```bash
# saus 桶的 raw\ 下有 Locale_*/perm_*/event_YYMMDD
"$ADB" shell su -c "cp '/…/saus/raw/Locale_Character.lss' /sdcard/_x.lss"
"$ADB" pull /sdcard/_x.lss <WORK>/device/Locale_Character.lss
"$VENV_PY" nkdb_dec.py <WORK>/device/Locale_Character.lss   # → .dec，SQLite
```

本期实测 **70 个 `.lss`**：`Locale_*`（本地化）、`perm_*`（常驻配置）、`event_YYMMDD`（分期）。

### 2. 先看有什么表（别猜表名）

```bash
"$VENV_PY" scripts/list_lss_tables.py <WORK>/device/*.dec
```

输出每张库的表名 + 行数 + 列名。**表名以这个输出为准，不许凭记忆写。**

### 3. 静态表走 mpdump

`拆包/02_Skills/mpdump`（365 类型）能解 MemoryPack 序列化的静态表。

```bash
cd "Nikke_Skills/拆包/02_Skills/mpdump"
# 先跑一次既有 Dump 确认能出 JSON，再决定要不要加类型
```

导出后一张表一个 JSON，放 `<输出>/staticdata/`。

### 4. 按需查表

| 要什么 | 查哪张 | 陷阱 |
| :--- | :--- | :--- |
| 技能数值（10 级） | **`SkillInfoTable`** | **不是 `SkillTable`**。`Locale_Skill` 只有文案，没数值 |
| 角色基础属性 | `CharacterTable` | 稀有度/爆裂阶段在别的字段 |
| 头像框 | `UserFrameTable` | 一个框可能占多行：主行 `SubResourceId` 为空，部件行 `SubResourceId` = 子资源名 |
| 称号 | `UserTitleTable` / `UserTitleAssemblyTable` / `Locale_Profile:title_*` | **三套体系并存**，只查一套必漏 |
| 皮肤 | `CharacterCostumeTable` | — |
| 卡池 | `GachaTypeTable` / `GachaSelectupListTable` / `GachaListProbTable` | 三张配合看 |
| BOSS 零件 | `MonsterPartsTable` | **`PartsSkin` 与 `PartsObject` 是两套命名**，混用会对不上 |
| 关卡 / 点位 | `campaignlevelmapgroup` / `<活动>levelmapgroup` | 直接给 `PositionId` + 世界坐标，**不要碰 LDtk** |

### 5. 文本表（本地化）

`Locale_*.lss` 的 `Key → Value`，5 语齐全（简中 / 繁中 / 日 / 英 / 韩）。
具体做法见 Skill `05-text-locale`。

### 6. 活动奖励模板（15 口径）

一期活动要交一份 **17 页 `活动收益_zh-CN.xlsx`**，另加一行跨期对照。
**只吃静态表，不依赖拉包** —— 键 diff 出完就能算，可与渲染并行。

```bash
python event_template_probe.py --event <事件Id>       # 也可 --all 批量
python event_template_probe.py --all --compare <活动模板收益_zh-CN.xlsx>
```

一条命令吐 15 个口径：主线关数 / 一次性 / 可重复 / 一次性主机 / 挑战 / 任务 /
签到 / 商店 / 地图件数 / 天数 / 活动代号 / 地图 prefab / 可重复单次产出。

**先定组，再填页**：

| 组（按 `EventSystemType` + 天数） | 上期同组数值（关/一次性/可重复/主机/挑战/任务/签到/商店） |
| :--- | :--- |
| 有地图 · 21 天（主流） | 36(21+15) / — / — / **270** / 7 / **52** / 14 / 25 |
| 有地图 · 28 天（CE 联动） | 36(21+15) / — / — / **280** / 7 / **54~55** / 14 / 23~24 |
| 无地图（剧情活动） | 24(14+10) / — / — / **210** / 5 / **26** / 无 / 无 |

**三个必记的坑**：

1. **「主机」不是按名字找的** —— 名字字段是 locale key，匹配「通用主机」**恒 0**。
   正解：`ItemPieceTable` 里 `ItemSubType == 14` 的 8 件（5 企业 + 3 职业）。
2. **商店要双条件**：先确认有 `sys=11` 子模块，再按
   `ContentsShopTable.BgResourceId == 活动代号`（banner 名去掉 `EVENT_BANNER_` 与尾部 `_S`）。
   只按 banner 匹配 → 无地图活动凭空多 42 项。
3. **一次性 / 可重复不混算**：`15_收益汇总` 分两段，**同段内同名相加，绝不跨段累加**。
   混了会把「每日 5 张门票」当一次性产出。

**已知偏差（登记，不许改脚本去凑）**：复算与归档在 **79/84** 期逐值一致；
5 期（`40001` / `40006` / `80100` / `80200` / `81600`）「一次性主机」低 2~23，
原因是 2022~2023 旧结构把主机塞进了挑战首通或地图产出。

### 7. 个人主页装饰（称号 / 头像框 / 名片 badge）

**四层，只查一层必漏。**

| 层 | 表 | 本期实测 |
| :-- | :--- | --: |
| 称号本体 | `UserTitleTable` | **250 行** |
| 称号装配 | `UserTitleAssemblyTable` | **182 行** |
| 名片 badge | `ProfileCardObjectTable` 的 `type1-sub3` | **166 行**（总表 654） |
| 资料文本 | `Locale_Profile` 的 `title_*` / `badge_*` | — |

```bash
# 打快照（一期一次，退出前跑）
python profile_assets.py --snapshot <基线目录>/00_基线_对象名

# 与基线 diff，出新增清单
python profile_assets.py --baseline <基线目录>/00_基线_对象名 --tsv <输出>/新增清单.tsv
```

**`UserTitleTable` 250 行分四块**（别一律叫「新称号」）：

| Id 段 | 类别 | 条数 |
| :--- | :--- | --: |
| `1~137` | 系统成就 | 40 |
| `201~241` | **活动称号**（一期一条，键后缀 = 活动代号） | 41 |
| `1007~5184` | 角色称号 | 169 |
| `10000~10002` | 特殊 | 3 |

活动称号可机检：`Id 240 = USERTITLE_NAME_COINRUSHSHOWDOWN` ↔ `EventManager 83400`。

**头像框必须按 `Id` 差，不许按 `ResourceId` 差** —— 实测：

```
UserFrameTable        326 行 / 236 个唯一 ResourceId
  其中 icn_soloraid_*  153 行 / 126 个唯一 ResourceId / 42 个 Boss 族（33 族 3 档 + 9 族 6 档）
  博物馆复刻 Id 20011~20093   27 行，ResourceId 与旧段 27/27 完全重合
```

那 27 行是**复刻框**，全部复用旧 `ResourceId`。按 `ResourceId` 差 → 一个都看不出来 → 误报「本期无新增头像框」。

**「个人主页称号」在客户端里是 `ProfileCardObjectTable` 那 166 条 badge**，
`ResourceId` 是裸数字（如 `"90"`），名字在 `Locale_Profile:badge_<id>_name`。
它和 `UserTitleTable` 是**两条独立下发链**。

---

## 校验

| # | 项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 表清单 | `list_lss_tables.py` 输出的表数 > 0，且每张有行数 |
| 2 | 抽样 | 随机抽 3 行，`Key` 与 `Value` 都非空 |
| 3 | 数值可信 | 抽 1 个技能，10 级数值单调递增（不递增就要查是不是取错表） |
| 4 | 口径 | 同一个数值在 JSON 与 `Locale_*` 文案里能对上（名称、倍率各自来源要写清） |
| 5 | 活动模板可复现 | `event_template_probe.py --event <id>` 的 15 口径能重跑出同一组数；与同组上期差 ≥3 项要能说出差在哪 |
| 6 | 头像框按 `Id` 差 | 上报的新增数来自 `Id` 集合差，**不是** `ResourceId` 差（后者会漏掉全部复刻框） |
| 7 | 称号四层都 diff 过 | 本体 / 装配 / badge / 文本，四层各自给出新增数，0 也写 0 |

---

## 失败退路

| 现象 | 处理 |
| :--- | :--- |
| `sqlite3` 打不开 | 没解密。先 `nkdb_dec.py`，产物应是 SQLite 头 `SQLite format 3\0` |
| mpdump 报未覆盖的类型 | **停**。判断是否影响本次交付；不影响就绕开，影响就问用户，不许硬解 |
| 表名搜不到 | 换桶（`saus` / `core` 都可能），或该表本期未上线。**不许用「应该叫 xxx」代替** |
| 数值与游戏内不符 | 先查是不是 1 级 vs 10 级，再看是不是取错表（`SkillTable` vs `SkillInfoTable`） |
| 活动模板「一次性主机」比上期低 2~23 | 先查是不是 2022~2023 的旧结构（5 期已知偏差）。**登记，不许改脚本去凑** |
| 头像框新增数为 0 但确实出了新框 | 用了 `ResourceId` 差。改按 `Id` 差重跑 |
| 称号基线 `LocaleKey` 全空 | 旧坏快照（取错字段名）。重建快照后再 diff，否则新增数假性为 0 |

---

## 关联

- 表清单与字段陷阱 → `reference/静态表清单.md`
- 5 语文本 → Skill `05-text-locale`
- 活动奖励模板的 17 页页序与简版选页 → `reference/活动模板.md`
- 称号 / 头像框的归族与档位规则 → `reference/个人主页.md`
