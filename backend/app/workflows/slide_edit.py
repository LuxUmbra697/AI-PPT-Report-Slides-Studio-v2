from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import TypeAdapter

from app.domain.content import Block, Slide
from app.domain.flex_layout import FlexContainer
from app.domain.slide_patch import (
    BlockPatch,
    DiscardedPatch,
    apply_patches,
    content_snapshot,
    filter_patches,
)
from app.domain.theme import resolve_theme
from app.domain.validation import StructureIssue, has_blocking_issue, validate_slide
from app.llm.base import EditOperation, SlideEditGenerator, SlideEditInput, SlideEditResult
from app.llm.errors import InvalidSlideEditOutputError

MAX_REPAIR_ROUNDS = 1

_blocks_adapter = TypeAdapter(list[Block])


class SlideEditWorkflowState(TypedDict, total=False):
    input: SlideEditInput
    slide_id: str
    layout_id: str
    layout_mode: str
    layout_tree: FlexContainer | None
    theme_id: str
    theme_overrides: dict[str, Any]
    original_blocks: list[Block]
    operations: list[EditOperation]
    discarded: list[DiscardedPatch]
    patched_blocks: list[Block]
    issues: list[StructureIssue]
    repairs: int
    from_tools: bool


def build_slide_edit_workflow(generator: SlideEditGenerator):
    """编译「工具改提案副本 → 校验 →（必要时）修复一轮」。

    改稿用 Graph 编排：生成器内 bind_tools 循环改内存副本；check 仍做领域校验。
    与大纲/正文的 LCEL json_mode 不同，这里不走 with_structured_output。
    """

    async def generate(state: SlideEditWorkflowState) -> dict:
        result = await generator.generate(state["input"])
        if isinstance(result, SlideEditResult):
            tree = result.layout_tree
            if tree is None:
                tree = state.get("layout_tree")
            return {
                "operations": result.operations,
                "patched_blocks": result.blocks,
                "layout_tree": tree,
                "from_tools": True,
                "repairs": state.get("repairs", 0),
            }
        operations = _patches_to_operations(list(result), state["original_blocks"])
        return {
            "operations": operations,
            "from_tools": False,
            "repairs": state.get("repairs", 0),
        }

    async def check(state: SlideEditWorkflowState) -> dict:
        if state.get("from_tools"):
            patched = list(state.get("patched_blocks") or [])
            discarded: list[DiscardedPatch] = []
            operations = list(state.get("operations") or [])
        else:
            patches = _operations_to_patches(state.get("operations") or [])
            filtered = filter_patches(state["original_blocks"], patches)
            patched = apply_patches(state["original_blocks"], filtered.accepted)
            discarded = filtered.discarded
            operations = _patches_to_operations(filtered.accepted, state["original_blocks"])
        slide = Slide(
            id=state["slide_id"],
            layout_id=state["layout_id"],
            layout_mode=state.get("layout_mode") or "fixed",
            layout_tree=state.get("layout_tree"),
            blocks=patched,
        )
        return {
            "operations": operations,
            "discarded": discarded,
            "patched_blocks": patched,
            "issues": validate_slide(
                slide,
                theme=resolve_theme(
                    state.get("theme_id") or "ivory", state.get("theme_overrides")
                ),
            ),
        }

    async def repair(state: SlideEditWorkflowState) -> dict:
        messages = [_describe(issue) for issue in state["issues"]]
        repaired = state["input"].model_copy(update={"issues": messages})
        return {"input": repaired, "repairs": state.get("repairs", 0) + 1}

    def route(state: SlideEditWorkflowState) -> str:
        if not state["issues"]:
            return END
        if state.get("repairs", 0) >= MAX_REPAIR_ROUNDS:
            return END
        return "repair"

    graph = StateGraph(SlideEditWorkflowState)
    graph.add_node("generate", generate)
    graph.add_node("check", check)
    graph.add_node("repair", repair)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", "check")
    graph.add_conditional_edges("check", route, {"repair": "repair", END: END})
    graph.add_edge("repair", "generate")
    return graph.compile()


async def run_slide_edit_workflow(
    workflow,
    *,
    payload: SlideEditInput,
    slide_id: str,
    layout_id: str,
    blocks: list[Block],
    layout_mode: str = "fixed",
    layout_tree: FlexContainer | None = None,
    theme_id: str | None = None,
    theme_overrides: dict[str, Any] | None = None,
) -> tuple[list[EditOperation], list[DiscardedPatch], list[StructureIssue], list[Block]]:
    result = await workflow.ainvoke(
        {
            "input": payload,
            "slide_id": slide_id,
            "layout_id": layout_id,
            "layout_mode": layout_mode,
            "layout_tree": layout_tree,
            "theme_id": theme_id or "ivory",
            "theme_overrides": theme_overrides or {},
            "original_blocks": blocks,
            "repairs": 0,
        }
    )
    operations = list(result.get("operations") or [])
    discarded = list(result.get("discarded") or [])
    issues = list(result.get("issues") or [])
    patched = list(result.get("patched_blocks") or [])

    if has_blocking_issue(issues):
        raise InvalidSlideEditOutputError(
            "局部修改后页面结构仍不合法："
            + "；".join(_describe(issue) for issue in issues if issue.severity == "error")
        )
    return operations, discarded, issues, patched


def parse_slide_blocks(raw: list[dict]) -> list[Block]:
    return _blocks_adapter.validate_python(raw)


def _patches_to_operations(
    patches: list[BlockPatch], originals: list[Block]
) -> list[EditOperation]:
    by_id = {block.id: block for block in originals}
    operations: list[EditOperation] = []
    for patch in patches:
        block = by_id.get(patch.block_id)
        before = None
        if block is not None:
            try:
                before = content_snapshot(block).model_dump(mode="json")
            except TypeError:
                before = None
        operations.append(
            EditOperation(
                op="replace",
                block_id=patch.block_id,
                slot_id=block.slot_id if block is not None else patch.block_id,
                type=patch.type,
                before=before,
                after=patch.model_dump(mode="json"),
            )
        )
    return operations


def _operations_to_patches(operations: list[EditOperation]) -> list[BlockPatch]:
    from app.domain.slide_patch import parse_block_patches

    raw = [item.after for item in operations if item.op == "replace" and item.after]
    if not raw:
        return []
    return parse_block_patches(raw)


def _describe(issue: StructureIssue) -> str:
    scope = f"槽位 {issue.slot_id}" if issue.slot_id else "本页"
    return f"{scope}：{issue.message}"
