"""文字度量：用本地下载的 Noto 字体估算折行与占用高度。

度量参数（字号、行高、字距、内边距、要点缩进）必须与
`app.render.pptx` 导出侧一致，否则溢出预警没有意义。
字体缺失时降级为字符宽度估算，不抛异常。
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.domain.theme import TextStyle

logger = logging.getLogger(__name__)

# 与 fetch_fonts.py 对齐：本地是 backend/fonts，镜像里 backend 被拷到 /app，即 /app/fonts
FONTS_DIR = Path(__file__).resolve().parents[2] / "fonts"
LATIN_FONT_NAME = "NotoSans-Regular.ttf"
CJK_FONT_NAME = "NotoSansSC-Regular.otf"

# 与 app.render.pptx 对齐的排版常量
TEXTBOX_MARGIN_PT = 0.0
BULLET_INDENT_PT = 18.0
BULLET_GAP_PT = 12.0

# 估算降级：中文按全角等宽，拉丁按经验系数（相对字号）
ESTIMATE_CJK_FACTOR = 1.0
ESTIMATE_LATIN_FACTOR = 0.55
ESTIMATE_SPACE_FACTOR = 0.33
ESTIMATE_OTHER_FACTOR = 0.6


@dataclass(frozen=True)
class TextMeasureResult:
    width_pt: float
    height_pt: float
    line_count: int
    used_estimate: bool
    overflows: bool


@dataclass
class _FontFace:
    path: Path
    units_per_em: int
    cmap: dict[int, str]
    advances: dict[str, int]
    missing_width: int


def fonts_available() -> bool:
    return _latin_font_path().is_file() and _cjk_font_path().is_file()


def _latin_font_path() -> Path:
    return FONTS_DIR / LATIN_FONT_NAME


def _cjk_font_path() -> Path:
    return FONTS_DIR / CJK_FONT_NAME


@lru_cache
def _load_face(path: str) -> _FontFace | None:
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        logger.warning("fontTools 不可用，文字度量将使用估算")
        return None

    try:
        font = TTFont(path)
        cmap = font.getBestCmap() or {}
        hmtx = font["hmtx"].metrics
        units = int(font["head"].unitsPerEm)
        missing = int(getattr(font["hhea"], "advanceWidthMax", units) * 0.5)
        if "OS/2" in font and hasattr(font["OS/2"], "xAvgCharWidth"):
            avg = int(font["OS/2"].xAvgCharWidth)
            if avg > 0:
                missing = avg
        advances = {name: int(metrics[0]) for name, metrics in hmtx.items()}
        font.close()
        return _FontFace(
            path=Path(path),
            units_per_em=units,
            cmap=cmap,
            advances=advances,
            missing_width=missing,
        )
    except Exception as error:
        logger.warning("加载度量字体失败 path=%s error=%s", path, error)
        return None


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3000 <= code <= 0x303F
        or 0x3040 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0xFF00 <= code <= 0xFFEF
        or 0x20000 <= code <= 0x2CEAF
    )


def _char_width_units(
    char: str, latin: _FontFace | None, cjk: _FontFace | None
) -> tuple[float, bool]:
    """返回 (相对 unitsPerEm=1.0 的宽度比例, 是否用了估算)。"""
    if char in "\r\n":
        return 0.0, False

    face = cjk if _is_cjk(char) and cjk is not None else latin
    if face is None and cjk is not None and not _is_cjk(char):
        face = cjk
    if face is None and latin is not None:
        face = latin

    if face is not None:
        glyph = face.cmap.get(ord(char))
        if glyph is not None and glyph in face.advances:
            return face.advances[glyph] / face.units_per_em, False
        if glyph is not None:
            return face.missing_width / face.units_per_em, False

    # 降级估算
    if char.isspace():
        return ESTIMATE_SPACE_FACTOR, True
    if _is_cjk(char):
        return ESTIMATE_CJK_FACTOR, True
    category = unicodedata.category(char)
    if category.startswith("P") or category.startswith("S"):
        return ESTIMATE_OTHER_FACTOR, True
    return ESTIMATE_LATIN_FACTOR, True


def _wrap_lines(
    text: str,
    *,
    max_width_pt: float,
    size_pt: float,
    letter_spacing_pt: float,
    latin: _FontFace | None,
    cjk: _FontFace | None,
) -> tuple[list[str], bool]:
    if max_width_pt <= 0:
        return ([text] if text else []), True

    used_estimate = False
    lines: list[str] = []

    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue

        current = ""
        current_width = 0.0
        # 拉丁词缓冲：尽量在空格处断行
        pending_word = ""
        pending_width = 0.0

        def flush_word() -> None:
            nonlocal current, current_width, pending_word, pending_width, used_estimate
            if not pending_word:
                return
            gap = letter_spacing_pt if current else 0.0
            needed = pending_width + gap
            if current and current_width + needed > max_width_pt + 1e-6:
                lines.append(current)
                current = pending_word
                current_width = pending_width
            else:
                current += pending_word
                current_width += needed
            pending_word = ""
            pending_width = 0.0

        for char in paragraph:
            ratio, estimated = _char_width_units(char, latin, cjk)
            used_estimate = used_estimate or estimated
            char_w = ratio * size_pt

            if _is_cjk(char) or unicodedata.category(char).startswith("P"):
                flush_word()
                gap = letter_spacing_pt if current else 0.0
                if current and current_width + gap + char_w > max_width_pt + 1e-6:
                    lines.append(current)
                    current = char
                    current_width = char_w
                else:
                    current += char
                    current_width += gap + char_w
                continue

            if char.isspace():
                flush_word()
                gap = letter_spacing_pt if current else 0.0
                if current and current_width + gap + char_w > max_width_pt + 1e-6:
                    lines.append(current)
                    current = char if char != " " else ""
                    current_width = char_w if current else 0.0
                else:
                    if current or char != " ":
                        current += char
                        current_width += gap + char_w
                continue

            # 拉丁字母：先攒词
            if pending_word:
                pending_width += letter_spacing_pt + char_w
            else:
                pending_width = char_w
            pending_word += char

            # 超长单词强制拆开
            if pending_width > max_width_pt + 1e-6:
                # 把已攒部分尽量放入当前行，剩余另起
                for piece in pending_word:
                    pr, pe = _char_width_units(piece, latin, cjk)
                    used_estimate = used_estimate or pe
                    pw = pr * size_pt
                    gap = letter_spacing_pt if current else 0.0
                    if current and current_width + gap + pw > max_width_pt + 1e-6:
                        lines.append(current)
                        current = piece
                        current_width = pw
                    else:
                        current += piece
                        current_width += gap + pw
                pending_word = ""
                pending_width = 0.0

        flush_word()
        lines.append(current)

    return lines, used_estimate


def measure_text(
    text: str,
    *,
    style: TextStyle,
    width_pt: float,
    height_pt: float,
    indent_pt: float = 0.0,
) -> TextMeasureResult:
    """计算文本在槽位内的折行行数与占用高度，并判断是否溢出。"""
    content_width = max(0.0, width_pt - 2 * TEXTBOX_MARGIN_PT - indent_pt)
    content_height = max(0.0, height_pt - 2 * TEXTBOX_MARGIN_PT)

    latin = _load_face(str(_latin_font_path())) if _latin_font_path().is_file() else None
    cjk = _load_face(str(_cjk_font_path())) if _cjk_font_path().is_file() else None
    # 两套都缺才算完全估算；有任一字体则优先精确路径
    force_estimate = latin is None and cjk is None

    lines, estimated = _wrap_lines(
        text,
        max_width_pt=content_width,
        size_pt=style.size_pt,
        letter_spacing_pt=style.letter_spacing_pt,
        latin=None if force_estimate else latin,
        cjk=None if force_estimate else cjk,
    )
    if not lines:
        lines = [""]

    line_count = len(lines)
    line_box = style.size_pt * style.line_height
    used_height = line_count * line_box
    overflows = used_height > content_height + 0.5  # 半 pt 容差，避免浮点误报

    return TextMeasureResult(
        width_pt=content_width,
        height_pt=used_height,
        line_count=line_count,
        used_estimate=force_estimate or estimated or latin is None or cjk is None,
        overflows=overflows,
    )


def measure_bullets(
    items: list[str],
    *,
    style: TextStyle,
    width_pt: float,
    height_pt: float,
) -> TextMeasureResult:
    """要点列表：每项独立折行，项间距与导出侧 BULLET_GAP_PT 一致。"""
    if not items:
        return TextMeasureResult(
            width_pt=width_pt,
            height_pt=0.0,
            line_count=0,
            used_estimate=not fonts_available(),
            overflows=False,
        )

    total_lines = 0
    total_height = 0.0
    used_estimate = False
    for index, item in enumerate(items):
        result = measure_text(
            item,
            style=style,
            width_pt=width_pt,
            height_pt=height_pt,
            indent_pt=BULLET_INDENT_PT,
        )
        total_lines += max(result.line_count, 1)
        total_height += result.height_pt
        if index > 0:
            total_height += BULLET_GAP_PT
        used_estimate = used_estimate or result.used_estimate

    content_height = max(0.0, height_pt - 2 * TEXTBOX_MARGIN_PT)
    return TextMeasureResult(
        width_pt=max(0.0, width_pt - BULLET_INDENT_PT),
        height_pt=total_height,
        line_count=total_lines,
        used_estimate=used_estimate,
        overflows=total_height > content_height + 0.5,
    )


def clear_font_cache() -> None:
    """测试用：字体文件变化后清缓存。"""
    _load_face.cache_clear()
