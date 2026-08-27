from app.domain.layout import load_layouts
from app.domain.layout_switch import (
    LayoutSwitchErr,
    LayoutSwitchOk,
    list_layout_candidates,
    plan_layout_switch,
)


def _block(block_id: str, block_type: str, slot_id: str) -> dict:
    return {"id": block_id, "type": block_type, "slot_id": slot_id}


def test_compatible_bullets_to_toc() -> None:
    blocks = [
        _block("t1", "text", "title"),
        _block("b1", "bullets", "body"),
    ]
    result = plan_layout_switch(blocks, "bullets", "toc")
    assert isinstance(result, LayoutSwitchOk)
    assert result.mapping == {"t1": "title", "b1": "items"}


def test_incompatible_when_missing_required_image() -> None:
    blocks = [
        _block("t1", "text", "title"),
        _block("b1", "bullets", "body"),
    ]
    result = plan_layout_switch(blocks, "bullets", "image-left")
    assert isinstance(result, LayoutSwitchErr)
    assert "图片" in result.reason


def test_incompatible_when_too_many_images() -> None:
    blocks = [
        _block("t1", "text", "title"),
        _block("i1", "image", "image"),
        _block("i2", "image", "body"),
    ]
    # 两图一文；目标 image-right 只有一个图片槽
    result = plan_layout_switch(blocks, "image-left", "image-right")
    assert isinstance(result, LayoutSwitchErr)
    assert "图片" in result.reason
    assert "2" in result.reason


def test_incompatible_when_required_chart_missing() -> None:
    blocks = [
        _block("t1", "text", "title"),
        _block("n1", "text", "note"),
    ]
    result = plan_layout_switch(blocks, "cover", "chart")
    assert isinstance(result, LayoutSwitchErr)
    assert "图表" in result.reason


def test_mapping_is_deterministic() -> None:
    blocks = [
        _block("body", "bullets", "body"),
        _block("title", "text", "title"),
        _block("image", "image", "image"),
    ]
    first = plan_layout_switch(blocks, "image-left", "image-right")
    second = plan_layout_switch(list(reversed(blocks)), "image-left", "image-right")
    assert isinstance(first, LayoutSwitchOk)
    assert isinstance(second, LayoutSwitchOk)
    assert first.mapping == second.mapping
    assert first.mapping == {
        "image": "image",
        "title": "title",
        "body": "body",
    }


def test_reading_order_keeps_title_before_body() -> None:
    """多解时取视觉顺序下的第一解，标题落到标题槽而非可选眉题槽。"""
    blocks = [
        _block("title", "text", "title"),
        _block("points", "bullets", "body"),
    ]
    result = plan_layout_switch(blocks, "bullets", "summary")
    assert isinstance(result, LayoutSwitchOk)
    assert result.mapping["title"] == "title"
    assert result.mapping["points"] == "points"


def test_current_layout_always_compatible() -> None:
    blocks = [_block("t1", "text", "title")]
    result = plan_layout_switch(blocks, "cover", "cover")
    assert isinstance(result, LayoutSwitchOk)
    assert result.mapping == {"t1": "title"}


def test_list_candidates_marks_current_and_compat() -> None:
    blocks = [
        _block("t1", "text", "title"),
        _block("b1", "bullets", "body"),
    ]
    candidates = list_layout_candidates(blocks, "bullets")
    assert len(candidates) == len(load_layouts())
    by_id = {item.layout_id: item for item in candidates}
    assert by_id["bullets"].current is True
    assert by_id["bullets"].compatible is True
    assert by_id["toc"].compatible is True
    assert by_id["chart"].compatible is False
    assert by_id["chart"].reason is not None
