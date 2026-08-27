from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.domain.outline import OutlineDraft, OutlinePageDraft
from app.llm.base import OutlineGenerationInput, OutlineSourceSection
from app.llm.client import create_chat_model
from app.llm.deepseek import (
    DeepSeekOutlineGenerator,
    InvalidOutlineOutputError,
    LLMNotConfiguredError,
)
from app.workflows.outline import (
    MAX_SECTION_CHARS,
    MAX_TOTAL_SOURCE_CHARS,
    build_outline_workflow,
    prepare_outline_input,
    run_outline_workflow,
)


def _section(
    ref: str,
    text: str,
    *,
    heading: str | None = None,
    level: int = 1,
    locator: str = "p1",
) -> OutlineSourceSection:
    return OutlineSourceSection(
        ref=ref,
        heading=heading,
        level=level,
        text=text,
        locator=locator,
    )


def _input(
    *,
    page_count: int = 3,
    sections: list[OutlineSourceSection] | None = None,
) -> OutlineGenerationInput:
    return OutlineGenerationInput(
        title="季度业务复盘",
        audience="管理层",
        tone="professional",
        page_count=page_count,
        sections=sections
        or [
            _section("S1:1", "市场增长稳健", heading="市场", level=1),
            _section("S1:2", "成本控制见效", heading="成本", level=2),
        ],
    )


def _draft_pages(count: int, *, layout_id: str = "bullets", refs: list[str] | None = None):
    pages = []
    for index in range(count):
        pages.append(
            OutlinePageDraft(
                title=f"第 {index + 1} 页",
                objective="说明本页目标",
                key_points=["要点甲", "要点乙"],
                source_refs=refs or [],
                layout_id=layout_id,
            )
        )
    return pages


class FakeOutlineGenerator:
    def __init__(self, pages: list[OutlinePageDraft] | None = None) -> None:
        self.calls: list[OutlineGenerationInput] = []
        self._pages = pages

    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        self.calls.append(payload)
        pages = self._pages or _draft_pages(payload.page_count, refs=["S1:1"])
        return OutlineDraft(pages=pages)


class FakeChat:
    def __init__(self, payload: str, api_key: str = "test-key") -> None:
        self.payload = payload
        self._api_key = api_key
        self.last_system: str | None = None
        self.last_user: str | None = None
        self.called = False

    async def complete(self, schema: Any, *, system: str, user: str, purpose: str) -> Any:
        if not self._api_key.strip():
            raise LLMNotConfiguredError(f"未配置 LLM API Key，无法{purpose}")
        self.called = True
        self.last_system = system
        self.last_user = user
        return schema.model_validate_json(self.payload)


def test_prepare_trims_long_section_without_breaking_ref() -> None:
    long_text = "甲" * (MAX_SECTION_CHARS + 500)
    payload = _input(sections=[_section("S1:1", long_text, heading="长节", level=2)])

    prepared = prepare_outline_input(payload)

    assert len(prepared.sections) == 1
    section = prepared.sections[0]
    assert section.ref == "S1:1"
    assert section.heading == "长节"
    assert section.level == 2
    assert len(section.text) == MAX_SECTION_CHARS


def test_prepare_respects_total_budget_and_keeps_earlier_refs() -> None:
    sections = [
        _section("S1:1", "A" * 100, heading="一"),
        _section("S1:2", "B" * 100, heading="二"),
        _section("S1:3", "C" * 100, heading="三"),
    ]
    payload = _input(sections=sections)

    prepared = prepare_outline_input(payload, max_total_chars=180, max_section_chars=100)

    assert [item.ref for item in prepared.sections] == ["S1:1", "S1:2"]
    total = sum(len(item.text) + len(item.heading or "") for item in prepared.sections)
    assert total <= 180
    # 第二节可能被部分截断，但 ref 仍完整对应同一节
    assert prepared.sections[1].ref == "S1:2"
    assert prepared.sections[1].text.startswith("B")


def test_prepare_skips_empty_sections() -> None:
    payload = _input(
        sections=[
            _section("S1:1", "  \n\t  ", heading=None),
            _section("S1:2", "有效内容", heading="保留"),
        ]
    )
    prepared = prepare_outline_input(payload)
    assert [item.ref for item in prepared.sections] == ["S1:2"]


@pytest.mark.asyncio
async def test_workflow_prepare_and_page_count_flow() -> None:
    generator = FakeOutlineGenerator()
    workflow = build_outline_workflow(generator)
    payload = _input(
        page_count=4,
        sections=[
            _section("S2:1", "产品进展", heading="产品", level=1, locator="第 2 页"),
            _section("S2:2", "风险清单", heading="风险", level=2, locator="第 5 页"),
        ],
    )

    draft = await run_outline_workflow(workflow, payload)

    assert len(draft.pages) == 4
    assert len(generator.calls) == 1
    prepared = generator.calls[0]
    assert prepared.page_count == 4
    assert prepared.title == payload.title
    assert [item.ref for item in prepared.sections] == ["S2:1", "S2:2"]
    assert prepared.sections[0].locator == "第 2 页"


@pytest.mark.asyncio
async def test_workflow_trims_long_input_before_generate() -> None:
    generator = FakeOutlineGenerator()
    workflow = build_outline_workflow(generator)
    oversized = [_section(f"S1:{index}", "X" * 3_000, heading=f"H{index}") for index in range(1, 8)]
    payload = _input(page_count=5, sections=oversized)

    await run_outline_workflow(workflow, payload)

    prepared = generator.calls[0]
    total = sum(len(item.text) + len(item.heading or "") for item in prepared.sections)
    assert total <= MAX_TOTAL_SOURCE_CHARS
    assert all(len(item.text) <= MAX_SECTION_CHARS for item in prepared.sections)
    assert prepared.sections[0].ref == "S1:1"


def _valid_outline_json(
    page_count: int = 2,
    *,
    layout_id: str = "bullets",
    ref: str = "S1:1",
) -> str:
    draft = OutlineDraft(pages=_draft_pages(page_count, layout_id=layout_id, refs=[ref]))
    return draft.model_dump_json()


@pytest.mark.asyncio
async def test_deepseek_parses_valid_outline() -> None:
    chat = FakeChat(_valid_outline_json())
    generator = DeepSeekOutlineGenerator(
        chat=chat,
        layout_ids=frozenset({"bullets", "cover"}),
    )

    draft = await generator.generate(_input(page_count=2))
    assert len(draft.pages) == 2
    assert chat.called


def test_create_chat_model_omits_thinking_by_default() -> None:
    model = create_chat_model(Settings(llm_api_key="k", llm_thinking_enabled=False))
    assert not getattr(model, "extra_body", None)


def test_create_chat_model_enables_thinking() -> None:
    model = create_chat_model(Settings(llm_api_key="k", llm_thinking_enabled=True))
    assert model.extra_body == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_deepseek_rejects_wrong_page_count() -> None:
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json(page_count=1)),
        layout_ids=frozenset({"bullets"}),
    )

    with pytest.raises(InvalidOutlineOutputError, match="页数不符"):
        await generator.generate(_input(page_count=2))


@pytest.mark.asyncio
async def test_deepseek_rejects_illegal_layout() -> None:
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json(layout_id="not-a-layout")),
        layout_ids=frozenset({"bullets", "cover"}),
    )

    with pytest.raises(InvalidOutlineOutputError, match="非法 layout_id"):
        await generator.generate(_input(page_count=2))


@pytest.mark.asyncio
async def test_deepseek_rejects_illegal_ref() -> None:
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json(ref="S9:9")),
        layout_ids=frozenset({"bullets"}),
    )

    with pytest.raises(InvalidOutlineOutputError, match="未知来源引用"):
        await generator.generate(_input(page_count=2))


@pytest.mark.asyncio
async def test_deepseek_missing_api_key() -> None:
    chat = FakeChat(_valid_outline_json(), api_key="   ")
    generator = DeepSeekOutlineGenerator(chat=chat, layout_ids=frozenset({"bullets"}))

    with pytest.raises(LLMNotConfiguredError, match="未配置 LLM API Key"):
        await generator.generate(_input(page_count=2))

    assert chat.called is False


def test_system_prompt_only_names_existing_layouts() -> None:
    """提示词里出现过的 layout_id 都必须能通过校验，否则等于诱导模型踩坑。"""
    layout_ids = frozenset({"bullets", "cover", "two-column"})
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json()),
        layout_ids=layout_ids,
    )

    prompt = generator._system_prompt()

    assert "two-column" in prompt
    for absent in ("image-text", "kpi", "chart", "table", "image-left"):
        assert absent not in prompt


def test_system_prompt_without_multi_slot_layouts() -> None:
    generator = DeepSeekOutlineGenerator(
        chat=FakeChat(_valid_outline_json()),
        layout_ids=frozenset({"bullets", "cover"}),
    )

    assert "多槽布局" not in generator._system_prompt()


def test_real_layouts_cover_the_preferred_multi_slot_hints() -> None:
    """提示里的推荐布局全部落空时只剩一句空话，等于悄悄退化。"""
    generator = DeepSeekOutlineGenerator(chat=FakeChat(_valid_outline_json()))

    assert "多槽布局" in generator._system_prompt()
