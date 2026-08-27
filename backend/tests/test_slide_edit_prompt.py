"""局部修改 prompt 契约：flex 页不得依赖固定布局的槽位定义。"""

import pytest

from app.domain.layout import get_layout
from app.llm.base import SlideEditInput
from app.llm.slide_edit import DeepSeekSlideEditGenerator


def _generator() -> DeepSeekSlideEditGenerator:
    return DeepSeekSlideEditGenerator.__new__(DeepSeekSlideEditGenerator)


def _payload(**overrides) -> SlideEditInput:
    base = {
        "deck_title": "云南攻略",
        "tone": "professional",
        "page_title": "云南七天深度游",
        "layout_id": "bullets",
        "instruction": "空白区域太多了",
        "blocks": [
            {
                "block_id": "pg-lead",
                "slot_id": "pg-lead",
                "type": "text",
                "text": "七天行程参考",
            }
        ],
    }
    return SlideEditInput(**{**base, **overrides})


def test_fixed_prompt_still_carries_slot_capacity() -> None:
    gen = _generator()
    layout = get_layout("bullets")
    prompt = gen._user_prompt(_payload(), layout)
    assert "slots" in prompt
    assert "槽位" in gen._system_prompt(layout)


def test_flex_prompt_drops_slot_table() -> None:
    gen = _generator()
    prompt = gen._user_prompt(_payload(layout_mode="flex"), None)
    assert "slots" not in prompt
    assert "空白区域太多了" in prompt

    system = gen._system_prompt(None, flex=True)
    assert "灵活布局" in system
    assert "add_block" in system
    assert "槽位的字数" not in system


def test_flex_layout_id_has_no_fixed_definition() -> None:
    """flex 页的 layout_id 可能就是 "flex"，按固定布局查会直接抛错。"""
    with pytest.raises(KeyError):
        get_layout("flex")
