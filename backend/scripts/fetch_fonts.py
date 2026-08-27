#!/usr/bin/env python3
"""下载文字度量所需的 Noto 字体到 backend/fonts/（不提交仓库）。

已存在的文件跳过，可重复执行。
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parents[1] / "fonts"

# 使用 raw.githubusercontent.com，避免 GitHub HTML 跳转页
FONTS = {
    "NotoSans-Regular.ttf": (
        "https://raw.githubusercontent.com/googlefonts/noto-fonts/"
        "main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
    ),
    "NotoSansSC-Regular.otf": (
        "https://raw.githubusercontent.com/notofonts/noto-cjk/"
        "main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf"
    ),
}


def fetch(name: str, url: str) -> None:
    target = FONTS_DIR / name
    if target.is_file() and target.stat().st_size > 0:
        print(f"skip  {name}（已存在）")
        return
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"get   {name}")
    print(f"      {url}")
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        urllib.request.urlretrieve(url, tmp)
        if tmp.stat().st_size < 10_000:
            raise RuntimeError(f"下载结果异常偏小：{tmp.stat().st_size} bytes")
        tmp.replace(target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    print(f"ok    {name}（{target.stat().st_size} bytes）")


def main() -> int:
    for name, url in FONTS.items():
        try:
            fetch(name, url)
        except Exception as error:
            print(f"fail  {name}: {error}", file=sys.stderr)
            return 1
    print(f"fonts ready → {FONTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
