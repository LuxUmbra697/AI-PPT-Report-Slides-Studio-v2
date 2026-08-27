import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.block_style import BlockStyle
from app.domain.content import Block
from app.domain.flex_layout import FlexContainer
from app.domain.slide_patch import BlockPatch
from app.domain.validation import StructureIssue

SlideStatus = Literal["pending", "generating", "ready", "failed"]
# idle 表示还没生成过；partial 表示有页未就绪且当前没有任务在跑，可逐页重试。
# 取消不单列状态：取消后剩下的就是「部分完成」，多一个状态只会让前端多分支。
DeckStatus = Literal["idle", "generating", "ready", "partial"]


class SlidePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outline_page_id: uuid.UUID
    position: int
    layout_id: str
    layout_mode: Literal["fixed", "flex"] = "flex"
    layout_tree: FlexContainer | None = None
    title: str
    status: SlideStatus
    blocks: list[Block]
    speaker_notes: str | None
    issues: list[StructureIssue]
    error: str | None
    revision: int
    updated_at: datetime


class DeckPublic(BaseModel):
    project_id: uuid.UUID
    title: str
    theme_id: str
    status: DeckStatus
    total: int
    ready: int
    failed: int
    slides: list[SlidePublic]


class DeckGenerateRequest(BaseModel):
    # 默认续跑：已就绪的页不会白白重来一遍，这也是断点恢复的入口
    regenerate_all: bool = False


class DeckGenerateAccepted(BaseModel):
    job_id: str
    status: Literal["generating"] = "generating"
    total: int
    pending: int


class DeckEvent(BaseModel):
    type: Literal[
        "snapshot",
        "slide_started",
        "slide_completed",
        "slide_failed",
        "completed",
        "cancelled",
        "failed",
    ]
    status: DeckStatus
    progress: int = Field(ge=0, le=100)
    message: str
    slide_id: uuid.UUID | None = None
    position: int | None = None
    ready: int = 0
    failed: int = 0
    total: int = 0


class TextBlockUpdate(BaseModel):
    type: Literal["text"]
    revision: int
    text: str


class BulletsBlockUpdate(BaseModel):
    type: Literal["bullets"]
    revision: int
    items: list[str]


class KpiBlockUpdate(BaseModel):
    type: Literal["kpi"]
    revision: int
    value: str
    label: str
    note: str | None = None


class TableBlockUpdate(BaseModel):
    type: Literal["table"]
    revision: int
    header: list[str]
    rows: list[list[str]]


class ChartSeriesUpdate(BaseModel):
    name: str
    values: list[float]


class ChartBlockUpdate(BaseModel):
    type: Literal["chart"]
    revision: int
    chart_type: Literal["bar", "column", "line", "pie"]
    categories: list[str]
    series: list[ChartSeriesUpdate]
    unit: str | None = None


class CardItemUpdate(BaseModel):
    title: str
    desc: str
    icon: str | None = None


class CardsBlockUpdate(BaseModel):
    type: Literal["cards"]
    revision: int
    items: list[CardItemUpdate]


class CalloutBlockUpdate(BaseModel):
    type: Literal["callout"]
    revision: int
    text: str
    icon: str | None = None
    variant: Literal["note", "source"] = "note"


BlockUpdate = Annotated[
    TextBlockUpdate
    | BulletsBlockUpdate
    | KpiBlockUpdate
    | TableBlockUpdate
    | ChartBlockUpdate
    | CardsBlockUpdate
    | CalloutBlockUpdate,
    Field(discriminator="type"),
]


class BlockStyleUpdate(BaseModel):
    """元素级样式覆盖；style 为 null 表示清除该元素的全部微调。"""

    revision: int
    style: BlockStyle | None = None


class BlockCreateRequest(BaseModel):
    revision: int
    type: Literal[
        "text", "bullets", "image", "chart", "table", "kpi", "cards", "callout"
    ]
    parent_id: str
    index: int = 0


class BlockDeleteRequest(BaseModel):
    revision: int


class FlexLayoutUpdateRequest(BaseModel):
    revision: int
    layout_tree: FlexContainer


class FlexStateUpdateRequest(BaseModel):
    """整页恢复灵活布局状态（撤销/重做增删块与换排布用）。"""

    revision: int
    blocks: list[Block]
    layout_tree: FlexContainer


class UnlockFlexRequest(BaseModel):
    revision: int


class RelayoutRequest(BaseModel):
    revision: int


class RelayoutCandidate(BaseModel):
    id: str
    layout_tree: FlexContainer


class RelayoutProposalPublic(BaseModel):
    revision: int
    candidates: list[RelayoutCandidate]


class RelayoutApplyRequest(BaseModel):
    revision: int
    layout_tree: FlexContainer


class SlideOrderRequest(BaseModel):
    slide_ids: list[uuid.UUID]


class SlideInsertRequest(BaseModel):
    """在指定页之后插入空白页；null 表示追加到末尾。"""

    after_slide_id: uuid.UUID | None = None


class DeckPageResult(BaseModel):
    """整页增删复制的结果。

    增删都会改动多页 position，返回整份 deck 让前端一次换掉缓存；slide_id 是
    操作后应当选中的页（新页，或删除后的邻页）。
    """

    deck: DeckPublic
    slide_id: uuid.UUID | None = None


class LayoutSwitchRequest(BaseModel):
    layout_id: str
    revision: int


class LayoutCandidatePublic(BaseModel):
    layout_id: str
    name: str
    usage: str
    compatible: bool
    reason: str | None = None
    current: bool = False


class AiEditHistoryTurn(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=200)


class AiEditRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)
    revision: int
    history: list[AiEditHistoryTurn] = Field(default_factory=list, max_length=5)

    @field_validator("instruction", mode="before")
    @classmethod
    def strip_instruction(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class AiEditOperationPublic(BaseModel):
    op: Literal["replace", "add", "delete", "change_type"] = "replace"
    block_id: str
    slot_id: str
    type: str
    after_block_id: str | None = None
    before: dict | None = None
    after: dict | None = None


class DiscardedOperationPublic(BaseModel):
    block_id: str
    reason: str


class AiEditProposalPublic(BaseModel):
    revision: int
    operations: list[AiEditOperationPublic]
    discarded: list[DiscardedOperationPublic]
    warnings: list[StructureIssue]


class AiEditApplyRequest(BaseModel):
    revision: int
    op: Literal["replace", "add", "delete", "change_type"] = "replace"
    block_id: str
    after_block_id: str | None = None
    side: Literal["before", "after"] = "after"
    replace: BlockPatch | None = None
    block: dict | None = None
