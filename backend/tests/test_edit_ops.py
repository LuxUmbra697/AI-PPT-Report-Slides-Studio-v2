import pytest

from app.domain.content import TextBlock
from app.domain.edit_ops import (
    EditStructureError,
    add_block,
    change_block_type,
    delete_block,
    previous_block_id,
)
from app.domain.flex_layout import FlexContainer, FlexLeaf, find_leaf_parent, iter_leaf_block_ids


def _tree() -> FlexContainer:
    return FlexContainer(
        type="column",
        id="root",
        children=[
            FlexLeaf(id="leaf-a", block_id="a", grow=1),
            FlexLeaf(id="leaf-b", block_id="b", grow=1),
        ],
    )


def _blocks(*, locked_a: bool = False) -> list[TextBlock]:
    return [
        TextBlock(id="a", slot_id="a", text="第一段", locked=locked_a),
        TextBlock(id="b", slot_id="b", text="第二段", locked=False),
    ]


def test_add_block_inserts_after_anchor() -> None:
    blocks, tree, created = add_block(
        _blocks(),
        _tree(),
        block_type="text",
        after_block_id="a",
        content={"text": "插在中间"},
    )
    assert created.text == "插在中间"
    assert created.id in {block.id for block in blocks}
    assert iter_leaf_block_ids(tree) == ["a", created.id, "b"]
    assert previous_block_id(tree, created.id) == "a"


def test_delete_block_keeps_tree_in_sync() -> None:
    blocks, tree, removed = delete_block(_blocks(), _tree(), "b")
    assert removed.id == "b"
    assert [block.id for block in blocks] == ["a"]
    assert iter_leaf_block_ids(tree) == ["a"]


def test_delete_locked_block_is_rejected() -> None:
    with pytest.raises(EditStructureError, match="人工修改"):
        delete_block(_blocks(locked_a=True), _tree(), "a")


def test_delete_last_block_is_rejected() -> None:
    blocks, tree, _ = delete_block(_blocks(), _tree(), "b")
    with pytest.raises(EditStructureError, match="至少保留"):
        delete_block(blocks, tree, "a")


def test_change_type_keeps_id_and_updates_leaf() -> None:
    blocks, tree, old, updated = change_block_type(
        _blocks(),
        _tree(),
        block_id="b",
        new_type="bullets",
        content={"items": ["新要点"]},
    )
    assert old.type == "text"
    assert updated.id == "b"
    assert updated.type == "bullets"
    assert updated.items == ["新要点"]
    assert [block.id for block in blocks] == ["a", "b"]
    found = find_leaf_parent(tree, "b")
    assert found is not None
    _parent, _index, leaf = found
    assert leaf.text_style == "bullet"
