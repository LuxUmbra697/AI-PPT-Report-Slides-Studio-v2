"""生成后内容质量检查：页面重复、数据无来源、过瘦与空话。

均为 warning，不阻断导出。措辞上只提示用户核对，
不把自动比对描述成事实核验。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.domain.content import Block, Deck, Slide
from app.domain.content_density import (
    contains_empty_phrase,
    effective_block_targets,
    get_profile,
    normalize_density,
    normalize_page_role,
)
from app.domain.flex_solve import solve
from app.domain.geometry import SAFE_AREA
from app.domain.validation import StructureIssue

# 内容底边相对安全区高度低于此比例 → 下半页太空，判 thin
_MIN_FILL_RATE = 0.72

# 抽取「具体数字」：整数、小数、百分号、带千分位
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z\d])"
    r"(?:"
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"  # 1,234 或 1,234.5
    r"|\d+\.\d+"  # 小数
    r"|\d{2,}"  # 至少两位数，避免页码/序号误报
    r")"
    r"(?:%|％)?"
    r"(?![A-Za-z\d])"
)

# 归一化后 Jaccard 相似度阈值：标题或正文高度雷同即告警
_TITLE_SIM_THRESHOLD = 0.85
_BODY_SIM_THRESHOLD = 0.8


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _bigrams(text: str) -> set[str]:
    if len(text) < 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def _similarity(a: str, b: str) -> float:
    left = _bigrams(_normalize(a))
    right = _bigrams(_normalize(b))
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _slide_title_text(slide: Slide, outline_title: str | None = None) -> str:
    if outline_title:
        return outline_title
    for block in slide.blocks:
        if block.type == "text" and block.slot_id in {"title", "heading", "display"}:
            return block.text
    for block in slide.blocks:
        if block.type == "text":
            return block.text
    return ""


def _block_plain_text(block: Block) -> str:
    match block.type:
        case "text":
            return block.text
        case "bullets":
            return "\n".join(block.items)
        case "kpi":
            parts = [block.value, block.label]
            if block.note:
                parts.append(block.note)
            return "\n".join(parts)
        case "table":
            rows = ["\t".join(block.header), *["\t".join(row) for row in block.rows]]
            return "\n".join(rows)
        case "chart":
            series = " ".join(
                f"{item.name}:{'/'.join(str(v) for v in item.values)}" for item in block.series
            )
            return f"{' '.join(block.categories)} {series}"
        case "image":
            return block.alt
        case "cards":
            return "\n".join(
                f"{item.icon + ' ' if item.icon else ''}{item.title}\n{item.desc}"
                for item in block.items
            )
        case "callout":
            prefix = f"{block.icon} " if block.icon else ""
            return f"{prefix}{block.text}"
        case _:
            return ""


def _slide_body_text(slide: Slide) -> str:
    return "\n".join(_block_plain_text(block) for block in slide.blocks)


def check_duplicate_pages(
    deck: Deck,
    *,
    slide_titles: Mapping[str, str] | None = None,
) -> list[StructureIssue]:
    """检测整份 PPT 中标题或正文高度雷同的页面。"""
    issues: list[StructureIssue] = []
    titles = slide_titles or {}
    slides = deck.slides
    for i, left in enumerate(slides):
        left_title = _slide_title_text(left, titles.get(left.id))
        left_body = _slide_body_text(left)
        for right in slides[i + 1 :]:
            right_title = _slide_title_text(right, titles.get(right.id))
            right_body = _slide_body_text(right)

            title_sim = _similarity(left_title, right_title) if left_title and right_title else 0.0
            body_sim = _similarity(left_body, right_body) if left_body and right_body else 0.0

            if title_sim >= _TITLE_SIM_THRESHOLD and left_title:
                issues.append(
                    StructureIssue(
                        severity="warning",
                        slide_id=right.id,
                        slot_id=None,
                        message=(
                            f"本页标题与另一页（{left.id}）高度相似"
                            f"（相似度 {title_sim:.0%}），请确认是否重复"
                        ),
                    )
                )
            elif body_sim >= _BODY_SIM_THRESHOLD and left_body:
                issues.append(
                    StructureIssue(
                        severity="warning",
                        slide_id=right.id,
                        slot_id=None,
                        message=(
                            f"本页正文与另一页（{left.id}）高度相似"
                            f"（相似度 {body_sim:.0%}），请确认是否重复"
                        ),
                    )
                )
    return issues


def extract_numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text)


def _number_variants(token: str) -> set[str]:
    """生成便于在来源里查找的数字变体。"""
    raw = token.replace("％", "%").strip()
    variants = {raw, raw.replace(",", ""), raw.replace("%", ""), raw.rstrip("%")}
    # 去掉前导零以外的形式：12.0 ↔ 12
    bare = raw.replace(",", "").rstrip("%")
    try:
        value = float(bare)
        if value.is_integer():
            variants.add(str(int(value)))
        variants.add(bare)
    except ValueError:
        pass
    return {item for item in variants if item}


def check_unsourced_numbers(
    slide: Slide,
    source_text: str,
) -> list[StructureIssue]:
    """页面出现具体数字但引用材料中找不到对应数据时告警。

    这是提示用户核对来源覆盖情况，不是事实准确性核验。
    """
    body = _slide_body_text(slide)
    numbers = extract_numbers(body)
    if not numbers:
        return []

    haystack = source_text or ""
    # 来源文本去掉千分位逗号，便于匹配
    compact = haystack.replace(",", "")
    missing: list[str] = []
    seen: set[str] = set()
    for token in numbers:
        if token in seen:
            continue
        seen.add(token)
        variants = _number_variants(token)
        found = any(variant and (variant in haystack or variant in compact) for variant in variants)
        if not found:
            missing.append(token)

    if not missing:
        return []

    shown = "、".join(missing[:5])
    more = f" 等 {len(missing)} 处" if len(missing) > 5 else ""
    return [
        StructureIssue(
            severity="warning",
            slide_id=slide.id,
            slot_id=None,
            message=(
                f"本页出现数字 {shown}{more}，"
                f"在该页引用的输入材料中未找到对应片段，请核对数据来源是否覆盖"
            ),
        )
    ]


def check_empty_phrases(slide: Slide) -> list[StructureIssue]:
    """检出占位/空话文案。"""
    hits: list[str] = []
    for block in slide.blocks:
        text = _block_plain_text(block)
        if contains_empty_phrase(text):
            hits.append(block.slot_id or block.id)
    if not hits:
        return []
    shown = "、".join(hits[:4])
    return [
        StructureIssue(
            severity="warning",
            slide_id=slide.id,
            slot_id=hits[0],
            message=f"内容含空话或占位表述（块 {shown}），请改成具体结论",
            code="empty_phrase",
        )
    ]


def check_thin_content(
    slide: Slide,
    *,
    content_density: str | None = None,
    page_role: str | None = None,
) -> list[StructureIssue]:
    """相对文字量档位检测过瘦页面（块数/要点偏少或要点过短）。"""
    density = normalize_density(content_density)
    role = normalize_page_role(page_role)
    # 封面/分隔允许更少块
    if role in {"cover", "section"}:
        return []

    profile = get_profile(density)
    min_blocks, _max_blocks = effective_block_targets(density, role)
    issues: list[StructureIssue] = []

    # 固定布局块数受槽位上限约束，块数下限只约束 flex 多元素页
    if slide.layout_mode == "flex" and len(slide.blocks) < min_blocks:
        issues.append(
            StructureIssue(
                severity="warning",
                slide_id=slide.id,
                slot_id=None,
                message=(
                    f"内容偏瘦：当前 {len(slide.blocks)} 个内容块，"
                    f"{profile.label}档建议至少 {min_blocks} 块（多元素组合）"
                ),
                code="thin_content",
            )
        )

    bullet_blocks = [block for block in slide.blocks if block.type == "bullets"]
    if (
        slide.layout_mode == "flex"
        and role == "content"
        and not bullet_blocks
        and density in {"medium", "detailed"}
    ):
        issues.append(
            StructureIssue(
                severity="warning",
                slide_id=slide.id,
                slot_id=None,
                message=f"内容偏瘦：{profile.label}档内容页应包含要点列表",
                code="thin_content",
            )
        )

    b_lo, _b_hi = profile.target_bullets
    for block in bullet_blocks:
        if len(block.items) < b_lo:
            issues.append(
                StructureIssue(
                    severity="warning",
                    slide_id=slide.id,
                    slot_id=block.slot_id,
                    message=(
                        f"要点偏少：{len(block.items)} 条，"
                        f"{profile.label}档建议至少 {b_lo} 条"
                    ),
                    code="thin_content",
                )
            )
        short = [item for item in block.items if len(item.strip()) < profile.min_chars_per_bullet]
        if short and len(short) >= max(1, len(block.items) // 2):
            issues.append(
                StructureIssue(
                    severity="warning",
                    slide_id=slide.id,
                    slot_id=block.slot_id,
                    message=(
                        f"要点过短：多条不足 {profile.min_chars_per_bullet} 字，"
                        "请补充具体结论或事实"
                    ),
                    code="thin_content",
                )
            )

    fill = content_fill_rate(slide)
    if (
        slide.layout_mode == "flex"
        and role == "content"
        and fill is not None
        and fill < _MIN_FILL_RATE
    ):
        issues.append(
            StructureIssue(
                severity="warning",
                slide_id=slide.id,
                slot_id=None,
                message=(
                    f"页面下半部空白（填充率 {fill:.0%}），"
                    "建议补要点、KPI、卡片或视觉块充实版面"
                ),
                code="thin_content",
            )
        )

    # 去重同 code+slot
    deduped: list[StructureIssue] = []
    seen: set[tuple[str | None, str]] = set()
    for issue in issues:
        key = (issue.slot_id, issue.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def content_fill_rate(slide: Slide) -> float | None:
    """内容底边相对安全区高度的填充率；非 flex 或无树时返回 None。"""
    if slide.layout_mode != "flex" or slide.layout_tree is None:
        return None
    placed = solve(slide.layout_tree)
    if not placed:
        return 0.0
    bottom = max(item.rect.bottom for item in placed)
    # 相对安全区：从 SAFE_AREA.y 起算到内容底边
    span = SAFE_AREA.h
    if span <= 0:
        return None
    return max(0.0, min(1.0, (bottom - SAFE_AREA.y) / span))


def check_slide_richness(
    slide: Slide,
    *,
    content_density: str | None = None,
    page_role: str | None = None,
) -> list[StructureIssue]:
    return [
        *check_empty_phrases(slide),
        *check_thin_content(slide, content_density=content_density, page_role=page_role),
    ]


def check_deck_content_quality(
    deck: Deck,
    *,
    slide_titles: Mapping[str, str] | None = None,
    slide_sources: Mapping[str, str] | None = None,
    content_density: str | None = None,
    slide_roles: Mapping[str, str] | None = None,
) -> list[StructureIssue]:
    """生成后内容质量检查（重复 + 无来源 + 过瘦/空话）。"""
    issues = check_duplicate_pages(deck, slide_titles=slide_titles)
    sources = slide_sources or {}
    roles = slide_roles or {}
    for slide in deck.slides:
        issues.extend(check_unsourced_numbers(slide, sources.get(slide.id, "")))
        issues.extend(
            check_slide_richness(
                slide,
                content_density=content_density,
                page_role=roles.get(slide.id),
            )
        )
    return issues


def is_repair_worthy(issue: StructureIssue) -> bool:
    """生成回路是否应因该问题触发充实/结构修复。

    溢出与容量超限只提示，不触发整页重写砍块。
    """
    if issue.severity == "error":
        return True
    if issue.code in {"thin_content", "empty_phrase"}:
        return True
    if issue.code in {"overflow", "capacity"}:
        return False
    # 未标注 code 的 warning 默认不修（避免容量类旧路径）
    return False
