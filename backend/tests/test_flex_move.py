from app.domain.flex_layout import (
    FlexContainer,
    FlexLeaf,
    find_leaf_parent,
    is_spacer,
    move_leaf_preserve_size,
)


def _leaf(block_id: str, *, grow: float = 1.0) -> FlexLeaf:
    return FlexLeaf(id=f"leaf-{block_id}", block_id=block_id, grow=grow)


def test_same_parent_reorder_keeps_grows() -> None:
    root = FlexContainer(
        type="column",
        id="root",
        children=[_leaf("a", grow=1.0), _leaf("b", grow=2.0), _leaf("c", grow=1.0)],
    )
    out = move_leaf_preserve_size(root, "a", "root", 3)
    assert out is not None
    assert [child.grow for child in out.children] == [2.0, 1.0, 1.0]
    assert [child.block_id for child in out.children if isinstance(child, FlexLeaf)] == [
        "b",
        "c",
        "a",
    ]


def test_cross_parent_leaves_spacer_and_keeps_sibling_grow() -> None:
    root = FlexContainer(
        type="row",
        id="root",
        ratios=[50.0, 50.0],
        children=[
            FlexContainer(
                type="column",
                id="col-left",
                children=[_leaf("a", grow=1.0), _leaf("b", grow=2.0)],
            ),
            FlexContainer(
                type="column",
                id="col-right",
                children=[_leaf("c", grow=1.0)],
            ),
        ],
    )
    out = move_leaf_preserve_size(root, "b", "col-right", 1)
    assert out is not None

    left = out.children[0]
    assert isinstance(left, FlexContainer)
    assert len(left.children) == 2
    a = next(child for child in left.children if isinstance(child, FlexLeaf))
    assert a.block_id == "a"
    assert a.grow == 1.0
    spacer = next(child for child in left.children if isinstance(child, FlexContainer))
    assert is_spacer(spacer)
    assert spacer.grow == 2.0

    found = find_leaf_parent(out, "b")
    assert found is not None
    parent, _index, leaf = found
    assert parent.id == "col-right"
    assert leaf.grow == 2.0
    right = out.children[1]
    assert isinstance(right, FlexContainer)
    c = next(
        child for child in right.children if isinstance(child, FlexLeaf) and child.block_id == "c"
    )
    assert c.grow == 1.0
