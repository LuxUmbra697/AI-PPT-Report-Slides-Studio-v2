from pathlib import Path

from app.ingest.base import DocumentParser, UnsupportedDocument
from app.ingest.docx import DocxParser
from app.ingest.markdown import MarkdownParser
from app.ingest.pdf import PdfParser
from app.ingest.plain import PlainTextParser

PARSERS: tuple[DocumentParser, ...] = (
    PlainTextParser(),
    MarkdownParser(),
    DocxParser(),
    PdfParser(),
)

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    extension for parser in PARSERS for extension in parser.extensions
)


def parser_for(filename: str) -> DocumentParser:
    extension = Path(filename).suffix.lower()
    for parser in PARSERS:
        if extension in parser.extensions:
            return parser

    supported = "、".join(sorted(SUPPORTED_EXTENSIONS))
    label = extension if extension else "（无扩展名）"
    raise UnsupportedDocument(f"不支持的文件类型：{label}。支持的类型：{supported}")
