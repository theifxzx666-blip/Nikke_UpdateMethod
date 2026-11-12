---
name: nikke-battle-scene
description: 把 NIKKE 的 spotbackground 关卡包重建成可看的 3D 场景——装配 world 顶点/UV/贴图/阵位/档位，按实机相机做透视投影，再扫多判充能点、还原章节大地图点位。当需要「战斗场景还原」「这个关卡长什么样」「充能点在哪」「地图点位」「5 个阵位」时使用。
---

# 07 · 战斗场景与地图还原

**输入是一个 `spotbackground` 包，输出是一张能对着实机核对的图 + 一份可算充能的 json。**
这一步是唯一会「导出成功但数字全错」的环节：遮挡算错不会报错，只会让段数偏高。

---

## 触发条件

- 「战斗场景还原」「sbg 包怎么变图」「这个关卡长什么样」
- 「多判充能点」「一枪能穿几件」
- 「章节大地图」「点位坐标」「关卡在地图哪个位置」
- 手上已有 `spotbackground(hd)_assets_sbg_<场景>_<hash>.bundle`（core 桶）

## 输入

| 项 | 从哪来 |
| :--- | :--- |
| `.bundle` | Skill `02-bundle-pull`，core 桶，键以 `spotbackground` 开头 |
| 关卡表 / 场景代号 | Skill `04-static-tables`（`CampaignStageTable` 等） |

## 输出

| 文件 | 内容 | 详见 |
| :--- | :--- | :--- |
| `assembly_<场景>.json` | world 顶点 / UV / 贴图 / 阵位 / 档位 / 分层 | `reference/assembly.md` |
| `<场景>_s1..s5.png` | 五个阵位的实机视角图 | `reference/assembly.md` |
| `<场景>_总览.png` | 广角框住 5 个阵位 | 同上 |
| `charge_multi_<场景>.json` + `.tsv` | 多判充能点 | `reference/charge.md` |
| 地点点位 tsv / 大地图 png | 章节地图 | `reference/map.md` |

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
| `NIKKE_BUNDLE` / `NIKKE_TAG` | 当期战场包 / 短名（如 `sbg_001`，用来命名产物） |
| `NIKKE_FIELDMAP` / `NIKKE_CHAP` | 地图数据 JSON / 章号（地图链路才要） |
引擎是同目录的 `runlib.py`：占位符解析 + 产物判定 + 强制 UTF-8 起子进程
（`PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1`，否则中文控制台下 UnityPy/json 里的中文直接炸）。

## 步骤

### 1. 装配（先出 json，再谈图）

```bash
python build_battle_scene.py <bundle> <out.json>
```

正常输出长这样（`sbg_001` 实测）：

```
bundle 内对象 2035 个
mesh 81 / 材质 4 / 贴图 135 / Sprite 130
物体 189（mesh 86 / quad 103）
根分组 {'noncol_object': 103, 'ground': 4, 'static_object': 37,
        'soft': 16, 'cover_object': 15, 'medium': 13, 'hard': 1}
分层 {'Near': 108, 'Mid': 0, 'Far': 26, 'End': 33}
UV 来源 {'mesh': 4, 'planar': 82}
```

**四个数必须都打印出来**：`props / tri / vert / ratio`。看下节判据。

### 2. 渲图

```bash
python render_overview.py <asm.json> <bundle> <out.png> [--w 1800] [--pitch 42] [--dist 30]
python render_battle_scene.py <asm.json> <bundle> <out.png> --slot 1
```

### 3. 扫充能点

```bash
python scan_charge_multi.py <asm_1.json> <asm_2.json> <asm_3.json>
python mark_charge_multi.py            # 已渲好的图上落点
```

### 4. 地图（另一条链路，独立）

```bash
python extract_map_points.py <bundle> <FieldMapData.json> <输出前缀>
python render_map.py <模型bundle> <章号> <out.png> [--scale N]
python build_map_tables.py <坐标tsv> <关卡表tsv> <章号> <输出目录>
```

## 校验

| # | 判据 | 通过条件 |
| :-: | :--- | :--- |
| 1 | **三角面/顶点 ≥ 1.5** | 实测正常 1.88；只取一层 0.91。`< 1.5` 判失败（通则见 Skill `03-asset-extract`） |
| 2 | **props 数对得上** | 三包实测 189 / 122 / 206。差一两个要能说出是哪个被过滤了 |
| 3 | **`ground` 不为 0** | `ground = 0` 说明 `*_col` 没滤掉或滤过头，射线会撞隐形地板 |
| 4 | **每阵位都有相机** | `slots[n].camera` 为空说明锚点没读到，渲出来的构图必错 |
| 5 | 图上无穿模/无落地 | 逐张看：物体悬空或插进地面 = 世界矩阵合成错 |

## 三条硬口径

### ① `*_col` 地形碰撞网格必须滤掉

`sbg_cityforestunder_ground_col` 这类**不是可视美术**，混进来会：

- 糊住画面
- 让射线在第一米就撞上「隐形地板」→ **段数全归零**

过滤后 `ground` 从 5 → 4，与独立实现一致。

### ② 档位只有一个来源：root 节点名

`CollisionGradeType`（`q` 字段）在 soft / medium / hard / static / noncol 里**全是 0**，
cover / ground 是 −1 —— 它只表「可穿 / 不可穿」，**判不出档位**。

名字前后缀也不能判：`_h` 后缀命中率仅 1/3
（反例：`dm_structure02_h`、`df_billboard31_h` 实为 medium）。

**唯一可靠来源是 GameObject 根节点名**：`soft_object_*` / `medium_object_*` /
`hard_object_*` / `static_object_*` / `noncol_object_*` / `cover_object_*`。

### ③ 1° 窗口是椭圆，不是 ±R 像素

@1600×900 / 纵向 fov 60：

| 方向 | 换算 |
| :--- | :--- |
| 横向 | **26.67 px/°** |
| 纵向 | **12.51 px/°** |

所以「1° 窗口」= **±13.3 × ±6.3 px 的椭圆**，与「±R px」不等价。
把这两者混用会让充能点数虚高。

## 失败退路

| 现象 | 处理 |
| :--- | :--- |
| `props = 0` | **停**。拿错包或网格没读出来，回 `03-asset-extract` 的硬口径 |
| 三角面 0 / 比值 < 1.5 | **停**。侧壁丢了，段数会偏高，不许往下算充能 |
| `ground` 数对不上 | **停**。查 `*_col` 过滤条件 |
| 渲出来整片战场在相机背后 | **停**。朝向不能用 `aim − camera` 反推（aim 距相机仅 0.1），要用 `slots[n].axes` 的 fwd/right/up |
| 相机 `camera = null` | 允许。无 `Camera` 组件时 fov 默认 60 / near 0.1 / far 300，**图角要标注「默认值」** |
| `layers.*.scrollWidth` 全 0 | 已知未解。11 套全部读成 0.0，字段可能取错；**不许**据此声称「分层不改变世界坐标」 |

## 关联

| 参考 | 内容 |
| :--- | :--- |
| `reference/assembly.md` | json 字段逐个含义 + 世界矩阵合成 + 阵位 |
| `reference/charge.md` | 充能算法：角度枚举 vs 像素枚举、遮挡规则、与 ChargeMap 的口径差异 |
| `reference/map.md` | 大地图点位三段链路：GUID → 脚本字段 → Transform |

上下游：`02-bundle-pull`（取包）→ **本 Skill** → `08-deliver-pdf`（出报告）
