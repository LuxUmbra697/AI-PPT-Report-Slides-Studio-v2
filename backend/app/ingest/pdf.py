from collections import Counter
from io import BytesIO
from typing import Any

import pdfplumber

from app.ingest.models import ParsedDocument, SourceSection

# 相对正文字号众数的放大倍数；1.15 能区分常见标题/正文，又不易把略大的强调行误判成标题
_HEADING_SIZE_RATIO = 1.15
# 标题通常是短行；过长的大字号段落更可能是正文强调，不按标题处理
_MAX_HEADING_CHARS = 40
_LINE_TOP_TOLERANCE = 3.0
_SCANNED_WARNING = "未能提取到文字，可能是扫描版 PDF；本项目不做 OCR"


class PdfParser:
    extensions = (".pdf",)

    def parse(self, data: bytes) -> ParsedDocument:
        sections: list[SourceSection] = []
        with pdfplumber.open(BytesIO(data)) as pdf:
            page_lines: list[tuple[int, list[list[dict[str, Any]]]]] = []
            all_sizes: list[float] = []

            for page_number, page in enumerate(pdf.pages, start=1):
                words = page.extract_words(extra_attrs=["size"]) or []
                lines = _cluster_lines(words)
                page_lines.append((page_number, lines))
                all_sizes.extend(float(word["size"]) for word in words)

            if not all_sizes:
                return ParsedDocument(sections=[], warnings=[_SCANNED_WARNING])

            body_size = _mode_size(all_sizes)
            heading_sizes = _collect_heading_sizes(page_lines, body_size)
            size_to_level = _size_levels(heading_sizes)

            for page_number, lines in page_lines:
                page_sections = _page_to_sections(lines, body_size, size_to_level, page_number)
                sections.extend(page_sections)

        return ParsedDocument(sections=sections)


def _mode_size(sizes: list[float]) -> float:
    rounded = [round(size, 1) for size in sizes]
    return Counter(rounded).most_common(1)[0][0]


def _cluster_lines(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not words:
        return []

    ordered = sorted(words, key=lambda word: (float(word["top"]), float(word["x0"])))
    lines: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_top: float | None = None

    for word in ordered:
        top = float(word["top"])
        if current_top is None or abs(top - current_top) <= _LINE_TOP_TOLERANCE:
            current.append(word)
            if current_top is None:
                current_top = top
        else:
            lines.append(current)
            current = [word]
            current_top = top

    if current:
        lines.append(current)
    return lines


def _line_text(words: list[dict[str, Any]]) -> str:
    return " ".join(str(word["text"]) for word in words).strip()


def _line_size(words: list[dict[str, Any]]) -> float:
    return max(float(word["size"]) for word in words)


def _is_heading_line(words: list[dict[str, Any]], body_size: float) -> bool:
    text = _line_text(words)
    if not text or len(text) > _MAX_HEADING_CHARS:
        return False
    # 整行字号都显著大于正文，才视为"独占一行"的标题，避免混排行被拆坏
    return min(float(word["size"]) for word in words) >= body_size * _HEADING_SIZE_RATIO


def _collect_heading_sizes(
    page_lines: list[tuple[int, list[list[dict[str, Any]]]]],
    body_size: float,
) -> list[float]:
    sizes: set[float] = set()
    for _, lines in page_lines:
        for line in lines:
            if _is_heading_line(line, body_size):
                sizes.add(round(_line_size(line), 1))
    return sorted(sizes, reverse=True)


def _size_levels(heading_sizes: list[float]) -> dict[float, int]:
    levels: dict[float, int] = {}
    for index, size in enumerate(heading_sizes):
        levels[size] = min(index + 1, 3)
    return levels


def _page_to_sections(
    lines: list[list[dict[str, Any]]],
    body_size: float,
    size_to_level: dict[float, int],
    page_number: int,
) -> list[SourceSection]:
    locator = f"第 {page_number} 页"
    page_text = "\n".join(_line_text(line) for line in lines if _line_text(line)).strip()
    if not page_text:
        return []

    if not size_to_level:
        return [SourceSection(level=0, heading=None, text=page_text, locator=locator)]

    sections: list[SourceSection] = []
    heading: str | None = None
    level = 0
    texts: list[str] = []

    def flush() -> None:
        nonlocal heading, level, texts
        body = "\n".join(part for part in texts if part).strip()
        if heading is None and not body:
            texts = []
            return
        sections.append(SourceSection(level=level, heading=heading, text=body, locator=locator))
        heading = None
        level = 0
        texts = []

    for line in lines:
        text = _line_text(line)
        if not text:
            continue
        if _is_heading_line(line, body_size):
            flush()
            size = round(_line_size(line), 1)
            heading = text
            level = size_to_level.get(size, 3)
            texts = []
        else:
            texts.append(text)

    flush()
    return sections
