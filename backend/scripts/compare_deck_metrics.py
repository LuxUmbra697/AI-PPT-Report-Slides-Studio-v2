"""同口径比对文稿的填充率 / 块数 / 块类型 / 皮肤 / 窄栏 / 配图 / 氛围图元。

改动排版或氛围层前后各跑一次，对照输出就知道改动是不是真的落到了产物上。

用法：
  uv run python scripts/compare_deck_metrics.py
  uv run python scripts/compare_deck_metrics.py path/to/deck.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from app.domain.ambient import iter_ambient_shapes
from app.domain.block_style import merge_text_style
from app.domain.content import Block, Deck, Slide
from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode
from app.domain.geometry import CANVAS_WIDTH_PT
from app.domain.quality import content_fill_rate
from app.domain.sample import load_sample_deck
from app.domain.slide_geometry import placed_by_block_id
from app.domain.theme import Theme, get_theme

# 会排出文字行的块类型。image/chart/table 的宽度另有约束，不参与「一行几个字」。
_TEXT_BLOCK_TYPES = frozenset({"text", "bullets", "cards", "callout"})

# 各类文字块在没有 text_style 时的默认样式，与渲染侧一致。
_DEFAULT_STYLE = {"text": "body", "bullets": "bullet", "cards": "body", "callout": "body"}


def _collect_presets(node: FlexNode) -> list[str]:
    if isinstance(node, FlexLeaf):
        return []
    found: list[str] = []
    if isinstance(node, FlexContainer) and node.preset:
        found.append(node.preset)
    for child in node.children:
        found.extend(_collect_presets(child))
    return found


def _chars_per_line(width_pt: float, block: Block, text_style: str | None, theme: Theme) -> float:
    """这一栏一行排得下几个全角字。中文按字号等宽估算，够粗但足以横向对照。"""
    name = text_style or _DEFAULT_STYLE[block.type]
    size_pt = merge_text_style(theme, name, block.style).size_pt
    return width_pt / size_pt if size_pt > 0 else 0.0


def _text_columns(slide: Slide, theme: Theme) -> list[tuple[float, float]]:
    """本页每个文字块的 (栏宽 pt, 一行字数)。"""
    placements = placed_by_block_id(slide)
    columns: list[tuple[float, float]] = []
    for block in slide.blocks:
        placed = placements.get(block.id)
        if placed is None or block.type not in _TEXT_BLOCK_TYPES:
            continue
        width_pt = placed.rect.w * CANVAS_WIDTH_PT
        columns.append((width_pt, _chars_per_line(width_pt, block, placed.text_style, theme)))
    return columns


def summarize(deck: Deck) -> dict:
    theme = get_theme(deck.theme_id)
    type_counts: Counter[str] = Counter()
    skin_counts: Counter[str] = Counter()
    fills: list[float] = []
    blocks_per_slide: list[int] = []
    narrowest_pt: list[float | None] = []
    narrowest_chars: list[float | None] = []
    images_per_slide: list[int] = []
    ambient_per_slide: list[int] = []

    for index, slide in enumerate(deck.slides):
        blocks_per_slide.append(len(slide.blocks))
        for block in slide.blocks:
            type_counts[block.type] += 1
        if slide.layout_tree is not None:
            for preset in _collect_presets(slide.layout_tree):
                skin_counts[preset] += 1
        fill = content_fill_rate(slide)
        if fill is not None:
            fills.append(fill)

        columns = _text_columns(slide, theme)
        narrowest = min(columns, default=None)
        narrowest_pt.append(round(narrowest[0], 1) if narrowest else None)
        narrowest_chars.append(round(narrowest[1], 1) if narrowest else None)
        images_per_slide.append(sum(1 for block in slide.blocks if block.type == "image"))
        occupied = [placed.rect for placed in placed_by_block_id(slide).values()]
        ambient_per_slide.append(len(iter_ambient_shapes(theme, slide.layout_id, index, occupied)))

    measured = [value for value in narrowest_chars if value is not None]
    return {
        "slides": len(deck.slides),
        "theme": deck.theme_id,
        "blocks_per_slide": blocks_per_slide,
        "avg_blocks": sum(blocks_per_slide) / max(len(blocks_per_slide), 1),
        "fill_rates": [round(v, 3) for v in fills],
        "min_fill": round(min(fills), 3) if fills else None,
        "avg_fill": round(sum(fills) / len(fills), 3) if fills else None,
        "block_types": dict(type_counts),
        "skins": dict(skin_counts),
        # 每页最窄文字栏：窄栏是可读性的第一杀手，平均值会把它藏掉
        "narrowest_column_pt": narrowest_pt,
        "narrowest_chars_per_line": narrowest_chars,
        "worst_chars_per_line": round(min(measured), 1) if measured else None,
        "images_per_slide": images_per_slide,
        "slides_with_image": sum(1 for count in images_per_slide if count > 0),
        "ambient_shapes_per_slide": ambient_per_slide,
    }


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        deck = Deck.model_validate(json.loads(path.read_text(encoding="utf-8")))
        label = path.name
    else:
        deck = load_sample_deck()
        label = "sample-deck"
    report = summarize(deck)
    print(f"== {label} ==")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
