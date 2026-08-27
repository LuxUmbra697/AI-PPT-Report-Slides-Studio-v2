from app.domain.flex_layout import FlexContainer, iter_leaf_block_ids
from app.domain.slide_pages import (
    BLANK_LAYOUT_ID,
    blank_outline_page,
    blank_slide_content,
    clone_slide_content,
)


def test_blank_page_is_a_valid_outline_page() -> None:
    page = blank_outline_page()
    assert page.layout_id == BLANK_LAYOUT_ID
    assert page.page_role == "content"
    # OutlinePage 要求至少两条要点，少一条会在写回大纲时炸掉
    assert len(page.key_points) >= 2
    assert blank_outline_page().id != page.id


def test_blank_content_puts_title_above_bullets() -> None:
    blocks, tree = blank_slide_content()

    assert [block["type"] for block in blocks] == ["text", "bullets"]
    assert tree.type == "column"
    assert iter_leaf_block_ids(tree) == [block["id"] for block in blocks]
    styles = [leaf.text_style for leaf in tree.children]
    assert styles == ["title", "bullet"]


def test_blank_content_uses_fresh_block_ids() -> None:
    first, _ = blank_slide_content()
    second, _ = blank_slide_content()
    assert {block["id"] for block in first}.isdisjoint(block["id"] for block in second)


def test_clone_rewrites_every_block_id() -> None:
    blocks, tree = blank_slide_content()
    layout_tree = tree.model_dump(mode="json")

    cloned, cloned_tree = clone_slide_content(blocks, layout_tree)

    assert cloned_tree is not None
    old_ids = {block["id"] for block in blocks}
    new_ids = {block["id"] for block in cloned}
    assert old_ids.isdisjoint(new_ids)
    # slot_id 与 id 同值是 flex 约定，改了 id 就得跟着改
    assert [block["slot_id"] for block in cloned] == [block["id"] for block in cloned]
    assert iter_leaf_block_ids(FlexContainer.model_validate(cloned_tree)) == [
        block["id"] for block in cloned
    ]


def test_clone_keeps_content_and_leaves_source_untouched() -> None:
    blocks, tree = blank_slide_content()
    layout_tree = tree.model_dump(mode="json")

    cloned, _ = clone_slide_content(blocks, layout_tree)

    assert [block["type"] for block in cloned] == [block["type"] for block in blocks]
    assert cloned[1]["items"] == blocks[1]["items"]
    cloned[1]["items"].append("改副本不该影响原页")
    assert blocks[1]["items"] != cloned[1]["items"]


def test_clone_renames_leaf_ids_alongside_block_ids() -> None:
    blocks, tree = blank_slide_content()

    _, cloned_tree = clone_slide_content(blocks, tree.model_dump(mode="json"))

    assert cloned_tree is not None
    for leaf in FlexContainer.model_validate(cloned_tree).children:
        assert leaf.id == f"leaf-{leaf.block_id}"


def test_clone_without_layout_tree_keeps_none() -> None:
    blocks, _ = blank_slide_content()

    cloned, cloned_tree = clone_slide_content(blocks, None)

    assert cloned_tree is None
    assert len(cloned) == len(blocks)


def test_clone_keeps_fixed_layout_slot_ids() -> None:
    blocks = [
        {"id": "t1", "slot_id": "title", "type": "text", "text": "标题", "locked": False},
    ]

    cloned, _ = clone_slide_content(blocks, None)

    # fixed 页的 slot_id 是布局定义的槽位名，不跟着 block id 走
    assert cloned[0]["slot_id"] == "title"
    assert cloned[0]["id"] != "t1"
