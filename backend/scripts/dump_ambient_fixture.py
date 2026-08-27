"""重新生成前后端氛围层对齐夹具。

用法：cd backend && python scripts/dump_ambient_fixture.py
改了 domain/ambient.py 或任一主题的 ambient 后跑一次，
前端 scripts/ambient-parity.mts 会拿它当基准。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import SHARED_DIR  # noqa: E402
from app.domain.ambient import iter_ambient_shapes  # noqa: E402
from app.domain.geometry import SAFE_AREA, Rect  # noqa: E402
from app.domain.theme import load_themes  # noqa: E402

# 覆盖三种作用域：封面、章节页、正文页
LAYOUT_IDS = ("cover", "section", "bullets")
SLIDE_INDEX = 2

FIXTURE = SHARED_DIR / "ambient-fixtures" / "theme-cases.json"

_TITLE_H = 0.14
_GUTTER = 0.02


def _two_column_content() -> list[Rect]:
    """安全区里典型的「标题 + 左右两栏」占位，用来验 avoid_content。

    栏间留了空隙：打开避让的网格线只该保留在这道缝里。
    """
    area = SAFE_AREA
    body_y = area.y + _TITLE_H
    body_h = area.bottom - body_y
    column_w = (area.w - _GUTTER) / 2
    return [
        Rect(x=area.x, y=area.y, w=area.w, h=_TITLE_H),
        Rect(x=area.x, y=body_y, w=column_w, h=body_h),
        Rect(x=area.right - column_w, y=body_y, w=column_w, h=body_h),
    ]


# 每个主题/布局都跑一遍空占位与两栏占位：前者验展开、后者验避让
OCCUPIED_CASES: dict[str, list[Rect]] = {
    "empty": [],
    "two_column": _two_column_content(),
}


def main() -> None:
    cases = [
        {
            "theme_id": theme_id,
            "layout_id": layout_id,
            "slide_index": SLIDE_INDEX,
            "occupied_id": occupied_id,
            "occupied": [rect.model_dump() for rect in occupied],
            "expected_shapes": [
                shape.model_dump()
                for shape in iter_ambient_shapes(theme, layout_id, SLIDE_INDEX, occupied)
            ],
        }
        for theme_id, theme in load_themes().items()
        for layout_id in LAYOUT_IDS
        for occupied_id, occupied in OCCUPIED_CASES.items()
    ]

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"写入 {FIXTURE}（{len(cases)} 个用例）")


if __name__ == "__main__":
    main()
