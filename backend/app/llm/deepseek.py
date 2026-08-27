from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import ValidationError

from app.domain.content_density import PAGE_ROLES, outline_density_hint
from app.domain.layout import load_layouts
from app.domain.outline import OutlineDraft
from app.llm.base import OutlineGenerationInput
from app.llm.client import StructuredChatClient
from app.llm.errors import (
    InvalidModelOutputError,
    InvalidOutlineOutputError,
    LLMNotConfiguredError,
)

__all__ = [
    "DeepSeekOutlineGenerator",
    "InvalidOutlineOutputError",
    "LLMNotConfiguredError",
]

_PREFERRED_MULTI_SLOT = ("two-column", "kpi", "image-left", "image-right", "chart", "table")

_VISUAL_RULE = (
    "8. visual 是一句配图意图（如「团队围着白板讨论路线图」），只描述画面，"
    "不要写「插入图片」这类指令。内容页里三分之一到一半给出 visual，"
    "其余留 null；相邻两页不要都配图。封面/目录/章节页一律 null。"
)


class DeepSeekOutlineGenerator:
    def __init__(
        self,
        *,
        model: BaseChatModel | None = None,
        api_key: str = "",
        chat: StructuredChatClient | None = None,
        layout_ids: frozenset[str] | None = None,
    ) -> None:
        if chat is not None:
            self._chat = chat
        elif model is not None:
            self._chat = StructuredChatClient(model=model, api_key=api_key)
        else:
            raise TypeError("需要 model 或 chat")
        self._layout_ids = layout_ids if layout_ids is not None else frozenset(load_layouts())

    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        try:
            draft = await self._chat.complete(
                OutlineDraft,
                system=self._system_prompt(),
                user=self._user_prompt(payload),
                purpose="生成大纲",
            )
        except (InvalidModelOutputError, ValidationError) as error:
            raise InvalidOutlineOutputError("模型返回的大纲 JSON 不符合约定结构") from error

        allowed_refs = {section.ref for section in payload.sections}
        self._validate_draft(draft, page_count=payload.page_count, allowed_refs=allowed_refs)
        return draft

    def _system_prompt(self) -> str:
        layout_list = ", ".join(sorted(self._layout_ids))
        roles = ", ".join(PAGE_ROLES)
        preferred = [layout for layout in _PREFERRED_MULTI_SLOT if layout in self._layout_ids]
        multi_slot_rule = (
            f"7. 固定布局时优先为内容页选择多槽布局（如 {'、'.join(preferred)}），"
            "避免整份都用单栏 bullets。"
            if preferred
            else "7. 内容页避免整份都用单栏 bullets。"
        )
        example = {
            "pages": [
                {
                    "title": "封面标题",
                    "objective": "本页要让听众抓住的核心目标",
                    "key_points": ["要点一：具体结论", "要点二：可展开事实"],
                    "source_refs": ["S1:1"],
                    "layout_id": "cover",
                    "page_role": "cover",
                    "visual": None,
                }
            ]
        }
        return (
            "你是 PPT 大纲规划助手。必须只输出一个 JSON 对象，不要 Markdown，不要额外说明。\n"
            "JSON 结构必须为：\n"
            '{"pages":[{"title":"...","objective":"...","key_points":["..."],'
            '"source_refs":["S1:1"],"layout_id":"cover","page_role":"cover","visual":null}]}\n'
            f"示例：{json.dumps(example, ensure_ascii=False)}\n"
            "硬性约束：\n"
            "1. pages 数组长度必须精确等于用户给定的 page_count。\n"
            "2. 每页 key_points 数量必须在 2–5 个之间；每条必须是可展开的事实/结论，"
            "禁止「介绍背景」「概述内容」这类空点。\n"
            "3. source_refs 只能使用用户提供的 ref，不得编造。\n"
            f"4. layout_id 只能从以下合法值中选择：{layout_list}。\n"
            f"5. page_role 必须是以下之一：{roles}。"
            "首屏多为 cover，中间多为 content，可选 toc/section，收尾可用 summary。\n"
            "6. title/objective/key_points 使用中文，信息具体，避免空话。\n"
            f"{multi_slot_rule}\n"
            f"{_VISUAL_RULE}"
        )

    def _user_prompt(self, payload: OutlineGenerationInput) -> str:
        sections_payload = [
            {
                "ref": section.ref,
                "heading": section.heading,
                "level": section.level,
                "text": section.text,
                "locator": section.locator,
            }
            for section in payload.sections
        ]
        body = {
            "title": payload.title,
            "audience": payload.audience,
            "tone": payload.tone,
            "page_count": payload.page_count,
            "content_density": payload.content_density,
            "sections": sections_payload,
        }
        return (
            "请根据以下项目参数与来源小节生成大纲 JSON。\n"
            f"{outline_density_hint(payload.content_density)}\n"
            f"{json.dumps(body, ensure_ascii=False)}"
        )

    def _validate_draft(
        self,
        draft: OutlineDraft,
        *,
        page_count: int,
        allowed_refs: set[str],
    ) -> None:
        if len(draft.pages) != page_count:
            raise InvalidOutlineOutputError(
                f"大纲页数不符：期望 {page_count} 页，实际 {len(draft.pages)} 页"
            )

        for index, page in enumerate(draft.pages, start=1):
            if page.layout_id not in self._layout_ids:
                raise InvalidOutlineOutputError(f"第 {index} 页使用了非法 layout_id")
            if page.page_role not in PAGE_ROLES:
                raise InvalidOutlineOutputError(f"第 {index} 页使用了非法 page_role")
            for ref in page.source_refs:
                if ref not in allowed_refs:
                    raise InvalidOutlineOutputError(f"第 {index} 页包含未知来源引用")
