# -*- coding: utf-8 -*-
"""verify_pull.py —— 校验拼装出来的 bundle 是否完整。拼装链路最后一步，别跳过。

用法：
  python verify_pull.py <x.bundle> [--png 1]

判据（四条全过才算成功）：
  ① 前 8 字节 == b"UnityFS\\0"
  ② 文件大小 > 0 且与期望一致（给了 --size 才比）
  ③ UnityPy 能 load，对象数 > 0
  ④ 抽一个 Texture2D 导 PNG，非全黑（只能证明"不是坏图"，不证明"是想要的图"）

为什么单独写：拼装错了也会「看起来成功」——
file_offset 断言漏了、zstd 段取偏了，UnityPy 有时仍能 load，但纹理全是花屏。
只看「脚本没报错」就交付，是本项目翻过最多次的一类错。
"""
from __future__ import annotations
import argparse, os, sys

MAGIC = b"UnityFS\x00"
ZSTD = b"\x28\xb5\x2f\xfd"


def check_head(p: str) -> bool:
    with open(p, "rb") as fh:
        head = fh.read(8)
    if head == MAGIC:
        print(f"  [1] 头部 UnityFS  OK")
        return True
    if head[:4] == b"NKAB":
        print(f"  [1] 头部 NKAB —— 需先走 NAU 解密，不是最终 bundle")
    else:
        print(f"  [1] 头部 {head!r} —— 不是 UnityFS（可能取到 zstd 段或加密段）")
    return False


def check_unitypy(p: str, want_png: int) -> bool:
    try:
        import UnityPy
    except ImportError:
        print(f"  [3] 跳过：当前 Python 无 UnityPy（要用 D:\\Codex\\依赖\\venv-nikke）")
        return True
    env = UnityPy.load(p)
    objs = list(env.objects)
    print(f"  [3] UnityPy 对象数 {len(objs)}")
    if not objs:
        print("      → 0 个对象，包是空的")
        return False

    from collections import Counter
    types = Counter(o.type.name for o in objs)
    print("      类型分布:", dict(types.most_common(6)))

    tex = [o for o in objs if o.type.name == "Texture2D"]
    if not tex or want_png < 0:
        print("  [4] 跳过（无 Texture2D 或指定不抽）")
        return True
    if want_png >= len(tex):
        print(f"  [4] 跳过（只有 {len(tex)} 个 Texture2D）")
        return True
    data = tex[want_png].read()
    try:
        img = data.image
    except Exception as e:                      # noqa: BLE001
        print(f"  [4] 导出失败：{e}")
        return False
    px = img.convert("RGB")
    ext = px.getextrema()                      # RGB 模式下是 ((rlo,rhi),(glo,ghi),(blo,bhi))
    not_black = sum(1 for ch in (0, 1, 2) if ext[ch][1] > 8)
    print(f"  [4] Texture2D[{want_png}] {img.size} 模式 {img.mode} 各通道最亮 {[e[1] for e in ext]}")
    if not_black == 0:
        print("      → 全黑，八成是拼装错或取错段")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--size", type=int, default=None, help="期望字节数（各 chunk original_size 之和）")
    ap.add_argument("--png", type=int, default=0, help="抽第几个 Texture2D；-1 表示不抽")
    a = ap.parse_args()

    if not os.path.isfile(a.bundle):
        sys.exit(f"[FATAL] 找不到 {a.bundle}")
    size = os.path.getsize(a.bundle)
    print(f"文件 {os.path.basename(a.bundle)}  {size:,} B")

    ok = check_head(a.bundle)

    print(f"  [2] 大小 {size:,} B", end="")
    if a.size is not None:
        if size == a.size:
            print(f"  == 期望  OK")
        else:
            print(f"  != 期望 {a.size:,}（差 {size - a.size:+,}）  FAIL")
            ok = False
    else:
        print("  （未给 --size，跳过比对）")
        ok = ok and size > 0

    if ok:
        ok = check_unitypy(a.bundle, a.png)

    print("\n结论:", "通过" if ok else "不通过 —— 不要往下走")


if __name__ == "__main__":
    main()
