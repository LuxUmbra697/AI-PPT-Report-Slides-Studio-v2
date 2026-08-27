import uuid

import pytest

from app.domain.slide_draft import BulletsContent, SlideDraft, TextContent
from app.llm.base import OutlineSourceSection, SlideGenerationInput
from app.workflows.slide import (
    build_slide_workflow,
    prepare_slide_input,
    run_slide_workflow,
)


def _payload(**overrides) -> SlideGenerationInput:
    base = {
        "deck_title": "平台化复盘",
        "tone": "professional",
        "position": 2,
        "total_pages": 5,
        "page_title": "现状与问题",
        "objective": "让听众认清当前瓶颈",
        "key_points": ["交付慢", "重复建设"],
        "layout_id": "bullets",
        "layout_mode": "fixed",
        "content_density": "medium",
        "page_role": "content",
    }
    return SlideGenerationInput(**{**base, **overrides})


class ScriptedGenerator:
    def __init__(self, drafts: list[SlideDraft]) -> None:
        self._drafts = drafts
        self.prompts: list[list[str]] = []

    async def generate(self, payload: SlideGenerationInput) -> SlideDraft:
        self.prompts.append(list(payload.issues))
        return self._drafts[min(len(self.prompts) - 1, len(self._drafts) - 1)]


def _draft(items: list[str], *, title: str = "现状与问题") -> SlideDraft:
    return SlideDraft(
        blocks=[
            TextContent(slot_id="title", text=title),
            BulletsContent(slot_id="body", items=items),
        ]
    )


def test_prepare_trims_sections_within_budget() -> None:
    payload = _payload(
        sections=[
            OutlineSourceSection(ref="S1:1", level=1, text="内容" * 5_000, locator="p1"),
            OutlineSourceSection(ref="S1:2", level=1, text="补充" * 5_000, locator="p2"),
        ]
    )

    prepared = prepare_slide_input(payload)

    total = sum(len(section.text) for section in prepared.sections)
    assert total <= 6_000
    assert [section.ref for section in prepared.sections] == ["S1:1", "S1:2"]


@pytest.mark.asyncio
async def test_workflow_skips_repair_for_capacity_overflow() -> None:
    """容量/溢出 warning 只提示，不触发整页重写。"""
    too_long = ["超出容量的要点" * 12] * 9
    generator = ScriptedGenerator([_draft(too_long)])
    workflow = build_slide_workflow(generator)

    slide, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    assert len(generator.prompts) == 1
    assert generator.prompts[0] == []
    assert any(issue.code == "capacity" for issue in issues)
    assert slide.blocks[1].items == too_long


@pytest.mark.asyncio
async def test_workflow_repairs_thin_content_once() -> None:
    thin = ["短", "也短"]
    rich = [
        "交付周期从六周缩短到三周，瓶颈在评审排队",
        "重复建设占比过高，跨团队接口缺少统一契约",
        "线上故障平均恢复时间仍超过四小时，需专人值班",
    ]
    generator = ScriptedGenerator([_draft(thin), _draft(rich)])
    workflow = build_slide_workflow(generator)

    slide, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    assert generator.prompts[0] == []
    assert generator.prompts[1]
    assert any("偏" in msg or "过短" in msg or "空话" in msg for msg in generator.prompts[1])
    assert slide.blocks[1].items == rich
    assert not any(issue.code == "thin_content" for issue in issues)


@pytest.mark.asyncio
async def test_workflow_gives_up_after_one_thin_repair() -> None:
    thin = ["短", "也短"]
    generator = ScriptedGenerator([_draft(thin)])
    workflow = build_slide_workflow(generator)

    _, issues = await run_slide_workflow(workflow, _payload(), uuid.uuid4())

    assert len(generator.prompts) == 2
    assert any(issue.code == "thin_content" for issue in issues)
