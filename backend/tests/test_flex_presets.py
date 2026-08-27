from app.domain.flex_layout import iter_leaf_block_ids
from app.domain.flex_presets import (
    BlockRef,
    adapt_preset_to_blocks,
    load_presets,
    seed_layout_for_blocks,
)


def test_load_presets_excludes_golden() -> None:
    presets = load_presets()
    assert presets
    assert all(not preset.id.startswith("golden") for preset in presets)
    ids = {preset.id for preset in presets}
    assert "title-bullets" in ids
    assert "image-text" in ids
    assert "three-columns" in ids
    assert "two-column-bullets" in ids
    assert "title-bullets-kpi" in ids
    assert "title-two-col-visual" in ids
    assert "title-kpi-body-visual" in ids


def test_adapt_preset_maps_all_blocks() -> None:
    presets = {preset.id: preset for preset in load_presets()}
    blocks = [
        BlockRef(id="t1", type="text"),
        BlockRef(id="b1", type="bullets"),
        BlockRef(id="img", type="image"),
    ]
    tree = adapt_preset_to_blocks(presets["image-text"].tree, list(blocks))
    assert set(iter_leaf_block_ids(tree)) == {"t1", "b1", "img"}


def test_seed_layout_for_title_bullets() -> None:
    blocks = [BlockRef(id="a", type="text"), BlockRef(id="b", type="bullets")]
    tree = seed_layout_for_blocks(blocks)
    assert set(iter_leaf_block_ids(tree)) == {"a", "b"}
