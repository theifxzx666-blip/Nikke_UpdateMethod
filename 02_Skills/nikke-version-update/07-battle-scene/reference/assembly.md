# assembly json 字段口径

## 一、顶层字段（`sbg_001` 实测）

| 字段 | 实测值 | 含义 |
| :--- | :--- | :--- |
| `bundle` | `sbg_001.bundle` | 来源包 |
| `scene` | `sbg_001` | 场景代号 |
| `camera` | `null` | 场景级 Camera 组件。**多数战场没有**，见 §四 |
| `anchors` | 11 组 | 锚点世界坐标（`camera_position` / `aim_position` / `character_position` / `hide_position` / `cover` / `cover_1..5` / `cover_object`） |
| `slots` | 5 个 | **每个阵位**一组 `cover / camera / aim / character / hide / axes` |
| `layers` | `Near 108 / Mid 0 / Far 26 / End 33` | 视差分层归属 |
| `bbox` | `[[-155.75,-52.88,2.7],[158.76,82.36,171.5]]` | 世界包围盒 |
| `n_props` | `189` | 物体数 |
| `roots` | `noncol 103 / ground 4 / static 37 / soft 16 / cover 15 / medium 13 / hard 1` | **档位来源** |
| `kinds` | `quad 103 / mesh 86` | billboard 与网格 |
| `uvs` | `mesh 4 / planar 82` | UV 来源 |
| `textures` | 哈希 → 贴图名 | 反查贴图 |
| `props` | 189 条 | 逐物体 |

## 二、`props[]` 单条

| 字段 | 例 | 说明 |
| :--- | :--- | :--- |
| `kind` | `quad` / `mesh` | quad = billboard（贴图直接贴，无网格） |
| `name` | `sbg_cityforest_nn_plant30` | GameObject 名 |
| `root` | `noncol_object` | **根节点名**，档位与分组的唯一依据 |
| `layer` | `null` / `Near`… | 视差层 |
| `grade` | `0` | `CollisionGradeType`。**全是 0，判不出档位** |
| `cover` | `null` / `cover_1` | 属于哪个阵位掩体 |
| `tex` | `-2623265923059957057` | 贴图哈希，键到 `textures` |
| `v` | `[[x,y,z],…]` | **世界空间**顶点（已合成父链矩阵） |
| `uv` | `[[u,v],…]` | 与 `v` 等长 |
| `tri` | `[0,1,2,…]` | 三角索引，长度 = 三角数 × 3 |

## 三、`slots[]` 单条（`sbg_001` slot 0 实测）

```json
{
  "cover": "cover_1",
  "camera":  [-4.8, 0.0, 0.0],
  "aim":     [-4.9, 0.0, -0.1],
  "character": [-6.0, -2.34, 4.5],
  "hide":    [-5.4, 0.236, -0.577],
  "axes": {"right": [1,0,0], "up": [0,1,0], "fwd": [0,0,1]}
}
```

**朝向必须用 `axes.fwd / right / up`。** 这是 `camera_position` 自身 Transform 世界矩阵的三列。

> 反例：用 `aim − camera` 反推朝向。`aim` 距相机只有 0.1 单位，
> 实测 `cityforest_001` 会算成朝 −X−Z，整片战场落到相机背后，只剩 73 个三角。

## 四、相机三分支

| 情况 | 判据 | 处理 |
| :--- | :--- | :--- |
| 场景有 `Camera` 组件 | `camera != null` | 用它的 fov / near / far |
| 无 `Camera`，有 `slots[n].camera` | `camera == null` 且 slots 有值 | 位姿用 slots，**fov 用默认 60**，图上标注「默认值」 |
| 两者都没有 | 都为 null | **停**。构图无法对齐实机，不许硬渲 |

渲染约定：透视投影，画家算法（按相机空间深度降序绘制），**不做背面剔除**
（平板两面都可能朝外）。

## 五、分层能不能用来改坐标

**不能，至少现在不能。** `layers.*.scrollWidth` 在 11 套包里**全部读成 0.0**：

```json
{"Near": {"scrollWidth": 0.0, "n": 108}, "Mid": {"scrollWidth": 0.0, "n": 0}, ...}
```

这要么是真的没有视差宽度，要么是字段取错了。**「分层不改变世界坐标」这句话从未被实证**，
不要在报告里写。层归属本身（`Near/Far/End` 与 `n`）是可用的。

## 六、同名多实例

`sbg_001` 有 20 件带 ` (1)` / ` (2)` 后缀的物体。用 `name.split(" (")[0]` 归并
**会不会误并未验证**。要用就单独记一条待核，别默认安全。

## 七、跨批 schema 差异

| 来源 | 键风格 |
| :--- | :--- |
| 本项目 `build_battle_scene.py` | 长键：`root` / `name` / `v` / `tri` |
| ChargeMap `build_assembly.py` | 短键：`g` / `n` / `v` / `i` |

**同一批包，两套实现在 `sbg_001/002/003` 上产物 md5 完全相同**
（`b436c0a7…` / `67e54273…` / `ff5ffbc7…`）。所以差异只是字段命名，不是算法分歧。
交叉验证时按 md5 比，不要按字段名比。
