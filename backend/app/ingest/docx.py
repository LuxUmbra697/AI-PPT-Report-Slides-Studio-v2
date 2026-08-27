import re
from io import BytesIO

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingest.models import ParsedDocument, SourceSection

_HEADING_STYLE = re.compile(r"^(?:Heading|标题)\s*(\d+)$", re.IGNORECASE)


class DocxParser:
    extensions = (".docx",)

    def parse(self, data: bytes) -> ParsedDocument:
        document = Document(BytesIO(data))
        sections: list[SourceSection] = []
        heading: str | None = None
        level = 0
        texts: list[str] = []
        locator = "第 1 段"
        para_index = 0

        def flush() -> None:
            nonlocal heading, level, texts, locator
            body = "\n".join(part for part in texts if part).strip()
            if heading is None and not body:
                texts = []
                return
            sections.append(SourceSection(level=level, heading=heading, text=body, locator=locator))
            heading = None
            level = 0
            texts = []

        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if not text:
                    continue

                para_index += 1
                heading_level = _heading_level(block)
                if heading_level is not None:
                    flush()
                    heading = text
                    level = heading_level
                    locator = f"第 {para_index} 段"
                    texts = []
                else:
                    if heading is None and not texts:
                        locator = f"第 {para_index} 段"
                    texts.append(text)
            elif isinstance(block, Table):
                para_index += 1
                if heading is None and not texts:
                    locator = f"第 {para_index} 段"
                table_text = _table_to_text(block)
                if table_text:
                    texts.append(table_text)

        flush()
        return ParsedDocument(sections=sections)


def _heading_level(paragraph: Paragraph) -> int | None:
    style = paragraph.style
    if style is None or style.name is None:
        return None
    match = _HEADING_STYLE.match(style.name.strip())
    if match is None:
        return None
    level = int(match.group(1))
    if 1 <= level <= 6:
        return level
    return None


def _table_to_text(table: Table) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        line = " | ".join(cells).strip()
        if line:
            rows.append(line)
    return "\n".join(rows)
