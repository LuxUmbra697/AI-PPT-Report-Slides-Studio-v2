from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.theme import ThemeOverrides
from app.ingest.models import SourceSection

Tone = Literal["professional", "plain", "punchy"]
ProjectStatus = Literal["draft", "outline_ready", "generating", "ready"]
SourceKind = Literal["topic", "text", "document"]
ContentDensity = Literal["concise", "medium", "detailed"]

# 页数范围与文档给出的推荐区间一致：太少不成篇，太多单次生成不可控
MIN_PAGE_COUNT = 5
MAX_PAGE_COUNT = 20

# 编辑器内可逐页增删，边界比创建/大纲阶段宽：那里的下限是为了让 LLM 一次生成
# 出成篇的内容，而手工改页时用户清楚自己要什么，卡在 5 页只会挡路。
MIN_DECK_PAGE_COUNT = 1
MAX_DECK_PAGE_COUNT = 40


LayoutMode = Literal["fixed", "flex"]


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    audience: str | None = Field(default=None, max_length=100)
    tone: Tone = "professional"
    page_count: int = Field(default=10, ge=MIN_PAGE_COUNT, le=MAX_PAGE_COUNT)
    theme_id: str = Field(default="ivory", max_length=50)
    layout_mode: LayoutMode = "flex"
    content_density: ContentDensity = "medium"


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    audience: str | None = Field(default=None, max_length=100)
    tone: Tone | None = None
    page_count: int | None = Field(default=None, ge=MIN_PAGE_COUNT, le=MAX_PAGE_COUNT)
    theme_id: str | None = Field(default=None, max_length=50)
    layout_mode: LayoutMode | None = None
    content_density: ContentDensity | None = None


class ProjectThemeUpdate(BaseModel):
    """样式专用更新：不受大纲 confirmed 锁定。"""

    theme_id: str | None = Field(default=None, max_length=50)
    overrides: ThemeOverrides | None = None


class SourcePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: SourceKind
    filename: str | None
    content_type: str | None
    size_bytes: int | None
    sections: list[SourceSection]
    warnings: list[str]
    char_count: int
    created_at: datetime


class ProjectPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    audience: str | None
    tone: Tone
    page_count: int
    theme_id: str
    theme_overrides: dict[str, Any] = Field(default_factory=dict)
    layout_mode: LayoutMode = "flex"
    content_density: ContentDensity = "medium"
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectPublic):
    sources: list[SourcePublic]


class TextSourceCreate(BaseModel):
    kind: Literal["topic", "text"]
    content: str = Field(min_length=1, max_length=200_000)
