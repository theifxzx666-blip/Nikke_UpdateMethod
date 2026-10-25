# -*- coding: utf-8 -*-
"""批量导出 BOSS 表演动画 glb（登场 / 转阶段 / 战败）。

一条动画一个文件 —— 合并进同一个 glb 时，只要有一条 clip 的骨骼路径对不上，
整个 mixer 会静默丢通道，表现是「播放正常但没动」。分开导，坏了看得出来。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import export_glb as E                     # noqa: E402

JOBS = [
    # 47 章 安尼希利奥
    # 登场包拼作 12phase（「1→2 阶段」的登场，不是第 12 阶段），而且**只绑 1 阶段骨架**：
    # 308 条曲线里 114 个唯一 path，命中 1phaseAvatar 102 个、命中 xbga03_2phaseAvatar 0 个。
    # 所以只能导 1 阶段这一份；2 阶段形态的登场不靠骨骼动画（靠 Timeline 里的粒子换形）。
    ("xba003", "1phase", "anim_xba003_12phase_appeanrance.bundle",
     "xba003_1phase_appearance.glb"),
    ("xba003", "2phase", "anim_xba003_2phase_groggy_start.bundle",
     "xba003_2phase_groggy_start.glb"),
    ("xba003", "2phase", "anim_xba003_2phase_groggy_loop.bundle",
     "xba003_2phase_groggy_loop.glb"),
    ("xba003", "2phase", "anim_xba003_2phase_groggy_end.bundle",
     "xba003_2phase_groggy_end.glb"),
    ("xba003", "2phase", "anim_xba003_2phase_death.bundle",
     "xba003_2phase_death.glb"),
    # 48 章 莉贝雷利奥躯体
    ("eba002", "1phase", "anim_eba002_1phase_intro.bundle",
     "eba002_1phase_intro.glb"),
    # 坑：包名写的是 2phase 的第 1 段，但 732 条曲线里 338 个唯一 path
    # **全部命中 eba002_1phaseAvatar**（命中 2phaseAvatar 只有 1 个）。
    # 也就是说「2 阶段登场」的第一段演的还是 1 阶段机体，必须用 1 阶段网格导，
    # 否则按 2phase 取骨架 → 0 条通道 → 导出来是个不动的静态模型。
    ("eba002", "1phase", "anim_eba002_2phase_intro_01.bundle",
     "eba002_2phase_intro_01.glb"),
    ("eba002", "2phase", "anim_eba002_2phase_intro_02.bundle",
     "eba002_2phase_intro_02.glb"),
    ("eba002", "2phase", "anim_eba002_2phase_groggy_start.bundle",
     "eba002_2phase_groggy_start.glb"),
    ("eba002", "2phase", "anim_eba002_2phase_groggy_loop.bundle",
     "eba002_2phase_groggy_loop.glb"),
    ("eba002", "2phase", "anim_eba002_2phase_groggy_end.bundle",
     "eba002_2phase_groggy_end.glb"),
    ("eba002", "2phase", "anim_eba002_2phase_death.bundle",
     "eba002_2phase_death.glb"),
    # 导不出的一个：`eba002_2phase_death_jelly` 1255 条曲线 / 431 个唯一 path，
    # 在本期客户端两个 eba002 模型包（hsta 与 hsta_singleraid）的**全部四个 Avatar**
    # 里命中数都是 0 —— 它绑的是「胶体态」那套独立骨架，本期没有下发对应模型，
    # 拉不到网格。别按常规骨骼硬导，会得到一具不动的躯壳。
    # 见 Prompt v2.3 21.5。
]


def main():
    E.OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    for i, (tag, ph, clip, out) in enumerate(JOBS, 1):
        dst = E.OUT / out
        if dst.exists():
            print(f"[{i}/{len(JOBS)}] {out} 已存在，跳过")
            ok += 1
            continue
        if not (E.DEV / clip).exists():
            print(f"[{i}/{len(JOBS)}] {out}  !! 缺 {clip}")
            continue
        print(f"[{i}/{len(JOBS)}] {tag} {ph} ← {clip}")
        try:
            E.export(tag, ph, clip, out_name=out)
            ok += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  !! {out} 失败：{e}")
    print(f"\n完成 {ok}/{len(JOBS)}")


if __name__ == "__main__":
    main()
