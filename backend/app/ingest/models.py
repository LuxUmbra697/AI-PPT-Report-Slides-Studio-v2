from pydantic import BaseModel, Field, field_validator


def _strip_null_bytes(value: object) -> object:
    """PostgreSQL text/JSONB 拒绝 \\u0000；PDF 抽取偶发带入，落库前必须清掉。"""
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


class SourceSection(BaseModel):
    """输入材料的一个章节。

    保留标题层级而非拍平成纯文本，是因为大纲规划本质上是结构提炼：
    原文档已有的结构信息如果丢掉，等于让模型再猜一遍。
    """

    # 0 表示没有标题的正文块，1–6 对应标题层级
    level: int = Field(ge=0, le=6)
    heading: str | None = None
    text: str
    # 来源位置，用于让用户追溯某段内容出自原文何处，例如"第 3 页""第 12 段"
    locator: str

    @field_validator("heading", "text", "locator", mode="before")
    @classmethod
    def drop_null_bytes(cls, value: object) -> object:
        return _strip_null_bytes(value)


class ParsedDocument(BaseModel):
    sections: list[SourceSection]
    # 解析过程中的降级说明，例如扫描版 PDF 取不到文字层
    warnings: list[str] = []

    @field_validator("warnings", mode="before")
    @classmethod
    def drop_null_bytes_in_warnings(cls, value: object) -> object:
        if isinstance(value, list):
            return [_strip_null_bytes(item) for item in value]
        return value

    @property
    def char_count(self) -> int:
        return sum(len(section.text) for section in self.sections)

    @property
    def is_empty(self) -> bool:
        return self.char_count == 0
