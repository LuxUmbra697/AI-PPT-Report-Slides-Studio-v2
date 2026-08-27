"""单页 prompt 契约：密度带与页型必须注入 user prompt。"""

from app.domain.layout import get_layout
from app.llm.base import SlideGenerationInput
from app.llm.slide import DeepSeekSlideGenerator


def _generator() -> DeepSeekSlideGenerator:
    # 不调用 LLM；只测 prompt 拼装
    return DeepSeekSlideGenerator.__new__(DeepSeekSlideGenerator)


def test_fixed_user_prompt_includes_density_and_role() -> None:
    gen = _generator()
    payload = SlideGenerationInput(
        deck_title="复盘",
        tone="professional",
        position=2,
        total_pages=5,
        page_title="现状",
        objective="认清瓶颈",
        key_points=["交付慢", "重复建设"],
        layout_id="bullets",
        layout_mode="fixed",
        content_density="detailed",
        page_role="content",
    )
    prompt = gen._user_prompt(payload, get_layout("bullets"))
    assert "detailed" in prompt
    assert "文字量档位" in prompt
    assert "page_role" in prompt
    assert "禁止仅输出" in prompt
    assert "宁可少写" not in prompt


def _flex_payload(**overrides) -> SlideGenerationInput:
    base = {
        "deck_title": "复盘",
        "tone": "professional",
        "position": 2,
        "total_pages": 5,
        "page_title": "现状",
        "objective": "认清瓶颈",
        "key_points": ["交付慢", "重复建设"],
        "layout_id": "bullets",
        "layout_mode": "flex",
        "content_density": "medium",
        "page_role": "content",
    }
    return SlideGenerationInput(**(base | overrides))


def test_flex_user_prompt_includes_multi_block_guidance() -> None:
    gen = _generator()
    payload = _flex_payload()
    prompt = gen._flex_user_prompt(payload)
    assert "medium" in prompt
    assert "内容块数量目标" in prompt
    system = gen._flex_system_prompt(payload)
    assert "宁可少写" not in system
    assert "多个内容块" in system


def test_visual_hint_becomes_a_hard_constraint() -> None:
    """配图意图不能只放在 user prompt 的参数里：那模型可以当没看见。"""
    gen = _generator()
    hint = "团队围着白板讨论路线图"
    system = gen._flex_system_prompt(_flex_payload(visual_hint=hint))
    assert "image 块" in system
    assert hint in system
    assert hint in gen._flex_user_prompt(_flex_payload(visual_hint=hint))

    assert "image 块" not in gen._flex_system_prompt(_flex_payload())


def test_skeleton_hint_becomes_a_hard_constraint() -> None:
    gen = _generator()
    system = gen._flex_system_prompt(_flex_payload(skeleton_hint="左文右卡：左栏标题，右栏卡片"))
    assert "左文右卡" in system


def test_callout_quota_is_stated_either_way() -> None:
    gen = _generator()
    assert "最多使用一个 callout" in gen._flex_system_prompt(_flex_payload())
    assert "不得出现 callout" in gen._flex_system_prompt(_flex_payload(allow_callout=False))
