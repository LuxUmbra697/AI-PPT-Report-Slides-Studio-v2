import logging
from io import BytesIO
from typing import NamedTuple

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.parts.image import Image as PptxImage
from pptx.presentation import Presentation as PresentationType
from pptx.shapes.base import BaseShape
from pptx.slide import Slide as PptxSlide
from pptx.text.text import TextFrame
from pptx.util import Emu, Pt

from app.domain.ambient import AMBIENT_SHAPE_PREFIX, AmbientShape, iter_ambient_shapes
from app.domain.block_style import BlockStyle, ResolvedBox, merge_text_style, resolve_box
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
from app.domain.flex_skin import BOX_RADIUS_PT, SkinDecoration, iter_skin_decorations
from app.domain.geometry import (
    CANVAS_HEIGHT_PT,
    CANVAS_WIDTH_PT,
    EMU_PER_POINT,
    BleedRect,
    Rect,
)
from app.domain.layout import get_layout
from app.domain.slide_geometry import placed_by_block_id
from app.domain.text_metrics import measure_bullets, measure_text
from app.domain.theme import TextStyle, Theme, get_theme
from app.render.chart import render_chart
from app.render.color import mix, to_rgb
from app.render.table import set_cell_borders, use_plain_style
from app.render.text import (
    apply_bullet,
    apply_text_style,
    disable_autofit,
    set_east_asian_font,
    shrink_text_to_fit,
    write_paragraph,
)
from app.services.media import load_image, media_key_from_url

logger = logging.getLogger(__name__)

PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# 空白版式。用空白版式而非内置的标题版式，是因为槽位几何完全由我们的
# 布局数据决定，套用 PowerPoint 自带占位符反而会引入我们控制不了的位置。
BLANK_LAYOUT_INDEX = 6

BULLET_INDENT_PT = 18.0
BULLET_GAP_PT = 12.0
CARD_GAP_PT = 16.0
CARD_PAD_PT = 12.0
# 卡片标题与描述、KPI 各行之间的段前距
STACK_GAP_PT = 6.0
KPI_GAP_PT = 6.0

_ALIGN = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
}


class _TextTarget(NamedTuple):
    """一个已经摆好位置的文本框：写文字要 frame 和 align，算 autofit 要 rect。"""

    frame: TextFrame
    align: str | None
    rect: Rect


class PptxRenderer:
    """把统一内容模型渲染为 PPTX。

    它与 Web 渲染器读同一份布局与主题数据，做同一件事：
    按槽位摆放内容块。因此两端不会因为各自演进而排版分叉。

    所有输出都是 PowerPoint 原生对象（文本框、表格、形状），
    不含任何位图截图，保证导出结果可以直接编辑。
    """

    def __init__(self, theme: Theme) -> None:
        self.theme = theme

    def render(self, deck: Deck) -> BytesIO:
        presentation = Presentation()
        self._set_canvas(presentation)

        for index, slide in enumerate(deck.slides):
            self._render_slide(presentation, slide, index)

        buffer = BytesIO()
        presentation.save(buffer)
        buffer.seek(0)
        return buffer

    def _set_canvas(self, presentation: PresentationType) -> None:
        presentation.slide_width = Pt(CANVAS_WIDTH_PT)
        presentation.slide_height = Pt(CANVAS_HEIGHT_PT)

    def _render_slide(
        self, presentation: PresentationType, slide: Slide, slide_index: int = 0
    ) -> None:
        pptx_slide = presentation.slides.add_slide(presentation.slide_layouts[BLANK_LAYOUT_INDEX])

        self._fill_background(pptx_slide)

        placements = placed_by_block_id(slide)

        # 主题氛围层压在最底层，两端读同一份展开结果
        occupied = [placed.rect for placed in placements.values()]
        for shape in iter_ambient_shapes(self.theme, slide.layout_id, slide_index, occupied):
            self._render_ambient_shape(pptx_slide, shape)

        # 固定布局装饰 vs flex preset 皮肤；均画在内容块之下
        if slide.layout_mode == "flex" and slide.layout_tree is not None:
            for decoration in iter_skin_decorations(slide.layout_tree):
                self._render_skin_decoration(pptx_slide, decoration)
        else:
            try:
                layout = get_layout(slide.layout_id)
            except KeyError:
                layout = None
            if layout is not None:
                for decoration in layout.decorations:
                    self._add_filled_rect(
                        pptx_slide, decoration.rect, self.theme.color(decoration.color)
                    )

        for block in slide.blocks:
            placed = placements.get(block.id)
            if placed is None:
                continue
            self._render_block(pptx_slide, block, rect=placed.rect, text_style=placed.text_style)

        if slide.speaker_notes:
            pptx_slide.notes_slide.notes_text_frame.text = slide.speaker_notes

    def _fill_background(self, pptx_slide: PptxSlide) -> None:
        full_bleed = Rect(x=0, y=0, w=1, h=1)
        shape = self._add_filled_rect(pptx_slide, full_bleed, self.theme.palette.background)
        # 背景必须位于所有内容之下，新形状默认追加在末尾，因此显式前置
        pptx_slide.shapes._spTree.remove(shape._element)
        pptx_slide.shapes._spTree.insert(2, shape._element)

    def _render_ambient_shape(self, pptx_slide: PptxSlide, shape: AmbientShape) -> None:
        if shape.kind == "text":
            self._add_ambient_text(pptx_slide, shape)
            return
        oval = shape.kind == "ellipse"
        drawn = self._add_filled_rect(
            pptx_slide, shape.rect, shape.color, MSO_SHAPE.OVAL if oval else MSO_SHAPE.RECTANGLE
        )
        drawn.name = f"{AMBIENT_SHAPE_PREFIX}{shape.kind}"

    def _add_ambient_text(self, pptx_slide: PptxSlide, shape: AmbientShape) -> None:
        family = self.theme.fonts.display if shape.font == "display" else self.theme.fonts.body
        frame = self._add_textbox(pptx_slide, shape.rect, name=f"{AMBIENT_SHAPE_PREFIX}text")
        frame.word_wrap = False
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        paragraph = frame.paragraphs[0]
        paragraph.line_spacing = 1.0
        self._apply_align(paragraph, shape.align)
        run = paragraph.add_run()
        run.text = shape.text or ""
        font = run.font
        font.name = family.pptx_latin
        font.size = Pt(shape.size_pt or 0)
        font.bold = (shape.weight or 400) >= 600
        font.color.rgb = to_rgb(shape.color)
        set_east_asian_font(font, family.pptx_east_asian)
        if shape.letter_spacing_pt:
            font._rPr.set("spc", str(round(shape.letter_spacing_pt * 100)))

    def _render_skin_decoration(self, pptx_slide: PptxSlide, decoration: SkinDecoration) -> None:
        color = self.theme.color(decoration.color_token)
        kind = decoration.kind
        if kind == "fill_box":
            shape_type = (
                MSO_SHAPE.ROUNDED_RECTANGLE if decoration.radius_pt > 0 else MSO_SHAPE.RECTANGLE
            )
            self._add_filled_rect(
                pptx_slide,
                decoration.rect,
                color,
                shape_type,
                radius_pt=decoration.radius_pt,
            )
            return
        if kind == "outline_box":
            self._add_outline_rect(
                pptx_slide,
                decoration.rect,
                color,
                radius_pt=decoration.radius_pt,
                border_width_pt=1.5,
            )
            return
        if kind in ("side_line", "timeline_axis"):
            self._add_filled_rect(pptx_slide, decoration.rect, color)
            return
        if kind == "timeline_dot":
            self._add_filled_rect(pptx_slide, decoration.rect, color, MSO_SHAPE.OVAL)
            return
        if kind == "number_badge":
            self._add_number_badge(pptx_slide, decoration.rect, color, decoration.text or "")
            return

    def _add_outline_rect(
        self,
        pptx_slide: PptxSlide,
        rect: Rect,
        color: str,
        *,
        radius_pt: float = 0,
        border_width_pt: float = 1.5,
    ) -> BaseShape:
        shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius_pt > 0 else MSO_SHAPE.RECTANGLE
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        shape = pptx_slide.shapes.add_shape(shape_type, left, top, width, height)
        shape.fill.background()
        shape.line.color.rgb = to_rgb(color)
        shape.line.width = Pt(border_width_pt)
        shape.shadow.inherit = False
        if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE and radius_pt > 0:
            short_side = min(rect.w * CANVAS_WIDTH_PT, rect.h * CANVAS_HEIGHT_PT)
            if short_side > 0:
                shape.adjustments[0] = min(0.5, max(0.0, radius_pt / short_side))
        return shape

    def _add_number_badge(
        self,
        pptx_slide: PptxSlide,
        rect: Rect,
        fill: str,
        text: str,
    ) -> None:
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        shape = pptx_slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = to_rgb(fill)
        shape.line.fill.background()
        shape.shadow.inherit = False
        frame = shape.text_frame
        frame.word_wrap = False
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        frame.margin_left = 0
        frame.margin_right = 0
        frame.margin_top = 0
        frame.margin_bottom = 0
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = text
        run.font.size = Pt(11)
        run.font.bold = True
        run.font.color.rgb = to_rgb(self.theme.palette.background)

    def _add_filled_rect(
        self,
        pptx_slide: PptxSlide,
        rect: BleedRect,
        color: str,
        shape_type: MSO_SHAPE = MSO_SHAPE.RECTANGLE,
        *,
        radius_pt: float = 0,
        border_width_pt: float = 0,
        border_color: str | None = None,
    ) -> BaseShape:
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        shape = pptx_slide.shapes.add_shape(shape_type, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = to_rgb(color)
        if border_width_pt > 0 and border_color is not None:
            shape.line.color.rgb = to_rgb(border_color)
            shape.line.width = Pt(border_width_pt)
        else:
            shape.line.fill.background()
        shape.shadow.inherit = False
        if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE and radius_pt > 0:
            # adjustments[0] 是相对短边的圆角比例，夹在 0–0.5
            short_side = min(rect.w * CANVAS_WIDTH_PT, rect.h * CANVAS_HEIGHT_PT)
            if short_side > 0:
                shape.adjustments[0] = min(0.5, max(0.0, radius_pt / short_side))
        return shape

    def _add_box_chrome(self, pptx_slide: PptxSlide, rect: Rect, box: ResolvedBox) -> None:
        if not box.has_chrome and box.radius_pt <= 0:
            return
        if not box.has_fill and not box.has_border:
            return
        shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if box.radius_pt > 0 else MSO_SHAPE.RECTANGLE
        fill = box.fill or self.theme.palette.background
        # 无填充但有边框时用背景色铺底再画线，避免透明形状在部分客户端丢边框
        if box.has_fill:
            color = fill
        else:
            left, top, width, height = (Emu(value) for value in rect.to_emu())
            shape = pptx_slide.shapes.add_shape(shape_type, left, top, width, height)
            shape.fill.background()
            if box.has_border:
                shape.line.color.rgb = to_rgb(box.border_color)  # type: ignore[arg-type]
                shape.line.width = Pt(box.border_width_pt)
            else:
                shape.line.fill.background()
            shape.shadow.inherit = False
            if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE and box.radius_pt > 0:
                short_side = min(rect.w * CANVAS_WIDTH_PT, rect.h * CANVAS_HEIGHT_PT)
                if short_side > 0:
                    shape.adjustments[0] = min(0.5, max(0.0, box.radius_pt / short_side))
            return

        self._add_filled_rect(
            pptx_slide,
            rect,
            color,
            shape_type,
            radius_pt=box.radius_pt,
            border_width_pt=box.border_width_pt,
            border_color=box.border_color,
        )

    def _padded_rect(self, rect: Rect, padding_pt: float) -> Rect:
        if padding_pt <= 0:
            return rect
        pad_x = padding_pt / CANVAS_WIDTH_PT
        pad_y = padding_pt / CANVAS_HEIGHT_PT
        # 内缩后仍保底一点尺寸，避免极端 padding 把文本框压成零
        w = max(0.01, rect.w - pad_x * 2)
        h = max(0.01, rect.h - pad_y * 2)
        return Rect(x=rect.x + pad_x, y=rect.y + pad_y, w=w, h=h)

    def _add_textbox(
        self, pptx_slide: PptxSlide, rect: BleedRect, *, name: str | None = None
    ) -> TextFrame:
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        textbox = pptx_slide.shapes.add_textbox(left, top, width, height)
        if name is not None:
            textbox.name = name
        frame = textbox.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = MSO_ANCHOR.TOP
        frame.margin_left = 0
        frame.margin_right = 0
        frame.margin_top = 0
        frame.margin_bottom = 0
        disable_autofit(frame)
        return frame

    def _apply_align(self, paragraph, align: str | None) -> None:
        if align is None:
            return
        paragraph.alignment = _ALIGN.get(align)

    def _styled_textbox(
        self,
        pptx_slide: PptxSlide,
        rect: Rect,
        style: BlockStyle | None,
    ) -> _TextTarget:
        box = resolve_box(self.theme, style)
        self._add_box_chrome(pptx_slide, rect, box)
        content_rect = self._padded_rect(rect, box.padding_pt)
        return _TextTarget(
            frame=self._add_textbox(pptx_slide, content_rect),
            align=style.align if style else None,
            rect=content_rect,
        )

    def _fit_stack(
        self,
        target: _TextTarget,
        lines: list[tuple[TextStyle, str]],
        *,
        gap_pt: float = 0.0,
    ) -> None:
        """按实测高度给文本框写 normAutofit，兜住排不下的内容。

        度量与溢出告警同源，所以"告警说溢出"和"导出后真的溢出"是一回事：
        告警提醒作者删字，autofit 保证在他动手之前观众也不会看到文字压到框外。
        """
        width_pt = target.rect.w * CANVAS_WIDTH_PT
        available_pt = target.rect.h * CANVAS_HEIGHT_PT
        needed_pt = 0.0
        for index, (style, content) in enumerate(lines):
            if index > 0:
                needed_pt += gap_pt
            needed_pt += measure_text(
                content, style=style, width_pt=width_pt, height_pt=available_pt
            ).height_pt
        shrink_text_to_fit(target.frame, needed_pt=needed_pt, available_pt=available_pt)

    def _render_block(
        self,
        pptx_slide: PptxSlide,
        block: Block,
        *,
        rect: Rect,
        text_style: str | None,
    ) -> None:
        match block:
            case TextBlock():
                self._render_text(pptx_slide, block, rect=rect, text_style=text_style)
            case BulletsBlock():
                self._render_bullets(pptx_slide, block, rect=rect, text_style=text_style)
            case KpiBlock():
                self._render_kpi(pptx_slide, block, rect=rect)
            case TableBlock():
                self._render_table(pptx_slide, block, rect=rect)
            case ImageBlock():
                self._render_image(pptx_slide, block, rect=rect)
            case ChartBlock():
                self._render_chart(pptx_slide, block, rect=rect)
            case CardsBlock():
                self._render_cards(pptx_slide, block, rect=rect)
            case CalloutBlock():
                self._render_callout(pptx_slide, block, rect=rect)

    def _render_text(
        self,
        pptx_slide: PptxSlide,
        block: TextBlock,
        *,
        rect: Rect,
        text_style: str | None,
    ) -> None:
        style = merge_text_style(self.theme, text_style or "body", block.style)
        target = self._styled_textbox(pptx_slide, rect, block.style)
        paragraph = target.frame.paragraphs[0]
        write_paragraph(paragraph, block.text, self.theme, style)
        self._apply_align(paragraph, target.align)
        self._fit_stack(target, [(style, block.text)])

    def _render_bullets(
        self,
        pptx_slide: PptxSlide,
        block: BulletsBlock,
        *,
        rect: Rect,
        text_style: str | None,
    ) -> None:
        style = merge_text_style(self.theme, text_style or "bullet", block.style)
        target = self._styled_textbox(pptx_slide, rect, block.style)

        for index, item in enumerate(block.items):
            paragraph = target.frame.paragraphs[0] if index == 0 else target.frame.add_paragraph()
            if index > 0:
                paragraph.space_before = Pt(BULLET_GAP_PT)
            write_paragraph(paragraph, item, self.theme, style)
            apply_bullet(paragraph, self.theme, BULLET_INDENT_PT)
            self._apply_align(paragraph, target.align)

        available_pt = target.rect.h * CANVAS_HEIGHT_PT
        measured = measure_bullets(
            block.items,
            style=style,
            width_pt=target.rect.w * CANVAS_WIDTH_PT,
            height_pt=available_pt,
        )
        shrink_text_to_fit(target.frame, needed_pt=measured.height_pt, available_pt=available_pt)

    def _render_kpi(self, pptx_slide: PptxSlide, block: KpiBlock, *, rect: Rect) -> None:
        # 与 Web KpiView 默认内边距对齐，避免窄列衬线数字贴边被裁
        box = resolve_box(self.theme, block.style)
        self._add_box_chrome(pptx_slide, rect, box)
        pad_pt = max(box.padding_pt, 14.0)
        content_rect = self._padded_rect(rect, pad_pt)
        target = _TextTarget(
            frame=self._add_textbox(pptx_slide, content_rect),
            align=block.style.align if block.style else None,
            rect=content_rect,
        )

        names = ["kpi_value", "kpi_label"]
        contents = [block.value, block.label]
        if block.note:
            names.append("kpi_note")
            contents.append(block.note)
        # KPI 各行共用同一份元素覆盖（字号/颜色/粗斜体）
        lines = [
            (merge_text_style(self.theme, name, block.style), content)
            for name, content in zip(names, contents, strict=True)
        ]

        for index, (style, content) in enumerate(lines):
            paragraph = target.frame.paragraphs[0] if index == 0 else target.frame.add_paragraph()
            if index > 0:
                paragraph.space_before = Pt(KPI_GAP_PT)
            write_paragraph(paragraph, content, self.theme, style)
            self._apply_align(paragraph, target.align)

        self._fit_stack(target, lines, gap_pt=KPI_GAP_PT)

    def _render_cards(self, pptx_slide: PptxSlide, block: CardsBlock, *, rect: Rect) -> None:
        """卡片横排：surface 底 + subtitle 标题 + body 描述，观感对齐 solid_boxes。"""
        n = len(block.items)
        if n == 0:
            return
        gap = CARD_GAP_PT / CANVAS_WIDTH_PT
        total_gap = gap * max(n - 1, 0)
        card_w = max((rect.w - total_gap) / n, 1e-6)
        pad_x = CARD_PAD_PT / CANVAS_WIDTH_PT
        pad_y = CARD_PAD_PT / CANVAS_HEIGHT_PT
        title_style = merge_text_style(self.theme, "subtitle", block.style)
        body_style = merge_text_style(self.theme, "body", block.style)
        align = block.style.align if block.style else None

        for index, item in enumerate(block.items):
            card = Rect(
                x=rect.x + index * (card_w + gap),
                y=rect.y,
                w=card_w,
                h=rect.h,
            )
            self._add_filled_rect(
                pptx_slide,
                card,
                self.theme.palette.surface,
                MSO_SHAPE.ROUNDED_RECTANGLE,
                radius_pt=BOX_RADIUS_PT,
            )
            content = Rect(
                x=card.x + pad_x,
                y=card.y + pad_y,
                w=max(card.w - 2 * pad_x, 1e-6),
                h=max(card.h - 2 * pad_y, 1e-6),
            )
            target = _TextTarget(
                frame=self._add_textbox(pptx_slide, content), align=align, rect=content
            )
            title_text = f"{item.icon} {item.title}".strip() if item.icon else item.title
            paragraph = target.frame.paragraphs[0]
            write_paragraph(paragraph, title_text, self.theme, title_style)
            self._apply_align(paragraph, align)
            desc = target.frame.add_paragraph()
            desc.space_before = Pt(STACK_GAP_PT)
            write_paragraph(desc, item.desc, self.theme, body_style)
            self._apply_align(desc, align)
            self._fit_stack(
                target,
                [(title_style, title_text), (body_style, item.desc)],
                gap_pt=STACK_GAP_PT,
            )

    def _render_callout(self, pptx_slide: PptxSlide, block: CalloutBlock, *, rect: Rect) -> None:
        """提示条：note 用 accent 浅底 + body；source 用弱底 + caption。"""
        if block.variant == "source":
            fill = mix(self.theme.palette.surface, self.theme.palette.background, 0.35)
            style_name = "caption"
        else:
            fill = mix(self.theme.palette.accent, self.theme.palette.background, 0.18)
            style_name = "body"
        self._add_filled_rect(
            pptx_slide,
            rect,
            fill,
            MSO_SHAPE.ROUNDED_RECTANGLE,
            radius_pt=BOX_RADIUS_PT,
        )
        pad_x = CARD_PAD_PT / CANVAS_WIDTH_PT
        pad_y = (CARD_PAD_PT * 0.75) / CANVAS_HEIGHT_PT
        content = Rect(
            x=rect.x + pad_x,
            y=rect.y + pad_y,
            w=max(rect.w - 2 * pad_x, 1e-6),
            h=max(rect.h - 2 * pad_y, 1e-6),
        )
        target = _TextTarget(
            frame=self._add_textbox(pptx_slide, content),
            align=block.style.align if block.style else None,
            rect=content,
        )
        style = merge_text_style(self.theme, style_name, block.style)
        text = f"{block.icon} {block.text}".strip() if block.icon else block.text
        write_paragraph(target.frame.paragraphs[0], text, self.theme, style)
        self._apply_align(target.frame.paragraphs[0], target.align)
        self._fit_stack(target, [(style, text)])

    def _render_table(self, pptx_slide: PptxSlide, block: TableBlock, *, rect: Rect) -> None:
        left, top, width, height = (Emu(value) for value in rect.to_emu())
        row_count = len(block.rows) + 1
        column_count = len(block.header)

        graphic_frame = pptx_slide.shapes.add_table(
            row_count, column_count, left, top, width, height
        )
        table = graphic_frame.table
        use_plain_style(table)

        header_style = merge_text_style(self.theme, "table_header", block.style)
        cell_style = merge_text_style(self.theme, "table_cell", block.style)
        header_rule = (1.5, self.theme.palette.accent)
        row_rule = (self.theme.shape.border_width_pt, self.theme.palette.line)
        align = block.style.align if block.style else None

        for column_index, title in enumerate(block.header):
            self._write_cell(
                table.cell(0, column_index), title, header_style, header_rule, align=align
            )

        for row_index, row in enumerate(block.rows, start=1):
            for column_index, value in enumerate(row):
                self._write_cell(
                    table.cell(row_index, column_index),
                    value,
                    cell_style,
                    row_rule,
                    align=align,
                )

    def _write_cell(
        self,
        cell,
        content: str,
        style,
        bottom: tuple[float, str],
        *,
        align: str | None = None,
    ) -> None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = to_rgb(self.theme.palette.background)
        cell.margin_left = Pt(12)
        cell.margin_right = Pt(12)
        cell.margin_top = Pt(9)
        cell.margin_bottom = Pt(9)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        set_cell_borders(cell, bottom)

        paragraph = cell.text_frame.paragraphs[0]
        run = paragraph.add_run()
        run.text = content
        apply_text_style(run, self.theme, style)
        self._apply_align(paragraph, align)

    def _apply_image_border(self, picture, style: BlockStyle | None) -> None:
        box = resolve_box(self.theme, style)
        if not box.has_border:
            return
        picture.line.color.rgb = to_rgb(box.border_color)  # type: ignore[arg-type]
        picture.line.width = Pt(box.border_width_pt)

    def _render_image(self, pptx_slide: PptxSlide, block: ImageBlock, *, rect: Rect) -> None:
        """插入真实图片，或在缺失时用形状拼出与 Web 端同构的占位图形。

        真实图片本来就是位图对象，插入后在 PowerPoint 里仍可选中、移动和替换；
        只有占位图用形状拼，避免把"没有图"这件事固化成一张不可编辑的图。
        """
        if block.url:
            key = media_key_from_url(block.url)
            if key is not None:
                try:
                    picture = self._add_cover_picture(pptx_slide, rect, load_image(key))
                    self._apply_image_border(picture, block.style)
                    return
                except Exception as error:
                    logger.warning("图片读取或解码失败，回退占位图：key=%s error=%s", key, error)

        accent = self.theme.palette.accent
        base = self.theme.palette.accent_soft

        self._add_filled_rect(pptx_slide, rect, base)

        outer = Rect(
            x=rect.x + rect.w * 0.44,
            y=rect.y + rect.h * 0.04,
            w=rect.w * 0.6,
            h=rect.h * 0.34,
        )
        inner = Rect(
            x=rect.x + rect.w * 0.56,
            y=rect.y + rect.h * 0.1,
            w=rect.w * 0.36,
            h=rect.h * 0.2,
        )
        # 圆形按 Web 端同一组比例摆放，会略微超出槽位；Web 由 viewBox 裁掉，这里显式收边
        self._add_clipped_oval(pptx_slide, outer, rect, mix(accent, base, 0.22))
        self._add_clipped_oval(pptx_slide, inner, rect, mix(accent, base, 0.32))
        self._add_placeholder_ridge(pptx_slide, rect, mix(accent, base, 0.16))

        rule = Rect(
            x=rect.x + rect.w * 0.08,
            y=rect.y + rect.h * 0.86,
            w=rect.w * 0.18,
            h=rect.h * 0.012,
        )
        self._add_filled_rect(pptx_slide, rule, accent)
        # 占位图用外层 chrome 画边框
        box = resolve_box(self.theme, block.style)
        if box.has_border:
            self._add_box_chrome(
                pptx_slide,
                rect,
                ResolvedBox(
                    fill=None,
                    radius_pt=0,
                    border_width_pt=box.border_width_pt,
                    border_color=box.border_color,
                    padding_pt=0,
                ),
            )

    def _add_clipped_oval(
        self,
        pptx_slide: PptxSlide,
        rect: Rect,
        bounds: Rect,
        color: str,
    ) -> None:
        clipped = rect.clipped_to(bounds)
        if clipped is None:
            return
        self._add_filled_rect(pptx_slide, clipped, color, MSO_SHAPE.OVAL)

    def _add_cover_picture(self, pptx_slide: PptxSlide, rect: Rect, data: bytes):
        """覆盖式裁切，等价于 CSS object-fit: cover，两端观感才一致。"""
        left_pt, top_pt, width_pt, height_pt = rect.to_points()
        left, top, width, height = (Pt(value) for value in (left_pt, top_pt, width_pt, height_pt))
        px_w, px_h = PptxImage.from_blob(data).size
        slot_ratio = width_pt / height_pt
        img_ratio = px_w / px_h

        picture = pptx_slide.shapes.add_picture(BytesIO(data), left, top, width, height)
        if img_ratio > slot_ratio:
            crop = (1 - slot_ratio / img_ratio) / 2
            picture.crop_left = crop
            picture.crop_right = crop
        else:
            crop = (1 - img_ratio / slot_ratio) / 2
            picture.crop_top = crop
            picture.crop_bottom = crop
        return picture

    def _add_placeholder_ridge(self, pptx_slide: PptxSlide, rect: Rect, color: str) -> None:
        """占位图下半部的折线剪影，与 Web 端 SVG 用的是同一组顶点"""
        left, top, width, height = rect.to_points()

        def point(x: float, y: float) -> tuple[int, int]:
            return (
                Emu(round((left + width * x) * EMU_PER_POINT)),
                Emu(round((top + height * y) * EMU_PER_POINT)),
            )

        vertices = [(0.34, 0.52), (0.58, 0.7), (1.0, 0.4), (1.0, 1.0), (0.0, 1.0)]
        builder = pptx_slide.shapes.build_freeform(*point(0.0, 0.78))
        builder.add_line_segments([point(x, y) for x, y in vertices], close=True)

        shape = builder.convert_to_shape()
        shape.fill.solid()
        shape.fill.fore_color.rgb = to_rgb(color)
        shape.line.fill.background()
        shape.shadow.inherit = False

    def _render_chart(self, pptx_slide: PptxSlide, block: ChartBlock, *, rect: Rect) -> None:
        render_chart(pptx_slide, rect, block, self.theme)


def render_deck_to_pptx(
    deck: Deck,
    theme_id: str | None = None,
    *,
    theme: Theme | None = None,
) -> BytesIO:
    resolved = theme or get_theme(theme_id or deck.theme_id)
    return PptxRenderer(resolved).render(deck)
