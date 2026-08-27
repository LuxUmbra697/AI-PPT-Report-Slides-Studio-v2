import json
from pathlib import Path

import pytest

from app.core.paths import REPO_ROOT
from app.domain.flex_layout import FlexContainer, FlexLeaf, insert_leaf
from app.domain.flex_normalize import normalize
from app.domain.flex_solve import solve
from app.domain.geometry import (
    CANVAS_HEIGHT_PT,
    CANVAS_WIDTH_PT,
    FULL_CANVAS,
    PAGE_MARGIN_BOTTOM_PT,
    PAGE_MARGIN_TOP_PT,
    PAGE_MARGIN_X_PT,
    SAFE_AREA,
    Rect,
)
from app.domain.slide_geometry import PlacedBlock


def solve_full(tree: FlexContainer) -> list[PlacedBlock]:
    """分配算法自身的用例用整块画布求解，免得断言和页面安全区取值耦合。"""
    return solve(tree, FULL_CANVAS)


def assert_rect(actual: Rect, *, x: float, y: float, w: float, h: float) -> None:
    assert actual.x == pytest.approx(x)
    assert actual.y == pytest.approx(y)
    assert actual.w == pytest.approx(w)
    assert actual.h == pytest.approx(h)


def test_row_splits_by_ratios() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[25, 75],
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b"),
        ],
    )
    placed = {p.block_id: p for p in solve_full(tree)}
    assert_rect(placed["a"].rect, x=0, y=0, w=0.25, h=1)
    assert_rect(placed["b"].rect, x=0.25, y=0, w=0.75, h=1)


def test_column_splits_by_grow() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexLeaf(id="a", block_id="a", grow=1),
            FlexLeaf(id="b", block_id="b", grow=3),
        ],
    )
    placed = {p.block_id: p for p in solve_full(tree)}
    assert_rect(placed["a"].rect, x=0, y=0, w=1, h=0.25)
    assert_rect(placed["b"].rect, x=0, y=0.25, w=1, h=0.75)


def test_row_gap_deducted_from_width() -> None:
    gap_pt = 48.0
    gap_norm = gap_pt / CANVAS_WIDTH_PT
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=gap_pt,
        ratios=[50, 50],
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b"),
        ],
    )
    placed = {p.block_id: p for p in solve_full(tree)}
    half = (1.0 - gap_norm) / 2
    assert_rect(placed["a"].rect, x=0, y=0, w=half, h=1)
    assert_rect(placed["b"].rect, x=half + gap_norm, y=0, w=half, h=1)


def test_column_gap_deducted_from_height() -> None:
    gap_pt = 54.0
    gap_norm = gap_pt / CANVAS_HEIGHT_PT
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=gap_pt,
        children=[
            FlexLeaf(id="a", block_id="a", grow=1),
            FlexLeaf(id="b", block_id="b", grow=1),
        ],
    )
    placed = {p.block_id: p for p in solve_full(tree)}
    half = (1.0 - gap_norm) / 2
    assert_rect(placed["a"].rect, x=0, y=0, w=1, h=half)
    assert_rect(placed["b"].rect, x=0, y=half + gap_norm, w=1, h=half)


@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_column_multi_child_stays_in_bounds(n: int) -> None:
    """三个及以上子项时，间隙只按单份推进，末项必须贴紧父区域底边。"""
    gap_pt = 16.0
    gap_norm = gap_pt / CANVAS_HEIGHT_PT
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=gap_pt,
        children=[FlexLeaf(id=f"l{i}", block_id=f"b{i}", grow=1.0) for i in range(n)],
    )
    rects = [p.rect for p in solve_full(tree)]
    assert len(rects) == n
    assert rects[0].y == pytest.approx(0.0)
    assert rects[-1].y + rects[-1].h == pytest.approx(1.0)
    for index in range(n - 1):
        actual_gap = rects[index + 1].y - (rects[index].y + rects[index].h)
        assert actual_gap == pytest.approx(gap_norm)


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_row_multi_child_stays_in_bounds(n: int) -> None:
    gap_pt = 16.0
    gap_norm = gap_pt / CANVAS_WIDTH_PT
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=gap_pt,
        children=[FlexLeaf(id=f"l{i}", block_id=f"b{i}") for i in range(n)],
    )
    rects = [p.rect for p in solve_full(tree)]
    assert rects[0].x == pytest.approx(0.0)
    assert rects[-1].x + rects[-1].w == pytest.approx(1.0)
    for index in range(n - 1):
        actual_gap = rects[index + 1].x - (rects[index].x + rects[index].w)
        assert actual_gap == pytest.approx(gap_norm)


def test_gap_larger_than_area_compresses_instead_of_overflowing() -> None:
    """间隙总量超过可用高度时压缩间隙，不得把子区域推出父区域。"""
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=400.0,
        children=[FlexLeaf(id=f"l{i}", block_id=f"b{i}") for i in range(4)],
    )
    rects = [p.rect for p in solve_full(tree)]
    assert max(rect.y + rect.h for rect in rects) <= 1.0001


def test_default_canvas_is_page_safe_area() -> None:
    """默认求解区域是安全区，内容不许贴画布边缘。"""
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[FlexLeaf(id="a", block_id="a")],
    )
    rect = solve(tree)[0].rect
    assert_rect(rect, x=SAFE_AREA.x, y=SAFE_AREA.y, w=SAFE_AREA.w, h=SAFE_AREA.h)
    assert rect.x * CANVAS_WIDTH_PT == pytest.approx(PAGE_MARGIN_X_PT)
    assert rect.y * CANVAS_HEIGHT_PT == pytest.approx(PAGE_MARGIN_TOP_PT)
    assert (1.0 - rect.bottom) * CANVAS_HEIGHT_PT == pytest.approx(PAGE_MARGIN_BOTTOM_PT)


def test_bleed_expands_only_the_edges_it_touches() -> None:
    """半幅出血图：贴边的三面顶到画布，与文字相邻的一面留在安全区内。"""
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[50, 50],
        children=[
            FlexLeaf(id="img", block_id="img", bleed=True),
            FlexLeaf(id="text", block_id="text"),
        ],
    )
    placed = {p.block_id: p.rect for p in solve(tree)}
    image = placed["img"]
    seam = SAFE_AREA.x + SAFE_AREA.w / 2
    assert image.x == pytest.approx(0.0)
    assert image.y == pytest.approx(0.0)
    assert image.bottom == pytest.approx(1.0)
    assert image.right == pytest.approx(seam)
    # 相邻的文字块不受影响，仍在安全区内
    assert placed["text"].x == pytest.approx(seam)
    assert placed["text"].right == pytest.approx(SAFE_AREA.right)


def test_bleed_on_middle_child_does_not_expand_sideways() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[30, 40, 30],
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b", bleed=True),
            FlexLeaf(id="c", block_id="c"),
        ],
    )
    middle = {p.block_id: p.rect for p in solve(tree)}["b"]
    assert middle.x > SAFE_AREA.x
    assert middle.right < SAFE_AREA.right
    # 纵向本来就贴着安全区上下边，因此出血到画布
    assert middle.y == pytest.approx(0.0)
    assert middle.bottom == pytest.approx(1.0)


def test_leaf_offset_shifts_position_without_resizing() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexContainer(
                type="row",
                id="row",
                gap_pt=0,
                ratios=[50, 50],
                grow=1,
                children=[
                    FlexLeaf(id="a", block_id="a", offset_x_pt=24.0, offset_y_pt=12.0),
                    FlexLeaf(id="b", block_id="b"),
                ],
            ),
            FlexLeaf(id="c", block_id="c", grow=1),
        ],
    )
    placed = {p.block_id: p.rect for p in solve_full(tree)}
    assert_rect(
        placed["a"],
        x=24.0 / CANVAS_WIDTH_PT,
        y=12.0 / CANVAS_HEIGHT_PT,
        w=0.5,
        h=0.5,
    )
    # 兄弟不受影响
    assert_rect(placed["b"], x=0.5, y=0, w=0.5, h=0.5)
    assert_rect(placed["c"], x=0, y=0.5, w=1, h=0.5)


def test_leaf_offset_is_clamped_inside_canvas() -> None:
    """偏移只挪位置，不允许把块推出画布而阻断导出。"""
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[50, 50],
        children=[
            FlexLeaf(id="a", block_id="a", offset_x_pt=-400.0, offset_y_pt=-400.0),
            FlexLeaf(id="b", block_id="b", offset_x_pt=900.0, offset_y_pt=900.0),
        ],
    )
    placed = {p.block_id: p.rect for p in solve_full(tree)}
    assert_rect(placed["a"], x=0.0, y=0.0, w=0.5, h=1.0)
    assert_rect(placed["b"], x=0.5, y=0.0, w=0.5, h=1.0)
    for rect in placed.values():
        assert rect.x + rect.w <= 1.0001
        assert rect.y + rect.h <= 1.0001


def test_nested_row_column() -> None:
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[40, 60],
        children=[
            FlexLeaf(id="img", block_id="img"),
            FlexContainer(
                type="column",
                id="col",
                gap_pt=0,
                children=[
                    FlexLeaf(id="t", block_id="t", grow=1),
                    FlexLeaf(id="b", block_id="b", grow=1),
                ],
            ),
        ],
    )
    placed = {p.block_id: p for p in solve_full(tree)}
    assert_rect(placed["img"].rect, x=0, y=0, w=0.4, h=1)
    assert_rect(placed["t"].rect, x=0.4, y=0, w=0.6, h=0.5)
    assert_rect(placed["b"].rect, x=0.4, y=0.5, w=0.6, h=0.5)


def test_preset_inset_shrinks_children() -> None:
    inset = 12.0
    tree = FlexContainer(
        type="row",
        id="root",
        gap_pt=0,
        ratios=[50, 50],
        preset="solid_boxes",
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b"),
        ],
    )
    placed = {p.block_id: p for p in solve_full(tree)}
    ix = inset / CANVAS_WIDTH_PT
    iy = inset / CANVAS_HEIGHT_PT
    assert_rect(placed["a"].rect, x=ix, y=iy, w=0.5 - 2 * ix, h=1 - 2 * iy)
    assert_rect(placed["b"].rect, x=0.5 + ix, y=iy, w=0.5 - 2 * ix, h=1 - 2 * iy)


def test_container_grow_in_column() -> None:
    tree = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexLeaf(id="title", block_id="title", grow=1),
            FlexContainer(
                type="row",
                id="row",
                gap_pt=0,
                ratios=[50, 50],
                grow=3,
                children=[
                    FlexLeaf(id="a", block_id="a"),
                    FlexLeaf(id="b", block_id="b"),
                ],
            ),
        ],
    )
    placed = {p.block_id: p for p in solve_full(tree)}
    assert_rect(placed["title"].rect, x=0, y=0, w=1, h=0.25)
    assert_rect(placed["a"].rect, x=0, y=0.25, w=0.5, h=0.75)
    assert_rect(placed["b"].rect, x=0.5, y=0.25, w=0.5, h=0.75)


def _golden_fixtures() -> list[Path]:
    return sorted((Path(REPO_ROOT) / "shared" / "flex-presets").glob("golden*.json"))


@pytest.mark.parametrize("path", _golden_fixtures(), ids=lambda p: p.stem)
def test_golden_fixture_matches_expected_rects(path: Path) -> None:
    """golden 走默认画布，因此同时锁住页面安全区与出血行为。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    tree = FlexContainer.model_validate(payload["tree"])
    placed = {p.block_id: p for p in solve(tree)}
    for block_id, expected in payload["expected_rects"].items():
        assert block_id in placed
        assert_rect(
            placed[block_id].rect,
            x=expected["x"],
            y=expected["y"],
            w=expected["w"],
            h=expected["h"],
        )
    assert placed["title"].text_style == "title"
    assert placed["body"].text_style == "bullet"


def test_insert_leaf_into_spacer_makes_it_content() -> None:
    """插到空白占位里的块必须能被看见：容器要去 spacer 化并拿到可见 grow。"""
    root = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexLeaf(id="a", block_id="a", grow=2),
            FlexContainer(type="column", id="spacer-tail", children=[], gap_pt=0, grow=0.001),
        ],
    )
    spacer = root.children[1]
    assert insert_leaf(root, "spacer-tail", 0, FlexLeaf(id="c", block_id="c"))

    assert not spacer.id.startswith("spacer-")
    assert spacer.grow >= 1.0
    assert [child.block_id for child in spacer.children] == ["c"]

    normalized = normalize(root, clamp_title_grow=False)
    placed = {item.block_id: item for item in solve(normalized)}
    assert placed["c"].rect.h > 0.1


def test_insert_leaf_splits_neighbor_grow_not_all() -> None:
    """插入时只从相邻块拆 grow，其他兄弟高度份额不变。"""
    root = FlexContainer(
        type="column",
        id="root",
        gap_pt=0,
        children=[
            FlexLeaf(id="a", block_id="a", grow=2),
            FlexLeaf(id="b", block_id="b", grow=2),
        ],
    )
    assert insert_leaf(root, "root", 1, FlexLeaf(id="c", block_id="c"))
    assert [child.block_id for child in root.children] == ["a", "c", "b"]
    assert root.children[0].grow == pytest.approx(1.0)
    assert root.children[1].grow == pytest.approx(1.0)
    assert root.children[2].grow == pytest.approx(2.0)
