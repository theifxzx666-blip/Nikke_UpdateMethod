# 贴图 / 图标 / 立绘 / 横幅

## 一、先按键族认，不按包名猜

| 键族 | 内容 | 说明 |
| :--- | :--- | :--- |
| `si_c8xx_*` | 角色 Live2D | 与 `c8xx` 同 cID |
| `lw_*` | 爆裂特写贴图 | 走 `06-spine-render` |
| `icons-skill(hd)_*` | 技能图标 | 名字来自 `SkillTable`，按名挑 |
| `icons-*` | UI 图标族 | 有 `sd` / `hd` 两种分辨率 |
| `ele_ce0XX_*` | 活动插画 | `XX` = 活动序号 |
| `ce0XX_*` | 活动教学图 / 道具图标 | 同上 |
| `eventscene_*` | 剧情插画 | 2048² 原图 |

## 二、角色图四个规格，缺一个就是残档

| 规格 | 用途 | 备注 |
| :--- | :--- | :--- |
| `立绘.png` | 全身 | 基准 |
| `立绘_高清.png` | 全身（大图） | 与上一项同一套 UV，别当成两套资源 |
| `半身像.png` | 头像区 | 裁切口径见 `00_规范/目录与命名.md` |
| `小人立绘.png` | Spine 小人 | 与大厅站立动画共用三件套 |

一期 3 个角色 × 4 规格 = 12 张；5 套皮肤 × 4 规格 = 19 张（有一张缺高清，属正常）。

## 三、`.lsc` 里的 sprite 不是加密

2026-10-25 实测：`lss` / `lsc`（SQLite）里 `sprite.texture` 存的是 **Unity ASTC 纹理块原始数据**，
扁平 block 布局、每块 16 字节。不是加密，用不着求解密。

反推块尺寸的条件：

```
len(texture) == ceil(w/bw) * ceil(h/bh) * 16
```

命中且 `bw × bh` 在合法块尺寸内即可解。解完必须做**垂直翻转** —— Unity 纹理原点在左下。

```bash
python lsc_sprite.py <某表.dec> <输出目录>
```

## 四、GIF 编码五条要点（从国服旧版并入，通用）

半透明边缘出绿边 / 全黑 / 硬锯齿，全是因为漏了这几条：

1. **预乘 alpha**：`RGB = RGB * alpha // 255`（numpy 逐像素），否则边缘发绿
2. **二值化 alpha**：`alpha >= 128 → 255`，否则 0。GIF 只有 1-bit 透明
3. **量化**：`quantize(colors=255, method=Image.FASTOCTREE, dither=Image.FLOYDSTEINBERG)`
   —— RGBA 只能用 `FASTOCTREE` 或 `libimagequant`，别的会丢 alpha
4. **保留调色板**：`Image.fromarray(qarr, 'P')` 之后**必须** `putpalette(原调色板)`，否则整张变黑
5. **手动透明索引**：透明像素设索引 255，保存时 `transparency=255`

**要保 alpha 渐变就用 APNG**，别用 GIF：

```python
frames[0].save(out, save_all=True, append_images=frames[1:], duration=60, loop=0, format='PNG')
```

## 五、Windows 上的三个坑

| 坑 | 现象 | 处理 |
| :--- | :--- | :--- |
| PowerShell 通配符 | 路径含 `[Game]` 时 `Test-Path` / `Get-ChildItem` 误判 | 一律 `-LiteralPath`；`%` 会被当取模，ffmpeg 序列模式改用 Python `subprocess` |
| `%04d` 取模 | 同上 | 同上 |
| 系统 ffmpeg 被裁剪 | 不支持 VP9 alpha / concat | `pip install imageio-ffmpeg` 拿完整版 |

## 六、命名与落位

```
<交付>/01_新角色/<角色名>_<cID>/
├── 立绘.png / 立绘_高清.png / 半身像.png / 小人立绘.png
├── 技能图标_1_爆裂技能.png / _2_技能1.png / _3_技能2.png
└── 角色信息.md
```

完整规则见 `00_规范/目录与命名.md`。**图片不写 jpg**，一律 png 保 alpha。
