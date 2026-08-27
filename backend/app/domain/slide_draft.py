import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.content import (
    BulletsBlock,
    CalloutBlock,
    CalloutVariant,
    CardItem,
    CardsBlock,
    ChartBlock,
    ChartKind,
    ChartSeries,
    ImageBlock,
    KpiBlock,
    Slide,
    TableBlock,
    TextBlock,
)
from app.domain.flex_layout import (
    FlexContainer,
    FlexLeaf,
    FlexNode,
    iter_leaf_block_ids,
    restrict_bleed,
)
from app.domain.flex_normalize import normalize
from app.domain.flex_presets import BlockRef, seed_layout_for_blocks

# 模型只负责"往哪个槽位放什么内容"。块 id、锁定标记、图片来源这些
# 由服务端掌握的字段不进入模型契约：让模型编造它们只会带来无谓的校验负担。

# 只有整幅视觉块允许出血到画布边缘
BLEEDABLE_TYPES = frozenset({"image", "chart"})


class SlotContentBase(BaseModel):
    slot_id: str


class TextContent(SlotContentBase):
    type: Literal["text"] = "text"
    text: str


class BulletsContent(SlotContentBase):
    type: Literal["bullets"] = "bullets"
    items: list[str] = Field(min_length=1)


class ImageContent(SlotContentBase):
    type: Literal["image"] = "image"
    # 草稿阶段仅有 alt 占位描述，真实 url/source 由配图流程后续写入
    alt: str


class ChartSeriesContent(BaseModel):
    name: str
    values: list[float] = Field(min_length=1)


class ChartContent(SlotContentBase):
    type: Literal["chart"] = "chart"
    chart_type: ChartKind
    categories: list[str] = Field(min_length=1)
    series: list[ChartSeriesContent] = Field(min_length=1)
    unit: str | None = None


class TableContent(SlotContentBase):
    type: Literal["table"] = "table"
    header: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)


class KpiContent(SlotContentBase):
    type: Literal["kpi"] = "kpi"
    value: str
    label: str
    note: str | None = None


class CardItemContent(BaseModel):
    title: str
    desc: str
    icon: str | None = None


class CardsContent(SlotContentBase):
    type: Literal["cards"] = "cards"
    items: list[CardItemContent] = Field(min_length=1)


class CalloutContent(SlotContentBase):
    type: Literal["callout"] = "callout"
    text: str
    icon: str | None = None
    variant: CalloutVariant = "note"


SlotContent = Annotated[
    TextContent
    | BulletsContent
    | ImageContent
    | ChartContent
    | TableContent
    | KpiContent
    | CardsContent
    | CalloutContent,
    Field(discriminator="type"),
]


class SlideDraft(BaseModel):
    blocks: list[SlotContent] = Field(min_length=1)
    speaker_notes: str | None = None


class FlexBlockBase(BaseModel):
    id: str = Field(min_length=1, max_length=32)


class FlexTextContent(FlexBlockBase):
    type: Literal["text"] = "text"
    text: str


class FlexBulletsContent(FlexBlockBase):
    type: Literal["bullets"] = "bullets"
    items: list[str] = Field(min_length=1)


class FlexImageContent(FlexBlockBase):
    type: Literal["image"] = "image"
    alt: str


class FlexChartContent(FlexBlockBase):
    type: Literal["chart"] = "chart"
    chart_type: ChartKind
    categories: list[str] = Field(min_length=1)
    series: list[ChartSeriesContent] = Field(min_length=1)
    unit: str | None = None


class FlexTableContent(FlexBlockBase):
    type: Literal["table"] = "table"
    header: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(min_length=1)


class FlexKpiContent(FlexBlockBase):
    type: Literal["kpi"] = "kpi"
    value: str
    label: str
    note: str | None = None


class FlexCardsContent(FlexBlockBase):
    type: Literal["cards"] = "cards"
    items: list[CardItemContent] = Field(min_length=1)


class FlexCalloutContent(FlexBlockBase):
    type: Literal["callout"] = "callout"
    text: str
    icon: str | None = None
    variant: CalloutVariant = "note"


FlexBlockContent = Annotated[
    FlexTextContent
    | FlexBulletsContent
    | FlexImageContent
    | FlexChartContent
    | FlexTableContent
    | FlexKpiContent
    | FlexCardsContent
    | FlexCalloutContent,
    Field(discriminator="type"),
]


class FlexSlideDraft(BaseModel):
    blocks: list[FlexBlockContent] = Field(min_length=1)
    layout_tree: FlexContainer
    speaker_notes: str | None = None


def draft_to_slide(slide_id: uuid.UUID, layout_id: str, draft: SlideDraft) -> Slide:
    """把模型产出的槽位内容补齐为完整内容块。"""
    blocks = [_to_block(f"{slide_id}-{content.slot_id}", content) for content in draft.blocks]
    return Slide(
        id=str(slide_id),
        layout_id=layout_id,
        layout_mode="fixed",
        layout_tree=None,
        blocks=blocks,
        speaker_notes=draft.speaker_notes,
    )


def flex_draft_to_slide(
    slide_id: uuid.UUID,
    draft: FlexSlideDraft,
    *,
    fallback_layout_id: str = "bullets",
    use_preset_on_invalid_tree: bool = True,
) -> Slide:
    """把 flex 草稿转为 Slide：本地 id 升格为全局 id，并 normalize 布局树。"""
    id_map = {content.id: f"{slide_id}-{content.id}" for content in draft.blocks}
    blocks = [_to_flex_block(id_map[content.id], content) for content in draft.blocks]

    tree = _rewrite_tree_block_ids(draft.layout_tree, id_map)
    leaf_ids = set(iter_leaf_block_ids(tree))
    block_ids = set(id_map.values())
    if leaf_ids != block_ids:
        if not use_preset_on_invalid_tree:
            raise ValueError(
                f"布局树叶子与内容块不一致：extra={leaf_ids - block_ids} "
                f"missing={block_ids - leaf_ids}"
            )
        refs = [BlockRef(id=block.id, type=block.type) for block in blocks]
        tree = seed_layout_for_blocks(refs)
    else:
        tree = normalize(tree)

    tree = restrict_bleed(tree, {b.id for b in blocks if b.type in BLEEDABLE_TYPES})

    return Slide(
        id=str(slide_id),
        layout_id=fallback_layout_id or "flex",
        layout_mode="flex",
        layout_tree=tree,
        blocks=blocks,
        speaker_notes=draft.speaker_notes,
    )


def _rewrite_tree_block_ids(node: FlexNode, id_map: dict[str, str]) -> FlexNode:
    if isinstance(node, FlexLeaf):
        mapped = id_map.get(node.block_id, node.block_id)
        return node.model_copy(update={"block_id": mapped, "id": f"leaf-{mapped}"})
    assert isinstance(node, FlexContainer)
    return node.model_copy(
        update={"children": [_rewrite_tree_block_ids(child, id_map) for child in node.children]}
    )


def _to_block(block_id: str, content: SlotContent):  # noqa: ANN202
    common = {"id": block_id, "slot_id": content.slot_id}
    match content:
        case TextContent():
            return TextBlock(**common, text=content.text)
        case BulletsContent():
            return BulletsBlock(**common, items=content.items)
        case ImageContent():
            # 没有图源时统一走占位图：图片获取失败不应阻断整页内容
            return ImageBlock(**common, alt=content.alt, source="placeholder")
        case ChartContent():
            return ChartBlock(
                **common,
                chart_type=content.chart_type,
                categories=content.categories,
                series=[ChartSeries(name=s.name, values=s.values) for s in content.series],
                unit=content.unit,
            )
        case TableContent():
            return TableBlock(**common, header=content.header, rows=content.rows)
        case KpiContent():
            return KpiBlock(**common, value=content.value, label=content.label, note=content.note)
        case CardsContent():
            return CardsBlock(
                **common,
                items=[
                    CardItem(title=item.title, desc=item.desc, icon=item.icon)
                    for item in content.items
                ],
            )
        case CalloutContent():
            return CalloutBlock(
                **common,
                text=content.text,
                icon=content.icon,
                variant=content.variant,
            )


def _to_flex_block(block_id: str, content: FlexBlockContent):  # noqa: ANN202
    # flex 约定：slot_id 与 id 对齐
    common = {"id": block_id, "slot_id": block_id}
    match content:
        case FlexTextContent():
            return TextBlock(**common, text=content.text)
        case FlexBulletsContent():
            return BulletsBlock(**common, items=content.items)
        case FlexImageContent():
            return ImageBlock(**common, alt=content.alt, source="placeholder")
        case FlexChartContent():
            return ChartBlock(
                **common,
                chart_type=content.chart_type,
                categories=content.categories,
                series=[ChartSeries(name=s.name, values=s.values) for s in content.series],
                unit=content.unit,
            )
        case FlexTableContent():
            return TableBlock(**common, header=content.header, rows=content.rows)
        case FlexKpiContent():
            return KpiBlock(**common, value=content.value, label=content.label, note=content.note)
        case FlexCardsContent():
            return CardsBlock(
                **common,
                items=[
                    CardItem(title=item.title, desc=item.desc, icon=item.icon)
                    for item in content.items
                ],
            )
        case FlexCalloutContent():
            return CalloutBlock(
                **common,
                text=content.text,
                icon=content.icon,
                variant=content.variant,
            )
