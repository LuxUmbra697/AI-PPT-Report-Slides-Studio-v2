from typing import Protocol

from app.ingest.models import ParsedDocument


class UnsupportedDocument(Exception):
    """文件类型不在支持范围内，或内容无法解析"""


class DocumentParser(Protocol):
    """文档解析适配器。

    每种格式一个实现，对外只暴露"字节进、结构化小节出"，
    上层的上传流程因此不需要知道任何格式细节。
    """

    extensions: tuple[str, ...]

    def parse(self, data: bytes) -> ParsedDocument: ...
