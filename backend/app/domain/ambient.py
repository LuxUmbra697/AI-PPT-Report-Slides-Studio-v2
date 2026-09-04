"""主题氛围层：每页自动铺一层随主题走的装饰。

主题 JSON 里声明的是"母题"（角部几何、细网格、光晕、巨字水印……），
这里把母题展开成矩形/椭圆/文本三种图元。只用这三种图元，是因为
Web 与 PPTX 都能原生画出它们，导出结果才能和预览完全一致——
不透明度也在这里先混算成实色，避免依赖两端表现不一的 alpha。
"""

from __future__ import annotations

import math
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

    kind: Literal["rect", "round_rect", "ellipse", "text"]
    rect: BleedRect
    color: str
    text: str | None = None
    font: Literal["display", "body"] | None = None
    size_pt: float | None = None
    weight: int | None = None
    letter_spacing_pt: float = 0.0
    align: Literal["left", "center", "right"] = "left"
    rotation: float = 0.0


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


class Scatter(_Motif):
    """确定性散落装饰：花瓣、星芒、圆点、菱形、短划与芯片点。"""

    motif: Literal["scatter"]
    symbol: Literal["petal", "spark", "dot", "diamond", "dash", "chip"] = "dot"
    count: int = Field(default=12, ge=1, le=40)
    seed: int = 17
    area: Rect = FULL_CANVAS
    min_size_pt: float = Field(default=4.0, gt=0)
    max_size_pt: float = Field(default=12.0, gt=0)


class Orbit(_Motif):
    """由小节点组成的椭圆星轨，可在角部或主体周围形成明显构图。"""

    motif: Literal["orbit"]
    cx: float = 0.82
    cy: float = 0.2
    radius_x_pt: float = Field(default=120.0, gt=0)
    radius_y_pt: float = Field(default=72.0, gt=0)
    nodes: int = Field(default=18, ge=4, le=48)
    dot_size_pt: float = Field(default=3.0, gt=0)
    start_deg: float = 0.0


class Sticker(_Motif):
    """圆角标签贴纸：背景与短文本组合，适合封面角标和栏目签。"""

    motif: Literal["sticker"]
    rect: Rect
    text: str
    size_pt: float = Field(default=11.0, gt=0)
    font: Literal["display", "body"] = "body"
    weight: int = Field(default=700, ge=100, le=900)
    align: Literal["left", "center", "right"] = "center"
    rotation: float = 0.0
    text_color: str = "background"

    @field_validator("text_color")
    @classmethod
    def text_token_or_hex(cls, value: str) -> str:
        return normalize_color_value(value)


class FrameMotif(_Motif):
    """四边框架与错位角块，形成海报、档案卡或科技面板构图。"""

    motif: Literal["frame"]
    inset_pt: float = Field(default=24.0, ge=0)
    thickness_pt: float = Field(default=1.0, gt=0)
    corner_size_pt: float = Field(default=18.0, gt=0)


class StripeField(_Motif):
    """一组可旋转的平行色带，用于速度感、纸条感和分区背景。"""

    motif: Literal["stripe_field"]
    area: Rect = FULL_CANVAS
    count: int = Field(default=5, ge=1, le=16)
    thickness_pt: float = Field(default=8.0, gt=0)
    gap_pt: float = Field(default=14.0, ge=0)
    rotation: float = -12.0


AmbientMotif = Annotated[
    EdgeBand
    | CornerBracket
    | HairlineGrid
    | Glow
    | Watermark
    | Scatter
    | Orbit
    | Sticker
    | FrameMotif
    | StripeField,
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
        case Scatter():
            return _scatter(motif, color, slide_index)
        case Orbit():
            return _orbit(motif, color)
        case Sticker():
            return _sticker(motif, color, theme.color(motif.text_color))
        case FrameMotif():
            return _frame(motif, color)
        case StripeField():
            return _stripe_field(motif, color)


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
    kind: Literal["rect", "round_rect", "ellipse"] = "rect",
    rotation: float = 0.0,
) -> list[AmbientShape]:
    rect = _bleed(x, y, w, h) if kind == "ellipse" else _clip(x, y, w, h)
    if rect is None:
        return []
    return [AmbientShape(kind=kind, rect=rect, color=color, rotation=rotation)]


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


def _random_values(seed: int):
    """与前端一致的 32 位 LCG，确保预览和 PPTX 的散点位置完全相同。"""
    state = seed & 0xFFFFFFFF
    while True:
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        yield state / 4294967296.0


def _scatter(motif: Scatter, color: str, slide_index: int) -> list[AmbientShape]:
    rand = _random_values(motif.seed + slide_index * 7919)
    low, high = sorted((motif.min_size_pt, motif.max_size_pt))
    area = motif.area
    shapes: list[AmbientShape] = []

    for _ in range(motif.count):
        size = low + next(rand) * (high - low)
        x = area.x + next(rand) * area.w
        y = area.y + next(rand) * area.h
        rotation = next(rand) * 180.0 - 90.0
        w = size / CANVAS_WIDTH_PT
        h = size / CANVAS_HEIGHT_PT

        if motif.symbol == "petal":
            shapes.extend(
                _fill(x - w / 2, y - h * 0.75, w, h * 1.5, color, "ellipse", rotation)
            )
        elif motif.symbol == "dot":
            shapes.extend(_fill(x - w / 2, y - h / 2, w, h, color, "ellipse"))
        elif motif.symbol == "diamond":
            shapes.extend(
                _fill(
                    x - w / 2,
                    y - h / 2,
                    w,
                    h,
                    color,
                    "round_rect",
                    45 + rotation * 0.15,
                )
            )
        elif motif.symbol == "dash":
            shapes.extend(
                _fill(
                    x - w,
                    y - h * 0.18,
                    w * 2,
                    h * 0.36,
                    color,
                    "round_rect",
                    rotation,
                )
            )
        elif motif.symbol == "chip":
            shapes.extend(_fill(x - w / 2, y - h / 2, w, h, color, "round_rect", rotation * 0.2))
            shapes.extend(_fill(x - w * 0.12, y - h * 0.12, w * 0.24, h * 0.24, color))
        else:
            shapes.extend(
                _fill(
                    x - w,
                    y - h * 0.12,
                    w * 2,
                    h * 0.24,
                    color,
                    "round_rect",
                    rotation,
                )
            )
            shapes.extend(
                _fill(
                    x - w * 0.12,
                    y - h,
                    w * 0.24,
                    h * 2,
                    color,
                    "round_rect",
                    rotation,
                )
            )
            shapes.extend(_fill(x - w * 0.2, y - h * 0.2, w * 0.4, h * 0.4, color, "ellipse"))
    return shapes


def _orbit(motif: Orbit, color: str) -> list[AmbientShape]:
    shapes: list[AmbientShape] = []
    rx = motif.radius_x_pt / CANVAS_WIDTH_PT
    ry = motif.radius_y_pt / CANVAS_HEIGHT_PT
    dot_w = motif.dot_size_pt / CANVAS_WIDTH_PT
    dot_h = motif.dot_size_pt / CANVAS_HEIGHT_PT
    start = math.radians(motif.start_deg)
    for index in range(motif.nodes):
        angle = start + math.tau * index / motif.nodes
        x = motif.cx + math.cos(angle) * rx
        y = motif.cy + math.sin(angle) * ry
        scale = 1.8 if index % 5 == 0 else 1.0
        shapes.extend(
            _fill(
                x - dot_w * scale / 2,
                y - dot_h * scale / 2,
                dot_w * scale,
                dot_h * scale,
                color,
                "ellipse",
            )
        )
    return shapes


def _sticker(motif: Sticker, color: str, text_color: str) -> list[AmbientShape]:
    return [
        AmbientShape(kind="round_rect", rect=motif.rect, color=color, rotation=motif.rotation),
        AmbientShape(
            kind="text",
            rect=motif.rect,
            color=text_color,
            text=motif.text,
            font=motif.font,
            size_pt=motif.size_pt,
            weight=motif.weight,
            align=motif.align,
            rotation=motif.rotation,
        ),
    ]


def _frame(motif: FrameMotif, color: str) -> list[AmbientShape]:
    ix = motif.inset_pt / CANVAS_WIDTH_PT
    iy = motif.inset_pt / CANVAS_HEIGHT_PT
    tx = motif.thickness_pt / CANVAS_WIDTH_PT
    ty = motif.thickness_pt / CANVAS_HEIGHT_PT
    cx = motif.corner_size_pt / CANVAS_WIDTH_PT
    cy = motif.corner_size_pt / CANVAS_HEIGHT_PT
    width = max(0.0, 1.0 - 2 * ix)
    height = max(0.0, 1.0 - 2 * iy)
    shapes = [
        *_fill(ix, iy, width, ty, color),
        *_fill(ix, 1 - iy - ty, width, ty, color),
        *_fill(ix, iy, tx, height, color),
        *_fill(1 - ix - tx, iy, tx, height, color),
    ]
    for x, y in ((ix, iy), (1 - ix - cx, iy), (ix, 1 - iy - cy), (1 - ix - cx, 1 - iy - cy)):
        shapes.extend(_fill(x, y, cx, cy, color, "round_rect"))
    return shapes


def _stripe_field(motif: StripeField, color: str) -> list[AmbientShape]:
    shapes: list[AmbientShape] = []
    thickness = motif.thickness_pt / CANVAS_HEIGHT_PT
    gap = motif.gap_pt / CANVAS_HEIGHT_PT
    total = motif.count * thickness + max(0, motif.count - 1) * gap
    start = motif.area.y + (motif.area.h - total) / 2
    for index in range(motif.count):
        y = start + index * (thickness + gap)
        shapes.extend(
            _fill(
                motif.area.x,
                y,
                motif.area.w,
                thickness,
                color,
                "round_rect",
                motif.rotation,
            )
        )
    return shapes
