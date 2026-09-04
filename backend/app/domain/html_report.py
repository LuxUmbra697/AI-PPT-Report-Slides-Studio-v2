"""HTML 报告的独立语义内容模型，不依赖 PPT Slide 表。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HtmlReportImage(BaseModel):
    """报告任务在正文完成后填充的可访问图片资产。"""

    url: str
    alt: str = Field(min_length=1, max_length=300)
    credit: str | None = Field(default=None, max_length=300)


class HtmlReportSection(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    lead: str = Field(min_length=1, max_length=260)
    paragraphs: list[str] = Field(min_length=1, max_length=3)
    highlights: list[str] = Field(min_length=2, max_length=5)
    callout: str | None = Field(default=None, max_length=220)
    image: HtmlReportImage | None = None


class HtmlReportDraft(BaseModel):
    summary: str = Field(min_length=1, max_length=360)
    sections: list[HtmlReportSection] = Field(min_length=1, max_length=20)
