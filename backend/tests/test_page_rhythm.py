"""跨页节奏：骨架轮换与 callout 限频。"""

from app.domain.page_rhythm import CALLOUT_EVERY, allows_callout, skeleton_hint


def test_content_pages_rotate_through_every_skeleton() -> None:
    """轮换池要真的转起来，否则十页仍是同一副样子。"""
    hints = {
        skeleton_hint(position, page_role="content", has_visual=False) for position in range(1, 11)
    }
    assert len(hints) >= 5
    assert None not in hints


def test_same_position_always_gets_the_same_skeleton() -> None:
    """单页重试要拿到同一份分配，否则重来一次版面就换了。"""
    first = skeleton_hint(4, page_role="content", has_visual=False)
    assert first == skeleton_hint(4, page_role="content", has_visual=False)


def test_neighbouring_content_pages_differ() -> None:
    for position in range(1, 10):
        left = skeleton_hint(position, page_role="content", has_visual=False)
        right = skeleton_hint(position + 1, page_role="content", has_visual=False)
        assert left != right, position


def test_visual_pages_are_pinned_to_side_by_side() -> None:
    """配图要占住一整栏，不能落到「全宽要点」这类不切栏的骨架上。"""
    for position in range(1, 10):
        hint = skeleton_hint(position, page_role="content", has_visual=True)
        assert hint is not None and "image" in hint


def test_non_content_pages_keep_their_own_layout() -> None:
    for role in ("cover", "toc", "section", "summary"):
        assert skeleton_hint(3, page_role=role, has_visual=False) is None


def test_callout_is_rationed() -> None:
    allowed = [position for position in range(1, 13) if allows_callout(position)]
    assert allowed == list(range(CALLOUT_EVERY, 13, CALLOUT_EVERY))
