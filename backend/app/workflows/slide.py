from __future__ import annotations

import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.content import Slide
from app.domain.flex_fit import fit_tree_to_content
from app.domain.flex_width import fit_row_widths
from app.domain.quality import check_slide_richness, is_repair_worthy
from app.domain.slide_draft import FlexSlideDraft, SlideDraft, draft_to_slide, flex_draft_to_slide
from app.domain.theme import resolve_theme
from app.domain.validation import StructureIssue, validate_slide
from app.llm.base import SlideGenerationInput, SlideGenerator
from app.llm.errors import InvalidSlideOutputError

# 只修一轮：结构 error 或过瘦/空话；溢出/容量 warning 不触发砍块重写。
# generate 节点内部是 LCEL json_mode；校验与条件修复留在 Graph。
MAX_REPAIR_ROUNDS = 1

MAX_SECTION_CHARS = 1_500
MAX_TOTAL_SOURCE_CHARS = 6_000


class SlideWorkflowState(TypedDict, total=False):
    input: SlideGenerationInput
    slide_id: str
    theme_id: str
    theme_overrides: dict[str, Any]
    draft: SlideDraft | FlexSlideDraft
    slide: Slide
    issues: list[StructureIssue]
    repairs: int


def prepare_slide_input(
    payload: SlideGenerationInput,
    *,
    max_total_chars: int = MAX_TOTAL_SOURCE_CHARS,
    max_section_chars: int = MAX_SECTION_CHARS,
) -> SlideGenerationInput:
    """裁剪单页可见的来源片段。

    单页只需要它引用到的少量证据，配额比大纲阶段小得多：
    上下文越短，模型越不容易把别页的内容混进来。
    """
    sections = []
    used = 0
    for section in payload.sections:
        text = " ".join(section.text.split())[:max_section_chars]
        if not text and not section.heading:
            continue
        remaining = max_total_chars - used
        if remaining <= 0:
            break
        text = text[:remaining]
        sections.append(section.model_copy(update={"text": text}))
        used += len(text)
    return payload.model_copy(update={"sections": sections})


def build_slide_workflow(generator: SlideGenerator):
    """编译「准备 → 生成 → 校验 →（必要时）修复」的单页工作流。

    校验放进图里而不是调用方，是为了让修复轮次能拿到结构问题，
    形成一个自纠正回路而不是简单的重试。
    """

    async def prepare(state: SlideWorkflowState) -> dict:
        return {"input": prepare_slide_input(state["input"]), "repairs": 0}

    async def generate(state: SlideWorkflowState) -> dict:
        draft = await generator.generate(state["input"])
        return {"draft": draft}

    async def check(state: SlideWorkflowState) -> dict:
        slide_id = uuid.UUID(state["slide_id"])
        draft = state["draft"]
        if isinstance(draft, FlexSlideDraft) or state["input"].layout_mode == "flex":
            if not isinstance(draft, FlexSlideDraft):
                raise InvalidSlideOutputError("灵活布局生成未返回 FlexSlideDraft")
            slide = flex_draft_to_slide(
                slide_id,
                draft,
                fallback_layout_id=state["input"].layout_id or "bullets",
            )
        else:
            if not isinstance(draft, SlideDraft):
                raise InvalidSlideOutputError("固定布局生成未返回 SlideDraft")
            slide = draft_to_slide(slide_id, state["input"].layout_id, draft)
        theme = resolve_theme(state.get("theme_id") or "ivory", state.get("theme_overrides"))
        payload = state["input"]
        # 生成期先定列宽再定行高：宽度决定折行，折行决定自然高度。
        # 两步都放在校验之前，让溢出/容量告警反映的是最终版面。
        if slide.layout_mode == "flex" and slide.layout_tree is not None:
            widened = fit_row_widths(slide.layout_tree, slide.blocks, theme=theme)
            slide = slide.model_copy(
                update={
                    "layout_tree": fit_tree_to_content(
                        widened,
                        slide.blocks,
                        theme=theme,
                        page_role=payload.page_role,
                    )
                }
            )
        issues = validate_slide(slide, theme=theme)
        issues.extend(
            check_slide_richness(
                slide,
                content_density=payload.content_density,
                page_role=payload.page_role,
            )
        )
        return {
            "slide": slide,
            "issues": issues,
        }

    async def repair(state: SlideWorkflowState) -> dict:
        repairable = [issue for issue in state["issues"] if is_repair_worthy(issue)]
        messages = [_describe(issue) for issue in repairable]
        repaired = state["input"].model_copy(update={"issues": messages})
        return {"input": repaired, "repairs": state.get("repairs", 0) + 1}

    def route(state: SlideWorkflowState) -> str:
        if state.get("repairs", 0) >= MAX_REPAIR_ROUNDS:
            return END
        if any(is_repair_worthy(issue) for issue in state["issues"]):
            return "repair"
        return END

    graph = StateGraph(SlideWorkflowState)
    graph.add_node("prepare", prepare)
    graph.add_node("generate", generate)
    graph.add_node("check", check)
    graph.add_node("repair", repair)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", route, {"repair": "repair", END: END})
    graph.add_edge("repair", "generate")
    return graph.compile()


async def run_slide_workflow(
    workflow,
    payload: SlideGenerationInput,
    slide_id: uuid.UUID,
    *,
    theme_id: str | None = None,
    theme_overrides: dict[str, Any] | None = None,
) -> tuple[Slide, list[StructureIssue]]:
    result = await workflow.ainvoke(
        {
            "input": payload,
            "slide_id": str(slide_id),
            "theme_id": theme_id or "ivory",
            "theme_overrides": theme_overrides or {},
        }
    )
    slide = result.get("slide")
    if not isinstance(slide, Slide):
        raise InvalidSlideOutputError("页面工作流未产出内容")
    return slide, list(result.get("issues") or [])


def _describe(issue: StructureIssue) -> str:
    scope = f"槽位 {issue.slot_id}" if issue.slot_id else "本页"
    return f"{scope}：{issue.message}"
