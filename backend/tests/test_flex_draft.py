import uuid

from app.domain.flex_layout import FlexContainer, FlexLeaf, iter_leaf_block_ids
from app.domain.flex_normalize import normalize
from app.domain.slide_draft import (
    FlexBulletsContent,
    FlexSlideDraft,
    FlexTextContent,
    SlideDraft,
    TextContent,
    draft_to_slide,
    flex_draft_to_slide,
)


def test_flex_draft_to_slide_rewrites_ids_and_normalizes() -> None:
    slide_id = uuid.uuid4()
    draft = FlexSlideDraft(
        blocks=[
            FlexTextContent(id="title", text="本页标题"),
            FlexBulletsContent(id="body", items=["要点一", "要点二"]),
        ],
        layout_tree=FlexContainer(
            type="column",
            id="root",
            gap_pt=16,
            children=[
                FlexLeaf(id="leaf-title", block_id="title", grow=0.5, text_style="title"),
                FlexLeaf(id="leaf-body", block_id="body", grow=1.5, text_style="bullet"),
            ],
        ),
        speaker_notes="讲稿",
    )

    slide = flex_draft_to_slide(slide_id, draft, fallback_layout_id="bullets")

    assert slide.layout_mode == "flex"
    assert slide.layout_id == "bullets"
    assert slide.layout_tree is not None
    assert {block.id for block in slide.blocks} == {
        f"{slide_id}-title",
        f"{slide_id}-body",
    }
    assert set(iter_leaf_block_ids(slide.layout_tree)) == {
        f"{slide_id}-title",
        f"{slide_id}-body",
    }
    # normalize 幂等：再 normalize 一次应等价
    again = normalize(slide.layout_tree)
    assert again.model_dump(mode="json") == slide.layout_tree.model_dump(mode="json")


def test_flex_draft_to_slide_falls_back_when_tree_mismatches() -> None:
    slide_id = uuid.uuid4()
    draft = FlexSlideDraft(
        blocks=[
            FlexTextContent(id="title", text="标题"),
            FlexBulletsContent(id="body", items=["一"]),
        ],
        # 故意漏掉 body
        layout_tree=FlexContainer(
            type="column",
            id="root",
            children=[FlexLeaf(id="leaf-title", block_id="title")],
        ),
    )

    slide = flex_draft_to_slide(slide_id, draft)

    assert slide.layout_tree is not None
    assert set(iter_leaf_block_ids(slide.layout_tree)) == {
        f"{slide_id}-title",
        f"{slide_id}-body",
    }


def test_draft_to_slide_keeps_fixed_mode() -> None:
    slide_id = uuid.uuid4()
    draft = SlideDraft(blocks=[TextContent(slot_id="title", text="标题")])
    slide = draft_to_slide(slide_id, "cover", draft)
    assert slide.layout_mode == "fixed"
    assert slide.layout_tree is None
