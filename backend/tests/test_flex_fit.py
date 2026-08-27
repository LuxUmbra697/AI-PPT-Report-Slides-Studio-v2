"""内容自适应高度：grow 应随内容多少变化，而不是恒等于预设权重。"""

from __future__ import annotations

from app.domain.content import Block, BulletsBlock, ImageBlock, TextBlock
from app.domain.flex_fit import fit_tree_to_content
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.flex_solve import solve
from app.domain.geometry import CANVAS_HEIGHT_PT, SAFE_AREA
from app.domain.theme import get_theme

THEME = get_theme("ivory")


def _title_body_tree() -> FlexContainer:
    """等价于 title-bullets 预设：标题 0.5 / 正文 1.5。"""
    return FlexContainer(
        type="column",
        id="root",
        gap_pt=16.0,
        children=[
            FlexLeaf(id="leaf-title", block_id="title", grow=0.5, text_style="title"),
            FlexLeaf(id="leaf-body", block_id="body", grow=1.5, text_style="bullet"),
        ],
    )


def _blocks(items: list[str]) -> list[Block]:
    return [
        TextBlock(id="title", slot_id="title", text="演示技巧"),
        BulletsBlock(id="body", slot_id="body", items=items),
    ]


def _heights_pt(tree: FlexContainer) -> dict[str, float]:
    return {p.block_id: p.rect.h * CANVAS_HEIGHT_PT for p in solve(tree)}


def _content_bottom(tree: FlexContainer) -> float:
    return max(p.rect.bottom for p in solve(tree))


def test_short_content_no_longer_fills_the_slot() -> None:
    blocks = _blocks(
        [
            "练习与准备：通过多次排练熟悉内容，控制时间与节奏。",
            "肢体语言：保持眼神交流，运用手势和站姿传递自信。",
            "互动设计：通过提问、讨论或小活动提升听众参与度。",
        ]
    )
    before = _heights_pt(_title_body_tree())
    after = _heights_pt(fit_tree_to_content(_title_body_tree(), blocks, theme=THEME))

    assert after["title"] < before["title"]
    assert after["body"] < before["body"]
    # 标题只有一行，不该比正文还高
    assert after["title"] < after["body"]


def test_more_content_gets_more_height() -> None:
    """有吸收型图片时，富余不摊回正文，正文高度应随内容增长。"""
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=16.0,
        children=[
            FlexLeaf(id="leaf-title", block_id="title", grow=0.5, text_style="title"),
            FlexLeaf(id="leaf-body", block_id="body", grow=1.0, text_style="bullet"),
            FlexLeaf(id="leaf-pic", block_id="pic", grow=1.0),
        ],
    )

    def with_items(items: list[str]) -> list[Block]:
        return [
            *_blocks(items),
            ImageBlock(id="pic", slot_id="visual", alt="配图", source="placeholder", url=None),
        ]

    few = with_items(["要点一：简短说明。", "要点二：简短说明。"])
    many = with_items(
        [
            "练习与准备：通过多次排练熟悉内容，控制时间与节奏，确保每个段落的过渡自然流畅。",
            "肢体语言：保持眼神交流，运用手势和站姿传递自信，避免背对听众或长时间盯着屏幕。",
            "互动设计：通过提问、讨论或小活动提升听众参与度，让单向讲述变成双向交流。",
            "视觉呈现：每页聚焦一个论点，用图表替代大段文字，让听众一眼抓住重点。",
            "应急预案：提前准备设备故障与超时的应对方案，保证现场不因意外中断。",
            "复盘改进：每次结束后记录听众反馈与自我观察，形成可迭代的改进清单。",
        ]
    )
    thin = _heights_pt(fit_tree_to_content(tree, few, theme=THEME))
    thick = _heights_pt(fit_tree_to_content(tree, many, theme=THEME))
    assert thick["body"] > thin["body"]


def test_image_absorbs_surplus_instead_of_creating_blank() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=16.0,
        children=[
            FlexLeaf(id="leaf-title", block_id="title", grow=0.5, text_style="title"),
            FlexLeaf(id="leaf-pic", block_id="pic", grow=1.0),
        ],
    )
    blocks: list[Block] = [
        TextBlock(id="title", slot_id="title", text="演示技巧"),
        ImageBlock(id="pic", slot_id="visual", alt="配图", source="placeholder", url=None),
    ]
    fitted = fit_tree_to_content(tree, blocks, theme=THEME)
    # 图片吃掉富余，安全区依然铺满，不额外造占位块
    assert _content_bottom(fitted) == SAFE_AREA.bottom
    assert {p.block_id for p in solve(fitted)} == {"title", "pic"}


def test_fitted_tree_stays_in_bounds_and_keeps_all_blocks() -> None:
    blocks = _blocks(["要点一。", "要点二。", "要点三。"])
    fitted = fit_tree_to_content(_title_body_tree(), blocks, theme=THEME)
    assert {p.block_id for p in solve(fitted)} == {"title", "body"}
    assert _content_bottom(fitted) <= SAFE_AREA.bottom + 1e-4


def test_unknown_block_ids_do_not_crash() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=16.0,
        children=[FlexLeaf(id="leaf-ghost", block_id="ghost", grow=1.0)],
    )
    fitted = fit_tree_to_content(tree, [], theme=THEME)
    assert [p.block_id for p in solve(fitted)] == ["ghost"]
