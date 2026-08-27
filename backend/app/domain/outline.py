import uuid
from typing import Literal

from pydantic import BaseModel, Field

PageRole = Literal["cover", "toc", "section", "content", "summary"]


class OutlinePageDraft(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=300)
    key_points: list[str] = Field(min_length=2, max_length=5)
    # 格式为「来源编号:小节编号」，例如 S1:2。服务端会校验引用确实存在，
    # 避免模型编造一个无法追溯的来源。
    source_refs: list[str] = Field(default_factory=list, max_length=10)
    layout_id: str
    page_role: PageRole = "content"
    # 一句配图意图，为空表示这页不配图。放在大纲阶段而不是正文阶段，
    # 是因为「哪些页该配图」是全局节奏问题：正文页各自并发生成，看不到彼此。
    visual: str | None = Field(default=None, max_length=120)


class OutlineDraft(BaseModel):
    pages: list[OutlinePageDraft]


class OutlinePage(OutlinePageDraft):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
