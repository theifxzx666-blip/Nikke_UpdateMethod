# 3D 模型与 glb

## 一、导 glb

```bash
python export_glb.py <型号> <阶段>              # 例：export_glb.py xba003 2phase
python export_glb.py <型号> <阶段> --anim <bundle>
python export_glb.py all                        # 全部型号
```

产物是 glTF 2.0 二进制（`.glb`），Three.js / Blender 直接能打开。

**三角形缠绕顺序不做翻转，改用 `doubleSided=True` 规避** —— 这不是偷懒，
是 `nkas` 同类工具的一致做法；翻绕组会让部分件消失。

## 二、导出后必须验两条，否则会拿到「不动的模型」且不报错

| 判据 | 通过条件 | 不通过说明 |
| :--- | :--- | :--- |
| `animations > 0` | 至少一条 | 0 说明动画没绑上 |
| 通道数 > 0 | 每条动画的 channel 非空 | 0 说明绑的骨架与包名阶段不符 |

第二条最容易漏：动画绑的骨架与包名阶段不符时，**导出是成功的**，只是模型不动。
报错信息要给「型号 + 阶段 + 命中骨骼路径数」，便于定位。

## 三、动画把模型搬出画面

常见于 idle 的根节点带位移。现象是打开 glb 一片空白或模型在视野外。

```bash
python fix_glb_offset.py --dry    # 先看会改哪几个
python fix_glb_offset.py --all    # 实改：把根节点位移通道相对化
```

原理：根节点的位移通道相对化到首帧，模型回到原点附近。

## 四、取景框按整段动画包络算，不按单帧

按单帧算会在动作幅度大的帧裁头或裁脚。

```
build_anim_framing.py    # 输出 framing.js，供查看器用
```

> 该脚本不内嵌，位于 `05_脚本\★主线\`。

## 五、Three.js 查看器

查看器本体在 `06-spine-render\renderer\`（同一套静态服务）。
3D 查看器的部署与在线验收是两个**单独的、不内嵌**的脚本：

```bash
deploy_github.py         # 推到 GitHub Pages
verify_pages_3d.py       # 在线打开，确认 glb 真的加载、动画真的在播
```

> 都在 `05_脚本\★主线\`。「部署成功」不等于「能看」，必须跑一次在线验收。

## 六、模型文件的落位

```
<交付>/06_3D模型/
├── <型号>_<阶段>.glb
├── framing.js
└── 说明.md          ← 写明「缠绕未翻转、doubleSided 规避」
```
