from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.flex_skin import iter_skin_decorations
from app.domain.flex_solve import solve_with_frames


def _two_column_tree(*, preset: str | None) -> FlexContainer:
    return FlexContainer(
        type="column",
        id="root",
        gap_pt=16,
        preset=preset,  # type: ignore[arg-type]
        children=[
            FlexLeaf(id="a", block_id="a"),
            FlexLeaf(id="b", block_id="b"),
        ],
    )


def test_solid_boxes_emits_fill_box_per_child() -> None:
    tree = _two_column_tree(preset="solid_boxes")
    decorations = iter_skin_decorations(tree)
    fills = [d for d in decorations if d.kind == "fill_box"]
    assert len(fills) == 2
    assert all(d.color_token == "surface" for d in fills)
    assert all(d.radius_pt == 8.0 for d in fills)


def test_outline_boxes_emits_outline_per_child() -> None:
    tree = _two_column_tree(preset="outline_boxes")
    decorations = iter_skin_decorations(tree)
    outlines = [d for d in decorations if d.kind == "outline_box"]
    assert len(outlines) == 2
    assert all(d.color_token == "line" for d in outlines)


def test_numbered_steps_badges() -> None:
    tree = _two_column_tree(preset="numbered_steps")
    decorations = iter_skin_decorations(tree)
    badges = [d for d in decorations if d.kind == "number_badge"]
    assert [d.text for d in badges] == ["1", "2"]
    assert all(d.color_token == "accent" for d in badges)


def test_timeline_axis_and_dots() -> None:
    tree = _two_column_tree(preset="timeline")
    decorations = iter_skin_decorations(tree)
    axes = [d for d in decorations if d.kind == "timeline_axis"]
    dots = [d for d in decorations if d.kind == "timeline_dot"]
    assert len(axes) == 1
    assert len(dots) == 2


def test_no_preset_no_decorations() -> None:
    tree = _two_column_tree(preset=None)
    assert iter_skin_decorations(tree) == []


def test_skin_frames_use_outer_rects_before_inset() -> None:
    tree = _two_column_tree(preset="solid_boxes")
    placed, frames = solve_with_frames(tree)
    assert len(frames) == 2
    # 内容区应小于外框（inset）
    by_id = {p.block_id: p.rect for p in placed}
    for frame in frames:
        # column 子叶 block_id 与 leaf 对应：按 index 对齐
        leaf = tree.children[frame.child_index]
        assert leaf.type == "block"
        content = by_id[leaf.block_id]
        assert content.w < frame.rect.w
        assert content.h < frame.rect.h
        assert content.x > frame.rect.x
        assert content.y > frame.rect.y
