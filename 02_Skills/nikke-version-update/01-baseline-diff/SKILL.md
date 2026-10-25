---
name: nikke-baseline-diff
description: NIKKE 版本更新第一步——环境自检、基线快照、键集合 diff 判本期新增。当用户说"开新一期版本更新""这期新增了什么""做基线""怎么判本期新增"时使用。
---

# 01 · 基线快照与键 diff

**这一步决定后面全部工作的正确性。跳过它，就无法判断「哪些是本期新增」，只能靠名字猜。**

---

## 触发条件

- 要开一期新的停服更新采集
- 要回答「本期有哪些新角色 / 新皮肤 / 新活动 / 新主线」
- 有人说「客户端里有 X，采一下」→ 先跑本 Skill 判定 X 是不是**本期新增**

---

## 输入

| 项 | 从哪来 |
| :--- | :--- |
| 设备连接 | `adb devices` = `device`，`su -c id` = `uid=0` |
| 客户端安装目录 | 实测，见 §步骤 1 |
| 上一期基线 | `<基线目录>/<桶>_keys.txt` |
| 本期 patch notes | **必须人工确认**，写明是国际服还是国服 |

## 输出

| 文件 | 内容 |
| :--- | :--- |
| `<基线目录>/<桶>_keys.txt` | 该桶全部 bundle 名，每行一个，排序 |
| `<基线目录>/<桶>_raw_keys.tsv` | catalog 原始文件的 `文件名<TAB>md5` |
| `<基线目录>/基线说明.md` | 时间 / 版本三要素 / 各桶条目数 / 工具版本 |
| `<输出>/新增键_<期次>.tsv` | 本期新增，按前缀分族 |
| `<输出>/本期有什么.md` | 人读版：按前缀给出「新增 N 个 c###、M 个 ce###」 |

---

## 步骤

### 1. 环境自检（5 项，逐项打印，不许口头声称）

```bash
ADB="D:\WorkBuddy\Supports\platform-tools\adb.exe"
VENV_PY="D:\Codex\依赖\venv-nikke\Scripts\python.exe"

"$ADB" devices                                  # 必须 device
"$ADB" shell su -c "id"                         # 必须 uid=0
"$ADB" shell pm list packages | grep -i nikke   # 包名实测，不许沿用记忆
"$VENV_PY" -c "import UnityPy,PIL,pymupdf,openpyxl;print(UnityPy.__version__)"
ls "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

**国际服布局**（152.8.7 实测，与国服完全不同）：
```
/storage/emulated/0/Android/data/com.proximabeta.nikke/files/
├─ com.shiftup.addressables\catalog.db          （NKDB，8.5 MB）
└─ com.shiftup.patch\<桶>\{catalog.ndb, catalog.ndb.nds, raw\, chunk\}
   桶 = core / dp / saus / ja / fd / en / ko
```
**没有 `runtime_data`**（那是国服 WeGame 的布局）。`chunk\store.cdb` 是内容寻址大文件，不是独立 bundle。

> 命中多个候选目录时比 `chunk\store.cdb` 的 mtime，取最新。曾因查了废弃目录得出「命中 0%」的错误结论。

### 2. 拉 catalog 并解密

```bash
# 外部存储对 shell 不可读，先 su cp 到 /sdcard
"$ADB" shell su -c "cp '/storage/.../com.shiftup.patch/core/catalog.ndb' /sdcard/_c.ndb"
"$ADB" pull /sdcard/_c.ndb <WORK>/device/core.ndb

"$VENV_PY" nkdb_dec.py <WORK>/device/core.ndb      # → core.ndb.dec（SQLite）
```

### 3. 导出全量 bundle 名（这就是「键清单」）

```sql
-- core.ndb.dec 是 SQLite，主表 files_chunktype
SELECT key FROM files_chunktype ORDER BY key;
```

一键：

```bash
"$VENV_PY" catalog_stat.py --bucket core --out <基线目录>
# → core_keys.txt     每行一个 bundle 名，如 spotskillcutscene_assets_c870_00_cut_scene_<hash32>.bundle
# → core_raw_keys.tsv 文件名 <TAB> md5
```

**五个桶都要跑**：`core / dp / saus / ja / fd`（`en / ko` 只有 catalog、无 chunk，轻量）。
本期实测 41,051 个 bundle。

### 4. 记版本三要素（缺一不可）

| 项 | 取法 |
| :--- | :--- |
| versionName | `adb shell dumpsys package <包名> \| grep versionName` |
| catalog mtime + 字节数 | `adb shell ls -l` |
| 语音包文件数 | 数 `saus/ja/ab/*.nab` 或等价目录 |

版本号相同但热更过的情况真实存在，三要素才能唯一确定一个客户端状态。

### 5. 键 diff

```bash
"$VENV_PY" scripts/diff_keys.py \
  --old <基线目录>/core_keys.txt \
  --new <本期目录>/core_keys.txt \
  --out  <输出>/新增键_<期次>.tsv
```

输出按前缀分族（见 `reference/键族表.md`）：

```
c8xx_        新角色      3
si_          立绘        0
lw_          爆裂特写    3
ce0xx        活动        1
event_YYMMDD 更新分期    1
sdcharacter  小人        3
```

### 6. 出「本期有什么」并**与 patch notes 对账**

两者必须能对上。对不上只有两种可能：
- patch notes 里有、键 diff 没有 → 要么没更新完，要么内容不在客户端（如纯文本公告）
- 键 diff 有、patch notes 没写 → 要么是隐藏内容，要么不是本期（**这是最容易出错的方向**）

---

## 校验（4 条）

| # | 校验 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 快照可回读 | `wc -l <桶>_keys.txt` > 0，且行数 = `catalog_stat.py` 报告的条目数 |
| 2 | 抽样 hash | 随机 3 个 `catalog.ndb` 重算 md5，与 `raw_keys.tsv` 一致 |
| 3 | diff 可复现 | 同一对输入重跑，输出条目数与集合完全相同 |
| 4 | 对账 | 键 diff 的「新增」与 patch notes 的「新增」逐条能对上，差异写明原因 |

---

## 失败退路

| 现象 | 处理 |
| :--- | :--- |
| `adb devices` 非 `device` | **停**。让用户在手机上重新确认 USB 调试授权 |
| `su -c id` 非 `uid=0` | **停**。不许改用 `adb backup` 之类降级方案硬跑 |
| 分桶结构与 `core/dp/saus/ja/fd/en/ko` 不符 | **停**。客户端布局变了，重新摸，不按旧路径硬找 |
| 没有基线 | **停**。本期只能做「客户端现状盘点」，不能声称「本期新增」 |
| 键 diff 为空 | **停**。查：更新生效了吗？拿的是同一个桶吗？混服务器了吗？ |

---

## 三条纪律

1. **「客户端里有」≠「本期新增」**。每期都有大量历史累积内容（E-01）。
2. **一期只对一服**。国际服与国服内容不同，混用结论作废（E-02）。
3. **基线快照只增不改**。第二次跑基线要新建目录，不覆盖上一次的。

---

## 关联

- 键族前缀含义 → `reference/键族表.md`
- 下一步取 bundle → Skill `02-bundle-pull`
- 键 diff 结果的用途 → `00_规范/采集优先级.md`
