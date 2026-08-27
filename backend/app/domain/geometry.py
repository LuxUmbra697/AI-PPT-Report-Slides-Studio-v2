from pydantic import BaseModel, Field

# 16:9 基准画布，单位 pt。选 pt 是因为它是 PPTX 的原生单位，
# 导出时无需换算；Web 端按 容器宽度 / CANVAS_WIDTH_PT 缩放即可。
CANVAS_WIDTH_PT = 960.0
CANVAS_HEIGHT_PT = 540.0

EMU_PER_POINT = 12700

# 页面安全区：内容不贴画布边缘，留出呼吸空间。
# 固定布局的槽位本来就内置了边距，flex 布局靠 solver 的默认画布统一给。
PAGE_MARGIN_X_PT = 52.0
PAGE_MARGIN_TOP_PT = 42.0
PAGE_MARGIN_BOTTOM_PT = 44.0


class BleedRect(BaseModel):
    """允许越出画布的归一化矩形。

    只有装饰层用得上：出血的光晕必须靠画布边缘去裁，把外接框收进画布
    等于把椭圆压扁。内容几何一律用 Rect，出界即是错误。
    """

    x: float
    y: float
    w: float = Field(gt=0)
    h: float = Field(gt=0)

    def to_points(self) -> tuple[float, float, float, float]:
        return (
            self.x * CANVAS_WIDTH_PT,
            self.y * CANVAS_HEIGHT_PT,
            self.w * CANVAS_WIDTH_PT,
            self.h * CANVAS_HEIGHT_PT,
        )

    def to_emu(self) -> tuple[int, int, int, int]:
        return tuple(round(value * EMU_PER_POINT) for value in self.to_points())  # type: ignore[return-value]

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


class Rect(BleedRect):
    """归一化矩形，取值 0–1，相对基准画布。

    用归一化而非绝对坐标，是为了让缩略图、全屏预览和导出三者
    共用同一份几何定义，换算只发生在各自的渲染边界上。
    """

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    def clipped_to(self, bounds: "Rect") -> "Rect | None":
        """与 bounds 求交，完全不重叠时返回 None。

        Web 端靠 SVG viewBox 与 overflow 自动裁掉溢出部分，PPTX 形状不会裁剪，
        导出侧必须显式收边，否则装饰图形会画到槽位甚至画布之外。
        """
        x = max(self.x, bounds.x)
        y = max(self.y, bounds.y)
        right = min(self.right, bounds.right)
        bottom = min(self.bottom, bounds.bottom)
        if right <= x or bottom <= y:
            return None
        return Rect(x=x, y=y, w=right - x, h=bottom - y)


FULL_CANVAS = Rect(x=0.0, y=0.0, w=1.0, h=1.0)

# flex solver 的默认求解区域。想让某个块顶到画布边缘要显式声明出血。
SAFE_AREA = Rect(
    x=PAGE_MARGIN_X_PT / CANVAS_WIDTH_PT,
    y=PAGE_MARGIN_TOP_PT / CANVAS_HEIGHT_PT,
    w=(CANVAS_WIDTH_PT - 2 * PAGE_MARGIN_X_PT) / CANVAS_WIDTH_PT,
    h=(CANVAS_HEIGHT_PT - PAGE_MARGIN_TOP_PT - PAGE_MARGIN_BOTTOM_PT) / CANVAS_HEIGHT_PT,
)

SAFE_AREA_WIDTH_PT = SAFE_AREA.w * CANVAS_WIDTH_PT
SAFE_AREA_HEIGHT_PT = SAFE_AREA.h * CANVAS_HEIGHT_PT
