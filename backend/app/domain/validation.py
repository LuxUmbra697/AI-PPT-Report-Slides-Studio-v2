from typing import Literal

from pydantic import BaseModel

from app.domain.content import Block, Deck, Slide
from app.domain.geometry import Rect
from app.domain.layout import Slot, get_layout
from app.domain.slide_geometry import placed_by_block_id
from app.domain.theme import Theme, get_theme

IssueSeverity = Literal["error", "warning"]

# 单页校验在缺少主题上下文时的回退；正式路径应传入项目主题
_DEFAULT_THEME_ID = "ivory"


def _resolve_theme(*, theme: Theme | None = None, theme_id: str | None = None) -> Theme:
    if theme is not None:
        return theme
    return get_theme(theme_id or _DEFAULT_THEME_ID)


class StructureIssue(BaseModel):
    """结构问题。

    error 表示内容与布局的契约被破坏，必须阻断导出；
    warning 表示内容偏长可能观感不佳，允许继续。
    code 用于生成 repair 分流：overflow/capacity 不触发砍块重写。
    """

    severity: IssueSeverity
    slide_id: str
    slot_id: str | None
    message: str
    code: str | None = None


def _capacity_issues(slide_id: str, slot: Slot, block: Block) -> list[StructureIssue]:
    capacity = slot.capacity
    issues: list[StructureIssue] = []

    def warn(message: str) -> None:
        issues.append(
            StructureIssue(
                severity="warning",
                slide_id=slide_id,
                slot_id=slot.id,
                message=message,
                code="capacity",
            )
        )

    if block.type == "text" and capacity.max_chars is not None:
        if len(block.text) > capacity.max_chars:
            warn(f"文字 {len(block.text)} 字，超出建议上限 {capacity.max_chars} 字")

    if block.type == "bullets":
        if capacity.max_items is not None and len(block.items) > capacity.max_items:
            warn(f"要点 {len(block.items)} 条，超出建议上限 {capacity.max_items} 条")
        if capacity.max_chars_per_item is not None:
            for index, item in enumerate(block.items):
                if len(item) > capacity.max_chars_per_item:
                    warn(
                        f"第 {index + 1} 条要点 {len(item)} 字，"
                        f"超出单条上限 {capacity.max_chars_per_item} 字"
                    )

    if block.type == "cards":
        if capacity.max_items is not None and len(block.items) > capacity.max_items:
            warn(f"卡片 {len(block.items)} 张，超出建议上限 {capacity.max_items} 张")
        if capacity.max_chars_per_item is not None:
            for index, item in enumerate(block.items):
                total = len(item.title) + len(item.desc)
                if total > capacity.max_chars_per_item:
                    warn(
                        f"第 {index + 1} 张卡片 {total} 字，"
                        f"超出单卡上限 {capacity.max_chars_per_item} 字"
                    )

    if block.type == "callout" and capacity.max_chars is not None:
        if len(block.text) > capacity.max_chars:
            warn(f"提示条 {len(block.text)} 字，超出建议上限 {capacity.max_chars} 字")

    if block.type == "table":
        if capacity.max_columns is not None and len(block.header) > capacity.max_columns:
            warn(f"表格 {len(block.header)} 列，超出上限 {capacity.max_columns} 列")
        if capacity.max_rows is not None and len(block.rows) > capacity.max_rows:
            warn(f"表格 {len(block.rows)} 行，超出上限 {capacity.max_rows} 行")

    if block.type == "chart":
        if capacity.max_series is not None and len(block.series) > capacity.max_series:
            warn(f"图表 {len(block.series)} 条系列，超出上限 {capacity.max_series} 条")
        if capacity.max_categories is not None and len(block.categories) > capacity.max_categories:
            warn(f"图表 {len(block.categories)} 个分类，超出上限 {capacity.max_categories} 个")

    return issues


def _overflow_issues(
    slide_id: str,
    block: Block,
    *,
    rect: Rect,
    text_style: str | None,
    theme: Theme,
    ref_id: str | None = None,
) -> list[StructureIssue]:
    """基于字体度量的文字溢出检测；warning，不阻断。"""
    if block.type not in {"text", "bullets"}:
        return []
    if text_style is None:
        return []

    from app.domain.block_style import content_rect_pt, merge_text_style, resolve_box
    from app.domain.text_metrics import measure_bullets, measure_text

    _x, _y, width_pt, height_pt = rect.to_points()
    box = resolve_box(theme, block.style)
    avail_w, avail_h = content_rect_pt(width_pt, height_pt, padding_pt=box.padding_pt)

    if block.type == "text":
        style = merge_text_style(theme, text_style or "body", block.style)
        result = measure_text(block.text, style=style, width_pt=avail_w, height_pt=avail_h)
        label = "文字"
    else:
        style = merge_text_style(theme, text_style or "bullet", block.style)
        result = measure_bullets(block.items, style=style, width_pt=avail_w, height_pt=avail_h)
        label = "要点"

    if not result.overflows:
        return []

    estimate_note = "（估算值）" if result.used_estimate else ""
    return [
        StructureIssue(
            severity="warning",
            slide_id=slide_id,
            slot_id=ref_id,
            message=(
                f"{label}可能溢出槽位{estimate_note}："
                f"约需 {result.line_count} 行"
                f"（占用 {result.height_pt:.0f} pt / 槽位 {height_pt:.0f} pt）"
            ),
            code="overflow",
        )
    ]


def _validate_fixed_slide(
    slide: Slide, *, theme: Theme
) -> list[StructureIssue]:
    try:
        layout = get_layout(slide.layout_id)
    except KeyError as error:
        return [
            StructureIssue(severity="error", slide_id=slide.id, slot_id=None, message=str(error))
        ]

    issues: list[StructureIssue] = []
    seen: set[str] = set()
    placed = placed_by_block_id(slide)

    for block in slide.blocks:
        slot = layout.slot_by_id(block.slot_id)
        if slot is None:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block.slot_id,
                    message=f"布局 {layout.id} 不存在该槽位",
                )
            )
            continue

        if block.slot_id in seen:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=slot.id,
                    message="同一槽位被多个内容块占用",
                )
            )
        seen.add(block.slot_id)

        if block.type not in slot.accepts:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=slot.id,
                    message=f"槽位只接受 {'、'.join(slot.accepts)}，实际为 {block.type}",
                )
            )
            continue

        # 字数上限约束提示词；度量溢出作为更准确的一层 warning
        issues.extend(_capacity_issues(slide.id, slot, block))
        placement = placed.get(block.id)
        if placement is not None:
            issues.extend(
                _overflow_issues(
                    slide.id,
                    block,
                    rect=placement.rect,
                    text_style=placement.text_style,
                    theme=theme,
                    ref_id=slot.id,
                )
            )

    for slot in layout.slots:
        if slot.required and slot.id not in seen:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=slot.id,
                    message="必填槽位缺少内容",
                )
            )

    return issues


def _validate_flex_slide(slide: Slide, *, theme: Theme) -> list[StructureIssue]:
    from app.domain.flex_layout import iter_leaf_block_ids

    issues: list[StructureIssue] = []
    if slide.layout_tree is None:
        return [
            StructureIssue(
                severity="error",
                slide_id=slide.id,
                slot_id=None,
                message="灵活布局缺少 layout_tree",
            )
        ]

    block_by_id = {block.id: block for block in slide.blocks}
    leaf_ids = iter_leaf_block_ids(slide.layout_tree)
    for block_id in leaf_ids:
        if block_id not in block_by_id:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block_id,
                    message=f"布局树引用了不存在的内容块 {block_id}",
                )
            )

    try:
        placed = placed_by_block_id(slide)
    except Exception as error:
        return issues + [
            StructureIssue(
                severity="error",
                slide_id=slide.id,
                slot_id=None,
                message=f"灵活布局求解失败：{error}",
            )
        ]

    for block in slide.blocks:
        placement = placed.get(block.id)
        if placement is None:
            issues.append(
                StructureIssue(
                    severity="error",
                    slide_id=slide.id,
                    slot_id=block.slot_id or block.id,
                    message=f"内容块 {block.id} 在布局树中没有几何位置",
                )
            )
            continue
        # flex 无槽位 capacity，跳过容量检查；仍做溢出度量
        issues.extend(
            _overflow_issues(
                slide.id,
                block,
                rect=placement.rect,
                text_style=placement.text_style,
                theme=theme,
                ref_id=block.slot_id or block.id,
            )
        )

    return issues


def validate_slide(
    slide: Slide,
    *,
    theme_id: str | None = None,
    theme: Theme | None = None,
) -> list[StructureIssue]:
    try:
        resolved_theme = _resolve_theme(theme=theme, theme_id=theme_id)
    except KeyError as error:
        return [
            StructureIssue(severity="error", slide_id=slide.id, slot_id=None, message=str(error))
        ]

    if slide.layout_mode == "flex":
        return _validate_flex_slide(slide, theme=resolved_theme)
    return _validate_fixed_slide(slide, theme=resolved_theme)


def validate_deck(deck: Deck, *, theme: Theme | None = None) -> list[StructureIssue]:
    resolved = theme
    if resolved is None:
        try:
            resolved = get_theme(deck.theme_id)
        except KeyError:
            resolved = get_theme(_DEFAULT_THEME_ID)
    return [issue for slide in deck.slides for issue in validate_slide(slide, theme=resolved)]


def has_blocking_issue(issues: list[StructureIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
