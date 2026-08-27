from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.ingest.models import ParsedDocument, SourceSection


class MarkdownParser:
    extensions = (".md", ".markdown")

    def __init__(self) -> None:
        self._md = MarkdownIt("commonmark")

    def parse(self, data: bytes) -> ParsedDocument:
        # Markdown 源文件几乎总是 utf-8；这里只做最小解码，避免引入误判的编码回退
        text = data.decode("utf-8", errors="replace")
        tokens = self._md.parse(text)
        sections = _tokens_to_sections(tokens)
        return ParsedDocument(sections=sections)


def _tokens_to_sections(tokens: list[Token]) -> list[SourceSection]:
    sections: list[SourceSection] = []
    heading: str | None = None
    level = 0
    texts: list[str] = []
    locator = "第 1 段"
    block_index = 0

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

    index = 0
    while index < len(tokens):
        token = tokens[index]

        if token.type == "heading_open":
            flush()
            block_index += 1
            level = int(token.tag[1])
            inline = tokens[index + 1]
            heading = _inline_to_plain(inline).strip() or None
            locator = f"第 {block_index} 段"
            texts = []
            index += 3
            continue

        if token.type == "paragraph_open":
            block_index += 1
            if heading is None and not texts:
                locator = f"第 {block_index} 段"
            plain = _inline_to_plain(tokens[index + 1]).strip()
            if plain:
                texts.append(plain)
            index += 3
            continue

        if token.type in {"fence", "code_block"}:
            block_index += 1
            if heading is None and not texts:
                locator = f"第 {block_index} 段"
            # 代码块保留原文，作为普通文本喂给后续大纲生成
            code = token.content.rstrip("\n")
            if code:
                texts.append(code)
            index += 1
            continue

        if token.type == "hr":
            index += 1
            continue

        if token.type.endswith("_open") and token.nesting == 1:
            # 列表、引用等容器：抽出其中的段落/行内文本，不保留 Markdown 结构标记
            end_type = token.type.removesuffix("_open") + "_close"
            depth = 1
            index += 1
            while index < len(tokens) and depth > 0:
                current = tokens[index]
                if current.type == token.type:
                    depth += 1
                elif current.type == end_type:
                    depth -= 1
                    if depth == 0:
                        index += 1
                        break
                elif current.type == "paragraph_open":
                    block_index += 1
                    if heading is None and not texts:
                        locator = f"第 {block_index} 段"
                    plain = _inline_to_plain(tokens[index + 1]).strip()
                    if plain:
                        texts.append(plain)
                    index += 3
                    continue
                elif current.type == "inline":
                    plain = _inline_to_plain(current).strip()
                    if plain:
                        if heading is None and not texts:
                            block_index += 1
                            locator = f"第 {block_index} 段"
                        texts.append(plain)
                index += 1
            continue

        index += 1

    flush()
    return sections


def _inline_to_plain(token: Token) -> str:
    if token.type != "inline":
        if token.children:
            return _children_to_plain(token.children)
        return token.content
    return _children_to_plain(token.children or [])


def _children_to_plain(children: list[Token]) -> str:
    parts: list[str] = []
    for child in children:
        if child.type == "text":
            parts.append(child.content)
        elif child.type == "code_inline":
            parts.append(child.content)
        elif child.type == "softbreak":
            parts.append(" ")
        elif child.type == "hardbreak":
            parts.append("\n")
        elif child.type == "image":
            parts.append(_children_to_plain(child.children or []))
        elif child.type in {
            "link_open",
            "link_close",
            "em_open",
            "em_close",
            "strong_open",
            "strong_close",
            "s_open",
            "s_close",
        }:
            continue
        elif child.children:
            parts.append(_children_to_plain(child.children))
        elif child.content:
            parts.append(child.content)
    return "".join(parts)
