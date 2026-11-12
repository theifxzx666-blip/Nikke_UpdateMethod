# -*- coding: utf-8 -*-
"""把报告 HTML 里指定的几页单独抽出来截图，用来核对有没有溢出裁切。

`.page` 是 height:296.5mm + overflow:hidden，内容超出会被静默裁掉，所以每改一次版式
都要逐页截图看一眼。

截图尺寸按满出血口径算：`@page margin:0`，`.page` 就是 210 × 296.5 mm。
CSS 的 mm 按 96dpi 换算 → 210mm = 794px，296.5mm = 1121px。
（旧版式是 margin:13mm 13mm 14mm、内容区 184×266mm = 696×1006px，换版式时这里必须跟着改，
否则截出来是缩放的，判断不了真实的裁切位置。）

用法
----
python check_pages.py                                  # 详版全部页
python check_pages.py 39 48                            # 只截第 39、48 页（1 起）
python check_pages.py --html <报告_简版.html>            # 换文件（简版验收）
python check_pages.py --html <…> --out <临时目录> 1 3 5

旧版的 off-by-one：不传页码时只截最后一页（`sys.argv[1:] or [len(pages)]`），
现在不传就是全截。
"""
import argparse
import subprocess
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEF_HTML = Path(r"D:\Codex\Nikke\02_工位\10_数据管线\版本更新\03_历史\20260813_国际服\_构建\报告.html")
DEF_OUT = Path(r"D:\Codex\临时\nikke_intl_20261029\out\pdfcheck2")
W, H = 794, 1121   # 210mm × 296.5mm @96dpi（满出血，与 .page 一致）


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="*", type=int, help="页码，1 起；不填=全部")
    ap.add_argument("--html", default=str(DEF_HTML))
    ap.add_argument("--out", default=str(DEF_OUT))
    a = ap.parse_args()

    html_path = Path(a.html)
    if not html_path.exists():
        raise SystemExit(f"HTML 不存在：{html_path}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    src = html_path.read_text(encoding="utf-8")
    head, *rest = src.split('<div class="page">')
    pages = ['<div class="page">' + b for b in rest]
    print(f"{html_path.name}：共 {len(pages)} 页")

    for idx in (a.pages or list(range(1, len(pages) + 1))):
        if not 1 <= idx <= len(pages):
            print(f"  跳过 {idx}（越界）")
            continue
        one = out / f"p{idx:02d}.html"
        one.write_text(head + pages[idx - 1], encoding="utf-8")
        png = out / f"p{idx:02d}.png"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        f"--window-size={W},{H}", "--hide-scrollbars",
                        "--allow-file-access-from-files", "--virtual-time-budget=8000",
                        f"--screenshot={png}", one.as_uri()],
                       capture_output=True, timeout=180)
        kb = png.stat().st_size // 1024 if png.exists() else "FAIL"
        print(f"  p{idx:02d} -> {png.name} {kb} KB")


if __name__ == "__main__":
    main()
