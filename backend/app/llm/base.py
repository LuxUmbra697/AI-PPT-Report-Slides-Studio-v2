from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.domain.content import Block
from app.domain.content_density import DEFAULT_CONTENT_DENSITY, DEFAULT_PAGE_ROLE
from app.domain.flex_layout import FlexContainer
from app.domain.outline import OutlineDraft
from app.domain.slide_draft import FlexSlideDraft, SlideDraft
from app.domain.slide_patch import BlockPatch
from app.schemas.project import MAX_DECK_PAGE_COUNT

ContentDensity = Literal["concise", "medium", "detailed"]
PageRole = Literal["cover", "toc", "section", "content", "summary"]


class OutlineSourceSection(BaseModel):
    """带稳定引用编号的来源小节。

    ref 采用「来源编号:小节编号」（如 S1:2），生成结果只能引用这些编号，
    才能在后续正文生成时追溯到真实输入。
    """

    ref: str = Field(min_length=1, max_length=32)
    heading: str | None = None
    level: int = Field(ge=0, le=6)
    text: str
    locator: str


class OutlineGenerationInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    audience: str | None = Field(default=None, max_length=100)
    tone: str = Field(min_length=1, max_length=32)
    # 上限跟着编辑器边界走：页面可以逐页手工增删，重新生成大纲时不该被旧上限卡住
    page_count: int = Field(ge=1, le=MAX_DECK_PAGE_COUNT)
    content_density: ContentDensity = DEFAULT_CONTENT_DENSITY
    sections: list[OutlineSourceSection] = Field(default_factory=list)


class OutlineGenerator(Protocol):
    async def generate(self, payload: OutlineGenerationInput) -> OutlineDraft:
        """根据项目参数与来源小节生成大纲草稿。"""


class SlideGenerationInput(BaseModel):
    """单页正文生成的输入。

    只带这一页需要的上下文：整份 PPT 的基调、本页在大纲里的定位，
    以及本页引用到的来源片段。页面之间因此互不依赖，可以并发生成。
    """

    deck_title: str
    audience: str | None = None
    tone: str
    position: int = Field(ge=1)
    total_pages: int = Field(ge=1)

    page_title: str
    objective: str
    key_points: list[str]
    layout_id: str
    layout_mode: Literal["fixed", "flex"] = "flex"
    content_density: ContentDensity = DEFAULT_CONTENT_DENSITY
    page_role: PageRole = DEFAULT_PAGE_ROLE
    sections: list[OutlineSourceSection] = Field(default_factory=list)
    # 相邻页标题，用来避免内容重复或衔接断裂
    neighbor_titles: list[str] = Field(default_factory=list)
    # 大纲给的配图意图，非空时本页必须产出一个 image 块并以它作 alt
    visual_hint: str | None = Field(default=None, max_length=120)
    # 版式骨架与 callout 配额由编排层按页序分配，见 domain/page_rhythm
    skeleton_hint: str | None = Field(default=None, max_length=200)
    allow_callout: bool = True
    # 修复轮次带上上一轮的结构问题，让模型定向改而不是从头重来
    issues: list[str] = Field(default_factory=list)


class SlideGenerator(Protocol):
    async def generate(self, payload: SlideGenerationInput) -> SlideDraft | FlexSlideDraft:
        """根据大纲页生成单页正文草稿（fixed 槽位或 flex 布局树）。"""


class AiEditHistoryTurn(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=200)


class SlideEditCardItem(BaseModel):
    title: str
    desc: str
    icon: str | None = None


class SlideEditBlockInput(BaseModel):
    """发给模型的可改块快照：不含 locked，也不含 image/chart。"""

    block_id: str
    slot_id: str
    type: Literal["text", "bullets", "kpi", "table", "cards", "callout"]
    text: str | None = None
    items: list[str] | None = None
    value: str | None = None
    label: str | None = None
    note: str | None = None
    header: list[str] | None = None
    rows: list[list[str]] | None = None
    card_items: list[SlideEditCardItem] | None = None
    icon: str | None = None
    variant: Literal["note", "source"] | None = None


class SlideEditInput(BaseModel):
    """单页 AI 局部修改的输入。

    只带当前页未锁定的可写块与槽位容量，模型返回块级操作清单，
    而不是整页重写。
    """

    deck_title: str
    audience: str | None = None
    tone: str
    page_title: str
    layout_id: str
    # flex 页没有固定槽位，提示词不能按 layout_id 去查槽位容量
    layout_mode: Literal["fixed", "flex"] = "fixed"
    instruction: str = Field(min_length=1, max_length=500)
    history: list[AiEditHistoryTurn] = Field(default_factory=list, max_length=5)
    blocks: list[SlideEditBlockInput] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    # 工具改的是整页副本（含 locked），与上面发给模型看的可写块快照分开
    original_blocks: list[Block] = Field(default_factory=list)
    layout_tree: FlexContainer | None = None


class EditOperation(BaseModel):
    op: Literal["replace", "add", "delete", "change_type"] = "replace"
    block_id: str
    slot_id: str = ""
    type: str = "text"
    after_block_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class SlideEditResult(BaseModel):
    operations: list[EditOperation]
    blocks: list[Block]
    layout_tree: FlexContainer | None = None


class SlideEditGenerator(Protocol):
    async def generate(self, payload: SlideEditInput) -> list[BlockPatch] | SlideEditResult:
        """按用户指令修改提案副本，返回块级操作或结构化结果。"""
