from app.domain.layout import get_layout
from app.llm.base import SlideEditBlockInput, SlideEditInput
from app.llm.slide_edit import DeepSeekSlideEditGenerator


def _generator() -> DeepSeekSlideEditGenerator:
    return DeepSeekSlideEditGenerator.__new__(DeepSeekSlideEditGenerator)


def test_instruct_system_prompt_follows_user_instruction() -> None:
    generator = _generator()
    layout = get_layout("bullets")
    prompt = generator._system_prompt(layout)
    assert "instruction" in prompt
    assert "replace_*" in prompt
    assert "改写＝" not in prompt


def test_instruct_user_prompt_includes_instruction() -> None:
    generator = _generator()
    layout = get_layout("bullets")
    payload = SlideEditInput(
        deck_title="演示",
        audience="管理层",
        tone="专业",
        page_title="要点页",
        layout_id="bullets",
        instruction="标题改得更正式",
        blocks=[
            SlideEditBlockInput(
                block_id="t1",
                slot_id="title",
                type="text",
                text="原标题",
            )
        ],
    )
    prompt = generator._user_prompt(payload, layout)
    assert "严格按用户 instruction" in prompt
    assert "标题改得更正式" in prompt
    assert '"action"' not in prompt
