from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.domain.content import (
    Block,
    BulletsBlock,
    CalloutBlock,
    CardsBlock,
    KpiBlock,
    TableBlock,
    TextBlock,
)
from app.domain.edit_ops import dump_block, previous_block_id
from app.domain.layout import Layout, Slot, get_layout
from app.domain.slide_patch import BlockPatch, content_snapshot
from app.llm.base import (
    EditOperation,
    SlideEditBlockInput,
    SlideEditCardItem,
    SlideEditInput,
    SlideEditResult,
)
from app.llm.edit_tools import EditSession, block_preview, build_edit_tools, sketch_tree
from app.llm.errors import LLMNotConfiguredError

MAX_TOOL_ROUNDS = 4


class DeepSeekSlideEditGenerator:
    """用工具调用改提案副本：模型选块、调 replace/add/delete/change_type。"""

    def __init__(
        self,
        *,
        model: BaseChatModel | None = None,
        api_key: str = "",
    ) -> None:
        self._model = model
        self._api_key = api_key

    async def generate(self, payload: SlideEditInput) -> list[BlockPatch] | SlideEditResult:
        if not self._api_key.strip() and self._model is not None:
            raise LLMNotConfiguredError("未配置 LLM API Key，无法局部修改页面")
        if self._model is None:
            raise LLMNotConfiguredError("未配置 LLM API Key，无法局部修改页面")

        originals = list(payload.original_blocks)
        session = EditSession(
            blocks=[block.model_copy(deep=True) for block in originals],
            tree=payload.layout_tree.model_copy(deep=True) if payload.layout_tree else None,
            layout_mode=payload.layout_mode,
        )
        tools = build_edit_tools(session)
        tool_map = {tool.name: tool for tool in tools}
        bound = self._model.bind_tools(tools)

        layout = None if payload.layout_mode == "flex" else get_layout(payload.layout_id)
        messages: list = [
            SystemMessage(content=self._system_prompt(layout, flex=payload.layout_mode == "flex")),
        ]
        for turn in payload.history:
            messages.append(HumanMessage(content=turn.instruction))
            if turn.note:
                messages.append(AIMessage(content=turn.note))
        messages.append(HumanMessage(content=self._user_prompt(payload, layout, session)))

        for _ in range(MAX_TOOL_ROUNDS):
            response = await bound.ainvoke(messages)
            messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                break
            for call in tool_calls:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
                call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", "")
                tool = tool_map.get(name)
                if tool is None:
                    result = f"错误：未知工具 {name}"
                else:
                    result = await tool.ainvoke(args)
                messages.append(ToolMessage(content=str(result), tool_call_id=str(call_id)))

        operations = _diff_operations(
            originals, session.blocks, payload.layout_tree, session.tree
        )
        return SlideEditResult(
            operations=operations,
            blocks=session.blocks,
            layout_tree=session.tree,
        )

    def _system_prompt(self, layout: Layout | None, *, flex: bool = False) -> str:
        capacity_rule = (
            "篇幅与现有内容保持相近，不要明显变长，避免把版面撑爆。"
            if layout is None
            else "严格遵守每个槽位的字数与条目上限；在上限内保持信息充实，不要无故删瘦。"
        )
        layout_note = (
            "本页为灵活布局，版面由布局树决定；可用 add_block / delete_block / change_type。"
            if layout is None or flex
            else (
                f"本页布局为 {layout.id}（{layout.name}）：{layout.usage}。"
                "固定布局只能 replace_*，不能增删块或改类型。"
            )
        )
        return (
            "你是 PPT 单页局部修改助手。按用户 instruction 调用工具修改提案副本，"
            "不要输出 JSON 操作清单。\n"
            "硬性约束：\n"
            "1. 只改 instruction 要求的内容；未点名的块不要调用工具。\n"
            f"2. {capacity_rule}\n"
            "3. 正文使用中文，写具体结论与事实，不写空话。\n"
            "4. 数字必须来自给定内容，缺少数据时不要编造。\n"
            "5. locked 块不可 replace / delete / change_type。\n"
            f"{layout_note}"
        )

    def _user_prompt(
        self,
        payload: SlideEditInput,
        layout: Layout | None,
        session: EditSession | None = None,
    ) -> str:
        body: dict = {
            "deck_title": payload.deck_title,
            "audience": payload.audience,
            "tone": payload.tone,
            "page_title": payload.page_title,
            "instruction": payload.instruction.strip(),
            "blocks": [_dump_edit_block(block) for block in payload.blocks],
        }
        if layout is not None:
            body["slots"] = [
                _slot_spec(slot)
                for slot in layout.slots
                if any(
                    block_type in {"text", "bullets", "kpi", "table", "cards", "callout"}
                    for block_type in slot.accepts
                )
            ]
        if session is not None and session.tree is not None:
            body["layout_tree"] = sketch_tree(session.tree)
            body["all_blocks"] = [block_preview(block) for block in session.blocks]
        prompt = (
            "请严格按用户 instruction 调用工具完成本页局部修改。\n"
            f"{json.dumps(body, ensure_ascii=False)}"
        )
        if payload.issues:
            prompt += (
                "\n上一次修改存在以下问题，请只修正这些问题并保持其余操作稳定：\n"
                + "\n".join(f"- {issue}" for issue in payload.issues)
            )
        return prompt


def block_to_edit_input(block: Block) -> SlideEditBlockInput:
    common = {"block_id": block.id, "slot_id": block.slot_id}
    match block:
        case TextBlock():
            return SlideEditBlockInput(**common, type="text", text=block.text)
        case BulletsBlock():
            return SlideEditBlockInput(**common, type="bullets", items=list(block.items))
        case KpiBlock():
            return SlideEditBlockInput(
                **common,
                type="kpi",
                value=block.value,
                label=block.label,
                note=block.note,
            )
        case TableBlock():
            return SlideEditBlockInput(
                **common,
                type="table",
                header=list(block.header),
                rows=[list(row) for row in block.rows],
            )
        case CardsBlock():
            return SlideEditBlockInput(
                **common,
                type="cards",
                card_items=[
                    SlideEditCardItem(title=item.title, desc=item.desc, icon=item.icon)
                    for item in block.items
                ],
            )
        case CalloutBlock():
            return SlideEditBlockInput(
                **common,
                type="callout",
                text=block.text,
                icon=block.icon,
                variant=block.variant,
            )
        case _:
            raise TypeError(f"块类型 {block.type} 不能作为 AI 修改输入")


def _diff_operations(
    original: list[Block],
    draft: list[Block],
    original_tree,
    draft_tree,
) -> list[EditOperation]:
    orig_by = {block.id: block for block in original}
    draft_by = {block.id: block for block in draft}
    operations: list[EditOperation] = []

    for block in draft:
        old = orig_by.get(block.id)
        if old is None:
            operations.append(
                EditOperation(
                    op="add",
                    block_id=block.id,
                    slot_id=block.slot_id,
                    type=block.type,
                    after_block_id=previous_block_id(draft_tree, block.id),
                    after=dump_block(block),
                )
            )
            continue
        if old.type != block.type:
            operations.append(
                EditOperation(
                    op="change_type",
                    block_id=block.id,
                    slot_id=block.slot_id,
                    type=block.type,
                    before=dump_block(old),
                    after=dump_block(block),
                )
            )
            continue
        if _content_changed(old, block):
            operations.append(
                EditOperation(
                    op="replace",
                    block_id=block.id,
                    slot_id=block.slot_id,
                    type=block.type,
                    before=_snapshot(old),
                    after=_snapshot(block),
                )
            )

    for old in original:
        if old.id not in draft_by:
            operations.append(
                EditOperation(
                    op="delete",
                    block_id=old.id,
                    slot_id=old.slot_id,
                    type=old.type,
                    after_block_id=previous_block_id(original_tree, old.id),
                    before=dump_block(old),
                )
            )
    return operations


def _snapshot(block: Block) -> dict:
    try:
        return content_snapshot(block).model_dump(mode="json")
    except TypeError:
        return dump_block(block)


def _content_changed(left: Block, right: Block) -> bool:
    left_dump = dump_block(left)
    right_dump = dump_block(right)
    left_dump.pop("locked", None)
    right_dump.pop("locked", None)
    return left_dump != right_dump


def _dump_edit_block(block: SlideEditBlockInput) -> dict:
    data = block.model_dump(exclude_none=True)
    if block.type == "cards" and block.card_items is not None:
        data.pop("card_items", None)
        data["items"] = [item.model_dump(exclude_none=True) for item in block.card_items]
    return data


def _slot_spec(slot: Slot) -> dict:
    capacity = slot.capacity.model_dump(exclude_none=True)
    return {
        "slot_id": slot.id,
        "accepts": list(slot.accepts),
        "required": slot.required,
        "capacity": capacity,
    }
