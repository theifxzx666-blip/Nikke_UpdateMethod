---
name: nikke-spine-render
description: Spine 动画离线渲成 GIF/WebP/首帧——headless Chrome + CDP 定帧，多层叠加、分位取景、空帧合并。当需要"大厅站立动画""爆裂特写动图""立绘动效""骨骼渲染"时使用。
---

# 05 · Spine 渲染

**路线：headless Chrome 里跑 Spine WebGL 运行时 → CDP 调 `window.__spine.seek(t)` 定帧 →
`canvas.toDataURL()` 取像素 → PIL 合成 GIF。**

不装 unity、不导 glTF、不用 ImageMagick。渲染器是自带的 `renderer/index.html`（345 行，
所有坑都写在注释里），依赖已 vendored（4.7 MB，`spine-core` + `spine-webgl`），**离线可用**。

---

## 触发条件

- 大厅站立动画 / 爆裂特写 `spotskillcutscene` / 立绘动效要出 GIF
- 静态首帧不够，要「动起来」证明演出效果
- 已经有 `.skel + .atlas + .png` 三件套（没有就先去 Skill `02-bundle-pull` 拉包）

## 输入 / 输出

| 方向 | 内容 |
| :--- | :--- |
| 输入 | `<name>.skel` + `<name>.atlas` + `<name>.png`（同目录同名） |
| 输出 | `<name>.gif`（主交付）/ `<name>.webp`（体积 3~5 成）/ `<name>_首帧.png` / `<name>_全帧网格.png`（验收） |

---

## 步骤

### 1. 摆目录

```bash
<WORK>/spine_render/
  index.html          # ← renderer/index.html 原样拷
  vendor/             # ← renderer/vendor 原样拷（必须有）
  assets/<name>/<name>.{skel,atlas,png}
  _prof_exp/          # Chrome 临时 profile，跑完删
```

### 2. 起静态服务（必须，不能 file://）

`file://` 下 ES module import + fetch 全被拦。在 `spine_render/` 里：

```bash
python -m http.server 8766
```

URL 形态：`http://127.0.0.1:8766/index.html?asset=assets/<name>/<name>&ui=0&ss=2`

### 3. 渲染器参数（`?` 后面这些）

| 参数 | 作用 | 什么时候用 |
| :--- | :--- | :--- |
| `asset` | 三件套路径（不带扩展名） | 必填 |
| `ss` | 超采样倍数，默认 2 | 输出长边 ≤ 1000 时保持 2 |
| `ui=0` | 隐藏左上角 HUD | 出图必加，否则文字被截进画面 |
| `layers=a,b,c` | **同一骨架多实例叠加**，先写的画在下面 | 爆裂特写必须用（见下） |
| `fit=<层号>` | 只用第 N 层取景 | 有背景层/特效层时必用 |
| `fitq=0.9` | 取景用分位数，丢两端极端帧 | 特效飞出画面时 |
| `hide=<层号,…>` | 只参与取景、不参与绘制 | 借别的动画当取景参照 |
| `anim` | 指定动画名（默认 idle→lobby→最长） | 单动画时 |

### 4. 三个「必须」

**① 不要用 `Page.captureScreenshot`。**
合成器异步，连拍会拿到上一帧。必须 `window.__spine.seek(t)` → `window.__spine.capture()`（同步读 canvas）。

**② 取景框用整段动画的并集包围盒，不能逐帧自适应。**
逐帧算会让角色「呼吸」——每帧缩放比都不一样，GIF 看起来像在抽搐。

**③ GIF 帧延迟只有 10 ms 粒度，帧数要反解。**
不能按 `dur × fps` 直接算。用 `plan_frames()`：在 20~200 ms 网格上遍历，
`n = round(dur*1000/ms)`，取「时长误差 + fps 偏离」加权最小的组合。

### 5. 多层叠加（爆裂特写专用）

爆裂特写是 **一个 skel 里既有人物层又有背景板/特效层**，Timeline 用两条 Spine 轨道
同时驱动两个 SkeletonAnimation 实例。**单播一条只能画出局部**：

- c872 的 `skillcut_1` 只有头 + 双手，`bg_skillcut_1` 是空画面
- c870 的 `skillcut_1` 是漫画卡面，`skillcut_2` 是机车场景 —— 两条才是完整演出

所以出图必须写明层序。本期实测配置（`export_cutscene_gif.py` 里的 `JOBS`）：

| 角色 | layers | fit | fitq | hide | trim |
| :--- | :--- | :-: | :-: | :-: | :-: |
| QUEEN（真）c870 | `idle, skillcut_2, skillcut_1` | 0 | 1.0 | `0` | 0.65 s |
| 雪子 c871 | `skillcut_1, skillcut_0` | 1 | 0.9 | — | 0.95 s |
| 埃癸斯 c872 | `bg_skillcut_1, skillcut_1` | 1 | 0.9 | — | 0 |

- **c870 的 `idle` 不属于爆裂**（它在另一个 Timeline 里，是壁纸循环）。把它当卡面层叠进去，
  4 秒全是同一张静止卡面，真演出被压在下面。正确做法：挂第 0 层 + `hide=0`，
  只借它的包围盒（4500×4381 正好是卡面大小）取景。
- **`trim` 是裁掉开头**：0~0.1 s 是淡入前空窗（渲出来纯黑）；c871 的 0~0.95 s 是
  卡面被压成一条白线的极端缩放帧，覆盖率 2~11%，**躲得过空帧阈值**，必须显式裁。

### 6. 逐帧取像素

```python
for i in range(n):
    t = start + ((i + 0.5) / n) * dur        # 帧中心采样，从演出窗起点算
    cdp.ev(f"window.__spine.seek({t:.6f})")
    frames.append(to_img(cdp.ev("window.__spine.capture()")))
```

渲染用 `css_h = long/2`、`ss=2`，最后 `resize((out_w, out_h), LANCZOS)` 降采样 —— 抗锯齿靠超采样，不靠 `antialias:true`。

### 7. 合成

| 格式 | 用法 |
| :--- | :--- |
| GIF | `quantize(MEDIANCUT)` + 首帧做调色板参照 + `duration` 逐帧可不同 |
| WebP | `quality=92, method=4`，体积通常只有 GIF 的 3~5 成，优先给 WebP 版 |

空帧处理：覆盖率 < 0.5% 的帧**并入相邻帧**（`durs[-1] += delay`），总时长不变。
首帧为空则靠 `carry` 顺延给下一帧。

**首帧 PNG 取「覆盖率最高」那帧，不是第 0 帧**——演出席开头是淡入，第 0 帧常常是全黑。

### 8. 验收：全帧网格

```bash
python scripts/check_gif.py <gif 或目录> --out <验收目录>
```

出 `<name>_全帧网格.png`：每格标「帧号 + 覆盖率%」，空帧描红框。同时打印帧数 / 时长 /
间隔 / 动幅 / 最低覆盖率。**这张图必须人眼看一遍再交付**（E-19）。

动幅算法：最多取 7 帧**两两比对**取最大平均像素差。不能用「首帧 vs 半周期帧」——
循环动画在半周期常回到近似姿态，会算出接近 0 误判成静止。

---

## 校验

| # | 项 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 全帧网格 | `check_gif.py` 退出码 0；人眼看完无黑帧、无抽搐 |
| 2 | 空帧 | 0 个；有就必须已并入相邻帧（报告里会写合并数） |
| 3 | 动幅 | ≥ 0.2%（低于就是静止图，渲染层选错了） |
| 4 | 层序 | 报告里的 `layers` 与实际画面一致；少一层就是「只画出局部」 |
| 5 | 帧数/时长 | `real_n × delay ≈ clip`，误差 < 5% |
| 6 | 首帧 | 覆盖率 > 20%，且能看出主体（不是淡入第一帧） |
| 7 | 清单 | `_manifest*.json` 是**合并写**，补导不冲掉旧记录（E-20） |

---

## 失败退路

| 现象 | 处理 |
| :--- | :--- |
| 首帧纯黑 | setup pose 全隐藏。`seek(0)` 也要 `update(1e-6)` 推一步（`advance()` 已处理） |
| 偶发个别帧纯黑（连拍时） | 上一帧的隐藏槽位残留。`seek()` 里每帧先 `setToSetupPose()`（已处理）；仍有就靠空帧合并兜住 |
| 角色缩成一个点 | 取景框混进了背景层/特效层。用 `fit=<人物层号>`，或 `fitq=0.9` |
| 画面里多了不该有的东西 | `hide=<层号>` 只取景不画 |
| 只画出局部（半个身子/空画面） | 少叠了一层。去看骨架里有哪些动画，`layers` 补齐 |
| WebGL 起不来 | headless 加 `--disable-gpu`（走 SwiftShader 软渲染，慢但稳）；`--remote-allow-origins=*` 不能省 |
| Chrome 连不上 CDP | 端口被占（默认 9415）。`/json` 探活失败就先杀残留 chrome，再删 `_prof_exp` |
| GIF 比预期小很多帧 | PIL `optimize` 合并了连续相同帧。清单里的帧数要用 `ImageSequence` 数**实际**帧，不要记渲染帧 |

---

## 关联

- 取包（拿三件套）→ Skill `02-bundle-pull`
- 验收网格工具 → `scripts/check_gif.py`
- 驱动脚本（单一源，不在此复制）→ `<ROOT>/05_脚本/主线/export_lobby_gif.py`（大厅）、
  `export_cutscene_gif.py`（爆裂，含 `JOBS` 表）
- 渲染器本体 → `renderer/index.html`（参数与坑都写在注释里）
