from app.domain.content import BulletsBlock, TextBlock
from app.domain.slide_patch import (
    BulletsPatch,
    TextPatch,
    apply_patches,
    filter_patches,
)


def _blocks() -> list[TextBlock | BulletsBlock]:
    return [
        TextBlock(id="t1", slot_id="title", text="原标题", locked=False),
        BulletsBlock(id="b1", slot_id="body", items=["要点一"], locked=True),
        TextBlock(id="t2", slot_id="subtitle", text="副标题", locked=False),
    ]


def test_apply_patches_updates_content_without_mutating_input() -> None:
    blocks = _blocks()
    original_title = blocks[0].text
    patches = [
        TextPatch(block_id="t1", text="新标题"),
        BulletsPatch(block_id="b1", items=["不会生效"]),
    ]

    # 应用前不过滤时仍按 id 替换；本测试只验证拷贝语义
    result = apply_patches(blocks, [patches[0]])

    assert result[0].text == "新标题"
    assert blocks[0].text == original_title
    assert result[0] is not blocks[0]
    assert result[1].items == ["要点一"]


def test_filter_discards_locked_missing_and_type_mismatch() -> None:
    blocks = _blocks()
    patches = [
        TextPatch(block_id="t1", text="新标题"),
        BulletsPatch(block_id="b1", items=["人工改过"]),
        TextPatch(block_id="missing", text="不存在"),
        BulletsPatch(block_id="t2", items=["类型不符"]),
    ]

    filtered = filter_patches(blocks, patches)

    assert [op.block_id for op in filtered.accepted] == ["t1"]
    reasons = {item.block_id: item.reason for item in filtered.discarded}
    assert "人工修改" in reasons["b1"]
    assert reasons["missing"] == "内容块不存在"
    assert "块类型不匹配" in reasons["t2"]


def test_apply_is_idempotent() -> None:
    blocks = _blocks()
    patches = [TextPatch(block_id="t1", text="稳定标题")]

    once = apply_patches(blocks, patches)
    twice = apply_patches(once, patches)

    assert once[0].text == twice[0].text == "稳定标题"
    assert once[0].locked is False
