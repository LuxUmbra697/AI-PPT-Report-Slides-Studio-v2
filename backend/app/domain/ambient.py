"""主题氛围层：每页自动铺一层随主题走的装饰。

主题 JSON 里声明的是"母题"（角部几何、细网格、光晕、巨字水印……），
这里把母题展开成矩形/椭圆/文本三种图元。只用这三种图元，是因为
Web 与 PPTX 都能原生画出它们，导出结果才能和预览完全一致——
不透明度也在这里先混算成实色，避免依赖两端表现不一的 alpha。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.color import mix_hex, normalize_color_value
from app.domain.geometry import (
    CANVAS_HEIGHT_PT,
    CANVAS_WIDTH_PT,
    FULL_CANVAS,
    BleedRect,
    Rect,
)

if TYPE_CHECKING:
    from app.domain.theme import Theme

AmbientScope = Literal["cover", "section", "content"]

# 导出时给氛围形状加的名字前缀：装饰允许出血，导出校验据此放行越界。
AMBIENT_SHAPE_PREFIX = "ambient-"

# 布局 id → 作用域。封面、章节页、正文页各自一套气质，其余布局都算正文。
_SCOPE_BY_LAYOUT: dict[str, AmbientScope] = {"cover": "cover", "section": "section"}

# 氛围层每多一个图元，导出的 PPTX 就多一个形状。
# 网格线与光晕层数必须封顶，否则几十页的稿子会膨胀到打不开。
MAX_GRID_LINES = 24
MAX_GLOW_LAYERS = 6

# 打开 avoid_content 的母题，图元与内容重叠超过自身面积的这个比例就整只丢弃。
# 阈值取小：装饰蹭到正文就是干扰。留一点余量是因为细网格线本身只有半个 pt 宽，
# 归一化后的浮点误差不该让贴着栏边的线被判成压字。
AVOID_OVERLAP_TOLERANCE = 0.05


def scope_of(layout_id: str) -> AmbientScope:
    return _SCOPE_BY_LAYOUT.get(layout_id, "content")


class AmbientShape(BaseModel):
    """氛围层图元。颜色已混算为实色，两端直接画即可。

    矩形可以越出画布：出血由渲染端的画布边界去裁，见 _bleed。
    """

    kind: Literal["rect", "ellipse", "text"]
    rect: BleedRect
    color: str
    text: str | None = None
    font: Literal["display", "body"] | None = None
    size_pt: float | None = None
    weight: int | None = None
    letter_spacing_pt: float = 0.0
    align: Literal["left", "center", "right"] = "left"


class _Motif(BaseModel):
    """母题公共字段：作用域、取色令牌、与背景的混合强度、是否避让内容。"""

    scope: list[AmbientScope] | None = None
    color: str = "accent"
    strength: float = Field(default=0.2, ge=0.0, le=1.0)
    # 打开后，压在内容上的图元会被丢弃而不是画到正文底下。
    # 适合网格与水印这类"结构感"装饰：它们的价值在空隙里，压字只会脏。
    # 光晕一般不开：它就是要笼在内容后面。
    avoid_content: bool = False

    @field_validator("color")
    @classmethod
    def token_or_hex(cls, value: str) -> str:
        return normalize_color_value(value)

    def applies_to(self, scope: AmbientScope) -> bool:
        return self.scope is None or scope in self.scope


class EdgeBand(_Motif):
    """贴着画布某条边的细色带。"""

    motif: Literal["edge_band"]
    edge: Literal["top", "bottom", "left", "right"] = "left"
    thickness_pt: float = Field(default=6.0, gt=0)
    start: float = Field(default=0.0, ge=0.0, le=1.0)
    end: float = Field(default=1.0, ge=0.0, le=1.0)


class CornerBracket(_Motif):
    """角部 L 形几何，由两条细矩形拼成。"""

    motif: Literal["corner_bracket"]
    corner: Literal["top_left", "top_right", "bottom_left", "bottom_right"] = "top_right"
    size_pt: float = Field(default=88.0, gt=0)
    thickness_pt: float = Field(default=1.5, gt=0)
    inset_pt: float = Field(default=22.0, ge=0)


class HairlineGrid(_Motif):
    """细网格：区域内等分的竖线与横线，只画内部分隔线。"""

    motif: Literal["hairline_grid"]
    columns: int = Field(default=0, ge=0, le=MAX_GRID_LINES)
    rows: int = Field(default=0, ge=0, le=MAX_GRID_LINES)
    thickness_pt: float = Field(default=0.75, gt=0)
    area: Rect | None = None


class Glow(_Motif):
    """光晕：同心椭圆逐层加深，越靠中心越浓，用实色台阶逼近径向渐变。"""

    motif: Literal["glow"]
    cx: float = 0.85
    cy: float = 0.16
    radius_pt: float = Field(default=320.0, gt=0)
    layers: int = Field(default=4, ge=1, le=MAX_GLOW_LAYERS)


class Watermark(_Motif):
    """巨字水印。text 留空时用页码（01、02……）。"""

    motif: Literal["watermark"]
    rect: Rect
    text: str | None = None
    size_pt: float = Field(default=180.0, gt=0)
    font: Literal["display", "body"] = "display"
    weight: int = Field(default=700, ge=100, le=900)
    letter_spacing_pt: float = 0.0
    align: Literal["left", "center", "right"] = "left"


AmbientMotif = Annotated[
    EdgeBand | CornerBracket | HairlineGrid | Glow | Watermark,
    Field(discriminator="motif"),
]


def iter_ambient_shapes(
    theme: Theme,
    layout_id: str,
    slide_index: int = 0,
    occupied: Sequence[BleedRect] = (),
) -> list[AmbientShape]:
    """展开当前主题在这一页上的氛围层图元，按声明顺序自下而上。

    occupied 是本页内容块占的位置，供 avoid_content 母题避让；不传就是不避让，
    此时结果只由主题和页序决定，缩略图这类拿不到几何的场景可以省略。
    """
    motifs: list[AmbientMotif] = getattr(theme, "ambient", None) or []
    if not motifs:
        return []

    scope = scope_of(layout_id)
    background = theme.palette.background
    shapes: list[AmbientShape] = []

    for motif in motifs:
        if not motif.applies_to(scope):
            continue
        drawn = _expand(motif, theme, background, slide_index)
        if motif.avoid_content:
            drawn = _keep_clear(drawn, occupied)
        shapes.extend(drawn)

    return shapes


def _expand(
    motif: AmbientMotif, theme: Theme, background: str, slide_index: int
) -> list[AmbientShape]:
    color = mix_hex(theme.color(motif.color), background, motif.strength)
    match motif:
        case EdgeBand():
            return _edge_band(motif, color)
        case CornerBracket():
            return _corner_bracket(motif, color)
        case HairlineGrid():
            return _hairline_grid(motif, color)
        case Glow():
            # 光晕自己按层混色，拿的是原色而非混好的 color
            return _glow(motif, theme.color(motif.color), background)
        case Watermark():
            return _watermark(motif, color, slide_index)


def _keep_clear(shapes: list[AmbientShape], occupied: Sequence[BleedRect]) -> list[AmbientShape]:
    """丢掉压在内容上的图元。

    逐图元判定而非整只母题判定，网格才能只保留落在栏间空隙的那几条线。
    """
    if not occupied:
        return shapes
    return [
        shape for shape in shapes if _covered_ratio(shape.rect, occupied) <= AVOID_OVERLAP_TOLERANCE
    ]


def _covered_ratio(rect: BleedRect, occupied: Sequence[BleedRect]) -> float:
    """内容盖住了自己多大比例。

    内容块出自同一次求解、彼此不重叠，所以逐个累加不会重复计数。
    """
    area = rect.w * rect.h
    if area <= 0:
        return 0.0
    covered = sum(_overlap_area(rect, other) for other in occupied)
    return covered / area


def _overlap_area(a: BleedRect, b: BleedRect) -> float:
    width = min(a.right, b.right) - max(a.x, b.x)
    height = min(a.bottom, b.bottom) - max(a.y, b.y)
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def _clip(x: float, y: float, w: float, h: float) -> Rect | None:
    """矩形按画布收边。轴对齐矩形的外接框求交就是它自己的裁剪，几何无损。"""
    left = max(0.0, x)
    top = max(0.0, y)
    right = min(1.0, x + w)
    bottom = min(1.0, y + h)
    if right <= left or bottom <= top:
        return None
    return Rect(x=left, y=top, w=right - left, h=bottom - top)


def _bleed(x: float, y: float, w: float, h: float) -> BleedRect | None:
    """保留原几何，只丢掉完全落在画布外的图元。

    椭圆不能按外接框收边：那等于把它压扁，本该同心的几层光晕会变成
    一串偏心月牙。让它原样出血，Web 靠 overflow、PPTX 靠幻灯片边界裁。
    """
    if x + w <= 0.0 or y + h <= 0.0 or x >= 1.0 or y >= 1.0:
        return None
    return BleedRect(x=x, y=y, w=w, h=h)


def _fill(
    x: float,
    y: float,
    w: float,
    h: float,
    color: str,
    kind: Literal["rect", "ellipse"] = "rect",
) -> list[AmbientShape]:
    rect = _clip(x, y, w, h) if kind == "rect" else _bleed(x, y, w, h)
    if rect is None:
        return []
    return [AmbientShape(kind=kind, rect=rect, color=color)]


def _edge_band(motif: EdgeBand, color: str) -> list[AmbientShape]:
    start, end = sorted((motif.start, motif.end))
    span = end - start
    if span <= 0:
        return []

    if motif.edge in ("left", "right"):
        w = motif.thickness_pt / CANVAS_WIDTH_PT
        x = 0.0 if motif.edge == "left" else 1.0 - w
        return _fill(x, start, w, span, color)

    h = motif.thickness_pt / CANVAS_HEIGHT_PT
    y = 0.0 if motif.edge == "top" else 1.0 - h
    return _fill(start, y, span, h, color)


def _corner_bracket(motif: CornerBracket, color: str) -> list[AmbientShape]:
    inset_x = motif.inset_pt / CANVAS_WIDTH_PT
    inset_y = motif.inset_pt / CANVAS_HEIGHT_PT
    arm_x = motif.size_pt / CANVAS_WIDTH_PT
    arm_y = motif.size_pt / CANVAS_HEIGHT_PT
    thick_x = motif.thickness_pt / CANVAS_WIDTH_PT
    thick_y = motif.thickness_pt / CANVAS_HEIGHT_PT

    left = "left" in motif.corner
    top = "top" in motif.corner
    x0 = inset_x if left else 1.0 - inset_x - arm_x
    y0 = inset_y if top else 1.0 - inset_y - arm_y
    # 两条臂都要压在 L 的拐角一侧：左角靠左、右角靠右，上角靠上、下角靠下
    arm_v_x = x0 if left else x0 + arm_x - thick_x
    arm_h_y = y0 if top else y0 + arm_y - thick_y

    return [
        *_fill(x0, arm_h_y, arm_x, thick_y, color),
        *_fill(arm_v_x, y0, thick_x, arm_y, color),
    ]


def _hairline_grid(motif: HairlineGrid, color: str) -> list[AmbientShape]:
    area = motif.area or FULL_CANVAS
    w = motif.thickness_pt / CANVAS_WIDTH_PT
    h = motif.thickness_pt / CANVAS_HEIGHT_PT

    shapes: list[AmbientShape] = []
    for index in range(1, motif.columns):
        x = area.x + area.w * index / motif.columns
        shapes.extend(_fill(x - w / 2, area.y, w, area.h, color))
    for index in range(1, motif.rows):
        y = area.y + area.h * index / motif.rows
        shapes.extend(_fill(area.x, y - h / 2, area.w, h, color))
    return shapes


def _glow(motif: Glow, base: str, background: str) -> list[AmbientShape]:
    shapes: list[AmbientShape] = []
    # 从最大最淡的一层画到最小最浓的一层，叠出径向渐变的观感
    for index in range(motif.layers):
        scale = (motif.layers - index) / motif.layers
        ratio = motif.strength * (index + 1) / motif.layers
        rx = motif.radius_pt * scale / CANVAS_WIDTH_PT
        ry = motif.radius_pt * scale / CANVAS_HEIGHT_PT
        shapes.extend(
            _fill(
                motif.cx - rx,
                motif.cy - ry,
                rx * 2,
                ry * 2,
                mix_hex(base, background, ratio),
                kind="ellipse",
            )
        )
    return shapes


def _watermark(motif: Watermark, color: str, slide_index: int) -> list[AmbientShape]:
    return [
        AmbientShape(
            kind="text",
            rect=motif.rect,
            color=color,
            text=motif.text if motif.text else f"{slide_index + 1:02d}",
            font=motif.font,
            size_pt=motif.size_pt,
            weight=motif.weight,
            letter_spacing_pt=motif.letter_spacing_pt,
            align=motif.align,
        )
    ]
