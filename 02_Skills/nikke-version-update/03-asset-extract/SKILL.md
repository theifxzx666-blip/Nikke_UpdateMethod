---
name: nikke-asset-extract
description: 从 NIKKE 的 .bundle 里扒出真实资源——贴图 / 技能图标 / 立绘 / 卡池横幅 / 3D 模型 glb / 莱彻立绘与透视 / BGM / 台词配音。当需要「提取立绘」「导出图标」「模型转 glb」「莱彻立绘」「拆包出图」「BGM 导出」「语音包」时使用。
---

# 03 · 资源提取（贴图 / 模型 / 音频）

**上游给的是 `.bundle`，下游要的是能直接放进交付目录的文件。这一步就是把二者接上。**
跳过它去手写 UnityPy 遍历，会踩三类坑：压缩网格读成 0 顶点、把 0.5 厚盒子当单面平板、`m_Vertices is None` 误判成包坏了。

---

## 触发条件

- 手上已有 `.bundle`（来自 Skill `02-bundle-pull`），要出图 / 出模型 / 出音频
- 「这批角色的立绘取一下」「技能图标导出来」「莱彻立绘」「BOSS 模型转 glb」
- 「这个包里有几张图」→ 先数 Texture2D / Sprite，再决定导哪几类

## 输入

| 项 | 从哪来 |
| :--- | :--- |
| `.bundle` 文件 | Skill `02-bundle-pull` 落盘的 UnityFS |
| 静态表 JSON（可选） | Skill `04-static-tables`，用于把 id 翻成名字 |
| 输出目录 | 当期交付目录，见 `00_规范/目录与命名.md` |

## 输出

| 类别 | 产物 | 详见 |
| :--- | :--- | :--- |
| 贴图 / 图标 / 立绘 / 横幅 | `.png`（原分辨率，保 alpha） | `reference/image.md` |
| 莱彻立绘 / 透视 / 拆件 | `.png` + 装配件表 | `reference/rapture.md` |
| 3D 模型 | `.glb`（glTF 2.0 二进制） | `reference/model3d.md` |
| 音频 | `.wav` / `.mp3` + 曲目表 | `reference/audio.md` |
| 国服 NKAB 包 | 解密后的 `_dec.bundle` | `reference/cn-nkab.md` |

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
| `NIKKE_BUNDLE` / `NIKKE_NAMES` | 当期主包 / 要导的技能图标名（空格分隔，名字取自静态表） |
| `NIKKE_MODEL` / `NIKKE_PHASE` | 莱彻型号（如 `xba003`）/ 阶段目录名（如 `2phase`） |
引擎是同目录的 `runlib.py`：占位符解析 + 产物判定 + 强制 UTF-8 起子进程
（`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，否则中文控制台下 UnityPy/json 里的中文直接炸）。

## 步骤

### 0. 先认包，别急着导

```bash
python -c "
import UnityPy, collections, sys
env = UnityPy.load(sys.argv[1])
c = collections.Counter(o.type.name for o in env.objects)
print(dict(c))
" <某个.bundle>
```

数量对不上就先别导 —— 见下面「三条硬口径」。

### 1. 按目标选命令

| 要什么 | 命令 | 说明 |
| :--- | :--- | :--- |
| 技能图标（按名字挑） | `python dump_skill_icons.py <bundle> <outdir> 名字1 名字2` | 名字取自静态表，不猜 |
| 文本库里的 sprite | `python lsc_sprite.py <某表.dec> <outdir>` | `.lsc` 里是 ASTC 块数据，非加密 |
| 皮肤键全量基线 | `python export_costume.py` | 无参数，输出键→cID→名称 |
| 莱彻立绘（绑定姿态） | `python render_monster_standee.py <型号>` | 不带参渲全部 |
| 莱彻透视 / 拆件 | `python render_monster_xray.py` | 外壳 30% 透明，让内部核心显形 |
| 网格正确性自检 | `python verify_skin.py` | 直出 vs 蒙皮，偏差大说明部件会错位 |
| 模型转 glb | `python export_glb.py <型号> <阶段>` | 例 `export_glb.py xba003 2phase` |
| 动画把模型搬出画面 | `python fix_glb_offset.py --all` | 先 `--dry` 看命中 |
| BGM | `python build_bgm.py` | 裸 WAV 原位改名 + 转 mp3 + 曲目表 |
| 台词配音包 | `python build_voice_pack.py` | 默认 c870/c871/c872，改顶部常量 |
| 大地图上的莱彻 | `python scan_map_monsters.py` | 从模型包反查型号，接中文名 |

### 2. 每个导出都必须打印自检

任何导图 / 导模型的脚本，结束前必须打印这四个数，缺一不可：

```
objects / triangles / vertices / ratio
```

`ratio = triangles / vertices`。判定见下节。看不到这四个数就当失败，不要往下游走。

## 校验

| # | 判据 | 通过条件 |
| :-: | :--- | :--- |
| 1 | **三角面/顶点比值** | **≥ 1.5**。实测正常 1.88、只取一层 0.91、纯 quad billboard 场景 0.5（例外，见下） |
| 2 | 三角面非 0 | 为 0 说明网格没读出来。查 `m_VertexData.m_DataSize` 是否为空、`m_IndexBuffer` 是否 `list[int]` |
| 3 | 图片非全透明 | 抽 3 张算 alpha 均值，接近 0 说明 UV 或取景错了 |
| 4 | glb 有动画 | `animations > 0` 且通道数 > 0，否则导出的是个不动的模型**且不报错** |
| 5 | 音频可播 | 采样率 44100 / 16bit / 立体声；纯静音说明取错了流 |

## 三条硬口径（都是实测推翻过的直觉）

### ① `m_Vertices is None` ≠ 包坏了

高层接口 `obj.read().m_Vertices` 对一批包返回 `None`，但 `read_typetree()` 里：

```
m_VertexCount = 112 / m_DataSize = 1344 / m_Channels[0].format = 0   ← Float32，未压缩
```

`format = 0` 就是没压缩。**不要因此去加 `MeshHelper` 补丁，也不要另写适配器。**

### ② 网格必须全取，不许只取 z 最小层

「所有原生 mesh 都是 0.5 厚平板，只导 z 最小那层」这句是错的。实测
`sbg_cityforest_c_desk06_03`（298 顶点 / 588 三角）：

| 分布 | 三角数 | 占比 |
| :--- | --: | --: |
| 全在 z=0 | 144 | 24.5% |
| 全在 z=0.5 | 144 | 24.5% |
| **跨两层（侧壁）** | **300** | **51%** |

只取 zmin → 侧壁全丢 → 该挡的没挡住 → **段数偏高且不报错**。

### ③ 比值 1.88 与 0.91 的来历

| 场景 | 比值 | 结论 |
| :--- | --: | :--- |
| 正常（三包实测） | 1.88 / 1.88 / 1.88 | 通过 |
| 只取一层 | 0.91 / 0.92 / 0.90 | 病态，判失败 |
| 纯 quad billboard | 0.5 | 例外（1 quad = 4 顶点 2 三角） |

**门限 `< 1.5` 判失败。** 纯 quad 场景要先看 `kinds` 里是不是只有 `quad`。

## 失败退路

| 现象 | 处理 |
| :--- | :--- |
| `objects` 为 0 | **停**。包没解压或拿错包，回 `02-bundle-pull` 重拉 |
| 三角面 0 但顶点正常 | **停**。索引没读出来，查 `m_IndexBuffer` 是不是 `list[int]`（每项一字节，先 `bytes(b & 0xFF)` 再 `unpack("<%dH")`） |
| 比值 < 1.5 | **停**。先确认有没有只取一层；不是的话报实测数，别硬导 |
| 立绘四边有触边像素 | **停**。取景框算小了，改 `build_anim_framing` 的包络，别逐张手调 |
| 看得到模型背面 | **停**。朝向反了，Unity 约定角色朝 +Z，相机在 +Z 侧沿 −Z 看 |
| 莱彻核心看不见 | 正常现象。绑定姿态下 `cm_core` 被外壳完全包裹，用透视版脚本，别以为是丢件 |

## 关联

| 参考 | 内容 |
| :--- | :--- |
| `reference/image.md` | 贴图 / 图标 / 立绘 / 横幅 + **GIF 编码五条要点**（预乘 alpha / 二值化 / FASTOCTREE / `putpalette` / 透明索引） |
| `reference/rapture.md` | 莱彻与关底 BOSS：型号族、两阶段、装配件、判定表 |
| `reference/model3d.md` | glb 导出与修复、动画取景、Three.js 查看器部署 |
| `reference/audio.md` | BGM 与台词配音链路 |
| `reference/cn-nkab.md` | **国服专用**：NKAB v4 → NAU 解密 → AssetStudioCLI 兜底 |

上下游：`02-bundle-pull` → **本 Skill** → `06-spine-render`（动画）/ `08-deliver-pdf`（出报告）
