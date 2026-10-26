# 国服链路：NKAB v4 → NAU → AssetStudio

> **一期只对一服。** 国服与国际服布局、加密、工具链全不同，本节只用于国服。
> 国际服走 `02-bundle-pull` 的 `chunk\store.cdb` 链路，**不要**套用本节。

## 一、国服布局（与国服 WeGame 版实测一致）

```
%LocalAppData%\LocalLow\com_tencent\胜利女神：新的希望\
├── com.unity.addressables\*.json           Addressables catalog（明文 JSON）
└── nikke_Data\runtime_data\
    ├── cache\<A>\<B>\__data                 Unity 下载缓存（NKAB 加密）
    └── saus\...                             文本 / 语音（SQLite 的 .lss）
```

与国服 PC 端另一处 `runtime_data\saus\saus\lss\*.lss` 也有关联，别混。

## 二、资源键从 catalog 里正则捞

Addressables catalog 是 JSON，`m_InternalIds` 里有完整 bundle 名。
按关键词正则搜即可（`user_frame` / `dynamic_soloraid` / `<Boss 名>`）。

典型键：

```
动态头像框  iconprefabs-user_frame-dynamic_soloraid_<Boss>_anmi_tier4_frame(sd)_assets_all_<hash>.bundle
静态头像框  icn_soloraid_<Boss>_03_tierN_frame
称号        usertitle_special_soloraid_<Boss>_ANMI
```

## 三、NKAB v4 必须用 NAU 解

国服缓存文件头是 `NKAB`，AssetStudio / UnityPy 都直接读不了。
**v4 的头部结构与标准版不同，要用 NAU（NikkeAssetUnpacker），不能用 NikkeTools。**

| 项 | 值 |
| :--- | :--- |
| 来源 | `https://github.com/asd790320224/Doro_Repacker_EX` 的 `NAU/` 目录 |
| 需要 | `NAU.exe` + `NikkeAssetUnpacker.dll` + `Keys/`（`key_iv`、`key_salt`、`v0~v29` 各版本 `key_0~key_4`） |
| 注意 | exe / dll 是 **git-lfs** 文件，直接 clone 拿到的是指针，需从 `https://media.githubusercontent.com/media/asd790320224/Doro_Repacker_EX/main/NAU/<文件名>` 下载 |
| 命令 | `NAU.exe d -i <输入目录> -o <输出目录>` |

NAU 自动识别版本密钥（如 v14），输出 UnityFS 格式的 `_dec.bundle`。

本机现成位置：`D:\Codex\Nikke\Nikke_Skills\拆包\NAU\`。

## 四、导出：UnityPy 优先，AssetStudioCLI 兜底

```python
import UnityPy
env = UnityPy.load(bundle_path)
for obj in env.objects:
    if obj.type.name == "Texture2D":
        obj.read().image.save(f"{obj.read().m_Name}.png")
    elif obj.type.name == "TextAsset":
        d = obj.read()
        open(d.m_Name, "wb").write(d.m_Script.encode("utf-8", "surrogateescape"))
    elif obj.type.name == "AudioClip":
        for name, audio in obj.read().samples.items():
            open(name, "wb").write(audio)
```

UnityPy 失败时退 AssetStudioCLI：

```
AssetStudioCLI.exe -o <输出目录> -t 0 -c 28,213 -s <解密后的bundle>
```

- `-t 0` 导出 PNG
- `-c 28,213` 只导 Texture2D(28) 与 Sprite(213)
- 输出分 `Sprite/` 与 `Texture2D/` 两个子目录

## 五、新增资源发现：排除法

维护「已提取 ID 清单」，用负向断言扫 catalog，快速定位本期新增：

```
^si_c(?!(已知ID))(\d{3})(.*)(_s$)     # 普通角色 Live2D
^c(?!(已知NPC ID))(\d{4}).*atlas$     # NPC
```

适用于每期个突头像框这类周期性需求。

## 六、国服特有的两类坑

| 坑 | 现象 | 处理 |
| :--- | :--- | :--- |
| NKAB 版本 4 | NAU 之外的解包器识别不了版本，或解出乱码 | 只用 NAU；`Keys/` 必须齐全 |
| `__data` 命名不可反推 | `cache\<A>\<B>\__data` 的 `B` 能对上 catalog 包名哈希后缀，`A` 反推不出来 | 按 `B` 精确对应，别按 `A` 猜 |

## 七、国服脚本

国服链路用 `cn_*` 系列（7 个：`cn_catalog` / `cn_diff_vol2` / `cn_index` /
`cn_probe_bundles` / `cn_pull_probe` / `cn_roles` + `CN_ROOT` 环境变量）。

> 这些不内嵌在 8 个 Skill 里，位于 `05_脚本\★主线\`。
> 国服另用 `CN_ROOT` 环境变量（`cn_diff_vol2.py` / `cn_roles.py` 读它）。
