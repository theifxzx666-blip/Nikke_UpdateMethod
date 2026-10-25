---
name: nikke-bundle-pull
description: 从 NIKKE 客户端按 bundle 键取回原始资源包——键到 chunk 到 store 偏移到 zstd 拼装到 UnityFS。当需要"拉包""取这个角色的资源""bundle 怎么拿下来""cache 里哪个文件是这个"时使用。
---

# 02 · 从键取回 bundle

**国际服用内容寻址存储（`store.cdb` + `.idx`），没有独立 bundle 文件。**
一次只取需要的字节段，不需要拉 20 GB 整库。

---

## 触发条件

- 已有一批「本期新增」的 bundle 键（来自 Skill `01-baseline-diff`）
- 要取某个角色的立绘 / 爆裂 / 大厅动画 / BOSS 模型

## 输入 / 输出

| 方向 | 内容 |
| :--- | :--- |
| 输入 | `catalog.ndb`（解密后的 SQLite）+ bundle 键清单 |
| 输出 | `<WORK>/device/<桶>.bundle`（`UnityFS\0` 开头）+ `<WORK>/device/<桶>.json`（UnityPy dump） |

---

## 链路（6 步，每步断言）

```
catalog.ndb(.dec)                     ← SQLite
   │  files_chunktype: key → file_id
   ▼
chunk_file_map: file_id → [(file_offset, chunk_id)]
   │
   ▼
chunks: chunk_id → (hash, compressed_size, original_size)
   │  store.cdb.idx 查 hash → store 内绝对偏移
   ▼
store.cdb ── 块对齐 dd 取连续段 ──→ 本地切出各 chunk
   │  zstd 解压（魔数 28 b5 2f fd），长度 == original_size
   ▼
按 file_offset 升序拼接，断言 file_offset == 已拼长度
   │
   ▼
UnityFS bundle → UnityPy
```

### 1. 定位（`locate.py`）

```bash
"$VENV_PY" locate.py --bucket core --key spotskillcutscene_assets_c871_00_cut_scene_18e7….bundle
```

输出该 bundle 的 `(chunk_id, file_offset, hash, compressed_size, original_size)` 列表。

**`.idx` 文件格式**（实测）：

| 段 | 长度 | 内容 |
| :--- | :--- | :--- |
| 头 | 12 B | magic `CIDX` |
| 记录 | 28 B × n | 16 B hash + 8 B 绝对偏移 + 4 B 压缩长度 |
| 尾 | 16 B | — |

### 2. 块对齐取段（**关键，别逐 chunk dd**）

同一 bundle 的 chunk 在 `store.cdb` 里基本连续（实测 91 个 chunk 落在 3.91 MB 单段）。

```python
lo_al = lo // 4096 * 4096
# dd if=store.cdb of=x.bin bs=4096 skip=<lo_al/4096> count=<ceil((hi-lo_al)/4096)>
# 本地跳过 (lo - lo_al) 字节后再切
```

### 3. 解压

- 魔数 `28 b5 2f fd` = Zstandard
- 解压后长度**必须等于** `original_size`，不等就是取错段了
- 扩展名不可信，只看魔数

### 4. 拼装

按 `file_offset` 升序拼，**每拼一段断言 `file_offset == 已拼长度`**。
不断言会拼出一个「看起来能开、图片全是花屏」的坏包。

### 5. 一键

```bash
"$VENV_PY" pull_bundle.py --bucket core --key <键>
```

- 大包（> 50 MB）用 `pull_chunks.py` 逐 chunk 取，断点可续
- **一次只拉一个**：`pull_bundle.py` 落地文件名固定为 `<桶>.bundle`，连续拉会互相覆盖
  （`pull_boss_assets.py` 就是为了绕开这点才另写的——每拉完立刻重命名）

### 6. 校验

```bash
"$VENV_PY" scripts/verify_pull.py <x.bundle>
```

| 检查 | 通过条件 |
| :--- | :--- |
| 头部 | 前 8 字节 = `UnityFS\0` |
| 大小 | 等于各 chunk `original_size` 之和 |
| 可解析 | UnityPy 能 load，对象数 > 0 |
| 抽样 | 第一个 Texture2D 能导出 PNG 且非全黑 |

---

## 本机坑（全部实测）

| 现象 | 根因 | 处理 |
| :--- | :--- | :--- |
| bundle 被写坏且不报错 | `adb exec-out` 的 stdout 做了 LF→CRLF 转换 | **只用 `adb pull`**；批量先设备侧 `tar` |
| 文件名被截断/乱码 | 设备路径含中文或特殊字符 | 设备侧先落 ASCII 临时名，pull 回来再改 |
| `Test-Path` 误判 | PowerShell 把 `[` `]` `(` 当通配符 | 一律 `-LiteralPath` |
| 大量 cache 文件报「需解密」 | 默认以为 `NKAB` 全需解密，实际很多是明文 `UnityFS` | **先读 8 字节判头部** |
| `File cab-xxx not found` | 纹理在别的 bundle | `UnityPy.load(*所有相关 path)` 合并环境 |
| grep `CAB-<hash>` 有假阳性 | 同一 CAB 名出现在十几个 bundle 的依赖表里 | 读每个 bundle 内**真实文件名** |
| 取到的图片尺寸不对 | 用了 `len(arr)` 当像素数（传 `(N,4)` 时碰巧对，传 flat 时虚报 4 倍） | 用 `arr.size // 4` 或直接 `Texture2D.image` |

---

## 失败退路

| 情况 | 处理 |
| :--- | :--- |
| 键在 catalog 里查不到 | 键拼错了，或该包不在这个桶。**五个桶都试一遍**再报错 |
| `.idx` 里查不到 hash | 该 chunk 未下载到本机 → 需先在游戏里触发一次加载，或从 CDN 补 |
| 解压长度不匹配 | 取段偏移算错了，回 §1 重算。**不要硬拼** |
| UnityPy 打不开 | 先看头部是否 `NKAB`，是则走 NAU 解密；产物以「头部为 `UnityFS`」为准，**不信 NAU 的返回码** |

---

## 关联

- 键 → 包名的对应规律 → `01-baseline-diff/reference/键族表.md`
- 解包后的处理 → Skill `03-static-tables` / `04-text-locale` / `05-spine-render`
- 环境常量 → `00_规范/技术选型.md` 第零节
