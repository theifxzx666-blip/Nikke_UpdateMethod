# 章节大地图与点位

## 一、三段链路：GUID → 脚本字段 → Transform

```
campaignlevelmapgroup_assets_<战场代号>_<hash>.bundle      （core 桶）
  └─ GameObject
       ├─ MonoBehaviour（NK.Field 系列）  带 _positionId(GUID) + 业务字段
       │    · StageSpawner._stageId       关卡刷新点
       │    · ItemSpawner._itemId         道具刷新点
       └─ Transform.m_LocalPosition       该点位的世界坐标
```

三者拼起来，地图就还原了。`_positionId` 是跨表关联的主键，**不要用名字匹配**。

## 二、取点位

```bash
python extract_map_points.py <bundle> <FieldMapData.json> <输出前缀>
```

产物：带关号的坐标 tsv（世界坐标 x / z）。这份 tsv 是后续两步的唯一输入。

## 三、渲底图

```bash
python render_map.py <模型bundle> <章号如 010> <out.png> [--scale N]
```

链路：

```
campaignmapmodelgroup(hd) bundle
  → Mesh `fcbg_cityforest_010_bg_01`（地面，4 个 submesh，各绑一张 bg_0X 图集）
  → 解 m_CompressedMesh（顶点 / UV / 三角索引）
  → World(Transform 链) → 投影到 XZ 平面 → 按 UV 采样贴图 → 填三角
```

**输出与原世界坐标同尺度**，所以点位 tsv 的 x/z 可以直接叠上去，不用另做变换。

`--scale` 是「每世界单位多少像素」，决定图的分辨率，不改变坐标含义。

## 四、合成交付用的两张表

```bash
python build_map_tables.py <坐标tsv> <关卡表tsv> <章号> <输出目录>
```

| 产出 | 用途 |
| :--- | :--- |
| 章节地图点位总表 | 全量点位，给工具/数据库 |
| 关卡坐标表 | **只保留 `StageSpawner`**，便于直接画图 |

> 第二个是第一个的子集，别当成两份不同数据去核对。

## 五、判据

| # | 判据 | 通过条件 |
| :-: | :--- | :--- |
| 1 | 点位数对得上 | 与 `CampaignStageTable` 该章的关卡数一致；差一个要能说出是哪种 Spawner |
| 2 | 坐标落在图的范围内 | 点位坐标 > 底图边界 = 投影或 scale 错了 |
| 3 | `_positionId` 唯一 | 重复说明 GUID 取错（取成脚本类名了） |
| 4 | 号段连续 | 章号 47/48 的关卡号应连续，断号要登记 |

## 六、坑

| 现象 | 原因 | 处理 |
| :--- | :--- | :--- |
| 点位全挤在原点 | `Transform.m_LocalPosition` 没合成父链 | 要走父链矩阵，不能只取 local |
| 点位整体偏移一个固定量 | 地图根节点本身有位移 | 减掉根节点世界位置 |
| 点位镜像 | XZ 平面投影时轴序搞反 | Unity 是左手系，X 右 Z 前；投影到图上是 `(x, z)` |
| 底图空白 | 取错 `bg_0X` 图集，或 submesh 没合并 | 4 个 submesh 都要解，不能只取第一个 |

## 七、与战斗场景的关系

地图点位和战斗场景是**两条独立链路**：

| 项 | 战斗场景 | 章节地图 |
| :--- | :--- | :--- |
| 包 | `spotbackground(hd)` | `campaignlevelmapgroup` / `campaignmapmodelgroup(hd)` |
| 产物 | 5 阵位视角图 + 充能点 | 底图 + 点位 |
| 共用 | 无（只有「读 mesh」这件事相同） | 同左 |

**不要**指望用战斗场景的相机去渲地图，两者没有共用坐标系。
