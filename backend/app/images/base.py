from typing import Protocol

from pydantic import BaseModel

from app.domain.content import ImageSource


class ImageRequest(BaseModel):
    """一次配图需求。

    prompt 面向生图模型，query 面向图库检索：同一段描述在两边的
    最佳表达并不一样，硬用一份会让其中一边效果明显变差。
    """

    prompt: str
    query: str
    # 槽位宽高比，供应商据此挑选最接近的可用尺寸，减少后续裁切损失
    aspect_ratio: float


class ImageAsset(BaseModel):
    data: bytes
    content_type: str
    source: ImageSource
    # 图库通常要求标注作者，这条信息必须随图片一起保存
    credit: str | None = None


class ImageProvider(Protocol):
    source: ImageSource

    def available(self) -> bool:
        """未配置凭证时返回 False，让调用方直接跳到下一级。"""

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        """取一张图；取不到返回 None，不抛异常打断整条链路。"""
