import json
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel

from app.core.paths import LAYOUTS_DIR
from app.domain.content import BlockType
from app.domain.geometry import Rect

TextStyleName = Literal[
    "display",
    "title",
    "subtitle",
    "body",
    "bullet",
    "caption",
    "kpi_value",
    "kpi_label",
    "kpi_note",
    "table_header",
    "table_cell",
    "chart_label",
]


class SlotCapacity(BaseModel):
    """布局对内容长度的声明式约束。

    它有两个用途：作为提示词里的硬指标约束模型生成长度，
    以及在字体度量之前做一次廉价的快速筛查。
    最终是否溢出仍以真实字体度量为准。
    """

    max_lines: int | None = None
    max_chars: int | None = None
    max_items: int | None = None
    max_chars_per_item: int | None = None
    max_rows: int | None = None
    max_columns: int | None = None
    max_chars_per_cell: int | None = None
    max_series: int | None = None
    max_categories: int | None = None


class Slot(BaseModel):
    id: str
    accepts: list[BlockType]
    rect: Rect
    required: bool = True
    text_style: TextStyleName | None = None
    capacity: SlotCapacity = SlotCapacity()


class Decoration(BaseModel):
    """纯装饰图形，不承载内容，两端渲染器按同一份声明绘制"""

    type: Literal["rule", "block"]
    rect: Rect
    color: str


class Layout(BaseModel):
    id: str
    name: str
    usage: str
    slots: list[Slot]
    decorations: list[Decoration] = []

    def slot_by_id(self, slot_id: str) -> Slot | None:
        return next((slot for slot in self.slots if slot.id == slot_id), None)


@lru_cache
def load_layouts() -> dict[str, Layout]:
    layouts: dict[str, Layout] = {}
    for path in sorted(LAYOUTS_DIR.glob("*.json")):
        layout = Layout.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if layout.id != path.stem:
            raise ValueError(f"布局 id 与文件名不一致：{path.name} 内声明为 {layout.id}")
        layouts[layout.id] = layout
    if not layouts:
        raise RuntimeError(f"未在 {LAYOUTS_DIR} 找到任何布局定义")
    return layouts


def get_layout(layout_id: str) -> Layout:
    try:
        return load_layouts()[layout_id]
    except KeyError as error:
        raise KeyError(f"未知布局：{layout_id}") from error
