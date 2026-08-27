from app.ingest.models import ParsedDocument, SourceSection


class PlainTextParser:
    extensions = (".txt",)

    def parse(self, data: bytes) -> ParsedDocument:
        text, warnings = _decode(data)
        paragraphs = _split_paragraphs(text)
        sections = [
            SourceSection(level=0, heading=None, text=paragraph, locator=f"第 {index} 段")
            for index, paragraph in enumerate(paragraphs, start=1)
        ]
        return ParsedDocument(sections=sections, warnings=warnings)


def _decode(data: bytes) -> tuple[str, list[str]]:
    # utf-8 优先、gbk 次之，是中文文档最常见的两种编码；
    # 两者都失败时用 replace 保住可读片段，总比整份解析失败更有用。
    try:
        return data.decode("utf-8"), []
    except UnicodeDecodeError:
        pass

    try:
        return data.decode("gbk"), []
    except UnicodeDecodeError:
        pass

    return data.decode("utf-8", errors="replace"), [
        "文本编码无法可靠识别，已按 UTF-8 替换无法解码的字节"
    ]


def _split_paragraphs(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    paragraphs: list[str] = []
    for block in normalized.split("\n\n"):
        paragraph = "\n".join(line.strip() for line in block.split("\n")).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return paragraphs
