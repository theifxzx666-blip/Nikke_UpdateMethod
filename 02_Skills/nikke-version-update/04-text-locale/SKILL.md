---
name: nikke-text-locale
description: NIKKE 本地化文本提取——Locale_*.lss 里是 Key→11 语对照，剧情必须 Main+Sub+SideStory 三表合并。当需要"角色台词/名字""活动剧情""番外篇""卡池文案""称号""5 语对照"时使用。
---

# 04 · 本地化文本与剧情

**所有 `.lss.dec` 共用一张表结构**：`Key, ko, en, ja, zh-TW, zh-CN, de, th, fr, es, IsSmart`。
交付只取 **5 语**：`zh-CN / zh-TW / ja / en / ko`。

一句话红线：**剧情永远三表合并，缺一张就整批漏活动**（详见 `reference/剧情三表.md`）。

---

## 触发条件

- 要角色名、台词、个人剧情、咨询对话
- 要活动剧情 / 主线剧情 / 番外篇正文
- 要卡池 / 皮肤 / 称号 / 关卡的文案
- 要「同一句话在 5 个语言里各是什么」

## 输入 / 输出

| 方向 | 内容 |
| :--- | :--- |
| 输入 | `<WORK>/device/Locale_*.lss.dec`（SQLite；`.lss` 需先 `nkdb_dec.py` 解密） |
| 输出 | TSV / JSON / 每语一个 txt；剧情按 `<活动>/<语言>.txt` 分目录 |

---

## 步骤

### 1. 确认有解密缓存

`.lss` 是 SQLite，但要**先解一层 NKDB**（`nkdb_dec.py`，产物头是 `SQLite format 3\0`）。
解密结果建议集中缓存（脚本默认读环境变量 `NIKKE_DEC_CACHE`），**每期只解一次**。

```bash
export NIKKE_DEC_CACHE="D:/Codex/临时/<期次>/dec_cache"    # 或 --cache 传参
python scripts/export_locale.py --list                     # 看有哪些库、各多少行
```

本期实测 14 个 Locale 库：

| 表 | 行数 | 用途 |
| :--- | ---: | :--- |
| `Locale_Character` | 16,443 | 角色名 / 台词 / CV / 简介 |
| `Locale_NikkeEpisode` | 112,023 | 个人剧情（**最大的一本，别全量导出**） |
| `Locale_Counseling` | 44,301 | 咨询对话 |
| `Locale_Event` | 9,441 | 活动标题与说明 |
| `Locale_Stage` | 5,354 | 关卡名 / 番外篇名（`SIDESTORY_<n>_STAGE_<m>`） |
| `Locale_Skill` | 3,468 | 技能**文案**（数值不在表里，去 `SkillInfoTable`） |
| `Locale_Profile` | 2,390 | 称号 / 玩家资料 |
| `Locale_MainScenario` / `Locale_SubScenario` / `Locale_SideStory` | 150,219 / 126,796 / 11,317 | 剧情，见下 |
| 其余 | — | `CharacterCostume` 皮肤名 / `Memorial` / `LiveWallpaper` / `SubQuest` |

### 2. 先探列名，别信记忆

```bash
python scripts/export_locale.py --table Locale_Character --probe
# Locale_Character  16,443 行  列：['Key', 'ko', 'en', 'ja', 'zh-TW', ...]
```

**语言列顺序是 `ko, en, ja, zh-TW, zh-CN`，不是简中在前。** 按位置取列必错，一律按列名取。

### 3. 通用导出（点查 / 单表）

```bash
# 角色名（key 是「编号_name」后缀式，用 %\_name）
python scripts/export_locale.py --table Locale_Character --like "%\_name" \
    --out out/角色名 --format tsv

# 某角色全部台词
python scripts/export_locale.py --table Locale_Character --like "872\_%" \
    --out out/c872 --format txt

# 几个活动表并集，每语一个 txt 便于通读
python scripts/export_locale.py --table Locale_Event --out out/活动文案 --format txt
```

| 参数 | 说明 |
| :--- | :--- |
| `--table` | 表名，逗号分隔可多个；必须与库里实际表名一致 |
| `--like` | SQL LIKE，可多次（OR）；**下划线要写 `\_`**，否则被当通配符 |
| `--format` | `tsv`（Excel）/ `json`（程序）/ `txt`（人工读，每语一份） |
| `--limit` | 每表最多几行，探查用 |
| `--langs` | 默认 `zh-CN,zh-TW,ja,en,ko`；库里没有的列会 WARN 并跳过 |

每次导出都会写 `00_导出报告.tsv`：行数 + **每语言空缺数** + 参数快照。这张报告就是交付时的口径凭证。

### 4. 剧情（三表合并，不许单表导）

```bash
# ① 体检：必须「不可归组 0 条」，非 0 立刻停
python scripts/merge_story.py --check

# ② 通过后导出
python scripts/merge_story.py --out "<期次>/04_主线/04_剧情文本"
```

```
04_剧情文本/
  活动剧情/
    <活动代号>/{简中,繁中,日文,英文,韩文}.txt
    00_活动清单.tsv            活动 / 条目数 / Main 条 / Sub 条
    00_全部活动_简中合集.txt
  番外篇/
    001_SECOND AFFECTION/{五语}.txt
    00_番外清单.tsv            编号 / 篇名 / 条数
```

三条硬规则（细节见 `reference/剧情三表.md`）：

1. `Locale_MainScenario` + `Locale_SubScenario` **同时开**，SQL 同时吃 `event\_%` 与
   `d\_contents\_%`。只读 Main 会漏 46 个活动（含 ce009 整部）。
2. 活动代号正则 **`[A-Za-z0-9]+`**，不是 `[a-z0-9]+`。早期活动是 PascalCase
   （`BunnyX777` 1,289 条 / `BlueWaterIsland` 26 条），小写正则会静默丢 1,315 条。
3. 番外篇键有 `s<N>_` 与 `m_s<N>_` 两种前缀（后者 97 条），正则 `^(?:m_)?s(\d+)_`。

### 4.5 番外篇要不要交（先判口径，再导）

`merge_story.py` 默认会把番外篇一起导出。**但「表里有」≠「本期有」**：

- 判据：这 6 篇是不是本期（停服更新那一版）**新增/开放**的；
- 20260813 国际服判定为「不是」（那 6 篇是版本累积的历史内容，最近一篇 10-08 才上线）；
- 所以那一期的 `04_剧情文本/` 里**没有番外篇子目录**，产物已移入 `拆包/05_回收站/`。

重跑导出后若发现番外篇目录又冒出来，按当期口径决定留还是移出——**别默认留着**（E-01）。

### 5. 交付前的口径

- 对外报「本期多少活动 / 多少条」**只用 `00_活动清单.tsv` 的合计数**，
  不要用「表行数」或「文件数」——三个数字互不相等（见 E-22/E-23）。
- 某语言整篇为空 → 不是漏导，先看 key 形态（`quest_npc_99xxxxx` 是占位行）。

---

## 校验

| # | 项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 不可归组 | `merge_story.py --check` 输出 **0 条** |
| 2 | 活动数 | ≥ 上期（只增不减）；掉了就是正则或表漏读，**不许当"本期活动少"解释** |
| 3 | 本期新活动 | 新代号出现在 `00_活动清单.tsv` 且条数 > 0 |
| 4 | 五语齐 | 每个活动目录下恰好 5 个 txt，无 0 字节 |
| 5 | 首尾 | 抽 1 个活动：首条是序章/第 1 章第 1 句，末条是尾声或最大句号 |
| 6 | 空缺 | `00_导出报告.tsv` 里空缺集中出现在同一语言 → 查是不是占位行，不是就登记 |

---

## 失败退路

| 现象 | 处理 |
| :--- | :--- |
| `sqlite3` 打不开 / `file is not a database` | 没解密。跑 `nkdb_dec.py`，检查产物头 |
| `--like` 一条都不命中 | 该表 key 是后缀式（`872_name`），改 `%\_name`；先 `--probe` + 手工 `select "Key" limit 10` 看形态 |
| 活动数比上期少 | **停**。先跑 `--check` 看不可归组条数；再确认两张表都开了 |
| 同一活动在两个表都有条目 | 正常。合并后按代号分组，`00_活动清单.tsv` 会分别列 Main/Sub 条数 |
| 剧情顺序看着不对 | e/s 是并行双轨，真实交错在场景脚本里，**不在 locale 表**。不要为此改排序规则 |
| 某语言缺失 | 先看 `Locale_*` 是否真有该列（`--probe`）。没有就是该语言未上线，记入 `00_规范/未采与放弃.md` |

---

## 关联

- 三表分工、活动 key 形态、排序与篇名反查 → `reference/剧情三表.md`
- 静态表（技能数值 / 属性 / BOSS 零件）→ Skill `03-static-tables`
- 文本表实体在交付目录的位置 → `00_规范/目录与命名.md`「唯一源裁决表」
