"""把统一的 Deck 内容模型投射为 HTML、Markdown 与静态 PDF。"""
# ruff: noqa: E501

from __future__ import annotations

import html
from collections.abc import Iterable
from io import BytesIO
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.domain.content import (
    Block,
    BulletsBlock,
    CalloutBlock,
    CardsBlock,
    ChartBlock,
    Deck,
    ImageBlock,
    KpiBlock,
    Slide,
    TableBlock,
    TextBlock,
)
from app.domain.theme import Theme
from app.services.html_style import HtmlStyleProfile, default_html_style, html_palette

HTML_MEDIA_TYPE = "text/html; charset=utf-8"
MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"
PDF_MEDIA_TYPE = "application/pdf"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _slide_title(slide: Slide, position: int) -> str:
    title = next(
        (
            block.text
            for block in slide.blocks
            if isinstance(block, TextBlock) and block.slot_id in {"title", "heading"}
        ),
        None,
    )
    return title or f"第 {position} 节"


def _safe_http_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _chart_value(value: float, unit: str | None) -> str:
    return f"{value:g}{unit or ''}"


def _non_title_blocks(slide: Slide) -> Iterable[Block]:
    for block in slide.blocks:
        if isinstance(block, TextBlock) and block.slot_id in {"title", "heading"}:
            continue
        yield block


def _render_html_block(block: Block) -> str:
    if isinstance(block, TextBlock):
        return f'<p class="copy">{_escape(block.text)}</p>'
    if isinstance(block, BulletsBlock):
        return "<ul class=\"bullets\">" + "".join(
            f"<li>{_escape(item)}</li>" for item in block.items
        ) + "</ul>"
    if isinstance(block, ImageBlock):
        url = _safe_http_url(block.url)
        if url:
            credit = f"<figcaption>{_escape(block.credit)}</figcaption>" if block.credit else ""
            return (
                f'<figure class="media"><img src="{_escape(url)}" alt="{_escape(block.alt)}" '
                f'loading="lazy">{credit}</figure>'
            )
        return f'<div class="image-placeholder" role="img" aria-label="{_escape(block.alt)}">✦</div>'
    if isinstance(block, KpiBlock):
        note = f"<small>{_escape(block.note)}</small>" if block.note else ""
        return (
            '<article class="kpi"><strong>'
            f"{_escape(block.value)}</strong><span>{_escape(block.label)}</span>{note}</article>"
        )
    if isinstance(block, CardsBlock):
        cards = "".join(
            '<article class="card">'
            f"<span class=\"card-icon\">{_escape(item.icon or '✦')}</span>"
            f"<h3>{_escape(item.title)}</h3><p>{_escape(item.desc)}</p></article>"
            for item in block.items
        )
        return f'<div class="cards">{cards}</div>'
    if isinstance(block, CalloutBlock):
        icon = f'<span aria-hidden="true">{_escape(block.icon)}</span>' if block.icon else ""
        return f'<aside class="callout {block.variant}">{icon}<p>{_escape(block.text)}</p></aside>'
    if isinstance(block, TableBlock):
        head = "".join(f"<th>{_escape(value)}</th>" for value in block.header)
        rows = "".join(
            "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
            for row in block.rows
        )
        return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
    if isinstance(block, ChartBlock):
        values = [value for series in block.series for value in series.values]
        maximum = max(values) if values else 1
        series = block.series[0] if block.series else None
        bars = "".join(
            (
                '<div class="bar-row"><span>'
                f"{_escape(category)}</span><i style=\"--value:{max(3, min(100, value / maximum * 100)):.2f}%\"></i>"
                f"<b>{_escape(_chart_value(value, block.unit))}</b></div>"
            )
            for category, value in zip(block.categories, series.values if series else [], strict=False)
        )
        label = _escape(series.name) if series else "数据"
        return f'<section class="chart" aria-label="{label}"><p>{label}</p>{bars}</section>'
    return ""


def render_deck_to_html(
    deck: Deck,
    theme: Theme,
    style_profile: dict | HtmlStyleProfile | None = None,
    *,
    embedded: bool = False,
) -> bytes:
    """生成可离线打开的单文件展示页，静态脚本只负责导航和 reveal 动画。"""

    profile = (
        style_profile
        if isinstance(style_profile, HtmlStyleProfile)
        else HtmlStyleProfile.model_validate(style_profile or default_html_style(theme).model_dump())
    )
    slides = "".join(
        (
            f'<section class="report-slide layout-{profile.layout}" id="slide-{index}" '
            f'data-index="{index}" aria-labelledby="slide-title-{index}">'
            f'<p class="eyebrow">{index:02d} / {len(deck.slides):02d}</p>'
            f'<h2 id="slide-title-{index}">{_escape(_slide_title(slide, index))}</h2>'
            '<div class="slide-content" data-reveal>'
            + "".join(_render_html_block(block) for block in _non_title_blocks(slide))
            + "</div></section>"
        )
        for index, slide in enumerate(deck.slides, start=1)
    )
    navigation = "".join(
        f'<a href="#slide-{index}" aria-label="跳到第 {index} 节">{index}</a>'
        for index in range(1, len(deck.slides) + 1)
    )
    top_bar = (
        f'<header class="top"><div><p class="brand">AI HTML REPORT · {profile.mood}</p>'
        f'<h1>{_escape(deck.title)}</h1></div><nav aria-label="章节导航">{navigation}</nav></header>'
        if not embedded
        else ""
    )
    palette = html_palette(theme, profile)
    vars_css = {
        "--bg": palette["background"],
        "--surface": palette["surface"],
        "--ink": palette["ink"],
        "--ink-soft": palette["ink_soft"],
        "--accent": palette["accent"],
        "--accent-soft": palette["accent_soft"],
        "--line": palette["line"],
        "--display": theme.fonts.display.web,
        "--body": theme.fonts.body.web,
    }
    css_vars = ";".join(f"{key}:{_escape(value)}" for key, value in vars_css.items())
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{_escape(deck.title)} - AI HTML 报告"><title>{_escape(deck.title)} · HTML 报告</title>
<style>
:root{{{css_vars};--radius:{'999px' if profile.corners == 'pill' else '24px' if profile.corners == 'soft' else '4px'};--pad:{'clamp(1.25rem,5vw,5rem)' if profile.density == 'airy' else 'clamp(1rem,4vw,3.5rem)' if profile.density == 'balanced' else 'clamp(.85rem,3vw,2.25rem)'}}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);line-height:1.65}}
body::before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.36;background:{'radial-gradient(circle at 15% 15%,var(--accent-soft) 0 2px,transparent 3px) 0 0/28px 28px' if profile.pattern == 'dots' else 'linear-gradient(90deg,var(--line) 1px,transparent 1px),linear-gradient(var(--line) 1px,transparent 1px)' if profile.pattern == 'grid' else 'radial-gradient(circle at 75% 18%,var(--accent-soft),transparent 28%),radial-gradient(circle at 15% 85%,var(--accent-soft),transparent 30%)' if profile.pattern == 'sparkles' else 'repeating-radial-gradient(ellipse at 50% 120%,transparent 0 16px,var(--accent-soft) 17px 18px)' if profile.pattern == 'waves' else 'none'}}}
body::after{{content:"";position:fixed;z-index:-1;inset:-18%;pointer-events:none;background:radial-gradient(circle at var(--cursor-x,78%) var(--cursor-y,15%),color-mix(in srgb,var(--accent-soft),transparent 22%),transparent 22%);opacity:{'.5' if profile.motion == 'energetic' else '.22'};filter:blur(28px);animation:{'drift 9s ease-in-out infinite alternate' if profile.motion == 'energetic' else 'none'}}}
.top{{position:sticky;top:0;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem var(--pad);border-bottom:1px solid color-mix(in srgb,var(--line),transparent 15%);background:color-mix(in srgb,var(--bg),transparent 8%);backdrop-filter:blur(16px)}} .brand{{font:600 .82rem/1 var(--body);letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}} .top h1{{margin:0;font:600 clamp(1rem,2.3vw,1.35rem)/1.25 var(--display)}} nav{{display:flex;gap:.35rem;overflow:auto}} nav a{{display:grid;place-items:center;width:1.8rem;height:1.8rem;border:1px solid var(--line);border-radius:50%;color:var(--ink-soft);text-decoration:none;font-size:.75rem}} nav a:hover,nav a:focus{{color:white;background:var(--accent);border-color:var(--accent)}}
main{{position:relative;max-width:1240px;margin:auto;padding:1.4rem var(--pad) 5rem}} .report-slide{{min-height:calc(100vh - 6rem);display:flex;flex-direction:column;justify-content:center;padding:var(--pad) 0;border-bottom:1px solid var(--line)}} .eyebrow{{margin:0 0 .75rem;color:var(--accent);font-size:.75rem;font-weight:700;letter-spacing:.14em}} h2{{max-width:18ch;margin:0 0 clamp(1.5rem,4vw,3.5rem);font:600 clamp(2.3rem,7vw,6rem)/1.04 var(--display);letter-spacing:-.035em}} .slide-content{{display:grid;gap:1.15rem;max-width:1000px}} .copy{{max-width:70ch;margin:0;font-size:clamp(1rem,1.5vw,1.18rem);color:var(--ink-soft)}} .bullets{{display:grid;gap:.8rem;max-width:65ch;margin:0;padding:0;list-style:none}} .bullets li{{position:relative;padding-left:1.5rem}} .bullets li::before{{content:"✦";position:absolute;left:0;color:var(--accent)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem}} .card,.kpi,.callout,.chart,.table-wrap,.media{{margin:0;padding:1.25rem;border:1px solid var(--line);border-radius:var(--radius);background:color-mix(in srgb,var(--surface),transparent 8%);box-shadow:0 18px 48px color-mix(in srgb,var(--ink),transparent 93%);transition:transform .35s ease,box-shadow .35s ease}} .card:hover,.chart:hover,.table-wrap:hover,.media:hover{{transform:translateY(-5px);box-shadow:0 24px 58px color-mix(in srgb,var(--ink),transparent 86%)}} .card-icon{{color:var(--accent)}} .card h3{{margin:.5rem 0 .3rem;font:600 1.15rem/1.3 var(--display)}} .card p,.callout p{{margin:0;color:var(--ink-soft);font-size:.94rem}} .kpi{{display:inline-flex;min-width:180px;flex-direction:column;gap:.2rem}} .kpi strong{{font:600 clamp(2rem,5vw,4.4rem)/1 var(--display);color:var(--accent)}} .kpi span{{font-weight:700}} .kpi small{{color:var(--ink-soft)}} .callout{{display:flex;gap:.65rem;align-items:flex-start;max-width:800px;border-left:4px solid var(--accent)}} .callout.source{{border-left-style:dashed}} .image-placeholder{{display:grid;place-items:center;min-height:220px;border-radius:var(--radius);background:linear-gradient(135deg,var(--accent-soft),var(--surface));color:var(--accent);font-size:4rem}} .media{{overflow:hidden;padding:.5rem}} .media img{{display:block;max-width:100%;max-height:560px;margin:auto;border-radius:calc(var(--radius) - 4px);transition:transform .7s cubic-bezier(.2,.8,.2,1),filter .7s ease}} .media:hover img{{transform:scale(1.045);filter:saturate(1.12)}} .media figcaption{{margin:.55rem .5rem .2rem;color:var(--ink-soft);font-size:.78rem}} table{{width:100%;border-collapse:collapse;font-size:.9rem}} th,td{{padding:.7rem;text-align:left;border-bottom:1px solid var(--line)}} th{{color:var(--accent)}} .chart p{{margin:0 0 .8rem;color:var(--ink-soft);font-size:.86rem;font-weight:700}} .bar-row{{display:grid;grid-template-columns:minmax(5rem,1fr) minmax(6rem,3fr) auto;gap:.75rem;align-items:center;margin:.6rem 0;font-size:.85rem}} .bar-row i{{display:block;height:.62rem;border-radius:99px;background:linear-gradient(90deg,var(--accent),var(--accent-soft));width:var(--value);animation:grow .9s cubic-bezier(.2,.8,.2,1) both}} .bar-row b{{font-size:.8rem;color:var(--ink-soft)}}
.layout-bento .slide-content{{max-width:1120px}} .layout-magazine .slide-content{{max-width:820px;column-count:2;column-gap:2rem}} .layout-magazine .slide-content>*{{break-inside:avoid;display:inline-block;width:100%;margin-bottom:1rem}} .layout-timeline .slide-content{{position:relative;padding-left:2rem;border-left:2px solid var(--accent)}} .layout-minimal .slide-content{{max-width:720px}} footer{{position:relative;padding:0 var(--pad) 2rem;color:var(--ink-soft);font-size:.78rem}}
@keyframes rise{{from{{opacity:0;transform:translateY(24px)}}to{{opacity:1;transform:none}}}} @keyframes float{{50%{{transform:translateY(-7px)}}}} @keyframes grow{{from{{width:0}}}} @keyframes drift{{to{{transform:translate3d(7%,-4%,0) scale(1.12)}}}} [data-reveal]{{opacity:0}} [data-reveal].is-visible{{animation:rise {'700ms' if profile.motion == 'soft' else '460ms'} cubic-bezier(.2,.8,.2,1) both}} {' .card:nth-child(odd){animation:float 4s ease-in-out infinite}' if profile.motion == 'energetic' else ''} @media (prefers-reduced-motion:reduce){{*{{animation-duration:1ms!important;scroll-behavior:auto!important}}[data-reveal]{{opacity:1}}}} @media (max-width:680px){{.top{{align-items:flex-start;flex-direction:column}}.layout-magazine .slide-content{{columns:1}}}}
</style></head><body>{top_bar}<main>{slides or '<p>暂无可导出的内容。</p>'}</main><footer>{'' if embedded else '由 Slide Report Studio 生成 · 本文件可离线打开 · 使用 ← / → 或章节编号浏览'}</footer><script>const q=[...document.querySelectorAll('[data-reveal]')];const io=new IntersectionObserver(es=>es.forEach(e=>{{if(e.isIntersecting){{e.target.classList.add('is-visible');io.unobserve(e.target)}}}}),{{threshold:.12}});q.forEach(x=>io.observe(x));addEventListener('pointermove',e=>{{document.body.style.setProperty('--cursor-x',`${{e.clientX/innerWidth*100}}%`);document.body.style.setProperty('--cursor-y',`${{e.clientY/innerHeight*100}}%`)}});addEventListener('keydown',e=>{{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;const s=[...document.querySelectorAll('.report-slide')];const i=s.findIndex(x=>x.getBoundingClientRect().top>=-20);s[Math.max(0,Math.min(s.length-1,(i<0?0:i)+(e.key==='ArrowRight'?1:-1)))]?.scrollIntoView({{behavior:'smooth'}})}});</script></body></html>""".encode()


def _markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_deck_to_markdown(deck: Deck) -> bytes:
    lines = [f"# {deck.title}", "", "_由 Slide Report Studio 导出_", ""]
    for position, slide in enumerate(deck.slides, start=1):
        lines.extend((f"## {position}. {_slide_title(slide, position)}", ""))
        for block in _non_title_blocks(slide):
            if isinstance(block, TextBlock):
                lines.extend((block.text, ""))
            elif isinstance(block, BulletsBlock):
                lines.extend(f"- {item}" for item in block.items)
                lines.append("")
            elif isinstance(block, KpiBlock):
                suffix = f"（{block.note}）" if block.note else ""
                lines.extend((f"**{block.label}：{block.value}**{suffix}", ""))
            elif isinstance(block, CardsBlock):
                lines.extend(f"- **{item.title}**：{item.desc}" for item in block.items)
                lines.append("")
            elif isinstance(block, CalloutBlock):
                lines.extend((f"> {block.text}", ""))
            elif isinstance(block, ImageBlock):
                lines.extend((f"![{block.alt}]({block.url})" if _safe_http_url(block.url) else f"_[配图：{block.alt}]_", ""))
            elif isinstance(block, TableBlock):
                lines.append("| " + " | ".join(_markdown_escape(value) for value in block.header) + " |")
                lines.append("| " + " | ".join("---" for _ in block.header) + " |")
                lines.extend(
                    "| " + " | ".join(_markdown_escape(value) for value in row) + " |"
                    for row in block.rows
                )
                lines.append("")
            elif isinstance(block, ChartBlock):
                lines.append(f"**图表：{block.chart_type}**")
                for series in block.series:
                    lines.append(f"- {series.name}：" + "、".join(f"{value:g}" for value in series.values))
                lines.append("")
        if slide.speaker_notes:
            lines.extend(("### 备注", slide.speaker_notes, ""))
    return "\n".join(lines).rstrip().encode("utf-8") + b"\n"


def _pdf_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_escape(text).replace("\n", "<br/>"), style)


def render_deck_to_pdf(deck: Deck, theme: Theme) -> bytes:
    """导出静态阅读版 PDF；网页动效在纸面/静态媒介中自然降级。"""

    buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    page_size = landscape((297 * mm, 210 * mm))
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title=deck.title,
        author="Slide Report Studio",
    )
    title_style = ParagraphStyle(
        "title", fontName="STSong-Light", fontSize=27, leading=34, textColor=colors.HexColor(theme.palette.ink)
    )
    heading_style = ParagraphStyle(
        "heading", fontName="STSong-Light", fontSize=20, leading=27, textColor=colors.HexColor(theme.palette.accent)
    )
    body_style = ParagraphStyle(
        "body", fontName="STSong-Light", fontSize=10.5, leading=17, textColor=colors.HexColor(theme.palette.ink_soft), alignment=TA_LEFT
    )
    note_style = ParagraphStyle(
        "note", parent=body_style, fontSize=9, leading=14, textColor=colors.HexColor(theme.palette.ink_muted)
    )
    story: list[object] = [_pdf_paragraph(deck.title, title_style), Spacer(1, 8 * mm)]
    story.append(_pdf_paragraph("AI 文稿静态阅读版 · HTML 动效不会写入 PDF", note_style))
    story.append(PageBreak())
    for position, slide in enumerate(deck.slides, start=1):
        story.extend((_pdf_paragraph(f"{position:02d}. {_slide_title(slide, position)}", heading_style), Spacer(1, 4 * mm)))
        for block in _non_title_blocks(slide):
            if isinstance(block, TextBlock):
                story.extend((_pdf_paragraph(block.text, body_style), Spacer(1, 3 * mm)))
            elif isinstance(block, BulletsBlock):
                story.extend(_pdf_paragraph(f"• {item}", body_style) for item in block.items)
                story.append(Spacer(1, 3 * mm))
            elif isinstance(block, KpiBlock):
                story.extend((_pdf_paragraph(f"{block.label}：{block.value}", heading_style),))
                if block.note:
                    story.append(_pdf_paragraph(block.note, note_style))
                story.append(Spacer(1, 3 * mm))
            elif isinstance(block, CardsBlock):
                story.extend(_pdf_paragraph(f"{item.title}：{item.desc}", body_style) for item in block.items)
                story.append(Spacer(1, 3 * mm))
            elif isinstance(block, CalloutBlock):
                story.extend((_pdf_paragraph(f"提示：{block.text}", note_style), Spacer(1, 3 * mm)))
            elif isinstance(block, ImageBlock):
                story.extend((_pdf_paragraph(f"配图说明：{block.alt}", note_style), Spacer(1, 3 * mm)))
            elif isinstance(block, ChartBlock):
                data = [["分类", *[series.name for series in block.series]]]
                for index, category in enumerate(block.categories):
                    data.append([category, *[f"{series.values[index]:g}" if index < len(series.values) else "" for series in block.series]])
                table = Table(data, repeatRows=1)
                table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.palette.accent_soft)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(theme.palette.ink)),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(theme.palette.line)),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.extend((table, Spacer(1, 3 * mm)))
            elif isinstance(block, TableBlock):
                table = Table([block.header, *block.rows], repeatRows=1)
                table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(theme.palette.accent_soft)),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor(theme.palette.line)),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.extend((table, Spacer(1, 3 * mm)))
        if slide.speaker_notes:
            story.extend((_pdf_paragraph("备注：" + slide.speaker_notes, note_style),))
        if position != len(deck.slides):
            story.append(PageBreak())
    document.build(story)
    return buffer.getvalue()
