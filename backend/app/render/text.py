from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml.ns import qn
from pptx.text.text import Font, TextFrame, _Paragraph, _Run
from pptx.util import Pt

from app.domain.theme import TextStyle, Theme
from app.render.color import to_rgb

# normAutofit 的兜底边界。缩得比这更狠就不是排版微调而是内容超载，
# 那种情况该由生成期的溢出告警去拦，导出侧只负责别让文字画到框外面。
MIN_FONT_SCALE = 0.75
MAX_LINE_SPACE_REDUCTION = 0.10

# OOXML 里这两个比例的单位是千分之一个百分点
_PERCENT_UNITS = 100_000


def set_east_asian_font(font: Font, typeface: str) -> None:
    """为文本设置中日韩字体。

    python-pptx 的 font.name 只写 a:latin，中文会落到 PowerPoint 的兜底字体，
    导出效果与 Web 端对不上。必须另外写入 a:ea，且按 schema 要求排在 a:latin 之后。
    """
    _set_typeface(font, "a:ea", typeface, after=("a:latin",))


def _set_typeface(font: Font, tag: str, typeface: str, *, after: tuple[str, ...]) -> None:
    """写入 rPr 下某个字体元素。after 是 schema 要求排在它前面的兄弟。"""
    rpr = font._rPr
    element = rpr.find(qn(tag))
    if element is None:
        element = rpr.makeelement(qn(tag), {})
        previous = next(
            (found for name in reversed(after) if (found := rpr.find(qn(name))) is not None),
            None,
        )
        if previous is not None:
            previous.addnext(element)
        else:
            rpr.insert(0, element)
    element.set("typeface", typeface)


def apply_font_style(font: Font, theme: Theme, style: TextStyle) -> None:
    """把主题文本样式落到任意 Font（含图表坐标轴/图例的 defRPr）。"""
    family = theme.font_family(style)
    font.name = family.pptx_latin
    font.size = Pt(style.size_pt)
    font.bold = style.weight >= 600
    font.italic = style.italic
    font.color.rgb = to_rgb(theme.color(style.color))
    set_east_asian_font(font, family.pptx_east_asian)

    if style.letter_spacing_pt:
        # 字距没有 python-pptx 封装，直接写 rPr@spc，单位为 1/100 pt
        font._rPr.set("spc", str(round(style.letter_spacing_pt * 100)))


def apply_text_style(run: _Run, theme: Theme, style: TextStyle) -> None:
    apply_font_style(run.font, theme, style)


def write_paragraph(paragraph: _Paragraph, content: str, theme: Theme, style: TextStyle) -> _Run:
    """写一段文字。emoji 单独成 run 并换成 emoji 字体。

    正文字体（微软雅黑、思源等）里没有 emoji 码位，混在同一个 run 里
    PowerPoint 会退化成方框或黑白轮廓。切 run 之后每段各自指定字体，
    文字仍按主题走，emoji 交给系统的彩色 emoji 字体。
    """
    paragraph.line_spacing = style.line_height
    first: _Run | None = None
    for segment, is_emoji in _split_emoji(content):
        run = paragraph.add_run()
        run.text = segment
        apply_text_style(run, theme, style)
        if is_emoji:
            family = theme.fonts.emoji
            run.font.name = family.pptx_latin
            set_east_asian_font(run.font, family.pptx_east_asian)
            # 部分播放器按复杂文本脚本挑字体，cs 不覆盖会又退回正文字体
            _set_typeface(run.font, "a:cs", family.pptx_latin, after=("a:latin", "a:ea"))
        first = first or run
    assert first is not None  # _split_emoji 至少返回一段
    return first


# 判定 emoji 的码位区间。宁可漏判不可错判：把普通符号（× ± —）划进 emoji
# 会让它们换字体，反而破坏正文观感。
_EMOJI_RANGES = (
    (0x2600, 0x27BF),  # 杂项符号与装饰符号
    (0x2B00, 0x2BFF),  # 箭头与几何图形补充
    (0x1F000, 0x1FAFF),  # 表情、交通、补充象形文字
)

# 只在紧跟 emoji 时才归给 emoji run：变体选择符、零宽连接符、组合用键帽。
_EMOJI_JOINERS = frozenset({0xFE0E, 0xFE0F, 0x200D, 0x20E3})


def _is_emoji(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _EMOJI_RANGES)


def _split_emoji(content: str) -> list[tuple[str, bool]]:
    """按 emoji 边界切段，返回 [(片段, 是否 emoji)]，顺序与原文一致。"""
    segments: list[tuple[str, bool]] = []
    for char in content:
        emoji = _is_emoji(char) or (
            bool(segments) and segments[-1][1] and ord(char) in _EMOJI_JOINERS
        )
        if segments and segments[-1][1] == emoji:
            segments[-1] = (segments[-1][0] + char, emoji)
        else:
            segments.append((char, emoji))
    return segments or [("", False)]


def disable_autofit(frame: TextFrame) -> None:
    """关掉 python-pptx 新建文本框自带的 spAutoFit。

    spAutoFit 是"形状随文字长高"，PowerPoint 打开时会把框撑出槽位。
    几何是我们算好的，任何客户端自作主张改尺寸都算破坏。
    """
    frame.auto_size = MSO_AUTO_SIZE.NONE


def shrink_text_to_fit(frame: TextFrame, *, needed_pt: float, available_pt: float) -> float | None:
    """内容比框高时写死 normAutofit 的缩放比例，返回字号比例；不需要缩则返回 None。

    只挂一个空的 <a:normAutofit/> 在程序生成的新文件里等于没写：PowerPoint
    要等用户编辑过该文本框才会自己算比例，WPS 之类干脆忽略。所以比例必须我们算。
    """
    scales = _autofit_scales(needed_pt, available_pt)
    if scales is None:
        return None

    font_scale, reduction = scales
    frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    element = frame._bodyPr.normAutofit
    element.set("fontScale", str(round(font_scale * _PERCENT_UNITS)))
    if reduction > 0:
        element.set("lnSpcReduction", str(round(reduction * _PERCENT_UNITS)))
    return font_scale


def _autofit_scales(needed_pt: float, available_pt: float) -> tuple[float, float] | None:
    """返回 (字号比例, 行距压缩比例)，装得下就返回 None。

    先压行距再缩字号：行距少 10% 几乎看不出来，字号变小一眼就能看见。
    """
    if available_pt <= 0 or needed_pt <= available_pt + 0.5:
        return None
    ratio = available_pt / needed_pt
    reduction = min(MAX_LINE_SPACE_REDUCTION, 1.0 - ratio)
    font_scale = min(1.0, ratio / (1.0 - reduction))
    return max(MIN_FONT_SCALE, font_scale), reduction


def apply_bullet(paragraph: _Paragraph, theme: Theme, indent_pt: float) -> None:
    """写入 PowerPoint 原生项目符号。

    用原生 buChar / buAutoNum 而非把符号拼进文本，
    这样用户在 PowerPoint 里增删条目时符号会自动维护。
    """
    ppr = paragraph._p.get_or_add_pPr()
    ppr.set("marL", str(round(indent_pt * 12700)))
    ppr.set("indent", str(-round(indent_pt * 12700)))

    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont", "a:buClr"):
        for existing in ppr.findall(qn(tag)):
            ppr.remove(existing)

    color = ppr.makeelement(qn("a:buClr"), {})
    srgb = ppr.makeelement(qn("a:srgbClr"), {"val": theme.palette.accent.lstrip("#").upper()})
    color.append(srgb)
    ppr.append(color)

    marker = theme.shape.bullet_marker
    if marker == "index":
        bullet = ppr.makeelement(qn("a:buAutoNum"), {"type": "arabicPeriod"})
    else:
        font = ppr.makeelement(qn("a:buFont"), {"typeface": "Arial"})
        ppr.append(font)
        bullet = ppr.makeelement(qn("a:buChar"), {"char": "•" if marker == "dot" else "—"})

    ppr.append(bullet)
