"""编辑器内的整页操作：空白页内容与整页克隆。

只做纯数据变换（大纲页、blocks、布局树），落库与序号维护在
``services/deck_pages.py``。
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.flex_edit import default_block_dict
from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode
from app.domain.flex_normalize import normalize
from app.domain.outline import OutlinePage

# 空白页用最通用的要点版式：既能过大纲的布局校验，也是手写页最常见的结构
BLANK_LAYOUT_ID = "bullets"
BLANK_TITLE = "新页面"
_BLANK_OBJECTIVE = "补充这一页想讲清楚的事"
# OutlinePage 要求至少两条要点，占位文案同时也是给用户的填写提示
_BLANK_KEY_POINTS = ("待补充要点", "待补充要点")
# 与 title-bullets 预设一致的纵向权重
_TITLE_GROW = 0.45
_BODY_GROW = 1.5


def blank_outline_page() -> OutlinePage:
    """空白页对应的大纲页。

    slides 以 outline_page_id 为幂等键，且 ``sync_slides`` 会删掉大纲里不存在
    的页，所以编辑器插入的页必须在大纲里同时有一条记录。
    """
    return OutlinePage(
        title=BLANK_TITLE,
        objective=_BLANK_OBJECTIVE,
        key_points=list(_BLANK_KEY_POINTS),
        source_refs=[],
        layout_id=BLANK_LAYOUT_ID,
        page_role="content",
    )


def blank_slide_content() -> tuple[list[dict[str, Any]], FlexContainer]:
    """空白页的最小可编辑内容：一个标题加一组要点。

    这里直接写死一棵纵向树而不走预设挑选：预设按块类型组成打分，两块内容会被
    评到左右分栏之类的版式上，对一张待填写的空页毫无必要。
    """
    prefix = uuid.uuid4().hex[:12]
    title_id = f"{prefix}-title"
    body_id = f"{prefix}-body"
    blocks = [
        {**default_block_dict("text", title_id), "text": BLANK_TITLE},
        default_block_dict("bullets", body_id),
    ]
    tree = normalize(
        FlexContainer(
            type="column",
            id="root",
            children=[
                FlexLeaf(
                    id=f"leaf-{title_id}",
                    block_id=title_id,
                    grow=_TITLE_GROW,
                    text_style="title",
                ),
                FlexLeaf(
                    id=f"leaf-{body_id}",
                    block_id=body_id,
                    grow=_BODY_GROW,
                    text_style="bullet",
                ),
            ],
        )
    )
    return blocks, tree


def clone_slide_content(
    blocks: list[dict[str, Any]],
    layout_tree: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """深拷贝整页内容，并把全部块 id 换成新的一批。

    两页各存一份 JSON，id 撞车本身写不坏数据，但编辑撤销栈与选中态都按
    block id 寻址，沿用旧 id 会让复制页与原页互相串。
    """
    renames = {str(block["id"]): uuid.uuid4().hex[:12] for block in blocks if block.get("id")}
    cloned = [_clone_block(block, renames) for block in blocks]
    if layout_tree is None:
        return cloned, None
    tree = _clone_node(FlexContainer.model_validate(layout_tree), renames)
    return cloned, tree.model_dump(mode="json")


def _clone_block(block: dict[str, Any], renames: dict[str, str]) -> dict[str, Any]:
    cloned = _deep_copy(block)
    old_id = str(block.get("id", ""))
    new_id = renames.get(old_id)
    if new_id is None:
        return cloned
    cloned["id"] = new_id
    # flex 约定 slot_id 与 id 同值；fixed 页的槽位名是布局定义的一部分，保持原样
    if str(block.get("slot_id", "")) == old_id:
        cloned["slot_id"] = new_id
    return cloned


def _clone_node(node: FlexNode, renames: dict[str, str]) -> FlexNode:
    if isinstance(node, FlexLeaf):
        new_id = renames.get(node.block_id)
        if new_id is None:
            return node.model_copy(deep=True)
        return node.model_copy(update={"block_id": new_id, "id": f"leaf-{new_id}"})
    children = [_clone_node(child, renames) for child in node.children]
    return node.model_copy(update={"children": children})


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value
