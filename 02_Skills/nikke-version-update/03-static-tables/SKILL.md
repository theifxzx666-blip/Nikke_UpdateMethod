---
name: nikke-static-tables
description: NIKKE 静态表与文本库提取——.lss/.lsc 实为 SQLite，用 mpdump 导静态表 JSON。当需要"技能数值""角色属性""BOSS 零件""表结构""lss 里有什么"时使用。
---

# 03 · 静态表与文本库

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
具体做法见 Skill `04-text-locale`。

---

## 校验

| # | 项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 表清单 | `list_lss_tables.py` 输出的表数 > 0，且每张有行数 |
| 2 | 抽样 | 随机抽 3 行，`Key` 与 `Value` 都非空 |
| 3 | 数值可信 | 抽 1 个技能，10 级数值单调递增（不递增就要查是不是取错表） |
| 4 | 口径 | 同一个数值在 JSON 与 `Locale_*` 文案里能对上（名称、倍率各自来源要写清） |

---

## 失败退路

| 现象 | 处理 |
| :--- | :--- |
| `sqlite3` 打不开 | 没解密。先 `nkdb_dec.py`，产物应是 SQLite 头 `SQLite format 3\0` |
| mpdump 报未覆盖的类型 | **停**。判断是否影响本次交付；不影响就绕开，影响就问用户，不许硬解 |
| 表名搜不到 | 换桶（`saus` / `core` 都可能），或该表本期未上线。**不许用「应该叫 xxx」代替** |
| 数值与游戏内不符 | 先查是不是 1 级 vs 10 级，再看是不是取错表（`SkillTable` vs `SkillInfoTable`） |

---

## 关联

- 表清单与字段陷阱 → `reference/静态表清单.md`
- 5 语文本 → Skill `04-text-locale`
